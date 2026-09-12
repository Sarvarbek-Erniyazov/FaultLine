"""Hill of Towie loaders, on a synthetic month shaped like the staged archives.

The shapes are the real ones -- one file per table per month, every turbine in each,
``(TimeStamp, StationId)`` keys, interval-end labels, a four-column alarm log -- but
the values are invented, so nothing here depends on the staged data.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from faultline.data.telemetry.adapters.base import RawMember
from faultline.data.telemetry.adapters.hill_of_towie import HillOfTowieAdapter

CHANNEL_MAP = {
    "wind_speed_ms": "tblSCTurbine.wtc_AcWindSp_mean",
    "wind_direction_deg": "tblSCTurbine.wtc_ActualWindDirection_mean",
    "power_pu": "tblSCTurGrid.wtc_ActPower_mean",
    "ambient_temp_c": "tblSCTurTemp.wtc_AmbieTmp_mean",
}

STATIONS = "Turbine Name,Station ID\nT01,2304510\nT02,2304511\n"

MONTH = {
    # 2019 carries no wind direction, as in the real export.
    "tblSCTurbine_2019_03.csv": (
        "TimeStamp,StationId,wtc_CurTime_endvalue,wtc_AcWindSp_mean\n"
        "2019-03-01 00:10:00,2304510,2019-03-01 00:09:58,9.5\n"
        "2019-03-01 00:10:00,2304511,2019-03-01 00:09:58,8.5\n"
        "2019-03-01 00:20:00,2304510,2019-03-01 00:19:58,9.0\n"
        "2019-03-01 00:20:00,2304511,2019-03-01 00:19:58,8.0\n"
        # a grid station, not a turbine: not in the metadata, so dropped
        "2019-03-01 00:20:00,91,2019-03-01 00:19:58,1.0\n"
    ),
    "tblSCTurGrid_2019_03.csv": (
        "TimeStamp,StationId,wtc_ActPower_mean\n"
        "2019-03-01 00:10:00,2304510,1800\n"
        "2019-03-01 00:10:00,2304511,1500\n"
        "2019-03-01 00:20:00,2304510,1750\n"
        "2019-03-01 00:20:00,2304511,\n"
    ),
    "tblSCTurTemp_2019_03.csv": (
        "TimeStamp,StationId,wtc_AmbieTmp_mean\n"
        "2019-03-01 00:10:00,2304510,4.0\n"
        "2019-03-01 00:10:00,2304511,4.5\n"
        "2019-03-01 00:20:00,2304510,4.1\n"
        "2019-03-01 00:20:00,2304511,4.4\n"
    ),
    # not read by the channel map above, so not part of the unit
    "tblSCTurFlag_2019_03.csv": "TimeStamp,StationId,wtc_ScTurSto_timeon\n",
    "tblAlarmLog_2019_03.csv": (
        "TimeOn,TimeOff,StationNr,Alarmcode\n"
        "2019-03-01 00:04:48,,2304510,127\n"
        "2019-03-01 00:05:10,2019-03-01 00:40:00,2304511,3130.0\n"
    ),
}


@pytest.fixture
def staged(tmp_path: Path) -> tuple[HillOfTowieAdapter, list[RawMember]]:
    (tmp_path / "Hill_of_Towie_turbine_metadata.csv").write_text(STATIONS, encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "2019.zip", "w") as handle:
        for name, content in MONTH.items():
            handle.writestr(name, content)
    with zipfile.ZipFile(tmp_path / "Hill_of_Towie_ShutdownDuration.zip", "w") as handle:
        handle.writestr(
            "ShutdownDuration.csv",
            "TimeStamp_StartFormat,TurbineName,ShutdownDuration\n2019-03-01 00:00:00+00:00,T01,0\n",
        )
    adapter = HillOfTowieAdapter(channel_map=dict(CHANNEL_MAP))
    return adapter, adapter.discover(tmp_path)


def test_a_unit_is_one_month_of_the_mapped_tables(
    staged: tuple[HillOfTowieAdapter, list[RawMember]],
) -> None:
    adapter, members = staged
    units = adapter.scada_units(members)
    assert len(units) == 1
    assert [m.name for m in units[0]] == [
        "tblSCTurGrid_2019_03.csv",
        "tblSCTurTemp_2019_03.csv",
        "tblSCTurbine_2019_03.csv",
    ]


def test_the_month_is_joined_named_and_moved_to_interval_start(
    staged: tuple[HillOfTowieAdapter, list[RawMember]],
) -> None:
    adapter, members = staged
    frame, accounts = adapter.load_scada_unit(adapter.scada_units(members)[0])

    assert sorted(frame["turbine_id"].unique()) == ["T01", "T02"]  # station 91 dropped
    # interval-end label 00:10 names the interval that opened at 00:00
    first = frame[frame["turbine_id"] == "T01"].sort_values("timestamp_utc").iloc[0]
    assert first["timestamp_utc"] == pd.Timestamp("2019-03-01 00:00", tz="UTC")
    assert (first["wind_speed_ms"], first["power_pu"], first["ambient_temp_c"]) == (9.5, 1800, 4.0)
    # the 2019 export has no wind direction: missing data, not a crash
    assert "wind_direction_deg" not in frame.columns
    t02 = frame[frame["turbine_id"] == "T02"].sort_values("timestamp_utc")
    assert t02["power_pu"].isna().tolist() == [False, True]
    assert t02["ambient_temp_c"].notna().all()  # the join keeps the other tables' values

    assert len(accounts) == 3
    grid = next(a for a in accounts if "tblSCTurGrid" in a.member)
    # four (label, station) keys, one of them with no power value
    assert (grid.stats.rows_raw, grid.stats.rows_after_null_drop) == (4, 3)
    assert grid.stats.labels_distinct == 4 and not grid.stats.repeated_export


def test_the_alarm_log_becomes_events_with_codes_and_no_message(
    staged: tuple[HillOfTowieAdapter, list[RawMember]],
) -> None:
    adapter, members = staged
    log = next(m for m in members if m.kind == "alarm_log")
    events = adapter.load_events(log)
    assert events is not None
    assert list(events["code"]) == ["127", "3130"]  # rendered the same however parsed
    assert list(events["turbine_id"]) == ["T01", "T02"]
    assert events["message"].isna().all()
    # instants, not interval labels: nothing is shifted
    assert events.iloc[0]["start_utc"] == pd.Timestamp("2019-03-01 00:04:48", tz="UTC")
    assert pd.isna(events.iloc[0]["end_utc"])


def test_shutdown_duration_is_a_downtime_series_and_not_an_event_log(
    staged: tuple[HillOfTowieAdapter, list[RawMember]],
) -> None:
    adapter, members = staged
    series = [m for m in members if m.name == "ShutdownDuration.csv"]
    assert [m.kind for m in series] == ["downtime_series"]
    assert adapter.load_events(series[0]) is None


def test_a_missing_station_file_is_an_error_not_a_guess(tmp_path: Path) -> None:
    with zipfile.ZipFile(tmp_path / "2019.zip", "w") as handle:
        handle.writestr("tblSCTurGrid_2019_03.csv", MONTH["tblSCTurGrid_2019_03.csv"])
    adapter = HillOfTowieAdapter(channel_map={"power_pu": CHANNEL_MAP["power_pu"]})
    unit = adapter.scada_units(adapter.discover(tmp_path))[0]
    with pytest.raises(RuntimeError, match="station ids cannot be named"):
        adapter.load_scada_unit(unit)
