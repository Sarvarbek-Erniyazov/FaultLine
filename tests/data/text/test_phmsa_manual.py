"""Read-only inspection of a manually retrieved PHMSA archive, against a synthetic zip."""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from faultline.data.text.phmsa_manual import (
    RETRIEVAL_METHOD,
    classify_member,
    inspect_archive,
    profile_member,
    record_manual_retrieval,
    render_report,
)
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
