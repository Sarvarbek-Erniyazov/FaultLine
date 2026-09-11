"""The core channel rule, measured (M1b step 10, ADR-0008).

A canonical channel is **core** -- a leave-site-out evaluation may depend on it -- when the
channel maps show it on both sides of the split (``channels.derive_core``) and three
conditions hold on the cleaned grid:

(a) **Held-out integrity.** Non-null on at least 95% of the grid at every held-out site,
    overall and in every calendar year there, so availability is not confounded with a
    year of the evaluation.
(b) **Training sufficiency.** At least 95% at one training site, and measured (above 0%)
    at every one.
(c) **No label shortcut.** Where a training site has the channel below 95%, its gaps are
    shown not to be label-informative against a *seasonally matched* control.

Condition (c) as first written compared affected with unaffected turbine-years, or missing
with present steps, without regard to the calendar. Block missingness and event rates are
both time-structured, so that comparison cannot separate them: at Penmanshiel it passed
pitch and gear oil over the training years (rate ratio 0.90) and failed them inside 2018
(0.23). The control here compares like with like. Within each calendar month, turbine-days
missing the channel are set against turbine-days of the same month that have it -- for a
site-wide gap, the same month in other years -- and the rate ratio is pooled over months
(Mantel-Haenszel) with a 95% interval. It is read by a rule fixed before any number was
seen: it **clears** when the interval contains 1 and lies within [0.5, 2] (a halving or a
doubling of the event rate is the size of difference this project already treats as
material: the late-period rise); it **does not clear** when the interval excludes 1; and
it is **inconclusive** otherwise.

Two things are measured beside the rule. The seasonally matched control the gate asked
for by name (:data:`SEASONAL_CONTROLS`): one calendar window in one year against the same
window in every other training year, events with Poisson intervals and the 24-hour base
rate. And whether each of the split specification's ``training_exclusions`` is what an
exclusion must be -- a bounded, site-wide, simultaneous outage of several channels -- on
the cleaned grid, not on the configuration's word.

Memory stays at one turbine-year of telemetry at a time; what is kept is one row per
turbine-day.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from faultline.config import load_config
from faultline.data.common.intervals import (
    mantel_haenszel_rate_ratio,
    poisson_interval,
    rate_ratio_interval,
)
from faultline.data.common.report import kv_table, section, table
from faultline.data.common.splits import SplitsConfig, TrainingExclusion, as_utc
from faultline.data.telemetry.adapters import ADAPTERS
from faultline.data.telemetry.channels import derive_core, load_channel_maps
from faultline.data.telemetry.harmonise import to_seconds
from faultline.data.telemetry.labels import STEPS_PER_YEAR, label_column
from faultline.data.telemetry.pipeline import (
    TelemetryPipelineConfig,
    parquet_files,
    stage_source_dir,
)
from faultline.data.telemetry.schemas import CHANNEL_NAMES
from faultline.data.telemetry.verify import GAP_THRESHOLD, REFERENCE_CHANNEL
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

#: The share a channel must reach on the cleaned grid: at every held-out site and in every
#: year there (a), and at one training site at least (b).
CORE_SHARE = 0.95
#: A matched rate ratio clears condition (c) only if its 95% interval lies inside this band
#: as well as containing 1.
MATERIAL_BAND: tuple[float, float] = (0.5, 2.0)
#: Inside an exclusion span every turbine misses every listed channel on at least this
#: share of its reporting steps: the mirror of the 95% the core rule asks for.
OUTAGE_SHARE = 0.95
#: An outage is bounded when the site publishes the listed channels on either side of it,
#: on more than half its reporting steps in the week before the start and the week after
#: the end. A gap that begins with the record, or never ends, is an era, not an outage.
EDGE_DAYS = 7
EDGE_SHARE = 0.5
#: The seasonally matched control asked for by name at M1b step 10: Penmanshiel's
#: February to May 2018, the site-wide gap in ambient and nacelle temperature, against
#: February to May of every other training year.
SEASONAL_CONTROLS: tuple[tuple[str, int, tuple[int, ...]], ...] = (
    ("penmanshiel", 2018, (2, 3, 4, 5)),
)
MONTHS: tuple[str, ...] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
DAY_SECONDS = 86_400


def _pct(value: float, digits: int = 1) -> str:
    return "n/a" if value != value else f"{value * 100:.{digits}f}%"


def _ratio(values: tuple[float, float, float]) -> str:
    ratio, low, high = values
    return "n/a" if ratio != ratio else f"{ratio:.2f} ({low:.2f}-{high:.2f})"


def read_ratio(ratio: float, low: float, high: float) -> str:
    """Read a rate ratio and its interval by the rule fixed before the numbers.

    Args:
        ratio: The rate ratio, affected to unaffected.
        low: Lower bound of its 95% interval.
        high: Upper bound.

    Returns:
        ``clears``, ``does not clear``, ``inconclusive``, or ``no events`` when the ratio
        is undefined.
    """
    if ratio != ratio:
        return "no events"
    if not low <= 1.0 <= high:
        return "does not clear"
    if MATERIAL_BAND[0] <= low and high <= MATERIAL_BAND[1]:
        return "clears"
    return "inconclusive"


# =====================================================================================
# one pass: a row per turbine-day
# =====================================================================================


def _present(frame: pd.DataFrame, names: Sequence[str]) -> dict[str, np.ndarray]:
    return {
        name: frame[name].notna().to_numpy()
        if name in frame.columns
        else np.zeros(len(frame), dtype=bool)
        for name in names
    }


def _second(stamp: pd.Timestamp) -> int:
    return int(to_seconds(pd.Series([stamp]))[0])


@dataclass
class OutageTally:
    """What one training exclusion's span holds on the cleaned grid.

    Attributes:
        exclusion: The configured exclusion.
        reporting: Per turbine, reporting steps inside the span.
        out: Per turbine, of those, the steps with every listed channel missing.
        missing: Per canonical channel, reporting steps inside the span without it.
        steps: Grid steps inside the span, every turbine.
        edge_reporting: Reporting steps in the week before the start and the week after
            the end.
        edge_present: Of those, the steps with every listed channel present.
    """

    exclusion: TrainingExclusion
    reporting: Counter[str] = field(default_factory=Counter)
    out: Counter[str] = field(default_factory=Counter)
    missing: Counter[str] = field(default_factory=Counter)
    steps: int = 0
    edge_reporting: list[int] = field(default_factory=lambda: [0, 0])
    edge_present: list[int] = field(default_factory=lambda: [0, 0])

    def add(
        self,
        turbine: str,
        seconds: np.ndarray,
        reporting: np.ndarray,
        present: Mapping[str, np.ndarray],
    ) -> np.ndarray:
        """Count one turbine-year's steps against the span.

        Args:
            turbine: Turbine identifier.
            seconds: Step times, integer seconds.
            reporting: Whether the turbine reports at each step.
            present: Per canonical channel, whether it has a value at each step.

        Returns:
            Which of the steps lie inside the span.
        """
        start, end = _second(self.exclusion.start_utc), _second(self.exclusion.end_utc)
        inside = (seconds >= start) & (seconds <= end)
        listed_out = np.ones(len(seconds), dtype=bool)
        listed_in = np.ones(len(seconds), dtype=bool)
        for name in self.exclusion.channels:
            listed_out &= ~present[name]
            listed_in &= present[name]
        here = inside & reporting
        self.steps += int(inside.sum())
        self.reporting[turbine] += int(here.sum())
        self.out[turbine] += int((here & listed_out).sum())
        for name, flags in present.items():
            self.missing[name] += int((here & ~flags).sum())
        week = EDGE_DAYS * DAY_SECONDS
        edges = (
            (seconds >= start - week) & (seconds < start),
            (seconds > end) & (seconds <= end + week),
        )
        for index, edge in enumerate(edges):
            self.edge_reporting[index] += int((edge & reporting).sum())
            self.edge_present[index] += int((edge & reporting & listed_in).sum())
        return inside

    @property
    def turbine_shares(self) -> dict[str, float]:
        """Per turbine reporting inside the span, the share with every listed channel out."""
        return {
            turbine: self.out[turbine] / count
            for turbine, count in sorted(self.reporting.items())
            if count
        }

    @property
    def edge_shares(self) -> tuple[float, float]:
        """Share of reporting steps with every listed channel present, before and after."""
        before, after = (
            present / reporting if reporting else math.nan
            for present, reporting in zip(self.edge_present, self.edge_reporting, strict=True)
        )
        return before, after

    def holds(self, turbines: int) -> dict[str, bool]:
        """Which of the four properties of an admissible outage the data shows.

        Args:
            turbines: Turbines with any grid at the source.

        Returns:
            ``several`` channels, ``site-wide`` (every turbine reports in the span),
            ``simultaneous`` (each misses every listed channel on at least
            :data:`OUTAGE_SHARE` of its reporting steps there) and ``bounded`` (the
            channels are published on either side).
        """
        shares = self.turbine_shares
        before, after = self.edge_shares
        return {
            "several": len(set(self.exclusion.channels)) >= 2,
            "site-wide": len(shares) == turbines,
            "simultaneous": bool(shares) and min(shares.values()) >= OUTAGE_SHARE,
            "bounded": before > EDGE_SHARE and after > EDGE_SHARE,
        }


def site_days(
    paths: ProjectPaths,
    source: str,
    channels: Sequence[str],
    label: str | None,
    exclusions: Sequence[TrainingExclusion],
) -> tuple[pd.DataFrame, list[OutageTally]]:
    """Reduce one source's cleaned grid to a row per turbine-day.

    Args:
        paths: Resolved project paths.
        source: Source identifier.
        channels: Channels counted.
        label: The label column counted, and narrow events joined, when given.
        exclusions: The split specification's training exclusions; those at this source
            are tallied, and every count has a ``kept`` twin outside their spans.

    Returns:
        Per turbine and UTC day: ``steps``, ``reporting`` (the reference channel present),
        ``kept`` and ``reporting_kept`` (outside every exclusion span), per channel
        ``nonnull:``, ``missing:`` (absent while reporting) and their ``_kept`` twins,
        ``known`` and ``positive`` steps of the label, and narrow ``events`` and
        ``events_kept`` by the day they start; and one tally per exclusion here.
    """
    cleaned = stage_source_dir(paths, "cleaned", source)
    tallies = [OutageTally(exclusion) for exclusion in exclusions if exclusion.source == source]
    parts = []
    for path in parquet_files(cleaned):
        frame = pd.read_parquet(path)
        if frame.empty:
            continue
        turbine = str(frame["turbine_id"].iloc[0])
        stamps = pd.to_datetime(frame["timestamp_utc"], utc=True).astype("datetime64[ns, UTC]")
        seconds = to_seconds(stamps)
        present = _present(frame, list(dict.fromkeys([REFERENCE_CHANNEL, *channels])))
        reporting = present[REFERENCE_CHANNEL]
        inside = np.zeros(len(frame), dtype=bool)
        for tally in tallies:
            inside |= tally.add(turbine, seconds, reporting, present)
        kept = ~inside
        columns: dict[str, np.ndarray] = {
            "steps": np.ones(len(frame), dtype=np.int64),
            "reporting": reporting,
            "kept": kept,
            "reporting_kept": reporting & kept,
        }
        for name in channels:
            columns[f"nonnull:{name}"] = present[name]
            columns[f"missing:{name}"] = ~present[name] & reporting
            columns[f"nonnull_kept:{name}"] = present[name] & kept
            columns[f"missing_kept:{name}"] = ~present[name] & reporting & kept
        known = np.zeros(len(frame), dtype=bool)
        positive = np.zeros(len(frame), dtype=bool)
        labels_path = cleaned / "labels" / path.name
        if label is not None and labels_path.is_file():
            labels = pd.read_parquet(labels_path, columns=["timestamp_utc", label])
            aligned = pd.DataFrame({"s": seconds}).merge(
                pd.DataFrame(
                    {"s": to_seconds(labels["timestamp_utc"]), "y": labels[label].astype("boolean")}
                ),
                on="s",
                how="left",
            )["y"]
            known = aligned.notna().to_numpy()
            positive = aligned.fillna(False).to_numpy(dtype=bool)
        columns["known"] = known
        columns["positive"] = positive
        table_ = pd.DataFrame({name: values.astype(np.int64) for name, values in columns.items()})
        table_["day"] = stamps.dt.floor("D").to_numpy()
        daily = table_.groupby("day", sort=True).sum().reset_index()
        daily.insert(0, "turbine_id", turbine)
        parts.append(daily)
    if not parts:
        return pd.DataFrame(), tallies
    days = pd.concat(parts, ignore_index=True).groupby(["turbine_id", "day"], sort=True).sum()
    days = days.reset_index()
    days["events"] = 0
    days["events_kept"] = 0
    events_path = cleaned / "labels" / "events_narrow.parquet"
    if label is not None and events_path.is_file():
        events = pd.read_parquet(events_path)
        events = events[events["in_grid"]] if "in_grid" in events.columns else events
        starts = pd.to_datetime(events["start_utc"], utc=True).astype("datetime64[ns, UTC]")
        within = np.zeros(len(events), dtype=bool)
        for exclusion in exclusions:
            if exclusion.source == source:
                within |= (
                    (starts >= exclusion.start_utc) & (starts <= exclusion.end_utc)
                ).to_numpy()
        counts = (
            pd.DataFrame(
                {
                    "turbine_id": events["turbine_id"].astype(str).to_numpy(),
                    "day": starts.dt.floor("D").to_numpy(),
                    "events": 1,
                    "events_kept": (~within).astype(np.int64),
                }
            )
            .groupby(["turbine_id", "day"], sort=True)
            .sum()
        )
        joined = days.set_index(["turbine_id", "day"]).drop(columns=["events", "events_kept"])
        days = joined.join(counts, how="left").fillna({"events": 0, "events_kept": 0})
        days = days.reset_index()
        days[["events", "events_kept"]] = days[["events", "events_kept"]].astype(np.int64)
    return days, tallies


# =====================================================================================
# the measurements
# =====================================================================================


def shares(days: pd.DataFrame, channels: Sequence[str], kept: bool = False) -> dict[str, float]:
    """Non-null share of each channel over every grid step, gaps included.

    Args:
        days: A :func:`site_days` table.
        channels: Channels measured.
        kept: Count only steps outside every exclusion span.

    Returns:
        Share per channel; ``nan`` for a table with no steps.
    """
    steps = int(days["kept" if kept else "steps"].sum()) if len(days) else 0
    prefix = "nonnull_kept" if kept else "nonnull"
    return {
        name: int(days[f"{prefix}:{name}"].sum()) / steps if steps else math.nan
        for name in channels
    }


def shares_by_year(days: pd.DataFrame, channels: Sequence[str]) -> dict[int, dict[str, float]]:
    """:func:`shares` per calendar year with at least a day of grid.

    Args:
        days: A :func:`site_days` table.
        channels: Channels measured.

    Returns:
        Share per channel, per year.
    """
    years = pd.DatetimeIndex(days["day"]).year
    result = {}
    for year in sorted(set(years)):
        chosen = days[years == year]
        if int(chosen["steps"].sum()) >= 144:
            result[int(year)] = shares(chosen, channels)
    return result


@dataclass(frozen=True)
class WindowYear:
    """One calendar window in one year at one site.

    Attributes:
        year: Calendar year.
        steps: Grid steps in the window, every turbine.
        events: Narrow events starting in the window.
        known: Steps with a known label.
        positive: Of those, the positive steps.
    """

    year: int
    steps: int
    events: int
    known: int
    positive: int

    @property
    def turbine_years(self) -> float:
        """Grid time, turbine-years."""
        return self.steps / STEPS_PER_YEAR


@dataclass(frozen=True)
class SeasonalControl:
    """One calendar window in one year against the same window in the other years.

    Attributes:
        source: Source identifier.
        window: The window, in words.
        year: The year whose window is tested.
        rows: One entry per year compared, the tested year included.
    """

    source: str
    window: str
    year: int
    rows: list[WindowYear]

    @property
    def tested(self) -> WindowYear:
        """The tested year's row."""
        return next(row for row in self.rows if row.year == self.year)

    @property
    def control(self) -> WindowYear:
        """Every other year's window, pooled."""
        others = [row for row in self.rows if row.year != self.year]
        return WindowYear(
            year=0,
            steps=sum(row.steps for row in others),
            events=sum(row.events for row in others),
            known=sum(row.known for row in others),
            positive=sum(row.positive for row in others),
        )

    @property
    def ratio(self) -> tuple[float, float, float]:
        """The tested year's rate against the pooled control's, with a 95% interval."""
        tested, control = self.tested, self.control
        return rate_ratio_interval(
            tested.events, tested.turbine_years, control.events, control.turbine_years
        )

    @property
    def verdict(self) -> str:
        """The ratio read by :func:`read_ratio`."""
        return read_ratio(*self.ratio)


def seasonal_control(
    days: pd.DataFrame, window: np.ndarray, source: str, label: str, year: int, years: Sequence[int]
) -> SeasonalControl:
    """Compare one year's calendar window with the same window in the other years.

    Args:
        days: A :func:`site_days` table with the label and events.
        window: Which rows of ``days`` fall in the calendar window.
        source: Source identifier.
        label: The window, in words.
        year: The year tested.
        years: Every year compared, the tested one included.

    Returns:
        Steps, events and the label's known and positive steps per year.
    """
    calendar = pd.DatetimeIndex(days["day"]).year.to_numpy()
    rows = []
    for each in years:
        chosen = days[window & (calendar == each)]
        rows.append(
            WindowYear(
                year=int(each),
                steps=int(chosen["steps"].sum()),
                events=int(chosen["events"].sum()),
                known=int(chosen["known"].sum()),
                positive=int(chosen["positive"].sum()),
            )
        )
    return SeasonalControl(source=source, window=label, year=year, rows=rows)


def month_window(days: pd.DataFrame, months: Sequence[int]) -> np.ndarray:
    """Which turbine-days fall in the given calendar months."""
    return np.asarray(pd.DatetimeIndex(days["day"]).month.isin(list(months)), dtype=bool)


def span_window(days: pd.DataFrame, spans: Sequence[TrainingExclusion]) -> np.ndarray:
    """Which turbine-days fall on a calendar day (month and day) some span covers."""
    covered: set[tuple[int, int]] = set()
    for span in spans:
        for day in pd.date_range(span.start_utc.floor("D"), span.end_utc.floor("D"), freq="D"):
            covered.add((day.month, day.day))
    stamps = pd.DatetimeIndex(days["day"])
    pairs = zip(stamps.month, stamps.day, strict=True)
    return np.array([pair in covered for pair in pairs], dtype=bool)


@dataclass(frozen=True)
class MatchedRatio:
    """Condition (c) for one channel at one training site.

    Attributes:
        source: Source identifier.
        channel: The channel.
        kept: Whether the grid outside every exclusion span was used.
        affected_days: Training turbine-days missing the channel on more than
            :data:`~faultline.data.telemetry.verify.GAP_THRESHOLD` of their reporting steps.
        affected: Narrow events and turbine-years on those days.
        unaffected: Narrow events and turbine-years on every other training turbine-day.
        crude: The unmatched rate ratio and its 95% interval.
        matched: The rate ratio pooled over calendar months, and its 95% interval.
        months: The months holding both affected and unaffected exposure.
    """

    source: str
    channel: str
    kept: bool
    affected_days: int
    affected: tuple[int, float]
    unaffected: tuple[int, float]
    crude: tuple[float, float, float]
    matched: tuple[float, float, float]
    months: tuple[int, ...]

    @property
    def verdict(self) -> str:
        """The matched ratio read by :func:`read_ratio`."""
        return read_ratio(*self.matched)


def matched_ratio(
    days: pd.DataFrame, source: str, channel: str, train_until: pd.Timestamp, kept: bool = False
) -> MatchedRatio:
    """Condition (c): affected against unaffected turbine-days, matched on calendar month.

    Args:
        days: A :func:`site_days` table with events.
        source: Source identifier.
        channel: The channel.
        train_until: The last training timestamp; later days are not compared.
        kept: Use only steps and events outside every exclusion span.

    Returns:
        The crude and the month-matched rate ratio, affected to unaffected.
    """
    train = days[(days["day"] <= train_until).to_numpy()]
    suffix = "_kept" if kept else ""
    reporting = train[f"reporting{suffix}"].to_numpy(dtype=float)
    missing = train[f"missing{suffix}:{channel}"].to_numpy(dtype=float)
    exposure = train["kept" if kept else "steps"].to_numpy(dtype=float) / STEPS_PER_YEAR
    events = train[f"events{suffix}"].to_numpy(dtype=np.int64)
    affected = (reporting > 0) & (missing > GAP_THRESHOLD * reporting)
    month = pd.DatetimeIndex(train["day"]).month.to_numpy()
    strata = []
    shared = []
    for each in range(1, 13):
        a = (month == each) & affected
        b = (month == each) & ~affected
        stratum = (
            int(events[a].sum()),
            float(exposure[a].sum()),
            int(events[b].sum()),
            float(exposure[b].sum()),
        )
        strata.append(stratum)
        if stratum[1] > 0 and stratum[3] > 0:
            shared.append(each)
    a_events, a_ty = int(events[affected].sum()), float(exposure[affected].sum())
    b_events, b_ty = int(events[~affected].sum()), float(exposure[~affected].sum())
    return MatchedRatio(
        source=source,
        channel=channel,
        kept=kept,
        affected_days=int(affected.sum()),
        affected=(a_events, a_ty),
        unaffected=(b_events, b_ty),
        crude=rate_ratio_interval(a_events, a_ty, b_events, b_ty),
        matched=mantel_haenszel_rate_ratio(strata),
        months=tuple(shared),
    )


@dataclass(frozen=True)
class ChannelVerdict:
    """One canonical channel under the rule.

    Attributes:
        channel: The channel.
        mappable: Whether the maps show it at every training and held-out site.
        held_out: Per held-out site, the non-null share on the grid.
        held_out_years: Per held-out site, the share in each calendar year.
        training: Per training site, the share on the whole grid.
        training_kept: Per training site, the share outside every exclusion span.
        shortcut: Per training site where the channel is measured but below
            :data:`CORE_SHARE` outside the exclusions, condition (c) there.
    """

    channel: str
    mappable: bool
    held_out: dict[str, float]
    held_out_years: dict[str, dict[int, float]]
    training: dict[str, float]
    training_kept: dict[str, float]
    shortcut: dict[str, MatchedRatio]

    @property
    def integrity(self) -> bool:
        """Condition (a)."""
        overall = all(share >= CORE_SHARE for share in self.held_out.values())
        yearly = all(
            share >= CORE_SHARE
            for years in self.held_out_years.values()
            for share in years.values()
        )
        return overall and yearly

    @property
    def sufficiency(self) -> bool:
        """Condition (b), on the grid training reads."""
        values = list(self.training_kept.values())
        return bool(values) and max(values) >= CORE_SHARE and min(values) > 0.0

    @property
    def no_shortcut(self) -> bool:
        """Condition (c): every training site below the threshold clears its control."""
        return all(result.verdict == "clears" for result in self.shortcut.values())

    @property
    def tier(self) -> str:
        """``core`` when the maps and all three conditions agree, else ``extended``."""
        core = self.mappable and self.integrity and self.sufficiency and self.no_shortcut
        return "core" if core else "extended"

    @property
    def reason(self) -> str:
        """The first condition that fails, or ``all hold``."""
        for failed, name in (
            (not self.mappable, "maps"),
            (not self.integrity, "(a)"),
            (not self.sufficiency, "(b)"),
            (not self.no_shortcut, "(c)"),
        ):
            if failed:
                return name
        return "all hold"


def channel_verdicts(
    days: Mapping[str, pd.DataFrame],
    training: Sequence[str],
    held_out: Sequence[str],
    mappable: Sequence[str],
    train_until: pd.Timestamp,
) -> list[ChannelVerdict]:
    """Apply the rule to every canonical channel.

    Args:
        days: A :func:`site_days` table per source.
        training: Training sources.
        held_out: Held-out sources.
        mappable: The channels the maps show on both sides of the split.
        train_until: The last training timestamp.

    Returns:
        One verdict per canonical channel, in identifier order.
    """
    whole = {source: shares(days[source], CHANNEL_NAMES) for source in [*training, *held_out]}
    kept = {source: shares(days[source], CHANNEL_NAMES, kept=True) for source in training}
    yearly = {source: shares_by_year(days[source], CHANNEL_NAMES) for source in held_out}
    verdicts = []
    for name in CHANNEL_NAMES:
        # (c) asks whether a measured channel's gaps are a shortcut; a channel a site does not
        # publish at all has no gaps to ask about, and fails the maps or (b) instead.
        shortcut = {
            source: matched_ratio(days[source], source, name, train_until, kept=True)
            for source in training
            if name in mappable and 0.0 < kept[source][name] < CORE_SHARE
        }
        verdicts.append(
            ChannelVerdict(
                channel=name,
                mappable=name in mappable,
                held_out={source: whole[source][name] for source in held_out},
                held_out_years={
                    source: {year: values[name] for year, values in yearly[source].items()}
                    for source in held_out
                },
                training={source: whole[source][name] for source in training},
                training_kept={source: kept[source][name] for source in training},
                shortcut=shortcut,
            )
        )
    return verdicts


# =====================================================================================
# the report
# =====================================================================================


def _rule_section() -> str:
    body = kv_table(
        {
            "(a) held-out integrity": f">= {CORE_SHARE:.0%} non-null on the cleaned grid at "
            "every held-out site, overall and in every calendar year there",
            "(b) training sufficiency": f">= {CORE_SHARE:.0%} at one training site at least, "
            "and above 0% at every one, on the grid outside the training exclusions",
            "(c) no label shortcut": "where a training site measures the channel but below "
            f"{CORE_SHARE:.0%}: "
            "narrow events per turbine-year on turbine-days missing the channel on more than "
            f"{GAP_THRESHOLD:.0%} of their reporting steps, against turbine-days of the same "
            "calendar month that have it; Mantel-Haenszel over months, 95% interval",
            "(c) is read": f"clears when the interval contains 1 and lies within "
            f"[{MATERIAL_BAND[0]:g}, {MATERIAL_BAND[1]:g}]; does not clear when it excludes 1; "
            "inconclusive otherwise. Fixed before any number was computed",
            "a training exclusion is admissible when": f"it names two channels or more; "
            f"every turbine of the source reports in its span; each misses every listed "
            f"channel on >= {OUTAGE_SHARE:.0%} of its reporting steps there; and the site "
            f"publishes the channels on more than {EDGE_SHARE:.0%} of its reporting steps in "
            f"the {EDGE_DAYS} days before and after",
        }
    )
    return section("The rule", body)


def _shares_section(
    verdicts: Sequence[ChannelVerdict], configured: Mapping[str, str], per_year: Sequence[int]
) -> str:
    first = verdicts[0]
    training = list(first.training)
    held_out = list(first.held_out)
    headers = ["channel", "maps"]
    for source in training:
        headers += [f"{source}", f"{source} outside exclusions"]
    for source in held_out:
        headers += [source, *(f"{source} {year}" for year in per_year)]
    headers += ["(a)", "(b)", "(c)", "tier by the rule", "tier in the config"]
    rows = []
    for verdict in verdicts:
        cells: list[Any] = [f"`{verdict.channel}`", "yes" if verdict.mappable else "no"]
        for source in training:
            cells += [_pct(verdict.training[source]), _pct(verdict.training_kept[source])]
        for source in held_out:
            cells.append(_pct(verdict.held_out[source]))
            cells += [_pct(verdict.held_out_years[source].get(year, math.nan)) for year in per_year]
        cells += [
            "holds" if verdict.integrity else "fails",
            "holds" if verdict.sufficiency else "fails",
            ("holds" if verdict.no_shortcut else "fails")
            + (
                " (" + "; ".join(f"{s}: {r.verdict}" for s, r in verdict.shortcut.items()) + ")"
                if verdict.shortcut
                else " (not needed)"
            ),
            f"**{verdict.tier}**"
            if verdict.tier != configured.get(verdict.channel)
            else verdict.tier,
            configured.get(verdict.channel, "-"),
        ]
        rows.append(tuple(cells))
    agree = all(verdict.tier == configured.get(verdict.channel) for verdict in verdicts)
    core = [verdict.channel for verdict in verdicts if verdict.tier == "core"]
    body = (
        "Non-null share of every grid step, gaps included. `maps` is whether the resolved "
        "channel maps show the channel at every training site and at the held-out site "
        "(`channels.derive_core`); the conditions are applied to the channels that pass it.\n\n"
        + table(headers, rows)
        + "\n"
        + kv_table(
            {
                "core by the rule": f"{len(core)}: {', '.join(core)}",
                "the rule and the configuration agree": "yes"
                if agree
                else "NO -- the bold tiers differ from the configuration",
            }
        )
    )
    return section("(a) and (b): coverage on the cleaned grid", body)


def _control_section(controls: Sequence[SeasonalControl]) -> str:
    body = (
        "One calendar window in one year against the same window in every other training "
        "year at the same site, every turbine pooled. Narrow events by the day they start, "
        "with the 95% interval of the count (Byar) divided by the same exposure; the "
        "24-hour base rate is the share of steps with a known `narrow_within_24h` label "
        "that are positive. The base rate carries no interval: its steps overlap by a day, "
        "so a binomial interval on them would claim a precision the events do not have.\n"
    )
    for control in controls:
        rows = []
        for row in control.rows:
            if not row.steps:
                rows.append((str(row.year), "no grid in the window", "-", "-", "-", "-"))
                continue
            low, high = poisson_interval(row.events)
            ty = row.turbine_years
            rows.append(
                (
                    f"**{row.year}**" if row.year == control.year else str(row.year),
                    f"{ty:.2f}",
                    f"{row.events:,}",
                    f"{row.events / ty:.1f}",
                    f"{low / ty:.1f}-{high / ty:.1f}",
                    _pct(row.positive / row.known, 2) if row.known else "n/a",
                )
            )
        pooled = control.control
        if pooled.steps:
            low, high = poisson_interval(pooled.events)
            ty = pooled.turbine_years
            rows.append(
                (
                    "other years, pooled",
                    f"{ty:.2f}",
                    f"{pooled.events:,}",
                    f"{pooled.events / ty:.1f}",
                    f"{low / ty:.1f}-{high / ty:.1f}",
                    _pct(pooled.positive / pooled.known, 2) if pooled.known else "n/a",
                )
            )
        body += (
            f"\n### {control.source}: {control.window}, {control.year} against the other "
            "years\n\n"
            + table(
                [
                    "year",
                    "turbine-years",
                    "narrow events",
                    "per turbine-year",
                    "95% interval",
                    "24 h base rate",
                ],
                rows,
            )
            + "\n"
            + kv_table(
                {
                    f"rate ratio, {control.year} to the other years": _ratio(control.ratio),
                    "verdict": f"**{control.verdict}**",
                }
            )
        )
    return section("(c) The seasonally matched control", body)


def _matched_section(results: Sequence[MatchedRatio]) -> str:
    rows = []
    for result in results:
        a_events, a_ty = result.affected
        b_events, b_ty = result.unaffected
        rows.append(
            (
                result.source,
                f"`{result.channel}`",
                "outside exclusions" if result.kept else "whole grid",
                f"{result.affected_days:,}",
                f"{a_events:,} / {a_ty:.1f} ty = {a_events / a_ty:.1f}" if a_ty else "-",
                f"{b_events:,} / {b_ty:.1f} ty = {b_events / b_ty:.1f}" if b_ty else "-",
                _ratio(result.crude),
                _ratio(result.matched),
                ", ".join(MONTHS[m - 1] for m in result.months) or "none",
                result.verdict,
            )
        )
    body = (
        "Every training channel below the threshold at a site, over the training years. A "
        f"turbine-day is affected when the channel is missing on more than {GAP_THRESHOLD:.0%} "
        "of its reporting steps. `crude` compares affected with unaffected turbine-days "
        "whenever they fall; `matched` compares them within each calendar month and pools the "
        "months, so a gap that sits in one season is set against the same season in other "
        "years. Only months holding both kinds of turbine-day contribute. Poisson intervals "
        "take no account of year-to-year variation beyond the count's own, which the "
        "per-year table above shows is real; they are the narrowest defensible intervals, "
        "not the widest.\n\n"
        + table(
            [
                "site",
                "channel",
                "grid",
                "affected turbine-days",
                "affected: events / exposure",
                "unaffected: events / exposure",
                "crude ratio",
                "matched ratio",
                "months matched",
                "verdict",
            ],
            rows,
        )
    )
    return section("(c) Month-matched rate ratios, every channel it applies to", body)


def _exclusions_section(
    tallies: Sequence[OutageTally],
    turbines: Mapping[str, int],
    train_steps: Mapping[str, int],
    published: Mapping[str, set[str]],
) -> str:
    if not tallies:
        return section(
            "Training exclusions",
            "The split specification names none: every training window is admitted.\n",
        )
    all_train = sum(train_steps.values())
    body = (
        "Each exclusion is measured on the cleaned grid. The steps stay in the corpus and in "
        "every evaluation; a training window whose context touches the span is withheld "
        "(`windows.window_ends`).\n"
    )
    for tally in tallies:
        exclusion = tally.exclusion
        holds = tally.holds(turbines.get(exclusion.source, 0))
        shares_ = tally.turbine_shares
        before, after = tally.edge_shares
        reporting = sum(tally.reporting.values())
        others = {
            name: count / reporting
            for name, count in tally.missing.items()
            if reporting
            and count
            and name not in exclusion.channels
            and name in published.get(exclusion.source, set())
        }
        source_train = train_steps.get(exclusion.source, 0)
        body += (
            f"\n### {exclusion.source}: {exclusion.start_utc:%Y-%m-%d %H:%M} to "
            f"{exclusion.end_utc:%Y-%m-%d %H:%M} UTC\n\n"
            + kv_table(
                {
                    "channels": ", ".join(f"`{name}`" for name in exclusion.channels),
                    "reason": exclusion.reason,
                    "grid steps in the span": f"{tally.steps:,} "
                    f"({tally.steps / STEPS_PER_YEAR:.2f} turbine-years)",
                    f"share of {exclusion.source}'s training steps": _pct(
                        tally.steps / source_train if source_train else math.nan, 2
                    ),
                    "share of every training site's training steps": _pct(
                        tally.steps / all_train if all_train else math.nan, 2
                    ),
                    "turbines reporting in the span": f"{len(shares_)} of "
                    f"{turbines.get(exclusion.source, 0)}",
                    "every listed channel out, per turbine (lowest, highest)": (
                        f"{_pct(min(shares_.values()), 2)}, {_pct(max(shares_.values()), 2)}"
                        if shares_
                        else "n/a"
                    ),
                    f"listed channels present, {EDGE_DAYS} days before and after": (
                        f"{_pct(before)}, {_pct(after)}"
                    ),
                    "other published channels missing on the same steps": ", ".join(
                        f"`{name}` {_pct(share)}" for name, share in sorted(others.items())
                    )
                    or "none",
                    "several channels": "yes" if holds["several"] else "NO",
                    "site-wide": "yes" if holds["site-wide"] else "NO",
                    "simultaneous": "yes" if holds["simultaneous"] else "NO",
                    "bounded": "yes" if holds["bounded"] else "NO",
                    "admissible": "**yes**" if all(holds.values()) else "**NO**",
                }
            )
        )
    return section("Training exclusions: is each a bounded, site-wide, simultaneous outage?", body)


def render_core(
    header: str,
    verdicts: Sequence[ChannelVerdict],
    configured: Mapping[str, str],
    per_year: Sequence[int],
    controls: Sequence[SeasonalControl],
    matched: Sequence[MatchedRatio],
    tallies: Sequence[OutageTally],
    turbines: Mapping[str, int],
    train_steps: Mapping[str, int],
    published: Mapping[str, set[str]],
) -> str:
    """Render the core-rule report.

    Args:
        header: The report header.
        verdicts: One per canonical channel.
        configured: The tier each channel has in the configuration read.
        per_year: The held-out years shown.
        controls: The seasonally matched controls.
        matched: Condition (c) on both grids for every channel it applies to.
        tallies: One per training exclusion.
        turbines: Turbines with grid per source.
        train_steps: Training-split grid steps per training source.
        published: Per training source, the channels it has any value for.

    Returns:
        A Markdown document.
    """
    return "".join(
        [
            header,
            _rule_section(),
            _shares_section(verdicts, configured, per_year),
            _control_section(controls),
            _matched_section(matched),
            _exclusions_section(tallies, turbines, train_steps, published),
        ]
    )


def inspect_core(paths: ProjectPaths, config: TelemetryPipelineConfig, config_path: Path) -> Path:
    """Measure the core rule on the cleaned grid and write its report.

    Args:
        paths: Resolved project paths.
        config: The configuration whose tiers and split specification are checked.
        config_path: Where it was read from.

    Returns:
        The report path.
    """
    splits = load_config(paths.repo_root / config.final.splits_config, SplitsConfig)
    sources = list(ADAPTERS)
    training = [
        s for s in sources if s not in splits.holdout_sites and s not in splits.eval_only_sources
    ]
    held_out = [s for s in sources if s in splits.holdout_sites]
    label = label_column("narrow", max(config.events.horizons_steps))
    train_until = as_utc(splits.time.train_until)

    days: dict[str, pd.DataFrame] = {}
    tallies: list[OutageTally] = []
    for source in [*training, *held_out]:
        logger.info("%s: reading the cleaned grid", source)
        table_, found = site_days(
            paths,
            source,
            CHANNEL_NAMES,
            label if source in training else None,
            splits.training_exclusions,
        )
        days[source] = table_
        tallies.extend(found)

    maps = load_channel_maps(paths.configs_dir, [*training, *held_out])
    mappable, _ = derive_core(maps, training, held_out)
    verdicts = channel_verdicts(days, training, held_out, mappable, train_until)

    controls = []
    for source, year, months in SEASONAL_CONTROLS:
        if source not in days:
            continue
        table_ = days[source]
        calendar = pd.DatetimeIndex(table_["day"])
        years = sorted(
            int(y)
            for y in set(calendar.year)
            if pd.Timestamp(f"{y}-12-31", tz="UTC") <= train_until
        )
        names = f"{MONTHS[months[0] - 1]}-{MONTHS[months[-1] - 1]}"
        controls.append(
            seasonal_control(table_, month_window(table_, months), source, names, year, years)
        )
        spans = [
            e for e in splits.training_exclusions if e.source == source and e.start_utc.year == year
        ]
        if spans:
            first, last = spans[0].start_utc, spans[-1].end_utc
            controls.append(
                seasonal_control(
                    table_,
                    span_window(table_, spans),
                    source,
                    f"the excluded spans' calendar days ({first:%d %b} to {last:%d %b})",
                    year,
                    years,
                )
            )

    below = sorted(
        {
            (source, name)
            for verdict in verdicts
            for source, share in verdict.training.items()
            for name in [verdict.channel]
            if share < CORE_SHARE and verdict.mappable
        }
    )
    matched = [
        matched_ratio(days[source], source, name, train_until, kept=kept)
        for source, name in below
        for kept in (False, True)
        if kept is False or splits.training_exclusions
    ]
    configured = {
        **dict.fromkeys(config.core_channels, "core"),
        **dict.fromkeys(config.extended_channels, "extended"),
    }
    per_year = sorted(
        {year for v in verdicts[:1] for years in v.held_out_years.values() for year in years}
    )
    turbines = {
        source: int(table_["turbine_id"].nunique())
        for source, table_ in days.items()
        if len(table_)
    }
    train_steps = {
        source: int(
            days[source].loc[(days[source]["day"] <= train_until).to_numpy(), "steps"].sum()
        )
        for source in training
    }
    header = "# The core channel rule, measured (M1b step 10)\n\n" + kv_table(
        {
            "config": config_path.as_posix(),
            "splits": config.final.splits_config,
            "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "git_sha": git_sha(paths.repo_root),
            "generated by": "faultline inspect core",
        }
    )
    published = {
        source: {name for name, share in shares(days[source], CHANNEL_NAMES).items() if share > 0}
        for source in training
    }
    report = render_core(
        header,
        verdicts,
        configured,
        per_year,
        controls,
        matched,
        tallies,
        turbines,
        train_steps,
        published,
    )
    destination = paths.data_reports_dir / f"core_rule_{datetime.now(tz=UTC):%Y%m%d}.md"
    destination.write_text(report, encoding="utf-8")
    logger.info("wrote %s", destination)
    return destination
