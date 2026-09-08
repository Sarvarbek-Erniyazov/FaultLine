"""Quality filtering, ported from notebook cells 21-23."""

from __future__ import annotations

from faultline.data.text.filter import (
    FilterConfig,
    alphabetic_ratio,
    filter_reason,
    keeps,
    repeated_line_ratio,
)


def test_course_defaults_are_preserved() -> None:
    config = FilterConfig()
    assert config.min_chars == 200
    assert config.max_chars == 100_000
    assert config.min_alpha_ratio == 0.30
    assert config.max_repeated_line_ratio == 0.30


def test_alphabetic_ratio() -> None:
    assert alphabetic_ratio("") == 0.0
    assert alphabetic_ratio("abcd") == 1.0
    assert alphabetic_ratio("ab12") == 0.5
    assert alphabetic_ratio("1234") == 0.0


def test_repeated_line_ratio() -> None:
    assert repeated_line_ratio("") == 0.0
    assert repeated_line_ratio("only one line") == 0.0
    assert repeated_line_ratio("a\nb\nc") == 0.0
    assert repeated_line_ratio("a\na\nb") == 2 / 3
    assert repeated_line_ratio("a\na\na") == 1.0
    # blank lines are ignored, and lines are compared stripped
    assert repeated_line_ratio("a\n\n  a  \nb") == 2 / 3


def test_first_failing_rule_wins() -> None:
    config = FilterConfig(min_chars=10, max_chars=50, min_alpha_ratio=0.5)
    # too short AND low alpha ratio; min_chars is checked first, so that is the reason
    assert filter_reason("12345", config) == "min_chars"
    assert filter_reason("x" * 100, config) == "max_chars"
    assert filter_reason("1234567890123", config) == "alpha_ratio"
    assert filter_reason("hello there friend", config) is None


def test_repeated_lines_rule() -> None:
    config = FilterConfig(min_chars=1, min_alpha_ratio=0.0, max_repeated_line_ratio=0.3)
    assert filter_reason("same\nsame\nsame\nsame", config) == "repeated_lines"


def test_keeps_matches_filter_reason() -> None:
    config = FilterConfig(min_chars=5)
    assert keeps("hello world", config) is True
    assert keeps("hi", config) is False
