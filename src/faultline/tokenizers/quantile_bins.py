"""Per-channel quantile binning of telemetry values.

A continuous SCADA channel becomes a token by falling into one of ``n_bins``
quantile bins. Quantiles, not fixed-width bins, because power and temperature
channels are heavily skewed: fixed widths would spend most of the vocabulary on
values that occur a few times a year.

Two rules matter for the science and are enforced here:

* Edges are fitted on the **training split only**. Fitting on the whole record
  leaks the held-out period's distribution into the vocabulary, which would flatter
  every drift result the project reports.
* Missing values are never imputed at this layer. They map to a dedicated sentinel
  and become the ``<nan>`` token, because missingness is itself a shift signal
  (ADR-0006).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from faultline.config import config_hash
from faultline.logging_utils import get_logger

logger = get_logger(__name__)

#: Local bin identifier reserved for a missing value.
MISSING_BIN = -1


class QuantileBinTokenizer:
    """Maps channel values to per-channel quantile bin identifiers.

    Attributes:
        channels: Channel names in fitted order; the order fixes channel identifiers.
        n_bins: Number of bins per channel.
        edges: Fitted bin edges per channel, ``n_bins + 1`` values each.
        meta: Provenance recorded at fit time and written to disk on save.
    """

    def __init__(
        self,
        channels: list[str],
        n_bins: int,
        edges: dict[str, list[float]] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Construct a tokenizer, normally via :meth:`fit` or :meth:`load`.

        Args:
            channels: Channel names in identifier order.
            n_bins: Number of bins per channel.
            edges: Pre-fitted edges; an unfitted tokenizer when omitted.
            meta: Provenance metadata.

        Raises:
            ValueError: If ``n_bins`` is smaller than two.
        """
        if n_bins < 2:
            raise ValueError(f"n_bins must be at least 2, got {n_bins}")
        self.channels = list(channels)
        self.n_bins = n_bins
        self.edges: dict[str, list[float]] = dict(edges or {})
        self.meta: dict[str, Any] = dict(meta or {})

    @property
    def is_fitted(self) -> bool:
        """Whether every configured channel has fitted edges."""
        return bool(self.channels) and all(name in self.edges for name in self.channels)

    def channel_index(self, channel: str) -> int:
        """Return the identifier of a channel.

        Args:
            channel: Channel name.

        Returns:
            Its index in the fitted channel order.

        Raises:
            KeyError: If the channel was not part of the fit.
        """
        try:
            return self.channels.index(channel)
        except ValueError as exc:
            raise KeyError(f"channel {channel!r} is not in this tokenizer") from exc

    @classmethod
    def fit(
        cls,
        frame: pd.DataFrame,
        channels: list[str],
        n_bins: int = 64,
        sample_rows: int | None = 500_000,
        seed: int = 20260909,
    ) -> QuantileBinTokenizer:
        """Fit quantile edges per channel.

        Args:
            frame: Wide telemetry table restricted to the training split.
            channels: Channels to fit, in the order that fixes channel identifiers.
            n_bins: Number of bins per channel.
            sample_rows: Row cap for the quantile estimate; ``None`` uses all rows.
            seed: Seed for the row subsample.

        Returns:
            A fitted tokenizer.

        Raises:
            KeyError: If a requested channel is missing from the table.
        """
        missing = [name for name in channels if name not in frame.columns]
        if missing:
            raise KeyError(f"channels missing from the fit table: {missing}")

        sampled = frame
        if sample_rows is not None and len(frame) > sample_rows:
            sampled = frame.sample(n=sample_rows, random_state=seed)

        probabilities = np.linspace(0.0, 1.0, n_bins + 1)
        edges: dict[str, list[float]] = {}
        coverage: dict[str, int] = {}
        for name in channels:
            values = pd.to_numeric(sampled[name], errors="coerce").to_numpy(dtype=float)
            finite = values[np.isfinite(values)]
            coverage[name] = int(finite.size)
            if finite.size == 0:
                raise ValueError(f"channel {name!r} has no finite values to fit bins on")
            edges[name] = [float(value) for value in np.quantile(finite, probabilities)]

        meta = {
            "n_bins": n_bins,
            "fit_rows": int(len(sampled)),
            "fit_rows_available": int(len(frame)),
            "finite_values_per_channel": coverage,
            "sample_rows": sample_rows,
            "seed": seed,
            "fitted_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        }
        tokenizer = cls(channels=channels, n_bins=n_bins, edges=edges, meta=meta)
        tokenizer.meta["config_hash"] = config_hash(
            {"channels": channels, "n_bins": n_bins, "edges": edges}
        )
        logger.info(
            "fitted %d channels into %d bins on %d rows", len(channels), n_bins, len(sampled)
        )
        return tokenizer

    def transform_channel(self, values: np.ndarray | pd.Series, channel: str) -> np.ndarray:
        """Bin one channel's values.

        Args:
            values: Numeric values for the channel.
            channel: Channel name.

        Returns:
            An integer array of local bin identifiers, with :data:`MISSING_BIN`
            wherever the input was missing or non-finite.

        Raises:
            KeyError: If the channel has no fitted edges.
        """
        if channel not in self.edges:
            raise KeyError(f"channel {channel!r} has no fitted edges")
        array = np.asarray(values, dtype=float)
        interior = np.asarray(self.edges[channel][1:-1], dtype=float)
        binned = np.searchsorted(interior, array, side="right").astype(np.int64)
        binned = np.clip(binned, 0, self.n_bins - 1)
        binned[~np.isfinite(array)] = MISSING_BIN
        return binned

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        """Bin every fitted channel of a wide table.

        Args:
            frame: Wide telemetry table; missing channels are treated as all-missing.

        Returns:
            An integer array of shape ``(len(frame), len(self.channels))``.

        Raises:
            RuntimeError: If the tokenizer has not been fitted.
        """
        if not self.is_fitted:
            raise RuntimeError("tokenizer is not fitted; call fit() or load() first")
        out = np.full((len(frame), len(self.channels)), MISSING_BIN, dtype=np.int64)
        for index, name in enumerate(self.channels):
            if name not in frame.columns:
                logger.warning("channel %s absent from the table; emitting missing bins", name)
                continue
            values = pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=float)
            out[:, index] = self.transform_channel(values, name)
        return out

    def inverse(self, bin_ids: np.ndarray, channel: str) -> np.ndarray:
        """Map bin identifiers back to representative values.

        Args:
            bin_ids: Local bin identifiers for one channel.
            channel: Channel name.

        Returns:
            An array of bin midpoints, with ``NaN`` wherever the identifier was
            :data:`MISSING_BIN`.

        Raises:
            KeyError: If the channel has no fitted edges.
        """
        if channel not in self.edges:
            raise KeyError(f"channel {channel!r} has no fitted edges")
        edges = np.asarray(self.edges[channel], dtype=float)
        midpoints = (edges[:-1] + edges[1:]) / 2.0
        ids = np.asarray(bin_ids, dtype=np.int64)
        out = np.full(ids.shape, np.nan, dtype=float)
        valid = ids != MISSING_BIN
        out[valid] = midpoints[np.clip(ids[valid], 0, self.n_bins - 1)]
        return out

    def to_dict(self) -> dict[str, Any]:
        """Serialize the tokenizer to a plain dictionary.

        Returns:
            A JSON-ready mapping of channels, bin count, edges and provenance.
        """
        return {
            "channels": self.channels,
            "n_bins": self.n_bins,
            "edges": self.edges,
            "meta": self.meta,
        }

    def save(self, path: Path) -> Path:
        """Write the tokenizer to a JSON file.

        Args:
            path: Destination file; parent directories are created.

        Returns:
            The path written.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> QuantileBinTokenizer:
        """Read a tokenizer back from JSON.

        Args:
            path: File written by :meth:`save`.

        Returns:
            The restored tokenizer.
        """
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            channels=list(payload["channels"]),
            n_bins=int(payload["n_bins"]),
            edges={key: [float(v) for v in values] for key, values in payload["edges"].items()},
            meta=dict(payload.get("meta", {})),
        )
