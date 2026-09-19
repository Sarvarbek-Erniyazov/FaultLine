"""The shipped read-out config is ADR-0026's, and restates its sources value for value."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import torch

from faultline.config import load_config
from faultline.evaluation.axis_gate import AxisGateConfig
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.h1_gate import H1ArmsConfig, H1GateConfig
from faultline.evaluation.readout import (
    READOUT_HEAD_LAYERS,
    READOUT_NAMES,
    READOUT_POOLING,
    READOUT_UNFROZEN_BLOCKS,
    ReadoutConfig,
    risk_spec,
)
from faultline.model.risk import RiskModel, RiskSpec, TextPositionRule
from faultline.model.transformer import ModelSpec
from faultline.tokenizers.layout import SPECIAL_TOKENS, TEXT_CAPACITY, TEXT_OFFSET
from faultline.training.config import LadderConfig, LadderModel

REPO = Path(__file__).resolve().parents[2]
READOUT = REPO / "configs/eval/readout_v0.yaml"
GATE = REPO / "configs/train/gate_check_v0.yaml"
ARMS = REPO / "configs/train/h1_arms_v0.yaml"
H1 = REPO / "configs/eval/h1_gate_v0.yaml"
LADDER = REPO / "configs/train/telemetry_v1.yaml"
MODEL = REPO / "configs/model/ladder_v0.yaml"
#: The read-outs in the order ADR-0026 §2 defines them: (a), (b), (d).
READOUT_NAMES_IN_ORDER = ("final_position", "mean_all", "last_plus_text")
HEADING = (
    "## ADR-0026 F7': is the read-out the limit? "
    "Text-aware linear probes on the existing joint backbones"
)


def _adr_0026() -> str:
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert decisions.count(HEADING) == 1
    return decisions[decisions.index(HEADING) :]


def _flat(text: str) -> str:
    """One line of prose: quote markers, emphasis and line breaks removed."""
    lines = [re.sub(r"^\s*>\s?", "", line) for line in text.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines).replace("*", "").replace("`", "")).strip()


def _blockquote(after: str) -> str:
    """The first ``>`` block of ADR-0026 following a marker, flattened."""
    adr = _adr_0026()
    body = adr[adr.index(after) + len(after) :]
    quoted: list[str] = []
    for line in body.splitlines():
        if line.startswith(">"):
            quoted.append(line)
        elif quoted:
            break
    assert quoted, f"no blockquote after {after!r}"
    return _flat("\n".join(quoted))


def test_the_config_loads_under_its_strict_schema() -> None:
    assert load_config(READOUT, ReadoutConfig).version == 0


def test_the_bootstrap_and_the_split_are_the_ones_in_force() -> None:
    readout = load_config(READOUT, ReadoutConfig)
    gate = load_config(GATE, GateCheckConfig)
    axis = load_config(REPO / readout.axis_config, AxisGateConfig)
    h1 = load_config(H1, H1GateConfig)
    assert readout.bootstrap == gate.bootstrap == axis.bootstrap == h1.bootstrap
    assert (readout.stride, readout.label, readout.axis) == (axis.stride, axis.label, "temporal")
    temporal = axis.axes.temporal
    assert (readout.windows, readout.positives) == (temporal.windows, temporal.positives)
    assert (readout.windows, readout.positives) == (137025, 5312)
    assert readout.h1_gate_config == "configs/eval/h1_gate_v0.yaml"
    assert readout.arms_config == "configs/train/h1_arms_v0.yaml"
    assert readout.random_init_config == "configs/train/probe_control_v0.yaml"


def test_the_probe_protocol_is_the_one_in_force() -> None:
    readout = load_config(READOUT, ReadoutConfig)
    arms = load_config(ARMS, H1ArmsConfig)
    ladder = load_config(LADDER, LadderConfig)
    model = load_config(MODEL, LadderModel)
    probe = readout.probe
    assert probe.cadence_config == arms.probe.cadence_config
    assert probe.checkpoint == arms.probe.checkpoint == "final_step"
    assert probe.window_rule == arms.probe.window_rule == "tail_anchored_2048"
    assert probe.status_rows == arms.probe.status_rows == "all"
    assert probe.context_tokens == arms.probe.context_tokens == 2048
    assert probe.selection == arms.probe.selection
    assert probe.head_hidden == model.head_hidden
    assert probe.learning_rate == ladder.risk.probe.learning_rate
    assert probe.train_stride == ladder.train_stride
    assert (probe.sampling, ladder.risk.sampling) == ("balanced", "balanced")
    assert readout.label == arms.probe.label


def test_the_readouts_are_exactly_adr_0026s_three() -> None:
    readout = load_config(READOUT, ReadoutConfig)
    assert readout.readout_names == set(READOUT_NAMES)
    assert readout.readout_names == {"final_position", "mean_all", "last_plus_text"}
    names = ("final_position", "mean_all", "last_plus_text")
    final, mean, text_aware = (readout.readout(name) for name in names)
    # (a) is the probe in force and is not re-run; (b) and (d) are new.
    assert (final.in_force, mean.in_force, text_aware.in_force) == (True, False, False)
    assert (final.pooling, final.d_model_blocks, final.scalars) == ("last_real", 1, 0)
    assert (mean.pooling, mean.d_model_blocks, mean.scalars) == ("mean_real", 1, 0)
    assert text_aware.pooling == "last_real_plus_text_mean"
    # (d): [last real state; mean over text positions; has-text indicator] = 2 d_model + 1.
    assert (text_aware.d_model_blocks, text_aware.scalars) == (2, 1)
    assert text_aware.head_input_width(192) == 2 * 192 + 1
    assert [r.text_block for r in (final, mean, text_aware)] == [False, False, True]
    # Only (d) carries a text block, and only (d) needs the text-position definition.
    positions = readout.text_positions
    assert positions.special_ids == [SPECIAL_TOKENS.index("<txt>"), SPECIAL_TOKENS.index("</txt>")]
    assert positions.min_id == TEXT_OFFSET == 1184
    assert positions.min_id + TEXT_CAPACITY == 33952
    assert positions.empty_window == "zero_vector"


def test_the_runs_are_adr_0026s_four_with_three_seeds_each() -> None:
    readout = load_config(READOUT, ReadoutConfig)
    arms = load_config(ARMS, H1ArmsConfig)
    assert [(run.name, run.readout, run.backbone) for run in readout.runs] == [
        ("R-joint-b", "mean_all", "joint"),
        ("R-joint-d", "last_plus_text", "joint"),
        ("R-ctrl-d", "last_plus_text", "tel_only"),
        ("R-rand-d", "last_plus_text", "random_init"),
    ]
    assert all(run.seeds == [1, 2, 3] == arms.seeds for run in readout.runs)
    assert readout.probes == 12
    # No run names final_position: the probe in force is a reference, never re-trained (§2).
    assert all(run.readout != "final_position" for run in readout.runs)
    # Nothing is pretrained: every backbone family already exists on disk (§3).
    assert {run.backbone for run in readout.runs} == {"joint", "tel_only", "random_init"}


def test_the_h1_prime_rule_is_adr_0026s_by_value() -> None:
    rule = load_config(READOUT, ReadoutConfig).rule
    clause = _blockquote("**H1' — this decides.**")
    assert rule.smallest_effect == float(
        re.search(r"Smallest effect of interest: ([0-9.]+) AUPRC", clause).group(1)
    )
    assert rule.supported_median_above == float(
        re.search(r"median Δ exceeds ([0-9.]+)", clause).group(1)
    )
    assert rule.refuted_upper_bound_below == float(
        re.search(r"upper bounds are below ([0-9.]+)", clause).group(1)
    )
    assert rule.smallest_effect == rule.supported_median_above == rule.refuted_upper_bound_below
    assert "all three paired lower bounds exceed zero" in clause
    assert rule.supported_lower_bound_above == 0.0
    assert "otherwise INCONCLUSIVE at this budget" in clause
    assert rule.otherwise == "inconclusive"
    assert "discarding more than 1% of its replicates counts toward neither clause" in clause
    assert "no clause is added afterwards" in clause
    # The two sides, and the reference side unchanged from ADR-0025 §5.
    assert (rule.arm_readout, rule.arm_backbone) == ("last_plus_text", "joint")
    assert (rule.reference_readout, rule.reference_backbone) == ("final_position", "tel_only")
    assert (rule.pairing, rule.checkpoint, rule.windows) == ("same_seed", "final_step", "R0")
    h1 = load_config(H1, H1GateConfig)
    assert rule.seeds == h1.comparison.seeds
    assert rule.reference_backbone == h1.comparison.reference
    assert rule.smallest_effect == h1.rule.smallest_effect


def test_the_random_init_gate_is_adr_0026s_by_value() -> None:
    gate = load_config(READOUT, ReadoutConfig).random_init_gate
    clause = _blockquote("**The random-init gate on the instrument")
    assert "same-seed and cross-seed" in clause
    assert gate.pairing == "same_and_cross_seed"
    assert re.search(r"all nine of nine paired lower bounds strictly above zero", clause)
    assert gate.comparisons == 9 == 3 * 3  # three trained seeds x three random-init seeds
    assert gate.lower_bound_above == 0.0
    assert (gate.readout, gate.arm_backbone) == ("last_plus_text", "joint")
    assert gate.reference_backbone == "random_init"
    assert "NOT EVALUABLE" in _flat(_adr_0026())
    assert gate.on_failure == "not_evaluable"


def test_the_reported_rows_and_caveats_are_adr_0026s() -> None:
    readout = load_config(READOUT, ReadoutConfig)
    assert readout.reported == [
        "d_joint_vs_d_control",
        "b_joint_vs_a_joint",
        "d_joint_vs_status_only_bag",
        "strata_has_status",
        "strata_no_status",
        "selected_vs_final",
    ]
    assert readout.caveats == [
        "adr_0009",
        "forward_in_time_same_sites",
        "message_volume_shift",
    ]
    adr = _flat(_adr_0026())
    assert "ADR-0009" in adr and "forward in time, same sites" in adr
    assert "67.2 status tokens in train (stride 6) and 190.1 in test (stride 12)" in adr


def test_adr_0026_withdraws_the_two_f7_arms_rather_than_deferring_them() -> None:
    adr = _flat(_adr_0026())
    assert "They are withdrawn from F7, not deferred." in adr
    assert "joint_status_raw" in adr and "joint_no_txt" in adr
    assert "may be revisited only if H1' below is SUPPORTED" in adr


def test_the_registration_hash_is_pending_or_recorded_in_adr_0026() -> None:
    registered = load_config(READOUT, ReadoutConfig).registered_in
    assert registered == "pending" or re.fullmatch(r"[0-9a-f]{7,40}", registered)
    adr = _adr_0026()
    head = adr[: adr.index("\n### ")]
    assert f"`{registered}`" in head


# =====================================================================================
# the selector: one registered name, one head specification (ADR-0026 §2)
# =====================================================================================

TINY = ModelSpec(name="T", d_model=32, n_layer=2, n_head=4, context=48, vocab_size=64)


def _readout() -> ReadoutConfig:
    return load_config(READOUT, ReadoutConfig)


def _head(name: str) -> RiskSpec:
    model = load_config(MODEL, LadderModel)
    config = _readout()
    return risk_spec(config, name, model.head_hidden, model.head_dropout, config.label)


def test_the_selector_builds_each_registered_read_out_by_name() -> None:
    config = _readout()
    final, mean, text_aware = (_head(name) for name in READOUT_NAMES_IN_ORDER)
    assert (final.pooling, mean.pooling) == ("last", "mean")
    assert text_aware.pooling == "last_plus_text"
    # Only (d) carries the text-position rule, and it carries the configuration's values.
    assert (final.text_positions, mean.text_positions) == (None, None)
    assert text_aware.text_positions == TextPositionRule(
        special_ids=tuple(config.text_positions.special_ids), min_id=config.text_positions.min_id
    )
    assert text_aware.text_positions is not None
    assert text_aware.text_positions.special_ids == (4, 5)
    assert text_aware.text_positions.min_id == 1184
    # Every read-out is a linear head over a frozen backbone: one hidden layer, no unfrozen block.
    assert {spec.layers for spec in (final, mean, text_aware)} == {1}
    assert (READOUT_HEAD_LAYERS, READOUT_UNFROZEN_BLOCKS) == (1, 0)
    assert set(READOUT_POOLING) == set(READOUT_NAMES)


def test_the_selector_builds_the_width_the_configuration_registers() -> None:
    config = _readout()
    for name in READOUT_NAMES_IN_ORDER:
        registered = config.readout(name)
        for d_model in (32, 192):
            built = _head(name).input_width(d_model)
            assert built == registered.head_input_width(d_model)
            assert built == registered.d_model_blocks * d_model + registered.scalars
    assert _head("last_plus_text").input_width(192) == 385


def test_the_selector_refuses_a_read_out_it_does_not_register() -> None:
    with pytest.raises(KeyError, match="no read-out named"):
        _head("mlp_mean_pooled")


def test_a_final_position_probe_through_the_selector_is_the_probe_in_force() -> None:
    # The head in force is built from RiskSpec(pooling="last"). Selecting "final_position" by
    # name must build that module, parameter for parameter and random number for random number,
    # and score a fixed window to the same bits -- or every number H1 read would move under a
    # change that is meant to add read-outs beside it, not alter it.
    model = load_config(MODEL, LadderModel)
    in_force = RiskSpec(
        hidden=model.head_hidden,
        dropout=model.head_dropout,
        label=_readout().label,
        pooling="last",
        layers=1,
    )
    selected = _head("final_position")
    assert selected == in_force
    torch.manual_seed(11)
    before = RiskModel(TINY, in_force, frozen=True, pad_id=0).eval()
    torch.manual_seed(11)
    after = RiskModel(TINY, selected, frozen=True, pad_id=0).eval()
    states = (before.state_dict(), after.state_dict())
    assert list(states[0]) == list(states[1])
    assert all(torch.equal(states[0][k], states[1][k]) for k in states[0])
    window = torch.cat(
        [torch.randint(1, 64, (2, 30)), torch.zeros((2, 18), dtype=torch.long)], dim=1
    )
    with torch.no_grad():
        assert torch.equal(before.pool(window), after.pool(window))
        assert torch.equal(before(window), after(window))
