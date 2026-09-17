"""ADR-0022's addendum: the one-sided rule, the checkpoint reader, and the resumable bootstrap."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from faultline.evaluation.bootstrap import DeltaInterval, window_blocks
from faultline.evaluation.checkpoint_selection import (
    FIXED_FINAL,
    SELECTED,
    decide_selection,
    read_checkpoints,
)
from faultline.evaluation.paired_control import PairedVerdict, paired_rows, paired_rows_cached
from faultline.evaluation.probe_control import ScoredWindows

REPO = Path(__file__).resolve().parents[2]


def interval(delta: float, low: float, high: float) -> DeltaInterval:
    return DeltaInterval(
        unit="block",
        delta=delta,
        low=low,
        high=high,
        first_auprc=0.05 + delta,
        second_auprc=0.05,
        windows=137_025,
        positives=5_312,
        blocks=5_799,
        positive_blocks=497,
        replicates=10_000,
        discarded=0,
        confidence=0.95,
        seed=20260916,
    )


def passing(lowest: float = 0.005) -> PairedVerdict:
    return PairedVerdict(True, lowest, "every paired lower bound is above zero")


# =====================================================================================
# the rule
# =====================================================================================


def test_fixed_final_is_adopted_when_nothing_is_worse_and_the_nine_cells_pass() -> None:
    verdict = decide_selection(
        {1: interval(+0.0041, +0.0022, +0.0066), 2: None, 3: interval(+0.0007, +0.0002, +0.0011)},
        {seed: passing() for seed in (1, 2, 3)},
    )
    assert verdict.rule == FIXED_FINAL
    assert verdict.fixed_final


def test_a_final_step_significantly_better_does_not_retain_the_selected_rule() -> None:
    # The clarification the addendum registers. Read as two-sided "agreement", an interval
    # entirely ABOVE zero fails and keeps the worse rule; the registered rule is one-sided.
    verdict = decide_selection({1: interval(+0.0041, +0.0022, +0.0066)}, {1: passing()})
    assert verdict.rule == FIXED_FINAL


def test_a_final_step_significantly_worse_on_any_seed_keeps_the_adr_0024_rule() -> None:
    verdict = decide_selection(
        {1: interval(+0.0041, +0.0022, +0.0066), 2: None, 3: interval(-0.0030, -0.0051, -0.0009)},
        {seed: passing() for seed in (1, 2, 3)},
    )
    assert verdict.rule == SELECTED
    assert not verdict.fixed_final
    assert "3" in verdict.reason


def test_a_failed_final_vs_final_cell_keeps_the_adr_0024_rule() -> None:
    verdict = decide_selection(
        {seed: None for seed in (1, 2, 3)},
        {
            1: passing(),
            2: PairedVerdict(False, -0.001, "1 of 3 paired lower bounds are not above zero"),
            3: passing(),
        },
    )
    assert verdict.rule == SELECTED
    assert "2" in verdict.reason


def test_a_seed_whose_two_checkpoints_coincide_cannot_fail_the_condition() -> None:
    # Δ is identically zero there, so it is stated and never bootstrapped.
    assert decide_selection({2: None}, {2: passing()}).rule == FIXED_FINAL


def test_the_rule_needs_both_measurements() -> None:
    with pytest.raises(ValueError, match="nine-cell"):
        decide_selection({}, {1: passing()})
    with pytest.raises(ValueError, match="nine-cell"):
        decide_selection({1: None}, {})


# =====================================================================================
# the checkpoint reader
# =====================================================================================


def write_scores(path: Path, seed: int, windows: int = 400) -> None:
    rng = np.random.default_rng(seed)
    labels = np.zeros(windows, dtype=np.float32)
    labels[::20] = 1.0
    np.savez(
        path,
        logits=rng.normal(size=windows).astype(np.float32),
        labels=labels,
        which=np.zeros(windows, dtype=np.int64),
        ends=np.arange(windows, dtype=np.int64) * 12,
        sources=np.array(["kelmarsh"]),
        prior_offset=np.float64(-3.0),
    )


def write_probe(path: Path, selected_step: int, last_step: int = 1000) -> None:
    history = [[step, 0.03] for step in (200, 700, last_step)]
    path.write_text(
        json.dumps({"selected": [selected_step, 0.04], "history": history}), encoding="utf-8"
    )


def test_a_probe_that_selected_its_last_step_has_one_checkpoint(tmp_path: Path) -> None:
    write_probe(tmp_path / "S2_trained_seed2_probe.json", 1000)
    write_scores(tmp_path / "S2_trained_seed2_stride12_scores.npz", 2)
    entry = read_checkpoints(tmp_path, "S2_trained_seed2", 12)
    assert entry.identical
    assert entry.final is entry.selected


def test_a_probe_that_selected_earlier_must_have_a_final_file(tmp_path: Path) -> None:
    write_probe(tmp_path / "S2_trained_seed3_probe.json", 700)
    write_scores(tmp_path / "S2_trained_seed3_stride12_scores.npz", 3)
    with pytest.raises(ValueError, match="must exist"):
        read_checkpoints(tmp_path, "S2_trained_seed3", 12)
    write_scores(tmp_path / "S2_trained_seed3_final_stride12_scores.npz", 33)
    entry = read_checkpoints(tmp_path, "S2_trained_seed3", 12)
    assert not entry.identical
    assert entry.final is not entry.selected


def test_a_final_file_beside_a_last_step_selection_is_refused(tmp_path: Path) -> None:
    write_probe(tmp_path / "S2_random_seed1_probe.json", 1000)
    write_scores(tmp_path / "S2_random_seed1_stride12_scores.npz", 1)
    write_scores(tmp_path / "S2_random_seed1_final_stride12_scores.npz", 11)
    with pytest.raises(ValueError, match="yet"):
        read_checkpoints(tmp_path, "S2_random_seed1", 12)


def test_missing_f3_outputs_are_named_not_guessed(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not on this machine"):
        read_checkpoints(tmp_path, "S2_trained_seed1", 12)


# =====================================================================================
# the resumable bootstrap
# =====================================================================================


def scored(seed: int, windows: int = 3_000) -> ScoredWindows:
    """Scores on ONE fixed set of windows and labels: only the logits differ by seed.

    A paired bootstrap refuses two scorers read on different windows, which is the property
    the cache must not be allowed to paper over.
    """
    rng = np.random.default_rng(seed)
    labels = np.zeros(windows, dtype=np.float32)
    for start in np.random.default_rng(0).choice(windows - 20, 60, replace=False):
        labels[start : start + 12] = 1.0
    return ScoredWindows(
        logits=(rng.normal(size=windows) + labels * 0.6).astype(np.float32),
        labels=labels,
        which=np.zeros(windows, dtype=np.int64),
        ends=np.arange(windows, dtype=np.int64) * 12,
        sources=["kelmarsh"],
        prior_offset=-3.0,
    )


def test_the_cache_reproduces_the_intervals_it_stood_in_for(tmp_path: Path) -> None:
    from faultline.evaluation.gate_check import BootstrapConfig

    bootstrap = BootstrapConfig(
        block_steps=288, replicates=200, seed=20260916, confidence=0.95, max_discarded_share=0.01
    )
    first, others = scored(1), [scored(2), scored(3)]
    cache = tmp_path / "nested" / "delta.json"
    fresh = paired_rows_cached(cache, first, others, ["kelmarsh"], bootstrap)
    assert cache.is_file()
    assert fresh == paired_rows(first, others, ["kelmarsh"], bootstrap)
    # A second call reads the JSON: same values, and no dependence on the scores it is given.
    assert (
        paired_rows_cached(cache, first, [scored(9), scored(9)], ["kelmarsh"], bootstrap) == fresh
    )


def test_a_cached_interval_round_trips_through_json(tmp_path: Path) -> None:
    cache = tmp_path / "delta.json"
    saved = replace(interval(+0.004, +0.002, +0.007), unit="block")
    cache.write_text(json.dumps([saved.__dict__], indent=1), encoding="utf-8")
    from faultline.evaluation.gate_check import BootstrapConfig

    bootstrap = BootstrapConfig(
        block_steps=288, replicates=1, seed=1, confidence=0.95, max_discarded_share=0.01
    )
    # The scores are never touched, because the cache is there.
    assert paired_rows_cached(cache, scored(1), [scored(2)], ["kelmarsh"], bootstrap) == [saved]


def test_the_blocks_the_cache_stands_in_for_are_the_registered_ones() -> None:
    windows = 3_000
    ends = np.arange(windows, dtype=np.int64) * 12
    blocks = window_blocks(ends, np.zeros(windows, dtype=np.int64), 288)
    # 288 steps is 48 hours at 10 minutes a step, twice the narrow_within_24h horizon.
    assert blocks.max() + 1 == int(np.ceil(windows * 12 / 288))
