"""One event rule for every site: seconds down per step by cause, then runs (ADR-0009).

The three training and held-out sources publish three different kinds of stop evidence
-- Senvion status rows with a start and an end, a Siemens downtime series with a
per-step split into stop classes, and CARE's one labelled event per dataset. Counting
events in each source's native unit is what made the held-out site look ten times
busier than the training sites: a Senvion fault episode is several status rows, and a
Siemens downtime run is one event whatever caused it.

So every source is first reduced to the same table, :data:`STOP_STEP_COLUMNS`: for each
turbine and 10-minute step, the seconds of downtime in the step and how many of them
each cause accounts for. The causes are an IEC 61400-26-style vocabulary,
:data:`CAUSES`. Mapping a provider's vocabulary onto it is per source and lives in
``configs/data/events_v2.yaml`` beside the evidence for each entry; that is a
translation, not a rule.

The rule is :func:`select_events`, and there is one of it. It takes the per-step table,
a set of causes and a minimum duration, and returns the runs of consecutive steps
holding downtime of those causes. It has no source argument and reads no provider
column, so it cannot treat one site differently from another: the narrow label is
``select_events(steps, ["technical"], d)`` at every site, and the broad label is
``select_events(steps, CAUSES, d)``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

import numpy as np
import pandas as pd

Cause = Literal["technical", "environmental", "grid", "planned", "unknown"]

#: The cause vocabulary, in report order. ``technical`` is a stop the turbine made
#: because a component failed or tripped a protection; ``planned`` covers commanded,
#: manual and scheduled stops (service, lubrication, cable unwinding); ``unknown`` is
#: downtime no published evidence attributes.
CAUSES: tuple[Cause, ...] = get_args(Cause)

STEP = pd.Timedelta(minutes=10)
STEP_SECONDS = 600
KEYS = ["turbine_id", "timestamp_utc"]
_EPOCH = pd.Timestamp("1970-01-01", tz="UTC")
_SECOND = pd.Timedelta(seconds=1)


def seconds_column(cause: str) -> str:
    """The per-step column holding one cause's seconds."""
    return f"{cause}_s"


#: The per-step stop table every source is reduced to.
STOP_STEP_COLUMNS: tuple[str, ...] = (*KEYS, "total_s", *(seconds_column(c) for c in CAUSES))

#: Columns of the event tables :func:`select_events` returns.
EVENT_TABLE_COLUMNS: tuple[str, ...] = (
    "turbine_id",
    "start_utc",
    "end_utc",
    "steps",
    "duration_s",
    "dominant_cause",
    "first_cause",
)


def empty_stop_steps() -> pd.DataFrame:
    """An empty per-step stop table with the canonical columns."""
    frame = pd.DataFrame({name: pd.Series(dtype="float64") for name in STOP_STEP_COLUMNS})
    frame["turbine_id"] = frame["turbine_id"].astype("object")
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    return frame


def to_seconds(stamps: pd.Series[Any]) -> np.ndarray:
    """UTC timestamps as integer seconds since the epoch, whatever their resolution."""
    return ((pd.to_datetime(stamps, utc=True) - _EPOCH) // _SECOND).to_numpy(dtype=np.int64)


def _from_seconds(seconds: np.ndarray) -> pd.DatetimeIndex:
    """Integer seconds since the epoch back to UTC timestamps."""
    return pd.DatetimeIndex(_EPOCH + pd.to_timedelta(seconds, unit="s"))


def _merge_intervals(turbine: np.ndarray, start: np.ndarray, end: np.ndarray) -> pd.DataFrame:
    """Union of overlapping ``[start, end)`` intervals per turbine, in integer seconds."""
    if len(start) == 0:
        return pd.DataFrame({"turbine_id": [], "s": [], "e": []})
    frame = pd.DataFrame({"turbine_id": turbine, "s": start, "e": end}).sort_values(
        ["turbine_id", "s"], kind="stable"
    )
    reach = frame.groupby("turbine_id", sort=False)["e"].cummax()
    previous = reach.groupby(frame["turbine_id"], sort=False).shift()
    new = previous.isna() | (frame["s"] > previous)
    group = new.cumsum().to_numpy()
    merged = frame.groupby(group, sort=False).agg(
        turbine_id=("turbine_id", "first"), s=("s", "min"), e=("e", "max")
    )
    return merged.reset_index(drop=True)


def _allocate(intervals: pd.DataFrame) -> pd.DataFrame:
    """Seconds of each interval falling in each 10-minute step it overlaps."""
    if intervals.empty:
        return pd.DataFrame({"turbine_id": [], "step": [], "sec": []})
    start = intervals["s"].to_numpy(dtype=np.int64)
    end = intervals["e"].to_numpy(dtype=np.int64)
    first = start - start % STEP_SECONDS
    count = (end - first + STEP_SECONDS - 1) // STEP_SECONDS
    index = np.repeat(np.arange(len(start)), count)
    offset = np.arange(int(count.sum())) - np.repeat(np.cumsum(count) - count, count)
    step = first[index] + offset * STEP_SECONDS
    seconds = np.minimum(step + STEP_SECONDS, end[index]) - np.maximum(step, start[index])
    frame = pd.DataFrame(
        {"turbine_id": intervals["turbine_id"].to_numpy()[index], "step": step, "sec": seconds}
    )
    return frame.groupby(["turbine_id", "step"], as_index=False).agg(sec=("sec", "sum"))


def status_stop_steps(
    stops: pd.DataFrame, causes: Sequence[str] | pd.Series[Any]
) -> tuple[pd.DataFrame, int]:
    """Reduce stop rows with a start and an end to seconds down per step, by cause.

    Overlapping rows of one cause are merged before they are counted, so two
    simultaneous status messages about one stop count its seconds once; the total is
    the union over every cause. A row without an end, or ending before it starts, has
    no duration to allocate and is left out and counted.

    Args:
        stops: Rows with ``turbine_id``, ``start_utc`` and ``end_utc``.
        causes: The cause of each row, aligned with ``stops``.

    Returns:
        The per-step stop table, and the number of rows without a usable interval.
    """
    if stops.empty:
        return empty_stop_steps(), 0
    cause = np.asarray(causes, dtype=object)
    unknown = sorted({str(c) for c in cause} - set(CAUSES))
    if unknown:
        raise ValueError(f"causes outside the vocabulary {CAUSES}: {unknown}")
    start_ok = stops["start_utc"].notna().to_numpy()
    end_ok = stops["end_utc"].notna().to_numpy()
    start = np.where(start_ok, to_seconds(stops["start_utc"].fillna(_EPOCH)), 0)
    end = np.where(end_ok, to_seconds(stops["end_utc"].fillna(_EPOCH)), 0)
    usable = start_ok & end_ok & (end > start)
    turbine = stops["turbine_id"].astype(str).to_numpy()

    parts = []
    for name in CAUSES:
        pick = usable & (cause == name)
        allocated = _allocate(_merge_intervals(turbine[pick], start[pick], end[pick]))
        parts.append(allocated.rename(columns={"sec": seconds_column(name)}))
    total = _allocate(_merge_intervals(turbine[usable], start[usable], end[usable]))
    frame = total.rename(columns={"sec": "total_s"})
    for part in parts:
        frame = frame.merge(part, on=["turbine_id", "step"], how="left")
    frame = frame.fillna(0.0)
    frame.insert(1, "timestamp_utc", _from_seconds(frame.pop("step").to_numpy(dtype=np.int64)))
    frame = frame.sort_values(KEYS).reset_index(drop=True)
    return frame[list(STOP_STEP_COLUMNS)].astype(
        {name: "float64" for name in STOP_STEP_COLUMNS[2:]}
    ), int((~usable).sum())


@dataclass
class OverrideCount:
    """What one described code's override moved.

    Attributes:
        code: The alarm code.
        cause: The cause its description gives it.
        steps: Steps in which its alarm was active and technical seconds were moved.
        seconds: Technical seconds moved to ``cause``.
    """

    code: str
    cause: str
    steps: int = 0
    seconds: float = 0.0


@dataclass
class DowntimeAttribution:
    """How a downtime series was split into causes.

    Attributes:
        down_steps: Steps with downtime above zero.
        unclassified_down_steps: Down steps with no stop-class row published.
        unattributed_down_steps: Down steps the published stop classes do not cover.
        overrides: What each described code's override moved.
    """

    down_steps: int = 0
    unclassified_down_steps: int = 0
    unattributed_down_steps: int = 0
    overrides: list[OverrideCount] = field(default_factory=list)


def downtime_stop_steps(
    downtime: pd.DataFrame,
    classes: pd.DataFrame,
    class_causes: Mapping[str, str],
    override_steps: pd.DataFrame,
    count_steps: Mapping[str, np.ndarray] | None = None,
) -> tuple[pd.DataFrame, DowntimeAttribution]:
    """Split a per-step downtime series into causes using the provider's stop classes.

    The total is the downtime series itself. Each published stop-class timer counts
    toward its mapped cause, clipped to the step's downtime; downtime no timer covers is
    ``unknown``. In a step where an alarm with a described non-technical cause is
    active, the step's technical seconds move to that cause: Hill of Towie files pitch
    lubrication under turbine error, and it is excluded here by what it is, not by how
    long it lasts.

    Args:
        downtime: ``turbine_id``, ``timestamp_utc``, ``downtime_s``.
        classes: ``turbine_id``, ``timestamp_utc`` and one seconds column per timer.
        class_causes: Timer column to cause.
        override_steps: ``turbine_id``, ``timestamp_utc``, ``code``, ``cause``: steps in
            which a described code's alarm is active. The first row per step wins.
        count_steps: Restrict the attribution counts to these steps per turbine (integer
            seconds), normally the labelled grid; the series runs past it.

    Returns:
        The per-step stop table (down steps only) and the attribution counts.
    """
    stats = DowntimeAttribution()
    down = downtime[downtime["downtime_s"] > 0][[*KEYS, "downtime_s"]]
    if down.empty:
        return empty_stop_steps(), stats
    timers = [name for name in class_causes if name in classes.columns]
    joined = down.merge(classes[[*KEYS, *timers]], on=KEYS, how="left", indicator=True)
    classified = (joined.pop("_merge") == "both").to_numpy()
    counted = (
        _member_of(joined, count_steps)
        if count_steps is not None
        else np.ones(len(joined), dtype=bool)
    )
    stats.down_steps = int(counted.sum())
    stats.unclassified_down_steps = int((~classified & counted).sum())
    total = joined["downtime_s"].clip(lower=0, upper=STEP_SECONDS)
    frame = pd.DataFrame(
        {"turbine_id": joined["turbine_id"].astype(str), "timestamp_utc": joined["timestamp_utc"]}
    )
    frame["total_s"] = total.to_numpy(dtype="float64")
    for name in CAUSES:
        frame[seconds_column(name)] = 0.0
    for timer in timers:
        seconds = joined[timer].fillna(0).clip(lower=0).clip(upper=total)
        column = seconds_column(class_causes[timer])
        frame[column] = np.minimum(frame[column].to_numpy() + seconds.to_numpy(), frame["total_s"])

    if not override_steps.empty:
        first = override_steps.drop_duplicates(subset=KEYS, keep="first")
        hit = frame[KEYS].merge(first, on=KEYS, how="left")
        technical = seconds_column("technical")
        for (code, cause), rows in hit.dropna(subset=["cause"]).groupby(["code", "cause"]):
            moved = frame.loc[rows.index, technical]
            moving = moved > 0
            tally = moving & counted[rows.index]
            target = seconds_column(str(cause))
            frame.loc[rows.index[moving], target] = np.minimum(
                frame.loc[rows.index[moving], target] + moved[moving],
                frame.loc[rows.index[moving], "total_s"],
            )
            frame.loc[rows.index[moving], technical] = 0.0
            stats.overrides.append(
                OverrideCount(str(code), str(cause), int(tally.sum()), float(moved[tally].sum()))
            )

    known = frame[[seconds_column(c) for c in CAUSES if c != "unknown"]].sum(axis=1)
    frame[seconds_column("unknown")] = (frame["total_s"] - known).clip(lower=0)
    stats.unattributed_down_steps = int(((known <= 0).to_numpy() & counted).sum())
    frame = frame.sort_values(KEYS).reset_index(drop=True)
    return frame[list(STOP_STEP_COLUMNS)], stats


def _member_of(frame: pd.DataFrame, steps: Mapping[str, np.ndarray]) -> np.ndarray:
    """Whether each (turbine, step) of a table is among the given steps per turbine."""
    mask = np.zeros(len(frame), dtype=bool)
    if frame.empty:
        return mask
    seconds = to_seconds(frame["timestamp_utc"])
    turbines = frame["turbine_id"].astype(str).to_numpy()
    for turbine, index in pd.Series(turbines).groupby(turbines).indices.items():
        known = steps.get(str(turbine))
        if known is None or len(known) == 0:
            continue
        wanted = seconds[index]
        position = np.minimum(np.searchsorted(known, wanted), len(known) - 1)
        mask[index] = known[position] == wanted
    return mask


def alarm_override_steps(alarms: pd.DataFrame, code_causes: Mapping[str, str]) -> pd.DataFrame:
    """The steps in which each described code's alarm is active.

    An alarm is active from the step its ``start_utc`` falls in through the step its
    ``end_utc`` falls in (its start step alone when the log has no end). Codes are
    returned in the order ``code_causes`` lists them, which is the order in which a step
    claimed by two of them is resolved.

    Args:
        alarms: ``turbine_id``, ``code``, ``start_utc``, ``end_utc``.
        code_causes: Described code to cause.

    Returns:
        ``turbine_id``, ``timestamp_utc``, ``code``, ``cause``.
    """
    columns = [*KEYS, "code", "cause"]
    parts = []
    for code, cause in code_causes.items():
        rows = alarms[alarms["code"].astype(str) == str(code)]
        if rows.empty:
            continue
        start = to_seconds(rows["start_utc"])
        end = np.where(
            rows["end_utc"].notna().to_numpy(),
            to_seconds(rows["end_utc"].fillna(rows["start_utc"])),
            start,
        )
        end = np.maximum(end, start)
        first = start - start % STEP_SECONDS
        count = (end - first) // STEP_SECONDS + 1
        index = np.repeat(np.arange(len(start)), count)
        offset = np.arange(int(count.sum())) - np.repeat(np.cumsum(count) - count, count)
        parts.append(
            pd.DataFrame(
                {
                    "turbine_id": rows["turbine_id"].astype(str).to_numpy()[index],
                    "timestamp_utc": _from_seconds(first[index] + offset * STEP_SECONDS),
                    "code": str(code),
                    "cause": str(cause),
                }
            ).drop_duplicates(subset=KEYS)
        )
    if not parts:
        return pd.DataFrame(columns=columns)
    return pd.concat(parts, ignore_index=True)[columns]


def select_events(
    steps: pd.DataFrame, causes: Sequence[str], min_duration_s: float
) -> pd.DataFrame:
    """The event rule: runs of steps holding downtime of the given causes.

    A step counts when the seconds of the chosen causes in it are above zero. A run is
    a sequence of consecutive counting steps of one turbine; a step without downtime of
    those causes, or a missing step, ends it. An event is a run whose seconds of the
    chosen causes add up to at least ``min_duration_s``; it starts at the run's first
    step.

    There is no source argument, on purpose: this is the one rule, applied identically
    at every site.

    Args:
        steps: The per-step stop table (:data:`STOP_STEP_COLUMNS`).
        causes: Causes whose downtime counts.
        min_duration_s: Shortest event kept, in seconds of downtime of those causes.

    Returns:
        One row per event (:data:`EVENT_TABLE_COLUMNS`). ``dominant_cause`` has the most
        seconds over the run among ``causes``; ``first_cause`` the most in its first step.
    """
    unknown = sorted(set(causes) - set(CAUSES))
    if unknown:
        raise ValueError(f"causes outside the vocabulary {CAUSES}: {unknown}")
    chosen = [seconds_column(c) for c in causes]
    if steps.empty or not chosen:
        return pd.DataFrame(columns=list(EVENT_TABLE_COLUMNS))
    frame = steps[[*KEYS, "total_s", *chosen]].copy()
    frame["_sec"] = frame[chosen].sum(axis=1).clip(upper=frame["total_s"])
    frame = frame[frame["_sec"] > 0].sort_values(KEYS, kind="stable").reset_index(drop=True)
    if frame.empty:
        return pd.DataFrame(columns=list(EVENT_TABLE_COLUMNS))
    turbine = frame["turbine_id"].astype(str).to_numpy()
    stamp = to_seconds(frame["timestamp_utc"])
    new = np.r_[True, (turbine[1:] != turbine[:-1]) | (np.diff(stamp) != STEP_SECONDS)]
    run = np.cumsum(new)
    grouped = frame.groupby(run, sort=True)
    sums = grouped[chosen].sum()
    firsts = grouped[chosen].first()
    events = pd.DataFrame(
        {
            "turbine_id": grouped["turbine_id"].first().astype(str),
            "start_utc": grouped["timestamp_utc"].min(),
            "end_utc": grouped["timestamp_utc"].max() + STEP,
            "steps": grouped.size().astype(int),
            "duration_s": grouped["_sec"].sum().astype(float),
            "dominant_cause": _cause_names(sums),
            "first_cause": _cause_names(firsts),
        }
    )
    events = events[events["duration_s"] >= min_duration_s]
    return events[list(EVENT_TABLE_COLUMNS)].reset_index(drop=True)


def _cause_names(seconds: pd.DataFrame) -> pd.Series[Any]:
    """The cause holding the most seconds in each row, by name."""
    columns = seconds.idxmax(axis=1)
    return pd.Series([str(c).removesuffix("_s") for c in columns], index=seconds.index)


def wind_state(
    events: pd.DataFrame, wind: pd.DataFrame, cut_in_ms: float, cut_out_ms: float
) -> pd.Series[Any]:
    """Classify each event by the wind speed in the step it starts in.

    Args:
        events: Events with ``turbine_id`` and ``start_utc``.
        wind: ``turbine_id``, ``timestamp_utc``, ``wind_speed_ms``.
        cut_in_ms: Below this the turbine would not be producing anyway.
        cut_out_ms: Above this it would be stopped for wind anyway.

    Returns:
        ``below_cut_in``, ``above_cut_out``, ``inside`` or ``unknown`` per event.
    """
    if events.empty:
        return pd.Series([], dtype="object")
    keyed = pd.DataFrame(
        {
            "turbine_id": events["turbine_id"].astype(str).to_numpy(),
            "timestamp_utc": pd.to_datetime(events["start_utc"], utc=True).dt.floor("10min"),
        }
    )
    lookup = wind[[*KEYS, "wind_speed_ms"]].drop_duplicates(subset=KEYS)
    lookup = lookup.assign(turbine_id=lookup["turbine_id"].astype(str))
    speed = keyed.merge(lookup, on=KEYS, how="left")["wind_speed_ms"].to_numpy()
    state = np.where(
        np.isnan(speed),
        "unknown",
        np.where(
            speed < cut_in_ms,
            "below_cut_in",
            np.where(speed > cut_out_ms, "above_cut_out", "inside"),
        ),
    )
    return pd.Series(state, index=events.index, dtype="object")


def horizon_labels(
    stamps: pd.Series[Any],
    starts: pd.Series[Any],
    horizon_steps: int,
    covered: np.ndarray,
) -> pd.Series[Any]:
    """Label each step: does an event start in ``(t, t + H]``, where that is knowable?

    A step is ``True`` when an event starts in its horizon. It is ``False`` only when
    every step of the horizon lies inside the record the events were read from; where
    the horizon runs past that record and no event was seen, the answer is unknown and
    the label is ``NA``, never ``False`` (ADR-0006).

    Args:
        stamps: The steps to label, UTC.
        starts: Event start times of the same turbine, UTC.
        horizon_steps: The horizon, in steps.
        covered: Sorted integer seconds of every step the event record covers.

    Returns:
        A nullable boolean Series aligned with ``stamps``.
    """
    t = to_seconds(pd.Series(stamps))
    horizon = horizon_steps * STEP_SECONDS
    event_seconds = (
        np.sort(to_seconds(pd.Series(starts))) if len(starts) else np.array([], dtype=np.int64)
    )
    position = np.searchsorted(event_seconds, t, side="right")
    hit = np.zeros(len(t), dtype=bool)
    valid = position < len(event_seconds)
    hit[valid] = event_seconds[position[valid]] <= t[valid] + horizon
    inside = np.searchsorted(covered, t + horizon, side="right") - np.searchsorted(
        covered, t, side="right"
    )
    known = hit | (inside >= horizon_steps)
    result = pd.array(hit, dtype="boolean")
    result[~known] = pd.NA
    return pd.Series(result, index=pd.Series(stamps).index)
