"""ADR-0029 (EXPLORATORY): the record's metrics under ADR-0009's variant label; persistence.

Reported, not gating. **Nothing here issues, re-decides or withdraws a verdict.** For each
registered gate and rule, the registered decision function is applied to the variant label's
quantities, and the report states as a fact whether it would return the outcome the record holds.

**Part A.** Every reported test metric of ADR-0025 (H1), ADR-0026 (H1′), ADR-0027 and ADR-0028,
recomputed from the saved per-window scores under ``narrow_within_24h_without``. The variant label
is taken from the window index for exactly the evaluated rows: per shard key, the rows known under
``narrow_within_24h``, every 12th from offset 0 (:func:`faultline.evaluation.axis_gate.index_rows`).
Each metric is computed on the evaluated rows the variant knows. The 9 rows it does not know are
named, with the reason, before anything else.

**Part B.** Four persistence scores on the same rows, under both labels:

- **P1**, a narrow event of the turbine started in ``(t − 24 h, t]``;
- **P2**, −(hours since the last narrow event start at or before ``t``), capped at 720 h;
- **P3**, a provider ``Stop`` row attached in ``(t − 24 h, t]`` whose code opens a narrow event in
  the training split (the frozen set of ADR-0029 §2);
- **P4**, P3 read only from the messages present in the model's R0 window.

**The estimator is ADR-0024's, unchanged**: two-day blocks within each shard, formed on the rows
evaluated; 10,000 replicates; seed 20260916; 95% percentile intervals; 1% discard rule. Every
scorer's replicate AUPRCs are computed once per set of rows by F6-3's
:func:`faultline.evaluation.h1_verdict.replicate_auprcs`, and a paired Δ is the percentile interval
of two vectors differenced replicate by replicate. ADR-0028's statistics are
:func:`faultline.evaluation.risk_coverage.run_statistics_job`'s, with τ, κ, the margin cut-off and
Platt's (a, b) read from the committed operating-point record, never refitted.

**Checks made before anything is reported.** Every saved score file covers the same 137,025 rows
in the same order. Under the full label, every recomputed point value equals the recorded one.
Both labels, re-derived from the event table, equal the window index on every evaluated row. The
full-label replicate vectors of ``joint`` (d) and of the status-only classifier equal F7'-3's
cached vectors element by element. The frozen code set equals the one the rule derives.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pydantic import Field

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, table
from faultline.data.common.splits import SplitsConfig
from faultline.data.joint.mixture_shards import messages_in_stream_order, nanoseconds
from faultline.data.telemetry.harmonise import horizon_labels, to_seconds
from faultline.data.telemetry.labels import EventLabelsConfig
from faultline.data.telemetry.pipeline import load_telemetry_config, parquet_files, stage_source_dir
from faultline.data.telemetry.shards import event_starts
from faultline.data.telemetry.verify import opening_messages
from faultline.evaluation.ablation_runs import ablation_layout
from faultline.evaluation.ablation_verdict import decide_ablation, random_prefix
from faultline.evaluation.ablation_verdict import scorer_files as ablation_files
from faultline.evaluation.abstention_gate import AbstentionConfig
from faultline.evaluation.abstention_outcome import ladder_file
from faultline.evaluation.abstention_verdict import (
    arm_label,
    decide_gate_a,
    decide_gate_b,
    decide_h2,
    load_ensemble,
    operating_point_record,
    operating_points,
    out_dir,
    platt_maps,
    registered_test_files,
)
from faultline.evaluation.axis_gate import AxisGateConfig, index_rows
from faultline.evaluation.bootstrap import AuprcInterval, DeltaInterval, window_blocks
from faultline.evaluation.gate_check import BootstrapConfig
from faultline.evaluation.h1_scoring import scoring_layout, write_json
from faultline.evaluation.h1_verdict import decide_h1, replicate_auprcs
from faultline.evaluation.h1_verdict import scorer_files as h1_files
from faultline.evaluation.metrics import average_precision
from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.readout_runs import readout_layout
from faultline.evaluation.readout_verdict import MAX_BOOTSTRAP_WORKERS, decide_random_init_gate
from faultline.evaluation.readout_verdict import scorer_files as readout_files
from faultline.evaluation.risk_coverage import (
    TEST,
    Ensemble,
    Interval,
    OperatingPoint,
    StatisticsJob,
    apply_platt,
    interval,
    paired_interval,
    permutation_seeds,
    run_statistics_job,
    statistics,
)
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.joint_windows import message_spans, step_offsets, tail_anchored
from faultline.training.mixture import JointMixtureConfig
from faultline.training.windows import ShardSet

logger = get_logger(__name__)

#: The two label sets every Part B score is read under; Part A reads the variant.
FULL, VARIANT = "full", "variant"
#: Seconds in an hour and in a grid step.
HOUR, STEP_SECONDS = 3600, 600
#: Two recomputations of one point value agree when they differ by no more than this.
AGREEMENT = 1e-12
#: The status of every number this module writes.
STATUS = "EXPLORATORY (ADR-0029): reported, not gating; no verdict is issued or re-decided"


# =====================================================================================
# configuration (configs/eval/exploratory_v0.yaml)
# =====================================================================================


class RecordedReports(StrictModel):
    """The committed records whose numbers are the "original" column."""

    h1: str
    readout: str
    ablation: str
    abstention: str


class PersistenceConfig(StrictModel):
    """ADR-0029 §2, by value.

    Attributes:
        window_hours: P1 and P3 read ``(t − window_hours, t]``.
        cap_hours: P2's cap; no earlier event reads the cap.
        composition_hours: The look-backs of the composition table.
        train_until: The training split's last instant; the code set is read before it.
        stop_status: The provider status of a stop row.
        opening_cause: The cause whose stop rows open a narrow event.
        codes: The frozen code set.
        joint_mixture_config: The mixture whose ``tel+status`` stream the model read.
        status_convention: The stream's status convention.
        context_tokens: The model window's token budget.
        context_steps: Steps an M1 window holds.
        tokens_per_step: Telemetry tokens per step.
    """

    window_hours: int = Field(gt=0)
    cap_hours: int = Field(gt=0)
    composition_hours: list[int]
    train_until: str
    stop_status: str
    opening_cause: str
    codes: list[str]
    joint_mixture_config: str
    status_convention: str
    context_tokens: int = Field(gt=0)
    context_steps: int = Field(gt=0)
    tokens_per_step: int = Field(gt=0)


class ExploratoryConfig(StrictModel):
    """Top level of ``configs/eval/exploratory_v*.yaml``."""

    version: int
    registered_in: str
    axis_config: str
    h1_gate_config: str
    readout_config: str
    ablation_config: str
    abstention_config: str
    recorded: RecordedReports
    label: str
    variant_label: str
    stride: int = Field(gt=0)
    windows: int = Field(gt=0)
    positives: int = Field(gt=0)
    bootstrap: BootstrapConfig
    persistence: PersistenceConfig


# =====================================================================================
# the persistence feature builders (pure; unit-tested on synthetic data)
# =====================================================================================


def starts_within(
    t: np.ndarray, turbines: np.ndarray, starts: Mapping[str, np.ndarray], seconds: int
) -> np.ndarray:
    """Per window, whether its turbine has a start in ``(t − seconds, t]``.

    Args:
        t: Per window, its end time in integer seconds.
        turbines: Per window, its turbine.
        starts: Per turbine, sorted start times in integer seconds.
        seconds: The look-back.

    Returns:
        Per window, the flag.
    """
    out = np.zeros(t.size, dtype=bool)
    for turbine in np.unique(turbines):
        mine = turbines == turbine
        mark = np.asarray(starts.get(str(turbine), np.zeros(0, dtype=np.int64)))
        upto = np.searchsorted(mark, t[mine], side="right")
        before = np.searchsorted(mark, t[mine] - seconds, side="right")
        out[mine] = upto > before
    return out


def hours_since_last(
    t: np.ndarray, turbines: np.ndarray, starts: Mapping[str, np.ndarray], cap_hours: float
) -> np.ndarray:
    """Per window, hours since its turbine's last start at or before ``t``, capped.

    Args:
        t: Per window, its end time in integer seconds.
        turbines: Per window, its turbine.
        starts: Per turbine, sorted start times in integer seconds.
        cap_hours: The cap; a window with no earlier start reads it.

    Returns:
        Per window, the hours (P2 is their negative).
    """
    out = np.full(t.size, float(cap_hours))
    for turbine in np.unique(turbines):
        mine = np.flatnonzero(turbines == turbine)
        mark = np.asarray(starts.get(str(turbine), np.zeros(0, dtype=np.int64)))
        upto = np.searchsorted(mark, t[mine], side="right")
        seen = upto > 0
        last = mark[upto[seen] - 1]
        out[mine[seen]] = np.minimum((t[mine[seen]] - last) / HOUR, float(cap_hours))
    return out


def by_turbine(turbines: np.ndarray, seconds: np.ndarray) -> dict[str, np.ndarray]:
    """Group times by turbine, each group sorted."""
    return {
        str(turbine): np.sort(seconds[turbines == turbine]).astype(np.int64)
        for turbine in np.unique(turbines)
    }


def opening_rows(
    events: pd.DataFrame, stream: pd.DataFrame, cause: str, stop_status: str
) -> np.ndarray:
    """Per event, the position in ``stream`` of the row that opens it, or −1.

    The rule is :func:`faultline.data.telemetry.verify.opening_messages`': the first stop row of
    the cause starting in the event's first step, failing that the last one started before it.
    It returns the row rather than its message, so the row's code can be read.

    Args:
        events: Events with ``turbine_id`` and ``start_utc``.
        stream: The status stream: ``turbine_id``, ``start_utc``, ``provider_status``, ``cause``.
        cause: The events' cause.
        stop_status: The provider status of a stop row.

    Returns:
        Per event, a position into ``stream``'s rows, or −1.
    """
    result = np.full(len(events), -1, dtype=np.int64)
    candidate = np.flatnonzero(
        (stream["provider_status"].to_numpy() == stop_status)
        & (stream["cause"].to_numpy() == cause)
    )
    if candidate.size == 0 or events.empty:
        return result
    stop_turbines = stream["turbine_id"].astype(str).to_numpy()[candidate]
    stop_seconds = to_seconds(stream["start_utc"].iloc[candidate])
    event_seconds = to_seconds(events["start_utc"])
    event_turbines = events["turbine_id"].astype(str).to_numpy()
    for turbine in np.unique(event_turbines):
        mine = np.flatnonzero(stop_turbines == turbine)
        if mine.size == 0:
            continue
        order = mine[np.argsort(stop_seconds[mine], kind="stable")]
        seconds = stop_seconds[order]
        wanted = np.flatnonzero(event_turbines == turbine)
        low = np.searchsorted(seconds, event_seconds[wanted], side="left")
        high = np.searchsorted(seconds, event_seconds[wanted] + STEP_SECONDS, side="left")
        pick = np.where(high > low, low, low - 1)
        found = pick >= 0
        result[wanted[found]] = candidate[order[pick[found]]]
    return result


def opening_codes(
    events: pd.DataFrame, stream: pd.DataFrame, cause: str, stop_status: str, until: str
) -> pd.DataFrame:
    """The codes that open the events starting at or before ``until``, with their counts.

    Args:
        events: Events with ``turbine_id`` and ``start_utc``.
        stream: The status stream, with ``code`` and ``message`` besides :func:`opening_rows`'.
        cause: The events' cause.
        stop_status: The provider status of a stop row.
        until: The last instant counted (UTC, ISO 8601).

    Returns:
        One row per (code, message): ``code``, ``message``, ``events``; and the events with no
        opener, as a row whose code is ``<none>``.
    """
    chosen = events[pd.to_datetime(events["start_utc"], utc=True) <= pd.Timestamp(until)]
    rows = opening_rows(chosen, stream, cause, stop_status)
    codes = np.where(
        rows >= 0, stream["code"].astype(str).to_numpy()[np.maximum(rows, 0)], "<none>"
    )
    messages = np.where(
        rows >= 0, stream["message"].astype(str).to_numpy()[np.maximum(rows, 0)], "<none>"
    )
    frame = pd.DataFrame({"code": codes, "message": messages})
    return frame.value_counts().rename("events").reset_index()


def flagged_stop_times(
    stream: pd.DataFrame, codes: Sequence[str], stop_status: str
) -> dict[str, np.ndarray]:
    """P3's rows: per turbine, the attachment times of stop rows whose code is in the set.

    A row is attached as the joint builder attaches a message: its start rounded **up** to the
    10-minute grid (:func:`faultline.data.joint.mixture_shards.attach_steps`).

    Args:
        stream: The status stream: ``turbine_id``, ``start_utc``, ``code``, ``provider_status``.
        codes: The code set.
        stop_status: The provider status of a stop row.

    Returns:
        Per turbine, sorted attachment times in integer seconds.
    """
    chosen = stream[
        (stream["provider_status"] == stop_status) & stream["code"].astype(str).isin(list(codes))
    ]
    if chosen.empty:
        return {}
    seconds = nanoseconds(chosen["start_utc"], ceil=True) // 1_000_000_000
    return by_turbine(chosen["turbine_id"].astype(str).to_numpy(), seconds)


def flagged_in_spans(
    opens: np.ndarray, closes: np.ndarray, flags: np.ndarray, first: np.ndarray, last: np.ndarray
) -> np.ndarray:
    """Per window ``[first, last)``, whether a flagged message has any token inside it.

    Args:
        opens: Per message in stream order, the offset of its ``<txt>``.
        closes: Per message, one past its ``</txt>``.
        flags: Per message, whether it counts.
        first: Per window, its first token.
        last: Per window, one past its last token.

    Returns:
        Per window, the flag.
    """
    counted = np.r_[0, np.cumsum(flags.astype(np.int64))]
    after = np.searchsorted(closes, first, side="right")
    before = np.searchsorted(opens, last, side="left")
    return np.asarray(counted[np.maximum(before, after)] - counted[after] > 0)


def flagged_in_steps(
    steps: np.ndarray, flags: np.ndarray, first: np.ndarray, last: np.ndarray
) -> np.ndarray:
    """Per window of steps ``[first, last]``, whether a flagged message follows one of them."""
    counted = np.r_[0, np.cumsum(flags.astype(np.int64))]
    after = np.searchsorted(steps, first, side="left")
    before = np.searchsorted(steps, last, side="right")
    return np.asarray(counted[np.maximum(before, after)] - counted[after] > 0)


def model_window_flags(
    stream: np.ndarray,
    message_steps: np.ndarray,
    flags: np.ndarray,
    ends: np.ndarray,
    context_steps: int,
    context: int,
    tokens_per_step: int,
) -> tuple[np.ndarray, np.ndarray]:
    """P4 and its uncapped twin, on one ``tel+status`` stream.

    Args:
        stream: The stream's tokens.
        message_steps: Per message in stream order, the step it follows.
        flags: Per message, whether its code and status count.
        ends: Per window, its end step.
        context_steps: Steps an M1 window holds.
        context: The model window's token budget.
        tokens_per_step: Telemetry tokens per step.

    Returns:
        Per window: whether a flagged message is inside the tail-anchored window (P4), and
        whether one follows any of the window's ``context_steps`` steps with no token cap.

    Raises:
        ValueError: If the messages do not follow the stream's steps.
    """
    offsets = step_offsets(stream)
    opens, closes = message_spans(stream)
    if not np.array_equal(np.searchsorted(offsets, opens, side="right") - 1, message_steps):
        raise ValueError("the messages do not follow the stream's steps")
    span = tail_anchored(offsets, int(stream.size), ends, context_steps, context, tokens_per_step)
    capped = flagged_in_spans(opens, closes, flags, span.first, span.first + span.length)
    uncapped = flagged_in_steps(message_steps, flags, ends - context_steps + 1, ends)
    return capped, uncapped


# =====================================================================================
# the evaluated rows
# =====================================================================================


@dataclass(frozen=True)
class EvaluatedRows:
    """The rows every saved score covers, in scoring order, joined to the window index.

    Attributes:
        keys: The shard keys, in set order.
        which: Per row, its shard index.
        ends: Per row, its end step.
        turbines: Per row, its turbine.
        years: Per row, its year.
        t: Per row, its end step's time, integer seconds.
        full: Per row, the full label.
        variant: Per row, the variant label (False where it is not known).
        variant_known: Per row, whether the variant knows it.
    """

    keys: list[str]
    which: np.ndarray
    ends: np.ndarray
    turbines: np.ndarray
    years: np.ndarray
    t: np.ndarray
    full: np.ndarray
    variant: np.ndarray
    variant_known: np.ndarray


def step_times(paths: ProjectPaths, source: str, split: str) -> np.ndarray:
    """Every step of one M1 shard, as integer seconds, in the order the shard holds them.

    The shard builder writes each final turbine-year's rows of a split in time order, file after
    file (:func:`faultline.data.telemetry.shards.encode_turbine_year`); this walks them the same
    way.
    """
    parts = []
    for file in parquet_files(stage_source_dir(paths, "final", source)):
        if "split" not in pq.read_schema(file).names:
            continue
        frame = pd.read_parquet(file, columns=["timestamp_utc", "split"])
        frame = frame.sort_values("timestamp_utc", kind="stable")
        parts.append(nanoseconds(frame["timestamp_utc"][frame["split"] == split]))
    return np.concatenate(parts) // 1_000_000_000


def evaluated_rows(
    paths: ProjectPaths,
    shards: ShardSet,
    keys: list[str],
    reference: ScoredWindows,
    label: str,
    variant_label: str,
    stride: int,
) -> EvaluatedRows:
    """Join the scored rows to the window index and to their end times, refusing any mismatch.

    Raises:
        ValueError: If a row's end step, shard or label differs from the reference scoring's.
    """
    frames, times = [], []
    for position, key in enumerate(keys):
        source, split = key.split("__")
        if reference.sources[position] != source:
            raise ValueError(f"scored source {reference.sources[position]} is not {key}'s")
        frame = index_rows(
            shards,
            key,
            label,
            stride,
            ["turbine_id", "year", label, variant_label, f"{variant_label}_known"],
        )
        steps = step_times(paths, source, split)
        if steps.size != int(shards.files()[key]["steps"]):
            raise ValueError(f"{key}: {steps.size} step times for {shards.files()[key]['steps']}")
        frames.append(frame.assign(which=position))
        times.append(steps[frame["end_step"].to_numpy(np.int64)])
    joined = pd.concat(frames, ignore_index=True)
    rows = EvaluatedRows(
        keys=keys,
        which=joined["which"].to_numpy(np.int64),
        ends=joined["end_step"].to_numpy(np.int64),
        turbines=joined["turbine_id"].astype(str).to_numpy(),
        years=joined["year"].to_numpy(np.int64),
        t=np.concatenate(times).astype(np.int64),
        full=joined[label].to_numpy(bool),
        variant=joined[variant_label].to_numpy(bool),
        variant_known=joined[f"{variant_label}_known"].to_numpy(bool),
    )
    if not (
        np.array_equal(rows.ends, reference.ends)
        and np.array_equal(rows.which, reference.which)
        and np.array_equal(rows.full, reference.labels > 0.5)
    ):
        raise ValueError("the window index does not join the scored rows in order")
    return rows


def _iso(seconds: int) -> str:
    return datetime.fromtimestamp(int(seconds), tz=UTC).strftime("%Y-%m-%d %H:%M")


def reconcile(
    paths: ProjectPaths,
    telemetry_config: Path,
    rows: EvaluatedRows,
    horizon_steps: int,
    stop_status: str,
    cause: str,
) -> dict[str, Any]:
    """Name the rows the variant does not know and why; re-derive both labels on every row.

    Args:
        paths: Resolved project paths.
        telemetry_config: The telemetry configuration the shards were built under.
        rows: The evaluated rows.
        horizon_steps: The label's horizon.
        stop_status: The provider status of a stop row.
        cause: The narrow cause.

    Returns:
        The reconciliation record.
    """
    telemetry = load_telemetry_config(telemetry_config)
    rules = load_config(paths.repo_root / str(telemetry.events.labels_config), EventLabelsConfig)
    splits = load_config(paths.repo_root / telemetry.final.splits_config, SplitsConfig)
    messages = list(splits.report_without_messages)
    horizon = horizon_steps * STEP_SECONDS
    mismatch = {"full": 0, "variant": 0, "variant_known": 0}
    unknown: list[dict[str, Any]] = []
    for position, key in enumerate(rows.keys):
        source = key.split("__")[0]
        starts = event_starts(paths, source, rules, messages)
        if starts is None:
            raise ValueError(f"{source} carries no status strings; the variant is undefined")
        labels_dir = paths.source_dir("cleaned", "telemetry", source) / "labels"
        events = pd.read_parquet(labels_dir / "events_narrow.parquet")
        stream = pd.read_parquet(labels_dir / "status_stream.parquet")
        opener = opening_messages(events, stream, cause, stop_status).astype(str).to_numpy()
        event_turbines = events["turbine_id"].astype(str).to_numpy()
        event_seconds = to_seconds(events["start_utc"])
        here = rows.which == position
        for turbine in np.unique(rows.turbines[here]):
            mine = np.flatnonzero(here & (rows.turbines == turbine))
            stamps = pd.Series(pd.to_datetime(rows.t[mine], unit="s", utc=True))
            covered = starts.covered.get(str(turbine), np.zeros(0, dtype=np.int64))
            every = starts.every.get(str(turbine), np.zeros(0, dtype=np.int64))
            kept = starts.kept.get(str(turbine), np.zeros(0, dtype=np.int64))
            full = horizon_labels(
                stamps, pd.Series(pd.to_datetime(every, unit="s", utc=True)), horizon_steps, covered
            )
            variant = horizon_labels(
                stamps, pd.Series(pd.to_datetime(kept, unit="s", utc=True)), horizon_steps, covered
            )
            mismatch["full"] += int(
                (full.isna().to_numpy() | (full.fillna(False).to_numpy() != rows.full[mine])).sum()
            )
            mismatch["variant_known"] += int(
                (variant.notna().to_numpy() != rows.variant_known[mine]).sum()
            )
            mismatch["variant"] += int(
                (variant.fillna(False).to_numpy() != rows.variant[mine]).sum()
            )
            for row in mine[~rows.variant_known[mine]]:
                t = int(rows.t[row])
                inside = int(
                    np.searchsorted(covered, t + horizon, side="right")
                    - np.searchsorted(covered, t, side="right")
                )
                opened = np.flatnonzero(
                    (event_turbines == turbine)
                    & (event_seconds > t)
                    & (event_seconds <= t + horizon)
                )
                unknown.append(
                    {
                        "shard": key,
                        "turbine": str(turbine),
                        "year": int(rows.years[row]),
                        "end_step": int(rows.ends[row]),
                        "end_utc": _iso(t),
                        "full_label": bool(rows.full[row]),
                        "events_in_horizon": [
                            {"start_utc": _iso(int(event_seconds[e])), "opened_by": str(opener[e])}
                            for e in opened
                        ],
                        "horizon_steps_in_record": inside,
                        "horizon_steps": horizon_steps,
                        "last_recorded_step_utc": _iso(int(covered[-1])) if covered.size else "",
                    }
                )
    reasons = {
        (
            all(e["opened_by"] in messages for e in u["events_in_horizon"])
            and bool(u["events_in_horizon"])
            and u["full_label"]
            and u["horizon_steps_in_record"] < horizon_steps
        )
        for u in unknown
    }
    return {
        "evaluated_windows": int(rows.t.size),
        "evaluated_positives": int(rows.full.sum()),
        "variant_known": int(rows.variant_known.sum()),
        "variant_positives": int(rows.variant[rows.variant_known].sum()),
        "unjoinable": 0,
        "unknown": unknown,
        "reason": (
            "every row the variant does not know is positive under the full label only through "
            "events that 'anemometer defect' opens, and its horizon runs past the event record "
            "(fewer covered steps than the horizon); with those events removed no event is seen, "
            "and ADR-0006 makes an unseen, uncovered horizon unknown (NA), never False"
            if reasons == {True}
            else "see the rows: not every unknown row has the same reason"
        ),
        "one_reason": reasons == {True},
        "relabel_mismatches": mismatch,
        "messages_removed": messages,
    }


# =====================================================================================
# sets of rows, scorers and replicate vectors
# =====================================================================================


@dataclass(frozen=True)
class RowSet:
    """One set of evaluated rows under one label: the rows every interval of it reads.

    Attributes:
        name: ``<label set>__<stratum>``.
        mask: Per evaluated row, whether it is in the set.
        labels: Per row in the set, 1 if positive.
        blocks: Per row in the set, its block.
    """

    name: str
    mask: np.ndarray
    labels: np.ndarray
    blocks: np.ndarray

    def describe(self) -> dict[str, Any]:
        """Windows, positives, blocks and positive blocks."""
        positive = self.labels > 0.5
        return {
            "windows": int(self.mask.sum()),
            "positives": int(positive.sum()),
            "base_rate": float(positive.mean()),
            "blocks": int(np.unique(self.blocks).size),
            "positive_blocks": int(np.unique(self.blocks[positive]).size),
        }


def row_set(
    labels: str, stratum: str, where: np.ndarray, rows: EvaluatedRows, block_steps: int
) -> RowSet:
    """The rows of one stratum known under one label set, with its blocks re-formed on them."""
    if labels == FULL:
        mask, truth = where.copy(), rows.full
    else:
        mask, truth = where & rows.variant_known, rows.variant
    return RowSet(
        name=f"{labels}__{stratum}",
        mask=mask,
        labels=truth[mask].astype(np.float64),
        blocks=window_blocks(rows.ends[mask], rows.which[mask], block_steps),
    )


@dataclass(frozen=True)
class AuprcJob:
    """One scorer's AUPRC and base rate on every replicate of one set of rows."""

    cache: Path
    scores: np.ndarray
    labels: np.ndarray
    blocks: np.ndarray
    replicates: int
    seed: int


def run_auprc_job(job: AuprcJob) -> Path:
    """Compute one replicate vector with F6-3's function and write it atomically."""
    values, bases = replicate_auprcs(job.scores, job.labels, job.blocks, job.replicates, job.seed)
    partial = job.cache.with_name(job.cache.stem + ".partial.npz")
    job.cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(partial, values=values, bases=bases)
    partial.replace(job.cache)
    return job.cache


def run_any(job: AuprcJob | StatisticsJob) -> Path:
    """Dispatch one job to its function (one pool serves both kinds)."""
    if isinstance(job, AuprcJob):
        return run_auprc_job(job)
    return run_statistics_job(job)


def run_pool(jobs: Sequence[AuprcJob | StatisticsJob], max_workers: int) -> int:
    """Every missing job on a capped process pool, in the order given; returns how many ran."""
    if not jobs:
        return 0
    workers = max(1, min(len(jobs), (os.cpu_count() or 2) - 2, max_workers))
    logger.info("bootstrapping %d jobs on %d worker processes", len(jobs), workers)
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_any, job) for job in jobs]
        for future in as_completed(futures):
            done += 1
            logger.info("written: %s (%d/%d)", future.result().name, done, len(jobs))
    return done


def scorer_id(path: Path) -> str:
    """A scores file's name in the cache: its directory and stem, unique across the record."""
    return f"{path.parent.name}__{path.stem}"


class Vectors:
    """Scores, row sets and their cached replicate vectors, and the intervals read from them."""

    def __init__(self, cache: Path, bootstrap: BootstrapConfig) -> None:
        """Start empty.

        Args:
            cache: Where the vectors are written.
            bootstrap: The estimator.
        """
        self.cache = cache
        self.bootstrap = bootstrap
        self.scores: dict[str, np.ndarray] = {}
        self.sets: dict[str, RowSet] = {}
        self.wanted: dict[tuple[str, str], None] = {}

    def add_file(self, path: Path, reference: ScoredWindows) -> str:
        """Register a scores file (logit plus prior offset), refusing other rows."""
        key = scorer_id(path)
        if key not in self.scores:
            scored = ScoredWindows.load(path)
            if not scored.same_windows(reference):
                raise ValueError(f"{path.name} does not cover the evaluated rows")
            # The record adds the offset in the logits' own dtype; so does this, or ties move.
            self.scores[key] = scored.logits + scored.prior_offset
        return key

    def path(self, where: str, scorer: str) -> Path:
        """The cache file of one vector."""
        return self.cache / f"{where}__{scorer}.npz"

    def want(self, where: str, scorer: str) -> None:
        """Ask for one vector."""
        self.wanted[(where, scorer)] = None

    def jobs(self) -> list[AuprcJob]:
        """The vectors asked for and not yet on disk."""
        b = self.bootstrap
        out = []
        for where, scorer in self.wanted:
            if self.path(where, scorer).is_file():
                continue
            s = self.sets[where]
            out.append(
                AuprcJob(
                    self.path(where, scorer),
                    self.scores[scorer][s.mask],
                    s.labels,
                    s.blocks,
                    b.replicates,
                    b.seed,
                )
            )
        return out

    def vector(self, where: str, scorer: str) -> tuple[np.ndarray, np.ndarray]:
        """One cached vector: per replicate, the AUPRC and the base rate."""
        with np.load(self.path(where, scorer)) as data:
            return data["values"], data["bases"]

    def point(self, where: str, scorer: str) -> float:
        """One scorer's AUPRC on the set's rows as scored."""
        s = self.sets[where]
        return average_precision(self.scores[scorer][s.mask], s.labels)

    def single(self, where: str, scorer: str) -> dict[str, Any]:
        """``bootstrap_auprc``'s interval from the cached vector, with the lift beside it."""
        s, b = self.sets[where], self.bootstrap
        values, bases = self.vector(where, scorer)
        described = s.describe()
        auprc = self.point(where, scorer)
        low, high = _quantiles(values, b.confidence)
        lift_low, lift_high = _quantiles(values - bases, b.confidence)
        found = AuprcInterval(
            unit="block",
            auprc=auprc,
            low=low,
            high=high,
            lift_low=lift_low,
            lift_high=lift_high,
            base_rate=described["base_rate"],
            windows=described["windows"],
            positives=described["positives"],
            blocks=described["blocks"],
            positive_blocks=described["positive_blocks"],
            replicates=b.replicates,
            discarded=int(np.isnan(values).sum()),
            confidence=b.confidence,
            seed=b.seed,
        )
        return {**asdict(found), "lift": auprc / described["base_rate"]}

    def paired(self, where: str, first: str, second: str) -> DeltaInterval:
        """``paired_bootstrap_deltas``' interval on AUPRC(first) − AUPRC(second).

        Raises:
            ValueError: If the two vectors discard different replicates.
        """
        s, b = self.sets[where], self.bootstrap
        va, _ = self.vector(where, first)
        vb, _ = self.vector(where, second)
        if not np.array_equal(np.isnan(va), np.isnan(vb)):
            raise ValueError(f"{first} and {second} were not drawn on the same rows")
        described = s.describe()
        a, c = self.point(where, first), self.point(where, second)
        low, high = _quantiles(va - vb, b.confidence)
        return DeltaInterval(
            unit="block",
            delta=a - c,
            low=low,
            high=high,
            first_auprc=a,
            second_auprc=c,
            windows=described["windows"],
            positives=described["positives"],
            blocks=described["blocks"],
            positive_blocks=described["positive_blocks"],
            replicates=b.replicates,
            discarded=int(np.isnan(va).sum()),
            confidence=b.confidence,
            seed=b.seed,
        )


def _quantiles(values: np.ndarray, confidence: float) -> tuple[float, float]:
    kept = values[~np.isnan(values)]
    if not kept.size:
        return math.nan, math.nan
    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(kept, [tail, 1.0 - tail])
    return float(low), float(high)


# =====================================================================================
# Part A: the rows of each record
# =====================================================================================


@dataclass(frozen=True)
class Row:
    """One reported number of a record, and where the record holds it.

    Attributes:
        family: The record (``ADR-0025`` ...).
        section: Its section (``B1`` ...).
        name: What the row reads.
        stratum: ``pooled``, ``has_status`` or ``no_status``.
        first: The scorer read (a single) or the first side of a Δ.
        second: The Δ's second side, or empty for a single.
        recorded: Keys into the record's JSON.
    """

    family: str
    section: str
    name: str
    stratum: str
    first: str
    second: str
    recorded: tuple[str, ...]


def _single(family: str, section: str, name: str, stratum: str, first: str, *path: str) -> Row:
    return Row(family, section, name, stratum, first, "", path)


def _pair(
    family: str, section: str, name: str, stratum: str, first: str, second: str, *path: str
) -> Row:
    return Row(family, section, name, stratum, first, second, path)


def h1_rows(ids: Mapping[str, str], seeds: Sequence[int], farms: Sequence[str]) -> list[Row]:
    """ADR-0025's B1-B6, as ``h1_verdict.run_h1_verdict`` reports them."""
    f, out = "ADR-0025", []
    for s in seeds:
        j, t, i = ids[f"joint_R0_{s}"], ids[f"tel_only_{s}"], ids[f"iii_R0_{s}"]
        k = str(s)
        out += [
            _single(f, "B1", f"joint (a) seed {s}", "pooled", j, "B1", k, "joint"),
            _single(f, "B1", f"tel_only (a) seed {s}", "pooled", t, "B1", k, "tel_only"),
            _pair(f, "B1", f"Δ(joint − tel_only) seed {s}", "pooled", j, t, "B1", k, "delta"),
            _single(f, "B2", f"control (iii) seed {s}", "pooled", i, "B2", k, "iii"),
            _pair(f, "B2", f"Δ(joint − iii) seed {s}", "pooled", j, i, "B2", k, "joint_minus_iii"),
            _pair(
                f,
                "B2",
                f"Δ(iii − tel_only) seed {s}",
                "pooled",
                i,
                t,
                "B2",
                k,
                "iii_minus_tel_only",
            ),
            _single(
                f, "B3", f"joint R2 seed {s}", "pooled", ids[f"joint_R2_{s}"], "B3", k, "joint_r2"
            ),
            _pair(
                f,
                "B3",
                f"Δ(R2 − R0) seed {s}",
                "pooled",
                ids[f"joint_R2_{s}"],
                j,
                "B3",
                k,
                "r2_minus_r0",
            ),
        ]
        for where in ("has_status", "no_status"):
            for prefix, label in (
                ("joint_R0", "joint"),
                ("tel_only", "tel_only"),
                ("iii_R0", "iii"),
            ):
                out.append(
                    _single(
                        f,
                        "B4",
                        f"{label} seed {s}",
                        where,
                        ids[f"{prefix}_{s}"],
                        "B4",
                        k,
                        where,
                        prefix,
                    )
                )
            out.append(
                _pair(
                    f,
                    "B4",
                    f"Δ(joint − tel_only) seed {s}",
                    where,
                    j,
                    t,
                    "B4",
                    k,
                    where,
                    "joint_minus_tel_only",
                )
            )
        out.append(
            _single(
                f,
                "B5",
                f"text withheld seed {s}",
                "pooled",
                ids[f"joint_m1_{s}"],
                "B5",
                k,
                "text_withheld",
            )
        )
        for farm in farms:
            m = ids[f"joint_mask_{farm}_{s}"]
            out += [
                _single(
                    f, "B5", f"{farm} mask seed {s}", "pooled", m, "B5", k, "masks", farm, "masked"
                ),
                _pair(
                    f,
                    "B5",
                    f"Δ({farm} mask − R0) seed {s}",
                    "pooled",
                    m,
                    j,
                    "B5",
                    k,
                    "masks",
                    farm,
                    "masked_minus_r0",
                ),
            ]
    for arm in ("joint", "iii"):
        for s in seeds:
            sel, fin = ids[f"{arm}_selected_{s}"], ids[f"{arm}_R0_{s}"]
            out += [
                _single(
                    f,
                    "B6",
                    f"{arm} selected seed {s}",
                    "pooled",
                    sel,
                    "B6",
                    f"{arm}_{s}",
                    "selected",
                ),
                _pair(
                    f,
                    "B6",
                    f"Δ({arm} final − selected) seed {s}",
                    "pooled",
                    fin,
                    sel,
                    "B6",
                    f"{arm}_{s}",
                    "final_minus_selected",
                ),
            ]
    return out


def readout_rows(ids: Mapping[str, str], seeds: Sequence[int]) -> list[Row]:
    """ADR-0026's gate and B1-B7, as ``readout_verdict.run_readout_verdict`` reports them."""
    f, out = "ADR-0026", []
    for j in seeds:
        for r in seeds:
            out.append(
                _pair(
                    f,
                    "G",
                    f"Δ((d) joint {j} − (d) random {r})",
                    "pooled",
                    ids[f"d_joint_{j}"],
                    ids[f"d_rand_{r}"],
                    "G",
                    f"joint{j}_rand{r}",
                )
            )
    for s in seeds:
        d, k = ids[f"d_joint_{s}"], str(s)
        out += [
            _single(f, "B1", f"joint (d) seed {s}", "pooled", d, "B1", k, "d_joint"),
            _single(
                f,
                "B1",
                f"tel_only (a) seed {s}",
                "pooled",
                ids[f"tel_only_{s}"],
                "B1",
                k,
                "tel_only",
            ),
            _pair(
                f,
                "B1",
                f"Δ(joint (d) − tel_only (a)) seed {s}",
                "pooled",
                d,
                ids[f"tel_only_{s}"],
                "B1",
                k,
                "delta",
            ),
            _single(
                f, "B2", f"(d) control seed {s}", "pooled", ids[f"d_ctrl_{s}"], "B2", k, "d_ctrl"
            ),
            _pair(
                f,
                "B2",
                f"Δ(joint (d) − (d) control) seed {s}",
                "pooled",
                d,
                ids[f"d_ctrl_{s}"],
                "B2",
                k,
                "delta",
            ),
            _single(
                f, "B3", f"joint (b) seed {s}", "pooled", ids[f"b_joint_{s}"], "B3", k, "b_joint"
            ),
            _single(
                f, "B3", f"joint (a) seed {s}", "pooled", ids[f"a_joint_{s}"], "B3", k, "a_joint"
            ),
            _pair(
                f,
                "B3",
                f"Δ(joint (b) − joint (a)) seed {s}",
                "pooled",
                ids[f"b_joint_{s}"],
                ids[f"a_joint_{s}"],
                "B3",
                k,
                "delta",
            ),
            _pair(
                f,
                "B4",
                f"parity Δ(joint (d) − status-only) seed {s}",
                "pooled",
                d,
                ids["status_only_bag"],
                "B4",
                k,
                "delta",
            ),
            _single(
                f, "B7", f"(d) random seed {s}", "pooled", ids[f"d_rand_{s}"], "B7", k, "d_rand"
            ),
            _pair(
                f,
                "B7",
                f"Δ((d) control − (d) random) seed {s}",
                "pooled",
                ids[f"d_ctrl_{s}"],
                ids[f"d_rand_{s}"],
                "B7",
                k,
                "delta",
            ),
        ]
        for where in ("has_status", "no_status"):
            out += [
                _single(f, "B5", f"joint (d) seed {s}", where, d, "B5", k, where, "d_joint"),
                _single(
                    f,
                    "B5",
                    f"tel_only (a) seed {s}",
                    where,
                    ids[f"tel_only_{s}"],
                    "B5",
                    k,
                    where,
                    "tel_only",
                ),
                _pair(
                    f,
                    "B5",
                    f"Δ(joint (d) − tel_only (a)) seed {s}",
                    where,
                    d,
                    ids[f"tel_only_{s}"],
                    "B5",
                    k,
                    where,
                    "delta",
                ),
            ]
    out.insert(
        len(seeds) ** 2,
        _single(
            f,
            "B4",
            "status-only classifier",
            "pooled",
            ids["status_only_bag"],
            "B4",
            "1",
            "status_only_bag",
        ),
    )
    return out


def ablation_rows(
    ids: Mapping[str, str],
    seeds: Sequence[int],
    arms: Sequence[str],
    random: Mapping[str, str],
    where_for: Callable[[str, str], str],
) -> list[Row]:
    """ADR-0027's gates and B1-B4, as ``ablation_verdict.run_ablation_verdict`` reports them."""
    f, out = "ADR-0027", []
    ref = "R-joint-d"
    for arm in arms:
        for j in seeds:
            for r in seeds:
                g = f"seed{j}_rand{r}"
                out.append(
                    _pair(
                        f,
                        f"G {arm}",
                        f"Δ({arm} {j} − random {r})",
                        "pooled",
                        ids[f"{arm}_{j}"],
                        ids[f"{random[arm]}_{r}"],
                        "G",
                        arm,
                        g,
                        "delta",
                    )
                )
        for s in seeds:
            a, d, k = ids[f"{arm}_{s}"], ids[f"{ref}_{s}"], str(s)
            out += [
                _single(
                    f, f"B1 {arm}", f"{arm} (d) seed {s}", "pooled", a, "B1", arm, k, "ablation"
                ),
                _single(
                    f, f"B1 {arm}", f"joint (d) seed {s}", "pooled", d, "B1", arm, k, "joint_d"
                ),
                _pair(
                    f,
                    f"B1 {arm}",
                    f"Δ({arm} − joint (d)) seed {s}",
                    "pooled",
                    a,
                    d,
                    "B1",
                    arm,
                    k,
                    "delta",
                ),
                _pair(
                    f,
                    f"B2 {arm}",
                    f"Δ({arm} − tel_only (a)) seed {s}",
                    "pooled",
                    a,
                    ids[f"tel_only_{s}"],
                    "B2",
                    arm,
                    k,
                    "delta",
                ),
                _pair(
                    f,
                    f"B3 {arm}",
                    f"Δ({arm} − status-only) seed {s}",
                    "pooled",
                    a,
                    ids["status_only_bag"],
                    "B3",
                    arm,
                    k,
                    "delta",
                ),
            ]
            for where in ("has_status", "no_status"):
                w = where_for(arm, where)
                out += [
                    _single(
                        f, f"B4 {arm}", f"{arm} seed {s}", w, a, "B4", arm, k, where, "ablation"
                    ),
                    _single(
                        f, f"B4 {arm}", f"joint (d) seed {s}", w, d, "B4", arm, k, where, "joint_d"
                    ),
                    _pair(
                        f,
                        f"B4 {arm}",
                        f"Δ({arm} − joint (d)) seed {s}",
                        w,
                        a,
                        d,
                        "B4",
                        arm,
                        k,
                        where,
                        "delta",
                    ),
                ]
    return out


def dig(record: Mapping[str, Any], path: Sequence[str]) -> dict[str, Any]:
    """Follow keys into a record."""
    node: Any = record
    for key in path:
        node = node[key]
    return dict(node)


def recorded_point(row: Row, record: Mapping[str, Any]) -> float:
    """The recorded point value of a row: its AUPRC, or its Δ."""
    found = dig(record, row.recorded)
    return float(found["delta"] if row.second else found["auprc"])


def _slim_single(d: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("auprc", "low", "high", "base_rate", "windows", "positives", "discarded")
    out = {k: d[k] for k in keys}
    out["lift"] = float(d["auprc"]) / float(d["base_rate"])
    return out


def _slim_delta(d: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("delta", "low", "high", "first_auprc", "second_auprc", "windows", "positives")
    return {**{k: d[k] for k in keys}, "discarded": d["discarded"], "replicates": d["replicates"]}


def evaluate_rows(
    rows: Sequence[Row], record: Mapping[str, Any], vectors: Vectors
) -> list[dict[str, Any]]:
    """Each row: the record's value beside the variant's, from the cached vectors."""
    out = []
    for row in rows:
        where = f"{VARIANT}__{row.stratum}"
        original = dig(record, row.recorded)
        if row.second:
            variant = _slim_delta(asdict(vectors.paired(where, row.first, row.second)))
            original = _slim_delta(original)
        else:
            variant = _slim_single(vectors.single(where, row.first))
            original = _slim_single(original)
        out.append(
            {
                "family": row.family,
                "section": row.section,
                "row": row.name,
                "stratum": row.stratum,
                "kind": "delta" if row.second else "auprc",
                "original": original,
                "variant": variant,
            }
        )
    return out


def check_full_points(
    rows: Sequence[Row], record: Mapping[str, Any], vectors: Vectors
) -> list[str]:
    """Rows whose full-label point value, recomputed here, differs from the record's."""
    wrong = []
    for row in rows:
        where = f"{FULL}__{row.stratum}"
        value = vectors.point(where, row.first)
        if row.second:
            value -= vectors.point(where, row.second)
        if abs(value - recorded_point(row, record)) > AGREEMENT:
            wrong.append(f"{row.family} {row.section} {row.name} ({row.stratum})")
    return wrong


def _delta(entries: Sequence[dict[str, Any]], section: str, name: str) -> DeltaInterval:
    for e in entries:
        if e["section"] == section and e["row"] == name:
            v = e["variant"]
            return DeltaInterval(
                unit="block",
                delta=v["delta"],
                low=v["low"],
                high=v["high"],
                first_auprc=v["first_auprc"],
                second_auprc=v["second_auprc"],
                windows=v["windows"],
                positives=v["positives"],
                blocks=0,
                positive_blocks=0,
                replicates=v["replicates"],
                discarded=v["discarded"],
                confidence=0.95,
                seed=0,
            )
    raise KeyError(f"{section} {name}")


# =====================================================================================
# Part A: ADR-0028
# =====================================================================================


def subset(e: Ensemble, mask: np.ndarray, labels: np.ndarray) -> Ensemble:
    """An ensemble restricted to some of its rows, with other labels."""
    return Ensemble(
        split=e.split,
        p=e.p[mask],
        u=e.u[mask],
        corrected=e.corrected[:, mask],
        labels=labels[mask].astype(np.float64),
        which=e.which[mask],
        ends=e.ends[mask],
        sources=e.sources,
    )


@dataclass(frozen=True)
class AbstentionInputs:
    """ADR-0028's ensembles and fitted operating model, as the record read them."""

    config: AbstentionConfig
    clean: dict[str, Ensemble]
    masked: dict[int, Ensemble]
    points: dict[str, OperatingPoint]
    platt: dict[str, tuple[float, float]]
    seeds: np.ndarray


def abstention_inputs(
    paths: ProjectPaths, config_path: Path, rows: EvaluatedRows
) -> AbstentionInputs:
    """Load the clean and masked ensembles and the committed operating points; refuse other rows."""
    config = load_config(config_path, AbstentionConfig)
    root, counts = paths.repo_root, config.splits.test
    record = operating_point_record(paths, config)
    if not record.is_file():
        raise FileNotFoundError(f"{record} is missing: the operating point is never fitted here")
    directory = out_dir(paths, config)
    clean = {
        arm.name: load_ensemble(
            registered_test_files(config, root, arm.name), TEST, counts.windows, counts.positives
        )
        for arm in config.arms
    }
    masked = {
        k: load_ensemble(
            [ladder_file(directory, config.ladder.arm, s, k, config.stride) for s in config.seeds],
            TEST,
            counts.windows,
            counts.positives,
        )
        for k in config.ladder.severities
    }
    for e in [*clean.values(), *masked.values()]:
        if not (np.array_equal(e.ends, rows.ends) and np.array_equal(e.which, rows.which)):
            raise ValueError("an ADR-0028 ensemble does not cover the evaluated rows in order")
    return AbstentionInputs(
        config=config,
        clean=clean,
        masked=masked,
        points=operating_points(record, config, directory),
        platt=platt_maps(record),
        seeds=permutation_seeds(
            config.risk_coverage.random_seed, config.risk_coverage.random_orderings
        ),
    )


def abstention_jobs(
    a: AbstentionInputs, rows: EvaluatedRows, cache: Path, bootstrap: BootstrapConfig
) -> dict[str, StatisticsJob]:
    """F9-3's scenarios, on the rows the variant knows, with the variant label."""
    m, y = rows.variant_known, rows.variant.astype(np.float64)
    c = a.config

    def job(
        name: str, e: Ensemble, p: np.ndarray, point: OperatingPoint | None, rand: bool
    ) -> StatisticsJob:
        return StatisticsJob(
            cache=cache / f"{VARIANT}__{name}.npz",
            p=p,
            u=e.u,
            labels=e.labels,
            blocks=e.blocks(bootstrap.block_steps),
            replicates=bootstrap.replicates,
            seed=bootstrap.seed,
            bins=c.calibration.ece_bins,
            point=point,
            random_seeds=a.seeds if rand else np.zeros(0, dtype=np.uint64),
        )

    jobs: dict[str, StatisticsJob] = {}
    for name, full in a.clean.items():
        e = subset(full, m, y)
        jobs[f"clean_{name}"] = job(f"clean_{name}", e, e.p, a.points[name], True)
        jobs[f"platt_{name}"] = job(
            f"platt_{name}", e, apply_platt(e.p, *a.platt[name]), None, False
        )
    for k, full in a.masked.items():
        e = subset(full, m, y)
        jobs[f"{c.ladder.arm}_k{k}"] = job(
            f"{c.ladder.arm}_k{k}", e, e.p, a.points[c.ladder.arm], False
        )
    return jobs


def abstention_full_check(a: AbstentionInputs, record: Mapping[str, Any]) -> list[str]:
    """Point values recomputed here on the full label, against the record's; the mismatches."""
    wrong = []
    names = {
        "ece_prior_corrected": "ece",
        "mean_p_prior_corrected": "mean_p",
        "auprc": "auprc",
        "aurc": "aurc",
        "aurc_random": "aurc_random",
        "coverage_at_operating_point": "coverage",
        "selective_risk_at_operating_point": "risk",
    }
    for name, e in a.clean.items():
        got = statistics(e.p, e.u, e.labels, a.config.calibration.ece_bins, a.points[name], a.seeds)
        platt = statistics(
            apply_platt(e.p, *a.platt[name]),
            e.u,
            e.labels,
            a.config.calibration.ece_bins,
            None,
            np.zeros(0, dtype=np.uint64),
        )
        held = record["part_a"][arm_label(name)]
        for key, stat in names.items():
            if abs(got[stat] - held[key]["value"]) > AGREEMENT:
                wrong.append(f"{name} {key}")
        for key, stat in (("ece_platt", "ece"), ("mean_p_platt", "mean_p")):
            if abs(platt[stat] - held[key]["value"]) > AGREEMENT:
                wrong.append(f"{name} {key}")
    return wrong


def abstention_outcome(
    a: AbstentionInputs, jobs: Mapping[str, StatisticsJob], record: Mapping[str, Any]
) -> dict[str, Any]:
    """ADR-0028's rows under the variant beside the record's, and each gate's rule applied."""
    b = a.config.bootstrap
    vectors: dict[str, dict[str, np.ndarray]] = {}
    points: dict[str, dict[str, float]] = {}
    for key, j in jobs.items():
        with np.load(j.cache) as loaded:
            vectors[key] = {n: loaded[n] for n in loaded.files}
        points[key] = statistics(j.p, j.u, j.labels, j.bins, j.point, j.random_seeds)

    def iv(key: str, stat: str) -> dict[str, Any]:
        return asdict(
            interval(points[key][stat], vectors[key][stat], b.confidence, b.max_discarded_share)
        )

    def pv(first: str, second: str, stat: str) -> Interval:
        return paired_interval(
            (points[first][stat], vectors[first][stat]),
            (points[second][stat], vectors[second][stat]),
            b.confidence,
            b.max_discarded_share,
        )

    rows: list[dict[str, Any]] = []
    gate_a: dict[str, Any] = {}
    shown = {
        "ece_prior_corrected": ("clean", "ece"),
        "mean_p_prior_corrected": ("clean", "mean_p"),
        "ece_platt": ("platt", "ece"),
        "mean_p_platt": ("platt", "mean_p"),
        "auprc": ("clean", "auprc"),
        "aurc": ("clean", "aurc"),
        "aurc_random": ("clean", "aurc_random"),
        "coverage_at_operating_point": ("clean", "coverage"),
        "selective_risk_at_operating_point": ("clean", "risk"),
    }
    for name in a.clean:
        label = arm_label(name)
        held = record["part_a"][label]
        rows.append(
            {
                "arm": label,
                "statistic": "base_rate",
                "original": {"value": held["base_rate"]},
                "variant": {"value": points[f"clean_{name}"]["base_rate"]},
            }
        )
        for key, (scenario, stat) in shown.items():
            rows.append(
                {
                    "arm": label,
                    "statistic": key,
                    "original": held[key],
                    "variant": iv(f"{scenario}_{name}", stat),
                }
            )
        delta = interval(
            points[f"clean_{name}"]["aurc_minus_random"],
            vectors[f"clean_{name}"]["aurc_minus_random"],
            b.confidence,
            b.max_discarded_share,
        )
        outcome = decide_gate_a(delta, a.config.gate_a)
        gate_a[label] = {
            "original": record["gate_a"][label],
            "variant": {"delta_aurc": asdict(delta), "outcome": outcome},
        }
    arm = a.config.ladder.arm
    k = a.config.gate_b.severity
    d_auprc = pv(f"{arm}_k{k}", f"clean_{arm}", "auprc")
    d_cov = pv(f"{arm}_k{k}", f"clean_{arm}", "coverage")
    d_risk = pv(f"{arm}_k{k}", f"clean_{arm}", "risk")
    gate_b = decide_gate_b(d_auprc, a.config.gate_b)
    h2 = decide_h2(
        gate_a[arm_label(arm)]["variant"]["outcome"], gate_b, d_cov, d_risk, a.config.h2_rule
    )
    ladder = []
    for held in record["ladder"]:
        severity = int(held["k"])
        key = f"clean_{arm}" if severity == 0 else f"{arm}_k{severity}"
        entry: dict[str, Any] = {"k": severity}
        for stat, name in (
            ("coverage", "coverage"),
            ("selective_risk", "risk"),
            ("auprc", "auprc"),
            ("ece", "ece"),
            ("mean_p", "mean_p"),
        ):
            entry[stat] = {"original": held[stat], "variant": iv(key, name)}
        entry["base_rate"] = points[key]["base_rate"]
        ladder.append(entry)
    return {
        "rows": rows,
        "gate_a": gate_a,
        "gate_b": {
            "original": {
                "delta_auprc": record["gate_b"]["delta_auprc"],
                "outcome": record["gate_b"]["outcome"],
            },
            "variant": {"delta_auprc": asdict(d_auprc), "outcome": gate_b},
        },
        "h2": {
            "original": {
                "delta_coverage": record["h2"]["delta_coverage"],
                "delta_selective_risk": record["h2"]["delta_selective_risk"],
                "verdict": record["h2"]["verdict"],
            },
            "variant": {
                "delta_coverage": asdict(d_cov),
                "delta_selective_risk": asdict(d_risk),
                "verdict": h2,
            },
        },
        "ladder": ladder,
        "operating_points": {n: asdict(p) for n, p in a.points.items()},
        "platt": {n: list(v) for n, v in a.platt.items()},
    }


# =====================================================================================
# Part B: persistence
# =====================================================================================


@dataclass(frozen=True)
class Persistence:
    """The four scores and what the report says about how they were built."""

    scores: dict[str, np.ndarray]
    uncapped: np.ndarray
    codes: list[dict[str, Any]]
    composition: dict[int, np.ndarray]
    starts: dict[str, np.ndarray]


def persistence(paths: ProjectPaths, config: ExploratoryConfig, rows: EvaluatedRows) -> Persistence:
    """Build P1-P4, P4's uncapped twin and the composition flags on the evaluated rows.

    Raises:
        ValueError: If the frozen code set is not the one the rule derives.
    """
    p = config.persistence
    look = p.window_hours * HOUR
    mixture = load_config(paths.repo_root / p.joint_mixture_config, JointMixtureConfig)
    stream_dir = (
        paths.data_root
        / "shards"
        / "joint"
        / f"joint_v{mixture.version}_{config_hash(mixture)}"
        / f"tel_status_{p.status_convention}"
    )
    starts: dict[str, np.ndarray] = {}
    stops: dict[str, np.ndarray] = {}
    tables = []
    p4 = np.zeros(rows.t.size, dtype=bool)
    p4_uncapped = np.zeros(rows.t.size, dtype=bool)
    for key in rows.keys:
        source = key.split("__")[0]
        labels_dir = paths.source_dir("cleaned", "telemetry", source) / "labels"
        events = pd.read_parquet(labels_dir / "events_narrow.parquet")
        stream = pd.read_parquet(labels_dir / "status_stream.parquet")
        tables.append(opening_codes(events, stream, p.opening_cause, p.stop_status, p.train_until))
        starts.update(
            by_turbine(events["turbine_id"].astype(str).to_numpy(), to_seconds(events["start_utc"]))
        )
        stops.update(flagged_stop_times(stream, p.codes, p.stop_status))
    derived = pd.concat(tables).groupby(["code", "message"], as_index=False)["events"].sum()
    if "<none>" in set(derived["code"]) or sorted(set(derived["code"]), key=int) != sorted(
        p.codes, key=int
    ):
        raise ValueError(
            f"the rule derives {sorted(set(derived['code']))}, the frozen set is {p.codes}"
        )
    for position, key in enumerate(rows.keys):
        source = key.split("__")[0]
        messages = messages_in_stream_order(paths, source, ["code", "provider_status"])[key]
        flags = (messages.columns["provider_status"].astype(str) == p.stop_status) & np.isin(
            messages.columns["code"].astype(str), p.codes
        )
        stream_tokens = np.memmap(stream_dir / f"{key}.bin", dtype=np.uint16, mode="r")
        here = rows.which == position
        capped, uncapped = model_window_flags(
            stream_tokens,
            messages.steps,
            flags,
            rows.ends[here],
            p.context_steps,
            p.context_tokens,
            p.tokens_per_step,
        )
        p4[here], p4_uncapped[here] = capped, uncapped
    scores = {
        "P1": starts_within(rows.t, rows.turbines, starts, look).astype(np.float64),
        "P2": -hours_since_last(rows.t, rows.turbines, starts, p.cap_hours),
        "P3": starts_within(rows.t, rows.turbines, stops, look).astype(np.float64),
        "P4": p4.astype(np.float64),
    }
    composition = {
        h: starts_within(rows.t, rows.turbines, starts, h * HOUR) for h in p.composition_hours
    }
    codes = [
        {"code": str(r.code), "message": str(r.message), "training_events": int(r.events)}
        for r in derived.assign(n=derived["code"].astype(int)).sort_values("n").itertuples()
    ]
    return Persistence(
        scores=scores,
        uncapped=p4_uncapped,
        codes=codes,
        composition=composition,
        starts=starts,
    )


def shares(flag: np.ndarray, truth: np.ndarray) -> dict[str, Any]:
    """The flag's share among positives and among negatives, with counts."""
    pos, neg = truth, ~truth
    return {
        "positives": int(pos.sum()),
        "positives_flagged": int((flag & pos).sum()),
        "positive_share": float((flag & pos).sum() / max(pos.sum(), 1)),
        "negatives": int(neg.sum()),
        "negatives_flagged": int((flag & neg).sum()),
        "negative_share": float((flag & neg).sum() / max(neg.sum(), 1)),
    }


# =====================================================================================
# the run
# =====================================================================================


def _json(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def rule_rows(
    h1: Sequence[dict[str, Any]],
    readout: Sequence[dict[str, Any]],
    ablation: Sequence[dict[str, Any]],
    records: Mapping[str, Mapping[str, Any]],
    layouts: Mapping[str, Any],
    abstention: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Each registered gate and rule, applied to the variant's quantities, beside the record's."""
    out: list[dict[str, Any]] = []
    b = layouts["bootstrap"]
    seeds = layouts["seeds"]

    def add(rule: str, record: str, variant: str, why: str) -> None:
        out.append(
            {
                "rule": rule,
                "record": record,
                "variant": variant,
                "same": record == variant,
                "variant_reason": why,
            }
        )

    g = layouts["h1_rule"]
    h1v = decide_h1(
        {s: _delta(h1, "B1", f"Δ(joint − tel_only) seed {s}") for s in seeds},
        g.smallest_effect,
        g.supported_lower_bound_above,
        g.supported_median_above,
        g.refuted_upper_bound_below,
        b.max_discarded_share,
    )
    add("ADR-0025 §5, H1 (B1)", records["h1"]["verdict"]["verdict"], h1v.verdict, h1v.reason)

    gate_cfg = layouts["readout_gate"]
    gate = decide_random_init_gate(
        {
            f"joint{j}_rand{k}": _delta(readout, "G", f"Δ((d) joint {j} − (d) random {k})")
            for j in seeds
            for k in seeds
        },
        gate_cfg.comparisons,
        gate_cfg.lower_bound_above,
        b.max_discarded_share,
    )
    add(
        "ADR-0026 §4, random-init gate on the instrument",
        "PASS" if records["readout"]["gate"]["passed"] else "FAIL",
        "PASS" if gate.passed else "FAIL",
        gate.reason,
    )
    r = layouts["readout_rule"]
    measured = decide_h1(
        {s: _delta(readout, "B1", f"Δ(joint (d) − tel_only (a)) seed {s}") for s in seeds},
        r.smallest_effect,
        r.supported_lower_bound_above,
        r.supported_median_above,
        r.refuted_upper_bound_below,
        b.max_discarded_share,
    )
    add(
        "ADR-0026 §4, H1′ (B1)",
        records["readout"]["verdict"]["verdict"],
        measured.verdict if gate.passed else "NOT EVALUABLE",
        measured.reason,
    )

    arule, igate = layouts["ablation_rule"], layouts["ablation_gate"]
    for arm in layouts["arms"]:
        pairs = {
            f"seed{j}_rand{k}": _delta(ablation, f"G {arm}", f"Δ({arm} {j} − random {k})")
            for j in seeds
            for k in seeds
        }
        ag = decide_random_init_gate(
            pairs, igate.comparisons, igate.lower_bound_above, b.max_discarded_share
        )
        held = records["ablation"]["gates"][arm]
        add(
            f"ADR-0027 §4, instrument gate, {arm}",
            "PASS" if held["passed"] else "FAIL",
            "PASS" if ag.passed else "FAIL",
            ag.reason,
        )
        av = decide_ablation(
            {s: _delta(ablation, f"B1 {arm}", f"Δ({arm} − joint (d)) seed {s}") for s in seeds},
            arule,
            b.max_discarded_share,
        )
        add(
            f"ADR-0027 §5, {arm} (B1)",
            records["ablation"]["verdicts"][arm]["verdict"],
            av.verdict if ag.passed else "NOT EVALUABLE",
            av.reason,
        )
        add(
            f"ADR-0027 §5, {arm} (B1), the rule as measured (reported beside a failed gate)",
            records["ablation"]["measured_rule"][arm]["verdict"],
            av.verdict,
            av.reason,
        )
        rep = decide_h1(
            {s: _delta(ablation, f"B2 {arm}", f"Δ({arm} − tel_only (a)) seed {s}") for s in seeds},
            r.smallest_effect,
            r.supported_lower_bound_above,
            r.supported_median_above,
            r.refuted_upper_bound_below,
            b.max_discarded_share,
        )
        add(
            f"ADR-0027 B2, H1′'s rule replicated, {arm} (reported)",
            records["ablation"]["B2_rule"][arm]["verdict"],
            rep.verdict,
            rep.reason,
        )

    for label, entry in abstention["gate_a"].items():
        add(
            f"ADR-0028 §2, Gate A, {label}",
            entry["original"]["outcome"],
            entry["variant"]["outcome"],
            "Δ AURC upper bound against 0",
        )
    add(
        "ADR-0028 §3, Gate B (k = 8)",
        abstention["gate_b"]["original"]["outcome"],
        abstention["gate_b"]["variant"]["outcome"],
        "Δ AUPRC upper bound against 0",
    )
    add(
        "ADR-0028 §3, H2",
        abstention["h2"]["original"]["verdict"],
        abstention["h2"]["variant"]["verdict"],
        "Δcoverage and Δselective risk against the rule",
    )
    return out


def run_exploratory(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """ADR-0029: Part A and Part B, written to ``reports/data/exploratory_v0_<date>.md/.json``.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/eval/exploratory_v0.yaml``.

    Returns:
        The report and its JSON record.

    Raises:
        ValueError: If any check made before reporting fails.
    """
    started = time.perf_counter()
    clock: dict[str, float] = {}
    config = load_config(config_path, ExploratoryConfig)
    root, b = paths.repo_root, config.bootstrap
    axis = load_config(root / config.axis_config, AxisGateConfig)
    shards = ShardSet.load(root / axis.shards)
    out = paths.checkpoints_dir / f"exploratory_v{config.version}_{config_hash(config)}"
    rep_dir = out / "replicates"
    records = {k: _json(root / v) for k, v in config.recorded.model_dump().items()}

    # -- the layouts, and every scores file the four records read ----------------------------
    h1 = scoring_layout(paths, root / config.h1_gate_config)
    readout = readout_layout(paths, root / config.readout_config)
    ablation = ablation_layout(paths, root / config.ablation_config)
    files = {
        "h1": h1_files(h1),
        "readout": readout_files(paths, readout),
        "ablation": ablation_files(paths, ablation),
    }
    reference = ScoredWindows.load(files["h1"]["tel_only_1"])
    if (reference.labels.size, int(reference.labels.sum())) != (config.windows, config.positives):
        raise ValueError("the scored rows are not the registered evaluated set")

    # -- the evaluated rows and the reconciliation -----------------------------------------------
    tick = time.perf_counter()
    rows = evaluated_rows(
        paths,
        shards,
        list(axis.axes.temporal.shard_keys),
        reference,
        config.label,
        config.variant_label,
        config.stride,
    )
    p = config.persistence
    manifest = json.loads((shards.root / "manifest.json").read_text(encoding="utf-8"))
    reconciliation = reconcile(
        paths,
        root / str(manifest["telemetry_config"]),
        rows,
        p.window_hours * HOUR // STEP_SECONDS,
        p.stop_status,
        p.opening_cause,
    )
    if any(reconciliation["relabel_mismatches"].values()):
        raise ValueError(
            f"labels re-derived from events differ: {reconciliation['relabel_mismatches']}"
        )
    clock["rows_and_reconciliation"] = time.perf_counter() - tick

    # -- scorers and row sets ----------------------------------------------------------------
    vectors = Vectors(rep_dir, b)
    ids: dict[str, dict[str, str]] = {
        family: {name: vectors.add_file(path, reference) for name, path in named.items()}
        for family, named in files.items()
    }
    with np.load(h1.out_dir / "status_strata.npz") as data:
        normalized = data["has_status"].astype(bool)
    with np.load(ablation.out_dir / "raw_status_strata.npz") as data:
        raw = data["has_status"].astype(bool)
    identical = bool(np.array_equal(normalized, raw))
    strata = {
        "pooled": np.ones(rows.t.size, dtype=bool),
        "has_status": normalized,
        "no_status": ~normalized,
    }
    if not identical:
        strata.update({"has_status_raw": raw, "no_status_raw": ~raw})
    for labels in (FULL, VARIANT):
        for name, mask in strata.items():
            s = row_set(labels, name, mask, rows, b.block_steps)
            vectors.sets[s.name] = s

    conventions = {arm.name: arm.status_convention for arm in ablation.mixture.arms}

    def where_for(arm: str, where: str) -> str:
        return where if conventions[arm] == "normalized" or identical else f"{where}_raw"

    seeds = list(h1.gate.comparison.seeds)
    arms = list(ablation.gate.comparison.arms)
    families = {
        "h1": h1_rows(ids["h1"], seeds, list(h1.patterns)),
        "readout": readout_rows(ids["readout"], list(readout.config.rule.seeds)),
        "ablation": ablation_rows(
            ids["ablation"],
            seeds,
            arms,
            {a: random_prefix(ablation.gate, a) for a in arms},
            where_for,
        ),
    }
    wrong = [w for f, rs in families.items() for w in check_full_points(rs, records[f], vectors)]
    if wrong:
        raise ValueError(f"full-label points differ from the record: {wrong}")
    for rs in families.values():
        for row in rs:
            for scorer in (row.first, row.second):
                if scorer:
                    vectors.want(f"{VARIANT}__{row.stratum}", scorer)

    # -- ADR-0028 -----------------------------------------------------------------------------
    absten = abstention_inputs(paths, root / config.abstention_config, rows)
    wrong = abstention_full_check(absten, records["abstention"])
    if wrong:
        raise ValueError(f"ADR-0028 full-label points differ from the record: {wrong}")
    stat_jobs = abstention_jobs(absten, rows, out / "abstention", b)

    # -- Part B ----------------------------------------------------------------------------------
    tick = time.perf_counter()
    built = persistence(paths, config, rows)
    clock["persistence_features"] = time.perf_counter() - tick
    vectors.scores.update(built.scores)
    ensemble = absten.clean[absten.config.ladder.arm]
    vectors.scores["d_ensemble"] = ensemble.p
    d_ids = [ids["readout"][f"d_joint_{s}"] for s in seeds]
    comparators = {
        **{f"joint (d) seed {s}": ids["readout"][f"d_joint_{s}"] for s in seeds},
        "(d) ensemble": "d_ensemble",
        "status-only classifier": ids["readout"]["status_only_bag"],
    }
    for labels in (FULL, VARIANT):
        for scorer in [*built.scores, *comparators.values()]:
            vectors.want(f"{labels}__pooled", scorer)

    # -- the bootstrap: the random-reference scenarios first, they take longest ------------------
    tick = time.perf_counter()
    pending_stats = [j for j in stat_jobs.values() if not j.cache.is_file()]
    pending_stats.sort(key=lambda j: -j.random_seeds.size)
    pending: list[AuprcJob | StatisticsJob] = [*pending_stats, *vectors.jobs()]
    workers = MAX_BOOTSTRAP_WORKERS
    ran = run_pool(pending, workers)
    clock["bootstrap"] = time.perf_counter() - tick
    # The compute time lives beside the vectors, so a resumed invocation still reports it.
    timing = out / "bootstrap_timing.json"
    if ran:
        write_json(
            timing,
            {
                "bootstrap_seconds": clock["bootstrap"],
                "jobs": ran,
                "workers": min(len(pending), (os.cpu_count() or 2) - 2, workers),
                "finished_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            },
        )
    computed = _json(timing) if timing.is_file() else {}

    # -- the identity check on the estimator ----------------------------------------------------
    # The draws are sequential from one seed, so a shorter run's replicates are the cached
    # vector's first ones; the full run compares all 10,000.
    cached_dir = readout.out_dir / "replicates"
    against = {
        f"joint (d) seed {seed}": (f"pooled__d_joint_{seed}.npz", scorer)
        for seed, scorer in zip(seeds, d_ids, strict=True)
    }
    against["status-only classifier"] = (
        "pooled__status_only_bag.npz",
        ids["readout"]["status_only_bag"],
    )
    identity = {}
    for name, (file, scorer) in against.items():
        mine = vectors.vector(f"{FULL}__pooled", scorer)[0]
        with np.load(cached_dir / file) as data:
            identity[name] = bool(np.array_equal(data["values"][: mine.size], mine, equal_nan=True))
    if not all(identity.values()):
        raise ValueError(f"the estimator does not reproduce F7'-3's cached vectors: {identity}")

    # -- Part A, assembled ---------------------------------------------------------------------
    part_a = {f: evaluate_rows(rs, records[f], vectors) for f, rs in families.items()}
    abstention = abstention_outcome(absten, stat_jobs, records["abstention"])
    rules = rule_rows(
        part_a["h1"],
        part_a["readout"],
        part_a["ablation"],
        records,
        {
            "bootstrap": b,
            "seeds": seeds,
            "h1_rule": h1.gate.rule,
            "readout_gate": readout.config.random_init_gate,
            "readout_rule": readout.config.rule,
            "ablation_rule": ablation.gate.rule,
            "ablation_gate": ablation.gate.instrument_gate,
            "arms": arms,
        },
        abstention,
    )

    # -- Part B, assembled ---------------------------------------------------------------------
    part_b: dict[str, Any] = {
        "codes": built.codes,
        "scores": {},
        "deltas": {},
        "prevalence": {},
        "comparators": {},
    }
    for labels in (FULL, VARIANT):
        where = f"{labels}__pooled"
        s = vectors.sets[where]
        part_b["scores"][labels] = {n: _slim_single(vectors.single(where, n)) for n in built.scores}
        part_b["comparators"][labels] = {
            n: _slim_single(vectors.single(where, c)) for n, c in comparators.items()
        }
        part_b["deltas"][labels] = {
            n: {
                c: _slim_delta(asdict(vectors.paired(where, n, cid)))
                for c, cid in comparators.items()
            }
            for n in built.scores
        }
        part_b["deltas"][labels]["P3"]["P4"] = _slim_delta(
            asdict(vectors.paired(where, "P3", "P4"))
        )
        truth = s.labels > 0.5
        part_b["prevalence"][labels] = {
            n: shares(built.scores[n][s.mask] > 0.5, truth) for n in ("P1", "P3", "P4")
        }
        part_b["prevalence"][labels]["P2_capped"] = shares(
            built.scores["P2"][s.mask] <= -p.cap_hours, truth
        )
    p3, p4 = built.scores["P3"] > 0.5, built.scores["P4"] > 0.5
    # An event is dated by its first step; one starting exactly at t is the only P1 input
    # whose qualifying duration can depend on steps after t. Measured, not removed.
    look = p.window_hours * HOUR
    at_t = starts_within(rows.t, rows.turbines, built.starts, 1)
    earlier = starts_within(rows.t - STEP_SECONDS, rows.turbines, built.starts, look - STEP_SECONDS)
    only_at_t = (built.scores["P1"] > 0.5) & ~earlier
    part_b["p1_start_at_t"] = {
        "windows_with_a_start_at_t": int(at_t.sum()),
        "p1_only_through_it": int(only_at_t.sum()),
        "p1_only_through_it_positive": int((only_at_t & rows.full).sum()),
        "p1_auprc_without_it_full_label": average_precision(
            earlier.astype(np.float64), rows.full.astype(np.float64)
        ),
    }
    part_b["gap"] = {
        "p3_not_p4": int((p3 & ~p4).sum()),
        "p4_not_p3": int((p4 & ~p3).sum()),
        "dropped_absent_step": int((p3 & ~built.uncapped).sum()),
        "cut_by_token_cap": int((built.uncapped & ~p4).sum()),
        "uncapped_not_p3": int((built.uncapped & ~p3).sum()),
    }
    composition: dict[str, Any] = {}
    for labels in (FULL, VARIANT):
        known = np.ones(rows.t.size, bool) if labels == FULL else rows.variant_known
        truth = rows.full if labels == FULL else rows.variant
        composition[labels] = {}
        for site, mask in [
            *((k.split("__")[0], rows.which == i) for i, k in enumerate(rows.keys)),
            ("pooled", np.ones(rows.t.size, bool)),
        ]:
            chosen = mask & known
            composition[labels][site] = {
                f"{h}h": shares(built.composition[h][chosen], truth[chosen])
                for h in p.composition_hours
            }
    part_b["composition"] = composition

    clock["total"] = time.perf_counter() - started
    payload: dict[str, Any] = {
        "adr": "ADR-0029",
        "status": STATUS,
        "registered_in": config.registered_in,
        "config": config_path.relative_to(root).as_posix(),
        "config_hash": config_hash(config),
        "recorded": config.recorded.model_dump(),
        "bootstrap": b.model_dump(),
        "row_sets": {n: s.describe() for n, s in vectors.sets.items()},
        "strata_identical": identical,
        "reconciliation": reconciliation,
        "identity_checks": {
            "full_label_points_equal_record": True,
            "adr_0028_full_label_points_equal_record": True,
            "labels_rederived_from_events_equal_index": True,
            "vectors_equal_f7_prime_cache": identity,
        },
        "part_a": {**part_a, "abstention": abstention},
        "rules": rules,
        "part_b": part_b,
        "runtime": {
            "seconds": clock,
            "jobs_run": ran,
            "jobs_resumed": len(vectors.wanted) + len(stat_jobs) - ran,
            "workers": min(len(pending), (os.cpu_count() or 2) - 2, workers) if pending else 0,
            "bootstrap_computed": computed,
        },
        "generated_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "git_sha": git_sha(root),
    }
    payload = json.loads(json.dumps(payload))
    stem = f"exploratory_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    record = paths.data_reports_dir / f"{stem}.json"
    write_json(record, payload)
    report.write_text(render_report(payload), encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record)
    return report, record


# =====================================================================================
# the report
# =====================================================================================


def _f(value: float, digits: int = 4) -> str:
    return "nan" if value is None or math.isnan(value) else f"{value:.{digits}f}"


def _s(value: float, digits: int = 4) -> str:
    return "nan" if value is None or math.isnan(value) else f"{value:+.{digits}f}"


def _ci(d: Mapping[str, Any], key: str = "auprc") -> str:
    return f"{_f(d[key])} [{_f(d['low'])}, {_f(d['high'])}]"


def _dci(d: Mapping[str, Any], key: str = "delta") -> str:
    return f"{_s(d[key])} [{_s(d['low'])}, {_s(d['high'])}]"


def _pct(x: float) -> str:
    return f"{100 * x:.2f}%"


def _ordered(entries: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Rows grouped by section (gates first), then stratum; seeds keep their order."""
    rank = {"pooled": 0, "has_status": 1, "no_status": 2}

    def key(e: Mapping[str, Any]) -> tuple[int, str, int]:
        return (
            0 if e["section"].startswith("G") else 1,
            e["section"],
            rank.get(e["stratum"].removesuffix("_raw"), 3),
        )

    return sorted(entries, key=key)


def _family_tables(entries: Sequence[Mapping[str, Any]]) -> list[str]:
    singles = _ordered([e for e in entries if e["kind"] == "auprc"])
    deltas = _ordered([e for e in entries if e["kind"] == "delta"])
    out = []
    if singles:
        out.append(
            table(
                [
                    "section",
                    "read",
                    "stratum",
                    "original AUPRC [95%]",
                    "base",
                    "lift",
                    "variant AUPRC [95%]",
                    "base",
                    "lift",
                    "variant n / pos",
                ],
                [
                    [
                        e["section"],
                        e["row"],
                        e["stratum"],
                        _ci(e["original"]),
                        _f(e["original"]["base_rate"]),
                        _f(e["original"]["lift"], 2),
                        _ci(e["variant"]),
                        _f(e["variant"]["base_rate"]),
                        _f(e["variant"]["lift"], 2),
                        f"{e['variant']['windows']:,} / {e['variant']['positives']:,}",
                    ]
                    for e in singles
                ],
            )
        )
    if deltas:
        out.append(
            table(
                [
                    "section",
                    "paired Δ",
                    "stratum",
                    "original Δ [95%]",
                    "variant Δ [95%]",
                    "variant discarded",
                ],
                [
                    [
                        e["section"],
                        e["row"],
                        e["stratum"],
                        _dci(e["original"]),
                        _dci(e["variant"]),
                        e["variant"]["discarded"],
                    ]
                    for e in deltas
                ],
            )
        )
    return out


def render_report(payload: Mapping[str, Any]) -> str:
    """The Markdown report, rendered from the JSON record alone."""
    rec = payload["reconciliation"]
    rt = payload["runtime"]
    lines = [
        "# ADR-0029: ADR-0009 compliance and persistence baselines (EXPLORATORY)\n",
        kv_table(
            {
                "status": payload["status"],
                "decision record": "docs/DECISIONS.md, ADR-0029",
                "registered in": payload["registered_in"],
                f"configuration {payload['config']}": f"hash {payload['config_hash']}",
                "records read (original column)": ", ".join(payload["recorded"].values()),
                "estimator": (
                    f"{payload['bootstrap']['block_steps']}-step blocks within each shard, "
                    f"{payload['bootstrap']['replicates']:,} replicates, seed "
                    f"{payload['bootstrap']['seed']}, {payload['bootstrap']['confidence']:.0%}, "
                    f"discard rule {payload['bootstrap']['max_discarded_share']:.0%}"
                ),
                "bootstrap, when computed": (
                    f"{rt['bootstrap_computed']['bootstrap_seconds'] / 60:.1f} min for "
                    f"{rt['bootstrap_computed']['jobs']} jobs on "
                    f"{rt['bootstrap_computed']['workers']} worker processes, finished "
                    f"{rt['bootstrap_computed']['finished_utc']}"
                    if rt["bootstrap_computed"]
                    else "not recorded"
                ),
                "this invocation": (
                    f"{rt['seconds']['total'] / 60:.1f} min; {rt['jobs_run']} jobs computed, "
                    f"{rt['jobs_resumed']} read from the cache"
                ),
                "generated (UTC)": payload["generated_utc"],
                "git_sha": payload["git_sha"],
                "generated by": "faultline model exploratory",
            }
        ),
        "\n**Nothing below is a verdict.** Where a registered rule is applied to the variant's "
        "numbers, the result is a statement of what that rule would return; the record's "
        "verdicts stand as written (ADR-0029).\n",
        "## A0. The evaluated set and the variant label\n",
        f"The saved scores cover **{rec['evaluated_windows']:,}** windows "
        f"({rec['evaluated_positives']:,} positive). The variant label "
        f"(`narrow_within_24h_without`) knows **{rec['variant_known']:,}** of them "
        f"({rec['variant_positives']:,} positive). **{rec['unjoinable']}** evaluated windows "
        "could not be joined to the window index. The join was checked row by row on end step, "
        "shard and full label. Both labels, re-derived from the event table and the record's "
        "coverage, equal the index on every evaluated window (mismatches: "
        f"{', '.join(f'{k} {v}' for k, v in rec['relabel_mismatches'].items())}).\n",
        f"**The {len(rec['unknown'])} windows the variant does not know.** Reason: "
        f"{rec['reason']}.\n",
        table(
            [
                "turbine",
                "end step",
                "t (UTC)",
                "full label",
                "events in (t, t + 24 h]",
                "horizon steps in record",
                "record ends",
            ],
            [
                [
                    u["turbine"],
                    u["end_step"],
                    u["end_utc"],
                    u["full_label"],
                    "; ".join(
                        f"{e['start_utc']} ({e['opened_by']})" for e in u["events_in_horizon"]
                    ),
                    f"{u['horizon_steps_in_record']} of {u['horizon_steps']}",
                    u["last_recorded_step_utc"],
                ]
                for u in rec["unknown"]
            ],
        ),
        "\n",
        table(
            ["row set", "windows", "positives", "base rate", "blocks", "positive blocks"],
            [
                [
                    n,
                    d["windows"],
                    d["positives"],
                    _f(d["base_rate"]),
                    d["blocks"],
                    d["positive_blocks"],
                ]
                for n, d in payload["row_sets"].items()
            ],
        ),
        "\n**Checks before reporting.** "
        + "; ".join(f"{k}: {v}" for k, v in payload["identity_checks"].items())
        + ".\n",
        "## A1. What each registered rule would return under the variant\n",
        table(
            ["registered gate or rule", "record", "under the variant", "same"],
            [[r["rule"], r["record"], r["variant"], r["same"]] for r in payload["rules"]],
        ),
        "\n",
        table(
            ["registered gate or rule", "why, under the variant"],
            [[r["rule"], r["variant_reason"]] for r in payload["rules"]],
        ),
    ]
    titles = {
        "h1": "A2. ADR-0025 (H1), the (a) read-outs",
        "readout": "A3. ADR-0026 (H1′), the read-outs",
        "ablation": "A4. ADR-0027, the ablations",
    }
    for family, title in titles.items():
        lines.append(f"\n## {title}\n")
        lines += _family_tables(payload["part_a"][family])
    ab = payload["part_a"]["abstention"]
    lines += [
        "\n## A5. ADR-0028: calibration, abstention and H2\n",
        "τ, κ, the margin cut-off and Platt's (a, b) are the validation fit of "
        "`reports/data/abstention_operating_points_v0.json`, unchanged.\n",
        table(
            ["arm", "statistic", "original [95%]", "variant [95%]"],
            [
                [
                    r["arm"],
                    r["statistic"],
                    _f(r["original"]["value"])
                    if "low" not in r["original"]
                    else _ci(r["original"], "value"),
                    _f(r["variant"]["value"])
                    if "low" not in r["variant"]
                    else _ci(r["variant"], "value"),
                ]
                for r in ab["rows"]
            ],
        ),
        "\n",
        table(
            [
                "quantity",
                "original Δ [95%]",
                "variant Δ [95%]",
                "original outcome",
                "variant outcome",
            ],
            [
                *[
                    [
                        f"Gate A Δ AURC, {k}",
                        _dci(v["original"]["delta_aurc"], "value"),
                        _dci(v["variant"]["delta_aurc"], "value"),
                        v["original"]["outcome"],
                        v["variant"]["outcome"],
                    ]
                    for k, v in ab["gate_a"].items()
                ],
                [
                    "Gate B Δ AUPRC (k = 8 − clean)",
                    _dci(ab["gate_b"]["original"]["delta_auprc"], "value"),
                    _dci(ab["gate_b"]["variant"]["delta_auprc"], "value"),
                    ab["gate_b"]["original"]["outcome"],
                    ab["gate_b"]["variant"]["outcome"],
                ],
                [
                    "H2 Δcoverage",
                    _dci(ab["h2"]["original"]["delta_coverage"], "value"),
                    _dci(ab["h2"]["variant"]["delta_coverage"], "value"),
                    ab["h2"]["original"]["verdict"],
                    ab["h2"]["variant"]["verdict"],
                ],
                [
                    "H2 Δselective risk",
                    _dci(ab["h2"]["original"]["delta_selective_risk"], "value"),
                    _dci(ab["h2"]["variant"]["delta_selective_risk"], "value"),
                    ab["h2"]["original"]["verdict"],
                    ab["h2"]["variant"]["verdict"],
                ],
            ],
        ),
        "\n",
        table(
            [
                "k",
                "coverage (orig → variant)",
                "selective risk",
                "AUPRC",
                "ECE",
                "mean p",
                "variant base rate",
            ],
            [
                [
                    e["k"],
                    *[
                        f"{_f(e[stat]['original']['value'])} → {_f(e[stat]['variant']['value'])}"
                        for stat in ("coverage", "selective_risk", "auprc", "ece", "mean_p")
                    ],
                    _f(e["base_rate"]),
                ]
                for e in ab["ladder"]
            ],
        ),
    ]
    pb = payload["part_b"]
    lines += [
        "\n## B1. Persistence baselines\n",
        "P1: a narrow event of the turbine started in (t − 24 h, t]. P2: −hours since the last "
        "narrow event start, capped at 720 h. P3: a provider `Stop` row attached in "
        "(t − 24 h, t] whose code is in the frozen set. P4: P3 read only from the messages in "
        "the model's R0 window. P1 and P2 read every narrow event, anemometer-defect events "
        "included; the scores are the same under both labels.\n",
        "An event is dated by its first step, so one starting exactly at t is the only P1 input "
        "whose 60-second qualification can rest on steps after t. "
        f"{pb['p1_start_at_t']['windows_with_a_start_at_t']:,} windows have an event starting "
        f"at t; P1 is set only through it on {pb['p1_start_at_t']['p1_only_through_it']:,} "
        f"({pb['p1_start_at_t']['p1_only_through_it_positive']:,} positive). Without them P1 "
        f"reads {_f(pb['p1_start_at_t']['p1_auprc_without_it_full_label'])} on the full "
        "label.\n",
    ]
    for labels in (FULL, VARIANT):
        lines += [
            f"\n**{labels} label.**\n",
            table(
                ["score", "AUPRC [95%]", "base", "lift", "discarded"],
                [
                    *[
                        [n, _ci(v), _f(v["base_rate"]), _f(v["lift"], 2), v["discarded"]]
                        for n, v in pb["scores"][labels].items()
                    ],
                    *[
                        [n, _ci(v), _f(v["base_rate"]), _f(v["lift"], 2), v["discarded"]]
                        for n, v in pb["comparators"][labels].items()
                    ],
                ],
            ),
            "\n",
            table(
                ["score", *pb["deltas"][labels]["P1"].keys()],
                [
                    [
                        f"Δ({n} − ·)",
                        *[_dci(pb["deltas"][labels][n][c]) for c in pb["deltas"][labels]["P1"]],
                    ]
                    for n in ("P1", "P2", "P3", "P4")
                ],
            ),
            "\n",
            table(
                ["flag", "positives flagged", "share", "negatives flagged", "share"],
                [
                    [
                        n,
                        f"{v['positives_flagged']:,} / {v['positives']:,}",
                        _pct(v["positive_share"]),
                        f"{v['negatives_flagged']:,} / {v['negatives']:,}",
                        _pct(v["negative_share"]),
                    ]
                    for n, v in pb["prevalence"][labels].items()
                ],
            ),
        ]
    gap = pb["gap"]
    lines += [
        "\n## B2. What the input pipeline loses: P3 − P4\n",
        table(
            ["label", "Δ(P3 − P4) [95%]"],
            [[labels, _dci(pb["deltas"][labels]["P3"]["P4"])] for labels in (FULL, VARIANT)],
        ),
        "\n",
        table(
            ["windows", "count"],
            [
                ["P3 set, P4 not", gap["p3_not_p4"]],
                [
                    "of which the row's step is absent from the final rows",
                    gap["dropped_absent_step"],
                ],
                ["of which the message is cut by the 2,048-token cap", gap["cut_by_token_cap"]],
                ["P4 set, P3 not", gap["p4_not_p3"]],
                ["uncapped model window set, P3 not", gap["uncapped_not_p3"]],
            ],
        ),
        "\n## B3. Composition: a narrow event started in the preceding 6 h and 24 h\n",
    ]
    comp = pb["composition"]
    lines.append(
        table(
            ["label", "site", "look-back", "positives", "share", "negatives", "share"],
            [
                [
                    labels,
                    site,
                    h,
                    f"{v['positives_flagged']:,} / {v['positives']:,}",
                    _pct(v["positive_share"]),
                    f"{v['negatives_flagged']:,} / {v['negatives']:,}",
                    _pct(v["negative_share"]),
                ]
                for labels in (FULL, VARIANT)
                for site, per in comp[labels].items()
                for h, v in per.items()
            ],
        )
    )
    lines += [
        "\n## B4. The frozen code set (ADR-0029 §2)\n",
        table(
            ["code", "message", "training events opened"],
            [[c["code"], c["message"], c["training_events"]] for c in pb["codes"]],
        ),
        "",
    ]
    return "\n".join(lines).rstrip("\n") + "\n"
