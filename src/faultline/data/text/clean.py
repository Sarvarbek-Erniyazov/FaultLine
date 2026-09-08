"""Text cleaning transforms.

Ported from the course reference notebook (cells 16-17); see ``docs/COURSE_PORT.md``.
The transform order is the notebook order and must not be changed casually: entity
decoding before tag stripping means an escaped ``&lt;b&gt;`` is stripped as markup,
which is what the reference pipeline did.

All functions here are pure: they take and return strings and never touch the
filesystem.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Literal

from faultline.config import StrictModel

_HTML_TAG = re.compile(r"<[^>]+>")
_INLINE_WHITESPACE = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")

#: Control characters kept by :func:`remove_control_characters` (course default).
KEEP_CONTROL_CHARS = "\n\t"

#: Unicode normalization forms accepted in the configuration.
NormalizationForm = Literal["NFC", "NFD", "NFKC", "NFKD"]


class CleanConfig(StrictModel):
    """Switches for the cleaning stage.

    Attributes:
        unescape_html_entities: Decode ``&amp;`` style entities before tag removal.
        remove_html_tags: Replace ``<...>`` spans with a single space.
        unicode_form: Unicode normalization form applied to every document.
        remove_control_chars: Drop Unicode category ``C`` characters other than
            newline and tab.
        normalize_whitespace: Collapse runs of spaces and blank lines, then strip.
        drop_empty: Discard documents that clean to an empty string.
    """

    unescape_html_entities: bool = True
    remove_html_tags: bool = True
    unicode_form: NormalizationForm = "NFKC"
    remove_control_chars: bool = True
    normalize_whitespace: bool = True
    drop_empty: bool = True


def remove_html(text: str) -> str:
    """Remove HTML/XML-like tags, replacing each with a space.

    Args:
        text: Input document.

    Returns:
        The document with tag spans replaced by single spaces.
    """
    return _HTML_TAG.sub(" ", text)


def normalize_unicode(text: str, form: NormalizationForm = "NFKC") -> str:
    """Apply Unicode normalization.

    Args:
        text: Input document.
        form: Normalization form, one of ``NFC``, ``NFKC``, ``NFD``, ``NFKD``.

    Returns:
        The normalized document.
    """
    return unicodedata.normalize(form, text)


def remove_control_characters(text: str, keep: str = KEEP_CONTROL_CHARS) -> str:
    """Drop control characters while preserving the listed ones.

    Args:
        text: Input document.
        keep: Characters that survive even if their Unicode category starts with C.

    Returns:
        The document without stray control characters.
    """
    return "".join(
        char for char in text if char in keep or not unicodedata.category(char).startswith("C")
    )


def normalize_whitespace(text: str) -> str:
    """Compress repeated whitespace and trim the document.

    Runs of spaces and tabs collapse to one space; runs of blank lines collapse to a
    single blank line, which preserves paragraph structure.

    Args:
        text: Input document.

    Returns:
        The whitespace-normalized, stripped document.
    """
    text = _INLINE_WHITESPACE.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def clean_text(text: str, config: CleanConfig | None = None) -> str:
    """Run the full cleaning chain over one document.

    Args:
        text: Raw document.
        config: Cleaning switches; course defaults when omitted.

    Returns:
        The cleaned document, possibly empty.
    """
    cfg = config or CleanConfig()
    if cfg.unescape_html_entities:
        text = html.unescape(text)
    if cfg.remove_html_tags:
        text = remove_html(text)
    text = normalize_unicode(text, cfg.unicode_form)
    if cfg.remove_control_chars:
        text = remove_control_characters(text)
    if cfg.normalize_whitespace:
        text = normalize_whitespace(text)
    return text
