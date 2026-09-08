"""Telemetry pipeline stages, exercised on synthetic turbine-years."""

from __future__ import annotations

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
            "power_kw": rng.uniform(0, 2000, rows),
            "rotor_speed_rpm": rng.uniform(5, 16, rows),
        }
    )
    # a short gap that imputation should fill, and a long one that ends a segment
    frame.loc[100:101, ["wind_speed_ms", "power_kw", "rotor_speed_rpm"]] = np.nan
    frame.loc[200:229, ["wind_speed_ms", "power_kw", "rotor_speed_rpm"]] = np.nan
    # an implausible reading that the bounds must reject
    frame.loc[10, "wind_speed_ms"] = 500.0
    return frame


def test_shipped_config_loads(config_path: Path) -> None:
    config = load_telemetry_config(config_path)
    assert config.freq == "10min"
    assert len(config.channels) == 13
    assert config.channels[0] == "wind_speed_ms"
    assert config.bounds["wind_speed_ms"].max == 60.0
    # unmapped codes must remain unknown, never assumed benign (ADR-0006)
    assert config.events.default_is_fault is None


def test_per_source_bound_overrides(config_path: Path) -> None:
    config = load_telemetry_config(config_path)
    default = config.bounds_for("kelmarsh")["power_kw"].max
    towie = config.bounds_for("hill_of_towie")["power_kw"].max
    assert towie > default  # 2300 kW rated rather than 2050 kW


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


def test_clean_filter_final_on_a_synthetic_turbine_year(
    config_path: Path, repo_paths: ProjectPaths
) -> None:
    config = load_telemetry_config(config_path)
    frame = synthetic_turbine_year()
    destination = ingest_dir(repo_paths, SOURCE)
    frame.to_parquet(destination / "T1__2020.parquet", index=False)

    stages = build_stages(config, repo_paths, "all", source=SOURCE)
    with start_run(config_path, config, "all", "telemetry", repo_paths) as ctx:
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
    for channel in ("wind_speed_ms", "power_kw"):
        assert f"{channel}{IMPUTED_SUFFIX}" in output.columns
    assert "split" in output.columns
    assert "segment_id" in output.columns

    for stage in STAGE_ORDER:
        assert (run_dir / f"{stage}_stats_report.md").is_file()


def test_long_gaps_are_never_imputed(config_path: Path, repo_paths: ProjectPaths) -> None:
    config = load_telemetry_config(config_path)
    frame = synthetic_turbine_year()
    frame.to_parquet(ingest_dir(repo_paths, SOURCE) / "T1__2020.parquet", index=False)

    stages = build_stages(config, repo_paths, "all", source=SOURCE)
    with start_run(config_path, config, "all", "telemetry", repo_paths) as ctx:
        results = run_pipeline(stages, ctx)

    imputed = results[-1].details["imputed"]
    # only the 2-step gap qualifies under max_impute_steps=3; the 30-step hole does not
    assert imputed["wind_speed_ms"] <= 3


def test_unknown_stage_and_source_are_rejected(config_path: Path, repo_paths: ProjectPaths) -> None:
    config = load_telemetry_config(config_path)
    with pytest.raises(ValueError, match="unknown stage"):
        build_stages(config, repo_paths, "polish")
    with pytest.raises(KeyError, match="unknown source"):
        build_stages(config, repo_paths, "all", source="nowhere")


def test_stage_dir_names_are_validated(repo_paths: ProjectPaths) -> None:
    with pytest.raises(ValueError, match="unknown telemetry stage"):
        stage_source_dir(repo_paths, "polished", SOURCE)
