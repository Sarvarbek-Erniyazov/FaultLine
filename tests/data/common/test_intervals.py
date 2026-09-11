"""Confidence intervals: known values, and the properties every report relies on."""

from __future__ import annotations

import math

import pytest

from faultline.data.common.intervals import (
    mantel_haenszel_rate_ratio,
    poisson_interval,
    rate_ratio_interval,
    wilson_interval,
)


def test_wilson_matches_the_textbook_value_at_zero_successes() -> None:
    low, high = wilson_interval(0, 10)
    assert low == 0.0
    assert high == pytest.approx(0.2775, abs=1e-3)


def test_wilson_is_symmetric_at_one_half_and_narrows_with_more_trials() -> None:
    low, high = wilson_interval(20, 40)
    assert 0.5 - low == pytest.approx(high - 0.5)
    wide = wilson_interval(5, 10)
    assert wide[1] - wide[0] > high - low


def test_wilson_rejects_impossible_counts() -> None:
    with pytest.raises(ValueError, match="at least one trial"):
        wilson_interval(0, 0)
    with pytest.raises(ValueError, match="outside"):
        wilson_interval(11, 10)


def test_byar_is_within_a_percent_of_the_exact_poisson_interval() -> None:
    # exact (Garwood) 95% interval for a count of 10: 4.795 to 18.390
    low, high = poisson_interval(10)
    assert low == pytest.approx(4.795, rel=0.01)
    assert high == pytest.approx(18.390, rel=0.01)
    assert poisson_interval(0)[0] == 0.0
    with pytest.raises(ValueError, match="negative"):
        poisson_interval(-1)


def test_equal_rates_give_a_ratio_of_one_inside_its_interval() -> None:
    ratio, low, high = rate_ratio_interval(20, 2.0, 30, 3.0)
    assert ratio == pytest.approx(1.0)
    assert low < 1.0 < high


def test_a_rate_ratio_without_events_is_not_a_number() -> None:
    assert all(math.isnan(x) for x in rate_ratio_interval(0, 1.0, 5, 1.0))


def test_mantel_haenszel_on_one_stratum_is_the_crude_ratio() -> None:
    assert mantel_haenszel_rate_ratio([(20, 2.0, 30, 3.0)]) == pytest.approx(
        rate_ratio_interval(20, 2.0, 30, 3.0)
    )


def test_matching_removes_a_seasonal_confound() -> None:
    # Winter runs at 10 events a turbine-year on both sides, summer at 2. The first group
    # sits mostly in summer, so the crude ratio calls it safer; matched by season it is not.
    strata = [(10, 1.0, 90, 9.0), (18, 9.0, 2, 1.0)]
    crude, _, _ = rate_ratio_interval(28, 10.0, 92, 10.0)
    matched, low, high = mantel_haenszel_rate_ratio(strata)
    assert crude < 0.5
    assert matched == pytest.approx(1.0)
    assert low < 1.0 < high


def test_a_stratum_with_exposure_on_one_side_adds_nothing() -> None:
    base = mantel_haenszel_rate_ratio([(20, 2.0, 30, 3.0)])
    assert mantel_haenszel_rate_ratio([(20, 2.0, 30, 3.0), (5, 1.0, 0, 0.0)]) == pytest.approx(base)
    assert all(math.isnan(x) for x in mantel_haenszel_rate_ratio([(5, 1.0, 0, 0.0)]))
