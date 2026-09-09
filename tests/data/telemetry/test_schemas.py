"""The canonical channel list and its core/extended tiers (ADR-0003, ADR-0006)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from faultline.data.telemetry.schemas import (
    CANONICAL_CHANNELS,
    CHANNEL_NAMES,
    CHANNELS_BY_NAME,
    CORE_CHANNELS,
    EXTENDED_CHANNELS,
    channel_tier,
)


def test_channel_names_are_unique_and_ordered_like_the_specs() -> None:
    assert len(set(CHANNEL_NAMES)) == len(CHANNEL_NAMES)
    assert CHANNEL_NAMES == tuple(spec.name for spec in CANONICAL_CHANNELS)


def test_every_channel_has_a_tier_and_the_two_tiers_partition_the_list() -> None:
    assert set(CORE_CHANNELS) | set(EXTENDED_CHANNELS) == set(CHANNEL_NAMES)
    assert not set(CORE_CHANNELS) & set(EXTENDED_CHANNELS)
    for spec in CANONICAL_CHANNELS:
        assert spec.tier in ("core", "extended")


def test_main_bearing_temperature_is_present_and_appended_last() -> None:
    # Appended rather than filed with the other bearing channels: position in this
    # list is the channel token identifier (ADR-0003), so an insert would move every
    # later id.
    assert CHANNEL_NAMES[-1] == "main_bearing_temp_c"
    assert CHANNELS_BY_NAME["main_bearing_temp_c"].unit == "degC"


def test_a_channel_verified_absent_from_a_training_site_is_extended() -> None:
    # Kelmarsh publishes no gearbox bearing temperature at all -- the one tier
    # assignment M0 evidence actually settles.
    assert channel_tier("gearbox_bearing_temp_c") == "extended"
    # A channel confirmed at one site only cannot be core either.
    assert channel_tier("main_bearing_temp_c") == "extended"


def test_channel_tier_rejects_an_unknown_name() -> None:
    with pytest.raises(KeyError, match="not a canonical channel"):
        channel_tier("power_kwh")


def test_the_shipped_config_lists_exactly_the_canonical_channels(repo_root: Path) -> None:
    # The YAML channel list and the canonical list are the same list in two places;
    # a drift between them would silently change channel token identifiers.
    payload = yaml.safe_load(
        (repo_root / "configs" / "data" / "telemetry_v0.yaml").read_text(encoding="utf-8")
    )
    assert tuple(payload["telemetry"]["channels"]) == CHANNEL_NAMES


def test_every_channel_has_a_plausibility_bound(repo_root: Path) -> None:
    payload = yaml.safe_load(
        (repo_root / "configs" / "data" / "telemetry_v0.yaml").read_text(encoding="utf-8")
    )
    bounds = payload["telemetry"]["bounds"]
    assert set(bounds) == set(CHANNEL_NAMES)
    assert bounds["main_bearing_temp_c"] == {"min": -40.0, "max": 150.0}
