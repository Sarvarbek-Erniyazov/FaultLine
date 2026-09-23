"""F8-3's CPU half: gate each ablation's instrument, apply ADR-0027 §5, report §6's rows.

Nothing is trained and nothing is scored here. The six ablation (d) scorings and the three raw
random-init (d) scorings are :mod:`faultline.evaluation.ablation_runs`'
(``checkpoints/ablation_arms_v0_<hash>``); ``joint``'s (d) scorings (``R-joint-d``) and the three
normalized random-init (d) scorings (``R-rand-d``) are F7'-2's; ``tel_only``'s (a) reference is
F3's final-step scores, unchanged from ADR-0025 §5; and the order-blind status-only classifier's
scores are F6-1b's. Every file is asserted to cover the same 137,025 rows in the same order before
any pairing.

**The bootstrap is ADR-0024's**, exactly as F6-3 and F7'-3 ran it: two-day blocks within each
shard, 10,000 replicates, seed 20260916, 95% percentile intervals, discard rule 1%. Each scorer's
replicate AUPRCs are computed **once** per stratum and cached, and every interval is derived from
those vectors, on :func:`faultline.evaluation.readout_verdict.run_capped_jobs`' memory-capped
pool.

**The gates are computed first, one per ablation** (ADR-0027 §4). ``joint_no_txt`` is gated
against ADR-0026's three normalized random-init (d) scorings, because it probes the same windows;
``joint_status_raw`` against the three new random-init (d) scorings on the raw windows. On FAIL
that ablation is NOT EVALUABLE and its sentence stays undecided; its B-rows are still computed
and labelled.

**Rows, in the brief's order.**

- **G**, per ablation: Δ(ablation (d) seed *j* − random-init (d) seed *k*), nine pairs.
- **B1**, per ablation: Δ(ablation (d) − ``joint`` (d)), same seed, under ADR-0027 §5.
- **B2**: Δ(ablation (d) − ``tel_only`` (a)), same seed, under ADR-0026's H1' rule unchanged — a
  replication of H1' with the component changed.
- **B3**: Δ(ablation (d) − the status-only order-blind classifier), paired, per seed.
- **B4**: the has-status and no-status strata of each ablation's own windows, Δ against
  ``joint`` (d) within each.
- **B5**: selected against final, from the nine probe records only; nothing is scored.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from faultline.config import config_hash
from faultline.data.common.report import kv_table, table
from faultline.evaluation.ablation_gate import AblationGateConfig, AblationRule
from faultline.evaluation.ablation_runs import (
    AblationLayout,
    _test_split,
    ablation_layout,
    open_inputs,
)
from faultline.evaluation.axis_gate import ADR_0009_CAVEAT, IN_DISTRIBUTION
from faultline.evaluation.bootstrap import DeltaInterval
from faultline.evaluation.h1_controls import per_window
from faultline.evaluation.h1_verdict import (
    CAVEATS,
    FIXED_FINAL_OUTCOME,
    FORWARD_SAME_SITES,
    MESSAGE_VOLUME_CAVEAT,
    ReplicateJob,
    decide_h1,
    delta_interval,
    single_interval,
    stratum,
)
from faultline.evaluation.readout_runs import readout_layout
from faultline.evaluation.readout_verdict import (
    BAG_DIR_GLOB,
    MAX_BOOTSTRAP_WORKERS,
    STATUS_ONLY_SCORES,
    assert_same_rows,
    decide_random_init_gate,
    run_capped_jobs,
)
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

#: ADR-0027's registration commit and the commit that recorded its hash.
ADR_0027_REGISTERED = "179d769"
ADR_0027_HASH_COMMIT = "37fbf74"

#: The F7' run whose (d) scorings are ``joint``'s reference side, and whose random-init (d)
#: scorings gate ``joint_no_txt`` (ADR-0027 §4, §5).
REFERENCE_RUN = "R-joint-d"
NORMALIZED_RANDOM_RUN = "R-rand-d"

#: What each ablation removes or changes, for B2's label.
COMPONENT = {
    "joint_no_txt": "the narrative corpus removed",
    "joint_status_raw": "status strings left in raw surface form",
}

#: The short form beside every raw row, in addition to :data:`CAVEATS`.
RAW_CAVEAT_SHORT = "raw truncation"

#: ADR-0027 §3's measured mean step difference among the differing windows, per site.
RAW_MEAN_FEWER_STEPS = {"kelmarsh": 1.54, "penmanshiel": 1.34}

#: ADR-0027 §5, the sentence on outcomes the clauses do not name.
NEITHER_READING = (
    "A comparison discarding >1% counts toward none; anything the clauses do not name is "
    "reported as measured and no clause is added afterwards."
)

#: ADR-0027 §5, stated before the run.
INCONCLUSIVE_FORESEEN = (
    "ADR-0027 §5 named INCONCLUSIVE as the most likely non-HURTS outcome before any arm was "
    "pretrained: paired Δ intervals in ADR-0026 were about 0.018 to 0.022 wide, and EQUIVALENT "
    "needs all three inside a 0.010-wide band. An INCONCLUSIVE result is not evidence that the "
    "component does not matter."
)

#: The alternatives each §1 sentence carries, struck by :func:`strike_bracket`.
BRACKET = "[does / does not measurably]"


# =====================================================================================
# the rule (ADR-0027 §5)
# =====================================================================================


@dataclass(frozen=True)
class AblationVerdict:
    """ADR-0027 §5, applied to one ablation's B1.

    Attributes:
        verdict: ``HURTS``, ``HELPS``, ``EQUIVALENT``, ``INCONCLUSIVE``, ``NOT EVALUABLE``, or
            ``REPORTED AS MEASURED`` when more than one clause holds, which §5 does not name.
        median_delta: The median of the three seeds' full-sample Δ.
        upper_below: Per seed, whether its trusted upper bound is below the HURTS line.
        lower_above: Per seed, whether its trusted lower bound is above the HELPS line.
        inside_band: Per seed, whether its trusted interval lies strictly inside the band.
        trusted: Per seed, whether its discard share is within the rule's.
        reason: One sentence saying why.
    """

    verdict: str
    median_delta: float
    upper_below: dict[int, bool]
    lower_above: dict[int, bool]
    inside_band: dict[int, bool]
    trusted: dict[int, bool]
    reason: str


def decide_ablation(
    deltas: dict[int, DeltaInterval], rule: AblationRule, max_discarded_share: float
) -> AblationVerdict:
    """Apply ADR-0027 §5's four clauses verbatim.

    HURTS if every paired upper bound is below zero and the median Δ is below −0.005. HELPS if
    every lower bound is above zero and the median exceeds +0.005. EQUIVALENT if every paired
    interval lies inside (−0.005, +0.005). Otherwise INCONCLUSIVE at this budget. A comparison
    discarding more than ``max_discarded_share`` counts toward none; an outcome the clauses do not
    name (two holding at once) is reported as measured.

    Args:
        deltas: Per seed, the paired Δ(ablation (d) − ``joint`` (d)).
        rule: The registered rule, read from the configuration.
        max_discarded_share: Above this share of discarded replicates, a seed counts toward none.

    Returns:
        The verdict.
    """
    band_low, band_high = rule.equivalent_interval_within
    trusted = {s: d.discarded_share <= max_discarded_share for s, d in deltas.items()}
    upper = {s: trusted[s] and d.high < rule.hurts_upper_bound_below for s, d in deltas.items()}
    lower = {s: trusted[s] and d.low > rule.helps_lower_bound_above for s, d in deltas.items()}
    inside = {s: trusted[s] and band_low < d.low and d.high < band_high for s, d in deltas.items()}
    median = float(statistics.median(d.delta for d in deltas.values()))
    held = {
        "HURTS": all(upper.values()) and median < rule.hurts_median_below,
        "HELPS": all(lower.values()) and median > rule.helps_median_above,
        "EQUIVALENT": all(inside.values()),
    }
    met = [name for name, ok in held.items() if ok]
    if len(met) > 1:
        verdict = "REPORTED AS MEASURED"
        reason = f"clauses {met} hold together; §5 names no such outcome, reported as measured"
    elif met == ["HURTS"]:
        verdict = "HURTS"
        reason = (
            f"every paired upper bound is below {rule.hurts_upper_bound_below:g} and the median "
            f"Δ {median:+.4f} is below {rule.hurts_median_below:+g}"
        )
    elif met == ["HELPS"]:
        verdict = "HELPS"
        reason = (
            f"every paired lower bound is above {rule.helps_lower_bound_above:g} and the median "
            f"Δ {median:+.4f} exceeds {rule.helps_median_above:+g}"
        )
    elif met == ["EQUIVALENT"]:
        verdict = "EQUIVALENT"
        reason = f"every paired interval lies inside ({band_low:+g}, {band_high:+g})"
    else:
        verdict = "INCONCLUSIVE"
        reason = "; ".join(
            _misses(upper, lower, inside, trusted, median, rule, max_discarded_share)
        )
    return AblationVerdict(
        verdict=verdict,
        median_delta=median,
        upper_below=upper,
        lower_above=lower,
        inside_band=inside,
        trusted=trusted,
        reason=reason,
    )


def _misses(
    upper: dict[int, bool],
    lower: dict[int, bool],
    inside: dict[int, bool],
    trusted: dict[int, bool],
    median: float,
    rule: AblationRule,
    max_discarded_share: float,
) -> list[str]:
    """Why each of the three named clauses failed, in §5's order."""
    band_low, band_high = rule.equivalent_interval_within
    hurts = [s for s, ok in upper.items() if not ok]
    helps = [s for s, ok in lower.items() if not ok]
    parts = []
    if hurts:
        parts.append(
            f"HURTS fails: seed(s) {hurts} have an upper bound not below "
            f"{rule.hurts_upper_bound_below:g}"
        )
    else:
        parts.append(
            f"HURTS fails: the median Δ {median:+.4f} is not below {rule.hurts_median_below:+g}"
        )
    if helps:
        parts.append(
            f"HELPS fails: seed(s) {helps} have a lower bound not above "
            f"{rule.helps_lower_bound_above:g}"
        )
    else:
        parts.append(
            f"HELPS fails: the median Δ {median:+.4f} does not exceed {rule.helps_median_above:+g}"
        )
    outside = [s for s, ok in inside.items() if not ok]
    parts.append(
        f"EQUIVALENT fails: seed(s) {outside} have an interval not inside "
        f"({band_low:+g}, {band_high:+g})"
    )
    untrusted = [s for s, ok in trusted.items() if not ok]
    if untrusted:
        parts.append(f"seed(s) {untrusted} discard more than {max_discarded_share:.0%}")
    return parts


def strike_bracket(sentence: str, verdict: str) -> str | None:
    """The §1 sentence with one bracket struck as §5 maps the verdict, or None if undecided.

    HURTS strikes to "does" ("does matter" / "does contribute"); EQUIVALENT to "does not
    measurably". Every other verdict strikes neither bracket.

    Args:
        sentence: The registered sentence, carrying :data:`BRACKET` once.
        verdict: The ablation's verdict.

    Returns:
        The struck sentence, or None.

    Raises:
        ValueError: If the sentence does not carry the registered alternatives exactly once.
    """
    if sentence.count(BRACKET) != 1:
        raise ValueError(f"the sentence does not carry {BRACKET!r} exactly once: {sentence!r}")
    struck = {"HURTS": "does", "EQUIVALENT": "does not measurably"}.get(verdict)
    return None if struck is None else sentence.replace(BRACKET, struck)


def sentence_outcome(sentence: str, verdict: AblationVerdict) -> str:
    """What the write-up may now say for one ablation, in §5's mapping."""
    struck = strike_bracket(sentence, verdict.verdict)
    if struck is not None:
        return f'licensed: *"{struck}"*'
    if verdict.verdict == "HELPS":
        return (
            f"reported as measured -- the ablation reads **higher** than `joint` (median Δ "
            f"{verdict.median_delta:+.4f}); neither bracket is struck, because the sentence was "
            "not written to be read in that direction"
        )
    return f"**undecided** ({verdict.verdict})"


# =====================================================================================
# the scorers
# =====================================================================================


def scorer_files(paths: ProjectPaths, layout: AblationLayout) -> dict[str, Path]:
    """Every scorer this record reads, by name; nothing here is recomputed.

    Args:
        paths: Resolved project paths.
        layout: F8-2's layout, which resolves the nine ablation scorings and ``joint``'s (d).

    Returns:
        Per scorer name, the ``.npz`` its per-row scores are read from.

    Raises:
        FileNotFoundError: If F6-1b's status-only classifier was never scored.
    """
    files: dict[str, Path] = {}
    for item in layout.plan:
        prefix = f"random_init_{item.convention}" if item.is_random_init else item.arm
        files[f"{prefix}_{item.seed}"] = layout.scores(item)
    readout = readout_layout(paths, paths.repo_root / layout.gate.readout_config)
    for probe in readout.plan:
        if probe.run in (REFERENCE_RUN, NORMALIZED_RANDOM_RUN):
            files[f"{probe.run}_{probe.seed}"] = readout.scores(probe)
    for seed in layout.gate.comparison.seeds:
        files[f"tel_only_{seed}"] = layout.h1.tel_only_scores(seed)
    scores_name = STATUS_ONLY_SCORES.format(stride=layout.stride)
    found = sorted(paths.checkpoints_dir.glob(f"{BAG_DIR_GLOB}/{scores_name}"))
    if not found:
        raise FileNotFoundError(
            "F6-1b's order-blind status-only classifier has no R0 scores under "
            f"checkpoints/{BAG_DIR_GLOB}"
        )
    files["status_only_bag"] = found[-1]
    return files


def random_prefix(gate: AblationGateConfig, arm: str) -> str:
    """The scorer prefix of the random-init (d) scorings that gate one ablation (§4)."""
    source = {s.arm: s.source for s in gate.instrument_gate.random_init_scores}[arm]
    if source == "adr_0026_r_rand_d":
        return NORMALIZED_RANDOM_RUN
    return "random_init_raw"


# =====================================================================================
# the strata
# =====================================================================================


def status_masks(
    paths: ProjectPaths, layout: AblationLayout, rows: int
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, Any]]:
    """Per convention, the has-status and no-status masks of that convention's own windows.

    The normalized masks are F6-3's, fixed on the R0 windows ``joint`` and ``joint_no_txt`` are
    scored on. The raw masks are measured here on the raw-framed windows (CPU, seconds) and cached
    beside the scorings, because the raw arm's strata are those of its own windows (ADR-0027 §6).

    Args:
        paths: Resolved project paths.
        layout: F8-2's layout.
        rows: Windows the masks must cover.

    Returns:
        Per convention, per stratum name, the mask; and a record of how the two compare.

    Raises:
        FileNotFoundError: If F6-3 never wrote the normalized strata.
        ValueError: If a mask does not cover the scored windows.
    """
    strata_file = layout.h1.out_dir / "status_strata.npz"
    if not strata_file.is_file():
        raise FileNotFoundError(f"F6-3's status strata are missing ({strata_file})")
    with np.load(strata_file) as data:
        normalized = data["has_status"].astype(bool)
    raw_file = layout.out_dir / "raw_status_strata.npz"
    if not raw_file.is_file():
        inputs = open_inputs(paths, layout, "cpu")
        measured = per_window(_test_split(inputs["raw"], layout), "status_tokens") > 0
        partial = raw_file.with_name(raw_file.stem + ".partial.npz")
        np.savez(partial, has_status=measured)
        partial.replace(raw_file)
    with np.load(raw_file) as data:
        raw = data["has_status"].astype(bool)
    if normalized.size != rows or raw.size != rows:
        raise ValueError("the status strata do not cover the scored windows")
    masks = {
        convention: {"has_status": has, "no_status": ~has}
        for convention, has in (("normalized", normalized), ("raw", raw))
    }
    comparison = {
        "normalized_has_status": int(normalized.sum()),
        "raw_has_status": int(raw.sum()),
        "rows_differing": int((normalized != raw).sum()),
    }
    return masks, comparison


def stratum_name(where: str, convention: str, identical: bool) -> str:
    """A stratum's cache name: the raw strata share the normalized ones' when row-identical."""
    return where if convention == "normalized" or identical else f"{where}_raw"


# =====================================================================================
# the run
# =====================================================================================


def _json(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def run_ablation_verdict(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """Bootstrap F8's rows, gate each instrument, apply ADR-0027 §5 and write the report.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/eval/ablation_gate_v0.yaml``.

    Returns:
        The report and its JSON record.

    Raises:
        FileNotFoundError: If a scoring or a probe record is missing.
        ValueError: If a scoring does not cover the registered windows.
    """
    started = time.perf_counter()
    layout = ablation_layout(paths, config_path)
    gate_config = layout.gate
    bootstrap = gate_config.bootstrap
    seeds = gate_config.comparison.seeds
    arms = gate_config.comparison.arms
    conventions = {arm.name: arm.status_convention for arm in layout.mixture.arms}
    out = layout.out_dir
    files = scorer_files(paths, layout)
    reference = assert_same_rows(files, gate_config.windows, gate_config.positives)
    masks, strata_comparison = status_masks(paths, layout, int(reference.labels.size))
    identical = strata_comparison["rows_differing"] == 0
    everything = np.ones_like(masks["normalized"]["has_status"])
    strata = {"pooled": stratum("pooled", everything, reference, bootstrap.block_steps)}
    for convention in ("normalized", "raw"):
        for where, mask in masks[convention].items():
            name = stratum_name(where, convention, identical)
            if name not in strata:
                strata[name] = stratum(name, mask, reference, bootstrap.block_steps)

    def where_for(arm: str, where: str) -> str:
        return stratum_name(where, conventions[arm], identical)

    # -- replicate vectors --------------------------------------------------------------------
    rep_dir = out / "replicates"
    rep_dir.mkdir(exist_ok=True)

    def vector(where: str, scorer: str) -> Path:
        return rep_dir / f"{where}__{scorer}.npz"

    wanted = [("pooled", name) for name in files]
    for arm in arms:
        for where in ("has_status", "no_status"):
            for seed in seeds:
                for scorer in (f"{arm}_{seed}", f"{REFERENCE_RUN}_{seed}"):
                    pair = (where_for(arm, where), scorer)
                    if pair not in wanted:
                        wanted.append(pair)
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

    # -- G: the two instrument gates, computed first -------------------------------------------
    instrument = gate_config.instrument_gate
    g_rows: dict[str, dict[str, Any]] = {}
    gates: dict[str, Any] = {}
    for arm in arms:
        rand = random_prefix(gate_config, arm)
        g_rows[arm] = {
            f"seed{j}_rand{k}": row(
                f"G_{arm}_seed{j}_rand{k}",
                lambda a=arm, j=j, k=k, r=rand: {
                    "ablation": single(f"{a}_{j}"),
                    "random_init": single(f"{r}_{k}"),
                    "delta": asdict(paired(f"{a}_{j}", f"{r}_{k}")),
                },
            )
            for j in seeds
            for k in seeds
        }
        gates[arm] = decide_random_init_gate(
            {k: DeltaInterval(**v["delta"]) for k, v in g_rows[arm].items()},
            instrument.comparisons,
            instrument.lower_bound_above,
            bootstrap.max_discarded_share,
        )
        logger.info(
            "%s instrument gate: %s (%s)",
            arm,
            "PASS" if gates[arm].passed else "FAIL",
            gates[arm].reason,
        )

    # -- B1: the §5 rule, per ablation -----------------------------------------------------------
    b1: dict[str, dict[str, Any]] = {}
    verdicts: dict[str, AblationVerdict] = {}
    measured: dict[str, AblationVerdict] = {}
    for arm in arms:
        b1[arm] = {
            str(seed): row(
                f"B1_{arm}_seed{seed}",
                lambda a=arm, s=seed: {
                    "ablation": single(f"{a}_{s}"),
                    "joint_d": single(f"{REFERENCE_RUN}_{s}"),
                    "delta": asdict(paired(f"{a}_{s}", f"{REFERENCE_RUN}_{s}")),
                },
            )
            for seed in seeds
        }
        measured[arm] = decide_ablation(
            {s: DeltaInterval(**b1[arm][str(s)]["delta"]) for s in seeds},
            gate_config.rule,
            bootstrap.max_discarded_share,
        )
        verdicts[arm] = (
            measured[arm]
            if gates[arm].passed
            else AblationVerdict(
                **{
                    **asdict(measured[arm]),
                    "verdict": "NOT EVALUABLE",
                    "reason": (
                        "the instrument gate FAILED on this arm's windows, so no Δ from the §5 "
                        "rule is read as a verdict (ADR-0027 §4); the sentence stays undecided"
                    ),
                }
            )
        )
        logger.info("%s: %s (%s)", arm, verdicts[arm].verdict, verdicts[arm].reason)

    # -- B2 to B4 --------------------------------------------------------------------------------
    readout_rule = layout.readout.rule
    b2: dict[str, dict[str, Any]] = {}
    b2_rule: dict[str, Any] = {}
    for arm in arms:
        b2[arm] = {
            str(seed): row(
                f"B2_{arm}_seed{seed}",
                lambda a=arm, s=seed: {
                    "tel_only": single(f"tel_only_{s}"),
                    "delta": asdict(paired(f"{a}_{s}", f"tel_only_{s}")),
                },
            )
            for seed in seeds
        }
        b2_rule[arm] = asdict(
            decide_h1(
                {s: DeltaInterval(**b2[arm][str(s)]["delta"]) for s in seeds},
                readout_rule.smallest_effect,
                readout_rule.supported_lower_bound_above,
                readout_rule.supported_median_above,
                readout_rule.refuted_upper_bound_below,
                bootstrap.max_discarded_share,
            )
        )
    b3 = {
        arm: {
            str(seed): row(
                f"B3_{arm}_seed{seed}",
                lambda a=arm, s=seed: {
                    "status_only_bag": single("status_only_bag"),
                    "delta": asdict(paired(f"{a}_{s}", "status_only_bag")),
                },
            )
            for seed in seeds
        }
        for arm in arms
    }
    b4 = {
        arm: {
            str(seed): row(
                f"B4_{arm}_seed{seed}",
                lambda a=arm, s=seed: {
                    where: {
                        "ablation": single(f"{a}_{s}", where_for(a, where)),
                        "joint_d": single(f"{REFERENCE_RUN}_{s}", where_for(a, where)),
                        "delta": asdict(
                            paired(f"{a}_{s}", f"{REFERENCE_RUN}_{s}", where_for(a, where))
                        ),
                    }
                    for where in ("has_status", "no_status")
                },
            )
            for seed in seeds
        }
        for arm in arms
    }

    # -- B5: the probe records only; nothing is scored ------------------------------------------
    records = {}
    for item in layout.plan:
        loaded = _json(layout.probe_record(item))
        records[item.name] = {
            "arm": item.arm,
            "family": item.family,
            "convention": item.convention,
            "seed": item.seed,
            "selected": loaded["selected"],
            "final": loaded["final"],
            "gap": float(loaded["final"][1] - loaded["selected"][1]),
        }

    # -- the sentences --------------------------------------------------------------------------
    sentences = {s.arm: s.sentence for s in gate_config.sentences}
    outcomes = {
        arm: {
            "registered": sentences[arm],
            "struck": strike_bracket(sentences[arm], verdicts[arm].verdict),
            "outcome": sentence_outcome(sentences[arm], verdicts[arm]),
        }
        for arm in arms
    }

    payload: dict[str, Any] = {
        "config_hashes": _config_hashes(layout),
        "adr_0027": {
            "registered": ADR_0027_REGISTERED,
            "hash_commit": ADR_0027_HASH_COMMIT,
            "registered_in_config": gate_config.registered_in,
        },
        "run_commit": _gpu(layout)["git_sha"],
        "checkpoint_rule": gate_config.comparison.checkpoint,
        "arms": arms,
        "conventions": {arm: conventions[arm] for arm in arms},
        "random_init_source": {arm: random_prefix(gate_config, arm) for arm in arms},
        "strata": {
            k: {
                "windows": v.windows,
                "positives": v.positives,
                "blocks": v.blocks,
                "positive_blocks": v.positive_blocks,
            }
            for k, v in strata.items()
        },
        "strata_comparison": strata_comparison,
        "scorers": {k: v.relative_to(paths.repo_root).as_posix() for k, v in sorted(files.items())},
        "G": g_rows,
        "gates": {arm: asdict(g) for arm, g in gates.items()},
        "B1": b1,
        "verdicts": {arm: asdict(v) for arm, v in verdicts.items()},
        "measured_rule": {arm: asdict(v) for arm, v in measured.items()},
        "sentences": outcomes,
        "B2": b2,
        "B2_rule": b2_rule,
        "B3": b3,
        "B4": b4,
        "B5": records,
        "raw_truncation": _raw_truncation(layout),
        "gpu": _gpu(layout),
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
    # One key type throughout: the report renders from exactly what the record holds.
    payload = json.loads(json.dumps(payload))
    stem = f"ablation_gate_v{gate_config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    record = paths.data_reports_dir / f"{stem}.json"
    report.write_text(render_report(payload, seeds), encoding="utf-8", newline="\n")
    record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record)
    return report, record


def _config_hashes(layout: AblationLayout) -> dict[str, str]:
    return {
        "configs/eval/ablation_gate_v0.yaml": config_hash(layout.gate),
        layout.gate.runner_config: config_hash(layout.runner),
        layout.gate.mixture_config: config_hash(layout.mixture),
        layout.gate.readout_config: config_hash(layout.readout),
    }


def _raw_truncation(layout: AblationLayout) -> dict[str, Any]:
    """ADR-0027 §8's raw-only caveat, by value, from the runner and the F8-2 assertions."""
    rule = next(r for r in layout.runner.window_rule_per_arm if r.status_convention == "raw")
    measured = _json(layout.assertions_record)["raw_index"]
    windows, positives = layout.gate.windows, layout.gate.positives
    if (
        measured["windows_differing_in_steps_retained"],
        measured["positives_differing_in_steps_retained"],
    ) != (rule.windows_differing_in_steps_retained, rule.positives_differing_in_steps_retained):
        raise ValueError("F8-2's measured truncation is not the registered one")
    return {
        "windows": rule.windows_differing_in_steps_retained,
        "windows_share": rule.windows_differing_in_steps_retained / windows,
        "positives": rule.positives_differing_in_steps_retained,
        "positives_share": rule.positives_differing_in_steps_retained / positives,
        "mean_fewer_steps": RAW_MEAN_FEWER_STEPS,
    }


def _gpu(layout: AblationLayout) -> dict[str, Any]:
    """F8-2's GPU wall clock, from its records: pretrainings, probes and scorings."""
    runner = layout.runner
    lm = [_json(layout.lm_record(arm, seed)) for arm in runner.arms for seed in runner.seeds]
    probes = [_json(layout.probe_record(item)) for item in layout.plan]
    sidecars = [_json(layout.scores(item).with_suffix(".timing.json")) for item in layout.plan]
    status = _json(layout.status)
    pretrain = sum(float(r["seconds"]) for r in lm)
    probe = sum(float(r["seconds"]) for r in probes)
    scoring = sum(float(r["seconds"]) for r in sidecars)
    return {
        "pretrainings_computed": len(status["pretrained_this_invocation"]),
        "probes_computed": len(status["probed_this_invocation"]),
        "scorings_computed": len(status["scored_this_invocation"]),
        "pretrainings_total": len(lm),
        "probes_total": status["probes_total"],
        "scorings_total": status["scorings_total"],
        "pretrain_seconds": pretrain,
        "probe_seconds": probe,
        "scoring_seconds": scoring,
        "wall_hours": (pretrain + probe + scoring) / 3600.0,
        "first_started_utc": min(v["started_utc"] for v in sidecars),
        "last_finished_utc": max(v["finished_utc"] for v in sidecars),
        "git_sha": sorted({str(r["git_sha"]) for r in [*probes, *sidecars]}),
        "tree_dirty": sorted({bool(r["tree_dirty"]) for r in [*probes, *sidecars]}),
    }


# =====================================================================================
# the report
# =====================================================================================


def _iv(value: dict[str, Any]) -> str:
    return f"{value['auprc']:.4f} [{value['low']:.4f}, {value['high']:.4f}]"


def _dv(value: dict[str, Any]) -> str:
    return f"{value['delta']:+.4f} [{value['low']:+.4f}, {value['high']:+.4f}]"


def _disc(value: dict[str, Any]) -> str:
    return f"{value['discarded'] / value['replicates']:.2%}"


def _cav(payload: dict[str, Any], arm: str) -> str:
    raw = payload["conventions"][arm] == "raw"
    return f"{CAVEATS} · {RAW_CAVEAT_SHORT}" if raw else CAVEATS


def _raw_caveat_text(payload: dict[str, Any]) -> str:
    t = payload["raw_truncation"]
    means = t["mean_fewer_steps"]
    return (
        f"On every `joint_status_raw` row: raw casing changes token counts and therefore "
        f"truncation in the tail-anchored window -- **{t['windows']:,} of "
        f"{payload['strata']['pooled']['windows']:,} windows ({t['windows_share']:.2%}) and "
        f"{t['positives']:,} of {payload['strata']['pooled']['positives']:,} positives "
        f"({t['positives_share']:.2%}) retain a different number of telemetry steps** than the "
        f"normalized windows `joint` is scored on, on average ~1.5 fewer ({means['kelmarsh']} at "
        f"Kelmarsh, {means['penmanshiel']} at Penmanshiel; ADR-0027 §3). The two sides pair row "
        "for row on identical keys, but they do not see identical telemetry."
    )


def _header(payload: dict[str, Any]) -> list[tuple[str, str]]:
    gpu, cpu = payload["gpu"], payload["cpu"]
    return [
        *[(f"configuration {k}", f"hash {v}") for k, v in payload["config_hashes"].items()],
        ("decision record", "docs/DECISIONS.md, ADR-0027 §4 (gates), §5 (rule), §6 (reported)"),
        ("ADR-0027 registered", payload["adr_0027"]["registered"]),
        ("ADR-0027 hash recorded", payload["adr_0027"]["hash_commit"]),
        ("run commit (F8-2)", ", ".join(payload["run_commit"])),
        (
            "checkpoint rule",
            f"`{payload['checkpoint_rule']}`: every probe is read at its last step (ADR-0022 "
            f"addendum outcome {FIXED_FINAL_OUTCOME}); B5 reports validation values only",
        ),
        (
            "GPU wall clock (F8-2)",
            f"{gpu['wall_hours']:.2f} h, all computed (none resumed): "
            f"{gpu['pretrain_seconds'] / 3600:.2f} h over {gpu['pretrainings_total']} "
            f"pretrainings, {gpu['probe_seconds'] / 3600:.2f} h over {gpu['probes_total']} "
            f"probes, {gpu['scoring_seconds'] / 3600:.2f} h over {gpu['scorings_total']} scorings",
        ),
        (
            "scoring provenance",
            f"git {', '.join(payload['run_commit'])}; tree dirty {gpu['tree_dirty']}",
        ),
        (
            "CPU (this step)",
            f"{cpu['replicate_vectors_computed']} replicate vectors computed, "
            f"{cpu['replicate_vectors_resumed']} resumed; "
            f"{cpu['bootstrap_seconds_this_invocation'] / 60:.1f} min bootstrap, "
            f"{cpu['seconds_this_invocation'] / 60:.1f} min this invocation",
        ),
        ("generated (UTC)", payload["generated_utc"]),
        ("git_sha", payload["git_sha"]),
        ("generated by", "faultline model ablation-gate"),
    ]


def _gate_section(payload: dict[str, Any], seeds: list[int]) -> list[str]:
    lines = [
        "## G -- the two instrument gates (computed first; each decides whether its arm is read)",
        "",
        "ADR-0027 §4: (d) on each ablation backbone must exceed (d) on every random-init "
        "backbone, same-seed and cross-seed -- nine of nine paired lower bounds strictly above "
        "zero, on the ablation's own windows. `joint_no_txt` is gated against ADR-0026's three "
        "normalized random-init (d) scorings (`R-rand-d`), because it probes the same windows; "
        "`joint_status_raw` against three new random-init (d) probes on the raw windows, over "
        "the same saved random-init backbones.",
        "",
    ]
    for arm in payload["arms"]:
        g, gate = payload["G"][arm], payload["gates"][arm]
        source = payload["random_init_source"][arm]
        lines += [
            f"### {arm} -- against `{source}`",
            "",
            table(
                [
                    "ablation (d)",
                    "random-init (d)",
                    "ablation AUPRC [95%]",
                    "random-init AUPRC [95%]",
                    "paired Δ [95%]",
                    "lower > 0",
                    "discarded",
                    "caveats",
                ],
                [
                    [
                        f"seed {j}",
                        f"seed {k}",
                        _iv(g[f"seed{j}_rand{k}"]["ablation"]),
                        _iv(g[f"seed{j}_rand{k}"]["random_init"]),
                        _dv(g[f"seed{j}_rand{k}"]["delta"]),
                        "yes"
                        if g[f"seed{j}_rand{k}"]["delta"]["low"] > gate["lower_bound_above"]
                        else "no",
                        _disc(g[f"seed{j}_rand{k}"]["delta"]),
                        _cav(payload, arm),
                    ]
                    for j in seeds
                    for k in seeds
                ],
            ),
            "",
            f"> **{arm} gate: {'PASS' if gate['passed'] else 'FAIL'}.** {gate['reason']}.",
            "",
        ]
    return lines


def _b1_section(payload: dict[str, Any], seeds: list[int]) -> list[str]:
    lines = [
        "## B1 -- the §5 primary rule: Δ(ablation (d) − joint (d)), same seed, R0, final step",
        "",
        "The reference side is `joint` read through **(d)** -- F7'-2's `R-joint-d` scorings, not "
        "`joint` under (a). HURTS if all three paired upper bounds are below zero and the median "
        "Δ is below −0.005; HELPS if all three lower bounds are above zero and the median exceeds "
        "+0.005; EQUIVALENT if all three paired intervals lie inside (−0.005, +0.005); otherwise "
        f"INCONCLUSIVE at this budget. {NEITHER_READING}",
        "",
    ]
    for arm in payload["arms"]:
        b1, verdict = payload["B1"][arm], payload["verdicts"][arm]
        evaluable = payload["gates"][arm]["passed"]
        lines += [f"### {arm}", ""]
        if payload["conventions"][arm] == "raw":
            lines += [
                "The pairing is row for row on identical (turbine, year, end step) keys and "
                "identical labels; the input tokens differ, by design -- the raw arm is probed "
                "and scored on its own raw-cased windows, `joint` on the normalized ones.",
                "",
            ]
        if not evaluable:
            lines += [
                "**This arm's gate FAILED: the numbers below carry no verdict** and are "
                "labelled NOT EVALUABLE.",
                "",
            ]
        lines += [
            table(
                [
                    "seed",
                    "ablation (d) AUPRC [95%]",
                    "joint (d) AUPRC [95%]",
                    "paired Δ [95%]",
                    "upper < 0",
                    "lower > 0",
                    "inside ±0.005",
                    "discarded",
                    "status",
                    "caveats",
                ],
                [
                    [
                        str(s),
                        _iv(b1[str(s)]["ablation"]),
                        _iv(b1[str(s)]["joint_d"]),
                        _dv(b1[str(s)]["delta"]),
                        "yes" if verdict["upper_below"][str(s)] else "no",
                        "yes" if verdict["lower_above"][str(s)] else "no",
                        "yes" if verdict["inside_band"][str(s)] else "no",
                        _disc(b1[str(s)]["delta"]),
                        "measured" if evaluable else "NOT EVALUABLE",
                        _cav(payload, arm),
                    ]
                    for s in seeds
                ],
            ),
            "",
            f"Median of the three point Δ: **{verdict['median_delta']:+.4f}**. "
            f"**{verdict['verdict']}**: {verdict['reason']}.",
            "",
        ]
    return lines


def _reported_sections(payload: dict[str, Any], seeds: list[int]) -> list[str]:
    lines = [
        "## B2 -- reported: each ablation (d) against tel_only (a), same seed, H1''s rule",
        "",
        "ADR-0026's H1' rule applied unchanged (SUPPORTED: every lower bound > 0 and median > "
        "+0.005; REFUTED: every upper bound < +0.005), against ADR-0025 §5's saved `tel_only` "
        "final-step scores. **Each row is a replication of H1' with the component changed**; it "
        "decides nothing.",
        "",
        table(
            [
                "arm",
                "seed",
                "ablation (d) AUPRC [95%]",
                "tel_only (a) AUPRC [95%]",
                "paired Δ [95%]",
                "H1' rule, replicated",
                "caveats",
            ],
            [
                [
                    f"{arm} ({COMPONENT[arm]})",
                    str(s),
                    _iv(payload["B1"][arm][str(s)]["ablation"]),
                    _iv(payload["B2"][arm][str(s)]["tel_only"]),
                    _dv(payload["B2"][arm][str(s)]["delta"]),
                    f"{payload['B2_rule'][arm]['verdict']} (median "
                    f"{payload['B2_rule'][arm]['median_delta']:+.4f})",
                    _cav(payload, arm),
                ]
                for arm in payload["arms"]
                for s in seeds
            ],
        ),
        "",
        "## B3 -- reported: each ablation (d) against the order-blind status-only classifier",
        "",
        "Control (ii) of F6-1b, a histogram of the status strings with no order and no model, "
        "paired on the identical 137,025 rows. **For `joint_status_raw`, the classifier was fit "
        "on normalized strings and is reported as-is, not refit on raw**: the row compares a "
        "raw-diet backbone with a normalized-string histogram.",
        "",
        table(
            [
                "arm",
                "seed",
                "ablation (d) AUPRC [95%]",
                "status-only bag AUPRC [95%]",
                "paired Δ(ablation − bag) [95%]",
                "caveats",
            ],
            [
                [
                    arm + (" (bag fit on normalized strings)" if arm.endswith("raw") else ""),
                    str(s),
                    _iv(payload["B1"][arm][str(s)]["ablation"]),
                    _iv(payload["B3"][arm][str(s)]["status_only_bag"]),
                    _dv(payload["B3"][arm][str(s)]["delta"]),
                    _cav(payload, arm),
                ]
                for arm in payload["arms"]
                for s in seeds
            ],
        ),
        "",
    ]
    lines += _b4_section(payload, seeds)
    lines += _b5_section(payload)
    return lines


def _b4_section(payload: dict[str, Any], seeds: list[int]) -> list[str]:
    comparison = payload["strata_comparison"]
    same = comparison["rows_differing"] == 0
    strata = payload["strata"]
    note = (
        f"The raw windows' has-status mask was measured on the raw-framed windows and is "
        f"**identical row for row** to the normalized one ({comparison['raw_has_status']:,} "
        "has-status windows under both; 0 rows differ), so both arms read the same strata."
        if same
        else f"The raw windows' has-status mask differs from the normalized one on "
        f"{comparison['rows_differing']:,} rows; each arm reads its own."
    )
    return [
        "## B4 -- reported: has-status and no-status strata, Δ against joint (d) within each",
        "",
        "A window is has-status if its window holds at least one status token. Blocks are "
        f"re-formed within each stratum. {note}",
        "",
        table(
            [
                "arm",
                "seed",
                "stratum",
                "windows / positives",
                "base rate",
                "ablation (d) [95%]",
                "joint (d) [95%]",
                "paired Δ [95%]",
                "caveats",
            ],
            [
                [
                    arm,
                    str(s),
                    where.replace("_", "-"),
                    f"{strata[where]['windows']:,} / {strata[where]['positives']:,}"
                    if same or payload["conventions"][arm] == "normalized"
                    else f"{strata[where + '_raw']['windows']:,} / "
                    f"{strata[where + '_raw']['positives']:,}",
                    f"{payload['B4'][arm][str(s)][where]['ablation']['base_rate']:.4f}",
                    _iv(payload["B4"][arm][str(s)][where]["ablation"]),
                    _iv(payload["B4"][arm][str(s)][where]["joint_d"]),
                    _dv(payload["B4"][arm][str(s)][where]["delta"]),
                    _cav(payload, arm),
                ]
                for arm in payload["arms"]
                for s in seeds
                for where in ("has_status", "no_status")
            ],
        ),
        "",
    ]


def _b5_section(payload: dict[str, Any]) -> list[str]:
    records = payload["B5"]
    order = list(records)
    widest = min(order, key=lambda k: records[k]["gap"])
    return [
        "## B5 -- reported: selected step against final step, validation split only",
        "",
        "From the nine probe records; nothing is scored. The fixed-final rule of ADR-0022's "
        "addendum stays in force and every row above reads the final step. The widest "
        f"validation gap is **{widest} {records[widest]['gap']:+.4f}**.",
        "",
        table(
            [
                "probe",
                "windows",
                "selected step (validation AUPRC)",
                "final step (validation AUPRC)",
                "final − selected",
                "read under the rule",
                "caveats",
            ],
            [
                [
                    k,
                    records[k]["convention"],
                    f"{records[k]['selected'][0]} ({records[k]['selected'][1]:.4f})",
                    f"{records[k]['final'][0]} ({records[k]['final'][1]:.4f})",
                    f"{records[k]['gap']:+.4f}",
                    "final",
                    f"{CAVEATS} · {RAW_CAVEAT_SHORT}"
                    if records[k]["convention"] == "raw"
                    else CAVEATS,
                ]
                for k in order
            ],
        ),
        "",
    ]


def render_report(payload: dict[str, Any], seeds: list[int]) -> str:
    """The F8 ablation report: header, G, B1-B5, then the two verdicts and their sentences.

    Args:
        payload: The record written beside the report.
        seeds: The seeds compared, in order.

    Returns:
        The Markdown report.
    """
    pooled = payload["strata"]["pooled"]
    lines = [
        "# Ablations: the narrative corpus and status surface form (ADR-0027, F8-3)",
        "",
        kv_table(dict(_header(payload))),
        "",
        "## Caveats carried on every row",
        "",
        f"The column **caveats** on every row stands for these three, in full: (1) ADR-0009: "
        f"{payload['caveats']['adr_0009']} (2) {payload['caveats']['in_distribution']} Every "
        f"row is {FORWARD_SAME_SITES}; none is a site-shift result. (3) "
        f"{payload['caveats']['message_volume']}",
        "",
        f"**{RAW_CAVEAT_SHORT}** (4): {_raw_caveat_text(payload)}",
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
    lines += ["## The two verdicts -- ADR-0027 §4 and §5", ""]
    for arm in payload["arms"]:
        gate, verdict = payload["gates"][arm], payload["verdicts"][arm]
        b1 = payload["B1"][arm]
        lines += [
            f"> **{arm}: gate {'PASS' if gate['passed'] else 'FAIL'}; §5 verdict "
            f"{verdict['verdict']}.** Median Δ {verdict['median_delta']:+.4f}; paired intervals "
            + "; ".join(f"seed {s} {_dv(b1[str(s)]['delta'])}" for s in seeds)
            + (
                "; no comparison discarded more than 1%."
                if all(verdict["trusted"].values())
                else "; untrusted seeds: "
                + str([s for s, ok in verdict["trusted"].items() if not ok])
                + "."
            ),
            ">",
            f'> Registered sentence: *"{payload["sentences"][arm]["registered"]}"* -- '
            f"{payload['sentences'][arm]['outcome']}.",
            "",
        ]
        if verdict["verdict"] == "INCONCLUSIVE":
            lines += [INCONCLUSIVE_FORESEEN, ""]
    lines += ["Nothing in B2-B5 changes either verdict.", ""]
    return "\n".join(lines)
