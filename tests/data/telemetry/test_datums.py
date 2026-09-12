"""The declared datum harmonisation, and the order it runs in (ADR-0012).

Three properties carry the decision and are tested here rather than assumed: the floor
moves a value expressed against another zero, it never rescues a value the plausibility
bounds already rejected, and it never invents a reading where there was none.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from faultline.data.telemetry.clean import BoundSpec, TelemetryCleanConfig, clean_turbine_frame
from faultline.data.telemetry.datums import DatumSpec, apply_datums
from faultline.data.telemetry.pipeline import TelemetryPipelineConfig, load_telemetry_config

FLOOR = {"pitch_angle_deg": DatumSpec(floor=0.0, reason="Senvion 0.0, Siemens -1.0")}


def frame(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"pitch_angle_deg": values, "power_pu": [1.0] * len(values)})


def test_a_value_below_the_floor_is_raised_to_it() -> None:
    out, moved = apply_datums(frame([-1.0, -0.087, 0.0, 3.5]), FLOOR)
    assert out["pitch_angle_deg"].tolist() == [0.0, 0.0, 0.0, 3.5]
    assert moved == {"pitch_angle_deg": 2}


def test_missing_stays_missing_and_is_not_counted() -> None:
    out, moved = apply_datums(frame([np.nan, -1.0]), FLOOR)
    assert bool(pd.isna(out["pitch_angle_deg"].iloc[0]))
    assert moved == {"pitch_angle_deg": 1}


def test_an_undeclared_channel_is_untouched() -> None:
    out, _ = apply_datums(frame([-1.0]), FLOOR)
    assert out["power_pu"].tolist() == [1.0]


def test_a_channel_absent_from_the_table_is_skipped() -> None:
    out, moved = apply_datums(pd.DataFrame({"power_pu": [1.0]}), FLOOR)
    assert list(out.columns) == ["power_pu"]
    assert moved == {}


def test_a_spec_without_a_floor_does_nothing() -> None:
    out, moved = apply_datums(frame([-1.0]), {"pitch_angle_deg": DatumSpec(reason="declared")})
    assert out["pitch_angle_deg"].tolist() == [-1.0]
    assert moved == {}


def test_the_floor_does_not_rescue_a_value_the_bounds_rejected() -> None:
    # The ordering ADR-0012 turns on: -40 degrees is an instrument failure, not fine
    # pitch. The bounds NaN it in the cleaning stage; the floor must leave it NaN.
    raw = pd.DataFrame(
        {
            "source": ["kelmarsh"] * 3,
            "site": ["Kelmarsh"] * 3,
            "turbine_id": ["K1"] * 3,
            "timestamp_utc": pd.date_range("2019-01-01", periods=3, freq="10min", tz="UTC"),
            "pitch_angle_deg": [-40.0, -1.0, 2.0],
        }
    )
    cleaned, counts = clean_turbine_frame(
        raw,
        channels=["pitch_angle_deg"],
        bounds={"pitch_angle_deg": BoundSpec(min=-5.0, max=100.0)},
        config=TelemetryCleanConfig(),
    )
    assert counts.bounds_flags == {"pitch_angle_deg": 1}
    harmonised, moved = apply_datums(cleaned, FLOOR)
    values = harmonised["pitch_angle_deg"]
    assert bool(pd.isna(values.iloc[0]))
    assert values.iloc[1] == 0.0
    assert values.iloc[2] == 2.0
    assert moved == {"pitch_angle_deg": 1}


def test_a_datum_on_an_unknown_channel_is_rejected() -> None:
    with pytest.raises(ValidationError, match="not configured"):
        TelemetryPipelineConfig.model_validate(
            {
                "channels": ["power_pu"],
                "harmonise": {"pitch_angle_deg": {"floor": 0.0, "reason": "x"}},
            }
        )


def test_a_datum_without_evidence_is_rejected() -> None:
    with pytest.raises(ValidationError, match="evidence"):
        TelemetryPipelineConfig.model_validate(
            {"channels": ["pitch_angle_deg"], "harmonise": {"pitch_angle_deg": {"floor": 0.0}}}
        )


def test_v4_floors_pitch_at_zero_and_earlier_versions_declare_nothing(repo_root: Path) -> None:
    configs = repo_root / "configs" / "data"
    v4 = load_telemetry_config(configs / "telemetry_v4.yaml")
    assert v4.harmonise["pitch_angle_deg"].floor == 0.0
    assert "datum" in v4.harmonise["pitch_angle_deg"].reason
    # The rule is per channel and never per source: one floor, applied everywhere.
    assert list(v4.harmonise) == ["pitch_angle_deg"]
    for version in ("v0", "v1", "v2", "v3"):
        assert not load_telemetry_config(configs / f"telemetry_{version}.yaml").harmonise
