"""Event labels: status categories, downtime runs, the Stopping cross-check, horizons."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from faultline.config import load_config
from faultline.data.common.stage import run_pipeline
from faultline.data.telemetry.events import EventConfig
from faultline.data.telemetry.labels import (
    UNMAPPED,
    EventLabelsConfig,
    StatusStringsConfig,
    categorize_status_events,
    downtime_events,
    horizon_name,
    label_turbine_year,
    stopping_cross_check,
)
from faultline.data.telemetry.pipeline import (
    build_stages,
    ingest_dir,
    load_telemetry_config,
    stage_source_dir,
)
from faultline.paths import ProjectPaths
from faultline.runs import start_run

T0 = pd.Timestamp("2020-01-01", tz="UTC")
STEP = pd.Timedelta(minutes=10)


def rule(**overrides: object) -> StatusStringsConfig:
    payload: dict[str, object] = {
        "sources": ["kelmarsh"],
        "fault_categories": ["equipment_fault"],
        "categories": {
            "normal_operation": ["System OK"],
            "equipment_fault": ["Anemometer defect"],
        },
    }
    payload.update(overrides)
    return StatusStringsConfig.model_validate(payload)


def status_events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": "kelmarsh",
            "site": "Kelmarsh",
            "turbine_id": "Kelmarsh 1",
            "start_utc": [T0, T0 + STEP * 3, T0 + STEP * 9],
            "end_utc": [pd.NaT] * 3,
            "code": ["0", "6530", "9999"],
            "message": ["system ok", "anemometer defect", "something new"],
            "category": ["Informational", "Stop", "Stop"],
            "is_fault": [None, None, None],
            "raw": [
                '{"IEC category":"Full Performance","Status":"Informational"}',
                '{"IEC category":"Forced outage","Status":"Stop"}',
                '{"IEC category":"Forced outage","Status":"Stop"}',
            ],
        }
    )


# -- configuration ----------------------------------------------------------------------


def test_the_shipped_labels_config_loads(repo_root: Path) -> None:
    cfg = load_config(repo_root / "configs" / "data" / "events_v1.yaml", EventLabelsConfig)
    assert cfg.status_strings.fault_categories == ["equipment_fault"]
    assert cfg.downtime.threshold_s == 300
    assert "Anemometer defect" in cfg.status_strings.categories["equipment_fault"]


def test_a_string_in_two_categories_is_rejected() -> None:
    with pytest.raises(ValidationError, match="listed under both"):
        rule(categories={"a": ["System OK"], "equipment_fault": ["system  ok"]})


def test_a_fault_category_must_be_defined() -> None:
    with pytest.raises(ValidationError, match="undefined categories"):
        rule(fault_categories=["nowhere"])


# -- status strings -----------------------------------------------------------------------


def test_is_fault_follows_the_category_and_unmapped_stays_unknown() -> None:
    events = categorize_status_events(status_events(), rule(), EventConfig())
    assert list(events["category"]) == ["normal_operation", "equipment_fault", UNMAPPED]
    assert events["is_fault"].tolist()[:2] == [False, True]
    assert pd.isna(events["is_fault"].iloc[2])  # unknown, never benign
    assert list(events["provider_status"]) == ["Informational", "Stop", "Stop"]
    assert list(events["provider_iec"])[1] == "Forced outage"


# -- downtime ------------------------------------------------------------------------------


def downtime(values: list[float], turbine: str = "T01", start: pd.Timestamp = T0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp_utc": [start + STEP * i for i in range(len(values))],
            "turbine_id": turbine,
            "downtime_s": values,
        }
    )


def test_a_run_of_down_steps_is_one_event() -> None:
    series = downtime([0, 600, 600, 120, 0, 600, 0])
    events = downtime_events(series, 300, "hill_of_towie", "Hill of Towie")
    assert list(events["start_utc"]) == [T0 + STEP, T0 + STEP * 5]
    assert list(events["end_utc"]) == [T0 + STEP * 3, T0 + STEP * 6]
    assert events["is_fault"].all()
    # a lower threshold joins the 120 s step to the first run
    assert len(downtime_events(series, 60, "h", "H")) == 2
    assert downtime_events(series, 60, "h", "H")["end_utc"].iloc[0] == T0 + STEP * 4


def test_a_missing_step_ends_a_run_and_turbines_never_merge() -> None:
    gap = downtime([600, 600]).drop(index=1)
    later = downtime([600], start=T0 + STEP * 2)
    other = downtime([600, 600], turbine="T02")
    events = downtime_events(pd.concat([gap, later, other]), 300, "h", "H")
    assert len(events) == 3


def test_the_stopping_cross_check_counts_agreement_per_code() -> None:
    series = pd.concat([downtime([0, 0, 600, 600, 0, 0]), downtime([0] * 6, turbine="T02")])
    alarms = pd.DataFrame(
        {
            "turbine_id": ["T01", "T02", "T01", "T02"],
            "code": ["10105", "10105", "25", "25"],
            "start_utc": [
                T0 + STEP * 2 + pd.Timedelta(seconds=30),  # stopping, downtime follows
                T0 + STEP * 2,  # stopping, no downtime at T02
                T0 + STEP * 5,  # non-stopping, nothing down
                T0 + STEP,  # non-stopping, nothing down at T02
            ],
            "end_utc": [T0 + STEP * 3, T0 + STEP * 3, pd.NaT, pd.NaT],
        }
    )
    check = stopping_cross_check(alarms, series, {"10105": True, "25": False}, 300, 1)
    by_code = check.set_index("code")
    assert by_code.loc["10105", "agreeing"] == 1
    assert by_code.loc["25", "agreeing"] == 2
    assert by_code.loc["10105", "agreement"] == 0.5


# -- horizons -------------------------------------------------------------------------------


def test_horizon_columns_are_named_in_hours() -> None:
    assert [horizon_name(s) for s in (6, 36, 144)] == [
        "event_within_1h",
        "event_within_6h",
        "event_within_24h",
    ]


def test_each_step_is_labelled_for_every_horizon() -> None:
    grid = pd.DataFrame(
        {
            "source": "kelmarsh",
            "turbine_id": "T1",
            "timestamp_utc": [T0 + STEP * i for i in range(12)],
            "power_pu": [1.0] * 11 + [np.nan],
        }
    )
    events = pd.DataFrame({"start_utc": [T0 + STEP * 10], "is_fault": [True]})
    labels = label_turbine_year(grid, events, [1, 6], EventConfig(), ["power_pu"])
    assert labels["event_within_10min"].tolist() == [False] * 9 + [True, False, False]
    assert labels["event_within_1h"].tolist() == [False] * 4 + [True] * 6 + [False, False]
    assert labels["has_data"].sum() == 11


def test_the_label_stage_labels_a_cleaned_grid(repo_root: Path, repo_paths: ProjectPaths) -> None:
    grid = pd.DataFrame(
        {
            "source": "kelmarsh",
            "site": "Kelmarsh",
            "turbine_id": "Kelmarsh 1",
            "timestamp_utc": [T0 + STEP * i for i in range(300)],
            "power_pu": np.linspace(0, 2000, 300),
        }
    )
    grid.to_parquet(
        stage_source_dir(repo_paths, "cleaned", "kelmarsh") / "Kelmarsh_1__2020.parquet"
    )
    events = status_events()
    events["message"] = ["System OK", "Anemometer defect", "Something new"]
    events.to_parquet(ingest_dir(repo_paths, "kelmarsh") / "events.parquet")

    v1 = repo_root / "configs" / "data" / "telemetry_v1.yaml"
    config = load_telemetry_config(v1)
    stages = build_stages(config, repo_paths, "label", source="kelmarsh")
    with start_run(v1, config, "label", "telemetry", repo_paths) as ctx:
        result = run_pipeline(stages, ctx)[0]
        report = (ctx.run_dir / "label_stats_report.md").read_text(encoding="utf-8")
        assert (ctx.run_dir / "events_v1.yaml").is_file()

    site = result.details["sites"]["kelmarsh"]
    assert site.fault_events == 1
    assert site.steps == 300
    # the anemometer defect starts at step 3: six steps see it within an hour
    assert site.positives["event_within_1h"] == 3  # steps 0, 1, 2
    assert site.extra["status"]["unmapped_rows"] == 1
    assert "Positive base rate per site and horizon" in report
    labels = pd.read_parquet(
        stage_source_dir(repo_paths, "cleaned", "kelmarsh") / "labels" / "Kelmarsh_1__2020.parquet"
    )
    assert {"event_within_1h", "event_within_6h", "event_within_24h"} <= set(labels.columns)
