"""Fixed boilerplate stripping and the general paragraph-frequency check.

Two artifacts, found by direct inspection of the modern-era (post-2020) event
notifications and declared as fixed rules (Gate-6 correction #2):

* ``EN_REVISION_HEADER_PATTERN`` -- the extractor's own metadata line pair,
  ``EN Revision Imported Date: <date> / EN Revision Text:``, prepended to the
  narrative rather than being page furniture NRC wrote; still not narrative
  content, so it is stripped the same way.
* ``IAEA_LESS_THAN_CAT3_PATTERN`` -- the fixed IAEA source-category explanation
  NRC appends whenever an event involves a "Less than Cat 3" source. Measured
  against the real corpus (2026-09-13): the header pattern matches all 1,316
  documents that contain the marker; the IAEA pattern matches 3,482 occurrences
  across the corpus, in two forms -- ending with the "For additional
  information" sentence and the Pub1227_web.pdf URL (2,616 occurrences, the
  modern-era form the brief named) or ending one sentence earlier, without the
  URL (the same fixed paragraph, used since at least 2005 -- found while
  building this rule, not in the brief, and included because it is unambiguously
  the same boilerplate). Three further occurrences carry a source-side URL typo
  (``www.pub.iaea.org`` for ``www-pub.iaea.org``, or a line-wrapped URL) and are
  not matched; left as a documented, measured gap rather than a regex chase.

The general check below is the second half of the same correction: split every
document into blank-line-delimited paragraphs, normalize internal whitespace,
and count how many *documents* (not raw occurrences) each distinct paragraph
appears in. Run against the real corpus, this finds exactly 7 paragraphs in
more than 100 documents, and every one of them is a short, genuine, formulaic
narrative sentence ("The licensee notified the NRC Resident Inspector.") that
recurs because many independent incident reports end the same way -- not page
furniture. None are stripped; see the checkpoint report addendum
(``reports/data/m2_checkpoint_20260913.md``) for the full list. The two
boilerplate blocks above are *not* found by this
sweep: both are joined to document-specific text by a single newline rather
than a blank line, so they are never their own paragraph. That is a real
limitation of paragraph-level hashing as a *discovery* method, stated plainly;
it does not affect the two rules above, which were found and are matched by
direct pattern, not by this sweep.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from faultline.config import StrictModel

_WHITESPACE = re.compile(r"\s+")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")

#: Any of the quote glyphs NRC's own copy-paste history has used around
#: "Less than Cat 3": straight, curly-single, curly-double.
_QUOTE = "[\"'‘’“”]"

#: The extractor's own metadata line pair, prepended to modern-era event text.
#: Tolerant of the two spacing variants found ("Date:" and "Date :") and of a
#: literal ``<br>`` separator instead of a newline (found in 2025 documents).
EN_REVISION_HEADER_PATTERN = re.compile(
    r"^EN Revision Imported Date\s*:\s*\S+\s*(?:<br\s*/?>\s*)*\n?\s*"
    r"(?:<br\s*/?>\s*)*EN Revision Text:\s*(?:<br\s*/?>\s*)*"
)

#: The fixed IAEA "Less than Cat 3" source-category explanation. The trailing
#: URL sentence is optional so the same rule matches both the modern-era form
#: (with it) and the older form (without it) -- the same fixed paragraph either
#: way; see the module docstring for the measured split between the two.
IAEA_LESS_THAN_CAT3_PATTERN = re.compile(
    rf"THIS MATERIAL EVENT CONTAINS A {_QUOTE}LESS THAN CAT 3{_QUOTE} LEVEL OF RADIOACTIVE "
    r"MATERIAL[.,]?\s+"
    rf"Sources that are {_QUOTE}Less than IAEA Category 3 sources,?{_QUOTE} are either sources "
    r"that are very unlikely to cause permanent injury to individuals or contain a very small "
    r"amount of radioactive material that would not cause any permanent injury\. Some of these "
    r"sources, such as moisture density gauges or thickness gauges that are Category 4, the "
    r"amount of unshielded radioactive material, if not safely managed or securely protected, "
    r"could possibly - although it is unlikely - temporarily injure someone who handled it or "
    r"were otherwise in contact with it, or who were close to it for a period of many weeks\."
    r"(?:\s+For additional information go to "
    r"http://www-pub\.iaea\.org/MTCD/publications/PDF/Pub1227_web\.pdf)?",
    re.IGNORECASE,
)

#: Declared rule name -> compiled pattern, in application order.
DECLARED_RULES: dict[str, re.Pattern[str]] = {
    "en_revision_header": EN_REVISION_HEADER_PATTERN,
    "iaea_less_than_cat3": IAEA_LESS_THAN_CAT3_PATTERN,
}


class BoilerplateConfig(StrictModel):
    """Which declared fixed-boilerplate rules to strip.

    Attributes:
        strip_en_revision_header: Strip the extractor metadata line pair.
        strip_iaea_less_than_cat3: Strip the fixed IAEA source-category
            explanation (both the URL-terminated and unterminated forms).
    """

    strip_en_revision_header: bool = False
    strip_iaea_less_than_cat3: bool = False


def strip_declared_boilerplate(text: str, config: BoilerplateConfig) -> tuple[str, dict[str, int]]:
    """Remove the enabled declared boilerplate patterns from one document.

    Args:
        text: Raw or partially cleaned document.
        config: Which rules are enabled.

    Returns:
        The document with matches removed, and a count of removals per enabled
        rule name (rules that are off are omitted, not reported as zero).
    """
    counts: dict[str, int] = {}
    if config.strip_en_revision_header:
        text, n = EN_REVISION_HEADER_PATTERN.subn("", text)
        counts["en_revision_header"] = n
    if config.strip_iaea_less_than_cat3:
        text, n = IAEA_LESS_THAN_CAT3_PATTERN.subn("", text)
        counts["iaea_less_than_cat3"] = n
    return text, counts


def boilerplate_counts(text: str, config: BoilerplateConfig) -> dict[str, int]:
    """Count matches of the enabled declared rules without modifying the text.

    Args:
        text: Document to inspect.
        config: Which rules are enabled.

    Returns:
        Match count per enabled rule name.
    """
    counts: dict[str, int] = {}
    if config.strip_en_revision_header:
        counts["en_revision_header"] = len(EN_REVISION_HEADER_PATTERN.findall(text))
    if config.strip_iaea_less_than_cat3:
        counts["iaea_less_than_cat3"] = len(IAEA_LESS_THAN_CAT3_PATTERN.findall(text))
    return counts


# --------------------------------------------------------------------------------------
# the general paragraph-frequency check
# --------------------------------------------------------------------------------------


def normalize_paragraph(paragraph: str) -> str:
    """Collapse internal whitespace so line-wrapping differences do not split a hash.

    Args:
        paragraph: Raw paragraph text.

    Returns:
        The paragraph with every run of whitespace collapsed to one space, and
        leading/trailing whitespace removed.
    """
    return _WHITESPACE.sub(" ", paragraph).strip()


def split_paragraphs(text: str) -> list[str]:
    """Split a document into normalized, non-empty, blank-line-delimited paragraphs.

    Args:
        text: Document body.

    Returns:
        Normalized paragraph strings, in document order.
    """
    return [
        normalized
        for raw in _PARAGRAPH_BREAK.split(text)
        if (normalized := normalize_paragraph(raw))
    ]


def paragraph_hash(paragraph: str) -> str:
    """Compute the identity of a normalized paragraph.

    Args:
        paragraph: Already-normalized paragraph text.

    Returns:
        The hex SHA-256 digest of the paragraph.
    """
    return hashlib.sha256(paragraph.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FrequentParagraph:
    """One paragraph that recurs verbatim across many documents.

    Attributes:
        text: The full normalized paragraph text.
        document_count: Number of distinct documents containing it (a paragraph
            repeated twice within one document counts once).
        first_120_chars: The first 120 characters, for a report table.
    """

    text: str
    document_count: int
    first_120_chars: str


def find_frequent_paragraphs(
    documents: Iterable[str], min_docs: int = 100
) -> list[FrequentParagraph]:
    """Find paragraphs that recur verbatim across more than `min_docs` documents.

    Args:
        documents: Document bodies to scan.
        min_docs: A paragraph must appear in more than this many distinct
            documents to be reported.

    Returns:
        Frequent paragraphs, most-common first.
    """
    doc_counts: Counter[str] = Counter()
    text_by_hash: dict[str, str] = {}
    for document in documents:
        for paragraph in set(split_paragraphs(document)):
            digest = paragraph_hash(paragraph)
            doc_counts[digest] += 1
            text_by_hash[digest] = paragraph
    frequent = [
        FrequentParagraph(
            text=text_by_hash[digest],
            document_count=count,
            first_120_chars=text_by_hash[digest][:120],
        )
        for digest, count in doc_counts.items()
        if count > min_docs
    ]
    frequent.sort(key=lambda item: item.document_count, reverse=True)
    return frequent
