"""The shipped F9 config is ADR-0028's, and restates its sources value for value."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from faultline.config import load_config
from faultline.evaluation.abstention_gate import (
    CORE_CHANNELS,
    AbstentionConfig,
    H2Rule,
    SeverityLadder,
    SplitCounts,
)
from faultline.evaluation.axis_gate import AxisGateConfig
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.readout import ReadoutConfig

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/eval/abstention_v0.yaml"
GATE_CHECK = REPO / "configs/train/gate_check_v0.yaml"
READOUT = REPO / "configs/eval/readout_v0.yaml"
HEADING = "## ADR-0028 Calibration, risk–coverage and graceful degradation (H2)"


def _adr_0028() -> str:
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert decisions.count(HEADING) == 1
    return decisions[decisions.index(HEADING) :]


def _flat(text: str) -> str:
    """One line of prose: quote markers, emphasis and line breaks removed."""
    lines = [re.sub(r"^\s*>\s?", "", line) for line in text.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines).replace("*", "").replace("`", "")).strip()


def _blockquote(after: str) -> str:
    """The first ``>`` block of ADR-0028 following a marker, flattened."""
    adr = _adr_0028()
    body = adr[adr.index(after) + len(after) :]
    quoted: list[str] = []
    for line in body.splitlines():
        if line.startswith(">"):
            quoted.append(line)
        elif quoted:
            break
    assert quoted, f"no blockquote after {after!r}"
    return _flat("\n".join(quoted))


def _config() -> AbstentionConfig:
    return load_config(CONFIG, AbstentionConfig)


# =====================================================================================
# the file loads strictly, and restates what it cites
# =====================================================================================


def test_the_config_loads_under_its_strict_schema() -> None:
    assert _config().version == 0


def test_an_unknown_key_is_refused() -> None:
    with pytest.raises(ValidationError):
        AbstentionConfig.model_validate({**_config().model_dump(), "extra": 1})


def test_the_bootstrap_block_is_the_gate_checks() -> None:
    config = _config()
    assert config.bootstrap == load_config(GATE_CHECK, GateCheckConfig).bootstrap
    assert config.bootstrap == load_config(READOUT, ReadoutConfig).bootstrap


def test_the_test_split_is_the_temporal_axis_in_force() -> None:
    config = _config()
    axis = load_config(REPO / config.axis_config, AxisGateConfig)
    assert (config.stride, config.label) == (axis.stride, axis.label)
    test = config.splits.test
    assert (test.windows, test.positives) == (
        axis.axes.temporal.windows,
        axis.axes.temporal.positives,
    )
    assert (test.windows, test.positives, test.base_rate) == (137_025, 5_312, 0.0388)
    validation = config.splits.validation
    counts = (validation.windows, validation.positives, validation.base_rate)
    assert counts == (85_529, 1_805, 0.0211)
    assert validation.shard_keys == ["kelmarsh__val", "penmanshiel__val"]


def test_the_arms_read_registered_runs_through_final_step_probes() -> None:
    config = _config()
    readout = load_config(READOUT, ReadoutConfig)
    assert [a.name for a in config.arms] == ["tel_only_a", "joint_a", "joint_d"]
    for arm in config.arms:
        assert arm.readout in readout.readout_names
    assert config.arm("joint_d").readout == "last_plus_text"
    assert config.arm("joint_a").readout == config.arm("tel_only_a").readout == "final_position"
    run = next(r for r in readout.runs if r.name == "R-joint-d")
    assert (run.readout, run.backbone, run.seeds) == ("last_plus_text", "joint", config.seeds)
    assert (config.checkpoint, config.windows, config.seeds) == ("final_step", "R0", [1, 2, 3])


# =====================================================================================
# §3: the ladder, against its seed and the step layout
# =====================================================================================


def test_the_core_channels_are_the_step_layouts() -> None:
    manifest = REPO / _config().telemetry_manifest
    if not manifest.exists():
        pytest.skip("the telemetry shards are not on this machine")
    step = json.loads(manifest.read_text(encoding="utf-8"))["step"]
    assert tuple(name for name in step if name != "<sep>") == CORE_CHANNELS
    assert len(CORE_CHANNELS) == 12


def test_the_ladder_sets_are_the_seeded_draw_nested_and_sized_2_4_6_8() -> None:
    ladder = _config().ladder
    assert ladder.severities == [2, 4, 6, 8]
    order = [CORE_CHANNELS[i] for i in np.random.default_rng(ladder.seed).permutation(12)]
    for k in ladder.severities:
        assert ladder.sets[k] == order[:k], k
        assert set(ladder.sets[k]) <= set(CORE_CHANNELS)
    for low, high in zip(ladder.severities, ladder.severities[1:], strict=False):
        assert set(ladder.sets[low]) < set(ladder.sets[high])
    assert ladder.seed == 20_260_924
    assert ladder.test_scorings == 12


def test_the_ladder_sets_are_listed_by_name_in_the_record() -> None:
    adr = _flat(_adr_0028())
    sets = _config().ladder.sets
    assert "| 2 | nacelle_position_deg, ambient_temp_c |" in adr
    for low, high in ((2, 4), (4, 6), (6, 8)):
        added = ", ".join(sets[high][low:])
        assert f"| {high} | + {added} |" in adr, high
    assert "numpy.random.default_rng(20260924).permutation(12)" in adr


@pytest.mark.parametrize(
    ("change", "sets"),
    [
        (
            "not nested",
            {
                2: ["power_pu", "wind_speed_ms"],
                4: ["rotor_speed_rpm", "pitch_angle_deg", "ambient_temp_c", "nacelle_temp_c"],
            },
        ),
        ("wrong size", {2: ["power_pu"], 4: ["power_pu", "wind_speed_ms", "rotor_speed_rpm"]}),
        (
            "not core",
            {2: ["power_pu", "wind_direction_deg"], 4: ["power_pu", "wind_direction_deg"]},
        ),
    ],
)
def test_a_ladder_that_is_not_nested_core_and_sized_is_refused(
    change: str, sets: dict[int, list[str]]
) -> None:
    shipped = _config().ladder.model_dump()
    SeverityLadder.model_validate(shipped)
    with pytest.raises(ValueError):
        SeverityLadder.model_validate({**shipped, "severities": [2, 4], "sets": sets})


# =====================================================================================
# §1-§3: the operating point, the gates and the rule, against ADR-0028's text
# =====================================================================================


def test_the_operating_point_is_fixed_on_validation() -> None:
    model = _config().operating_model
    adr = _flat(_adr_0028())
    assert (model.operating_point_split, model.tau_rule, model.kappa_coverage) == (
        "validation",
        "max_f1",
        0.90,
    )
    assert "fixed on the 2021 VALIDATION split before any test number is read" in adr
    assert "Abstain when u > κ. On covered windows, alarm when p ≥ τ." in adr
    assert model.validation_scorings == 9
    assert "nine new validation scorings" in adr


def test_gate_a_is_adr_0028s_by_value() -> None:
    gate = _config().gate_a
    clause = _blockquote("**GATE A (the instrument), per arm:**")
    assert "Δ = AURC(seed disagreement) − AURC(random ordering)" in clause
    assert "PASS iff the 95% upper bound is below zero" in clause
    assert gate.upper_bound_below == 0.0
    assert "abstention on that arm is NOT EVALUABLE" in clause
    assert gate.on_failure == "not_evaluable"
    rc = _config().risk_coverage
    assert (rc.random_orderings, rc.random_seed) == (100, 20_260_924)


def test_gate_b_is_adr_0028s_by_value() -> None:
    gate = _config().gate_b
    clause = _blockquote("**GATE B (damage), computed first:**")
    assert "AUPRC(ensemble, k=8) − AUPRC(ensemble, clean)" in clause
    assert f"k={gate.severity}" in clause and gate.severity == 8
    assert "If its upper bound is not below zero" in clause
    assert gate.upper_bound_below == 0.0
    assert "H2 is NOT TESTABLE at this severity" in clause
    assert gate.on_failure == "not_testable"


def test_the_h2_rule_is_adr_0028s_by_value() -> None:
    rule = _config().h2_rule
    clause = _blockquote("**H2 RULE**, on the ensemble at k = 8 against clean")
    effect = float(re.search(r"selective risk: ([0-9]+\.[0-9]+) absolute", clause).group(1))
    assert rule.smallest_effect_risk == effect == 0.005
    assert "SUPPORTED (graceful) if the upper bound of Δcov is below zero" in clause
    assert rule.supported_cov_upper_below == 0.0
    assert "AND the upper bound of Δrisk is below +0.005" in clause
    assert rule.supported_risk_upper_below == 0.005
    assert "REFUTED if the lower bound of Δcov is at or above zero" in clause
    assert rule.refuted_cov_lower_at_or_above == 0.0
    assert "AND the lower bound of Δrisk is above zero" in clause
    assert rule.refuted_risk_lower_above == 0.0
    assert "Otherwise INCONCLUSIVE" in clause and rule.otherwise == "inconclusive"
    assert "Requires Gate A PASS on joint (d) and Gate B damage" in clause
    assert rule.requires == ["gate_a_pass_joint_d", "gate_b_damage"]
    assert "no clause is added afterwards" in clause
    # 0.005 is about 13% of the test base rate, as the record says.
    assert round(effect / _config().splits.test.base_rate, 2) == 0.13


def test_the_rule_quotes_h2s_falsifier_as_first_written() -> None:
    quote = _blockquote("H2 and its falsifier, as first written")
    assert quote.startswith("As degradation severity rises, coverage falls and selective risk")
    assert quote.endswith("if coverage stays flat while selective risk rises, H2 is refuted.")


def test_the_caveats_are_carried_on_every_row() -> None:
    config = _config()
    assert config.caveats[:3] == load_config(READOUT, ReadoutConfig).caveats
    assert config.caveats[3:] == ["small_ensemble", "operating_point_base_rate_shift"]


def test_nothing_in_the_record_authorises_a_run() -> None:
    adr = _flat(_adr_0028())
    assert "Nothing in this record authorises a GPU run" in adr
    assert "Each needs the user's authorisation" in adr
    assert _config().ladder.launched_by == "author"


# =====================================================================================
# the schemas refuse what the record forbids
# =====================================================================================


def test_a_supported_bound_that_drifts_from_the_smallest_effect_is_refused() -> None:
    shipped = _config().h2_rule.model_dump()
    H2Rule.model_validate(shipped)
    with pytest.raises(ValueError):
        H2Rule.model_validate({**shipped, "supported_risk_upper_below": 0.01})


def test_a_base_rate_that_is_not_the_counts_is_refused() -> None:
    with pytest.raises(ValueError):
        SplitCounts.model_validate({"windows": 137_025, "positives": 5_312, "base_rate": 0.04})


def test_a_rule_read_below_the_strongest_severity_is_refused() -> None:
    shipped = _config().model_dump()
    with pytest.raises(ValueError):
        AbstentionConfig.model_validate(
            {**shipped, "h2_rule": {**shipped["h2_rule"], "severity": 6}}
        )
