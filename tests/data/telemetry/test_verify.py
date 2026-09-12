"""The step-9 verification checks, on synthetic tables."""

from __future__ import annotations

import json
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from faultline.data.common.splits import SplitsConfig
from faultline.data.telemetry.labels import STEPS_PER_YEAR
from faultline.data.telemetry.pipeline import stage_source_dir
from faultline.data.telemetry.verify import (
    CareProbe,
    SiteYears,
    YearRow,
    _care_section,
    channel_gaps,
    compare_event_sets,
    daily_agreement,
    duration_shares,
    export_column_sets,
    onset_profile,
    opening_messages,
    profile_timers,
    split_of_year,
    timer_runs,
)
from faultline.paths import ProjectPaths

T0 = pd.Timestamp("2019-03-04 08:00", tz="UTC")  # a Monday
STEP = pd.Timedelta(minutes=10)
TIMER = "wtc_ScComSto_timeon"
SPLITS = SplitsConfig.model_validate(
    {
        "site_column": "source",
        "holdout_sites": ["hill_of_towie"],
        "eval_only_sources": ["care"],
        "time": {"train_until": "2020-12-31T23:59:59Z", "val_until": "2021-12-31T23:59:59Z"},
    }
)


# -- (a) stop classes ---------------------------------------------------------------------


def test_a_run_ends_at_a_zero_step_at_a_missing_step_and_at_another_turbine() -> None:
    frame = pd.DataFrame(
        {
            "turbine_id": ["T01"] * 6 + ["T02"],
            "timestamp_utc": [T0 + STEP * i for i in (0, 1, 2, 3, 5, 6)] + [T0 + STEP * 7],
            TIMER: [600.0, 300.0, 0.0, 120.0, 600.0, 60.0, 600.0],
        }
    )
    runs = timer_runs(frame, TIMER)
    # steps 0-1; step 3 alone, because step 4 is missing; steps 5-6; and T02 on its own
    assert runs["steps"].tolist() == [2, 1, 2, 1]
    assert runs["seconds"].tolist() == [900.0, 120.0, 660.0, 600.0]
    assert runs["start_utc"].iloc[1] == T0 + STEP * 3
    assert runs["turbine_id"].tolist() == ["T01", "T01", "T01", "T02"]


def test_onsets_are_placed_in_the_week_and_the_day() -> None:
    starts = [T0 + pd.Timedelta(hours=h) for h in (0, 1, 2)]  # Monday, 08:00 to 10:00
    starts.append(pd.Timestamp("2019-03-09 23:00", tz="UTC"))  # Saturday night
    profile = onset_profile(pd.Series(starts))
    assert profile.runs == 4
    assert profile.working_hours == 0.75
    assert profile.weekend == 0.25
    assert profile.weekday[0] == 0.75
    assert profile.weekday[5] == 0.25
    assert profile.peak_hour == 8


def test_every_run_falls_in_one_duration_bucket() -> None:
    shares = duration_shares(np.array([30.0, 300.0, 1200.0, 7200.0, 30000.0, 100000.0]))
    assert shares == pytest.approx((1 / 6,) * 6)


def test_a_farm_wide_timer_and_a_single_turbine_timer_profile_apart() -> None:
    state = pd.DataFrame(
        {
            "turbine_id": ["T01", "T02", "T03", "T04"],
            "timestamp_utc": [T0] * 4,
            "grd": [600.0] * 4,
            "cmd": [600.0, 0.0, 0.0, 0.0],
            "telemetry_present": [False, True, True, True],
            "power_pu": [0.0] * 4,
            "rotor_speed_rpm": [0.0, 5.0, 0.0, 0.0],
        }
    )
    grid, command = profile_timers(state, {"grd": "grid", "cmd": "planned"}, turbines=4)
    assert (grid.turbines_at_once, grid.farm_wide) == (4.0, 1.0)
    assert (command.turbines_at_once, command.farm_wide) == (1.0, 0.0)
    assert command.telemetry_missing == 1.0
    assert grid.telemetry_missing == 0.25
    assert grid.rotating == 0.25
    assert (grid.onset.runs, command.onset.runs) == (4, 1)


def test_the_daily_summary_is_matched_by_values_not_by_names() -> None:
    day = T0.floor("D")
    state = pd.DataFrame(
        {
            "turbine_id": "T01",
            "timestamp_utc": [day + STEP * i for i in range(144)],
            "a": np.where(np.arange(144) < 6, 600.0, 0.0),  # one hour
            "b": np.where(np.arange(144) == 0, 60.0, 0.0),  # one minute
        }
    )
    daily = pd.DataFrame({"turbine_id": ["T01"], "day": [day], "OutX": [1.0], "OutY": [1 / 60]})
    agreement, days = daily_agreement(state, daily, ["a", "b"], ["OutX", "OutY"])
    assert days == 1
    assert agreement.loc["a", "OutX"] == 1.0
    assert agreement.loc["a", "OutY"] == 0.0
    assert agreement.loc["b", "OutY"] == 1.0
    assert agreement.loc["b", "OutX"] == 0.0


def test_reclassified_events_are_unchanged_extended_or_added() -> None:
    def event(turbine: str, start: int, end: int) -> dict[str, object]:
        return {"turbine_id": turbine, "start_utc": T0 + STEP * start, "end_utc": T0 + STEP * end}

    now = pd.DataFrame([event("T01", 0, 2), event("T01", 10, 11), event("T02", 0, 1)])
    then = pd.DataFrame(
        [event("T01", 0, 2), event("T01", 8, 11), event("T02", 0, 1), event("T02", 20, 22)]
    )
    assert compare_event_sets(now, then) == (2, 1, 1)


# -- (b) the late period ----------------------------------------------------------------


def test_the_message_opening_an_event_is_the_stop_row_in_its_first_step() -> None:
    minute = pd.Timedelta(minutes=1)
    stream = pd.DataFrame(
        {
            "turbine_id": ["T01"] * 4,
            "start_utc": [T0 + minute, T0 + 3 * minute, T0 + 5 * minute, T0 + 48 * minute],
            "message": ["a warning", "anemometer defect", "frequency converter error", "safety"],
            "provider_status": ["Warning", "Stop", "Stop", "Stop"],
            "cause": ["unknown", "technical", "technical", "technical"],
        }
    )
    events = pd.DataFrame({"turbine_id": ["T01", "T01"], "start_utc": [T0, T0 + STEP * 5]})
    opened = opening_messages(events, stream, "technical", "Stop")
    # the second event starts at 08:50: no stop row starts in its step, one runs into it
    assert opened.tolist() == ["anemometer defect", "safety"]


def test_an_export_column_set_is_read_from_each_file_header() -> None:
    def row(year: int, keys: list[str]) -> dict[str, object]:
        return {
            "turbine_id": "T01",
            "start_utc": pd.Timestamp(f"{year}-06-01", tz="UTC"),
            "raw": json.dumps(dict.fromkeys(keys, 1)),
        }

    events = pd.DataFrame(
        [
            row(2019, ["Code", "Message"]),
            row(2020, ["Code", "Message"]),
            row(2021, ["Code", "Custom", "Message"]),
        ]
    )
    assert export_column_sets(events) == [
        (("Code", "Message"), [2019, 2020]),
        (("Code", "Custom", "Message"), [2021]),
    ]


def test_a_year_takes_the_split_of_its_steps() -> None:
    assert split_of_year(2019, "kelmarsh", "Kelmarsh", SPLITS) == "train"
    assert split_of_year(2021, "kelmarsh", "Kelmarsh", SPLITS) == "val"
    assert split_of_year(2023, "kelmarsh", "Kelmarsh", SPLITS) == "test"
    assert split_of_year(2019, "hill_of_towie", "Hill of Towie", SPLITS) == "test"


def test_the_onset_is_the_first_later_year_whose_interval_clears_the_training_rate() -> None:
    year = int(STEPS_PER_YEAR)
    rows = [
        YearRow(2019, "train", year, 10, 100, "T1", 3, 0),
        YearRow(2020, "train", year, 10, 100, "T1", 3, 0),
        YearRow(2021, "val", year, 12, 100, "T1", 3, 0),  # above the rate, not clearly
        YearRow(2022, "test", year, 40, 100, "T1", 30, 0),
    ]
    site = SiteYears("kelmarsh", rows)
    assert site.pooled("train") == (20, 2 * year)
    assert site.onset == 2022


# -- (c) channel gaps --------------------------------------------------------------------


def test_a_channel_missing_while_the_turbine_reports_is_a_gap(repo_paths: ProjectPaths) -> None:
    source = "penmanshiel"
    cleaned = stage_source_dir(repo_paths, "cleaned", source)
    (cleaned / "labels").mkdir(parents=True, exist_ok=True)
    stamps = pd.date_range("2017-01-01", periods=200, freq="10min", tz="UTC")
    pitch = np.where(np.arange(200) < 100, np.nan, 1.0)
    wind = np.where(np.arange(200) < 150, 7.0, np.nan)
    pd.DataFrame(
        {
            "source": source,
            "site": "Penmanshiel",
            "turbine_id": "P01",
            "timestamp_utc": stamps,
            "wind_speed_ms": wind,
            "pitch_angle_deg": pitch,
        }
    ).to_parquet(cleaned / "P01__2017.parquet", index=False)
    label = pd.array([True] * 20 + [False] * 180, dtype="boolean")
    pd.DataFrame({"timestamp_utc": stamps, "narrow_within_24h": label}).to_parquet(
        cleaned / "labels" / "P01__2017.parquet", index=False
    )
    pd.DataFrame(
        {
            "turbine_id": ["P01", "P01"],
            "start_utc": [stamps[10], stamps[199] + pd.Timedelta(days=1)],
            "in_grid": [True, False],
        }
    ).to_parquet(cleaned / "labels" / "events_narrow.parquet", index=False)

    (row,) = channel_gaps(
        repo_paths,
        source,
        ["wind_speed_ms", "pitch_angle_deg"],
        ["pitch_angle_deg"],
        SPLITS,
        "narrow_within_24h",
    )
    assert row.split == "train"
    assert row.reporting == 150
    assert row.missing["pitch_angle_deg"] == pytest.approx(100 / 150)
    assert row.missing["wind_speed_ms"] == 0.0
    assert row.affected(["pitch_angle_deg"])
    assert not row.affected(["wind_speed_ms"])
    assert row.narrow == 1
    assert (row.known_missing, row.positive_missing) == (100, 20)
    assert (row.known_present, row.positive_present) == (50, 0)


# -- (d) CARE ------------------------------------------------------------------------------


def test_care_is_reported_per_dataset_with_the_interval_its_counts_allow() -> None:
    probe = CareProbe(
        source="care",
        datasets={
            "farm_a": Counter({"anomaly": 12, "normal": 10}),
            "farm_b": Counter({"anomaly": 6, "normal": 9}),
        },
        steps={"farm_a": 1000, "farm_b": 500},
        presence={"farm_a": {"power_pu": 1.0}, "farm_b": {"power_pu": 0.5}},
        power_bound=(-0.1, 1.1),
        absolute_time=False,
    )
    text = _care_section(probe, ["power_pu"])
    assert "dataset-level generalisation probe" in text
    assert "| anomalous, all farms | 18 |" in text
    assert "| anomalous, without farm A (ADR-0004) | 6 |" in text
    assert "anonymised by the provider" in text
    assert "per unit" in text
