"""Download manifests: the tracked, checksummed record of what was staged.

Raw archives never enter git. The manifest is what does: for every file it records
size, checksum, source URL, licence and the moment it was retrieved, so a third
party can reconstruct the exact corpus from the repository plus the public record.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ConfigDict, Field

from faultline.config import StrictModel


def hash_file(path: Path, algorithm: str = "md5", chunk_size: int = 1 << 20) -> str:
    """Stream a file through a hash function.

    Args:
        path: File to read.
        algorithm: Any algorithm name accepted by :mod:`hashlib`.
        chunk_size: Read size in bytes; the file is never loaded whole.

    Returns:
        The hex digest.
    """
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


class FileRecord(StrictModel):
    """One retrieved file.

    Attributes:
        filename: File name as published by the provider.
        relative_path: Location under the data root, POSIX-style.
        size_bytes: Size on disk.
        md5: MD5 digest as published by the provider and recomputed locally.
        sha256: Optional SHA-256 digest computed locally.
        url: Download URL used.
        license: SPDX-style licence identifier for this file, when it can differ
            from the source's own (a Zenodo record can mix licences across files).
            ``None`` means "the same as the manifest's own `license`" -- every file
            of a single-licence source (an NRC text collection, one licence for
            every document) should leave this unset rather than repeat an identical
            string thousands of times; a manifest with many small files is exactly
            where that repetition first became large enough to matter
            (`nrc_event_notifications.json`, ADR-0016).
        retrieved_at: UTC timestamp of a successful download.
        verified: Whether the local digest matched the published one.
        retrieval_method: How the file reached this repository -- ``None`` (the
            default) for this project's own automated, robots.txt-gated downloader;
            an explicit string such as ``"manual, author, browser"`` when a human
            fetched it directly (PHMSA's flagged-incident file, ADR-0016), so the
            manifest states the provenance rather than leaving it implied by every
            other record's silence.
        template_era: Which HTML template this document was extracted from, for a
            source whose markup changed shape over the years it spans (NRC Event
            Notification Reports, ADR-0016) -- ``None`` for every other source, which
            only ever has one template. Not recoverable after the fact from anything
            else on the record: `doc_id` and `url` are the same shape regardless of
            which template produced them, so this is measured once, at extraction
            time, or not at all.
    """

    filename: str
    relative_path: str
    size_bytes: int
    md5: str | None = None
    sha256: str | None = None
    url: str
    license: str | None = None
    retrieved_at: datetime
    verified: bool = False
    retrieval_method: str | None = None
    template_era: str | None = None


class SourceManifest(StrictModel):
    """Every file retrieved for one data source.

    Unlike a configuration, a manifest is accumulated as files land, so this model is
    mutable while still rejecting unknown keys.

    Attributes:
        source: Source identifier, for example ``kelmarsh``.
        provider: Organisation publishing the data.
        license: Licence covering the source as a whole.
        record_id: Version-pinned Zenodo record identifier.
        concept_doi: DOI resolving to the latest version of the record.
        version_doi: DOI of the exact version retrieved.
        generated_at: When this manifest was last written.
        files: One record per retrieved file.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    source: str
    provider: str
    license: str
    record_id: int | None = None
    concept_doi: str | None = None
    version_doi: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    files: list[FileRecord] = Field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        """Total size of every file listed."""
        return sum(record.size_bytes for record in self.files)

    @property
    def all_verified(self) -> bool:
        """Whether every listed file matched its published checksum."""
        return bool(self.files) and all(record.verified for record in self.files)

    def by_filename(self) -> dict[str, FileRecord]:
        """Index the file records by published file name.

        Returns:
            A mapping from file name to record.
        """
        return {record.filename: record for record in self.files}

    def upsert(self, record: FileRecord) -> None:
        """Insert a file record, replacing any existing entry with the same name.

        Args:
            record: The record to store.
        """
        self.files = [existing for existing in self.files if existing.filename != record.filename]
        self.files.append(record)
        self.files.sort(key=lambda item: item.filename)


def manifest_path(manifests_dir: Path, source: str) -> Path:
    """Return the tracked manifest location for a source.

    Args:
        manifests_dir: ``data/cards/manifests`` directory.
        source: Source identifier.

    Returns:
        Path of the source's JSON manifest.
    """
    return manifests_dir / f"{source}.json"


def read_manifest(path: Path) -> SourceManifest | None:
    """Load a manifest if it exists.

    Args:
        path: Manifest location.

    Returns:
        The parsed manifest, or ``None`` when the file is absent.
    """
    if not path.is_file():
        return None
    return SourceManifest.model_validate_json(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, manifest: SourceManifest) -> Path:
    """Write a manifest as indented JSON.

    An unset optional field (``md5``, per-file ``license``, ``retrieval_method``) is
    omitted rather than written as ``null``: harmless for the handful of files a
    telemetry source manifest carries, and the difference between a manifest that
    fits comfortably under the large-file hook's limit and one that does not once a
    source carries thousands of small files (``nrc_event_notifications.json``, over
    ten thousand records). :func:`read_manifest` restores the same default either
    way, since Pydantic fills in an omitted optional field exactly as it would a
    ``null`` one.

    Args:
        path: Destination file.
        manifest: Manifest to serialize.

    Returns:
        The path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest.model_dump(mode="json", exclude_none=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def manifest_shard_dir(manifests_dir: Path, source: str) -> Path:
    """Return the shard directory a source's manifest keeps its file records under.

    Args:
        manifests_dir: ``data/cards/manifests`` directory.
        source: Source identifier.

    Returns:
        Directory holding one compact JSONL file per shard, when the source's
        manifest is sharded at all (:func:`load_manifest` treats a directory that
        does not exist as "not sharded", not as an error).
    """
    return manifests_dir / source


def write_manifest_sharded(
    manifests_dir: Path,
    source: str,
    manifest: SourceManifest,
    shard_key_of: Callable[[FileRecord], str],
) -> Path:
    """Write a manifest whose file records are too many for one indented JSON file.

    A single ``<source>.json``, indented for human review, is the right shape for a
    source with a handful of files. It stops being the right shape once a source
    carries tens of thousands of them (``nrc_event_notifications``, ADR-0016): the
    file crossed the repository's large-file limit twice as this source grew, which
    is the file's own shape being wrong, not the limit. This instead keeps the
    manifest's own top-level fields (provider, licence, ...) in that same
    ``<source>.json`` with ``files`` left empty, a header, and splits the file
    records themselves across compact, unindented JSONL shards --
    ``<manifests_dir>/<source>/<shard_key>.jsonl``, one record per line -- grouped
    by ``shard_key_of`` (a report year, for event notifications). Every shard is
    rewritten from ``manifest.files`` in full each call, including deleting any
    shard whose key is no longer present, so a shard directory always matches the
    manifest passed in; nothing here appends only. :func:`load_manifest` reads this
    layout back as one ordinary :class:`SourceManifest`.

    Args:
        manifests_dir: ``data/cards/manifests`` directory.
        source: Source identifier.
        manifest: The manifest to write; its ``files`` are what gets sharded.
        shard_key_of: Assigns one file record to its shard.

    Returns:
        The shard directory written.
    """
    shard_dir = manifest_shard_dir(manifests_dir, source)
    shard_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[FileRecord]] = {}
    for record in manifest.files:
        grouped.setdefault(shard_key_of(record), []).append(record)
    for shard_key, records in grouped.items():
        records.sort(key=lambda item: item.filename)
        lines = [
            json.dumps(record.model_dump(mode="json", exclude_none=True), separators=(",", ":"))
            for record in records
        ]
        (shard_dir / f"{shard_key}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for stray in shard_dir.glob("*.jsonl"):
        if stray.stem not in grouped:
            stray.unlink()
    write_manifest(manifest_path(manifests_dir, source), manifest.model_copy(update={"files": []}))
    return shard_dir


def load_manifest(manifests_dir: Path, source: str) -> SourceManifest | None:
    """Load a source's manifest, whether it is one file or sharded.

    A caller that only wants "every file record this source has" should not need to
    know which layout backs it. This reads the ``<source>.json`` header for the
    manifest's own fields, then -- only if ``<manifests_dir>/<source>/`` exists --
    replaces its (empty) ``files`` with every record from every ``*.jsonl`` shard
    there, sorted for a stable read.

    Args:
        manifests_dir: ``data/cards/manifests`` directory.
        source: Source identifier.

    Returns:
        The manifest with every file record present, or ``None`` if the source has
        no manifest at all yet.
    """
    header = read_manifest(manifest_path(manifests_dir, source))
    if header is None:
        return None
    shard_dir = manifest_shard_dir(manifests_dir, source)
    if not shard_dir.is_dir():
        return header
    records: list[FileRecord] = []
    for shard_file in sorted(shard_dir.glob("*.jsonl")):
        for line in shard_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(FileRecord.model_validate_json(line))
    records.sort(key=lambda item: item.filename)
    return header.model_copy(update={"files": records})
