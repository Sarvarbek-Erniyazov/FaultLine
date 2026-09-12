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
from collections.abc import Callable, Mapping, Sequence
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


class ReferenceFit(StrictModel):
    """A control fit measured beside the chosen one and never written.

    The pure-quantile fit of the same bin count is always measured (ADR-0014); this adds
    the others a revision needs, which at v2 is the fit it supersedes, so that the report
    reads as a ladder rather than as a pair (ADR-0015).

    Attributes:
        label: The column heading in the report.
        n_tail: Fixed-width bins in each tail of the control.
        clamp_floor: The control's population floor on the outermost bin.
    """

    label: str
    n_tail: int = Field(default=0, ge=0)
    clamp_floor: float = Field(default=0.0, ge=0.0, lt=1.0)


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
        n_tail: Fixed-width bins in each tail (ADR-0014). ``0`` fits pure quantiles, as
            v0 did. The knob to turn when tail bins run out of training values.
        tail_quantile: Where the lower tail ends; the upper ends at its complement.
            ``0.005`` puts them below the training p0.5 and above the p99.5.
        clamp_floor: The share of a channel's measured training values its outermost bin
            on each side must hold (ADR-0015). After the fixed-width bins are laid the
            outermost is merged inward until it does. ``0.0`` leaves them as laid, which
            is v0's and v1's behaviour.
        reference_fits: Controls measured beside the chosen fit and never written; the
            pure-quantile fit of the same bin count is always one and is not listed here.
        tail_curve: The ``n_tail`` values whose tail-bin occupancy is measured and
            printed as a curve, so that the turn of the knob is evidenced in the report
            rather than asserted. Measured without the population floor: the curve is
            the ``n_tail`` signal alone.
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
    n_tail: int = Field(default=0, ge=0)
    tail_quantile: float = Field(default=0.005, gt=0.0, lt=0.5)
    clamp_floor: float = Field(default=0.0, ge=0.0, lt=1.0)
    reference_fits: list[ReferenceFit] = Field(default_factory=list)
    tail_curve: list[int] = Field(default_factory=list)
    include_imputed: bool = False
    excluded: dict[str, list[str]] = Field(default_factory=dict)
    exclusion_reasons: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self) -> QuantileBinsConfig:
        """Reject a configuration the fit or the token stream could not honour.

        Raises:
            ValueError: If the chosen bin count is not a candidate or not a size the bin
                block can hold, the channels are not the core set in identifier order,
                an exclusion names a channel not fitted or gives no reason, the choice
                gives no reason, a population floor is asked for without tails, or a
                reference fit repeats a control that is already measured.
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
        fixed = 2 * self.n_tail + self.max_point_masses
        if fixed >= min(self.candidates):
            raise ValueError(
                f"two {self.n_tail}-bin tails and {self.max_point_masses} point masses need "
                f"{fixed} bins, which leaves no quantile bins at n_bins={min(self.candidates)}"
            )
        if self.clamp_floor and not self.n_tail:
            raise ValueError(
                "clamp_floor floors the outermost fixed-width bin and needs n_tail > 0"
            )
        seen = {(0, 0.0), (self.n_tail, self.clamp_floor)}
        for reference in self.reference_fits:
            if not reference.label.strip():
                raise ValueError("every reference fit needs a label")
            key = (reference.n_tail, reference.clamp_floor)
            if key in seen:
                raise ValueError(
                    f"reference fit {reference.label!r} repeats a fit already measured: "
                    f"n_tail={key[0]}, clamp_floor={key[1]}"
                )
            seen.add(key)
        if self.tail_curve and self.n_tail not in self.tail_curve:
            raise ValueError(
                f"tail_curve {self.tail_curve} does not measure the chosen n_tail "
                f"{self.n_tail}, so the report could not show where the choice sits on it"
            )
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


#: A tail bin holding fewer training values than this is starved, and is the signal to
#: turn ``n_tail`` down -- not the median reconstruction error (ADR-0014).
STARVED_TAIL_BIN = 500

#: The channel ADR-0014 argued the tail rule on: at 256 pure quantile bins its top bin
#: spanned 42.7 degrees C, where overheating is. Every tail report follows it by name.
TAIL_WITNESS = "generator_bearing_temp_c"

#: The control every tail fit is measured against: the same bin count on the same values,
#: pure quantiles, which is the M1b rule (ADR-0014).
PLAIN = "quantile only"


@dataclass(frozen=True)
class TailOccupancy:
    """How many training values each of a channel's fixed-width tail bins holds.

    Attributes:
        channel: The channel.
        lower: Training values in each lower-tail bin, lowest bin first.
        upper: Training values in each upper-tail bin, lowest bin first.
        edges: The two tail boundaries, the training p0.5 and p99.5.
        merged: Outer bins the population floor merged away, lower side then upper
            (ADR-0015); ``(0, 0)`` where the floor is off or was already met.
    """

    channel: str
    lower: list[int]
    upper: list[int]
    edges: tuple[float, float]
    merged: tuple[int, int] = (0, 0)

    @property
    def starved(self) -> int:
        """Tail bins holding fewer than :data:`STARVED_TAIL_BIN` training values."""
        return sum(1 for count in [*self.lower, *self.upper] if count < STARVED_TAIL_BIN)

    @property
    def empty(self) -> int:
        """Tail bins holding no training value at all."""
        return sum(1 for count in [*self.lower, *self.upper] if count == 0)


def tail_occupancy(
    tokenizer: QuantileBinTokenizer, channel: str, train: np.ndarray
) -> TailOccupancy:
    """Count the training values in each of a channel's fixed-width tail bins.

    Args:
        tokenizer: The fitted tokenizer.
        channel: The channel.
        train: The training values it was fitted on.

    Returns:
        The per-bin counts of each tail, and where the tails end. Both lists are empty
        for a channel fitted without tails, or whose tails had no width.
    """
    tails = dict(tokenizer.meta.get("tails", {}).get(channel, {}))
    lower_bins, upper_bins = int(tails.get("lower_bins", 0)), int(tails.get("upper_bins", 0))
    bins = tokenizer.bins_in_use(channel)
    counts = np.bincount(tokenizer.transform_channel(train, channel), minlength=bins)
    return TailOccupancy(
        channel=channel,
        lower=[int(c) for c in counts[:lower_bins]],
        upper=[int(c) for c in counts[bins - upper_bins :]] if upper_bins else [],
        edges=(float(tails.get("low", math.nan)), float(tails.get("high", math.nan))),
        merged=(int(tails.get("lower_merged", 0)), int(tails.get("upper_merged", 0))),
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
    if config.n_tail:
        shares = ", ".join(f"{n}: {2 * config.n_tail / n:.0%}" for n in config.candidates)
        body += (
            f"\nRead the smaller candidates with care. The tails take {2 * config.n_tail} bins "
            f"whatever the budget is, which is {shares} of it, so a candidate below the chosen "
            "one is not the like-for-like comparison M1b made -- it is a different rule as well "
            "as a smaller budget. The bin count is not reopened here (ADR-0011); the comparison "
            "that matters for the tail rule is the quantile-only fit at the chosen count, "
            "below.\n"
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


@dataclass(frozen=True)
class CurvePoint:
    """One point of the ``n_tail`` curve: what that many tail bins a side would hold.

    Attributes:
        n_tail: Fixed-width bins laid in each tail.
        bins: Tail bins the channels actually got, after rule 5 returned the bins of
            every zero-width tail to the middle.
        starved: Of those, holding fewer than :data:`STARVED_TAIL_BIN` training values.
        empty: Of those, holding none.
        witness: The top-bin width of :data:`TAIL_WITNESS`, the channel the rule was
            argued on.
        widest: The widest top bin over the channels, and the channel it belongs to.
    """

    n_tail: int
    bins: int
    starved: int
    empty: int
    witness: float
    widest: tuple[str, float]


def _curve_section(config: QuantileBinsConfig, curve: Sequence[CurvePoint]) -> str:
    """Render the measured ``n_tail`` curve the chosen value was picked off.

    Args:
        config: The tokenizer configuration.
        curve: One point per ``n_tail`` measured, in the configuration's order.

    Returns:
        A Markdown section.
    """
    rows = [
        (
            f"**{point.n_tail}**" if point.n_tail == config.n_tail else str(point.n_tail),
            point.bins,
            f"{point.starved} ({point.starved / point.bins:.0%})" if point.bins else "-",
            point.empty,
            f"{point.witness:.4g}",
            f"{point.widest[1]:.4g} (`{point.widest[0]}`)",
        )
        for point in curve
    ]
    body = (
        "ADR-0014 fixed the knob and the signal before the v1 fit: the knob is `n_tail`, "
        f"and the signal to turn it down is tail bins holding under {STARVED_TAIL_BIN:,} "
        "training values -- not the median reconstruction error, which is the rule's cost "
        "and not evidence about it. The signal fired at 16. This is the curve the turn was "
        "made on, measured here on the same training values as the fit, each point a whole "
        "fit at the chosen bin count.\n\n"
        "The floor of ADR-0015 is **not** applied in this table: the curve is the `n_tail` "
        "signal alone, so that the two changes this version makes are separable. The "
        "chosen row is therefore the fit *before* its own clamp bins were floored.\n\n"
        + table(
            [
                "n_tail",
                "tail bins",
                f"under {STARVED_TAIL_BIN:,}",
                "empty",
                f"top bin of `{TAIL_WITNESS}`",
                "widest top bin, any channel",
            ],
            rows,
        )
    )
    return section("The curve n_tail was turned on", body)


@dataclass(frozen=True)
class Reference:
    """One control fit, measured beside the chosen one and never written.

    Attributes:
        label: The column heading in the report.
        fits: One measurement per channel, in the configuration's channel order.
    """

    label: str
    fits: list[ChannelFit]


def _column(labels: Sequence[str], what: str) -> str:
    """Say which fit each slash-separated value in a column belongs to."""
    return f"{what} ({' / '.join(labels)})"


def _tails_section(
    config: QuantileBinsConfig,
    hybrid: Sequence[ChannelFit],
    references: Sequence[Reference],
    occupancy: Sequence[TailOccupancy],
) -> str:
    """Render the chosen tail rule against every control fitted on the same values.

    Args:
        config: The tokenizer configuration.
        hybrid: Per channel, the chosen fit.
        references: The controls: the pure-quantile fit of the same bin count, and any
            the configuration adds. Each is the same bin count on the same values, so
            the columns differ by the tail rule and nothing else.
        occupancy: Per channel, the training values in each tail bin.

    Returns:
        A Markdown section.
    """
    labels = [*(r.label for r in references), "chosen"]
    series = [*(list(r.fits) for r in references), list(hybrid)]

    def across(index: int, render: Callable[[ChannelFit], str]) -> str:
        return " / ".join(render(column[index]) for column in series)

    ends = [
        (
            f"`{o.channel}`",
            across(i, lambda f: str(f.bins)),
            across(i, lambda f: f"{f.bottom_width:.4g}"),
            across(i, lambda f: f"{f.top_width:.4g}"),
            f"{len(o.lower)} / {len(o.upper)}",
        )
        for i, o in enumerate(occupancy)
    ]
    errors = [
        (
            f"`{fit.channel}`",
            across(i, lambda f: _pct(f.train_error)),
            across(i, lambda f: _pct(f.val_error)),
        )
        for i, fit in enumerate(hybrid)
    ]
    counts = [
        (
            f"`{o.channel}`",
            f"{o.edges[0]:.4g} / {o.edges[1]:.4g}",
            f"{min(o.lower):,} / {int(np.median(o.lower)):,} / {max(o.lower):,}"
            if o.lower
            else "-",
            f"{min(o.upper):,} / {int(np.median(o.upper)):,} / {max(o.upper):,}"
            if o.upper
            else "-",
            f"{o.merged[0]} / {o.merged[1]}",
            o.starved,
            o.empty,
        )
        for o in occupancy
    ]
    collapsed = [
        f"`{o.channel}` "
        + ", ".join(side for side, taken in (("lower", o.lower), ("upper", o.upper)) if not taken)
        for o in occupancy
        if not o.lower or not o.upper
    ]
    tail_bins = sum(len(o.lower) + len(o.upper) for o in occupancy)
    floored = (
        " The outermost bin on each side is then merged inward until it holds "
        f"{config.clamp_floor:.1%} of the channel's measured training values (ADR-0015), "
        "so a tail can end with fewer bins than it was laid with."
        if config.clamp_floor
        else ""
    )
    body = (
        f"Every channel gets {config.n_tail} fixed-width bins below the training "
        f"p{config.tail_quantile:.1%} and {config.n_tail} above the p"
        f"{1 - config.tail_quantile:.1%}, after the point masses take their exact bins; "
        f"the rest of the bin budget is quantiles over the middle.{floored}\n\n"
        "Every column is the same bin count fitted on the same values, so the fits differ "
        "by the tail rule and nothing else. `quantile only` is the M1b rule; a fit between "
        "it and `chosen` is a revision this one supersedes.\n\n"
        "**The end bins**, widths in the channel's unit\n\n"
        + table(
            [
                "channel",
                _column(labels, "bins"),
                _column(labels, "bottom-bin width"),
                _column(labels, "top-bin width"),
                "tail bins: lower / upper",
            ],
            ends,
        )
        + "\n**Reconstruction error**, as a share of the interquartile range\n\n"
        + table(["channel", _column(labels, "train"), _column(labels, "validation")], errors)
        + "\n**What the tail bins hold.** Training values per tail bin: smallest / median "
        "/ largest, how many of the channel's tail bins hold fewer than "
        f"{STARVED_TAIL_BIN:,}, and how many hold none. A starved tail bin is the signal "
        "to turn `n_tail` down; the median reconstruction error is not.\n\n"
        + table(
            [
                "channel",
                "tail boundaries",
                "lower tail: min / median / max",
                "upper tail: min / median / max",
                "bins merged by the floor: lower / upper",
                f"bins under {STARVED_TAIL_BIN:,}",
                "empty bins",
            ],
            counts,
        )
        + "\n"
        + kv_table(
            {
                "tails with no width, their bins returned to the middle": ", ".join(collapsed)
                or "none",
                f"tail bins under {STARVED_TAIL_BIN:,} training values": (
                    f"{sum(o.starved for o in occupancy)} of {tail_bins}"
                ),
                "empty tail bins": f"{sum(o.empty for o in occupancy)} of {tail_bins}",
            }
        )
        + "\n**Every tail bin's training count**, lowest bin first.\n"
    )
    for o in occupancy:
        lower = ", ".join(f"{c:,}" for c in o.lower) or "no lower tail"
        upper = ", ".join(f"{c:,}" for c in o.upper) or "no upper tail"
        body += f"\n**`{o.channel}`**\n\n```text\nlower: {lower}\nupper: {upper}\n```\n"
    return section(f"The tails: {config.n_tail} fixed-width bins a side", body)


def _acceptance_section(
    config: QuantileBinsConfig,
    fitted: SplitValues,
    hybrid: Sequence[ChannelFit],
    references: Sequence[Reference],
    occupancy: Sequence[TailOccupancy],
) -> str:
    """Render the pre-registered acceptance check of ADR-0015.

    The checks were fixed before the fit and are reported, not iterated on: a channel
    that fails one is a limitation in the record rather than a reason to fit again.

    Args:
        config: The tokenizer configuration.
        fitted: The training values fitted on, whose per-channel count the floor is a
            share of.
        hybrid: Per channel, the chosen fit.
        references: The controls measured beside it.
        occupancy: Per channel, the training values in each tail bin.

    Returns:
        A Markdown section.
    """
    clamps = []
    short: list[str] = []
    for fit in hybrid:
        size = int(fitted.values[fit.channel].size)
        floor = int(math.ceil(config.clamp_floor * size))
        bottom, top = int(round(fit.first * size)), int(round(fit.last * size))
        if bottom < floor or top < floor:
            missed = ", ".join(
                f"{side} {held:,}"
                for side, held in (("bottom", bottom), ("top", top))
                if held < floor
            )
            short.append(f"`{fit.channel}` ({missed}, floor {floor:,})")
        clamps.append(
            (
                f"`{fit.channel}`",
                f"{size:,}",
                f"{floor:,}",
                f"{bottom:,} ({_pct(fit.first, 3)})",
                f"{top:,} ({_pct(fit.last, 3)})",
                bottom >= floor and top >= floor,
            )
        )
    empty = sum(o.empty for o in occupancy)
    index = next(i for i, fit in enumerate(hybrid) if fit.channel == TAIL_WITNESS)
    widths = " -> ".join(
        f"{label}: {fits[index].top_width:.4g}"
        for label, fits in [
            *((r.label, list(r.fits)) for r in references),
            ("chosen", list(hybrid)),
        ]
    )
    control = next((r for r in references if r.label == PLAIN), None)
    pairs = list(zip(hybrid, control.fits, strict=True)) if control is not None else []
    wider = (
        sum(1 for chosen, plain in pairs if chosen.bottom_width > plain.bottom_width),
        sum(1 for chosen, plain in pairs if chosen.top_width > plain.top_width),
    )
    verdicts = {
        "no tail bin empty at any channel": (
            "PASS"
            if empty == 0
            else f"FAIL: {empty} of "
            f"{sum(len(o.lower) + len(o.upper) for o in occupancy)} tail bins hold none"
        ),
        f"every clamp bin at or above the {config.clamp_floor:.1%} floor": (
            "PASS" if not short else "FAIL: " + "; ".join(short)
        ),
        f"`{TAIL_WITNESS}` top-bin width, in degC": widths,
        "reconstruction error against every prior fit": "reported above, one column a fit",
        f"clamp bins wider than the `{PLAIN}` control": (
            f"bottom {wider[0]} of {len(hybrid)}, top {wider[1]} of {len(hybrid)}"
        ),
    }
    body = (
        "Four checks fixed before the fit (ADR-0015). They are reported and not iterated "
        "on: a channel that fails one is a limitation in the record, not a reason to fit "
        "a third time.\n\n"
        + kv_table(verdicts, key_header="check", value_header="result")
        + "\n**The clamp bins.** The outermost bin on each side is where every value "
        "beyond the training range lands, so its effective width is unbounded whatever "
        "its nominal width. The floor is "
        f"{config.clamp_floor:.1%} of the channel's own measured training values.\n\n"
        + table(
            [
                "channel",
                "values fitted",
                "floor",
                "bottom bin holds",
                "top bin holds",
                "meets the floor",
            ],
            clamps,
        )
    )
    if any(wider):
        collapsed = 2 * config.tail_quantile
        quantile_end = 1 / config.n_bins
        body += (
            f"\n**What the floor costs, and it is not small.** On {wider[0]} channels the "
            f"bottom bin and on {wider[1]} the top bin came out wider than the `{PLAIN}` "
            "control -- wider than doing nothing, on the measure ADR-0014 was accepted for. "
            "The mechanism is arithmetic rather than a defect. A tail's values are packed "
            "against its inner boundary, so the outer fixed-width bins are nearly empty and "
            "the merge cascades; where it runs to the boundary the clamp bin spans the whole "
            f"tail and holds {config.tail_quantile:.1%} of the channel's values by "
            f"construction, against the {quantile_end:.2%} a pure quantile end bin holds. A "
            "population floor and a fixed-width tail pull opposite ways and the floor wins. "
            "The two objectives of ADR-0015 cannot both be met by merging alone: this fit "
            "buys a clamp token the model can learn and pays for it in clamp resolution on "
            "most channels. Reported, not iterated on -- and the reason the tails are "
            f"{collapsed:.0%} of the values wide in the first place is the tail rule itself, "
            "so the honest reading is that the rule and the floor need one design, not two.\n"
        )
    return section("Pre-registered acceptance check", body)


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
    references: Sequence[Reference] = (),
    occupancy: Sequence[TailOccupancy] = (),
    curve: Sequence[CurvePoint] = (),
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
        references: The control fits measured beside the chosen one, each the same bin
            count on the same values; empty under a pure-quantile configuration.
        occupancy: Per channel, the training values in each fixed-width tail bin.
        curve: One point per ``n_tail`` measured, the curve the choice was made on.

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
    if curve:
        parts.append(_curve_section(config, curve))
    if config.n_tail:
        parts.append(_tails_section(config, fits[config.n_bins], references, occupancy))
        parts.append(
            _acceptance_section(config, fitted, fits[config.n_bins], references, occupancy)
        )
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
            n_tail=config.n_tail,
            tail_quantile=config.tail_quantile,
            clamp_floor=config.clamp_floor,
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
    # The controlled before to the chosen fit's after: the same bin count on the same
    # values, differing by the tail rule alone. The pure-quantile fit is always one of
    # them; a revision adds the fit it supersedes, so the report reads as a ladder. They
    # are measured and never written, so no run can read one by mistake.
    references: list[Reference] = []
    occupancy: list[TailOccupancy] = []
    if config.n_tail:
        controls = [(PLAIN, 0, 0.0)] + [
            (r.label, r.n_tail, r.clamp_floor) for r in config.reference_fits
        ]
        for label, n_tail, clamp_floor in controls:
            control = QuantileBinTokenizer.fit_values(
                fitted.values,
                config.channels,
                config.n_bins,
                point_masses=config.point_masses,
                max_point_masses=config.max_point_masses,
                n_tail=n_tail,
                tail_quantile=config.tail_quantile,
                clamp_floor=clamp_floor,
            )
            references.append(
                Reference(
                    label=label,
                    fits=[
                        channel_fit(control, name, fitted.values[name], held_back.values[name])
                        for name in config.channels
                    ],
                )
            )
        occupancy = [tail_occupancy(chosen, name, fitted.values[name]) for name in config.channels]
    curve: list[CurvePoint] = []
    for n_tail in config.tail_curve:
        point = QuantileBinTokenizer.fit_values(
            fitted.values,
            config.channels,
            config.n_bins,
            point_masses=config.point_masses,
            max_point_masses=config.max_point_masses,
            n_tail=n_tail,
            tail_quantile=config.tail_quantile,
        )
        held = [tail_occupancy(point, name, fitted.values[name]) for name in config.channels]
        tops = {name: point.edges[name][-1] - point.edges[name][-2] for name in config.channels}
        curve.append(
            CurvePoint(
                n_tail=n_tail,
                bins=sum(len(o.lower) + len(o.upper) for o in held),
                starved=sum(o.starved for o in held),
                empty=sum(o.empty for o in held),
                witness=tops[TAIL_WITNESS],
                widest=max(tops.items(), key=lambda pair: pair[1]),
            )
        )
    tokenizer_path = chosen.save(
        paths.tokenizers_dir / f"quantile_bins_v{config.version}_{digest}.json"
    )
    ranges = {source: out_of_range(paths, source, chosen) for source in held_out}
    checks = [
        excluded_channel(paths, source, name, chosen)
        for source, names in config.excluded.items()
        for name in names
    ]
    header = "# The telemetry quantile-bin tokenizer\n\n" + kv_table(
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
    report = render_bins(
        header,
        config,
        fitted,
        fits,
        ranges,
        checks,
        chosen,
        training,
        references,
        occupancy,
        curve,
    )
    # The version is in the name because two tokenizer versions can be fitted on one
    # day, and the second must not overwrite the first's report. Re-fitting the same
    # version does overwrite, which is regeneration and is the point.
    destination = (
        paths.data_reports_dir / f"quantile_bins_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}.md"
    )
    destination.write_text(report, encoding="utf-8")
    logger.info("wrote %s and %s", tokenizer_path, destination)
    return tokenizer_path, destination
