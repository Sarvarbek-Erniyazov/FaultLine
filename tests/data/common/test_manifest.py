"""Manifest storage: one file for a small source, shards for a source too big for one."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from faultline.data.common.manifest import (
    FileRecord,
    SourceManifest,
    load_manifest,
    manifest_path,
    manifest_shard_dir,
    read_manifest,
    write_manifest,
    write_manifest_sharded,
)


def _record(filename: str, template_era: str | None = None) -> FileRecord:
    return FileRecord(
        filename=filename,
        relative_path=f"raw/text/x/{filename}",
        size_bytes=10,
        sha256="deadbeef",
        url=f"https://example.invalid/{filename}",
        retrieved_at=datetime(2026, 9, 13, tzinfo=UTC),
        verified=True,
        template_era=template_era,
    )


def test_a_source_with_no_manifest_at_all_loads_as_none(tmp_path: Path) -> None:
    assert load_manifest(tmp_path, "nonexistent") is None


def test_load_manifest_reads_an_unsharded_source_unchanged(tmp_path: Path) -> None:
    manifest = SourceManifest(source="x", provider="p", license="public-domain")
    manifest.upsert(_record("a.txt"))
    manifest.upsert(_record("b.txt"))
    write_manifest(manifest_path(tmp_path, "x"), manifest)

    reloaded = load_manifest(tmp_path, "x")

    assert reloaded is not None
    assert [record.filename for record in reloaded.files] == ["a.txt", "b.txt"]
    # nothing sharded: no shard directory was ever created
    assert not manifest_shard_dir(tmp_path, "x").exists()


def test_sharded_write_then_load_round_trips_every_record(tmp_path: Path) -> None:
    manifest = SourceManifest(source="events", provider="NRC", license="public-domain")
    manifest.upsert(_record("20180703en_en1.txt", template_era="midera"))
    manifest.upsert(_record("20180704en_en2.txt", template_era="midera"))
    manifest.upsert(_record("20240101en_en3.txt", template_era="modern"))

    write_manifest_sharded(
        tmp_path, "events", manifest, shard_key_of=lambda record: record.filename[:4]
    )
    reloaded = load_manifest(tmp_path, "events")

    assert reloaded is not None
    assert reloaded.source == "events"
    assert reloaded.provider == "NRC"
    assert {record.filename for record in reloaded.files} == {
        "20180703en_en1.txt",
        "20180704en_en2.txt",
        "20240101en_en3.txt",
    }
    by_filename = reloaded.by_filename()
    assert by_filename["20180703en_en1.txt"].template_era == "midera"
    assert by_filename["20240101en_en3.txt"].template_era == "modern"


def test_sharded_write_splits_one_file_per_shard_key(tmp_path: Path) -> None:
    manifest = SourceManifest(source="events", provider="NRC", license="public-domain")
    manifest.upsert(_record("2018_a.txt"))
    manifest.upsert(_record("2018_b.txt"))
    manifest.upsert(_record("2024_a.txt"))

    write_manifest_sharded(tmp_path, "events", manifest, shard_key_of=lambda r: r.filename[:4])

    shard_dir = manifest_shard_dir(tmp_path, "events")
    assert sorted(p.name for p in shard_dir.glob("*.jsonl")) == ["2018.jsonl", "2024.jsonl"]
    # one JSON object per line, no pretty-printing: two records made exactly two
    # lines, and each parses as its own object
    lines_2018 = (shard_dir / "2018.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines_2018) == 2
    assert all(json.loads(line)["filename"].startswith("2018_") for line in lines_2018)


def test_sharded_header_file_carries_the_manifests_own_fields_with_files_empty(
    tmp_path: Path,
) -> None:
    manifest = SourceManifest(source="events", provider="NRC", license="public-domain")
    manifest.upsert(_record("2018_a.txt"))

    write_manifest_sharded(tmp_path, "events", manifest, shard_key_of=lambda r: r.filename[:4])

    header = read_manifest(manifest_path(tmp_path, "events"))
    assert header is not None
    assert header.provider == "NRC"
    assert header.files == []


def test_rewriting_sharded_manifest_deletes_a_shard_whose_key_disappeared(
    tmp_path: Path,
) -> None:
    manifest = SourceManifest(source="events", provider="NRC", license="public-domain")
    manifest.upsert(_record("2018_a.txt"))
    write_manifest_sharded(tmp_path, "events", manifest, shard_key_of=lambda r: r.filename[:4])
    assert (manifest_shard_dir(tmp_path, "events") / "2018.jsonl").is_file()

    # the 2018 record is gone from the manifest passed in on a later write
    manifest.files = []
    manifest.upsert(_record("2024_a.txt"))
    write_manifest_sharded(tmp_path, "events", manifest, shard_key_of=lambda r: r.filename[:4])

    shard_dir = manifest_shard_dir(tmp_path, "events")
    assert sorted(p.name for p in shard_dir.glob("*.jsonl")) == ["2024.jsonl"]


def test_a_sharded_manifest_round_trips_optional_fields(tmp_path: Path) -> None:
    manifest = SourceManifest(source="events", provider="NRC", license="public-domain")
    manifest.upsert(_record("2018_a.txt", template_era=None))

    write_manifest_sharded(tmp_path, "events", manifest, shard_key_of=lambda r: r.filename[:4])
    reloaded = load_manifest(tmp_path, "events")

    assert reloaded is not None
    assert reloaded.files[0].template_era is None
