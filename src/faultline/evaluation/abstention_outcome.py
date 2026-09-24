"""F9-3 (ADR-0028 §1-§4): Part A, Gate A, Gate B, the H2 verdict and the severity ladder.

CPU only, on saved scores. The operating point is **read** from the write-once record that
:func:`faultline.evaluation.abstention_verdict.operating_points` fitted on validation and that was
committed alone before this module opened a test file; nothing here fits τ, κ or Platt.

**Scenarios.** Each is one :class:`faultline.evaluation.risk_coverage.StatisticsJob` over the
137,025 clean test rows, all drawn by one ``BlockDraws`` at the registered seed, so any two pair
replicate by replicate:

- ``clean_<arm>``: the arm's prior-corrected ensemble at its (τ, κ), with the random-ordering
  reference (Part A's ECE (i), risk–coverage, AURC, Gate A);
- ``platt_<arm>``: the same ensemble through its validation-fitted Platt map (Part A's ECE (ii));
- ``joint_d_k<k>``: ``joint`` (d) with k core channels masked, at ``joint`` (d)'s clean (τ, κ)
  (Gate B, H2, the ladder).

**The claim table.** Every number the ADR-0028 outcome cites is recomputed a second way — point
values by a separate implementation on the scores, intervals by re-reading the replicate vectors —
and the report prints whether the two agree.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from faultline.config import config_hash, load_config
from faultline.data.common.report import kv_table, table
from faultline.evaluation.abstention_gate import AbstentionConfig
from faultline.evaluation.abstention_verdict import (
    CAVEAT_TEXT,
    arm_label,
    assert_paired,
    decide_gate_a,
    decide_gate_b,
    decide_h2,
    load_ensemble,
    operating_point_record,
    operating_points,
    out_dir,
    platt_maps,
    registered_test_files,
)
from faultline.evaluation.h1_scoring import write_json
from faultline.evaluation.readout_verdict import MAX_BOOTSTRAP_WORKERS
from faultline.evaluation.risk_coverage import (
    TEST,
    Ensemble,
    Interval,
    OperatingPoint,
    StatisticsJob,
    admission_order,
    apply_platt,
    equal_mass_ece,
    interval,
    misclassified,
    paired_interval,
    percentile_interval,
    permutation_seeds,
    risk_coverage_curve,
    run_capped,
    run_statistics_job,
    statistics,
)
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

#: The coverages the risk–coverage curves are tabulated at (the full curve is AURC's).
CURVE_COVERAGES = tuple(round(0.05 * i, 2) for i in range(1, 21))

#: ADR-0028 §4's caveats, short enough for a table column; the full text is under each table.
CAVEAT_SHORT = (
    "ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · "
    "operating point at validation base rate 0.0211 vs test 0.0388"
)

#: Two implementations of one point value agree when they differ by no more than this.
AGREEMENT = 1e-9

#: The step-0 stop and its resolution, recorded in the report (one line).
STEP_0_LINE = (
    "Step 0 stopped F9-3 once: the brief assumed `tel_only` (a)'s test scores were on the M1 "
    "1,872-token windows; they are on R0 (ADR-0028 §1, control iii), as are its validation "
    "scorings, and the author ruled to proceed as registered with the arm relabelled."
)


def ladder_file(directory: Path, arm: str, seed: int, severity: int, stride: int) -> Path:
    """F9-2's masked test scores (``AbstentionLayout.ladder_scores``' name)."""
    return directory / f"{arm}_seed{seed}_final_R0_masked_k{severity}_stride{stride}_scores.npz"


# =====================================================================================
# second implementations, for the claim table
# =====================================================================================


def ap_by_thresholds(p: np.ndarray, labels: np.ndarray) -> float:
    """Average precision computed threshold by threshold with ``searchsorted``, not a cumsum."""
    y = labels > 0.5
    thresholds = np.unique(p)[::-1]
    ranked_all, ranked_pos = np.sort(p), np.sort(p[y])
    admitted = p.size - np.searchsorted(ranked_all, thresholds, side="left")
    hits = ranked_pos.size - np.searchsorted(ranked_pos, thresholds, side="left")
    recall = hits / ranked_pos.size
    return float(np.sum(hits / admitted * np.diff(np.r_[0.0, recall])))


def aurc_by_curve(errors: np.ndarray, order: np.ndarray) -> float:
    """AURC as the plain mean of the risk–coverage curve, not the weighted error sum."""
    return float(risk_coverage_curve(errors, order)[1].mean())


def random_aurc_by_curve(errors: np.ndarray, seeds: np.ndarray) -> float:
    """The random-ordering reference, each permutation's curve averaged explicitly."""
    return float(
        np.mean(
            [
                aurc_by_curve(errors, np.random.default_rng(int(s)).permutation(errors.size))
                for s in seeds
            ]
        )
    )


def second_reading(
    p: np.ndarray, u: np.ndarray, labels: np.ndarray, point: OperatingPoint, seeds: np.ndarray
) -> dict[str, float]:
    """Each point statistic the outcome cites, by a second implementation.

    Independent of :func:`faultline.evaluation.risk_coverage.statistics`.
    """
    y = labels > 0.5
    errors = (p >= point.tau) != y
    covered = u <= point.kappa
    out = {
        "ece": equal_mass_ece(p, labels)[0],
        "mean_p": float(np.mean(p)),
        "auprc": ap_by_thresholds(p, labels),
        "coverage": float(np.count_nonzero(covered)) / p.size,
        "risk": float(np.count_nonzero(errors & covered)) / float(np.count_nonzero(covered)),
        "aurc": aurc_by_curve(errors, np.lexsort((np.arange(u.size), u))),
    }
    if seeds.size:
        out["aurc_random"] = random_aurc_by_curve(errors, seeds)
        out["aurc_minus_random"] = out["aurc"] - out["aurc_random"]
    return out


# =====================================================================================
# the run
# =====================================================================================


def _iv(value: float, vector: np.ndarray, config: AbstentionConfig) -> Interval:
    b = config.bootstrap
    return interval(value, vector, b.confidence, b.max_discarded_share)


def _paired(
    first: tuple[float, np.ndarray], second: tuple[float, np.ndarray], config: AbstentionConfig
) -> Interval:
    b = config.bootstrap
    return paired_interval(first, second, b.confidence, b.max_discarded_share)


def _curve(p: np.ndarray, u: np.ndarray, labels: np.ndarray, tau: float) -> list[dict[str, float]]:
    errors = misclassified(p, labels, tau)
    coverage, risk = risk_coverage_curve(errors, admission_order(u, False))
    rows = []
    for c in CURVE_COVERAGES:
        i = max(1, math.ceil(c * p.size - 1e-9))
        rows.append({"coverage": float(coverage[i - 1]), "selective_risk": float(risk[i - 1])})
    return rows


def run_outcome(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """F9-3: every ADR-0028 row after the operating point, and the verdict.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/eval/abstention_v0.yaml``.

    Returns:
        The Markdown report and its JSON record.

    Raises:
        FileNotFoundError: If the operating-point record does not exist: it is never fitted here.
    """
    config = load_config(config_path, AbstentionConfig)
    root, bootstrap = paths.repo_root, config.bootstrap
    record = operating_point_record(paths, config)
    if not record.is_file():
        raise FileNotFoundError(f"{record.name}: fix the operating point on validation first")
    directory = out_dir(paths, config)
    points = operating_points(record, config, directory)
    platt = platt_maps(record)
    counts = config.splits.test

    clean = {
        arm.name: load_ensemble(
            registered_test_files(config, root, arm.name), TEST, counts.windows, counts.positives
        )
        for arm in config.arms
    }
    ladder_arm = config.ladder.arm
    masked = {
        k: load_ensemble(
            [ladder_file(directory, ladder_arm, s, k, config.stride) for s in config.seeds],
            TEST,
            counts.windows,
            counts.positives,
        )
        for k in config.ladder.severities
    }
    # The one alignment check F9-3 makes: every ensemble read together covers the same rows.
    assert_paired({**clean, **{f"{ladder_arm}_k{k}": e for k, e in masked.items()}})

    first = next(iter(clean.values()))
    blocks = first.blocks(bootstrap.block_steps)
    seeds = permutation_seeds(
        config.risk_coverage.random_seed, config.risk_coverage.random_orderings
    )
    cache_dir = directory / "bootstrap"
    platt_p = {name: apply_platt(e.p, *platt[name]) for name, e in clean.items()}

    def job(
        name: str, e: Ensemble, p: np.ndarray, point: OperatingPoint | None, rand: bool
    ) -> StatisticsJob:
        return StatisticsJob(
            cache=cache_dir / f"f9_3_{name}.npz",
            p=p,
            u=e.u,
            labels=e.labels,
            blocks=blocks,
            replicates=bootstrap.replicates,
            seed=bootstrap.seed,
            bins=config.calibration.ece_bins,
            point=point,
            random_seeds=seeds if rand else np.zeros(0, dtype=np.uint64),
        )

    jobs: dict[str, StatisticsJob] = {}
    for name, e in clean.items():
        jobs[f"clean_{name}"] = job(f"clean_{name}", e, e.p, points[name], True)
    for name, e in clean.items():
        jobs[f"platt_{name}"] = job(f"platt_{name}", e, platt_p[name], None, False)
    for k, e in masked.items():
        jobs[f"{ladder_arm}_k{k}"] = job(f"{ladder_arm}_k{k}", e, e.p, points[ladder_arm], False)
    run_capped(
        run_statistics_job,
        [j for j in jobs.values() if not j.cache.is_file()],
        MAX_BOOTSTRAP_WORKERS,
    )
    vectors: dict[str, dict[str, np.ndarray]] = {}
    for key, j in jobs.items():
        with np.load(j.cache) as loaded:
            vectors[key] = {name: loaded[name] for name in loaded.files}

    # -- point values ------------------------------------------------------------------
    point_values: dict[str, dict[str, float]] = {}
    for key, j in jobs.items():
        point_values[key] = statistics(j.p, j.u, j.labels, j.bins, j.point, j.random_seeds)

    def stat(key: str, name: str) -> Interval:
        return _iv(point_values[key][name], vectors[key][name], config)

    # -- Part A --------------------------------------------------------------------------
    part_a: dict[str, Any] = {}
    gate_a: dict[str, Any] = {}
    for name, e in clean.items():
        key = f"clean_{name}"
        errors = misclassified(e.p, e.labels, points[name].tau)
        label = arm_label(name)
        part_a[label] = {
            "config_arm": name,
            "base_rate": float(e.labels.mean()),
            "ece_prior_corrected": asdict(stat(key, "ece")),
            "mean_p_prior_corrected": asdict(stat(key, "mean_p")),
            "ece_platt": asdict(stat(f"platt_{name}", "ece")),
            "mean_p_platt": asdict(stat(f"platt_{name}", "mean_p")),
            "platt_a_b": list(platt[name]),
            "reliability_platt": [
                asdict(x)
                for x in equal_mass_ece(platt_p[name], e.labels, config.calibration.ece_bins)[1]
            ],
            "auprc": asdict(stat(key, "auprc")),
            "aurc": asdict(stat(key, "aurc")),
            "aurc_random": asdict(stat(key, "aurc_random")),
            "full_coverage_selective_risk": float(errors.mean()),
            "coverage_at_operating_point": asdict(stat(key, "coverage")),
            "selective_risk_at_operating_point": asdict(stat(key, "risk")),
            "margin": {
                "coverage": asdict(stat(key, "margin_coverage")),
                "selective_risk": asdict(stat(key, "margin_risk")),
                "aurc": asdict(stat(key, "margin_aurc")),
            },
            "operating_point": asdict(points[name]),
            "curve": _curve(e.p, e.u, e.labels, points[name].tau),
            "caveats": list(config.caveats),
        }
        delta = stat(key, "aurc_minus_random")
        gate_a[label] = {
            "config_arm": name,
            "delta_aurc": asdict(delta),
            "outcome": decide_gate_a(delta, config.gate_a),
            "caveats": list(config.caveats),
        }

    # -- Gate B and H2 -----------------------------------------------------------------------
    k = config.gate_b.severity
    clean_key, k_key = f"clean_{ladder_arm}", f"{ladder_arm}_k{k}"

    def paired(name: str) -> Interval:
        return _paired(
            (point_values[k_key][name], vectors[k_key][name]),
            (point_values[clean_key][name], vectors[clean_key][name]),
            config,
        )

    delta_auprc, delta_cov, delta_risk = paired("auprc"), paired("coverage"), paired("risk")
    gate_b_outcome = decide_gate_b(delta_auprc, config.gate_b)
    gate_a_ladder = gate_a[arm_label(ladder_arm)]["outcome"]
    verdict = decide_h2(gate_a_ladder, gate_b_outcome, delta_cov, delta_risk, config.h2_rule)

    # -- the ladder, as measured -------------------------------------------------------------
    ladder_rows = []
    for severity in [0, *config.ladder.severities]:
        key = clean_key if severity == 0 else f"{ladder_arm}_k{severity}"
        e = clean[ladder_arm] if severity == 0 else masked[severity]
        ladder_rows.append(
            {
                "k": severity,
                "channels": [] if severity == 0 else config.ladder.sets[severity],
                "coverage": asdict(stat(key, "coverage")),
                "selective_risk": asdict(stat(key, "risk")),
                "auprc": asdict(stat(key, "auprc")),
                "ece": asdict(stat(key, "ece")),
                "mean_p": asdict(stat(key, "mean_p")),
                "aurc": asdict(stat(key, "aurc")),
                "margin_coverage": asdict(stat(key, "margin_coverage")),
                "margin_selective_risk": asdict(stat(key, "margin_risk")),
                "curve": _curve(e.p, e.u, e.labels, points[ladder_arm].tau),
                "caveats": list(config.caveats),
            }
        )

    # -- the claim table ---------------------------------------------------------------------
    claims = build_claims(
        jobs,
        point_values,
        vectors,
        clean,
        masked,
        points,
        platt_p,
        seeds,
        config,
        part_a,
        gate_a,
        delta_auprc,
        delta_cov,
        delta_risk,
        gate_b_outcome,
        verdict,
        json.loads(record.read_text(encoding="utf-8")),
    )

    payload = {
        "adr": "ADR-0028 §1-§4, F9-3",
        "config": config_path.relative_to(root).as_posix(),
        "config_hash": config_hash(config),
        "registered_in": config.registered_in,
        "operating_point_record": record.relative_to(root).as_posix(),
        "operating_point_commit": OPERATING_POINT_COMMIT,
        "step_0": STEP_0_LINE,
        "arm_labels": {arm.name: arm_label(arm.name) for arm in config.arms},
        "split": TEST,
        "windows": first.windows,
        "positives": first.positives,
        "blocks": int(np.unique(blocks).size),
        "bootstrap": bootstrap.model_dump(),
        "random_orderings": config.risk_coverage.random_orderings,
        "random_seed": config.risk_coverage.random_seed,
        "known_under_read": config.calibration.known_under_read,
        "part_a": part_a,
        "gate_a": gate_a,
        "gate_b": {
            "arm": arm_label(ladder_arm),
            "severity": k,
            "delta_auprc": asdict(delta_auprc),
            "outcome": gate_b_outcome,
            "caveats": list(config.caveats),
        },
        "h2": {
            "arm": arm_label(ladder_arm),
            "severity": k,
            "gate_a": gate_a_ladder,
            "gate_b": gate_b_outcome,
            "delta_coverage": asdict(delta_cov),
            "delta_selective_risk": asdict(delta_risk),
            "smallest_effect_risk": config.h2_rule.smallest_effect_risk,
            "verdict": verdict,
            "caveats": list(config.caveats),
        },
        "ladder": ladder_rows,
        "claims": claims,
        "caveats": {c: CAVEAT_TEXT[c] for c in config.caveats},
        "git_sha": git_sha(root),
        "written_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
    }
    stem = f"abstention_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report_dir = paths.data_reports_dir
    json_path, md_path = report_dir / f"{stem}.json", report_dir / f"{stem}.md"
    write_json(json_path, payload)
    md_path.write_text(render(payload), encoding="utf-8", newline="\n")
    return md_path, json_path


#: The commit that fixed the operating point alone, before any test file was opened.
OPERATING_POINT_COMMIT = "1ad1890"


# =====================================================================================
# claims
# =====================================================================================


def build_claims(
    jobs: dict[str, StatisticsJob],
    point_values: dict[str, dict[str, float]],
    vectors: dict[str, dict[str, np.ndarray]],
    clean: dict[str, Ensemble],
    masked: dict[int, Ensemble],
    points: dict[str, OperatingPoint],
    platt_p: dict[str, np.ndarray],
    seeds: np.ndarray,
    config: AbstentionConfig,
    part_a: dict[str, Any],
    gate_a: dict[str, Any],
    delta_auprc: Interval,
    delta_cov: Interval,
    delta_risk: Interval,
    gate_b_outcome: str,
    verdict: str,
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    """Every number the outcome cites, each read a second way, with whether the two agree."""
    confidence = config.bootstrap.confidence
    tail = (1.0 - confidence) / 2.0
    ladder_arm = config.ladder.arm
    k = config.gate_b.severity
    claims: list[dict[str, Any]] = []

    def bounds(vector: np.ndarray) -> tuple[float, float]:
        kept = np.sort(vector[~np.isnan(vector)])
        return (
            float(np.quantile(kept, tail, method="linear")),
            float(np.quantile(kept, 1.0 - tail, method="linear")),
        )

    def add(
        claim: str, source: str, reported: Any, second: Any, how: str, tol: float = AGREEMENT
    ) -> None:
        if isinstance(reported, str) or isinstance(second, str):
            ok = reported == second
        else:
            ok = all(
                abs(float(r) - float(s)) <= tol
                for r, s in zip(np.atleast_1d(reported), np.atleast_1d(second), strict=True)
            )
        claims.append(
            {
                "claim": claim,
                "source": source,
                "reported": reported,
                "second_reading": second,
                "how": how,
                "matches": bool(ok),
            }
        )

    for name, e in clean.items():
        label = arm_label(name)
        second = second_reading(e.p, e.u, e.labels, points[name], seeds)
        key = f"clean_{name}"
        row = part_a[label]
        root = f"part_a[{label!r}]"
        for stat_name, field in (
            ("ece", "ece_prior_corrected"),
            ("mean_p", "mean_p_prior_corrected"),
            ("coverage", "coverage_at_operating_point"),
            ("risk", "selective_risk_at_operating_point"),
            ("aurc", "aurc"),
            ("aurc_random", "aurc_random"),
        ):
            add(
                f"{label}: {field}",
                f"{root}.{field}.value",
                row[field]["value"],
                second[stat_name],
                "separate implementation on the scores",
            )
            add(
                f"{label}: {field} 95% interval",
                f"{root}.{field}.low/high",
                [row[field]["low"], row[field]["high"]],
                list(bounds(vectors[key][stat_name])),
                "percentiles re-read from the replicate vector",
            )
        platt_second = equal_mass_ece(platt_p[name], e.labels, config.calibration.ece_bins)[0]
        add(
            f"{label}: ece_platt",
            f"{root}.ece_platt.value",
            row["ece_platt"]["value"],
            platt_second,
            "equal_mass_ece's table path",
        )
        add(
            f"{label}: ece_platt 95% interval",
            f"{root}.ece_platt.low/high",
            [row["ece_platt"]["low"], row["ece_platt"]["high"]],
            list(bounds(vectors[f"platt_{name}"]["ece"])),
            "percentiles re-read from the replicate vector",
        )
        add(
            f"{label}: random-ordering AURC ≈ full-coverage selective risk",
            f"{root}.aurc_random.value vs full_coverage_selective_risk",
            row["aurc_random"]["value"],
            row["full_coverage_selective_risk"],
            "sanity check: within 0.001",
            tol=1e-3,
        )
        delta = gate_a[label]["delta_aurc"]
        vector = vectors[key]["aurc_minus_random"]
        add(
            f"{label}: Gate A Δ AURC",
            f"gate_a[{label!r}].delta_aurc.value",
            delta["value"],
            second["aurc_minus_random"],
            "curve means, explicit permutations",
        )
        add(
            f"{label}: Gate A Δ AURC 95% interval",
            f"gate_a[{label!r}].delta_aurc.low/high",
            [delta["low"], delta["high"]],
            list(bounds(vector)),
            "percentiles re-read from the replicate vector",
        )
        add(
            f"{label}: Gate A outcome",
            f"gate_a[{label!r}].outcome",
            gate_a[label]["outcome"],
            "pass" if delta["trusted"] and delta["high"] < 0.0 else "not_evaluable",
            "the §2 sentence, applied by hand",
        )

    # The operating point as the committed record holds it.
    held = {row["config_arm"]: row for row in record["arms"].values()}
    for name in clean:
        label = arm_label(name)
        for field in ("tau", "kappa"):
            add(
                f"{label}: {field}",
                f"part_a[{label!r}].operating_point.{field}",
                part_a[label]["operating_point"][field],
                held[name][field],
                "the committed validation record",
            )
        add(
            f"{label}: mean_p_platt",
            f"part_a[{label!r}].mean_p_platt.value",
            part_a[label]["mean_p_platt"]["value"],
            float(np.mean(platt_p[name])),
            "mean of the Platt-mapped scores",
        )
        add(
            f"{label}: mean_p_platt 95% interval",
            f"part_a[{label!r}].mean_p_platt.low/high",
            [part_a[label]["mean_p_platt"]["low"], part_a[label]["mean_p_platt"]["high"]],
            list(bounds(vectors[f"platt_{name}"]["mean_p"])),
            "percentiles re-read from the replicate vector",
        )

    # The ladder, every severity.
    for severity, e in masked.items():
        second = second_reading(e.p, e.u, e.labels, points[ladder_arm], np.zeros(0))
        key = f"{ladder_arm}_k{severity}"
        for stat_name in ("coverage", "risk", "auprc", "ece", "mean_p"):
            add(
                f"ladder k={severity}: {stat_name}",
                f"ladder[k={severity}].{stat_name}.value",
                point_values[key][stat_name],
                second[stat_name],
                "separate implementation on the scores",
            )
            add(
                f"ladder k={severity}: {stat_name} 95% interval",
                f"ladder[k={severity}].{stat_name}.low/high",
                list(percentile_interval(vectors[key][stat_name], confidence)),
                list(bounds(vectors[key][stat_name])),
                "percentiles re-read from the replicate vector",
            )

    # Gate B and H2, paired.
    e_k, e_0 = masked[k], clean[ladder_arm]
    second_k = second_reading(e_k.p, e_k.u, e_k.labels, points[ladder_arm], np.zeros(0))
    second_0 = second_reading(e_0.p, e_0.u, e_0.labels, points[ladder_arm], np.zeros(0))
    k_key, clean_key = f"{ladder_arm}_k{k}", f"clean_{ladder_arm}"
    for claim, field, iv, stat_name in (
        ("Gate B Δ AUPRC (k=8 − clean)", "gate_b.delta_auprc", delta_auprc, "auprc"),
        ("H2 Δcov (k=8 − clean)", "h2.delta_coverage", delta_cov, "coverage"),
        ("H2 Δrisk (k=8 − clean)", "h2.delta_selective_risk", delta_risk, "risk"),
    ):
        add(
            claim,
            f"{field}.value",
            iv.value,
            second_k[stat_name] - second_0[stat_name],
            "separate implementation on both sides",
        )
        add(
            f"{claim} 95% interval",
            f"{field}.low/high",
            [iv.low, iv.high],
            list(bounds(vectors[k_key][stat_name] - vectors[clean_key][stat_name])),
            "percentiles of the re-read paired difference",
        )
    by_hand_b = "damage" if delta_auprc.trusted and delta_auprc.high < 0.0 else "not_testable"
    add("Gate B outcome", "gate_b.outcome", gate_b_outcome, by_hand_b, "the §3 sentence by hand")
    rule = config.h2_rule
    if gate_a[arm_label(ladder_arm)]["outcome"] != "pass":
        by_hand = "not_evaluable"
    elif by_hand_b != "damage":
        by_hand = "not_testable"
    elif not (delta_cov.trusted and delta_risk.trusted):
        by_hand = "inconclusive"
    elif delta_cov.high < 0.0 and delta_risk.high < rule.smallest_effect_risk:
        by_hand = "supported"
    elif delta_cov.low >= 0.0 and delta_risk.low > 0.0:
        by_hand = "refuted"
    else:
        by_hand = "inconclusive"
    add("H2 verdict", "h2.verdict", verdict, by_hand, "the §3 clauses by hand")
    return claims


# =====================================================================================
# the report
# =====================================================================================


def _ci(iv: dict[str, Any], digits: int = 4) -> str:
    return f"{iv['value']:.{digits}f} [{iv['low']:.{digits}f}, {iv['high']:.{digits}f}]"


def _signed(iv: dict[str, Any], digits: int = 4) -> str:
    return f"{iv['value']:+.{digits}f} [{iv['low']:+.{digits}f}, {iv['high']:+.{digits}f}]"


def render(payload: dict[str, Any]) -> str:
    """The F9-3 report as Markdown."""
    b = payload["bootstrap"]
    header = kv_table(
        {
            "record": payload["adr"],
            "config": f"{payload['config']} ({payload['config_hash']}), registered in "
            f"{payload['registered_in']}",
            "operating point": f"{payload['operating_point_record']}, committed alone in "
            f"**{payload['operating_point_commit']}** before any test file was opened",
            "split": f"clean test: {payload['windows']:,} windows, {payload['positives']:,} "
            f"positive, {payload['blocks']:,} two-day blocks",
            "interval": f"block bootstrap, {b['replicates']:,} replicates, seed {b['seed']}, "
            f"{b['confidence']:.0%}; more than {b['max_discarded_share']:.0%} discarded is "
            "untrusted",
            "random reference": f"{payload['random_orderings']} permutations, seeds from "
            f"default_rng({payload['random_seed']})",
            "git": payload["git_sha"],
        }
    )
    tel = payload["arm_labels"]["tel_only_a"]
    lines = [
        "# ADR-0028: calibration, abstention and H2 (F9-3)",
        "",
        payload["step_0"],
        "",
        header,
        "",
        f'**Arm naming.** "{tel}" is the `tel_only` backbone read through (a) on the joint R0 '
        "windows. It is **not** F3's `tel_only` (a) on the 1,872-token M1 windows that serves as "
        "the H1/H1′ comparator, and its calibration is not that baseline's.",
        "",
        "## Operating points (validation only)",
        "",
        table(
            ["arm", "τ", "κ", "margin cut", "Platt a", "Platt b"],
            [
                [
                    label,
                    f"{r['operating_point']['tau']:.4f}",
                    f"{r['operating_point']['kappa']:.4f}",
                    f"{r['operating_point']['margin_cut']:.4f}",
                    f"{r['platt_a_b'][0]:.4f}",
                    f"{r['platt_a_b'][1]:.4f}",
                ]
                for label, r in payload["part_a"].items()
            ],
        ),
        "",
        "## Part A: calibration on clean test (reported, no verdict)",
        "",
        table(
            [
                "arm",
                "ECE, prior-corrected",
                "ECE, Platt (validation)",
                "mean p, corrected",
                "mean p, Platt",
                "base rate",
                "caveats",
            ],
            [
                [
                    label,
                    _ci(r["ece_prior_corrected"]),
                    _ci(r["ece_platt"]),
                    _ci(r["mean_p_prior_corrected"]),
                    _ci(r["mean_p_platt"]),
                    f"{r['base_rate']:.4f}",
                    CAVEAT_SHORT,
                ]
                for label, r in payload["part_a"].items()
            ],
        ),
        "",
        "Stated before the run: F3 read `tel_only`'s corrected mean test probability at "
        + ", ".join(f"{v:.4f}" for v in payload["known_under_read"])
        + " against the test base rate 0.0388. The Platt map is fitted at the validation base "
        "rate 0.0211 and does not remove that shift.",
        "",
        "## Part A: risk–coverage on clean test",
        "",
        table(
            [
                "arm",
                "AURC (disagreement)",
                "AURC (random, mean of 100)",
                "full-coverage selective risk",
                "coverage at (τ, κ)",
                "selective risk at (τ, κ)",
                "AUPRC",
                "caveats",
            ],
            [
                [
                    label,
                    _ci(r["aurc"]),
                    _ci(r["aurc_random"]),
                    f"{r['full_coverage_selective_risk']:.4f}",
                    _ci(r["coverage_at_operating_point"]),
                    _ci(r["selective_risk_at_operating_point"]),
                    _ci(r["auprc"]),
                    CAVEAT_SHORT,
                ]
                for label, r in payload["part_a"].items()
            ],
        ),
        "",
        "The random-ordering AURC's expectation is the full-coverage selective risk; the two "
        "columns are the sanity check the brief asked for.",
        "",
        "**Margin signal, reported only** (covered when |p − τ| ≥ the validation cut):",
        "",
        table(
            ["arm", "coverage", "selective risk", "AURC (margin)", "caveats"],
            [
                [
                    label,
                    _ci(r["margin"]["coverage"]),
                    _ci(r["margin"]["selective_risk"]),
                    _ci(r["margin"]["aurc"]),
                    CAVEAT_SHORT,
                ]
                for label, r in payload["part_a"].items()
            ],
        ),
        "",
        "**Risk–coverage curves** (disagreement ascending; selective risk at each coverage):",
        "",
        table(
            ["coverage", *payload["part_a"].keys()],
            [
                [
                    f"{c['coverage']:.2f}",
                    *[f"{r['curve'][i]['selective_risk']:.4f}" for r in payload["part_a"].values()],
                ]
                for i, c in enumerate(next(iter(payload["part_a"].values()))["curve"])
            ],
        ),
        "",
        "## Gate A: does seed disagreement order risk better than chance?",
        "",
        "> PASS iff the 95% upper bound of AURC(seed disagreement) − AURC(random) is below zero; "
        "FAIL → abstention on that arm NOT EVALUABLE.",
        "",
        table(
            ["arm", "Δ AURC", "discarded", "outcome", "caveats"],
            [
                [
                    label,
                    _signed(g["delta_aurc"]),
                    f"{g['delta_aurc']['discarded']}",
                    g["outcome"].replace("_", " ").upper(),
                    CAVEAT_SHORT,
                ]
                for label, g in payload["gate_a"].items()
            ],
        ),
        "",
        "## Gate B: does k = 8 damage joint (d)'s ranking?",
        "",
        "> Paired Δ AUPRC(ensemble, k=8) − AUPRC(ensemble, clean); damage iff the upper bound is "
        "below zero, else H2 NOT TESTABLE.",
        "",
        table(
            ["arm", "Δ AUPRC", "discarded", "outcome", "caveats"],
            [
                [
                    payload["gate_b"]["arm"],
                    _signed(payload["gate_b"]["delta_auprc"]),
                    f"{payload['gate_b']['delta_auprc']['discarded']}",
                    payload["gate_b"]["outcome"].replace("_", " ").upper(),
                    CAVEAT_SHORT,
                ]
            ],
        ),
        "",
        "## H2",
        "",
        "> SUPPORTED if the upper bound of Δcov is below zero AND the upper bound of Δrisk is "
        "below +0.005. REFUTED if the lower bound of Δcov is at or above zero AND the lower "
        "bound of Δrisk is above zero. Otherwise INCONCLUSIVE. Requires Gate A PASS on joint (d) "
        "and Gate B damage.",
        "",
        table(
            ["arm", "Gate A", "Gate B", "Δcov", "Δrisk", "verdict", "caveats"],
            [
                [
                    payload["h2"]["arm"],
                    payload["h2"]["gate_a"].replace("_", " ").upper(),
                    payload["h2"]["gate_b"].replace("_", " ").upper(),
                    _signed(payload["h2"]["delta_coverage"]),
                    _signed(payload["h2"]["delta_selective_risk"]),
                    f"**{payload['h2']['verdict'].replace('_', ' ').upper()}**",
                    CAVEAT_SHORT,
                ]
            ],
        ),
        "",
        "## The severity ladder on joint (d), as measured (no verdict)",
        "",
        table(
            [
                "k",
                "coverage",
                "selective risk",
                "AUPRC",
                "ECE",
                "mean p",
                "margin coverage",
                "margin risk",
                "caveats",
            ],
            [
                [
                    str(r["k"]),
                    _ci(r["coverage"]),
                    _ci(r["selective_risk"]),
                    _ci(r["auprc"]),
                    _ci(r["ece"]),
                    _ci(r["mean_p"]),
                    _ci(r["margin_coverage"]),
                    _ci(r["margin_selective_risk"]),
                    CAVEAT_SHORT,
                ]
                for r in payload["ladder"]
            ],
        ),
        "",
        "Channels masked at each k (nested): "
        + "; ".join(f"k={r['k']}: {', '.join(r['channels'])}" for r in payload["ladder"] if r["k"])
        + ".",
        "",
        "## Claims the ADR-0028 outcome cites",
        "",
        table(
            ["claim", "source (this JSON)", "reported", "second reading", "how", "matches"],
            [
                [
                    c["claim"],
                    f"`{c['source']}`",
                    _fmt_claim(c["reported"]),
                    _fmt_claim(c["second_reading"]),
                    c["how"],
                    "yes" if c["matches"] else "**NO**",
                ]
                for c in payload["claims"]
            ],
        ),
        "",
    ]
    for label, r in payload["part_a"].items():
        lines += [
            f"## Reliability after Platt: {label}",
            "",
            table(
                ["bin", "windows", "p range", "mean p", "positive share", "gap"],
                [
                    [
                        str(i),
                        f"{x['windows']:,}",
                        f"{x['low']:.4f}–{x['high']:.4f}",
                        f"{x['mean_p']:.4f}",
                        f"{x['positive_share']:.4f}",
                        f"{x['mean_p'] - x['positive_share']:+.4f}",
                    ]
                    for i, x in enumerate(r["reliability_platt"], 1)
                ],
            ),
            "",
        ]
    lines += ["## Caveats, on every row (ADR-0028 §4)", ""]
    lines += [f"- {text}" for text in payload["caveats"].values()]
    lines += [
        "- Message-volume shift: Kelmarsh positives average 67.2 status tokens in train (stride "
        "6) and 190.1 in test (stride 12).",
        "",
    ]
    return "\n".join(lines)


def _fmt_claim(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "[" + ", ".join(f"{float(v):.6f}" for v in value) + "]"
    return f"{float(value):.6f}"


def load_payload(path: Path) -> dict[str, Any]:
    """A written F9-3 record."""
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded
