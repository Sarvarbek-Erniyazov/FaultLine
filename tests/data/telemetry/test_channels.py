"""Channel map statuses, header presence, and the core set derived from them."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from faultline.data.telemetry.adapters.base import RawMember, header_columns
from faultline.data.telemetry.adapters.hill_of_towie import HillOfTowieAdapter
from faultline.data.telemetry.channels import (
    derive_core,
    header_presence,
    load_channel_maps,
    parse_channel_map,
    render_channel_report,
)
from faultline.data.telemetry.schemas import CHANNEL_NAMES

SOURCES = ("kelmarsh", "penmanshiel", "hill_of_towie", "care")


def write_map(tmp_path: Path, name: str = "x", **sections: Any) -> Path:
    body: dict[str, Any] = {"source": name, "channels": dict.fromkeys(CHANNEL_NAMES)}
    for key, value in sections.items():
        if key == "channels":
            body["channels"].update(value)
        else:
            body[key] = value
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    return path


# -- the shipped maps -----------------------------------------------------------------


def test_every_shipped_map_is_valid_and_leaves_nothing_open(repo_root: Path) -> None:
    maps = load_channel_maps(repo_root / "configs", SOURCES)
    for doc in maps.values():
        for group in doc.groups:
            assert list(group.entries) == list(CHANNEL_NAMES)
            # every channel is a finding -- resolved, absent or ambiguous -- not a gap
            assert all(entry.status != "unresolved" for entry in group.entries.values())


def test_hill_of_towie_resolves_every_channel_from_its_field_lookup(repo_root: Path) -> None:
    doc = load_channel_maps(repo_root / "configs", ["hill_of_towie"])["hill_of_towie"]
    assert doc.resolved_everywhere() == set(CHANNEL_NAMES)
    power = doc.groups[0].entries["power_kw"]
    assert power.column == "tblSCTurGrid.wtc_ActPower_mean"
    assert power.evidence == "Active power (kW)"


def test_gearbox_bearing_is_published_at_the_held_out_site_only(repo_root: Path) -> None:
    maps = load_channel_maps(repo_root / "configs", SOURCES)
    assert maps["kelmarsh"].status("gearbox_bearing_temp_c") == "verified absent"
    assert maps["penmanshiel"].status("gearbox_bearing_temp_c") == "verified absent"
    assert maps["hill_of_towie"].status("gearbox_bearing_temp_c") == "resolved"


def test_care_is_mapped_per_farm_with_its_unit_caveats(repo_root: Path) -> None:
    doc = load_channel_maps(repo_root / "configs", ["care"])["care"]
    farms = {group.name: group for group in doc.groups}
    assert set(farms) == {"farm_a", "farm_b", "farm_c"}
    assert farms["farm_a"].directory == "Wind Farm A"
    assert farms["farm_c"].entries["wind_direction_deg"].status == "verified absent"
    assert farms["farm_b"].entries["gearbox_bearing_temp_c"].status == "ambiguous"
    # CARE power is normalised; the map must not let it pass for kW
    for group in doc.groups:
        note = group.entries["power_kw"].unit_note
        assert note is not None and "not kW" in note


# -- validation -----------------------------------------------------------------------


def test_a_mapped_channel_needs_evidence(tmp_path: Path) -> None:
    path = write_map(tmp_path, channels={"power_kw": "Power (kW)"})
    with pytest.raises(ValueError, match="no evidence"):
        parse_channel_map(path)


def test_every_canonical_channel_must_be_declared(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    path.write_text("channels:\n  power_kw: Power (kW)\n", encoding="utf-8")
    with pytest.raises(ValueError, match="every canonical channel must be declared"):
        parse_channel_map(path)


def test_a_channel_cannot_be_mapped_and_absent_at_once(tmp_path: Path) -> None:
    path = write_map(
        tmp_path,
        channels={"power_kw": "Power (kW)"},
        evidence={"power_kw": "active power"},
        verified_absent={"power_kw": "not published"},
    )
    with pytest.raises(ValueError, match="also listed as absent or ambiguous"):
        parse_channel_map(path)


def test_a_non_canonical_channel_is_rejected(tmp_path: Path) -> None:
    path = write_map(tmp_path, verified_absent={"gearbox_bearing_temp": "typo"})
    with pytest.raises(ValueError, match="non-canonical"):
        parse_channel_map(path)


def test_an_unchecked_null_is_unresolved_not_absent(tmp_path: Path) -> None:
    # "Nobody looked" must not read as "not published": only the second demotes a
    # channel from core.
    doc = parse_channel_map(write_map(tmp_path))
    assert {entry.status for entry in doc.groups[0].entries.values()} == {"unresolved"}


# -- the core set ---------------------------------------------------------------------


def _resolved_map(tmp_path: Path, name: str, missing: dict[str, str]) -> Path:
    channels = {c: f"col {c}" for c in CHANNEL_NAMES if c not in missing}
    evidence = {c: f"provider says {c}" for c in channels}
    return write_map(tmp_path, name, channels=channels, evidence=evidence, verified_absent=missing)


def test_core_needs_every_training_site_and_the_held_out_site(tmp_path: Path) -> None:
    maps = {
        "a": parse_channel_map(_resolved_map(tmp_path, "a", {"nacelle_temp_c": "absent"})),
        "b": parse_channel_map(_resolved_map(tmp_path, "b", {})),
        "h": parse_channel_map(_resolved_map(tmp_path, "h", {"main_bearing_temp_c": "absent"})),
    }
    core, extended = derive_core(maps, training=["a", "b"], holdout=["h"])
    assert "nacelle_temp_c" in extended  # missing at one training site
    assert "main_bearing_temp_c" in extended  # not mappable at the held-out site
    assert len(core) == len(CHANNEL_NAMES) - 2
    assert core == [c for c in CHANNEL_NAMES if c in core]  # canonical order kept


def test_core_derivation_refuses_a_source_without_a_map(tmp_path: Path) -> None:
    maps = {"a": parse_channel_map(_resolved_map(tmp_path, "a", {}))}
    with pytest.raises(KeyError, match="no channel map"):
        derive_core(maps, training=["a"], holdout=["h"])


# -- header presence ------------------------------------------------------------------


def _member(archive: Path, name: str) -> RawMember:
    with zipfile.ZipFile(archive) as handle:
        size = handle.getinfo(name).file_size
    return RawMember(archive, name, "scada_10min", size, size, True)


def test_header_presence_counts_by_year_for_a_table_column(tmp_path: Path) -> None:
    archive = tmp_path / "hot.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("tblSCTurbine_2019_01.csv", "TimeStamp,StationId,wtc_Windvane_timeon\n")
        handle.writestr(
            "tblSCTurbine_2023_01.csv", "TimeStamp,StationId,wtc_ActualWindDirection_mean\n"
        )
        handle.writestr("tblSCTurTemp_2023_01.csv", "TimeStamp,StationId,wtc_AmbieTmp_mean\n")
    members = [
        _member(archive, name)
        for name in (
            "tblSCTurbine_2019_01.csv",
            "tblSCTurbine_2023_01.csv",
            "tblSCTurTemp_2023_01.csv",
        )
    ]
    doc = parse_channel_map(
        write_map(
            tmp_path,
            channels={"wind_direction_deg": "tblSCTurbine.wtc_ActualWindDirection_mean"},
            evidence={"wind_direction_deg": "Actual wind direction"},
        )
    )
    presence = header_presence(doc, HillOfTowieAdapter(), members)
    where = presence[("all", "wind_direction_deg")]
    # the tblSCTurTemp member is not one the column could live in
    assert (where.members, where.present) == (2, 1)
    assert where.describe() == "2019: 0/1, 2023: 1/1"


def test_header_columns_reads_every_provider_layout(tmp_path: Path) -> None:
    archive = tmp_path / "layouts.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        # Greenbyte turbine data: the last comment line is the header
        handle.writestr(
            "a.csv", '# x\n#\n# Date and time,"Wind speed, Max (m/s)",Power (kW)\n1,2,3\n'
        )
        # Greenbyte status: a clean header after the preamble
        handle.writestr("b.csv", "# x\n#\nTimestamp start,Code,Message\n1,2,3\n")
        # CARE: semicolons, no preamble
        handle.writestr("c.csv", "time_stamp;asset_id;sensor_0_avg\n1;2;3\n")
    assert header_columns(_member(archive, "a.csv")) == [
        "Date and time",
        "Wind speed, Max (m/s)",
        "Power (kW)",
    ]
    assert header_columns(_member(archive, "b.csv")) == ["Timestamp start", "Code", "Message"]
    assert header_columns(_member(archive, "c.csv")) == ["time_stamp", "asset_id", "sensor_0_avg"]


def test_the_report_names_the_channel_only_the_held_out_site_publishes(repo_root: Path) -> None:
    maps = load_channel_maps(repo_root / "configs", SOURCES)
    report = render_channel_report(
        maps, {}, ["kelmarsh", "penmanshiel"], ["hill_of_towie"], repo_root
    )
    assert "`gearbox_bearing_temp_c` is published at the held-out site" in report
    assert "## care - farm_c" in report
