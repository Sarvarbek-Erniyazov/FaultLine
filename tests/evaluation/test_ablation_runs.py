"""F8-1: the F8-2 runner's plan, layout and pre-flight, and ADR-0027's three registered assertions.

The three assertions of ADR-0027 §2, §3 and §4 are tested hard, on both sides: each passes on the
shipped configuration and on a faithful synthetic index, and each **raises** on the specific defect
it exists to catch. Everything else here is plumbing -- that the plan is the nine items in the
registered order, that the layout names the files the record names, and that the pre-flight refuses
what is missing.

Nothing in this module trains, scores or reads a shard.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from faultline.config import load_config
from faultline.evaluation.ablation_gate import AblationArmsConfig, AblationGateConfig
from faultline.evaluation.ablation_runs import (
    ABLATION_FAMILY,
    RANDOM_FAMILY,
    AblationItem,
    ArmPretraining,
    assert_random_init_reads_raw,
    assert_raw_index_matches_normalized,
    assert_registered_truncation,
    assert_sampler_counts,
    probe_plan,
    realised_stream_windows,
)
from faultline.evaluation.h1_gate import H1ArmsConfig
from faultline.training.joint_windows import JointWindowSet
from faultline.training.mixture import JointMixtureConfig

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "configs/eval/ablation_gate_v0.yaml"
ARMS = REPO / "configs/train/ablation_arms_v0.yaml"
MIXTURE = REPO / "configs/train/joint_v2.yaml"
H1_ARMS = REPO / "configs/train/h1_arms_v0.yaml"


def _configs() -> tuple[AblationArmsConfig, JointMixtureConfig, AblationGateConfig]:
    return (
        load_config(ARMS, AblationArmsConfig),
        load_config(MIXTURE, JointMixtureConfig),
        load_config(GATE, AblationGateConfig),
    )


def _window_set(
    key: str, ends: np.ndarray, labels: np.ndarray, steps: np.ndarray, head_cut: np.ndarray | None
) -> JointWindowSet:
    """A framed window set with only the fields the index assertion reads."""
    size = ends.size
    return JointWindowSet(
        key=key,
        tokens=np.zeros(0, np.uint16),
        starts=ends - 143,
        ends=ends,
        labels=labels,
        years=np.full(size, 2022, np.int64),
        context=2048,
        first=np.zeros(size, np.int64),
        length=np.full(size, 2048, np.int64),
        steps_retained=steps,
        head_cut=np.zeros(size, bool) if head_cut is None else head_cut,
        status_tokens=np.zeros(size, np.int64),
    )


def _pair(
    normalized_steps: np.ndarray, raw_steps: np.ndarray, labels: np.ndarray
) -> tuple[list[JointWindowSet], list[JointWindowSet]]:
    """One shard key, framed twice: same keys and labels, possibly different truncation."""
    ends = np.arange(143, 143 + labels.size, dtype=np.int64)
    return (
        [_window_set("kelmarsh__test", ends, labels, normalized_steps, None)],
        [_window_set("kelmarsh__test", ends, labels, raw_steps, None)],
    )


# =====================================================================================
# assertion 1 (ADR-0027 §2): the sampler's realised counts
# =====================================================================================


def test_the_schedule_hits_the_registered_counts_for_every_arm() -> None:
    runner, mixture, _ = _configs()
    budget = runner.token_budget
    for arm in mixture.arms:
        windows = realised_stream_windows(arm, budget.windows)
        assert sum(windows.values()) == budget.windows
        assert windows["tel+status"] * budget.context_tokens == budget.paired_tel_status_tokens
    by_name = {arm.name: arm for arm in mixture.arms}
    assert realised_stream_windows(by_name["joint"], budget.windows) == {
        "tel": 7_325,
        "txt": 4_883,
        "tel+status": 12_208,
    }
    assert realised_stream_windows(by_name["joint_no_txt"], budget.windows) == {
        "tel": 12_208,
        "tel+status": 12_208,
    }
    # The raw arm differs from joint in the convention alone, so its schedule is joint's.
    assert realised_stream_windows(by_name["joint_status_raw"], budget.windows) == (
        realised_stream_windows(by_name["joint"], budget.windows)
    )


def test_the_sampler_assertion_passes_on_every_shipped_arm() -> None:
    runner, mixture, _ = _configs()
    budget = runner.token_budget
    for name in (runner.reference_arm, *runner.arms):
        tokens = assert_sampler_counts(runner, mixture, name)
        assert sum(tokens.values()) == budget.total_tokens == 50_003_968
        assert tokens["tel+status"] == budget.paired_tel_status_tokens == 25_001_984
    # The equality across arms is the point: the ablation must not change status exposure.
    paired = {
        name: assert_sampler_counts(runner, mixture, name)["tel+status"]
        for name in (runner.reference_arm, *runner.arms)
    }
    assert len(set(paired.values())) == 1, paired


def test_the_sampler_assertion_accepts_a_matching_realised_draw() -> None:
    runner, mixture, _ = _configs()
    drawn = realised_stream_windows(
        next(a for a in mixture.arms if a.name == "joint_no_txt"), runner.token_budget.windows
    )
    assert_sampler_counts(runner, mixture, "joint_no_txt", drawn=dict(drawn))
    # A zero-count stream in the record is ignored, not treated as a disagreement.
    assert_sampler_counts(runner, mixture, "joint_no_txt", drawn={**drawn, "txt": 0})


def test_a_proportionally_renormalised_no_txt_arm_is_refused() -> None:
    """The defect this assertion exists to catch: the ablation silently adds status."""
    runner, mixture, _ = _configs()
    confounded = mixture.model_copy(
        update={
            "arms": [
                arm.model_copy(update={"mixture": {"tel": 0.375, "tel+status": 0.625}})
                if arm.name == "joint_no_txt"
                else arm
                for arm in mixture.arms
            ]
        }
    )
    with pytest.raises(ValueError, match="paired tel\\+status exposure"):
        assert_sampler_counts(runner, confounded, "joint_no_txt")
    # And it is caught because the exposure rises to what ADR-0027 §2 names.
    arm = next(a for a in confounded.arms if a.name == "joint_no_txt")
    windows = realised_stream_windows(arm, runner.token_budget.windows)
    raised = windows["tel+status"] * runner.token_budget.context_tokens
    assert raised == runner.token_budget.proportional_tel_status_tokens == 31_252_480


def test_a_drifted_realised_draw_is_refused() -> None:
    runner, mixture, _ = _configs()
    drawn = realised_stream_windows(
        next(a for a in mixture.arms if a.name == "joint_no_txt"), runner.token_budget.windows
    )
    off_by_one = {**drawn, "tel": drawn["tel"] + 1, "tel+status": drawn["tel+status"] - 1}
    with pytest.raises(ValueError, match="the sampler drew"):
        assert_sampler_counts(runner, mixture, "joint_no_txt", drawn=off_by_one)


def test_an_unknown_arm_is_refused() -> None:
    runner, mixture, _ = _configs()
    with pytest.raises(ValueError, match="is not an arm of"):
        assert_sampler_counts(runner, mixture, "tel_only")


# =====================================================================================
# assertion 2 (ADR-0027 §3): the raw index is the normalized index, re-framed
# =====================================================================================


def test_the_index_assertion_passes_when_only_truncation_differs() -> None:
    labels = np.array([0, 1, 0, 1, 0], dtype=np.float32)
    normalized = np.array([144, 144, 140, 144, 138], dtype=np.int64)
    raw = np.array([144, 142, 140, 141, 138], dtype=np.int64)  # two windows retain fewer steps
    left, right = _pair(normalized, raw, labels)
    measured = assert_raw_index_matches_normalized(left, right, windows=5, positives=2)
    assert measured == {
        "windows": 5,
        "positives": 2,
        "windows_differing_in_steps_retained": 2,
        "positives_differing_in_steps_retained": 2,
    }


def test_the_index_assertion_counts_the_shipped_measurement_shape() -> None:
    """Identical truncation is allowed too, and is reported as zero differing."""
    labels = np.array([0, 1, 0], dtype=np.float32)
    steps = np.array([144, 143, 144], dtype=np.int64)
    left, right = _pair(steps, steps.copy(), labels)
    measured = assert_raw_index_matches_normalized(left, right, windows=3, positives=1)
    assert measured["windows_differing_in_steps_retained"] == 0
    assert measured["positives_differing_in_steps_retained"] == 0


@pytest.mark.parametrize("field_name", ["ends", "labels", "years", "starts"])
def test_an_index_that_differs_in_keys_or_labels_is_refused(field_name: str) -> None:
    labels = np.array([0, 1, 0], dtype=np.float32)
    steps = np.array([144, 144, 144], dtype=np.int64)
    left, right = _pair(steps, steps.copy(), labels)
    moved = getattr(right[0], field_name).copy()
    moved[1] += 1
    setattr(right[0], field_name, moved)
    with pytest.raises(ValueError, match=f"differ in {field_name}"):
        assert_raw_index_matches_normalized(left, right, windows=3, positives=1)


def test_a_different_shard_key_is_refused() -> None:
    labels = np.array([0, 1], dtype=np.float32)
    steps = np.array([144, 144], dtype=np.int64)
    left, right = _pair(steps, steps.copy(), labels)
    right[0].key = "penmanshiel__test"
    with pytest.raises(ValueError, match="shard keys differ"):
        assert_raw_index_matches_normalized(left, right, windows=2, positives=1)


def test_a_head_cut_that_appears_only_under_raw_is_refused() -> None:
    labels = np.array([0, 1], dtype=np.float32)
    ends = np.array([143, 144], dtype=np.int64)
    steps = np.array([144, 144], dtype=np.int64)
    left = [_window_set("kelmarsh__test", ends, labels, steps, np.array([False, False]))]
    right = [_window_set("kelmarsh__test", ends, labels, steps, np.array([False, True]))]
    with pytest.raises(ValueError, match="head-cut flags differ"):
        assert_raw_index_matches_normalized(left, right, windows=2, positives=1)


def test_counts_that_are_not_the_registered_ones_are_refused() -> None:
    labels = np.array([0, 1, 0], dtype=np.float32)
    steps = np.array([144, 144, 144], dtype=np.int64)
    left, right = _pair(steps, steps.copy(), labels)
    with pytest.raises(ValueError, match="the registered counts are 137025"):
        assert_raw_index_matches_normalized(left, right, windows=137_025, positives=5_312)


def test_a_missing_shard_set_is_refused() -> None:
    labels = np.array([0, 1], dtype=np.float32)
    steps = np.array([144, 144], dtype=np.int64)
    left, right = _pair(steps, steps.copy(), labels)
    with pytest.raises(ValueError, match="window sets against"):
        assert_raw_index_matches_normalized(left, [], windows=2, positives=1)


def test_the_registered_truncation_must_be_the_measured_truncation() -> None:
    runner, _, _ = _configs()
    rule = runner.window_rule("joint_status_raw")
    measured = {
        "windows_differing_in_steps_retained": rule.windows_differing_in_steps_retained,
        "positives_differing_in_steps_retained": rule.positives_differing_in_steps_retained,
    }
    assert measured == {
        "windows_differing_in_steps_retained": 41_371,
        "positives_differing_in_steps_retained": 1_838,
    }
    assert_registered_truncation(runner, measured)
    for field_name in measured:
        drifted = {**measured, field_name: measured[field_name] + 1}
        with pytest.raises(ValueError, match="quote the registered number"):
            assert_registered_truncation(runner, drifted)


# =====================================================================================
# assertion 3 (ADR-0027 §4): the raw arm's gate probes read raw windows
# =====================================================================================


class _FakeStreams:
    def __init__(self, name: str) -> None:
        self.root = Path("data/shards/joint/joint_v2_d432c6d7") / name


class _FakeInputs:
    def __init__(self, name: str | None) -> None:
        self.tel_status = None if name is None else _FakeStreams(name)


def _plan_and_inputs() -> tuple[list[AblationItem], dict[str, object], AblationGateConfig]:
    runner, mixture, gate = _configs()
    plan = probe_plan(runner, mixture, gate)
    inputs = {
        "normalized": _FakeInputs("tel_status_normalized"),
        "raw": _FakeInputs("tel_status_raw"),
    }
    return plan, inputs, gate


def test_the_gate_assertion_passes_on_the_shipped_plan() -> None:
    plan, inputs, gate = _plan_and_inputs()
    lines = assert_random_init_reads_raw(plan, inputs, gate)  # type: ignore[arg-type]
    assert len(lines) == 3
    assert all("tel_status_raw" in line for line in lines)
    assert all("gates joint_status_raw" in line for line in lines)
    # joint_no_txt gets no gate probe: ADR-0026 already gated those windows.
    assert not any("joint_no_txt" in line for line in lines)


def test_a_gate_probe_framed_over_normalized_windows_is_refused() -> None:
    plan, inputs, gate = _plan_and_inputs()
    wrong = {**inputs, "raw": _FakeInputs("tel_status_normalized")}
    with pytest.raises(ValueError, match="not a gate"):
        assert_random_init_reads_raw(plan, wrong, gate)  # type: ignore[arg-type]


def test_a_gate_probe_with_no_opened_inputs_is_refused() -> None:
    plan, inputs, gate = _plan_and_inputs()
    with pytest.raises(ValueError, match="no opened tel\\+status inputs"):
        assert_random_init_reads_raw(plan, {"normalized": inputs["normalized"]}, gate)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="no opened tel\\+status inputs"):
        assert_random_init_reads_raw(plan, {**inputs, "raw": _FakeInputs(None)}, gate)  # type: ignore[arg-type]


def test_a_plan_whose_gate_probes_are_not_the_registered_ones_is_refused() -> None:
    plan, inputs, gate = _plan_and_inputs()
    short = [item for item in plan if not (item.is_random_init and item.seed == 3)]
    with pytest.raises(ValueError, match="the gate registers"):
        assert_random_init_reads_raw(short, inputs, gate)  # type: ignore[arg-type]
    extra = [*plan, AblationItem("joint_no_txt", RANDOM_FAMILY, 1, "normalized", "x")]
    with pytest.raises(ValueError, match="the gate registers"):
        assert_random_init_reads_raw(extra, inputs, gate)  # type: ignore[arg-type]


# =====================================================================================
# plumbing: the plan, the adapter, the layout and the pre-flight
# =====================================================================================


def test_the_plan_is_nine_items_in_the_registered_order() -> None:
    runner, mixture, gate = _configs()
    plan = probe_plan(runner, mixture, gate)
    assert len(plan) == 9 == runner.cost.ablation_probes + runner.cost.random_init_probes
    assert [(i.arm, i.family, i.seed) for i in plan] == [
        ("joint_status_raw", ABLATION_FAMILY, 1),
        ("joint_status_raw", ABLATION_FAMILY, 2),
        ("joint_status_raw", ABLATION_FAMILY, 3),
        ("joint_no_txt", ABLATION_FAMILY, 1),
        ("joint_no_txt", ABLATION_FAMILY, 2),
        ("joint_no_txt", ABLATION_FAMILY, 3),
        ("joint_status_raw", RANDOM_FAMILY, 1),
        ("joint_status_raw", RANDOM_FAMILY, 2),
        ("joint_status_raw", RANDOM_FAMILY, 3),
    ]
    assert [i.convention for i in plan] == ["raw"] * 3 + ["normalized"] * 3 + ["raw"] * 3
    assert len({i.name for i in plan}) == 9
    assert plan[0].name == "S2_joint_status_raw_seed1"
    assert plan[-1].name == "S2_random_init_raw_seed3"
    # Every scoring in the cost has an item, and no item is uncosted.
    assert runner.cost.scorings == len(plan)


def test_the_plan_refuses_an_arm_that_is_not_in_the_mixture() -> None:
    runner, mixture, gate = _configs()
    stray = runner.model_copy(update={"arms": ["joint_status_raw", "joint_no_status"]})
    with pytest.raises(ValueError, match="are not arms of"):
        probe_plan(stray, mixture, gate)


def test_the_pretraining_adapter_carries_joints_own_budget() -> None:
    runner, mixture, _ = _configs()
    h1 = load_config(H1_ARMS, H1ArmsConfig)
    context = mixture.context_tokens
    for arm in runner.arms:
        config = ArmPretraining(runner=runner, arm=arm)
        assert config.arm == arm
        assert config.rung == runner.rung == h1.rung
        assert config.batch_windows == runner.batch_windows
        # The budget an ablation pretrains under is the one joint pretrained under.
        assert config.budget(context) == h1.budget(context)
        assert config.budget(context).windows == runner.token_budget.windows == 24_416


def test_the_layout_names_the_files_the_record_names(tmp_path: Path) -> None:
    from faultline.evaluation.ablation_runs import ablation_layout
    from faultline.paths import ProjectPaths

    paths = ProjectPaths.resolve()
    layout = ablation_layout(paths, GATE)
    assert layout.out_dir.name.startswith("ablation_arms_v0_")
    assert layout.log_dir.name == "ablation_arms_v0_steps"
    assert layout.rung == "S2"
    assert layout.stride == 12
    assert layout.conventions() == ["raw", "normalized"]
    assert layout.arm_of("raw") == "joint_status_raw"
    assert layout.arm_of("normalized") == "joint"
    with pytest.raises(KeyError, match="no arm of"):
        layout.arm_of("titlecase")
    first, gate_probe = layout.plan[0], layout.plan[-1]
    assert layout.backbone(first).name == "S2_joint_status_raw_seed1.pt"
    assert layout.backbone(gate_probe) == layout.random_backbone(3)
    assert layout.scores(first).name == "S2_joint_status_raw_seed1_final_R0_stride12_scores.npz"
    assert layout.probe(first).name == "S2_joint_status_raw_seed1_final_probe.pt"
    assert layout.probe(first, role="selected").name == "S2_joint_status_raw_seed1_probe.pt"
    assert layout.lm_record("joint_no_txt", 2).name == "S2_joint_no_txt_seed2_lm.json"
    # The reference side is F7'-2's R-joint-d scores, and this record never writes them.
    reference = layout.reference_scores(1)
    assert reference.name == "S2_R-joint-d_seed1_final_R0_stride12_scores.npz"
    assert reference.parent == layout.reference_dir != layout.out_dir
    assert tmp_path.exists()  # the layout touches no directory of its own


def test_the_preflight_requires_the_reference_scores_and_both_streams() -> None:
    from faultline.evaluation.ablation_runs import ablation_layout, preflight
    from faultline.paths import ProjectPaths

    paths = ProjectPaths.resolve()
    layout = ablation_layout(paths, GATE)
    problems, lines = preflight(paths, layout)
    # Six pretraining lines, nine probe lines, nine scoring lines.
    assert len(lines) == 6 + 9 + 9
    assert lines[0].startswith("pretrain joint_status_raw seed 1")
    # On a machine with no GPU the only expected problem is CUDA; shards and scores are on disk.
    assert [p for p in problems if not p.startswith("CUDA")] == []
    assert any("raw" in line and "windows" in line for line in lines)
