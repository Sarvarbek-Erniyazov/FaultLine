"""ADR-0022's F6-0 addendum: two reported-only diagnostics that attribute the CARE null.

F5 found CARE at chance on every seed, farm and checkpoint. Two readings predict that equally: the
probe does not transfer across OEMs, or the CARE missing-channel pattern lies outside everything
the backbone was pretrained on. The addendum registers two diagnostics that separate them:

- **F6-0a, masking transfer.** The three ``tel_only`` final-step probes scored on the training-site
  temporal split with each CARE farm's absent core channels imposed as ``<nan>``.
- **F6-0b, bag of tokens on CARE.** The G2 comparator, unchanged, scored on the CARE stride-12 set.

The configuration classes were written in the registration commit (``ad1b7a3``), before any code
that scores either diagnostic existed. The scoring code below was added once the user authorised
the run. ``configs/eval/care_attribution_v*.yaml`` is what it reads.

**How an absent CARE channel reaches the stream, and so how it is imposed here.** No adapter
writes ``<nan>`` itself. A CARE farm's absent core channel is a column the farm's frame does not
carry. ``QuantileBinTokenizer.transform`` emits ``MISSING_BIN`` for it on every row, and
``JointVocab.encode_steps`` maps that to ``special("<nan>")`` at the channel's fixed position in
the step: ``1 + channel_index``, after ``<sep>``. The stream carries no channel tokens; a token's
position in the step names its channel. The masking below therefore overwrites exactly those
positions of every step with the shard manifest's ``<nan>`` id. Nothing else changes: not
``<sep>``, not the other channels, not the window boundaries. Before scoring, the run checks
that masking a real CARE window of each farm with that farm's pattern leaves it unchanged.

**Resume is per artefact.** Each scoring checks for its own ``.npz`` and skips it. Each row's
bootstrap is written to its own JSON as it completes, and a later invocation reads it back.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from pydantic import Field

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.evaluation.axis_gate import (
    CARE_FARMS,
    AxisGateConfig,
    ProbeCheckpoints,
    care_window_farms,
    check_care_counts,
    index_counts,
    index_rows,
    masked_interval,
    read_probes,
    window_steps,
)
from faultline.evaluation.bag_of_tokens import BagOfTokens, BagOfTokensConfig
from faultline.evaluation.bootstrap import AuprcInterval, DeltaInterval
from faultline.evaluation.checkpoint_selection import FIXED_FINAL
from faultline.evaluation.gate_check import BootstrapConfig, GateCheckConfig
from faultline.evaluation.ladder import SplitEval, build_split
from faultline.evaluation.paired_control import (
    load_saved_probe,
    paired_rows,
    save_split_scores,
    score_saved_probe,
)
from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.seed_replication import SeedReplicationConfig
from faultline.evaluation.variance_probe import ProbeInputs, open_probe_inputs
from faultline.logging_utils import get_logger
from faultline.model.checkpoints import read_checkpoint
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.loop import risk_logits
from faultline.training.windows import Batch, ShardSet, WindowSampler

logger = get_logger(__name__)


class MaskingConfig(StrictModel):
    """F6-0a: each CARE farm's absent core channels, imposed on the temporal split.

    Attributes:
        axis: The split scored, ``temporal`` in the axis configuration.
        seed_replication_config: The F3 configuration naming the probes and their unmasked reads.
        windows: Windows at the registered stride.
        positives: Positive windows at that stride.
        base_rate: The scored set's own positive rate, to four decimals.
        seeds_required: Seeds of three on which either registered reading must hold.
        patterns: Per farm, the core channels emitted as ``<nan>`` on every step.
    """

    axis: str
    seed_replication_config: str
    windows: int = Field(gt=0)
    positives: int = Field(gt=0)
    base_rate: float = Field(gt=0.0, lt=1.0)
    seeds_required: int = Field(gt=0)
    patterns: dict[str, list[str]] = Field(min_length=1)


class BagOfTokensTransferConfig(StrictModel):
    """F6-0b: the G2 comparator, not refit, scored on the CARE evaluation set.

    Attributes:
        axis: The set scored, ``care`` in the axis configuration.
        config: The comparator's training configuration (ADR-0024 §6).
        refit: Whether the comparator is refit; registered false.
        windows: Windows at the registered stride.
        positives: Positive windows at that stride.
        base_rate: The scored set's own positive rate, to six decimals.
        per_farm: Whether per-farm rows are reported beside the pooled one.
    """

    axis: str
    config: str
    refit: bool
    windows: int = Field(gt=0)
    positives: int = Field(gt=0)
    base_rate: float = Field(gt=0.0, lt=1.0)
    per_farm: bool


class CareAttributionConfig(StrictModel):
    """Top level of ``configs/eval/care_attribution_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        registered_in: The addendum's registration commit, or ``pending`` inside that commit.
        axis_config: The axis-gate configuration in force.
        label: The label every probe is scored on.
        stride: The registered thinning.
        bootstrap: ADR-0021's interval, unchanged.
        checkpoint: The probe checkpoint read, under the ADR-0022 addendum rule.
        base_rate_source: Where every chance level comes from; ``scored_set``.
        seeds: The full-budget ``tel_only`` seeds.
        masking: F6-0a.
        bag_of_tokens: F6-0b.
    """

    version: int = 0
    registered_in: str
    axis_config: str
    label: str
    stride: int = Field(gt=0)
    bootstrap: BootstrapConfig
    checkpoint: str
    base_rate_source: str
    seeds: list[int] = Field(min_length=1)
    masking: MaskingConfig
    bag_of_tokens: BagOfTokensTransferConfig


# =====================================================================================
# the masking, exactly as the CARE adapter emits an absent channel
# =====================================================================================

#: The farm the addendum's first F6-0a clause names. Only farm A's pattern can read as failure
#: to transfer; for farms B and C the registered reading has only the second clause.
FIRST_CLAUSE_FARM = "farm_a"

#: The addendum's gap sentence, applied when an outcome meets neither registered clause.
NEITHER_READING = (
    "meets neither registered clause; it is reported as measured, and the farm's null stays "
    "unattributed. No third clause is added after the numbers exist."
)

#: Windows per farm read back from the CARE stream to check the masking against the adapter.
ADAPTER_CHECK_WINDOWS = 256


def mask_positions(step: Sequence[str], channels: Sequence[str], context_steps: int) -> np.ndarray:
    """Every position of a window that carries one of ``channels``'s bin tokens.

    Args:
        step: The token layout of one step, as the shard manifest lists it: ``<sep>``, then the
            channels in the tokenizer's fitted order.
        channels: The channels to mask.
        context_steps: Steps in a window.

    Returns:
        The positions, sorted, within a flattened window of ``context_steps * len(step)`` tokens.

    Raises:
        ValueError: If a channel is not in the step layout, is ``<sep>``, or is listed twice.
    """
    if len(set(channels)) != len(channels):
        raise ValueError(f"a channel is listed twice in {list(channels)}")
    stray = [name for name in channels if name not in step or name == "<sep>"]
    if stray:
        raise ValueError(f"{stray} are not channel positions of the step layout {list(step)}")
    offsets = np.array(sorted(list(step).index(name) for name in channels), dtype=np.int64)
    starts = np.arange(context_steps, dtype=np.int64) * len(step)
    positions: np.ndarray = np.sort((starts[:, None] + offsets[None, :]).ravel())
    return positions


def mask_tokens(tokens: np.ndarray, positions: np.ndarray, nan_id: int) -> np.ndarray:
    """A copy of one or more windows with ``positions`` replaced by ``<nan>``.

    Args:
        tokens: A window, or ``(windows, width)``.
        positions: Positions within a window (``mask_positions``).
        nan_id: The ``<nan>`` identifier of the stream.

    Returns:
        The masked copy.
    """
    masked = np.array(tokens, copy=True)
    masked[..., positions] = nan_id
    return masked


class MaskedSampler(WindowSampler):
    """A window sampler whose every batch carries ``<nan>`` at the masked positions.

    It reads the same window sets in the same order as the sampler it wraps, so its scores line
    up with the unmasked scoring of those windows row for row.

    Attributes:
        positions: Positions within a window replaced in every batch.
        nan_id: The identifier written there.
    """

    def __init__(self, base: WindowSampler, positions: np.ndarray, nan_id: int) -> None:
        """Wrap a sampler.

        Args:
            base: The unmasked sampler.
            positions: Positions within a window to replace (``mask_positions``).
            nan_id: The ``<nan>`` identifier of the stream.

        Raises:
            ValueError: If a position lies outside a window.
        """
        super().__init__(
            base.sets, base.batch_size, base.tokens_per_step, base.context_steps, base.labelled
        )
        width = base.context_steps * base.tokens_per_step
        if positions.size and (int(positions.min()) < 0 or int(positions.max()) >= width):
            raise ValueError(f"a masked position lies outside a window of {width} tokens")
        self.positions = torch.from_numpy(positions.astype(np.int64))
        self.nan_id = nan_id

    def _gather(self, rows: np.ndarray) -> Batch:
        tokens, labels, sets = super()._gather(rows)
        tokens[:, self.positions] = self.nan_id
        return tokens, labels, sets


def masked_split(split: SplitEval, positions: np.ndarray, nan_id: int) -> SplitEval:
    """The same split, read through a ``MaskedSampler``.

    Args:
        split: The unmasked split.
        positions: Positions within a window to replace.
        nan_id: The ``<nan>`` identifier of the stream.

    Returns:
        The split with its sampler wrapped; sources, years and set order unchanged.
    """
    return replace(split, sampler=MaskedSampler(split.sampler, positions, nan_id))


def check_adapter_agreement(
    shards: ShardSet,
    care_key: str,
    label: str,
    stride: int,
    patterns: dict[str, list[str]],
) -> dict[str, int]:
    """Check that each farm's pattern, imposed by ``mask_tokens``, is what CARE already carries.

    Masking a real CARE window of a farm with that farm's own pattern must leave it unchanged:
    the adapter put exactly this ``<nan>`` id at exactly these positions. Up to
    ``ADAPTER_CHECK_WINDOWS`` windows a farm are read, evenly spaced over its scored windows.

    Args:
        shards: The shard set in force.
        care_key: The CARE shard key.
        label: The label the windows are scored under.
        stride: The registered thinning.
        patterns: Per farm, the channels imposed.

    Returns:
        Per farm, how many windows were checked.

    Raises:
        ValueError: If a farm has no window, or a checked window differs from its masked copy.
    """
    record = shards.files()[care_key]
    per_step, context = shards.tokens_per_step, shards.context_steps
    nan_id = int(dict(shards.manifest["specials"])["<nan>"])
    step = [str(name) for name in shards.manifest["step"]]
    stream = np.memmap(
        shards.root / str(record["tokens"]),
        dtype=np.uint16,
        mode="r",
        shape=(int(record["steps"]) * per_step,),
    )
    frame = index_rows(shards, care_key, label, stride, ["start_step"])
    starts = frame["start_step"].to_numpy(np.int64)
    farms = care_window_farms(shards, care_key, label, stride)
    checked: dict[str, int] = {}
    for farm, channels in patterns.items():
        positions = mask_positions(step, channels, context)
        mine = starts[farms == farm]
        if not mine.size:
            raise ValueError(f"{farm} holds no scored CARE window")
        count = min(ADAPTER_CHECK_WINDOWS, int(mine.size))
        picked = mine[np.linspace(0, mine.size - 1, count).astype(np.int64)]
        for first in picked:
            window = np.asarray(stream[first * per_step : (first + context) * per_step])
            if not np.array_equal(mask_tokens(window, positions, nan_id), window):
                raise ValueError(
                    f"{farm}'s window at step {first} does not carry <nan> ({nan_id}) at every "
                    f"position of {channels}: the masking would not be the adapter's"
                )
        checked[farm] = int(picked.size)
    return checked


# =====================================================================================
# the readings, as registered
# =====================================================================================


def interval_position(interval: AuprcInterval, line: float, max_discarded_share: float) -> str:
    """Where an interval lies against a line: ``clears``, ``contains`` or ``below``.

    ``clears`` is ADR-0021's strict rule, and an interval with more than ``max_discarded_share``
    of its replicates discarded does not clear whatever its bounds say; it is then read by its
    bounds as ``contains`` or ``below``.

    Args:
        interval: The interval.
        line: The line, the scored set's registered base rate.
        max_discarded_share: The discard rule.

    Returns:
        The position.
    """
    trusted = interval.discarded_share <= max_discarded_share and not math.isnan(interval.low)
    if interval.low > line and trusted:
        return "clears"
    if interval.high < line:
        return "below"
    return "contains"


@dataclass(frozen=True)
class FarmReading:
    """F6-0a's registered reading, applied to one farm's pattern.

    Attributes:
        farm: The farm whose pattern was imposed.
        clears: Seeds whose pooled lower bound is strictly above the line.
        contains: Seeds whose pooled interval contains the line.
        below: Seeds whose pooled interval lies wholly below the line.
        clause: ``first``, ``second`` or ``neither``.
        attribution: ``transfer failure`` or ``unattributed``; nothing else is registered.
        sentence: The outcome in the addendum's own words.
    """

    farm: str
    clears: tuple[int, ...]
    contains: tuple[int, ...]
    below: tuple[int, ...]
    clause: str
    attribution: str
    sentence: str


def read_masking(farm: str, positions: dict[int, str], required: int) -> FarmReading:
    """Apply the F6-0a reading verbatim to one farm's pattern.

    Clause one: under farm A's pattern, a lower bound above the base rate on at least
    ``required`` seeds reads farm A's CARE null as failure to transfer. Clause two: under any
    farm's pattern, an interval containing the base rate on at least ``required`` seeds means
    the pattern alone is sufficient to null the probe, and the farm's null stays unattributed.
    Anything else meets neither clause.

    Args:
        farm: The farm whose pattern was imposed.
        positions: Per seed, ``interval_position`` of its masked interval.
        required: Seeds on which a clause must hold.

    Returns:
        The reading.
    """
    by = {
        kind: tuple(s for s in sorted(positions) if positions[s] == kind)
        for kind in ("clears", "contains", "below")
    }
    counts = (by["clears"], by["contains"], by["below"])
    tally = (
        f"{len(by['clears'])} of {len(positions)} seeds clear 0.0388, {len(by['contains'])} "
        f"contain it, {len(by['below'])} lie wholly below it"
    )
    if farm == FIRST_CLAUSE_FARM and len(by["clears"]) >= required:
        return FarmReading(
            farm,
            *counts,
            clause="first",
            attribution="transfer failure",
            sentence=f"{tally}: a one-channel gap does not null the probe, and the CARE farm-A "
            "null is read as failure to transfer.",
        )
    if len(by["contains"]) >= required:
        return FarmReading(
            farm,
            *counts,
            clause="second",
            attribution="unattributed",
            sentence=f"{tally}: that pattern alone is sufficient to null the probe, and "
            f"{farm}'s CARE null remains unattributed.",
        )
    return FarmReading(
        farm,
        *counts,
        clause="neither",
        attribution="unattributed",
        sentence=f"{tally}: the outcome {NEITHER_READING}",
    )


@dataclass(frozen=True)
class BagReading:
    """F6-0b's registered reading, applied to the pooled CARE interval.

    Attributes:
        position: ``clears``, ``contains`` or ``below`` the line.
        clause: ``first`` (contains), ``second`` (clears) or ``neither``.
        sentence: The outcome in the addendum's own words.
    """

    position: str
    clause: str
    sentence: str


def read_bag(pooled: AuprcInterval, line: float, max_discarded_share: float) -> BagReading:
    """Apply the F6-0b reading verbatim to the pooled CARE interval.

    Args:
        pooled: The comparator's pooled CARE interval.
        line: The registered CARE base rate.
        max_discarded_share: The discard rule.

    Returns:
        The reading.
    """
    where = interval_position(pooled, line, max_discarded_share)
    if where == "contains":
        return BagReading(
            where,
            "first",
            "the pooled interval contains 0.001254: no order-blind classifier transfers either, "
            "and the null is a property of the token stream across OEMs.",
        )
    if where == "clears":
        return BagReading(
            where,
            "second",
            "the pooled lower bound exceeds 0.001254: the backbone specifically fails to "
            "transfer where an order-blind classifier does not.",
        )
    return BagReading(
        where,
        "neither",
        "the pooled interval lies wholly below 0.001254, which meets neither registered clause; "
        "it is reported as measured.",
    )


# =====================================================================================
# the bootstrap rows, one JSON each, computed in parallel
# =====================================================================================


@dataclass(frozen=True)
class MaskedJob:
    """One F6-0a row's bootstrap: the masked interval and its paired delta.

    Attributes:
        cache: The JSON the row is written to.
        masked: The masked scores.
        unmasked: The seed's unmasked F3 scores on the same windows.
        sources: The sources pooled.
        bootstrap: ADR-0021's interval.
    """

    cache: Path
    masked: Path
    unmasked: Path
    sources: list[str]
    bootstrap: BootstrapConfig


@dataclass(frozen=True)
class GroupJob:
    """One F6-0b row's bootstrap: the comparator's interval over one group of CARE windows.

    Attributes:
        cache: The JSON the row is written to.
        scores: The comparator's CARE scores.
        mask: Per scored window, whether it is in the group.
        bootstrap: ADR-0021's interval.
    """

    cache: Path
    scores: Path
    mask: np.ndarray
    bootstrap: BootstrapConfig


def _write(cache: Path, payload: dict[str, Any]) -> None:
    """Write a JSON whole: to a partial file first, then renamed, so a crash leaves none."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    partial = cache.with_suffix(".partial")
    partial.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(partial, cache)


def run_job(job: MaskedJob | GroupJob) -> Path:
    """Compute one row's bootstrap and write it whole. Runs in a worker process.

    Args:
        job: The row.

    Returns:
        The JSON written.

    Raises:
        ValueError: If the masked and unmasked scores cover other windows.
    """
    if isinstance(job, MaskedJob):
        masked, unmasked = ScoredWindows.load(job.masked), ScoredWindows.load(job.unmasked)
        if not masked.same_windows(unmasked):
            raise ValueError(f"{job.masked.name} and {job.unmasked.name} cover other windows")
        interval = masked.interval(job.sources, job.bootstrap)
        # ADR-0024 §2's paired bootstrap with the masked read as the reference: the delta is
        # AUPRC(masked) - AUPRC(unmasked), both read on the identical resampled rows.
        delta = paired_rows(masked, [unmasked], job.sources, job.bootstrap)[0]
        _write(job.cache, {"interval": asdict(interval), "delta": asdict(delta)})
    else:
        scored = ScoredWindows.load(job.scores)
        _write(job.cache, {"interval": asdict(masked_interval(scored, job.mask, job.bootstrap))})
    return job.cache


def run_jobs(jobs: list[MaskedJob | GroupJob]) -> list[Path]:
    """Run the rows not yet on disk in parallel; each writes its own JSON as it completes.

    Every row draws its replicates from its own generator at the registered seed, so the result
    does not depend on which worker runs it or in what order.

    Args:
        jobs: Every row whose JSON is missing.

    Returns:
        The JSON files written.
    """
    if not jobs:
        return []
    workers = max(1, min(len(jobs), (os.cpu_count() or 2) - 2))
    logger.info("bootstrapping %d rows on %d worker processes", len(jobs), workers)
    written: list[Path] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_job, job) for job in jobs]
        for future in as_completed(futures):
            written.append(future.result())
            logger.info("row written: %s", written[-1].name)
    return written


# =====================================================================================
# the record
# =====================================================================================


@dataclass(frozen=True)
class MaskedRow:
    """One F6-0a row: a seed's final-step probe under one farm's pattern.

    Attributes:
        farm: The farm whose pattern was imposed.
        channels: The channels imposed as ``<nan>``.
        seed: The pretraining seed.
        probe: The probe file read.
        interval: The masked read's pooled interval.
        delta: AUPRC(masked) minus AUPRC(unmasked), paired.
        unmasked: The seed's unmasked final-step read: F5's interval on the same windows.
        position: Where the masked interval lies against the registered base rate.
    """

    farm: str
    channels: tuple[str, ...]
    seed: int
    probe: str
    interval: AuprcInterval
    delta: DeltaInterval
    unmasked: AuprcInterval
    position: str


@dataclass(frozen=True)
class GroupRow:
    """One F6-0b row, beside F5's final-step probe rows on the same CARE windows.

    Attributes:
        group: ``care`` (pooled) or a farm.
        interval: The comparator's interval.
        position: Where it lies against the row's line.
        line: The registered base rate for the pooled row; the group's own rate for a farm.
        probes: Per seed, F5's final-step probe interval on the same group.
        nan_share: The group's ``<nan>`` share of value tokens, F5's per-step measurement.
    """

    group: str
    interval: AuprcInterval
    position: str
    line: float
    probes: dict[int, AuprcInterval]
    nan_share: float


@dataclass(frozen=True)
class AttributionRecord:
    """Everything F6-0 measured.

    Attributes:
        config_hash: The configuration's hash.
        masked: The nine F6-0a rows.
        farm_readings: Per farm, the F6-0a reading.
        bag: The F6-0b rows, pooled first.
        bag_reading: The F6-0b reading on the pooled row.
        adapter_check: Per farm, CARE windows checked against the masking.
        nan_id: The ``<nan>`` identifier imposed.
        reproduction: Per probe, the largest logit difference between the unmasked first batch
            re-scored here and F3's saved logits, measured when that probe was first scored.
        gpu_seconds: The masked scorings' GPU time, summed over the invocations that paid for it.
        cpu_seconds: The comparator's CARE scoring's CPU time.
        scorings_computed: Scorings this invocation paid for.
        scorings_resumed: Scorings read back from disk.
        rows_computed: Bootstrap rows this invocation computed.
        rows_resumed: Bootstrap rows read back from disk.
        seconds: Wall clock of this invocation.
    """

    config_hash: str
    masked: tuple[MaskedRow, ...]
    farm_readings: dict[str, FarmReading]
    bag: tuple[GroupRow, ...]
    bag_reading: BagReading
    adapter_check: dict[str, int]
    nan_id: int
    reproduction: dict[str, float]
    gpu_seconds: float
    cpu_seconds: float
    scorings_computed: tuple[str, ...]
    scorings_resumed: tuple[str, ...]
    rows_computed: tuple[str, ...]
    rows_resumed: tuple[str, ...]
    seconds: float


def record_payload(record: AttributionRecord) -> dict[str, Any]:
    """Serialize the record to the JSON the report is written beside.

    Args:
        record: What F6-0 measured.

    Returns:
        A JSON-serializable mapping.
    """
    payload = asdict(record)
    payload["bag"] = [
        {**asdict(row), "probes": {str(s): asdict(i) for s, i in row.probes.items()}}
        for row in record.bag
    ]
    return payload


# =====================================================================================
# the run
# =====================================================================================

#: Above this, an unmasked first batch re-scored here does not reproduce F3's saved logits.
REPRODUCTION_TOLERANCE = 0.05


def _timing(path: Path) -> float:
    timing = path.with_suffix(".timing.json")
    if not timing.is_file():
        return 0.0
    return float(json.loads(timing.read_text(encoding="utf-8"))["seconds"])


def _score_to(
    path: Path,
    score: Callable[[], tuple[np.ndarray, np.ndarray]],
    split: SplitEval,
    offset: float,
) -> ScoredWindows:
    """Score, save in ``save_scores``'s layout, and write the timing beside the scores.

    The timing lets a later invocation, which resumes every scoring and so pays for none, still
    report what the scorings cost.
    """
    started = time.perf_counter()
    scored = save_split_scores(path, score(), split, offset)
    _write(path.with_suffix(".timing.json"), {"seconds": time.perf_counter() - started})
    return scored


def first_batch_difference(
    probe: Path, design: str, inputs: ProbeInputs, split: SplitEval, reference: ScoredWindows
) -> float:
    """Re-score the unmasked split's first batch and compare it with F3's saved logits.

    It checks that the scoring path here is F3's, so that a masked-minus-unmasked delta measures
    the masking and nothing else. It costs one batch.

    Args:
        probe: The probe's saved state.
        design: The ADR-0023 design it was trained under.
        inputs: The opened shards and rung.
        split: The unmasked split.
        reference: F3's saved scores on it.

    Returns:
        The largest absolute logit difference over the batch.
    """
    model = load_saved_probe(probe, design, inputs)
    autocast = torch.autocast(
        device_type=inputs.device.type,
        dtype=torch.bfloat16,
        enabled=inputs.ladder.optimiser.precision == "bf16" and inputs.device.type == "cuda",
    )
    tokens, _, _ = next(iter(split.sampler.epoch()))
    with torch.inference_mode(), autocast:
        logits = model(tokens.to(inputs.device)).float().cpu().numpy()
    return float(np.abs(logits - reference.logits[: logits.size]).max())


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing")
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def run_care_attribution(
    paths: ProjectPaths, config_path: Path, device_name: str | None = None
) -> tuple[Path, Path]:
    """Score F6-0a on the GPU and F6-0b on the CPU, bootstrap every row, apply both readings.

    Args:
        paths: Resolved project paths.
        config_path: The CARE-attribution configuration.
        device_name: Torch device for F6-0a; chosen automatically when omitted.

    Returns:
        The report and its JSON record.

    Raises:
        ValueError: If the configuration disagrees with the axis gate's, the index no longer
            holds the registered counts, the comparator is to be refit, the scoring path does
            not reproduce F3's, or scores do not line up with the windows they are read against.
        FileNotFoundError: If the comparator's fitted weights or an F3 or F5 artefact is missing.
    """
    config = load_config(config_path, CareAttributionConfig)
    root = paths.repo_root
    axis = load_config(root / config.axis_config, AxisGateConfig)
    f3 = load_config(root / config.masking.seed_replication_config, SeedReplicationConfig)
    gate = load_config(root / f3.gate_config, GateCheckConfig)
    bag_config = load_config(root / config.bag_of_tokens.config, BagOfTokensConfig)
    bootstrap, stride, label = config.bootstrap, config.stride, config.label
    if config.bag_of_tokens.refit:
        raise ValueError("the addendum registers the comparator unchanged; refit must be false")
    if config.checkpoint != FIXED_FINAL:
        raise ValueError(f"the addendum reads the {FIXED_FINAL} probes, not {config.checkpoint}")
    if (stride, label, bootstrap, config.seeds) != (
        axis.stride,
        axis.label,
        axis.bootstrap,
        axis.seeds,
    ):
        raise ValueError("the stride, label, bootstrap or seeds differ from the axis gate's")
    started = time.perf_counter()
    digest = config_hash(config)
    out_dir = paths.checkpoints_dir / f"care_attribution_v{config.version}_{digest}"
    f3_dir = paths.checkpoints_dir / f"seed_replication_v{f3.version}_{config_hash(f3)}"
    axis_dir = paths.checkpoints_dir / f"axis_gate_v{axis.version}_{config_hash(axis)}"
    bag_dir = (
        paths.checkpoints_dir / f"bag_of_tokens_v{bag_config.version}_{config_hash(bag_config)}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    shards = ShardSet.load(root / axis.shards)
    care_key = axis.axes.care.shard_keys[0]
    temporal_keys = axis.axes.temporal.shard_keys
    nan_id = int(dict(shards.manifest["specials"])["<nan>"])
    step = [str(name) for name in shards.manifest["step"]]

    # -- the counts, asserted from the index before anything is scored -------------------------
    temporal_counts = index_counts(shards, temporal_keys, label, stride, bootstrap.block_steps)
    measured = (temporal_counts.windows, temporal_counts.positives)
    if measured != (config.masking.windows, config.masking.positives):
        raise ValueError(
            f"the temporal index holds {measured} windows and positives, not the registered "
            f"{(config.masking.windows, config.masking.positives)}"
        )
    thinned = index_counts(shards, [care_key], label, stride, bootstrap.block_steps)
    full = index_counts(shards, [care_key], label, 1, bootstrap.block_steps)
    check_care_counts(axis.axes.care, thinned, full)
    if (thinned.windows, thinned.positives) != (
        config.bag_of_tokens.windows,
        config.bag_of_tokens.positives,
    ):
        raise ValueError("the CARE index does not hold the registered F6-0b counts")
    logger.info(
        "index: temporal %d windows, %d positive; CARE %d windows, %d positive",
        temporal_counts.windows,
        temporal_counts.positives,
        thinned.windows,
        thinned.positives,
    )

    # -- the masking is the adapter's -----------------------------------------------------------
    adapter_check = check_adapter_agreement(
        shards, care_key, label, stride, config.masking.patterns
    )
    logger.info("each farm's pattern is what its CARE windows carry: %s", adapter_check)

    probes = {seed: read_probes(paths, f3, seed) for seed in config.seeds}
    for seed, probe in probes.items():
        logger.info(
            "seed %d reads %s (step %d)%s",
            seed,
            probe.state(FIXED_FINAL).name,
            probe.last_step,
            "; its selected probe is its final probe" if probe.identical else "",
        )

    def unmasked_path(probe: ProbeCheckpoints) -> Path:
        infix = "" if probe.identical else "_final"
        return f3_dir / f"{probe.name}{infix}_stride{stride}_scores.npz"

    opened: list[ProbeInputs] = []
    splits: dict[str, SplitEval] = {}

    def inputs() -> ProbeInputs:
        if not opened:
            opened.append(
                open_probe_inputs(
                    paths,
                    gate.mixture_config,
                    gate.ladder_config,
                    gate.arm,
                    gate.rung,
                    gate.selection_windows,
                    gate.held_out_source,
                    device_name,
                )
            )
        return opened[0]

    def split(which: str) -> SplitEval:
        if which not in splits:
            evaluation = inputs().ladder.evaluation
            splits[which] = build_split(
                inputs().telemetry,
                "test",
                None,
                stride,
                evaluation.seed,
                evaluation.batch_windows,
                label,
                sources=f3.pooled_sources if which == "temporal" else ["care"],
            )
        return splits[which]

    # -- F6-0a, on the GPU ---------------------------------------------------------------------
    computed: list[str] = []
    resumed: list[str] = []
    reproduction_file = out_dir / "reproduction.json"
    reproduction: dict[str, float] = (
        {str(k): float(v) for k, v in _json(reproduction_file).items()}
        if reproduction_file.is_file()
        else {}
    )
    masked_files: dict[tuple[str, int], Path] = {}
    for seed in config.seeds:
        probe = probes[seed]
        reference = ScoredWindows.load(unmasked_path(probe))
        for farm, channels in config.masking.patterns.items():
            path = out_dir / f"{probe.name}_masked_{farm}_stride{stride}_scores.npz"
            masked_files[farm, seed] = path
            if path.exists():
                resumed.append(path.stem)
                continue
            if probe.name not in reproduction:
                difference = first_batch_difference(
                    probe.state(FIXED_FINAL), f3.design, inputs(), split("temporal"), reference
                )
                logger.info(
                    "%s unmasked first batch vs F3: max |dlogit| %.2e", probe.name, difference
                )
                if difference > REPRODUCTION_TOLERANCE:
                    raise ValueError(
                        f"{probe.name} does not reproduce F3's unmasked logits (largest "
                        f"difference {difference:.3f}), so a delta would not be the masking's"
                    )
                reproduction[probe.name] = difference
                _write(reproduction_file, dict(reproduction))
            positions = mask_positions(step, channels, shards.context_steps)
            logger.info("=== scoring %s with %s's pattern: %s ===", probe.name, farm, channels)
            view = masked_split(split("temporal"), positions, nan_id)
            state = probe.state(FIXED_FINAL)

            def masked_scores(
                state: Path = state, view: SplitEval = view
            ) -> tuple[np.ndarray, np.ndarray]:
                return score_saved_probe(state, f3.design, inputs(), view)

            scored = _score_to(path, masked_scores, view, probe.prior_offset)
            if not scored.same_windows(reference):
                raise ValueError(f"{path.name} does not cover F3's windows")
            computed.append(path.stem)
    gpu_seconds = sum(_timing(p) for p in masked_files.values())

    # -- F6-0b, on the CPU, the comparator as saved -----------------------------------------------
    bag_state = bag_dir / "bag_of_tokens.pt"
    if not bag_state.is_file():
        raise FileNotFoundError(f"{bag_state} is missing: G2's fitted weights are not on disk")
    bag_path = out_dir / f"care_bag_of_tokens_stride{stride}_scores.npz"
    care_reference = ScoredWindows.load(
        axis_dir / f"{probes[config.seeds[0]].stem(FIXED_FINAL, stride)}.npz"
    )
    if bag_path.exists():
        resumed.append(bag_path.stem)
    else:
        payload = read_checkpoint(bag_state)
        if payload.get("kind") != "bag_of_tokens":
            raise ValueError(f"{bag_state} is not the bag-of-tokens comparator")
        telemetry = inputs().telemetry
        model = BagOfTokens(telemetry.vocab_size, telemetry.context_steps)
        model.load_state_dict(payload["state"])
        model.eval()
        offset = ScoredWindows.load(
            bag_dir / f"bag_of_tokens_stride{stride}_scores.npz"
        ).prior_offset
        logger.info("=== scoring CARE with the bag-of-tokens comparator on the CPU ===")

        def bag_scores() -> tuple[np.ndarray, np.ndarray]:
            with torch.inference_mode():
                logits, labels, _ = risk_logits(
                    model, split("care").sampler, torch.device("cpu"), False
                )
            return logits, labels

        _score_to(bag_path, bag_scores, split("care"), offset)
        computed.append(bag_path.stem)
    if not ScoredWindows.load(bag_path).same_windows(care_reference):
        raise ValueError("the comparator's CARE scores do not cover F5's CARE windows")
    if not np.array_equal(window_steps(shards, [care_key], label, stride), care_reference.ends):
        raise ValueError("the CARE index rows do not line up with the saved CARE scores")
    cpu_seconds = _timing(bag_path)
    farms = care_window_farms(shards, care_key, label, stride)

    # -- the bootstrap rows ------------------------------------------------------------------------
    jobs: list[MaskedJob | GroupJob] = []
    masked_caches: dict[tuple[str, int], Path] = {}
    for (farm, seed), path in masked_files.items():
        cache = out_dir / f"bootstrap_{probes[seed].name}_masked_{farm}.json"
        masked_caches[farm, seed] = cache
        if not cache.exists():
            jobs.append(
                MaskedJob(cache, path, unmasked_path(probes[seed]), f3.pooled_sources, bootstrap)
            )
    groups = {"care": np.ones(farms.size, dtype=bool)} | {f: farms == f for f in CARE_FARMS}
    group_caches = {g: out_dir / f"bootstrap_bag_{g}.json" for g in groups}
    for group, mask in groups.items():
        if not group_caches[group].exists():
            jobs.append(GroupJob(group_caches[group], bag_path, mask, bootstrap))
    pending = {job.cache for job in jobs}
    every_cache = [*masked_caches.values(), *group_caches.values()]
    rows_resumed = tuple(c.stem for c in every_cache if c not in pending)
    rows_computed = tuple(p.stem for p in run_jobs(jobs))

    # -- the rows, read back ---------------------------------------------------------------------
    f5 = {seed: _json(axis_dir / f"bootstrap_seed{seed}.json") for seed in config.seeds}

    def f5_interval(seed: int, axis_name: str, group: str | None = None) -> AuprcInterval:
        if group is None:
            rows = [r for r in f5[seed]["rows"] if r["axis"] == axis_name]
        else:
            rows = [r for r in f5[seed]["reported"] if r["group"] == group]
        row = next(r for r in rows if r["checkpoint"] == FIXED_FINAL)
        return AuprcInterval(**row["interval"])

    masked_rows: list[MaskedRow] = []
    for (farm, seed), cache in sorted(masked_caches.items()):
        saved = _json(cache)
        interval, delta = AuprcInterval(**saved["interval"]), DeltaInterval(**saved["delta"])
        unmasked = f5_interval(seed, "temporal")
        if not math.isclose(delta.second_auprc, unmasked.auprc, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"{cache.name}: the unmasked read is not F5's {unmasked.auprc}")
        masked_rows.append(
            MaskedRow(
                farm=farm,
                channels=tuple(config.masking.patterns[farm]),
                seed=seed,
                probe=probes[seed].state(FIXED_FINAL).name,
                interval=interval,
                delta=delta,
                unmasked=unmasked,
                position=interval_position(
                    interval, config.masking.base_rate, bootstrap.max_discarded_share
                ),
            )
        )
    farm_readings = {
        farm: read_masking(
            farm,
            {r.seed: r.position for r in masked_rows if r.farm == farm},
            config.masking.seeds_required,
        )
        for farm in config.masking.patterns
    }
    absence = _json(axis_dir / "channel_absence.json")
    bag_rows: list[GroupRow] = []
    for group, cache in group_caches.items():
        interval = AuprcInterval(**_json(cache)["interval"])
        line = config.bag_of_tokens.base_rate if group == "care" else interval.base_rate
        bag_rows.append(
            GroupRow(
                group=group,
                interval=interval,
                position=interval_position(interval, line, bootstrap.max_discarded_share),
                line=line,
                probes={
                    seed: f5_interval(seed, "care", None if group == "care" else group)
                    for seed in config.seeds
                },
                nan_share=float(absence[group]["nan_share_steps"]),
            )
        )
    bag_reading = read_bag(
        bag_rows[0].interval, config.bag_of_tokens.base_rate, bootstrap.max_discarded_share
    )
    for farm, reading in farm_readings.items():
        logger.info("F6-0a %s: %s", farm, reading.sentence)
    logger.info("F6-0b: %s", bag_reading.sentence)

    record = AttributionRecord(
        config_hash=digest,
        masked=tuple(masked_rows),
        farm_readings=farm_readings,
        bag=tuple(bag_rows),
        bag_reading=bag_reading,
        adapter_check=adapter_check,
        nan_id=nan_id,
        reproduction=reproduction,
        gpu_seconds=gpu_seconds,
        cpu_seconds=cpu_seconds,
        scorings_computed=tuple(computed),
        scorings_resumed=tuple(resumed),
        rows_computed=rows_computed,
        rows_resumed=rows_resumed,
        seconds=time.perf_counter() - started,
    )
    stem = f"care_attribution_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report_file = paths.data_reports_dir / f"{stem}.md"
    report_file.write_text(
        render_report(config, config_path, record, probes, paths), encoding="utf-8", newline="\n"
    )
    record_file = paths.data_reports_dir / f"{stem}.json"
    body = {"config": config.model_dump(mode="json"), **record_payload(record)}
    record_file.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report_file, record_file)
    return report_file, record_file


# =====================================================================================
# the report
# =====================================================================================

#: The commits the addendum was registered in and its hash recorded by, and the rule in force.
HASHES = {
    "ADR-0022 F6-0 addendum, registered": "ad1b7a3",
    "ADR-0022 F6-0 addendum, hash recorded": "6aca9b9",
    "ADR-0022 checkpoint-rule addendum, outcome": "267147d",
}


def _iv(interval: AuprcInterval, digits: int = 4) -> str:
    return f"{interval.auprc:.{digits}f} [{interval.low:.{digits}f}, {interval.high:.{digits}f}]"


def _dv(delta: DeltaInterval) -> str:
    return f"{delta.delta:+.4f} [{delta.low:+.4f}, {delta.high:+.4f}]"


def render_report(
    config: CareAttributionConfig,
    config_path: Path,
    record: AttributionRecord,
    probes: dict[int, ProbeCheckpoints],
    paths: ProjectPaths,
) -> str:
    """Render F6-0's report.

    Args:
        config: The configuration.
        config_path: Where it was read from.
        record: What F6-0 measured.
        probes: Per seed, its checkpoints.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    relative = config_path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    line = config.masking.base_rate
    identical = [str(s) for s, p in probes.items() if p.identical]
    rate = record.masked[0].interval.base_rate
    between = [
        f"{r.farm} seed {r.seed}"
        for r in record.masked
        for bound in (r.interval.low, r.interval.high)
        if min(line, rate) <= bound <= max(line, rate)
    ]
    rounding = f"The registered line is {line}; the split's unrounded rate is {rate:.5f}. " + (
        "No masked bound lies between the two, so the rounding decides nothing."
        if not between
        else f"A masked bound lies between the two ({', '.join(between)}); the registered "
        f"{line} is the line read."
    )
    masked_table = [
        (
            row.farm,
            ", ".join(f"`{c}`" for c in row.channels),
            str(row.seed),
            row.probe,
            _iv(row.interval),
            f"{row.interval.base_rate:.4f}",
            row.position,
            _dv(row.delta),
            _iv(row.unmasked),
            f"{row.interval.discarded_share:.2%}",
        )
        for row in record.masked
    ]
    reading_rows = [
        (
            farm,
            ", ".join(map(str, r.clears)) or "none",
            ", ".join(map(str, r.contains)) or "none",
            ", ".join(map(str, r.below)) or "none",
            r.clause,
            r.attribution,
        )
        for farm, r in record.farm_readings.items()
    ]
    bag_table = [
        (
            "CARE, pooled" if row.group == "care" else row.group,
            f"{row.nan_share:.2%}",
            f"{row.interval.windows:,}",
            str(row.interval.positives),
            f"{row.interval.base_rate:.6f}",
            _iv(row.interval, 6),
            row.position + (" 0.001254 (registered)" if row.group == "care" else " own rate"),
            f"{row.interval.discarded_share:.2%}",
            *(_iv(row.probes[s], 6) for s in sorted(row.probes)),
        )
        for row in record.bag
    ]
    pooled = record.bag[0].interval
    closing = "\n".join(
        f"- **{farm}.** By the registered F6-0a reading, {reading.sentence} The CARE null at "
        f"{farm} is attributed to: **{reading.attribution}**."
        for farm, reading in record.farm_readings.items()
    )
    reproduced = (
        ", ".join(f"{k} {v:.1e}" for k, v in record.reproduction.items())
        or "not re-measured: every scoring was resumed"
    )
    return "".join(
        [
            "# CARE null attribution diagnostics (ADR-0022, F6-0 addendum)\n\n",
            kv_table(
                {
                    "configuration": f"{relative} (hash {record.config_hash})",
                    "decision record": "docs/DECISIONS.md, ADR-0022, Addendum (F6-0), "
                    "registered before its code or run",
                    **HASHES,
                    "checkpoint rule": f"`{config.checkpoint}`: every probe is read at its last "
                    "step"
                    + (
                        f"; seed {', '.join(identical)}'s selected probe is its final probe, "
                        "and that one file is read"
                        if identical
                        else ""
                    ),
                    "GPU wall clock (F6-0a)": f"{record.gpu_seconds / 3600:.2f} h over "
                    f"{len(record.masked)} scorings, whenever paid for; read from the timing "
                    "written beside each set of scores",
                    "CPU scoring (F6-0b)": f"{record.cpu_seconds / 60:.1f} min",
                    "scorings": f"{len(record.scorings_computed)} computed in this invocation, "
                    f"{len(record.scorings_resumed)} resumed from disk",
                    "bootstrap rows": f"{len(record.rows_computed)} computed in this invocation, "
                    f"{len(record.rows_resumed)} resumed from disk",
                    "wall clock (this invocation)": f"{record.seconds / 60:.1f} min",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model care-attribution",
                }
            ),
            section(
                "How an absent channel is imposed",
                "The CARE adapter never writes `<nan>` itself. A farm's absent core channel is "
                "a column its frame does not carry. `QuantileBinTokenizer.transform` emits "
                "`MISSING_BIN` for it on every row, and `JointVocab.encode_steps` maps that to "
                f"`<nan>` (id **{record.nan_id}**, the shard manifest's) at the channel's fixed "
                "position in the step, `1 + channel_index`, after `<sep>`. The stream carries no "
                "channel tokens: position in the step is the channel. F6-0a overwrites exactly "
                "those positions of every step of every window with that id, at inference. "
                "Nothing else changes: `<sep>`, the other channels and the window boundaries "
                "are the unmasked read's.\n\n"
                "Checked before scoring: masking real CARE windows with their own farm's pattern "
                "leaves every one of them unchanged ("
                + ", ".join(f"{f}: {n} windows" for f, n in record.adapter_check.items())
                + "). The unmasked first batch, re-scored here, reproduces F3's saved logits "
                f"(largest absolute difference: {reproduced}).\n",
            ),
            section(
                "Table 1 -- F6-0a, masking transfer",
                f"The training-site forward-in-time test split at stride {config.stride}: "
                f"{config.masking.windows:,} windows, {config.masking.positives:,} positive. "
                f"Position is against the registered base rate {line}: `clears` means a lower "
                "bound strictly above it, `contains` an interval holding it, and `below` an "
                "interval wholly under it. Δ is AUPRC(masked) − AUPRC(unmasked), from ADR-0024 "
                "§2's paired block bootstrap on the identical windows; it decides nothing. The "
                "unmasked read is F5's final-step interval on the same windows.\n\n"
                + table(
                    [
                        "pattern",
                        "channels set to `<nan>`",
                        "seed",
                        "probe",
                        "masked AUPRC, 95% block interval",
                        "base rate",
                        "position",
                        "paired Δ vs unmasked",
                        "unmasked AUPRC (F5)",
                        "discarded",
                    ],
                    masked_table,
                )
                + f"\n{rounding}\n\n**The registered reading, per farm** "
                f"({config.masking.seeds_required} of {len(config.seeds)} seeds):\n\n"
                + table(
                    [
                        "farm",
                        "seeds clearing",
                        "seeds containing",
                        "seeds below",
                        "clause met",
                        "attribution",
                    ],
                    reading_rows,
                )
                + "\n"
                + "\n".join(f"- **{f}**: {r.sentence}" for f, r in record.farm_readings.items())
                + "\n\nThe first clause is registered for farm A's pattern only. For farms B "
                "and C the reading has only the second clause, so no outcome there attributes "
                "the null to failure to transfer.\n",
            ),
            section(
                "Table 2 -- F6-0b, bag of tokens on CARE",
                "The G2 comparator as saved (`bag_of_tokens.pt`, not refit), scored on the CARE "
                f"stride-{config.stride} set: {config.bag_of_tokens.windows:,} windows, "
                f"{config.bag_of_tokens.positives} positive. Each window's histogram is G2's: "
                "every token id of the window counted, `<sep>` and `<nan>` included, and divided "
                "by the window's steps. F5's final-step probe intervals on the same windows are "
                "set beside it. The pooled row is read against the registered 0.001254, and "
                "each farm against its own base rate.\n\n"
                + table(
                    [
                        "group",
                        "`<nan>` share",
                        "windows",
                        "positives",
                        "own base rate",
                        "bag of tokens, 95% block interval",
                        "position against",
                        "discarded",
                        *(f"probe seed {s} (F5, final step)" for s in config.seeds),
                    ],
                    bag_table,
                )
                + f"\nThe pooled lower bound is {pooled.low:.6f}, "
                f"{abs(pooled.low - config.bag_of_tokens.base_rate):.6f} "
                f"{'below' if pooled.low <= config.bag_of_tokens.base_rate else 'above'} the "
                "registered line. CARE intervals are printed to six decimals so that each "
                "position can be read off the table.\n"
                + f"\n**The registered reading** (pooled): {record.bag_reading.sentence} The "
                "per-farm rows are reported beside it and decide nothing.\n",
            ),
            section(
                "What the CARE null is now attributed to",
                "By the registered F6-0a reading only, per farm:\n\n"
                + closing
                + "\n\nNo registered clause attributes a farm's null to the missing-channel "
                "pattern. The second clause finds a pattern *sufficient* to null the probe and "
                "leaves the farm unattributed. F6-0b's reading is pooled and is not a per-farm "
                f"attribution: {record.bag_reading.sentence}\n\n"
                "The nine F6-0a rows are the project's first H2 targeted-dropout measurement: "
                "forward in time, at the same sites. They are not a site-shift result.\n",
            ),
        ]
    )
