"""The shipped CARE-attribution config is ADR-0022's F6-0 addendum, and matches its sources."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from faultline.config import load_config
from faultline.evaluation.axis_gate import CARE_FARMS, AxisGateConfig
from faultline.evaluation.bootstrap import AuprcInterval
from faultline.evaluation.care_attribution import (
    CareAttributionConfig,
    MaskedSampler,
    interval_position,
    mask_positions,
    mask_tokens,
    read_bag,
    read_masking,
)
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.tokenizers.joint import JointVocab
from faultline.tokenizers.layout import VocabLayout
from faultline.tokenizers.quantile_bins import QuantileBinTokenizer
from faultline.training.windows import WindowSampler, WindowSet

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


# ------------------------------------------------------------------ the masking


CHANNELS = ["wind_speed_ms", "power_pu", "nacelle_temp_c"]
STEPS = 6


def _vocab() -> JointVocab:
    rng = np.random.default_rng(7)
    fit = pd.DataFrame({name: rng.uniform(0, 100, 400) for name in CHANNELS})
    bins = QuantileBinTokenizer.fit(fit, CHANNELS, n_bins=8)
    return JointVocab(VocabLayout.from_sizes(0, 14, 8), bin_tokenizer=bins)


def _window_frame() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    return pd.DataFrame({name: rng.uniform(0, 100, STEPS) for name in CHANNELS})


def test_masking_a_synthetic_window_changes_only_the_masked_channels_bin_positions() -> None:
    vocab = _vocab()
    step = ["<sep>", *CHANNELS]
    unmasked = vocab.encode_steps(_window_frame()).astype(np.int64).ravel()
    positions = mask_positions(step, ["nacelle_temp_c"], STEPS)
    masked = mask_tokens(unmasked, positions, vocab.special("<nan>"))
    # the stream differs from the unmasked one only at the masked channel's bin positions
    changed = np.flatnonzero(masked != unmasked)
    assert changed.tolist() == positions.tolist()
    assert positions.tolist() == [3 + 4 * s for s in range(STEPS)]
    # the replacement id is the tokenizer's <nan> id, and <sep> never moves
    assert (masked[positions] == vocab.special("<nan>")).all()
    assert (masked[0 :: len(step)] == vocab.special("<sep>")).all()
    # and it is exactly what the adapter path emits for a channel the frame does not carry
    adapter = vocab.encode_steps(_window_frame().drop(columns=["nacelle_temp_c"]))
    assert np.array_equal(masked, adapter.astype(np.int64).ravel())
    excluded = vocab.encode_steps(_window_frame(), masked=["nacelle_temp_c"])
    assert np.array_equal(masked, excluded.astype(np.int64).ravel())


def test_masking_several_channels_matches_the_adapter_too() -> None:
    vocab = _vocab()
    unmasked = vocab.encode_steps(_window_frame()).astype(np.int64).ravel()
    positions = mask_positions(["<sep>", *CHANNELS], ["power_pu", "wind_speed_ms"], STEPS)
    masked = mask_tokens(unmasked, positions, vocab.special("<nan>"))
    adapter = vocab.encode_steps(_window_frame()[["nacelle_temp_c"]])
    assert np.array_equal(masked, adapter.astype(np.int64).ravel())
    assert len(positions) == 2 * STEPS


def test_mask_positions_refuses_sep_unknown_and_repeated_channels() -> None:
    step = ["<sep>", *CHANNELS]
    with pytest.raises(ValueError, match="not channel positions"):
        mask_positions(step, ["<sep>"], STEPS)
    with pytest.raises(ValueError, match="not channel positions"):
        mask_positions(step, ["main_bearing_temp_c"], STEPS)
    with pytest.raises(ValueError, match="twice"):
        mask_positions(step, ["power_pu", "power_pu"], STEPS)


def test_the_masked_sampler_reads_the_same_windows_masked(tmp_path: Path) -> None:
    per_step, steps = 4, 20
    stream = (np.arange(steps * per_step) % 50 + 10).astype(np.uint16)
    stream.tofile(tmp_path / "alpha__test.bin")
    tokens = np.memmap(tmp_path / "alpha__test.bin", dtype=np.uint16, mode="r")
    starts = np.arange(0, steps - STEPS + 1, 3, dtype=np.int64)
    window_set = WindowSet(
        key="alpha__test",
        tokens=tokens,
        starts=starts,
        ends=starts + STEPS - 1,
        labels=(starts % 2).astype(np.float32),
        years=np.full(starts.size, 2020),
    )
    base = WindowSampler([window_set], 2, per_step, STEPS, labelled=True)
    positions = mask_positions(["<sep>", *CHANNELS], ["power_pu"], STEPS)
    masked = MaskedSampler(base, positions, 9)
    for (plain, y, s), (hidden, my, ms) in zip(base.epoch(), masked.epoch(), strict=True):
        assert np.array_equal(y.numpy(), my.numpy()) and np.array_equal(s, ms)
        assert np.array_equal(hidden.numpy(), mask_tokens(plain.numpy(), positions, 9))
    with pytest.raises(ValueError, match="outside a window"):
        MaskedSampler(base, np.array([STEPS * per_step]), 9)


# ------------------------------------------------------------------ the readings


def _interval(auprc: float, low: float, high: float, discarded: int = 0) -> AuprcInterval:
    return AuprcInterval(
        unit="block",
        auprc=auprc,
        low=low,
        high=high,
        lift_low=0.0,
        lift_high=0.0,
        base_rate=0.03877,
        windows=137025,
        positives=5312,
        blocks=5799,
        positive_blocks=497,
        replicates=10000,
        discarded=discarded,
        confidence=0.95,
        seed=20260916,
    )


def test_interval_position_is_strict_and_honours_the_discard_rule() -> None:
    assert interval_position(_interval(0.05, 0.0389, 0.06), 0.0388, 0.01) == "clears"
    assert interval_position(_interval(0.05, 0.0388, 0.06), 0.0388, 0.01) == "contains"
    assert interval_position(_interval(0.03, 0.02, 0.0387), 0.0388, 0.01) == "below"
    untrusted = _interval(0.05, 0.045, 0.06, discarded=101)
    assert interval_position(untrusted, 0.0388, 0.01) == "contains"


def test_the_first_clause_belongs_to_farm_a_alone() -> None:
    reading = read_masking("farm_a", {1: "clears", 2: "clears", 3: "contains"}, 2)
    assert (reading.clause, reading.attribution) == ("first", "transfer failure")
    other = read_masking("farm_b", {1: "clears", 2: "clears", 3: "contains"}, 2)
    assert (other.clause, other.attribution) == ("neither", "unattributed")


def test_the_second_clause_and_the_gap() -> None:
    second = read_masking("farm_c", {1: "contains", 2: "contains", 3: "clears"}, 2)
    assert (second.clause, second.attribution) == ("second", "unattributed")
    one_seed = read_masking("farm_a", {1: "clears", 2: "below", 3: "below"}, 2)
    assert one_seed.clause == "neither" and "neither registered clause" in one_seed.sentence
    assert read_masking("farm_a", {1: "contains", 2: "below", 3: "clears"}, 2).clause == "neither"


def test_the_bag_reading_has_two_clauses_and_a_gap() -> None:
    assert read_bag(_interval(0.0013, 0.0009, 0.0019), 0.001254, 0.01).clause == "first"
    assert read_bag(_interval(0.003, 0.0020, 0.004), 0.001254, 0.01).clause == "second"
    assert read_bag(_interval(0.001, 0.0008, 0.0011), 0.001254, 0.01).clause == "neither"
