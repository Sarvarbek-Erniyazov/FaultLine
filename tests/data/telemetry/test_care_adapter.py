"""CARE loaders, on a synthetic farm shaped like the staged archive.

Synthetic on purpose: CARE is CC BY-SA 4.0, and a verbatim excerpt committed here would
be redistributed adapted material. The shapes are the README's: semicolon-separated
datasets named by event id, and one event_info file per farm.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from faultline.data.telemetry.adapters.base import RawMember
from faultline.data.telemetry.adapters.care import CareAdapter

DATASET = (
    "time_stamp;asset_id;id;train_test;status_type_id;sensor_0_avg;wind_speed_3_avg;sensor_18_avg\n"
    "2022-08-04 06:10:00;0;0;train;0;20.0;5.6;600.0\n"
    "2022-08-04 06:20:00;0;1;train;0;;;\n"
    "2022-08-04 06:30:00;0;2;prediction;4;21.0;6.1;610.0\n"
)

EVENT_INFO = (
    "asset;event_id;event_label;event_start;event_start_id;event_end;event_end_id;"
    "event_description\n"
    "0;7;anomaly;2022-08-04 06:30:00;2;2022-08-11 06:30:00;1010;Hydraulic group\n"
    "0;8;normal;2022-09-01 00:00:00;3;2022-09-14 00:00:00;1900;\n"
)


@pytest.fixture
def adapter() -> CareAdapter:
    return CareAdapter(
        farm_maps={
            "farm_a": {
                "ambient_temp_c": "sensor_0_avg",
                "wind_speed_ms": "wind_speed_3_avg",
                "generator_speed_rpm": "sensor_18_avg",
            }
        },
        farm_directories={"farm_a": "Wind Farm A"},
        farm_scales={"farm_a": {"generator_speed_rpm": 2.0}},
    )


@pytest.fixture
def members(tmp_path: Path, adapter: CareAdapter) -> list[RawMember]:
    with zipfile.ZipFile(tmp_path / "CARE_To_Compare.zip", "w") as handle:
        handle.writestr("CARE_To_Compare/Wind Farm A/datasets/7.csv", DATASET)
        handle.writestr("CARE_To_Compare/Wind Farm A/event_info.csv", EVENT_INFO)
        handle.writestr("CARE_To_Compare/Wind Farm Z/datasets/1.csv", DATASET)
    return adapter.discover(tmp_path)


def _named(members: list[RawMember], fragment: str) -> RawMember:
    return next(member for member in members if fragment in member.name)


def test_a_dataset_is_read_with_its_farm_map_and_scale(
    adapter: CareAdapter, members: list[RawMember]
) -> None:
    frame, account = adapter.load_scada_with_stats(_named(members, "Wind Farm A/datasets/7"))
    assert frame["turbine_id"].unique().tolist() == ["farm_a:asset0:dataset7"]
    assert list(frame["generator_speed_rpm"]) == [1200.0, 1220.0]  # scaled x2
    assert str(frame["timestamp_utc"].dt.tz) == "UTC"
    # the row with no mapped value is dropped and accounted for
    assert (account.stats.rows_raw, account.stats.rows_after_null_drop) == (3, 2)


def test_events_share_the_dataset_id_the_scada_rows_carry(
    adapter: CareAdapter, members: list[RawMember]
) -> None:
    events = adapter.load_events(_named(members, "event_info"))
    assert events is not None
    assert list(events["turbine_id"]) == ["farm_a:asset0:dataset7", "farm_a:asset0:dataset8"]
    assert list(events["category"]) == ["anomaly", "normal"]
    assert events.iloc[0]["message"] == "Hydraulic group"
    assert pd.isna(events.iloc[1]["message"])  # a normal window has no description
    assert events.iloc[0]["start_utc"] == pd.Timestamp("2022-08-04 06:30", tz="UTC")


def test_event_info_may_name_the_turbine_asset_id(tmp_path: Path, adapter: CareAdapter) -> None:
    # Farm A's file says `asset`, as the README does; farms B and C say `asset_id`.
    with zipfile.ZipFile(tmp_path / "CARE_To_Compare.zip", "w") as handle:
        handle.writestr(
            "CARE_To_Compare/Wind Farm A/event_info.csv",
            EVENT_INFO.replace("asset;", "asset_id;", 1),
        )
    events = adapter.load_events(_named(adapter.discover(tmp_path), "event_info"))
    assert events is not None
    assert list(events["turbine_id"]) == ["farm_a:asset0:dataset7", "farm_a:asset0:dataset8"]


def test_event_info_without_a_turbine_column_is_an_error(
    tmp_path: Path, adapter: CareAdapter
) -> None:
    with zipfile.ZipFile(tmp_path / "CARE_To_Compare.zip", "w") as handle:
        handle.writestr(
            "CARE_To_Compare/Wind Farm A/event_info.csv",
            EVENT_INFO.replace("asset;", "turbine;", 1),
        )
    with pytest.raises(RuntimeError, match="asset or asset_id"):
        adapter.load_events(_named(adapter.discover(tmp_path), "event_info"))


def test_a_member_outside_every_mapped_farm_is_an_error(
    adapter: CareAdapter, members: list[RawMember]
) -> None:
    with pytest.raises(RuntimeError, match="none of the farm directories"):
        adapter.load_scada_with_stats(_named(members, "Wind Farm Z"))


def test_the_shipped_map_loads_every_farm_and_the_rad_per_second_scale(repo_root: Path) -> None:
    shipped = CareAdapter.from_configs(repo_root / "configs")
    assert set(shipped.farm_maps) == {"farm_a", "farm_b", "farm_c"}
    assert shipped.farm_directories["farm_c"] == "Wind Farm C"
    assert shipped.farm_scales["farm_c"]["generator_speed_rpm"] == pytest.approx(
        60 / (2 * 3.141592653589793)
    )
    assert shipped.farm_maps["farm_c"]["generator_speed_rpm"] == "sensor_8_avg"
    # CARE power is normalised and has no known factor, so nothing scales it
    assert "power_pu" not in shipped.farm_scales["farm_a"]
