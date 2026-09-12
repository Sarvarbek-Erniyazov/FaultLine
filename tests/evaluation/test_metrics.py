"""Average precision, checked against values computed by hand.

The metric is written from scratch, so it is checked against arithmetic a reader can
follow rather than against another implementation of the same idea.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from faultline.evaluation.metrics import (
    average_precision,
    binary_cross_entropy,
    score_source,
    wilson_interval,
)


def test_a_perfect_ranking_scores_one() -> None:
    scores = np.array([0.9, 0.8, 0.2, 0.1])
    labels = np.array([1, 1, 0, 0])
    assert average_precision(scores, labels) == pytest.approx(1.0)


def test_the_worst_ranking_scores_the_hand_computed_value() -> None:
    # Both positives last: precision is 1/3 when the first is admitted and 2/4 when the
    # second is, each contributing half the recall.
    scores = np.array([0.9, 0.8, 0.2, 0.1])
    labels = np.array([0, 0, 1, 1])
    expected = 0.5 * (1 / 3) + 0.5 * (2 / 4)
    assert average_precision(scores, labels) == pytest.approx(expected)


def test_a_constant_scorer_scores_its_base_rate() -> None:
    # The tie-handling clause. Without grouping ties, the sort order alone would decide
    # the score of a model that expresses no preference at all.
    for positives, total in ((3, 10), (1, 4), (25, 100)):
        labels = np.array([1] * positives + [0] * (total - positives))
        rng = np.random.default_rng(0)
        rng.shuffle(labels)
        assert average_precision(np.zeros(total), labels) == pytest.approx(positives / total)


def test_a_reversed_constant_scorer_is_not_flattered_by_the_sort() -> None:
    labels = np.array([0, 0, 0, 1])
    assert average_precision(np.ones(4), labels) == pytest.approx(0.25)
    assert average_precision(np.ones(4), labels[::-1].copy()) == pytest.approx(0.25)


def test_without_a_positive_the_metric_is_undefined_rather_than_zero() -> None:
    # A source whose subsample held no positive window must read `n/a`; a zero would be
    # a score, and would pull any average it entered.
    assert math.isnan(average_precision(np.array([0.4, 0.6]), np.array([0, 0])))
    assert math.isnan(average_precision(np.zeros(0), np.zeros(0)))


def test_partial_ordering_is_scored_between_the_extremes() -> None:
    scores = np.array([0.9, 0.5, 0.4, 0.1])
    labels = np.array([1, 0, 1, 0])
    expected = 0.5 * 1.0 + 0.5 * (2 / 3)
    assert average_precision(scores, labels) == pytest.approx(expected)


def test_cross_entropy_matches_the_closed_form_and_survives_large_logits() -> None:
    logits = np.array([0.0, 0.0])
    assert binary_cross_entropy(logits, np.array([0, 1])) == pytest.approx(math.log(2))
    # A confident and correct prediction costs almost nothing; a confident and wrong one
    # costs about the logit itself, and neither may overflow.
    assert binary_cross_entropy(np.array([800.0]), np.array([1])) == pytest.approx(0.0)
    assert binary_cross_entropy(np.array([800.0]), np.array([0])) == pytest.approx(800.0)


def test_the_wilson_interval_stays_inside_the_unit_range() -> None:
    low, high = wilson_interval(0, 20)
    assert low == 0.0 and 0.0 < high < 1.0
    low, high = wilson_interval(20, 20)
    assert high == 1.0 and 0.0 < low < 1.0
    low, high = wilson_interval(5, 10)
    assert low < 0.5 < high
    assert all(math.isnan(v) for v in wilson_interval(1, 0))


def test_a_source_score_carries_its_base_rate_lift_and_nan_share() -> None:
    labels = np.array([1, 0, 0, 0])
    scored = score_source("kelmarsh", np.array([2.0, 1.0, 0.0, -1.0]), labels, nan_share=0.12)
    assert scored.source == "kelmarsh"
    assert scored.windows == 4 and scored.positives == 1
    assert scored.base_rate == pytest.approx(0.25)
    assert scored.auprc == pytest.approx(1.0)
    assert scored.lift == pytest.approx(4.0)
    assert scored.nan_share == pytest.approx(0.12)
