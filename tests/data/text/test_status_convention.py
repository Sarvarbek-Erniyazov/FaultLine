"""H3' Stage A: the convention measurement and its pre-registered verdict (ADR-0017)."""

from __future__ import annotations

import re

import numpy as np

from faultline.data.text.status_convention import (
    CONVENTION_DOMINANT_ABOVE,
    NORMALIZED,
    RAW,
    ConventionCoverage,
    StageAResult,
    compare_with_word_level,
    first_token_only,
    measure_conventions,
    normalize_status,
)


class _PieceTokenizer:
    """One token per word, keeping its leading space and its case, as prose BPE does."""

    def __init__(self) -> None:
        self.ids: dict[str, int] = {}

    def encode(self, text: str) -> list[int]:
        return [self.ids.setdefault(p, len(self.ids)) for p in re.findall(r" ?\S+", text)]

    def decode_piece(self, token: int) -> str:
        return next(p for p, i in self.ids.items() if i == token)


def _frequency(tokenizer: _PieceTokenizer, frequent: set[str]) -> np.ndarray:
    return np.array([500 if p in frequent else 3 for p in tokenizer.ids], dtype=np.int64)


def test_normalize_status_lowercases_after_one_space() -> None:
    assert normalize_status("Wind < start wind") == " wind < start wind"


def test_first_token_only_matches_the_card_definition() -> None:
    frequency = np.array([3, 500, 500])
    assert first_token_only([0, 1, 2], frequency, 100)
    assert not first_token_only([1, 0, 2], frequency, 100)
    assert not first_token_only([0, 0], frequency, 100)


def test_measure_conventions_counts_coverage_diff_and_first_token_fixes() -> None:
    book = ["Wind ok", "Yaw error", "grid loss"]
    tokenizer = _PieceTokenizer()
    # pre-encode every convention so the id table is complete before frequencies exist
    for s in book:
        for text in (s, " " + s, s.lower(), normalize_status(s)):
            tokenizer.encode(text)
    frequency = _frequency(tokenizer, {" wind", " ok", " error", "grid", " loss", " grid"})

    coverage, changes, failures, fixed = measure_conventions(
        book, tokenizer.encode, tokenizer.decode_piece, frequency, threshold=100
    )
    by_name = {c.convention: c for c in coverage}
    # raw: "Wind" rare (first only), "Yaw" rare (first only), "grid loss" covered
    assert by_name[RAW].covered == 1
    # normalized: " wind ok" covered, " yaw" still rare, " grid loss" covered
    assert by_name[NORMALIZED].covered == 2
    assert failures == 2
    assert fixed == 1
    assert [(c.text, c.gained) for c in changes] == [("Wind ok", True)]
    assert changes[0].raw_pieces == ["Wind", " ok"]
    assert changes[0].normalized_pieces == [" wind", " ok"]
    # the added space is counted in the characters
    assert by_name[NORMALIZED].chars == by_name[RAW].chars + len(book)


def test_a_string_normalization_loses_is_listed_as_lost() -> None:
    tokenizer = _PieceTokenizer()
    for text in ("OK", " OK", "ok", " ok"):
        tokenizer.encode(text)
    frequency = _frequency(tokenizer, {"OK"})
    _coverage, changes, _failures, _fixed = measure_conventions(
        ["OK"], tokenizer.encode, tokenizer.decode_piece, frequency, threshold=100
    )
    assert [(c.text, c.gained) for c in changes] == [("OK", False)]


def _result(normalized: int) -> StageAResult:
    return StageAResult(
        strings=264,
        coverage=[
            ConventionCoverage(RAW, 18, 1, 1, 1),
            ConventionCoverage(NORMALIZED, normalized, 1, 1, 1),
        ],
        changes=[],
        first_token_failures=60,
        first_token_fixed=0,
        word_covered=80,
        normalized_not_word=[],
        word_not_normalized=[],
        narrative_bytes_per_token={},
        tokenizer_file="t",
        shard_dir="s",
        corpus_name="c",
    )


def test_the_verdict_line_is_strictly_above_fifty() -> None:
    assert CONVENTION_DOMINANT_ABOVE == 50
    assert not _result(50).convention_dominant()
    assert _result(51).convention_dominant()


def test_equal_counts_are_compared_as_sets() -> None:
    normalized_only, word_only = compare_with_word_level({"a", "b", "c"}, {"b", "c", "d"})
    assert normalized_only == ["a"]
    assert word_only == ["d"]
