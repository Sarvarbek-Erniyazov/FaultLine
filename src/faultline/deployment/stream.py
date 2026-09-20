"""One turbine-year scored step by step on CPU: the deployment path, end to end.

**This is a demonstration, not an evaluation.** It registers no rule, decides nothing and
adds no number to the record. It runs the path a deployment would run -- backbone, frozen
probe, prior-corrected probability, one window after another in time order -- over real
forward-in-time data, so that a reader can see what a signal of this strength looks like
against a year of a single turbine instead of as a pooled scalar.

**Nothing here re-derives a rule.** The probe is loaded whole by
:func:`faultline.evaluation.paired_control.load_saved_probe`, the correction is
:func:`faultline.evaluation.calibration.at_natural_rate` (ADR-0019's two-term rule) called
with the registered training prior and the balanced-mean offset the record measured for
this probe, and the interval is
:func:`faultline.evaluation.bootstrap.bootstrap_auprc` under ADR-0021's registered block
bootstrap. A local copy of any of those would be a second implementation of a rule that
already has one.

**Which turbine-year, and why that one.** A demonstration chooses its example, and
choosing it badly is how a demonstration quietly becomes a claim. Two rules are in
force, both declared in :mod:`faultline.deployment.selection` before any score was
looked at -- the most events, and the positive-window rate closest to the pooled test
base rate -- and both traces are reported side by side wherever either appears. Neither
is an evaluation result, and two examples are not a sample.

**What the trace deliberately does not draw.** No threshold, no alarm mark, no abstention
band. Choosing an operating point is a decision this project has not earned the right to
make, and drawing one would read as a claim. The figure shows the corrected probability
and the labelled events, and stops there.

**The step axis.** The window index names a window by its first and last step in the
shard's step stream, and carries no timestamp. The stream is the final tables concatenated
one turbine-year at a time, in the shard builder's own order, so :func:`step_stamps`
rebuilds that axis from the same files in the same order and reads the timestamp off it.
The grid has gaps -- a turbine-year holds fewer steps than a full year -- so a step is
never converted to a time by arithmetic.
"""

from __future__ import annotations

import calendar
import csv
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import torch

from faultline.config import load_config
from faultline.data.common.report import kv_table, section, table
from faultline.data.telemetry.bins import QuantileBinsConfig
from faultline.data.telemetry.pipeline import parquet_files, stage_source_dir
from faultline.data.telemetry.shards import shards_dir, tokenizer_path
from faultline.deployment.selection import (
    MOST_EVENTS,
    RULE_CRITERIA,
    RULE_NAMES,
    RULES,
    TIE_BREAK,
    TRACE_RECORD,
    read_traces,
    rules_block,
    write_trace,
)
from faultline.evaluation.bootstrap import AuprcInterval, bootstrap_auprc, window_blocks
from faultline.evaluation.calibration import at_natural_rate
from faultline.evaluation.paired_control import load_saved_probe
from faultline.evaluation.variance_probe import open_probe_inputs
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.config import LadderConfig, PositiveAwareRiskStage
from faultline.training.loop import risk_logits
from faultline.training.mixture import JointMixtureConfig
from faultline.training.windows import ShardSet, WindowSampler, WindowSet, load_windows

logger = get_logger(__name__)

#: The horizon the in-force label asks about: an event starting in ``(t, t + 24h]``.
HORIZON_HOURS = 24

#: ADR-0021's registered block bootstrap, read here as it was registered there.
BLOCK_STEPS, REPLICATES, BOOTSTRAP_SEED = 288, 10_000, 20260916
CONFIDENCE, MAX_DISCARDED_SHARE = 0.95, 0.01

#: The record the pooled test base rate and this probe's F2 offset are read from.
SEED_RECORD = "reports/data/seed_replication_v0_20260917.json"

#: Where that record keeps the ``tel_only`` seed whose probe this trace runs.
SEED = 2

#: The probe design in force, ADR-0022's §a (:data:`faultline.evaluation.readout` names it).
DESIGN = "final_position"

#: ``open_probe_inputs`` opens the splits a probe *run* needs; this trace scores none of
#: them, so the language-model selection set is asked for at its smallest and the cost is
#: a few index reads rather than a pass.
LM_SELECTION_WINDOWS = 1

#: Categorical slots of the validated reference palette, on its light surface. ``RATE``
#: is the turbine-year's own positive-rate line, which has to be told apart from both
#: the trace and the event marks; every one of them also carries a word.
TRACE, EVENT, RATE = "#2a78d6", "#c2475f", "#8a5cd0"
INK, MUTED, GRID, SURFACE, BAND = "#1a1a19", "#5f5e58", "#e4e3dd", "#fcfcfb", "#f6dfe4"


@dataclass(frozen=True)
class TurbineYear:
    """One turbine's year as the selection rules see it: labels only, never a score.

    Attributes:
        turbine: The turbine.
        events: Its labelled narrow event starts in the year.
        windows: Its known windows in the year, at the stride the trace scores.
        positives: How many of those the in-force label calls positive.
    """

    turbine: str
    events: int
    windows: int
    positives: int

    @property
    def rate(self) -> float:
        """Its positive-window rate, which is what the typical-rate rule reads."""
        return self.positives / self.windows if self.windows else float("nan")


@dataclass(frozen=True)
class TurbineChoice:
    """Which turbine of a site-year the trace runs on, under which rule, and why.

    Attributes:
        rule: The rule applied, one of :data:`faultline.deployment.selection.RULES`.
        target: The pooled test base rate, which the typical-rate rule aims at.
        turbine: The chosen turbine.
        runner_up: The next turbine down under the same rule, so the margin is visible.
        candidates: Every turbine of the site-year that has a window, in turbine order.
        tied: Whether the choice was a tie on the criterion, broken by lowest turbine id.
    """

    rule: str
    target: float
    turbine: str
    runner_up: str
    candidates: dict[str, TurbineYear]
    tied: bool

    @property
    def chosen(self) -> TurbineYear:
        """The chosen turbine's year."""
        return self.candidates[self.turbine]

    @property
    def events(self) -> int:
        """The chosen turbine's labelled narrow event starts in the year."""
        return self.chosen.events

    @property
    def runner_up_events(self) -> int:
        """The runner-up's count, or ``0`` when the site-year offers no runner-up."""
        year = self.candidates.get(self.runner_up)
        return year.events if year is not None else 0

    @property
    def criterion(self) -> str:
        """The rule exactly as it was declared, with its tie-break."""
        return f"{RULE_CRITERIA[self.rule]}, {TIE_BREAK}"

    def picks(self, rule: str) -> str:
        """Which turbine another rule would choose from the same candidates.

        Args:
            rule: The rule to apply.

        Returns:
            The turbine it chooses.
        """
        return choose_turbine(self.candidates, rule, self.target).turbine


@dataclass(frozen=True)
class StreamTrace:
    """One turbine-year scored in time order, and what the run measured.

    Attributes:
        source: The site.
        year: The calendar year.
        choice: The turbine, the rule that chose it and the field it was chosen from.
        stamps: Per window, the UTC timestamp of its last step.
        ends: Per window, that step's index in the shard's step stream.
        probabilities: Per window, the prior-corrected probability.
        labels: Per window, the in-force label.
        hours: Per window, hours to the next event start, ``nan`` beyond the horizon.
        events: Event start timestamps inside the traced span.
        interval: This turbine-year's own AUPRC and its block-bootstrap interval.
        train_rate: The registered training prior the correction reads.
        natural_rate: The training split's natural positive rate, which it corrects to.
        balanced_shift: The F2 balanced-mean offset measured for this probe.
        offset: The constant the correction actually added.
        pooled_base_rate: The pooled test base rate, drawn as a labelled reference line.
        pooled_auprc: The pooled test AUPRC, named only to refuse the comparison.
        pooled_low: Its 95% lower bound.
        pooled_high: Its 95% upper bound.
        pooled_positives: Its positive windows, which is the count the refusal rests on.
        pooled_positive_blocks: Its positive blocks, which is what the bootstrap resamples.
        seconds: CPU wall clock of the scoring pass.
        checkpoint: The backbone the probe carries.
        probe: The probe that was loaded.
    """

    source: str
    year: int
    choice: TurbineChoice
    stamps: np.ndarray
    ends: np.ndarray
    probabilities: np.ndarray
    labels: np.ndarray
    hours: np.ndarray
    events: np.ndarray
    interval: AuprcInterval
    train_rate: float
    natural_rate: float
    balanced_shift: float
    offset: float
    pooled_base_rate: float
    pooled_auprc: float
    pooled_low: float
    pooled_high: float
    pooled_positives: int
    pooled_positive_blocks: int
    seconds: float
    checkpoint: str
    probe: str

    @property
    def windows(self) -> int:
        """Windows scored."""
        return int(self.probabilities.size)

    @property
    def windows_per_second(self) -> float:
        """Scoring throughput on CPU."""
        return self.windows / self.seconds if self.seconds > 0 else float("nan")

    @property
    def positive_rate(self) -> float:
        """This turbine-year's own positive rate, which is not the pooled one."""
        return float(self.labels.mean()) if self.labels.size else float("nan")

    @property
    def mean_probability(self) -> float:
        """The mean corrected probability, which a calibrated head puts at the base rate."""
        return float(self.probabilities.mean()) if self.probabilities.size else float("nan")

    @property
    def positives(self) -> int:
        """Positive windows of this turbine-year.

        This is the count the refusal of the pooled comparison rests on: it is what makes
        this interval wider than the pooled split's, and so what makes the two unreadable
        against each other.
        """
        return int(self.labels.sum())

    @property
    def interval_width(self) -> float:
        """Width of this turbine-year's 95% interval."""
        return self.interval.high - self.interval.low

    @property
    def pooled_interval_width(self) -> float:
        """Width of the pooled test split's 95% interval, for the same coverage."""
        return self.pooled_high - self.pooled_low

    @property
    def widening(self) -> float:
        """How many times wider this interval is than the pooled one, as measured."""
        pooled = self.pooled_interval_width
        return self.interval_width / pooled if pooled > 0 else float("nan")

    @property
    def root_widening(self) -> float:
        """The widening a square-root-of-n rule would suggest from the positive counts.

        It is a guide and not a rule: the registered interval resamples two-day blocks
        rather than windows, so the count that actually drives its width is the positive
        *blocks*. It is reported beside :attr:`widening` so a reader can hold the two
        against each other rather than take either on trust.
        """
        return (
            float(np.sqrt(self.pooled_positives / self.positives))
            if self.positives
            else float("nan")
        )

    @property
    def clears(self) -> bool:
        """Whether the interval's lower bound is strictly above this turbine-year's own rate.

        This is the shape of ADR-0021's registered rule, read here against one turbine-year
        rather than against a scored set. It decides nothing: it is reported so that the
        reader is not left to compare an interval with a base rate by eye.
        """
        return bool(self.interval.low > self.positive_rate)

    @property
    def days_between_events(self) -> float:
        """Days of the calendar year per labelled event start, the density in plain units.

        The event count is a calendar-year count, so the year is what it is divided by.
        """
        days = 366 if calendar.isleap(self.year) else 365
        return days / self.choice.events if self.choice.events else float("nan")

    @property
    def stem(self) -> str:
        """The output stem the three files share.

        A turbine id repeats its site ("Kelmarsh 5"), and the stem already names the site,
        so the prefix is dropped rather than written twice. The rule that chose the turbine
        is not in the stem: two rules that landed on the same turbine-year would produce
        the same trace, and writing it twice under two names would not make it two.
        """
        turbine = self.choice.turbine.lower().replace(" ", "_")
        site = self.source.lower()
        turbine = turbine.removeprefix(f"{site}_")
        return f"stream_trace_{site}_{turbine}_{self.year}"

    def record(self) -> dict[str, Any]:
        """This trace as one entry of the shared trace record.

        Returns:
            The fields the figure index and the other trace's report read.
        """
        return {
            "rule": self.choice.rule,
            "stem": self.stem,
            "source": self.source,
            "year": self.year,
            "turbine": self.choice.turbine,
            "events": self.choice.events,
            "windows": self.windows,
            "positive_rate": self.positive_rate,
            "mean_probability": self.mean_probability,
            "auprc": self.interval.auprc,
            "low": self.interval.low,
            "high": self.interval.high,
            "clears_own_base_rate": self.clears,
            "seconds": self.seconds,
        }


def narrow_event_starts(paths: ProjectPaths, source: str) -> pd.DataFrame:
    """Read a site's narrow events: the starts the in-force label is built from.

    Args:
        paths: Resolved project paths.
        source: The site.

    Returns:
        ``turbine_id`` and a UTC ``start_utc``, one row an event.

    Raises:
        FileNotFoundError: If the site has no narrow event table.
    """
    path = paths.source_dir("cleaned", "telemetry", source) / "labels" / "events_narrow.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found: run `faultline telemetry run`")
    events = pd.read_parquet(path, columns=["turbine_id", "start_utc"])
    return pd.DataFrame(
        {
            "turbine_id": events["turbine_id"].astype(str),
            "start_utc": pd.to_datetime(events["start_utc"], utc=True),
        }
    )


def event_counts(events: pd.DataFrame, year: int) -> dict[str, int]:
    """Per turbine, its labelled narrow event starts in a year, in turbine order.

    The count is unfiltered: the labelling stage reads every start of the turbine, and
    ``in_grid`` is a reporting column there rather than a filter.

    Args:
        events: The site's narrow event starts, from :func:`narrow_event_starts`.
        year: The calendar year.

    Returns:
        Turbine to count, for every turbine that saw a start that year.

    Raises:
        ValueError: If no turbine has an event start in the year.
    """
    inside = events[events["start_utc"].dt.year == year]
    if inside.empty:
        raise ValueError(f"no narrow event starts in {year}")
    counts = {
        str(turbine): int(count) for turbine, count in inside["turbine_id"].value_counts().items()
    }
    return {turbine: counts[turbine] for turbine in sorted(counts)}


def choose_turbine(
    candidates: Mapping[str, TurbineYear], rule: str, target: float
) -> TurbineChoice:
    """Apply one of the two declared selection rules to a site-year.

    Both rules read labels only -- an event count and a positive-window rate -- and neither
    reads a score, so the choice is a function of the data and the rule alone. The rules
    themselves are declared in :mod:`faultline.deployment.selection`, and both are reported
    wherever either trace appears.

    Args:
        candidates: Every turbine of the site-year, from :func:`turbine_years`.
        rule: :data:`~faultline.deployment.selection.MOST_EVENTS` or
            :data:`~faultline.deployment.selection.TYPICAL_RATE`.
        target: The pooled test base rate the typical-rate rule aims at.

    Returns:
        The choice, its runner-up, and the whole field it was chosen from.

    Raises:
        ValueError: If the rule is not one of the two, or there is nothing to choose from.
    """
    if rule not in RULES:
        raise ValueError(f"unknown selection rule {rule!r}; expected one of {RULES}")
    if not candidates:
        raise ValueError("no turbine-year to choose from")

    def criterion(year: TurbineYear) -> float:
        """Lower is better, under whichever rule is in force."""
        return float(-year.events) if rule == MOST_EVENTS else abs(year.rate - target)

    # Sorted by the criterion, then by turbine id, so a tie is broken by the lowest id and
    # the runner-up is the next one down under the same rule.
    order = sorted(candidates.values(), key=lambda year: (criterion(year), year.turbine))
    best = order[0]
    second = order[1] if len(order) > 1 else None
    return TurbineChoice(
        rule=rule,
        target=target,
        turbine=best.turbine,
        runner_up=second.turbine if second is not None else "-",
        candidates={turbine: candidates[turbine] for turbine in sorted(candidates)},
        tied=second is not None and criterion(second) == criterion(best),
    )


@dataclass(frozen=True)
class SelectionField:
    """A site-year as the two rules see it: a window index and a label column, no score.

    The scoring pass and the render-only pass build the field through the same function,
    so a report rendered from the record shows the field the run actually chose from
    rather than a second reconstruction of it.

    Attributes:
        key: The shard key the windows are carried under.
        every: Every known window of that shard, at stride 1.
        turbines: Per window, its turbine id.
        starts: The site's narrow event starts, unfiltered.
        candidates: Per turbine of the year, the two quantities the rules read.
    """

    key: str
    every: WindowSet
    turbines: np.ndarray
    starts: pd.DataFrame
    candidates: dict[str, TurbineYear]

    def choose(self, rule: str, target: float) -> TurbineChoice:
        """Apply one of the two declared rules to the field.

        Args:
            rule: The rule.
            target: The pooled test base rate the typical-rate rule aims at.

        Returns:
            The choice.
        """
        return choose_turbine(self.candidates, rule, target)

    def event_starts(self, turbine: str) -> np.ndarray:
        """One turbine's labelled event start timestamps, sorted.

        Args:
            turbine: The turbine.

        Returns:
            Its start timestamps, in time order.
        """
        mine = self.starts[self.starts["turbine_id"] == turbine]
        return np.sort(mine["start_utc"].to_numpy(dtype="datetime64[ns]"))


def selection_field(
    paths: ProjectPaths, shards: ShardSet, source: str, year: int, label: str, stride: int
) -> SelectionField:
    """Build the field both rules choose from, reading labels and never a score.

    Args:
        paths: Resolved project paths.
        shards: The telemetry shard set.
        source: The site, whose test split holds the year.
        year: The calendar year.
        label: The window-index column the risk head reads as its target.
        stride: The stride a trace of a turbine-year scores at.

    Returns:
        The field.
    """
    key = f"{source}__test"
    starts = narrow_event_starts(paths, source)
    every, turbines = known_windows(shards, key, label)
    candidates = turbine_years(every, turbines, event_counts(starts, year), year, stride)
    return SelectionField(
        key=key, every=every, turbines=turbines, starts=starts, candidates=candidates
    )


def step_stamps(paths: ProjectPaths, source: str, split: str) -> np.ndarray:
    """Rebuild a shard's step axis: per step of the stream, its UTC timestamp.

    The shard builder appends one turbine-year at a time, in ``parquet_files`` order, each
    sorted by timestamp, and a split's rows inside a turbine-year are one contiguous run
    (:mod:`faultline.data.telemetry.shards`). Reading the same files in the same order
    reproduces the axis exactly, which the caller checks against the manifest.

    Args:
        paths: Resolved project paths.
        source: The site.
        split: ``train``, ``val`` or ``test``.

    Returns:
        One UTC timestamp per step of ``<source>__<split>``, in stream order.
    """
    blocks: list[np.ndarray] = []
    for path in parquet_files(stage_source_dir(paths, "final", source)):
        frame = pd.read_parquet(path, columns=["timestamp_utc", "split"])
        frame = frame.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)
        rows = np.flatnonzero(frame["split"].to_numpy(dtype=object) == split)
        if rows.size == 0:
            continue
        if not (np.diff(rows) == 1).all():
            raise ValueError(f"{path}: split {split} is not one run of the turbine-year")
        stamps = pd.to_datetime(frame["timestamp_utc"].to_numpy()[rows], utc=True)
        blocks.append(stamps.to_numpy(dtype="datetime64[ns]"))
    if not blocks:
        raise ValueError(f"{source} has no {split} rows")
    return np.concatenate(blocks)


def known_windows(shards: ShardSet, key: str, label: str) -> tuple[WindowSet, np.ndarray]:
    """A shard's known windows at stride 1, and the turbine each of them belongs to.

    ``load_windows`` keeps the known rows of the index, in index order, and nothing else,
    so the known rows of the same file line up with its arrays one for one.

    Args:
        shards: The shard set.
        key: The shard key, ``<source>__<split>``.
        label: The window-index column read as the target.

    Returns:
        The windows and, per window, its turbine id.

    Raises:
        ValueError: If the index and the window arrays disagree on length.
    """
    every = load_windows(shards, key, stride=1, label=label)
    record = shards.files()[key]
    frame = pq.read_table(
        shards.root / str(record["windows"]), columns=["turbine_id", f"{label}_known"]
    ).to_pandas()
    known = frame[frame[f"{label}_known"].to_numpy()].reset_index(drop=True)
    if len(known) != len(every):
        raise ValueError(f"{key}: {len(known)} known rows against {len(every)} windows")
    return every, known["turbine_id"].astype(str).to_numpy(dtype=object)


def turbine_year_rows(
    every: WindowSet, turbines: np.ndarray, turbine: str, year: int, stride: int
) -> np.ndarray:
    """The rows of one turbine-year in the known window set, strided inside it.

    The turbine-year is masked out of the index in index order and the stride is taken
    afterwards, so the stride counts that turbine's windows and not the site's.

    Args:
        every: Every known window, from :func:`known_windows`.
        turbines: Per window, its turbine id.
        turbine: The turbine.
        year: The calendar year.
        stride: Keep every ``stride``-th known window of the turbine-year.

    Returns:
        Row indices into ``every``, in index order, which is time order inside a
        turbine-year.
    """
    mine = np.flatnonzero((turbines == turbine) & (every.years == year))
    return mine[::stride]


def turbine_years(
    every: WindowSet,
    turbines: np.ndarray,
    counts: Mapping[str, int],
    year: int,
    stride: int,
) -> dict[str, TurbineYear]:
    """Per turbine of a site-year, the two quantities the selection rules read.

    The positive-window rate is taken over exactly the windows a trace of that turbine
    would score, so the rate reported for the chosen turbine is the positive rate its own
    trace reports. Nothing is scored to compute it: the label column is read off the
    window index.

    Args:
        every: Every known window, from :func:`known_windows`.
        turbines: Per window, its turbine id.
        counts: Per turbine, its event starts in the year, from :func:`event_counts`.
        year: The calendar year.
        stride: The stride the trace scores at.

    Returns:
        Turbine to its year, in turbine order. A turbine with an event start but no known
        window that year is left out: a turbine-year with nothing to score is not a
        candidate under either rule.

    Raises:
        ValueError: If no turbine has a known window in the year.
    """
    out: dict[str, TurbineYear] = {}
    for turbine, events in counts.items():
        rows = turbine_year_rows(every, turbines, turbine, year, stride)
        if rows.size == 0:
            logger.info("%s: %d event starts in %d but no known window", turbine, events, year)
            continue
        out[turbine] = TurbineYear(
            turbine=turbine,
            events=events,
            windows=int(rows.size),
            positives=int(every.labels[rows].sum()),
        )
    if not out:
        raise ValueError(f"no turbine has a known window in {year}")
    return out


def turbine_year_windows(
    every: WindowSet, turbines: np.ndarray, key: str, turbine: str, year: int, stride: int
) -> WindowSet:
    """Every known window of one turbine-year, in time order, at a stride.

    Args:
        every: Every known window, from :func:`known_windows`.
        turbines: Per window, its turbine id.
        key: The shard key the windows are carried under.
        turbine: The turbine.
        year: The calendar year.
        stride: Keep every ``stride``-th known window of the turbine-year.

    Returns:
        The windows, in the index's own order.

    Raises:
        ValueError: If the turbine-year holds no known window.
    """
    rows = turbine_year_rows(every, turbines, turbine, year, stride)
    if rows.size == 0:
        raise ValueError(f"{key}: {turbine} has no known window in {year}")
    return WindowSet(
        key=key,
        tokens=every.tokens,
        starts=every.starts[rows],
        ends=every.ends[rows],
        labels=every.labels[rows],
        years=every.years[rows],
    )


def events_inside(starts: np.ndarray, when: np.ndarray) -> np.ndarray:
    """The event starts a trace's span covers, which are the marks the figure draws.

    The span runs from the first window's last step to the horizon past the last one's, so
    an event the final windows are labelled against is drawn even though it falls after
    the last window.

    Args:
        starts: The turbine's event start timestamps, sorted.
        when: Per window, the UTC timestamp of its last step, in time order.

    Returns:
        The starts inside the span.
    """
    horizon = np.timedelta64(HORIZON_HOURS, "h")
    inside: np.ndarray = starts[(starts >= when[0]) & (starts <= when[-1] + horizon)]
    return inside


def hours_to_next_event(stamps: np.ndarray, starts: np.ndarray, horizon: int) -> np.ndarray:
    """Hours from each window's last step to the next event start, ``nan`` past the horizon.

    The label is true when an event starts in ``(t, t + H]``, so the search is strict on
    the left and inclusive on the right, and this column is present on exactly the windows
    the label calls positive.

    Args:
        stamps: Per window, the UTC timestamp of its last step.
        starts: Event start timestamps, sorted.
        horizon: The horizon, in hours.

    Returns:
        Per window, the hours, or ``nan`` where no event starts inside the horizon.
    """
    out = np.full(stamps.size, np.nan)
    if starts.size == 0:
        return out
    position = np.searchsorted(starts, stamps, side="right")
    inside = position < starts.size
    gap = np.full(stamps.size, np.nan)
    gap[inside] = (starts[position[inside]] - stamps[inside]) / np.timedelta64(1, "h")
    reached = inside & (gap <= horizon)
    out[reached] = gap[reached]
    return out


def read_probe_record(paths: ProjectPaths, seed: int) -> dict[str, Any]:
    """The tracked record of one ``tel_only`` seed: its rates and its F2 offset.

    Args:
        paths: Resolved project paths.
        seed: The trained seed.

    Returns:
        That seed's block of the seed-replication record.

    Raises:
        FileNotFoundError: If the record is not tracked.
        ValueError: If the record holds no such seed.
    """
    path = paths.repo_root / SEED_RECORD
    if not path.is_file():
        raise FileNotFoundError(f"{SEED_RECORD} not found")
    record = json.loads(path.read_text(encoding="utf-8"))
    for block in record["trained"]:
        if int(block["seed"]) == seed:
            return dict(block)
    raise ValueError(f"{SEED_RECORD} holds no trained seed {seed}")


def trace_turbine_year(
    paths: ProjectPaths,
    source: str,
    year: int,
    mixture_config: str,
    ladder_config: str,
    rung: str,
    checkpoint_dir: str,
    device_name: str = "cpu",
    rule: str = MOST_EVENTS,
) -> StreamTrace:
    """Score one turbine-year window by window and measure the pass.

    Args:
        paths: Resolved project paths.
        source: The site, whose test split holds the year.
        year: The calendar year.
        mixture_config: The joint mixture configuration, relative to the repository.
        ladder_config: The ladder configuration, relative to the repository.
        rung: The rung the backbone was pretrained at.
        checkpoint_dir: The run directory under ``checkpoints/`` holding the probe.
        device_name: Torch device; ``cpu``, which is the point of the demonstration.
        rule: Which declared selection rule chooses the turbine-year.

    Returns:
        The trace.

    Raises:
        FileNotFoundError: If the probe was never written.
        ValueError: If the rebuilt step axis disagrees with the shard manifest.
    """
    block = read_probe_record(paths, SEED)
    inputs = open_probe_inputs(
        paths,
        mixture_config,
        ladder_config,
        "tel_only",
        rung,
        LM_SELECTION_WINDOWS,
        "hill_of_towie",
        device_name,
    )
    label = inputs.ladder.risk.label
    stride = inputs.mixture.window_stride_steps

    # Both rules read the window index and the event table, and neither reads a score, so
    # the whole field is built before the probe is even loaded.
    field = selection_field(paths, inputs.telemetry, source, year, label, stride)
    key = field.key
    choice = field.choose(rule, float(block["pooled"]["base_rate"]))
    logger.info(
        "%s %d under %r: %s (%d event starts, positive-window rate %.4f; runner-up %s)",
        source,
        year,
        rule,
        choice.turbine,
        choice.events,
        choice.chosen.rate,
        choice.runner_up,
    )

    probe_path = paths.checkpoints_dir / checkpoint_dir / f"{rung}_trained_seed{SEED}_probe.pt"
    if not probe_path.is_file():
        raise FileNotFoundError(f"{probe_path} not found")
    model = load_saved_probe(probe_path, DESIGN, inputs)

    windows = turbine_year_windows(field.every, field.turbines, key, choice.turbine, year, stride)
    stamps = step_stamps(paths, source, "test")
    steps = int(inputs.telemetry.files()[key]["steps"])
    if stamps.size != steps:
        raise ValueError(f"{key}: rebuilt {stamps.size} steps against the manifest's {steps}")

    sampler = WindowSampler(
        [windows],
        batch_size=inputs.ladder.evaluation.batch_windows,
        tokens_per_step=inputs.telemetry.tokens_per_step,
        context_steps=inputs.telemetry.context_steps,
        labelled=True,
    )
    # As score_saved_probe scores everywhere else: no optimiser step, no graph, and the
    # pass in float32 because autocast is a CUDA path and this trace is the CPU one.
    started = time.perf_counter()
    with torch.inference_mode():
        logits, labels, _ = risk_logits(model, sampler, inputs.device, autocast_on=False)
    seconds = time.perf_counter() - started

    # ADR-0019's two-term correction, as the evaluation code applies it everywhere else:
    # the registered training prior, the training split's natural rate, and this probe's
    # own measured balanced-mean offset.
    risk = inputs.ladder.risk
    # open_probe_inputs refuses any other stage; restated here so the prior is read off the
    # stage that registers it rather than off a number written down again.
    if not isinstance(risk, PositiveAwareRiskStage):  # pragma: no cover - refused upstream
        raise ValueError(f"{ladder_config} is not the positive-aware risk stage")
    scores = at_natural_rate(
        logits,
        train_rate=float(risk.positive_fraction),
        natural_rate=float(block["natural_rate"]),
        balanced_shift=float(block["prior_band"]["shift"]),
    )

    ends = windows.ends
    interval = bootstrap_auprc(
        scores.probabilities,
        labels,
        window_blocks(ends, np.zeros_like(ends), BLOCK_STEPS),
        replicates=REPLICATES,
        seed=BOOTSTRAP_SEED,
        confidence=CONFIDENCE,
    )
    when = stamps[ends]
    starts = field.event_starts(choice.turbine)
    inside = events_inside(starts, when)
    pooled = block["pooled"]
    return StreamTrace(
        source=source,
        year=year,
        choice=choice,
        stamps=when,
        ends=ends,
        probabilities=scores.probabilities,
        labels=labels,
        hours=hours_to_next_event(when, starts, HORIZON_HOURS),
        events=inside,
        interval=interval,
        train_rate=scores.train_rate,
        natural_rate=scores.natural_rate,
        balanced_shift=float(block["prior_band"]["shift"]),
        offset=scores.offset,
        pooled_base_rate=float(pooled["base_rate"]),
        pooled_auprc=float(pooled["auprc"]),
        pooled_low=float(pooled["low"]),
        pooled_high=float(pooled["high"]),
        pooled_positives=int(pooled["positives"]),
        pooled_positive_blocks=int(pooled["positive_blocks"]),
        seconds=seconds,
        checkpoint=f"{checkpoint_dir}/{rung}_tel_only_seed{SEED}.pt",
        probe=f"{checkpoint_dir}/{probe_path.name}",
    )


def write_csv(trace: StreamTrace, path: Path) -> Path:
    """Write the trace: one row a window, in time order.

    Args:
        trace: The trace.
        path: Where to write.

    Returns:
        The file written.
    """
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ["timestamp_utc", "window_end_step", "probability", "label", "hours_to_next_event"]
        )
        for when, end, probability, label, hours in zip(
            trace.stamps,
            trace.ends,
            trace.probabilities,
            trace.labels,
            trace.hours,
            strict=True,
        ):
            writer.writerow(
                [
                    np.datetime_as_string(when, unit="s") + "Z",
                    int(end),
                    f"{float(probability):.6f}",
                    int(label),
                    "" if not np.isfinite(hours) else f"{float(hours):.2f}",
                ]
            )
    return path


def render_svg(trace: StreamTrace) -> str:
    """Draw the corrected probability against time, with the labelled events.

    Two horizontal reference lines are drawn, each labelled in words on the line itself:
    the pooled test base rate, and this turbine-year's own positive rate. Both are needed,
    because they differ by a large factor and a reader shown only the pooled one would
    read this turbine-year against the wrong denominator.

    Each event start is a vertical marker and the horizon before it a shaded band. No
    threshold, no alarm mark and no abstention band is drawn: the trace shows the score and
    the events, and the reader is left to judge.

    Args:
        trace: The trace.

    Returns:
        A standalone SVG document.
    """
    width, height = 900, 360
    left, right, top, bottom = 64, 24, 44, 52
    first, last = trace.stamps[0], trace.stamps[-1]
    span = max(float((last - first) / np.timedelta64(1, "h")), 1.0)
    ceiling = max(float(trace.probabilities.max()), trace.pooled_base_rate, trace.positive_rate)
    high = ceiling * 1.08

    def x(when: np.datetime64) -> float:
        hours = float((when - first) / np.timedelta64(1, "h"))
        return left + hours / span * (width - left - right)

    def y(value: float) -> float:
        return top + (high - value) / high * (height - top - bottom)

    turbine = trace.choice.turbine
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="system-ui, sans-serif" font-size="12">',
        f"<title>Prior-corrected probability against time, {turbine} {trace.year}, "
        f"{trace.windows:,} windows</title>",
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
        f'<text x="{left}" y="24" fill="{INK}" font-size="14" font-weight="600">'
        f"Prior-corrected probability, {turbine}, {trace.year} (illustrative)</text>",
    ]
    # The horizon before each event start, then the start itself, both under the trace so
    # that the score is never hidden by its own annotation.
    horizon = np.timedelta64(HORIZON_HOURS, "h")
    for start in trace.events:
        x0, x1 = x(max(start - horizon, first)), x(min(start, last))
        if x1 > x0:
            out.append(
                f'<rect class="horizon" x="{x0:.1f}" y="{top}" '
                f'width="{max(x1 - x0, 0.6):.1f}" '
                f'height="{height - top - bottom:.1f}" fill="{BAND}"/>'
            )
    for start in trace.events:
        if first <= start <= last:
            out.append(
                f'<line class="event" x1="{x(start):.1f}" x2="{x(start):.1f}" '
                f'y1="{top}" y2="{height - bottom}" stroke="{EVENT}" stroke-width="0.8" '
                'stroke-opacity="0.75"/>'
            )
    tick = 0.05 if high <= 0.6 else 0.2
    value = 0.0
    while value <= high:
        out.append(
            f'<line x1="{left}" x2="{width - right}" y1="{y(value):.1f}" y2="{y(value):.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
            f'<text x="{left - 8}" y="{y(value) + 4:.1f}" fill="{MUTED}" '
            f'text-anchor="end">{value:.2f}</text>'
        )
        value += tick
    out.extend(_reference_lines(trace, left, width - right, y))
    path = " ".join(
        f"{x(when):.1f},{y(float(p)):.1f}"
        for when, p in zip(trace.stamps, trace.probabilities, strict=True)
    )
    out.append(
        f'<polyline points="{path}" fill="none" stroke="{TRACE}" stroke-width="0.9" '
        'stroke-linejoin="round" stroke-opacity="0.9"/>'
    )
    for month in range(1, 13):
        when = np.datetime64(f"{trace.year}-{month:02d}-01T00:00:00")
        if first <= when <= last:
            out.append(
                f'<text x="{x(when):.1f}" y="{height - bottom + 18}" fill="{MUTED}" '
                f'text-anchor="middle">{"JFMAMJJASOND"[month - 1]}</text>'
            )
    out.append(
        f'<text x="{(left + width - right) / 2:.0f}" y="{height - 12}" fill="{MUTED}" '
        f'text-anchor="middle">{trace.year}, UTC</text>'
    )
    # A direct label on each mark, so nothing is identified by colour alone.
    out.append(
        f'<line x1="{left}" x2="{left + 16}" y1="34" y2="34" stroke="{TRACE}" '
        f'stroke-width="2"/><text x="{left + 22}" y="38" fill="{INK}">probability</text>'
        f'<rect x="{left + 110}" y="28" width="12" height="12" fill="{BAND}"/>'
        f'<text x="{left + 126}" y="38" fill="{INK}">{HORIZON_HOURS} h before an event</text>'
        f'<line x1="{left + 268}" x2="{left + 268}" y1="28" y2="40" stroke="{EVENT}" '
        f'stroke-width="1.5"/><text x="{left + 274}" y="38" fill="{INK}">'
        f"event start ({len(trace.events)})</text>"
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _reference_lines(
    trace: StreamTrace, left: float, right: float, y: Callable[[float], float]
) -> list[str]:
    """The two labelled rate lines: the pooled one, and this turbine-year's own.

    Each carries its name and its value as text on the line, so neither is identified by
    colour alone. When the two sit close enough for their labels to collide, the lower
    line's label is written under it instead of over it.

    Args:
        trace: The trace.
        left: Left edge of the plotting area.
        right: Right edge of the plotting area.
        y: The value-to-pixel mapping.

    Returns:
        One SVG fragment a line, in drawing order.
    """
    lines = [
        (trace.pooled_base_rate, "pooled test base rate", INK, "6 4"),
        (trace.positive_rate, f"{trace.choice.turbine} {trace.year} positive rate", RATE, "2 3"),
    ]
    heights = [y(value) for value, *_ in lines]
    under = [False, False]
    if abs(heights[0] - heights[1]) < 16:
        under[0 if heights[0] > heights[1] else 1] = True
    out = []
    for (value, name, colour, dashes), height, below in zip(lines, heights, under, strict=True):
        out.append(
            f'<line class="reference" x1="{left}" x2="{right}" y1="{height:.1f}" '
            f'y2="{height:.1f}" stroke="{colour}" stroke-width="1.2" '
            f'stroke-dasharray="{dashes}"/>'
            f'<text x="{right - 4}" y="{height + (14 if below else -6):.1f}" fill="{colour}" '
            f'text-anchor="end">{name} {value:.4f}</text>'
        )
    return out


def interval_against_own_rate(trace: StreamTrace) -> str:
    """The interval read against this turbine-year's own positive rate, in words.

    An AUPRC is only above chance relative to the base rate of the set it was measured on,
    and this set's base rate is not the pooled one. Stating which way round the comparison
    came out is not a verdict -- nothing is gated on it -- but leaving the reader to make
    it by eye would be.

    Args:
        trace: The trace.

    Returns:
        One sentence.
    """
    i = trace.interval
    if trace.clears:
        return (
            f"This turbine-year's 95% interval [{i.low:.4f}, {i.high:.4f}] CLEARS its own "
            f"positive rate {trace.positive_rate:.4f}: the lower bound is strictly above "
            f"it, which is the shape of ADR-0021's registered rule, read here against one "
            f"turbine-year rather than against a scored set, and gating nothing."
        )
    return (
        f"This turbine-year's 95% interval [{i.low:.4f}, {i.high:.4f}] CONTAINS its own "
        f"positive rate {trace.positive_rate:.4f}, so the trace is consistent with chance "
        f"on this turbine-year."
    )


def comparability(trace: StreamTrace) -> str:
    """Why this turbine-year's AUPRC does not stand beside the pooled one.

    The ground is the positive count, not the base rate. A single turbine-year holds a
    small fraction of the pooled split's positive windows, so its interval is far wider,
    and an estimate of that precision cannot be read against one of the pooled split's.
    (A ratio of base rates is no ground at all: two sets can share a base rate exactly and
    still be incomparable, and Kelmarsh 4's rate is only 1.1 times the pooled one.)

    The measured widening and the square-root guide are both stated, and whether they
    agree is read off the two numbers rather than asserted. They need not agree: the
    registered interval resamples two-day blocks, so the effective count is the positive
    blocks, not the positive windows.

    Args:
        trace: The trace.

    Returns:
        One or two sentences.
    """
    i = trace.interval
    gap = trace.widening / trace.root_widening
    if 0.8 <= gap <= 1.25:
        tail = f", and the two agree to within {abs(gap - 1.0) * 100:.0f}%."
    else:
        off = (
            f"{gap:.1f} times the guide"
            if gap > 1.0
            else f"{1.0 / gap:.1f} times narrower than the guide"
        )
        tail = (
            f", and the two do not agree: the measured widening is {off}. The guide counts "
            f"positive windows as though each stood on its own, while the registered "
            f"interval resamples two-day blocks, and this turbine-year's positives fall in "
            f"{i.positive_blocks:,} blocks against the pooled split's "
            f"{trace.pooled_positive_blocks:,} -- a reason to expect the guide to understate "
            f"the widening here, though not one that accounts for the whole of the gap."
        )
    return (
        f"The {i.auprc:.4f} is not comparable with the pooled test AUPRC "
        f"({trace.pooled_auprc:.4f} [{trace.pooled_low:.4f}, {trace.pooled_high:.4f}]): a "
        f"single turbine-year holds far fewer positive windows than the pooled test split "
        f"-- {trace.positives:,} against {trace.pooled_positives:,} -- so its interval is "
        f"correspondingly wider, and two estimates of such different precision do not stand "
        f"beside each other. This interval is {trace.widening:.1f} times the width of the "
        f"pooled one ({trace.interval_width:.4f} against {trace.pooled_interval_width:.4f}); "
        f"a square root of the positive counts, sqrt({trace.pooled_positives:,}/"
        f"{trace.positives:,}), suggests {trace.root_widening:.1f}{tail}"
    )


def observation(trace: StreamTrace) -> str:
    """What the selection rule did to this turbine-year, stated rather than left implicit.

    Args:
        trace: The trace.

    Returns:
        One sentence.
    """
    choice = trace.choice
    if choice.rule == MOST_EVENTS:
        return (
            f"One observation: {choice.events} event starts against a site runner-up of "
            f"{choice.runner_up_events} -- about one every {trace.days_between_events:.1f} "
            f"days -- so this turbine-year is atypical for the site, and it was selected by "
            f'"most events", which is a rule that selects atypical turbine-years by '
            f"construction."
        )
    runner_up = choice.candidates.get(choice.runner_up)
    beside = (
        f" (runner-up {choice.runner_up}, {runner_up.rate:.4f})" if runner_up is not None else ""
    )
    return (
        f"One observation: {choice.events} event starts -- about one every "
        f"{trace.days_between_events:.1f} days -- and a positive-window rate of "
        f"{trace.positive_rate:.4f}, {abs(trace.positive_rate - choice.target):.4f} from the "
        f"pooled test base rate {choice.target:.4f} and the closest of the site's "
        f'{len(choice.candidates)} turbines{beside}; it was selected by "typical event '
        f'rate", which is a rule that selects the turbine-year least unlike the pooled test '
        f"split, and reads no score to do it."
    )


def caption(trace: StreamTrace) -> str:
    """The caption, carrying the same numbers as the report.

    Args:
        trace: The trace.

    Returns:
        One paragraph.
    """
    i = trace.interval
    return (
        f"{trace.choice.turbine}, {trace.year}, scored on CPU: {trace.windows:,} windows of "
        f"1,872 telemetry tokens (144 steps x 13), one an hour, in time order. Selected "
        f"under the {RULE_NAMES[trace.choice.rule]} rule -- {trace.choice.criterion} -- one "
        f"of the two rules declared before any score was looked at; the other trace is "
        f"shown beside this one and neither is an evaluation result. Its own AUPRC is "
        f"{i.auprc:.4f} [{i.low:.4f}, {i.high:.4f}] under ADR-0021's block bootstrap "
        f"({BLOCK_STEPS // 144}-day blocks, {REPLICATES:,} replicates, seed "
        f"{BOOTSTRAP_SEED}). {interval_against_own_rate(trace)} {comparability(trace)} The "
        f"figure draws this turbine-year's own positive rate {trace.positive_rate:.4f} and "
        f"the pooled {trace.pooled_base_rate:.4f} as two labelled reference lines rather "
        f"than the pooled one alone, because an AUPRC is read against the base rate of the "
        f"set it was measured on. The mean corrected probability is "
        f"{trace.mean_probability:.4f}, beside a positive rate of {trace.positive_rate:.4f}: "
        f"they differ because ADR-0019's correction targets the training split's natural "
        f"rate {trace.natural_rate:.4f}, and not this turbine-year's. {observation(trace)} "
        f"**Illustrative, forward-in-time, same site, "
        f"a single turbine-year: not an evaluation result, and not comparable with the "
        f"pooled gate numbers.** No threshold, no alarm and no abstention is drawn or "
        f"computed. The model reads telemetry only."
    )


def selection_table(trace: StreamTrace) -> str:
    """The field both rules chose from: per turbine, its events and its positive rate.

    Args:
        trace: The trace.

    Returns:
        A Markdown table, one row a turbine of the site-year.
    """
    choice = trace.choice
    picks = {rule: choice.picks(rule) for rule in RULES}

    def note(turbine: str) -> str:
        """What the rules did with one turbine, and what this trace did with it."""
        parts = [f"chosen by {RULE_NAMES[rule]}" for rule in RULES if picks[rule] == turbine]
        if turbine == choice.turbine:
            parts.append("traced here")
        elif turbine == choice.runner_up:
            parts.append(f"runner-up under {RULE_NAMES[choice.rule]}")
        return "; ".join(parts)

    return table(
        [
            "turbine",
            f"narrow event starts in {trace.year}",
            "known windows",
            "positive-window rate",
            f"distance from {choice.target:.4f}",
            "note",
        ],
        [
            [
                year.turbine,
                year.events,
                f"{year.windows:,}",
                f"{year.rate:.4f}",
                f"{abs(year.rate - choice.target):.4f}",
                note(year.turbine),
            ]
            for year in choice.candidates.values()
        ],
    )


def render_report(trace: StreamTrace, paths: ProjectPaths, out_dir: Path | None = None) -> str:
    """Render the Markdown that sits beside the trace and its figure.

    Args:
        trace: The trace.
        paths: Resolved project paths.
        out_dir: Where the trace is written, and where its shared record is read
            from; ``reports/data/`` when omitted.

    Returns:
        The report.
    """
    i = trace.interval
    parts = [
        f"# Streaming trace: {trace.choice.turbine}, {trace.year}\n\n",
        kv_table(
            {
                "what this is": "a demonstration of the deployment path on CPU, not an evaluation",
                "selection rule": f"{RULE_NAMES[trace.choice.rule]} -- {trace.choice.criterion}",
                "backbone": f"`{trace.checkpoint}`",
                "probe": f"`{trace.probe}` (§a {DESIGN}, ADR-0022's addendum rule)",
                "windows": f"{trace.windows:,} at stride 6, every known window of the "
                "turbine-year in time order",
                "device": "cpu",
                "wall clock": f"{trace.seconds:.1f} s ({trace.windows_per_second:.1f} windows/s)",
                "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "git_sha": git_sha(paths.repo_root),
                "generated by": "faultline model stream-trace",
            }
        ),
        section(
            "1. The two selection rules, and the one this trace ran under",
            rules_block(read_traces((out_dir or paths.data_reports_dir) / TRACE_RECORD))
            + "\nBoth rules read labels only, and neither reads a score. The event count is "
            "the event starts the in-force label is built from, unfiltered, read from "
            f"`data/cleaned/telemetry/{trace.source}/labels/events_narrow.parquet`; the "
            "positive-window rate is taken over exactly the windows a trace of that turbine "
            "would score, so the chosen turbine's rate below is the positive rate section 3 "
            "reports.\n\n"
            f"**This trace ran under the {RULE_NAMES[trace.choice.rule]} rule**: "
            f"{trace.choice.criterion}.\n\n"
            + selection_table(trace)
            + "\nTie on the criterion, broken by lowest turbine id: "
            f"{'yes' if trace.choice.tied else 'no'}.\n",
        ),
        section(
            "2. The correction, as the record registered it",
            "ADR-0019's two-term logit correction, applied by "
            "`faultline.evaluation.calibration.at_natural_rate` -- the same function every "
            "gate reads its probabilities through. Nothing is re-derived here.\n\n"
            + kv_table(
                {
                    "π_train (registered)": f"{trace.train_rate} "
                    "(`configs/train/telemetry_v1.yaml`, `risk.positive_fraction`)",
                    "natural rate": f"{trace.natural_rate:.10f} (`{SEED_RECORD}`, "
                    f"`trained[seed {SEED}].natural_rate`)",
                    "F2 balanced-mean offset": f"{trace.balanced_shift:+.4f} (`{SEED_RECORD}`, "
                    f"`trained[seed {SEED}].prior_band.shift`; balanced mean rate "
                    "0.4900 is inside the registered band [0.45, 0.55], so the declared "
                    "correction stands and no re-centring is applied)",
                    "offset applied": f"{trace.offset:+.4f}",
                }
            ),
        ),
        section(
            "3. What the trace measured",
            kv_table(
                {
                    "windows scored": f"{trace.windows:,}",
                    "positive windows": f"{int(trace.labels.sum()):,}",
                    "this turbine-year's positive rate": f"{trace.positive_rate:.4f}",
                    "mean corrected probability": f"{trace.mean_probability:.4f}",
                    "this turbine-year's AUPRC": f"{i.auprc:.4f}",
                    "95% block-bootstrap interval": f"[{i.low:.4f}, {i.high:.4f}]",
                    "the interval against its own positive rate": "CLEARS it"
                    if trace.clears
                    else "CONTAINS it, so this turbine-year is consistent with chance",
                    "blocks": f"{i.blocks:,} two-day blocks, {i.positive_blocks:,} holding a "
                    "positive window",
                    "replicates": f"{i.replicates:,}, seed {i.seed}, "
                    f"{i.discarded:,} discarded ({i.discarded_share:.4%}; the registered "
                    f"rule refuses above {MAX_DISCARDED_SHARE:.0%})",
                    "pooled test base rate (reference line)": f"{trace.pooled_base_rate:.4f} "
                    f"(`{SEED_RECORD}`, `trained[seed {SEED}].pooled.base_rate`)",
                    "pooled test AUPRC (not comparable)": f"{trace.pooled_auprc:.4f} "
                    f"[{trace.pooled_low:.4f}, {trace.pooled_high:.4f}], measured on "
                    f"{trace.pooled_positives:,} positive windows against this "
                    f"turbine-year's {trace.positives:,}",
                    "CPU wall clock": f"{trace.seconds:.1f} s",
                    "throughput": f"{trace.windows_per_second:.1f} windows/s",
                }
            )
            + "\nThe interval is ADR-0021's registered block bootstrap, called through "
            "`faultline.evaluation.bootstrap.bootstrap_auprc`. It describes this turbine-year "
            f"and nothing else. {interval_against_own_rate(trace)}\n\n"
            f"{comparability(trace)}\n\nThe mean corrected "
            f"probability ({trace.mean_probability:.4f}) sits near the training split's "
            f"natural rate ({trace.natural_rate:.4f}), which is what ADR-0019's "
            "correction targets, and not near this turbine-year's own positive rate "
            f"({trace.positive_rate:.4f}). The correction was never aimed at this turbine: "
            "the gap is this turbine-year's event density against the distribution the head "
            "was calibrated on, visible here rather than argued, and one more reason these "
            "numbers do not transfer to the pooled ones.\n",
        ),
        section(
            "4. The files",
            table(
                ["file", "what it holds"],
                [
                    [
                        f"`{trace.stem}.csv`",
                        "one row a window: `timestamp_utc`, `window_end_step`, `probability`, "
                        "`label`, `hours_to_next_event` (blank beyond the "
                        f"{HORIZON_HOURS} h horizon)",
                    ],
                    [
                        f"`{trace.stem}.svg`",
                        "probability against time; two labelled reference lines, the pooled "
                        "test base rate and this turbine-year's own positive rate; each event "
                        "start a vertical marker with the horizon before it shaded",
                    ],
                    [
                        f"`{TRACE_RECORD}`",
                        "both traces in one record, a row a rule, which is where this report "
                        "and `figures_index.md` read the other rule's trace from",
                    ],
                ],
            ),
        ),
        section("5. Caption", caption(trace)),
        section(
            "6. What this is not",
            "This trace adds no rule, no ADR and no verdict, and changes nothing in the "
            "record. It is one turbine-year of one site, and the site is a training site: "
            "the split is forward in time, not across sites. Its AUPRC is therefore not "
            "comparable with the pooled gate numbers, and the programme's findings "
            "(ADR-0025 INCONCLUSIVE, ADR-0026's read-out result) stand exactly as the "
            "ledger records them.\n\nTwo turbine-years are not a sample. The two rules in "
            "section 1 were written down before any score was looked at, and both traces "
            "are shown whichever way they came out -- but two examples chosen under two "
            "rules measure nothing. They show what a signal of this strength looks like "
            "against a year of one turbine, on the site's densest turbine-year and on its "
            "most typical, and they stop there.\n",
        ),
    ]
    return "".join(parts)


@dataclass(frozen=True)
class RecordInputs:
    """What a render-only pass opens: two configs and a shard index, and nothing else.

    No checkpoint is loaded and no split is built, because nothing is scored. The stride
    and the label column come from the same configurations the scoring pass reads them
    from, so the field the render rebuilds is the field the run chose from.

    Attributes:
        mixture: The joint mixture configuration.
        ladder: The ladder configuration, whose risk stage names the label.
        telemetry: The telemetry shard set.
    """

    mixture: JointMixtureConfig
    ladder: LadderConfig
    telemetry: ShardSet

    @property
    def label(self) -> str:
        """The window-index column the risk head reads as its target."""
        return self.ladder.risk.label

    @property
    def stride(self) -> int:
        """The stride a trace of a turbine-year scores at."""
        return self.mixture.window_stride_steps


def open_record_inputs(
    paths: ProjectPaths, mixture_config: str, ladder_config: str
) -> RecordInputs:
    """Open the configurations and shards a render reads; no model, no split, no checkpoint.

    Args:
        paths: Resolved project paths.
        mixture_config: The joint mixture configuration, relative to the repository.
        ladder_config: The ladder configuration, relative to the repository.

    Returns:
        The opened inputs.

    Raises:
        ValueError: If the ladder is not the positive-aware risk stage the trace reads.
    """
    mixture = load_config(paths.repo_root / mixture_config, JointMixtureConfig)
    ladder = load_config(paths.repo_root / ladder_config, LadderConfig)
    if not isinstance(ladder.risk, PositiveAwareRiskStage):
        raise ValueError(f"{ladder_config} is not the positive-aware risk stage")
    bins = load_config(paths.repo_root / mixture.telemetry_tokenizer_config, QuantileBinsConfig)
    return RecordInputs(
        mixture=mixture,
        ladder=ladder,
        telemetry=ShardSet.load(shards_dir(paths, tokenizer_path(paths, bins))),
    )


def read_csv(path: Path) -> dict[str, np.ndarray]:
    """Read back a written trace, column by column, as :func:`write_csv` wrote it.

    Args:
        path: The trace's CSV.

    Returns:
        ``stamps``, ``ends``, ``probabilities``, ``labels`` and ``hours``, in file order,
        which is time order.

    Raises:
        FileNotFoundError: If the CSV is absent; it is part of the record, not an output
            the render may invent.
        ValueError: If it holds no window.
    """
    if not path.is_file():
        raise FileNotFoundError(f"{path.name} not found: a trace's CSV is part of the record")
    stamps: list[np.datetime64] = []
    ends: list[int] = []
    probabilities: list[float] = []
    labels: list[int] = []
    hours: list[float] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            stamps.append(np.datetime64(row["timestamp_utc"].removesuffix("Z"), "ns"))
            ends.append(int(row["window_end_step"]))
            probabilities.append(float(row["probability"]))
            labels.append(int(row["label"]))
            gap = row["hours_to_next_event"]
            hours.append(float(gap) if gap else float("nan"))
    if not ends:
        raise ValueError(f"{path.name} holds no window")
    return {
        "stamps": np.array(stamps, dtype="datetime64[ns]"),
        "ends": np.array(ends, dtype=np.int64),
        "probabilities": np.array(probabilities, dtype=np.float64),
        "labels": np.array(labels, dtype=np.int64),
        "hours": np.array(hours, dtype=np.float64),
    }


def check_against_record(
    trace: StreamTrace, entry: Mapping[str, Any], measured: AuprcInterval
) -> None:
    """Refuse a render whose rebuilt trace disagrees with the record it was read from.

    A render-only pass prints the record's own AUPRC and bounds, and reads the rest off
    the committed CSV. That is only honest if the two agree, so every quantity the record
    carries is held against the rebuilt one at the precision the report prints it, and the
    interval recomputed from the CSV is held against the recorded one at the same
    precision. Nothing is written when any of them disagrees.

    Args:
        trace: The trace rebuilt from the record and the CSV.
        entry: Its entry in the record.
        measured: The interval recomputed from the CSV, before the record's own AUPRC and
            bounds were substituted into it.

    Raises:
        ValueError: On the first disagreement, naming the field and both values.
    """
    exact: list[tuple[str, Any, Any]] = [
        ("turbine", trace.choice.turbine, str(entry["turbine"])),
        ("stem", trace.stem, str(entry["stem"])),
        ("events", trace.choice.events, int(entry["events"])),
        ("windows", trace.windows, int(entry["windows"])),
        ("clears_own_base_rate", trace.clears, bool(entry["clears_own_base_rate"])),
    ]
    for field, rebuilt, recorded in exact:
        if rebuilt != recorded:
            raise ValueError(
                f"{entry['stem']}: {field} is {rebuilt!r}, the record says {recorded!r}"
            )
    printed: list[tuple[str, float, float, str]] = [
        ("positive_rate", trace.positive_rate, float(entry["positive_rate"]), ".4f"),
        ("mean_probability", trace.mean_probability, float(entry["mean_probability"]), ".4f"),
        ("auprc", measured.auprc, float(entry["auprc"]), ".4f"),
        ("low", measured.low, float(entry["low"]), ".4f"),
        ("high", measured.high, float(entry["high"]), ".4f"),
        ("seconds", trace.seconds, float(entry["seconds"]), ".1f"),
    ]
    for field, rebuilt, recorded, spec in printed:
        if format(rebuilt, spec) != format(recorded, spec):
            raise ValueError(
                f"{entry['stem']}: {field} renders as {rebuilt:{spec}}, "
                f"the record says {recorded:{spec}}"
            )


def trace_from_record(
    paths: ProjectPaths,
    entry: Mapping[str, Any],
    inputs: RecordInputs,
    block: Mapping[str, Any],
    checkpoint_dir: str,
    rung: str,
    out_dir: Path,
) -> StreamTrace:
    """Rebuild one trace from the committed record and its committed CSV.

    Nothing is scored and no checkpoint is opened: the per-window probabilities are the
    ones the run wrote, the AUPRC and its bounds are the ones the record holds, and the
    field the rules chose from is rebuilt from the label column. The block counts and the
    discard count are the only figures the record does not carry, and they come from
    ADR-0021's registered bootstrap re-run over the written probabilities -- which also
    reproduces the AUPRC and its bounds, so :func:`check_against_record` can hold the
    rebuild against the record before a byte is written.

    Args:
        paths: Resolved project paths.
        entry: One entry of the trace record.
        inputs: The configurations and shards, from :func:`open_record_inputs`.
        block: The trained seed's block of the seed-replication record.
        checkpoint_dir: The run directory the probe was loaded from, for the header.
        rung: The rung the backbone was pretrained at, for the header.
        out_dir: Where the record and the CSVs live.

    Returns:
        The rebuilt trace.

    Raises:
        ValueError: If the rebuild disagrees with the record.
    """
    source, year = str(entry["source"]), int(entry["year"])
    columns = read_csv(out_dir / f"{entry['stem']}.csv")
    field = selection_field(paths, inputs.telemetry, source, year, inputs.label, inputs.stride)
    choice = field.choose(str(entry["rule"]), float(block["pooled"]["base_rate"]))
    ends = columns["ends"]
    # ADR-0021's registered bootstrap, over the probabilities the run wrote. The record's
    # own auprc, low and high are put back afterwards, so the report prints the record's
    # numbers and not a second measurement of them.
    measured = bootstrap_auprc(
        columns["probabilities"],
        columns["labels"],
        window_blocks(ends, np.zeros_like(ends), BLOCK_STEPS),
        replicates=REPLICATES,
        seed=BOOTSTRAP_SEED,
        confidence=CONFIDENCE,
    )
    interval = replace(
        measured,
        auprc=float(entry["auprc"]),
        low=float(entry["low"]),
        high=float(entry["high"]),
    )
    risk = inputs.ladder.risk
    if not isinstance(risk, PositiveAwareRiskStage):  # pragma: no cover - refused upstream
        raise ValueError("the ladder is not the positive-aware risk stage")
    # The correction is a constant of three registered rates; asking the registered
    # function for it over no logits is how the offset is read without scoring anything.
    scores = at_natural_rate(
        np.zeros(0),
        train_rate=float(risk.positive_fraction),
        natural_rate=float(block["natural_rate"]),
        balanced_shift=float(block["prior_band"]["shift"]),
    )
    pooled = block["pooled"]
    trace = StreamTrace(
        source=source,
        year=year,
        choice=choice,
        stamps=columns["stamps"],
        ends=ends,
        probabilities=columns["probabilities"],
        labels=columns["labels"],
        hours=columns["hours"],
        events=events_inside(field.event_starts(choice.turbine), columns["stamps"]),
        interval=interval,
        train_rate=scores.train_rate,
        natural_rate=scores.natural_rate,
        balanced_shift=float(block["prior_band"]["shift"]),
        offset=scores.offset,
        pooled_base_rate=float(pooled["base_rate"]),
        pooled_auprc=float(pooled["auprc"]),
        pooled_low=float(pooled["low"]),
        pooled_high=float(pooled["high"]),
        pooled_positives=int(pooled["positives"]),
        pooled_positive_blocks=int(pooled["positive_blocks"]),
        seconds=float(entry["seconds"]),
        checkpoint=f"{checkpoint_dir}/{rung}_tel_only_seed{SEED}.pt",
        probe=f"{checkpoint_dir}/{rung}_trained_seed{SEED}_probe.pt",
    )
    check_against_record(trace, entry, measured)
    return trace


def render_stream_traces(
    paths: ProjectPaths,
    mixture_config: str = "configs/train/joint_v0.yaml",
    ladder_config: str = "configs/train/telemetry_v1.yaml",
    rung: str = "S2",
    checkpoint_dir: str = "seed_replication_v0_424c4f33",
    out_dir: Path | None = None,
) -> list[tuple[Path, Path]]:
    """Rewrite every trace's report and figure from the committed record. Nothing is scored.

    This is the path a correction to the prose takes. The scoring pass is a GPU-free but
    twenty-minute affair and it would write new numbers; a caption fixed by re-scoring
    would therefore be a caption fixed against a different measurement. So the record is
    the input here, the record and the CSVs are read and never written, and the two
    derived files -- the report and the figure -- are the only things that move.

    Args:
        paths: Resolved project paths.
        mixture_config: The joint mixture configuration.
        ladder_config: The ladder configuration.
        rung: The rung the backbone was pretrained at, for the header.
        checkpoint_dir: The run directory the probe was loaded from, for the header.
        out_dir: Where the record and the traces live; ``reports/data/`` when omitted.

    Returns:
        Per trace, its figure and its report.

    Raises:
        FileNotFoundError: If the record is absent. There is nothing to render from, and
            writing a report without one would be inventing the numbers rather than
            reading them.
        ValueError: If the record holds no trace, or a rebuild disagrees with it.
    """
    target = out_dir or paths.data_reports_dir
    record = target / TRACE_RECORD
    if not record.is_file():
        raise FileNotFoundError(
            f"{record} not found: --render-only reads the committed record and writes none"
        )
    entries = read_traces(record)
    if not entries:
        raise ValueError(f"{record} holds no trace")
    before = record.read_bytes()
    inputs = open_record_inputs(paths, mixture_config, ladder_config)
    block = read_probe_record(paths, SEED)
    traces = [
        trace_from_record(paths, entry, inputs, block, checkpoint_dir, rung, target)
        for entry in entries
    ]
    written: list[tuple[Path, Path]] = []
    for trace in traces:
        svg_path = target / f"{trace.stem}.svg"
        svg_path.write_text(render_svg(trace), encoding="utf-8", newline="\n")
        report = target / f"{trace.stem}.md"
        report.write_text(render_report(trace, paths, target), encoding="utf-8", newline="\n")
        logger.info(
            "%s: rendered from the record, AUPRC %.4f [%.4f, %.4f]; nothing scored",
            trace.stem,
            trace.interval.auprc,
            trace.interval.low,
            trace.interval.high,
        )
        written.append((svg_path, report))
    if record.read_bytes() != before:
        raise ValueError(f"{record} changed during a render-only pass")
    return written


def write_stream_traces(
    paths: ProjectPaths,
    source: str = "kelmarsh",
    year: int = 2023,
    mixture_config: str = "configs/train/joint_v0.yaml",
    ladder_config: str = "configs/train/telemetry_v1.yaml",
    rung: str = "S2",
    checkpoint_dir: str = "seed_replication_v0_424c4f33",
    device_name: str = "cpu",
    rules: Sequence[str] = RULES,
    out_dir: Path | None = None,
) -> list[tuple[Path, Path, Path]]:
    """Trace a turbine-year under each rule, then write every file once all are scored.

    Every report states both rules side by side, so a report written between two scoring
    passes would name a trace that did not exist yet. The passes therefore all run first,
    the shared record is written whole, and only then is a report rendered: the pair of
    reports a run leaves behind agrees with itself.

    Args:
        paths: Resolved project paths.
        source: The site.
        year: The calendar year of its test split to trace.
        mixture_config: The joint mixture configuration.
        ladder_config: The ladder configuration.
        rung: The rung the backbone was pretrained at.
        checkpoint_dir: The run directory under ``checkpoints/`` holding the probe.
        device_name: Torch device.
        rules: The declared rules to run, one trace each.
        out_dir: Where to write; ``reports/data/`` when omitted.

    Returns:
        Per rule, its CSV, its SVG and its Markdown report.
    """
    traces = [
        trace_turbine_year(
            paths,
            source,
            year,
            mixture_config,
            ladder_config,
            rung,
            checkpoint_dir,
            device_name,
            rule,
        )
        for rule in rules
    ]
    target = out_dir or paths.data_reports_dir
    target.mkdir(parents=True, exist_ok=True)
    for trace in traces:
        write_trace(target / TRACE_RECORD, trace.record())
    written: list[tuple[Path, Path, Path]] = []
    for trace in traces:
        csv_path = write_csv(trace, target / f"{trace.stem}.csv")
        svg_path = target / f"{trace.stem}.svg"
        svg_path.write_text(render_svg(trace), encoding="utf-8", newline="\n")
        report = target / f"{trace.stem}.md"
        report.write_text(render_report(trace, paths, target), encoding="utf-8", newline="\n")
        logger.info(
            "%s %d %s under %r: %d windows in %.1f s (%.1f windows/s), AUPRC %.4f "
            "[%.4f, %.4f] against a positive rate of %.4f",
            trace.source,
            trace.year,
            trace.choice.turbine,
            trace.choice.rule,
            trace.windows,
            trace.seconds,
            trace.windows_per_second,
            trace.interval.auprc,
            trace.interval.low,
            trace.interval.high,
            trace.positive_rate,
        )
        written.append((csv_path, svg_path, report))
    return written


def write_stream_trace(
    paths: ProjectPaths,
    source: str = "kelmarsh",
    year: int = 2023,
    mixture_config: str = "configs/train/joint_v0.yaml",
    ladder_config: str = "configs/train/telemetry_v1.yaml",
    rung: str = "S2",
    checkpoint_dir: str = "seed_replication_v0_424c4f33",
    device_name: str = "cpu",
    rule: str = MOST_EVENTS,
    out_dir: Path | None = None,
) -> tuple[Path, Path, Path]:
    """Run one rule's trace and write its files, leaving the other rule's alone.

    The shared record is merged rather than overwritten, so rerunning one rule keeps the
    other's entry. The other rule's *report* is not re-rendered, though, so a run of one
    rule after the other has moved is best done through :func:`write_stream_traces`.

    Args:
        paths: Resolved project paths.
        source: The site.
        year: The calendar year of its test split to trace.
        mixture_config: The joint mixture configuration.
        ladder_config: The ladder configuration.
        rung: The rung the backbone was pretrained at.
        checkpoint_dir: The run directory under ``checkpoints/`` holding the probe.
        device_name: Torch device.
        rule: Which declared selection rule chooses the turbine-year.
        out_dir: Where to write; ``reports/data/`` when omitted.

    Returns:
        The CSV, the SVG and the Markdown report.
    """
    return write_stream_traces(
        paths,
        source,
        year,
        mixture_config,
        ladder_config,
        rung,
        checkpoint_dir,
        device_name,
        [rule],
        out_dir,
    )[0]
