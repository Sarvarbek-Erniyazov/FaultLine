"""The Hill of Towie daily summary reader, on a synthetic month."""

from __future__ import annotations

import zipfile
from pathlib import Path

from faultline.data.telemetry.adapters.hill_of_towie import HillOfTowieAdapter

STATIONS = "Turbine Name,Station ID\nT01,2304510\nT02,2304511\n"

DAILY = (
    "TimeStamp,StationId,OutCmdHours,OutTurHours\n"
    "2019-03-01 00:00:00,2304510,1.5,0\n"
    "2019-03-01 00:00:00,2304511,0,0.25\n"
    # a grid station, not a turbine: not in the metadata, so dropped
    "2019-03-01 00:00:00,91,,\n"
    "2019-03-02 00:00:00,2304510,0,0\n"
)


def test_the_daily_summary_is_read_per_turbine_and_day(tmp_path: Path) -> None:
    (tmp_path / "Hill_of_Towie_turbine_metadata.csv").write_text(STATIONS, encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "2019.zip", "w") as handle:
        handle.writestr("tblDailySummary_2019_03.csv", DAILY)
        # a year not asked for
        handle.writestr("tblDailySummary_2018_12.csv", DAILY.replace("2019-03", "2018-12"))
    adapter = HillOfTowieAdapter(channel_map={})
    daily = adapter.read_daily_summary(
        adapter.discover(tmp_path), {2019}, ["OutCmdHours", "OutTurHours", "OutGrdHours"]
    )
    assert daily["turbine_id"].tolist() == ["T01", "T01", "T02"]
    assert daily["day"].dt.day.tolist() == [1, 2, 1]
    assert daily["OutCmdHours"].tolist() == [1.5, 0.0, 0.0]
    assert daily["OutTurHours"].tolist() == [0.0, 0.0, 0.25]
    # a column the export does not carry is left out, not invented
    assert "OutGrdHours" not in daily.columns
