"""The paired probe-sensitivity test (ADR-0024): trained minus random-init AUPRC, paired.

ADR-0023 asked whether the probe can see backbone quality, and it asked through independent
intervals that had to separate. Both models are scored on the same windows, so their estimates
are correlated. The question calls for a test on the difference. ADR-0024, registered after
ADR-0023's four FAILs and before any paired interval existed, reads it that way. The blocks are
resampled once per replicate, both models are read on the same rows, and the probe is sensitive
if the 95% interval on Δ AUPRC lies above zero against **each** of the three random-init seeds.

**Which windows decide.** The pooled Kelmarsh + Penmanshiel test split thinned to stride 12: all
windows at that stride, uncapped, which is 5,799 of the split's 5,800 blocks. It was the user's
choice over stride 1 at 1.33 GPU-hours a model. ADR-0023's 24,000-window subsample is reported
beside it for all four designs, from the scores already on disk.

**The order.** §a, then §d, then §b, then §c. Designs are re-scored at stride 12 only while none
has passed, and the first to pass is the probe. Every selected probe is re-scored from its saved
state, with no optimiser step. The one exception is §a's trained probe: the gate run never saved
its head, so its probe stage is re-run seeded and accepted only if it reproduces the gate run's
record to four decimals.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from pydantic import Field, model_validator

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.evaluation.bootstrap import DeltaInterval, paired_bootstrap_deltas, window_blocks
from faultline.evaluation.gate_check import BootstrapConfig, GateCheckConfig, window_ends
from faultline.evaluation.ladder import SplitEval, build_split
from faultline.evaluation.metrics import average_precision
from faultline.evaluation.probe_control import (
    HEAD_LAYERS,
    POOLING,
    UNFROZEN_BLOCKS,
    ProbeControlConfig,
    ScoredWindows,
    trained_scores_path,
)
from faultline.evaluation.variance_probe import ProbeInputs, open_probe_inputs, probe_and_score
from faultline.logging_utils import get_logger
from faultline.model.checkpoints import read_checkpoint
from faultline.model.risk import RiskModel, RiskSpec
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.loop import risk_logits

logger = get_logger(__name__)

#: The design names ADR-0023 registered, by sub-section.
SECTION = {
    "final_position": "§a",
    "mean_pooled": "§b",
    "mlp_mean_pooled": "§c",
    "unfrozen_mlp_mean_pooled": "§d",
}


class Reproduction(StrictModel):
    """The gate run's probe record, which a seeded re-run of it must match (ADR-0024 §4).

    Attributes:
        selected_step: The selected validation measurement's step.
        selected_auprc: Its validation AUPRC.
        pooled_auprc: Pooled test AUPRC on the 24,000-window subsample.
        decimals: Decimal places the re-run must match.
    """

    selected_step: int
    selected_auprc: float
    pooled_auprc: float
    decimals: int = Field(ge=1)


class PairedControlConfig(StrictModel):
    """Top level of ``configs/train/paired_control_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        control_configs: ADR-0023's control configurations, **in ADR-0024's order of application**.
        stride: The stride of the deciding test windows, uncapped.
        reproduction: The record §a's re-run probe must reproduce.
    """

    version: int = 0
    control_configs: list[str] = Field(min_length=1)
    stride: int = Field(gt=0)
    reproduction: Reproduction

    @model_validator(mode="after")
    def _distinct(self) -> PairedControlConfig:
        """Refuse a control listed twice.

        Raises:
            ValueError: If a control configuration repeats.
        """
        if len(set(self.control_configs)) != len(self.control_configs):
            raise ValueError(f"control configurations repeat: {self.control_configs}")
        return self


# =====================================================================================
# the criterion
# =====================================================================================


@dataclass(frozen=True)
class PairedVerdict:
    """ADR-0024's criterion, applied to one design.

    Attributes:
        sensitive: Whether the probe is judged sensitive to backbone quality.
        lowest: The smallest lower bound among the comparisons.
        reason: One sentence saying why.
    """

    sensitive: bool
    lowest: float
    reason: str


def decide_paired(deltas: list[DeltaInterval], max_discarded_share: float) -> PairedVerdict:
    """Apply ADR-0024: every trained-minus-random interval must have a lower bound above zero.

    Args:
        deltas: Per random-init seed, the paired interval on trained minus it.
        max_discarded_share: Above this share of discarded replicates a comparison is untrusted.

    Returns:
        The verdict.

    Raises:
        ValueError: If no comparison is given.
    """
    if not deltas:
        raise ValueError("the criterion needs at least one random-init comparison")
    lowest = min(d.low for d in deltas)
    untrusted = [d for d in deltas if d.discarded_share > max_discarded_share or math.isnan(d.low)]
    if untrusted:
        return PairedVerdict(
            False,
            lowest,
            f"{len(untrusted)} comparison(s) untrusted (discarded share above "
            f"{max_discarded_share:.0%}); the criterion is not met",
        )
    failing = sum(1 for d in deltas if not d.low > 0.0)
    if failing == 0:
        return PairedVerdict(
            True, lowest, f"every paired lower bound is above zero (lowest {lowest:+.4f})"
        )
    return PairedVerdict(
        False,
        lowest,
        f"{failing} of {len(deltas)} paired lower bounds are not above zero (lowest {lowest:+.4f})",
    )


def paired_rows(
    trained: ScoredWindows,
    random: list[ScoredWindows],
    sources: list[str],
    bootstrap: BootstrapConfig,
) -> list[DeltaInterval]:
    """The paired intervals of one trained probe against each random-init probe, pooled.

    Args:
        trained: The trained backbone's scores.
        random: Each random-init backbone's scores on the same windows.
        sources: The sources pooled.
        bootstrap: Blocks, replicates, seed and coverage.

    Returns:
        Per random-init probe, the interval on trained minus it.

    Raises:
        ValueError: If a random-init probe was scored on other windows.
    """
    for other in random:
        if not other.same_windows(trained):
            raise ValueError("a random-init probe was scored on other windows than the trained one")
    mask = trained.chosen(sources)
    blocks = window_blocks(trained.ends[mask], trained.which[mask], bootstrap.block_steps)
    return paired_bootstrap_deltas(
        trained.logits[mask] + trained.prior_offset,
        [other.logits[mask] + other.prior_offset for other in random],
        trained.labels[mask],
        blocks,
        bootstrap.replicates,
        bootstrap.seed,
        bootstrap.confidence,
    )


# =====================================================================================
# scoring a saved probe
# =====================================================================================


def score_saved_probe(
    probe_path: Path, design: str, inputs: ProbeInputs, split: SplitEval
) -> tuple[np.ndarray, np.ndarray]:
    """Load a selected probe, whole, and score a split with it. No optimiser step is taken.

    Args:
        probe_path: The probe's saved state (``save_to`` of ``probe_and_score``).
        design: The ADR-0023 design it was trained under.
        inputs: The opened shards and rung.
        split: The windows to score.

    Returns:
        Every window's logit before the prior offset, and its label, in the split's order.

    Raises:
        ValueError: If the saved probe was trained under another design.
    """
    payload = read_checkpoint(probe_path)
    # A probe saved before an option existed was saved at that option's default (§a predates
    # pooling, §b the layers, §c the unfrozen blocks).
    saved = (
        payload.get("pooling", "last"),
        payload.get("head_layers", 1),
        payload.get("unfrozen_blocks", 0),
    )
    wanted = (POOLING[design], HEAD_LAYERS[design], UNFROZEN_BLOCKS[design])
    if saved != wanted:
        raise ValueError(f"{probe_path} was saved as {saved}, not {design} {wanted}")
    risk = RiskSpec(
        hidden=inputs.ladder_model.head_hidden,
        dropout=inputs.ladder_model.head_dropout,
        label=inputs.ladder.risk.label,
        pooling=POOLING[design],
        layers=HEAD_LAYERS[design],
    )
    model = RiskModel(inputs.spec, risk, frozen=True, unfrozen_blocks=UNFROZEN_BLOCKS[design]).to(
        inputs.device
    )
    model.load_state_dict({k: v.to(inputs.device) for k, v in payload["state"].items()})
    model.eval()
    autocast_on = inputs.ladder.optimiser.precision == "bf16"
    with torch.inference_mode():
        logits, labels, _ = risk_logits(model, split.sampler, inputs.device, autocast_on)
    return logits, labels


def save_split_scores(
    path: Path, scored: tuple[np.ndarray, np.ndarray], split: SplitEval, prior_offset: float
) -> ScoredWindows:
    """Write a split's scores in ``save_scores``'s layout, and read them back.

    Args:
        path: The ``.npz`` file to write.
        scored: Every window's logit and label, in the split's order.
        split: The split scored.
        prior_offset: The probe's prior offset.

    Returns:
        The scores as written.
    """
    logits, labels = scored
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        logits=logits,
        labels=labels,
        which=split.sets,
        ends=window_ends(split),
        sources=np.asarray(split.sources),
        prior_offset=np.asarray(prior_offset),
    )
    return ScoredWindows.load(path)


# =====================================================================================
# the run
# =====================================================================================


@dataclass(frozen=True)
class DesignResult:
    """One design's paired intervals.

    Attributes:
        design: The ADR-0023 design.
        subsample: Per random-init seed, the pooled interval on the 24,000-window subsample.
        held_out: Per random-init seed, the Hill of Towie interval on its 12,000-window subsample.
        deciding: Per random-init seed, the pooled interval on the stride-12 split, if tested.
        verdict: ADR-0024's criterion on ``deciding``, if tested.
        rescore_check: Per probe, its pooled subsample AUPRC as recorded and as re-scored.
    """

    design: str
    subsample: list[DeltaInterval]
    held_out: list[DeltaInterval]
    deciding: list[DeltaInterval] | None
    verdict: PairedVerdict | None
    rescore_check: dict[str, tuple[float, float]]


def run_paired_control(
    paths: ProjectPaths, config_path: Path, device_name: str | None = None
) -> tuple[Path, Path]:
    """Apply ADR-0024 in its registered order and write the report.

    Resume-safe: a probe whose stride-12 scores are on disk is read, not re-scored.

    Args:
        paths: Resolved project paths.
        config_path: The paired-control configuration.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The report and its JSON record.

    Raises:
        RuntimeError: If §a's re-run probe does not reproduce the gate run's record.
        ValueError: If the controls disagree on the gate run, the seeds or the pooled sources.
    """
    config = load_config(config_path, PairedControlConfig)
    controls = [
        load_config(paths.repo_root / c, ProbeControlConfig) for c in config.control_configs
    ]
    if len({(c.gate_config, tuple(c.init_seeds), tuple(c.pooled_sources)) for c in controls}) != 1:
        raise ValueError("the controls must share the gate run, the seeds and the pooled sources")
    gate = load_config(paths.repo_root / controls[0].gate_config, GateCheckConfig)
    seeds, pooled, bootstrap = controls[0].init_seeds, controls[0].pooled_sources, gate.bootstrap
    digest = config_hash(config)
    out_dir = paths.checkpoints_dir / f"paired_control_v{config.version}_{digest}"
    log_dir = paths.data_reports_dir / f"paired_control_v{config.version}_steps"
    started = time.perf_counter()
    opened: list[ProbeInputs] = []
    deciding_split: list[SplitEval] = []
    check_split: list[SplitEval] = []

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

    def split_of(cache: list[SplitEval], per_source: int | None, stride: int) -> SplitEval:
        if not cache:
            evaluation = inputs().ladder.evaluation
            cache.append(
                build_split(
                    inputs().telemetry,
                    "test",
                    per_source,
                    stride,
                    evaluation.seed,
                    evaluation.batch_windows,
                    inputs().ladder.risk.label,
                    sources=pooled,
                )
            )
        return cache[0]

    reproduction: dict[str, Any] = {}
    results: list[DesignResult] = []
    passed: str | None = None
    for control in controls:
        design = control.design
        control_dir = paths.checkpoints_dir / (
            f"probe_control_v{control.version}_{config_hash(control)}"
        )
        name = f"{gate.rung}_trained_seed{gate.seed}"
        trained_sub_path = (
            trained_scores_path(paths, gate)
            if design == "final_position"
            else control_dir / f"{name}_test_scores.npz"
        )
        trained_sub = ScoredWindows.load(trained_sub_path)
        random_sub = [
            ScoredWindows.load(control_dir / f"{gate.rung}_random_seed{s}_test_scores.npz")
            for s in seeds
        ]
        subsample = paired_rows(trained_sub, random_sub, pooled, bootstrap)
        held_out = paired_rows(trained_sub, random_sub, [gate.held_out_source], bootstrap)
        if passed is not None:
            logger.info("%s is reported on the subsample only: %s passed", design, passed)
            results.append(DesignResult(design, subsample, held_out, None, None, {}))
            continue

        design_dir = out_dir / design
        probes: list[tuple[str, Path, float, ScoredWindows]] = []
        if design == "final_position":
            probe_file = design_dir / f"{name}_probe.pt"
            record_file = design_dir / f"{name}_probe.json"
            if not record_file.exists():
                logger.info("=== re-running the gate run's probe (its head was never saved) ===")
                result = probe_and_score(
                    gate.seed,
                    trained_scores_path(paths, gate).with_name(
                        f"{gate.rung}_{gate.arm}_seed{gate.seed}.pt"
                    ),
                    inputs(),
                    gate.held_out_source,
                    log_dir / f"{name}_probe.steps.csv",
                    f"paired/{design}/{name}",
                    save_to=probe_file,
                )
                chosen = np.isin(
                    result.which,
                    [inputs().splits["test"].sources.index(s) for s in pooled],
                )
                record_file.parent.mkdir(parents=True, exist_ok=True)
                record_file.write_text(
                    json.dumps(
                        {
                            "selected": list(result.probe_selected),
                            "prior_offset": result.prior_offset,
                            "pooled_auprc": average_precision(
                                result.logits[chosen], result.labels[chosen].astype(np.float64)
                            ),
                            "max_abs_logit_difference": float(
                                np.max(np.abs(result.logits - trained_sub.logits))
                            ),
                            "seconds": result.probe_seconds,
                        },
                        indent=1,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            reproduction = json.loads(record_file.read_text(encoding="utf-8"))
            expected = config.reproduction
            places = expected.decimals
            matches = (
                reproduction["selected"][0] == expected.selected_step
                and round(reproduction["selected"][1], places)
                == round(expected.selected_auprc, places)
                and round(reproduction["pooled_auprc"], places)
                == round(expected.pooled_auprc, places)
            )
            reproduction["reproduces"] = matches
            if not matches:
                raise RuntimeError(
                    f"the re-run gate probe does not reproduce the record to {places} decimals: "
                    f"{reproduction} against {expected}; nothing is scored (ADR-0024 §4)"
                )
            probes.append((name, probe_file, float(reproduction["prior_offset"]), trained_sub))
        else:
            record = json.loads((control_dir / f"{name}_probe.json").read_text(encoding="utf-8"))
            probes.append(
                (name, control_dir / f"{name}_probe.pt", float(record["prior_offset"]), trained_sub)
            )
        for seed, sub in zip(seeds, random_sub, strict=True):
            random_name = f"{gate.rung}_random_seed{seed}"
            record = json.loads(
                (control_dir / f"{random_name}_probe.json").read_text(encoding="utf-8")
            )
            probes.append(
                (random_name, control_dir / f"{random_name}_probe.pt", record["prior_offset"], sub)
            )

        rescore_check: dict[str, tuple[float, float]] = {}
        deciding_scores: list[ScoredWindows] = []
        for probe_name, probe_path, offset, sub in probes:
            scores_file = design_dir / f"{probe_name}_stride{config.stride}_scores.npz"
            check_file = design_dir / f"{probe_name}_subsample_check.json"
            if not check_file.exists():
                logger.info("re-scoring %s %s on the 24,000-window subsample", design, probe_name)
                check = split_of(check_split, gate_test_windows(inputs()), 1)
                rescored = save_split_scores(
                    design_dir / f"{probe_name}_subsample_scores.npz",
                    score_saved_probe(probe_path, design, inputs(), check),
                    check,
                    offset,
                )
                if not rescored.same_windows(_restricted(sub, pooled)):
                    raise ValueError(f"{probe_name}: the check split is not the scored subsample")
                check_file.parent.mkdir(parents=True, exist_ok=True)
                check_file.write_text(
                    json.dumps({"recorded": sub.auprc(pooled), "rescored": rescored.auprc(pooled)})
                    + "\n",
                    encoding="utf-8",
                )
            checked = json.loads(check_file.read_text(encoding="utf-8"))
            rescore_check[probe_name] = (checked["recorded"], checked["rescored"])
            if scores_file.exists():
                logger.info("%s %s already scored at stride %d", design, probe_name, config.stride)
                deciding_scores.append(ScoredWindows.load(scores_file))
                continue
            logger.info("scoring %s %s at stride %d", design, probe_name, config.stride)
            split = split_of(deciding_split, None, config.stride)
            deciding_scores.append(
                save_split_scores(
                    scores_file,
                    score_saved_probe(probe_path, design, inputs(), split),
                    split,
                    offset,
                )
            )
        deciding = paired_rows(deciding_scores[0], deciding_scores[1:], pooled, bootstrap)
        verdict = decide_paired(deciding, bootstrap.max_discarded_share)
        logger.info(
            "PAIRED CONTROL (ADR-0024) %s: %s -- %s",
            SECTION[design],
            "PASS" if verdict.sensitive else "FAIL",
            verdict.reason,
        )
        results.append(DesignResult(design, subsample, held_out, deciding, verdict, rescore_check))
        if verdict.sensitive:
            passed = design

    seconds = time.perf_counter() - started
    stem = f"paired_control_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(
        render_paired_report(
            config, config_path, gate, seeds, pooled, results, passed, reproduction, seconds, paths
        ),
        encoding="utf-8",
        newline="\n",
    )
    record = paths.data_reports_dir / f"{stem}.json"
    payload = {
        "config": config.model_dump(mode="json"),
        "config_hash": digest,
        "seconds": seconds,
        "in_force": passed,
        "reproduction": reproduction,
        "designs": [
            {
                "design": r.design,
                "section": SECTION[r.design],
                "subsample": [asdict(d) for d in r.subsample],
                "held_out": [asdict(d) for d in r.held_out],
                "deciding": None if r.deciding is None else [asdict(d) for d in r.deciding],
                "verdict": None if r.verdict is None else asdict(r.verdict),
                "rescore_check": r.rescore_check,
            }
            for r in results
        ],
    }
    record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record)
    return report, record


def gate_test_windows(inputs: ProbeInputs) -> int:
    """The per-source cap the probes' test pass used (12,000)."""
    return inputs.ladder.evaluation.test_windows


def _restricted(scores: ScoredWindows, sources: list[str]) -> ScoredWindows:
    """The scores of some sources only, re-indexed to those sources."""
    mask = scores.chosen(sources)
    remap = {scores.sources.index(s): i for i, s in enumerate(sources)}
    which = np.array([remap[int(w)] for w in scores.which[mask]], dtype=scores.which.dtype)
    return ScoredWindows(
        scores.logits[mask],
        scores.labels[mask],
        which,
        scores.ends[mask],
        list(sources),
        scores.prior_offset,
    )


# =====================================================================================
# the report
# =====================================================================================


def _relative(path: Path, paths: ProjectPaths) -> str:
    try:
        return path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _delta_row(label: str, seed: int, d: DeltaInterval, decides: bool) -> tuple[str, ...]:
    return (
        label,
        str(seed),
        f"{d.first_auprc:.4f}",
        f"{d.second_auprc:.4f}",
        f"{d.delta:+.4f}",
        f"[{d.low:+.4f}, {d.high:+.4f}]",
        ("yes" if d.low > 0.0 else "no") if decides else "(reported)",
    )


def render_paired_report(
    config: PairedControlConfig,
    config_path: Path,
    gate: GateCheckConfig,
    seeds: list[int],
    pooled: list[str],
    results: list[DesignResult],
    passed: str | None,
    reproduction: dict[str, Any],
    seconds: float,
    paths: ProjectPaths,
) -> str:
    """Render the paired control's report.

    Args:
        config: The paired-control configuration.
        config_path: Where it was read from.
        gate: The gate configuration (bootstrap, held-out site).
        seeds: The random-init seeds.
        pooled: The pooled sources.
        results: Per design, in the order applied, its intervals.
        passed: The design in force, if any passed.
        reproduction: §a's re-run probe record.
        seconds: Wall clock of the invocation.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    headers = [
        "design",
        "random seed",
        "trained AUPRC",
        "random AUPRC",
        "Δ",
        "paired 95% interval",
        "lower bound above 0",
    ]
    deciding_rows, subsample_rows, held_rows = [], [], []
    verdict_rows, check_rows = [], []
    for r in results:
        label = f"{SECTION[r.design]} {r.design}"
        if r.deciding is not None and r.verdict is not None:
            deciding_rows += [
                _delta_row(label, s, d, True) for s, d in zip(seeds, r.deciding, strict=True)
            ]
            verdict_rows.append(
                (label, "PASS" if r.verdict.sensitive else "FAIL", r.verdict.reason)
            )
        else:
            verdict_rows.append((label, "not tested", f"{passed} is in force"))
        subsample_rows += [
            _delta_row(label, s, d, False) for s, d in zip(seeds, r.subsample, strict=True)
        ]
        held_rows += [
            _delta_row(label, s, d, False) for s, d in zip(seeds, r.held_out, strict=True)
        ]
        check_rows += [
            (label, name, f"{recorded:.4f}", f"{rescored:.4f}")
            for name, (recorded, rescored) in r.rescore_check.items()
        ]
    first_deciding = next((r.deciding[0] for r in results if r.deciding), None)
    first_sub = results[0].subsample[0]
    in_force = (
        f"**{SECTION[passed]} {passed} is the probe in force.**"
        if passed
        else "**No design passes. As registered, the work stops and is reported.**"
    )
    repro = (
        f"selected step {reproduction['selected'][0]}, validation AUPRC "
        f"{reproduction['selected'][1]:.4f}, pooled subsample AUPRC "
        f"{reproduction['pooled_auprc']:.4f}, largest test logit difference from the gate run "
        f"{reproduction['max_abs_logit_difference']:.2e}"
        if reproduction
        else "not run"
    )
    split_line = (
        f"pooled {' + '.join(pooled)} test at stride {config.stride}: "
        f"{first_deciding.windows:,} windows, {first_deciding.positives:,} positive, "
        f"{first_deciding.positive_blocks:,} of {first_deciding.blocks:,} blocks holding a positive"
        if first_deciding
        else "not scored"
    )
    return "".join(
        [
            "# Paired probe-sensitivity control\n\n",
            kv_table(
                {
                    "configuration": f"{_relative(config_path, paths)} "
                    f"(hash {config_hash(config)})",
                    "decision record": "docs/DECISIONS.md, ADR-0024 (registered in 79d4e97, "
                    "before this code)",
                    "order applied": ", ".join(SECTION[r.design] for r in results),
                    "deciding split": split_line,
                    "reported subsample": f"{first_sub.windows:,} windows, "
                    f"{first_sub.positives:,} positive, {first_sub.positive_blocks:,} of "
                    f"{first_sub.blocks:,} blocks holding a positive",
                    "bootstrap": f"paired, {gate.bootstrap.replicates:,} replicates, blocks of "
                    f"{gate.bootstrap.block_steps} steps within each shard, seed "
                    f"{gate.bootstrap.seed}, {gate.bootstrap.confidence:.0%} percentile",
                    "§a re-run probe": repro,
                    "wall clock": f"{seconds / 3600:.2f} h",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model paired-control",
                }
            ),
            section(
                "1. The criterion, as registered",
                table(["design", "verdict", "reason"], verdict_rows) + f"\n{in_force}\n",
            ),
            section(
                f"2. Deciding: paired Δ AUPRC at stride {config.stride}",
                table(headers, deciding_rows) if deciding_rows else "No design was scored.\n",
            ),
            section(
                "3. Reported: paired Δ AUPRC on ADR-0023's 24,000-window subsample",
                table(headers, subsample_rows),
            ),
            section(
                f"4. Reported: paired Δ AUPRC on {gate.held_out_source} (12,000 windows)",
                table(headers, held_rows),
            ),
            section(
                "5. Re-scoring check: pooled subsample AUPRC, recorded and re-scored",
                table(["design", "probe", "recorded", "re-scored"], check_rows)
                if check_rows
                else "No probe was re-scored.\n",
            ),
        ]
    )
