"""F7'-3's CPU half: bootstrap the read-out scorings, gate the instrument, and apply ADR-0026 §4.

Nothing is trained and nothing is scored here. The twelve read-out scorings are
:mod:`faultline.evaluation.readout_runs`' (``checkpoints/readout_v0_<hash>``), read from disk;
``tel_only``'s reference side is F3's final-step scores, unchanged from ADR-0025 §5; the joint
arm's ``final_position`` column is F6-3's R0 scorings; and the order-blind status-only
classifier's scores are F6-1b's. Every file is asserted to cover the same 137,025 rows in the
same order before any pairing.

**The bootstrap is ADR-0024's**, exactly as F6-3 ran it: two-day blocks within each shard,
10,000 replicates, seed 20260916, 95% percentile intervals, discard rule 1%. Each scorer's
replicate AUPRCs are computed **once** per stratum and cached, and every interval below is
derived from those vectors — a single read's interval is its vector's percentiles, a paired Δ's
is the percentiles of two vectors differenced replicate by replicate. The machinery is
:mod:`faultline.evaluation.h1_verdict`'s, re-used rather than re-written, so an F7' interval and
an F6-3 interval are the same computation on the same draws.

**The gate is computed first, and it decides whether H1' is read at all** (ADR-0026 §4). If
``last_plus_text`` on the trained joint backbone does not beat it on every random-init backbone,
same-seed and cross-seed, nine of nine, then whatever the read-out harvests is the tokens'
embeddings rather than the pretraining, and H1' is NOT EVALUABLE. B1's numbers are still
computed and reported in that case — as measured, with no verdict attached.

**Rows, in the brief's order.**

- **G**, the gate: Δ((d)-joint seed *j* − (d)-random seed *k*) for all nine pairs.
- **B1**, the H1' row: Δ((d)-joint − ``tel_only`` (a)), same seed, under ADR-0026 §4.
- **B2**: Δ((d)-joint − (d)-control), same seed.
- **B3**: Δ((b)-joint − (a)-joint), same seed.
- **B4**: Δ((d)-joint − the status-only order-blind classifier), paired, per seed.
- **B5**: the has-status and no-status strata of the R0 windows, with base rates.
- **B6**: selected against final, from the probe records only. **No selected checkpoint is
  scored**: ADR-0026 registered ``final_step``, and this step scores nothing.
- **B7**: Δ((d)-control − (d)-random), same seed, for the record.

**Resume is per artefact**, as F6-3's is: each replicate vector is cached as it completes and
each row's JSON is written from the cached vectors.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from faultline.config import config_hash
from faultline.data.common.report import kv_table, table
from faultline.evaluation.axis_gate import ADR_0009_CAVEAT, IN_DISTRIBUTION
from faultline.evaluation.bootstrap import DeltaInterval
from faultline.evaluation.h1_verdict import (
    CAVEATS,
    FIXED_FINAL_OUTCOME,
    FORWARD_SAME_SITES,
    MESSAGE_VOLUME_CAVEAT,
    H1Verdict,
    ReplicateJob,
    decide_h1,
    delta_interval,
    run_job,
    single_interval,
    stratum,
)
from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.readout_runs import ReadoutLayout, readout_layout
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

#: ADR-0026's registration commit and the commit that recorded its hash.
ADR_0026_REGISTERED = "319ae3b"
ADR_0026_HASH_COMMIT = "ce0eb5a"

#: Where F6-1b's order-blind classifiers live, and the scoring this record reads from them.
BAG_DIR_GLOB = "bag_of_tokens_v1_*"
STATUS_ONLY_SCORES = "status_only_R0_stride{stride}_scores.npz"

#: ADR-0026 §4's sentence on a failed gate, written into that record before the gate was run.
GATE_FAILURE_SENTENCE = (
    "whatever (d) harvests is the tokens' embeddings, not the pretraining — a bag of text "
    "embeddings pushed through an untrained backbone already reads the status text"
)

#: Workers the bootstrap pool may use at once. F6-3's ``run_jobs`` sizes its pool by CPU count
#: alone (22 here). Under Windows' spawn start method every worker re-imports this package, which
#: pulls in torch and costs about 0.6 GB of resident memory before a single replicate is drawn, so
#: 22 workers ask for roughly 13 GB and the pool is killed mid-run. The cap is a memory guard and
#: nothing else: each job is independent and deterministic, :func:`run_job` is F6-3's unchanged,
#: and the cached vectors a capped pool writes are identical to the ones an uncapped pool would.
MAX_BOOTSTRAP_WORKERS = int(os.environ.get("FAULTLINE_BOOTSTRAP_WORKERS", "8"))


def run_capped_jobs(jobs: list[ReplicateJob], max_workers: int) -> list[Path]:
    """Every missing replicate vector, on a pool no wider than the machine's memory allows.

    This is F6-3's ``run_jobs`` with its pool width capped; the work each worker does is
    :func:`faultline.evaluation.h1_verdict.run_job`, unchanged, so the vectors written here are
    the ones that function has always written.

    Args:
        jobs: The replicate vectors still to compute.
        max_workers: The widest pool allowed.

    Returns:
        The vectors written, in completion order.
    """
    if not jobs:
        return []
    workers = max(1, min(len(jobs), (os.cpu_count() or 2) - 2, max_workers))
    logger.info("bootstrapping %d replicate vectors on %d worker processes", len(jobs), workers)
    written: list[Path] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_job, job) for job in jobs]
        for future in as_completed(futures):
            written.append(future.result())
            logger.info("replicates written: %s (%d/%d)", written[-1].name, len(written), len(jobs))
    return written


#: Why no selected-step read exists on the test split for any F7' probe (ADR-0026 §2, §4).
SELECTED_NOT_SCORED = (
    "Test-split selected-step reads were not produced for F7'. ADR-0026 §2 registered the "
    "final-step probe under ADR-0022's addendum, and F7'-3 scores nothing: producing them would "
    "be twelve further scorings of checkpoints the rule does not read. The selected checkpoints "
    "are saved beside the final ones and any later re-run can score them."
)


# =====================================================================================
# the scorers
# =====================================================================================


def scorer_files(paths: ProjectPaths, layout: ReadoutLayout) -> dict[str, Path]:
    """Every scorer this record reads, by name; nothing here is recomputed.

    Args:
        paths: Resolved project paths.
        layout: F7's layout, which resolves the twelve read-out scorings.

    Returns:
        Per scorer name, the ``.npz`` its per-row scores are read from.

    Raises:
        FileNotFoundError: If F6-1b's status-only classifier was never scored.
    """
    short = {"R-joint-d": "d_joint", "R-joint-b": "b_joint", "R-ctrl-d": "d_ctrl"}
    short["R-rand-d"] = "d_rand"
    files = {f"{short[item.run]}_{item.seed}": layout.scores(item) for item in layout.plan}
    stride = layout.h1.gate.stride
    for seed in layout.config.rule.seeds:
        files[f"tel_only_{seed}"] = layout.h1.tel_only_scores(seed)
    for scoring in layout.h1.plan:
        if scoring.stage == "S1":
            files[f"a_joint_{scoring.seed}"] = layout.h1.scores(scoring)
    scores_name = STATUS_ONLY_SCORES.format(stride=stride)
    found = sorted(paths.checkpoints_dir.glob(f"{BAG_DIR_GLOB}/{scores_name}"))
    if not found:
        raise FileNotFoundError(
            "F6-1b's order-blind status-only classifier has no R0 scores under "
            f"checkpoints/{BAG_DIR_GLOB}"
        )
    files["status_only_bag"] = found[-1]
    return files


def assert_same_rows(files: dict[str, Path], windows: int, positives: int) -> ScoredWindows:
    """Refuse to pair anything until every file covers the registered rows, in order.

    Args:
        files: Per scorer name, its scores file.
        windows: The registered window count.
        positives: The registered positive count.

    Returns:
        The reference scoring every other was checked against.

    Raises:
        FileNotFoundError: If a scorer's file is missing.
        ValueError: If a scorer covers different rows, or the rows are not the registered ones.
    """
    missing = [name for name, path in files.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"not scored yet: {sorted(missing)}")
    reference = ScoredWindows.load(files["tel_only_1"])
    if (reference.labels.size, int(reference.labels.sum())) != (windows, positives):
        raise ValueError(
            f"the scored windows are not the registered {windows:,} / {positives:,}: "
            f"{reference.labels.size:,} / {int(reference.labels.sum()):,}"
        )
    for name, path in files.items():
        if not ScoredWindows.load(path).same_windows(reference):
            raise ValueError(f"{name} ({path.name}) does not cover F3's windows")
    return reference


# =====================================================================================
# the gate on the instrument (ADR-0026 §4)
# =====================================================================================


@dataclass(frozen=True)
class GateOutcome:
    """ADR-0026 §4's random-init gate on the instrument, applied.

    Attributes:
        passed: Whether every registered pair cleared the bound.
        comparisons: Pairs formed.
        cleared: Pairs whose trusted lower bound is strictly above the bound.
        lower_bound_above: The bound each lower bound had to exceed.
        untrusted: Pairs discarding more than the rule's share of replicates.
        weakest: The pair with the smallest lower bound, and that bound.
        reason: One sentence saying why.
    """

    passed: bool
    comparisons: int
    cleared: int
    lower_bound_above: float
    untrusted: list[str]
    weakest: tuple[str, float]
    reason: str


def decide_random_init_gate(
    pairs: dict[str, DeltaInterval],
    comparisons: int,
    lower_bound_above: float,
    max_discarded_share: float,
) -> GateOutcome:
    """Apply ADR-0026 §4's gate verbatim: nine of nine paired lower bounds strictly above zero.

    Args:
        pairs: Per ``joint<j>_rand<k>`` pair, the paired Δ(joint − random-init).
        comparisons: The number of pairs the gate registers.
        lower_bound_above: The bound every paired lower bound must strictly exceed.
        max_discarded_share: Above this discard share a pair is untrusted and cannot clear.

    Returns:
        The outcome.

    Raises:
        ValueError: If the pairs formed are not the registered number, which would mean the
            gate was read on a different comparison from the one ADR-0026 §4 names.
    """
    if len(pairs) != comparisons:
        raise ValueError(
            f"the gate registers {comparisons} comparisons, {len(pairs)} were formed: "
            f"{sorted(pairs)}"
        )
    untrusted = sorted(k for k, d in pairs.items() if d.discarded_share > max_discarded_share)
    cleared = sorted(
        k
        for k, d in pairs.items()
        if d.discarded_share <= max_discarded_share and d.low > lower_bound_above
    )
    weakest_key = min(pairs, key=lambda k: pairs[k].low)
    passed = len(cleared) == comparisons
    if passed:
        reason = (
            f"all {comparisons} of {comparisons} paired lower bounds are strictly above "
            f"{lower_bound_above:g}; the weakest is {pairs[weakest_key].low:+.4f} "
            f"({weakest_key.replace('_', ' vs ')})"
        )
    else:
        failed = sorted(set(pairs) - set(cleared))
        reason = (
            f"{len(cleared)} of {comparisons} paired lower bounds are strictly above "
            f"{lower_bound_above:g}; {len(failed)} are not ({', '.join(failed)}), the weakest "
            f"{pairs[weakest_key].low:+.4f}"
        )
        if untrusted:
            reason += f"; untrusted (discard above {max_discarded_share:.0%}): {untrusted}"
    return GateOutcome(
        passed=passed,
        comparisons=comparisons,
        cleared=len(cleared),
        lower_bound_above=lower_bound_above,
        untrusted=untrusted,
        weakest=(weakest_key, pairs[weakest_key].low),
        reason=reason,
    )


# =====================================================================================
# the run
# =====================================================================================


def _json(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _strata_masks(layout: ReadoutLayout, rows: int) -> dict[str, np.ndarray]:
    """The has-status and no-status masks, F6-3's, fixed on the same R0 windows.

    Args:
        layout: F7's layout, whose H1 layout names F6-3's output directory.
        rows: Windows the masks must cover.

    Returns:
        Per stratum name, the mask over the scored windows.

    Raises:
        FileNotFoundError: If F6-3 never wrote the strata.
        ValueError: If the strata do not cover the scored windows.
    """
    strata_file = layout.h1.out_dir / "status_strata.npz"
    if not strata_file.is_file():
        raise FileNotFoundError(
            f"F6-3's status strata are missing ({strata_file}); F7' fixes its strata on the "
            "same R0 windows and does not re-frame them"
        )
    with np.load(strata_file) as data:
        has_status = data["has_status"].astype(bool)
    if has_status.size != rows:
        raise ValueError("the status strata do not cover the scored windows")
    return {
        "pooled": np.ones_like(has_status),
        "has_status": has_status,
        "no_status": ~has_status,
    }


def run_readout_verdict(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """Bootstrap F7's rows, gate the instrument, apply ADR-0026 §4 and write the report.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/eval/readout_v0.yaml``.

    Returns:
        The report and its JSON record.

    Raises:
        FileNotFoundError: If a scoring or a probe record is missing.
        ValueError: If a scoring does not cover F3's windows.
    """
    started = time.perf_counter()
    layout = readout_layout(paths, config_path)
    config = layout.config
    bootstrap = config.bootstrap
    seeds = config.rule.seeds
    out = layout.out_dir
    files = scorer_files(paths, layout)
    reference = assert_same_rows(files, config.windows, config.positives)
    masks = _strata_masks(layout, int(reference.labels.size))
    strata = {
        name: stratum(name, mask, reference, bootstrap.block_steps) for name, mask in masks.items()
    }

    # -- replicate vectors --------------------------------------------------------------------
    rep_dir = out / "replicates"
    rep_dir.mkdir(exist_ok=True)

    def vector(where: str, scorer: str) -> Path:
        return rep_dir / f"{where}__{scorer}.npz"

    wanted = [("pooled", name) for name in files]
    wanted += [
        (where, f"{prefix}_{seed}")
        for where in ("has_status", "no_status")
        for prefix in ("d_joint", "tel_only")
        for seed in seeds
    ]
    jobs = [
        ReplicateJob(vector(w, s), files[s], strata[w].mask, bootstrap)
        for w, s in wanted
        if not vector(w, s).exists()
    ]
    tick = time.perf_counter()
    computed = run_capped_jobs(jobs, MAX_BOOTSTRAP_WORKERS)
    bootstrap_seconds = time.perf_counter() - tick

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

    # -- G: the gate on the instrument, computed first ------------------------------------------
    gate_config = config.random_init_gate
    g_rows = {
        f"joint{j}_rand{k}": row(
            f"G_joint{j}_rand{k}",
            lambda a=j, b=k: asdict(paired(f"d_joint_{a}", f"d_rand_{b}")),
        )
        for j in seeds
        for k in seeds
    }
    gate_pairs = {k: DeltaInterval(**v) for k, v in g_rows.items()}
    gate = decide_random_init_gate(
        gate_pairs,
        gate_config.comparisons,
        gate_config.lower_bound_above,
        bootstrap.max_discarded_share,
    )
    logger.info("random-init gate: %s (%s)", "PASS" if gate.passed else "FAIL", gate.reason)

    # -- B1: H1', read only if the gate passed --------------------------------------------------
    b1 = {
        seed: row(
            f"B1_seed{seed}",
            lambda s=seed: {
                "d_joint": single(f"d_joint_{s}"),
                "tel_only": single(f"tel_only_{s}"),
                "delta": asdict(paired(f"d_joint_{s}", f"tel_only_{s}")),
            },
        )
        for seed in seeds
    }
    rule = config.rule
    measured = decide_h1(
        {s: DeltaInterval(**b1[s]["delta"]) for s in seeds},
        rule.smallest_effect,
        rule.supported_lower_bound_above,
        rule.supported_median_above,
        rule.refuted_upper_bound_below,
        bootstrap.max_discarded_share,
    )
    verdict = (
        measured
        if gate.passed
        else H1Verdict(
            verdict="NOT EVALUABLE",
            median_delta=measured.median_delta,
            lower_bounds_above_zero=measured.lower_bounds_above_zero,
            upper_bounds_below=measured.upper_bounds_below,
            trusted=measured.trusted,
            reason=(
                "the random-init gate on the instrument FAILED, so no Δ from the H1' rule is "
                f"reported as a verdict (ADR-0026 §4): {GATE_FAILURE_SENTENCE}"
            ),
        )
    )

    # -- B2 to B7 -------------------------------------------------------------------------------
    b2 = {
        seed: row(
            f"B2_seed{seed}",
            lambda s=seed: {
                "d_ctrl": single(f"d_ctrl_{s}"),
                "delta": asdict(paired(f"d_joint_{s}", f"d_ctrl_{s}")),
            },
        )
        for seed in seeds
    }
    b3 = {
        seed: row(
            f"B3_seed{seed}",
            lambda s=seed: {
                "b_joint": single(f"b_joint_{s}"),
                "a_joint": single(f"a_joint_{s}"),
                "delta": asdict(paired(f"b_joint_{s}", f"a_joint_{s}")),
            },
        )
        for seed in seeds
    }
    b4 = {
        seed: row(
            f"B4_seed{seed}",
            lambda s=seed: {
                "status_only_bag": single("status_only_bag"),
                "delta": asdict(paired(f"d_joint_{s}", "status_only_bag")),
            },
        )
        for seed in seeds
    }
    b5 = {
        seed: row(
            f"B5_seed{seed}",
            lambda s=seed: {
                where: {
                    "d_joint": single(f"d_joint_{s}", where),
                    "tel_only": single(f"tel_only_{s}", where),
                    "delta": asdict(paired(f"d_joint_{s}", f"tel_only_{s}", where)),
                }
                for where in ("has_status", "no_status")
            },
        )
        for seed in seeds
    }
    b7 = {
        seed: row(
            f"B7_seed{seed}",
            lambda s=seed: {
                "d_rand": single(f"d_rand_{s}"),
                "delta": asdict(paired(f"d_ctrl_{s}", f"d_rand_{s}")),
            },
        )
        for seed in seeds
    }

    # -- B6: the probe records only; nothing is scored ------------------------------------------
    records = {}
    for item in layout.plan:
        record_file = layout.probe_record(item)
        if not record_file.is_file():
            raise FileNotFoundError(f"missing probe record {record_file}")
        loaded = _json(record_file)
        records[f"{item.run}_{item.seed}"] = {
            "run": item.run,
            "readout": item.readout,
            "family": item.family,
            "seed": item.seed,
            "selected": loaded["selected"],
            "final": loaded["final"],
            "gap": float(loaded["final"][1] - loaded["selected"][1]),
        }

    # -- beside the rows --------------------------------------------------------------------------
    sidecars = {
        item.name: _json(layout.scores(item).with_suffix(".timing.json")) for item in layout.plan
    }
    probe_seconds = sum(float(_json(layout.probe_record(i))["seconds"]) for i in layout.plan)
    scoring_seconds = sum(float(v["seconds"]) for v in sidecars.values())
    status = _json(layout.status)
    checks = _json(out / "selection_check.json")
    random_init = _json(layout.random_record)
    gpu = {
        "probes_computed": len(status["probed_this_invocation"]),
        "scorings_computed": len(status["scored_this_invocation"]),
        "probes_total": status["probes_total"],
        "scorings_total": status["scorings_total"],
        "probe_seconds": probe_seconds,
        "scoring_seconds": scoring_seconds,
        "selection_check_seconds": sum(float(v["seconds"]) for v in checks.values()),
        "wall_hours": (probe_seconds + scoring_seconds) / 3600.0,
        "first_started_utc": min(v["started_utc"] for v in sidecars.values()),
        "last_finished_utc": max(v["finished_utc"] for v in sidecars.values()),
        "git_sha": sorted({str(v["git_sha"]) for v in sidecars.values()}),
        "tree_dirty": sorted({bool(v["tree_dirty"]) for v in sidecars.values()}),
    }
    payload: dict[str, Any] = {
        "config_hashes": {"configs/eval/readout_v0.yaml": config_hash(config)},
        "adr_0026": {
            "registered": ADR_0026_REGISTERED,
            "hash_commit": ADR_0026_HASH_COMMIT,
            "registered_in_config": config.registered_in,
        },
        "run_commit": gpu["git_sha"],
        "checkpoint_rule": rule.checkpoint,
        "strata": {
            k: {
                "windows": v.windows,
                "positives": v.positives,
                "blocks": v.blocks,
                "positive_blocks": v.positive_blocks,
            }
            for k, v in strata.items()
        },
        "scorers": {k: v.name for k, v in sorted(files.items())},
        "G": g_rows,
        "gate": asdict(gate),
        "B1": {str(s): v for s, v in b1.items()},
        "verdict": asdict(verdict),
        "measured_rule": asdict(measured),
        "B2": {str(s): v for s, v in b2.items()},
        "B3": {str(s): v for s, v in b3.items()},
        "B4": {str(s): v for s, v in b4.items()},
        "B5": {str(s): v for s, v in b5.items()},
        "B6": records,
        "B7": {str(s): v for s, v in b7.items()},
        "selected_not_scored": SELECTED_NOT_SCORED,
        "random_init_backbones": random_init["rows"],
        "selection_check": checks,
        "gpu": gpu,
        "cpu": {
            "replicate_vectors_computed": len(computed),
            "replicate_vectors_resumed": len(wanted) - len(computed),
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
    stem = f"readout_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    record = paths.data_reports_dir / f"{stem}.json"
    report.write_text(render_report(payload, seeds), encoding="utf-8", newline="\n")
    record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("H1' : %s (%s)", verdict.verdict, verdict.reason)
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


def _header(payload: dict[str, Any]) -> list[tuple[str, str]]:
    gpu, cpu = payload["gpu"], payload["cpu"]
    return [
        *[(f"configuration {k}", f"hash {v}") for k, v in payload["config_hashes"].items()],
        ("decision record", "docs/DECISIONS.md, ADR-0026 §4 (rule and gate), §2 (read-outs)"),
        ("ADR-0026 registered", payload["adr_0026"]["registered"]),
        ("ADR-0026 hash recorded", payload["adr_0026"]["hash_commit"]),
        ("run commit (F7'-2)", ", ".join(payload["run_commit"])),
        (
            "checkpoint rule",
            f"`{payload['checkpoint_rule']}`: every probe is read at its last step (ADR-0022 "
            f"addendum outcome {FIXED_FINAL_OUTCOME}); B6 reports validation values only",
        ),
        (
            "GPU wall clock",
            f"{gpu['wall_hours']:.2f} h: {gpu['probe_seconds'] / 3600:.2f} h over "
            f"{gpu['probes_total']} probes and {gpu['scoring_seconds'] / 3600:.2f} h over "
            f"{gpu['scorings_total']} scorings, all computed (none resumed), plus "
            f"{gpu['selection_check_seconds'] / 60:.1f} min selection re-checks; "
            f"{gpu['first_started_utc']} to {gpu['last_finished_utc']} UTC",
        ),
        (
            "scoring provenance",
            f"git {', '.join(payload['run_commit'])}; tree dirty {gpu['tree_dirty']}",
        ),
        (
            "CPU bootstrap",
            f"{cpu['replicate_vectors_computed']} replicate vectors computed, "
            f"{cpu['replicate_vectors_resumed']} resumed; "
            f"{cpu['seconds_this_invocation'] / 60:.1f} min this invocation",
        ),
        ("generated (UTC)", payload["generated_utc"]),
        ("git_sha", payload["git_sha"]),
        ("generated by", "faultline model readout-gate"),
    ]


def _gate_section(payload: dict[str, Any], seeds: list[int]) -> list[str]:
    gate, g = payload["gate"], payload["G"]
    rows = [
        [
            f"joint seed {j}",
            f"random-init seed {k}",
            f"{g[f'joint{j}_rand{k}']['first_auprc']:.4f}",
            f"{g[f'joint{j}_rand{k}']['second_auprc']:.4f}",
            _dv(g[f"joint{j}_rand{k}"]),
            "yes" if g[f"joint{j}_rand{k}"]["low"] > gate["lower_bound_above"] else "no",
            _disc(g[f"joint{j}_rand{k}"]),
            CAVEATS,
        ]
        for j in seeds
        for k in seeds
    ]
    return [
        "## " + "G -- the random-init gate on the instrument (computed first; it decides)",
        "",
        "ADR-0026 §4: `last_plus_text` on the trained joint backbone must exceed `last_plus_text` "
        "on every random-init backbone, same-seed and cross-seed -- all nine of nine paired lower "
        "bounds strictly above zero. The random-init backbones are ADR-0023's three saved ones, "
        "re-used rather than re-drawn. **This table is computed before B1, and H1' is read only "
        "if it passes.**",
        "",
        table(
            [
                "(d) trained",
                "(d) random init",
                "joint AUPRC",
                "random AUPRC",
                "paired Δ [95%]",
                "lower > 0",
                "discarded",
                "caveats",
            ],
            rows,
        ),
        "",
        f"> **Gate: {'PASS' if gate['passed'] else 'FAIL'}.** {gate['reason']}.",
        "",
    ]


def _b1_section(payload: dict[str, Any], seeds: list[int]) -> list[str]:
    b1, verdict, gate = payload["B1"], payload["verdict"], payload["gate"]
    evaluable = gate["passed"]
    heading = "B1 -- H1': Δ((d) last_plus_text on joint − tel_only (a)), same seed, R0, final step"
    lines = [
        "## " + heading,
        "",
        (
            "The reference side is ADR-0025 §5's unchanged `tel_only` final-step scores, so H1 "
            "and H1' differ in the instrument on the joint side and in nothing else."
        ),
        "",
    ]
    if not evaluable:
        lines += [
            "**The gate above FAILED, so these numbers carry no verdict.** They are reported as "
            "measured, under ADR-0026 §4's instruction that on a failed gate no Δ from the H1' "
            "rule is reported as a verdict. Every row below is labelled NOT EVALUABLE.",
            "",
        ]
    lines += [
        table(
            [
                "seed",
                "(d)-joint AUPRC [95%]",
                "tel_only (a) AUPRC [95%]",
                "paired Δ [95%]",
                "lower > 0",
                "upper < 0.005",
                "discarded",
                "status",
                "caveats",
            ],
            [
                [
                    str(s),
                    _iv(b1[str(s)]["d_joint"]),
                    _iv(b1[str(s)]["tel_only"]),
                    _dv(b1[str(s)]["delta"]),
                    "yes" if verdict["lower_bounds_above_zero"][s] else "no",
                    "yes" if verdict["upper_bounds_below"][s] else "no",
                    _disc(b1[str(s)]["delta"]),
                    "measured" if evaluable else "NOT EVALUABLE",
                    CAVEATS,
                ]
                for s in seeds
            ],
        ),
        "",
        f"Median of the three point Δ: **{verdict['median_delta']:+.4f}**.",
        "",
    ]
    return lines


def _reported_sections(payload: dict[str, Any], seeds: list[int]) -> list[str]:
    b2, b3, b4, b5, b7 = (payload[k] for k in ("B2", "B3", "B4", "B5", "B7"))
    b1, strata = payload["B1"], payload["strata"]
    lines = [
        "## " + "B2 -- (d)-joint against (d)-control, same seed",
        "",
        "Control (iii)'s `tel_only` backbones read through the same text-aware read-out: does "
        "joint pretraining matter once the text has a direct path to the head?",
        "",
        table(
            [
                "seed",
                "(d)-control AUPRC [95%]",
                "paired Δ((d)-joint − (d)-control) [95%]",
                "caveats",
            ],
            [[str(s), _iv(b2[str(s)]["d_ctrl"]), _dv(b2[str(s)]["delta"]), CAVEATS] for s in seeds],
        ),
        "",
        "## " + "B3 -- (b)-joint against (a)-joint, same seed",
        "",
        "What mean pooling alone buys, with no text-specific block. The (a) column is F6-3's B1 "
        "joint read, unchanged.",
        "",
        table(
            [
                "seed",
                "(b) mean_all AUPRC [95%]",
                "(a) final_position AUPRC [95%]",
                "paired Δ((b) − (a)) [95%]",
                "caveats",
            ],
            [
                [
                    str(s),
                    _iv(b3[str(s)]["b_joint"]),
                    _iv(b3[str(s)]["a_joint"]),
                    _dv(b3[str(s)]["delta"]),
                    CAVEATS,
                ]
                for s in seeds
            ],
        ),
        "",
        "## " + "B4 -- (d)-joint against the order-blind status-only classifier, paired",
        "",
        "Control (ii) of F6-1b: a histogram of the status strings, no order and no model, fitted "
        "on the R0 training windows and scored on the identical 137,025 rows. ADR-0026 §4: **if "
        "a linear read of the SLM's text-position states cannot match a histogram of the strings, "
        "the sequence model adds nothing over counting them.**",
        "",
        table(
            [
                "seed",
                "(d)-joint AUPRC [95%]",
                "status-only bag AUPRC [95%]",
                "paired Δ((d)-joint − bag) [95%]",
                "caveats",
            ],
            [
                [
                    str(s),
                    _iv(b1[str(s)]["d_joint"]),
                    _iv(b4[str(s)]["status_only_bag"]),
                    _dv(b4[str(s)]["delta"]),
                    CAVEATS,
                ]
                for s in seeds
            ],
        ),
        "",
        "## " + "B5 -- (d)-joint within the has-status and no-status strata of the R0 windows",
        "",
        "A window is has-status if its ADR-0025 §2 window holds at least one status token; the "
        "strata are F6-3's, fixed on the same windows. Blocks are re-formed within each stratum.",
        "",
        table(
            [
                "seed",
                "stratum",
                "windows / positives",
                "base rate",
                "(d)-joint [95%]",
                "tel_only (a) [95%]",
                "paired Δ [95%]",
                "caveats",
            ],
            [
                [
                    str(s),
                    where.replace("_", "-"),
                    f"{strata[where]['windows']:,} / {strata[where]['positives']:,}",
                    f"{b5[str(s)][where]['d_joint']['base_rate']:.4f}",
                    _iv(b5[str(s)][where]["d_joint"]),
                    _iv(b5[str(s)][where]["tel_only"]),
                    _dv(b5[str(s)][where]["delta"]),
                    CAVEATS,
                ]
                for s in seeds
                for where in ("has_status", "no_status")
            ],
        ),
        "",
    ]
    lines += _b6_section(payload)
    lines += [
        "## " + "B7 -- (d)-control against (d)-random, same seed, for the record",
        "",
        "Whether a telemetry-only backbone's text rows -- collapsed, as F6-R found them -- read "
        "the text any better than an untrained one.",
        "",
        table(
            [
                "seed",
                "(d)-random AUPRC [95%]",
                "paired Δ((d)-control − (d)-random) [95%]",
                "caveats",
            ],
            [[str(s), _iv(b7[str(s)]["d_rand"]), _dv(b7[str(s)]["delta"]), CAVEATS] for s in seeds],
        ),
        "",
    ]
    return lines


def _b6_section(payload: dict[str, Any]) -> list[str]:
    records = payload["B6"]
    order = sorted(records, key=lambda k: (records[k]["run"], records[k]["seed"]))
    widest = sorted(order, key=lambda k: records[k]["gap"])[:2]
    named = " and ".join(
        f"**{records[k]['run']} seed {records[k]['seed']} {records[k]['gap']:+.4f}**"
        for k in widest
    )
    return [
        "## " + "B6 -- selected step against final step, validation split only",
        "",
        f"{SELECTED_NOT_SCORED} The fixed-final rule stays in force and reads the final step; "
        f"the widest validation gaps are {named}, and the rule reads the final value in both "
        "cases.",
        "",
        table(
            [
                "run",
                "read-out",
                "backbone",
                "seed",
                "selected step (validation AUPRC)",
                "final step (validation AUPRC)",
                "final − selected (validation)",
                "read under the rule",
                "caveats",
            ],
            [
                [
                    records[k]["run"],
                    records[k]["readout"],
                    records[k]["family"],
                    str(records[k]["seed"]),
                    f"{records[k]['selected'][0]} ({records[k]['selected'][1]:.4f})",
                    f"{records[k]['final'][0]} ({records[k]['final'][1]:.4f})",
                    f"{records[k]['gap']:+.4f}",
                    "final",
                    CAVEATS,
                ]
                for k in order
            ],
        ),
        "",
    ]


def render_report(payload: dict[str, Any], seeds: list[int]) -> str:
    """The F7' read-out report: header, G, B1-B7, then the gate result and the verdict.

    Args:
        payload: The record written beside the report.
        seeds: The seeds compared, in order.

    Returns:
        The Markdown report.
    """
    pooled, verdict, gate = payload["strata"]["pooled"], payload["verdict"], payload["gate"]
    b1 = payload["B1"]
    lines = [
        "# Read-outs: is the read-out the limit? (ADR-0026, F7'-3)",
        "",
        kv_table(dict(_header(payload))),
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
        "identical (turbine, year, end step) rows and identical replicates, and every single read "
        "carries its own unpaired 95% interval. Nothing in this report was trained or scored: "
        "every score file was read from disk.",
        "",
    ]
    lines += _gate_section(payload, seeds)
    lines += _b1_section(payload, seeds)
    lines += _reported_sections(payload, seeds)
    lines += [
        "## " + "The gate result and the verdict -- ADR-0026 §4",
        "",
        f"> **Random-init gate on the instrument: {'PASS' if gate['passed'] else 'FAIL'}.** "
        f"{gate['reason']}.",
        "",
        f"> **H1': {verdict['verdict']}.** {verdict['reason']}.",
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
        + (
            " Nothing in B2-B7 changes the verdict."
            if gate["passed"]
            else f" On a failed gate ADR-0026 §4 says: {GATE_FAILURE_SENTENCE}."
        ),
        "",
    ]
    return "\n".join(lines)
