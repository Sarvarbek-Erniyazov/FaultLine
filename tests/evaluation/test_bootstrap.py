"""ADR-0021's within-seed interval: block resampling, and a gate that can fail."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from faultline.evaluation.bootstrap import (
    AuprcInterval,
    bootstrap_auprc,
    decide_evaluable,
    window_blocks,
)
from faultline.evaluation.gate_check import window_ends
from faultline.evaluation.ladder import SplitEval
from faultline.training.windows import WindowSampler, WindowSet


def _clustered(
    seed: int, signal: float, windows: int = 6_000, runs: int = 120
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Windows whose positives come in runs of consecutive steps, as event horizons make them."""
    rng = np.random.default_rng(seed)
    ends = np.arange(windows, dtype=np.int64) * 12
    labels = np.zeros(windows)
    for start in rng.choice(windows - 20, runs, replace=False):
        labels[start : start + 12] = 1.0
    scores = rng.normal(size=windows) + signal * labels
    return scores, labels, window_blocks(ends, np.zeros(windows, dtype=np.int64), 288)


# ------------------------------------------------------------------ blocks


def test_a_block_is_shared_only_within_one_shard_and_one_span() -> None:
    ends = np.array([0, 287, 288, 0, 575], dtype=np.int64)
    sets = np.array([0, 0, 0, 1, 0], dtype=np.int64)
    blocks = window_blocks(ends, sets, 288)
    assert blocks[0] == blocks[1]
    assert blocks[1] != blocks[2]
    assert blocks[0] != blocks[3]
    assert blocks[2] == blocks[4]


def test_block_arguments_are_checked() -> None:
    with pytest.raises(ValueError, match="block_steps"):
        window_blocks(np.zeros(2, np.int64), np.zeros(2, np.int64), 0)
    with pytest.raises(ValueError, match="shape"):
        window_blocks(np.zeros(2, np.int64), np.zeros(3, np.int64), 288)


# ------------------------------------------------------------------ the interval


def test_the_interval_is_seeded_and_brackets_the_point_estimate() -> None:
    scores, labels, blocks = _clustered(0, signal=1.0)
    first = bootstrap_auprc(scores, labels, blocks, 300, seed=7)
    again = bootstrap_auprc(scores, labels, blocks, 300, seed=7)
    assert first == again
    assert first.low < first.auprc < first.high
    assert first.positives == int(labels.sum())
    assert first.positive_blocks < first.positives
    assert first.lift_low < first.auprc - first.base_rate < first.lift_high


def test_clustered_positives_widen_the_block_interval_over_the_window_interval() -> None:
    # the reason the unit is a block: resampling windows treats a run of positives as
    # independent draws and understates the interval
    scores, labels, blocks = _clustered(1, signal=1.0)
    block = bootstrap_auprc(scores, labels, blocks, 400, seed=3)
    window = bootstrap_auprc(
        scores, labels, np.arange(labels.size, dtype=np.int64), 400, seed=3, unit="window"
    )
    assert block.high - block.low > 1.3 * (window.high - window.low)


def test_no_positive_window_is_refused() -> None:
    with pytest.raises(ValueError, match="no positive"):
        bootstrap_auprc(np.zeros(4), np.zeros(4), np.arange(4, dtype=np.int64), 10, seed=0)


# ------------------------------------------------------------------ the gate


def test_a_scorer_with_signal_is_evaluable() -> None:
    scores, labels, blocks = _clustered(2, signal=3.0)
    verdict = decide_evaluable(bootstrap_auprc(scores, labels, blocks, 300, seed=0))
    assert verdict.evaluable
    assert verdict.lower_bound > verdict.base_rate


def test_a_scorer_without_signal_is_not_evaluable() -> None:
    scores, labels, blocks = _clustered(4, signal=0.0)
    verdict = decide_evaluable(bootstrap_auprc(scores, labels, blocks, 300, seed=0))
    assert not verdict.evaluable
    assert "not above" in verdict.reason


def _interval(low: float, base_rate: float, discarded: int = 0) -> AuprcInterval:
    return AuprcInterval(
        unit="block",
        auprc=0.05,
        low=low,
        high=0.07,
        lift_low=0.0,
        lift_high=0.03,
        base_rate=base_rate,
        windows=12_000,
        positives=399,
        blocks=5_983,
        positive_blocks=274,
        replicates=10_000,
        discarded=discarded,
        confidence=0.95,
        seed=20260916,
    )


def test_a_lower_bound_equal_to_the_base_rate_is_not_above_it() -> None:
    assert not decide_evaluable(_interval(low=0.03325, base_rate=0.03325)).evaluable
    assert decide_evaluable(_interval(low=0.03326, base_rate=0.03325)).evaluable
    # the ruling's rounded 0.033 is not the line: a bound between the two fails
    assert not decide_evaluable(_interval(low=0.0331, base_rate=0.03325)).evaluable


def test_too_many_discarded_replicates_make_the_interval_untrusted() -> None:
    good = _interval(low=0.04, base_rate=0.03325)
    assert decide_evaluable(replace(good, discarded=100)).evaluable
    verdict = decide_evaluable(replace(good, discarded=101))
    assert not verdict.evaluable
    assert "not trusted" in verdict.reason


# ------------------------------------------------------------------ scored order


def test_window_ends_follow_the_order_a_test_pass_scores(tmp_path: Path) -> None:
    sets = []
    for position, offset in enumerate((1_000, 5_000)):
        path = tmp_path / f"{position}.bin"
        np.zeros(40, dtype=np.uint16).tofile(path)
        sets.append(
            WindowSet(
                key=f"s{position}__test",
                tokens=np.memmap(path, dtype=np.uint16, mode="r", shape=(40,)),
                starts=np.arange(4, dtype=np.int64),
                ends=np.arange(4, dtype=np.int64) + offset,
                labels=np.zeros(4, dtype=np.float32),
                years=np.full(4, 2020, dtype=np.int64),
            )
        )
    sampler = WindowSampler(sets, batch_size=3, tokens_per_step=1, context_steps=1, labelled=True)
    split = SplitEval(
        sampler=sampler, sources=["s0", "s1"], shares={}, years=np.zeros(8), sets=np.zeros(8)
    )
    expected = []
    for _, _, which in sampler.epoch():
        expected.extend(which.tolist())
    ends = window_ends(split)
    index = sampler.index
    assert index[:, 0].tolist() == expected
    assert ends.tolist() == [sets[int(i)].ends[int(r)] for i, r in index]
