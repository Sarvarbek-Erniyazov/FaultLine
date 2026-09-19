"""F6-3's CPU half: bootstrap the scorings, apply ADR-0025 §5, and write the H1 report.

Nothing is scored here. The scorings are :mod:`faultline.evaluation.h1_scoring`'s, read from disk
(``checkpoints/h1_gate_v0_<hash>``). ``tel_only``'s final-step scores are F3's.

**The bootstrap is ADR-0024's**: two-day blocks within each shard, 10,000 replicates, seed
20260916, 95% percentile intervals, discard rule 1%. For each stratum of windows, every scorer's
AUPRC is computed on each replicate's rows, and the resulting vector is cached. Replicates are
drawn from the same blocks at the same seed for every scorer of a stratum, so they are the rows
``bootstrap_auprc`` and ``paired_bootstrap_deltas`` would draw. A single read's interval is the
percentiles of its vector. A paired Δ's interval is the percentiles of the difference of two
vectors, taken replicate by replicate. The two computations are equal, and
``tests/evaluation/test_h1_verdict.py`` checks it. Scoring each scorer once lets every
comparison below share its replicates.

**Rows, in the brief's order.**

- **B1**, the verdict row: Δ(joint − ``tel_only``) per seed, same-seed pairs, R0.
- **B2**: Δ(joint − iii) and Δ(iii − ``tel_only``).
- **B3**: the joint arm on R2, and Δ(R2 − R0).
- **B4**: the has-status and no-status strata of the R0 windows.
- **B5**: H2. Text withheld, which reads a different window and is not paired. The channel
  masks, paired against R0.
- **B6**: Δ(final − selected) for every joint and control (iii) probe. Reported only.

**Resume is per artefact.** Each replicate vector is cached as it completes, and each row's JSON
is written from the cached vectors.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from faultline.config import config_hash, load_config
from faultline.data.common.report import kv_table, table
from faultline.evaluation.axis_gate import ADR_0009_CAVEAT, IN_DISTRIBUTION
from faultline.evaluation.bootstrap import (
    AuprcInterval,
    BlockDraws,
    DeltaInterval,
    window_blocks,
)
from faultline.evaluation.care_attribution import CareAttributionConfig
from faultline.evaluation.gate_check import BootstrapConfig, GateCheckConfig
from faultline.evaluation.h1_controls import per_window
from faultline.evaluation.h1_scoring import MASK_CONFIG, ScoringLayout, scoring_layout
from faultline.evaluation.ladder import build_split
from faultline.evaluation.metrics import average_precision
from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.seed_replication import SeedReplicationConfig
from faultline.evaluation.variance_probe import open_probe_inputs
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.mixture import JointMixtureConfig

logger = get_logger(__name__)

#: ADR-0025's registration commit and the commit that recorded its hash.
ADR_0025_REGISTERED = "3e29202"
ADR_0025_HASH_COMMIT = "7a03201"
#: The ADR-0022 addendum outcome that put fixed-final-step selection in force.
FIXED_FINAL_OUTCOME = "267147d"

#: ADR-0025 §3's caveat, carried on every H1 row.
MESSAGE_VOLUME_CAVEAT = (
    "Message volume differs between train and test: Kelmarsh positives average 67.2 status "
    "tokens in train (stride 6) and 190.1 in test (stride 12); the joint probe learns on the "
    "train mix and is scored on the test mix."
)
#: ADR-0025 §6: what every row here is, and is not.
FORWARD_SAME_SITES = "forward-in-time, same sites"
#: The short form beside every row; the full texts head the report.
CAVEATS = "ADR-0009 · forward-in-time, same sites · message volume"


# =====================================================================================
# replicate vectors
# =====================================================================================


@dataclass(frozen=True)
class ReplicateJob:
    """One scorer's AUPRC on every replicate of one stratum.

    Attributes:
        cache: The ``.npz`` the vector is written to.
        scores: The scorings file.
        mask: Per window, whether it is in the stratum.
        bootstrap: ADR-0021's interval settings.
    """

    cache: Path
    scores: Path
    mask: np.ndarray
    bootstrap: BootstrapConfig


def replicate_auprcs(
    scores: np.ndarray, labels: np.ndarray, blocks: np.ndarray, replicates: int, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    """Per replicate, the AUPRC and the base rate; NaN for a replicate with no positive window.

    The draws are ``bootstrap_auprc``'s and ``paired_bootstrap_deltas``'s at the same seed.

    Args:
        scores: Per window, its score.
        labels: Per window, 1 if positive.
        blocks: Per window, its block id.
        replicates: Replicates to draw.
        seed: Seed of the resampling.

    Returns:
        The AUPRC and the positive share of each replicate.
    """
    truth = labels.astype(np.float64)
    values = np.full(replicates, math.nan)
    bases = np.full(replicates, math.nan)
    for i, rows in enumerate(BlockDraws(blocks).replicates(replicates, seed)):
        sample = truth[rows]
        if sample.sum() == 0:
            continue
        values[i] = average_precision(scores[rows], sample)
        bases[i] = float(sample.mean())
    return values, bases


def run_job(job: ReplicateJob) -> Path:
    """Compute one replicate vector and write it atomically."""
    scored = ScoredWindows.load(job.scores)
    mask = job.mask
    blocks = window_blocks(scored.ends[mask], scored.which[mask], job.bootstrap.block_steps)
    values, bases = replicate_auprcs(
        scored.logits[mask] + scored.prior_offset,
        scored.labels[mask],
        blocks,
        job.bootstrap.replicates,
        job.bootstrap.seed,
    )
    partial = job.cache.with_name(job.cache.stem + ".partial.npz")
    np.savez(partial, values=values, bases=bases)
    partial.replace(job.cache)
    return job.cache


def run_jobs(jobs: list[ReplicateJob]) -> list[Path]:
    """Every missing replicate vector, on worker processes; each cached as it completes."""
    if not jobs:
        return []
    workers = max(1, min(len(jobs), (os.cpu_count() or 2) - 2))
    logger.info("bootstrapping %d replicate vectors on %d worker processes", len(jobs), workers)
    written: list[Path] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_job, job) for job in jobs]
        for future in as_completed(futures):
            written.append(future.result())
            logger.info("replicates written: %s (%d/%d)", written[-1].name, len(written), len(jobs))
    return written


# =====================================================================================
# intervals from vectors
# =====================================================================================


@dataclass(frozen=True)
class Stratum:
    """The windows one set of rows is read on.

    Attributes:
        name: ``pooled``, ``has_status`` or ``no_status``.
        mask: Per window, whether it is in the stratum.
        windows: Windows in it.
        positives: Positive windows.
        blocks: Occupied blocks.
        positive_blocks: Blocks holding a positive window.
    """

    name: str
    mask: np.ndarray
    windows: int
    positives: int
    blocks: int
    positive_blocks: int


def stratum(name: str, mask: np.ndarray, reference: ScoredWindows, block_steps: int) -> Stratum:
    """Describe one stratum of the reference scoring's windows."""
    blocks = window_blocks(reference.ends[mask], reference.which[mask], block_steps)
    labels = reference.labels[mask] > 0.5
    return Stratum(
        name=name,
        mask=mask,
        windows=int(mask.sum()),
        positives=int(labels.sum()),
        blocks=int(np.unique(blocks).size),
        positive_blocks=int(np.unique(blocks[labels]).size),
    )


def _quantiles(values: np.ndarray, confidence: float) -> tuple[float, float]:
    kept = values[~np.isnan(values)]
    if not kept.size:
        return math.nan, math.nan
    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(kept, [tail, 1.0 - tail])
    return float(low), float(high)


def full_auprc(scores: Path, mask: np.ndarray) -> tuple[float, float]:
    """A scorer's AUPRC and base rate on the stratum's windows as scored."""
    scored = ScoredWindows.load(scores)
    truth = scored.labels[mask].astype(np.float64)
    return (
        average_precision(scored.logits[mask] + scored.prior_offset, truth),
        float(truth.mean()),
    )


def single_interval(
    vector: Path, scores: Path, where: Stratum, bootstrap: BootstrapConfig
) -> AuprcInterval:
    """``bootstrap_auprc``'s interval, read from a cached replicate vector."""
    with np.load(vector) as data:
        values, bases = data["values"], data["bases"]
    auprc, base_rate = full_auprc(scores, where.mask)
    low, high = _quantiles(values, bootstrap.confidence)
    lift_low, lift_high = _quantiles(values - bases, bootstrap.confidence)
    return AuprcInterval(
        unit="block",
        auprc=auprc,
        low=low,
        high=high,
        lift_low=lift_low,
        lift_high=lift_high,
        base_rate=base_rate,
        windows=where.windows,
        positives=where.positives,
        blocks=where.blocks,
        positive_blocks=where.positive_blocks,
        replicates=bootstrap.replicates,
        discarded=int(np.isnan(values).sum()),
        confidence=bootstrap.confidence,
        seed=bootstrap.seed,
    )


def delta_interval(
    first: tuple[Path, Path],
    second: tuple[Path, Path],
    where: Stratum,
    bootstrap: BootstrapConfig,
) -> DeltaInterval:
    """``paired_bootstrap_deltas``'s interval on AUPRC(first) − AUPRC(second), from two vectors.

    Args:
        first: The first scorer's replicate vector and scores file.
        second: The second scorer's.
        where: The stratum both were read on.
        bootstrap: The interval settings.

    Returns:
        The paired interval.

    Raises:
        ValueError: If the two vectors discard different replicates, which would mean they were
            not drawn on the same rows.
    """
    with np.load(first[0]) as a, np.load(second[0]) as b:
        va, vb = a["values"], b["values"]
    if not np.array_equal(np.isnan(va), np.isnan(vb)):
        raise ValueError(f"{first[0].name} and {second[0].name} were not drawn on the same rows")
    first_auprc, _ = full_auprc(first[1], where.mask)
    second_auprc, _ = full_auprc(second[1], where.mask)
    low, high = _quantiles(va - vb, bootstrap.confidence)
    return DeltaInterval(
        unit="block",
        delta=first_auprc - second_auprc,
        low=low,
        high=high,
        first_auprc=first_auprc,
        second_auprc=second_auprc,
        windows=where.windows,
        positives=where.positives,
        blocks=where.blocks,
        positive_blocks=where.positive_blocks,
        replicates=bootstrap.replicates,
        discarded=int(np.isnan(va).sum()),
        confidence=bootstrap.confidence,
        seed=bootstrap.seed,
    )


# =====================================================================================
# the rule
# =====================================================================================


@dataclass(frozen=True)
class H1Verdict:
    """ADR-0025 §5, applied to B1.

    Attributes:
        verdict: ``SUPPORTED``, ``REFUTED``, ``INCONCLUSIVE``, or ``SUPPORTED_AND_REFUTED``,
            which the rule names only as "reported as measured".
        median_delta: The median of the three seeds' full-sample Δ.
        lower_bounds_above_zero: Per seed, whether its trusted lower bound exceeds zero.
        upper_bounds_below: Per seed, whether its trusted upper bound is below the effect.
        trusted: Per seed, whether its discard share is within the rule's.
        reason: One sentence saying why.
    """

    verdict: str
    median_delta: float
    lower_bounds_above_zero: dict[int, bool]
    upper_bounds_below: dict[int, bool]
    trusted: dict[int, bool]
    reason: str


def decide_h1(
    deltas: dict[int, DeltaInterval],
    smallest_effect: float,
    lower_above: float,
    median_above: float,
    upper_below: float,
    max_discarded_share: float,
) -> H1Verdict:
    """Apply ADR-0025 §5 verbatim.

    SUPPORTED if every paired lower bound exceeds ``lower_above`` and the median Δ exceeds
    ``median_above``. REFUTED if every paired upper bound is below ``upper_below``. Otherwise
    INCONCLUSIVE at this budget. A comparison discarding more than ``max_discarded_share`` of
    its replicates counts toward neither. If both clauses hold, the outcome is one the rule does
    not name, and it is reported as measured.

    Args:
        deltas: Per seed, the paired Δ(joint − ``tel_only``).
        smallest_effect: The smallest effect of interest, for the record.
        lower_above: The SUPPORTED lower-bound line.
        median_above: The SUPPORTED median line.
        upper_below: The REFUTED upper-bound line.
        max_discarded_share: Above this share of discarded replicates, a seed counts toward neither.

    Returns:
        The verdict.
    """
    del smallest_effect
    trusted = {s: d.discarded_share <= max_discarded_share for s, d in deltas.items()}
    lower = {s: trusted[s] and d.low > lower_above for s, d in deltas.items()}
    upper = {s: trusted[s] and d.high < upper_below for s, d in deltas.items()}
    median = float(statistics.median(d.delta for d in deltas.values()))
    supported = all(lower.values()) and median > median_above
    refuted = all(upper.values())
    if supported and refuted:
        verdict = "SUPPORTED_AND_REFUTED"
        reason = (
            "both registered clauses hold; the rule names no such outcome, reported as measured"
        )
    elif supported:
        verdict = "SUPPORTED"
        reason = (
            f"every paired lower bound exceeds {lower_above:g} and the median Δ {median:+.4f} "
            f"exceeds {median_above:g}"
        )
    elif refuted:
        verdict = "REFUTED"
        reason = f"every paired upper bound is below {upper_below:g}"
    else:
        missed = [s for s, ok in lower.items() if not ok]
        not_below = [s for s, ok in upper.items() if not ok]
        parts = []
        if missed:
            parts.append(f"seed(s) {missed} have a lower bound not above {lower_above:g}")
        if median <= median_above:
            parts.append(f"the median Δ {median:+.4f} does not exceed {median_above:g}")
        parts.append(f"seed(s) {not_below} have an upper bound not below {upper_below:g}")
        untrusted = [s for s, ok in trusted.items() if not ok]
        if untrusted:
            parts.append(f"seed(s) {untrusted} discard more than {max_discarded_share:.0%}")
        verdict = "INCONCLUSIVE"
        reason = "; ".join(parts)
    return H1Verdict(
        verdict=verdict,
        median_delta=median,
        lower_bounds_above_zero=lower,
        upper_bounds_below=upper,
        trusted=trusted,
        reason=reason,
    )


# =====================================================================================
# the run
# =====================================================================================


def scorer_files(layout: ScoringLayout) -> dict[str, Path]:
    """Every scorer read, by name: this step's 27 scorings and ``tel_only``'s F3 scores."""
    files: dict[str, Path] = {}
    short = {
        ("S1", False): "joint_R0",
        ("S2", True): "iii_R0",
        ("S3", False): "joint_R2",
        ("S4", False): "joint_m1",
        ("S6", False): "joint_selected",
        ("S6", True): "iii_selected",
    }
    for scoring in layout.plan:
        if scoring.stage == "S5":
            files[f"joint_mask_{scoring.farm}_{scoring.seed}"] = layout.scores(scoring)
        else:
            files[f"{short[scoring.stage, scoring.control]}_{scoring.seed}"] = layout.scores(
                scoring
            )
    for seed in layout.gate.comparison.seeds:
        files[f"tel_only_{seed}"] = layout.tel_only_scores(seed)
    return files


#: The scorers read within the has-status and no-status strata (B4).
STRATA_SCORERS = ("joint_R0", "tel_only", "iii_R0")


def status_strata(paths: ProjectPaths, layout: ScoringLayout) -> np.ndarray:
    """Per scored window, whether its R0 window (ADR-0025 §2 framing) holds a status token."""
    runner = layout.arms.runner
    gate_run = load_config(paths.repo_root / runner.gate_config, GateCheckConfig)
    inputs = open_probe_inputs(
        paths,
        runner.mixture_config,
        runner.ladder_config,
        runner.arm,
        runner.rung,
        runner.optimiser.selection_windows,
        gate_run.held_out_source,
        "cpu",
        window_rule=runner.probe.window_rule,
        status_rows=runner.probe.status_rows,
    )
    evaluation = inputs.ladder.evaluation
    m1 = build_split(
        inputs.telemetry,
        "test",
        None,
        layout.gate.stride,
        evaluation.seed,
        evaluation.batch_windows,
        layout.gate.label,
        sources=inputs.mixture.training_sources,
    )
    has: np.ndarray = per_window(inputs.frame(m1), "status_tokens") > 0
    return has


def _json(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def run_h1_verdict(paths: ProjectPaths, gate_path: Path) -> tuple[Path, Path]:
    """Bootstrap every F6-3 row, apply ADR-0025 §5 on B1, and write the report.

    Args:
        paths: Resolved project paths.
        gate_path: ``configs/eval/h1_gate_v0.yaml``.

    Returns:
        The report and its JSON record.

    Raises:
        FileNotFoundError: If a scoring or the validation-loss row is missing.
        ValueError: If a scoring does not cover F3's windows.
    """
    started = time.perf_counter()
    layout = scoring_layout(paths, gate_path)
    gate, bootstrap = layout.gate, layout.gate.bootstrap
    seeds = gate.comparison.seeds
    out = layout.out_dir
    files = scorer_files(layout)
    missing = [p for p in [*files.values(), layout.validation_file] if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"not scored yet: {[p.name for p in missing]}")
    reference = ScoredWindows.load(files[f"tel_only_{seeds[0]}"])
    for name, path in files.items():
        if not ScoredWindows.load(path).same_windows(reference):
            raise ValueError(f"{name} ({path.name}) does not cover F3's windows")
    if (reference.labels.size, int(reference.labels.sum())) != (gate.windows, gate.positives):
        raise ValueError("the scored windows are not the registered 137,025 / 5,312")

    # -- strata ---------------------------------------------------------------------------
    strata_file = out / "status_strata.npz"
    if not strata_file.exists():
        logger.info("framing the R0 test windows on the CPU for the status strata")
        has = status_strata(paths, layout)
        partial = out / "status_strata.partial.npz"
        np.savez(partial, has_status=has)
        partial.replace(strata_file)
    with np.load(strata_file) as data:
        has_status = data["has_status"].astype(bool)
    if has_status.size != reference.labels.size:
        raise ValueError("the status strata do not cover the scored windows")
    strata = {
        name: stratum(name, mask, reference, bootstrap.block_steps)
        for name, mask in (
            ("pooled", np.ones_like(has_status)),
            ("has_status", has_status),
            ("no_status", ~has_status),
        )
    }

    # -- replicate vectors ------------------------------------------------------------------
    rep_dir = out / "replicates"
    rep_dir.mkdir(exist_ok=True)

    def vector(where: str, scorer: str) -> Path:
        return rep_dir / f"{where}__{scorer}.npz"

    wanted = [("pooled", name) for name in files]
    wanted += [
        (where, f"{prefix}_{seed}")
        for where in ("has_status", "no_status")
        for prefix in STRATA_SCORERS
        for seed in seeds
    ]
    jobs = [
        ReplicateJob(vector(w, s), files[s], strata[w].mask, bootstrap)
        for w, s in wanted
        if not vector(w, s).exists()
    ]
    tick = time.perf_counter()
    computed = run_jobs(jobs)
    bootstrap_seconds = time.perf_counter() - tick
    vectors_resumed = len(wanted) - len(computed)

    def single(scorer: str, where: str = "pooled") -> dict[str, Any]:
        return asdict(
            single_interval(vector(where, scorer), files[scorer], strata[where], bootstrap)
        )

    def paired(first: str, second: str, where: str = "pooled") -> DeltaInterval:
        return delta_interval(
            (vector(where, first), files[first]),
            (vector(where, second), files[second]),
            strata[where],
            bootstrap,
        )

    rows_dir = out / "rows"
    rows_dir.mkdir(exist_ok=True)

    def row(name: str, build: Any) -> dict[str, Any]:
        path = rows_dir / f"{name}.json"
        if not path.exists():
            payload = build()
            partial = path.with_name(path.name + ".partial")
            partial.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
            partial.replace(path)
        return _json(path)

    # -- B1 and the verdict -------------------------------------------------------------------
    b1 = {
        seed: row(
            f"B1_seed{seed}",
            lambda s=seed: {
                "joint": single(f"joint_R0_{s}"),
                "tel_only": single(f"tel_only_{s}"),
                "delta": asdict(paired(f"joint_R0_{s}", f"tel_only_{s}")),
            },
        )
        for seed in seeds
    }
    b1_deltas = {s: DeltaInterval(**b1[s]["delta"]) for s in seeds}
    rule = gate.rule
    verdict = decide_h1(
        b1_deltas,
        rule.smallest_effect,
        rule.supported_lower_bound_above,
        rule.supported_median_above,
        rule.refuted_upper_bound_below,
        bootstrap.max_discarded_share,
    )

    # -- B2 to B6 ------------------------------------------------------------------------------
    b2 = {
        seed: row(
            f"B2_seed{seed}",
            lambda s=seed: {
                "iii": single(f"iii_R0_{s}"),
                "joint_minus_iii": asdict(paired(f"joint_R0_{s}", f"iii_R0_{s}")),
                "iii_minus_tel_only": asdict(paired(f"iii_R0_{s}", f"tel_only_{s}")),
            },
        )
        for seed in seeds
    }
    b3 = {
        seed: row(
            f"B3_seed{seed}",
            lambda s=seed: {
                "joint_r2": single(f"joint_R2_{s}"),
                "r2_minus_r0": asdict(paired(f"joint_R2_{s}", f"joint_R0_{s}")),
            },
        )
        for seed in seeds
    }
    b4 = {
        seed: row(
            f"B4_seed{seed}",
            lambda s=seed: {
                where: {
                    **{p: single(f"{p}_{s}", where) for p in STRATA_SCORERS},
                    "joint_minus_tel_only": asdict(paired(f"joint_R0_{s}", f"tel_only_{s}", where)),
                }
                for where in ("has_status", "no_status")
            },
        )
        for seed in seeds
    }
    farms = list(layout.patterns)
    b5 = {
        seed: row(
            f"B5_seed{seed}",
            lambda s=seed: {
                "text_withheld": single(f"joint_m1_{s}"),
                "masks": {
                    f: {
                        "masked": single(f"joint_mask_{f}_{s}"),
                        "masked_minus_r0": asdict(paired(f"joint_mask_{f}_{s}", f"joint_R0_{s}")),
                    }
                    for f in farms
                },
            },
        )
        for seed in seeds
    }
    b6 = {
        f"{arm}_{seed}": row(
            f"B6_{arm}_seed{seed}",
            lambda a=arm, s=seed: {
                "selected": single(f"{a}_selected_{s}"),
                "final_minus_selected": asdict(paired(f"{a}_R0_{s}", f"{a}_selected_{s}")),
            },
        )
        for arm in ("joint", "iii")
        for seed in seeds
    }
    records = {
        f"{arm}_{seed}": _json(layout.arms.probe_record(seed, arm == "iii"))
        for arm in ("joint", "iii")
        for seed in seeds
    }

    # -- beside the rows ------------------------------------------------------------------------
    validation = _json(layout.validation_file)
    f3 = load_config(paths.repo_root / gate.reference_config, SeedReplicationConfig)
    gate_run = load_config(paths.repo_root / f3.gate_config, GateCheckConfig)
    tel_only_loss: dict[int, float] = {}
    for seed in seeds:
        if seed == gate_run.seed:
            gate_report = sorted(paths.data_reports_dir.glob("gate_check_v0_*.json"))[-1]
            tel_only_loss[seed] = float(_json(gate_report)["pretraining"]["lm_history"][-1][1])
        else:
            lm = _json(layout.f3_dir / f"{gate_run.rung}_tel_only_seed{seed}_lm.json")
            tel_only_loss[seed] = float(lm["history"][-1][1])
    care_file = sorted(paths.data_reports_dir.glob("care_attribution_v0_*.json"))[-1]
    f6_0a = {
        f"{r['farm']}_{r['seed']}": {
            "auprc": r["interval"]["auprc"],
            "delta": r["delta"]["delta"],
            "low": r["delta"]["low"],
            "high": r["delta"]["high"],
        }
        for r in _json(care_file)["masked"]
    }
    sidecars = {s.name: _json(layout.scores(s).with_suffix(".timing.json")) for s in layout.plan}
    status = _json(out / "h1_scoring_status.json")
    checks = _json(out / "selection_check.json")
    computed_names = set(status["computed_this_invocation"])
    gpu = {
        "scorings_computed": len(computed_names),
        "scorings_resumed": len(layout.plan) - len(computed_names),
        "scoring_seconds_computed": sum(
            float(v["seconds"]) for k, v in sidecars.items() if k in computed_names
        ),
        "scoring_seconds_resumed": sum(
            float(v["seconds"]) for k, v in sidecars.items() if k not in computed_names
        ),
        "selection_check_seconds": sum(float(v["seconds"]) for v in checks.values()),
        "validation_loss_seconds": float(validation["seconds"]),
        "first_started_utc": min(v["started_utc"] for v in sidecars.values()),
        "last_finished_utc": max(v["finished_utc"] for v in sidecars.values()),
        "git_sha": sorted({v["git_sha"] for v in sidecars.values()}),
        "tree_dirty": sorted({v["tree_dirty"] for v in sidecars.values()}),
        "h1_scoring_sha256": sorted({v["h1_scoring_sha256"] for v in sidecars.values()}),
        "masked_tokens": {
            k: [v["masked_tokens"], v["expected_masked_tokens"]]
            for k, v in sidecars.items()
            if "masked_tokens" in v
        },
    }

    mixture = load_config(paths.repo_root / layout.arms.runner.mixture_config, JointMixtureConfig)
    masks = load_config(paths.repo_root / MASK_CONFIG, CareAttributionConfig)
    hashes = {
        "configs/eval/h1_gate_v0.yaml": config_hash(gate),
        "configs/train/h1_arms_v0.yaml": config_hash(layout.arms.runner),
        "configs/train/joint_v1.yaml": config_hash(mixture),
        "configs/train/seed_replication_v0.yaml": config_hash(f3),
        MASK_CONFIG: config_hash(masks),
    }
    payload: dict[str, Any] = {
        "config_hashes": hashes,
        "adr_0025": {"registered": ADR_0025_REGISTERED, "hash_commit": ADR_0025_HASH_COMMIT},
        "checkpoint_rule": gate.comparison.checkpoint,
        "strata": {
            k: {
                "windows": v.windows,
                "positives": v.positives,
                "blocks": v.blocks,
                "positive_blocks": v.positive_blocks,
            }
            for k, v in strata.items()
        },
        "B1": {str(s): v for s, v in b1.items()},
        "verdict": asdict(verdict),
        "B2": {str(s): v for s, v in b2.items()},
        "B3": {str(s): v for s, v in b3.items()},
        "B4": {str(s): v for s, v in b4.items()},
        "B5": {str(s): v for s, v in b5.items()},
        "B6": b6,
        "probe_records": {
            k: {"selected": v["selected"], "final": v["final"]} for k, v in records.items()
        },
        "f6_0a_tel_only_masked": f6_0a,
        "validation_loss": {
            str(s): {**validation["rows"][str(s)], "tel_only_tel_val": tel_only_loss[s]}
            for s in seeds
        },
        "selection_check": checks,
        "gpu": gpu,
        "cpu": {
            "replicate_vectors_computed": len(computed),
            "replicate_vectors_resumed": vectors_resumed,
            "bootstrap_seconds_this_invocation": bootstrap_seconds,
            "seconds_this_invocation": time.perf_counter() - started,
        },
        "caveats": {
            "adr_0009": ADR_0009_CAVEAT,
            "in_distribution": IN_DISTRIBUTION,
            "forward_same_sites": FORWARD_SAME_SITES,
            "message_volume": MESSAGE_VOLUME_CAVEAT,
        },
        "generated_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "git_sha": git_sha(paths.repo_root),
    }
    stem = f"h1_gate_v{gate.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    record = paths.data_reports_dir / f"{stem}.json"
    report.write_text(render_report(payload, seeds, farms), encoding="utf-8", newline="\n")
    record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("H1 verdict: %s (%s)", verdict.verdict, verdict.reason)
    logger.info("wrote %s and %s", report, record)
    return report, record


# =====================================================================================
# the report
# =====================================================================================


def _iv(value: dict[str, Any]) -> str:
    return f"{value['auprc']:.4f} [{value['low']:.4f}, {value['high']:.4f}]"


def _dv(value: dict[str, Any]) -> str:
    return f"{value['delta']:+.4f} [{value['low']:+.4f}, {value['high']:+.4f}]"


def _disc(value: dict[str, Any]) -> str:
    return f"{value['discarded'] / value['replicates']:.2%}"


def render_report(payload: dict[str, Any], seeds: list[int], farms: list[str]) -> str:
    """The H1 report: header, B1 to B6 in order, then the verdict."""
    gpu, cpu, verdict = payload["gpu"], payload["cpu"], payload["verdict"]
    header = [
        *[(f"configuration {k}", f"hash {v}") for k, v in payload["config_hashes"].items()],
        ("decision record", "docs/DECISIONS.md, ADR-0025 §5 (rule), §3 (R2, strata), §6 (H2)"),
        ("ADR-0025 registered", payload["adr_0025"]["registered"]),
        ("ADR-0025 hash recorded", payload["adr_0025"]["hash_commit"]),
        (
            "checkpoint rule",
            f"`{payload['checkpoint_rule']}`: every probe is read at its last step (ADR-0022 "
            f"addendum outcome {FIXED_FINAL_OUTCOME}); selected-step reads are B6 only",
        ),
        (
            "GPU wall clock, computed",
            f"{gpu['scoring_seconds_computed'] / 3600:.2f} h over {gpu['scorings_computed']} "
            f"scorings, plus {gpu['selection_check_seconds'] / 60:.1f} min selection re-checks "
            f"and {gpu['validation_loss_seconds'] / 60:.1f} min validation loss; "
            f"{gpu['first_started_utc']} to {gpu['last_finished_utc']} UTC",
        ),
        (
            "GPU wall clock, resumed",
            f"{gpu['scoring_seconds_resumed'] / 3600:.2f} h over "
            f"{gpu['scorings_resumed']} scorings",
        ),
        (
            "scoring provenance",
            f"git {', '.join(gpu['git_sha'])}; tree dirty {gpu['tree_dirty']}; h1_scoring.py "
            f"sha256 {', '.join(gpu['h1_scoring_sha256'])}",
        ),
        (
            "CPU bootstrap",
            f"{cpu['replicate_vectors_computed']} replicate vectors computed, "
            f"{cpu['replicate_vectors_resumed']} resumed; "
            f"{cpu['seconds_this_invocation'] / 60:.1f} min this invocation",
        ),
        ("generated (UTC)", payload["generated_utc"]),
        ("git_sha", payload["git_sha"]),
        ("generated by", "faultline model h1-gate"),
    ]
    pooled = payload["strata"]["pooled"]
    lines = [
        "# H1 gate: the joint arm against tel_only (ADR-0025, F6-3)",
        "",
        kv_table(dict(header)),
        "",
        "## " + "Caveats carried on every row",
        "",
        f"The column **caveats** on every row stands for these three, in full: (1) ADR-0009: "
        f"{payload['caveats']['adr_0009']} (2) {payload['caveats']['in_distribution']} Every "
        f"row is {FORWARD_SAME_SITES}; none is a site-shift result. (3) "
        f"{payload['caveats']['message_volume']}",
        "",
        f"Every row reads the pooled Kelmarsh + Penmanshiel stride-12 forward-in-time test split: "
        f"{pooled['windows']:,} windows, {pooled['positives']:,} positive, {pooled['blocks']:,} "
        f"two-day blocks ({pooled['positive_blocks']:,} with a positive). Intervals are ADR-0024's "
        "paired block bootstrap (10,000 replicates, seed 20260916, 95%); every Δ is paired on "
        "identical (turbine, year, end step) rows and identical replicates.",
        "",
    ]

    b1 = payload["B1"]
    lines += [
        "## " + "B1 -- H1: Δ(joint − tel_only), same seed, R0, final step (the verdict row)",
        "",
        table(
            [
                "seed",
                "joint AUPRC [95%]",
                "tel_only AUPRC [95%]",
                "paired Δ [95%]",
                "lower > 0",
                "upper < 0.005",
                "discarded",
                "caveats",
            ],
            [
                [
                    str(s),
                    _iv(b1[str(s)]["joint"]),
                    _iv(b1[str(s)]["tel_only"]),
                    _dv(b1[str(s)]["delta"]),
                    "yes" if verdict["lower_bounds_above_zero"][s] else "no",
                    "yes" if verdict["upper_bounds_below"][s] else "no",
                    _disc(b1[str(s)]["delta"]),
                    CAVEATS,
                ]
                for s in seeds
            ],
        ),
        "",
        f"Median of the three point Δ: **{verdict['median_delta']:+.4f}**.",
        "",
    ]

    b2 = payload["B2"]
    lines += [
        "## " + "B2 -- decomposition through control (iii)",
        "",
        "Control (iii) is `tel_only`'s frozen backbone with a new §a probe on the joint windows. "
        "Δ(joint − iii) is joint pretraining at identical input; Δ(iii − tel_only) is the input "
        "change (truncation plus text presence) on a backbone that never read text.",
        "",
        table(
            [
                "seed",
                "iii AUPRC [95%]",
                "Δ(joint − iii) [95%]",
                "Δ(iii − tel_only) [95%]",
                "caveats",
            ],
            [
                [
                    str(s),
                    _iv(b2[str(s)]["iii"]),
                    _dv(b2[str(s)]["joint_minus_iii"]),
                    _dv(b2[str(s)]["iii_minus_tel_only"]),
                    CAVEATS,
                ]
                for s in seeds
            ],
        ),
        "",
    ]

    b3 = payload["B3"]
    lines += [
        "## " + "B3 -- R2: every provider Stop row removed, R0 probe re-scored",
        "",
        table(
            ["seed", "joint R0 AUPRC", "joint R2 AUPRC [95%]", "Δ(R2 − R0) [95%]", "caveats"],
            [
                [
                    str(s),
                    f"{b1[str(s)]['joint']['auprc']:.4f}",
                    _iv(b3[str(s)]["joint_r2"]),
                    _dv(b3[str(s)]["r2_minus_r0"]),
                    CAVEATS,
                ]
                for s in seeds
            ],
        ),
        "",
    ]

    b4 = payload["B4"]
    strata = payload["strata"]
    rows4 = []
    for s in seeds:
        for where in ("has_status", "no_status"):
            cell = b4[str(s)][where]
            rows4.append(
                [
                    str(s),
                    where.replace("_", "-"),
                    f"{strata[where]['windows']:,} / {strata[where]['positives']:,}",
                    f"{cell['joint_R0']['base_rate']:.4f}",
                    _iv(cell["joint_R0"]),
                    _iv(cell["tel_only"]),
                    _iv(cell["iii_R0"]),
                    _dv(cell["joint_minus_tel_only"]),
                    CAVEATS,
                ]
            )
    lines += [
        "## " + "B4 -- strata of the R0 windows: has status / no status",
        "",
        "A window is has-status if its ADR-0025 §2 window holds at least one status token. "
        "Blocks are re-formed within each stratum.",
        "",
        table(
            [
                "seed",
                "stratum",
                "windows / positives",
                "base rate",
                "joint [95%]",
                "tel_only [95%]",
                "iii [95%]",
                "Δ(joint − tel_only) [95%]",
                "caveats",
            ],
            rows4,
        ),
        "",
    ]

    b5 = payload["B5"]
    f60 = payload["f6_0a_tel_only_masked"]
    rows5 = []
    for s in seeds:
        rows5.append(
            [
                str(s),
                "text withheld (M1 1,872-token windows)",
                _iv(b5[str(s)]["text_withheld"]),
                "not paired: different window",
                "--",
                CAVEATS,
            ]
        )
        for f in farms:
            cell = b5[str(s)]["masks"][f]
            ref = f60.get(f"{f}_{s}")
            beside = (
                f"{ref['auprc']:.4f}; Δ {ref['delta']:+.4f} [{ref['low']:+.4f}, {ref['high']:+.4f}]"
                if ref
                else "--"
            )
            rows5.append(
                [
                    str(s),
                    f"{f} mask on R0 windows, text present",
                    _iv(cell["masked"]),
                    _dv(cell["masked_minus_r0"]),
                    beside,
                    CAVEATS,
                ]
            )
    lines += [
        "## " + "B5 -- H2, reported only: text withheld and channel loss",
        "",
        "The text-withheld read is the joint backbone and its final R0 probe on `tel_only`'s "
        "1,872-token M1 windows (144 full steps, no messages). **It is a different window from "
        "the R0 read and from the masked reads, and is not comparable with them**; no paired Δ is "
        "given. Each mask imposes one F6-0a CARE farm's absent core channels as `<nan>` on the "
        "telemetry slots of the R0 windows, text left in place, and is paired against the seed's "
        "R0 joint read. Beside it: F6-0a's `tel_only` masked read on its own 1,872-token windows "
        "(AUPRC; Δ masked − unmasked). Coverage and selective risk are deferred (ADR-0025 §6).",
        "",
        table(
            [
                "seed",
                "condition",
                "AUPRC [95%]",
                "paired Δ vs R0 joint [95%]",
                "F6-0a tel_only masked (AUPRC; Δ)",
                "caveats",
            ],
            rows5,
        ),
        "",
    ]

    b6, recs = payload["B6"], payload["probe_records"]
    rows6 = []
    for arm in ("joint", "iii"):
        for s in seeds:
            key = f"{arm}_{s}"
            cell, rec = b6[key], recs[key]
            final = b1[str(s)]["joint"] if arm == "joint" else b2[str(s)]["iii"]
            rows6.append(
                [
                    "joint" if arm == "joint" else "control (iii)",
                    str(s),
                    f"{rec['selected'][0]} ({rec['selected'][1]:.4f})",
                    f"{rec['final'][0]} ({rec['final'][1]:.4f})",
                    _iv(cell["selected"]),
                    f"{final['auprc']:.4f}",
                    _dv(cell["final_minus_selected"]),
                    CAVEATS,
                ]
            )
    lines += [
        "## " + "B6 -- selected-step against final-step probes, reported only",
        "",
        "The fixed-final rule is in force; nothing here changes which probe is read.",
        "",
        table(
            [
                "probe",
                "seed",
                "selected step (validation AUPRC)",
                "final step (validation AUPRC)",
                "selected, test [95%]",
                "final, test",
                "Δ(final − selected) [95%]",
                "caveats",
            ],
            rows6,
        ),
        "",
    ]

    val = payload["validation_loss"]
    lines += [
        "## " + "Validation next-token loss, for the record",
        "",
        "Each backbone at its final pretraining step. `tel+status`: 500 windows per training "
        "site drawn from the `tel_status_normalized` validation shards as the `tel` selection "
        "windows are drawn; `tel`: pretraining's own selection windows.",
        "",
        table(
            [
                "seed",
                "joint on tel+status val",
                "joint on tel val",
                "tel_only on tel val",
            ],
            [
                [
                    str(s),
                    f"{val[str(s)]['tel_status_val']:.3f}",
                    f"{val[str(s)]['tel_val']:.3f}",
                    f"{val[str(s)]['tel_only_tel_val']:.3f}",
                ]
                for s in seeds
            ],
        ),
        "",
    ]

    lines += [
        "## " + "Verdict -- ADR-0025 §5, on B1",
        "",
        f"> **H1: {verdict['verdict']}.** {verdict['reason']}.",
        "",
        f"Median Δ {verdict['median_delta']:+.4f}; paired intervals: "
        + "; ".join(f"seed {s} {_dv(b1[str(s)]['delta'])}" for s in seeds)
        + ". A comparison discarding more than 1% of its replicates counts toward neither "
        + (
            "clause; none did."
            if all(verdict["trusted"].values())
            else "clause; untrusted: seeds "
            + str([s for s, ok in verdict["trusted"].items() if not ok])
            + "."
        )
        + " Nothing in B2-B6 changes the verdict.",
        "",
    ]
    return "\n".join(lines)
