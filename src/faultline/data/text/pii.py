"""Personally identifiable information scrubbing.

Ported from the course reference notebook (cells 32-34); see ``docs/COURSE_PORT.md``.
The three regexes are the notebook's, unchanged.

One semantic change (ADR-0005): digit masking is **off** by default. The course
corpus is TinyStories, where a long digit run is noise; a FaultLine operator
narrative says things like "reactor power held at 850000 kW for six minutes" and
masking that destroys exactly the technical content the model has to learn. Emails
and phone numbers stay masked by default for every corpus. Each corpus records its
own setting on its dataset card.

The phone regex has two generations, selected by ``pii.phone_pattern`` and defined
alongside the notebook's in :mod:`faultline.data.text.patterns`. The default is the
notebook's. ADR-0005 recorded that turning digit masking off does not protect
technical content on its own, because the phone pattern eats serial numbers anyway;
``v1`` is the replacement that record asked for.
"""

from __future__ import annotations

import re

from faultline.config import StrictModel
from faultline.data.text.patterns import PHONE_PATTERNS, PatternVersion

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
NUMBER_PATTERN = re.compile(r"(?<!\d)\d{6,}(?!\d)")

#: The course notebook's phone regex, kept under its original name.
PHONE_PATTERN = PHONE_PATTERNS["v0"]

#: PII categories, in the order they are applied.
PII_KINDS: tuple[str, ...] = ("email", "phone", "digits")


class PIIConfig(StrictModel):
    """Which PII classes to mask and what to replace them with.

    Attributes:
        mask_emails: Replace email addresses (course default: on).
        mask_phones: Replace phone-like digit runs (course default: on).
        mask_digits: Replace digit runs of six or more (course default: on;
            FaultLine default: off, see ADR-0005).
        phone_pattern: Which generation of the phone regex to apply. ``v0`` is the
            course notebook's, which masks any run of nine or more digits and so
            eats serial numbers; ``v1`` is anchored on telephone formatting.
            Defaults to ``v0`` so the port keeps behaving like the port.
        email_placeholder: Replacement token for emails.
        phone_placeholder: Replacement token for phone numbers.
        number_placeholder: Replacement token for long digit runs.
    """

    mask_emails: bool = True
    mask_phones: bool = True
    mask_digits: bool = False
    phone_pattern: PatternVersion = "v0"
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
        text, stats["phone"] = PHONE_PATTERNS[cfg.phone_pattern].subn(cfg.phone_placeholder, text)
    if cfg.mask_digits:
        text, stats["digits"] = NUMBER_PATTERN.subn(cfg.number_placeholder, text)
    return text, stats
