"""Calibration and abstention read scores at the natural base rate, never at the training rate.

Balanced sampling (M3 step 0, ADR-0019) trains the risk head on batches that are half
positive, while the windows it will be scored on are about 2% positive. A head trained that
way learns the 50% prior. Its probabilities are miscalibrated against the true prior **by
construction**, and this project claims risk-calibrated abstention. So the correction is
part of the method and not a reporting detail.

**The correction is logit adjustment.** Under label shift (the windows given a label are the
same in training and deployment, and only the class mix changes), the posterior at the
natural prior follows from the posterior at the training prior by Bayes' rule. Per class
``c``, subtract ``log(pi_train_c / pi_true_c)`` from its logit. With one binary logit,
``z = z_1 - z_0``, that is one constant::

    z_true = z_train - log(pi_train / pi_true) + log((1 - pi_train) / (1 - pi_true))
           = z_train + logit(pi_true) - logit(pi_train)

which is :func:`faultline.model.risk.prior_correction`. The first term alone, without the
negative class's, is the multi-class rule applied to one of two classes. It under-corrects
by ``log((1 - pi_true) / (1 - pi_train))``, 0.67 nats for 50% against 2%, so its scores
would still read above the true prior.

**The ordering is enforced by type, not by convention.** Every calibration metric and every
abstention threshold here takes :class:`NaturalRateScores`, and the only way to build one
is :func:`at_natural_rate`, which applies the correction. A raw logit array is refused at
run time as well as by the type checker. A ranking metric (AUPRC) does not change under a
constant shift and does not need it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from faultline.model.risk import prior_correction

#: Equal-width probability bins for the expected calibration error.
CALIBRATION_BINS = 15


@dataclass(frozen=True)
class NaturalRateScores:
    """Risk logits read at the natural base rate. Build with :func:`at_natural_rate` only.

    Attributes:
        logits: The corrected logits.
        train_rate: The positive share of the training batches.
        natural_rate: The positive share the logits now read at.
        offset: The constant added, ``logit(natural_rate) - logit(train_rate)``.
    """

    logits: np.ndarray
    train_rate: float
    natural_rate: float
    offset: float

    @property
    def probabilities(self) -> np.ndarray:
        """The corrected probabilities."""
        return 1.0 / (1.0 + np.exp(-self.logits.astype(np.float64)))


def at_natural_rate(
    logits: np.ndarray, train_rate: float, natural_rate: float, balanced_shift: float = 0.0
) -> NaturalRateScores:
    """Correct logits from the training prior to the natural prior.

    Args:
        logits: The head's logits as trained.
        train_rate: The positive share of its training batches; the natural rate itself for
            a head trained without rebalancing, which makes the offset zero.
        natural_rate: The positive share of the training windows at the natural rate.
        balanced_shift: A measured shift that first re-centres the head on ``train_rate``
            (ADR-0019 F2, :func:`balanced_shift`); zero keeps the declared correction.

    Returns:
        The corrected scores.
    """
    offset = balanced_shift + prior_correction(train_rate, natural_rate)
    return NaturalRateScores(
        logits=np.asarray(logits, dtype=np.float64) + offset,
        train_rate=train_rate,
        natural_rate=natural_rate,
        offset=offset,
    )


def balanced_shift(logits: np.ndarray, target: float, tolerance: float = 1e-6) -> float:
    """The constant ``c`` with ``mean(sigmoid(logits + c)) == target``, by bisection.

    ADR-0019 F2: a head trained on batches at ``target`` should put its mean prediction there.
    If it does not, ``c`` is the shift that makes it, measured on the balanced windows.

    Args:
        logits: The head's uncorrected logits over balanced windows.
        target: The positive share of those windows.
        tolerance: Width of the final bracket, in nats.

    Returns:
        The shift.

    Raises:
        ValueError: If there are no logits or the target is not strictly between 0 and 1.
    """
    if logits.size == 0:
        raise ValueError("no logits to re-centre")
    if not 0.0 < target < 1.0:
        raise ValueError(f"target must be strictly between 0 and 1, got {target}")
    z = np.asarray(logits, dtype=np.float64)

    def mean_at(shift: float) -> float:
        return float(np.mean(0.5 * (1.0 + np.tanh(0.5 * (z + shift)))))

    low, high = -60.0, 60.0
    while high - low > tolerance:
        middle = 0.5 * (low + high)
        if mean_at(middle) < target:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


def _require(scores: object) -> NaturalRateScores:
    """Refuse anything that has not been through :func:`at_natural_rate`.

    Raises:
        TypeError: If ``scores`` is not :class:`NaturalRateScores`.
    """
    if not isinstance(scores, NaturalRateScores):
        raise TypeError(
            "calibration and abstention read NaturalRateScores; apply at_natural_rate "
            f"(the prior correction) first, got {type(scores).__name__}"
        )
    return scores


def mean_predicted_rate(scores: NaturalRateScores) -> float:
    """The mean corrected probability, which a calibrated head puts at the base rate."""
    return float(_require(scores).probabilities.mean())


def expected_calibration_error(
    scores: NaturalRateScores, labels: np.ndarray, bins: int = CALIBRATION_BINS
) -> float:
    """Expected calibration error over equal-width probability bins.

    Args:
        scores: Corrected scores.
        labels: 1 for a positive window, 0 otherwise.
        bins: Number of bins over ``[0, 1]``.

    Returns:
        The window-weighted mean absolute gap between mean probability and positive share
        per bin, or ``nan`` without windows.
    """
    p = _require(scores).probabilities
    y = np.asarray(labels, dtype=np.float64)
    if p.size == 0:
        return math.nan
    which = np.minimum((p * bins).astype(np.int64), bins - 1)
    total = 0.0
    for b in range(bins):
        chosen = which == b
        if chosen.any():
            total += chosen.sum() * abs(p[chosen].mean() - y[chosen].mean())
    return float(total / p.size)


def abstention_threshold(scores: NaturalRateScores, coverage: float) -> float:
    """The confidence below which a window is abstained on, to keep ``coverage`` of them.

    Confidence is ``max(p, 1 - p)`` of the corrected probability. Without the correction
    a balanced head puts most windows near 0.5, so abstention would spend itself on
    windows that are confidently negative at the true prior.

    Args:
        scores: Corrected scores.
        coverage: Share of windows to answer on, in ``(0, 1]``.

    Returns:
        The confidence threshold; windows at or above it are answered.

    Raises:
        ValueError: If ``coverage`` is outside ``(0, 1]`` or there are no windows.
    """
    p = _require(scores).probabilities
    if not 0.0 < coverage <= 1.0:
        raise ValueError(f"coverage must be in (0, 1], got {coverage}")
    if p.size == 0:
        raise ValueError("no windows to set a threshold on")
    confidence = np.maximum(p, 1.0 - p)
    return float(np.quantile(confidence, 1.0 - coverage, method="lower"))
