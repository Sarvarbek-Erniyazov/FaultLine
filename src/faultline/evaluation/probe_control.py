"""The random-init probe control (ADR-0023): can the frozen probe see backbone quality?

H1 is read entirely through the frozen probe. Doubling pretraining lowered validation loss by
about 0.9 nats, and no site's probe AUPRC moved (ADR-0021 outcome). Either the loss does not
track a risk-relevant representation, or the probe cannot see the backbone at all. This control
separates the two. The S2 backbone is left at its initialisation for three seeds, with no
optimiser step, and the frozen probe is trained on each exactly as it was trained on the
full-budget ``tel_only`` backbone. Only the backbone's weights differ.

**The criterion, registered in** ``c9489a2`` **before this module existed.** On the pooled
Kelmarsh + Penmanshiel test windows, with ADR-0021's block bootstrap, the trained backbone's 95%
interval must lie entirely above the random-init interval: its lower bound strictly above the
upper bound of **every** random-init seed. Hill of Towie is reported and does not decide.

Under §a (the final position) the trained side is the registered gate run as scored, read from its
saved test scores. Under a redesigned probe (§b onward), both sides are probed through the design:
the gate run's saved backbone with its seed, and the untrained backbones with theirs.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import Field, model_validator

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.evaluation.bootstrap import AuprcInterval, bootstrap_auprc, window_blocks
from faultline.evaluation.gate_check import BootstrapConfig, GateCheckConfig, save_scores
from faultline.evaluation.metrics import average_precision
from faultline.evaluation.variance_probe import ProbeInputs, open_probe_inputs, probe_and_score
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

#: What the head reads under each registered design (ADR-0023: §a the final position, §b the mean).
POOLING: dict[str, Literal["last", "mean"]] = {"final_position": "last", "mean_pooled": "mean"}


class ProbeControlConfig(StrictModel):
    """Top level of ``configs/train/probe_control_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        gate_config: The full-budget gate run: its inputs, its interval and its trained backbone.
        design: The probe design under test (ADR-0023; the first design is the final position).
        init_seeds: Seeds of the untrained backbones, each also seeding its probe.
        pooled_sources: The test sources pooled into the split the criterion reads.
    """

    version: int = 0
    gate_config: str
    design: Literal["final_position", "mean_pooled"]
    init_seeds: list[int] = Field(min_length=1)
    pooled_sources: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _distinct(self) -> ProbeControlConfig:
        """Refuse repeated seeds or sources.

        Raises:
            ValueError: If a seed or a source is listed twice.
        """
        if len(set(self.init_seeds)) != len(self.init_seeds):
            raise ValueError(f"init seeds repeat: {self.init_seeds}")
        if len(set(self.pooled_sources)) != len(self.pooled_sources):
            raise ValueError(f"pooled sources repeat: {self.pooled_sources}")
        return self


# =====================================================================================
# scores on disk
# =====================================================================================


@dataclass(frozen=True)
class ScoredWindows:
    """One backbone's probe scores on the test windows, as ``save_scores`` wrote them.

    Attributes:
        logits: Per window, the probe's logit before the prior offset.
        labels: Per window, 1 if positive.
        which: Per window, its window-set index into ``sources``.
        ends: Per window, its end step in its shard.
        sources: The test split's sources, in set order.
        prior_offset: The constant reading logits at the natural rate.
    """

    logits: np.ndarray
    labels: np.ndarray
    which: np.ndarray
    ends: np.ndarray
    sources: list[str]
    prior_offset: float

    @classmethod
    def load(cls, path: Path) -> ScoredWindows:
        """Read a scores file."""
        with np.load(path) as data:
            return cls(
                logits=data["logits"],
                labels=data["labels"],
                which=data["which"],
                ends=data["ends"],
                sources=[str(s) for s in data["sources"]],
                prior_offset=float(data["prior_offset"]),
            )

    def same_windows(self, other: ScoredWindows) -> bool:
        """Whether two score files cover the same windows, in order, with the same labels."""
        return (
            self.sources == other.sources
            and np.array_equal(self.labels, other.labels)
            and np.array_equal(self.which, other.which)
            and np.array_equal(self.ends, other.ends)
        )

    def chosen(self, sources: list[str]) -> np.ndarray:
        """The mask of windows from the named sources."""
        return np.isin(self.which, [self.sources.index(s) for s in sources])

    def auprc(self, sources: list[str]) -> float:
        """AUPRC over the named sources' windows, pooled."""
        mask = self.chosen(sources)
        return average_precision(self.logits[mask], self.labels[mask].astype(np.float64))

    def interval(self, sources: list[str], bootstrap: BootstrapConfig) -> AuprcInterval:
        """ADR-0021's block bootstrap over the named sources' windows, pooled.

        Blocks are ``block_steps`` long within each source's shard, so windows of two sources
        never share a block.
        """
        mask = self.chosen(sources)
        blocks = window_blocks(self.ends[mask], self.which[mask], bootstrap.block_steps)
        return bootstrap_auprc(
            self.logits[mask] + self.prior_offset,
            self.labels[mask],
            blocks,
            bootstrap.replicates,
            bootstrap.seed,
            bootstrap.confidence,
        )


# =====================================================================================
# the criterion
# =====================================================================================


@dataclass(frozen=True)
class ControlVerdict:
    """ADR-0023's criterion, applied.

    Attributes:
        sensitive: Whether the probe is judged sensitive to backbone quality.
        trained_low: The trained backbone's lower bound.
        random_high: The highest upper bound among the random-init backbones.
        reason: One sentence saying why.
    """

    sensitive: bool
    trained_low: float
    random_high: float
    reason: str


def decide_sensitive(
    trained: AuprcInterval, random: list[AuprcInterval], max_discarded_share: float
) -> ControlVerdict:
    """Apply ADR-0023: the trained interval must lie entirely above every random-init interval.

    Args:
        trained: The trained backbone's pooled interval.
        random: Each random-init backbone's pooled interval.
        max_discarded_share: Above this share of discarded replicates an interval is untrusted.

    Returns:
        The verdict.

    Raises:
        ValueError: If no random-init interval is given.
    """
    if not random:
        raise ValueError("the control needs at least one random-init interval")
    random_high = max(iv.high for iv in random)
    untrusted = [
        iv
        for iv in (trained, *random)
        if iv.discarded_share > max_discarded_share or math.isnan(iv.low) or math.isnan(iv.high)
    ]
    if untrusted:
        return ControlVerdict(
            sensitive=False,
            trained_low=trained.low,
            random_high=random_high,
            reason=f"{len(untrusted)} interval(s) untrusted (discarded share above "
            f"{max_discarded_share:.0%}); the criterion is not met",
        )
    if trained.low > random_high:
        reason = (
            f"the trained lower bound {trained.low:.4f} is above every random-init upper bound "
            f"(highest {random_high:.4f})"
        )
        return ControlVerdict(True, trained.low, random_high, reason)
    reason = (
        f"the trained lower bound {trained.low:.4f} is not above the highest random-init upper "
        f"bound {random_high:.4f}"
    )
    return ControlVerdict(False, trained.low, random_high, reason)


# =====================================================================================
# the run
# =====================================================================================


def trained_scores_path(paths: ProjectPaths, gate: GateCheckConfig) -> Path:
    """Where the gate run saved its test scores."""
    name = f"{gate.rung}_{gate.arm}_seed{gate.seed}_test_scores.npz"
    return paths.checkpoints_dir / f"gate_check_v{gate.version}_{config_hash(gate)}" / name


def run_probe_control(
    paths: ProjectPaths, config_path: Path, device_name: str | None = None
) -> tuple[Path, Path]:
    """Probe each untrained backbone, bootstrap both sides, and apply ADR-0023's criterion.

    Resume-safe: a seed whose scores and probe record are already on disk is read, not re-run.

    Args:
        paths: Resolved project paths.
        config_path: The control configuration.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The report and its JSON record.

    Raises:
        FileNotFoundError: If the gate run's test scores are missing.
        ValueError: If a random-init backbone was scored on other windows than the trained one.
    """
    config = load_config(config_path, ProbeControlConfig)
    gate_path = paths.repo_root / config.gate_config
    gate = load_config(gate_path, GateCheckConfig)
    digest = config_hash(config)
    out_dir = paths.checkpoints_dir / f"probe_control_v{config.version}_{digest}"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = paths.data_reports_dir / f"probe_control_v{config.version}_steps"
    pooling = POOLING[config.design]
    started = time.perf_counter()
    opened: list[ProbeInputs] = []

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

    def probed(name: str, seed: int, checkpoint: Path | None) -> tuple[dict[str, Any], Path]:
        scores_file = out_dir / f"{name}_test_scores.npz"
        record_file = out_dir / f"{name}_probe.json"
        if scores_file.exists() and record_file.exists():
            logger.info("%s already scored, reading %s", name, scores_file)
        else:
            logger.info("=== probe control %s, design %s ===", name, config.design)
            opened_inputs = inputs()
            probe = probe_and_score(
                seed,
                checkpoint,
                opened_inputs,
                gate.held_out_source,
                log_dir / f"{name}_probe.steps.csv",
                f"{name}/probe",
                save_to=out_dir / f"{name}_probe.pt",
                pooling=pooling,
            )
            save_scores(scores_file, probe, opened_inputs.splits["test"])
            probe_record = {
                "seed": seed,
                "backbone": None if checkpoint is None else _relative(checkpoint, paths),
                "design": config.design,
                "positives_seen": probe.probe_positives_seen,
                "seconds": probe.probe_seconds,
                "selected": list(probe.probe_selected),
                "prior_offset": probe.prior_offset,
                "natural_rate": probe.natural_rate,
                "test": [asdict(score) for score in probe.test],
                "held_out_calibration": probe.held_out_calibration,
                "probe_state": _relative(out_dir / f"{name}_probe.pt", paths),
                "step_log": _relative(probe.step_log, paths),
            }
            record_file.write_text(json.dumps(probe_record, indent=1) + "\n", encoding="utf-8")
        return json.loads(record_file.read_text(encoding="utf-8")), scores_file

    backbone = trained_scores_path(paths, gate).with_name(
        f"{gate.rung}_{gate.arm}_seed{gate.seed}.pt"
    )
    if config.design == "final_position":
        # §a: the registered gate run as scored, not re-run.
        trained_path = trained_scores_path(paths, gate)
        if not trained_path.exists():
            raise FileNotFoundError(f"the gate run's test scores are missing: {trained_path}")
        trained_run: dict[str, Any] = {"seed": gate.seed, "selected": list(_gate_selected(paths))}
    else:
        if not backbone.exists():
            raise FileNotFoundError(f"the gate run's backbone is missing: {backbone}")
        trained_run, trained_path = probed(
            f"{gate.rung}_trained_seed{gate.seed}", gate.seed, backbone
        )
    trained = ScoredWindows.load(trained_path)
    runs: dict[int, dict[str, Any]] = {}
    scored: dict[int, ScoredWindows] = {}
    for seed in config.init_seeds:
        name = f"{gate.rung}_random_seed{seed}"
        runs[seed], scores_file = probed(name, seed, None)
        scored[seed] = ScoredWindows.load(scores_file)
        if not scored[seed].same_windows(trained):
            raise ValueError(f"{name} was scored on other windows than the trained backbone")
    gpu_seconds = time.perf_counter() - started

    bootstrap, pooled, held_out = gate.bootstrap, config.pooled_sources, [gate.held_out_source]
    rows = [_backbone_row("trained", gate.seed, trained, pooled, held_out, bootstrap)]
    rows += [
        _backbone_row("random", seed, scored[seed], pooled, held_out, bootstrap)
        for seed in config.init_seeds
    ]
    verdict = decide_sensitive(
        rows[0]["pooled"], [row["pooled"] for row in rows[1:]], bootstrap.max_discarded_share
    )
    seconds = time.perf_counter() - started
    logger.info(
        "PROBE CONTROL (ADR-0023): %s -- %s",
        "PASS" if verdict.sensitive else "FAIL",
        verdict.reason,
    )

    stem = f"probe_control_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(
        render_control_report(
            config,
            config_path,
            gate,
            trained_path,
            rows,
            trained_run,
            runs,
            verdict,
            gpu_seconds,
            seconds,
            paths,
        ),
        encoding="utf-8",
        newline="\n",
    )
    record = paths.data_reports_dir / f"{stem}.json"
    payload = {
        "config": config.model_dump(mode="json"),
        "config_hash": digest,
        "gate_config_hash": config_hash(gate),
        "trained_scores": _relative(trained_path, paths),
        "seconds": seconds,
        "verdict": asdict(verdict),
        "backbones": [
            {
                "backbone": row["backbone"],
                "seed": row["seed"],
                "pooled": asdict(row["pooled"]),
                "held_out": asdict(row["held_out"]),
                "per_source_auprc": row["per_source"],
            }
            for row in rows
        ],
        "trained_probe": trained_run,
        "random_probes": [runs[seed] for seed in config.init_seeds],
    }
    record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record)
    return report, record


def _gate_selected(paths: ProjectPaths) -> tuple[int, float]:
    """The gate run's selected probe step and validation AUPRC, from its newest record."""
    found = sorted(paths.data_reports_dir.glob("gate_check_v0_[0-9]*.json"))
    if not found:
        raise FileNotFoundError("no gate_check_v0_<date>.json record")
    step, value = json.loads(found[-1].read_text(encoding="utf-8"))["probe"]["selected"]
    return int(step), float(value)


def _backbone_row(
    backbone: str,
    seed: int,
    scores: ScoredWindows,
    pooled: list[str],
    held_out: list[str],
    bootstrap: BootstrapConfig,
) -> dict[str, Any]:
    logger.info("bootstrapping %s seed %d", backbone, seed)
    return {
        "backbone": backbone,
        "seed": seed,
        "pooled": scores.interval(pooled, bootstrap),
        "held_out": scores.interval(held_out, bootstrap),
        "per_source": {source: scores.auprc([source]) for source in scores.sources},
    }


def _relative(path: Path, paths: ProjectPaths) -> str:
    try:
        return path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# =====================================================================================
# the report
# =====================================================================================


def _interval(iv: AuprcInterval) -> tuple[str, str]:
    return f"{iv.auprc:.4f}", f"[{iv.low:.4f}, {iv.high:.4f}]"


def render_control_report(
    config: ProbeControlConfig,
    config_path: Path,
    gate: GateCheckConfig,
    trained_path: Path,
    rows: list[dict[str, Any]],
    trained_run: dict[str, Any],
    runs: dict[int, dict[str, Any]],
    verdict: ControlVerdict,
    gpu_seconds: float,
    seconds: float,
    paths: ProjectPaths,
) -> str:
    """Render the control's report.

    Args:
        config: The control configuration.
        config_path: Where it was read from.
        gate: The gate configuration the trained side and the interval come from.
        trained_path: The trained backbone's scores file.
        rows: Per backbone, its pooled and held-out intervals and per-source AUPRC.
        trained_run: The trained backbone's probe record (its seed and selected step at least).
        runs: Per random-init seed, its probe record.
        verdict: The criterion applied.
        gpu_seconds: Wall clock of the probe stages this invocation ran.
        seconds: Wall clock of the whole invocation.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    pooled_name = " + ".join(config.pooled_sources)
    first = rows[0]["pooled"]
    main_rows = []
    for row in rows:
        pooled_auprc, pooled_iv = _interval(row["pooled"])
        held_auprc, held_iv = _interval(row["held_out"])
        label = (
            f"full-budget tel_only, seed {row['seed']}"
            if row["backbone"] == "trained"
            else f"random init, seed {row['seed']}"
        )
        main_rows.append((label, pooled_auprc, pooled_iv, held_auprc, held_iv))
    source_rows = [
        (
            f"{row['backbone']} seed {row['seed']}",
            *(f"{row['per_source'][s]:.4f}" for s in rows[0]["per_source"]),
        )
        for row in rows
    ]
    probe_rows = [
        (
            label,
            f"{run['positives_seen']:,}" if "positives_seen" in run else "16,000",
            f"{run['selected'][1]:.4f} at step {run['selected'][0]}",
            f"{run['seconds'] / 60:.1f}" if "seconds" in run else "(gate run)",
        )
        for label, run in [
            (f"trained, seed {trained_run['seed']}", trained_run),
            *((f"random init, seed {seed}", run) for seed, run in runs.items()),
        ]
    ]
    word = "PASS" if verdict.sensitive else "FAIL"
    consequence = (
        f"The probe is judged sensitive to backbone quality. The {config.design} design is the "
        "probe for every arm."
        if verdict.sensitive
        else f"The {config.design} design is the defect. The arm runs do not proceed until a "
        "redesigned probe passes this same criterion (ADR-0023, the next registered sub-step)."
    )
    return "".join(
        [
            "# Random-init probe control\n\n",
            kv_table(
                {
                    "configuration": f"{_relative(config_path, paths)} "
                    f"(hash {config_hash(config)})",
                    "decision record": "docs/DECISIONS.md, ADR-0023 (registered in c9489a2, "
                    "before this code)",
                    "probe design": config.design,
                    "trained side": f"{_relative(trained_path, paths)} "
                    + (
                        "(the ADR-0021 gate run, not re-run)"
                        if config.design == "final_position"
                        else f"(the ADR-0021 gate backbone, probed through {config.design})"
                    ),
                    "random-init seeds": ", ".join(str(s) for s in config.init_seeds),
                    "pooled split": f"{pooled_name} test: {first.windows:,} windows, "
                    f"{first.positives:,} positive, {first.positive_blocks:,} of "
                    f"{first.blocks:,} blocks holding a positive",
                    "bootstrap": f"{gate.bootstrap.replicates:,} replicates, blocks of "
                    f"{gate.bootstrap.block_steps} steps within each shard, seed "
                    f"{gate.bootstrap.seed}, {gate.bootstrap.confidence:.0%} percentile",
                    "probe wall clock": f"{gpu_seconds / 3600:.2f} GPU-hours",
                    "total wall clock": f"{seconds / 60:.1f} min",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model probe-control",
                }
            ),
            section(
                "1. The criterion, as registered",
                f"**{word}: {verdict.reason}.**\n\n{consequence}\n",
            ),
            section(
                "2. Test AUPRC with 95% block intervals",
                table(
                    [
                        "backbone",
                        f"pooled {pooled_name}",
                        "95% interval (decides)",
                        gate.held_out_source,
                        "95% interval (reported)",
                    ],
                    main_rows,
                )
                + "\nThe criterion reads the pooled column: the trained lower bound must be above "
                "every random-init upper bound. Hill of Towie is not evaluable under ADR-0021 "
                "and decides nothing here.\n",
            ),
            section(
                "3. Test AUPRC per source",
                table(["backbone", *rows[0]["per_source"]], source_rows),
            ),
            section(
                "4. The probes",
                table(
                    ["backbone", "positives seen", "selected validation AUPRC", "probe min"],
                    probe_rows,
                ),
            ),
        ]
    )
