"""F8-2's GPU half (ADR-0027 §7): six ablation pretrainings, nine (d) probes, nine scorings.

The two ablations of ``configs/train/joint_v2.yaml`` are pretrained at ``joint``'s own budget and
protocol, then read through **(d) ``last_plus_text``** — the read-out ADR-0026's gate showed reads
the text. ``joint`` is neither retrained nor re-probed: its three (d) reads are F7'-2's
``R-joint-d`` records, and this runner never writes them.

The three phases, in order:

1. **Pretraining.** ``joint_status_raw`` and ``joint_no_txt``, three seeds each, by
   ``pretrain_joint`` under the gate run's protocol (S2, 763 steps, 50,003,968 tokens).
2. **Probes.** (d) on each ablation backbone (six), plus **three random-init (d) probes on the raw
   windows** — ``joint_no_txt`` reuses ADR-0026's random-init reads because it probes the same
   windows, and the raw arm cannot, because its windows are not those (§4).
3. **Scorings.** All nine final-step probes on the 137,025-window stride-12 pooled test split,
   under :mod:`faultline.evaluation.h1_scoring`'s guards, re-used rather than re-implemented.

**Each arm reads its own windows.** ``open_probe_inputs`` takes the ``tel+status`` convention from
the arm, so the raw arm is framed over ``tel_status_raw`` and the normalized arm over
``tel_status_normalized``. Inputs are opened once per convention and shared.

**Three registered assertions, and they raise rather than warn** (ADR-0027 §2, §3, §4):

- :func:`assert_sampler_counts` — every arm's realised per-stream window counts are the registered
  ones, and paired ``tel+status`` exposure is ``joint``'s to the token. This is what stops the
  narrative ablation from quietly becoming a status increase.
- :func:`assert_raw_index_matches_normalized` — the raw-framed index carries the same keys, labels,
  years and counts as the normalized one, so a paired difference pairs row for row. Truncation is
  allowed to differ, and by how much is recorded.
- :func:`assert_random_init_reads_raw` — the raw arm's gate probes read raw windows.

**Resume is per artefact**, as F6-2, F6-3 and F7'-2 resume. ``RUNNING.lock`` holds the running
process's id and is removed when the process ends.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

from faultline.config import config_hash, load_config
from faultline.evaluation.ablation_gate import (
    AblationArmsConfig,
    AblationGateConfig,
)
from faultline.evaluation.checkpoint_selection import FIXED_FINAL
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.h1_scoring import (
    SELECTION_TOLERANCE,
    ScoringLayout,
    save_atomically,
    scoring_layout,
    selection_auprc,
    tree_dirty,
    write_json,
)
from faultline.evaluation.ladder import SplitEval, build_split
from faultline.evaluation.paired_control import score_saved_probe
from faultline.evaluation.probe_cadence import ProbeCadenceConfig
from faultline.evaluation.probe_control import ProbeControlConfig, ScoredWindows
from faultline.evaluation.readout import (
    READOUT_HEAD_LAYERS,
    READOUT_POOLING,
    READOUT_UNFROZEN_BLOCKS,
    ReadoutConfig,
    risk_spec,
)
from faultline.evaluation.readout_runs import (
    RANDOM_BACKBONE_STEM,
    RANDOM_PROBE_STEM,
    materialise_random_init,
    relative,
)
from faultline.evaluation.variance_probe import (
    ProbeInputs,
    open_probe_inputs,
    pretrain_joint,
    probe_and_score,
)
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.config import Budget, PositiveAwareRiskStage
from faultline.training.joint_windows import JointWindowSet, mixture_schedule
from faultline.training.mixture import STREAM_DIRS, STREAMS, Arm, JointMixtureConfig, StreamName

logger = get_logger(__name__)

#: The two families of probe this runner trains: an ablation backbone, or an untrained one.
ABLATION_FAMILY = "ablation"
RANDOM_FAMILY = "random_init"


# =====================================================================================
# the plan
# =====================================================================================


@dataclass(frozen=True)
class ArmPretraining:
    """One arm's view of the runner, as ``pretrain_joint`` reads a configuration.

    ``AblationArmsConfig`` names two arms, and pretraining reads one at a time. This adapter
    carries the runner's rung, budget and optimiser with a single ``arm``, so the pretraining
    path is the one ``joint`` ran under and not a second copy of it.

    Attributes:
        runner: The F8-2 runner configuration.
        arm: The arm pretrained.
    """

    runner: AblationArmsConfig
    arm: str

    @property
    def rung(self) -> str:
        """The rung, the runner's."""
        return self.runner.rung

    @property
    def batch_windows(self) -> int:
        """Windows per forward pass while pretraining."""
        return self.runner.batch_windows

    def budget(self, context_tokens: int) -> Budget:
        """The pretraining window budget, the runner's."""
        return self.runner.budget(context_tokens)


@dataclass(frozen=True)
class AblationItem:
    """One of ADR-0027 §7's nine probes, and the scoring that reads it.

    Attributes:
        arm: The ablation this item belongs to. A random-init item carries the arm whose gate it
            serves, because that is what fixes which windows it reads.
        family: ``ablation`` or ``random_init``.
        seed: The pretraining seed, or the initialisation seed for ``random_init``.
        convention: The ``tel+status`` convention its windows are framed over.
        name: The file stem of every artefact this probe writes.
    """

    arm: str
    family: str
    seed: int
    convention: str
    name: str

    @property
    def is_random_init(self) -> bool:
        """Whether this probe reads an untrained backbone."""
        return self.family == RANDOM_FAMILY


def probe_plan(
    runner: AblationArmsConfig, mixture: JointMixtureConfig, gate: AblationGateConfig
) -> list[AblationItem]:
    """Every F8-2 probe, arm-major and seed-minor, ablations first and the gate probes after.

    Args:
        runner: The F8-2 runner configuration.
        mixture: The mixture naming each arm's convention.
        gate: The gate, which says per arm whether new random-init probes are needed.

    Returns:
        The nine probes, in the order they run and the order they are scored.

    Raises:
        ValueError: If an arm of the runner is not in the mixture.
    """
    conventions = {arm.name: arm.status_convention for arm in mixture.arms}
    missing = [arm for arm in runner.arms if arm not in conventions]
    if missing:
        raise ValueError(f"{missing} are not arms of {runner.mixture_config}")
    plan = [
        AblationItem(
            arm=arm,
            family=ABLATION_FAMILY,
            seed=seed,
            convention=conventions[arm],
            name=f"{runner.rung}_{arm}_seed{seed}",
        )
        for arm in runner.arms
        for seed in runner.seeds
    ]
    needs = {s.arm: s.new_probes for s in gate.instrument_gate.random_init_scores}
    plan += [
        AblationItem(
            arm=arm,
            family=RANDOM_FAMILY,
            seed=seed,
            convention=conventions[arm],
            name=f"{runner.rung}_random_init_{conventions[arm]}_seed{seed}",
        )
        for arm in runner.arms
        if needs.get(arm, 0)
        for seed in runner.seeds
    ]
    return plan


# =====================================================================================
# the three registered assertions (ADR-0027 §2, §3, §4)
# =====================================================================================


def realised_stream_windows(arm: Arm, windows: int) -> dict[StreamName, int]:
    """Per stream, the windows the mixture sampler draws for one arm at a budget.

    ``MixtureSampler`` fixes which stream each window comes from with the seed-independent
    largest-deficit schedule, so these counts are a property of the configuration and can be
    checked before a single window is read.

    Args:
        arm: The arm.
        windows: Windows in the budget.

    Returns:
        Per stream with a positive share, its window count.
    """
    shares = {stream: arm.share(stream) for stream in STREAMS if arm.share(stream)}
    schedule = mixture_schedule(shares, windows)
    order = list(STREAMS)
    return {stream: int((schedule == order.index(stream)).sum()) for stream in shares}


def assert_sampler_counts(
    runner: AblationArmsConfig,
    mixture: JointMixtureConfig,
    arm_name: str,
    drawn: dict[str, int] | None = None,
) -> dict[str, int]:
    """ADR-0027 §2: the arm's realised per-stream token counts are the registered ones.

    The paired ``tel+status`` count is the one this record exists to hold fixed: the narrative
    share was given to plain telemetry rather than renormalised proportionally so that every arm
    sees ``joint``'s paired exposure to the token. If that equality fails, the ablation is
    confounded — it removes the narrative *and* changes status exposure — and the run must stop.

    Args:
        runner: The F8-2 runner, carrying the registered budget.
        mixture: The mixture naming the arm's shares.
        arm_name: The arm checked.
        drawn: Per stream, the windows a sampler actually drew; skipped when omitted.

    Returns:
        Per stream, the tokens the arm sees.

    Raises:
        ValueError: If the arm is not in the mixture; if the windows do not sum to the registered
            budget; if paired ``tel+status`` exposure is not the registered count; or if a
            sampler's realised draw differs from the schedule.
    """
    budget = runner.token_budget
    arm = next((a for a in mixture.arms if a.name == arm_name), None)
    if arm is None:
        raise ValueError(f"{arm_name} is not an arm of {runner.mixture_config}")
    windows = realised_stream_windows(arm, budget.windows)
    total = sum(windows.values())
    if total != budget.windows:
        raise ValueError(
            f"{arm_name}: the schedule draws {total} windows, the budget is {budget.windows}"
        )
    tokens: dict[str, int] = {
        stream: count * budget.context_tokens for stream, count in windows.items()
    }
    if sum(tokens.values()) != budget.total_tokens:
        raise ValueError(
            f"{arm_name}: {sum(tokens.values())} tokens, the budget is {budget.total_tokens}"
        )
    paired = tokens.get("tel+status", 0)
    if paired != budget.paired_tel_status_tokens:
        raise ValueError(
            f"{arm_name}: paired tel+status exposure is {paired} tokens, not the registered "
            f"{budget.paired_tel_status_tokens}; removing the narrative must not change status "
            "exposure (ADR-0027 §2)"
        )
    if drawn is not None:
        realised = {stream: int(count) for stream, count in drawn.items() if count}
        if realised != {stream: count for stream, count in windows.items()}:
            raise ValueError(
                f"{arm_name}: the sampler drew {realised}, the schedule says {windows}"
            )
    return tokens


def assert_raw_index_matches_normalized(
    normalized: list[JointWindowSet], raw: list[JointWindowSet], windows: int, positives: int
) -> dict[str, int]:
    """ADR-0027 §3: the raw index is the normalized index, re-framed and nothing more.

    The two must agree on every key, end step, label and year, and on the scored counts, because
    the paired difference of §5 pairs row for row. They are *allowed* to differ in how many whole
    telemetry steps survive the 2,048-token budget — raw strings are longer — and how many
    windows differ is measured here rather than assumed.

    Args:
        normalized: The test window sets framed over ``tel_status_normalized``, in split order.
        raw: The same sets framed over ``tel_status_raw``, in the same order.
        windows: The registered window count.
        positives: The registered positive count.

    Returns:
        The measured counts: windows, positives, and how many of each retain a different number
        of telemetry steps under raw casing.

    Raises:
        ValueError: If the two framings disagree on keys, end steps, labels or years, if either
            does not carry the registered counts, or if a window is head-cut under one framing
            and not the other.
    """
    if len(normalized) != len(raw):
        raise ValueError(f"{len(normalized)} normalized window sets against {len(raw)} raw")
    total = positives_seen = differing = positives_differing = 0
    for left, right in zip(normalized, raw, strict=True):
        if left.key != right.key:
            raise ValueError(f"shard keys differ: {left.key} against {right.key}")
        for field_name in ("ends", "labels", "years", "starts"):
            if not np.array_equal(getattr(left, field_name), getattr(right, field_name)):
                raise ValueError(f"{left.key}: the two framings differ in {field_name}")
        if not np.array_equal(left.head_cut, right.head_cut):
            raise ValueError(f"{left.key}: head-cut flags differ between the two framings")
        label = np.asarray(left.labels).astype(bool)
        changed = np.asarray(left.steps_retained) != np.asarray(right.steps_retained)
        total += int(label.size)
        positives_seen += int(label.sum())
        differing += int(changed.sum())
        positives_differing += int((changed & label).sum())
    if (total, positives_seen) != (windows, positives):
        raise ValueError(
            f"the framed index holds {total} windows and {positives_seen} positives, "
            f"the registered counts are {windows} and {positives}"
        )
    return {
        "windows": total,
        "positives": positives_seen,
        "windows_differing_in_steps_retained": differing,
        "positives_differing_in_steps_retained": positives_differing,
    }


def assert_registered_truncation(
    runner: AblationArmsConfig, measured: dict[str, int], arm: str = "joint_status_raw"
) -> None:
    """ADR-0027 §3: the truncation the runner records is the truncation the shards give.

    ``ablation_arms_v0.yaml`` carries the F8 read-only check's counts by value, so a change in the
    shards, the tokenizer or the window rule that moved them would otherwise pass unnoticed and
    the caveat of §8 would name a number that is no longer true.

    Args:
        runner: The F8-2 runner, carrying the registered counts.
        measured: What :func:`assert_raw_index_matches_normalized` measured.
        arm: The arm whose window rule holds the registered counts.

    Raises:
        ValueError: If a registered count is not the measured one.
    """
    rule = runner.window_rule(arm)
    for field_name in (
        "windows_differing_in_steps_retained",
        "positives_differing_in_steps_retained",
    ):
        registered = int(getattr(rule, field_name))
        if registered != int(measured[field_name]):
            raise ValueError(
                f"{arm}: {field_name} is registered as {registered} and measures "
                f"{measured[field_name]}; ADR-0027 §3 and §8 quote the registered number"
            )


def assert_random_init_reads_raw(
    plan: list[AblationItem],
    inputs_by_convention: dict[str, ProbeInputs],
    gate: AblationGateConfig,
) -> list[str]:
    """ADR-0027 §4: every gate probe reads the windows of the arm it gates.

    A gate computed on different windows from the arm it gates is not a gate. The raw arm's three
    random-init probes must therefore be framed over ``tel_status_raw``, and the normalized arm
    must have no new gate probes at all, because ADR-0026 already gated those windows.

    Args:
        plan: The nine probes.
        inputs_by_convention: The opened inputs, keyed by ``tel+status`` convention.
        gate: The gate, which says per arm how many new probes are registered.

    Returns:
        One line per gate probe, naming the stream directory it reads.

    Raises:
        ValueError: If a gate probe's convention has no opened inputs, if those inputs are not
            framed over that convention's stream, or if the plan's gate probes do not match the
            counts the gate registers.
    """
    registered = {s.arm: s.new_probes for s in gate.instrument_gate.random_init_scores}
    seen: dict[str, int] = {}
    lines: list[str] = []
    for item in plan:
        if not item.is_random_init:
            continue
        seen[item.arm] = seen.get(item.arm, 0) + 1
        inputs = inputs_by_convention.get(item.convention)
        if inputs is None or inputs.tel_status is None:
            raise ValueError(f"{item.name}: no opened tel+status inputs for {item.convention}")
        expected = f"{STREAM_DIRS['tel+status']}_{item.convention}"
        if inputs.tel_status.root.name != expected:
            raise ValueError(
                f"{item.name}: the gate probe reads {inputs.tel_status.root.name}, not {expected}; "
                "a gate computed on other windows than the arm it gates is not a gate"
            )
        lines.append(f"{item.name}: {expected} (gates {item.arm})")
    wanted = {arm: count for arm, count in registered.items() if count}
    if seen != wanted:
        raise ValueError(f"the plan holds gate probes {seen}, the gate registers {wanted}")
    return lines


# =====================================================================================
# the layout
# =====================================================================================


@dataclass
class AblationLayout:
    """Every file F8-2 reads or writes, named once.

    Attributes:
        runner: The F8-2 runner configuration.
        gate: The gate, for the registered counts and the per-arm gate probes.
        mixture: The arms.
        h1: F6-3's layout, which resolves the joint backbones and F3's ``tel_only`` scores.
        readout: F7''s configuration, whose (d) definition this record re-uses.
        out_dir: Backbones, probes, records, scores and sidecars.
        log_dir: Per-step training logs, tracked beside the reports.
        random_dir: ADR-0023's random-init output directory.
        reference_dir: F7'-2's output directory, holding ``joint``'s (d) probes and scores.
        stride: The scored thinning.
        plan: The nine probes, in order.
    """

    runner: AblationArmsConfig
    gate: AblationGateConfig
    mixture: JointMixtureConfig
    h1: ScoringLayout
    readout: ReadoutConfig
    out_dir: Path
    log_dir: Path
    random_dir: Path
    reference_dir: Path
    stride: int
    plan: list[AblationItem] = field(default_factory=list)

    @property
    def rung(self) -> str:
        """The model rung, the first part of every file name."""
        return self.runner.rung

    def backbone(self, item: AblationItem) -> Path:
        """The frozen backbone a probe reads."""
        if item.is_random_init:
            return self.random_backbone(item.seed)
        return self.arm_backbone(item.arm, item.seed)

    def arm_backbone(self, arm: str, seed: int) -> Path:
        """One ablation seed's pretrained backbone."""
        return self.out_dir / f"{self.rung}_{arm}_seed{seed}.pt"

    def lm_record(self, arm: str, seed: int) -> Path:
        """A pretraining record: its presence marks pretraining finished."""
        return self.out_dir / f"{self.rung}_{arm}_seed{seed}_lm.json"

    def random_backbone(self, seed: int) -> Path:
        """Where this record holds the random-init backbone of an initialisation seed."""
        return self.out_dir / RANDOM_BACKBONE_STEM.format(rung=self.rung, seed=seed)

    def random_source(self, seed: int) -> Path:
        """ADR-0023's saved probe, which holds that seed's random-init backbone."""
        return self.random_dir / RANDOM_PROBE_STEM.format(rung=self.rung, seed=seed)

    def probe(self, item: AblationItem, role: str = FIXED_FINAL) -> Path:
        """A probe's saved state: the final step under the rule in force, or the selected one."""
        infix = "_final" if role == FIXED_FINAL else ""
        return self.out_dir / f"{item.name}{infix}_probe.pt"

    def probe_record(self, item: AblationItem) -> Path:
        """A probe's record: its presence marks the probe finished."""
        return self.out_dir / f"{item.name}_probe.json"

    def scores(self, item: AblationItem) -> Path:
        """A probe's test scores on the R0 stride-12 split."""
        return self.out_dir / f"{item.name}_final_R0_stride{self.stride}_scores.npz"

    def reference_scores(self, seed: int) -> Path:
        """``joint`` under (d), from F7'-2: the reference side of every §5 difference."""
        run = self.runner.reference_run
        stem = f"{self.rung}_{run}_seed{seed}_final_R0_stride{self.stride}_scores.npz"
        return self.reference_dir / stem

    @property
    def random_record(self) -> Path:
        """Which random-init backbones the gate probes used, and where each came from."""
        return self.out_dir / "random_init.json"

    @property
    def assertions_record(self) -> Path:
        """The three registered assertions' measured values, written before any probe trains."""
        return self.out_dir / "assertions.json"

    @property
    def lock(self) -> Path:
        """The running process's lock."""
        return self.out_dir / "RUNNING.lock"

    @property
    def status(self) -> Path:
        """The status file this runner returns."""
        return self.out_dir / "ablation_status.json"

    def conventions(self) -> list[str]:
        """The ``tel+status`` conventions the plan reads, in first-appearance order."""
        seen: list[str] = []
        for item in self.plan:
            if item.convention not in seen:
                seen.append(item.convention)
        return seen

    def arm_of(self, convention: str) -> str:
        """An arm of the mixture written in one convention, for opening that convention's inputs."""
        for arm in self.mixture.arms:
            if arm.status_convention == convention:
                return arm.name
        raise KeyError(f"no arm of {self.runner.mixture_config} is written {convention!r}")

    def done(self, item: AblationItem) -> bool:
        """Whether a probe and its scoring both have their artefacts."""
        return self.probe_record(item).exists() and self.scores(item).exists()


def ablation_layout(paths: ProjectPaths, config_path: Path) -> AblationLayout:
    """Resolve every path F8-2 touches from its configurations.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/eval/ablation_gate_v0.yaml``.

    Returns:
        The layout.
    """
    gate = load_config(config_path, AblationGateConfig)
    runner = load_config(paths.repo_root / gate.runner_config, AblationArmsConfig)
    mixture = load_config(paths.repo_root / runner.mixture_config, JointMixtureConfig)
    readout = load_config(paths.repo_root / gate.readout_config, ReadoutConfig)
    h1 = scoring_layout(paths, paths.repo_root / gate.h1_gate_config)
    control = load_config(paths.repo_root / runner.random_init_config, ProbeControlConfig)
    return AblationLayout(
        runner=runner,
        gate=gate,
        mixture=mixture,
        h1=h1,
        readout=readout,
        out_dir=paths.checkpoints_dir / f"ablation_arms_v{runner.version}_{config_hash(runner)}",
        log_dir=paths.data_reports_dir / f"ablation_arms_v{runner.version}_steps",
        random_dir=paths.checkpoints_dir
        / f"probe_control_v{control.version}_{config_hash(control)}",
        reference_dir=paths.checkpoints_dir / f"readout_v{readout.version}_{config_hash(readout)}",
        stride=gate.stride,
        plan=probe_plan(runner, mixture, gate),
    )


# =====================================================================================
# pre-flight
# =====================================================================================


def preflight(paths: ProjectPaths, layout: AblationLayout) -> tuple[list[str], list[str]]:
    """What must exist before F8-2 starts, and where each item stands.

    Args:
        paths: Resolved project paths.
        layout: The resolved layout.

    Returns:
        The problems (empty when F8-2 may start) and one status line per item.
    """
    root = paths.repo_root
    runner, gate = layout.runner, layout.gate
    problems: list[str] = []
    if (gate.stride, gate.label) != (layout.h1.gate.stride, layout.h1.gate.label):
        problems.append(
            f"ablation stride/label {(gate.stride, gate.label)} are not the H1 gate's "
            f"{(layout.h1.gate.stride, layout.h1.gate.label)}"
        )
    # That the probe read-out is ABLATION_READOUT is fixed by the schema's Literal and needs no
    # run-time check; that readout_v0 actually defines it does.
    if runner.probe.readout not in layout.readout.readout_names:
        problems.append(f"{runner.probe.readout} is not a read-out of {gate.readout_config}")
    required: list[Path] = [layout.h1.arms.joint_root / "manifest.json"]
    for convention in layout.conventions():
        status_dir = layout.h1.arms.joint_root / f"{STREAM_DIRS['tel+status']}_{convention}"
        for source in layout.mixture.training_sources:
            required += [
                status_dir / f"{source}__{split}.bin" for split in ("train", "val", "test")
            ]
            required.append(status_dir / f"{source}__train.runs.parquet")
    txt_dir = layout.h1.arms.joint_root / STREAM_DIRS["txt"]
    if not list(txt_dir.glob("*__train.bin")):
        problems.append(f"no txt train shard under {txt_dir}")
    for seed in runner.seeds:
        required.append(layout.reference_scores(seed))
        required.append(layout.h1.tel_only_scores(seed))
    for item in layout.plan:
        if item.is_random_init and not (
            layout.random_source(item.seed).is_file() or layout.random_backbone(item.seed).is_file()
        ):
            logger.info(
                "random-init seed %d has no saved backbone; it is constructed fresh", item.seed
            )
    missing = sorted({p for p in required if not p.exists()})
    problems += [f"missing: {relative(p, root)}" for p in missing]
    if layout.lock.exists():
        problems.append(
            f"{relative(layout.lock, root)} exists (pid "
            f"{layout.lock.read_text(encoding='utf-8').strip()}): a run may be active; check the "
            "process list, and delete the lock only if that process is gone"
        )
    if not torch.cuda.is_available():
        problems.append("CUDA is not available: F8-2 is a GPU run")
    lines = [
        f"pretrain {arm} seed {seed}: "
        f"{'done' if layout.lm_record(arm, seed).exists() else 'to run'}"
        for arm in runner.arms
        for seed in runner.seeds
    ]
    lines += [
        f"[{i:2d}/{len(layout.plan)}] probe {item.name} ({item.convention} windows): "
        f"{'done' if layout.probe_record(item).exists() else 'to run'}"
        for i, item in enumerate(layout.plan, 1)
    ]
    lines += [
        f"[{i:2d}/{len(layout.plan)}] score {item.name}: "
        f"{'done' if layout.scores(item).exists() else 'to run'}"
        for i, item in enumerate(layout.plan, 1)
    ]
    return problems, lines


# =====================================================================================
# the run
# =====================================================================================


def run_ablation(paths: ProjectPaths, config_path: Path, device_name: str | None = None) -> Path:
    """Pretrain, probe and score every F8-2 item not yet on disk.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/eval/ablation_gate_v0.yaml``.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The status file, ``ablation_status.json`` in the output directory.

    Raises:
        RuntimeError: If a pre-flight problem stands.
    """
    layout = ablation_layout(paths, config_path)
    problems, _ = preflight(paths, layout)
    if device_name == "cpu":
        problems = [p for p in problems if not p.startswith("CUDA")]
    if problems:
        raise RuntimeError("pre-flight failed:\n" + "\n".join(problems))
    layout.out_dir.mkdir(parents=True, exist_ok=True)
    layout.lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
    try:
        return _run(paths, layout, device_name)
    finally:
        layout.lock.unlink(missing_ok=True)


def open_inputs(
    paths: ProjectPaths, layout: AblationLayout, device_name: str | None
) -> dict[str, ProbeInputs]:
    """One opened input per ``tel+status`` convention the plan reads.

    Args:
        paths: Resolved project paths.
        layout: The resolved layout.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The inputs, keyed by convention.
    """
    runner = layout.runner
    gate_run = load_config(paths.repo_root / runner.gate_config, GateCheckConfig)
    return {
        convention: open_probe_inputs(
            paths,
            runner.mixture_config,
            runner.ladder_config,
            layout.arm_of(convention),
            runner.rung,
            runner.optimiser.selection_windows,
            gate_run.held_out_source,
            device_name,
            window_rule=runner.probe.window_rule,
            status_rows=runner.probe.status_rows,
        )
        for convention in layout.conventions()
    }


def check_assertions(
    paths: ProjectPaths, layout: AblationLayout, inputs_by_convention: dict[str, ProbeInputs]
) -> dict[str, Any]:
    """Run ADR-0027's three registered assertions and record what they measured.

    Args:
        paths: Resolved project paths.
        layout: The resolved layout.
        inputs_by_convention: The opened inputs, keyed by convention.

    Returns:
        The measured values, as written to ``assertions.json``.
    """
    runner, gate = layout.runner, layout.gate
    sampler = {
        arm: assert_sampler_counts(runner, layout.mixture, arm)
        for arm in (runner.reference_arm, *runner.arms)
    }
    logger.info("ablation: sampler counts pass for %s", ", ".join(sampler))
    index: dict[str, Any] = {}
    if "raw" in inputs_by_convention and "normalized" in inputs_by_convention:
        index = assert_raw_index_matches_normalized(
            _framed_sets(inputs_by_convention["normalized"], layout),
            _framed_sets(inputs_by_convention["raw"], layout),
            gate.windows,
            gate.positives,
        )
        assert_registered_truncation(runner, index)
        logger.info("ablation: raw index matches the normalized index: %s", index)
    gate_probes = assert_random_init_reads_raw(layout.plan, inputs_by_convention, gate)
    for line in gate_probes:
        logger.info("ablation: gate probe %s", line)
    record = {
        "sampler_counts": sampler,
        "raw_index": index,
        "gate_probes": gate_probes,
        "written_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "git_sha": git_sha(paths.repo_root),
    }
    write_json(layout.assertions_record, record)
    return record


def _framed_sets(inputs: ProbeInputs, layout: AblationLayout) -> list[JointWindowSet]:
    """The pooled stride-12 test window sets, framed over one input's stream."""
    sets = _test_split(inputs, layout).sampler.sets
    return [s for s in sets if isinstance(s, JointWindowSet)]


def _test_split(inputs: ProbeInputs, layout: AblationLayout) -> SplitEval:
    """The pooled stride-12 test split, framed as ADR-0025 §2's R0 windows."""
    evaluation = inputs.ladder.evaluation
    return inputs.frame(
        build_split(
            inputs.telemetry,
            "test",
            None,
            layout.stride,
            evaluation.seed,
            evaluation.batch_windows,
            layout.gate.label,
            sources=inputs.mixture.training_sources,
        )
    )


def _run(paths: ProjectPaths, layout: AblationLayout, device_name: str | None) -> Path:
    runner = layout.runner
    gate_run = load_config(paths.repo_root / runner.gate_config, GateCheckConfig)
    cadence = load_config(paths.repo_root / runner.probe.cadence_config, ProbeCadenceConfig)
    sha, dirty = git_sha(paths.repo_root), tree_dirty(paths.repo_root)
    logger.info("ablation: git %s%s", sha, " (dirty)" if dirty else "")
    inputs_by_convention = open_inputs(paths, layout, device_name)
    check_assertions(paths, layout, inputs_by_convention)
    seeds = sorted({item.seed for item in layout.plan if item.is_random_init})
    if seeds:
        spec = next(iter(inputs_by_convention.values())).spec
        for line in materialise_random_init(layout, spec, seeds):
            logger.info("ablation: random-init %s", line)
    pretrained = _pretrainings(paths, layout, inputs_by_convention)
    probed = _probes(
        paths, layout, inputs_by_convention, cadence, gate_run.held_out_source, sha, dirty
    )
    scored = _scorings(paths, layout, inputs_by_convention, sha, dirty)
    probes_done = [item.name for item in layout.plan if layout.probe_record(item).exists()]
    done = [item.name for item in layout.plan if layout.scores(item).exists()]
    write_json(
        layout.status,
        {
            "config_hash": config_hash(layout.gate),
            "runner_hash": config_hash(runner),
            "pretrained_this_invocation": pretrained,
            "probes_done": probes_done,
            "probes_total": len(layout.plan),
            "scorings_done": done,
            "scorings_total": len(layout.plan),
            "probed_this_invocation": probed,
            "scored_this_invocation": scored,
            "written_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "git_sha": sha,
            "tree_dirty": dirty,
        },
    )
    logger.info(
        "ablation: DONE %d of %d probes, %d of %d scorings; all done: %s",
        len(probes_done),
        len(layout.plan),
        len(done),
        len(layout.plan),
        len(done) == len(layout.plan),
    )
    return layout.status


def _pretrainings(
    paths: ProjectPaths, layout: AblationLayout, inputs_by_convention: dict[str, ProbeInputs]
) -> list[str]:
    """Phase one: six pretrainings, each skipped if its record exists."""
    runner = layout.runner
    computed: list[str] = []
    for arm in runner.arms:
        convention = next(a.status_convention for a in layout.mixture.arms if a.name == arm)
        inputs = inputs_by_convention[convention]
        config = ArmPretraining(runner=runner, arm=arm)
        for seed in runner.seeds:
            record = layout.lm_record(arm, seed)
            if record.exists():
                logger.info("ablation pretrain %s seed %d: on disk, skipped", arm, seed)
                continue
            logger.info("=== ablation pretrain %s seed %d (%s streams) ===", arm, seed, convention)
            started = time.perf_counter()
            lm, streams = pretrain_joint(seed, config, inputs, layout.out_dir, layout.log_dir)
            windows = {stream: int(body["windows"]) for stream, body in streams.items()}
            assert_sampler_counts(runner, layout.mixture, arm, drawn=windows)
            write_json(
                record,
                {
                    "arm": arm,
                    "seed": seed,
                    "convention": convention,
                    "tokens": lm.lm_tokens,
                    "steps": lm.lm_steps,
                    "seconds": lm.lm_seconds,
                    "selected": list(lm.lm_selected),
                    "history": lm.lm_history,
                    "final_train_loss": lm.lm_final_train_loss,
                    "checkpoint": relative(lm.checkpoint, paths.repo_root),
                    "streams": streams,
                    "wall_seconds": time.perf_counter() - started,
                },
            )
            computed.append(f"{arm}_seed{seed}")
            logger.info("ablation pretrain %s seed %d done in %.1f s", arm, seed, lm.lm_seconds)
    return computed


def _probes(
    paths: ProjectPaths,
    layout: AblationLayout,
    inputs_by_convention: dict[str, ProbeInputs],
    cadence: ProbeCadenceConfig,
    held_out_source: str,
    sha: str,
    dirty: bool,
) -> list[str]:
    """Phase two: the nine (d) probes, in plan order, each skipped if its record exists."""
    computed: list[str] = []
    total = len(layout.plan)
    for number, item in enumerate(layout.plan, 1):
        if layout.probe_record(item).exists():
            logger.info("ablation probe [%d/%d] %s: on disk, skipped", number, total, item.name)
            continue
        inputs = inputs_by_convention[item.convention]
        stage = inputs.ladder.risk
        assert isinstance(stage, PositiveAwareRiskStage)
        readout = layout.runner.probe.readout
        spec = risk_spec(
            layout.readout,
            readout,
            inputs.ladder_model.head_hidden,
            inputs.ladder_model.head_dropout,
            stage.label,
        )
        width = spec.input_width(inputs.spec.d_model)
        backbone = layout.backbone(item)
        logger.info(
            "=== ablation probe [%d/%d] %s: %s on %s seed %d, %s windows, head input %d ===",
            number,
            total,
            item.name,
            readout,
            item.family,
            item.seed,
            item.convention,
            width,
        )
        started = time.perf_counter()
        probe = probe_and_score(
            item.seed,
            backbone,
            inputs,
            held_out_source,
            layout.log_dir / f"{item.name}_probe.steps.csv",
            f"ablation/{item.name}/probe",
            save_to=layout.probe(item, role="selected"),
            pooling=READOUT_POOLING[readout],
            head_layers=READOUT_HEAD_LAYERS,
            unfrozen_blocks=READOUT_UNFROZEN_BLOCKS,
            text_positions=spec.text_positions,
            measure_steps=cadence.steps(stage.budget("probe").steps),
            measure_initial=cadence.measure_initial,
            save_final_to=layout.probe(item),
            score_test=False,
        )
        write_json(
            layout.probe_record(item),
            {
                "arm": item.arm,
                "family": item.family,
                "seed": item.seed,
                "convention": item.convention,
                "readout": readout,
                "head_input_width": width,
                "backbone": relative(backbone, paths.repo_root),
                "window_rule": layout.runner.probe.window_rule,
                "status_rows": layout.runner.probe.status_rows,
                "tel_status_root": inputs.tel_status.root.name if inputs.tel_status else None,
                "selected": list(probe.probe_selected),
                "final": list(probe.probe_history[-1]),
                "history": probe.probe_history,
                "selected_probe": relative(layout.probe(item, "selected"), paths.repo_root),
                "final_probe": relative(layout.probe(item), paths.repo_root),
                "prior_offset": probe.prior_offset,
                "natural_rate": probe.natural_rate,
                "positives_seen": probe.probe_positives_seen,
                "seconds": probe.probe_seconds,
                "wall_seconds": time.perf_counter() - started,
                "git_sha": sha,
                "tree_dirty": dirty,
            },
        )
        computed.append(item.name)
        logger.info(
            "ablation probe [%d/%d] %s done in %.1f s; selected %s, final %s",
            number,
            total,
            item.name,
            probe.probe_seconds,
            probe.probe_selected,
            probe.probe_history[-1],
        )
    return computed


def _scorings(
    paths: ProjectPaths,
    layout: AblationLayout,
    inputs_by_convention: dict[str, ProbeInputs],
    sha: str,
    dirty: bool,
) -> list[str]:
    """Phase three: the nine scorings of the final-step probes, in plan order.

    Args:
        paths: Resolved project paths.
        layout: The resolved layout.
        inputs_by_convention: The opened inputs, keyed by convention.
        sha: The commit the run is on.
        dirty: Whether the working tree differs from it.

    Returns:
        The scorings computed in this invocation.

    Raises:
        ValueError: If a scoring does not cover F3's windows, or a probe's re-scored selection
            AUPRC is not the one its training record holds.
    """
    splits: dict[str, SplitEval] = {}
    checks_file = layout.out_dir / "selection_check.json"
    checks: dict[str, Any] = (
        json.loads(checks_file.read_text(encoding="utf-8")) if checks_file.exists() else {}
    )
    computed: list[str] = []
    total = len(layout.plan)
    readout = layout.runner.probe.readout
    for number, item in enumerate(layout.plan, 1):
        path = layout.scores(item)
        inputs = inputs_by_convention[item.convention]
        reference = ScoredWindows.load(layout.h1.tel_only_scores(item.seed))
        if path.exists():
            if not ScoredWindows.load(path).same_windows(reference):
                raise ValueError(f"{path.name} on disk does not cover F3's windows")
            logger.info("ablation score [%d/%d] %s: on disk, skipped", number, total, item.name)
            continue
        if item.convention not in splits:
            splits[item.convention] = _test_split(inputs, layout)
        split = splits[item.convention]
        probe = layout.probe(item)
        record = json.loads(layout.probe_record(item).read_text(encoding="utf-8"))
        recorded = float(record["final"][1])
        logger.info("=== ablation score [%d/%d] %s ===", number, total, item.name)
        if probe.name not in checks:
            tick = time.perf_counter()
            measured = selection_auprc(probe, readout, inputs)
            checks[probe.name] = {
                "recorded": recorded,
                "rescored": measured,
                "difference": measured - recorded,
                "seconds": time.perf_counter() - tick,
            }
            write_json(checks_file, checks)
            logger.info(
                "%s selection AUPRC re-scored %.5f, recorded %.5f", probe.name, measured, recorded
            )
        if abs(float(checks[probe.name]["difference"])) > SELECTION_TOLERANCE:
            raise ValueError(
                f"{probe.name}: selection AUPRC re-scored {checks[probe.name]['rescored']:.5f}, "
                f"recorded {recorded:.5f}; the scoring path is not the probe's"
            )
        started_utc = datetime.now(tz=UTC).isoformat(timespec="seconds")
        tick = time.perf_counter()
        scored = score_saved_probe(probe, readout, inputs, split)
        seconds = time.perf_counter() - tick
        sidecar = {
            "seconds": seconds,
            "started_utc": started_utc,
            "finished_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "arm": item.arm,
            "family": item.family,
            "seed": item.seed,
            "convention": item.convention,
            "readout": readout,
            "role": FIXED_FINAL,
            "windows": "R0",
            "head_input_width": int(record["head_input_width"]),
            "probe": relative(probe, paths.repo_root),
            "prior_offset": float(record["prior_offset"]),
            "device": str(inputs.device),
            "git_sha": sha,
            "tree_dirty": dirty,
        }
        written = save_atomically(path, scored, split, float(record["prior_offset"]), sidecar)
        if not written.same_windows(reference):
            raise ValueError(f"{path.name} does not cover F3's windows")
        computed.append(item.name)
        logger.info("ablation score [%d/%d] %s done in %.1f s", number, total, item.name, seconds)
    return computed
