"""Checksum-verified staging of Zenodo records.

The downloader is deliberately paranoid, because a silently changed corpus is the
kind of error that survives all the way into a results table:

* record ids are pinned to a version, and every configured file name must exist in
  that record or the run aborts before a byte is fetched;
* every file is verified against the MD5 published in the record metadata;
* a verified file is never re-downloaded, and a partial file is resumed with an
  HTTP Range request rather than restarted;
* what was fetched, when, from where and under which licence is written to a
  tracked manifest under ``data/cards/manifests/``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from pydantic import Field
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

from faultline import __version__
from faultline.config import StrictModel, load_config
from faultline.data.common.manifest import (
    FileRecord,
    SourceManifest,
    hash_file,
    manifest_path,
    read_manifest,
    write_manifest,
)
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths

logger = get_logger(__name__)

#: Identifies this project to the Zenodo API. The header name is the sole permitted
#: use of that word in the repository; see ADR-0002.
USER_AGENT = (
    f"FaultLine-downloader/{__version__} (+https://github.com/Sarvarbek-Erniyazov/FaultLine)"
)

CHUNK_SIZE = 1 << 20


class SiteSpec(StrictModel):
    """Descriptive metadata about the site behind a source.

    Attributes:
        name: Human-readable site name.
        country: Country code or name.
        oem: Turbine manufacturer and model.
        n_turbines: Number of turbines in the record.
        rated_kw: Rated power per turbine in kW, 0 when not published.
        period: Coverage period as published.
        note: Free-text caveat from the provider.
    """

    name: str
    country: str | None = None
    oem: str | None = None
    n_turbines: int | None = None
    rated_kw: int | None = None
    period: str | None = None
    note: str | None = None


class SourceSpec(StrictModel):
    """One configured data source.

    Attributes:
        provider: Publishing organisation.
        zenodo_record: Version-pinned record id.
        concept_doi: DOI resolving to the latest version.
        license: SPDX-style licence identifier.
        attribution: Attribution string required by the licence.
        cite: Optional accompanying publication.
        site: Site metadata.
        timezone: Timezone of the timestamps, or a TODO when unconfirmed.
        intended_use: Role this source plays in the study design.
        tiers: File names grouped by download tier.
    """

    provider: str
    zenodo_record: int
    concept_doi: str | None = None
    license: str
    attribution: str
    cite: str | None = None
    site: SiteSpec
    timezone: str | None = None
    intended_use: str | None = None
    tiers: dict[int, list[str]] = Field(default_factory=dict)

    def files_for_tier(self, tier: int) -> list[str]:
        """Return the file names in tiers up to and including ``tier``.

        Args:
            tier: Highest tier to include.

        Returns:
            File names, in configuration order, without duplicates.
        """
        names: list[str] = []
        for level in sorted(self.tiers):
            if level <= tier:
                names.extend(name for name in self.tiers[level] if name not in names)
        return names


class DownloadDefaults(StrictModel):
    """Transport-level settings shared by every source.

    Attributes:
        api_base: Base URL of the Zenodo records API.
        verify_checksums: Verify the local digest against the published one.
        resume: Resume partial files with a Range request.
    """

    api_base: str = "https://zenodo.org/api/records"
    verify_checksums: bool = True
    resume: bool = True


class SourcesConfig(StrictModel):
    """Top level of ``configs/data/sources_telemetry.yaml``.

    Attributes:
        version: Version of this specification.
        defaults: Transport-level settings.
        sources: Source specifications keyed by source id.
    """

    version: int = 0
    defaults: DownloadDefaults = Field(default_factory=DownloadDefaults)
    sources: dict[str, SourceSpec]


def load_sources_config(path: Path) -> SourcesConfig:
    """Load and validate the telemetry source specification.

    Args:
        path: Path to the YAML file.

    Returns:
        The validated configuration.
    """
    return load_config(path, SourcesConfig)


class ZenodoClient:
    """Thin HTTP client for the Zenodo records API.

    Attributes:
        api_base: Base URL of the records API.
        session: Underlying requests session carrying the project identification.
    """

    def __init__(
        self,
        api_base: str = "https://zenodo.org/api/records",
        timeout: int = 60,
        retries: int = 8,
    ) -> None:
        """Create a client with a persistent, retrying session.

        Zenodo returns 502/503/504 under load often enough that a multi-hour,
        multi-gigabyte staging run will meet one. Transient statuses are retried
        with exponential backoff rather than failing the run.

        Args:
            api_base: Base URL of the records API.
            timeout: Per-request timeout in seconds.
            retries: Number of retries for transient failures.
        """
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        policy = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=3.0,
            backoff_max=300.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=policy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def fetch_record(self, record_id: int) -> dict[str, Any]:
        """Fetch record metadata.

        Args:
            record_id: Version-pinned record id.

        Returns:
            The parsed record JSON.

        Raises:
            requests.HTTPError: If the record cannot be fetched.
        """
        url = f"{self.api_base}/{record_id}"
        logger.info("fetching record metadata %s", url)
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload

    def download_file(self, url: str, destination: Path, expected_size: int | None = None) -> Path:
        """Download one file, resuming a partial local copy when possible.

        Args:
            url: Download URL from the record metadata.
            destination: Local file path.
            expected_size: Published size in bytes, used for the progress bar.

        Returns:
            The path written.

        Raises:
            requests.HTTPError: If the server rejects the request.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        existing = destination.stat().st_size if destination.exists() else 0
        headers: dict[str, str] = {}
        mode = "wb"
        if existing and expected_size and existing < expected_size:
            headers["Range"] = f"bytes={existing}-"
            mode = "ab"
            logger.info("resuming %s at %d bytes", destination.name, existing)
        elif existing:
            existing = 0

        with self.session.get(url, stream=True, timeout=self.timeout, headers=headers) as response:
            response.raise_for_status()
            if mode == "ab" and response.status_code != 206:
                logger.warning("server ignored the range request; restarting %s", destination.name)
                mode, existing = "wb", 0
            total = expected_size or int(response.headers.get("Content-Length", 0)) or None
            with (
                destination.open(mode) as handle,
                tqdm(
                    total=total,
                    initial=existing,
                    unit="B",
                    unit_scale=True,
                    desc=destination.name[:40],
                    leave=False,
                ) as progress,
            ):
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        handle.write(chunk)
                        progress.update(len(chunk))
        return destination


def published_files(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index a record's published files by file name.

    Args:
        record: Record JSON from the Zenodo API.

    Returns:
        A mapping from file name to its metadata entry.
    """
    files: dict[str, dict[str, Any]] = {}
    for entry in record.get("files", []):
        key = entry.get("key") or entry.get("filename")
        if key:
            files[str(key)] = entry
    return files


def expected_md5(entry: dict[str, Any]) -> str | None:
    """Extract the published MD5 digest of a file entry.

    Args:
        entry: One element of the record's ``files`` list.

    Returns:
        The hex digest, or ``None`` when the record publishes another algorithm.
    """
    checksum = str(entry.get("checksum", ""))
    if checksum.startswith("md5:"):
        return checksum.split(":", 1)[1]
    return None


def download_url(entry: dict[str, Any]) -> str:
    """Extract the download URL of a file entry.

    Args:
        entry: One element of the record's ``files`` list.

    Returns:
        The URL to fetch.

    Raises:
        KeyError: If the entry carries no usable link.
    """
    links = entry.get("links", {})
    for key in ("self", "download", "content"):
        if key in links:
            return str(links[key])
    raise KeyError(f"file entry has no download link: {entry.get('key')}")


class DownloadPlan(StrictModel):
    """What a download would fetch, before anything is fetched.

    Attributes:
        source: Source id.
        record_id: Version-pinned record id.
        tier: Requested tier.
        files: Planned files as ``(name, size_bytes, already_verified)``.
        missing: Configured names absent from the published record.
    """

    source: str
    record_id: int
    tier: int
    files: list[tuple[str, int, bool]]
    missing: list[str]

    @property
    def total_bytes(self) -> int:
        """Total size of every planned file."""
        return sum(size for _, size, _ in self.files)

    @property
    def pending_bytes(self) -> int:
        """Total size of the files not already verified locally."""
        return sum(size for _, size, verified in self.files if not verified)


def plan_download(
    source: str,
    spec: SourceSpec,
    tier: int,
    record: dict[str, Any],
    target_dir: Path,
    manifest: SourceManifest | None,
) -> DownloadPlan:
    """Resolve a configured tier against a published record.

    Args:
        source: Source id.
        spec: Source specification.
        tier: Highest tier to include.
        record: Record JSON from the Zenodo API.
        target_dir: Directory the files will land in.
        manifest: Existing manifest, used to skip verified files.

    Returns:
        The plan, including any configured names missing from the record.
    """
    published = published_files(record)
    known = manifest.by_filename() if manifest else {}
    files: list[tuple[str, int, bool]] = []
    missing: list[str] = []
    for name in spec.files_for_tier(tier):
        entry = published.get(name)
        if entry is None:
            missing.append(name)
            continue
        size = int(entry.get("size", 0))
        record_entry = known.get(name)
        local = target_dir / name
        verified = bool(
            record_entry
            and record_entry.verified
            and local.is_file()
            and local.stat().st_size == size
        )
        files.append((name, size, verified))
    return DownloadPlan(
        source=source, record_id=spec.zenodo_record, tier=tier, files=files, missing=missing
    )


def download_source(
    source: str,
    spec: SourceSpec,
    tier: int,
    paths: ProjectPaths,
    client: ZenodoClient,
    defaults: DownloadDefaults,
    dry_run: bool = False,
) -> DownloadPlan:
    """Stage one source and update its manifest.

    Args:
        source: Source id.
        spec: Source specification.
        tier: Highest tier to include.
        paths: Resolved project paths.
        client: Zenodo client.
        defaults: Transport settings.
        dry_run: Resolve and report the plan without downloading.

    Returns:
        The resolved plan.

    Raises:
        FileNotFoundError: If a configured file is absent from the pinned record.
        ValueError: If a downloaded file fails checksum verification.
    """
    record = client.fetch_record(spec.zenodo_record)
    target_dir = paths.source_dir("raw", "telemetry", source)
    path = manifest_path(paths.manifests_dir, source)
    manifest = read_manifest(path) or SourceManifest(
        source=source,
        provider=spec.provider,
        license=spec.license,
        record_id=spec.zenodo_record,
        concept_doi=spec.concept_doi,
        version_doi=str(record.get("doi") or "") or None,
    )
    plan = plan_download(source, spec, tier, record, target_dir, manifest)

    if plan.missing:
        raise FileNotFoundError(
            f"{source}: record {spec.zenodo_record} does not publish {plan.missing}; "
            "the record changed or the configuration is wrong - do not proceed"
        )
    if dry_run:
        return plan

    published = published_files(record)
    for name, size, verified in plan.files:
        destination = target_dir / name
        if verified:
            logger.info("%s: %s already verified, skipping", source, name)
            continue
        entry = published[name]
        client.download_file(download_url(entry), destination, expected_size=size or None)

        digest = expected_md5(entry)
        ok = True
        local_md5 = None
        if defaults.verify_checksums and digest:
            local_md5 = hash_file(destination, "md5")
            ok = local_md5 == digest
            if not ok:
                raise ValueError(
                    f"{source}/{name}: md5 mismatch, expected {digest}, got {local_md5}"
                )
        manifest.upsert(
            FileRecord(
                filename=name,
                relative_path=f"raw/telemetry/{source}/{name}",
                size_bytes=destination.stat().st_size,
                md5=local_md5 or digest,
                url=download_url(entry),
                license=spec.license,
                retrieved_at=datetime.now(tz=UTC),
                verified=ok and bool(digest),
            )
        )
        manifest.generated_at = datetime.now(tz=UTC)
        write_manifest(path, manifest)
        logger.info("%s: staged %s (%.1f MB)", source, name, destination.stat().st_size / 1e6)

    manifest.generated_at = datetime.now(tz=UTC)
    write_manifest(path, manifest)
    return plan
