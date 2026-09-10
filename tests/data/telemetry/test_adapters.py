"""Adapter discovery, classification and the channel map contract."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from faultline.data.telemetry.adapters import ADAPTERS, get_adapter
from faultline.data.telemetry.adapters.base import RawMember, load_channel_map, open_member
from faultline.data.telemetry.adapters.hill_of_towie import HillOfTowieAdapter
from faultline.data.telemetry.adapters.kelmarsh import KelmarshAdapter


def make_archive(directory: Path, name: str, members: dict[str, str]) -> Path:
    path = directory / name
    with zipfile.ZipFile(path, "w") as archive:
        for member, content in members.items():
            archive.writestr(member, content)
    return path


def test_every_source_has_an_adapter() -> None:
    assert set(ADAPTERS) == {"kelmarsh", "penmanshiel", "hill_of_towie", "care"}


def test_get_adapter_loads_the_channel_map(repo_root: Path) -> None:
    adapter = get_adapter("kelmarsh", repo_root / "configs")
    assert adapter.source_id == "kelmarsh"
    # Kelmarsh was resolved at M0 from the real SCADA header.
    assert adapter.channel_map["power_kw"] == "Power (kW)"
    assert adapter.channel_map["wind_speed_ms"] == "Wind speed (m/s)"
    # The main-shaft bearing was added to the canonical list on 2026-09-09 and mapped
    # from signal 447, "Temperature of rotor bearing".
    assert adapter.channel_map["main_bearing_temp_c"] == "Rotor bearing temp (°C)"
    assert len(adapter.channel_map) == 13
    # The one channel this record does not publish is absent rather than guessed: the
    # signal mapping resolves every bearing column, and none of them is a gearbox
    # bearing.
    assert "gearbox_bearing_temp_c" not in adapter.channel_map


def test_unresolved_channel_maps_stay_empty(repo_root: Path) -> None:
    # The other three sources are still TODO(m1), so their maps resolve to nothing
    # rather than to something plausible and wrong.
    for source in ("penmanshiel", "hill_of_towie", "care"):
        assert get_adapter(source, repo_root / "configs").channel_map == {}


def test_unknown_source_is_rejected(repo_root: Path) -> None:
    with pytest.raises(KeyError, match="no adapter"):
        get_adapter("nowhere", repo_root / "configs")


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Turbine_Data_Kelmarsh_1_2020.csv", "scada_10min"),
        ("Status_Kelmarsh_1_2020.csv", "status_events"),
        ("alarms_2020.csv", "alarm_log"),
        ("Kelmarsh_WT_dataSignalMapping.csv", "metadata"),
        ("Kelmarsh_WT_static.csv", "metadata"),
        ("something_else.bin", "other"),
    ],
)
def test_classification(name: str, kind: str) -> None:
    assert KelmarshAdapter().classify(name) == kind


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("tblAlarmLog_2019_01.csv", "alarm_log"),
        ("tblSCTurbine_2019_01.csv", "scada_10min"),
        # The turbine table that carries active power; a generic "grid" rule sent it
        # to "other".
        ("tblSCTurGrid_2019_01.csv", "scada_10min"),
        ("tblSCTurFlag_2019_01.csv", "scada_10min"),
        ("tblSCTurTemp_2023_12.csv", "scada_10min"),
        ("tblGrid_2019_01.csv", "other"),
        ("tblGridScientific_2019_01.csv", "other"),
        ("tblDailySummary_2019_01.csv", "other"),
        ("ShutdownDuration.csv", "status_events"),
        ("Hill_of_Towie_alarms_description.csv", "metadata"),
        ("Hill_of_Towie_tables_description.csv", "metadata"),
        ("Hill_of_Towie_turbine_fields_description.csv", "metadata"),
    ],
)
def test_hill_of_towie_classification_follows_the_provider_table_names(
    name: str, kind: str
) -> None:
    assert HillOfTowieAdapter().classify(name) == kind


def test_classification_source_is_stated_for_every_adapter() -> None:
    for adapter_class in ADAPTERS.values():
        assert adapter_class.CLASSIFICATION_SOURCE
    assert "tables_description" in HillOfTowieAdapter.CLASSIFICATION_SOURCE


def test_discover_lists_archive_members_without_extracting(tmp_path: Path) -> None:
    make_archive(
        tmp_path,
        "Kelmarsh_SCADA_2020_3086.zip",
        {
            "Turbine_Data_Kelmarsh_1_2020.csv": "a,b\n1,2\n",
            "Status_Kelmarsh_1_2020.csv": "code,message\n1,ok\n",
        },
    )
    (tmp_path / "Kelmarsh_WT_static.csv").write_text("id,name\n1,T1\n", encoding="utf-8")

    members = KelmarshAdapter().discover(tmp_path)
    kinds = {member.kind for member in members}
    assert kinds == {"scada_10min", "status_events", "metadata"}
    assert len(members) == 3
    # nothing was written next to the archive
    assert not (tmp_path / "Turbine_Data_Kelmarsh_1_2020.csv").exists()


def test_discover_on_an_empty_directory(tmp_path: Path) -> None:
    assert KelmarshAdapter().discover(tmp_path) == []


def test_discover_survives_a_corrupt_archive(tmp_path: Path) -> None:
    (tmp_path / "broken.zip").write_bytes(b"not a zip file")
    assert KelmarshAdapter().discover(tmp_path) == []


def test_open_member_reads_from_inside_the_archive(tmp_path: Path) -> None:
    archive = make_archive(tmp_path, "x.zip", {"inner.csv": "a,b\n1,2\n"})
    member = RawMember(
        archive=archive,
        name="inner.csv",
        kind="scada_10min",
        size=8,
        compressed_size=8,
        in_archive=True,
    )
    with open_member(member) as handle:
        assert handle.read() == b"a,b\n1,2\n"


def test_open_member_reads_a_loose_file(tmp_path: Path) -> None:
    path = tmp_path / "loose.csv"
    path.write_bytes(b"x\n")  # bytes, so Windows text mode does not insert a CR
    member = RawMember(
        archive=path, name="", kind="metadata", size=2, compressed_size=2, in_archive=False
    )
    with open_member(member) as handle:
        assert handle.read() == b"x\n"


def test_unimplemented_loaders_raise_with_an_actionable_todo(tmp_path: Path) -> None:
    # Kelmarsh has real loaders (see test_kelmarsh_adapter.py). The other three wait on
    # their own inspection evidence, and must say what is needed rather than guess at a
    # column layout -- a wrong guess there is silent and produces a plausible table
    # built from the wrong columns.
    member = RawMember(
        archive=tmp_path / "x.zip",
        name="a.csv",
        kind="scada_10min",
        size=1,
        compressed_size=1,
        in_archive=True,
    )
    pending = {name: cls for name, cls in ADAPTERS.items() if name != "kelmarsh"}
    assert set(pending) == {"penmanshiel", "hill_of_towie", "care"}
    for adapter_class in pending.values():
        adapter = adapter_class()
        with pytest.raises(NotImplementedError, match="TODO"):
            adapter.load_scada(member)
        with pytest.raises(NotImplementedError, match="TODO"):
            adapter.load_events(member)


def test_channel_map_skips_unresolved_entries(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        "channels:\n"
        "  wind_speed_ms: Wind speed (m/s)\n"
        "  power_kw: null\n"
        "  rotor_speed_rpm: TODO(m1) fill from the mapping file\n",
        encoding="utf-8",
    )
    assert load_channel_map(path) == {"wind_speed_ms": "Wind speed (m/s)"}


def test_missing_channel_map_is_empty(tmp_path: Path) -> None:
    assert load_channel_map(tmp_path / "absent.yaml") == {}
