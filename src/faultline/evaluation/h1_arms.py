"""F6-2 (ADR-0025 §8): pretrain the joint arm, probe it, and probe control (iii). Nothing is scored.

Per seed k of ``configs/train/h1_arms_v0.yaml``, in this order:

1. **Joint pretraining.** ``pretrain_joint``: the gate run's protocol (S2, 763 steps, 50,003,968
   tokens), windows drawn by the mixture sampler in joint_v1's ratio.
2. **The joint probe.** §a on the joint backbone under G3's cadence, reading the tail-anchored R0
   windows (ADR-0025 §2). The selected and the final states are both saved; the final one is read
   (fixed-final-step selection).
3. **Control (iii).** The same probe on ``tel_only`` seed k's saved backbone, on the same windows.

**Scoring is F6-3's.** No test window is read here (``score_test=False``).

**Resume is per artefact.** A stage whose record file exists is skipped:

- ``S2_joint_seed{k}_lm.json``: pretraining finished (written after ``S2_joint_seed{k}.pt``).
- ``S2_joint_seed{k}_probe.json``: the joint probe finished (after ``..._probe.pt`` and
  ``..._final_probe.pt``).
- ``S2_tel_only_seed{k}_on_joint_probe.json``: control (iii) finished.

A stage interrupted before its record is written is re-run from its start. Pretraining keeps no
mid-run checkpoint, and a seeded re-run starts from the same state. ``RUNNING.lock`` holds the
running process's id and is removed when the process ends, whether it succeeded or not.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch

from faultline.config import config_hash, load_config
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.h1_gate import H1ArmsConfig, H1GateConfig
from faultline.evaluation.probe_cadence import ProbeCadenceConfig
from faultline.evaluation.probe_control import HEAD_LAYERS, POOLING, UNFROZEN_BLOCKS
from faultline.evaluation.seed_replication import SeedReplicationConfig
from faultline.evaluation.variance_probe import (
    ProbeInputs,
    open_probe_inputs,
    pretrain_joint,
    probe_and_score,
)
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.config import PositiveAwareRiskStage
from faultline.training.mixture import STREAM_DIRS, JointMixtureConfig

logger = get_logger(__name__)


@dataclass
class ArmsLayout:
    """Every file F6-2 reads or writes, named once.

    Attributes:
        runner: The runner configuration.
        out_dir: Checkpoints and records, ``checkpoints/h1_arms_v0_<hash>``.
        log_dir: Per-step training logs, tracked beside the reports.
        joint_root: The joint_v1 shard directory.
        tel_only: Per seed, ``tel_only``'s saved final-budget backbone.
    """

    runner: H1ArmsConfig
    out_dir: Path
    log_dir: Path
    joint_root: Path
    tel_only: dict[int, Path] = field(default_factory=dict)

    def backbone(self, seed: int) -> Path:
        """The joint backbone of a seed."""
        return self.out_dir / f"{self.runner.rung}_{self.runner.arm}_seed{seed}.pt"

    def lm_record(self, seed: int) -> Path:
        """The pretraining record: its presence marks pretraining finished."""
        return self.out_dir / f"{self.runner.rung}_{self.runner.arm}_seed{seed}_lm.json"

    def probe_name(self, seed: int, control: bool) -> str:
        """The joint probe's or control (iii)'s file stem."""
        if control:
            return f"{self.runner.rung}_tel_only_seed{seed}_on_joint"
        return f"{self.runner.rung}_{self.runner.arm}_seed{seed}"

    def probe_record(self, seed: int, control: bool) -> Path:
        """A probe's record: its presence marks the probe finished."""
        return self.out_dir / f"{self.probe_name(seed, control)}_probe.json"

    def done(self, seed: int) -> bool:
        """Whether every F6-2 stage of a seed has its record."""
        return all(
            p.exists()
            for p in (
                self.lm_record(seed),
                self.probe_record(seed, False),
                self.probe_record(seed, True),
            )
        )


def arms_layout(paths: ProjectPaths, config_path: Path, gate_path: Path) -> ArmsLayout:
    """Resolve every path F6-2 touches from its configurations.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/train/h1_arms_v0.yaml``.
        gate_path: ``configs/eval/h1_gate_v0.yaml``, for ``tel_only``'s runs.

    Returns:
        The layout.
    """
    runner = load_config(config_path, H1ArmsConfig)
    h1 = load_config(gate_path, H1GateConfig)
    gate = load_config(paths.repo_root / runner.gate_config, GateCheckConfig)
    replication = load_config(paths.repo_root / h1.reference_config, SeedReplicationConfig)
    mixture = load_config(paths.repo_root / runner.mixture_config, JointMixtureConfig)
    gate_dir = paths.checkpoints_dir / f"gate_check_v{gate.version}_{config_hash(gate)}"
    replication_dir = (
        paths.checkpoints_dir
        / f"seed_replication_v{replication.version}_{config_hash(replication)}"
    )
    tel_only = {
        seed: (gate_dir if seed == gate.seed else replication_dir)
        / f"{gate.rung}_{gate.arm}_seed{seed}.pt"
        for seed in runner.seeds
    }
    return ArmsLayout(
        runner=runner,
        out_dir=paths.checkpoints_dir / f"h1_arms_v{runner.version}_{config_hash(runner)}",
        log_dir=paths.data_reports_dir / f"h1_arms_v{runner.version}_steps",
        joint_root=paths.data_root
        / "shards"
        / "joint"
        / f"joint_v{mixture.version}_{config_hash(mixture)}",
        tel_only=tel_only,
    )


def preflight(paths: ProjectPaths, layout: ArmsLayout) -> tuple[list[str], list[str]]:
    """What must exist before F6-2 starts, and where each seed stands.

    Args:
        paths: Resolved project paths.
        layout: The resolved layout.

    Returns:
        The problems (empty when F6-2 may start) and one status line per seed.
    """
    problems: list[str] = []
    root = layout.joint_root
    mixture = load_config(paths.repo_root / layout.runner.mixture_config, JointMixtureConfig)
    arm = next(a for a in mixture.arms if a.name == layout.runner.arm)
    status_dir = root / f"{STREAM_DIRS['tel+status']}_{arm.status_convention}"
    required = [root / "manifest.json"]
    for source in mixture.training_sources:
        required.append(root / STREAM_DIRS["tel"] / f"{source}__train.runs.parquet")
        for split in ("train", "val", "test"):
            required.append(status_dir / f"{source}__{split}.bin")
        required.append(status_dir / f"{source}__train.runs.parquet")
    if not list((root / STREAM_DIRS["txt"]).glob("*__train.bin")):
        problems.append(f"no txt train shard under {root / STREAM_DIRS['txt']}")
    required += list(layout.tel_only.values())
    problems += [
        f"missing: {p.relative_to(paths.repo_root).as_posix()}" for p in required if not p.exists()
    ]
    lock = layout.out_dir / "RUNNING.lock"
    if lock.exists():
        problems.append(
            f"{lock.relative_to(paths.repo_root).as_posix()} exists (pid "
            f"{lock.read_text(encoding='utf-8').strip()}): a run may be active; check the "
            "process list, and delete the lock only if that process is gone"
        )
    if not torch.cuda.is_available():
        problems.append("CUDA is not available: F6-2 is a GPU run")
    status = []
    for seed in layout.runner.seeds:
        stages = {
            "pretraining": layout.lm_record(seed).exists(),
            "joint probe": layout.probe_record(seed, False).exists(),
            "control (iii)": layout.probe_record(seed, True).exists(),
        }
        status.append(
            f"seed {seed}: "
            + ", ".join(f"{name} {'done' if done else 'to run'}" for name, done in stages.items())
        )
    return problems, status


def run_h1_arms(
    paths: ProjectPaths,
    config_path: Path,
    gate_path: Path,
    seeds: list[int] | None = None,
    device_name: str | None = None,
) -> Path:
    """Run F6-2 for the given seeds, resuming from whatever is on disk.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/train/h1_arms_v0.yaml``.
        gate_path: ``configs/eval/h1_gate_v0.yaml``.
        seeds: Seeds to run, in order; every configured seed when omitted.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The status file, ``h1_arms_status.json`` in the output directory.

    Raises:
        RuntimeError: If a pre-flight problem stands.
        ValueError: If a requested seed is not configured.
    """
    layout = arms_layout(paths, config_path, gate_path)
    runner = layout.runner
    wanted = seeds or runner.seeds
    if not set(wanted) <= set(runner.seeds):
        raise ValueError(f"seeds {wanted} are not all in {runner.seeds}")
    problems, _ = preflight(paths, layout)
    if device_name == "cpu":
        problems = [p for p in problems if not p.startswith("CUDA")]
    if problems:
        raise RuntimeError("pre-flight failed:\n" + "\n".join(problems))
    layout.out_dir.mkdir(parents=True, exist_ok=True)
    lock = layout.out_dir / "RUNNING.lock"
    lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
    try:
        gate = load_config(paths.repo_root / runner.gate_config, GateCheckConfig)
        cadence = load_config(paths.repo_root / runner.probe.cadence_config, ProbeCadenceConfig)
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
        for seed in wanted:
            run_seed(seed, layout, inputs, cadence, gate.held_out_source, paths)
            logger.info("h1-arms: seed %d done", seed)
        status = layout.out_dir / "h1_arms_status.json"
        status.write_text(
            json.dumps(
                {
                    "config_hash": config_hash(runner),
                    "seeds_done": [s for s in runner.seeds if layout.done(s)],
                    "written_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        done = [s for s in runner.seeds if layout.done(s)]
        logger.info(
            "h1-arms: DONE seeds %s; all configured seeds done: %s", wanted, done == runner.seeds
        )
        return status
    finally:
        lock.unlink(missing_ok=True)


def run_seed(
    seed: int,
    layout: ArmsLayout,
    inputs: ProbeInputs,
    cadence: ProbeCadenceConfig,
    held_out_source: str,
    paths: ProjectPaths,
) -> None:
    """One seed's pretraining, joint probe and control (iii), each skipped if its record exists."""
    runner = layout.runner
    if not layout.lm_record(seed).exists():
        logger.info("=== h1-arms: pretraining %s seed %d ===", runner.arm, seed)
        lm, streams = pretrain_joint(seed, runner, inputs, layout.out_dir, layout.log_dir)
        _write(
            layout.lm_record(seed),
            {
                "tokens": lm.lm_tokens,
                "steps": lm.lm_steps,
                "seconds": lm.lm_seconds,
                "selected": list(lm.lm_selected),
                "history": lm.lm_history,
                "final_train_loss": lm.lm_final_train_loss,
                "checkpoint": lm.checkpoint.relative_to(paths.repo_root).as_posix(),
                "streams": streams,
            },
        )
    for control in (False, True):
        record = layout.probe_record(seed, control)
        if record.exists():
            continue
        name = layout.probe_name(seed, control)
        backbone = layout.tel_only[seed] if control else layout.backbone(seed)
        logger.info("=== h1-arms: probing %s under the G3 cadence ===", name)
        stage = inputs.ladder.risk
        assert isinstance(stage, PositiveAwareRiskStage)
        design = runner.probe.design
        started = time.perf_counter()
        probe = probe_and_score(
            seed,
            backbone,
            inputs,
            held_out_source,
            layout.log_dir / f"{name}_probe.steps.csv",
            f"h1_arms/{name}/probe",
            save_to=layout.out_dir / f"{name}_probe.pt",
            pooling=POOLING[design],
            head_layers=HEAD_LAYERS[design],
            unfrozen_blocks=UNFROZEN_BLOCKS[design],
            measure_steps=cadence.steps(stage.budget("probe").steps),
            measure_initial=cadence.measure_initial,
            save_final_to=layout.out_dir / f"{name}_final_probe.pt",
            score_test=False,
        )
        _write(
            record,
            {
                "seed": seed,
                "backbone": backbone.relative_to(paths.repo_root).as_posix(),
                "window_rule": runner.probe.window_rule,
                "status_rows": runner.probe.status_rows,
                "selected": list(probe.probe_selected),
                "final": list(probe.probe_history[-1]),
                "history": probe.probe_history,
                "prior_offset": probe.prior_offset,
                "natural_rate": probe.natural_rate,
                "positives_seen": probe.probe_positives_seen,
                "seconds": probe.probe_seconds,
                "wall_seconds": time.perf_counter() - started,
            },
        )


def _write(path: Path, payload: dict[str, Any]) -> None:
    """Write a record atomically: a partial file never stands for a finished stage."""
    partial = path.with_suffix(".json.partial")
    partial.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    partial.replace(path)
