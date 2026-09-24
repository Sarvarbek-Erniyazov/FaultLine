"""ADR-0028's numerics: the ensemble, equal-mass ECE, Platt, τ and κ, risk–coverage, bootstrap."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.risk_coverage import (
    TEST,
    VALIDATION,
    OperatingPoint,
    StatisticsJob,
    admission_order,
    apply_platt,
    aurc,
    aurc_weights,
    coverage_and_risk,
    ensemble,
    equal_mass_bins,
    equal_mass_ece,
    fit_kappa,
    fit_margin_cut,
    fit_platt,
    fit_tau,
    logit,
    paired_interval,
    permutation_seeds,
    random_aurc,
    risk_coverage_curve,
    run_statistics_job,
    sigmoid,
    statistics,
)


def _scored(logits: np.ndarray, labels: np.ndarray, offset: float = 0.0) -> ScoredWindows:
    n = labels.size
    return ScoredWindows(
        logits=np.asarray(logits, dtype=np.float32),
        labels=np.asarray(labels, dtype=np.float32),
        which=np.zeros(n, dtype=np.int64),
        ends=np.arange(n, dtype=np.int64) * 12,
        sources=["kelmarsh"],
        prior_offset=offset,
    )


def _seeds(n: int = 400, seed: int = 0) -> list[ScoredWindows]:
    rng = np.random.default_rng(seed)
    labels = (rng.random(n) < 0.1).astype(np.float32)
    signal = 2.0 * labels - 1.0
    return [_scored(signal + rng.normal(0, 1.0, n), labels, offset=-1.0) for _ in range(3)]


# -- the ensemble ------------------------------------------------------------------------


def test_ensemble_is_the_mean_corrected_probability_and_the_logit_spread() -> None:
    labels = np.array([0.0, 1.0])
    seeds = [
        _scored(np.array([0.0, 1.0]), labels, 0.5),
        _scored(np.array([1.0, 2.0]), labels, 0.5),
        _scored(np.array([2.0, 3.0]), labels, 0.5),
    ]
    e = ensemble(seeds, TEST)
    z = np.array([[0.5, 1.5], [1.5, 2.5], [2.5, 3.5]])
    assert np.allclose(e.p, (1 / (1 + np.exp(-z))).mean(axis=0))
    assert np.allclose(e.u, z.std(axis=0, ddof=0))
    assert e.windows == 2 and e.positives == 1


def test_ensemble_refuses_seeds_that_do_not_align_row_for_row() -> None:
    seeds = _seeds()
    shuffled = ScoredWindows(**{**seeds[2].__dict__, "ends": seeds[2].ends[::-1].copy()})
    with pytest.raises(ValueError, match="does not align"):
        ensemble([seeds[0], seeds[1], shuffled], TEST)
    relabelled = ScoredWindows(**{**seeds[1].__dict__, "labels": 1.0 - seeds[1].labels})
    with pytest.raises(ValueError, match="does not align"):
        ensemble([seeds[0], relabelled, seeds[2]], TEST)
    with pytest.raises(ValueError, match="unknown split"):
        ensemble(seeds, "train")


# -- calibration -------------------------------------------------------------------------


def test_equal_mass_bins_hold_equal_counts_by_rank() -> None:
    p = np.random.default_rng(1).random(1000) ** 4
    bins = equal_mass_bins(p, 15)
    assert len(bins) == 15
    assert {b.size for b in bins} <= {66, 67}
    assert np.array_equal(np.concatenate(bins), np.argsort(p, kind="stable"))


def test_equal_mass_ece_is_zero_when_calibrated_per_bin_and_matches_a_hand_count() -> None:
    p = np.array([0.1, 0.1, 0.5, 0.5])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    ece, table = equal_mass_ece(p, y, 2)
    assert ece == pytest.approx(0.5 * 0.1 + 0.5 * 0.5)
    assert [row.windows for row in table] == [2, 2]
    calibrated, _ = equal_mass_ece(np.array([0.0, 0.0, 1.0, 1.0]), y, 2)
    assert calibrated == 0.0


def test_platt_recovers_a_known_map_and_is_validation_only() -> None:
    rng = np.random.default_rng(3)
    x = rng.normal(-2.0, 1.5, 20000)
    labels = (rng.random(x.size) < sigmoid(0.6 * x - 0.4)).astype(np.float32)
    # One seed at a time would do; three identical seeds make p = sigmoid(x) and u = 0.
    seeds = [_scored(x, labels) for _ in range(3)]
    a, b = fit_platt(ensemble(seeds, VALIDATION))
    assert a == pytest.approx(0.6, abs=0.05) and b == pytest.approx(-0.4, abs=0.08)
    assert np.allclose(apply_platt(sigmoid(x), 1.0, 0.0), sigmoid(x))
    assert np.allclose(logit(sigmoid(x)), x)
    with pytest.raises(ValueError, match="validation split only"):
        fit_platt(ensemble(seeds, TEST))


# -- the operating point -----------------------------------------------------------------


def _brute_tau(p: np.ndarray, y: np.ndarray) -> float:
    best, chosen = -1.0, np.inf
    for t in np.unique(p):
        alarm = p >= t
        tp = float((alarm & (y > 0.5)).sum())
        f1 = 2 * tp / (alarm.sum() + (y > 0.5).sum())
        if f1 > best + 1e-15 or (abs(f1 - best) <= 1e-15 and t < chosen):
            best, chosen = f1, float(t)
    return chosen


def test_tau_maximises_f1_over_distinct_validation_values() -> None:
    validation = ensemble(_seeds(600, seed=5), VALIDATION)
    assert fit_tau(validation) == _brute_tau(validation.p, validation.labels)


def test_tau_takes_the_smallest_threshold_on_a_tie() -> None:
    p = np.array([0.9, 0.7, 0.7, 0.1])
    y = np.array([1.0, 1.0, 0.0, 0.0])
    labels = y.astype(np.float32)
    seeds = [_scored(logit(p), labels) for _ in range(3)]
    tau = fit_tau(ensemble(seeds, VALIDATION))
    # F1 at 0.9: 2/3; at 0.7: 4/5; at 0.1: 4/6. The unique maximum is 0.7.
    assert tau == pytest.approx(0.7)
    tied_p = np.array([0.9, 0.6, 0.5, 0.5, 0.1])
    tied_y = np.array([1.0, 0.0, 1.0, 0.0, 0.0])
    # At 0.9: 2/(1+2) = 2/3; at 0.5: 4/(4+2) = 2/3; the smaller threshold is taken.
    tied = [_scored(logit(tied_p), tied_y.astype(np.float32)) for _ in range(3)]
    assert fit_tau(ensemble(tied, VALIDATION)) == pytest.approx(0.5)


def test_kappa_and_the_margin_cut_give_at_least_the_registered_validation_coverage() -> None:
    validation = ensemble(_seeds(1000, seed=7), VALIDATION)
    kappa = fit_kappa(validation, 0.90)
    assert kappa == float(np.quantile(validation.u, 0.90, method="lower"))
    assert 0.899 <= (validation.u <= kappa).mean() <= 0.901
    tau = fit_tau(validation)
    cut = fit_margin_cut(validation, tau, 0.90)
    assert (np.abs(validation.p - tau) >= cut).mean() >= 0.90
    with pytest.raises(ValueError, match="validation split only"):
        fit_kappa(ensemble(_seeds(), TEST), 0.9)
    with pytest.raises(ValueError, match="validation split only"):
        fit_tau(ensemble(_seeds(), TEST))


def test_coverage_and_risk_count_misclassifications_on_the_covered_set() -> None:
    covered = np.array([True, True, False, True])
    errors = np.array([True, False, True, False])
    assert coverage_and_risk(covered, errors) == (0.75, pytest.approx(1 / 3))
    assert np.isnan(coverage_and_risk(np.zeros(3, bool), np.ones(3, bool))[1])


# -- risk–coverage -----------------------------------------------------------------------


def test_aurc_as_a_weighted_sum_is_the_mean_of_the_curve() -> None:
    rng = np.random.default_rng(11)
    errors = rng.random(500) < 0.2
    u = rng.random(500)
    order = admission_order(u, higher_is_confident=False)
    coverage, risk = risk_coverage_curve(errors, order)
    assert coverage[-1] == 1.0 and risk[-1] == pytest.approx(errors.mean())
    assert aurc(errors, order) == pytest.approx(risk.mean())
    assert aurc_weights(4) == pytest.approx([25 / 48, 13 / 48, 7 / 48, 3 / 48])


def test_admission_is_most_confident_first_with_ties_by_row_order() -> None:
    u = np.array([0.3, 0.1, 0.3, 0.1])
    assert admission_order(u, False).tolist() == [1, 3, 0, 2]
    assert admission_order(u, True).tolist() == [0, 2, 1, 3]


def test_the_random_reference_sits_at_the_error_rate_and_its_seeds_are_fixed() -> None:
    errors = np.random.default_rng(13).random(5000) < 0.1
    seeds = permutation_seeds(20260924, 100)
    assert np.array_equal(seeds, permutation_seeds(20260924, 100)) and seeds.size == 100
    assert random_aurc(errors, seeds) == pytest.approx(errors.mean(), abs=0.01)
    # A perfect ordering puts every error last and beats random.
    perfect = admission_order(errors.astype(float), False)
    assert aurc(errors, perfect) < random_aurc(errors, seeds)


# -- the bootstrap -----------------------------------------------------------------------


def test_statistics_on_the_full_rows_and_a_job_that_discards_positive_free_replicates(
    tmp_path: Path,
) -> None:
    e = ensemble(_seeds(300, seed=17), TEST)
    point = OperatingPoint(tau=0.3, kappa=float(np.quantile(e.u, 0.9)), margin_cut=0.05)
    seeds = permutation_seeds(1, 5)
    values = statistics(e.p, e.u, e.labels, 15, point, seeds)
    errors = (e.p >= 0.3) != (e.labels > 0.5)
    assert values["aurc"] == pytest.approx(aurc(errors, admission_order(e.u, False)))
    assert values["aurc_minus_random"] == pytest.approx(values["aurc"] - values["aurc_random"])
    assert values["ece"] == pytest.approx(equal_mass_ece(e.p, e.labels, 15)[0])
    labels = np.zeros_like(e.labels)
    labels[0] = 1.0  # one positive, in block 0 only: many replicates will hold none
    blocks = np.arange(e.windows) // 10
    job = StatisticsJob(
        cache=tmp_path / "job.npz",
        p=e.p,
        u=e.u,
        labels=labels,
        blocks=blocks,
        replicates=50,
        seed=20260916,
        point=point,
        random_seeds=seeds,
    )
    with np.load(run_statistics_job(job)) as vectors:
        assert set(vectors.files) >= {"ece", "coverage", "risk", "aurc", "aurc_random"}
        ece = vectors["ece"]
        assert np.isnan(ece).any() and not np.isnan(ece).all()
        assert np.array_equal(np.isnan(ece), np.isnan(vectors["aurc"]))


def test_a_paired_interval_differences_replicate_by_replicate() -> None:
    first = np.array([1.0, 2.0, 3.0, np.nan])
    second = np.array([0.5, 1.0, 1.5, np.nan])
    iv = paired_interval((2.0, first), (1.0, second), 0.5, 0.3)
    assert iv.value == 1.0 and iv.discarded == 1 and iv.trusted
    assert iv.low == pytest.approx(0.75) and iv.high == pytest.approx(1.25)
    assert not paired_interval((2.0, first), (1.0, second), 0.5, 0.2).trusted
