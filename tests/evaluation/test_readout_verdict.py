"""F7'-3's CPU half: ADR-0026 §4's random-init gate, the row guard, and the NOT EVALUABLE path."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from faultline.evaluation.bootstrap import DeltaInterval
from faultline.evaluation.readout_verdict import (
    GATE_FAILURE_SENTENCE,
    assert_same_rows,
    decide_random_init_gate,
)

SEEDS = (1, 2, 3)


def _delta(low: float, high: float = 0.05, discarded: int = 0) -> DeltaInterval:
    return DeltaInterval(
        unit="block",
        delta=(low + high) / 2.0,
        low=low,
        high=high,
        first_auprc=0.07,
        second_auprc=0.03,
        windows=137025,
        positives=5312,
        blocks=5799,
        positive_blocks=497,
        replicates=10000,
        discarded=discarded,
        confidence=0.95,
        seed=20260916,
    )


def _pairs(
    lows: dict[str, float], discarded: dict[str, int] | None = None
) -> dict[str, DeltaInterval]:
    shares = discarded or {}
    return {k: _delta(v, discarded=shares.get(k, 0)) for k, v in lows.items()}


def _nine(low: float) -> dict[str, float]:
    return {f"joint{j}_rand{k}": low for j in SEEDS for k in SEEDS}


def test_gate_passes_only_when_all_nine_lower_bounds_clear_the_bound() -> None:
    gate = decide_random_init_gate(_pairs(_nine(0.01)), 9, 0.0, 0.01)
    assert (gate.passed, gate.cleared, gate.comparisons) == (True, 9, 9)
    assert gate.weakest[1] == pytest.approx(0.01)


@pytest.mark.parametrize("low", [0.0, -0.001])
def test_one_pair_not_strictly_above_the_bound_fails_the_gate(low: float) -> None:
    lows = _nine(0.01)
    lows["joint2_rand3"] = low
    gate = decide_random_init_gate(_pairs(lows), 9, 0.0, 0.01)
    assert not gate.passed
    assert (gate.cleared, gate.weakest[0]) == (8, "joint2_rand3")
    assert "joint2_rand3" in gate.reason


def test_an_untrusted_pair_cannot_clear_the_gate() -> None:
    lows = _nine(0.01)
    gate = decide_random_init_gate(_pairs(lows, {"joint1_rand1": 200}), 9, 0.0, 0.01)
    assert not gate.passed
    assert gate.untrusted == ["joint1_rand1"]
    assert gate.cleared == 8


def test_the_gate_refuses_a_count_other_than_the_registered_one() -> None:
    lows = _nine(0.01)
    del lows["joint3_rand3"]
    with pytest.raises(ValueError, match="registers 9 comparisons"):
        decide_random_init_gate(_pairs(lows), 9, 0.0, 0.01)


def test_the_failure_sentence_is_adr_0026s_own_words() -> None:
    assert "the tokens' embeddings, not the pretraining" in GATE_FAILURE_SENTENCE
    assert "untrained backbone already reads the status text" in GATE_FAILURE_SENTENCE


def _scores(path: Path, ends: np.ndarray, labels: np.ndarray) -> Path:
    np.savez(
        path,
        logits=np.zeros(labels.size, dtype=np.float32),
        labels=labels.astype(np.float32),
        which=np.zeros(labels.size, dtype=np.int64),
        ends=ends,
        sources=np.asarray(["a"]),
        prior_offset=np.asarray(-1.0),
    )
    return path


def test_misaligned_rows_are_refused_before_anything_is_paired(tmp_path: Path) -> None:
    ends = np.arange(10)
    labels = np.array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0])
    files = {
        "tel_only_1": _scores(tmp_path / "a.npz", ends, labels),
        "d_joint_1": _scores(tmp_path / "b.npz", ends[::-1].copy(), labels),
    }
    with pytest.raises(ValueError, match="does not cover F3's windows"):
        assert_same_rows(files, 10, 2)


def test_rows_other_than_the_registered_count_are_refused(tmp_path: Path) -> None:
    ends = np.arange(10)
    labels = np.array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0])
    files = {"tel_only_1": _scores(tmp_path / "a.npz", ends, labels)}
    with pytest.raises(ValueError, match="not the registered"):
        assert_same_rows(files, 137025, 5312)


def test_a_missing_scorer_is_named(tmp_path: Path) -> None:
    files = {"tel_only_1": tmp_path / "absent.npz"}
    with pytest.raises(FileNotFoundError, match="tel_only_1"):
        assert_same_rows(files, 10, 2)


def test_aligned_rows_pass_and_return_the_reference(tmp_path: Path) -> None:
    ends = np.arange(10)
    labels = np.array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0])
    files = {
        "tel_only_1": _scores(tmp_path / "a.npz", ends, labels),
        "d_joint_1": _scores(tmp_path / "b.npz", ends, labels),
    }
    reference = assert_same_rows(files, 10, 2)
    assert reference.labels.size == 10
    assert not math.isnan(reference.prior_offset)
