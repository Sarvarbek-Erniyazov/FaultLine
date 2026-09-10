"""The downtime series is streamed in chunks and profiled without being held whole."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from faultline.data.telemetry.adapters.base import RawMember
from faultline.data.telemetry.downtime import (
    profile_downtime,
    read_downtime,
    render_downtime_report,
)

SERIES = (
    "TimeStamp_StartFormat,TurbineName,ShutdownDuration\n"
    "2019-01-01 00:00:00+00:00,T01,0\n"
    "2019-01-01 00:00:00+00:00,T02,600\n"
    "2019-01-01 00:10:00+00:00,T01,120\n"
    "2019-01-01 00:10:00+00:00,T02,600\n"
    "2019-01-01 00:20:00+00:00,T01,0\n"
    # T02 misses 00:20; a 2023 row for the year filter
    "2023-06-01 00:00:00+00:00,T01,30\n"
)


@pytest.fixture
def member(tmp_path: Path) -> RawMember:
    archive = tmp_path / "Hill_of_Towie_ShutdownDuration.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("ShutdownDuration.csv", SERIES)
    size = len(SERIES)
    return RawMember(archive, "ShutdownDuration.csv", "downtime_series", size, size, True)


def test_the_profile_is_the_same_whatever_the_chunk_size(member: RawMember) -> None:
    whole = profile_downtime(member, chunk_rows=1_000)
    streamed = profile_downtime(member, chunk_rows=2)
    assert streamed.chunks == 3 and whole.chunks == 1
    for profile in (whole, streamed):
        assert profile.rows == 6
        assert profile.columns == ["TimeStamp_StartFormat", "TurbineName", "ShutdownDuration"]
        assert profile.values == {600.0: 2, 120.0: 1, 30.0: 1}
        assert profile.off_grid == 0
        t01 = profile.per_turbine["T01"]
        assert (t01.rows, t01.nonzero, t01.full_step) == (4, 2, 0)
        assert profile.per_turbine["T02"].full_step == 2


def test_the_report_carries_schema_coverage_and_distribution(member: RawMember) -> None:
    report = render_downtime_report(profile_downtime(member, chunk_rows=2), Path("."))
    assert "| rows | 6 |" in report
    assert "| 600 s (the whole step) | 2 | 50.00% |" in report
    assert "the 200 MB inspection cap was not raised" in report
    # T02: two rows over the three steps from its first to its last timestamp
    assert "| T02 | 2 |" in report


def test_read_downtime_keeps_only_the_years_asked_for(member: RawMember) -> None:
    frame = read_downtime(member, years=[2019])
    assert len(frame) == 5
    assert str(frame["timestamp_utc"].dt.tz) == "UTC"
    assert frame.iloc[0]["timestamp_utc"] == pd.Timestamp("2019-01-01", tz="UTC")
    assert len(read_downtime(member)) == 6
