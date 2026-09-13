"""Source-aware (keyed) deduplication for republished, revised documents.

Exact deduplication (``dedup.py``) removes byte-identical reposts. It does not
remove the other republishing pattern this corpus has: an NRC event notification
is filed under a stable event number (``enNNNNN``) and then *republished* on later
report days as the story develops, each later copy holding the earlier text
verbatim plus one or more appended ``"* * * UPDATE FROM ... * * *"`` blocks. Two
such copies are never byte-identical (the update text differs), so exact dedup
correctly leaves both in the corpus -- they are near-duplicates, not duplicates,
and the M2b brief's own near-duplicate trigger (``near_duplicates.py``) is a
random-pair sample that is structurally the wrong instrument for this: with
22,029 distinct event numbers spread across a corpus of tens of thousands of
documents, a random pair almost never lands on two revisions of the *same*
event, so the trigger measures true novel-content overlap correctly and reports
it as near zero, while never being asked about same-event revision chains at
all. This module is the keyed measurement that question actually needs, and the
declared rule it justifies: for ``nrc_event_notifications``, keep one document
per event number -- the latest report day.

Measured on the real corpus, in actual pipeline order (2026-09-13: cleaned,
filtered, then exact-deduped -- 27,662 survivors of ``nrc_event_notifications``
reaching this rule): 21,882 distinct event numbers, 3,901 with more than one
surviving document, 4,521 documents (1,214,427 whitespace tokens) removed by
keeping only the latest. Within multi-document groups the surviving revisions
grow monotonically (40/40 sampled pairs: the latest is never shorter than the
earliest) and the later text contains the earlier text near-verbatim (30/40
sampled pairs contain the earlier document's post-title body, normalized, as a
substring of the later one; the rest differ only in a reworded opening
sentence, not a rewrite). See
``reports/data/20260913-142340_all_text_2a6ec5b7/dedup_stats_report.md`` for
the generated report and ADR-0016 for the decision record.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any

from faultline.config import StrictModel

#: Extracts (report day, event number) from an NRC event-notification doc_id,
#: e.g. ``"20030425en_en39780"`` -> ``("20030425", "en39780")``. No other staged
#: source uses this shape (``in00013``, ``bl71001``, ``gl77001``, ``ri00001`` all
#: lack the day-prefix/underscore structure), so the pattern alone is already a
#: safe filter; ``KeyedDedupConfig.source`` is the explicit, declared guard on top
#: of that so the rule's scope is a config value, not an implicit regex property.
EVENT_KEY_PATTERN = re.compile(r"^(?P<day>\d{8})en_(?P<event>en\d+)$")


def event_key(doc_id: str) -> tuple[str, str] | None:
    """Extract (report day, event number) from an event-notification doc_id.

    Args:
        doc_id: Document identifier.

    Returns:
        ``(day, event_number)`` sorted so that string comparison of ``day``
        orders chronologically (it is zero-padded ``YYYYMMDD``), or ``None`` if
        `doc_id` does not have the event-notification shape.
    """
    match = EVENT_KEY_PATTERN.match(doc_id)
    if match is None:
        return None
    return match.group("day"), match.group("event")


class KeyedDedupConfig(StrictModel):
    """Keep only the latest revision per key, for one source.

    Attributes:
        enabled: Whether this rule runs at all. Off by default so every config
            that does not mention it keeps exact dedup as the whole story.
        source: The record's ``source`` field this rule applies to; records from
            any other source pass through untouched.
    """

    enabled: bool = False
    source: str = "nrc_event_notifications"


class KeyedDeduplicator:
    """Streaming keep-latest-revision filter, keyed on event number.

    Only the current latest-day record per key is held in memory at any time --
    memory grows with the number of *distinct* keys, not with the number of
    revisions, mirroring :class:`~faultline.data.text.dedup.ExactDeduplicator`'s
    memory model. A record is only ever superseded, never re-emitted early,
    because an earlier report day cannot be known to be final until the whole
    input has been read.

    Attributes:
        config: The settings used to select which records this rule touches.
    """

    def __init__(self, config: KeyedDedupConfig) -> None:
        """Initialize an empty deduplicator.

        Args:
            config: Keyed-dedup settings.
        """
        self.config = config
        self._latest: dict[str, tuple[str, dict[str, Any]]] = {}
        self._seen_counts: dict[str, int] = {}

    def run(
        self,
        records: Iterable[dict[str, Any]],
        doc_id_field: str = "doc_id",
        source_field: str = "source",
    ) -> Iterator[dict[str, Any]]:
        """Filter a stream, keeping only the latest revision per key.

        Args:
            records: Input stream, already exact-deduplicated.
            doc_id_field: Field holding the document identifier.
            source_field: Field holding the source name.

        Yields:
            Every record whose source does not match `config.source`, or whose
            ``doc_id`` does not have the event-notification shape, immediately
            and unchanged; then, once the input is exhausted, one record per
            key (the latest by report day).
        """
        if not self.config.enabled:
            yield from records
            return
        for record in records:
            if record.get(source_field) != self.config.source:
                yield record
                continue
            key = event_key(str(record.get(doc_id_field, "")))
            if key is None:
                yield record
                continue
            day, event = key
            self._seen_counts[event] = self._seen_counts.get(event, 0) + 1
            current = self._latest.get(event)
            if current is None or day >= current[0]:
                self._latest[event] = (day, record)
        yield from (record for _, record in self._latest.values())

    @property
    def groups_seen(self) -> int:
        """Number of distinct keys observed among matching-source records."""
        return len(self._seen_counts)

    @property
    def groups_with_multiple(self) -> int:
        """Number of keys with more than one surviving revision."""
        return sum(1 for count in self._seen_counts.values() if count > 1)

    @property
    def documents_removed(self) -> int:
        """Total superseded revisions removed across every key."""
        return sum(count - 1 for count in self._seen_counts.values())
