"""Cleaning transforms, ported from notebook cell 16 (docs/COURSE_PORT.md)."""

from __future__ import annotations

import pytest

from faultline.data.text.clean import (
    CleanConfig,
    clean_text,
    normalize_unicode,
    normalize_whitespace,
    remove_control_characters,
    remove_html,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<p>hello</p>", " hello "),
        ("a <br/> b", "a   b"),
        ("<div class='x'>y</div>", " y "),
        ("no markup here", "no markup here"),
        # Preserved wart: the notebook regex <[^>]+> is greedy about angle
        # brackets, so prose comparisons are eaten as if they were markup. The
        # port keeps the behaviour rather than silently improving it; see
        # docs/COURSE_PORT.md.
        ("2 < 3 and 4 > 1", "2   1"),
    ],
)
def test_remove_html(raw: str, expected: str) -> None:
    assert remove_html(raw) == expected


def test_normalize_unicode_nfkc() -> None:
    assert normalize_unicode("１５") == "15"
    assert normalize_unicode("ﬁle") == "file"


def test_remove_control_characters_keeps_newline_and_tab() -> None:
    assert remove_control_characters("a\x00b\x07c") == "abc"
    assert remove_control_characters("a\nb\tc") == "a\nb\tc"


def test_normalize_whitespace() -> None:
    assert normalize_whitespace("a    b") == "a b"
    assert normalize_whitespace("a\t\tb") == "a b"
    assert normalize_whitespace("a\n\n\n\nb") == "a\n\nb"
    assert normalize_whitespace("  padded  ") == "padded"


def test_clean_text_chain_order() -> None:
    # Entities are decoded before tags are stripped, so an escaped tag is stripped as
    # markup. This is the notebook behaviour and the port preserves it.
    assert clean_text("&lt;b&gt;bold&lt;/b&gt;") == "bold"


def test_clean_text_handles_crlf_and_entities() -> None:
    # CR is a control character and is dropped; LF is kept, so the paragraph break
    # survives as a single newline rather than collapsing into a space.
    assert clean_text("<p>a &amp; b</p>\r\n<p>c</p>") == "a & b \n c"


def test_clean_text_can_produce_empty() -> None:
    assert clean_text("<span></span>   \r\n\t  ") == ""


def test_switches_disable_steps() -> None:
    config = CleanConfig(remove_html_tags=False, unescape_html_entities=False)
    assert clean_text("<b>x</b>", config) == "<b>x</b>"
