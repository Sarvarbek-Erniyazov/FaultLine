"""Source-aware (keyed) deduplication, the M2 Gate-6 correction."""

from __future__ import annotations

from faultline.data.text.keyed_dedup import (
    KeyedDedupConfig,
    KeyedDeduplicator,
    event_key,
)


def test_event_key_extracts_day_and_event_number() -> None:
    assert event_key("20030425en_en39780") == ("20030425", "en39780")


def test_event_key_rejects_other_doc_id_shapes() -> None:
    assert event_key("in00013") is None
    assert event_key("bl71001") is None
    assert event_key("gl77001") is None
    assert event_key("ri00001") is None
    assert event_key("not-a-doc-id") is None


def _record(doc_id: str, source: str = "nrc_event_notifications", **extra: object) -> dict:
    return {"doc_id": doc_id, "source": source, "text": doc_id, **extra}


def test_disabled_is_a_no_op() -> None:
    dedup = KeyedDeduplicator(KeyedDedupConfig(enabled=False))
    records = [_record("20030425en_en39780"), _record("20030428en_en39780")]
    assert list(dedup.run(records)) == records
    assert dedup.groups_seen == 0
    assert dedup.documents_removed == 0


def test_keeps_only_the_latest_revision_per_event_number() -> None:
    dedup = KeyedDeduplicator(KeyedDedupConfig(enabled=True))
    records = [
        _record("20030425en_en39780"),
        _record("20030428en_en39780"),
        _record("20030101en_en40000"),  # single-revision event, untouched
    ]
    kept = list(dedup.run(records))
    kept_ids = {record["doc_id"] for record in kept}
    assert kept_ids == {"20030428en_en39780", "20030101en_en40000"}
    assert dedup.groups_seen == 2
    assert dedup.groups_with_multiple == 1
    assert dedup.documents_removed == 1


def test_input_order_does_not_matter_latest_day_wins() -> None:
    # Revisions arriving out of chronological order still resolve to the latest day.
    dedup = KeyedDeduplicator(KeyedDedupConfig(enabled=True))
    records = [
        _record("20030428en_en39780"),
        _record("20030101en_en39780"),
        _record("20030601en_en39780"),
    ]
    kept = list(dedup.run(records))
    assert [record["doc_id"] for record in kept] == ["20030601en_en39780"]


def test_only_the_configured_source_is_touched() -> None:
    dedup = KeyedDeduplicator(KeyedDedupConfig(enabled=True, source="nrc_event_notifications"))
    records = [
        _record("20030425en_en39780"),
        _record("20030428en_en39780"),
        _record("in00013", source="nrc_info_notices"),
    ]
    kept = list(dedup.run(records))
    kept_ids = {record["doc_id"] for record in kept}
    assert kept_ids == {"20030428en_en39780", "in00013"}


def test_unrecognised_doc_id_shape_passes_through_unaffected() -> None:
    dedup = KeyedDeduplicator(KeyedDedupConfig(enabled=True))
    records = [_record("weird-doc-id")]
    assert list(dedup.run(records)) == records
    assert dedup.groups_seen == 0
