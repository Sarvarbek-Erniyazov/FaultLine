"""Downloader behaviour against a fake record. No network access."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from faultline.data.common.manifest import (
    SourceManifest,
    hash_file,
    manifest_path,
    read_manifest,
    write_manifest,
)
from faultline.download.zenodo import (
    USER_AGENT,
    SourceSpec,
    download_source,
    download_url,
    expected_md5,
    load_sources_config,
    plan_download,
    published_files,
)
from faultline.paths import ProjectPaths

GOOD = b"good file contents\n"
BAD = b"bad file contents\n"


def fake_record(entries: dict[str, tuple[bytes, str]]) -> dict[str, Any]:
    """Build a record whose published checksums may or may not match the payload."""
    return {
        "doi": "10.5281/zenodo.999999",
        "files": [
            {
                "key": name,
                "size": len(payload),
                "checksum": f"md5:{digest}",
                "links": {"self": f"https://example.invalid/{name}"},
            }
            for name, (payload, digest) in entries.items()
        ],
    }


class FakeClient:
    """A ZenodoClient stand-in that serves bytes from a dictionary."""

    def __init__(self, record: dict[str, Any], payloads: dict[str, bytes]) -> None:
        self.record = record
        self.payloads = payloads
        self.fetched: list[int] = []
        self.downloaded: list[str] = []

    def fetch_record(self, record_id: int) -> dict[str, Any]:
        self.fetched.append(record_id)
        return self.record

    def download_file(self, url: str, destination: Path, expected_size: int | None = None) -> Path:
        name = url.rsplit("/", 1)[-1]
        self.downloaded.append(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.payloads[name])
        return destination


def spec(**overrides: Any) -> SourceSpec:
    payload: dict[str, Any] = {
        "provider": "Test Provider",
        "zenodo_record": 999999,
        "concept_doi": "10.5281/zenodo.111111",
        "license": "CC-BY-4.0",
        "attribution": "Test Provider, test data (CC BY 4.0)",
        "site": {"name": "Testfarm", "country": "UK", "n_turbines": 2},
        "tiers": {1: ["a.zip", "b.csv"], 2: ["big.zip"]},
    }
    payload.update(overrides)
    return SourceSpec.model_validate(payload)


def md5(payload: bytes) -> str:
    return hashlib.md5(payload).hexdigest()


def test_shipped_source_config_loads(repo_root: Path) -> None:
    config = load_sources_config(repo_root / "configs" / "data" / "sources_telemetry.yaml")
    assert set(config.sources) == {"kelmarsh", "penmanshiel", "hill_of_towie", "care"}
    # CARE is the share-alike source; the licence must survive into the config
    assert config.sources["care"].license == "CC-BY-SA-4.0"
    for source in config.sources.values():
        assert source.attribution
        assert source.files_for_tier(1)


def test_tiers_accumulate() -> None:
    source = spec()
    assert source.files_for_tier(1) == ["a.zip", "b.csv"]
    assert source.files_for_tier(2) == ["a.zip", "b.csv", "big.zip"]


def test_published_files_and_links() -> None:
    record = fake_record({"a.zip": (GOOD, md5(GOOD))})
    files = published_files(record)
    assert set(files) == {"a.zip"}
    assert expected_md5(files["a.zip"]) == md5(GOOD)
    assert download_url(files["a.zip"]).endswith("a.zip")


def test_expected_md5_ignores_other_algorithms() -> None:
    assert expected_md5({"checksum": "sha256:abc"}) is None


def test_download_url_without_links_raises() -> None:
    with pytest.raises(KeyError):
        download_url({"key": "a.zip", "links": {}})


def test_user_agent_identifies_the_project() -> None:
    assert USER_AGENT.startswith("FaultLine-downloader/")


def test_dry_run_downloads_nothing(tmp_paths: ProjectPaths) -> None:
    record = fake_record({"a.zip": (GOOD, md5(GOOD)), "b.csv": (GOOD, md5(GOOD))})
    client = FakeClient(record, {"a.zip": GOOD, "b.csv": GOOD})
    plan = download_source("test", spec(), 1, tmp_paths, client, load_defaults(), dry_run=True)
    assert client.downloaded == []
    assert plan.total_bytes == 2 * len(GOOD)
    assert plan.pending_bytes == plan.total_bytes
    assert not manifest_path(tmp_paths.manifests_dir, "test").exists()


def load_defaults():
    from faultline.download.zenodo import DownloadDefaults

    return DownloadDefaults()


def test_successful_download_writes_a_verified_manifest(tmp_paths: ProjectPaths) -> None:
    record = fake_record({"a.zip": (GOOD, md5(GOOD)), "b.csv": (BAD, md5(BAD))})
    client = FakeClient(record, {"a.zip": GOOD, "b.csv": BAD})

    download_source("test", spec(), 1, tmp_paths, client, load_defaults())

    manifest = read_manifest(manifest_path(tmp_paths.manifests_dir, "test"))
    assert manifest is not None
    assert manifest.all_verified
    assert manifest.license == "CC-BY-4.0"
    assert manifest.concept_doi == "10.5281/zenodo.111111"
    assert manifest.version_doi == "10.5281/zenodo.999999"
    assert {record.filename for record in manifest.files} == {"a.zip", "b.csv"}
    for entry in manifest.files:
        assert entry.relative_path.startswith("raw/telemetry/test/")
        assert entry.license == "CC-BY-4.0"


def test_checksum_mismatch_aborts_loudly(tmp_paths: ProjectPaths) -> None:
    # The record advertises the md5 of GOOD, but the server serves BAD.
    record = fake_record({"a.zip": (GOOD, md5(GOOD))})
    client = FakeClient(record, {"a.zip": BAD})
    single = spec(tiers={1: ["a.zip"]})

    with pytest.raises(ValueError, match="md5 mismatch"):
        download_source("test", single, 1, tmp_paths, client, load_defaults())


def test_a_file_missing_from_the_record_aborts_before_any_download(
    tmp_paths: ProjectPaths,
) -> None:
    # This is the check that catches a record being republished with different files.
    record = fake_record({"a.zip": (GOOD, md5(GOOD))})
    client = FakeClient(record, {"a.zip": GOOD})

    with pytest.raises(FileNotFoundError, match="does not publish"):
        download_source("test", spec(), 1, tmp_paths, client, load_defaults())
    assert client.downloaded == []


def test_verified_files_are_not_downloaded_again(tmp_paths: ProjectPaths) -> None:
    record = fake_record({"a.zip": (GOOD, md5(GOOD)), "b.csv": (GOOD, md5(GOOD))})
    client = FakeClient(record, {"a.zip": GOOD, "b.csv": GOOD})

    download_source("test", spec(), 1, tmp_paths, client, load_defaults())
    assert sorted(client.downloaded) == ["a.zip", "b.csv"]

    client.downloaded.clear()
    plan = download_source("test", spec(), 1, tmp_paths, client, load_defaults())
    assert client.downloaded == []
    assert plan.pending_bytes == 0


def test_plan_marks_unverified_files_as_pending(tmp_paths: ProjectPaths) -> None:
    record = fake_record({"a.zip": (GOOD, md5(GOOD))})
    target = tmp_paths.source_dir("raw", "telemetry", "test")
    (target / "a.zip").write_bytes(GOOD)
    plan = plan_download("test", spec(tiers={1: ["a.zip"]}), 1, record, target, None)
    assert plan.pending_bytes == len(GOOD)  # present on disk but not verified


def test_hash_file_streams(tmp_path: Path) -> None:
    path = tmp_path / "payload.bin"
    path.write_bytes(GOOD)
    assert hash_file(path, "md5") == md5(GOOD)


def test_manifest_round_trip(tmp_path: Path) -> None:
    manifest = SourceManifest(source="test", provider="p", license="CC-BY-4.0")
    path = write_manifest(tmp_path / "test.json", manifest)
    restored = read_manifest(path)
    assert restored is not None
    assert restored.source == "test"
    assert restored.files == []
    assert not restored.all_verified  # an empty manifest is not "all verified"


def test_read_missing_manifest_returns_none(tmp_path: Path) -> None:
    assert read_manifest(tmp_path / "absent.json") is None
