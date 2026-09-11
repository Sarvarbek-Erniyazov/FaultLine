"""The frozen core channel set agrees with the channel maps and with schemas.py.

The core set exists in three places: derived from the channel maps and the coverage rule,
frozen with evidence in telemetry_v3.yaml (v1 before it), and repeated as tiers in
schemas.py so that config validation needs no file reads. These tests are what keep the
three one set.
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


@pytest.fixture
def v3(repo_root: Path) -> TelemetryPipelineConfig:
    return load_telemetry_config(repo_root / "configs" / "data" / "telemetry_v3.yaml")


def test_the_v1_core_set_is_what_the_maps_derive(
    repo_root: Path, v1: TelemetryPipelineConfig
) -> None:
    # v1 froze the maps' answer, and v1 is not edited.
    maps = load_channel_maps(repo_root / "configs", [*TRAINING, *HOLDOUT])
    core, extended = derive_core(maps, TRAINING, HOLDOUT)
    assert list(v1.core_channels) == core
    assert list(v1.extended_channels) == extended


def test_the_v3_core_set_is_the_maps_less_what_coverage_demotes(
    repo_root: Path, v3: TelemetryPipelineConfig
) -> None:
    # Since M1b step 10 the maps are necessary, not sufficient (ADR-0008): wind direction
    # is mappable everywhere and fails condition (a) at the held-out site.
    maps = load_channel_maps(repo_root / "configs", [*TRAINING, *HOLDOUT])
    mappable, _ = derive_core(maps, TRAINING, HOLDOUT)
    assert list(v3.core_channels) == [c for c in mappable if c != "wind_direction_deg"]
    assert len(v3.core_channels) == 12


def test_the_declared_tiers_match_the_frozen_set(v3: TelemetryPipelineConfig) -> None:
    assert tuple(v3.core_channels) == CORE_CHANNELS
    assert tuple(v3.extended_channels) == EXTENDED_CHANNELS


def test_the_two_extended_channels(
    v1: TelemetryPipelineConfig, v3: TelemetryPipelineConfig
) -> None:
    # v1: neither Senvion site publishes a gearbox bearing. v3 adds wind direction.
    assert list(v1.extended_channels) == ["gearbox_bearing_temp_c"]
    assert list(v3.extended_channels) == ["wind_direction_deg", "gearbox_bearing_temp_c"]
    assert len(v3.core_channels) == len(CHANNEL_NAMES) - 2


def test_every_tiered_channel_carries_its_evidence(
    v1: TelemetryPipelineConfig, v3: TelemetryPipelineConfig
) -> None:
    for note in {**v1.core_channels, **v1.extended_channels}.values():
        assert note.strip()
    # v3's notes carry the non-null share at every site the rule reads
    for note in {**v3.core_channels, **v3.extended_channels}.values():
        assert all(f"{site} " in note for site in ("K", "P", "H")), note
        assert "%" in note
    assert "0.0% in 2019" in v3.extended_channels["wind_direction_deg"]


def test_the_channel_order_is_unchanged_from_v0(
    repo_root: Path, v1: TelemetryPipelineConfig, v3: TelemetryPipelineConfig
) -> None:
    # Channel order is token identity (ADR-0003); a demotion must not move it.
    v0 = load_telemetry_config(repo_root / "configs" / "data" / "telemetry_v0.yaml")
    assert v3.channels == v1.channels == v0.channels == list(CHANNEL_NAMES)
    assert not v0.core_channels  # v0 is left as M0 declared it


def test_v3_reads_the_v2_split(v3: TelemetryPipelineConfig) -> None:
    assert v3.final.splits_config == "configs/data/splits_v2.yaml"


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
