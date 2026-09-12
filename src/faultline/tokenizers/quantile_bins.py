"""Per-channel quantile binning of telemetry values.

A continuous SCADA channel becomes a token by falling into one of at most ``n_bins``
bins. Quantiles, not fixed-width bins, because power and temperature channels are
heavily skewed: fixed widths would spend most of the vocabulary on values that occur a
few times a year.

Three rules matter for the science and are enforced here:

* Edges are fitted on the **training split only**. Fitting on the whole record
  leaks the held-out period's distribution into the vocabulary, which would flatter
  every drift result the project reports.
* Missing values are never imputed at this layer. They map to a dedicated sentinel
  and become the ``<nan>`` token, because missingness is itself a shift signal
  (ADR-0006).
* **A point mass gets a bin of its own** (``point_masses=True``). A value holding at
  least ``1 / n_bins`` of the fitted values -- blade pitch at exactly 0 degrees, a rotor
  at rest -- fills one or more quantile bins by itself, and plain quantiles spend those
  bins on duplicate edges while squeezing the rest of the channel into what is left.
  Each such value instead gets one exact bin, reaching halfway to its nearest observed
  neighbours, whose representative is the value itself; the other bins are quantiles of
  the remaining values. A channel then uses at most ``n_bins`` bins, and the local
  identifier space stays ``n_bins`` wide for every channel.
* **The tails get fixed-width bins** (``n_tail > 0``, ADR-0014). Quantile bins put
  resolution where the data is dense, and faults live where it is not: at 256 pure
  quantile bins the top bin of generator bearing temperature spanned 42.7 degrees C.
  So each tail -- below the training ``tail_quantile`` and above its complement --
  is cut into ``n_tail`` bins of equal width, and only what is left of ``n_bins`` after
  the point masses and the tails goes to quantiles over the middle. A tail with no
  width gives its bins back to the middle.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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


def sorted_quantiles(ordered: np.ndarray, probabilities: np.ndarray) -> np.ndarray:
    """Quantiles of an already sorted array, computed as ``numpy.quantile`` does.

    The linear method, without the partition ``numpy.quantile`` repeats on every call:
    the bin search below asks for many quantile sets of one sorted array.

    Args:
        ordered: Values sorted ascending, at least one.
        probabilities: Probabilities in ``[0, 1]``.

    Returns:
        One quantile per probability.
    """
    positions = np.asarray(probabilities, dtype=float) * (ordered.size - 1)
    lower = np.floor(positions).astype(np.int64)
    upper = np.minimum(lower + 1, ordered.size - 1)
    fraction = positions - lower
    return np.asarray(ordered[lower] + fraction * (ordered[upper] - ordered[lower]), dtype=float)


def _midpoints(edges: np.ndarray) -> np.ndarray:
    return np.asarray((edges[:-1] + edges[1:]) / 2.0, dtype=float)


@dataclass(frozen=True)
class ChannelBins:
    """One channel's fitted bins.

    Attributes:
        edges: Bin edges, ascending, one more than the bins in use.
        representatives: The value each bin decodes to: a point mass for its exact bin,
            the midpoint otherwise.
        point_masses: The values that were given an exact bin.
        tail_edges: The two boundaries between the fixed-width tails and the quantile
            middle; the training range itself when no tail was carved.
        tail_bins: How many fixed-width bins the lower and the upper tail actually got.
            ``(0, 0)`` under a pure-quantile fit, and ``0`` on a side whose tail had no
            width -- its bins went back to the quantile middle (ADR-0014, rule 5).
    """

    edges: list[float]
    representatives: list[float]
    point_masses: list[float]
    tail_edges: tuple[float, float] = (math.nan, math.nan)
    tail_bins: tuple[int, int] = (0, 0)


def fit_channel(
    values: np.ndarray,
    n_bins: int,
    point_masses: bool = False,
    max_point_masses: int | None = None,
    n_tail: int = 0,
    tail_quantile: float = 0.005,
) -> ChannelBins:
    """Fit one channel's bins.

    With ``n_tail = 0`` this is the pure-quantile fit with exact bins for point masses
    that M1b used. With ``n_tail > 0`` it is the hybrid of ADR-0014, in the order that
    record states: point masses take their exact bins first, each tail takes ``n_tail``
    fixed-width bins over ``[train_min, p)`` and ``(1 - p, train_max]``, and whatever is
    left of ``n_bins`` goes to quantile bins over the middle. A tail with no width --
    its boundary already at the range edge, or swallowed by the exact bin of a point
    mass -- contributes nothing, and its bins fall back to the middle.

    Args:
        values: The channel's values; non-finite values are ignored.
        n_bins: The most bins the channel may use.
        point_masses: Give every value holding at least ``1 / n_bins`` of the values an
            exact bin of its own.
        max_point_masses: Keep at most this many point masses, the heaviest; never more
            than a quarter of ``n_bins``, so that most bins stay continuous.
        n_tail: Fixed-width bins in each tail; ``0`` for a pure-quantile fit.
        tail_quantile: Where a tail ends. ``0.005`` puts the tails below the training
            p0.5 and above the training p99.5.

    Returns:
        The edges, the representative of each bin, the point masses and what the tails
        got.

    Raises:
        ValueError: If there is no finite value, or the fixed bins alone cannot fit in
            ``n_bins``.
    """
    array = np.asarray(values, dtype=float)
    ordered = np.sort(array[np.isfinite(array)])
    if ordered.size == 0:
        raise ValueError("no finite values to fit bins on")
    plain = sorted_quantiles(ordered, np.linspace(0.0, 1.0, n_bins + 1))
    low, high = float(ordered[0]), float(ordered[-1])
    if not point_masses and n_tail == 0:
        return ChannelBins(plain.tolist(), _midpoints(plain).tolist(), [], (low, high), (0, 0))

    distinct = np.unique(ordered)
    heavy = _heavy_values(ordered, n_bins, point_masses, max_point_masses)
    if heavy.size == 0 and n_tail == 0:
        return ChannelBins(plain.tolist(), _midpoints(plain).tolist(), [], (low, high), (0, 0))

    masses = distinct[heavy]
    # An exact bin reaches halfway to the nearest observed value either side, so no
    # training value falls in the gap between a point mass and its neighbours.
    lows = np.array(
        [(distinct[i - 1] + distinct[i]) / 2 if i > 0 else -np.inf for i in heavy], dtype=float
    )
    highs = np.array(
        [(distinct[i] + distinct[i + 1]) / 2 if i < distinct.size - 1 else np.inf for i in heavy],
        dtype=float,
    )
    mass_cuts = np.concatenate([lows[np.isfinite(lows)], highs[np.isfinite(highs)]])
    rest = ordered[~np.isin(ordered, masses)]

    def inside_a_mass(cuts: np.ndarray) -> np.ndarray:
        """Which cuts fall in a point mass's exact bin, which owns its whole span."""
        inside = np.zeros(cuts.size, dtype=bool)
        for start, stop in zip(lows, highs, strict=True):
            inside |= (cuts >= start) & (cuts <= stop)
        return inside

    lo_edge, hi_edge, tail_cuts = _tail_cuts(
        ordered, low, high, n_tail, tail_quantile, inside_a_mass
    )
    fixed = np.unique(np.concatenate([mass_cuts, tail_cuts]))
    fixed = fixed[(fixed > low) & (fixed < high)]
    if fixed.size + 1 > n_bins:
        raise ValueError(
            f"{fixed.size + 1} fixed bins (point masses and {n_tail}-bin tails) do not fit "
            f"in n_bins={n_bins}"
        )
    middle = rest[(rest >= lo_edge) & (rest <= hi_edge)]

    def cuts_for(continuous: int) -> np.ndarray:
        found = np.concatenate([mass_cuts, tail_cuts])
        if middle.size and continuous > 1:
            cuts = sorted_quantiles(middle, np.linspace(0.0, 1.0, continuous + 1))[1:-1]
            found = np.concatenate([found, cuts[~inside_a_mass(cuts)]])
        found = np.unique(found)
        return found[(found > low) & (found < high)]

    # The most quantile bins in the middle that keep the channel within n_bins. A tail
    # that contributed no cuts leaves its share here, which is rule 5 of ADR-0014.
    lower, upper = 1, n_bins
    while lower < upper:
        probe = (lower + upper + 1) // 2
        if cuts_for(probe).size + 1 <= n_bins:
            lower = probe
        else:
            upper = probe - 1
    cuts = cuts_for(lower)
    edges = np.concatenate([[low], cuts, [high]])
    representatives = _midpoints(edges) if edges.size > 1 else np.array([low])
    representatives[np.searchsorted(cuts, masses, side="right")] = masses
    return ChannelBins(
        edges.tolist(),
        representatives.tolist(),
        masses.tolist(),
        (lo_edge, hi_edge),
        (int(np.sum(edges <= lo_edge)) - 1, int(np.sum(edges >= hi_edge)) - 1),
    )


def _heavy_values(
    ordered: np.ndarray, n_bins: int, point_masses: bool, max_point_masses: int | None
) -> np.ndarray:
    """Indices, into the channel's distinct values, of the masses given exact bins.

    Args:
        ordered: The channel's finite values, sorted.
        n_bins: The most bins the channel may use.
        point_masses: Whether point masses get exact bins at all.
        max_point_masses: The most to keep, the heaviest first.

    Returns:
        Ascending indices into ``numpy.unique(ordered)``; empty when none qualify.
    """
    if not point_masses:
        return np.zeros(0, dtype=np.int64)
    _, counts = np.unique(ordered, return_counts=True)
    heavy = np.flatnonzero(counts >= ordered.size / n_bins)
    limit = n_bins // 4 if max_point_masses is None else min(max_point_masses, n_bins // 4)
    if heavy.size > limit:
        heavy = np.sort(heavy[np.argsort(counts[heavy], kind="stable")[::-1][:limit]])
    return heavy


def _tail_cuts(
    ordered: np.ndarray,
    low: float,
    high: float,
    n_tail: int,
    tail_quantile: float,
    inside_a_mass: Callable[[np.ndarray], np.ndarray],
) -> tuple[float, float, np.ndarray]:
    """The fixed-width cuts of the two tails, and where each tail ends.

    Args:
        ordered: The channel's finite values, sorted.
        low: The lowest training value.
        high: The highest.
        n_tail: Fixed-width bins in each tail; ``0`` carves none.
        tail_quantile: Where the lower tail ends; the upper ends at its complement.
        inside_a_mass: Which of a set of cuts fall in a point mass's exact bin.

    Returns:
        The lower and upper tail boundaries -- collapsed onto the range edge where the
        tail has no width -- and every surviving tail cut.
    """
    if n_tail <= 0:
        return low, high, np.zeros(0, dtype=float)
    lo_edge, hi_edge = sorted_quantiles(ordered, np.array([tail_quantile, 1 - tail_quantile]))
    pieces = []
    if lo_edge > low:
        pieces.append(np.linspace(low, lo_edge, n_tail + 1)[1:])
    else:
        lo_edge = low
    if hi_edge < high:
        pieces.append(np.linspace(hi_edge, high, n_tail + 1)[:-1])
    else:
        hi_edge = high
    if not pieces:
        return float(lo_edge), float(hi_edge), np.zeros(0, dtype=float)
    candidate = np.concatenate(pieces)
    return float(lo_edge), float(hi_edge), candidate[~inside_a_mass(candidate)]


class QuantileBinTokenizer:
    """Maps channel values to per-channel quantile bin identifiers.

    Attributes:
        channels: Channel names in fitted order; the order fixes channel identifiers.
        n_bins: The width of every channel's local identifier space.
        edges: Fitted bin edges per channel: ``n_bins + 1`` values each, or fewer when
            point masses were given exact bins.
        representatives: The value each bin decodes to, per channel; empty for a
            tokenizer saved before point masses, which decodes to midpoints.
        point_masses: Per channel, the values given an exact bin.
        meta: Provenance recorded at fit time and written to disk on save.
    """

    def __init__(
        self,
        channels: list[str],
        n_bins: int,
        edges: dict[str, list[float]] | None = None,
        meta: dict[str, Any] | None = None,
        representatives: dict[str, list[float]] | None = None,
        point_masses: dict[str, list[float]] | None = None,
    ) -> None:
        """Construct a tokenizer, normally via :meth:`fit` or :meth:`load`.

        Args:
            channels: Channel names in identifier order.
            n_bins: Number of bins per channel.
            edges: Pre-fitted edges; an unfitted tokenizer when omitted.
            meta: Provenance metadata.
            representatives: Pre-fitted bin representatives.
            point_masses: Pre-fitted point masses.

        Raises:
            ValueError: If ``n_bins`` is smaller than two.
        """
        if n_bins < 2:
            raise ValueError(f"n_bins must be at least 2, got {n_bins}")
        self.channels = list(channels)
        self.n_bins = n_bins
        self.edges: dict[str, list[float]] = dict(edges or {})
        self.representatives: dict[str, list[float]] = dict(representatives or {})
        self.point_masses: dict[str, list[float]] = dict(point_masses or {})
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

    def bins_in_use(self, channel: str) -> int:
        """The number of bins one channel uses, at most ``n_bins``.

        Args:
            channel: Channel name.

        Returns:
            One less than the number of its edges.

        Raises:
            KeyError: If the channel has no fitted edges.
        """
        if channel not in self.edges:
            raise KeyError(f"channel {channel!r} has no fitted edges")
        return max(1, len(self.edges[channel]) - 1)

    @classmethod
    def fit(
        cls,
        frame: pd.DataFrame,
        channels: list[str],
        n_bins: int = 64,
        sample_rows: int | None = 500_000,
        seed: int = 20260909,
        point_masses: bool = False,
        max_point_masses: int | None = None,
        n_tail: int = 0,
        tail_quantile: float = 0.005,
    ) -> QuantileBinTokenizer:
        """Fit quantile edges per channel.

        Args:
            frame: Wide telemetry table restricted to the training split.
            channels: Channels to fit, in the order that fixes channel identifiers.
            n_bins: Number of bins per channel.
            sample_rows: Row cap for the quantile estimate; ``None`` uses all rows.
            seed: Seed for the row subsample.
            point_masses: Give heavy repeated values an exact bin (module docstring).
            max_point_masses: The most point masses per channel.
            n_tail: Fixed-width bins in each tail; ``0`` for a pure-quantile fit.
            tail_quantile: Where each tail ends (module docstring).

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
        values = {
            name: pd.to_numeric(sampled[name], errors="coerce").to_numpy(dtype=float)
            for name in channels
        }
        return cls.fit_values(
            values,
            channels,
            n_bins,
            point_masses=point_masses,
            max_point_masses=max_point_masses,
            n_tail=n_tail,
            tail_quantile=tail_quantile,
            meta={
                "fit_rows": int(len(sampled)),
                "fit_rows_available": int(len(frame)),
                "sample_rows": sample_rows,
                "seed": seed,
            },
        )

    @classmethod
    def fit_values(
        cls,
        values: Mapping[str, np.ndarray],
        channels: list[str],
        n_bins: int,
        point_masses: bool = False,
        max_point_masses: int | None = None,
        n_tail: int = 0,
        tail_quantile: float = 0.005,
        meta: dict[str, Any] | None = None,
    ) -> QuantileBinTokenizer:
        """Fit every channel from arrays of its values.

        Args:
            values: The values of each channel, gathered by the caller.
            channels: Channels to fit, in the order that fixes channel identifiers.
            n_bins: Number of bins per channel.
            point_masses: Give heavy repeated values an exact bin (module docstring).
            max_point_masses: The most point masses per channel.
            n_tail: Fixed-width bins in each tail; ``0`` for a pure-quantile fit.
            tail_quantile: Where each tail ends (module docstring).
            meta: Provenance to record beside the fit's own.

        Returns:
            A fitted tokenizer.

        Raises:
            KeyError: If a channel has no values array.
            ValueError: If a channel has no finite value.
        """
        missing = [name for name in channels if name not in values]
        if missing:
            raise KeyError(f"channels missing from the fit table: {missing}")
        edges: dict[str, list[float]] = {}
        representatives: dict[str, list[float]] = {}
        masses: dict[str, list[float]] = {}
        coverage: dict[str, int] = {}
        tails: dict[str, dict[str, Any]] = {}
        for name in channels:
            array = np.asarray(values[name], dtype=float)
            coverage[name] = int(np.isfinite(array).sum())
            try:
                fitted = fit_channel(
                    array, n_bins, point_masses, max_point_masses, n_tail, tail_quantile
                )
            except ValueError as exc:
                raise ValueError(f"channel {name!r} cannot be binned: {exc}") from exc
            edges[name] = fitted.edges
            representatives[name] = fitted.representatives
            if fitted.point_masses:
                masses[name] = fitted.point_masses
            tails[name] = {
                "low": fitted.tail_edges[0],
                "high": fitted.tail_edges[1],
                "lower_bins": fitted.tail_bins[0],
                "upper_bins": fitted.tail_bins[1],
            }

        provenance = {
            **(meta or {}),
            "n_bins": n_bins,
            "point_masses": point_masses,
            "n_tail": n_tail,
            "tail_quantile": tail_quantile,
            "tails": tails,
            "finite_values_per_channel": coverage,
            "fitted_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        }
        tokenizer = cls(
            channels=channels,
            n_bins=n_bins,
            edges=edges,
            meta=provenance,
            representatives=representatives,
            point_masses=masses,
        )
        tokenizer.meta["config_hash"] = config_hash(
            {
                "channels": channels,
                "n_bins": n_bins,
                "edges": edges,
                "representatives": representatives,
            }
        )
        logger.info("fitted %d channels into at most %d bins", len(channels), n_bins)
        return tokenizer

    def transform_channel(self, values: np.ndarray | pd.Series, channel: str) -> np.ndarray:
        """Bin one channel's values.

        Args:
            values: Numeric values for the channel.
            channel: Channel name.

        Returns:
            An integer array of local bin identifiers, with :data:`MISSING_BIN`
            wherever the input was missing or non-finite. A value outside the fitted
            range lands in the first or the last bin.

        Raises:
            KeyError: If the channel has no fitted edges.
        """
        if channel not in self.edges:
            raise KeyError(f"channel {channel!r} has no fitted edges")
        array = np.asarray(values, dtype=float)
        interior = np.asarray(self.edges[channel][1:-1], dtype=float)
        binned = np.searchsorted(interior, array, side="right").astype(np.int64)
        binned = np.clip(binned, 0, self.bins_in_use(channel) - 1)
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
            Each bin's representative -- the point mass for an exact bin, the midpoint
            otherwise -- with ``NaN`` wherever the identifier was :data:`MISSING_BIN`.

        Raises:
            KeyError: If the channel has no fitted edges.
        """
        if channel not in self.edges:
            raise KeyError(f"channel {channel!r} has no fitted edges")
        edges = np.asarray(self.edges[channel], dtype=float)
        stored = self.representatives.get(channel)
        representatives = (
            (np.asarray(stored, dtype=float) if stored else _midpoints(edges))
            if edges.size > 1
            else edges
        )
        ids = np.asarray(bin_ids, dtype=np.int64)
        out = np.full(ids.shape, np.nan, dtype=float)
        valid = ids != MISSING_BIN
        out[valid] = representatives[np.clip(ids[valid], 0, representatives.size - 1)]
        return out

    def to_dict(self) -> dict[str, Any]:
        """Serialize the tokenizer to a plain dictionary.

        Returns:
            A JSON-ready mapping of channels, bin count, edges, representatives, point
            masses and provenance.
        """
        return {
            "channels": self.channels,
            "n_bins": self.n_bins,
            "edges": self.edges,
            "representatives": self.representatives,
            "point_masses": self.point_masses,
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

        def floats(key: str) -> dict[str, list[float]]:
            return {name: [float(v) for v in items] for name, items in payload.get(key, {}).items()}

        return cls(
            channels=list(payload["channels"]),
            n_bins=int(payload["n_bins"]),
            edges=floats("edges"),
            meta=dict(payload.get("meta", {})),
            representatives=floats("representatives"),
            point_masses=floats("point_masses"),
        )
