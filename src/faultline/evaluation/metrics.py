"""Risk metrics, computed here rather than imported (M1e).

Average precision is the ladder's selection metric and the axis of its second panel, so
it is written out: a metric whose tie-handling and interpolation the reader cannot see is
a metric the reader cannot check. The definition used is the one scikit-learn calls
``average_precision_score`` -- the step-wise sum of precision at each threshold weighted
by the change in recall -- and never the trapezoid under an interpolated curve, which
flatters a model at low recall.

The base rate is reported beside every AUPRC. At a base rate of 2% an AUPRC of 0.10 is
five times a coin toss and looks like failure; without the base rate next to it the number
says nothing at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: z for a two-sided 95% interval.
Z95 = 1.959963984540054


@dataclass(frozen=True)
class RiskScore:
    """One source's risk metrics on one evaluation pass.

    Attributes:
        source: The source scored.
        windows: Windows scored.
        positives: Of those, windows whose horizon holds an event.
        auprc: Average precision.
        base_rate: Share of windows that are positive, the floor a random scorer reaches.
        lift: ``auprc / base_rate``; 1.0 is no better than random.
        loss: Mean binary cross entropy, unweighted.
        nan_share: Share of the source's value tokens that are ``<nan>``, carried beside
            every per-source figure by the project's first reporting rule.
    """

    source: str
    windows: int
    positives: int
    auprc: float
    base_rate: float
    lift: float
    loss: float
    nan_share: float


def average_precision(scores: np.ndarray, labels: np.ndarray) -> float:
    """Average precision: the step-wise area under the precision-recall curve.

    Ties are handled by grouping: every window with the same score is admitted at the
    same threshold, so a model that outputs one constant scores its base rate rather
    than an artefact of the sort order.

    Args:
        scores: Predicted risk, higher meaning more at risk.
        labels: 1 for a positive window, 0 otherwise.

    Returns:
        The average precision, or ``nan`` where there is no positive window.
    """
    if scores.size == 0 or labels.sum() == 0:
        return math.nan
    order = np.argsort(-scores, kind="stable")
    ranked, truth = scores[order], labels[order].astype(np.float64)
    positives = np.cumsum(truth)
    admitted = np.arange(1, truth.size + 1, dtype=np.float64)
    # The last index of each run of equal scores: precision and recall are only defined
    # at a threshold, and a threshold admits every window that ties with it.
    last = np.r_[ranked[1:] != ranked[:-1], True]
    precision = positives[last] / admitted[last]
    recall = positives[last] / truth.sum()
    return float(np.sum(precision * np.diff(np.r_[0.0, recall])))


def binary_cross_entropy(logits: np.ndarray, labels: np.ndarray) -> float:
    """Mean binary cross entropy of logits against labels, in nats.

    Args:
        logits: Unnormalised scores.
        labels: 1 for a positive window, 0 otherwise.

    Returns:
        The mean loss, or ``nan`` without windows.
    """
    if logits.size == 0:
        return math.nan
    x = logits.astype(np.float64)
    # log(1 + exp(x)) computed so that a large positive logit does not overflow.
    softplus = np.logaddexp(0.0, x)
    return float(np.mean(softplus - labels.astype(np.float64) * x))


def wilson_interval(successes: int, trials: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    The normal approximation is wrong at the rates this project reports -- a few per cent,
    sometimes over a few dozen datasets -- so the interval that does not run off the end
    of ``[0, 1]`` is the one used (ADR-0010).

    Args:
        successes: Positive outcomes.
        trials: Total outcomes.
        z: Normal quantile; the default is a two-sided 95% interval.

    Returns:
        The lower and upper bound, or ``(nan, nan)`` without trials.
    """
    if trials <= 0:
        return math.nan, math.nan
    p = successes / trials
    denominator = 1 + z**2 / trials
    centre = (p + z**2 / (2 * trials)) / denominator
    spread = z * math.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2)) / denominator
    return max(0.0, centre - spread), min(1.0, centre + spread)


def score_source(
    source: str, logits: np.ndarray, labels: np.ndarray, nan_share: float
) -> RiskScore:
    """Score one source's windows.

    Args:
        source: The source scored.
        logits: Predicted risk logits.
        labels: 1 for a positive window, 0 otherwise.
        nan_share: The source's ``<nan>`` share, carried beside the metrics.

    Returns:
        The source's metrics.
    """
    positives = int(labels.sum())
    base = positives / labels.size if labels.size else math.nan
    auprc = average_precision(logits, labels)
    return RiskScore(
        source=source,
        windows=int(labels.size),
        positives=positives,
        auprc=auprc,
        base_rate=base,
        lift=auprc / base if base else math.nan,
        loss=binary_cross_entropy(logits, labels),
        nan_share=nan_share,
    )
