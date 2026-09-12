"""The telemetry quantile-bin tokenizer, fitted on the training split (M1b step 11).

``faultline telemetry bins`` reads ``configs/tokenizer/quantile_bins_v0.yaml``. It gathers
every measured value of the configured channels on the TRAIN split of the training sites
-- never validation, never the late test, never the held-out site, never CARE -- fits one
tokenizer per candidate bin count, writes the configured one with its configuration hash
to ``data/tokenizers/``, and reports, per channel and candidate:

* the reconstruction error: the mean absolute difference between a value and the value
  its bin decodes to, as a share of the channel's interquartile range, on the training
  values and on the validation split, which the edges never saw;
* the share of training values in the first and the last bin, and those bins' widths;
* the point masses given an exact bin;

and, for the configured bin count, the share of the held-out site's values outside the
training range, per calendar year (``per_year_sites``), with the training occupancy of the
bin they clamp into; what the excluded CARE power would have read as; and every edge.

Memory holds the training split's values of the fitted channels: about 4.7 million values
a channel, some 450 MB in all. Every other read is one turbine-year at a time.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pydantic import Field, model_validator

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.data.common.splits import SplitsConfig
from faultline.data.telemetry.adapters import ADAPTERS
from faultline.data.telemetry.pipeline import (
    load_telemetry_config,
    parquet_files,
    stage_source_dir,
)
from faultline.data.telemetry.schemas import CORE_CHANNELS, IMPUTED_SUFFIX
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.tokenizers.layout import BIN_CAPACITY
from faultline.tokenizers.quantile_bins import QuantileBinTokenizer

logger = get_logger(__name__)

#: A power bin whose representative is at or below this reads as a turbine not producing,
#: in per unit of rated power (the threshold of ``verify.PRODUCING_PU``, ADR-0013).
IDLE_PU = 0.005


class QuantileBinsConfig(StrictModel):
    """Top level of ``configs/tokenizer/quantile_bins_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        telemetry_config: The telemetry configuration whose final tables and split
            specification the fit reads, relative to the repository root.
        fit_split: The split the edges are fitted on. Only ``train`` is accepted.
        channels: The channels fitted: every core channel, in identifier order, because
            position is identity in the fixed-order token stream.
        candidates: The bin counts compared.
        n_bins: The bin count chosen, one of the candidates.
        n_bins_reason: Why, in a sentence or two; printed in the report.
        point_masses: Give values holding at least ``1 / n_bins`` of the training values
            an exact bin.
        max_point_masses: The most point masses per channel.
        include_imputed: Fit on imputed values too. They are interpolations, not
            measurements, so the default is not to.
        excluded: Per source, channels emitted as ``<nan>`` whatever their value.
        exclusion_reasons: Per source in ``excluded``, why.
    """

    version: int = 0
    telemetry_config: str
    fit_split: Literal["train"] = "train"
    channels: list[str]
    candidates: list[int]
    n_bins: int
    n_bins_reason: str
    point_masses: bool = True
    max_point_masses: int = Field(default=16, ge=0)
    include_imputed: bool = False
    excluded: dict[str, list[str]] = Field(default_factory=dict)
    exclusion_reasons: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self) -> QuantileBinsConfig:
        """Reject a configuration the fit or the token stream could not honour.

        Raises:
            ValueError: If the chosen bin count is not a candidate or not a size the bin
                block can hold, the channels are not the core set in identifier order,
                an exclusion names a channel not fitted or gives no reason, or the choice
                gives no reason.
        """
        if self.n_bins not in self.candidates:
            raise ValueError(f"n_bins {self.n_bins} is not one of the candidates {self.candidates}")
        wrong = [n for n in self.candidates if not 2 <= n <= BIN_CAPACITY]
        if wrong:
            raise ValueError(
                f"candidates {wrong} do not fit the bin block: between 2 and {BIN_CAPACITY}"
            )
        if self.channels != list(CORE_CHANNELS):
            raise ValueError(
                "channels must be every core channel in identifier order, "
                f"{list(CORE_CHANNELS)}: position is identity in the fixed-order stream"
            )
        for source, names in self.excluded.items():
            stray = [name for name in names if name not in self.channels]
            if stray:
                raise ValueError(f"excluded[{source}] names {stray}, which are not fitted")
            if not self.exclusion_reasons.get(source, "").strip():
                raise ValueError(f"excluded[{source}] needs a reason in exclusion_reasons")
        if not self.n_bins_reason.strip():
            raise ValueError("n_bins_reason must say why the bin count was chosen")
        return self


# =====================================================================================
# the values
# =====================================================================================


def _columns(path: Path, wanted: Sequence[str]) -> list[str]:
    names = set(pq.read_schema(path).names)
    return [name for name in wanted if name in names]


@dataclass
class SplitValues:
    """Every value of each channel on one split.

    Attributes:
        values: Per channel, the finite values kept.
        imputed: Per channel, finite values skipped for being imputed.
        rows: Per source, the split's rows read.
    """

    values: dict[str, np.ndarray]
    imputed: dict[str, int]
    rows: dict[str, int]


def split_values(
    paths: ProjectPaths,
    sources: Sequence[str],
    channels: Sequence[str],
    split: str,
    include_imputed: bool = False,
) -> SplitValues:
    """Gather every value of the channels on one split of the given sources.

    Args:
        paths: Resolved project paths.
        sources: The sources read; the caller decides which may be.
        channels: The channels gathered.
        split: The split whose rows are read.
        include_imputed: Keep imputed values.

    Returns:
        The values per channel, the imputed values skipped and the rows read per source.
    """
    parts: dict[str, list[np.ndarray]] = {name: [] for name in channels}
    skipped: Counter[str] = Counter()
    rows: Counter[str] = Counter()
    wanted = [*channels, *(f"{name}{IMPUTED_SUFFIX}" for name in channels), "split"]
    for source in sources:
        for path in parquet_files(stage_source_dir(paths, "final", source)):
            frame = pd.read_parquet(path, columns=_columns(path, wanted))
            if frame.empty or "split" not in frame.columns:
                continue
            chosen = (frame["split"] == split).to_numpy()
            rows[source] += int(chosen.sum())
            if not chosen.any():
                continue
            for name in channels:
                if name not in frame.columns:
                    continue
                values = frame.loc[chosen, name].to_numpy(dtype=float)
                keep = np.isfinite(values)
                flag = f"{name}{IMPUTED_SUFFIX}"
                if not include_imputed and flag in frame.columns:
                    imputed = frame.loc[chosen, flag].to_numpy(dtype=bool)
                    skipped[name] += int((imputed & keep).sum())
                    keep &= ~imputed
                parts[name].append(values[keep])
    return SplitValues(
        values={
            name: np.concatenate(items) if items else np.zeros(0, dtype=float)
            for name, items in parts.items()
        },
        imputed=dict(skipped),
        rows=dict(rows),
    )


# =====================================================================================
# the measurements
# =====================================================================================


def reconstruction_error(
    tokenizer: QuantileBinTokenizer, channel: str, values: np.ndarray
) -> float:
    """Mean absolute difference between each value and the value its bin decodes to.

    Args:
        tokenizer: A fitted tokenizer.
        channel: The channel.
        values: Finite values.

    Returns:
        The mean absolute difference, in the channel's unit; ``nan`` without values.
    """
    if values.size == 0:
        return math.nan
    decoded = tokenizer.inverse(tokenizer.transform_channel(values, channel), channel)
    return float(np.mean(np.abs(values - decoded)))


@dataclass(frozen=True)
class ChannelFit:
    """One channel under one candidate bin count.

    Attributes:
        channel: The channel.
        n_bins: The candidate.
        bins: Bins the channel uses.
        masses: Point masses with their share of the training values.
        iqr: The interquartile range of the training values.
        train_error: Reconstruction error on the training values, as a share of the IQR.
        val_error: The same on the validation split.
        first: Share of training values in the first bin.
        last: Share of training values in the last bin.
        bottom_width: Width of the first bin.
        top_width: Width of the last bin.
    """

    channel: str
    n_bins: int
    bins: int
    masses: list[tuple[float, float]]
    iqr: float
    train_error: float
    val_error: float
    first: float
    last: float
    bottom_width: float
    top_width: float


def channel_fit(
    tokenizer: QuantileBinTokenizer, channel: str, train: np.ndarray, val: np.ndarray
) -> ChannelFit:
    """Measure one channel of a fitted tokenizer.

    Args:
        tokenizer: A fitted tokenizer.
        channel: The channel.
        train: The training values it was fitted on.
        val: Validation values, never fitted on.

    Returns:
        Bins in use, point masses, reconstruction errors and the end bins.
    """
    q25, q75 = np.quantile(train, [0.25, 0.75])
    iqr = float(q75 - q25)
    ids = tokenizer.transform_channel(train, channel)
    bins = tokenizer.bins_in_use(channel)
    edges = tokenizer.edges[channel]

    def relative(values: np.ndarray) -> float:
        error = reconstruction_error(tokenizer, channel, values)
        return error / iqr if iqr > 0 else math.nan

    return ChannelFit(
        channel=channel,
        n_bins=tokenizer.n_bins,
        bins=bins,
        masses=[(v, float(np.mean(train == v))) for v in tokenizer.point_masses.get(channel, [])],
        iqr=iqr,
        train_error=relative(train),
        val_error=relative(val),
        first=float(np.mean(ids == 0)),
        last=float(np.mean(ids == bins - 1)),
        bottom_width=float(edges[1] - edges[0]) if len(edges) > 1 else 0.0,
        top_width=float(edges[-1] - edges[-2]) if len(edges) > 1 else 0.0,
    )


@dataclass
class RangeTally:
    """One source's values against the training range, per channel and calendar year.

    Attributes:
        values: Finite values per (channel, year).
        below: Of those, below the lowest training value.
        above: Of those, above the highest.
    """

    values: Counter[tuple[str, int]]
    below: Counter[tuple[str, int]]
    above: Counter[tuple[str, int]]

    def years(self) -> list[int]:
        """The calendar years with values."""
        return sorted({year for _, year in self.values})


def out_of_range(paths: ProjectPaths, source: str, tokenizer: QuantileBinTokenizer) -> RangeTally:
    """Count a source's values outside the training range, per channel and year.

    Args:
        paths: Resolved project paths.
        source: The source, the held-out site.
        tokenizer: The fitted tokenizer, whose first and last edges are the training
            range.

    Returns:
        Values, and those below and above the range, per channel and calendar year.
    """
    tally = RangeTally(Counter(), Counter(), Counter())
    wanted = [*tokenizer.channels, "timestamp_utc"]
    for path in parquet_files(stage_source_dir(paths, "final", source)):
        frame = pd.read_parquet(path, columns=_columns(path, wanted))
        if frame.empty:
            continue
        years = pd.to_datetime(frame["timestamp_utc"], utc=True).dt.year.to_numpy()
        for name in tokenizer.channels:
            if name not in frame.columns:
                continue
            values = frame[name].to_numpy(dtype=float)
            finite = np.isfinite(values)
            low, high = tokenizer.edges[name][0], tokenizer.edges[name][-1]
            for year in np.unique(years[finite]):
                here = finite & (years == year)
                key = (name, int(year))
                tally.values[key] += int(here.sum())
                tally.below[key] += int((here & (values < low)).sum())
                tally.above[key] += int((here & (values > high)).sum())
    return tally


@dataclass(frozen=True)
class ExcludedChannel:
    """What an excluded channel's values would have read as, had they been binned.

    Attributes:
        source: The source.
        channel: The channel.
        values: Finite values.
        low: The lowest value.
        high: The highest value.
        idle: Share of values landing in a bin whose representative reads as a turbine
            not producing (at or below :data:`IDLE_PU`); for power only.
    """

    source: str
    channel: str
    values: int
    low: float
    high: float
    idle: float


def excluded_channel(
    paths: ProjectPaths, source: str, channel: str, tokenizer: QuantileBinTokenizer
) -> ExcludedChannel:
    """Bin an excluded channel as if it were not, to show what exclusion avoids.

    Args:
        paths: Resolved project paths.
        source: The source.
        channel: The channel excluded there.
        tokenizer: The fitted tokenizer.

    Returns:
        The count and range of its values, and for power the share that would read as idle.
    """
    count = idle = 0
    low, high = math.inf, -math.inf
    for path in parquet_files(stage_source_dir(paths, "final", source)):
        frame = pd.read_parquet(path, columns=_columns(path, [channel]))
        if frame.empty or channel not in frame.columns:
            continue
        values = frame[channel].to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        if not values.size:
            continue
        count += int(values.size)
        low, high = min(low, float(values.min())), max(high, float(values.max()))
        decoded = tokenizer.inverse(tokenizer.transform_channel(values, channel), channel)
        idle += int((decoded <= IDLE_PU).sum())
    return ExcludedChannel(
        source=source,
        channel=channel,
        values=count,
        low=low,
        high=high,
        idle=idle / count if count else math.nan,
    )


# =====================================================================================
# the report
# =====================================================================================


def _pct(value: float, digits: int = 2) -> str:
    return "n/a" if value != value else f"{value * 100:.{digits}f}%"


def _choice_section(config: QuantileBinsConfig, fits: Mapping[int, Sequence[ChannelFit]]) -> str:
    headers = ["channel"]
    for n in config.candidates:
        headers += [f"{n}: bins", f"{n}: error train", f"{n}: error val"]
    rows = []
    for index, name in enumerate(config.channels):
        cells: list[str | int] = [f"`{name}`"]
        for n in config.candidates:
            fit = fits[n][index]
            cells += [fit.bins, _pct(fit.train_error), _pct(fit.val_error)]
        rows.append(tuple(cells))
    summary = []
    for n in config.candidates:
        train = [f.train_error for f in fits[n] if f.train_error == f.train_error]
        val = [f.val_error for f in fits[n] if f.val_error == f.val_error]
        summary.append(
            (
                n,
                _pct(float(np.median(train))),
                _pct(max(train)),
                _pct(float(np.median(val))),
                _pct(max(val)),
            )
        )
    ends = []
    for index, name in enumerate(config.channels):
        cells = [f"`{name}`"]
        for n in config.candidates:
            fit = fits[n][index]
            cells += [f"{_pct(fit.first)} / {_pct(fit.last)}", f"{fit.top_width:.4g}"]
        ends.append(tuple(cells))
    end_headers = ["channel"]
    for n in config.candidates:
        end_headers += [f"{n}: first / last bin", f"{n}: top-bin width"]
    body = (
        "Reconstruction error is the mean absolute difference between a value and the value "
        "its bin decodes to -- a point mass decodes to itself, any other bin to its midpoint "
        "-- as a share of the channel's interquartile range on the training values. `train` is "
        "measured on the values the edges were fitted on, `val` on the validation split "
        "(2021), which they never saw. `bins` is the number a channel uses: fewer than the "
        "candidate only where point masses took exact bins.\n\n"
        + table(headers, rows)
        + "\n**Across the channels**\n\n"
        + table(
            [
                "n_bins",
                "median error, train",
                "largest error, train",
                "median error, val",
                "largest error, val",
            ],
            summary,
        )
        + "\n**The end bins.** Share of training values in the first and the last bin, and the "
        "width of the last bin in the channel's unit: quantile bins spend few identifiers on "
        "the tails, where overheating lives.\n\n"
        + table(end_headers, ends)
        + "\n"
        + kv_table({"n_bins chosen": config.n_bins, "why": config.n_bins_reason})
    )
    return section("Choosing n_bins", body)


def _masses_section(fits: Sequence[ChannelFit]) -> str:
    rows = [
        (f"`{fit.channel}`", f"{value:g}", _pct(share))
        for fit in fits
        for value, share in fit.masses
    ]
    body = (
        "A value holding at least 1/n_bins of a channel's training values would fill a whole "
        "quantile bin by itself; each such value has an exact bin, reaching halfway to its "
        "nearest observed neighbours, and decodes to itself.\n\n"
        + (table(["channel", "value", "share of training values"], rows) if rows else "None.\n")
    )
    return section(f"Point masses at n_bins = {fits[0].n_bins if fits else 0}", body)


def _range_section(
    source: str, tally: RangeTally, fits: Sequence[ChannelFit], channels: Sequence[str]
) -> str:
    years = tally.years()
    headers = ["channel"]
    for year in years:
        headers += [f"{year}: below", f"{year}: above"]
    headers += ["training share of the first bin", "training share of the last bin"]
    rows = []
    for fit, name in zip(fits, channels, strict=True):
        cells: list[str] = [f"`{name}`"]
        for year in years:
            key = (name, year)
            total = tally.values.get(key, 0)
            cells += [
                _pct(tally.below.get(key, 0) / total if total else math.nan),
                _pct(tally.above.get(key, 0) / total if total else math.nan),
            ]
        cells += [_pct(fit.first), _pct(fit.last)]
        rows.append(tuple(cells))
    body = (
        f"Share of {source}'s values below the lowest training value or above the highest, "
        "per calendar year (reported per year, never pooled only: `per_year_sites`). Such a "
        "value lands in the first or the last bin, and the last two columns say how much of "
        "the training data that bin holds: a value clamped into a bin the training split "
        "rarely visits reads as a rare state, whatever it was.\n\n" + table(headers, rows)
    )
    return section(f"The held-out site against the training range: {source}", body)


def _excluded_section(config: QuantileBinsConfig, checks: Sequence[ExcludedChannel]) -> str:
    rows = [
        (
            check.source,
            f"`{check.channel}`",
            f"{check.values:,}",
            f"{check.low:g} to {check.high:g}",
            _pct(check.idle),
        )
        for check in checks
    ]
    body = (
        "Channels emitted as `<nan>` at a source, whatever their value, and why:\n\n"
        + kv_table(
            {
                f"{source}: {', '.join(names)}": config.exclusion_reasons[source]
                for source, names in config.excluded.items()
            }
        )
        + "\nWhat the values would have read as, binned against the training edges: the share "
        f"landing in a bin that decodes to {IDLE_PU:g} pu or less, a turbine not producing.\n\n"
        + table(["source", "channel", "values", "range", "would read as idle"], rows)
    )
    return section("Excluded channels", body)


def _edges_section(tokenizer: QuantileBinTokenizer) -> str:
    body = (
        "Every edge of the fitted tokenizer, lowest first; the first and last are the "
        "training range.\n"
    )
    for name in tokenizer.channels:
        values = ", ".join(f"{edge:.6g}" for edge in tokenizer.edges[name])
        body += f"\n**`{name}`** ({tokenizer.bins_in_use(name)} bins)\n\n```text\n{values}\n```\n"
    return section("Edges", body)


def render_bins(
    header: str,
    config: QuantileBinsConfig,
    fitted: SplitValues,
    fits: Mapping[int, Sequence[ChannelFit]],
    ranges: Mapping[str, RangeTally],
    checks: Sequence[ExcludedChannel],
    tokenizer: QuantileBinTokenizer,
    training: Sequence[str],
) -> str:
    """Render the tokenizer report.

    Args:
        header: The report header.
        config: The tokenizer configuration.
        fitted: The training values fitted on.
        fits: Per candidate, one entry per channel.
        ranges: Per held-out source, its values against the training range.
        checks: One per excluded channel.
        tokenizer: The tokenizer written.
        training: The training sources.

    Returns:
        A Markdown document.
    """
    what = kv_table(
        {
            "fitted on": f"the `{config.fit_split}` split of {', '.join(training)}; never "
            "validation, the late test, the held-out site or CARE",
            "rows read": ", ".join(f"{s} {n:,}" for s, n in fitted.rows.items()),
            "imputed values not fitted": f"{sum(fitted.imputed.values()):,} "
            "(interpolations, not measurements)",
            "training exclusions": "their rows are fitted: an exclusion withholds training "
            "windows, not values (ADR-0008)",
            "point masses": f"exact bins, at most {config.max_point_masses} a channel"
            if config.point_masses
            else "none",
        }
    ) + table(
        ["channel", "values fitted"],
        [(f"`{name}`", f"{fitted.values[name].size:,}") for name in config.channels],
    )
    parts = [
        header,
        section("What is fitted, on what", what),
        _choice_section(config, fits),
        _masses_section(fits[config.n_bins]),
    ]
    parts.extend(
        _range_section(source, tally, fits[config.n_bins], config.channels)
        for source, tally in ranges.items()
    )
    if config.excluded:
        parts.append(_excluded_section(config, checks))
    parts.append(_edges_section(tokenizer))
    return "".join(parts)


def fit_bins(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """Fit the quantile-bin tokenizer on the training split and write it and its report.

    Args:
        paths: Resolved project paths.
        config_path: The tokenizer configuration.

    Returns:
        The tokenizer file and the report.

    Raises:
        ValueError: If a source the fit would read is held out or evaluation-only.
    """
    config = load_config(config_path, QuantileBinsConfig)
    telemetry = load_telemetry_config(paths.repo_root / config.telemetry_config)
    splits = load_config(paths.repo_root / telemetry.final.splits_config, SplitsConfig)
    sources = list(ADAPTERS)
    training = [
        s for s in sources if s not in splits.holdout_sites and s not in splits.eval_only_sources
    ]
    held_out = [s for s in sources if s in splits.holdout_sites]
    leaked = [s for s in training if s in splits.holdout_sites or s in splits.eval_only_sources]
    if leaked:  # pragma: no cover - guarded by the comprehension above
        raise ValueError(f"the fit would read {leaked}, which never train")

    logger.info("gathering the %s split of %s", config.fit_split, ", ".join(training))
    fitted = split_values(
        paths, training, config.channels, config.fit_split, config.include_imputed
    )
    held_back = split_values(paths, training, config.channels, "val", config.include_imputed)
    digest = config_hash(config)
    tokenizers = {
        n: QuantileBinTokenizer.fit_values(
            fitted.values,
            config.channels,
            n,
            point_masses=config.point_masses,
            max_point_masses=config.max_point_masses,
            meta={
                "tokenizer_config": config_path.as_posix(),
                "tokenizer_config_hash": digest,
                "telemetry_config": config.telemetry_config,
                "fit_split": config.fit_split,
                "fit_sources": training,
                "git_sha": git_sha(paths.repo_root),
            },
        )
        for n in config.candidates
    }
    fits = {
        n: [
            channel_fit(tokenizer, name, fitted.values[name], held_back.values[name])
            for name in config.channels
        ]
        for n, tokenizer in tokenizers.items()
    }
    chosen = tokenizers[config.n_bins]
    tokenizer_path = chosen.save(
        paths.tokenizers_dir / f"quantile_bins_v{config.version}_{digest}.json"
    )
    ranges = {source: out_of_range(paths, source, chosen) for source in held_out}
    checks = [
        excluded_channel(paths, source, name, chosen)
        for source, names in config.excluded.items()
        for name in names
    ]
    header = "# The telemetry quantile-bin tokenizer (M1b step 11)\n\n" + kv_table(
        {
            "config": config_path.as_posix(),
            "config hash": digest,
            "telemetry config": config.telemetry_config,
            "tokenizer": tokenizer_path.relative_to(paths.repo_root).as_posix(),
            "edges hash": chosen.meta["config_hash"],
            "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "git_sha": git_sha(paths.repo_root),
            "generated by": "faultline telemetry bins",
        }
    )
    report = render_bins(header, config, fitted, fits, ranges, checks, chosen, training)
    destination = paths.data_reports_dir / f"quantile_bins_{datetime.now(tz=UTC):%Y%m%d}.md"
    destination.write_text(report, encoding="utf-8")
    logger.info("wrote %s and %s", tokenizer_path, destination)
    return tokenizer_path, destination
