"""Hill of Towie's stop-class timers, read like every other 10-minute table."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from faultline.data.telemetry.adapters.hill_of_towie import HillOfTowieAdapter

STATIONS = "Turbine Name,Station ID\nT01,2304510\nT02,2304511\n"
HEADER = "TimeStamp,StationId,wtc_ScTurSto_timeon,wtc_ScEnvSto_timeon,wtc_OpCode_endvalue\n"
FIELDS = ["wtc_ScTurSto_timeon", "wtc_ScEnvSto_timeon"]


def stage(tmp_path: Path, april_boundary: str) -> HillOfTowieAdapter:
    (tmp_path / "Hill_of_Towie_turbine_metadata.csv").write_text(STATIONS, encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "2019.zip", "w") as handle:
        handle.writestr(
            "tblSCTurFlag_2019_03.csv",
            HEADER
            + "2019-03-31 23:50:00,2304510,600,0,x\n"
            + "2019-04-01 00:00:00,2304510,0,120,x\n",
        )
        handle.writestr(
            "tblSCTurFlag_2019_04.csv",
            HEADER + april_boundary + "2019-04-01 00:10:00,2304511,30,0,x\n",
        )
    return HillOfTowieAdapter()


def test_timers_move_to_interval_start_and_a_boundary_copy_is_dropped(tmp_path: Path) -> None:
    adapter = stage(tmp_path, "2019-04-01 00:00:00,2304510,0,120,x\n")
    frame = adapter.read_stop_classes(adapter.discover(tmp_path), [2019], "tblSCTurFlag", FIELDS)
    assert list(frame.columns) == ["turbine_id", "timestamp_utc", *FIELDS]
    assert list(frame["turbine_id"]) == ["T01", "T01", "T02"]
    assert list(frame["timestamp_utc"]) == list(
        pd.to_datetime(["2019-03-31 23:40", "2019-03-31 23:50", "2019-04-01 00:00"], utc=True)
    )
    assert frame["wtc_ScEnvSto_timeon"].tolist() == [0, 120, 0]


def test_years_not_asked_for_are_not_read(tmp_path: Path) -> None:
    adapter = stage(tmp_path, "")
    frame = adapter.read_stop_classes(adapter.discover(tmp_path), [2023], "tblSCTurFlag", FIELDS)
    assert frame.empty


def test_a_boundary_label_with_two_different_values_stops_the_read(tmp_path: Path) -> None:
    adapter = stage(tmp_path, "2019-04-01 00:00:00,2304510,600,0,x\n")
    with pytest.raises(RuntimeError, match="two different sets"):
        adapter.read_stop_classes(adapter.discover(tmp_path), [2019], "tblSCTurFlag", FIELDS)
