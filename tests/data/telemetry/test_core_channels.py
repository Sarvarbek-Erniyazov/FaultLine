"""The frozen core channel set agrees with the channel maps and with schemas.py.

The core set exists in three places: derived from the channel maps, frozen with
evidence in telemetry_v1.yaml, and repeated as tiers in schemas.py so that config
validation needs no file reads. These tests are what keep the three one set.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from faultline.data.telemetry.channels import derive_core, load_channel_maps
from faultline.data.telemetry.pipeline import TelemetryPipelineConfig, load_telemetry_config
from faultline.data.telemetry.schemas import CHANNEL_NAMES, CORE_CHANNELS, EXTENDED_CHANNELS

TRAINING = ["kelmarsh", "penmanshiel"]
HOLDOUT = ["hill_of_towie"]


@pytest.fixture
def v1(repo_root: Path) -> TelemetryPipelineConfig:
    return load_telemetry_config(repo_root / "configs" / "data" / "telemetry_v1.yaml")


def test_the_frozen_core_set_is_what_the_maps_derive(
    repo_root: Path, v1: TelemetryPipelineConfig
) -> None:
    maps = load_channel_maps(repo_root / "configs", [*TRAINING, *HOLDOUT])
    core, extended = derive_core(maps, TRAINING, HOLDOUT)
    assert list(v1.core_channels) == core
    assert list(v1.extended_channels) == extended


def test_the_declared_tiers_match_the_frozen_set(v1: TelemetryPipelineConfig) -> None:
    assert tuple(v1.core_channels) == CORE_CHANNELS
    assert tuple(v1.extended_channels) == EXTENDED_CHANNELS


def test_the_one_extended_channel_is_the_gearbox_bearing(v1: TelemetryPipelineConfig) -> None:
    # Neither Senvion site publishes it; the held-out site publishes four.
    assert list(v1.extended_channels) == ["gearbox_bearing_temp_c"]
    assert len(v1.core_channels) == len(CHANNEL_NAMES) - 1


def test_every_tiered_channel_carries_its_evidence(v1: TelemetryPipelineConfig) -> None:
    for note in {**v1.core_channels, **v1.extended_channels}.values():
        assert note.strip()
    # the caveat on the one core channel the held-out site publishes in part
    assert "2023 only" in v1.core_channels["wind_direction_deg"]


def test_the_channel_order_is_unchanged_from_v0(
    repo_root: Path, v1: TelemetryPipelineConfig
) -> None:
    # Channel order is token identity (ADR-0003); freezing the tiers must not move it.
    v0 = load_telemetry_config(repo_root / "configs" / "data" / "telemetry_v0.yaml")
    assert v1.channels == v0.channels == list(CHANNEL_NAMES)
    assert not v0.core_channels  # v0 is left as M0 declared it


def _config(**overrides: object) -> TelemetryPipelineConfig:
    payload: dict[str, object] = {"channels": ["wind_speed_ms", "power_kw"]}
    payload.update(overrides)
    return TelemetryPipelineConfig.model_validate(payload)


def test_tiers_must_cover_every_channel() -> None:
    with pytest.raises(ValidationError, match="must partition channels"):
        _config(core_channels={"wind_speed_ms": "both sites"})


def test_a_channel_cannot_be_core_and_extended() -> None:
    with pytest.raises(ValidationError, match="both core and extended"):
        _config(
            core_channels={"wind_speed_ms": "x", "power_kw": "y"},
            extended_channels={"power_kw": "z"},
        )


def test_a_tier_without_evidence_is_rejected() -> None:
    with pytest.raises(ValidationError, match="evidence note"):
        _config(core_channels={"wind_speed_ms": "both sites", "power_kw": "  "})
