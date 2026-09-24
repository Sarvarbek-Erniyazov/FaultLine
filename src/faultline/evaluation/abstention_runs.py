"""F9-2's GPU half (ADR-0028 §1, §3): nine clean validation scorings, then twelve ladder scorings.

Nothing is trained. Every probe read here already exists and is read at its **final step**:

- **Validation (9).** ``tel_only`` (a), ``joint`` (a) and ``joint`` (d), seeds 1-3, on the clean
  2021 validation split (``kelmarsh__val`` + ``penmanshiel__val``, stride 12), framed as each
  arm's test scores were framed. τ and κ are fitted from these files alone (F9-3).
- **Ladder (12).** ``joint`` (d), seeds 1-3, on the 137,025-window test split's R0 windows, with
  the first k channels of ADR-0028 §3's one permutation masked to ``<nan>`` on every step, for
  k in {2, 4, 6, 8}. Text is kept.

**The probes are resolved through the runs that trained them** — F6-3's layout for the (a) reads,
F7''s for (d) — and each arm's registered test file (``abstention_v0.yaml``, ``test_scores``) must
be the file those layouts name. :func:`assert_validation_scoring` then checks, from the test
file's own timing sidecar, that the probe about to score validation is the one that scored test
and that it scored test in the framing validation is about to be read in.

**The masks** are built once per severity by :func:`ladder_channel_offsets`, which re-draws the
permutation from its seed and refuses any set that is not the registered one, not nested, or not
made of telemetry bin slots. The same offsets array is used for every seed and every window.
F6-3's :class:`~faultline.evaluation.h1_scoring.MaskedJointSampler` then checks every overwritten
token is a telemetry value, and a scoring is refused unless the tokens it masked equal the
retained steps × k.

**Resume is per artefact**, as F6-3's: a scores file on disk is re-checked against its reference
rows and skipped; scores and their sidecar are written so a scores file is always whole and timed.
``RUNNING.lock`` holds the running process's id.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

from faultline.config import config_hash, load_config
from faultline.evaluation.abstention_gate import CORE_CHANNELS, AbstentionConfig
from faultline.evaluation.care_attribution import mask_positions
from faultline.evaluation.checkpoint_selection import FIXED_FINAL
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.h1_scoring import (
    SELECTION_TOLERANCE,
    MaskedJointSampler,
    masked_joint_split,
    save_atomically,
    selection_auprc,
    timing_path,
    tree_dirty,
    write_json,
)
from faultline.evaluation.ladder import SplitEval, build_split
from faultline.evaluation.paired_control import score_saved_probe
from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.readout_runs import ReadoutLayout, readout_layout, relative
from faultline.evaluation.seed_replication import SeedReplicationConfig
from faultline.evaluation.variance_probe import open_probe_inputs
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.joint_windows import JointWindowSet

logger = get_logger(__name__)

#: The F7' run whose probes are ``joint`` (d).
JOINT_D_RUN = "R-joint-d"

#: F6-3's stage per (a) arm: S1 reads the joint backbones, S2 is control (iii) on ``tel_only``'s.
A_STAGES = {"joint_a": "S1", "tel_only_a": "S2"}

#: F3's validation scores, whose rows (not scores) every validation scoring must reproduce.
F3_VALIDATION_SCORES = "{rung}_trained_seed{seed}_val_stride{stride}_scores.npz"


# =====================================================================================
# the plan
# =====================================================================================


@dataclass(frozen=True)
class ArmProbe:
    """One arm's final-step probe at one seed, and the test file it already wrote.

    Attributes:
        arm: The arm's name in ADR-0028.
        seed: The seed.
        readout: The read-out the probe was trained under (``score_saved_probe``'s design).
        probe: The saved final-step probe state.
        test_scores: Its registered clean test scores.
        recorded_selection: The selection-split AUPRC its training record holds at the final step.
        prior_offset: The probe's prior offset.
    """

    arm: str
    seed: int
    readout: str
    probe: Path
    test_scores: Path
    recorded_selection: float
    prior_offset: float


@dataclass(frozen=True)
class AbstentionScoring:
    """One F9-2 scoring.

    Attributes:
        kind: ``validation`` or ``ladder``.
        arm: The arm scored.
        seed: The seed.
        severity: Channels masked (0 for validation).
        name: The file stem before ``_stride<k>_scores``.
    """

    kind: str
    arm: str
    seed: int
    severity: int
    name: str


def scoring_plan(config: AbstentionConfig) -> list[AbstentionScoring]:
    """The nine validation scorings (arm-major, seed-minor), then the twelve ladder scorings.

    Args:
        config: The loaded abstention configuration.

    Returns:
        The scorings, in the order they run.
    """
    plan = [
        AbstentionScoring("validation", arm.name, s, 0, f"{arm.name}_seed{s}_final_R0_val")
        for arm in config.arms
        for s in config.seeds
    ]
    plan += [
        AbstentionScoring(
            "ladder", config.ladder.arm, s, k, f"{config.ladder.arm}_seed{s}_final_R0_masked_k{k}"
        )
        for k in config.ladder.severities
        for s in config.seeds
    ]
    return plan


@dataclass
class AbstentionLayout:
    """Every file F9 reads or writes, named once.

    Attributes:
        config: The abstention configuration.
        readout: F7''s layout, which holds F6-3's as ``readout.h1``.
        out_dir: ``checkpoints/abstention_v<version>_<hash>``: scores, sidecars, checks.
        f3_dir: F3's output directory, whose validation rows every validation scoring reproduces.
        plan: The scorings, in order.
    """

    config: AbstentionConfig
    readout: ReadoutLayout
    out_dir: Path
    f3_dir: Path
    plan: list[AbstentionScoring]

    def scores(self, scoring: AbstentionScoring) -> Path:
        """A scoring's scores file."""
        return self.out_dir / f"{scoring.name}_stride{self.config.stride}_scores.npz"

    def validation_scores(self, arm: str, seed: int) -> Path:
        """An arm's clean validation scores at a seed."""
        return self.out_dir / f"{arm}_seed{seed}_final_R0_val_stride{self.config.stride}_scores.npz"

    def ladder_scores(self, seed: int, severity: int) -> Path:
        """``joint`` (d)'s masked test scores at a seed and severity."""
        name = f"{self.config.ladder.arm}_seed{seed}_final_R0_masked_k{severity}"
        return self.out_dir / f"{name}_stride{self.config.stride}_scores.npz"

    def test_scores(self, arm: str, seed: int, root: Path) -> Path:
        """An arm's registered clean test scores at a seed."""
        return root / self.config.arm(arm).test_scores.format(seed=seed)

    def f3_validation(self, seed: int) -> Path:
        """F3's validation scores at a seed: the reference rows of every validation scoring."""
        name = F3_VALIDATION_SCORES.format(
            rung=self.readout.rung, seed=seed, stride=self.config.stride
        )
        return self.f3_dir / name

    @property
    def lock(self) -> Path:
        """The running process's lock."""
        return self.out_dir / "RUNNING.lock"

    @property
    def status(self) -> Path:
        """The status file the runner returns."""
        return self.out_dir / "abstention_status.json"

    @property
    def checks_file(self) -> Path:
        """Every probe's re-scored selection AUPRC."""
        return self.out_dir / "selection_check.json"


def abstention_layout(paths: ProjectPaths, config_path: Path) -> AbstentionLayout:
    """Resolve every path F9 touches from its configurations.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/eval/abstention_v0.yaml``.

    Returns:
        The layout.
    """
    config = load_config(config_path, AbstentionConfig)
    readout = readout_layout(paths, paths.repo_root / config.readout_config)
    f3 = load_config(paths.repo_root / readout.h1.gate.reference_config, SeedReplicationConfig)
    return AbstentionLayout(
        config=config,
        readout=readout,
        out_dir=paths.checkpoints_dir / f"abstention_v{config.version}_{config_hash(config)}",
        f3_dir=paths.checkpoints_dir / f"seed_replication_v{f3.version}_{config_hash(f3)}",
        plan=scoring_plan(config),
    )


def arm_probe(paths: ProjectPaths, layout: AbstentionLayout, arm: str, seed: int) -> ArmProbe:
    """Resolve one arm's final-step probe through the run that trained it.

    Args:
        paths: Resolved project paths.
        layout: The resolved layout.
        arm: The arm's name in ADR-0028.
        seed: The seed.

    Returns:
        The probe, its registered test file and its training record's numbers.

    Raises:
        ValueError: If the arm is unknown, the resolved probe is not a final-step state, or the
            test file the training layout names is not the one ADR-0028 registered.
    """
    h1, readout = layout.readout.h1, layout.readout
    declared = layout.config.arm(arm)
    if arm in A_STAGES:
        scoring = next(
            s for s in h1.plan if s.stage == A_STAGES[arm] and s.seed == seed and s.farm is None
        )
        if scoring.role != FIXED_FINAL:
            raise ValueError(f"{arm} seed {seed}: F6-3's {scoring.name} is not a final-step read")
        record = h1.probe_record(scoring)
        found = ArmProbe(
            arm=arm,
            seed=seed,
            readout=h1.arms.runner.probe.design,
            probe=h1.probe(scoring),
            test_scores=h1.scores(scoring),
            recorded_selection=float(record["final"][1]),
            prior_offset=float(record["prior_offset"]),
        )
    elif arm == "joint_d":
        item = next(i for i in readout.plan if i.run == JOINT_D_RUN and i.seed == seed)
        record = json.loads(readout.probe_record(item).read_text(encoding="utf-8"))
        found = ArmProbe(
            arm=arm,
            seed=seed,
            readout=item.readout,
            probe=readout.probe(item, FIXED_FINAL),
            test_scores=readout.scores(item),
            recorded_selection=float(record["final"][1]),
            prior_offset=float(record["prior_offset"]),
        )
    else:
        raise ValueError(f"unknown arm {arm!r}")
    if found.readout != declared.readout:
        raise ValueError(
            f"{arm}: the probe reads {found.readout}, ADR-0028 names {declared.readout}"
        )
    if not found.probe.name.endswith("_final_probe.pt"):
        raise ValueError(f"{arm} seed {seed}: {found.probe.name} is not a final-step probe")
    registered = layout.test_scores(arm, seed, paths.repo_root)
    if found.test_scores.resolve() != registered.resolve():
        raise ValueError(
            f"{arm} seed {seed}: the training layout names "
            f"{relative(found.test_scores, paths.repo_root)}, ADR-0028 registered "
            f"{relative(registered, paths.repo_root)}"
        )
    return found


# =====================================================================================
# the three assertions
# =====================================================================================


def ladder_channel_offsets(
    config: AbstentionConfig, step: list[str]
) -> dict[int, tuple[list[str], np.ndarray]]:
    """Each severity's channels and their slots within a step, checked against ADR-0028 §3.

    Assertion 1's static half. The permutation is re-drawn from the registered seed over the step
    layout's core channels; each set must be its first k channels, equal to the registered set,
    nested in the next, and every slot must be a telemetry bin slot (never ``<sep>``) holding a
    channel of the set. The returned arrays are the only ones any seed or window is masked with.

    Args:
        config: The loaded abstention configuration.
        step: The shard manifest's step layout: ``<sep>``, then the channels.

    Returns:
        Per severity, its channels and their offsets within a step, ascending.

    Raises:
        ValueError: On any departure from the record.
    """
    core = [name for name in step if name != "<sep>"]
    if step[0] != "<sep>" or tuple(core) != CORE_CHANNELS:
        raise ValueError(f"the step layout {step} is not <sep> then ADR-0028's core channels")
    order = np.random.default_rng(config.ladder.seed).permutation(len(CORE_CHANNELS))
    drawn = [CORE_CHANNELS[int(i)] for i in order]
    out: dict[int, tuple[list[str], np.ndarray]] = {}
    previous: set[int] = set()
    for k in config.ladder.severities:
        channels = list(config.ladder.sets[k])
        if channels != drawn[:k]:
            raise ValueError(f"k={k}: registered {channels}, the permutation gives {drawn[:k]}")
        offsets = mask_positions(step, channels, 1)
        if offsets.size != k or int(offsets.min()) < 1 or int(offsets.max()) >= len(step):
            raise ValueError(f"k={k}: offsets {offsets.tolist()} are not {k} telemetry bin slots")
        if sorted(step[int(o)] for o in offsets) != sorted(channels):
            raise ValueError(f"k={k}: offsets {offsets.tolist()} do not hold {channels}")
        if not previous <= set(offsets.tolist()):
            raise ValueError(f"k={k}: offsets do not contain the smaller severity's")
        previous = set(offsets.tolist())
        out[k] = (channels, offsets)
    return out


def retained_slots(sampler: MaskedJointSampler) -> int:
    """Whole telemetry steps retained over every window the sampler reads."""
    return sum(
        int(np.asarray(s.steps_retained)[sampler.index[sampler.index[:, 0] == i, 1]].sum())
        for i, s in enumerate(sampler.sets)
        if isinstance(s, JointWindowSet)
    )


def assert_masked_count(name: str, masked: int, retained_steps: int, severity: int) -> None:
    """Assertion 1's run-time half: masked slots = retained steps × k.

    Raises:
        ValueError: If the counts differ.
    """
    if masked != retained_steps * severity:
        raise ValueError(
            f"{name}: {masked:,} tokens masked, {retained_steps:,} retained steps × {severity} "
            f"= {retained_steps * severity:,} channel slots"
        )


def assert_validation_scoring(probe: ArmProbe, windows: str, root: Path) -> dict[str, Any]:
    """Assertion 2: validation reads the probe that scored test, at its final step, in its framing.

    The test file's timing sidecar is the witness: it names the probe that wrote the scores, the
    role it was read at and the window framing.

    Args:
        probe: The resolved probe.
        windows: The framing validation is about to be read in.
        root: The repository root.

    Returns:
        The test sidecar.

    Raises:
        ValueError: If the sidecar names another probe, a role other than the final step, or a
            framing other than ``windows``.
    """
    sidecar: dict[str, Any] = json.loads(timing_path(probe.test_scores).read_text(encoding="utf-8"))
    named = relative(probe.probe, root)
    if sidecar.get("probe") != named:
        raise ValueError(
            f"{probe.test_scores.name} was scored by {sidecar.get('probe')}, not {named}"
        )
    if sidecar.get("role") != FIXED_FINAL:
        raise ValueError(f"{probe.test_scores.name} was read at {sidecar.get('role')}, not final")
    if sidecar.get("windows") != windows:
        raise ValueError(
            f"{probe.test_scores.name} was scored on {sidecar.get('windows')} windows; "
            f"validation is framed as {windows}"
        )
    return sidecar


def assert_aligned(name: str, scored: ScoredWindows, reference: ScoredWindows) -> None:
    """Assertion 3's per-file half: a scoring covers its reference's rows, in order.

    Raises:
        ValueError: If it does not.
    """
    if not scored.same_windows(reference):
        raise ValueError(f"{name} does not cover its reference's windows row for row")


# =====================================================================================
# the run
# =====================================================================================


def preflight(paths: ProjectPaths, layout: AbstentionLayout) -> tuple[list[str], list[str]]:
    """What must exist before F9-2 starts, and where each scoring stands.

    Args:
        paths: Resolved project paths.
        layout: The resolved layout.

    Returns:
        The problems (empty when F9-2 may start) and one status line per scoring.
    """
    root, config = paths.repo_root, layout.config
    problems: list[str] = []
    h1 = layout.readout.h1
    if (config.stride, config.label) != (h1.gate.stride, h1.gate.label):
        problems.append(f"stride/label {(config.stride, config.label)} are not F6-3's")
    if config.h1_gate_config != layout.readout.config.h1_gate_config:
        problems.append(f"{config.h1_gate_config} is not F7''s h1 gate configuration")
    required: list[Path] = []
    for arm in config.arms:
        for seed in config.seeds:
            try:
                probe = arm_probe(paths, layout, arm.name, seed)
            except (ValueError, FileNotFoundError, StopIteration) as error:
                problems.append(f"{arm.name} seed {seed}: {error}")
                continue
            required += [probe.probe, probe.test_scores, timing_path(probe.test_scores)]
    required += [layout.f3_validation(seed) for seed in config.seeds]
    missing = sorted({p for p in required if not p.exists()})
    problems += [f"missing: {relative(p, root)}" for p in missing]
    if not missing and not problems:
        for arm in config.arms:
            for seed in config.seeds:
                try:
                    assert_validation_scoring(arm_probe(paths, layout, arm.name, seed), "R0", root)
                except ValueError as error:
                    problems.append(str(error))
    if layout.lock.exists():
        problems.append(
            f"{relative(layout.lock, root)} exists (pid "
            f"{layout.lock.read_text(encoding='utf-8').strip()}): a run may be active; check the "
            "process list, and delete the lock only if that process is gone"
        )
    if not torch.cuda.is_available():
        problems.append("CUDA is not available: F9-2 is a GPU run")
    lines = [
        f"[{i:2d}/{len(layout.plan)}] {s.kind} {s.name}: "
        f"{'done' if layout.scores(s).exists() else 'to run'}"
        for i, s in enumerate(layout.plan, 1)
    ]
    return problems, lines


def run_abstention(paths: ProjectPaths, config_path: Path, device_name: str | None = None) -> Path:
    """Run every F9-2 scoring not yet on disk: validation first, then the ladder.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/eval/abstention_v0.yaml``.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The status file, ``abstention_status.json`` in the output directory.

    Raises:
        RuntimeError: If a pre-flight problem stands.
    """
    layout = abstention_layout(paths, config_path)
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


def _run(paths: ProjectPaths, layout: AbstentionLayout, device_name: str | None) -> Path:
    config, root = layout.config, paths.repo_root
    runner = layout.readout.h1.arms.runner
    gate = load_config(root / runner.gate_config, GateCheckConfig)
    sha, dirty = git_sha(root), tree_dirty(root)
    logger.info("abstention: git %s%s", sha, " (dirty)" if dirty else "")
    inputs = open_probe_inputs(
        paths,
        runner.mixture_config,
        runner.ladder_config,
        runner.arm,
        runner.rung,
        runner.optimiser.selection_windows,
        gate.held_out_source,
        device_name,
        window_rule=runner.probe.window_rule,
        status_rows=runner.probe.status_rows,
    )
    probe_config = layout.readout.config.probe
    if (probe_config.window_rule, probe_config.status_rows) != (
        runner.probe.window_rule,
        runner.probe.status_rows,
    ):
        raise ValueError("F7''s probes and F6-2's are framed differently; one input cannot serve")
    step = [str(name) for name in inputs.telemetry.manifest["step"]]
    masks = ladder_channel_offsets(config, step)
    splits: dict[str, SplitEval] = {}

    def split(which: str) -> SplitEval:
        """The pooled stride-12 split, R0-framed; ``val`` or ``test``."""
        if which not in splits:
            evaluation = inputs.ladder.evaluation
            m1 = build_split(
                inputs.telemetry,
                which,
                None,
                config.stride,
                evaluation.seed,
                evaluation.batch_windows,
                config.label,
                sources=inputs.mixture.training_sources,
            )
            if which == "val":
                keys = [s.key for s in m1.sampler.sets]
                if keys != config.splits.validation.shard_keys:
                    raise ValueError(f"validation reads {keys}, ADR-0028 names its shard keys")
            splits[which] = inputs.frame(m1)
        return splits[which]

    checks: dict[str, Any] = (
        json.loads(layout.checks_file.read_text(encoding="utf-8"))
        if layout.checks_file.exists()
        else {}
    )
    computed: list[str] = []
    total = len(layout.plan)
    for number, scoring in enumerate(layout.plan, 1):
        path = layout.scores(scoring)
        probe = arm_probe(paths, layout, scoring.arm, scoring.seed)
        test_sidecar = assert_validation_scoring(probe, "R0", root)
        if scoring.kind == "validation":
            reference = ScoredWindows.load(layout.f3_validation(scoring.seed))
            counts = config.splits.validation
        else:
            reference = ScoredWindows.load(probe.test_scores)
            counts = config.splits.test
        if (reference.labels.size, int(reference.labels.sum())) != (
            counts.windows,
            counts.positives,
        ):
            raise ValueError(
                f"{scoring.name}: reference rows {reference.labels.size:,} / "
                f"{int(reference.labels.sum()):,}, registered {counts.windows:,} / "
                f"{counts.positives:,}"
            )
        if path.exists():
            assert_aligned(path.name, ScoredWindows.load(path), reference)
            logger.info("abstention [%d/%d] %s: on disk, skipped", number, total, scoring.name)
            continue
        logger.info("=== abstention [%d/%d] %s ===", number, total, scoring.name)
        if probe.probe.name not in checks:
            tick = time.perf_counter()
            measured = selection_auprc(probe.probe, probe.readout, inputs)
            checks[probe.probe.name] = {
                "recorded": probe.recorded_selection,
                "rescored": measured,
                "difference": measured - probe.recorded_selection,
                "seconds": time.perf_counter() - tick,
            }
            write_json(layout.checks_file, checks)
            logger.info(
                "%s selection AUPRC re-scored %.5f, recorded %.5f",
                probe.probe.name,
                measured,
                probe.recorded_selection,
            )
        if abs(float(checks[probe.probe.name]["difference"])) > SELECTION_TOLERANCE:
            raise ValueError(
                f"{probe.probe.name}: selection AUPRC re-scored "
                f"{checks[probe.probe.name]['rescored']:.5f}, recorded "
                f"{probe.recorded_selection:.5f}; the scoring path is not the probe's"
            )
        extra: dict[str, Any] = {}
        view = split("val" if scoring.kind == "validation" else "test")
        masked: MaskedJointSampler | None = None
        if scoring.kind == "ladder":
            channels, offsets = masks[scoring.severity]
            nan_id = int(dict(inputs.telemetry.manifest["specials"])["<nan>"])
            view = masked_joint_split(view, offsets, nan_id, inputs.telemetry.vocab_size)
            assert isinstance(view.sampler, MaskedJointSampler)
            masked = view.sampler
            extra = {
                "severity": scoring.severity,
                "channels": channels,
                "channel_offsets": offsets.tolist(),
                "nan_id": nan_id,
                "expected_masked_tokens": retained_slots(masked) * scoring.severity,
            }
        started_utc = datetime.now(tz=UTC).isoformat(timespec="seconds")
        tick = time.perf_counter()
        scored = score_saved_probe(probe.probe, probe.readout, inputs, view)
        seconds = time.perf_counter() - tick
        if masked is not None:
            extra["masked_tokens"] = masked.masked
            assert_masked_count(
                scoring.name, masked.masked, retained_slots(masked), scoring.severity
            )
        sidecar = {
            "seconds": seconds,
            "started_utc": started_utc,
            "finished_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "kind": scoring.kind,
            "arm": scoring.arm,
            "readout": probe.readout,
            "seed": scoring.seed,
            "role": FIXED_FINAL,
            "windows": "R0",
            "split": "val" if scoring.kind == "validation" else "test",
            "probe": relative(probe.probe, root),
            "test_scores": relative(probe.test_scores, root),
            "test_windows": test_sidecar.get("windows"),
            "prior_offset": probe.prior_offset,
            "device": str(inputs.device),
            "git_sha": sha,
            "tree_dirty": dirty,
            **extra,
        }
        written = save_atomically(path, scored, view, probe.prior_offset, sidecar)
        assert_aligned(path.name, written, reference)
        computed.append(scoring.name)
        logger.info("abstention [%d/%d] %s done in %.1f s", number, total, scoring.name, seconds)

    done = [s.name for s in layout.plan if layout.scores(s).exists()]
    write_json(
        layout.status,
        {
            "config_hash": config_hash(config),
            "scorings_done": done,
            "scorings_total": total,
            "computed_this_invocation": computed,
            "ladder_offsets": {str(k): v[1].tolist() for k, v in masks.items()},
            "written_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "git_sha": sha,
            "tree_dirty": dirty,
        },
    )
    logger.info(
        "abstention: DONE %d of %d scorings; all done: %s", len(done), total, len(done) == total
    )
    return layout.status
