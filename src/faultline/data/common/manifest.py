"""Download manifests: the tracked, checksummed record of what was staged.

Raw archives never enter git. The manifest is what does: for every file it records
size, checksum, source URL, licence and the moment it was retrieved, so a third
party can reconstruct the exact corpus from the repository plus the public record.
"""

from __future__ import annotations

import hashlib
import json
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
        license: SPDX-style licence identifier for this file.
        retrieved_at: UTC timestamp of a successful download.
        verified: Whether the local digest matched the published one.
    """

    filename: str
    relative_path: str
    size_bytes: int
    md5: str | None = None
    sha256: str | None = None
    url: str
    license: str
    retrieved_at: datetime
    verified: bool = False


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

    Args:
        path: Destination file.
        manifest: Manifest to serialize.

    Returns:
        The path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
