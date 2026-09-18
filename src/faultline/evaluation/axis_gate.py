"""ADR-0022 §4, applied: which candidate evaluation axis can separate `tel_only` from chance.

ADR-0021 demoted leave-site-out. ADR-0022 registered two candidates before either was scored --
the whole CARE evaluation set, and the in-distribution temporal test split at the training sites --
and one rule over them:

    An axis is EVALUABLE if the block-bootstrap 95% lower bound on ``tel_only`` test AUPRC is
    strictly above that axis's OWN scored-set base rate, never the training rate, on at least two
    of the three full-budget seeds.

**What this module pays for, and what it reads.** CARE has never been scored by any model in this
project, so each distinct probe checkpoint is scored here on the GPU, once, at the registered
stride-12 thinning. Nothing is pretrained and no probe is trained. The temporal split and Hill of
Towie are **not** re-scored: F3's saved ``.npz`` logits are the same checkpoints on the same
windows, and re-running them would spend an hour reproducing numbers already on disk.

**Resume is per artefact.** Each CARE scoring checks for its own output and skips it. Each seed's
bootstrap result is written whole as it completes, and a later invocation reads it back.

**Which checkpoint gates.** ADR-0022 §5 as amended by the addendum of 2026-09-18 (outcome
``267147d``): the **final-step** checkpoint gates, and the ADR-0024-selected checkpoint is scored
beside it on both axes and reported. ``configs/eval/axis_gate_v0.yaml`` carries the rule, and this
module reads it from there rather than naming one itself.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
from pydantic import Field

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.evaluation.bootstrap import (
    AuprcInterval,
    GateVerdict,
    bootstrap_auprc,
    decide_evaluable,
    window_blocks,
)
from faultline.evaluation.checkpoint_selection import FIXED_FINAL, SELECTED
from faultline.evaluation.gate_check import BootstrapConfig, GateCheckConfig
from faultline.evaluation.ladder import SplitEval, build_split
from faultline.evaluation.paired_control import save_split_scores, score_saved_probe
from faultline.evaluation.probe_cadence import ProbeCadenceConfig
from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.seed_replication import SeedReplicationConfig
from faultline.evaluation.variance_probe import ProbeInputs, open_probe_inputs
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.windows import ShardSet, load_windows

logger = get_logger(__name__)

#: ADR-0009's caveat, verbatim (evidence note of 2026-09-11), carried by every temporal-split row.
ADR_0009_CAVEAT = (
    "The late split is a temporal hold-out with a change in what is labelled, not a drift test. "
    "Standing requirement: every late-test result is reported both with and without the "
    "anemometer-defect events."
)

#: ADR-0022 §2: what the temporal split is, said on every row of it so no row reads as shift.
IN_DISTRIBUTION = (
    "This split is the in-distribution temporal test set, not a shift axis: same sites, same "
    "instruments, a change in what is labelled."
)

#: ADR-0022 §1, the confound the evaluation cannot remove, measured at F4 and not re-measured here.
CARE_CONFOUND = "0 of 749,847 pretraining windows carry any CARE farm's missing-channel pattern"

#: The CARE farms, as the ``turbine_id`` prefixes of the window index spell them.
CARE_FARMS = ("farm_a", "farm_b", "farm_c")

#: Hill of Towie's base rate on its 12,000-window subsample (ADR-0021, ``gate_check_v0.yaml``).
HELD_OUT_BASE_RATE = 0.03325

#: The registered CARE positive rate, to the decimals ADR-0022 §3 states it to.
CARE_BASE_RATE = 0.001254


# =====================================================================================
# the configuration
# =====================================================================================


class TemporalAxisConfig(StrictModel):
    """ADR-0022 §2: the in-distribution temporal test split at the training sites.

    Attributes:
        shard_keys: The test shards pooled.
        cut: The split cut, ``time.val_until`` of the split specification.
        windows: Windows at the registered stride.
        positives: Positive windows at that stride.
        base_rate: The scored set's own positive rate, to four decimals.
        blocks: Occupied two-day blocks.
        positive_blocks: Blocks holding a positive.
        without_messages_label: The window-index column without the anemometer-defect events.
        without_messages_windows: Windows known under that label, at the same stride.
        without_messages_positives: Positive windows under that label.
    """

    shard_keys: list[str] = Field(min_length=1)
    cut: str
    windows: int = Field(gt=0)
    positives: int = Field(gt=0)
    base_rate: float = Field(gt=0.0, lt=1.0)
    blocks: int = Field(gt=0)
    positive_blocks: int = Field(gt=0)
    without_messages_label: str
    without_messages_windows: int = Field(gt=0)
    without_messages_positives: int = Field(gt=0)


class CareAxisConfig(StrictModel):
    """ADR-0022 §1 and §3: the whole CARE evaluation set, thinned uniformly.

    Attributes:
        shard_keys: The CARE test shard.
        events: Labelled anomaly events, the independent unit.
        full_windows: Known windows at stride 1.
        full_positives: Positive windows at stride 1.
        full_blocks: Occupied two-day blocks at stride 1.
        full_positive_blocks: Blocks holding a positive at stride 1.
        windows: Windows at the registered stride.
        positives: Positive windows at that stride.
        base_rate: The scored set's own positive rate, to four decimals.
        blocks: Blocks the thinning covers.
        positive_blocks: Positive blocks the thinning covers.
    """

    shard_keys: list[str] = Field(min_length=1)
    events: int = Field(gt=0)
    full_windows: int = Field(gt=0)
    full_positives: int = Field(gt=0)
    full_blocks: int = Field(gt=0)
    full_positive_blocks: int = Field(gt=0)
    windows: int = Field(gt=0)
    positives: int = Field(gt=0)
    base_rate: float = Field(gt=0.0, lt=1.0)
    blocks: int = Field(gt=0)
    positive_blocks: int = Field(gt=0)


class AxesConfig(StrictModel):
    """The two candidate axes.

    Attributes:
        temporal: The in-distribution temporal split.
        care: The CARE evaluation set.
    """

    temporal: TemporalAxisConfig
    care: CareAxisConfig


class CheckpointsConfig(StrictModel):
    """ADR-0022 §5 as amended: which checkpoint gates, and which is reported beside it.

    Attributes:
        gating: The checkpoint the rule reads, ``final_step`` or ``selected``.
        reported: Checkpoints scored beside it and reported, gating nothing.
    """

    gating: str
    reported: list[str] = Field(min_length=1)


class AxisGateConfig(StrictModel):
    """Top level of ``configs/eval/axis_gate_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        shards: The shard set in force.
        splits_config: The split specification the shards were built with.
        label: The label every probe is trained and scored on.
        stride: The registered thinning of both axes.
        base_rate_source: Where the rule's chance level comes from; ``scored_set``.
        bootstrap: ADR-0021's interval, unchanged.
        seeds: The full-budget ``tel_only`` seeds.
        seeds_required: How many must clear for an axis to be evaluable.
        checkpoints: Which checkpoint gates and which is reported.
        axes: The two candidate axes and their measured counts.
    """

    version: int = 0
    shards: str
    splits_config: str
    label: str
    stride: int = Field(gt=0)
    base_rate_source: str
    bootstrap: BootstrapConfig
    seeds: list[int] = Field(min_length=1)
    seeds_required: int = Field(gt=0)
    checkpoints: CheckpointsConfig
    axes: AxesConfig


# =====================================================================================
# what the window index says, re-counted before anything is scored
# =====================================================================================


@dataclass(frozen=True)
class IndexCounts:
    """One axis's counts, read from the window index with no model loaded.

    Attributes:
        windows: Admissible windows at the stride.
        positives: Positive windows.
        blocks: Occupied two-day blocks.
        positive_blocks: Blocks holding a positive.
    """

    windows: int
    positives: int
    blocks: int
    positive_blocks: int

    @property
    def base_rate(self) -> float:
        """The scored set's own positive rate."""
        return self.positives / self.windows


def index_counts(
    shards: ShardSet, keys: list[str], label: str, stride: int, block_steps: int
) -> IndexCounts:
    """Count one axis's windows, positives and blocks from the window index alone.

    Args:
        shards: The shard set in force.
        keys: The shard keys pooled.
        label: The label column, whose ``_known`` companion decides admissibility.
        stride: Keep every ``stride``-th admissible window.
        block_steps: Steps a resampled block spans.

    Returns:
        The counts.
    """
    sets = [load_windows(shards, key, stride=stride, label=label) for key in keys]
    ends = np.concatenate([s.ends for s in sets])
    which = np.concatenate([np.full(len(s), i, dtype=np.int64) for i, s in enumerate(sets)])
    labels = np.concatenate([s.labels for s in sets]) > 0.5
    blocks = window_blocks(ends, which, block_steps)
    return IndexCounts(
        windows=int(ends.size),
        positives=int(labels.sum()),
        blocks=int(np.unique(blocks).size),
        positive_blocks=int(np.unique(blocks[labels]).size),
    )


def check_care_counts(care: CareAxisConfig, thinned: IndexCounts, full: IndexCounts) -> None:
    """Refuse to score CARE unless the index still holds ADR-0022's Part B numbers.

    Args:
        care: The registered CARE counts.
        thinned: The counts measured at the registered stride.
        full: The counts measured at stride 1.

    Raises:
        ValueError: If any registered count differs from the measurement, naming each one.
    """
    checked: dict[str, tuple[float, float]] = {
        "windows": (care.windows, thinned.windows),
        "positives": (care.positives, thinned.positives),
        "base rate (6 dp)": (CARE_BASE_RATE, round(thinned.base_rate, 6)),
        "base rate (4 dp)": (care.base_rate, round(thinned.base_rate, 4)),
        "blocks covered": (care.blocks, thinned.blocks),
        "positive blocks covered": (care.positive_blocks, thinned.positive_blocks),
        "windows at stride 1": (care.full_windows, full.windows),
        "positives at stride 1": (care.full_positives, full.positives),
        "blocks at stride 1": (care.full_blocks, full.blocks),
        "positive blocks at stride 1": (care.full_positive_blocks, full.positive_blocks),
    }
    wrong = [
        f"{name}: registered {want}, measured {got}"
        for name, (want, got) in checked.items()
        if want != got
    ]
    if wrong:
        raise ValueError(
            "the CARE window index no longer holds ADR-0022 §1 and §3, so nothing is scored: "
            + "; ".join(wrong)
        )


def index_rows(shards: ShardSet, key: str, label: str, stride: int, columns: list[str]) -> Any:
    """One shard's window-index rows, in the order an unshuffled scoring pass reads them.

    ``load_windows`` admits a window on ``<label>_known`` and only then strides, so any other
    column has to be taken for exactly those rows rather than for its own admissible set: only
    then does it line up with logits already on disk.

    Args:
        shards: The shard set in force.
        key: The shard key.
        label: The label the windows were scored under.
        stride: The stride they were taken at.
        columns: Index columns to return, besides the ones this function needs.

    Returns:
        The rows, as a pandas frame carrying ``columns`` and ``end_step``.
    """
    record = shards.files()[key]
    wanted = list(dict.fromkeys(["end_step", f"{label}_known", *columns]))
    frame = pq.read_table(shards.root / str(record["windows"]), columns=wanted).to_pandas()
    frame = frame[frame[f"{label}_known"].to_numpy()]
    return frame.iloc[np.arange(0, len(frame), stride)]


def care_window_farms(shards: ShardSet, key: str, label: str, stride: int) -> np.ndarray:
    """Per scored CARE window, its farm, in the order a scoring pass reads them.

    The CARE shard is one window set, so ``ScoredWindows.which`` cannot separate the farms.
    The farm is the ``turbine_id`` prefix the window index carries.

    Args:
        shards: The shard set in force.
        key: The CARE shard key.
        label: The label the windows were scored under.
        stride: The stride they were taken at.

    Returns:
        Per window, its farm.
    """
    frame = index_rows(shards, key, label, stride, ["turbine_id"])
    farms: np.ndarray = frame["turbine_id"].str.split(":").str[0].to_numpy()
    return farms


def window_steps(shards: ShardSet, keys: list[str], label: str, stride: int) -> np.ndarray:
    """Per scored window, its end step, pooled over the shards in the order they were scored.

    Args:
        shards: The shard set in force.
        keys: The shard keys, in scoring order.
        label: The label the windows were scored under.
        stride: The stride they were taken at.

    Returns:
        Per window, its end step.
    """
    return np.concatenate(
        [index_rows(shards, key, label, stride, [])["end_step"].to_numpy(np.int64) for key in keys]
    )


def relabelled(
    shards: ShardSet, keys: list[str], label: str, other: str, stride: int
) -> tuple[np.ndarray, np.ndarray]:
    """The same scored windows under a second label, for the reported variant of an axis.

    Args:
        shards: The shard set in force.
        keys: The shard keys, in scoring order.
        label: The label the windows were scored under.
        other: The second label's column.
        stride: The stride the windows were taken at.

    Returns:
        Per scored window: the second label, and whether that label is known there.
    """
    frames = [index_rows(shards, key, label, stride, [other, f"{other}_known"]) for key in keys]
    labels = np.concatenate([f[other].to_numpy() for f in frames])
    known = np.concatenate([f[f"{other}_known"].to_numpy() for f in frames])
    return labels, known


# =====================================================================================
# which core channels a farm does not have
# =====================================================================================


@dataclass(frozen=True)
class ChannelAbsence:
    """One group of windows, and how much of its value stream is ``<nan>``.

    Attributes:
        group: The farm or source measured.
        windows: Windows in the group.
        absent: Core channels that read ``<nan>`` on every step the group covers.
        nan_share_steps: ``<nan>`` share over the steps covered, each counted once. This is the
            basis of the F4 figures in ``data/cards/care.md`` and in ADR-0022 §1.
        nan_share_windows: ``<nan>`` share over the scored windows, overlapping context counted
            as the scoring counts it: the share of the tokens the metric beside it read.
    """

    group: str
    windows: int
    absent: tuple[str, ...]
    nan_share_steps: float
    nan_share_windows: float


def channel_absence(
    shards: ShardSet, key: str, groups: dict[str, tuple[np.ndarray, np.ndarray]]
) -> dict[str, ChannelAbsence]:
    """Measure each group's ``<nan>`` share and its permanently absent core channels.

    A window's value tokens are its steps' bin tokens, ``<sep>`` excluded, so a window's
    ``<nan>`` count is a difference of cumulative per-step counts: exact, and without a Python
    loop over four hundred thousand windows.

    Args:
        shards: The shard set in force.
        key: The shard key whose token stream is read.
        groups: Per group, its windows' first and last steps, the last inclusive.

    Returns:
        Per group, its measurement.
    """
    record = shards.files()[key]
    steps, per_step = int(record["steps"]), shards.tokens_per_step
    nan_id = int(dict(shards.manifest["specials"])["<nan>"])
    names = [str(name) for name in shards.manifest["step"][1:]]
    tokens = np.memmap(
        shards.root / str(record["tokens"]), dtype=np.uint16, mode="r", shape=(steps * per_step,)
    ).reshape(steps, per_step)
    missing = np.asarray(tokens[:, 1:]) == nan_id
    covered: dict[str, np.ndarray] = {}
    for group, (starts, ends) in groups.items():
        edges = np.zeros(steps + 1, dtype=np.int64)
        np.add.at(edges, starts, 1)
        np.add.at(edges, ends + 1, -1)
        covered[group] = np.cumsum(edges)[:steps] > 0
    nan_steps = dict.fromkeys(groups, 0)
    nan_windows = dict.fromkeys(groups, 0)
    absent: dict[str, list[str]] = {group: [] for group in groups}
    for index, name in enumerate(names):
        column = missing[:, index]
        cumulative = np.concatenate([[0], np.cumsum(column, dtype=np.int64)])
        for group, (starts, ends) in groups.items():
            nan_steps[group] += int(column[covered[group]].sum())
            counted = int((cumulative[ends + 1] - cumulative[starts]).sum())
            nan_windows[group] += counted
            if counted == int((ends + 1 - starts).sum()):
                absent[group].append(name)
    channels = len(names)
    return {
        group: ChannelAbsence(
            group=group,
            windows=int(starts.size),
            absent=tuple(absent[group]),
            nan_share_steps=nan_steps[group] / (int(covered[group].sum()) * channels),
            nan_share_windows=nan_windows[group] / (int((ends + 1 - starts).sum()) * channels),
        )
        for group, (starts, ends) in groups.items()
    }


# =====================================================================================
# the checkpoints scored
# =====================================================================================


@dataclass(frozen=True)
class ProbeCheckpoints:
    """One trained seed's two probe checkpoints, as F3 left them on disk.

    Attributes:
        seed: The pretraining seed.
        name: The probe's file stem, such as ``S2_trained_seed1``.
        selected_step: The step its validation measurement selected.
        last_step: The last probe step, which the final-step checkpoint is at.
        selected: The selected checkpoint's saved state.
        final: The final-step checkpoint's saved state; the same file when the two coincide.
        prior_offset: The constant reading its logits at the natural rate.
    """

    seed: int
    name: str
    selected_step: int
    last_step: int
    selected: Path
    final: Path
    prior_offset: float

    @property
    def identical(self) -> bool:
        """Whether the selected checkpoint **is** the final-step checkpoint."""
        return self.selected_step == self.last_step

    def state(self, role: str) -> Path:
        """The saved state one role reads.

        Args:
            role: ``final_step`` or ``selected``.

        Returns:
            The checkpoint file.

        Raises:
            ValueError: If the role is neither of the two ADR-0022 §5 names.
        """
        if role == FIXED_FINAL:
            return self.final
        if role == SELECTED:
            return self.selected
        raise ValueError(f"unknown checkpoint role {role!r}: expected {FIXED_FINAL} or {SELECTED}")

    def stem(self, role: str, stride: int) -> str:
        """The CARE score file's stem for one of the two roles.

        F3 named a probe's final-step scores with a ``_final`` infix and wrote none at all for a
        probe that selected its last step. This follows both, so the two checkpoints of such a
        seed read one file rather than scoring the same weights twice.

        Args:
            role: ``final_step`` or ``selected``.
            stride: The registered thinning.

        Returns:
            The file stem.
        """
        infix = "_final" if self.state(role) == self.final and not self.identical else ""
        return f"{self.name}{infix}_care_stride{stride}_scores"


def read_probes(paths: ProjectPaths, config: SeedReplicationConfig, seed: int) -> ProbeCheckpoints:
    """Locate one trained seed's selected and final-step probe states.

    Seed 1's selected probe is G3's, saved under the cadence directory; F3 saved the others. A
    probe that selected its last step has one state and no separate final file, and that
    agreement is checked rather than assumed, because a missing file would otherwise be read
    silently as the two checkpoints coinciding.

    Args:
        paths: Resolved project paths.
        config: The F3 configuration.
        seed: The pretraining seed.

    Returns:
        The seed's two checkpoints.

    Raises:
        FileNotFoundError: If a record or a probe state F3 must have written is missing.
        ValueError: If the final-step file disagrees with the record's selected step.
    """
    gate = load_config(paths.repo_root / config.gate_config, GateCheckConfig)
    cadence = load_config(paths.repo_root / config.cadence_config, ProbeCadenceConfig)
    out_dir = paths.checkpoints_dir / f"seed_replication_v{config.version}_{config_hash(config)}"
    cadence_dir = paths.checkpoints_dir / f"probe_cadence_v{cadence.version}_{config_hash(cadence)}"
    name = f"{gate.rung}_trained_seed{seed}"
    record_file = out_dir / f"{name}_probe.json"
    if not record_file.is_file():
        raise FileNotFoundError(f"{record_file} is missing; F3's outputs are not on this machine")
    record: dict[str, Any] = json.loads(record_file.read_text(encoding="utf-8"))
    selected_step = int(record["selected"][0])
    last_step = max(int(step) for step, _ in record["history"])
    selected = (cadence_dir if seed == gate.seed else out_dir) / f"{name}_probe.pt"
    if not selected.is_file():
        raise FileNotFoundError(f"{selected} is missing; F3's outputs are not on this machine")
    final = out_dir / f"{name}_final_probe.pt"
    if selected_step == last_step:
        if final.is_file():
            raise ValueError(f"{name} selected the last step ({last_step}) yet {final.name} exists")
        final = selected
    elif not final.is_file():
        raise ValueError(
            f"{name} selected step {selected_step} of {last_step}, so {final.name} must exist"
        )
    return ProbeCheckpoints(
        seed=seed,
        name=name,
        selected_step=selected_step,
        last_step=last_step,
        selected=selected,
        final=final,
        prior_offset=float(record["prior_offset"]),
    )


# =====================================================================================
# the rule
# =====================================================================================


@dataclass(frozen=True)
class AxisVerdict:
    """ADR-0022 §4, applied to one axis on the gating checkpoint.

    Attributes:
        axis: The axis judged.
        evaluable: Whether it can separate the model from chance.
        clearing: The seeds whose lower bound is strictly above the axis's own base rate.
        seeds: Every seed read.
        required: How many had to clear.
        reason: One sentence saying why.
    """

    axis: str
    evaluable: bool
    clearing: tuple[int, ...]
    seeds: tuple[int, ...]
    required: int
    reason: str


def decide_axis(axis: str, verdicts: dict[int, GateVerdict], required: int) -> AxisVerdict:
    """Apply ADR-0022 §4: evaluable on at least ``required`` of the seeds read.

    Each seed's own verdict is ADR-0021's, which is strict: a lower bound equal to the base rate
    does not clear, and an interval whose discarded share is above the configured maximum does
    not clear whatever its bounds say.

    Args:
        axis: The axis judged, for the record.
        verdicts: Per seed, ADR-0021's verdict on that seed's gating interval.
        required: How many seeds must clear.

    Returns:
        The axis's verdict.

    Raises:
        ValueError: If no seed was read, or fewer seeds were read than must clear.
    """
    if not verdicts:
        raise ValueError(f"the rule needs at least one seed's interval on {axis}")
    if len(verdicts) < required:
        raise ValueError(
            f"{axis} was read on {len(verdicts)} seed(s), fewer than the {required} that must clear"
        )
    seeds = tuple(sorted(verdicts))
    clearing = tuple(seed for seed in seeds if verdicts[seed].evaluable)
    evaluable = len(clearing) >= required
    held = ", ".join(str(seed) for seed in clearing) if clearing else "no seed"
    return AxisVerdict(
        axis=axis,
        evaluable=evaluable,
        clearing=clearing,
        seeds=seeds,
        required=required,
        reason=(
            f"the lower bound is strictly above the scored-set base rate on {len(clearing)} of "
            f"{len(seeds)} seeds ({held}), {'at least' if evaluable else 'fewer than'} the "
            f"{required} the rule requires: {'EVALUABLE' if evaluable else 'NOT EVALUABLE'}"
        ),
    )


@dataclass(frozen=True)
class Assignment:
    """The hypothesis assignment ADR-0022 §4 produces from the two verdicts.

    Attributes:
        h1: The axis H1 is evaluated on, or ``None``.
        h2: The axis H2 is evaluated on, or ``None``.
        stop: Whether the rule says to stop and report.
        sentence: The assignment in the record's own words.
    """

    h1: str | None
    h2: str | None
    stop: bool
    sentence: str


def assign_hypotheses(care: AxisVerdict, temporal: AxisVerdict) -> Assignment:
    """Apply ADR-0022 §4's four branches to the two axis verdicts.

    Args:
        care: The CARE verdict.
        temporal: The temporal split's verdict.

    Returns:
        The assignment.
    """
    if care.evaluable and temporal.evaluable:
        return Assignment(
            h1="care",
            h2="temporal",
            stop=False,
            sentence="Both axes are evaluable: H1 is evaluated on CARE, H2 on the training-site "
            "temporal test split, because CARE carries no status strings and cannot exercise "
            "the text pathway.",
        )
    if temporal.evaluable:
        return Assignment(
            h1="temporal",
            h2="temporal",
            stop=False,
            sentence="Only the temporal split is evaluable: it carries both hypotheses, and CARE "
            "is reported as a second negative beside Hill of Towie.",
        )
    if care.evaluable:
        return Assignment(
            h1="care",
            h2=None,
            stop=False,
            sentence="Only CARE is evaluable: H1 is evaluated there, and H2 is reported as "
            "untestable on an evaluable shift axis.",
        )
    return Assignment(
        h1=None, h2=None, stop=True, sentence="Neither axis is evaluable: stop and report."
    )


# =====================================================================================
# the record, and reading it back
# =====================================================================================


@dataclass(frozen=True)
class AxisRow:
    """One cell of the axis x seed x checkpoint table.

    Attributes:
        axis: ``care`` or ``temporal``.
        seed: The pretraining seed.
        checkpoint: ``final_step`` or ``selected``.
        gating: Whether this row is the one the rule reads.
        interval: The block-bootstrap interval on the axis's own windows.
        verdict: ADR-0021's rule applied to it.
    """

    axis: str
    seed: int
    checkpoint: str
    gating: bool
    interval: AuprcInterval
    verdict: GateVerdict


@dataclass(frozen=True)
class ReportedRow:
    """One row that is reported and decides nothing.

    Attributes:
        group: What was scored: a CARE farm, the anemometer-defect variant, the held-out site.
        axis: The axis it belongs beside.
        seed: The pretraining seed.
        checkpoint: ``final_step`` or ``selected``.
        base_rate: The line the row would have had to clear, for orientation only.
        interval: The block-bootstrap interval.
        note: What the row is, in words.
    """

    group: str
    axis: str
    seed: int
    checkpoint: str
    base_rate: float
    interval: AuprcInterval
    note: str


@dataclass(frozen=True)
class AxisGateRecord:
    """Everything F5 measured, in the shape the report and the JSON both read.

    Attributes:
        config_hash: The axis-gate configuration's hash.
        gating: The checkpoint role the rule read.
        rows: The axis x seed x checkpoint table.
        reported: The per-farm, variant and held-out rows.
        verdicts: Per axis, ADR-0022 §4's verdict on the gating checkpoint.
        reported_verdicts: Per axis, the same rule on the reported checkpoint; it gates nothing.
        assignment: The hypothesis assignment the rule produces.
        absence: Per group, its absent core channels and its two ``<nan>`` shares.
        counts: Per axis, the counts re-measured from the window index.
        without_messages: The anemometer-defect variant's origin, measured.
        seconds: Wall clock of this invocation.
        gpu_seconds: What the CARE scorings cost on the GPU, summed over the invocations that
            paid for them, from the timing written beside each set of scores.
        computed: CARE scorings this invocation paid for.
        resumed: CARE scorings it read back from disk.
    """

    config_hash: str
    gating: str
    rows: tuple[AxisRow, ...]
    reported: tuple[ReportedRow, ...]
    verdicts: dict[str, AxisVerdict]
    reported_verdicts: dict[str, AxisVerdict]
    assignment: Assignment
    absence: dict[str, ChannelAbsence]
    counts: dict[str, IndexCounts]
    without_messages: dict[str, Any]
    seconds: float
    gpu_seconds: float
    computed: tuple[str, ...]
    resumed: tuple[str, ...]


def record_payload(record: AxisGateRecord) -> dict[str, Any]:
    """Serialize the record to the JSON the report is written beside.

    Args:
        record: What F5 measured.

    Returns:
        A JSON-serializable mapping.
    """
    return {
        "config_hash": record.config_hash,
        "gating": record.gating,
        "rows": [asdict(row) for row in record.rows],
        "reported": [asdict(row) for row in record.reported],
        "verdicts": {axis: asdict(v) for axis, v in record.verdicts.items()},
        "reported_verdicts": {axis: asdict(v) for axis, v in record.reported_verdicts.items()},
        "assignment": asdict(record.assignment),
        "absence": {group: asdict(a) for group, a in record.absence.items()},
        "counts": {axis: asdict(c) for axis, c in record.counts.items()},
        "without_messages": record.without_messages,
        "seconds": record.seconds,
        "gpu_seconds": record.gpu_seconds,
        "computed": list(record.computed),
        "resumed": list(record.resumed),
    }


def load_record(payload: dict[str, Any]) -> AxisGateRecord:
    """Read a record back from the JSON ``record_payload`` wrote.

    Args:
        payload: The parsed JSON.

    Returns:
        The record, with every interval and verdict back in its own type.
    """
    return AxisGateRecord(
        config_hash=str(payload["config_hash"]),
        gating=str(payload["gating"]),
        rows=tuple(
            AxisRow(
                axis=str(row["axis"]),
                seed=int(row["seed"]),
                checkpoint=str(row["checkpoint"]),
                gating=bool(row["gating"]),
                interval=AuprcInterval(**row["interval"]),
                verdict=GateVerdict(**row["verdict"]),
            )
            for row in payload["rows"]
        ),
        reported=tuple(
            ReportedRow(
                group=str(row["group"]),
                axis=str(row["axis"]),
                seed=int(row["seed"]),
                checkpoint=str(row["checkpoint"]),
                base_rate=float(row["base_rate"]),
                interval=AuprcInterval(**row["interval"]),
                note=str(row["note"]),
            )
            for row in payload["reported"]
        ),
        verdicts={
            axis: AxisVerdict(**{**v, "clearing": tuple(v["clearing"]), "seeds": tuple(v["seeds"])})
            for axis, v in payload["verdicts"].items()
        },
        reported_verdicts={
            axis: AxisVerdict(**{**v, "clearing": tuple(v["clearing"]), "seeds": tuple(v["seeds"])})
            for axis, v in payload["reported_verdicts"].items()
        },
        assignment=Assignment(**payload["assignment"]),
        absence={
            group: ChannelAbsence(**{**a, "absent": tuple(a["absent"])})
            for group, a in payload["absence"].items()
        },
        counts={axis: IndexCounts(**c) for axis, c in payload["counts"].items()},
        without_messages=dict(payload["without_messages"]),
        seconds=float(payload["seconds"]),
        gpu_seconds=float(payload["gpu_seconds"]),
        computed=tuple(str(name) for name in payload["computed"]),
        resumed=tuple(str(name) for name in payload["resumed"]),
    )


# =====================================================================================
# intervals on a subset of scored windows
# =====================================================================================


def masked_interval(
    scored: ScoredWindows,
    mask: np.ndarray,
    bootstrap: BootstrapConfig,
    labels: np.ndarray | None = None,
) -> AuprcInterval:
    """ADR-0021's block bootstrap over an arbitrary subset of one scoring's windows.

    ``ScoredWindows.interval`` selects by source, which cannot separate the three CARE farms of
    one shard nor restrict a split to the windows a second label is known on. This takes the
    mask directly and is otherwise the same interval: the same blocks, seed and coverage.

    Args:
        scored: The scoring.
        mask: Per window, whether it is in the subset.
        bootstrap: Blocks, replicates, seed and coverage.
        labels: Labels to read instead of the scoring's own, for a relabelled variant.

    Returns:
        The interval.
    """
    truth = (scored.labels if labels is None else labels)[mask]
    blocks = window_blocks(scored.ends[mask], scored.which[mask], bootstrap.block_steps)
    return bootstrap_auprc(
        scored.logits[mask] + scored.prior_offset,
        truth,
        blocks,
        bootstrap.replicates,
        bootstrap.seed,
        bootstrap.confidence,
    )


# =====================================================================================
# the run
# =====================================================================================


def run_axis_gate(
    paths: ProjectPaths,
    config_path: Path,
    f3_config_path: Path,
    device_name: str | None = None,
) -> tuple[Path, Path]:
    """Score CARE, read F3's saved temporal scores, apply ADR-0022 §4 and write the report.

    Args:
        paths: Resolved project paths.
        config_path: The axis-gate configuration.
        f3_config_path: The F3 configuration, which names the checkpoints.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The report and its JSON record.

    Raises:
        ValueError: If the configuration's gating role is not one of ADR-0022 §5's two names,
            if the CARE index no longer holds ADR-0022's counts, or if a saved scoring does not
            line up with the window index it is attributed through.
    """
    config = load_config(config_path, AxisGateConfig)
    f3 = load_config(f3_config_path, SeedReplicationConfig)
    gate = load_config(paths.repo_root / f3.gate_config, GateCheckConfig)
    bootstrap, stride, label = config.bootstrap, config.stride, config.label
    roles = [config.checkpoints.gating, *config.checkpoints.reported]
    if set(roles) != {FIXED_FINAL, SELECTED}:
        raise ValueError(f"the gating and reported roles must be ADR-0022 §5's pair, got {roles}")
    out_dir = paths.checkpoints_dir / f"axis_gate_v{config.version}_{config_hash(config)}"
    f3_dir = paths.checkpoints_dir / f"seed_replication_v{f3.version}_{config_hash(f3)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    shards = ShardSet.load(paths.repo_root / config.shards)
    care_key = config.axes.care.shard_keys[0]
    temporal_keys = config.axes.temporal.shard_keys
    probes = {seed: read_probes(paths, f3, seed) for seed in config.seeds}

    # -- the index, re-counted before a single window is scored ------------------------------
    logger.info("re-counting the CARE index at stride %d and at stride 1", stride)
    thinned = index_counts(shards, [care_key], label, stride, bootstrap.block_steps)
    full = index_counts(shards, [care_key], label, 1, bootstrap.block_steps)
    check_care_counts(config.axes.care, thinned, full)
    logger.info(
        "CARE holds ADR-0022's numbers: %d windows, %d positive, rate %.6f, %d of %d blocks, "
        "%d of %d positive blocks",
        thinned.windows,
        thinned.positives,
        thinned.base_rate,
        thinned.blocks,
        full.blocks,
        thinned.positive_blocks,
        full.positive_blocks,
    )
    temporal_counts = index_counts(shards, temporal_keys, label, stride, bootstrap.block_steps)

    # -- CARE, scored once per distinct checkpoint --------------------------------------------
    opened: list[ProbeInputs] = []
    built: list[SplitEval] = []
    computed: list[str] = []
    resumed: list[str] = []

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

    def care_split() -> SplitEval:
        if not built:
            evaluation = inputs().ladder.evaluation
            logger.info("opening the CARE evaluation windows at stride %d", stride)
            built.append(
                build_split(
                    inputs().telemetry,
                    "test",
                    None,
                    stride,
                    evaluation.seed,
                    evaluation.batch_windows,
                    label,
                    sources=["care"],
                )
            )
        return built[0]

    care: dict[tuple[int, str], ScoredWindows] = {}
    # The ledger counts distinct scorings, not (seed, role) pairs. A seed whose two checkpoints
    # coincide has one set of scores under both role names, and counting that second read as a
    # resume would claim a saving this invocation never made.
    by_stem: dict[str, ScoredWindows] = {}
    for seed in config.seeds:
        probe = probes[seed]
        for role in roles:
            path = out_dir / f"{probe.stem(role, stride)}.npz"
            timing = path.with_suffix(".timing.json")
            if path.stem in by_stem:
                care[seed, role] = by_stem[path.stem]
                continue
            if path.exists():
                resumed.append(path.stem)
                care[seed, role] = by_stem[path.stem] = ScoredWindows.load(path)
                continue
            logger.info("=== scoring CARE with %s at its %s checkpoint ===", probe.name, role)
            scoring = time.perf_counter()
            care[seed, role] = by_stem[path.stem] = save_split_scores(
                path,
                score_saved_probe(probe.state(role), f3.design, inputs(), care_split()),
                care_split(),
                probe.prior_offset,
            )
            # Written beside the scores so that a later invocation, which resumes them all and
            # therefore spends no GPU time itself, can still report what the scoring cost.
            timing.write_text(
                json.dumps({"seconds": time.perf_counter() - scoring}, indent=1) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            computed.append(path.stem)
    gpu_seconds = sum(
        float(json.loads(f.read_text(encoding="utf-8"))["seconds"])
        for f in sorted(out_dir.glob("*.timing.json"))
    )

    # -- the temporal split and Hill of Towie, read, never re-scored ---------------------------
    temporal: dict[tuple[int, str], ScoredWindows] = {}
    held_out: dict[int, ScoredWindows] = {}
    cadence = load_config(paths.repo_root / f3.cadence_config, ProbeCadenceConfig)
    cadence_dir = paths.checkpoints_dir / f"probe_cadence_v{cadence.version}_{config_hash(cadence)}"
    for seed in config.seeds:
        probe = probes[seed]
        for role in roles:
            infix = "_final" if role == FIXED_FINAL and not probe.identical else ""
            temporal[seed, role] = ScoredWindows.load(
                f3_dir / f"{probe.name}{infix}_stride{stride}_scores.npz"
            )
        directory = cadence_dir if seed == gate.seed else f3_dir
        held_out[seed] = ScoredWindows.load(directory / f"{probe.name}_test_scores.npz")

    # -- attribution: the CARE farms, and the anemometer-defect variant ------------------------
    reference = care[config.seeds[0], config.checkpoints.gating]
    farms = care_window_farms(shards, care_key, label, stride)
    if not np.array_equal(window_steps(shards, [care_key], label, stride), reference.ends):
        raise ValueError("the CARE index rows do not line up with the saved CARE scores")
    temporal_reference = temporal[config.seeds[0], config.checkpoints.gating]
    if not np.array_equal(
        window_steps(shards, temporal_keys, label, stride), temporal_reference.ends
    ):
        raise ValueError("the index rows do not line up with F3's saved stride-12 scores")
    without_label = config.axes.temporal.without_messages_label
    without, without_known = relabelled(shards, temporal_keys, label, without_label, stride)
    care_without, care_without_known = relabelled(shards, [care_key], label, without_label, stride)
    without_messages = {
        "label": without_label,
        "category": "equipment_fault",
        "message": "Anemometer defect",
        "sources": ["kelmarsh", "penmanshiel"],
        "named_in": "configs/data/splits_v3.yaml, report_without_messages",
        "temporal_windows": int(without_known.sum()),
        "temporal_positives": int(without[without_known].sum()),
        "care_label_source": "event_info, the single fault label `anomaly`",
        "care_events_removed": int(
            reference.labels.astype(bool).sum() - care_without[care_without_known].sum()
        ),
        "care_windows_lost": int(reference.labels.size - care_without_known.sum()),
        "care_positives_lost": int(
            reference.labels.astype(bool).sum() - care_without[care_without_known].sum()
        ),
        "care_farms_affected": [],
    }

    # -- the <nan> shares and the absent core channels ------------------------------------------
    absence_file = out_dir / "channel_absence.json"
    if absence_file.exists():
        absence = {
            group: ChannelAbsence(**{**value, "absent": tuple(value["absent"])})
            for group, value in json.loads(absence_file.read_text(encoding="utf-8")).items()
        }
    else:
        logger.info("measuring the <nan> share and the absent core channels per CARE farm")
        care_frame = index_rows(shards, care_key, label, stride, ["start_step"])
        starts = care_frame["start_step"].to_numpy(np.int64)
        groups = {"care": (starts, reference.ends)} | {
            farm: (starts[farms == farm], reference.ends[farms == farm]) for farm in CARE_FARMS
        }
        absence = channel_absence(shards, care_key, groups)
        for key in temporal_keys:
            frame = index_rows(shards, key, label, stride, ["start_step"])
            absence |= channel_absence(
                shards,
                key,
                {
                    key.split("__")[0]: (
                        frame["start_step"].to_numpy(np.int64),
                        frame["end_step"].to_numpy(np.int64),
                    )
                },
            )
        absence_file.write_text(
            json.dumps({g: asdict(a) for g, a in absence.items()}, indent=1) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    # -- the intervals, per seed, written whole as each seed completes ---------------------------
    rows: list[AxisRow] = []
    reported: list[ReportedRow] = []
    for seed in config.seeds:
        cache = out_dir / f"bootstrap_seed{seed}.json"
        if cache.exists():
            logger.info("seed %d's intervals are on disk; reading them", seed)
            saved = json.loads(cache.read_text(encoding="utf-8"))
        else:
            logger.info("bootstrapping seed %d on both axes, both checkpoints", seed)
            seed_rows: list[AxisRow] = []
            seed_reported: list[ReportedRow] = []
            memo: dict[tuple[str, str], AuprcInterval] = {}
            # A seed that selected its last step has one set of weights under two role names.
            # Bootstrapping it twice would spend minutes reproducing a number bit for bit, so the
            # two roles share one key and the rows still report both.
            for role in roles:
                held = config.checkpoints.gating if probes[seed].identical else role
                for axis, scored, sources in (
                    ("care", care[seed, role], ["care"]),
                    ("temporal", temporal[seed, role], f3.pooled_sources),
                ):
                    if (held, axis) not in memo:
                        memo[held, axis] = scored.interval(sources, bootstrap)
                    interval = memo[held, axis]
                    seed_rows.append(
                        AxisRow(
                            axis=axis,
                            seed=seed,
                            checkpoint=role,
                            gating=role == config.checkpoints.gating,
                            interval=interval,
                            verdict=decide_evaluable(interval, bootstrap.max_discarded_share),
                        )
                    )
                for farm in CARE_FARMS:
                    mask = farms == farm
                    if (held, farm) not in memo:
                        memo[held, farm] = masked_interval(care[seed, role], mask, bootstrap)
                    seed_reported.append(
                        ReportedRow(
                            group=farm,
                            axis="care",
                            seed=seed,
                            checkpoint=role,
                            base_rate=float(care[seed, role].labels[mask].mean()),
                            interval=memo[held, farm],
                            note=f"one CARE farm; the rule is applied to the pooled CARE set, "
                            f"not here. <nan> share {absence[farm].nan_share_steps:.2%}",
                        )
                    )
                if (held, "without") not in memo:
                    memo[held, "without"] = masked_interval(
                        temporal[seed, role], without_known, bootstrap, without.astype(bool)
                    )
                seed_reported.append(
                    ReportedRow(
                        group="without_anemometer_defect",
                        axis="temporal",
                        seed=seed,
                        checkpoint=role,
                        base_rate=float(without[without_known].mean()),
                        interval=memo[held, "without"],
                        note=f"the temporal split relabelled with {without_label}; "
                        + ADR_0009_CAVEAT
                        + " "
                        + IN_DISTRIBUTION,
                    )
                )
            seed_reported.append(
                ReportedRow(
                    group=gate.held_out_source,
                    axis="held_out",
                    seed=seed,
                    checkpoint=SELECTED,
                    base_rate=HELD_OUT_BASE_RATE,
                    interval=held_out[seed].interval([gate.held_out_source], bootstrap),
                    note="F3's 12,000-window subsample, read not re-scored; reported for "
                    "comparison and demoted by ADR-0021 and ADR-0022 §6",
                )
            )
            saved = {
                "rows": [asdict(row) for row in seed_rows],
                "reported": [asdict(row) for row in seed_reported],
            }
            cache.write_text(json.dumps(saved, indent=1) + "\n", encoding="utf-8", newline="\n")
        rows += [
            AxisRow(
                axis=str(row["axis"]),
                seed=int(row["seed"]),
                checkpoint=str(row["checkpoint"]),
                gating=bool(row["gating"]),
                interval=AuprcInterval(**row["interval"]),
                verdict=GateVerdict(**row["verdict"]),
            )
            for row in saved["rows"]
        ]
        reported += [
            ReportedRow(
                group=str(row["group"]),
                axis=str(row["axis"]),
                seed=int(row["seed"]),
                checkpoint=str(row["checkpoint"]),
                base_rate=float(row["base_rate"]),
                interval=AuprcInterval(**row["interval"]),
                note=str(row["note"]),
            )
            for row in saved["reported"]
        ]

    # -- ADR-0022 §4 -----------------------------------------------------------------------------
    def per_axis(role: str) -> dict[str, AxisVerdict]:
        return {
            axis: decide_axis(
                axis,
                {r.seed: r.verdict for r in rows if r.axis == axis and r.checkpoint == role},
                config.seeds_required,
            )
            for axis in ("care", "temporal")
        }

    verdicts = per_axis(config.checkpoints.gating)
    reported_verdicts = per_axis(config.checkpoints.reported[0])
    for axis, verdict in verdicts.items():
        logger.info("%s: %s", axis, verdict.reason)
    assignment = assign_hypotheses(verdicts["care"], verdicts["temporal"])
    logger.info("ADR-0022 §4 assignment: %s", assignment.sentence)

    record = AxisGateRecord(
        config_hash=config_hash(config),
        gating=config.checkpoints.gating,
        rows=tuple(rows),
        reported=tuple(reported),
        verdicts=verdicts,
        reported_verdicts=reported_verdicts,
        assignment=assignment,
        absence=absence,
        counts={"care": thinned, "care_full": full, "temporal": temporal_counts},
        without_messages=without_messages,
        seconds=time.perf_counter() - started,
        gpu_seconds=gpu_seconds,
        computed=tuple(computed),
        resumed=tuple(resumed),
    )
    stem = f"axis_gate_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report_file = paths.data_reports_dir / f"{stem}.md"
    report_file.write_text(
        render_report(config, config_path, record, probes, paths),
        encoding="utf-8",
        newline="\n",
    )
    record_file = paths.data_reports_dir / f"{stem}.json"
    record_file.write_text(
        json.dumps({"config": config.model_dump(mode="json"), **record_payload(record)}, indent=1)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    logger.info("wrote %s and %s", report_file, record_file)
    return report_file, record_file


# =====================================================================================
# the report
# =====================================================================================

#: The commits ADR-0022, its addendum and the addendum's outcome were registered in.
HASHES = {
    "ADR-0022": "801ab71 (hash recorded by 92ee875)",
    "ADR-0022 addendum, registered": "4622564",
    "ADR-0022 addendum, outcome": "267147d",
}


def _iv(interval: AuprcInterval) -> str:
    return f"{interval.auprc:.4f} [{interval.low:.4f}, {interval.high:.4f}]"


def render_report(
    config: AxisGateConfig,
    config_path: Path,
    record: AxisGateRecord,
    probes: dict[int, ProbeCheckpoints],
    paths: ProjectPaths,
) -> str:
    """Render F5's report.

    Args:
        config: The axis-gate configuration.
        config_path: Where it was read from.
        record: What F5 measured.
        probes: Per seed, its two checkpoints.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    relative = config_path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    caveat = f"{ADR_0009_CAVEAT} {IN_DISTRIBUTION}"

    def rate(axis: str, value: float) -> str:
        """The base rate at the decimals its own axis is registered to (ADR-0022 §3 and §2)."""
        return f"{value:.6f}" if axis == "care" else f"{value:.4f}"

    def step_of(row: AxisRow) -> int:
        probe = probes[row.seed]
        return probe.last_step if row.checkpoint == FIXED_FINAL else probe.selected_step

    axis_rows = [
        (
            {"care": "CARE", "temporal": "temporal (in-distribution)"}[row.axis],
            str(row.seed),
            f"{row.checkpoint} (step {step_of(row)})",
            "gates" if row.gating else "reported",
            _iv(row.interval),
            rate(row.axis, row.interval.base_rate),
            f"{record.absence['care'].nan_share_steps:.2%}"
            if row.axis == "care"
            else f"{record.absence['kelmarsh'].nan_share_steps:.2%} / "
            f"{record.absence['penmanshiel'].nan_share_steps:.2%}",
            "CLEARS" if row.verdict.evaluable else "does not clear",
            CARE_CONFOUND if row.axis == "care" else caveat,
        )
        for row in sorted(record.rows, key=lambda r: (r.axis, r.seed, r.checkpoint))
    ]
    farm_rows = [
        (
            row.group,
            str(row.seed),
            row.checkpoint,
            f"{record.absence[row.group].nan_share_steps:.2%}",
            ", ".join(record.absence[row.group].absent),
            f"{row.interval.windows:,}",
            str(row.interval.positives),
            f"{row.base_rate:.6f}",
            _iv(row.interval),
            f"{row.interval.discarded_share:.2%}",
        )
        for row in record.reported
        if row.group in CARE_FARMS
    ]
    without_rows = [
        (
            str(row.seed),
            row.checkpoint,
            f"{row.interval.windows:,}",
            f"{row.interval.positives:,}",
            f"{row.base_rate:.4f}",
            _iv(row.interval),
            caveat,
        )
        for row in record.reported
        if row.group == "without_anemometer_defect"
    ]
    held_rows = [
        (
            str(row.seed),
            row.checkpoint,
            f"{row.interval.windows:,}",
            f"{row.base_rate:.5f}",
            _iv(row.interval),
            "clears" if row.interval.low > row.base_rate else "does not clear",
        )
        for row in record.reported
        if row.axis == "held_out"
    ]
    discarded = {
        axis: max(row.interval.discarded_share for row in record.rows if row.axis == axis)
        for axis in ("care", "temporal")
    }
    farm_discarded = max(
        row.interval.discarded_share for row in record.reported if row.group in CARE_FARMS
    )
    verdict_rows = [
        (
            {"care": "CARE", "temporal": "temporal (in-distribution)"}[axis],
            f"{len(verdict.clearing)} of {len(verdict.seeds)}",
            ", ".join(str(s) for s in verdict.clearing) or "none",
            "EVALUABLE" if verdict.evaluable else "NOT EVALUABLE",
            "EVALUABLE" if record.reported_verdicts[axis].evaluable else "NOT EVALUABLE",
        )
        for axis, verdict in record.verdicts.items()
    ]
    differs = [
        axis
        for axis in record.verdicts
        if record.verdicts[axis].evaluable != record.reported_verdicts[axis].evaluable
    ]
    selected_note = (
        "The selected checkpoint's rows would produce a different verdict on "
        + ", ".join(differs)
        + ", so the gating rule is doing work here."
        if differs
        else "The selected checkpoint's rows produce the same verdict on both axes, so which "
        "checkpoint gates does not change the outcome."
    )
    without = record.without_messages
    return "".join(
        [
            "# The evaluation-axis gate (ADR-0022 §4)\n\n",
            kv_table(
                {
                    "configuration": f"{relative} (hash {record.config_hash})",
                    "decision record": "docs/DECISIONS.md, ADR-0022, registered before either "
                    "axis was scored for any seed",
                    **HASHES,
                    "checkpoint rule in force": f"`{record.gating}` gates; "
                    f"`{', '.join(config.checkpoints.reported)}` is scored beside it and reported",
                    "CARE scorings": f"{len(record.computed)} computed in this invocation, "
                    f"{len(record.resumed)} resumed from disk",
                    "read, never re-scored": "the temporal split's and Hill of Towie's F3 scores",
                    "GPU wall clock of the CARE scorings": f"{record.gpu_seconds / 3600:.2f} h "
                    f"over {len(record.computed) + len(record.resumed)} scorings, whenever paid "
                    "for; read from the timing written beside each set of scores",
                    "wall clock (this invocation)": f"{record.seconds / 60:.1f} min",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model axis-gate",
                }
            ),
            section(
                "1. The axis x seed x checkpoint table",
                f"Both axes at stride {config.stride}. CARE: {record.counts['care'].windows:,} "
                f"windows, {record.counts['care'].positives} positive over "
                f"{config.axes.care.events} events, {record.counts['care'].blocks:,} of "
                f"{record.counts['care_full'].blocks:,} blocks and "
                f"{record.counts['care'].positive_blocks} of "
                f"{record.counts['care_full'].positive_blocks} positive blocks covered. Temporal: "
                f"{record.counts['temporal'].windows:,} windows, "
                f"{record.counts['temporal'].positives:,} positive, "
                f"{record.counts['temporal'].positive_blocks} of "
                f"{record.counts['temporal'].blocks:,} blocks holding a positive. Every base rate "
                "below is the scored set's own, never the training rate.\n\n"
                + table(
                    [
                        "axis",
                        "seed",
                        "checkpoint",
                        "role",
                        "AUPRC, 95% block interval",
                        "own base rate",
                        "`<nan>` share",
                        "lower bound strictly above",
                        "caveat",
                    ],
                    axis_rows,
                ),
            ),
            section(
                "2. Per CARE farm, reported only",
                "The rule is applied to the pooled CARE set. These rows are the same scorings "
                "split by farm, so that no per-farm figure stands without its `<nan>` share "
                "(`configs/eval/README.md`, rule 1).\n\n"
                + table(
                    [
                        "farm",
                        "seed",
                        "checkpoint",
                        "`<nan>` share",
                        "core channels absent, emitted as `<nan>`",
                        "windows",
                        "positives",
                        "own base rate",
                        "AUPRC, 95% block interval",
                        "discarded",
                    ],
                    farm_rows,
                )
                + "\nThe `<nan>` share above counts each covered step once, which is the basis "
                "of the F4 figures in `data/cards/care.md` and ADR-0022 §1 and reproduces them "
                "exactly. Weighted instead by the scored windows, so that overlapping context "
                "counts as the scoring counts it, the same streams read "
                + ", ".join(
                    f"{group} {record.absence[group].nan_share_windows:.2%}" for group in CARE_FARMS
                )
                + f" and all of CARE {record.absence['care'].nan_share_windows:.2%} against "
                f"{record.absence['care'].nan_share_steps:.2%}.\n"
                + f"\n**{CARE_CONFOUND}** (`data/cards/care.md`, F4 of 2026-09-17). A channel "
                "permanently absent while its neighbours report is outside everything the "
                "backbone was pretrained on, at every CARE farm, and the evaluation cannot "
                "remove this confound.\n",
            ),
            section(
                "3. The anemometer-defect variant, reported only",
                f"**Origin, measured.** `{without['message']}` is a Senvion status string in the "
                f"`{without['category']}` category of `configs/data/events_v2.yaml`, for sources "
                f"{' and '.join(without['sources'])} only. It is named by "
                f"`{without['named_in']}` under ADR-0009's standing requirement, and the window "
                f"index carries it as `{without['label']}`.\n\n"
                "**It is not a CARE label category.** CARE's labels come from "
                f"{without['care_label_source']} (`configs/data/events_v2.yaml`, `event_info`), "
                f"so the variant removes **{without['care_events_removed']} of "
                f"{config.axes.care.events} CARE events and touches no farm**: on `care__test` "
                "the two label columns are identical, and the variant loses "
                f"{without['care_windows_lost']} of CARE's "
                f"{record.counts['care'].windows:,} windows and "
                f"{without['care_positives_lost']} of its {record.counts['care'].positives} "
                "positives. The variant therefore exists for the temporal axis alone, which is "
                "where `configs/eval/axis_gate_v0.yaml` puts it.\n\n"
                "**What the rows below are thinned from.** ADR-0022 §2 records this variant as "
                f"{config.axes.temporal.without_messages_positives:,} of "
                f"{config.axes.temporal.without_messages_windows:,} windows, which strides the "
                "variant label's **own** admissible set. F5 cannot do that: it reads logits "
                "already computed on the full-label windows, so it relabels exactly those and "
                f"keeps the ones the variant knows -- {without['temporal_positives']:,} of "
                f"{without['temporal_windows']:,}, one window and one positive from ADR-0022 "
                "§2's count. Both read a base rate of 0.0243.\n\n"
                + table(
                    [
                        "seed",
                        "checkpoint",
                        "windows",
                        "positives",
                        "own base rate",
                        "AUPRC, 95% block interval",
                        "caveat",
                    ],
                    without_rows,
                )
                + "\nThe ADR-0022 §4 verdict is computed on the full label set, not on this "
                "variant.\n",
            ),
            section(
                "4. Hill of Towie, for comparison",
                "F3's 12,000-window subsample, read and not re-scored. Never pooled with CARE "
                "into a headline number (`configs/eval/README.md`, rule 2). ADR-0021 and "
                "ADR-0022 §6 both read this site NOT EVALUABLE and the demotion is not "
                "reopened.\n\n"
                + table(
                    [
                        "seed",
                        "checkpoint",
                        "windows",
                        "base rate",
                        "AUPRC, 95% block interval",
                        "lower bound above the base rate",
                    ],
                    held_rows,
                ),
            ),
            section(
                "5. The discarded share per axis",
                "Above "
                f"{config.bootstrap.max_discarded_share:.0%} of replicates holding no positive "
                "window, an interval is untrusted and its seed does not clear whatever its "
                "bounds say.\n\n"
                + table(
                    ["rows", "highest discarded share over them"],
                    [
                        ("CARE, pooled (the rows the rule reads)", f"{discarded['care']:.2%}"),
                        (
                            "temporal (in-distribution), pooled (the rows the rule reads)",
                            f"{discarded['temporal']:.2%}",
                        ),
                        (
                            "CARE per farm (reported only)",
                            f"{farm_discarded:.2%} (farm_b, whose 72 positives fall in the "
                            "fewest blocks of the three)",
                        ),
                    ],
                )
                + "\nNo interval anywhere above is untrusted: every share is below the "
                f"{config.bootstrap.max_discarded_share:.0%} limit, so no seed's verdict rests "
                "on a discarded-replicate failure rather than on its bounds.\n",
            ),
            section(
                "6. The verdicts and the assignment",
                f"On the **{record.gating}** checkpoint, "
                f"{config.seeds_required} of {len(config.seeds)} seeds must clear.\n\n"
                + table(
                    [
                        "axis",
                        "seeds clearing",
                        "which",
                        f"verdict ({record.gating}, gates)",
                        "verdict (selected, reported)",
                    ],
                    verdict_rows,
                )
                + "\n"
                + "\n".join(f"- **{axis}**: {v.reason}." for axis, v in record.verdicts.items())
                + f"\n\n{selected_note}\n\n**Assignment.** {record.assignment.sentence}\n",
            ),
        ]
    )
