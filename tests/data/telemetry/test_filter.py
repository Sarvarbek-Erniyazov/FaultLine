"""Coverage thresholds and gap segmentation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from faultline.data.telemetry.filter import (
    TelemetryFilterConfig,
    channel_coverage,
    drop_short_segments,
    segment_ids,
    segment_lengths,
    select_channels,
    turbine_year_coverage,
)

CHANNELS = ["wind_speed_ms", "power_kw", "gearbox_oil_temp_c"]


def gridded(rows: int = 100) -> pd.DataFrame:
    stamps = pd.date_range("2020-01-01", periods=rows, freq="10min", tz="UTC")
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "timestamp_utc": stamps,
            "wind_speed_ms": rng.uniform(3, 15, rows),
            "power_kw": rng.uniform(0, 2000, rows),
            "gearbox_oil_temp_c": np.nan,
        }
    )


def test_channel_coverage() -> None:
    frame = gridded(10)
    frame.loc[0:4, "power_kw"] = np.nan
    coverage = channel_coverage(frame, CHANNELS)
    assert coverage["wind_speed_ms"] == 1.0
    assert coverage["power_kw"] == 0.5
    assert coverage["gearbox_oil_temp_c"] == 0.0


def test_absent_channel_reports_zero_coverage() -> None:
    assert channel_coverage(gridded(4), ["absent_channel"])["absent_channel"] == 0.0


def test_empty_frame_coverage() -> None:
    assert channel_coverage(gridded(0), CHANNELS) == dict.fromkeys(CHANNELS, 0.0)


def test_select_channels_drops_sparse_ones() -> None:
    frame = gridded(10)
    frame.loc[0:6, "power_kw"] = np.nan
    kept, coverage = select_channels(frame, CHANNELS, TelemetryFilterConfig())
    assert kept == ["wind_speed_ms"]
    assert coverage["power_kw"] < 0.5


def test_turbine_year_coverage_is_the_mean() -> None:
    frame = gridded(10)
    frame.loc[0:4, "power_kw"] = np.nan
    assert turbine_year_coverage(frame, CHANNELS) == (1.0 + 0.5 + 0.0) / 3


def test_segments_split_on_long_gaps() -> None:
    frame = gridded(40)
    # a gap of 10 steps (100 minutes) exceeds the 6-step break threshold
    frame.loc[10:19, ["wind_speed_ms", "power_kw"]] = np.nan
    config = TelemetryFilterConfig(segment_break_steps=6, min_segment_steps=1)
    ids = segment_ids(frame, ["wind_speed_ms", "power_kw"], config)
    assert set(ids[ids >= 0]) == {0, 1}
    assert (ids == -1).sum() == 10
    lengths = segment_lengths(ids)
    assert lengths == {0: 10, 1: 20}


def test_short_gaps_do_not_split_a_segment() -> None:
    frame = gridded(30)
    frame.loc[10:12, ["wind_speed_ms", "power_kw"]] = np.nan  # 3 steps, under the threshold
    config = TelemetryFilterConfig(segment_break_steps=6, min_segment_steps=1)
    ids = segment_ids(frame, ["wind_speed_ms", "power_kw"], config)
    assert set(ids[ids >= 0]) == {0}


def test_empty_frame_segments() -> None:
    ids = segment_ids(gridded(0), CHANNELS, TelemetryFilterConfig())
    assert ids.empty


def test_drop_short_segments() -> None:
    frame = gridded(40)
    frame.loc[10:19, ["wind_speed_ms", "power_kw"]] = np.nan
    config = TelemetryFilterConfig(segment_break_steps=6, min_segment_steps=15)
    ids = segment_ids(frame, ["wind_speed_ms", "power_kw"], config)
    filtered, counters = drop_short_segments(frame, ids, config)

    assert counters["segments_total"] == 2
    assert counters["segments_kept"] == 1
    assert counters["segments_dropped_short"] == 1
    assert len(filtered) == 20
    assert set(filtered["segment_id"]) == {1}
