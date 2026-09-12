"""Kelmarsh loaders, tested against real provider bytes.

These tests use the committed excerpt in ``tests/fixtures/telemetry/kelmarsh/``
(CC BY 4.0, see its README) rather than synthetic data. The adapter exists to survive
one provider's quirks, and a synthetic fixture only ever reproduces the quirks the
author already thought of.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from faultline.data.telemetry.adapters.base import RawMember, read_csv_member, read_preamble
from faultline.data.telemetry.adapters.kelmarsh import KelmarshAdapter
from faultline.data.telemetry.adapters.penmanshiel import PenmanshielAdapter
from faultline.data.telemetry.collapse import RepeatedLabelConflictError
from faultline.data.telemetry.schemas import EVENT_COLUMNS, INDEX_COLUMNS, validate_events

CHANNEL_MAP = {
    "wind_speed_ms": "Wind speed (m/s)",
    "power_pu": "Power (kW)",
    "rotor_speed_rpm": "Rotor speed (RPM)",
    "generator_speed_rpm": "Generator RPM (RPM)",
    "pitch_angle_deg": "Blade angle (pitch position) A (°)",
    "nacelle_position_deg": "Nacelle position (°)",
    "wind_direction_deg": "Wind direction (°)",
    "ambient_temp_c": "Nacelle ambient temperature (°C)",
    "nacelle_temp_c": "Nacelle temperature (°C)",
    "gearbox_oil_temp_c": "Gear oil temperature (°C)",
    "generator_bearing_temp_c": "Generator bearing front temperature (°C)",
    "generator_winding_temp_c": "Stator temperature 1 (°C)",
}


@pytest.fixture
def kelmarsh_fixtures(fixtures_dir: Path) -> Path:
    return fixtures_dir / "telemetry" / "kelmarsh"


def loose_member(path: Path, kind: str) -> RawMember:
    size = path.stat().st_size
    return RawMember(
        archive=path,
        name="",
        kind=kind,  # type: ignore[arg-type]
        size=size,
        compressed_size=size,
        in_archive=False,
    )


@pytest.fixture
def adapter() -> KelmarshAdapter:
    return KelmarshAdapter(channel_map=dict(CHANNEL_MAP))


@pytest.fixture
def scada_member(kelmarsh_fixtures: Path) -> RawMember:
    return loose_member(kelmarsh_fixtures / "Turbine_Data_Kelmarsh_1_excerpt.csv", "scada_10min")


@pytest.fixture
def status_member(kelmarsh_fixtures: Path) -> RawMember:
    return loose_member(kelmarsh_fixtures / "Status_Kelmarsh_1_excerpt.csv", "status_events")


def test_preamble_carries_turbine_and_timezone(scada_member: RawMember) -> None:
    preamble = read_preamble(scada_member)
    assert preamble["turbine"] == "Kelmarsh 1"
    # The record's timezone is stated by the file, not assumed by the pipeline.
    assert preamble["time zone"] == "UTC"
    assert preamble["turbine type"] == "Senvion MM92"


def test_turbine_id_comes_from_the_preamble(
    adapter: KelmarshAdapter, scada_member: RawMember
) -> None:
    assert adapter.turbine_id(scada_member) == "Kelmarsh 1"


def test_load_scada_produces_the_canonical_schema(
    adapter: KelmarshAdapter, scada_member: RawMember
) -> None:
    frame = adapter.load_scada(scada_member)

    for column in INDEX_COLUMNS:
        assert column in frame.columns
    assert frame["source"].unique().tolist() == ["kelmarsh"]
    assert frame["site"].unique().tolist() == ["Kelmarsh"]
    assert frame["turbine_id"].unique().tolist() == ["Kelmarsh 1"]

    # every mapped channel arrives under its canonical name
    for canonical in CHANNEL_MAP:
        assert canonical in frame.columns
        assert pd.api.types.is_numeric_dtype(frame[canonical])

    # the unmapped channel is absent rather than invented
    assert "gearbox_bearing_temp_c" not in frame.columns


def test_load_scada_timestamps_are_utc_and_on_a_ten_minute_grid(
    adapter: KelmarshAdapter, scada_member: RawMember
) -> None:
    frame = adapter.load_scada(scada_member)
    stamps = frame["timestamp_utc"]
    assert str(stamps.dt.tz) == "UTC"
    assert stamps.is_monotonic_increasing
    deltas = stamps.diff().dropna().unique()
    assert list(deltas) == [pd.Timedelta(minutes=10)]


def test_rows_with_no_mapped_value_are_dropped_and_accounted_for(
    adapter: KelmarshAdapter, scada_member: RawMember
) -> None:
    # The leading rows of this file are the turbine before it started reporting. A row
    # null in every mapped channel carries nothing, so ingest drops it -- and says so,
    # and the clean stage puts the timestep back on the grid as missing. What must never
    # happen is a value appearing that the provider did not write.
    frame, account = adapter.load_scada_with_stats(scada_member)
    raw = read_csv_member(scada_member)
    mapped = [column for column in CHANNEL_MAP.values() if column in raw.columns]
    carrying = raw[mapped].apply(pd.to_numeric, errors="coerce").notna().any(axis=1)

    assert account.stats.rows_raw == len(raw) == 40
    assert account.stats.labels_distinct == 40  # 2016: one row per label
    assert account.stats.rows_after_null_drop == int(carrying.sum()) < 40
    assert len(frame) == int(carrying.sum())
    kept = raw[carrying].reset_index(drop=True)
    for canonical, column in CHANNEL_MAP.items():
        expected = pd.to_numeric(kept[column], errors="coerce")
        assert frame[canonical].equals(expected.rename(canonical)) or (
            frame[canonical].isna().equals(expected.isna())
            and (frame[canonical].dropna() == expected.dropna()).all()
        )


GREENBYTE_HEADER = "# Date and time,Wind speed (m/s),Power (kW),Production-based System Avail."
GREENBYTE_PREAMBLE = "# Exported by a vendor tool.\n#\n# Turbine: Kelmarsh 1\n# Time zone: UTC\n#\n"


def greenbyte_member(tmp_path: Path, rows: list[str]) -> RawMember:
    path = tmp_path / "Turbine_Data_Kelmarsh_1_2023.csv"
    path.write_bytes(
        (GREENBYTE_PREAMBLE + GREENBYTE_HEADER + "\n" + "\n".join(rows) + "\n").encode()
    )
    return loose_member(path, "scada_10min")


def test_a_repeated_greenbyte_export_collapses_without_losing_a_value(
    tmp_path: Path, adapter: KelmarshAdapter
) -> None:
    # The 2023 layout in miniature: cumulative blocks that re-emit earlier labels with
    # the measured channels empty and the availability figure repeated.
    member = greenbyte_member(
        tmp_path,
        [
            "2023-01-01 00:00:00,9.1,1850,100",
            "2023-01-01 00:00:00,NaN,NaN,100",
            "2023-01-01 00:10:00,8.2,1600,100",
            "2023-01-01 00:00:00,NaN,NaN,100",
            "2023-01-01 00:10:00,NaN,NaN,100",
            "2023-01-01 00:20:00,7.5,1400,100",
        ],
    )
    frame, account = adapter.load_scada_with_stats(member)
    assert list(frame["power_pu"]) == [1850.0, 1600.0, 1400.0]
    assert list(frame["wind_speed_ms"]) == [9.1, 8.2, 7.5]
    assert frame["timestamp_utc"].is_monotonic_increasing
    stats = account.stats
    assert (stats.rows_raw, stats.rows_after_null_drop, stats.labels_distinct) == (6, 3, 3)
    assert stats.rows_out == 3 and stats.repeated_export


def test_repeats_that_disagree_stop_the_ingest(tmp_path: Path, adapter: KelmarshAdapter) -> None:
    member = greenbyte_member(
        tmp_path, ["2023-01-01 00:00:00,9.1,1850,100", "2023-01-01 00:00:00,9.1,1790,100"]
    )
    with pytest.raises(RepeatedLabelConflictError, match="Power"):
        adapter.load_scada_with_stats(member)


def test_penmanshiel_reads_the_same_greenbyte_export(scada_member: RawMember) -> None:
    # Same publisher, same export, confirmed against all 98 Penmanshiel headers: the
    # loader is shared, not copied.
    frame = PenmanshielAdapter(channel_map=dict(CHANNEL_MAP)).load_scada(scada_member)
    assert frame["source"].unique().tolist() == ["penmanshiel"]
    assert frame["power_pu"].notna().any()


def test_load_scada_needs_a_channel_map(scada_member: RawMember) -> None:
    with pytest.raises(RuntimeError, match="channel map is empty"):
        KelmarshAdapter().load_scada(scada_member)


def test_load_events_produces_the_canonical_schema(
    adapter: KelmarshAdapter, status_member: RawMember
) -> None:
    events = adapter.load_events(status_member)
    assert events is not None
    assert list(events.columns) == list(EVENT_COLUMNS)
    validate_events(events)

    assert events["turbine_id"].unique().tolist() == ["Kelmarsh 1"]
    assert str(events["start_utc"].dt.tz) == "UTC"
    assert events["message"].notna().all()
    assert events["code"].notna().all()


def test_load_events_keeps_the_provider_row_verbatim(
    adapter: KelmarshAdapter, status_member: RawMember
) -> None:
    # ADR-0006: normalization is lossy and the fault mapping is unresolved, so the raw
    # row is preserved and a later mapping revision needs no re-ingest.
    events = adapter.load_events(status_member)
    assert events is not None
    assert events["raw"].str.startswith("{").all()
    assert "Emergency stop nacelle" in " ".join(events["raw"].tolist())


def test_load_events_leaves_the_fault_flag_unset(
    adapter: KelmarshAdapter, status_member: RawMember
) -> None:
    # Deciding that a provider status means "fault" is a labelling decision for the
    # configured code mapping, not something the reader may assume.
    events = adapter.load_events(status_member)
    assert events is not None
    assert events["is_fault"].isna().all()


def test_load_events_carries_the_provider_category(
    adapter: KelmarshAdapter, status_member: RawMember
) -> None:
    events = adapter.load_events(status_member)
    assert events is not None
    assert set(events["category"].dropna().unique()) <= {
        "Stop",
        "Warning",
        "Informational",
        "Ok",
        "Maintenance",
    }


def test_messages_are_a_controlled_vocabulary(
    adapter: KelmarshAdapter, status_member: RawMember
) -> None:
    # The evidence behind ADR-0001, pinned as a test: a couple of hundred rows carry
    # only a few dozen distinct short strings.
    events = adapter.load_events(status_member)
    assert events is not None
    messages = events["message"].dropna()
    assert len(messages) > 100
    assert messages.nunique() < 100
    assert messages.str.len().mean() < 40


def test_missing_status_columns_raise(tmp_path: Path, adapter: KelmarshAdapter) -> None:
    path = tmp_path / "Status_broken.csv"
    path.write_bytes(b"# preamble\nTimestamp start,Something\n2016-01-01 00:00:00,1\n")
    with pytest.raises(RuntimeError, match="missing columns"):
        adapter.load_events(loose_member(path, "status_events"))


def test_scada_without_a_timestamp_column_raises(tmp_path: Path, adapter: KelmarshAdapter) -> None:
    path = tmp_path / "Turbine_Data_broken.csv"
    path.write_bytes(b"# preamble\nA,B\n1,2\n")
    with pytest.raises(RuntimeError, match="Date and time"):
        adapter.load_scada(loose_member(path, "scada_10min"))


def test_loader_works_on_a_member_inside_an_archive(
    tmp_path: Path, adapter: KelmarshAdapter, kelmarsh_fixtures: Path
) -> None:
    # Real ingest reads inside the zip, so the archive path must behave identically.
    archive = tmp_path / "Kelmarsh_SCADA_2016_test.zip"
    payload = (kelmarsh_fixtures / "Status_Kelmarsh_1_excerpt.csv").read_bytes()
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("Status_Kelmarsh_1_2016.csv", payload)

    member = RawMember(
        archive=archive,
        name="Status_Kelmarsh_1_2016.csv",
        kind="status_events",
        size=len(payload),
        compressed_size=len(payload),
        in_archive=True,
    )
    events = adapter.load_events(member)
    assert events is not None
    assert len(events) > 100
