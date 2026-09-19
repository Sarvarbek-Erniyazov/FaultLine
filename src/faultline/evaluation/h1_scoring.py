"""F6-3's GPU half (ADR-0025 §3, §5, §6): score the saved joint and control (iii) probes.

Nothing is trained.

Every scoring reads the pooled Kelmarsh + Penmanshiel stride-12 test split that F3 scored
``tel_only`` on (137,025 windows, 5,312 positives), under one framing, and in this order:

- **S1.** Each joint seed's final-step probe, tail-anchored R0 windows (ADR-0025 §2).
- **S2.** Control (iii): each ``tel_only`` backbone's final-step probe, R0 windows.
- **S3.** Each joint seed's final-step probe, R2 windows (every provider ``Stop`` row removed).
- **S4.** H2, text withheld: each joint seed's backbone and final probe on M1's 1,872-token
  windows. **A different window from S5's**, so the two are not comparable.
- **S5.** H2, channel loss: each joint seed × each F6-0a CARE-farm mask
  (``configs/eval/care_attribution_v0.yaml``, ``masking.patterns``), imposed as ``<nan>`` on the
  telemetry slots of the R0 windows. Text stays in the window.
- **S6.** The selected-step probes of joint seeds 1-3, then of control (iii) seeds 1-3, on R0
  windows, for the selected-against-final comparison. It is reported only.
- **V.** Each joint backbone's next-token loss on ``tel+status`` validation windows, beside its
  recomputed ``tel`` validation loss.

``tel_only``'s final-step scores are F3's, read from disk and never re-scored. Every scoring
here must cover exactly F3's windows (sources, order, labels, end steps), so that each Δ pairs
row for row.

**Resume is per artefact.** A scoring writes ``<name>_stride12_scores.npz`` and a timing sidecar
``<name>_stride12_scores.timing.json``. It writes both under temporary names and renames the
scores last, so a scores file on disk is always whole and always has its sidecar. A scoring whose
scores exist is skipped. ``RUNNING.lock`` holds the running process's id and is removed when the
process ends. The bootstrap and the verdict are not computed here: they run on the CPU, from the
files this module leaves.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
import torch

from faultline.config import config_hash, load_config
from faultline.evaluation.axis_gate import ProbeCheckpoints, read_probes
from faultline.evaluation.care_attribution import CareAttributionConfig, mask_positions
from faultline.evaluation.checkpoint_selection import FIXED_FINAL, SELECTED
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.h1_arms import ArmsLayout, arms_layout
from faultline.evaluation.h1_gate import H1GateConfig
from faultline.evaluation.ladder import SplitEval, build_split
from faultline.evaluation.metrics import average_precision
from faultline.evaluation.paired_control import save_split_scores, score_saved_probe
from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.seed_replication import SeedReplicationConfig
from faultline.evaluation.variance_probe import (
    ProbeInputs,
    TelWindows,
    frame_split,
    open_probe_inputs,
    tel_lm_loss,
    tel_status_streams,
)
from faultline.logging_utils import get_logger
from faultline.model.checkpoints import read_checkpoint
from faultline.model.transformer import TelemetryDecoder
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.joint_windows import (
    PAD_ID,
    SEP_ID,
    TXT_CLOSE_ID,
    TXT_OPEN_ID,
    JointWindowSampler,
    JointWindowSet,
    run_step_starts,
    step_offsets,
)
from faultline.training.mixture import STREAM_DIRS, JointMixtureConfig
from faultline.training.windows import Batch

logger = get_logger(__name__)

#: ADR-0025 §6 names the F6-0a masks by this file; ``h1_gate_v0.yaml`` does not restate them.
MASK_CONFIG = "configs/eval/care_attribution_v0.yaml"

#: A probe's re-scored selection-split AUPRC must be within this of the value F6-2 recorded
#: at the same step, or the scoring path is not the one the probe was trained and read under.
SELECTION_TOLERANCE = 0.002

# =====================================================================================
# the plan
# =====================================================================================


@dataclass(frozen=True)
class Scoring:
    """One scoring: a saved probe, a set of windows, and the file its scores go to.

    Attributes:
        stage: ``S1`` to ``S6``.
        name: The file stem before ``_stride<k>_scores``.
        seed: The pretraining seed of the backbone.
        control: Whether the backbone is ``tel_only``'s (control (iii)) rather than the joint one.
        role: ``final_step`` or ``selected``.
        windows: ``R0``, ``R2`` or ``m1`` (text withheld).
        farm: The CARE farm whose mask is imposed, or ``None``.
    """

    stage: str
    name: str
    seed: int
    control: bool
    role: str
    windows: str
    farm: str | None = None


def scoring_plan(seeds: list[int], farms: list[str], rung: str = "S2") -> list[Scoring]:
    """Every F6-3 scoring, in the order it runs.

    Args:
        seeds: The pretraining seeds.
        farms: The CARE farms whose masks are imposed, in configuration order.
        rung: The model rung, the first part of every file name.

    Returns:
        S1, S2, S3, S4, S5 (seed-major, farm-minor) and S6 (joint seeds, then control (iii)).
    """
    joint = f"{rung}_joint_seed{{}}"
    iii = f"{rung}_tel_only_seed{{}}_on_joint"
    plan = [
        Scoring("S1", f"{joint.format(s)}_final_R0", s, False, FIXED_FINAL, "R0") for s in seeds
    ]
    plan += [Scoring("S2", f"{iii.format(s)}_final_R0", s, True, FIXED_FINAL, "R0") for s in seeds]
    plan += [
        Scoring("S3", f"{joint.format(s)}_final_R2", s, False, FIXED_FINAL, "R2") for s in seeds
    ]
    plan += [
        Scoring("S4", f"{joint.format(s)}_final_text_withheld_m1", s, False, FIXED_FINAL, "m1")
        for s in seeds
    ]
    plan += [
        Scoring("S5", f"{joint.format(s)}_final_R0_masked_{f}", s, False, FIXED_FINAL, "R0", f)
        for s in seeds
        for f in farms
    ]
    plan += [
        Scoring("S6", f"{joint.format(s)}_selected_R0", s, False, SELECTED, "R0") for s in seeds
    ]
    plan += [Scoring("S6", f"{iii.format(s)}_selected_R0", s, True, SELECTED, "R0") for s in seeds]
    return plan


@dataclass
class ScoringLayout:
    """Every file F6-3's scoring reads or writes.

    Attributes:
        gate: The H1 gate configuration.
        arms: F6-2's layout: its probes and records.
        out_dir: ``checkpoints/h1_gate_v<version>_<hash>``: scores, sidecars, checks.
        patterns: Per CARE farm, the channels its mask imposes.
        reference: Per seed, ``tel_only``'s F3 final-step probe checkpoints.
        f3_dir: F3's output directory, holding ``tel_only``'s final-step scores.
        sources: The training sites, pooled in every scoring.
        plan: The scorings, in order.
    """

    gate: H1GateConfig
    arms: ArmsLayout
    out_dir: Path
    patterns: dict[str, list[str]]
    reference: dict[int, ProbeCheckpoints]
    f3_dir: Path
    sources: list[str]
    plan: list[Scoring]

    def scores(self, scoring: Scoring) -> Path:
        """A scoring's scores file."""
        return self.out_dir / f"{scoring.name}_stride{self.gate.stride}_scores.npz"

    def probe(self, scoring: Scoring) -> Path:
        """The saved probe state a scoring reads."""
        stem = self.arms.probe_name(scoring.seed, scoring.control)
        infix = "_final" if scoring.role == FIXED_FINAL else ""
        return self.arms.out_dir / f"{stem}{infix}_probe.pt"

    def probe_record(self, scoring: Scoring) -> dict[str, Any]:
        """F6-2's record of the probe a scoring reads."""
        path = self.arms.probe_record(scoring.seed, scoring.control)
        loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return loaded

    def tel_only_scores(self, seed: int) -> Path:
        """F3's final-step ``tel_only`` scores of a seed.

        F3 wrote no ``_final`` infix for a probe that selected its last step.
        """
        probe = self.reference[seed]
        infix = "" if probe.identical else "_final"
        return self.f3_dir / f"{probe.name}{infix}_stride{self.gate.stride}_scores.npz"

    @property
    def validation_file(self) -> Path:
        """The validation-loss row."""
        return self.out_dir / "validation_loss.json"

    @property
    def lock(self) -> Path:
        """The running process's lock."""
        return self.out_dir / "RUNNING.lock"


def scoring_layout(paths: ProjectPaths, gate_path: Path) -> ScoringLayout:
    """Resolve every path F6-3's scoring touches.

    Args:
        paths: Resolved project paths.
        gate_path: ``configs/eval/h1_gate_v0.yaml``.

    Returns:
        The layout.
    """
    gate = load_config(gate_path, H1GateConfig)
    arms = arms_layout(paths, paths.repo_root / gate.runner_config, gate_path)
    masks = load_config(paths.repo_root / MASK_CONFIG, CareAttributionConfig)
    f3 = load_config(paths.repo_root / gate.reference_config, SeedReplicationConfig)
    mixture = load_config(paths.repo_root / arms.runner.mixture_config, JointMixtureConfig)
    seeds = gate.comparison.seeds
    return ScoringLayout(
        gate=gate,
        arms=arms,
        out_dir=paths.checkpoints_dir / f"h1_gate_v{gate.version}_{config_hash(gate)}",
        patterns=dict(masks.masking.patterns),
        reference={seed: read_probes(paths, f3, seed) for seed in seeds},
        f3_dir=paths.checkpoints_dir / f"seed_replication_v{f3.version}_{config_hash(f3)}",
        sources=list(mixture.training_sources),
        plan=scoring_plan(seeds, list(masks.masking.patterns), arms.runner.rung),
    )


def preflight(paths: ProjectPaths, layout: ScoringLayout) -> tuple[list[str], list[str]]:
    """What must exist before F6-3's scoring starts, and where each scoring stands.

    Args:
        paths: Resolved project paths.
        layout: The resolved layout.

    Returns:
        The problems (empty when scoring may start) and one status line per scoring.
    """
    root = paths.repo_root
    problems: list[str] = []
    runner = layout.arms.runner
    status_path = layout.arms.out_dir / "h1_arms_status.json"
    if not status_path.is_file():
        problems.append(f"missing: {status_path.relative_to(root).as_posix()}")
    else:
        done = json.loads(status_path.read_text(encoding="utf-8"))["seeds_done"]
        if sorted(done) != sorted(runner.seeds):
            problems.append(f"F6-2 seeds done {done}, configured {runner.seeds}")
    required: list[Path] = []
    for scoring in layout.plan:
        required += [layout.probe(scoring), layout.arms.probe_record(scoring.seed, scoring.control)]
    for seed in layout.gate.comparison.seeds:
        required += [layout.arms.backbone(seed), layout.tel_only_scores(seed)]
    status_dir = layout.arms.joint_root / f"{STREAM_DIRS['tel+status']}_normalized"
    for source in layout.sources:
        for split in ("val", "test"):
            required += [status_dir / f"{source}__{split}.bin"]
        required += [status_dir / f"{source}__val.runs.parquet"]
    missing = sorted({p for p in required if not p.exists()})
    problems += [f"missing: {p.relative_to(root).as_posix()}" for p in missing]
    if layout.lock.exists():
        problems.append(
            f"{layout.lock.relative_to(root).as_posix()} exists (pid "
            f"{layout.lock.read_text(encoding='utf-8').strip()}): a run may be active; check the "
            "process list, and delete the lock only if that process is gone"
        )
    if not torch.cuda.is_available():
        problems.append("CUDA is not available: F6-3's scoring is a GPU run")
    lines = [
        f"[{i:2d}/{len(layout.plan)}] {s.stage} {s.name}: "
        f"{'done' if layout.scores(s).exists() else 'to run'}"
        for i, s in enumerate(layout.plan, 1)
    ]
    lines.append(
        f"[ V ] validation loss: {'done' if layout.validation_file.exists() else 'to run'}"
    )
    return problems, lines


# =====================================================================================
# channel masks on tail-anchored windows
# =====================================================================================


def window_mask_positions(
    offsets: np.ndarray,
    first: int,
    length: int,
    channel_offsets: np.ndarray,
    tokens_per_step: int,
) -> np.ndarray:
    """Every position of one tail-anchored window that holds a masked channel's bin token.

    A ``tel+status`` step is ``<sep>``, its channels in the tokenizer's order, then its messages,
    so channel ``c`` of a step sits at the step's ``<sep>`` offset plus ``c``'s position in the
    step layout. A step whose ``<sep>`` lies before the window's first token (only possible in a
    head-cut window) contributes the slots that reach into the window.

    Args:
        offsets: The stream's step offsets (``step_offsets``).
        first: The window's first token in the stream.
        length: The window's real tokens.
        channel_offsets: The masked channels' positions within a step (``<sep>`` is 0).
        tokens_per_step: Telemetry tokens a step contributes.

    Returns:
        The positions within the window, ascending.
    """
    lo = int(np.searchsorted(offsets, first - tokens_per_step + 1, side="left"))
    hi = int(np.searchsorted(offsets, first + length, side="left"))
    starts = offsets[lo:hi] - first
    positions = (starts[:, None] + channel_offsets[None, :]).ravel()
    chosen: np.ndarray = np.sort(positions[(positions >= 0) & (positions < length)])
    return chosen


class MaskedJointSampler(JointWindowSampler):
    """A tail-anchored sampler whose every window carries ``<nan>`` on the masked channels.

    It reads the same sets in the same order as the sampler it wraps, so its scores pair row for
    row with the unmasked R0 scoring. Every overwritten token is checked to be a telemetry value
    id (below ``value_ids``, and not ``<pad>``, ``<sep>``, ``<txt>`` or ``</txt>``). Text is never
    touched.

    Attributes:
        channel_offsets: The masked channels' positions within a step.
        nan_id: The id written there.
        value_ids: Ids below this are the M1 vocabulary; text ids start here.
        masked: Tokens overwritten so far.
    """

    def __init__(
        self, base: JointWindowSampler, channel_offsets: np.ndarray, nan_id: int, value_ids: int
    ) -> None:
        """Wrap a tail-anchored sampler.

        Args:
            base: The unmasked sampler.
            channel_offsets: The masked channels' positions within a step.
            nan_id: The ``<nan>`` id.
            value_ids: The M1 vocabulary size.
        """
        super().__init__(
            base.sets, base.batch_size, base.tokens_per_step, base.context_steps, base.labelled
        )
        self.channel_offsets = channel_offsets.astype(np.int64)
        self.nan_id = nan_id
        self.value_ids = value_ids
        self.masked = 0
        self._offsets = [step_offsets(np.asarray(s.tokens)) for s in self.sets]

    def _gather(self, rows: np.ndarray) -> Batch:
        tokens, labels, sets = super()._gather(rows)
        structural = torch.tensor([PAD_ID, SEP_ID, TXT_OPEN_ID, TXT_CLOSE_ID])
        for position, (which, row) in enumerate(rows):
            window = self.sets[int(which)]
            assert isinstance(window, JointWindowSet)
            chosen = torch.from_numpy(
                window_mask_positions(
                    self._offsets[int(which)],
                    int(window.first[row]),
                    int(window.length[row]),
                    self.channel_offsets,
                    self.tokens_per_step,
                )
            )
            original = tokens[position, chosen]
            if bool((original >= self.value_ids).any()) or bool(
                torch.isin(original, structural).any()
            ):
                raise ValueError(
                    f"{window.key} row {int(row)}: a masked position holds a non-telemetry id"
                )
            tokens[position, chosen] = self.nan_id
            self.masked += int(chosen.numel())
        return tokens, labels, sets


def masked_joint_split(
    split: SplitEval, channel_offsets: np.ndarray, nan_id: int, value_ids: int
) -> SplitEval:
    """The same tail-anchored split, read through a :class:`MaskedJointSampler`."""
    sampler = split.sampler
    assert isinstance(sampler, JointWindowSampler)
    return replace(split, sampler=MaskedJointSampler(sampler, channel_offsets, nan_id, value_ids))


# =====================================================================================
# the run
# =====================================================================================


def module_digest() -> str:
    """SHA-256 of this module's source: what the scores were computed with, if the tree is dirty."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def tree_dirty(repo_root: Path) -> bool:
    """Whether the working tree differs from HEAD in any tracked or untracked, unignored file."""
    out = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(out.stdout.strip())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically: a partial file never stands for a finished artefact."""
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    partial.replace(path)


def timing_path(scores: Path) -> Path:
    """A scores file's timing sidecar."""
    return scores.with_suffix(".timing.json")


def save_atomically(
    path: Path,
    scored: tuple[np.ndarray, np.ndarray],
    split: SplitEval,
    offset: float,
    sidecar: dict[str, Any],
) -> ScoredWindows:
    """Write the scores and their sidecar so that a scores file on disk is whole and timed.

    The scores go to a temporary name, the sidecar is written, and the scores are renamed last.
    A run killed at any point leaves either nothing under the scores' name or both files.

    Args:
        path: The scores file.
        scored: Every window's logit and label.
        split: The split scored.
        offset: The probe's prior offset.
        sidecar: The timing sidecar's content.

    Returns:
        The scores as written.
    """
    partial = path.with_name(path.stem + ".partial.npz")
    save_split_scores(partial, scored, split, offset)
    write_json(timing_path(path), sidecar)
    partial.replace(path)
    return ScoredWindows.load(path)


def selection_auprc(probe: Path, design: str, inputs: ProbeInputs) -> float:
    """A saved probe's AUPRC on the R0 selection split, re-scored now."""
    logits, labels = score_saved_probe(probe, design, inputs, inputs.splits["selection"])
    return average_precision(logits, labels.astype(np.float64))


def tel_status_val_windows(inputs: ProbeInputs, limit: int, seed: int) -> TelWindows:
    """``tel+status`` validation windows, drawn as pretraining's ``tel`` selection windows are.

    Each source's windows start at a step's ``<sep>`` every ``window_stride_steps`` steps and end
    inside its run, as the pretraining pool's do. At most ``limit`` per source are kept, drawn
    without replacement by ``default_rng(seed)``, as ``tel_windows`` draws them.

    Args:
        inputs: The opened inputs.
        limit: Windows per source.
        seed: Seed of the subsample.

    Returns:
        The windows.
    """
    directory = inputs.joint_root / f"{STREAM_DIRS['tel+status']}_normalized"
    context, stride = inputs.spec.context, inputs.mixture.window_stride_steps
    streams: dict[str, np.memmap] = {}
    keys: list[str] = []
    rows: list[np.ndarray] = []
    for source in inputs.mixture.training_sources:
        key = f"{source}__val"
        stream = np.memmap(directory / f"{key}.bin", dtype=np.uint16, mode="r")
        offsets = step_offsets(stream)
        runs = pq.read_table(directory / f"{key}.runs.parquet").to_pandas()
        starts = np.concatenate(
            [
                run_step_starts(offsets, int(first), int(tokens), stride, context)
                for first, tokens in zip(runs["first_token"], runs["tokens"], strict=True)
            ]
        )
        if starts.size > limit:
            starts = np.sort(np.random.default_rng(seed).choice(starts, limit, replace=False))
        streams[key] = stream
        keys.append(key)
        rows.append(np.stack([np.full(starts.size, len(keys) - 1), starts], axis=1))
    return TelWindows(
        streams=streams, keys=keys, index=np.concatenate(rows).astype(np.int64), context=context
    )


def run_h1_scoring(paths: ProjectPaths, gate_path: Path, device_name: str | None = None) -> Path:
    """Run every F6-3 scoring not yet on disk, then the validation-loss row.

    Args:
        paths: Resolved project paths.
        gate_path: ``configs/eval/h1_gate_v0.yaml``.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The status file, ``h1_scoring_status.json`` in the output directory.

    Raises:
        RuntimeError: If a pre-flight problem stands.
        ValueError: If a scoring does not cover F3's windows, a probe's re-scored selection
            AUPRC is not the one F6-2 recorded, or a mask touches a non-telemetry token.
    """
    layout = scoring_layout(paths, gate_path)
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


def _run(paths: ProjectPaths, layout: ScoringLayout, device_name: str | None) -> Path:
    gate, runner = layout.gate, layout.arms.runner
    gate_run = load_config(paths.repo_root / runner.gate_config, GateCheckConfig)
    design = runner.probe.design
    sha, dirty, digest = git_sha(paths.repo_root), tree_dirty(paths.repo_root), module_digest()
    logger.info(
        "h1-score: git %s%s, h1_scoring.py sha256 %s", sha, " (dirty)" if dirty else "", digest
    )
    opened: list[ProbeInputs] = []
    splits: dict[str, SplitEval] = {}

    def inputs() -> ProbeInputs:
        if not opened:
            opened.append(
                open_probe_inputs(
                    paths,
                    runner.mixture_config,
                    runner.ladder_config,
                    runner.arm,
                    runner.rung,
                    runner.optimiser.selection_windows,
                    gate_run.held_out_source,
                    device_name,
                    window_rule=runner.probe.window_rule,
                    status_rows=runner.probe.status_rows,
                )
            )
        return opened[0]

    def split(windows: str) -> SplitEval:
        """The pooled stride-12 test split, framed as ``windows`` names."""
        if "m1" not in splits:
            evaluation = inputs().ladder.evaluation
            splits["m1"] = build_split(
                inputs().telemetry,
                "test",
                None,
                gate.stride,
                evaluation.seed,
                evaluation.batch_windows,
                gate.label,
                sources=inputs().mixture.training_sources,
            )
        if windows not in splits:
            if windows == "R0":
                splits["R0"] = inputs().frame(splits["m1"])
            elif windows == "R2":
                streams = tel_status_streams(
                    paths,
                    inputs().joint_root,
                    inputs().telemetry,
                    "normalized",
                    inputs().spec.context,
                    "no_stop",
                    inputs().mixture.training_sources,
                )
                splits["R2"] = frame_split(splits["m1"], streams)
            else:
                raise ValueError(f"unknown window variant {windows!r}")
        return splits[windows]

    checks_file = layout.out_dir / "selection_check.json"
    checks: dict[str, Any] = (
        json.loads(checks_file.read_text(encoding="utf-8")) if checks_file.exists() else {}
    )
    computed: list[str] = []
    resumed: list[str] = []
    total = len(layout.plan)
    for number, scoring in enumerate(layout.plan, 1):
        path = layout.scores(scoring)
        reference = ScoredWindows.load(layout.tel_only_scores(scoring.seed))
        if path.exists():
            if not ScoredWindows.load(path).same_windows(reference):
                raise ValueError(f"{path.name} on disk does not cover F3's windows")
            resumed.append(scoring.name)
            logger.info(
                "h1-score [%d/%d] %s %s: on disk, skipped",
                number,
                total,
                scoring.stage,
                scoring.name,
            )
            continue
        probe = layout.probe(scoring)
        record = layout.probe_record(scoring)
        recorded = float(
            record["final"][1] if scoring.role == FIXED_FINAL else record["selected"][1]
        )
        logger.info("=== h1-score [%d/%d] %s %s ===", number, total, scoring.stage, scoring.name)
        if probe.name not in checks:
            tick = time.perf_counter()
            measured = selection_auprc(probe, design, inputs())
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
        view = split(scoring.windows)
        masked: MaskedJointSampler | None = None
        extra: dict[str, Any] = {}
        if scoring.farm is not None:
            telemetry = inputs().telemetry
            step = [str(name) for name in telemetry.manifest["step"]]
            nan_id = int(dict(telemetry.manifest["specials"])["<nan>"])
            channels = layout.patterns[scoring.farm]
            channel_offsets = mask_positions(step, channels, 1)
            view = masked_joint_split(view, channel_offsets, nan_id, telemetry.vocab_size)
            assert isinstance(view.sampler, MaskedJointSampler)
            masked = view.sampler
            retained = sum(
                int(
                    np.asarray(s.steps_retained)[
                        view.sampler.index[view.sampler.index[:, 0] == i, 1]
                    ].sum()
                )
                for i, s in enumerate(view.sampler.sets)
                if isinstance(s, JointWindowSet)
            )
            extra = {
                "farm": scoring.farm,
                "channels": channels,
                "channel_offsets": channel_offsets.tolist(),
                "nan_id": nan_id,
                "expected_masked_tokens": retained * len(channels),
            }
        started_utc = datetime.now(tz=UTC).isoformat(timespec="seconds")
        tick = time.perf_counter()
        scored = score_saved_probe(probe, design, inputs(), view)
        seconds = time.perf_counter() - tick
        if masked is not None:
            extra["masked_tokens"] = masked.masked
            if masked.masked != extra["expected_masked_tokens"]:
                raise ValueError(
                    f"{scoring.name}: {masked.masked:,} tokens masked, "
                    f"{extra['expected_masked_tokens']:,} channel slots in the retained steps"
                )
        sidecar = {
            "seconds": seconds,
            "started_utc": started_utc,
            "finished_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "stage": scoring.stage,
            "seed": scoring.seed,
            "arm": "tel_only_on_joint" if scoring.control else "joint",
            "role": scoring.role,
            "windows": scoring.windows,
            "probe": probe.relative_to(paths.repo_root).as_posix(),
            "prior_offset": float(record["prior_offset"]),
            "device": str(inputs().device),
            "git_sha": sha,
            "tree_dirty": dirty,
            "h1_scoring_sha256": digest,
            **extra,
        }
        written = save_atomically(path, scored, view, float(record["prior_offset"]), sidecar)
        if not written.same_windows(reference):
            raise ValueError(f"{path.name} does not cover F3's windows")
        computed.append(scoring.name)
        logger.info(
            "h1-score [%d/%d] %s %s done in %.1f s",
            number,
            total,
            scoring.stage,
            scoring.name,
            seconds,
        )

    if not layout.validation_file.exists():
        logger.info("=== h1-score [ V ] validation loss on tel+status and tel windows ===")
        tick = time.perf_counter()
        evaluation = inputs().ladder.evaluation
        status_windows = tel_status_val_windows(
            inputs(), runner.optimiser.selection_windows, evaluation.seed
        )
        rows: dict[str, Any] = {}
        for seed in runner.seeds:
            decoder = TelemetryDecoder(inputs().spec).to(inputs().device)
            state = read_checkpoint(layout.arms.backbone(seed))["state"]
            decoder.load_state_dict({k: v.to(inputs().device) for k, v in state.items()})
            decoder.eval()
            lm = json.loads(layout.arms.lm_record(seed).read_text(encoding="utf-8"))
            with torch.inference_mode():
                rows[str(seed)] = {
                    "tel_status_val": tel_lm_loss(
                        decoder, status_windows, inputs().device, runner.batch_windows
                    ),
                    "tel_val": tel_lm_loss(
                        decoder,
                        inputs().splits["lm_selection"],
                        inputs().device,
                        runner.batch_windows,
                    ),
                    "tel_val_recorded": float(lm["history"][-1][1]),
                }
            logger.info("joint seed %d validation loss: %s", seed, rows[str(seed)])
            del decoder
        write_json(
            layout.validation_file,
            {
                "rows": rows,
                "tel_status_windows": len(status_windows),
                "tel_windows": len(inputs().splits["lm_selection"]),
                "seconds": time.perf_counter() - tick,
                "git_sha": sha,
                "tree_dirty": dirty,
                "h1_scoring_sha256": digest,
            },
        )

    status = layout.out_dir / "h1_scoring_status.json"
    done = [s.name for s in layout.plan if layout.scores(s).exists()]
    write_json(
        status,
        {
            "gate_config_hash": config_hash(gate),
            "scorings_done": done,
            "scorings_total": total,
            "computed_this_invocation": computed,
            "resumed_this_invocation": resumed,
            "validation_loss_done": layout.validation_file.exists(),
            "written_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "git_sha": sha,
            "tree_dirty": dirty,
            "h1_scoring_sha256": digest,
        },
    )
    logger.info(
        "h1-score: DONE %d of %d scorings; all done: %s",
        len(done),
        total,
        len(done) == total and layout.validation_file.exists(),
    )
    return status
