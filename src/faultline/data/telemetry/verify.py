"""Four checks on the harmonised labels, made before any token is cut (M1b step 9).

Gate 2 accepted the labels of ADR-0009 and left four questions about them open. Each is
answered here from the staged data, by one command (``faultline inspect verification``),
in one tracked report with a section per question:

(a) **What the held-out site's undescribed stop classes are.** ``wtc_ScComSto_timeon`` is
    read as a *commanded* stop, so its downtime is planned and never narrow; read as a
    *communication* stop it could be a fault. The name settles nothing, so every timer is
    profiled by behaviour -- when in the week and the day its stops begin, how long they
    last, whether telemetry is missing while it runs, how many turbines share it at once
    -- and compared, without assuming a pairing, with the provider's own daily summary.
    What a different reading would do to the narrow label is counted, not argued.
(b) **Where the late-period rise begins.** Events per turbine-year for every calendar
    year, the turbine that holds the most of them, and at the Senvion sites the status
    message that opens each narrow event, so that a rise can be placed in time (before,
    or exactly at, the 2023 SCADA export change) and in the fleet (every turbine, or one).
(c) **Whether a channel gap is a shortcut.** Which turbine-years miss a channel while the
    turbine reports, in which split they sit, and whether their event rate differs from
    the rest.
(d) **CARE at the resolution it has.** One labelled anomaly per dataset: dataset counts,
    the interval a dataset-level score can carry at those counts, and the reasons its
    per-step base rates do not compare with the other sites.

Memory stays at one turbine-year of telemetry at a time; the held-out site's stop-class
table, about two million rows of four timers, is the one table read whole.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from faultline.config import load_config
from faultline.data.common.intervals import poisson_interval, rate_ratio_interval, wilson_interval
from faultline.data.common.report import kv_table, section, table
from faultline.data.common.splits import SplitsConfig, assign_splits
from faultline.data.telemetry.adapters import ADAPTERS, get_adapter
from faultline.data.telemetry.adapters.hill_of_towie import HillOfTowieAdapter
from faultline.data.telemetry.downtime import read_downtime
from faultline.data.telemetry.harmonise import (
    alarm_override_steps,
    downtime_stop_steps,
    select_events,
    to_seconds,
)
from faultline.data.telemetry.labels import (
    STEPS_PER_YEAR,
    EventLabelsConfig,
    HarmonisedConfig,
    grid_coverage,
    grid_years,
    in_grid,
    label_column,
)
from faultline.data.telemetry.pipeline import (
    TelemetryPipelineConfig,
    ingest_dir,
    parquet_files,
    stage_source_dir,
)
from faultline.download.zenodo import load_sources_config
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

KEYS = ["turbine_id", "timestamp_utc"]
STEP_SECONDS = 600

# -- (a) stop classes ------------------------------------------------------------------

#: Working hours in UTC, Monday to Friday: 07:00-17:00 UTC is 07:00-18:00 local time at
#: a UK site across the year. A stop somebody schedules starts inside them; a failure of
#: a communication link has no reason to.
WORK_START_HOUR = 7
WORK_END_HOUR = 17
#: The share of run starts that would fall in working hours, and at the weekend, if starts
#: were spread evenly over the week.
UNIFORM_WORKING_SHARE = 5 * (WORK_END_HOUR - WORK_START_HOUR) / (7 * 24)
UNIFORM_WEEKEND_SHARE = 2 / 7
WEEKDAYS: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
#: A rotor turning faster than this is not stopped.
ROTATING_RPM = 1.0
#: A step producing more than this is producing: the threshold the wind envelope's
#: provenance in events_v2.yaml uses for "producing steps".
PRODUCING_KW = 10.0
#: Run lengths, seconds.
DURATION_BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.0, 60.0, "< 1 min"),
    (60.0, 600.0, "1-10 min"),
    (600.0, 3600.0, "10 min-1 h"),
    (3600.0, 6 * 3600.0, "1-6 h"),
    (6 * 3600.0, 24 * 3600.0, "6-24 h"),
    (24 * 3600.0, math.inf, ">= 1 day"),
)
#: The provider's daily summary columns holding hours out of operation per stop class.
#: Every timer is compared with every one of them; no pairing is assumed from the names.
DAILY_HOURS_COLUMNS: tuple[str, ...] = ("OutTurHours", "OutEnvHours", "OutCmdHours", "OutGrdHours")
#: Daily hours agree with a timer's day when they differ by at most three minutes.
DAILY_TOLERANCE_HOURS = 0.05

# -- (c) channel gaps --------------------------------------------------------------------

#: The channel that says a turbine is reporting: the highest coverage at every site.
REFERENCE_CHANNEL = "wind_speed_ms"
#: A turbine-year misses a channel when the channel is absent on more than 5% of the
#: steps on which the turbine reports: the complement of the 95% the core rule asks for.
GAP_THRESHOLD = 0.05
#: The training-site channels gate 2 kept core at about 70% coverage (ADR-0008 evidence
#: note, 2026-09-11), whose turbine-years, splits and event rates are listed in full.
WATCHED: dict[str, tuple[str, ...]] = {
    "penmanshiel": ("pitch_angle_deg", "gearbox_oil_temp_c"),
}

# -- (d) CARE ----------------------------------------------------------------------------

#: Detection rates at which a dataset-level interval is quoted: the widest (0.5), and one
#: a useful detector might reach (0.8).
CARE_RATES: tuple[float, ...] = (0.5, 0.8)


def _share(mask: np.ndarray) -> float:
    return float(np.mean(mask)) if mask.size else math.nan


def _pct(value: float, digits: int = 1) -> str:
    return "n/a" if value != value else f"{value * 100:.{digits}f}%"


def _utc_ns(stamps: pd.Series[Any]) -> pd.Series[Any]:
    return pd.to_datetime(stamps, utc=True).astype("datetime64[ns, UTC]")


# =====================================================================================
# (a) stop classes
# =====================================================================================


def timer_runs(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Runs of consecutive steps in which one stop-class timer is above zero.

    A run is a sequence of consecutive 10-minute steps of one turbine with the timer
    above zero; a step without it, or a missing step, ends the run.

    Args:
        frame: ``turbine_id``, ``timestamp_utc`` and the timer column.
        column: The timer column.

    Returns:
        One row per run: ``turbine_id``, ``start_utc``, ``steps`` and ``seconds``.
    """
    columns = ["turbine_id", "start_utc", "steps", "seconds"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    ordered = frame.sort_values(KEYS, kind="stable").reset_index(drop=True)
    on = (ordered[column].fillna(0) > 0).to_numpy()
    seconds = to_seconds(ordered["timestamp_utc"])
    turbines = ordered["turbine_id"].astype(str).to_numpy()
    follows = np.r_[False, (turbines[1:] == turbines[:-1]) & (np.diff(seconds) == STEP_SECONDS)]
    starts = on & ~(np.r_[False, on[:-1]] & follows)
    chosen = ordered.loc[on].assign(_run=np.cumsum(starts)[on])
    if chosen.empty:
        return pd.DataFrame(columns=columns)
    grouped = chosen.groupby("_run", sort=True)
    return pd.DataFrame(
        {
            "turbine_id": grouped["turbine_id"].first().astype(str),
            "start_utc": grouped["timestamp_utc"].min(),
            "steps": grouped.size().astype(int),
            "seconds": grouped[column].sum().astype(float),
        }
    ).reset_index(drop=True)


@dataclass(frozen=True)
class OnsetProfile:
    """When in the week and the day a set of runs begins.

    Attributes:
        runs: Runs counted.
        weekday: Share of runs starting on each weekday, Monday first.
        hour: Share of runs starting in each hour of the day, UTC.
        working_hours: Share starting Monday to Friday, 07:00-17:00 UTC.
        weekend: Share starting on a Saturday or Sunday.
    """

    runs: int
    weekday: tuple[float, ...]
    hour: tuple[float, ...]
    working_hours: float
    weekend: float

    @property
    def peak_hour(self) -> int:
        """The hour of the day (UTC) in which most runs start."""
        return int(np.argmax(self.hour)) if self.runs else 0


def onset_profile(starts: pd.Series[Any]) -> OnsetProfile:
    """Profile the start times of a set of runs over the week and the day.

    Args:
        starts: Run start times.

    Returns:
        The shares per weekday and hour, in working hours and at the weekend.
    """
    stamps = pd.Series(pd.to_datetime(starts, utc=True))
    count = len(stamps)
    if count == 0:
        return OnsetProfile(0, (0.0,) * 7, (0.0,) * 24, math.nan, math.nan)
    weekday = stamps.dt.weekday.to_numpy(dtype=np.int64)
    hour = stamps.dt.hour.to_numpy(dtype=np.int64)
    working = (weekday < 5) & (hour >= WORK_START_HOUR) & (hour < WORK_END_HOUR)
    return OnsetProfile(
        runs=count,
        weekday=tuple(float(x) for x in np.bincount(weekday, minlength=7) / count),
        hour=tuple(float(x) for x in np.bincount(hour, minlength=24) / count),
        working_hours=float(working.mean()),
        weekend=float((weekday >= 5).mean()),
    )


def duration_shares(seconds: np.ndarray) -> tuple[float, ...]:
    """The share of runs in each duration bucket.

    Args:
        seconds: Seconds of each run.

    Returns:
        One share per :data:`DURATION_BUCKETS` entry.
    """
    values = np.asarray(seconds, dtype=float)
    if values.size == 0:
        return (math.nan,) * len(DURATION_BUCKETS)
    return tuple(float(((values >= lo) & (values < hi)).mean()) for lo, hi, _ in DURATION_BUCKETS)


@dataclass(frozen=True)
class TimerProfile:
    """How one stop-class timer behaves.

    Attributes:
        column: The provider's timer field.
        cause: The cause events_v2.yaml reads it as.
        steps: Steps with the timer above zero.
        seconds: Seconds the timer accounts for.
        onset: When its runs begin.
        median_run_s: Median run length, seconds.
        p90_run_s: 90th percentile run length, seconds.
        durations: Share of runs per duration bucket.
        telemetry_missing: Share of its steps with no core channel on the grid.
        rotating: Share of its steps with the rotor turning.
        producing: Share of its steps producing power.
        turbines_at_once: Median number of turbines with the timer on in the same step.
        farm_wide: Share of its steps with at least half the site's turbines in it too.
    """

    column: str
    cause: str
    steps: int
    seconds: float
    onset: OnsetProfile
    median_run_s: float
    p90_run_s: float
    durations: tuple[float, ...]
    telemetry_missing: float
    rotating: float
    producing: float
    turbines_at_once: float
    farm_wide: float


def profile_timers(
    state: pd.DataFrame, causes: Mapping[str, str], turbines: int
) -> list[TimerProfile]:
    """Profile every stop-class timer on a table of timers joined to the grid.

    Args:
        state: One row per (turbine, step): the timers, ``telemetry_present``,
            ``power_kw`` and ``rotor_speed_rpm``.
        causes: Timer column to the cause events_v2.yaml reads it as.
        turbines: Turbines at the site, for the farm-wide share.

    Returns:
        One profile per timer, in the order of ``causes``.
    """
    half = math.ceil(turbines / 2)
    profiles = []
    for column, cause in causes.items():
        on = (state[column].fillna(0) > 0).to_numpy()
        runs = timer_runs(state[[*KEYS, column]], column)
        active = state.loc[on]
        at_once = active.groupby("timestamp_utc")["turbine_id"].transform("size").to_numpy()
        run_seconds = runs["seconds"].to_numpy(dtype=float)
        profiles.append(
            TimerProfile(
                column=column,
                cause=cause,
                steps=int(on.sum()),
                seconds=float(state[column].fillna(0).clip(lower=0).sum()),
                onset=onset_profile(runs["start_utc"]),
                median_run_s=float(np.median(run_seconds)) if run_seconds.size else math.nan,
                p90_run_s=float(np.quantile(run_seconds, 0.9)) if run_seconds.size else math.nan,
                durations=duration_shares(run_seconds),
                telemetry_missing=_share(~active["telemetry_present"].to_numpy(dtype=bool)),
                rotating=_share((active["rotor_speed_rpm"] > ROTATING_RPM).to_numpy()),
                producing=_share((active["power_kw"] > PRODUCING_KW).to_numpy()),
                turbines_at_once=float(np.median(at_once)) if at_once.size else math.nan,
                farm_wide=_share(at_once >= half),
            )
        )
    return profiles


def daily_agreement(
    state: pd.DataFrame,
    daily: pd.DataFrame,
    timers: Sequence[str],
    columns: Sequence[str],
) -> tuple[pd.DataFrame, int]:
    """Compare each timer's hours per turbine-day with each daily-summary column.

    No pairing is assumed from the names: every timer meets every column. Two days that
    are both zero agree trivially, so agreement is counted over the turbine-days on which
    either side is above zero.

    Args:
        state: One row per (turbine, step) with the timer columns.
        daily: ``turbine_id``, ``day`` and the daily-summary columns.
        timers: Timer columns.
        columns: Daily-summary columns, in hours.

    Returns:
        The share of such turbine-days agreeing within :data:`DAILY_TOLERANCE_HOURS`,
        timers by columns, and the number of turbine-days compared.
    """
    days = pd.to_datetime(state["timestamp_utc"], utc=True).dt.floor("D")
    hours = state.assign(day=days).groupby(["turbine_id", "day"])[list(timers)].sum() / 3600.0
    present = [name for name in columns if name in daily.columns]
    summary = daily.assign(day=pd.to_datetime(daily["day"], utc=True)).set_index(
        ["turbine_id", "day"]
    )[present]
    joined = hours.join(summary, how="inner")
    result = pd.DataFrame(np.nan, index=list(timers), columns=list(columns))
    for timer in timers:
        ours = joined[timer].to_numpy(dtype=float)
        for name in present:
            theirs = pd.to_numeric(joined[name], errors="coerce").to_numpy(dtype=float)
            usable = np.isfinite(ours) & np.isfinite(theirs) & ((ours > 0) | (theirs > 0))
            if usable.any():
                close = np.abs(ours[usable] - theirs[usable]) <= DAILY_TOLERANCE_HOURS
                result.loc[timer, name] = float(close.mean())
    return result, int(len(joined))


@dataclass(frozen=True)
class Reclassification:
    """What reading one timer as another cause does to the narrow label.

    Attributes:
        column: The timer.
        now: The cause events_v2.yaml reads it as.
        then: The cause it is read as instead.
        events_now: Narrow events on the grid under the configured reading.
        events_then: Narrow events under the other reading.
        unchanged: Events of the configured reading found identical in the other.
        changed: Events of the configured reading that the other extends or merges.
        added: Events of the other reading overlapping no event of the configured one.
    """

    column: str
    now: str
    then: str
    events_now: int
    events_then: int
    unchanged: int
    changed: int
    added: int

    @property
    def moved(self) -> float:
        """Changed and added events as a share of the configured narrow events."""
        return (self.changed + self.added) / self.events_now if self.events_now else math.nan


def compare_event_sets(now: pd.DataFrame, then: pd.DataFrame) -> tuple[int, int, int]:
    """Count how one event table differs from another of the same label set.

    Args:
        now: Events under the configured reading: ``turbine_id``, ``start_utc``,
            ``end_utc``.
        then: Events under another reading, same columns.

    Returns:
        Events of ``now`` found identical in ``then``; events of ``now`` that are not;
        and events of ``then`` that overlap no event of ``now``.
    """
    key = ["turbine_id", "start_utc", "end_utc"]

    def normal(frame: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "turbine_id": frame["turbine_id"].astype(str).to_numpy(),
                "start_utc": _utc_ns(frame["start_utc"]).to_numpy(),
                "end_utc": _utc_ns(frame["end_utc"]).to_numpy(),
            }
        )

    ours, theirs = normal(now), normal(then)
    unchanged = int(len(ours.merge(theirs.drop_duplicates(), on=key, how="inner")))
    pairs = theirs.reset_index().merge(ours, on="turbine_id", suffixes=("", "_now"))
    overlap = (pairs["start_utc"] < pairs["end_utc_now"]) & (
        pairs["start_utc_now"] < pairs["end_utc"]
    )
    touched = int(pairs.loc[overlap, "index"].nunique())
    return unchanged, len(ours) - unchanged, len(theirs) - touched


@dataclass
class StopClassEvidence:
    """Everything section (a) measures at one site.

    Attributes:
        source: Source identifier.
        years: Calendar years read.
        turbines: Turbines at the site.
        steps: Grid steps with a stop-class row.
        profiles: One profile per timer.
        agreement: Daily agreement, timers by daily-summary columns.
        days: Turbine-days compared with the daily summary.
        reclassified: One entry per timer not read as a narrow cause.
        turbine_years: Grid time, turbine-years.
    """

    source: str
    years: list[int]
    turbines: int
    steps: int
    profiles: list[TimerProfile]
    agreement: pd.DataFrame
    days: int
    reclassified: list[Reclassification]
    turbine_years: float


def _grid_state(grid_files: Sequence[Path], core: Sequence[str]) -> pd.DataFrame:
    """Per grid step: whether any core channel has a value, the power and the rotor speed."""
    parts = []
    for path in grid_files:
        frame = pd.read_parquet(path)
        if frame.empty:
            continue
        present = [name for name in core if name in frame.columns]
        part = pd.DataFrame(
            {
                "turbine_id": frame["turbine_id"].astype(str).to_numpy(),
                "timestamp_utc": _utc_ns(frame["timestamp_utc"]).to_numpy(),
                "telemetry_present": frame[present].notna().any(axis=1).to_numpy()
                if present
                else np.zeros(len(frame), dtype=bool),
            }
        )
        for name in ("power_kw", "rotor_speed_rpm"):
            part[name] = frame[name].to_numpy(dtype=float) if name in frame.columns else np.nan
        parts.append(part)
    grid = pd.concat(parts, ignore_index=True)
    grid["timestamp_utc"] = _utc_ns(grid["timestamp_utc"])
    return grid


def stop_class_evidence(
    paths: ProjectPaths,
    config: TelemetryPipelineConfig,
    rule: HarmonisedConfig,
    source: str,
) -> StopClassEvidence:
    """Measure section (a) at a site that publishes stop-class timers.

    Args:
        paths: Resolved project paths.
        config: The configuration the cleaned grid was produced under.
        rule: The harmonised rule, which names the timers and their causes.
        source: The source, Hill of Towie.

    Returns:
        The timer profiles, the daily-summary agreement and the reclassification counts.

    Raises:
        TypeError: If the source's adapter publishes no daily summary.
        FileNotFoundError: If the downtime series is not staged.
    """
    adapter = get_adapter(source, paths.configs_dir)
    if not isinstance(adapter, HillOfTowieAdapter):
        raise TypeError(f"{source}: stop classes are read from the Hill of Towie tables only")
    members = adapter.discover(paths.source_dir("raw", "telemetry", source))
    grid_files = parquet_files(stage_source_dir(paths, "cleaned", source))
    years = grid_years(grid_files)
    causes = dict(rule.stop_classes.fields)
    classes = adapter.read_stop_classes(members, years, rule.stop_classes.table, list(causes))
    classes["timestamp_utc"] = _utc_ns(classes["timestamp_utc"])
    core = list(config.core_channels) or list(config.channels)
    state = classes.merge(_grid_state(grid_files, core), on=KEYS, how="inner")
    turbines = int(state["turbine_id"].nunique())
    profiles = profile_timers(state, causes, turbines)
    daily = adapter.read_daily_summary(members, years, DAILY_HOURS_COLUMNS)
    agreement, days = daily_agreement(state, daily, list(causes), DAILY_HOURS_COLUMNS)

    covered = grid_coverage(grid_files)
    series = [member for member in members if member.kind == "downtime_series"]
    if not series:
        raise FileNotFoundError(f"{source}: no downtime series staged")
    # A step late in December looks into January of the next year, as in the label stage.
    downtime = read_downtime(series[0], years | {year + 1 for year in years})
    alarms = pd.read_parquet(ingest_dir(paths, source) / "events.parquet")
    overrides = alarm_override_steps(alarms, rule.code_causes)

    def narrow(reading: Mapping[str, str]) -> pd.DataFrame:
        steps, _ = downtime_stop_steps(downtime, classes, reading, overrides, count_steps=covered)
        events = select_events(steps, rule.narrow_causes, rule.min_duration_s)
        return events[in_grid(events, covered)]

    now = narrow(causes)
    reclassified = []
    for column, cause in causes.items():
        if cause in rule.narrow_causes:
            continue
        then = narrow({**causes, column: rule.narrow_causes[0]})
        unchanged, changed, added = compare_event_sets(now, then)
        reclassified.append(
            Reclassification(
                column=column,
                now=cause,
                then=rule.narrow_causes[0],
                events_now=len(now),
                events_then=len(then),
                unchanged=unchanged,
                changed=changed,
                added=added,
            )
        )
    steps = sum(len(stamps) for stamps in covered.values())
    return StopClassEvidence(
        source=source,
        # Years with at least a day of grid: moving interval-end labels to interval start
        # leaves one-row files in the year before each staged year.
        years=sorted(
            int(year)
            for year, count in state["timestamp_utc"].dt.year.value_counts().items()
            if count >= 144
        ),
        turbines=turbines,
        steps=int(len(state)),
        profiles=profiles,
        agreement=agreement,
        days=days,
        reclassified=reclassified,
        turbine_years=steps / STEPS_PER_YEAR,
    )


# =====================================================================================
# (b) the late period
# =====================================================================================


@dataclass(frozen=True)
class YearRow:
    """One calendar year at one site.

    Attributes:
        year: Calendar year.
        split: The split the whole year falls in, or ``mixed``.
        steps: Grid steps.
        narrow: Narrow events starting in the year.
        broad: Broad events starting in the year.
        busiest: The turbine with the most narrow events.
        busiest_narrow: Its narrow events.
        leading: Narrow events opened by the site's leading late-period message.
    """

    year: int
    split: str
    steps: int
    narrow: int
    broad: int
    busiest: str
    busiest_narrow: int
    leading: int

    @property
    def turbine_years(self) -> float:
        """Grid time in turbine-years."""
        return self.steps / STEPS_PER_YEAR


@dataclass
class SiteYears:
    """Section (b) at one site.

    Attributes:
        source: Source identifier.
        rows: One row per calendar year with at least a day of grid.
        leading_message: The message whose narrow events rose most from the training
            period to the late period; ``None`` where no message is published.
        opening: Narrow events per opening message (rows) and year (columns), top six.
        export_columns: Each status-export column set with the years it appears in.
    """

    source: str
    rows: list[YearRow]
    leading_message: str | None = None
    opening: pd.DataFrame | None = None
    export_columns: list[tuple[tuple[str, ...], list[int]]] | None = None

    def pooled(self, split: str) -> tuple[int, int]:
        """Narrow events and grid steps over the years of one split."""
        rows = [row for row in self.rows if row.split == split]
        return sum(row.narrow for row in rows), sum(row.steps for row in rows)

    @property
    def routine_year(self) -> int | None:
        """The first year the leading message opens more than one event per turbine-year."""
        for row in self.rows:
            if row.steps and row.leading / row.turbine_years > 1.0:
                return row.year
        return None

    @property
    def onset(self) -> int | None:
        """The first year after training whose 95% interval lies above the training rate."""
        events, steps = self.pooled("train")
        if not steps:
            return None
        rate = events / (steps / STEPS_PER_YEAR)
        for row in self.rows:
            if row.split in ("val", "test") and row.steps:
                lower, _ = poisson_interval(row.narrow)
                if lower / row.turbine_years > rate:
                    return row.year
        return None


def split_of_year(year: int, source: str, site: str, config: SplitsConfig) -> str:
    """The split a whole calendar year falls in at one source, or ``mixed``.

    Args:
        year: Calendar year.
        source: Source identifier.
        site: Site name, as the adapters write it.
        config: The split specification.

    Returns:
        The split of the year's first and last step when they agree, else ``mixed``.
    """
    probe = pd.DataFrame(
        {
            config.time_column: pd.to_datetime(
                [f"{year}-01-01 00:00", f"{year}-12-31 23:50"], utc=True
            ),
            config.source_column: source,
        }
    )
    if config.site_column != config.source_column:
        probe[config.site_column] = site
    labels = assign_splits(probe, config)
    return str(labels.iloc[0]) if labels.iloc[0] == labels.iloc[1] else "mixed"


def opening_messages(
    events: pd.DataFrame, stream: pd.DataFrame, cause: str, stop_status: str
) -> pd.Series[Any]:
    """The status message that opens each event.

    It is the first stop row of the event's cause starting in the event's first step, or
    failing that the last such row started before it -- a stop running into the step.

    Args:
        events: Events with ``turbine_id`` and ``start_utc``.
        stream: The status stream: ``turbine_id``, ``start_utc``, ``message``,
            ``provider_status`` and ``cause``.
        cause: The cause of the events.
        stop_status: The provider status marking a stop row.

    Returns:
        A message per event, aligned with ``events.index``; missing where none is found.
    """
    stops = stream[(stream["provider_status"] == stop_status) & (stream["cause"] == cause)]
    result = pd.Series(pd.NA, index=events.index, dtype="string")
    if stops.empty or events.empty:
        return result
    stop_turbines = stops["turbine_id"].astype(str).to_numpy()
    stop_seconds = to_seconds(stops["start_utc"])
    stop_messages = stops["message"].astype("string").to_numpy()
    event_seconds = to_seconds(events["start_utc"])
    event_turbines = events["turbine_id"].astype(str).to_numpy()
    for turbine in np.unique(event_turbines):
        mine = np.flatnonzero(stop_turbines == turbine)
        if mine.size == 0:
            continue
        order = mine[np.argsort(stop_seconds[mine], kind="stable")]
        seconds = stop_seconds[order]
        wanted = np.flatnonzero(event_turbines == turbine)
        starts = event_seconds[wanted]
        low = np.searchsorted(seconds, starts, side="left")
        high = np.searchsorted(seconds, starts + STEP_SECONDS, side="left")
        pick = np.where(high > low, low, low - 1)
        found = pick >= 0
        result.iloc[wanted[found]] = stop_messages[order[pick[found]]]
    return result


def export_column_sets(events: pd.DataFrame) -> list[tuple[tuple[str, ...], list[int]]]:
    """The provider's status-export column sets, with the years each appears in.

    Read from the first preserved raw row of each turbine and month: one export file has
    one header, so its first row carries the file's columns.

    Args:
        events: Ingested events with ``turbine_id``, ``start_utc`` and ``raw``.

    Returns:
        Each distinct column set, in order of first appearance, with its years.
    """
    stamps = pd.to_datetime(events["start_utc"], utc=True)
    firsts = events.assign(_month=stamps.dt.strftime("%Y-%m"), _year=stamps.dt.year)
    firsts = firsts.dropna(subset=["raw"]).drop_duplicates(subset=["turbine_id", "_month"])
    sets: dict[tuple[str, ...], set[int]] = {}
    order: list[tuple[str, ...]] = []
    for raw, year in zip(firsts["raw"], firsts["_year"], strict=True):
        columns = tuple(sorted(json.loads(str(raw))))
        if columns not in sets:
            sets[columns] = set()
            order.append(columns)
        sets[columns].add(int(year))
    return [(columns, sorted(sets[columns])) for columns in order]


def site_years(
    paths: ProjectPaths,
    source: str,
    splits: SplitsConfig,
    rules: EventLabelsConfig,
) -> SiteYears:
    """Measure section (b) at one site.

    Args:
        paths: Resolved project paths.
        source: Source identifier.
        splits: The split specification.
        rules: The labelling file.

    Returns:
        Events per year, their busiest turbine, and at a status-string site the message
        that opens each narrow event and the export's column sets.
    """
    cleaned = stage_source_dir(paths, "cleaned", source)
    steps: Counter[int] = Counter()
    site = source
    for path in parquet_files(cleaned):
        frame = pd.read_parquet(path, columns=["site", "timestamp_utc"])
        if frame.empty:
            continue
        site = str(frame["site"].iloc[0])
        steps.update(pd.to_datetime(frame["timestamp_utc"], utc=True).dt.year.tolist())
    events = {}
    for name in ("narrow", "broad"):
        table_ = pd.read_parquet(cleaned / "labels" / f"events_{name}.parquet")
        events[name] = table_[table_["in_grid"]].reset_index(drop=True)
    narrow = events["narrow"]
    narrow_years = pd.to_datetime(narrow["start_utc"], utc=True).dt.year
    broad_years = pd.to_datetime(events["broad"]["start_utc"], utc=True).dt.year
    years = sorted(year for year, count in steps.items() if count >= 144)
    split = {year: split_of_year(year, source, site, splits) for year in years}

    result = SiteYears(source=source, rows=[])
    leading = pd.Series(False, index=narrow.index)
    rule = rules.harmonised
    stream_path = cleaned / "labels" / "status_stream.parquet"
    if rule is not None and source in rules.status_strings.sources and stream_path.is_file():
        stream = pd.read_parquet(stream_path)
        opened = opening_messages(narrow, stream, rule.narrow_causes[0], rule.stop_status)
        table_ = pd.crosstab(opened.fillna("(none found)"), narrow_years)
        late = [year for year in years if split[year] == "test"]
        train = [year for year in years if split[year] == "train"]
        train_ty = sum(steps[year] for year in train) / STEPS_PER_YEAR
        late_ty = sum(steps[year] for year in late) / STEPS_PER_YEAR
        if train_ty and late_ty:
            rise = (
                table_.reindex(columns=late, fill_value=0).sum(axis=1) / late_ty
                - table_.reindex(columns=train, fill_value=0).sum(axis=1) / train_ty
            )
            result.leading_message = str(rise.idxmax())
            leading = (opened == result.leading_message).fillna(False)
        top = table_.sum(axis=1).sort_values(ascending=False).index[:6]
        result.opening = table_.loc[top]
        ingested = pd.read_parquet(ingest_dir(paths, source) / "events.parquet")
        result.export_columns = export_column_sets(ingested)

    for year in years:
        in_year = narrow[(narrow_years == year).to_numpy()]
        per_turbine = in_year["turbine_id"].astype(str).value_counts()
        result.rows.append(
            YearRow(
                year=year,
                split=split[year],
                steps=steps[year],
                narrow=len(in_year),
                broad=int((broad_years == year).sum()),
                busiest=str(per_turbine.index[0]) if len(per_turbine) else "-",
                busiest_narrow=int(per_turbine.iloc[0]) if len(per_turbine) else 0,
                leading=int(leading[(narrow_years == year).to_numpy()].sum()),
            )
        )
    return result


# =====================================================================================
# (c) channel gaps
# =====================================================================================


@dataclass(frozen=True)
class GapRow:
    """One turbine-year's coverage of every core channel, and its labels.

    Attributes:
        source: Source identifier.
        turbine: Turbine identifier.
        year: Calendar year.
        split: The split the year falls in.
        steps: Grid steps.
        reporting: Steps with the reference channel present.
        missing: Per core channel, the share of reporting steps where it is missing.
        narrow: Narrow events starting in the turbine-year.
        known_missing: Reporting steps with a known label and a watched channel missing.
        positive_missing: Of those, the positive ones.
        known_present: Reporting steps with a known label and every watched channel present.
        positive_present: Of those, the positive ones.
    """

    source: str
    turbine: str
    year: int
    split: str
    steps: int
    reporting: int
    missing: dict[str, float]
    narrow: int
    known_missing: int
    positive_missing: int
    known_present: int
    positive_present: int

    def affected(self, channels: Sequence[str]) -> bool:
        """Whether any of the channels is missing on more than the gap threshold."""
        return any(self.missing.get(name, 0.0) > GAP_THRESHOLD for name in channels)


def channel_gaps(
    paths: ProjectPaths,
    source: str,
    core: Sequence[str],
    watched: Sequence[str],
    splits: SplitsConfig,
    label: str,
) -> list[GapRow]:
    """Measure section (c) at one training site, one turbine-year at a time.

    Args:
        paths: Resolved project paths.
        source: Source identifier.
        core: Core channels, each measured per turbine-year.
        watched: Channels whose missing steps are compared with the rest on the label.
        splits: The split specification.
        label: The label column compared, for example ``narrow_within_24h``.

    Returns:
        One row per turbine-year with grid.
    """
    cleaned = stage_source_dir(paths, "cleaned", source)
    narrow = pd.read_parquet(cleaned / "labels" / "events_narrow.parquet")
    narrow = narrow[narrow["in_grid"]]
    narrow_turbines = narrow["turbine_id"].astype(str).to_numpy()
    narrow_seconds = to_seconds(narrow["start_utc"])
    rows = []
    for path in parquet_files(cleaned):
        frame = pd.read_parquet(path)
        if frame.empty or REFERENCE_CHANNEL not in frame.columns:
            continue
        turbine = str(frame["turbine_id"].iloc[0])
        year = int(path.stem.rsplit("__", 1)[-1])
        seconds = to_seconds(frame["timestamp_utc"])
        reporting = frame[REFERENCE_CHANNEL].notna().to_numpy()
        missing = {}
        for name in core:
            absent = (
                frame[name].isna().to_numpy()
                if name in frame.columns
                else np.ones(len(frame), dtype=bool)
            )
            missing[name] = (
                float((absent & reporting).sum() / reporting.sum()) if reporting.any() else 0.0
            )
        gap = np.zeros(len(frame), dtype=bool)
        for name in watched:
            gap |= frame[name].isna().to_numpy() if name in frame.columns else True
        labels_path = cleaned / "labels" / path.name
        known = np.zeros(len(frame), dtype=bool)
        positive = np.zeros(len(frame), dtype=bool)
        if labels_path.is_file():
            labels = pd.read_parquet(labels_path, columns=["timestamp_utc", label])
            aligned = pd.DataFrame({"s": seconds}).merge(
                pd.DataFrame(
                    {"s": to_seconds(labels["timestamp_utc"]), "y": labels[label].astype("boolean")}
                ),
                on="s",
                how="left",
            )["y"]
            known = aligned.notna().to_numpy() & reporting
            positive = aligned.fillna(False).to_numpy(dtype=bool) & reporting
        in_file = (
            (narrow_turbines == turbine)
            & (narrow_seconds >= seconds.min())
            & (narrow_seconds <= seconds.max())
        )
        rows.append(
            GapRow(
                source=source,
                turbine=turbine,
                year=year,
                split=split_of_year(year, source, str(frame["site"].iloc[0]), splits),
                steps=len(frame),
                reporting=int(reporting.sum()),
                missing=missing,
                narrow=int(in_file.sum()),
                known_missing=int((known & gap).sum()),
                positive_missing=int((positive & gap).sum()),
                known_present=int((known & ~gap).sum()),
                positive_present=int((positive & ~gap).sum()),
            )
        )
    return rows


# =====================================================================================
# (d) CARE
# =====================================================================================


@dataclass
class CareProbe:
    """CARE at dataset level.

    Attributes:
        source: Source identifier.
        datasets: Per farm, datasets per provider label (``anomaly``, ``normal``).
        steps: Per farm, grid steps.
        presence: Per farm, the non-null share of each core channel on the clean grid.
        power_bound: The configured power bound at CARE, which is per unit, not kW.
        absolute_time: Whether the source specification declares real calendar time.
    """

    source: str
    datasets: dict[str, Counter[str]]
    steps: dict[str, int]
    presence: dict[str, dict[str, float]]
    power_bound: tuple[float, float] | None
    absolute_time: bool

    def total(self, label: str, farms: Sequence[str] | None = None) -> int:
        """Datasets with one provider label, over the given farms or all of them."""
        chosen = farms if farms is not None else list(self.datasets)
        return sum(self.datasets[farm].get(label, 0) for farm in chosen if farm in self.datasets)


def care_probe(
    paths: ProjectPaths, config: TelemetryPipelineConfig, source: str, core: Sequence[str]
) -> CareProbe:
    """Measure section (d).

    Args:
        paths: Resolved project paths.
        config: The telemetry configuration, for the configured power bound.
        source: The CARE source identifier.
        core: Core channels, measured per farm.

    Returns:
        Dataset counts, grid steps and channel presence per farm.
    """
    events = pd.read_parquet(ingest_dir(paths, source) / "events.parquet")
    farms = events["turbine_id"].astype(str).str.split(":").str[0]
    datasets: dict[str, Counter[str]] = {}
    for farm, label in zip(farms, events["category"].astype(str), strict=True):
        datasets.setdefault(str(farm), Counter())[label] += 1
    steps: Counter[str] = Counter()
    present: dict[str, Counter[str]] = {}
    for path in parquet_files(stage_source_dir(paths, "cleaned", source)):
        frame = pd.read_parquet(path)
        if frame.empty:
            continue
        farm = str(frame["turbine_id"].iloc[0]).split(":")[0]
        steps[farm] += len(frame)
        counts = present.setdefault(farm, Counter())
        for name in core:
            if name in frame.columns:
                counts[name] += int(frame[name].notna().sum())
    bound = config.bounds_for(source).get("power_kw")
    sources = load_sources_config(paths.configs_dir / "data" / "sources_telemetry.yaml")
    spec = sources.sources.get(source)
    return CareProbe(
        source=source,
        datasets=dict(sorted(datasets.items())),
        steps=dict(sorted(steps.items())),
        presence={
            farm: {name: present[farm][name] / steps[farm] for name in core}
            for farm in sorted(steps)
            if steps[farm]
        },
        power_bound=(bound.min, bound.max) if bound is not None else None,
        absolute_time=bool(spec.absolute_time) if spec is not None else True,
    )


# =====================================================================================
# the report
# =====================================================================================


def _hours(seconds: float) -> str:
    if seconds != seconds:
        return "n/a"
    if seconds < 3600:
        return f"{seconds / 60:.0f} min"
    return f"{seconds / 3600:.1f} h"


def _stop_class_section(evidence: StopClassEvidence) -> str:
    """Section (a)."""
    names = [p.column.removeprefix("wtc_").removesuffix("_timeon") for p in evidence.profiles]
    overview = table(
        [
            "timer",
            "read as (events_v2)",
            "steps",
            "runs",
            "hours",
            "runs starting Mon-Fri 07-17 UTC",
            "runs starting at the weekend",
            "peak hour (UTC), share",
            "median run",
            "p90 run",
        ],
        [
            (
                f"`{p.column}`",
                p.cause,
                p.steps,
                p.onset.runs,
                round(p.seconds / 3600),
                f"{_pct(p.onset.working_hours)} (even: {_pct(UNIFORM_WORKING_SHARE)})",
                f"{_pct(p.onset.weekend)} (even: {_pct(UNIFORM_WEEKEND_SHARE)})",
                f"{p.onset.peak_hour:02d}:00, {_pct(p.onset.hour[p.onset.peak_hour])}",
                _hours(p.median_run_s),
                _hours(p.p90_run_s),
            )
            for p in evidence.profiles
        ],
    )
    weekday = table(
        ["timer", *WEEKDAYS],
        [
            (name, *(_pct(x) for x in p.onset.weekday))
            for name, p in zip(names, evidence.profiles, strict=True)
        ],
    )
    hours = table(
        ["timer", *(f"{h:02d}" for h in range(24))],
        [
            (name, *(f"{x * 100:.0f}" for x in p.onset.hour))
            for name, p in zip(names, evidence.profiles, strict=True)
        ],
    )
    durations = table(
        ["timer", *(label for _, _, label in DURATION_BUCKETS)],
        [
            (name, *(_pct(x) for x in p.durations))
            for name, p in zip(names, evidence.profiles, strict=True)
        ],
    )
    state = table(
        [
            "timer",
            "steps with no core telemetry",
            "steps with the rotor turning (> 1 rpm)",
            "steps producing (> 10 kW)",
            "turbines in the class in the same step (median)",
            f"steps with at least {math.ceil(evidence.turbines / 2)} of "
            f"{evidence.turbines} turbines in it",
        ],
        [
            (
                name,
                _pct(p.telemetry_missing, 2),
                _pct(p.rotating),
                _pct(p.producing),
                f"{p.turbines_at_once:g}",
                _pct(p.farm_wide),
            )
            for name, p in zip(names, evidence.profiles, strict=True)
        ],
    )
    agreement = table(
        ["timer", *(f"`{c}`" for c in evidence.agreement.columns)],
        [
            (name, *(_pct(v) for v in values))
            for name, values in zip(
                names, evidence.agreement.to_numpy(dtype=float).tolist(), strict=True
            )
        ],
    )
    moves = table(
        [
            "timer read as technical",
            "configured reading",
            "narrow events now (/ty)",
            "narrow events then (/ty)",
            "unchanged",
            "extended or merged",
            "added",
            "share of the narrow label that moves",
        ],
        [
            (
                f"`{r.column}`",
                r.now,
                f"{r.events_now:,} ({r.events_now / evidence.turbine_years:.1f})",
                f"{r.events_then:,} ({r.events_then / evidence.turbine_years:.1f})",
                r.unchanged,
                r.changed,
                r.added,
                _pct(r.moved),
            )
            for r in evidence.reclassified
        ],
    )
    body = (
        kv_table(
            {
                "source": evidence.source,
                "years": ", ".join(str(y) for y in evidence.years),
                "turbines": evidence.turbines,
                "grid steps with a stop-class row": evidence.steps,
                "working hours": f"Monday to Friday, {WORK_START_HOUR:02d}:00-"
                f"{WORK_END_HOUR:02d}:00 UTC ({_pct(UNIFORM_WORKING_SHARE)} of the week)",
                "a run": "consecutive 10-minute steps of one turbine with the timer above zero",
            }
        )
        + "\nEach timer is profiled by what it does, not by its name. A stop someone commands "
        "begins in working hours and on weekdays; a failure of a link or of a component "
        "begins at any hour. A communication outage leaves the telemetry missing while it "
        "lasts; a grid event stops the whole farm at once.\n\n"
        + overview
        + "\n**Run starts per weekday**\n\n"
        + weekday
        + "\n**Run starts per hour of the day (UTC, percent)**\n\n"
        + hours
        + "\n**Run lengths**\n\n"
        + durations
        + "\n**The turbine and the farm while the timer runs**\n\n"
        + state
        + f"\n**Against the provider's daily summary.** Share of turbine-days on which a "
        f"timer's hours and a `tblDailySummary` column agree within "
        f"{DAILY_TOLERANCE_HOURS * 60:.0f} minutes, over the {evidence.days:,} turbine-days "
        "compared, counting only days on which either is above zero. Every timer meets every "
        "column; no pairing is assumed.\n\n"
        + agreement
        + "\n**What another reading would do to the narrow label.** Each timer not read as "
        "technical is read as technical instead, the per-step table rebuilt and the one rule "
        "applied again (ADR-0009). An event of the configured narrow label is `unchanged` "
        "when the same turbine, start and end recur; otherwise its downtime merged with the "
        "timer's and it is `extended or merged`. `added` counts new events.\n\n" + moves
    )
    return section(f"(a) Stop classes at {evidence.source}: what each timer does", body)


def _years_section(sites: Sequence[SiteYears], splits: SplitsConfig) -> str:
    """Section (b)."""
    body = (
        "Narrow events per turbine-year of grid time for every calendar year with at least "
        "a day of grid, with the 95% interval of the count (Byar's approximation to the "
        "exact Poisson interval) divided by the same exposure. `onset` is the first year "
        f"after training (train to {splits.time.train_until:%Y-%m-%d}) whose whole interval "
        "lies above the pooled training rate. The leading message is the one whose narrow "
        "events rose most, per turbine-year, from the training years to the late test; it "
        "is found, not chosen.\n"
    )
    for site in sites:
        train_events, train_steps = site.pooled("train")
        late_events, late_steps = site.pooled("test")
        rows = []
        for row in site.rows:
            low, high = poisson_interval(row.narrow)
            ty = row.turbine_years
            busiest = row.busiest_narrow / row.narrow if row.narrow else math.nan
            rows.append(
                (
                    str(row.year),
                    row.split,
                    f"{ty:.2f}",
                    f"{row.narrow:,} ({row.narrow / ty:.1f})",
                    f"{low / ty:.1f}-{high / ty:.1f}",
                    f"{row.broad:,} ({row.broad / ty:.1f})",
                    f"{row.busiest} ({row.busiest_narrow}, {_pct(busiest, 0)})",
                    *(
                        (
                            f"{row.leading}",
                            f"{(row.narrow - row.leading) / ty:.1f}",
                        )
                        if site.leading_message
                        else ()
                    ),
                )
            )
        headers = [
            "year",
            "split",
            "turbine-years",
            "narrow (/ty)",
            "narrow /ty, 95%",
            "broad (/ty)",
            "busiest turbine (narrow, share)",
        ]
        if site.leading_message:
            headers += ["opened by the leading message", "narrow /ty without it"]
        facts: dict[str, Any] = {}
        if train_steps:
            train_rate = train_events / (train_steps / STEPS_PER_YEAR)
            facts["training-period narrow rate"] = f"{train_rate:.2f} /ty ({train_events:,} events)"
            if late_steps:
                late_rate = late_events / (late_steps / STEPS_PER_YEAR)
                facts["late-test narrow rate"] = (
                    f"{late_rate:.2f} /ty ({late_events:,} events), "
                    f"{late_rate / train_rate:.2f} x training"
                )
            facts["onset of the rise"] = str(site.onset) if site.onset is not None else "none"
        if site.leading_message:
            facts["leading late-period message"] = f"`{site.leading_message}`"
            facts["first year it opens more than one narrow event per turbine-year"] = (
                str(site.routine_year) if site.routine_year is not None else "none"
            )
            opened = sum(row.leading for row in site.rows if row.split == "test")
            if late_steps:
                late_ty = late_steps / STEPS_PER_YEAR
                facts["late-test narrow rate without it"] = (
                    f"{(late_events - opened) / late_ty:.2f} /ty "
                    f"({late_events - opened:,} events; it opens {opened:,})"
                )
        body += f"\n### {site.source}\n\n"
        if facts:
            body += kv_table(facts) + "\n"
        body += table(headers, rows)
        if site.opening is not None:
            body += "\n**Narrow events by the status message that opens them (top six)**\n\n"
            body += table(
                ["message", *(str(c) for c in site.opening.columns)],
                [
                    (f"`{index}`", *(int(v) for v in values))
                    for index, values in site.opening.iterrows()
                ],
            )
        if site.export_columns:
            first = set(site.export_columns[0][0])
            body += (
                "\n**The status export's columns, per year** (first row of each turbine and "
                "month)\n\n"
                + table(
                    ["column set", "years", "columns against the first set"],
                    [
                        (
                            index + 1,
                            ", ".join(str(y) for y in years),
                            "first set"
                            if index == 0
                            else "; ".join(
                                [f"+ `{c}`" for c in sorted(set(columns) - first)]
                                + [f"- `{c}`" for c in sorted(first - set(columns))]
                            )
                            or "same columns",
                        )
                        for index, (columns, years) in enumerate(site.export_columns)
                    ],
                )
            )
    if any(site.leading_message for site in sites):
        body += (
            "\n**Reading (M1b gate 3).** The late split is a temporal hold-out that carries a "
            "change in what is labelled, and it is not a drift test. The leading message "
            "opens stops in routine volume from the same year at both training sites, which "
            "a reporting or firmware change explains and simultaneous degradation of two "
            "farms does not, and single turbines hold most of it. Every late-test result is "
            "reported twice, with and without the events the leading message opens "
            "(ADR-0009, evidence note of 2026-09-11).\n"
        )
    return section("(b) The late period: events per year", body)


def _gaps_section(rows: Mapping[str, list[GapRow]], core: Sequence[str], label: str) -> str:
    """Section (c)."""
    body = (
        f"A turbine-year misses a channel when the channel is absent on more than "
        f"{GAP_THRESHOLD * 100:.0f}% of the steps on which the turbine reports "
        f"`{REFERENCE_CHANNEL}` -- the complement of the 95% the core rule asks for, and a "
        "gap of the channel's own rather than one of the whole turbine.\n\n"
    )
    matrix = []
    for source, gaps in rows.items():
        for name in core:
            counts = Counter(row.split for row in gaps if row.affected([name]))
            total = Counter(row.split for row in gaps)
            if sum(counts.values()):
                matrix.append(
                    (
                        source,
                        name,
                        *(
                            f"{counts.get(s, 0)} of {total.get(s, 0)}"
                            for s in ("train", "val", "test")
                        ),
                    )
                )
    body += (
        "**Every core channel at every training site: turbine-years missing it, by split** "
        "(channels missing in no turbine-year are left out)\n\n"
        + table(["site", "channel", "train", "val", "late test"], matrix)
    )
    for source, channels in WATCHED.items():
        gaps = rows.get(source, [])
        if not gaps:
            continue
        affected = [row for row in gaps if row.affected(channels)]
        rest = [row for row in gaps if not row.affected(channels)]
        body += f"\n### {source}: {', '.join(f'`{c}`' for c in channels)}\n\n"
        body += table(
            ["turbine", "year", "split", *(f"{c} missing" for c in channels), "narrow events"],
            [
                (
                    row.turbine,
                    str(row.year),
                    row.split,
                    *(_pct(row.missing[c]) for c in channels),
                    row.narrow,
                )
                for row in affected
            ],
        )
        by_split = []
        for split in ("train", "val", "test"):
            a = [row for row in affected if row.split == split]
            r = [row for row in rest if row.split == split]
            by_split.append((split, len(a), len(a) + len(r)))
        body += "\n" + table(["split", "turbine-years affected", "turbine-years"], by_split)

        def rate(group: Sequence[GapRow]) -> tuple[int, float]:
            return sum(g.narrow for g in group), sum(g.steps for g in group) / STEPS_PER_YEAR

        comparisons = []
        for scope, a_rows, r_rows in (
            ("all splits", affected, rest),
            (
                "train only",
                [g for g in affected if g.split == "train"],
                [g for g in rest if g.split == "train"],
            ),
        ):
            a_n, a_ty = rate(a_rows)
            r_n, r_ty = rate(r_rows)
            ratio, low, high = rate_ratio_interval(a_n, a_ty, r_n, r_ty)
            comparisons.append(
                (
                    scope,
                    f"{a_n:,} / {a_ty:.1f} ty = {a_n / a_ty:.1f}" if a_ty else "-",
                    f"{r_n:,} / {r_ty:.1f} ty = {r_n / r_ty:.1f}" if r_ty else "-",
                    f"{ratio:.2f} ({low:.2f}-{high:.2f})" if ratio == ratio else "n/a",
                )
            )
        body += (
            "\n**Narrow events per turbine-year, affected against unaffected turbine-years** "
            "(rate ratio with a 95% log-normal interval)\n\n"
            + table(["scope", "affected", "unaffected", "rate ratio"], comparisons)
        )
        steps_rows = []
        for scope, group in (
            ("all splits", gaps),
            ("train only", [g for g in gaps if g.split == "train"]),
        ):
            km, pm = sum(g.known_missing for g in group), sum(g.positive_missing for g in group)
            kp, pp = sum(g.known_present for g in group), sum(g.positive_present for g in group)
            cells: list[Any] = [scope]
            for known, positive in ((km, pm), (kp, pp)):
                if known:
                    low, high = wilson_interval(positive, known)
                    cells.append(
                        f"{positive / known * 100:.2f}% "
                        f"({low * 100:.2f}-{high * 100:.2f}%) of {known:,}"
                    )
                else:
                    cells.append("-")
            steps_rows.append(tuple(cells))
        body += (
            f"\n**`{label}` base rate on reporting steps, a watched channel missing against "
            "all present** (Wilson 95% interval)\n\n"
            + table(["scope", "channel missing", "channels present"], steps_rows)
        )
    return section("(c) Channel gaps: in which split, and at what event rate", body)


def _care_section(probe: CareProbe, core: Sequence[str]) -> str:
    """Section (d)."""
    farms = list(probe.datasets)
    counts = table(
        ["farm", "anomalous datasets", "normal datasets", "grid steps", "turbine-years"],
        [
            (
                farm,
                probe.datasets[farm].get("anomaly", 0),
                probe.datasets[farm].get("normal", 0),
                probe.steps.get(farm, 0),
                f"{probe.steps.get(farm, 0) / STEPS_PER_YEAR:.2f}",
            )
            for farm in farms
        ]
        + [
            (
                "all",
                probe.total("anomaly"),
                probe.total("normal"),
                sum(probe.steps.values()),
                f"{sum(probe.steps.values()) / STEPS_PER_YEAR:.2f}",
            )
        ],
    )
    without_a = [farm for farm in farms if farm != "farm_a"]
    groups: list[tuple[str, int]] = [
        ("anomalous, all farms", probe.total("anomaly")),
        ("normal, all farms", probe.total("normal")),
        ("anomalous, without farm A (ADR-0004)", probe.total("anomaly", without_a)),
        ("normal, without farm A", probe.total("normal", without_a)),
        *((f"anomalous, {farm}", probe.datasets[farm].get("anomaly", 0)) for farm in farms),
    ]
    intervals = []
    for name, n in groups:
        cells: list[Any] = [name, n]
        for rate in CARE_RATES:
            if n:
                low, high = wilson_interval(round(rate * n), n)
                cells.append(f"{low * 100:.0f}-{high * 100:.0f}% (+/- {(high - low) * 50:.0f} pp)")
            else:
                cells.append("-")
        intervals.append(tuple(cells))
    presence = table(
        ["farm", *core],
        [(farm, *(_pct(probe.presence[farm][c], 0) for c in core)) for farm in probe.presence],
    )
    body = (
        "CARE is a benchmark of datasets, not of steps: each dataset is one turbine's "
        "history built around one provider label, `anomaly` or `normal`, and the provider "
        "scores a detector per dataset with its own CARE score. A per-step base rate over "
        "CARE counts steps of 95 hand-picked datasets and does not compare with the three "
        "sites whose steps are a whole record. It is read here as a secondary, dataset-level "
        "generalisation probe, with the interval its counts allow.\n\n"
        + counts
        + "\n**The interval a dataset-level rate can carry** (Wilson 95%, at the rate "
        "shown)\n\n"
        + table(["datasets", "n", *(f"at a rate of {r:.0%}" for r in CARE_RATES)], intervals)
        + "\n**Why its steps do not compare**\n\n"
        + kv_table(
            {
                "power": "normalised to a rated power the record does not publish"
                + (
                    f" (configured bound {probe.power_bound[0]:g} to "
                    f"{probe.power_bound[1]:g}, per unit)"
                    if probe.power_bound
                    else ""
                ),
                "timestamps": "anonymised by the provider; spacing real, dates not"
                if not probe.absolute_time
                else "declared absolute",
                "missingness": "core channels present per farm below; three farms map "
                "different subsets of the canonical list",
            }
        )
        + "\n**Core channels present on the clean grid, per farm**\n\n"
        + presence
    )
    return section("(d) CARE: a dataset-level probe", body)


def render_verification(
    header: str,
    stop: Sequence[StopClassEvidence],
    years: Sequence[SiteYears],
    gaps: Mapping[str, list[GapRow]],
    care: CareProbe | None,
    core: Sequence[str],
    splits: SplitsConfig,
    label: str,
) -> str:
    """Render the verification report.

    Args:
        header: The report header.
        stop: Section (a), one entry per site with stop classes.
        years: Section (b), one entry per site.
        gaps: Section (c), turbine-year rows per training site.
        care: Section (d), when a dataset-level source is configured.
        core: Core channels.
        splits: The split specification.
        label: The label column section (c) compares.

    Returns:
        A Markdown document.
    """
    parts = [header]
    parts.extend(_stop_class_section(evidence) for evidence in stop)
    parts.append(_years_section(years, splits))
    parts.append(_gaps_section(gaps, core, label))
    if care is not None:
        parts.append(_care_section(care, core))
    return "".join(parts)


def inspect_verification(
    paths: ProjectPaths, config: TelemetryPipelineConfig, config_path: Path
) -> Path:
    """Run the four checks and write the verification report.

    Args:
        paths: Resolved project paths.
        config: The configuration the labels and tables were produced under.
        config_path: Where it was read from.

    Returns:
        The report path.

    Raises:
        ValueError: If the labelling file has no harmonised rule.
    """
    if not config.events.labels_config:
        raise ValueError("events.labels_config names no labelling file to verify")
    rules = load_config(paths.repo_root / config.events.labels_config, EventLabelsConfig)
    if rules.harmonised is None:
        raise ValueError(f"{config.events.labels_config} has no harmonised rule to verify")
    splits = load_config(paths.repo_root / config.final.splits_config, SplitsConfig)
    sources = list(ADAPTERS)
    training = [
        s for s in sources if s not in splits.holdout_sites and s not in splits.eval_only_sources
    ]
    held_out = [s for s in sources if s in splits.holdout_sites]
    core = list(config.core_channels) or list(config.channels)
    label = label_column("narrow", max(config.events.horizons_steps))

    stop = [
        stop_class_evidence(paths, config, rules.harmonised, source)
        for source in held_out
        if source in rules.downtime.sources
    ]
    years = [site_years(paths, source, splits, rules) for source in [*training, *held_out]]
    watched = {source: list(WATCHED.get(source, ())) for source in training}
    gaps = {
        source: channel_gaps(paths, source, core, watched[source], splits, label)
        for source in training
    }
    care_sources = [s for s in rules.event_info.sources if s in sources]
    care = care_probe(paths, config, care_sources[0], core) if care_sources else None

    header = "# Verification of the harmonised labels (M1b step 9)\n\n" + kv_table(
        {
            "config": config_path.as_posix(),
            "labels": config.events.labels_config,
            "splits": config.final.splits_config,
            "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "git_sha": git_sha(paths.repo_root),
            "generated by": "faultline inspect verification",
        }
    )
    report = render_verification(header, stop, years, gaps, care, core, splits, label)
    destination = paths.data_reports_dir / f"verification_{datetime.now(tz=UTC):%Y%m%d}.md"
    destination.write_text(report, encoding="utf-8")
    logger.info("wrote %s", destination)
    return destination
