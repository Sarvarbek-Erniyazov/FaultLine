"""F8-3's CPU half: ADR-0027 §5's four clauses, the sentence mapping and the per-arm gate source."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultline.config import load_config
from faultline.evaluation.ablation_gate import AblationGateConfig
from faultline.evaluation.ablation_verdict import (
    BRACKET,
    NEITHER_READING,
    NORMALIZED_RANDOM_RUN,
    AblationVerdict,
    decide_ablation,
    random_prefix,
    sentence_outcome,
    stratum_name,
    strike_bracket,
)
from faultline.evaluation.bootstrap import DeltaInterval

REPO = Path(__file__).resolve().parents[2]
GATE = load_config(REPO / "configs/eval/ablation_gate_v0.yaml", AblationGateConfig)
RULE = GATE.rule
SEEDS = (1, 2, 3)


def _delta(delta: float, low: float, high: float, discarded: int = 0) -> DeltaInterval:
    return DeltaInterval(
        unit="block",
        delta=delta,
        low=low,
        high=high,
        first_auprc=0.07,
        second_auprc=0.07 - delta,
        windows=137025,
        positives=5312,
        blocks=5799,
        positive_blocks=497,
        replicates=10000,
        discarded=discarded,
        confidence=0.95,
        seed=20260916,
    )


def _three(delta: float, low: float, high: float) -> dict[int, DeltaInterval]:
    return {s: _delta(delta, low, high) for s in SEEDS}


def _decide(deltas: dict[int, DeltaInterval]) -> AblationVerdict:
    return decide_ablation(deltas, RULE, GATE.bootstrap.max_discarded_share)


def test_hurts_needs_every_upper_bound_below_zero_and_the_median_below_the_effect() -> None:
    assert _decide(_three(-0.012, -0.020, -0.003)).verdict == "HURTS"
    # every upper bound below zero, but the median is not below -0.005
    assert _decide(_three(-0.004, -0.008, -0.001)).verdict == "INCONCLUSIVE"


def test_helps_needs_every_lower_bound_above_zero_and_the_median_above_the_effect() -> None:
    assert _decide(_three(0.012, 0.003, 0.020)).verdict == "HELPS"
    assert _decide(_three(0.004, 0.001, 0.008)).verdict == "INCONCLUSIVE"


def test_equivalent_needs_every_interval_strictly_inside_the_band() -> None:
    assert _decide(_three(0.0, -0.004, 0.004)).verdict == "EQUIVALENT"
    assert _decide(_three(0.0, -0.005, 0.004)).verdict == "INCONCLUSIVE"


def test_one_seed_spanning_zero_leaves_the_verdict_inconclusive() -> None:
    deltas = _three(-0.012, -0.020, -0.003)
    deltas[2] = _delta(-0.010, -0.021, 0.001)
    verdict = _decide(deltas)
    assert verdict.verdict == "INCONCLUSIVE"
    assert verdict.upper_below == {1: True, 2: False, 3: True}
    assert "seed(s) [2]" in verdict.reason


def test_a_seed_discarding_more_than_one_percent_counts_toward_no_clause() -> None:
    deltas = _three(-0.012, -0.020, -0.003)
    deltas[3] = _delta(-0.012, -0.020, -0.003, discarded=101)
    verdict = _decide(deltas)
    assert verdict.verdict == "INCONCLUSIVE"
    assert verdict.trusted[3] is False
    assert "discard more than 1%" in verdict.reason


def test_the_median_is_of_the_three_point_estimates() -> None:
    deltas = {1: _delta(-0.020, -0.03, -0.01), 2: _delta(-0.006, -0.02, -0.001)}
    deltas[3] = _delta(-0.001, -0.02, -0.0005)
    assert _decide(deltas).median_delta == pytest.approx(-0.006)


@pytest.mark.parametrize(
    ("arm", "verdict", "expected"),
    [
        ("joint_no_txt", "HURTS", "The unpaired narrative corpus does contribute"),
        (
            "joint_no_txt",
            "EQUIVALENT",
            "The unpaired narrative corpus does not measurably contribute",
        ),
        ("joint_status_raw", "HURTS", "prose surface form (H3') does matter"),
        ("joint_status_raw", "EQUIVALENT", "(H3') does not measurably matter"),
    ],
)
def test_hurts_and_equivalent_strike_one_bracket_as_section_5_maps_them(
    arm: str, verdict: str, expected: str
) -> None:
    sentence = next(s.sentence for s in GATE.sentences if s.arm == arm)
    struck = strike_bracket(sentence, verdict)
    assert struck is not None and expected in struck and BRACKET not in struck


@pytest.mark.parametrize(
    "verdict", ["HELPS", "INCONCLUSIVE", "NOT EVALUABLE", "REPORTED AS MEASURED"]
)
def test_every_other_verdict_strikes_neither_bracket(verdict: str) -> None:
    for sentence in GATE.sentences:
        assert strike_bracket(sentence.sentence, verdict) is None


def test_helps_is_reported_with_its_direction_and_inconclusive_as_undecided() -> None:
    sentence = GATE.sentences[0].sentence
    helps = _decide(_three(0.012, 0.003, 0.020))
    assert "higher" in sentence_outcome(sentence, helps)
    assert "neither bracket is struck" in sentence_outcome(sentence, helps)
    assert "undecided" in sentence_outcome(sentence, _decide(_three(0.0, -0.01, 0.01)))


def test_a_sentence_without_the_registered_alternatives_is_refused() -> None:
    with pytest.raises(ValueError, match="exactly once"):
        strike_bracket("The corpus does matter.", "HURTS")


def test_each_ablation_is_gated_against_the_random_init_scorings_section_4_names() -> None:
    assert random_prefix(GATE, "joint_no_txt") == NORMALIZED_RANDOM_RUN
    assert random_prefix(GATE, "joint_status_raw") == "random_init_raw"


def test_raw_strata_share_the_normalized_cache_only_when_row_identical() -> None:
    assert stratum_name("has_status", "raw", identical=True) == "has_status"
    assert stratum_name("has_status", "raw", identical=False) == "has_status_raw"
    assert stratum_name("no_status", "normalized", identical=False) == "no_status"


def test_the_neither_reading_sentence_is_section_5s_own_words() -> None:
    adr = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    section = adr[adr.index("### 5. The primary rule, per ablation") :]
    flat = " ".join(line.removeprefix("> ") for line in section.splitlines())
    flat = " ".join(flat.split())
    assert NEITHER_READING in flat
