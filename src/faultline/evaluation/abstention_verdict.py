"""F9's CPU half (ADR-0028 §1-§3): the operating point, Part A's rows, Gate A, Gate B and H2.

Nothing is trained and nothing is scored here. The clean test scores are the nine saved reads
ADR-0028 §1 names; the validation and ladder scores are F9-2's
(:mod:`faultline.evaluation.abstention_runs`). Every ensemble is formed by
:func:`faultline.evaluation.risk_coverage.ensemble`, which refuses seeds that do not align row
for row, and every set of arms or severities read together is checked to cover the same rows.

**What F9-1 reports now** is :func:`run_part_a_ece`: Part A's ECE of the prior-corrected ensemble
per arm, over 15 equal-mass bins, with its reliability table and ADR-0024's block-bootstrap
interval, on clean test. It needs no τ, no κ and no Platt fit, so it is provisional-free.

**What waits for F9-2** is everything that needs validation: :func:`operating_points` fits τ, κ,
the margin cut-off and Platt's (a, b) from the validation files **only**, writes them to a
record, and on every later call reads that record back rather than fitting again — nothing here
can recompute an operating point from test. :func:`decide_gate_a`, :func:`decide_gate_b` and
:func:`decide_h2` apply ADR-0028 §2-§3 to intervals built by
:func:`faultline.evaluation.risk_coverage.paired_interval`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from faultline.config import config_hash, load_config
from faultline.data.common.report import kv_table, table
from faultline.evaluation.abstention_gate import AbstentionConfig, GateA, GateB, H2Rule
from faultline.evaluation.h1_scoring import write_json
from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.readout_verdict import MAX_BOOTSTRAP_WORKERS
from faultline.evaluation.risk_coverage import (
    TEST,
    VALIDATION,
    Ensemble,
    Interval,
    OperatingPoint,
    StatisticsJob,
    ensemble,
    equal_mass_ece,
    fit_kappa,
    fit_margin_cut,
    fit_platt,
    fit_tau,
    interval,
    run_capped,
    run_statistics_job,
)
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

#: The label Part A's F9-1 rows carry: none of them reads τ, κ or a validation fit.
PROVISIONAL_FREE = "provisional-free: nothing here depends on τ, κ or Platt"

#: ADR-0028 §4's caveats, by the short names the configuration lists.
CAVEAT_TEXT = {
    "adr_0009": "ADR-0009: one harmonised event rule across sites",
    "forward_in_time_same_sites": "forward in time, same sites (ADR-0022): never site shift",
    "message_volume_shift": "message-volume shift (ADR-0025)",
    "small_ensemble": "a three-seed ensemble is a small ensemble",
    "operating_point_base_rate_shift": "operating point fixed at validation base rate 0.0211",
}


# =====================================================================================
# the files
# =====================================================================================


def registered_test_files(config: AbstentionConfig, root: Path, arm: str) -> list[Path]:
    """An arm's registered clean test scores, one per seed, in seed order."""
    return [root / config.arm(arm).test_scores.format(seed=seed) for seed in config.seeds]


def validation_file(out_dir: Path, arm: str, seed: int, stride: int) -> Path:
    """F9-2's clean validation scores of an arm at a seed (``AbstentionLayout``'s name)."""
    return out_dir / f"{arm}_seed{seed}_final_R0_val_stride{stride}_scores.npz"


def out_dir(paths: ProjectPaths, config: AbstentionConfig) -> Path:
    """``checkpoints/abstention_v<version>_<hash>``, without resolving the training layouts."""
    return paths.checkpoints_dir / f"abstention_v{config.version}_{config_hash(config)}"


def load_ensemble(files: list[Path], split: str, windows: int, positives: int) -> Ensemble:
    """The seeds' ensemble, refused unless every seed holds the registered rows, aligned.

    Args:
        files: One scores file per seed, in seed order.
        split: ``validation`` or ``test``.
        windows: The registered window count.
        positives: The registered positive count.

    Returns:
        The ensemble.

    Raises:
        FileNotFoundError: If a seed's file is missing.
        ValueError: If a seed holds other counts or the seeds do not align row for row.
    """
    missing = [f.name for f in files if not f.is_file()]
    if missing:
        raise FileNotFoundError(f"not scored yet: {missing}")
    seeds = [ScoredWindows.load(f) for f in files]
    for path, scored in zip(files, seeds, strict=True):
        found = (scored.labels.size, int(scored.labels.sum()))
        if found != (windows, positives):
            raise ValueError(f"{path.name} holds {found}, registered {(windows, positives)}")
    return ensemble(seeds, split)


def assert_paired(ensembles: dict[str, Ensemble]) -> None:
    """Refuse to read ensembles together unless they cover the same rows, in order.

    Raises:
        ValueError: If any differs from the first.
    """
    names = list(ensembles)
    for name in names[1:]:
        if not ensembles[name].same_rows(ensembles[names[0]]):
            raise ValueError(f"{name} and {names[0]} do not cover the same rows")


# =====================================================================================
# the operating point
# =====================================================================================


def fit_operating_point(validation: Ensemble, coverage: float) -> dict[str, float]:
    """τ, κ, the margin cut-off and Platt's (a, b), fitted on one clean validation ensemble.

    Raises:
        ValueError: If the ensemble is not the validation split's.
    """
    tau = fit_tau(validation)
    a, b = fit_platt(validation)
    return {
        "tau": tau,
        "kappa": fit_kappa(validation, coverage),
        "margin_cut": fit_margin_cut(validation, tau, coverage),
        "platt_a": a,
        "platt_b": b,
        "validation_coverage": float((validation.u <= fit_kappa(validation, coverage)).mean()),
        "validation_windows": validation.windows,
        "validation_positives": validation.positives,
    }


def operating_points(
    record: Path, config: AbstentionConfig, validation_dir: Path
) -> dict[str, OperatingPoint]:
    """Each arm's operating point: read from ``record`` if it exists, else fitted and written.

    The record is written once, from validation files alone, and never rewritten; a later call
    reads it back. No test file is opened here.

    Args:
        record: The operating-point record.
        config: The loaded abstention configuration.
        validation_dir: Where F9-2 wrote the validation scores.

    Returns:
        Per arm, its operating point.
    """
    if not record.is_file():
        counts = config.splits.validation
        rows: dict[str, Any] = {}
        reference: Ensemble | None = None
        for arm in config.arms:
            files = [
                validation_file(validation_dir, arm.name, s, config.stride) for s in config.seeds
            ]
            scores = load_ensemble(files, VALIDATION, counts.windows, counts.positives)
            if reference is not None and not scores.same_rows(reference):
                raise ValueError(f"{arm.name}'s validation rows are not the other arms'")
            reference = scores
            rows[arm.name] = fit_operating_point(scores, config.operating_model.kappa_coverage)
            rows[arm.name]["files"] = [f.name for f in files]
        write_json(
            record,
            {
                "config_hash": config_hash(config),
                "split": VALIDATION,
                "rule": {
                    "tau": config.operating_model.tau_rule,
                    "kappa_coverage": config.operating_model.kappa_coverage,
                    "margin_cut": "F9-1: the 1 - coverage quantile of validation |p - tau|",
                },
                "arms": rows,
                "written_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            },
        )
    loaded = json.loads(record.read_text(encoding="utf-8"))
    if loaded.get("split") != VALIDATION:
        raise ValueError(f"{record.name} was not fitted on validation")
    return {
        name: OperatingPoint(tau=row["tau"], kappa=row["kappa"], margin_cut=row["margin_cut"])
        for name, row in loaded["arms"].items()
    }


# =====================================================================================
# the gates and the rule
# =====================================================================================


def decide_gate_a(delta: Interval, gate: GateA) -> str:
    """ADR-0028 §2: ``pass`` iff the Δ AURC upper bound is below the bound and trusted."""
    if not delta.trusted:
        return "untrusted"
    return "pass" if delta.high < gate.upper_bound_below else gate.on_failure


def decide_gate_b(delta: Interval, gate: GateB) -> str:
    """ADR-0028 §3: ``damage`` iff the Δ AUPRC upper bound is below the bound and trusted."""
    if not delta.trusted:
        return "untrusted"
    return "damage" if delta.high < gate.upper_bound_below else gate.on_failure


def decide_h2(
    gate_a: str, gate_b: str, delta_coverage: Interval, delta_risk: Interval, rule: H2Rule
) -> str:
    """ADR-0028 §3's H2 rule, prerequisites first.

    Args:
        gate_a: Gate A's outcome on ``joint`` (d).
        gate_b: Gate B's outcome.
        delta_coverage: Δcov = coverage(k=8) − coverage(clean).
        delta_risk: Δrisk = selective risk(k=8) − selective risk(clean).
        rule: The registered rule.

    Returns:
        One of :data:`faultline.evaluation.abstention_gate.H2_VERDICTS`.
    """
    if gate_a != "pass":
        return "not_evaluable"
    if gate_b != "damage":
        return "not_testable"
    if not (delta_coverage.trusted and delta_risk.trusted):
        return rule.otherwise
    if (
        delta_coverage.high < rule.supported_cov_upper_below
        and delta_risk.high < rule.supported_risk_upper_below
    ):
        return "supported"
    if (
        delta_coverage.low >= rule.refuted_cov_lower_at_or_above
        and delta_risk.low > rule.refuted_risk_lower_above
    ):
        return "refuted"
    return rule.otherwise


# =====================================================================================
# Part A's ECE (F9-1)
# =====================================================================================


@dataclass(frozen=True)
class EceRow:
    """One arm's Part A calibration row.

    Attributes:
        arm: The arm.
        ece: Its equal-mass ECE, with interval.
        mean_p: Its mean ensemble probability, with interval.
        base_rate: The clean test base rate.
        seed_means: Each seed's mean corrected probability.
        reliability: The reliability table.
    """

    arm: str
    ece: Interval
    mean_p: Interval
    base_rate: float
    seed_means: list[float]
    reliability: list[dict[str, float]]


def run_part_a_ece(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """Part A's ECE of the prior-corrected ensemble per arm, on clean test, with intervals.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/eval/abstention_v0.yaml``.

    Returns:
        The Markdown report and its JSON record.
    """
    config = load_config(config_path, AbstentionConfig)
    root, bootstrap = paths.repo_root, config.bootstrap
    counts = config.splits.test
    ensembles = {
        arm.name: load_ensemble(
            registered_test_files(config, root, arm.name), TEST, counts.windows, counts.positives
        )
        for arm in config.arms
    }
    assert_paired(ensembles)
    first = next(iter(ensembles.values()))
    blocks = first.blocks(bootstrap.block_steps)
    cache_dir = out_dir(paths, config) / "bootstrap"
    jobs = {
        name: StatisticsJob(
            cache=cache_dir / f"part_a_ece_{name}.npz",
            p=e.p,
            u=e.u,
            labels=e.labels,
            blocks=blocks,
            replicates=bootstrap.replicates,
            seed=bootstrap.seed,
            bins=config.calibration.ece_bins,
        )
        for name, e in ensembles.items()
    }
    run_capped(
        run_statistics_job,
        [job for job in jobs.values() if not job.cache.is_file()],
        MAX_BOOTSTRAP_WORKERS,
    )
    rows: list[EceRow] = []
    for name, e in ensembles.items():
        ece, reliability = equal_mass_ece(e.p, e.labels, config.calibration.ece_bins)
        with np.load(jobs[name].cache) as vectors:
            ece_vector, mean_vector = vectors["ece"], vectors["mean_p"]
        rows.append(
            EceRow(
                arm=name,
                ece=interval(ece, ece_vector, bootstrap.confidence, bootstrap.max_discarded_share),
                mean_p=interval(
                    float(e.p.mean()),
                    mean_vector,
                    bootstrap.confidence,
                    bootstrap.max_discarded_share,
                ),
                base_rate=float(e.labels.mean()),
                seed_means=[float(m) for m in (1.0 / (1.0 + np.exp(-e.corrected))).mean(axis=1)],
                reliability=[asdict(b) for b in reliability],
            )
        )
    payload = {
        "adr": "ADR-0028 §2, Part A (i)",
        "label": PROVISIONAL_FREE,
        "config": config_path.relative_to(root).as_posix(),
        "config_hash": config_hash(config),
        "registered_in": config.registered_in,
        "split": TEST,
        "windows": first.windows,
        "positives": first.positives,
        "blocks": int(np.unique(blocks).size),
        "bins": config.calibration.ece_bins,
        "binning": config.calibration.binning,
        "bootstrap": bootstrap.model_dump(),
        "known_under_read": config.calibration.known_under_read,
        "caveats": [CAVEAT_TEXT[c] for c in config.caveats],
        "rows": [asdict(row) for row in rows],
        "git_sha": git_sha(root),
        "written_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
    }
    stem = f"abstention_part_a_ece_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report_dir = paths.data_reports_dir
    record = report_dir / f"{stem}.json"
    report = report_dir / f"{stem}.md"
    write_json(record, payload)
    report.write_text(render_part_a(payload), encoding="utf-8")
    return report, record


def render_part_a(payload: dict[str, Any]) -> str:
    """Part A's ECE rows as Markdown."""
    header = kv_table(
        dict(
            [
                ("record", payload["adr"]),
                ("label", payload["label"]),
                ("config", f"{payload['config']} ({payload['config_hash']})"),
                (
                    "split",
                    f"clean test: {payload['windows']:,} windows, {payload['positives']:,} "
                    f"positive, {payload['blocks']:,} two-day blocks",
                ),
                ("ECE", f"{payload['bins']} {payload['binning'].replace('_', '-')} bins"),
                (
                    "interval",
                    f"block bootstrap, {payload['bootstrap']['replicates']:,} replicates, "
                    f"seed {payload['bootstrap']['seed']}, "
                    f"{payload['bootstrap']['confidence']:.0%}",
                ),
                ("git", payload["git_sha"]),
            ]
        )
    )
    lines = [
        "# ADR-0028 Part A: ECE of the prior-corrected ensemble",
        "",
        f"**{payload['label']}.** Reported, no verdict (ADR-0028 §2). The Platt rows, the "
        "risk–coverage curves, AURC, Gate A and the (τ, κ) rows wait for F9-2's validation "
        "scorings.",
        "",
        header,
        "",
        "## ECE per arm",
        "",
        table(
            [
                "arm",
                "ECE",
                "95% interval",
                "mean p",
                "95% interval",
                "base rate",
                "seed means",
                "discarded",
            ],
            [
                [
                    r["arm"],
                    f"{r['ece']['value']:.4f}",
                    f"[{r['ece']['low']:.4f}, {r['ece']['high']:.4f}]",
                    f"{r['mean_p']['value']:.4f}",
                    f"[{r['mean_p']['low']:.4f}, {r['mean_p']['high']:.4f}]",
                    f"{r['base_rate']:.4f}",
                    " / ".join(f"{m:.4f}" for m in r["seed_means"]),
                    f"{r['ece']['discarded']}",
                ]
                for r in payload["rows"]
            ],
        ),
        "",
        "Stated before the run (ADR-0028 §2): F3 read `tel_only`'s corrected mean test "
        "probability at "
        + ", ".join(f"{v:.4f}" for v in payload["known_under_read"])
        + ", against the test base rate 0.0388, so the ensemble is expected to under-read.",
        "",
    ]
    for r in payload["rows"]:
        lines += [
            f"## Reliability: {r['arm']}",
            "",
            table(
                ["bin", "windows", "p range", "mean p", "positive share", "gap"],
                [
                    [
                        str(i),
                        f"{b['windows']:,}",
                        f"{b['low']:.4f}–{b['high']:.4f}",
                        f"{b['mean_p']:.4f}",
                        f"{b['positive_share']:.4f}",
                        f"{b['mean_p'] - b['positive_share']:+.4f}",
                    ]
                    for i, b in enumerate(r["reliability"], 1)
                ],
            ),
            "",
        ]
    lines += ["## Caveats, on every row", ""] + [f"- {c}" for c in payload["caveats"]] + [""]
    return "\n".join(lines)
