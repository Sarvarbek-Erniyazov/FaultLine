"""Telemetry cleaning on synthetic turbine data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from faultline.data.telemetry.clean import (
    BoundSpec,
    TelemetryCleanConfig,
    apply_bounds,
    clean_turbine_frame,
    parse_timestamps,
    reindex_to_grid,
    resolve_duplicate_timestamps,
)

CHANNELS = ["wind_speed_ms", "power_kw"]


def synthetic(rows: int = 12, freq: str = "10min", naive: bool = True) -> pd.DataFrame:
    stamps = pd.date_range("2020-01-01 00:00", periods=rows, freq=freq)
    if not naive:
        stamps = stamps.tz_localize("UTC")
    rng = np.random.default_rng(20260909)
    return pd.DataFrame(
        {
            "source": "kelmarsh",
            "site": "Kelmarsh",
            "turbine_id": "T1",
            "timestamp_utc": stamps,
            "wind_speed_ms": rng.uniform(3, 15, rows),
            "power_kw": rng.uniform(0, 2000, rows),
        }
    )


def test_parse_timestamps_localizes_naive_input() -> None:
    frame, dropped = parse_timestamps(synthetic())
    assert dropped == 0
    assert str(frame["timestamp_utc"].dt.tz) == "UTC"


def test_parse_timestamps_drops_unparseable_rows() -> None:
    frame = synthetic(4)
    frame["timestamp_utc"] = frame["timestamp_utc"].astype(str)
    frame.loc[1, "timestamp_utc"] = "not a timestamp"
    parsed, dropped = parse_timestamps(frame)
    assert dropped == 1
    assert len(parsed) == 3


def test_parse_timestamps_requires_the_column() -> None:
    with pytest.raises(KeyError):
        parse_timestamps(pd.DataFrame({"a": [1]}))


def test_duplicate_timestamps_mean() -> None:
    frame = synthetic(3, naive=False)
    duplicated = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    duplicated.loc[3, "power_kw"] = 0.0
    collapsed, removed = resolve_duplicate_timestamps(duplicated, CHANNELS, "mean")
    assert removed == 1
    assert len(collapsed) == 3
    expected = (frame.loc[0, "power_kw"] + 0.0) / 2
    row = collapsed.loc[collapsed["timestamp_utc"] == frame.loc[0, "timestamp_utc"]]
    assert row["power_kw"].iloc[0] == pytest.approx(expected)
    # identifier columns survive the collapse
    assert row["turbine_id"].iloc[0] == "T1"


def test_duplicate_timestamps_first() -> None:
    frame = synthetic(3, naive=False)
    duplicated = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    duplicated.loc[3, "power_kw"] = -999.0
    collapsed, removed = resolve_duplicate_timestamps(duplicated, CHANNELS, "first")
    assert removed == 1
    assert -999.0 not in set(collapsed["power_kw"])


def test_duplicate_strategy_is_validated() -> None:
    with pytest.raises(ValueError, match="mean or first"):
        resolve_duplicate_timestamps(synthetic(2, naive=False), CHANNELS, "median")


def test_reindex_fills_the_grid() -> None:
    frame = synthetic(6, naive=False)
    gapped = frame.drop(index=[2, 3]).reset_index(drop=True)
    gridded, inserted = reindex_to_grid(gapped)
    assert inserted == 2
    assert len(gridded) == 6
    assert gridded["wind_speed_ms"].isna().sum() == 2
    # identifier columns are carried across the inserted rows
    assert gridded["turbine_id"].notna().all()


def test_bounds_flag_out_of_range_values() -> None:
    frame = synthetic(5, naive=False)
    frame.loc[0, "wind_speed_ms"] = 999.0
    frame.loc[1, "wind_speed_ms"] = -5.0
    bounded, flags = apply_bounds(frame, {"wind_speed_ms": BoundSpec(min=0.0, max=60.0)})
    assert flags["wind_speed_ms"] == 2
    assert bounded["wind_speed_ms"].isna().sum() == 2
    # values are set to NaN, never clipped into a plausible-looking reading
    assert 60.0 not in set(bounded["wind_speed_ms"].dropna())


def test_clean_turbine_frame_end_to_end() -> None:
    frame = synthetic(10)
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    frame.loc[11, "power_kw"] = 99999.0
    frame = frame.drop(index=[5]).reset_index(drop=True)

    cleaned, counts = clean_turbine_frame(
        frame,
        channels=CHANNELS,
        bounds={"power_kw": BoundSpec(min=-100.0, max=2255.0)},
        config=TelemetryCleanConfig(),
    )
    assert counts.duplicate_timestamps == 1
    assert counts.grid_rows_inserted == 1
    assert counts.bounds_flags is not None
    assert counts.rows_out == len(cleaned)
    assert str(cleaned["timestamp_utc"].dt.tz) == "UTC"
    counters = counts.as_counters()
    assert counters["duplicate_timestamps"] == 1
    assert "bounds:power_kw" in counters
