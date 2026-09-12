"""Adapter discovery, classification and the channel map contract."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from faultline.data.telemetry.adapters import ADAPTERS, get_adapter
from faultline.data.telemetry.adapters.base import (
    BaseAdapter,
    RawMember,
    load_channel_map,
    load_rated_power_kw,
    open_member,
)
from faultline.data.telemetry.adapters.hill_of_towie import HillOfTowieAdapter
from faultline.data.telemetry.adapters.kelmarsh import KelmarshAdapter
from faultline.download.zenodo import RatedPower, SourceSpec, load_sources_config


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
    assert adapter.channel_map["power_pu"] == "Power (kW)"
    assert adapter.channel_map["wind_speed_ms"] == "Wind speed (m/s)"
    # The main-shaft bearing was added to the canonical list on 2026-09-09 and mapped
    # from signal 447, "Temperature of rotor bearing".
    assert adapter.channel_map["main_bearing_temp_c"] == "Rotor bearing temp (°C)"
    assert len(adapter.channel_map) == 13
    # The one channel this record does not publish is absent rather than guessed: the
    # signal mapping resolves every bearing column, and none of them is a gearbox
    # bearing.
    assert "gearbox_bearing_temp_c" not in adapter.channel_map


def test_penmanshiel_channel_map_agrees_with_kelmarsh_column_for_column(repo_root: Path) -> None:
    # Resolved on 2026-09-10 from Penmanshiel's own headers and signal-mapping workbook,
    # not copied from Kelmarsh. That the two Senvion records agree is the finding, and
    # this pins it -- including the gearbox bearing temperature neither of them has.
    penmanshiel = get_adapter("penmanshiel", repo_root / "configs").channel_map
    kelmarsh = get_adapter("kelmarsh", repo_root / "configs").channel_map
    assert len(penmanshiel) == 13
    assert "gearbox_bearing_temp_c" not in penmanshiel
    assert penmanshiel == kelmarsh


def test_hill_of_towie_map_names_the_table_as_well_as_the_field(repo_root: Path) -> None:
    # Resolved on 2026-09-10 from the provider's field lookup. The record spreads one
    # turbine's signals over several tables, so a column is <table>.<field>.
    towie = get_adapter("hill_of_towie", repo_root / "configs")
    assert len(towie.channel_map) == 14
    assert towie.channel_map["power_pu"] == "tblSCTurGrid.wtc_ActPower_mean"
    assert towie.split_channel_column(towie.channel_map["power_pu"]) == (
        "tblSCTurGrid",
        "wtc_ActPower_mean",
    )


def test_care_keeps_its_columns_per_farm_and_out_of_the_flat_map(repo_root: Path) -> None:
    # CARE's farms publish different sensor sets, so its map is per farm (see
    # test_channels.py). The flat map must stay empty rather than stringify a nested
    # block into a column name that does not exist.
    assert get_adapter("care", repo_root / "configs").channel_map == {}


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
        # A per-turbine downtime series: a label source, not an event log.
        ("ShutdownDuration.csv", "downtime_series"),
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


def test_every_source_has_its_own_scada_loader() -> None:
    # Each was written against its own inspection evidence (M1a step 4); none falls
    # through to the base adapter, which refuses rather than guess at a layout.
    for name, adapter_class in ADAPTERS.items():
        assert adapter_class.load_scada_with_stats is not BaseAdapter.load_scada_with_stats, name


def test_the_base_adapter_refuses_to_guess_a_layout(tmp_path: Path) -> None:
    member = RawMember(tmp_path / "x.zip", "a.csv", "scada_10min", 1, 1, True)
    with pytest.raises(NotImplementedError):
        BaseAdapter().load_scada(member)
    with pytest.raises(NotImplementedError):
        BaseAdapter().load_events(member)


def test_channel_map_skips_unresolved_entries(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        "channels:\n"
        "  wind_speed_ms: Wind speed (m/s)\n"
        "  power_pu: null\n"
        "  rotor_speed_rpm: TODO(m1) fill from the mapping file\n",
        encoding="utf-8",
    )
    assert load_channel_map(path) == {"wind_speed_ms": "Wind speed (m/s)"}


def test_missing_channel_map_is_empty(tmp_path: Path) -> None:
    assert load_channel_map(tmp_path / "absent.yaml") == {}


# -- power in per unit of rated power (ADR-0013) ---------------------------------------


def test_every_source_that_publishes_kw_declares_a_cited_rating(repo_root: Path) -> None:
    # The divisor is a nameplate fact, and it has to be checkable: a rating nobody can
    # verify would be a guess, and a guess fitted to the record is what ADR-0011 rejected.
    sources = load_sources_config(repo_root / "configs" / "data" / "sources_telemetry.yaml")
    ratings = {name: spec.rated_power_kw for name, spec in sources.sources.items()}
    assert {name: r.value for name, r in ratings.items() if r} == {
        "kelmarsh": 2050.0,
        "penmanshiel": 2050.0,
        "hill_of_towie": 2300.0,
    }
    # CARE publishes power already per unit, so it declares no rating and none is inferred.
    assert ratings["care"] is None
    for name, rating in ratings.items():
        if rating is not None:
            assert "Rated power (kW)" in rating.citation, name
            assert "Zenodo record" in rating.citation, name


def test_a_rating_without_a_citation_is_rejected() -> None:
    with pytest.raises(ValidationError, match="needs a citation"):
        RatedPower.model_validate({"value": 2050, "citation": "  "})


@pytest.mark.parametrize(
    ("source", "rated"),
    [("kelmarsh", 2050.0), ("penmanshiel", 2050.0), ("hill_of_towie", 2300.0), ("care", None)],
)
def test_the_adapter_carries_its_rating(repo_root: Path, source: str, rated: float | None) -> None:
    assert get_adapter(source, repo_root / "configs").rated_power_kw == rated


def test_power_is_divided_by_the_rating_and_nothing_else_is(repo_root: Path) -> None:
    adapter = get_adapter("hill_of_towie", repo_root / "configs")
    frame = pd.DataFrame({"power_pu": [0.0, 1150.0, 2300.0, None], "wind_speed_ms": [1.0] * 4})
    out = adapter.to_canonical_units(frame)
    assert out["power_pu"].tolist()[:3] == [0.0, 0.5, 1.0]
    assert bool(pd.isna(out["power_pu"].iloc[3]))
    assert out["wind_speed_ms"].tolist() == [1.0] * 4


def test_a_source_with_no_rating_is_left_alone(repo_root: Path) -> None:
    # CARE's values are already per unit; dividing them again would be the guess the
    # record cannot support.
    adapter = get_adapter("care", repo_root / "configs")
    frame = pd.DataFrame({"power_pu": [0.0, 0.5, 1.04]})
    assert adapter.to_canonical_units(frame)["power_pu"].tolist() == [0.0, 0.5, 1.04]


def test_rated_power_of_an_unknown_source_is_none(repo_root: Path) -> None:
    assert load_rated_power_kw(repo_root / "configs", "no_such_source") is None


def test_rated_power_without_a_source_specification_is_none(tmp_path: Path) -> None:
    assert load_rated_power_kw(tmp_path, "kelmarsh") is None


def test_the_two_ratings_cannot_drift_apart(repo_root: Path) -> None:
    # site.rated_kw is printed on the dataset cards and rated_power_kw is what the
    # adapters divide by. They are the same fact, and a drift would rescale a site.
    payload = yaml.safe_load(
        (repo_root / "configs" / "data" / "sources_telemetry.yaml").read_text(encoding="utf-8")
    )
    spec = payload["sources"]["kelmarsh"]
    spec["rated_power_kw"]["value"] = 2300
    with pytest.raises(ValidationError, match="disagree"):
        SourceSpec.model_validate(spec)
