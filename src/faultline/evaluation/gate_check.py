"""The held-out-site gate (ADR-0021): can Hill of Towie separate ``tel_only`` from chance?

Two commands share this module.

- ``faultline model gate-check`` pretrains ``tel_only`` **once, at the full per-arm budget**
  (50,000,000 tokens), trains the frozen probe of ADR-0020 on it, scores the test windows, and
  reads ADR-0021's rule: Hill of Towie is *evaluable* only if the lower bound of a 48-hour
  block-bootstrap interval on its AUPRC is strictly above its base rate. The rule, the interval
  and the fallback were committed before this module existed.
- ``faultline model probe-intervals`` applies the same interval to **both half-budget seeds of
  ADR-0020**. Their probe heads and test scores were not saved, so the probe stage is re-run on
  each saved backbone, seeded as the original was, and the re-run's AUPRC is reported beside the
  recorded one. It decides nothing.

Every scored window's logit, label, source and end step is written beside the checkpoints, so
no later interval needs the GPU again.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
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
from faultline.evaluation.ladder import SplitEval
from faultline.evaluation.variance_probe import (
    PretrainRecord,
    ProbeInputs,
    ProbeResult,
    VarianceProbeConfig,
    open_probe_inputs,
    pretrain_tel,
    probe_and_score,
)
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.config import Budget
from faultline.training.mixture import JointMixtureConfig

logger = get_logger(__name__)


class BootstrapConfig(StrictModel):
    """ADR-0021's within-seed interval, as registered before the run.

    Attributes:
        block_steps: Steps a resampled block spans (288: 48 hours, twice the label horizon).
        replicates: Bootstrap replicates.
        seed: Seed of the resampling.
        confidence: Coverage of the percentile interval.
        max_discarded_share: Above this share of replicates without a positive window, the
            interval is untrusted and the verdict is not evaluable.
    """

    block_steps: int = Field(gt=0)
    replicates: int = Field(gt=0)
    seed: int
    confidence: float = Field(gt=0.0, lt=1.0)
    max_discarded_share: float = Field(ge=0.0, lt=1.0)


class GateCheckConfig(StrictModel):
    """Top level of ``configs/train/gate_check_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        mixture_config: The joint mixture (shards, arms, the per-arm budget).
        ladder_config: The positive-aware risk stage, the evaluation windows and the optimiser.
        arm: The arm; only a telemetry-only arm is supported.
        rung: The rung.
        seed: The one seed.
        tokens: Pretraining tokens: the mixture's full per-arm budget.
        batch_windows: Windows per forward pass while pretraining.
        accumulate: Forward passes per optimiser step while pretraining.
        learning_rate: Peak pretraining learning rate.
        evaluations: Validation measurements during pretraining.
        selection_windows: Validation windows per source for pretraining selection.
        held_out_source: The held-out site the rule reads.
        bootstrap: The within-seed interval.
        half_budget_probe_config: ADR-0020's probe, whose saved backbones get the same interval.
    """

    version: int = 0
    mixture_config: str
    ladder_config: str
    arm: str
    rung: str
    seed: int
    tokens: int = Field(gt=0)
    batch_windows: int = Field(gt=0)
    accumulate: int = Field(gt=0)
    learning_rate: float = Field(gt=0.0)
    evaluations: int = Field(gt=0)
    selection_windows: int = Field(gt=0)
    held_out_source: str
    bootstrap: BootstrapConfig
    half_budget_probe_config: str

    def budget(self, context_tokens: int) -> Budget:
        """The pretraining window budget: the token target, rounded up to a whole step."""
        per_step = self.batch_windows * self.accumulate
        steps = -(-self.tokens // (per_step * context_tokens))
        return Budget(
            windows=steps * per_step,
            batch_windows=self.batch_windows,
            accumulate=self.accumulate,
            learning_rate=self.learning_rate,
            evaluations=self.evaluations,
        )


# =====================================================================================
# scores on disk, and the interval
# =====================================================================================


def window_ends(split: SplitEval) -> np.ndarray:
    """Per scored window, its end step, in the order a test pass scores them."""
    index = split.sampler.index
    ends = np.empty(index.shape[0], dtype=np.int64)
    for position, window_set in enumerate(split.sampler.sets):
        chosen = index[:, 0] == position
        ends[chosen] = window_set.ends[index[chosen, 1]]
    return ends


def save_scores(path: Path, probe: ProbeResult, split: SplitEval) -> Path:
    """Write every test window's logit, label, set, source and end step.

    Args:
        path: The ``.npz`` file to write.
        probe: The probe's result.
        split: The test split it scored.

    Returns:
        The file written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        logits=probe.logits,
        labels=probe.labels,
        which=probe.which,
        ends=window_ends(split),
        sources=np.asarray(split.sources),
        prior_offset=np.asarray(probe.prior_offset),
    )
    return path


@dataclass(frozen=True)
class SiteIntervals:
    """The held-out site's intervals, block and window, and the rule read on the block one.

    Attributes:
        block: The registered interval, resampling 48-hour blocks.
        window: The same, resampling windows, reported to show what the unit changes.
        verdict: ADR-0021's rule on the block interval.
    """

    block: AuprcInterval
    window: AuprcInterval
    verdict: GateVerdict


def site_intervals(
    probe: ProbeResult, split: SplitEval, source: str, bootstrap: BootstrapConfig
) -> SiteIntervals:
    """Bootstrap one source's test AUPRC, by block and by window, and read the rule.

    Args:
        probe: The probe's result.
        split: The test split it scored.
        source: The source.
        bootstrap: The registered interval.

    Returns:
        Both intervals and the verdict.
    """
    chosen = probe.which == split.sources.index(source)
    scores = probe.logits[chosen] + probe.prior_offset
    labels = probe.labels[chosen]
    blocks = window_blocks(window_ends(split)[chosen], probe.which[chosen], bootstrap.block_steps)
    block = bootstrap_auprc(
        scores, labels, blocks, bootstrap.replicates, bootstrap.seed, bootstrap.confidence
    )
    window = bootstrap_auprc(
        scores,
        labels,
        np.arange(labels.size, dtype=np.int64),
        bootstrap.replicates,
        bootstrap.seed,
        bootstrap.confidence,
        unit="window",
    )
    return SiteIntervals(
        block=block,
        window=window,
        verdict=decide_evaluable(block, bootstrap.max_discarded_share),
    )


# =====================================================================================
# the full-budget gate check
# =====================================================================================


def run_gate_check(
    paths: ProjectPaths, config_path: Path, device_name: str | None = None
) -> tuple[Path, Path]:
    """Pretrain ``tel_only`` at full budget, probe it, and read ADR-0021's rule.

    Args:
        paths: Resolved project paths.
        config_path: The gate configuration.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The report and its JSON record.

    Raises:
        ValueError: If the budget is not the mixture's full per-arm budget.
    """
    config = load_config(config_path, GateCheckConfig)
    mixture = load_config(paths.repo_root / config.mixture_config, JointMixtureConfig)
    if config.tokens != mixture.tokens_per_arm:
        raise ValueError(
            f"the gate runs at full budget: {config.tokens:,} != {mixture.tokens_per_arm:,}"
        )
    inputs = open_probe_inputs(
        paths,
        config.mixture_config,
        config.ladder_config,
        config.arm,
        config.rung,
        config.selection_windows,
        config.held_out_source,
        device_name,
    )
    digest = config_hash(config)
    out_dir = paths.checkpoints_dir / f"gate_check_v{config.version}_{digest}"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = paths.data_reports_dir / f"gate_check_v{config.version}_steps"
    log_dir.mkdir(parents=True, exist_ok=True)
    name = f"{config.rung}_{config.arm}_seed{config.seed}"

    started = time.perf_counter()
    logger.info("=== gate check %s seed %d, %s tokens ===", config.arm, config.seed, config.tokens)
    lm = pretrain_tel(config.seed, config, inputs, out_dir, log_dir)
    probe = probe_and_score(
        config.seed,
        lm.checkpoint,
        inputs,
        config.held_out_source,
        log_dir / f"{name}_probe.steps.csv",
        f"{config.rung}/{config.arm}/seed{config.seed}/probe",
    )
    scores = save_scores(out_dir / f"{name}_test_scores.npz", probe, inputs.splits["test"])
    intervals = site_intervals(
        probe, inputs.splits["test"], config.held_out_source, config.bootstrap
    )
    seconds = time.perf_counter() - started
    verdict = intervals.verdict
    logger.info(
        "GATE VERDICT (ADR-0021): %s -- %s",
        "EVALUABLE" if verdict.evaluable else "NOT EVALUABLE",
        verdict.reason,
    )

    stem = f"gate_check_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(
        render_gate_report(config, config_path, inputs, lm, probe, intervals, seconds, paths),
        encoding="utf-8",
        newline="\n",
    )
    record = paths.data_reports_dir / f"{stem}.json"
    payload = {
        "config": config.model_dump(mode="json"),
        "config_hash": digest,
        "spec": inputs.spec.__dict__,
        "seconds": seconds,
        "device": str(inputs.device),
        "verdict": asdict(verdict),
        "intervals": {"block": asdict(intervals.block), "window": asdict(intervals.window)},
        "pretraining": {
            **{k: v for k, v in asdict(lm).items() if k not in ("checkpoint", "step_log")},
            "checkpoint": _relative(lm.checkpoint, paths),
            "step_log": _relative(lm.step_log, paths),
        },
        "probe": _probe_payload(probe, paths),
        "test_scores": _relative(scores, paths),
    }
    record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record)
    return report, record


# =====================================================================================
# the half-budget seeds, re-probed
# =====================================================================================


def run_probe_intervals(
    paths: ProjectPaths, config_path: Path, device_name: str | None = None
) -> tuple[Path, Path]:
    """Re-run the frozen probe on ADR-0020's saved backbones and bootstrap each seed.

    Args:
        paths: Resolved project paths.
        config_path: The gate configuration, for the interval and the probe it names.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The report and its JSON record.

    Raises:
        FileNotFoundError: If a saved backbone or the probe's recorded JSON is missing.
    """
    config = load_config(config_path, GateCheckConfig)
    probe_path = paths.repo_root / config.half_budget_probe_config
    probe_config = load_config(probe_path, VarianceProbeConfig)
    digest = config_hash(probe_config)
    checkpoints = paths.checkpoints_dir / f"variance_probe_v{probe_config.version}_{digest}"
    recorded = recorded_probe_auprc(paths, probe_config.version, digest, probe_config)
    inputs = open_probe_inputs(
        paths,
        probe_config.mixture_config,
        probe_config.ladder_config,
        probe_config.arm,
        probe_config.rung,
        probe_config.selection_windows,
        probe_config.held_out_source,
        device_name,
    )
    log_dir = paths.data_reports_dir / f"variance_probe_v{probe_config.version}_intervals_steps"
    log_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    for seed in probe_config.seeds:
        name = f"{probe_config.rung}_{probe_config.arm}_seed{seed}"
        checkpoint = checkpoints / f"{name}.pt"
        if not checkpoint.exists():
            raise FileNotFoundError(f"ADR-0020's backbone is missing: {checkpoint}")
        logger.info("=== half-budget re-probe %s ===", name)
        probe = probe_and_score(
            seed,
            checkpoint,
            inputs,
            probe_config.held_out_source,
            log_dir / f"{name}_probe.steps.csv",
            f"{probe_config.rung}/{probe_config.arm}/seed{seed}/probe-rerun",
        )
        scores = save_scores(
            checkpoints / f"{name}_rerun_test_scores.npz", probe, inputs.splits["test"]
        )
        intervals = site_intervals(
            probe, inputs.splits["test"], probe_config.held_out_source, config.bootstrap
        )
        logger.info(
            "seed %d: recorded AUPRC %.4f, re-run %.4f, block interval [%.4f, %.4f], "
            "base rate %.5f (reported, not a gate)",
            seed,
            recorded[seed],
            intervals.block.auprc,
            intervals.block.low,
            intervals.block.high,
            intervals.block.base_rate,
        )
        rows.append(
            {
                "seed": seed,
                "recorded_auprc": recorded[seed],
                "intervals": intervals,
                "probe": _probe_payload(probe, paths),
                "test_scores": _relative(scores, paths),
            }
        )
    seconds = time.perf_counter() - started

    stem = f"variance_probe_v{probe_config.version}_intervals_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(
        render_intervals_report(config, config_path, probe_path, rows, seconds, paths),
        encoding="utf-8",
        newline="\n",
    )
    record = paths.data_reports_dir / f"{stem}.json"
    payload = {
        "config": config.model_dump(mode="json"),
        "config_hash": config_hash(config),
        "probe_config_hash": digest,
        "seconds": seconds,
        "device": str(inputs.device),
        "seeds": [
            {
                **{k: v for k, v in row.items() if k != "intervals"},
                "block": asdict(row["intervals"].block),
                "window": asdict(row["intervals"].window),
                "rule_if_it_applied": asdict(row["intervals"].verdict),
            }
            for row in rows
        ],
    }
    record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record)
    return report, record


def recorded_probe_auprc(
    paths: ProjectPaths, version: int, digest: str, probe_config: VarianceProbeConfig
) -> dict[int, float]:
    """Read each seed's held-out AUPRC from ADR-0020's recorded JSON, checked against the config.

    Args:
        paths: Resolved project paths.
        version: The probe configuration's version.
        digest: The probe configuration's hash.
        probe_config: The probe configuration.

    Returns:
        Per seed, the recorded held-out-site test AUPRC.

    Raises:
        FileNotFoundError: If no record exists.
        ValueError: If the newest record was made under another configuration.
    """
    pattern = re.compile(rf"^variance_probe_v{version}_\d{{8}}\.json$")
    found = sorted(p for p in paths.data_reports_dir.iterdir() if pattern.match(p.name))
    if not found:
        raise FileNotFoundError(f"no variance_probe_v{version}_<date>.json record")
    payload = json.loads(found[-1].read_text(encoding="utf-8"))
    if payload["config_hash"] != digest:
        raise ValueError(f"{found[-1].name} was made under {payload['config_hash']}, not {digest}")
    return {
        int(seed["seed"]): float(
            next(t["auprc"] for t in seed["test"] if t["source"] == probe_config.held_out_source)
        )
        for seed in payload["seeds"]
    }


# =====================================================================================
# reports
# =====================================================================================


def _relative(path: Path, paths: ProjectPaths) -> str:
    try:
        return path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _probe_payload(probe: ProbeResult, paths: ProjectPaths) -> dict[str, Any]:
    return {
        "positives_seen": probe.probe_positives_seen,
        "seconds": probe.probe_seconds,
        "selected": probe.probe_selected,
        "prior_offset": probe.prior_offset,
        "natural_rate": probe.natural_rate,
        "test": [asdict(score) for score in probe.test],
        "held_out_calibration": probe.held_out_calibration,
        "step_log": _relative(probe.step_log, paths),
    }


def _interval_rows(intervals: SiteIntervals) -> list[tuple[object, ...]]:
    return [
        (
            iv.unit,
            f"{iv.auprc:.4f}",
            f"[{iv.low:.4f}, {iv.high:.4f}]",
            f"[{iv.lift_low:+.4f}, {iv.lift_high:+.4f}]",
            f"{iv.base_rate:.5f}",
            f"{iv.positives:,}",
            f"{iv.positive_blocks:,} of {iv.blocks:,}",
            f"{iv.discarded} of {iv.replicates:,}",
        )
        for iv in (intervals.block, intervals.window)
    ]


_CALIBRATION_ROWS = (
    ("mean p, uncorrected", "uncorrected_mean_predicted_rate"),
    ("mean p, corrected", "mean_predicted_rate"),
    ("held-out base rate", "base_rate"),
    ("ECE, corrected", "expected_calibration_error"),
)

_INTERVAL_HEADER = [
    "resampled unit",
    "AUPRC",
    "95% interval",
    "lift over chance, 95%",
    "base rate",
    "positive windows",
    "units with a positive",
    "replicates discarded",
]


def render_gate_report(
    config: GateCheckConfig,
    config_path: Path,
    inputs: ProbeInputs,
    lm: PretrainRecord,
    probe: ProbeResult,
    intervals: SiteIntervals,
    seconds: float,
    paths: ProjectPaths,
) -> str:
    """Render the gate check's report.

    Args:
        config: The gate configuration.
        config_path: Where it was read from.
        inputs: The opened inputs, for the rung.
        lm: The pretraining record.
        probe: The probe's result.
        intervals: The held-out site's intervals and verdict.
        seconds: Wall clock of the run.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    verdict, spec = intervals.verdict, inputs.spec
    if verdict.evaluable:
        consequence = (
            "Leave-site-out on Hill of Towie **stays the primary evaluation**. The three-arm "
            "design of ADR-0020 proceeds, and every arm's Hill of Towie AUPRC is reported with "
            "its within-seed interval beside the 0.010 line."
        )
    else:
        consequence = (
            "**Leave-site-out is demoted to a reported negative result.** Every arm's Hill of "
            "Towie AUPRC and interval are still reported, labelled not evaluable under ADR-0021, "
            "and no arm claim rests on them. **The primary evaluation is promoted to CARE "
            "(ADR-0010) or a temporal holdout at the training sites.** The choice is the user's, "
            "committed before either is scored for any arm."
        )
    word = "EVALUABLE" if verdict.evaluable else "NOT EVALUABLE"
    verdict_body = (
        f"**{config.held_out_source} is {word}: {verdict.reason}.**\n\n{consequence}\n\n"
        "The interval is within one seed: evaluation sampling noise at a fixed model, not seed "
        "variance. No other run was started.\n"
    )
    score_rows = [
        (s.source, f"{s.auprc:.4f}", f"{s.lift:.2f}", f"{s.windows:,}", f"{s.positives:,}")
        for s in probe.test
    ]
    calibration = probe.held_out_calibration
    return "".join(
        [
            "# Held-out-site gate: tel_only at full budget\n\n",
            kv_table(
                {
                    "configuration": f"{_relative(config_path, paths)} "
                    f"(hash {config_hash(config)})",
                    "decision record": "docs/DECISIONS.md, ADR-0021 (registered before this run)",
                    "arm": config.arm,
                    "rung": f"{spec.name}: d_model {spec.d_model}, {spec.n_layer} layers, "
                    f"context {spec.context}, vocabulary {spec.vocab_size:,}",
                    "seed": str(config.seed),
                    "pretraining": f"{lm.lm_tokens:,} tokens, {lm.lm_steps} steps, "
                    f"selected val loss {lm.lm_selected[1]:.4f} at step {lm.lm_selected[0]}, "
                    f"{lm.lm_seconds / 60:.1f} min",
                    "probe": f"{probe.probe_positives_seen:,} positives, selected val AUPRC "
                    f"{probe.probe_selected[1]:.4f} at step {probe.probe_selected[0]}, "
                    f"{probe.probe_seconds / 60:.1f} min",
                    "bootstrap": f"{config.bootstrap.replicates:,} replicates, blocks of "
                    f"{config.bootstrap.block_steps} steps, seed {config.bootstrap.seed}, "
                    f"{config.bootstrap.confidence:.0%} percentile",
                    "device": str(inputs.device),
                    "wall clock": f"{seconds / 3600:.2f} GPU-hours",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model gate-check",
                }
            ),
            section("1. The verdict, under the rule registered before the run", verdict_body),
            section(
                f"2. {config.held_out_source} test AUPRC, within-seed intervals",
                table(_INTERVAL_HEADER, _interval_rows(intervals))
                + "\nThe rule reads the block interval's lower bound. The window row shows what "
                "treating clustered positives as independent would have given.\n",
            ),
            section(
                "3. Test AUPRC per source",
                table(["source", "AUPRC", "lift", "windows", "positives"], score_rows),
            ),
            section(
                f"4. Calibration on {config.held_out_source}, prior-corrected (ADR-0019)",
                kv_table(
                    {
                        "logit offset": f"{probe.prior_offset:.3f}",
                        "training natural rate": f"{probe.natural_rate:.4f}",
                        **{
                            label: f"{calibration.get(key, float('nan')):.4f}"
                            for label, key in _CALIBRATION_ROWS
                        },
                    }
                ),
            ),
        ]
    )


def render_intervals_report(
    config: GateCheckConfig,
    config_path: Path,
    probe_path: Path,
    rows: list[dict[str, Any]],
    seconds: float,
    paths: ProjectPaths,
) -> str:
    """Render the half-budget seeds' intervals.

    Args:
        config: The gate configuration, for the interval.
        config_path: Where it was read from.
        probe_path: ADR-0020's probe configuration.
        rows: Per seed: recorded AUPRC, intervals, probe payload, scores file.
        seconds: Wall clock.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    comparison = [
        (
            row["seed"],
            f"{row['recorded_auprc']:.4f}",
            f"{row['intervals'].block.auprc:.4f}",
            f"{row['intervals'].block.auprc - row['recorded_auprc']:+.4f}",
        )
        for row in rows
    ]
    body = []
    for row in rows:
        intervals: SiteIntervals = row["intervals"]
        body.append(
            section(
                f"2.{row['seed']} Seed {row['seed']}",
                table(_INTERVAL_HEADER, _interval_rows(intervals))
                + f"\nHad ADR-0021's rule applied to this seed: {intervals.verdict.reason}. "
                "It does not apply; this is reported only.\n",
                level=3,
            )
        )
    return "".join(
        [
            "# Seed-variance probe, half budget: within-seed intervals\n\n",
            kv_table(
                {
                    "interval": f"{_relative(config_path, paths)}, section bootstrap (ADR-0021)",
                    "backbones": f"{_relative(probe_path, paths)} (ADR-0020), saved checkpoints",
                    "what was re-run": "the frozen probe stage and the test pass, seeded as the "
                    "original; pretraining was not re-run",
                    "decides": "nothing: ADR-0020's verdict and ADR-0021's gate are unchanged",
                    "wall clock": f"{seconds / 3600:.2f} GPU-hours",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model probe-intervals",
                }
            ),
            section(
                "1. The re-run against the recorded probe",
                table(["seed", "recorded AUPRC", "re-run AUPRC", "difference"], comparison)
                + "\nA non-zero difference is the probe stage's run-to-run nondeterminism on the "
                "GPU. The intervals below read the re-run's scores.\n",
            ),
            section("2. Hill of Towie test AUPRC, within each seed", "".join(body)),
        ]
    )
