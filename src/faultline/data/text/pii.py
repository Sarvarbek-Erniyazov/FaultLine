"""Personally identifiable information scrubbing.

Ported from the course reference notebook (cells 32-34); see ``docs/COURSE_PORT.md``.
The three regexes are the notebook's, unchanged.

One semantic change (ADR-0005): digit masking is **off** by default. The course
corpus is TinyStories, where a long digit run is noise; a FaultLine operator
narrative says things like "reactor power held at 850000 kW for six minutes" and
masking that destroys exactly the technical content the model has to learn. Emails
and phone numbers stay masked by default for every corpus. Each corpus records its
own setting on its dataset card.
"""

from __future__ import annotations

import re

from faultline.config import StrictModel

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
NUMBER_PATTERN = re.compile(r"(?<!\d)\d{6,}(?!\d)")

#: PII categories, in the order they are applied.
PII_KINDS: tuple[str, ...] = ("email", "phone", "digits")


class PIIConfig(StrictModel):
    """Which PII classes to mask and what to replace them with.

    Attributes:
        mask_emails: Replace email addresses (course default: on).
        mask_phones: Replace phone-like digit runs (course default: on).
        mask_digits: Replace digit runs of six or more (course default: on;
            FaultLine default: off, see ADR-0005).
        email_placeholder: Replacement token for emails.
        phone_placeholder: Replacement token for phone numbers.
        number_placeholder: Replacement token for long digit runs.
    """

    mask_emails: bool = True
    mask_phones: bool = True
    mask_digits: bool = False
    email_placeholder: str = "<EMAIL>"
    phone_placeholder: str = "<PHONE>"
    number_placeholder: str = "<NUMBER>"


def scrub_pii(text: str, config: PIIConfig | None = None) -> tuple[str, dict[str, int]]:
    """Replace configured PII patterns with placeholders.

    Args:
        text: Document to scrub.
        config: Which classes to mask; FaultLine defaults when omitted.

    Returns:
        A tuple of the scrubbed document and a count of replacements per class.
        Disabled classes report zero.
    """
    cfg = config or PIIConfig()
    stats = dict.fromkeys(PII_KINDS, 0)
    if cfg.mask_emails:
        text, stats["email"] = EMAIL_PATTERN.subn(cfg.email_placeholder, text)
    if cfg.mask_phones:
        text, stats["phone"] = PHONE_PATTERN.subn(cfg.phone_placeholder, text)
    if cfg.mask_digits:
        text, stats["digits"] = NUMBER_PATTERN.subn(cfg.number_placeholder, text)
    return text, stats
