"""H3's vocabulary split under three conditions, and the pre-registered gate."""

from __future__ import annotations

from collections import Counter

import pandas as pd

from faultline.data.text.vocab_overlap import (
    CONDITIONS,
    HIGH,
    LOW,
    MIN_EVENTS_PER_SIDE,
    MIN_TYPES_PER_SIDE,
    SideCount,
    check_terms,
    count_sides,
    measure_condition,
    moves,
    partition,
)

BOOK = ["System OK", "Wind < start wind", "Yaw error", "Grid loss"]


def test_conditions_isolate_the_split_from_phmsa() -> None:
    by_name = {c.name: c for c in CONDITIONS}
    assert by_name["A"].corpus_name == "nrc_operator_narratives"
    assert by_name["B"].corpus_name == by_name["C"].corpus_name == "operator_narratives"
    assert not by_name["B"].keep()("phmsa_incident_narratives")
    assert by_name["B"].keep()("nrc_event_notifications")
    assert by_name["C"].keep()("phmsa_incident_narratives")


def test_measure_condition_counts_types_tokens_and_strings() -> None:
    frequency = Counter({"system": 500, "ok": 100, "wind": 150, "start": 99, "error": 1000})
    result = measure_condition("X", "x", BOOK, frequency, {"s": 1})
    # word types: system ok wind start yaw error grid loss
    assert result.types_total == 8
    assert result.types_frequent == 4  # system ok wind error
    assert result.types_seen == 5
    assert result.absent == ["grid", "loss", "yaw"]
    # word tokens: system ok | wind start wind | yaw error | grid loss = 9; frequent 5
    assert result.token_coverage == 5 / 9
    assert result.strings_frequent == 1  # only "System OK"


def test_moves_list_every_crossing_either_way() -> None:
    before = {"a": 0, "b": 0, "c": 50, "d": 150, "e": 5, "f": 120}
    after = {"a": 3, "b": 200, "c": 100, "d": 99, "e": 0, "f": 130}
    kinds = {m.word: m.kind for m in moves(before, after)}
    assert kinds == {
        "a": "absent -> present",
        "b": "absent -> frequent",
        "c": "rare -> frequent",
        "d": "frequent -> rare",
        "e": "present -> absent",
    }


def test_check_terms_separates_the_corpus_from_the_split() -> None:
    types = {"pressure", "yaw"}
    freq_b = Counter({"compressor": 200, "pressure": 9000, "yaw": 0, "rotor": 91})
    freq_c = Counter({"compressor": 1400, "pressure": 13000, "yaw": 1, "rotor": 95})
    pipeline = {
        t.term: t for t in check_terms(["compressor", "pressure"], types, freq_b, freq_c, True)
    }
    assert pipeline["compressor"].verdict.startswith("corpus: confirmed")
    assert "not a code-book word" in pipeline["compressor"].verdict
    assert "already frequent under B" in pipeline["pressure"].verdict
    wind = {t.term: t for t in check_terms(["yaw", "rotor"], types, freq_b, freq_c, False)}
    assert wind["yaw"].moved and wind["yaw"].verdict == "refutes 'no wind terms'"
    assert not wind["rotor"].moved  # rose, but stayed below the floor


def test_partition_is_every_word_frequent_under_the_condition() -> None:
    sides = partition(BOOK, Counter({"system": 100, "ok": 100, "grid": 500, "loss": 50}))
    assert sides == {
        "system ok": HIGH,
        "wind < start wind": LOW,
        "yaw error": LOW,
        "grid loss": LOW,
    }


def test_unmapped_events_are_on_neither_side_and_trip_the_gate() -> None:
    types = pd.Series([pd.NA] * 693, dtype="string")
    count = count_sides("hill_of_towie", "rule", types, {"system ok": HIGH}.get)
    assert count.unmapped == 693
    assert count.per_side == {HIGH: 0, LOW: 0}
    assert not count.testable()


def test_gate_needs_both_events_and_types_on_both_sides() -> None:
    def side_count(per_high: int, types_high: int, per_low: int, types_low: int) -> SideCount:
        return SideCount(
            source="s",
            reading="rule",
            events=per_high + per_low,
            unmapped=0,
            per_side={HIGH: per_high, LOW: per_low},
            types_per_side={
                HIGH: {f"h{i}": 1 for i in range(types_high)},
                LOW: {f"l{i}": 1 for i in range(types_low)},
            },
        )

    enough, types = MIN_EVENTS_PER_SIDE, MIN_TYPES_PER_SIDE
    assert side_count(enough, types, enough, types).testable()
    assert not side_count(enough - 1, types, enough, types).testable()
    assert not side_count(enough, types, enough, types - 1).testable()
    # the training sites' shape: many events, two types on the high side
    assert not side_count(44, 2, 675, 14).testable()
