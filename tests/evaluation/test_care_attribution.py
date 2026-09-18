"""The shipped CARE-attribution config is ADR-0022's F6-0 addendum, and matches its sources."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from faultline.config import load_config
from faultline.evaluation.axis_gate import CARE_FARMS, AxisGateConfig
from faultline.evaluation.care_attribution import CareAttributionConfig
from faultline.evaluation.gate_check import GateCheckConfig

REPO = Path(__file__).resolve().parents[2]
SHIPPED = REPO / "configs/eval/care_attribution_v0.yaml"
HEADING = (
    "### Addendum (F6-0), registered 2026-09-18 before its code or run -- "
    "attribution of the CARE null"
)


def _shipped() -> CareAttributionConfig:
    return load_config(SHIPPED, CareAttributionConfig)


def _card_patterns() -> dict[str, list[str]]:
    """Per farm, the card's "core channels absent from the stream, emitted as `<nan>`" column."""
    lines = (REPO / "data/cards/care.md").read_text(encoding="utf-8").splitlines()
    header = next(line for line in lines if "core channels absent from the stream" in line)
    cells = [cell.strip() for cell in header.strip("|").split("|")]
    column = next(i for i, cell in enumerate(cells) if cell.startswith("core channels absent"))
    patterns: dict[str, list[str]] = {}
    for line in lines:
        match = re.match(r"\|\s*farm ([ABC])\s*\|", line)
        if match is None:
            continue
        row = [cell.strip() for cell in line.strip().strip("|").split("|")]
        patterns[f"farm_{match.group(1).lower()}"] = re.findall(r"`([a-z_]+)`", row[column])
    return patterns


def test_the_configuration_is_registered_in_the_adr_0022_f6_0_addendum() -> None:
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert decisions.count(HEADING) == 1
    adr_0022 = decisions.index("## ADR-0022 ")
    assert adr_0022 < decisions.index(HEADING) < decisions.index("## ADR-0023 ")
    assert "configs/eval/care_attribution_v0.yaml" in decisions


def test_the_registration_hash_is_pending_or_recorded_in_the_addendum() -> None:
    registered = _shipped().registered_in
    assert registered == "pending" or re.fullmatch(r"[0-9a-f]{7,40}", registered)
    if registered != "pending":
        decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
        addendum = decisions[decisions.index(HEADING) :]
        assert f"`{registered}`" in addendum[: addendum.index("\n### ")]


def test_the_masking_patterns_are_the_cards_per_farm_absences() -> None:
    shipped = _shipped()
    card = _card_patterns()
    assert set(card) == set(CARE_FARMS)
    assert shipped.masking.patterns == card
    # The patterns the addendum registers, written out once so a card edit cannot move them.
    assert card == {
        "farm_a": ["main_bearing_temp_c"],
        "farm_b": ["nacelle_temp_c", "generator_bearing_temp_c", "generator_winding_temp_c"],
        "farm_c": ["nacelle_position_deg", "nacelle_temp_c", "generator_bearing_temp_c"],
    }


def test_every_masked_channel_is_a_core_channel_of_the_telemetry_in_force() -> None:
    telemetry = yaml.safe_load((REPO / "configs/data/telemetry_v4.yaml").read_text("utf-8"))
    core = set(telemetry["telemetry"]["core_channels"])
    assert len(core) == 12
    for channels in _shipped().masking.patterns.values():
        assert channels and set(channels) <= core
        assert len(set(channels)) == len(channels)


def test_the_restated_protocol_is_the_axis_gates_and_adr_0021s() -> None:
    shipped = _shipped()
    axis = load_config(REPO / shipped.axis_config, AxisGateConfig)
    gate = load_config(REPO / "configs/train/gate_check_v0.yaml", GateCheckConfig)
    assert shipped.bootstrap == gate.bootstrap == axis.bootstrap
    assert shipped.bootstrap.block_steps == 288 and shipped.bootstrap.replicates == 10000
    assert shipped.bootstrap.seed == 20260916 and shipped.bootstrap.max_discarded_share == 0.01
    assert shipped.stride == axis.stride == 12
    assert shipped.label == axis.label
    assert shipped.seeds == axis.seeds == [1, 2, 3]
    assert shipped.masking.seeds_required == axis.seeds_required == 2
    assert shipped.checkpoint == axis.checkpoints.gating == "final_step"
    assert shipped.base_rate_source == axis.base_rate_source == "scored_set"


def test_the_scored_sets_are_the_axis_gates_counts() -> None:
    shipped = _shipped()
    axis = load_config(REPO / shipped.axis_config, AxisGateConfig)
    masking, bag = shipped.masking, shipped.bag_of_tokens
    assert masking.axis == "temporal" and bag.axis == "care"
    temporal, care = axis.axes.temporal, axis.axes.care
    assert (masking.windows, masking.positives) == (temporal.windows, temporal.positives)
    assert (masking.windows, masking.positives) == (137025, 5312)
    assert masking.base_rate == temporal.base_rate == round(5312 / 137025, 4) == 0.0388
    assert (bag.windows, bag.positives) == (care.windows, care.positives) == (430506, 540)
    assert bag.base_rate == round(540 / 430506, 6) == 0.001254


def test_the_comparator_is_g2s_and_is_not_refit() -> None:
    bag = _shipped().bag_of_tokens
    assert bag.config == "configs/train/bag_of_tokens_v0.yaml"
    assert (REPO / bag.config).is_file()
    assert bag.refit is False and bag.per_farm is True
    assert (REPO / _shipped().masking.seed_replication_config).is_file()
