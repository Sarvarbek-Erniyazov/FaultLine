"""The label stage under the harmonised rule (events_v2.yaml, ADR-0009)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from faultline.config import load_config
from faultline.data.common.stage import StageResult, run_pipeline
from faultline.data.telemetry.labels import EventLabelsConfig, HarmonisedSite
from faultline.data.telemetry.pipeline import (
    TelemetryPipelineConfig,
    build_stages,
    ingest_dir,
    load_telemetry_config,
    stage_source_dir,
)
from faultline.paths import ProjectPaths
from faultline.runs import start_run

T0 = pd.Timestamp("2019-03-01", tz="UTC")
STEP = pd.Timedelta(minutes=10)
S = pd.Timedelta(seconds=1)


def v2_payload(repo_root: Path) -> dict[str, object]:
    payload = yaml.safe_load(
        (repo_root / "configs" / "data" / "events_v2.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(payload, dict)
    return payload


def config_with_v2(repo_root: Path) -> tuple[Path, TelemetryPipelineConfig]:
    v1 = repo_root / "configs" / "data" / "telemetry_v1.yaml"
    config = load_telemetry_config(v1)
    config = config.model_copy(
        update={
            "events": config.events.model_copy(
                update={"labels_config": "configs/data/events_v2.yaml"}
            )
        }
    )
    return v1, config


def run_label(
    repo_root: Path, paths: ProjectPaths, source: str
) -> tuple[StageResult, HarmonisedSite, str]:
    path, config = config_with_v2(repo_root)
    stages = build_stages(config, paths, "label", source=source)
    with start_run(path, config, "label", "telemetry", paths) as ctx:
        result = run_pipeline(stages, ctx)[0]
        report = (ctx.run_dir / "label_stats_report.md").read_text(encoding="utf-8")
    return result, result.details["sites"][source], report


# -- configuration ---------------------------------------------------------------------


def test_the_shipped_v2_file_loads(repo_root: Path) -> None:
    cfg = load_config(repo_root / "configs" / "data" / "events_v2.yaml", EventLabelsConfig)
    assert cfg.harmonised is not None
    assert cfg.harmonised.narrow_causes == ["technical"]
    assert cfg.harmonised.min_duration_s == 60
    assert cfg.harmonised.durations == [60, 300, 600]
    assert cfg.harmonised.code_causes["3130"] == "planned"
    assert cfg.harmonised.stop_classes.fields["wtc_ScTurSto_timeon"] == "technical"
    assert not cfg.harmonised.wind_envelope.apply


def test_the_v2_status_table_is_the_v1_table_string_for_string(repo_root: Path) -> None:
    v1 = load_config(repo_root / "configs" / "data" / "events_v1.yaml", EventLabelsConfig)
    v2 = load_config(repo_root / "configs" / "data" / "events_v2.yaml", EventLabelsConfig)
    assert v1.status_strings == v2.status_strings


def test_version_2_requires_the_harmonised_rule(repo_root: Path) -> None:
    payload = v2_payload(repo_root)
    payload.pop("harmonised")
    with pytest.raises(ValidationError, match="must define `harmonised`"):
        EventLabelsConfig.model_validate(payload)


def test_every_category_needs_a_cause(repo_root: Path) -> None:
    payload = v2_payload(repo_root)
    harmonised = payload["harmonised"]
    assert isinstance(harmonised, dict)
    harmonised["category_causes"].pop("equipment_fault")
    with pytest.raises(ValidationError, match="no cause for"):
        EventLabelsConfig.model_validate(payload)


def test_the_cross_check_threshold_cannot_drift_from_the_rule(repo_root: Path) -> None:
    payload = v2_payload(repo_root)
    downtime = payload["downtime"]
    assert isinstance(downtime, dict)
    downtime["threshold_s"] = 300
    with pytest.raises(ValidationError, match="cannot drift"):
        EventLabelsConfig.model_validate(payload)


# -- a training site ---------------------------------------------------------------------


def status_row(
    start: pd.Timestamp, end: pd.Timestamp, message: str, status: str
) -> dict[str, object]:
    return {
        "source": "kelmarsh",
        "site": "Kelmarsh",
        "turbine_id": "Kelmarsh 1",
        "start_utc": start,
        "end_utc": end,
        "code": "0",
        "message": message.lower(),
        "category": status,
        "is_fault": None,
        # compact, as ingest preserves the provider row (greenbyte._raw_row)
        "raw": json.dumps(
            {"Status": status, "IEC category": "Forced outage"}, separators=(",", ":")
        ),
    }


def test_a_training_site_counts_episodes_and_keeps_warnings_out_of_the_target(
    repo_root: Path, repo_paths: ProjectPaths
) -> None:
    grid = pd.DataFrame(
        {
            "source": "kelmarsh",
            "site": "Kelmarsh",
            "turbine_id": "Kelmarsh 1",
            "timestamp_utc": [T0 + STEP * i for i in range(300)],
            "wind_speed_ms": 8.0,
        }
    )
    grid.to_parquet(
        stage_source_dir(repo_paths, "cleaned", "kelmarsh") / "Kelmarsh_1__2019.parquet"
    )
    fault = T0 + 3 * STEP
    events = pd.DataFrame(
        [
            status_row(T0, T0 + 30 * S, "System OK", "Informational"),
            # one converter fault written as two overlapping rows: one episode
            status_row(fault, fault + 120 * S, "Frequency converter not ready", "Stop"),
            status_row(fault + 30 * S, fault + 300 * S, "Frequency converter error", "Stop"),
            # a warning: an input, never a target
            status_row(T0 + 10 * STEP, T0 + 20 * STEP, "Overload generator fan 1", "Warning"),
            status_row(T0 + 30 * STEP, T0 + 33 * STEP, "Manual stop - remote", "Stop"),
        ]
    )
    events.to_parquet(ingest_dir(repo_paths, "kelmarsh") / "events.parquet")

    result, site, report = run_label(repo_root, repo_paths, "kelmarsh")

    assert site.events == {"narrow": 1, "broad": 2}
    assert site.rows["any"] == 2  # gate 1 would have counted two faults
    assert site.causes == {"technical": 1, "planned": 1}
    labels_dir = stage_source_dir(repo_paths, "cleaned", "kelmarsh") / "labels"
    narrow = pd.read_parquet(labels_dir / "events_narrow.parquet")
    broad = pd.read_parquet(labels_dir / "events_broad.parquet")
    assert list(narrow["start_utc"]) == [fault]
    assert (T0 + 10 * STEP) not in set(broad["start_utc"])
    stream = pd.read_parquet(labels_dir / "status_stream.parquet")
    assert "Warning" in set(stream["provider_status"])
    assert len(stream) == len(events)

    labels = pd.read_parquet(labels_dir / "Kelmarsh_1__2019.parquet")
    assert labels["narrow_within_1h"].iloc[:3].tolist() == [True, True, True]
    # the last day looks past the end of the record: unknown, never False
    assert labels["narrow_within_24h"].iloc[-1:].isna().all()
    assert labels["broad_within_1h"].iloc[25:30].all()
    assert "Label table: events per turbine-year and base rate, both sets" in report
    assert "Training sites: status rows against episodes" in report
    assert result.details["harmonised"]


# -- the held-out site ---------------------------------------------------------------------


def turflag(rows: list[tuple[pd.Timestamp, float, float]]) -> str:
    header = (
        "TimeStamp,StationId,wtc_ScTurSto_timeon,wtc_ScEnvSto_timeon,"
        "wtc_ScComSto_timeon,wtc_ScGrdSto_timeon\n"
    )
    # interval-end labels, as published
    lines = [f"{(t + STEP):%Y-%m-%d %H:%M:%S},2304510,{tur},{env},0,0" for t, tur, env in rows]
    return header + "\n".join(lines) + "\n"


def test_the_held_out_site_is_narrowed_by_cause(repo_root: Path, repo_paths: ProjectPaths) -> None:
    raw = repo_paths.source_dir("raw", "telemetry", "hill_of_towie")
    (raw / "Hill_of_Towie_turbine_metadata.csv").write_text(
        "Turbine Name,Station ID\nT01,2304510\n", encoding="utf-8"
    )
    (raw / "Hill_of_Towie_alarms_description.csv").write_text(
        "Alarm Code,Description,Stopping\n20,Large generator Cut-in,0\n3130,Pitch lubrication,1\n",
        encoding="utf-8",
    )
    steps = 300
    downtime = np.zeros(steps)
    tur = np.zeros(steps)
    env = np.zeros(steps)
    downtime[10], tur[10] = 600, 600  # a turbine error: technical
    downtime[20:22], tur[20:22] = 180, 180  # pitch lubrication, filed as turbine error
    downtime[40], env[40] = 600, 600  # a wind stop
    stamps = [T0 + STEP * i for i in range(steps)]
    with zipfile.ZipFile(raw / "2019.zip", "w") as handle:
        handle.writestr(
            "tblSCTurFlag_2019_03.csv", turflag(list(zip(stamps, tur, env, strict=True)))
        )
    with zipfile.ZipFile(raw / "Hill_of_Towie_ShutdownDuration.zip", "w") as handle:
        handle.writestr(
            "ShutdownDuration.csv",
            "TimeStamp_StartFormat,TurbineName,ShutdownDuration\n"
            + "\n".join(
                f"{t:%Y-%m-%d %H:%M:%S}+00:00,T01,{d:g}"
                for t, d in zip(stamps, downtime, strict=True)
            )
            + "\n",
        )
    pd.DataFrame(
        {
            "source": "hill_of_towie",
            "site": "Hill of Towie",
            "turbine_id": "T01",
            "timestamp_utc": stamps,
            "wind_speed_ms": 8.0,
        }
    ).to_parquet(stage_source_dir(repo_paths, "cleaned", "hill_of_towie") / "T01__2019.parquet")
    alarms = pd.DataFrame(
        {
            "source": "hill_of_towie",
            "site": "Hill of Towie",
            "turbine_id": "T01",
            "start_utc": [T0 + 20 * STEP + 5 * S, T0 + 5 * STEP],
            "end_utc": [T0 + 21 * STEP + 190 * S, pd.NaT],
            "code": ["3130", "20"],
            "message": None,
            "category": None,
            "is_fault": None,
            "raw": "{}",
        }
    )
    alarms["end_utc"] = pd.to_datetime(alarms["end_utc"], utc=True)
    alarms.to_parquet(ingest_dir(repo_paths, "hill_of_towie") / "events.parquet")

    _, site, report = run_label(repo_root, repo_paths, "hill_of_towie")

    assert site.events == {"narrow": 1, "broad": 3}
    assert site.causes == {"technical": 1, "planned": 1, "environmental": 1}
    attribution = site.extra["attribution"]
    assert [(o.code, o.steps) for o in attribution.overrides] == [("3130", 2)]
    assert "wtc_ScTurSto_timeon" in site.extra["schema"]["tblSCTurFlag"]
    assert site.extra["schema"]["ShutdownDuration.csv"] == [
        "TimeStamp_StartFormat",
        "TurbineName",
        "ShutdownDuration",
    ]
    assert site.stream == {"rows": 2, "stopping codes": 1, "non-stopping codes": 1}
    assert "hill_of_towie: how the downtime was attributed" in report
