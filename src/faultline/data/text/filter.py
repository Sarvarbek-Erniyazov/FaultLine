"""Quality filtering for text documents.

Ported from the course reference notebook (cells 21-23); see ``docs/COURSE_PORT.md``.
Thresholds and rule order are the notebook defaults. Rules are evaluated in a fixed
order and the *first* failing rule is the recorded drop reason, so per-rule counts
sum exactly to the number of dropped documents.
"""

from __future__ import annotations

from collections import Counter

from faultline.config import StrictModel

#: Rule names in evaluation order.
RULES: tuple[str, ...] = ("min_chars", "max_chars", "alpha_ratio", "repeated_lines")


class FilterConfig(StrictModel):
    """Quality thresholds applied to each cleaned document.

    Attributes:
        min_chars: Documents shorter than this are dropped.
        max_chars: Documents longer than this are dropped.
        min_alpha_ratio: Minimum share of alphabetic characters.
        max_repeated_line_ratio: Maximum share of lines that occur more than once.
    """

    min_chars: int = 200
    max_chars: int = 100_000
    min_alpha_ratio: float = 0.30
    max_repeated_line_ratio: float = 0.30


def alphabetic_ratio(text: str) -> float:
    """Compute the share of characters that are alphabetic.

    Args:
        text: Document to measure.

    Returns:
        A value in ``[0, 1]``; ``0.0`` for an empty document.
    """
    if not text:
        return 0.0
    alpha_count = sum(char.isalpha() for char in text)
    return alpha_count / len(text)


def repeated_line_ratio(text: str) -> float:
    """Compute the share of non-empty lines that occur more than once.

    Args:
        text: Document to measure.

    Returns:
        A value in ``[0, 1]``; ``0.0`` when the document has at most one non-empty line.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return 0.0
    counts = Counter(lines)
    repeated_lines = sum(count for count in counts.values() if count > 1)
    return repeated_lines / len(lines)


def filter_reason(text: str, config: FilterConfig) -> str | None:
    """Return the name of the first rule the document fails.

    Args:
        text: Cleaned document.
        config: Thresholds to apply.

    Returns:
        The failing rule name, or ``None`` when the document passes every rule.
    """
    if len(text) < config.min_chars:
        return "min_chars"
    if len(text) > config.max_chars:
        return "max_chars"
    if alphabetic_ratio(text) < config.min_alpha_ratio:
        return "alpha_ratio"
    if repeated_line_ratio(text) > config.max_repeated_line_ratio:
        return "repeated_lines"
    return None


def keeps(text: str, config: FilterConfig) -> bool:
    """Report whether a document passes every quality rule.

    Args:
        text: Cleaned document.
        config: Thresholds to apply.

    Returns:
        ``True`` when no rule fires.
    """
    return filter_reason(text, config) is None
