"""Read-only inspection of a manually retrieved PHMSA archive, against a synthetic zip."""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests
from typer.testing import CliRunner

from faultline import cli
from faultline.data.common.manifest import manifest_path
from faultline.data.text.phmsa_manual import (
    RETRIEVAL_METHOD,
    ArchiveParseError,
    classify_member,
    fetch_socrata_attachment,
    inspect_archive,
    profile_member,
    record_manual_retrieval,
    render_report,
)
from faultline.download.nrc_text import NrcTextClient
from faultline.paths import ProjectPaths


def _csv_bytes(header: str, rows: list[str]) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


@pytest.fixture
def synthetic_zip(tmp_path: Path) -> Path:
    """A small zip mimicking PHMSA's flagged-incident-file structure.

    Several member files, one with a genuine narrative column, one purely
    categorical.
    """
    zip_path = tmp_path / "PHMSA_Pipeline_Safety_Flagged_Incidents.zip"
    distribution_2010 = _csv_bytes(
        "REPORT_NUMBER,CAUSE,NARRATIVE",
        [
            '1001,EQUIPMENT FAILURE,"The valve failed during routine operation and released gas '
            'into the surrounding area before crews could isolate the segment."',
            '1002,CORROSION,"External corrosion was found on the pipe wall during a scheduled '
            'inspection, leading to a small leak that was repaired the same day."',
            '1003,EXCAVATION DAMAGE,"A third-party contractor struck the line during unrelated '
            'excavation work, causing a rupture that was reported within the hour."',
        ],
    )
    hazardous_liquid_pre2010 = _csv_bytes(
        "REPORT_NUMBER,CAUSE_CODE,COMMODITY",
        ["2001,04,CRUDE OIL", "2002,07,REFINED PRODUCT"],
    )
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("gas_distribution_2010_present.csv", distribution_2010)
        archive.writestr("hazardous_liquid_1986_2009.csv", hazardous_liquid_pre2010)
        archive.writestr("readme.pdf", b"%PDF-1.4 not a table")
    return zip_path


def test_classify_member_reads_pipeline_type_and_generation() -> None:
    assert (
        classify_member("gas_distribution_2010_present.csv")
        == "gas distribution / 2010-present form"
    )
    assert classify_member("hazardous_liquid_1986_2009.csv") == "hazardous liquid / pre-2010 form"
    assert classify_member("mystery_file.csv") == "unknown / unknown"


def test_profile_member_finds_the_narrative_column_by_name() -> None:
    raw = _csv_bytes(
        "ID,NARRATIVE",
        ['1,"A short narrative sentence describing what happened during the event."'],
    )
    profile = profile_member("x.csv", raw)
    assert profile is not None
    assert profile.narrative_columns == ["NARRATIVE"]
    assert profile.narrative_tokens > 0
    assert profile.samples


def test_profile_member_finds_a_long_column_even_without_a_narrative_name() -> None:
    long_text = "word " * 30
    raw = _csv_bytes("ID,FREEFORM_FIELD", [f'1,"{long_text.strip()}"'])
    profile = profile_member("x.csv", raw)
    assert profile is not None
    assert "FREEFORM_FIELD" in profile.narrative_columns


def test_a_long_but_repeated_coded_column_is_not_narrative() -> None:
    # the OE-417 shape: a few long category sentences repeated across many rows
    categories = [
        "Loss of electric service to more than 50,000 customers for one hour or more",
        "Complete loss of electric power to the transmission system for one hour or more",
    ]
    rows = [f'{i},"{categories[i % 2]}"' for i in range(20)]
    profile = profile_member("x.csv", _csv_bytes("ID,ALERT_CRITERIA", rows))
    assert profile is not None
    assert profile.narrative_columns == []


def test_a_narrative_named_closed_code_set_is_not_narrative() -> None:
    # the CAUSE_DETAILS shape: a name the hints match, holding a few repeated codes
    codes = ["PIPE BODY", "WELD", "VALVE"]
    rows = [f"{i},{codes[i % 3]}" for i in range(30)]
    profile = profile_member("x.csv", _csv_bytes("ID,CAUSE_DETAILS", rows))
    assert profile is not None
    assert profile.narrative_columns == []
    assert profile.narrative_tokens == 0


def test_profile_member_finds_no_narrative_column_in_purely_categorical_data() -> None:
    raw = _csv_bytes("ID,CODE,COMMODITY", ["1,04,CRUDE OIL", "2,07,REFINED PRODUCT"])
    profile = profile_member("x.csv", raw)
    assert profile is not None
    assert profile.narrative_columns == []
    assert profile.narrative_tokens == 0


def test_profile_member_returns_none_for_a_non_tabular_member() -> None:
    assert profile_member("readme.pdf", b"%PDF-1.4 not a table") is None


def test_inspect_archive_profiles_every_tabular_member(synthetic_zip: Path) -> None:
    profiles = inspect_archive(synthetic_zip)
    names = {p.name for p in profiles}
    assert names == {"gas_distribution_2010_present.csv", "hazardous_liquid_1986_2009.csv"}
    by_name = {p.name: p for p in profiles}
    assert by_name["gas_distribution_2010_present.csv"].narrative_columns == ["NARRATIVE"]
    assert by_name["hazardous_liquid_1986_2009.csv"].narrative_columns == []


def test_record_manual_retrieval_states_the_method_and_hash(
    tmp_paths: ProjectPaths, synthetic_zip: Path
) -> None:
    retrieved_at = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    manifest = record_manual_retrieval(
        tmp_paths,
        synthetic_zip,
        url="https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/"
        "PHMSA_Pipeline_Safety_Flagged_Incidents.zip",
        retrieved_at=retrieved_at,
    )
    record = manifest.by_filename()[synthetic_zip.name]
    assert record.retrieval_method == RETRIEVAL_METHOD
    assert record.sha256 is not None and len(record.sha256) == 64
    assert record.retrieved_at == retrieved_at
    assert record.verified is True

    # re-reads from disk, not just the in-memory object
    from faultline.data.common.manifest import manifest_path, read_manifest

    reloaded = read_manifest(manifest_path(tmp_paths.manifests_dir, "phmsa"))
    assert reloaded is not None
    assert reloaded.by_filename()[synthetic_zip.name].retrieval_method == RETRIEVAL_METHOD


def test_render_report_shows_classification_totals_and_samples(
    tmp_paths: ProjectPaths, synthetic_zip: Path
) -> None:
    manifest = record_manual_retrieval(
        tmp_paths,
        synthetic_zip,
        url="https://example.org/flagged.zip",
        retrieved_at=datetime.now(tz=UTC),
    )
    profiles = inspect_archive(synthetic_zip)
    report = render_report(synthetic_zip, manifest, profiles)
    assert "manual, author, browser" in report
    assert "gas distribution / 2010-present form" in report
    assert "hazardous liquid / pre-2010 form" in report
    assert "NARRATIVE" in report
    assert "valve failed during routine operation" in report  # a verbatim sample


#: Shaped like the body Akamai served for the blocked flagged zip (PHMSA gate brief,
#: section 1b): what a browser "save as" of a denied download would leave behind.
ACCESS_DENIED_HTML = (
    b"<HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>\n<H1>Access Denied</H1>\n"
    b"You don't have permission to access this resource.</BODY></HTML>\n"
)


def test_inspect_archive_raises_on_an_error_page_saved_as_zip(tmp_path: Path) -> None:
    fake = tmp_path / "PHMSA_Pipeline_Safety_Flagged_Incidents.zip"
    fake.write_bytes(ACCESS_DENIED_HTML)
    with pytest.raises(ArchiveParseError, match="not a readable zip"):
        inspect_archive(fake)


def test_inspect_archive_raises_when_a_tabular_member_does_not_parse(tmp_path: Path) -> None:
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("incidents.xlsx", b"this is not an xlsx workbook")
    with pytest.raises(ArchiveParseError, match="incidents.xlsx"):
        inspect_archive(broken)


def test_inspect_archive_raises_when_no_member_is_tabular(tmp_path: Path) -> None:
    empty = tmp_path / "no_tables.zip"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("readme.pdf", b"%PDF-1.4")
    with pytest.raises(ArchiveParseError, match="no tabular member"):
        inspect_archive(empty)


def test_cli_writes_nothing_and_exits_non_zero_for_a_malformed_archive(
    tmp_paths: ProjectPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "PHMSA_Pipeline_Safety_Flagged_Incidents.zip"
    fake.write_bytes(ACCESS_DENIED_HTML)
    monkeypatch.setattr(cli.ProjectPaths, "resolve", classmethod(lambda _cls: tmp_paths))

    result = CliRunner().invoke(cli.app, ["inspect", "phmsa", "--file", str(fake)])

    assert result.exit_code != 0
    assert not manifest_path(tmp_paths.manifests_dir, "phmsa").exists()
    assert not list(tmp_paths.data_reports_dir.glob("phmsa_manual_*.md"))


class _RecordingSession(requests.Session):
    """Canned responses per URL; records every URL that reached the transport."""

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


def _robots_client(fixtures_dir: Path, extra: dict[str, tuple[int, bytes]]) -> NrcTextClient:
    robots = (fixtures_dir / "robots" / "data_transportation_gov.txt").read_bytes()
    robots_url = "https://data.transportation.gov/robots.txt"
    session = _RecordingSession({robots_url: (200, robots), **extra})
    client = NrcTextClient(min_interval=0, session=session)
    client._pace = lambda interval: None  # type: ignore[method-assign]
    return client


def test_fetch_socrata_attachment_saves_an_allowed_file(
    tmp_paths: ProjectPaths, fixtures_dir: Path
) -> None:
    url = (
        "https://data.transportation.gov/api/views/27nc-rsge/files/abc"
        "?download=true&filename=Hazardous%20Liquid%20x.zip"
    )
    client = _robots_client(fixtures_dir, {url: (200, b"PK\x03\x04zip-bytes")})

    path, fetched = fetch_socrata_attachment(
        client, tmp_paths, view="27nc-rsge", asset_id="abc", filename="Hazardous Liquid x.zip"
    )

    assert fetched == url
    assert path.read_bytes() == b"PK\x03\x04zip-bytes"
    assert path.parent.name == "phmsa"


def test_fetch_socrata_attachment_writes_nothing_on_a_non_200(
    tmp_paths: ProjectPaths, fixtures_dir: Path
) -> None:
    url = (
        "https://data.transportation.gov/api/views/27nc-rsge/files/abc?download=true&filename=x.zip"
    )
    client = _robots_client(fixtures_dir, {url: (403, b"Access Denied")})
    with pytest.raises(requests.HTTPError):
        fetch_socrata_attachment(
            client, tmp_paths, view="27nc-rsge", asset_id="abc", filename="x.zip"
        )
    assert not (tmp_paths.stage_dir("raw", "text") / "phmsa" / "x.zip").exists()


def test_a_tab_delimited_cp1252_member_reads_every_row() -> None:
    # the shape of PHMSA's 2010-onward flat file: tabs, Windows-1252, a lone quote in text
    header = "REPORT_NUMBER\tCOMMODITY_DETAILS\tNARRATIVE\r\n"
    rows = [
        '1\tCRUDE\tOperator found a 6" crack per \xa7195.402 and isolated the segment.\r\n',
        "2\tCRUDE\tA “weep” was found at the flange during a routine walk of the line.\r\n",
        "3\tDIESEL\tThe tank overfilled when the level alarm failed to actuate on time.\r\n",
    ]
    raw = (header + "".join(rows)).encode("cp1252")
    profile = profile_member("accident_hazardous_liquid_jan2010_present.txt", raw)
    assert profile is not None
    assert (profile.encoding, profile.delimiter) == ("cp1252", "tab")
    assert profile.rows == profile.physical_rows == 3
    assert profile.narrative_columns == ["COMMODITY_DETAILS", "NARRATIVE"]
    by_column = {v.column: v for v in profile.verdicts}
    assert by_column["NARRATIVE"].test == "name"
