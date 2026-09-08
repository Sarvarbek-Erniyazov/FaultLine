"""Exact deduplication, ported from notebook cells 27-28."""

from __future__ import annotations

import pytest

from faultline.data.text.dedup import (
    DedupConfig,
    ExactDeduplicator,
    document_hash,
    normalize_for_hash,
)


def test_hash_normalisation_is_case_and_whitespace_insensitive() -> None:
    assert normalize_for_hash("  Hello  ") == "hello"
    assert document_hash("Hello") == document_hash("  hello  ")
    assert document_hash("Hello") != document_hash("Hello!")


def test_hash_is_sha256_hex() -> None:
    digest = document_hash("anything")
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


def test_normalisation_switches() -> None:
    config = DedupConfig(lowercase=False, strip=False)
    assert document_hash("Hello", config) != document_hash("hello", config)
    assert document_hash(" a ", config) != document_hash("a", config)


def test_exact_deduplicator() -> None:
    deduper = ExactDeduplicator()
    assert deduper.accept("first") is True
    assert deduper.accept("second") is True
    assert deduper.accept("FIRST") is False
    assert deduper.accept("  first  ") is False
    assert deduper.duplicates == 2
    assert len(deduper) == 2


def test_unimplemented_strategy_is_rejected_loudly() -> None:
    # Silently doing nothing when asked for minhash would be the dangerous outcome.
    with pytest.raises(NotImplementedError, match="m2"):
        ExactDeduplicator(DedupConfig(strategy="minhash"))
