"""The two regex generations, side by side.

``v0`` is the course reference notebook's regex, byte for byte. ``v1`` is
FaultLine's replacement. Both live here, in one file, so that the claim
``docs/COURSE_PORT.md`` makes -- that v0 is a faithful port and v1 is a deliberate
departure from it -- is checkable by reading twenty lines rather than by trusting a
sentence.

Nothing here changes what v0 does. A configuration selects a version; the default
everywhere is ``v0``, so the port keeps behaving like the port unless a config says
otherwise. ``configs/data/text_v1.yaml`` is the config that says otherwise, and it is
what FaultLine uses from M2 onward.

Two patterns have a v1. Both were found by running the port over the fixture corpus
at M0 and recorded then (``docs/COURSE_PORT.md``, ADR-0005); what changed since is
that ADR-0007 made one of them load-bearing.
"""

from __future__ import annotations

import re
from typing import Literal

#: Which generation of a pattern to apply.
PatternVersion = Literal["v0", "v1"]

# -- HTML tags -------------------------------------------------------------------------

#: Course notebook, cell 16. Everything from a ``<`` to the next ``>`` is markup.
HTML_TAG_V0 = re.compile(r"<[^>]+>")

#: FaultLine. A tag opens with ``<`` or ``</`` followed immediately by a *letter*,
#: so a ``<`` used as a comparison operator is left alone. HTML comments are still
#: removed, because they are markup by any reading.
#:
#: The case that forced this: ADR-0007 routes SCADA status messages through the text
#: pathway, and the second most frequent Kelmarsh status message is
#: ``Wind < start wind``. Under v0, that message combined with any later ``>`` in the
#: same document loses everything between them. The port's own documentation called
#: this wart harmless on TinyStories, and it was; it is not harmless here.
HTML_TAG_V1 = re.compile(
    r"<!--.*?-->|</?[A-Za-z][A-Za-z0-9:._-]*(?:\s[^<>]*)?/?>",
    re.DOTALL,
)

# -- telephone numbers -----------------------------------------------------------------

#: Course notebook, cell 32. Any run of nine or more digits, spaces and punctuation.
PHONE_V0 = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")

#: FaultLine. Anchored on telephone *formatting* rather than on digit count, which is
#: what ADR-0005 asked for. A number qualifies only if it looks like one of four
#: conventional shapes:
#:
#: * international, with an explicit country code: ``+44 1234 567890``
#: * a parenthesised area code: ``(0123) 456 7890``
#: * a national trunk number, three separated groups after a leading 0:
#:   ``020 7946 0958``
#: * the North American 3-3-4 grouping: ``555 123 4567``
#:
#: Every shape requires either a ``+`` or at least one separator between groups of at
#: least two digits, which is what excludes the false positives v0 produced: a bare
#: run of digits is never a phone number here. ``Serial number 8812349900`` and a
#: line of single digits both survive, and both were masked by v0.
#:
#: **What this trades away, stated:** recall. A two-group national number written
#: without a trunk prefix, or an unusual international format, is missed. ADR-0005
#: requires the false-positive rate to be measured against the real narrative corpus
#: before this is enabled on it; the corpus is an M2 artefact, so that measurement is
#: still owed. What is settled is that v1 does not eat serial numbers, and that is
#: the failure ADR-0005 was written about.
PHONE_V1 = re.compile(
    r"(?<![\w+])(?:"
    r"\+\d{1,3}[ .\-]?\d{2,5}(?:[ .\-]?\d{2,6}){1,3}"
    r"|\(0?\d{2,5}\)[ .\-]?\d{3,4}[ .\-]?\d{3,4}"
    r"|0\d{1,4}[ .\-]\d{3,4}[ .\-]\d{3,4}"
    r"|\d{3}[ .\-]\d{3}[ .\-]\d{4}"
    r")(?!\w)"
)

#: Tag pattern by version.
HTML_TAG_PATTERNS: dict[PatternVersion, re.Pattern[str]] = {
    "v0": HTML_TAG_V0,
    "v1": HTML_TAG_V1,
}

#: Phone pattern by version.
PHONE_PATTERNS: dict[PatternVersion, re.Pattern[str]] = {"v0": PHONE_V0, "v1": PHONE_V1}
