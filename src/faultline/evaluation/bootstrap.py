"""A within-seed interval on AUPRC, resampled in time blocks, and ADR-0021's gate on it.

**Why blocks.** An event makes every window whose horizon reaches it positive, so positive
windows arrive in runs. On Hill of Towie's 12,000 seeded test windows the 399 positives fall
into 274 blocks of 48 hours. Resampling windows one at a time would treat them as 399
independent draws and give an interval that is too narrow. The unit resampled here is a block:
a window's end step integer-divided by ``block_steps``, within its shard. Every window of a
drawn block comes along, as many times as the block is drawn.

**The gate (ADR-0021, registered before the run it governs).** A site is *evaluable* only if the
interval's lower bound is strictly above the site's base rate on the scored windows, the AUPRC
a scorer with no signal reaches. More than ``max_discarded_share`` of replicates without a
positive window makes the interval untrusted, and the verdict is then not evaluable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from faultline.evaluation.metrics import average_precision


def window_blocks(ends: np.ndarray, sets: np.ndarray, block_steps: int) -> np.ndarray:
    """Name each window's time block: its end step's block, within its shard.

    Args:
        ends: Per window, its last step in the shard's step axis.
        sets: Per window, the index of the shard (window set) it came from.
        block_steps: Steps a block spans.

    Returns:
        Per window, a block id; two windows share one only if they share a shard and a block.

    Raises:
        ValueError: If ``block_steps`` is not positive or the arrays differ in length.
    """
    if block_steps < 1:
        raise ValueError(f"block_steps must be at least 1, got {block_steps}")
    if ends.shape != sets.shape:
        raise ValueError(f"ends {ends.shape} and sets {sets.shape} differ in shape")
    pairs = np.stack([sets.astype(np.int64), ends.astype(np.int64) // block_steps], axis=1)
    _, ids = np.unique(pairs, axis=0, return_inverse=True)
    return ids.reshape(-1).astype(np.int64)


@dataclass(frozen=True)
class AuprcInterval:
    """A bootstrap interval on one source's AUPRC.

    Attributes:
        unit: What was resampled, ``block`` or ``window``.
        auprc: AUPRC on the windows as scored.
        low: The interval's lower bound.
        high: Its upper bound.
        lift_low: Lower bound on AUPRC minus each replicate's own base rate.
        lift_high: Upper bound on the same.
        base_rate: Positive share of the windows as scored.
        windows: Windows scored.
        positives: Positive windows.
        blocks: Units resampled.
        positive_blocks: Units holding at least one positive window.
        replicates: Replicates drawn.
        discarded: Replicates with no positive window, left out of the interval.
        confidence: The interval's coverage.
        seed: The bootstrap seed.
    """

    unit: str
    auprc: float
    low: float
    high: float
    lift_low: float
    lift_high: float
    base_rate: float
    windows: int
    positives: int
    blocks: int
    positive_blocks: int
    replicates: int
    discarded: int
    confidence: float
    seed: int

    @property
    def discarded_share(self) -> float:
        """Share of replicates discarded for holding no positive window."""
        return self.discarded / self.replicates


def bootstrap_auprc(
    scores: np.ndarray,
    labels: np.ndarray,
    blocks: np.ndarray,
    replicates: int,
    seed: int,
    confidence: float = 0.95,
    unit: str = "block",
) -> AuprcInterval:
    """Percentile bootstrap of AUPRC, resampling whole blocks with replacement.

    Args:
        scores: Per window, its score (a logit or a probability; AUPRC reads the order).
        labels: Per window, 1 if positive.
        blocks: Per window, its block id (``window_blocks``); ``np.arange`` resamples windows.
        replicates: Replicates to draw.
        seed: Seed of the resampling.
        confidence: Coverage of the interval.
        unit: The name of what ``blocks`` groups, for the record.

    Returns:
        The interval.

    Raises:
        ValueError: On mismatched arrays, no positive window, or a confidence outside (0, 1).
    """
    if not scores.shape == labels.shape == blocks.shape:
        raise ValueError("scores, labels and blocks must have one entry per window")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be strictly between 0 and 1, got {confidence}")
    if replicates < 1:
        raise ValueError(f"replicates must be at least 1, got {replicates}")
    truth = labels.astype(np.float64)
    if truth.sum() == 0:
        raise ValueError("no positive window: AUPRC is undefined")
    order = np.argsort(blocks, kind="stable")
    ids, starts, lengths = np.unique(blocks[order], return_index=True, return_counts=True)
    positive_blocks = int(np.unique(blocks[truth > 0]).size)
    generator = np.random.default_rng(seed)
    values: list[float] = []
    lifts: list[float] = []
    discarded = 0
    for _ in range(replicates):
        drawn = generator.integers(0, ids.size, ids.size)
        sizes = lengths[drawn]
        offsets = np.repeat(starts[drawn] - (np.cumsum(sizes) - sizes), sizes)
        rows = order[np.arange(int(sizes.sum())) + offsets]
        sample = truth[rows]
        if sample.sum() == 0:
            discarded += 1
            continue
        value = average_precision(scores[rows], sample)
        values.append(value)
        lifts.append(value - float(sample.mean()))
    tail = (1.0 - confidence) / 2.0
    low, high = _quantiles(values, tail)
    lift_low, lift_high = _quantiles(lifts, tail)
    return AuprcInterval(
        unit=unit,
        auprc=average_precision(scores, truth),
        low=low,
        high=high,
        lift_low=lift_low,
        lift_high=lift_high,
        base_rate=float(truth.mean()),
        windows=int(truth.size),
        positives=int(truth.sum()),
        blocks=int(ids.size),
        positive_blocks=positive_blocks,
        replicates=replicates,
        discarded=discarded,
        confidence=confidence,
        seed=seed,
    )


def _quantiles(values: list[float], tail: float) -> tuple[float, float]:
    if not values:
        return math.nan, math.nan
    low, high = np.quantile(np.asarray(values), [tail, 1.0 - tail])
    return float(low), float(high)


@dataclass(frozen=True)
class GateVerdict:
    """ADR-0021's rule, applied.

    Attributes:
        evaluable: Whether the site can separate the model from chance.
        lower_bound: The interval's lower bound the rule read.
        base_rate: The line it had to clear, strictly.
        discarded_share: Share of replicates discarded.
        reason: One sentence saying why.
    """

    evaluable: bool
    lower_bound: float
    base_rate: float
    discarded_share: float
    reason: str


def decide_evaluable(interval: AuprcInterval, max_discarded_share: float = 0.01) -> GateVerdict:
    """Apply ADR-0021: evaluable only if the lower bound is strictly above the base rate.

    Args:
        interval: The block-bootstrap interval on the held-out site.
        max_discarded_share: Above this share of discarded replicates the interval is untrusted.

    Returns:
        The verdict.
    """
    share = interval.discarded_share
    if share > max_discarded_share or math.isnan(interval.low):
        reason = (
            f"{share:.2%} of replicates held no positive window, above "
            f"{max_discarded_share:.0%}; the interval is not trusted"
        )
        evaluable = False
    elif interval.low > interval.base_rate:
        reason = (
            f"the lower bound {interval.low:.4f} is above the base rate {interval.base_rate:.5f}"
        )
        evaluable = True
    else:
        reason = (
            f"the lower bound {interval.low:.4f} is not above the base rate "
            f"{interval.base_rate:.5f}"
        )
        evaluable = False
    return GateVerdict(
        evaluable=evaluable,
        lower_bound=interval.low,
        base_rate=interval.base_rate,
        discarded_share=share,
        reason=reason,
    )
