"""The shipped H1 configs are ADR-0025's, and restate their sources value for value."""

from __future__ import annotations

import re
from pathlib import Path

from faultline.config import load_config
from faultline.evaluation.axis_gate import AxisGateConfig
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.h1_gate import H1ArmsConfig, H1GateConfig
from faultline.evaluation.paired_control import PairedControlConfig
from faultline.evaluation.seed_replication import SeedReplicationConfig
from faultline.training.mixture import JointMixtureConfig

REPO = Path(__file__).resolve().parents[2]
JOINT_V0 = REPO / "configs/train/joint_v0.yaml"
JOINT_V1 = REPO / "configs/train/joint_v1.yaml"
ARMS = REPO / "configs/train/h1_arms_v0.yaml"
GATE = REPO / "configs/train/gate_check_v0.yaml"
H1 = REPO / "configs/eval/h1_gate_v0.yaml"
HEADING = "## ADR-0025 H1: the joint arm against `tel_only`, forward-in-time on the training sites"


def _adr_0025() -> str:
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert decisions.count(HEADING) == 1
    return decisions[decisions.index(HEADING) :]


def test_each_config_loads_under_its_strict_schema() -> None:
    assert load_config(JOINT_V1, JointMixtureConfig).version == 1
    assert load_config(ARMS, H1ArmsConfig).version == 0
    assert load_config(H1, H1GateConfig).version == 0


def test_joint_v1_has_one_default_arm_and_no_txt_only() -> None:
    v1 = load_config(JOINT_V1, JointMixtureConfig)
    v0 = load_config(JOINT_V0, JointMixtureConfig)
    assert [arm.name for arm in v1.arms if arm.role == "default"] == ["joint"]
    assert {arm.name for arm in v1.arms} == {"joint", "tel_only"}
    # joint_status_raw is deferred to F7 (ADR-0025 §1); txt_only is not an arm at all.
    assert all(arm.name not in {"txt_only", "joint_status_raw"} for arm in v1.arms)
    # Only the arm list moved: every carried arm and every other value is joint_v0's.
    carried = {arm.name: arm for arm in v0.arms}
    for arm in v1.arms:
        assert arm == carried[arm.name]
    joint = next(arm for arm in v1.arms if arm.name == "joint")
    assert joint.mixture == {"tel": 0.30, "txt": 0.20, "tel+status": 0.50}
    assert joint.status_convention == "normalized"
    same = v0.model_dump(exclude={"version", "arms"})
    assert v1.model_dump(exclude={"version", "arms"}) == same


def test_the_runners_optimiser_block_is_the_gate_runs() -> None:
    arms = load_config(ARMS, H1ArmsConfig)
    gate = load_config(GATE, GateCheckConfig)
    assert arms.gate_config == "configs/train/gate_check_v0.yaml"
    assert arms.optimiser.model_dump() == gate.model_dump(
        include={"batch_windows", "accumulate", "learning_rate", "evaluations", "selection_windows"}
    )
    assert (arms.tokens, arms.rung, arms.ladder_config) == (
        gate.tokens,
        gate.rung,
        gate.ladder_config,
    )
    mixture = load_config(REPO / arms.mixture_config, JointMixtureConfig)
    budget = gate.budget(mixture.context_tokens)
    assert budget.windows * mixture.context_tokens == 50_003_968  # 763 x 32 x 2,048
    assert arms.mixture_config == "configs/train/joint_v1.yaml"
    assert [arm.role for arm in mixture.arms if arm.name == arms.arm] == ["default"]


def test_the_runners_seeds_probe_and_index_are_the_protocol_in_force() -> None:
    arms = load_config(ARMS, H1ArmsConfig)
    gate = load_config(GATE, GateCheckConfig)
    replication = load_config(
        REPO / "configs/train/seed_replication_v0.yaml", SeedReplicationConfig
    )
    axis = load_config(REPO / "configs/eval/axis_gate_v0.yaml", AxisGateConfig)
    paired = load_config(REPO / "configs/train/paired_control_v0.yaml", PairedControlConfig)
    assert arms.seeds == [gate.seed, *replication.new_seeds] == [1, 2, 3]
    probe = arms.probe
    assert probe.design == replication.design == "final_position"
    assert probe.cadence_config == replication.cadence_config
    assert probe.checkpoint == axis.checkpoints.gating == "final_step"
    assert probe.label == axis.label
    assert (probe.window_rule, probe.status_rows, probe.context_tokens) == (
        "tail_anchored_2048",
        "all",
        2048,
    )
    selection = probe.selection
    assert selection.shard_keys == ["kelmarsh__val", "penmanshiel__val"]
    assert (selection.windows_per_source, selection.stride, selection.seed) == (3000, 1, 20260912)
    index, temporal = arms.window_index, axis.axes.temporal
    assert index.test_shard_keys == temporal.shard_keys
    assert index.test_stride == paired.stride == axis.stride == 12
    assert (index.test_windows, index.test_positives) == (temporal.windows, temporal.positives)
    assert (index.test_windows, index.test_positives) == (137025, 5312)
    assert (index.train_stride, index.train_windows, index.train_positives) == (6, 749387, 16524)


def test_the_h1_bootstrap_is_the_gate_runs() -> None:
    h1 = load_config(H1, H1GateConfig)
    gate = load_config(GATE, GateCheckConfig)
    axis = load_config(REPO / h1.axis_config, AxisGateConfig)
    assert h1.bootstrap == gate.bootstrap == axis.bootstrap
    assert (h1.stride, h1.label) == (axis.stride, axis.label)
    assert (h1.windows, h1.positives) == (axis.axes.temporal.windows, axis.axes.temporal.positives)
    assert h1.runner_config == "configs/train/h1_arms_v0.yaml"
    assert h1.comparison.seeds == load_config(ARMS, H1ArmsConfig).seeds


def test_the_h1_rule_is_adr_0025s_by_value() -> None:
    h1 = load_config(H1, H1GateConfig)
    rule = h1.rule
    assert rule.smallest_effect == 0.005
    assert rule.supported_lower_bound_above == 0.0
    assert rule.supported_median_above == rule.refuted_upper_bound_below == rule.smallest_effect
    assert rule.otherwise == "inconclusive"
    comparison = h1.comparison
    assert (comparison.arm, comparison.reference, comparison.windows) == ("joint", "tel_only", "R0")
    assert h1.reported_variants == ["R2", "strata_has_status", "strata_no_status"]
    assert len(h1.controls) == 3
    adr = _adr_0025()
    assert "Smallest effect of\n> interest: 0.005 AUPRC." in adr
    assert "The verdict is read on R0 only" in adr


def test_the_registration_hash_is_pending_or_recorded_in_adr_0025() -> None:
    registered = load_config(H1, H1GateConfig).registered_in
    assert registered == "pending" or re.fullmatch(r"[0-9a-f]{7,40}", registered)
    head = _adr_0025()[: _adr_0025().index("\n### ")]
    assert f"`{registered}`" in head
