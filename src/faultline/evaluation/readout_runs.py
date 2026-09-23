"""F7'-2's GPU half (ADR-0026 §3): twelve read-out probes on saved backbones, then twelve scorings.

Nothing is pretrained. Every backbone this runner reads already exists on disk and is read
frozen: the joint backbones F6-2 wrote, ``tel_only``'s F3 backbones (control (iii)'s), and the
random-init S2 backbones ADR-0023 built with no optimiser step.

The four runs of ADR-0026 §3, in that order, three seeds each:

- **R-joint-b** -- ``mean_all`` on the joint backbones.
- **R-joint-d** -- ``last_plus_text`` on the joint backbones. This is H1''s arm side.
- **R-ctrl-d** -- ``last_plus_text`` on ``tel_only``'s backbones, on the same windows.
- **R-rand-d** -- ``last_plus_text`` on the random-init backbones: the gate on the instrument.

**Two phases, in this order: all twelve probes, then all twelve scorings.** A probe is F6-2's
probe with one thing changed, the read-out: the G3 cadence, the §a optimiser and rate, balanced
sampling, the tail-anchored R0 windows of ADR-0025 §2, and no test window read. A scoring is
F6-3's scoring of the **final-step** probe on the 137,025-window stride-12 pooled test split,
under :mod:`faultline.evaluation.h1_scoring`'s guards, re-used here rather than re-implemented:
the scored rows must be F3's windows row for row, and the probe's re-scored selection AUPRC must
be the one its own training record holds.

**Selected against final.** Every probe saves both states: ``..._probe.pt`` at the selected step
and ``..._final_probe.pt`` at the last. The fixed-final rule stays in force and the twelve
scorings read the final state; the selected state is saved so that F7'-3 reports the
selected-against-final row, and any later re-scoring of it, without training a probe again.

**Resume is per artefact**, as F6-2 and F6-3 resume. A probe whose record exists is skipped; a
scoring whose scores exist is re-checked against F3's windows and skipped. Scores and their
timing sidecar are written so that a scores file on disk is always whole and always timed.
``RUNNING.lock`` holds the running process's id and is removed when the process ends.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import torch

from faultline.config import config_hash, load_config
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
from faultline.evaluation.variance_probe import ProbeInputs, open_probe_inputs, probe_and_score
from faultline.logging_utils import get_logger
from faultline.model.checkpoints import read_checkpoint
from faultline.model.risk import RiskModel, RiskSpec
from faultline.model.transformer import ModelSpec
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.seed import seed_everything
from faultline.training.config import PositiveAwareRiskStage
from faultline.training.mixture import STREAM_DIRS, JointMixtureConfig

logger = get_logger(__name__)

#: ADR-0023's random-init control saved the whole risk model of each init seed, backbone
#: included, under this stem. F7' reads the backbone out of it rather than re-drawing it.
RANDOM_PROBE_STEM = "{rung}_random_seed{seed}_probe.pt"

#: Where the backbone of an init seed is written for this record, whatever it was read from.
RANDOM_BACKBONE_STEM = "{rung}_random_init_seed{seed}.pt"


# =====================================================================================
# the plan
# =====================================================================================


@dataclass(frozen=True)
class ReadoutProbe:
    """One of ADR-0026 §3's twelve probes, and the scoring that reads it.

    Attributes:
        run: The registered run name, ``R-joint-b`` to ``R-rand-d``.
        readout: The read-out probed, by registered name.
        family: The backbone family: ``joint``, ``tel_only`` or ``random_init``.
        seed: The pretraining seed, or the initialisation seed for ``random_init``.
        name: The file stem of every artefact this probe writes.
    """

    run: str
    readout: str
    family: str
    seed: int
    name: str


def probe_plan(config: ReadoutConfig, rung: str) -> list[ReadoutProbe]:
    """Every F7' probe, in ADR-0026 §3's order: run-major, seed-minor.

    Args:
        config: The loaded read-out configuration.
        rung: The model rung, the first part of every file name.

    Returns:
        The twelve probes, in the order they run and the order they are scored.
    """
    return [
        ReadoutProbe(
            run=run.name,
            readout=run.readout,
            family=run.backbone,
            seed=seed,
            name=f"{rung}_{run.name}_seed{seed}",
        )
        for run in config.runs
        for seed in run.seeds
    ]


@dataclass
class ReadoutLayout:
    """Every file F7' reads or writes, named once.

    Attributes:
        config: The read-out configuration.
        h1: F6-3's layout, which already resolves the joint and ``tel_only`` backbones and F3's
            ``tel_only`` scores, so this record cannot name a different file for either.
        out_dir: Probes, records, scores and sidecars.
        log_dir: Per-step probe training logs, tracked beside the reports.
        random_dir: ADR-0023's random-init output directory.
        rung: The model rung.
        plan: The twelve probes, in order.
    """

    config: ReadoutConfig
    h1: ScoringLayout
    out_dir: Path
    log_dir: Path
    random_dir: Path
    rung: str
    plan: list[ReadoutProbe]

    def probe(self, item: ReadoutProbe, role: str = FIXED_FINAL) -> Path:
        """A probe's saved state: the final step under the rule in force, or the selected one."""
        infix = "_final" if role == FIXED_FINAL else ""
        return self.out_dir / f"{item.name}{infix}_probe.pt"

    def probe_record(self, item: ReadoutProbe) -> Path:
        """A probe's record: its presence marks the probe finished."""
        return self.out_dir / f"{item.name}_probe.json"

    def scores(self, item: ReadoutProbe) -> Path:
        """A probe's test scores on the R0 stride-12 split."""
        return self.out_dir / f"{item.name}_final_R0_stride{self.h1.gate.stride}_scores.npz"

    def backbone(self, item: ReadoutProbe) -> Path:
        """The frozen backbone a probe reads.

        Args:
            item: The probe.

        Returns:
            The checkpoint it loads.

        Raises:
            ValueError: If the backbone family is not one of ADR-0026 §3's three.
        """
        if item.family == "joint":
            return self.h1.arms.backbone(item.seed)
        if item.family == "tel_only":
            return self.h1.arms.tel_only[item.seed]
        if item.family == "random_init":
            return self.random_backbone(item.seed)
        raise ValueError(f"unknown backbone family {item.family!r}")

    def random_backbone(self, seed: int) -> Path:
        """Where this record holds the random-init backbone of an initialisation seed."""
        return self.out_dir / RANDOM_BACKBONE_STEM.format(rung=self.rung, seed=seed)

    def random_source(self, seed: int) -> Path:
        """ADR-0023's saved probe, which holds that seed's random-init backbone."""
        return self.random_dir / RANDOM_PROBE_STEM.format(rung=self.rung, seed=seed)

    @property
    def random_record(self) -> Path:
        """Which random-init backbones ``R-rand-d`` used, and where each came from."""
        return self.out_dir / "random_init.json"

    @property
    def lock(self) -> Path:
        """The running process's lock."""
        return self.out_dir / "RUNNING.lock"

    @property
    def status(self) -> Path:
        """The status file this runner returns."""
        return self.out_dir / "readout_status.json"


def readout_layout(paths: ProjectPaths, config_path: Path) -> ReadoutLayout:
    """Resolve every path F7' touches from its configurations.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/eval/readout_v0.yaml``.

    Returns:
        The layout.
    """
    config = load_config(config_path, ReadoutConfig)
    h1 = scoring_layout(paths, paths.repo_root / config.h1_gate_config)
    control = load_config(paths.repo_root / config.random_init_config, ProbeControlConfig)
    rung = h1.arms.runner.rung
    return ReadoutLayout(
        config=config,
        h1=h1,
        out_dir=paths.checkpoints_dir / f"readout_v{config.version}_{config_hash(config)}",
        log_dir=paths.data_reports_dir / f"readout_v{config.version}_steps",
        random_dir=paths.checkpoints_dir
        / f"probe_control_v{control.version}_{config_hash(control)}",
        rung=rung,
        plan=probe_plan(config, rung),
    )


# =====================================================================================
# the random-init backbones (ADR-0026 §3)
# =====================================================================================


def random_init_state(spec: ModelSpec, seed: int) -> dict[str, Any]:
    """The S2 backbone as pretraining at an initialisation seed constructs it, with no step.

    This is ADR-0023's construction: ``probe_and_score`` with no checkpoint seeds the run and
    builds the risk model, and the backbone is built before the head, so the backbone's weights
    are the ones pretraining at that seed starts from, whatever head is asked for afterwards.

    Args:
        spec: The rung, at the joint vocabulary and the mixture context.
        seed: The initialisation seed.

    Returns:
        The backbone's parameters.
    """
    seed_everything(seed)
    torch.manual_seed(seed)
    model = RiskModel(spec, RiskSpec(), frozen=True)
    return {key: value.clone() for key, value in model.backbone.state_dict().items()}


class RandomInitHost(Protocol):
    """What :func:`materialise_random_init` needs of a layout: where the backbones live.

    Both F7''s and F8's layouts satisfy it, so the two records construct their random-init
    backbones by one code path and cannot drift apart in how the gate's reference is built.
    """

    def random_source(self, seed: int) -> Path:
        """ADR-0023's saved probe, which holds that seed's random-init backbone."""

    def random_backbone(self, seed: int) -> Path:
        """Where this record holds the random-init backbone of an initialisation seed."""

    @property
    def random_record(self) -> Path:
        """Which random-init backbones were used, and where each came from."""


def materialise_random_init(layout: RandomInitHost, spec: ModelSpec, seeds: list[int]) -> list[str]:
    """Write each random-init backbone into this record, and say where each came from.

    ADR-0023's control saved the whole risk model of each initialisation seed, backbone
    included. Where that file is on disk the backbone is **read out of it**, so the gate on the
    instrument is read against the backbones ADR-0023 actually probed rather than against a
    reconstruction of them, and its rung is checked to be this record's. Where it is not, the
    backbone is constructed fresh at the same seed with the joint spec, which is the same
    construction, and the record says which of the two it was.

    Args:
        layout: The resolved layout.
        spec: The rung the joint backbones carry.
        seeds: The initialisation seeds.

    Returns:
        One provenance line per seed, in seed order.

    Raises:
        ValueError: If a saved random-init probe carries another rung than this record's.
    """
    rows: list[dict[str, Any]] = []
    for seed in seeds:
        source, target = layout.random_source(seed), layout.random_backbone(seed)
        if source.is_file():
            payload = read_checkpoint(source)
            saved = ModelSpec(**payload["spec"])
            if saved != spec:
                raise ValueError(f"{source}: the saved random-init backbone is {saved}, not {spec}")
            prefix = "backbone."
            state = {
                key[len(prefix) :]: value
                for key, value in payload["state"].items()
                if key.startswith(prefix)
            }
            origin = f"ADR-0023 saved backbone, read from {source.name}"
        else:
            state = random_init_state(spec, seed)
            origin = "constructed fresh at this init seed with the joint spec"
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            torch.save(
                {"spec": spec.__dict__, "kind": "random_init", "seed": seed, "state": state},
                target,
            )
        rows.append(
            {
                "seed": seed,
                "origin": origin,
                "source": source.as_posix() if source.is_file() else None,
                "backbone": target.as_posix(),
            }
        )
    write_json(
        layout.random_record,
        {
            "spec": spec.__dict__,
            "vocab_size": spec.vocab_size,
            "context": spec.context,
            "rows": rows,
            "written_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        },
    )
    return [f"seed {row['seed']}: {row['origin']}" for row in rows]


# =====================================================================================
# pre-flight
# =====================================================================================


def preflight(paths: ProjectPaths, layout: ReadoutLayout) -> tuple[list[str], list[str]]:
    """What must exist before F7' starts, and where each probe and each scoring stands.

    Args:
        paths: Resolved project paths.
        layout: The resolved layout.

    Returns:
        The problems (empty when F7' may start) and one status line per item.
    """
    root = paths.repo_root
    config, arms = layout.config, layout.h1.arms
    problems: list[str] = []
    if (config.stride, config.label) != (layout.h1.gate.stride, layout.h1.gate.label):
        problems.append(
            f"readout stride/label {(config.stride, config.label)} are not the gate's "
            f"{(layout.h1.gate.stride, layout.h1.gate.label)}"
        )
    if config.ladder_config != arms.runner.ladder_config:
        problems.append(
            f"readout ladder {config.ladder_config} is not F6-2's {arms.runner.ladder_config}"
        )
    required: list[Path] = []
    for item in layout.plan:
        if item.family == "random_init":
            saved = layout.random_source(item.seed).is_file()
            if not (saved or layout.random_backbone(item.seed).is_file()):
                logger.info(
                    "random-init seed %d has no saved backbone; it is constructed fresh", item.seed
                )
        else:
            required.append(layout.backbone(item))
        required.append(layout.h1.tel_only_scores(item.seed))
    mixture = load_config(root / arms.runner.mixture_config, JointMixtureConfig)
    arm = next(a for a in mixture.arms if a.name == arms.runner.arm)
    status_dir = arms.joint_root / f"{STREAM_DIRS['tel+status']}_{arm.status_convention}"
    for source in mixture.training_sources:
        required += [status_dir / f"{source}__{split}.bin" for split in ("train", "val", "test")]
        required.append(status_dir / f"{source}__train.runs.parquet")
    missing = sorted({p for p in required if not p.exists()})
    problems += [f"missing: {relative(p, root)}" for p in missing]
    if layout.lock.exists():
        problems.append(
            f"{relative(layout.lock, root)} exists (pid "
            f"{layout.lock.read_text(encoding='utf-8').strip()}): a run may be active; check the "
            "process list, and delete the lock only if that process is gone"
        )
    if not torch.cuda.is_available():
        problems.append("CUDA is not available: F7'-2 is a GPU run")
    lines = [
        f"[{i:2d}/{len(layout.plan)}] probe {item.run} seed {item.seed} "
        f"({item.readout} on {item.family}): "
        f"{'done' if layout.probe_record(item).exists() else 'to run'}"
        for i, item in enumerate(layout.plan, 1)
    ]
    lines += [
        f"[{i:2d}/{len(layout.plan)}] score {item.name}: "
        f"{'done' if layout.scores(item).exists() else 'to run'}"
        for i, item in enumerate(layout.plan, 1)
    ]
    return problems, lines


def relative(path: Path, root: Path) -> str:
    """A path as the records and the pre-flight print it: repository-relative where it can be."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:  # pragma: no cover - a path outside the repository
        return path.as_posix()


# =====================================================================================
# the run
# =====================================================================================


def run_readout(paths: ProjectPaths, config_path: Path, device_name: str | None = None) -> Path:
    """Train every F7' probe not yet on disk, then score every one not yet scored.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/eval/readout_v0.yaml``.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The status file, ``readout_status.json`` in the output directory.

    Raises:
        RuntimeError: If a pre-flight problem stands.
    """
    layout = readout_layout(paths, config_path)
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


def _run(paths: ProjectPaths, layout: ReadoutLayout, device_name: str | None) -> Path:
    runner = layout.h1.arms.runner
    gate = load_config(paths.repo_root / runner.gate_config, GateCheckConfig)
    cadence = load_config(paths.repo_root / layout.config.probe.cadence_config, ProbeCadenceConfig)
    sha, dirty = git_sha(paths.repo_root), tree_dirty(paths.repo_root)
    logger.info("readout: git %s%s", sha, " (dirty)" if dirty else "")
    inputs = open_probe_inputs(
        paths,
        runner.mixture_config,
        layout.config.ladder_config,
        runner.arm,
        runner.rung,
        runner.optimiser.selection_windows,
        gate.held_out_source,
        device_name,
        window_rule=layout.config.probe.window_rule,
        status_rows=layout.config.probe.status_rows,
    )
    seeds = sorted({item.seed for item in layout.plan if item.family == "random_init"})
    for line in materialise_random_init(layout, inputs.spec, seeds) if seeds else []:
        logger.info("readout: random-init %s", line)
    probed = _probes(paths, layout, inputs, cadence, gate.held_out_source, sha, dirty)
    scored = _scorings(paths, layout, inputs, sha, dirty)
    probes_done = [item.name for item in layout.plan if layout.probe_record(item).exists()]
    done = [item.name for item in layout.plan if layout.scores(item).exists()]
    write_json(
        layout.status,
        {
            "config_hash": config_hash(layout.config),
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
        "readout: DONE %d of %d probes, %d of %d scorings; all done: %s",
        len(probes_done),
        len(layout.plan),
        len(done),
        len(layout.plan),
        len(done) == len(layout.plan),
    )
    return layout.status


def _probes(
    paths: ProjectPaths,
    layout: ReadoutLayout,
    inputs: ProbeInputs,
    cadence: ProbeCadenceConfig,
    held_out_source: str,
    sha: str,
    dirty: bool,
) -> list[str]:
    """Phase one: the twelve probes, in §3 order, each skipped if its record exists."""
    stage = inputs.ladder.risk
    assert isinstance(stage, PositiveAwareRiskStage)
    computed: list[str] = []
    total = len(layout.plan)
    for number, item in enumerate(layout.plan, 1):
        if layout.probe_record(item).exists():
            logger.info("readout probe [%d/%d] %s: on disk, skipped", number, total, item.name)
            continue
        spec = risk_spec(
            layout.config,
            item.readout,
            inputs.ladder_model.head_hidden,
            inputs.ladder_model.head_dropout,
            stage.label,
        )
        width = spec.input_width(inputs.spec.d_model)
        backbone = layout.backbone(item)
        logger.info(
            "=== readout probe [%d/%d] %s: %s on %s seed %d, head input %d ===",
            number,
            total,
            item.name,
            item.readout,
            item.family,
            item.seed,
            width,
        )
        started = time.perf_counter()
        probe = probe_and_score(
            item.seed,
            backbone,
            inputs,
            held_out_source,
            layout.log_dir / f"{item.name}_probe.steps.csv",
            f"readout/{item.name}/probe",
            save_to=layout.probe(item, role="selected"),
            pooling=READOUT_POOLING[item.readout],
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
                "run": item.run,
                "readout": item.readout,
                "family": item.family,
                "seed": item.seed,
                "head_input_width": width,
                "backbone": relative(backbone, paths.repo_root),
                "backbone_origin": _origin(layout, item),
                "window_rule": layout.config.probe.window_rule,
                "status_rows": layout.config.probe.status_rows,
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
            "readout probe [%d/%d] %s done in %.1f s; selected %s, final %s",
            number,
            total,
            item.name,
            probe.probe_seconds,
            probe.probe_selected,
            probe.probe_history[-1],
        )
    return computed


def _origin(layout: ReadoutLayout, item: ReadoutProbe) -> str:
    """Where a probe's backbone came from, for its record."""
    if item.family != "random_init":
        return item.family
    record = json.loads(layout.random_record.read_text(encoding="utf-8"))
    row = next(r for r in record["rows"] if int(r["seed"]) == item.seed)
    return str(row["origin"])


def _scorings(
    paths: ProjectPaths, layout: ReadoutLayout, inputs: ProbeInputs, sha: str, dirty: bool
) -> list[str]:
    """Phase two: the twelve scorings of the final-step probes, in §3 order.

    Args:
        paths: Resolved project paths.
        layout: The resolved layout.
        inputs: The opened shards, rung and windows.
        sha: The commit the run is on.
        dirty: Whether the working tree differs from it.

    Returns:
        The scorings computed in this invocation.

    Raises:
        ValueError: If a scoring does not cover F3's windows, or a probe's re-scored selection
            AUPRC is not the one its training record holds.
    """
    gate = layout.h1.gate
    evaluation = inputs.ladder.evaluation
    framed: list[SplitEval] = []

    def split() -> SplitEval:
        """The pooled stride-12 test split, framed as ADR-0025 §2's R0 windows."""
        if not framed:
            m1 = build_split(
                inputs.telemetry,
                "test",
                None,
                gate.stride,
                evaluation.seed,
                evaluation.batch_windows,
                gate.label,
                sources=inputs.mixture.training_sources,
            )
            framed.append(inputs.frame(m1))
        return framed[0]

    checks_file = layout.out_dir / "selection_check.json"
    checks: dict[str, Any] = (
        json.loads(checks_file.read_text(encoding="utf-8")) if checks_file.exists() else {}
    )
    computed: list[str] = []
    total = len(layout.plan)
    for number, item in enumerate(layout.plan, 1):
        path = layout.scores(item)
        reference = ScoredWindows.load(layout.h1.tel_only_scores(item.seed))
        if path.exists():
            if not ScoredWindows.load(path).same_windows(reference):
                raise ValueError(f"{path.name} on disk does not cover F3's windows")
            logger.info("readout score [%d/%d] %s: on disk, skipped", number, total, item.name)
            continue
        probe = layout.probe(item)
        record = json.loads(layout.probe_record(item).read_text(encoding="utf-8"))
        recorded = float(record["final"][1])
        logger.info("=== readout score [%d/%d] %s ===", number, total, item.name)
        if probe.name not in checks:
            tick = time.perf_counter()
            measured = selection_auprc(probe, item.readout, inputs)
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
        scored = score_saved_probe(probe, item.readout, inputs, split())
        seconds = time.perf_counter() - tick
        sidecar = {
            "seconds": seconds,
            "started_utc": started_utc,
            "finished_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "run": item.run,
            "readout": item.readout,
            "family": item.family,
            "seed": item.seed,
            "role": FIXED_FINAL,
            "windows": "R0",
            "head_input_width": int(record["head_input_width"]),
            "probe": relative(probe, paths.repo_root),
            "prior_offset": float(record["prior_offset"]),
            "device": str(inputs.device),
            "git_sha": sha,
            "tree_dirty": dirty,
        }
        written = save_atomically(path, scored, split(), float(record["prior_offset"]), sidecar)
        if not written.same_windows(reference):
            raise ValueError(f"{path.name} does not cover F3's windows")
        computed.append(item.name)
        logger.info("readout score [%d/%d] %s done in %.1f s", number, total, item.name, seconds)
    return computed
