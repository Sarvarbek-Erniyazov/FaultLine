"""Adapter discovery, classification and the channel map contract."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from faultline.data.telemetry.adapters import ADAPTERS, get_adapter
from faultline.data.telemetry.adapters.base import RawMember, load_channel_map, open_member
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
    # every entry is TODO(m1) at M0, so the resolved map is empty rather than wrong
    assert adapter.channel_map == {}


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


def test_loaders_raise_with_an_actionable_todo(tmp_path: Path) -> None:
    member = RawMember(
        archive=tmp_path / "x.zip",
        name="a.csv",
        kind="scada_10min",
        size=1,
        compressed_size=1,
        in_archive=True,
    )
    for adapter_class in ADAPTERS.values():
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
