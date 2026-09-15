"""PHMSA incident narratives: one document per report, from a verified, recorded archive."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import requests

from faultline.data.common.manifest import FileRecord, manifest_path, read_manifest
from faultline.data.text.phmsa_manual import (
    ArchiveParseError,
    fetch_incident_narratives,
    unquote_field,
)
from faultline.download.nrc_text import (
    NrcTextClient,
    SocrataAttachment,
    SocrataAttachmentsSpec,
    pipeline_type_shard_key,
    shard_key_for,
)
from faultline.paths import ProjectPaths

ATTACHMENT_URL = (
    "https://data.transportation.gov/api/views/27nc-rsge/files/abc"
    "?download=true&filename=Hazardous%20Liquid%20x.zip"
)


def _zip_bytes(tmp_path: Path, member: str, table: str) -> bytes:
    path = tmp_path / "built.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, table.encode("cp1252"))
        archive.writestr("Data fields.pdf", b"%PDF-1.4")
    return path.read_bytes()


class _Session(requests.Session):
    def __init__(self, responses: dict[str, tuple[int, bytes]]) -> None:
        super().__init__()
        self.responses = responses
        self.requested: list[str] = []

    def get(self, url: str, *args: object, **kwargs: object) -> requests.Response:
        self.requested.append(url)
        status, body = self.responses[url]
        response = requests.Response()
        response.status_code = status
        response._content = body
        response.url = url
        return response


def _spec() -> SocrataAttachmentsSpec:
    return SocrataAttachmentsSpec(
        provider="PHMSA",
        license="public domain",
        attribution="PHMSA",
        view="27nc-rsge",
        archive_source="phmsa",
        narrative_column="NARRATIVE",
        id_column="REPORT_NUMBER",
        robots_basis="r",
        attachments=[
            SocrataAttachment(
                asset_id="abc", filename="Hazardous Liquid x.zip", pipeline_type="hazardous-liquid"
            )
        ],
    )


def _client(fixtures_dir: Path, body: bytes) -> tuple[NrcTextClient, _Session]:
    robots = (fixtures_dir / "robots" / "data_transportation_gov.txt").read_bytes()
    session = _Session(
        {
            "https://data.transportation.gov/robots.txt": (200, robots),
            ATTACHMENT_URL: (200, body),
        }
    )
    client = NrcTextClient(min_interval=0, session=session)
    client._pace = lambda interval: None  # type: ignore[method-assign]
    return client, session


TABLE = (
    "REPORT_NUMBER\tCAUSE_DETAILS\tNARRATIVE\r\n"
    '20100001\tCORROSION\t"A 2"" NIPPLE FAILED, RELEASING 3 BBLS OF CRUDE OIL."\r\n'
    "20100002\tOTHER\t\r\n"
    "20100003\tEXCAVATION\tTHIRD PARTY STRUCK THE LINE WHILE GRADING.\r\n"
)


def test_unquote_field_removes_one_enclosing_pair_and_restores_inner_quotes() -> None:
    assert unquote_field('"A 2"" NIPPLE"') == 'A 2" NIPPLE'
    assert unquote_field("NO QUOTES HERE") == "NO QUOTES HERE"
    assert unquote_field('"') == '"'


def test_one_document_per_non_empty_narrative(
    tmp_paths: ProjectPaths, tmp_path: Path, fixtures_dir: Path
) -> None:
    client, _ = _client(fixtures_dir, _zip_bytes(tmp_path, "accident.txt", TABLE))

    documents = list(fetch_incident_narratives(client, _spec(), tmp_paths))

    assert [d.doc_id for d in documents] == [
        "hazardous-liquid_20100001",
        "hazardous-liquid_20100003",
    ]
    assert documents[0].text == 'A 2" NIPPLE FAILED, RELEASING 3 BBLS OF CRUDE OIL.'
    assert documents[0].url == ATTACHMENT_URL + "#REPORT_NUMBER=20100001"


def test_the_archive_is_recorded_as_automated_and_reused_once_recorded(
    tmp_paths: ProjectPaths, tmp_path: Path, fixtures_dir: Path
) -> None:
    body = _zip_bytes(tmp_path, "accident.txt", TABLE)
    client, session = _client(fixtures_dir, body)
    list(fetch_incident_narratives(client, _spec(), tmp_paths))

    manifest = read_manifest(manifest_path(tmp_paths.manifests_dir, "phmsa"))
    assert manifest is not None
    record = manifest.by_filename()["Hazardous Liquid x.zip"]
    assert record.retrieval_method is None and record.verified is True

    list(fetch_incident_narratives(client, _spec(), tmp_paths))
    assert session.requested.count(ATTACHMENT_URL) == 1


def test_an_archive_missing_the_narrative_column_raises_and_is_not_recorded(
    tmp_paths: ProjectPaths, tmp_path: Path, fixtures_dir: Path
) -> None:
    body = _zip_bytes(tmp_path, "accident.txt", "REPORT_NUMBER\tCAUSE\r\n1\tX\r\n")
    client, _ = _client(fixtures_dir, body)
    with pytest.raises(ArchiveParseError, match="NARRATIVE"):
        list(fetch_incident_narratives(client, _spec(), tmp_paths))
    assert not manifest_path(tmp_paths.manifests_dir, "phmsa").exists()


def test_incident_manifests_shard_by_pipeline_type() -> None:
    record = FileRecord(
        filename="gas-distribution_20260008.txt",
        relative_path="raw/text/phmsa_incident_narratives/gas-distribution_20260008.txt",
        size_bytes=1,
        url="u",
        retrieved_at="2026-09-16T00:00:00Z",  # type: ignore[arg-type]
    )
    assert pipeline_type_shard_key(record) == "gas-distribution"
    assert shard_key_for("phmsa_incident_narratives", _spec()) is pipeline_type_shard_key
