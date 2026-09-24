"""ADR-0028's numerics: the three-seed ensemble, its calibration, and its risk–coverage.

Nothing here reads a checkpoint or a configuration. Every function takes arrays, or an
:class:`Ensemble` built by :func:`ensemble`, and returns numbers; the runs that feed them are
:mod:`faultline.evaluation.abstention_runs` (GPU) and :mod:`faultline.evaluation.abstention_verdict`
(CPU).

**The ensemble (§1).** Per arm, the three seeds' ADR-0019 prior-corrected logits ``z_s`` (the
probe's logit plus its saved ``prior_offset``), paired row for row. Its probability is
``p = mean_s sigmoid(z_s)``; its confidence is seed disagreement ``u = std_s(z_s)`` with ddof 0,
lower meaning more confident. :func:`ensemble` refuses seeds that do not cover the same rows in
the same order, so no ensemble is ever formed over misaligned windows.

**The operating point** is fitted on the clean validation ensemble only: τ maximises F1 over the
distinct validation values of ``p`` (the smallest on a tie), κ is the 0.90 quantile of validation
``u`` (``method="lower"``). :func:`fit_tau`, :func:`fit_kappa` and :func:`fit_platt` refuse an
ensemble that is not the validation split's.

**Calibration** is :func:`equal_mass_ece`: 15 bins of equal window count, cut by rank of ``p``.
:func:`faultline.evaluation.calibration.expected_calibration_error` (equal-width) is untouched.

**Risk–coverage.** Windows are admitted most confident first, ties by row order; at coverage
``i / n`` the selective risk is the misclassification rate of the ``i`` admitted windows at τ, and
AURC is the mean over the ``n`` points. Written as a weighted sum, AURC is
``sum_k e_(k) * w_k`` with ``w_k = (1 / n) * sum_{i >= k} 1 / i``, which is how
:func:`aurc` computes it and how the random-ordering reference reuses one weight vector across its
100 permutations. The permutations are seeded by :func:`permutation_seeds`, one seed per
permutation, so a bootstrap replicate of any size draws "the same 100 permutations".

**The bootstrap** is ADR-0024's, unchanged: :class:`faultline.evaluation.bootstrap.BlockDraws`
at the registered seed, a replicate with no positive window discarded. One
:class:`StatisticsJob` computes every statistic of one scenario (an arm's clean ensemble, or
``joint`` (d) at one severity) on every replicate, so any two scenarios' vectors pair replicate
by replicate — a paired Δ's interval is the percentiles of their difference.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from faultline.evaluation.bootstrap import BlockDraws, window_blocks
from faultline.evaluation.metrics import average_precision
from faultline.evaluation.probe_control import ScoredWindows
from faultline.logging_utils import get_logger

logger = get_logger(__name__)

#: ADR-0028 §2: equal-mass bins of the expected calibration error.
EQUAL_MASS_BINS = 15

#: The splits an ensemble can be read on. Only ``validation`` may fit τ, κ or Platt.
VALIDATION, TEST = "validation", "test"

#: Probabilities are clipped this far from 0 and 1 before a logit is taken (Platt).
_EPSILON = 1e-12


# =====================================================================================
# the ensemble
# =====================================================================================


@dataclass(frozen=True)
class Ensemble:
    """One arm's three-seed ensemble on one split. Build with :func:`ensemble` only.

    Attributes:
        split: ``validation`` or ``test``.
        p: Per window, the mean of the seeds' corrected probabilities.
        u: Per window, the population std of the seeds' corrected logits.
        corrected: Per seed and window, the corrected logit ``z_s``.
        labels: Per window, 1 if positive.
        which: Per window, its shard index into ``sources``.
        ends: Per window, its end step in its shard.
        sources: The shards' sources, in set order.
    """

    split: str
    p: np.ndarray
    u: np.ndarray
    corrected: np.ndarray
    labels: np.ndarray
    which: np.ndarray
    ends: np.ndarray
    sources: list[str]

    @property
    def windows(self) -> int:
        """Windows in the ensemble."""
        return int(self.p.size)

    @property
    def positives(self) -> int:
        """Positive windows."""
        return int((self.labels > 0.5).sum())

    def blocks(self, block_steps: int) -> np.ndarray:
        """Per window, its ADR-0021 time block."""
        return window_blocks(self.ends, self.which, block_steps)

    def same_rows(self, other: Ensemble) -> bool:
        """Whether two ensembles cover the same windows, in order, with the same labels."""
        return (
            self.sources == other.sources
            and np.array_equal(self.labels, other.labels)
            and np.array_equal(self.which, other.which)
            and np.array_equal(self.ends, other.ends)
        )


def sigmoid(z: np.ndarray) -> np.ndarray:
    """The logistic function, in float64, without overflow."""
    return np.asarray(0.5 * (1.0 + np.tanh(0.5 * np.asarray(z, dtype=np.float64))))


def ensemble(seeds: Sequence[ScoredWindows], split: str) -> Ensemble:
    """The seeds' ensemble, after refusing any seed that does not align row for row.

    Args:
        seeds: Each seed's saved scores, in seed order.
        split: ``validation`` or ``test``.

    Returns:
        The ensemble.

    Raises:
        ValueError: If fewer than two seeds are given, the split is unknown, or any seed covers
            different windows (sources, order, labels or end steps) from the first.
    """
    if split not in (VALIDATION, TEST):
        raise ValueError(f"unknown split {split!r}")
    if len(seeds) < 2:
        raise ValueError(f"an ensemble needs at least two seeds, got {len(seeds)}")
    first = seeds[0]
    for number, other in enumerate(seeds[1:], 2):
        if not other.same_windows(first):
            raise ValueError(
                f"seed {number} of {len(seeds)} does not align with seed 1 row for row"
            )
    corrected = np.stack(
        [np.asarray(s.logits, dtype=np.float64) + float(s.prior_offset) for s in seeds]
    )
    return Ensemble(
        split=split,
        p=sigmoid(corrected).mean(axis=0),
        u=corrected.std(axis=0, ddof=0),
        corrected=corrected,
        labels=np.asarray(first.labels, dtype=np.float64),
        which=np.asarray(first.which),
        ends=np.asarray(first.ends),
        sources=list(first.sources),
    )


def _validation_only(scores: Ensemble, what: str) -> None:
    if scores.split != VALIDATION:
        raise ValueError(f"{what} is fitted on the validation split only, got {scores.split!r}")


# =====================================================================================
# calibration
# =====================================================================================


@dataclass(frozen=True)
class ReliabilityBin:
    """One equal-mass bin of the reliability table.

    Attributes:
        windows: Windows in the bin.
        mean_p: Their mean probability.
        positive_share: Their positive share.
        low: The smallest probability in the bin.
        high: The largest.
    """

    windows: int
    mean_p: float
    positive_share: float
    low: float
    high: float


def equal_mass_bins(p: np.ndarray, bins: int = EQUAL_MASS_BINS) -> list[np.ndarray]:
    """The rows of each equal-mass bin: ``p`` ranked (ties by row order) and cut into ``bins``.

    Bin sizes differ by at most one window (``numpy.array_split``).
    """
    if bins < 1:
        raise ValueError(f"bins must be at least 1, got {bins}")
    order = np.argsort(np.asarray(p, dtype=np.float64), kind="stable")
    return [chunk for chunk in np.array_split(order, bins) if chunk.size]


def equal_mass_ece(
    p: np.ndarray, labels: np.ndarray, bins: int = EQUAL_MASS_BINS
) -> tuple[float, list[ReliabilityBin]]:
    """Expected calibration error over equal-mass bins, and its reliability table.

    Args:
        p: Per window, a probability read at the natural rate.
        labels: Per window, 1 if positive.
        bins: Bins of equal window count.

    Returns:
        The window-weighted mean ``|mean p - positive share|`` over the bins (``nan`` without
        windows), and one row per bin in ascending ``p``.
    """
    p = np.asarray(p, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    if p.size == 0:
        return math.nan, []
    total, table = 0.0, []
    for rows in equal_mass_bins(p, bins):
        mean_p, share = float(p[rows].mean()), float(y[rows].mean())
        total += rows.size * abs(mean_p - share)
        table.append(
            ReliabilityBin(
                windows=int(rows.size),
                mean_p=mean_p,
                positive_share=share,
                low=float(p[rows].min()),
                high=float(p[rows].max()),
            )
        )
    return total / p.size, table


def _ece_only(p: np.ndarray, y: np.ndarray, bins: int) -> float:
    """:func:`equal_mass_ece`'s value alone, for the bootstrap's inner loop."""
    order = np.argsort(p, kind="stable")
    total = 0.0
    for rows in np.array_split(order, bins):
        if rows.size:
            total += abs(float(p[rows].sum()) - float(y[rows].sum()))
    return total / p.size


def logit(p: np.ndarray) -> np.ndarray:
    """``log(p / (1 - p))``, with ``p`` clipped away from 0 and 1."""
    q = np.clip(np.asarray(p, dtype=np.float64), _EPSILON, 1.0 - _EPSILON)
    return np.asarray(np.log(q) - np.log1p(-q))


def fit_platt(validation: Ensemble, iterations: int = 100) -> tuple[float, float]:
    """Platt recalibration ``sigmoid(a * logit(p) + b)``, fitted on the validation ensemble.

    Maximum likelihood by Newton's method from ``(a, b) = (1, 0)``, the identity.

    Args:
        validation: The clean validation ensemble.
        iterations: Most Newton steps.

    Returns:
        ``(a, b)``.

    Raises:
        ValueError: If the ensemble is not the validation split's.
    """
    _validation_only(validation, "Platt recalibration")
    x, y = logit(validation.p), validation.labels
    a, b = 1.0, 0.0
    for _ in range(iterations):
        q = sigmoid(a * x + b)
        weight = q * (1.0 - q)
        gradient = np.array([np.dot(q - y, x), np.sum(q - y)])
        hessian = np.array(
            [[np.dot(weight, x * x), np.dot(weight, x)], [np.dot(weight, x), weight.sum()]]
        )
        step = np.linalg.solve(hessian, gradient)
        a, b = a - float(step[0]), b - float(step[1])
        if float(np.abs(step).max()) < 1e-10:
            break
    return a, b


def apply_platt(p: np.ndarray, a: float, b: float) -> np.ndarray:
    """A fitted Platt map applied, unchanged, to any probabilities."""
    return sigmoid(a * logit(p) + b)


# =====================================================================================
# the operating point
# =====================================================================================


def fit_tau(validation: Ensemble) -> float:
    """τ: the validation probability threshold with the highest F1; the smallest on a tie.

    The candidates are the distinct validation values of ``p``; at candidate ``t`` every window
    with ``p >= t`` alarms. F1 is ``2 TP / (alarms + positives)``, compared exactly in integers.

    Args:
        validation: The clean validation ensemble.

    Returns:
        τ.

    Raises:
        ValueError: If the ensemble is not the validation split's or holds no positive window.
    """
    _validation_only(validation, "tau")
    positives = validation.positives
    if positives == 0:
        raise ValueError("no positive validation window: F1 is undefined")
    order = np.argsort(-validation.p, kind="stable")
    ranked = validation.p[order]
    hits = np.cumsum(validation.labels[order] > 0.5).astype(np.int64)
    last = np.r_[ranked[1:] != ranked[:-1], True]
    candidates, tp = ranked[last], hits[last]
    denominator = np.flatnonzero(last).astype(np.int64) + 1 + positives
    best = int(np.argmax(tp / denominator))
    ties = np.flatnonzero(tp * denominator[best] == tp[best] * denominator)
    return float(candidates[ties].min())


def fit_kappa(validation: Ensemble, coverage: float) -> float:
    """κ: the ``coverage`` quantile of validation disagreement, ``method="lower"``.

    Raises:
        ValueError: If the ensemble is not the validation split's.
    """
    _validation_only(validation, "kappa")
    return float(np.quantile(validation.u, coverage, method="lower"))


def fit_margin_cut(validation: Ensemble, tau: float, coverage: float) -> float:
    """The margin signal's cut-off at the same validation coverage as κ; reported only.

    ADR-0028 §1 fixes κ for disagreement alone and says the margin rows are reported beside the
    primary. This is F9-1's reading of that sentence, made before any test number is read: a
    window is covered when ``|p - τ| >= cut``, and the cut is the ``1 - coverage`` quantile of
    validation margin (``method="lower"``), so validation coverage is at least ``coverage``.

    Raises:
        ValueError: If the ensemble is not the validation split's.
    """
    _validation_only(validation, "the margin cut-off")
    return float(np.quantile(np.abs(validation.p - tau), 1.0 - coverage, method="lower"))


def misclassified(p: np.ndarray, labels: np.ndarray, tau: float) -> np.ndarray:
    """Per window, whether the alarm at τ (``p >= τ``) disagrees with the label."""
    return np.asarray((np.asarray(p) >= tau) != (np.asarray(labels) > 0.5))


def coverage_and_risk(covered: np.ndarray, errors: np.ndarray) -> tuple[float, float]:
    """The covered share, and the misclassification rate on it (``nan`` if nothing is covered)."""
    kept = int(covered.sum())
    risk = float(errors[covered].sum()) / kept if kept else math.nan
    return kept / covered.size, risk


# =====================================================================================
# risk–coverage
# =====================================================================================


def aurc_weights(n: int) -> np.ndarray:
    """``w_k = (1 / n) * sum_{i >= k} 1 / i`` for ``k = 1..n``: AURC as a weighted error sum."""
    inverse = 1.0 / np.arange(1, n + 1, dtype=np.float64)
    return np.asarray(np.cumsum(inverse[::-1])[::-1] / n)


def admission_order(confidence: np.ndarray, higher_is_confident: bool) -> np.ndarray:
    """Rows most confident first, ties by row order."""
    key = -np.asarray(confidence) if higher_is_confident else np.asarray(confidence)
    return np.argsort(key, kind="stable")


def risk_coverage_curve(errors: np.ndarray, order: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Coverage ``i / n`` and selective risk of the first ``i`` admitted windows, ``i = 1..n``."""
    n = errors.size
    admitted = np.arange(1, n + 1, dtype=np.float64)
    return admitted / n, np.cumsum(errors[order].astype(np.float64)) / admitted


def aurc(errors: np.ndarray, order: np.ndarray, weights: np.ndarray | None = None) -> float:
    """Mean selective risk over the ``n`` coverage points of one admission order."""
    w = aurc_weights(errors.size) if weights is None else weights
    return float(np.dot(errors[order].astype(np.float64), w))


def permutation_seeds(seed: int, count: int) -> np.ndarray:
    """The seeds of the random-ordering reference's permutations, drawn once from ``seed``."""
    return np.random.default_rng(seed).integers(0, 2**32, size=count, dtype=np.uint64)


def random_aurc(errors: np.ndarray, seeds: np.ndarray, weights: np.ndarray | None = None) -> float:
    """AURC under a uniformly random admission order, averaged over one permutation per seed."""
    w = aurc_weights(errors.size) if weights is None else weights
    e = errors.astype(np.float64)
    draws = [np.dot(e[np.random.default_rng(int(s)).permutation(e.size)], w) for s in seeds]
    return float(np.mean(draws))


# =====================================================================================
# the bootstrap
# =====================================================================================


@dataclass(frozen=True)
class OperatingPoint:
    """One arm's operating point, fixed on clean validation (ADR-0028 §1).

    Attributes:
        tau: The alarm threshold on ``p``.
        kappa: The disagreement cut-off; covered when ``u <= kappa``.
        margin_cut: The margin signal's cut-off; covered when ``|p - tau| >= margin_cut``.
    """

    tau: float
    kappa: float
    margin_cut: float


@dataclass(frozen=True)
class StatisticsJob:
    """Every statistic of one scenario on every bootstrap replicate.

    Attributes:
        cache: The ``.npz`` the vectors are written to.
        p: Per window, the ensemble probability.
        u: Per window, the seed disagreement.
        labels: Per window, 1 if positive.
        blocks: Per window, its time block.
        replicates: Replicates to draw.
        seed: The bootstrap seed.
        bins: Equal-mass ECE bins.
        point: The operating point, or ``None`` for the rows that need none (Part A's ECE).
        random_seeds: The random-ordering reference's permutation seeds; empty skips it.
    """

    cache: Path
    p: np.ndarray
    u: np.ndarray
    labels: np.ndarray
    blocks: np.ndarray
    replicates: int
    seed: int
    bins: int = EQUAL_MASS_BINS
    point: OperatingPoint | None = None
    random_seeds: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.uint64))


def statistic_names(job: StatisticsJob) -> list[str]:
    """The vectors a job writes, in order."""
    names = ["base_rate", "mean_p", "ece", "auprc"]
    if job.point is not None:
        names += ["coverage", "risk", "aurc", "margin_coverage", "margin_risk", "margin_aurc"]
        if job.random_seeds.size:
            names += ["aurc_random", "aurc_minus_random"]
    return names


def statistics(
    p: np.ndarray,
    u: np.ndarray,
    labels: np.ndarray,
    bins: int,
    point: OperatingPoint | None,
    random_seeds: np.ndarray,
) -> dict[str, float]:
    """Every statistic of one set of rows; ``nan`` everywhere if none is positive.

    Args:
        p: Per window, the ensemble probability.
        u: Per window, the seed disagreement.
        labels: Per window, 1 if positive.
        bins: Equal-mass ECE bins.
        point: The operating point, or ``None``.
        random_seeds: Permutation seeds of the random reference; empty skips it.

    Returns:
        Per statistic name, its value.
    """
    y = labels > 0.5
    out: dict[str, float] = {
        "base_rate": float(y.mean()),
        "mean_p": float(p.mean()),
        "ece": _ece_only(p, labels.astype(np.float64), bins),
        "auprc": average_precision(p, labels.astype(np.float64)),
    }
    if point is not None:
        errors = (p >= point.tau) != y
        weights = aurc_weights(p.size)
        out["coverage"], out["risk"] = coverage_and_risk(u <= point.kappa, errors)
        out["aurc"] = aurc(errors, admission_order(u, False), weights)
        margin = np.abs(p - point.tau)
        out["margin_coverage"], out["margin_risk"] = coverage_and_risk(
            margin >= point.margin_cut, errors
        )
        out["margin_aurc"] = aurc(errors, admission_order(margin, True), weights)
        if random_seeds.size:
            out["aurc_random"] = random_aurc(errors, random_seeds, weights)
            out["aurc_minus_random"] = out["aurc"] - out["aurc_random"]
    return out


def run_statistics_job(job: StatisticsJob) -> Path:
    """Compute one scenario's replicate vectors and write them atomically.

    A replicate with no positive window is ``nan`` in every vector (ADR-0021's discard rule).
    """
    names = statistic_names(job)
    vectors = {name: np.full(job.replicates, math.nan) for name in names}
    labels = np.asarray(job.labels, dtype=np.float64)
    for i, rows in enumerate(BlockDraws(job.blocks).replicates(job.replicates, job.seed)):
        if labels[rows].sum() == 0:
            continue
        values = statistics(
            job.p[rows], job.u[rows], labels[rows], job.bins, job.point, job.random_seeds
        )
        for name in names:
            vectors[name][i] = values[name]
    partial = job.cache.with_name(job.cache.stem + ".partial.npz")
    job.cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(partial, **vectors)  # type: ignore[arg-type]
    partial.replace(job.cache)
    return job.cache


def run_capped(
    function: Callable[[Any], Path], jobs: Sequence[Any], max_workers: int
) -> list[Path]:
    """Run jobs on a process pool no wider than ``max_workers`` (F7'-3's memory cap).

    Under Windows' spawn start method every worker re-imports the package (about 0.6 GB with
    torch), so the pool is capped; each job is independent and deterministic, so the width
    changes nothing written.
    """
    if not jobs:
        return []
    workers = max(1, min(len(jobs), (os.cpu_count() or 2) - 2, max_workers))
    logger.info("bootstrapping %d scenarios on %d worker processes", len(jobs), workers)
    written: list[Path] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(function, job) for job in jobs]
        for future in as_completed(futures):
            written.append(future.result())
            logger.info("replicates written: %s (%d/%d)", written[-1].name, len(written), len(jobs))
    return written


# =====================================================================================
# intervals
# =====================================================================================


@dataclass(frozen=True)
class Interval:
    """A percentile interval from a replicate vector, or a paired Δ from two.

    Attributes:
        value: The statistic on the rows as scored (a Δ for a paired interval).
        low: The lower percentile bound.
        high: The upper one.
        replicates: Replicates drawn.
        discarded: Replicates left out for holding no positive window (or no covered one).
        trusted: Whether ``discarded / replicates`` is within the registered share.
    """

    value: float
    low: float
    high: float
    replicates: int
    discarded: int
    trusted: bool


def percentile_interval(values: np.ndarray, confidence: float) -> tuple[float, float]:
    """The central ``confidence`` percentile interval of the non-``nan`` values."""
    kept = values[~np.isnan(values)]
    if not kept.size:
        return math.nan, math.nan
    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(kept, [tail, 1.0 - tail])
    return float(low), float(high)


def interval(
    value: float, vector: np.ndarray, confidence: float, max_discarded_share: float
) -> Interval:
    """One statistic's interval from its replicate vector."""
    low, high = percentile_interval(vector, confidence)
    discarded = int(np.isnan(vector).sum())
    return Interval(
        value=value,
        low=low,
        high=high,
        replicates=int(vector.size),
        discarded=discarded,
        trusted=discarded / vector.size <= max_discarded_share,
    )


def paired_interval(
    first: tuple[float, np.ndarray],
    second: tuple[float, np.ndarray],
    confidence: float,
    max_discarded_share: float,
) -> Interval:
    """Δ = first − second, replicate by replicate, on vectors drawn on the same rows.

    Raises:
        ValueError: If the two vectors differ in length, which would mean different draws.
    """
    if first[1].shape != second[1].shape:
        raise ValueError("paired vectors must come from the same replicates")
    return interval(first[0] - second[0], first[1] - second[1], confidence, max_discarded_share)
