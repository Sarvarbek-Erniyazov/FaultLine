"""The paired probe-sensitivity test (ADR-0024): the paired bootstrap, the criterion, the config."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from faultline.config import load_config
from faultline.evaluation.bootstrap import (
    BlockDraws,
    DeltaInterval,
    bootstrap_auprc,
    paired_bootstrap_deltas,
    window_blocks,
)
from faultline.evaluation.metrics import average_precision
from faultline.evaluation.paired_control import (
    PairedControlConfig,
    _restricted,
    decide_paired,
)
from faultline.evaluation.probe_control import ProbeControlConfig, ScoredWindows

REPO = Path(__file__).resolve().parents[2]
SHIPPED = REPO / "configs/train/paired_control_v0.yaml"


def clustered(seed: int, windows: int = 6_000, runs: int = 120) -> tuple[np.ndarray, np.ndarray]:
    """Labels whose positives come in runs, and their blocks."""
    rng = np.random.default_rng(seed)
    labels = np.zeros(windows)
    for start in rng.choice(windows - 20, runs, replace=False):
        labels[start : start + 12] = 1.0
    ends = np.arange(windows, dtype=np.int64) * 12
    return labels, window_blocks(ends, np.zeros(windows, dtype=np.int64), 288)


def delta(low: float, discarded: int = 0) -> DeltaInterval:
    return DeltaInterval(
        unit="block",
        delta=low + 0.005,
        low=low,
        high=low + 0.01,
        first_auprc=0.05,
        second_auprc=0.04,
        windows=100,
        positives=10,
        blocks=10,
        positive_blocks=5,
        replicates=1000,
        discarded=discarded,
        confidence=0.95,
        seed=1,
    )


# ------------------------------------------------------------------ the paired bootstrap


def test_block_draws_are_the_intervals_draws() -> None:
    # The paired bootstrap reads the same replicates as each side's own interval.
    labels, blocks = clustered(0)
    rows = list(BlockDraws(blocks).replicates(3, seed=11))
    again = list(BlockDraws(blocks).replicates(3, seed=11))
    assert all(np.array_equal(a, b) for a, b in zip(rows, again, strict=True))
    # every window of a drawn block comes along
    for sample in rows:
        drawn, counts = np.unique(blocks[sample], return_counts=True)
        sizes = np.bincount(blocks)[drawn]
        assert np.all(counts % sizes == 0)


def test_pairing_narrows_the_interval_when_two_scorers_share_their_noise() -> None:
    labels, blocks = clustered(1)
    rng = np.random.default_rng(2)
    shared = rng.normal(size=labels.size) + 1.0 * labels
    better = shared + 0.1 * labels
    (paired,) = paired_bootstrap_deltas(better, [shared], labels, blocks, 400, seed=5)
    alone = [bootstrap_auprc(s, labels, blocks, 400, seed=5) for s in (better, shared)]
    assert paired.delta == pytest.approx(
        average_precision(better, labels) - average_precision(shared, labels)
    )
    assert paired.low > 0.0
    # the unpaired rule ADR-0023 used cannot see the same difference
    assert alone[0].low < alone[1].high
    assert paired.high - paired.low < (alone[0].high - alone[0].low)


def test_a_scorer_against_itself_has_a_zero_interval() -> None:
    labels, blocks = clustered(3)
    scores = np.random.default_rng(4).normal(size=labels.size) + labels
    (same,) = paired_bootstrap_deltas(scores, [scores.copy()], labels, blocks, 100, seed=0)
    assert same.delta == 0.0 and same.low == 0.0 and same.high == 0.0


def test_every_comparison_shares_the_reference_and_the_draws() -> None:
    labels, blocks = clustered(5)
    rng = np.random.default_rng(6)
    reference = rng.normal(size=labels.size) + labels
    others = [rng.normal(size=labels.size) + s * labels for s in (0.0, 0.5)]
    both = paired_bootstrap_deltas(reference, others, labels, blocks, 200, seed=9)
    one = paired_bootstrap_deltas(reference, others[1:], labels, blocks, 200, seed=9)
    assert both[1] == one[0]
    assert both[0].first_auprc == both[1].first_auprc


def test_paired_arguments_are_checked() -> None:
    labels, blocks = clustered(7)
    scores = np.zeros(labels.size)
    with pytest.raises(ValueError, match="at least one"):
        paired_bootstrap_deltas(scores, [], labels, blocks, 10, seed=0)
    with pytest.raises(ValueError, match="one entry per window"):
        paired_bootstrap_deltas(scores, [scores[:-1]], labels, blocks, 10, seed=0)
    with pytest.raises(ValueError, match="no positive"):
        paired_bootstrap_deltas(scores, [scores], np.zeros(labels.size), blocks, 10, seed=0)


# ------------------------------------------------------------------ the criterion


def test_every_lower_bound_must_be_above_zero() -> None:
    assert decide_paired([delta(0.001), delta(0.002), delta(0.0005)], 0.01).sensitive
    failing = decide_paired([delta(0.001), delta(-0.001), delta(0.002)], 0.01)
    assert not failing.sensitive and "1 of 3" in failing.reason


def test_a_lower_bound_of_exactly_zero_is_not_above_it() -> None:
    assert not decide_paired([delta(0.0)], 0.01).sensitive


def test_an_untrusted_comparison_fails() -> None:
    verdict = decide_paired([delta(0.01, discarded=11)], 0.01)
    assert not verdict.sensitive and "untrusted" in verdict.reason
    assert decide_paired([replace(delta(0.01), discarded=10)], 0.01).sensitive


def test_the_criterion_needs_a_comparison() -> None:
    with pytest.raises(ValueError, match="at least one"):
        decide_paired([], 0.01)


# ------------------------------------------------------------------ scores on disk


def test_restricting_scores_reindexes_their_sources(tmp_path: Path) -> None:
    path = tmp_path / "s.npz"
    np.savez(
        path,
        logits=np.arange(6, dtype=np.float32),
        labels=np.array([0, 1, 0, 1, 0, 1], dtype=np.float32),
        which=np.array([0, 0, 1, 1, 2, 2]),
        ends=np.array([5, 6, 7, 8, 9, 10]),
        sources=np.asarray(["hill_of_towie", "kelmarsh", "penmanshiel"]),
        prior_offset=np.asarray(-3.0),
    )
    kept = _restricted(ScoredWindows.load(path), ["kelmarsh", "penmanshiel"])
    assert kept.sources == ["kelmarsh", "penmanshiel"]
    assert kept.which.tolist() == [0, 0, 1, 1]
    assert kept.logits.tolist() == [2.0, 3.0, 4.0, 5.0]


# ------------------------------------------------------------------ the configuration


def test_the_shipped_order_is_the_one_registered_in_adr_0024() -> None:
    config = load_config(SHIPPED, PairedControlConfig)
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "## ADR-0024 The probe-sensitivity criterion is a paired test" in decisions
    designs = [load_config(REPO / c, ProbeControlConfig).design for c in config.control_configs]
    assert designs == [
        "final_position",
        "unfrozen_mlp_mean_pooled",
        "mean_pooled",
        "mlp_mean_pooled",
    ]
    assert config.stride == 12
    assert config.reproduction.selected_step == 166
    assert round(config.reproduction.pooled_auprc, 4) == 0.0502
    assert round(config.reproduction.selected_auprc, 4) == 0.0441
