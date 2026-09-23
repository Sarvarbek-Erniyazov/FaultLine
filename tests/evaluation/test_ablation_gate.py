"""The shipped F8 configs are ADR-0027's, and restate their sources value for value."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from faultline.config import load_config
from faultline.evaluation.ablation_gate import (
    ABLATION_READOUT,
    ABLATION_VERDICTS,
    AblationArmsConfig,
    AblationGateConfig,
    AblationRule,
    AblationSentence,
    ArmWindowRule,
    RandomInitSource,
    StatusOnlyBag,
    TokenBudget,
)
from faultline.evaluation.axis_gate import AxisGateConfig
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.h1_gate import H1ArmsConfig, H1GateConfig
from faultline.evaluation.readout import ReadoutConfig
from faultline.training.config import LadderConfig, LadderModel
from faultline.training.joint_windows import mixture_schedule
from faultline.training.mixture import STREAMS, JointMixtureConfig

REPO = Path(__file__).resolve().parents[2]
MIXTURE = REPO / "configs/train/joint_v2.yaml"
JOINT_V1 = REPO / "configs/train/joint_v1.yaml"
ARMS = REPO / "configs/train/ablation_arms_v0.yaml"
GATE = REPO / "configs/eval/ablation_gate_v0.yaml"
GATE_CHECK = REPO / "configs/train/gate_check_v0.yaml"
H1_ARMS = REPO / "configs/train/h1_arms_v0.yaml"
H1 = REPO / "configs/eval/h1_gate_v0.yaml"
READOUT = REPO / "configs/eval/readout_v0.yaml"
LADDER = REPO / "configs/train/telemetry_v1.yaml"
MODEL = REPO / "configs/model/ladder_v0.yaml"
HEADING = (
    "## ADR-0027 The two ablations: does the narrative corpus matter, and does status-string "
    "surface form matter, to the text signal read-out (d) harvests?"
)
#: The two ablations, in the order joint_v2.yaml lists them.
ABLATIONS = ("joint_status_raw", "joint_no_txt")


def _adr_0027() -> str:
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert decisions.count(HEADING) == 1
    return decisions[decisions.index(HEADING) :]


def _flat(text: str) -> str:
    """One line of prose: quote markers, emphasis and line breaks removed."""
    lines = [re.sub(r"^\s*>\s?", "", line) for line in text.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines).replace("*", "").replace("`", "")).strip()


def _blockquote(after: str) -> str:
    """The first ``>`` block of ADR-0027 following a marker, flattened."""
    adr = _adr_0027()
    body = adr[adr.index(after) + len(after) :]
    quoted: list[str] = []
    for line in body.splitlines():
        if line.startswith(">"):
            quoted.append(line)
        elif quoted:
            break
    assert quoted, f"no blockquote after {after!r}"
    return _flat("\n".join(quoted))


# =====================================================================================
# each file loads strictly
# =====================================================================================


def test_the_three_configs_load_under_their_strict_schemas() -> None:
    assert load_config(MIXTURE, JointMixtureConfig).version == 2
    assert load_config(ARMS, AblationArmsConfig).version == 0
    assert load_config(GATE, AblationGateConfig).version == 0


def test_an_unknown_key_is_refused_by_every_schema() -> None:
    for path, schema in ((ARMS, AblationArmsConfig), (GATE, AblationGateConfig)):
        with pytest.raises(ValidationError):
            schema.model_validate({**load_config(path, schema).model_dump(), "extra": 1})


# =====================================================================================
# §2: the arms, and the re-weighting the ablation exists to keep honest
# =====================================================================================


def test_joint_v2_holds_the_three_arms_adr_0027_registers() -> None:
    mixture = load_config(MIXTURE, JointMixtureConfig)
    assert [(arm.name, arm.role) for arm in mixture.arms] == [
        ("joint", "default"),
        ("joint_status_raw", "ablation"),
        ("joint_no_txt", "ablation"),
    ]
    by_name = {arm.name: arm for arm in mixture.arms}
    assert by_name["joint"].mixture == {"tel": 0.30, "txt": 0.20, "tel+status": 0.50}
    assert by_name["joint_status_raw"].mixture == by_name["joint"].mixture
    assert by_name["joint_status_raw"].status_convention == "raw"
    assert by_name["joint_no_txt"].mixture == {"tel": 0.50, "tel+status": 0.50}
    assert by_name["joint_no_txt"].status_convention == "normalized"
    # tel_only is not carried into v2: F8 compares each ablation with joint (§2).
    assert "tel_only" not in by_name


def test_every_mixture_sums_to_one() -> None:
    # The schema enforces it; this asserts the shipped file actually exercises that path.
    for arm in load_config(MIXTURE, JointMixtureConfig).arms:
        assert sum(arm.mixture.values()) == pytest.approx(1.0, abs=1e-9)


def test_joint_v2_keeps_joint_v1s_arm_and_everything_around_it() -> None:
    v1, v2 = (load_config(path, JointMixtureConfig) for path in (JOINT_V1, MIXTURE))
    old = next(arm for arm in v1.arms if arm.name == "joint")
    new = next(arm for arm in v2.arms if arm.name == "joint")
    # joint is not retrained, so its mixture must be the one it WAS pretrained under (§2).
    assert (new.mixture, new.status_convention) == (old.mixture, old.status_convention)
    for field in (
        "telemetry_tokenizer_config",
        "text_shards_config",
        "status_sources",
        "training_sources",
        "context_tokens",
        "window_stride_steps",
        "tokens_per_arm",
    ):
        assert getattr(v2, field) == getattr(v1, field), field
    assert (v1.version, v2.version) == (1, 2)


def test_joint_no_txts_paired_exposure_equals_joint_v1_joints_to_the_token() -> None:
    """The re-weighting's whole purpose: removing the narrative must not add status (§2)."""
    v1, v2 = (load_config(path, JointMixtureConfig) for path in (JOINT_V1, MIXTURE))
    budget = load_config(ARMS, AblationArmsConfig).token_budget
    reference = next(arm for arm in v1.arms if arm.name == "joint")
    shares = {
        arm.name: {s: arm.share(s) for s in STREAMS if arm.share(s)} for arm in [*v1.arms, *v2.arms]
    }

    def paired(name: str) -> int:
        schedule = mixture_schedule(shares[name], budget.windows)
        index = list(STREAMS).index("tel+status")
        return int((schedule == index).sum()) * budget.context_tokens

    v1_joint = paired("joint")
    assert v1_joint == budget.paired_tel_status_tokens == 25_001_984
    for arm in ABLATIONS:
        assert paired(arm) == v1_joint, arm
    # And the narrative share really did move to plain telemetry, not proportionally.
    no_txt = next(arm for arm in v2.arms if arm.name == "joint_no_txt")
    assert no_txt.share("txt") == 0.0
    assert no_txt.share("tel") == reference.share("tel") + reference.share("txt") == 0.50
    assert no_txt.share("tel+status") == reference.share("tel+status") == 0.50


def test_proportional_renormalisation_would_have_confounded_the_ablation() -> None:
    budget = load_config(ARMS, AblationArmsConfig).token_budget
    proportional = {"tel": 0.30 / 0.80, "tel+status": 0.50 / 0.80}
    assert proportional["tel+status"] == pytest.approx(0.625)
    schedule = mixture_schedule(proportional, budget.windows)
    windows = int((schedule == list(STREAMS).index("tel+status")).sum())
    assert windows * budget.context_tokens == budget.proportional_tel_status_tokens
    assert budget.proportional_tel_status_tokens == 31_252_480
    # ~31.25M against 25,001,984: the confound ADR-0027 §2 names, in tokens.
    assert budget.proportional_tel_status_tokens - budget.paired_tel_status_tokens == 6_250_496


def test_the_token_budget_is_the_one_joint_pretrained_under() -> None:
    arms = load_config(ARMS, AblationArmsConfig)
    h1 = load_config(H1_ARMS, H1ArmsConfig)
    mixture = load_config(MIXTURE, JointMixtureConfig)
    assert arms.tokens == h1.tokens == mixture.tokens_per_arm == 50_000_000
    assert arms.budget(mixture.context_tokens) == h1.budget(mixture.context_tokens)
    budget = arms.token_budget
    assert budget.windows == arms.budget(mixture.context_tokens).windows == 24_416
    assert budget.steps * arms.optimiser.batch_windows * arms.optimiser.accumulate == budget.windows
    assert (budget.steps, budget.context_tokens) == (763, 2048)
    assert budget.total_tokens == 50_003_968
    assert (arms.rung, arms.seeds) == (h1.rung, h1.seeds) == ("S2", [1, 2, 3])


def test_the_optimiser_is_the_gate_runs_value_for_value() -> None:
    arms = load_config(ARMS, AblationArmsConfig)
    gate_run = load_config(GATE_CHECK, GateCheckConfig)
    h1 = load_config(H1_ARMS, H1ArmsConfig)
    for field in ("batch_windows", "accumulate", "learning_rate", "evaluations"):
        assert getattr(arms.optimiser, field) == getattr(gate_run, field), field
        assert getattr(arms.optimiser, field) == getattr(h1.optimiser, field), field
    assert arms.optimiser.selection_windows == gate_run.selection_windows == 500
    assert arms.optimiser.initial_loss_guard is True


def test_the_reference_arm_is_joint_and_is_not_retrained() -> None:
    arms = load_config(ARMS, AblationArmsConfig)
    readout = load_config(READOUT, ReadoutConfig)
    assert arms.arms == list(ABLATIONS)
    assert arms.reference_arm == "joint" and arms.reference_arm not in arms.arms
    # Its (d) reads come from a run readout_v0 registered, not from anything F8 trains.
    assert (
        arms.reference_run
        in {run.name for run in readout.runs}
        == {
            "R-joint-b",
            "R-joint-d",
            "R-ctrl-d",
            "R-rand-d",
        }
    )
    run = next(r for r in readout.runs if r.name == arms.reference_run)
    assert (run.readout, run.backbone, run.seeds) == ("last_plus_text", "joint", arms.seeds)


# =====================================================================================
# §3: the probe protocol and the windows
# =====================================================================================


def test_the_probe_protocol_is_readout_ds_in_force() -> None:
    arms = load_config(ARMS, AblationArmsConfig)
    readout = load_config(READOUT, ReadoutConfig)
    h1 = load_config(H1_ARMS, H1ArmsConfig)
    ladder = load_config(LADDER, LadderConfig)
    probe = arms.probe
    assert probe.readout == ABLATION_READOUT == "last_plus_text"
    assert probe.readout in readout.readout_names
    assert readout.readout(probe.readout).text_block is True
    assert probe.cadence_config == readout.probe.cadence_config == h1.probe.cadence_config
    assert probe.checkpoint == readout.probe.checkpoint == "final_step"
    assert probe.window_rule == readout.probe.window_rule == "tail_anchored_2048"
    assert probe.status_rows == readout.probe.status_rows == "all"
    assert probe.context_tokens == readout.probe.context_tokens == 2048
    assert probe.sampling == readout.probe.sampling == ladder.risk.sampling == "balanced"
    assert probe.train_stride == readout.probe.train_stride == ladder.train_stride
    assert probe.selection == readout.probe.selection == h1.probe.selection
    assert probe.label == h1.probe.label == "narrow_within_24h"
    assert probe.context_tokens == load_config(MIXTURE, JointMixtureConfig).context_tokens
    assert load_config(MODEL, LadderModel).head_hidden == readout.probe.head_hidden


def test_the_window_index_is_the_one_in_force_and_its_strata_partition_it() -> None:
    arms = load_config(ARMS, AblationArmsConfig)
    h1 = load_config(H1_ARMS, H1ArmsConfig)
    index, reference = arms.window_index, h1.window_index
    for field in (
        "test_shard_keys",
        "test_stride",
        "test_windows",
        "test_positives",
        "train_shard_keys",
        "train_stride",
        "train_windows",
        "train_positives",
    ):
        assert getattr(index, field) == getattr(reference, field), field
    assert (index.test_windows, index.test_positives) == (137_025, 5_312)
    # ADR-0026's strata, unchanged under either convention (the F8 read-only check).
    assert (index.has_status_windows, index.has_status_positives) == (97_810, 4_224)
    assert (index.no_status_windows, index.no_status_positives) == (39_215, 1_088)


def test_each_arm_declares_the_stream_its_windows_are_framed_over() -> None:
    arms = load_config(ARMS, AblationArmsConfig)
    mixture = load_config(MIXTURE, JointMixtureConfig)
    assert {rule.arm for rule in arms.window_rule_per_arm} == set(ABLATIONS)
    for rule in arms.window_rule_per_arm:
        arm = next(a for a in mixture.arms if a.name == rule.arm)
        assert rule.status_convention == arm.status_convention, rule.arm
    raw = arms.window_rule("joint_status_raw")
    no_txt = arms.window_rule("joint_no_txt")
    # joint_no_txt probes joint's own windows; nothing is rebuilt and no new gate probe is needed.
    assert no_txt.reuses_normalized_index is True
    assert (no_txt.windows_differing_in_steps_retained, no_txt.random_init_probes) == (0, 0)
    # The raw arm frames its own, and the F8 read-only check's counts are carried by value.
    assert raw.reuses_normalized_index is False
    assert raw.windows_differing_in_steps_retained == 41_371
    assert raw.positives_differing_in_steps_retained == 1_838
    assert raw.random_init_probes == len(arms.seeds) == 3
    assert raw.head_cut_windows == no_txt.head_cut_windows == 0
    index = arms.window_index
    assert raw.windows_differing_in_steps_retained < index.test_windows
    assert raw.positives_differing_in_steps_retained < index.test_positives


# =====================================================================================
# §4, §5: the gate and the rule, against ADR-0027's own text
# =====================================================================================


def test_the_bootstrap_block_is_the_gate_checks() -> None:
    gate = load_config(GATE, AblationGateConfig)
    assert gate.bootstrap == load_config(GATE_CHECK, GateCheckConfig).bootstrap
    assert gate.bootstrap == load_config(READOUT, ReadoutConfig).bootstrap
    assert gate.bootstrap == load_config(H1, H1GateConfig).bootstrap
    assert gate.bootstrap == load_config(REPO / gate.axis_config, AxisGateConfig).bootstrap
    assert gate.bootstrap.block_steps == 288
    assert gate.bootstrap.replicates == 10_000
    assert gate.bootstrap.seed == 20_260_916
    assert gate.bootstrap.max_discarded_share == 0.01


def test_the_split_is_the_temporal_axis_in_force() -> None:
    gate = load_config(GATE, AblationGateConfig)
    axis = load_config(REPO / gate.axis_config, AxisGateConfig)
    assert (gate.stride, gate.label, gate.axis) == (axis.stride, axis.label, "temporal")
    assert (gate.windows, gate.positives) == (
        axis.axes.temporal.windows,
        axis.axes.temporal.positives,
    )
    assert (gate.windows, gate.positives) == (137_025, 5_312)
    assert gate.runner_config == "configs/train/ablation_arms_v0.yaml"
    assert gate.mixture_config == "configs/train/joint_v2.yaml"
    assert gate.readout_config == "configs/eval/readout_v0.yaml"


def test_the_smallest_effect_of_interest_is_read_from_readout_v0() -> None:
    gate = load_config(GATE, AblationGateConfig)
    readout = load_config(READOUT, ReadoutConfig)
    assert gate.rule.smallest_effect == readout.rule.smallest_effect
    assert gate.rule.smallest_effect == load_config(H1, H1GateConfig).rule.smallest_effect
    assert gate.rule.smallest_effect == 0.005


def test_the_instrument_gate_is_adr_0027s_by_value() -> None:
    gate = load_config(GATE, AblationGateConfig).instrument_gate
    clause = _blockquote("### 4. The instrument gate, per ablation, computed first")
    assert "must exceed (d) on every random-init backbone" in clause
    assert "same-seed and cross-seed" in clause
    assert "nine of nine paired lower bounds strictly above zero" in clause
    assert gate.pairing == "same_and_cross_seed"
    assert gate.comparisons == 9 == 3 * 3
    assert gate.lower_bound_above == 0.0
    assert "NOT EVALUABLE" in clause and "reported as undecided" in clause
    assert gate.on_failure == "not_evaluable"
    assert (gate.readout, gate.reference_backbone) == ("last_plus_text", "random_init")


def test_the_gate_draws_each_arms_random_init_scores_from_the_arms_own_windows() -> None:
    gate = load_config(GATE, AblationGateConfig)
    arms = load_config(ARMS, AblationArmsConfig)
    sources = {s.arm: s for s in gate.instrument_gate.random_init_scores}
    assert set(sources) == set(ABLATIONS)
    assert sources["joint_no_txt"].source == "adr_0026_r_rand_d"
    assert sources["joint_no_txt"].new_probes == 0
    assert sources["joint_status_raw"].source == "new_on_raw_windows"
    assert sources["joint_status_raw"].new_probes == 3
    # The same saved backbones ADR-0026 gated on, re-used rather than re-drawn (§4).
    assert sources["joint_status_raw"].backbones_reused_from == arms.random_init_config
    assert arms.random_init_config == load_config(READOUT, ReadoutConfig).random_init_config
    # Every new probe the gate asks for is a probe the runner costs.
    for arm, source in sources.items():
        assert arms.window_rule(arm).random_init_probes == source.new_probes, arm


def test_the_primary_rule_is_adr_0027s_by_value() -> None:
    gate = load_config(GATE, AblationGateConfig)
    rule = gate.rule
    clause = _blockquote("### 5. The primary rule, per ablation")
    assert "AUPRC(ablation, (d)) - AUPRC(joint, (d))" in clause.replace("−", "-")
    assert rule.smallest_effect == float(
        re.search(r"Smallest effect of interest ([0-9]+\.[0-9]+)", clause).group(1)
    )
    assert "HURTS if all three paired upper bounds are below zero" in clause
    assert rule.hurts_upper_bound_below == 0.0
    assert rule.hurts_median_below == -float(
        re.search(r"median . is below .([0-9]+\.[0-9]+)", clause).group(1)
    )
    assert "HELPS if all three lower bounds are above zero" in clause
    assert rule.helps_lower_bound_above == 0.0
    assert rule.helps_median_above == float(
        re.search(r"the median exceeds \+([0-9]+\.[0-9]+)", clause).group(1)
    )
    assert "EQUIVALENT if all three paired intervals lie inside" in clause
    low, high = rule.equivalent_interval_within
    assert (low, high) == (-0.005, 0.005)
    assert f"({low}, +{high})".replace("-0.005", "-0.005") in clause.replace("−", "-")
    assert "Otherwise INCONCLUSIVE at this budget" in clause
    assert rule.otherwise == "inconclusive"
    assert "discarding >1% counts toward none" in clause
    assert gate.bootstrap.max_discarded_share == 0.01
    assert "no clause is added afterwards" in clause
    # One number read four ways.
    assert rule.helps_median_above == -rule.hurts_median_below == rule.smallest_effect


def test_the_comparison_reads_both_sides_through_readout_d() -> None:
    gate = load_config(GATE, AblationGateConfig)
    comparison = gate.comparison
    assert comparison.arms == list(ABLATIONS)
    assert comparison.reference == "joint"
    # The reference is joint under (d), NOT joint under (a): H1's instrument, not H1's.
    assert comparison.reference_readout == gate.readout == "last_plus_text"
    assert (comparison.pairing, comparison.checkpoint, comparison.windows) == (
        "same_seed",
        "final_step",
        "R0",
    )
    assert comparison.seeds == load_config(ARMS, AblationArmsConfig).seeds == [1, 2, 3]
    assert comparison.seeds == load_config(H1, H1GateConfig).comparison.seeds


# =====================================================================================
# §1, §6, §8: the sentences, the reported rows and the caveats
# =====================================================================================


def test_each_ablation_is_registered_to_one_bracketed_write_up_sentence() -> None:
    gate = load_config(GATE, AblationGateConfig)
    adr = _flat(_adr_0027())
    assert {s.arm for s in gate.sentences} == set(ABLATIONS)
    no_txt = _flat(gate.sentence("joint_no_txt"))
    raw = _flat(gate.sentence("joint_status_raw"))
    assert no_txt == (
        "The unpaired narrative corpus [does / does not measurably] contribute to the text signal "
        "the joint model's read-out harvests."
    )
    assert raw == (
        "Normalising status strings to prose surface form (H3') [does / does not measurably] "
        "matter to the joint model's risk read-out."
    )
    # Both sentences are in the record, in the words the config carries.
    assert no_txt.rstrip(".") in adr and raw.rstrip(".") in adr


def test_each_verdict_maps_to_what_adr_0027_says_it_writes() -> None:
    gate = load_config(GATE, AblationGateConfig)
    mapping = gate.verdict_to_sentence
    assert set(mapping.model_dump()) == set(ABLATION_VERDICTS)
    assert mapping.hurts == "does_matter"
    assert mapping.equivalent == "does_not_measurably"
    assert mapping.helps == "reported_as_measured_with_direction"
    assert mapping.inconclusive == mapping.not_evaluable == "undecided"
    adr = _flat(_adr_0027())
    assert 'HURTS - "does matter / does contribute"' in adr.replace("→", "-")
    assert 'EQUIVALENT - "does not measurably"' in adr.replace("→", "-")
    assert "INCONCLUSIVE - the sentence stays undecided" in adr.replace("→", "-")


def test_the_record_says_equivalent_is_unlikely_before_the_run() -> None:
    adr = _flat(_adr_0027())
    assert "EQUIVALENT is very unlikely to be reachable at this budget" in adr
    assert "0.018 to 0.022 wide" in adr
    assert "most likely non-HURTS outcome of this record is INCONCLUSIVE" in adr
    assert "INCONCLUSIVE result is not evidence that a component does not matter" in adr


def test_the_reported_rows_are_adr_0027s_and_decide_nothing() -> None:
    gate = load_config(GATE, AblationGateConfig)
    assert gate.reported == [
        "ablation_d_vs_tel_only_a",
        "ablation_d_vs_status_only_bag",
        "strata_has_status",
        "strata_no_status",
        "selected_vs_final",
    ]
    bag = gate.status_only_bag
    assert bag.auprc == 0.0725
    assert bag.interval == (0.0537, 0.0979)
    # The comparator is F6-1b's, fit on normalized strings, and it is NOT refit for the raw arm.
    assert bag.fit_on == "normalized"
    assert bag.refit_for_raw is False
    adr = _flat(_adr_0027())
    assert "the order-blind classifier was fit on normalized strings" in adr
    assert "reported as-is and is not refit on raw" in adr


def test_the_caveats_are_carried_on_every_row_and_the_raw_arm_carries_a_fourth() -> None:
    gate = load_config(GATE, AblationGateConfig)
    assert gate.caveats == load_config(READOUT, ReadoutConfig).caveats
    assert gate.caveats == ["adr_0009", "forward_in_time_same_sites", "message_volume_shift"]
    assert gate.raw_only_caveat == "raw_casing_changes_truncation"
    adr = _flat(_adr_0027())
    assert "67.2 status tokens in train (stride 6)" in adr
    assert "190.1" in adr
    assert "raw casing changes token counts and therefore truncation" in adr


def test_nothing_in_the_record_authorises_a_run() -> None:
    adr = _flat(_adr_0027())
    assert "Nothing in this record authorises a run" in adr
    assert "Each step needs the user's authorisation" in adr
    assert load_config(ARMS, AblationArmsConfig).cost.launched_by == "author"


# =====================================================================================
# the schemas refuse what the record forbids
# =====================================================================================


def test_a_rule_whose_clauses_drift_from_the_smallest_effect_is_refused() -> None:
    shipped = load_config(GATE, AblationGateConfig).rule.model_dump()
    AblationRule.model_validate(shipped)  # the shipped one loads
    for field, value in (
        ("hurts_median_below", -0.01),
        ("helps_median_above", 0.01),
        ("equivalent_interval_within", (-0.01, 0.01)),
    ):
        with pytest.raises(ValueError):
            AblationRule.model_validate({**shipped, field: value})


def test_a_budget_whose_re_weighting_changes_nothing_is_refused() -> None:
    shipped = load_config(ARMS, AblationArmsConfig).token_budget.model_dump()
    TokenBudget.model_validate(shipped)
    with pytest.raises(ValueError):
        TokenBudget.model_validate({**shipped, "proportional_tel_status_tokens": 25_001_984})
    with pytest.raises(ValueError):
        TokenBudget.model_validate({**shipped, "total_tokens": 50_000_000})


def test_an_arm_that_frames_its_own_windows_must_gate_on_them() -> None:
    raw = load_config(ARMS, AblationArmsConfig).window_rule("joint_status_raw").model_dump()
    ArmWindowRule.model_validate(raw)
    with pytest.raises(ValueError):
        ArmWindowRule.model_validate({**raw, "random_init_probes": 0})
    with pytest.raises(ValueError):
        ArmWindowRule.model_validate({**raw, "reuses_normalized_index": True})


def test_a_random_init_source_must_match_the_probes_it_asks_for() -> None:
    with pytest.raises(ValueError):
        RandomInitSource.model_validate(
            {"arm": "joint_no_txt", "source": "adr_0026_r_rand_d", "new_probes": 3}
        )
    with pytest.raises(ValueError):
        RandomInitSource.model_validate(
            {"arm": "joint_status_raw", "source": "new_on_raw_windows", "new_probes": 3}
        )


def test_a_sentence_without_its_alternatives_is_refused() -> None:
    with pytest.raises(ValueError):
        AblationSentence.model_validate({"arm": "joint_no_txt", "sentence": "It contributes."})


def test_a_refit_order_blind_comparator_is_refused() -> None:
    shipped = load_config(GATE, AblationGateConfig).status_only_bag.model_dump()
    StatusOnlyBag.model_validate(shipped)
    with pytest.raises(ValueError):
        StatusOnlyBag.model_validate({**shipped, "refit_for_raw": True})
