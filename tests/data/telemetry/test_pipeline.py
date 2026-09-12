"""Telemetry pipeline stages, exercised on synthetic turbine-years."""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from faultline.data.common.stage import run_pipeline
from faultline.data.telemetry.pipeline import (
    STAGE_ORDER,
    build_stages,
    ingest_dir,
    load_telemetry_config,
    parquet_files,
    stage_source_dir,
    turbine_year_name,
)
from faultline.data.telemetry.schemas import IMPUTED_SUFFIX
from faultline.paths import ProjectPaths
from faultline.runs import start_run

SOURCE = "kelmarsh"


@pytest.fixture
def config_path(repo_root: Path) -> Path:
    return repo_root / "configs" / "data" / "telemetry_v0.yaml"


@pytest.fixture
def current_path(repo_root: Path) -> Path:
    # Runs through the final stage read the current split spec: v0's and v1's no longer
    # load (they evaluate wind direction, extended from M1b step 10, ADR-0008), and v2's
    # names power_kw, renamed at M1c (ADR-0013).
    return repo_root / "configs" / "data" / "telemetry_v4.yaml"


def synthetic_turbine_year(rows: int = 500) -> pd.DataFrame:
    stamps = pd.date_range("2020-01-01", periods=rows, freq="10min", tz="UTC")
    rng = np.random.default_rng(20260909)
    frame = pd.DataFrame(
        {
            "source": SOURCE,
            "site": "Kelmarsh",
            "turbine_id": "T1",
            "timestamp_utc": stamps,
            "wind_speed_ms": rng.uniform(3, 18, rows),
            "power_pu": rng.uniform(0, 2000, rows),
            "rotor_speed_rpm": rng.uniform(5, 16, rows),
        }
    )
    # a short gap that imputation should fill, and a long one that ends a segment
    frame.loc[100:101, ["wind_speed_ms", "power_pu", "rotor_speed_rpm"]] = np.nan
    frame.loc[200:229, ["wind_speed_ms", "power_pu", "rotor_speed_rpm"]] = np.nan
    # an implausible reading that the bounds must reject
    frame.loc[10, "wind_speed_ms"] = 500.0
    return frame


def test_shipped_config_loads(config_path: Path) -> None:
    config = load_telemetry_config(config_path)
    assert config.freq == "10min"
    assert len(config.channels) == 14
    assert config.channels[0] == "wind_speed_ms"
    assert config.channels[-1] == "main_bearing_temp_c"
    assert config.bounds["wind_speed_ms"].max == 60.0
    # unmapped codes must remain unknown, never assumed benign (ADR-0006)
    assert config.events.default_is_fault is None


def test_the_v1_config_loads_and_chooses_no_primary_horizon(repo_root: Path) -> None:
    config = load_telemetry_config(repo_root / "configs" / "data" / "telemetry_v1.yaml")
    assert config.events.horizons_steps == [6, 36, 144]  # 1 h, 6 h, 24 h
    assert config.events.horizon_steps is None
    assert config.final.splits_config == "configs/data/splits_v1.yaml"
    # v1 predates the rename and spells the channel power_kw. CARE's bound was already
    # per unit there, which is why ADR-0013 had nothing to convert for it.
    assert config.bounds_for("care")["power_kw"].max == 1.1


def test_per_source_bound_overrides(config_path: Path, current_path: Path) -> None:
    # v0, in kW: the held-out site's bound is higher because its machine is bigger.
    v0 = load_telemetry_config(config_path)
    assert (
        v0.bounds_for("hill_of_towie")["power_kw"].max > v0.bounds_for("kelmarsh")["power_kw"].max
    )

    # v4, in per unit of rated power: the same bound is the same number at both sites,
    # because dividing by the rating is what made them comparable (ADR-0013). The minima
    # still differ: -100 kW was an absolute allowance and does not scale with a rating.
    v4 = load_telemetry_config(current_path)
    assert v4.bounds_for("kelmarsh")["power_pu"].max == 1.1
    assert v4.bounds_for("hill_of_towie")["power_pu"].max == 1.1
    assert v4.bounds_for("care")["power_pu"].max == 1.1
    assert (
        v4.bounds_for("hill_of_towie")["power_pu"].min > v4.bounds_for("kelmarsh")["power_pu"].min
    )


def test_turbine_year_name_is_filesystem_safe() -> None:
    assert turbine_year_name("Kelmarsh/1", 2020) == "Kelmarsh_1__2020"


def test_ingest_reports_unimplemented_adapters(config_path: Path, repo_paths: ProjectPaths) -> None:
    # At M0 no loader is implemented. The stage must say so in its report rather than
    # silently producing an empty corpus.
    config = load_telemetry_config(config_path)
    repo_paths.source_dir("raw", "telemetry", SOURCE)
    stages = build_stages(config, repo_paths, "ingest", source=SOURCE)
    with start_run(config_path, config, "ingest", "telemetry", repo_paths) as ctx:
        results = run_pipeline(stages, ctx)
        report = (ctx.run_dir / "ingest_stats_report.md").read_text(encoding="utf-8")

    result = results[0]
    assert result.rows_out == 0
    assert "Adapters not yet implemented" in report or result.counters["not_implemented"] == 0


def test_ingest_accounts_for_every_row_of_every_file(
    repo_root: Path, repo_paths: ProjectPaths, fixtures_dir: Path
) -> None:
    # The committed Kelmarsh excerpt, zipped the way the record ships it.
    excerpt = fixtures_dir / "telemetry" / "kelmarsh"
    raw = repo_paths.source_dir("raw", "telemetry", SOURCE)
    with zipfile.ZipFile(raw / "Kelmarsh_SCADA_2016_test.zip", "w") as handle:
        handle.write(
            excerpt / "Turbine_Data_Kelmarsh_1_excerpt.csv", "Turbine_Data_Kelmarsh_1_2016.csv"
        )
        handle.write(excerpt / "Status_Kelmarsh_1_excerpt.csv", "Status_Kelmarsh_1_2016.csv")

    v1 = repo_root / "configs" / "data" / "telemetry_v1.yaml"
    config = load_telemetry_config(v1)
    stages = build_stages(config, repo_paths, "ingest", source=SOURCE)
    with start_run(v1, config, "ingest", "telemetry", repo_paths) as ctx:
        result = run_pipeline(stages, ctx)[0]
        report = (ctx.run_dir / "ingest_stats_report.md").read_text(encoding="utf-8")

    assert result.counters["files"] == 1
    assert result.counters["files_with_repeated_labels"] == 0
    source, member, turbine, rows_raw, after_drop, labels, rows_out = result.details["files"][0]
    assert (source, turbine, rows_raw, labels) == (SOURCE, "Kelmarsh 1", 40, 40)
    assert rows_out == after_drop == result.rows_out
    assert "Row accounting per file" in report
    assert (ingest_dir(repo_paths, SOURCE) / "events.parquet").is_file()


def test_a_month_of_three_joined_tables_is_counted_once(
    repo_root: Path, repo_paths: ProjectPaths
) -> None:
    # Hill of Towie: one month, three tables, two stations, two labels. Summing the
    # tables' rows_out counted every row three times (M1a step 6c).
    raw = repo_paths.source_dir("raw", "telemetry", "hill_of_towie")
    (raw / "Hill_of_Towie_turbine_metadata.csv").write_text(
        "Turbine Name,Station ID\nT01,2304510\nT02,2304511\n", encoding="utf-8"
    )
    rows = [
        f"2019-03-01 00:{m}0:00,{station}" for m in (1, 2) for station in ("2304510", "2304511")
    ]
    tables = {
        "tblSCTurbine_2019_03.csv": "wtc_AcWindSp_mean",
        "tblSCTurGrid_2019_03.csv": "wtc_ActPower_mean",
        "tblSCTurTemp_2019_03.csv": "wtc_AmbieTmp_mean",
    }
    with zipfile.ZipFile(raw / "2019.zip", "w") as handle:
        for name, column in tables.items():
            body = "\n".join(f"{row},{i + 1.5}" for i, row in enumerate(rows))
            handle.writestr(name, f"TimeStamp,StationId,{column}\n{body}\n")

    v1 = repo_root / "configs" / "data" / "telemetry_v1.yaml"
    config = load_telemetry_config(v1)
    stages = build_stages(config, repo_paths, "ingest", source="hill_of_towie")
    with start_run(v1, config, "ingest", "telemetry", repo_paths) as ctx:
        result = run_pipeline(stages, ctx)[0]
        report = (ctx.run_dir / "ingest_stats_report.md").read_text(encoding="utf-8")

    assert sum(row[6] for row in result.details["files"]) == 12  # 3 tables x 4 rows
    assert [(unit[2], unit[3]) for unit in result.details["units"]] == [(3, 4)]
    assert result.rows_out == 4
    assert "| rows_out, over units (after each unit's join) | 4 |" in report
    assert "| rows_out over units less the copies equals rows loaded | yes |" in report


def test_clean_filter_final_on_a_synthetic_turbine_year(
    current_path: Path, repo_paths: ProjectPaths
) -> None:
    config = load_telemetry_config(current_path)
    frame = synthetic_turbine_year()
    destination = ingest_dir(repo_paths, SOURCE)
    frame.to_parquet(destination / "T1__2020.parquet", index=False)

    stages = build_stages(config, repo_paths, "all", source=SOURCE)
    with start_run(current_path, config, "all", "telemetry", repo_paths) as ctx:
        results = run_pipeline(stages, ctx)
        run_dir = ctx.run_dir

    by_name = {result.name: result for result in results}
    assert list(by_name) == list(STAGE_ORDER)

    clean = by_name["clean"]
    assert clean.rows_in == 500
    assert clean.counters["bounds:wind_speed_ms"] == 1  # the 500 m/s reading

    filtered = by_name["filter"]
    # the 30-step hole splits the year into two segments
    assert filtered.counters["segments_total"] == 2
    assert filtered.rows_out < filtered.rows_in

    final = by_name["final"]
    assert final.rows_out > 0
    assert final.details["imputed"]["wind_speed_ms"] >= 1  # the 2-step gap was filled

    written = parquet_files(stage_source_dir(repo_paths, "final", SOURCE))
    assert written
    output = pd.read_parquet(written[0])
    for channel in ("wind_speed_ms", "power_pu"):
        assert f"{channel}{IMPUTED_SUFFIX}" in output.columns
    assert "split" in output.columns
    assert "segment_id" in output.columns

    for stage in STAGE_ORDER:
        assert (run_dir / f"{stage}_stats_report.md").is_file()
    final_report = (run_dir / "final_stats_report.md").read_text(encoding="utf-8")
    assert "Splits: windows and events per split" in final_report
    assert final.details["checked"]["segments"] >= 1
    assert final.details["checked"]["windows"] >= 1


def test_long_gaps_are_never_imputed(current_path: Path, repo_paths: ProjectPaths) -> None:
    config = load_telemetry_config(current_path)
    frame = synthetic_turbine_year()
    frame.to_parquet(ingest_dir(repo_paths, SOURCE) / "T1__2020.parquet", index=False)

    stages = build_stages(config, repo_paths, "all", source=SOURCE)
    with start_run(current_path, config, "all", "telemetry", repo_paths) as ctx:
        results = run_pipeline(stages, ctx)

    imputed = results[-1].details["imputed"]
    # only the 2-step gap qualifies under max_impute_steps=3; the 30-step hole does not
    assert imputed["wind_speed_ms"] <= 3


def test_the_final_stage_withholds_training_windows_inside_an_exclusion(
    current_path: Path, repo_paths: ProjectPaths
) -> None:
    # splits_v3 excludes Penmanshiel from 2018-03-01 00:00; these twenty days start nine
    # days before it, so the last 11 days' rows (1,584) lie inside the first span.
    config = load_telemetry_config(current_path)
    rows = 20 * 144
    frame = synthetic_turbine_year(rows).assign(
        source="penmanshiel", site="Penmanshiel", turbine_id="Penmanshiel 01"
    )
    frame["timestamp_utc"] = pd.date_range("2018-02-20", periods=rows, freq="10min", tz="UTC")
    frame.to_parquet(ingest_dir(repo_paths, "penmanshiel") / "P01__2018.parquet", index=False)

    stages = build_stages(config, repo_paths, "all", source="penmanshiel")
    with start_run(current_path, config, "all", "telemetry", repo_paths) as ctx:
        results = run_pipeline(stages, ctx)
        report = (ctx.run_dir / "final_stats_report.md").read_text(encoding="utf-8")

    counts = results[-1].details["split_windows"][("train", "penmanshiel")]
    assert counts["rows in a training exclusion"] == 11 * 144
    assert "**Training exclusions** (ADR-0008)" in report
    assert "| train | penmanshiel | 1,584 |" in report


def test_unknown_stage_and_source_are_rejected(config_path: Path, repo_paths: ProjectPaths) -> None:
    config = load_telemetry_config(config_path)
    with pytest.raises(ValueError, match="unknown stage"):
        build_stages(config, repo_paths, "polish")
    with pytest.raises(KeyError, match="unknown source"):
        build_stages(config, repo_paths, "all", source="nowhere")


def test_stage_dir_names_are_validated(repo_paths: ProjectPaths) -> None:
    with pytest.raises(ValueError, match="unknown telemetry stage"):
        stage_source_dir(repo_paths, "polished", SOURCE)
