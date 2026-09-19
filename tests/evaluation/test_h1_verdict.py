"""F6-3's CPU half: cached replicate vectors reproduce ADR-0024's intervals; ADR-0025 §5's rule."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from faultline.evaluation.bootstrap import (
    DeltaInterval,
    bootstrap_auprc,
    paired_bootstrap_deltas,
    window_blocks,
)
from faultline.evaluation.gate_check import BootstrapConfig
from faultline.evaluation.h1_verdict import (
    ReplicateJob,
    decide_h1,
    delta_interval,
    run_job,
    single_interval,
    stratum,
)
from faultline.evaluation.probe_control import ScoredWindows

BOOTSTRAP = BootstrapConfig(
    block_steps=10, replicates=400, seed=7, confidence=0.95, max_discarded_share=0.01
)


def _scores(path: Path, logits: np.ndarray, labels: np.ndarray, ends: np.ndarray) -> Path:
    np.savez(
        path,
        logits=logits.astype(np.float32),
        labels=labels.astype(np.float32),
        which=(np.arange(labels.size) % 2).astype(np.int64),
        ends=ends,
        sources=np.asarray(["a", "b"]),
        prior_offset=np.asarray(-1.0),
    )
    return path


@pytest.mark.parametrize("masked", [False, True])
def test_cached_vectors_reproduce_bootstrap_auprc_and_paired_deltas(
    tmp_path: Path, masked: bool
) -> None:
    rng = np.random.default_rng(0)
    n = 600
    labels = (rng.random(n) < 0.08).astype(np.float64)
    ends = np.arange(n) // 2
    first = _scores(tmp_path / "a.npz", labels * 1.5 + rng.normal(size=n), labels, ends)
    second = _scores(tmp_path / "b.npz", labels * 0.5 + rng.normal(size=n), labels, ends)
    mask = (rng.random(n) < 0.7) if masked else np.ones(n, dtype=bool)
    reference = ScoredWindows.load(first)
    where = stratum("s", mask, reference, BOOTSTRAP.block_steps)
    va, vb = tmp_path / "va.npz", tmp_path / "vb.npz"
    run_job(ReplicateJob(va, first, mask, BOOTSTRAP))
    run_job(ReplicateJob(vb, second, mask, BOOTSTRAP))
    a, b = ScoredWindows.load(first), ScoredWindows.load(second)
    blocks = window_blocks(a.ends[mask], a.which[mask], BOOTSTRAP.block_steps)
    sa = a.logits[mask] + a.prior_offset
    sb = b.logits[mask] + b.prior_offset
    args = (BOOTSTRAP.replicates, BOOTSTRAP.seed, BOOTSTRAP.confidence)
    expected = bootstrap_auprc(sa, a.labels[mask], blocks, *args)
    got = single_interval(va, first, where, BOOTSTRAP)
    for field in ("auprc", "low", "high", "lift_low", "lift_high", "base_rate", "discarded"):
        assert getattr(got, field) == pytest.approx(getattr(expected, field), abs=1e-12)
    assert (got.blocks, got.positive_blocks) == (expected.blocks, expected.positive_blocks)
    paired = paired_bootstrap_deltas(sa, [sb], a.labels[mask], blocks, *args)[0]
    delta = delta_interval((va, first), (vb, second), where, BOOTSTRAP)
    for field in ("delta", "low", "high", "first_auprc", "second_auprc", "discarded"):
        assert getattr(delta, field) == pytest.approx(getattr(paired, field), abs=1e-12)


def _d(delta: float, low: float, high: float, discarded: int = 0) -> DeltaInterval:
    return DeltaInterval(
        unit="block",
        delta=delta,
        low=low,
        high=high,
        first_auprc=0.0,
        second_auprc=0.0,
        windows=1,
        positives=1,
        blocks=1,
        positive_blocks=1,
        replicates=10000,
        discarded=discarded,
        confidence=0.95,
        seed=1,
    )


def _decide(deltas: dict[int, DeltaInterval]) -> str:
    return decide_h1(deltas, 0.005, 0.0, 0.005, 0.005, 0.01).verdict


def test_the_rule_reads_supported_refuted_and_inconclusive_as_registered() -> None:
    assert (
        _decide({1: _d(0.01, 0.001, 0.02), 2: _d(0.008, 0.002, 0.02), 3: _d(0.006, 0.0001, 0.01)})
        == "SUPPORTED"
    )
    # Every lower bound above zero but the median at or below 0.005: not SUPPORTED.
    assert (
        _decide({1: _d(0.004, 0.001, 0.008), 2: _d(0.005, 0.001, 0.009), 3: _d(0.009, 0.001, 0.02)})
        == "INCONCLUSIVE"
    )
    assert (
        _decide(
            {1: _d(-0.01, -0.02, 0.004), 2: _d(0.0, -0.004, 0.0049), 3: _d(-0.02, -0.03, -0.01)}
        )
        == "REFUTED"
    )
    assert (
        _decide({1: _d(-0.01, -0.02, 0.004), 2: _d(0.0, -0.004, 0.006), 3: _d(-0.02, -0.03, -0.01)})
        == "INCONCLUSIVE"
    )


def test_a_comparison_discarding_over_one_percent_counts_toward_neither_clause() -> None:
    refuted = {1: _d(-0.01, -0.02, 0.004), 2: _d(0.0, -0.004, 0.0049), 3: _d(-0.02, -0.03, -0.01)}
    refuted[3] = _d(-0.02, -0.03, -0.01, discarded=101)
    assert _decide(refuted) == "INCONCLUSIVE"
    both = {s: _d(0.006, 0.001, 0.004) for s in (1, 2, 3)}  # a Δ outside its own interval
    assert _decide(both) == "SUPPORTED_AND_REFUTED"
