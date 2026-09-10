"""Provider missing-value codes become NaN before bounds and duplicates see them."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from faultline.data.telemetry.clean import (
    BoundSpec,
    TelemetryCleanConfig,
    apply_sentinels,
    clean_turbine_frame,
)
from faultline.data.telemetry.pipeline import load_telemetry_config

T0 = pd.Timestamp("2023-01-01", tz="UTC")


def frame(values: list[float], source: str = "care") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": source,
            "site": "x",
            "turbine_id": "t",
            "timestamp_utc": [T0 + pd.Timedelta(minutes=10 * i) for i in range(len(values))],
            "ambient_temp_c": values,
        }
    )


def test_a_code_becomes_nan_and_is_counted() -> None:
    result, flags = apply_sentinels(frame([12.0, -273.2, 0.0]), {"ambient_temp_c": [-273.2]})
    assert np.isnan(result["ambient_temp_c"].iloc[1])
    assert result["ambient_temp_c"].iloc[2] == 0.0  # not a code for this channel
    assert flags == {"ambient_temp_c": 1}


def test_a_code_exported_at_single_precision_still_matches() -> None:
    # Kelmarsh's stuck gear-oil value is stored as 323.70001220703114.
    result, flags = apply_sentinels(frame([323.70001220703114, 60.0]), {"ambient_temp_c": [323.7]})
    assert flags == {"ambient_temp_c": 1}
    assert result["ambient_temp_c"].iloc[1] == 60.0


def test_a_code_inside_the_bounds_is_still_removed() -> None:
    # A bound cannot catch a code that looks plausible; the sentinel list can.
    config = TelemetryCleanConfig(sentinels={"care": {"ambient_temp_c": [0.0]}})
    cleaned, counts = clean_turbine_frame(
        frame([12.0, 0.0, 13.0]),
        channels=["ambient_temp_c"],
        bounds={"ambient_temp_c": BoundSpec(min=-30, max=50)},
        config=config,
    )
    assert cleaned["ambient_temp_c"].isna().tolist() == [False, True, False]
    assert counts.as_counters()["sentinel:ambient_temp_c"] == 1
    assert counts.as_counters()["bounds:ambient_temp_c"] == 0


def test_the_clean_report_lists_the_codes_apart_from_the_bounds() -> None:
    from datetime import UTC, datetime

    from faultline.config import RunMeta
    from faultline.data.common.stage import StageResult
    from faultline.data.telemetry.report import clean_report

    meta = RunMeta(
        run_id="r", config_path="c", config_hash="h", git_sha="g", created_at=datetime.now(tz=UTC)
    )
    result = StageResult(
        name="clean",
        rows_in=100,
        rows_out=100,
        counters={"sentinel:ambient_temp_c": 4, "bounds:ambient_temp_c": 1},
    )
    report = clean_report(meta, result)
    assert "Missing-value codes per channel" in report
    assert "| ambient_temp_c | 4 | 4.000% |" in report


def test_codes_are_per_source() -> None:
    config = TelemetryCleanConfig(sentinels={"care": {"ambient_temp_c": [0.0]}})
    cleaned, _ = clean_turbine_frame(
        frame([0.0], source="kelmarsh"), ["ambient_temp_c"], {}, config
    )
    assert cleaned["ambient_temp_c"].tolist() == [0.0]


def test_the_v2_config_lists_the_named_codes_and_leaves_v1_alone(repo_root: Path) -> None:
    v2 = load_telemetry_config(repo_root / "configs" / "data" / "telemetry_v2.yaml")
    assert -273.2 in v2.clean.sentinels["care"]["ambient_temp_c"]
    assert 323.7 in v2.clean.sentinels["kelmarsh"]["gearbox_oil_temp_c"]
    # the encoding errors are out of bounds, not extremes
    assert v2.bounds_for("penmanshiel")["generator_speed_rpm"].min > -71_583
    assert v2.bounds_for("kelmarsh")["gearbox_oil_temp_c"].max < 323.7
    assert v2.events.labels_config == "configs/data/events_v2.yaml"
    v1 = load_telemetry_config(repo_root / "configs" / "data" / "telemetry_v1.yaml")
    assert v1.clean.sentinels == {}
    assert (
        v1.bounds
        == load_telemetry_config(repo_root / "configs" / "data" / "telemetry_v1.yaml").bounds
    )
