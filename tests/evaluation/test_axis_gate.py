"""The shipped axis-gate configuration is ADR-0022's, and agrees with ADR-0021 and ADR-0024."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from faultline.config import load_config
from faultline.evaluation.axis_gate import (
    AxisGateRecord,
    AxisRow,
    ChannelAbsence,
    IndexCounts,
    ReportedRow,
    assign_hypotheses,
    decide_axis,
    load_record,
    record_payload,
)
from faultline.evaluation.bootstrap import (
    AuprcInterval,
    GateVerdict,
    decide_evaluable,
    window_blocks,
)
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.paired_control import PairedControlConfig
from faultline.training.windows import ShardSet, load_windows

REPO = Path(__file__).resolve().parents[2]
SHIPPED = REPO / "configs/eval/axis_gate_v0.yaml"


def _shipped() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(SHIPPED.read_text(encoding="utf-8"))
    return loaded


def test_the_axis_gate_is_registered_in_adr_0022() -> None:
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "## ADR-0022 The primary evaluation axis after ADR-0021" in decisions
    assert "(number reserved)" not in decisions
    assert "ADR-0022" in SHIPPED.read_text(encoding="utf-8")


def test_the_interval_is_adr_0021s_and_the_stride_is_f3s() -> None:
    shipped = _shipped()
    gate = load_config(REPO / "configs/train/gate_check_v0.yaml", GateCheckConfig)
    paired = load_config(REPO / "configs/train/paired_control_v0.yaml", PairedControlConfig)
    assert shipped["bootstrap"] == gate.bootstrap.model_dump()
    assert shipped["stride"] == paired.stride == 12
    ladder = yaml.safe_load((REPO / "configs/train/telemetry_v1.yaml").read_text(encoding="utf-8"))
    assert shipped["label"] == ladder["risk"]["label"] == "narrow_within_24h"


def test_the_chance_level_is_the_scored_sets_own_rate_on_two_of_three_seeds() -> None:
    shipped = _shipped()
    # ADR-0021's rule reads the base rate on the scored windows, never the training natural rate.
    assert shipped["base_rate_source"] == "scored_set"
    assert shipped["seeds"] == [1, 2, 3] and shipped["seeds_required"] == 2
    # Which of the two gates is ADR-0022's addendum's to decide; the pair is always both.
    assert set(shipped["checkpoints"]) == {"gating", "reported"}
    assert {shipped["checkpoints"]["gating"], *shipped["checkpoints"]["reported"]} == {
        "selected",
        "final_step",
    }
    for axis in shipped["axes"].values():
        assert axis["base_rate"] == round(axis["positives"] / axis["windows"], 4)
    care = shipped["axes"]["care"]
    assert care["full_positives"] == 144 * care["events"] == 6480
    assert round(care["full_positives"] / care["full_windows"], 4) == care["base_rate"]


def test_the_selection_rule_is_the_one_the_adr_0022_addendum_decided() -> None:
    """The shipped gating checkpoint is read out of ADR-0022's addendum, not pinned here.

    The addendum's outcome is the registered decision; this configuration is what F5 and every
    arm run actually read. Pinning the string in the test would let the two drift apart and
    still pass, so the expected value is parsed from ``docs/DECISIONS.md``.
    """
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "### Addendum, registered 2026-09-18" in decisions
    stated = re.findall(r"The rule in force for the arm runs and for F5: `([a-z_]+)`", decisions)
    assert len(stated) == 1, f"the addendum must state the rule exactly once, found {stated}"
    shipped = _shipped()
    assert shipped["checkpoints"]["gating"] == stated[0]
    assert stated[0] not in shipped["checkpoints"]["reported"]
    # The addendum's commit hash is in the configuration's comment, so the value it states is
    # traceable to the record that decided it. The hash itself is not pinned here.
    assert re.search(
        r"addendum of 2026-09-18, registered in [0-9a-f]{7,40}", SHIPPED.read_text(encoding="utf-8")
    )


def _count(shards: ShardSet, keys: list[str], label: str, stride: int) -> dict[str, int]:
    sets = [load_windows(shards, key, stride=stride, label=label) for key in keys]
    ends = np.concatenate([s.ends for s in sets])
    which = np.concatenate([np.full(len(s), i) for i, s in enumerate(sets)])
    labels = np.concatenate([s.labels for s in sets]) > 0.5
    blocks = window_blocks(ends, which, 288)
    return {
        "windows": int(ends.size),
        "positives": int(labels.sum()),
        "blocks": int(np.unique(blocks).size),
        "positive_blocks": int(np.unique(blocks[labels]).size),
    }


@pytest.mark.skipif(
    not (REPO / _shipped()["shards"] / "manifest.json").is_file(),
    reason="the shards in force are not staged here",
)
def test_the_registered_counts_are_the_window_index_counts() -> None:
    shipped = _shipped()
    shards = ShardSet.load(REPO / shipped["shards"])
    temporal = shipped["axes"]["temporal"]
    assert _count(shards, temporal["shard_keys"], shipped["label"], shipped["stride"]) == {
        key: temporal[key] for key in ("windows", "positives", "blocks", "positive_blocks")
    }
    without = _count(
        shards, temporal["shard_keys"], temporal["without_messages_label"], shipped["stride"]
    )
    assert without["windows"] == temporal["without_messages_windows"]
    assert without["positives"] == temporal["without_messages_positives"]
    care = shipped["axes"]["care"]
    assert _count(shards, care["shard_keys"], shipped["label"], shipped["stride"]) == {
        key: care[key] for key in ("windows", "positives", "blocks", "positive_blocks")
    }
    assert _count(shards, care["shard_keys"], shipped["label"], 1) == {
        "windows": care["full_windows"],
        "positives": care["full_positives"],
        "blocks": care["full_blocks"],
        "positive_blocks": care["full_positive_blocks"],
    }


# =====================================================================================
# ADR-0022 §4: the rule over the seeds, and the record the report is written beside
# =====================================================================================


def _interval(low: float, base_rate: float, discarded: int = 0) -> AuprcInterval:
    """One seed's interval, with only the two numbers the rule reads left free."""
    return AuprcInterval(
        unit="block",
        auprc=low + 0.01,
        low=low,
        high=low + 0.02,
        lift_low=low - base_rate,
        lift_high=low + 0.02 - base_rate,
        base_rate=base_rate,
        windows=430_506,
        positives=540,
        blocks=18_193,
        positive_blocks=67,
        replicates=10_000,
        discarded=discarded,
        confidence=0.95,
        seed=20260916,
    )


def _verdicts(*lows: float, base_rate: float = 0.001254) -> dict[int, GateVerdict]:
    """ADR-0021's verdict per seed, from each seed's lower bound."""
    return {
        seed: decide_evaluable(_interval(low, base_rate), 0.01)
        for seed, low in enumerate(lows, start=1)
    }


def test_an_axis_is_evaluable_on_two_of_three_seeds() -> None:
    verdict = decide_axis("care", _verdicts(0.01, 0.01, 0.0005), required=2)
    assert verdict.evaluable
    assert verdict.clearing == (1, 2)
    assert verdict.seeds == (1, 2, 3)
    assert "2 of 3" in verdict.reason and "EVALUABLE" in verdict.reason


def test_one_of_three_seeds_is_not_enough() -> None:
    verdict = decide_axis("care", _verdicts(0.01, 0.0005, 0.0005), required=2)
    assert not verdict.evaluable
    assert verdict.clearing == (1,)
    assert "NOT EVALUABLE" in verdict.reason


def test_three_of_three_seeds_clear() -> None:
    verdict = decide_axis("temporal", _verdicts(0.06, 0.05, 0.04, base_rate=0.0388), required=2)
    assert verdict.evaluable
    assert verdict.clearing == (1, 2, 3)


def test_a_lower_bound_equal_to_the_base_rate_does_not_clear() -> None:
    """The rule is strictly above, so equality is a failure, not a pass.

    This is the edge the whole gate turns on: a scorer with no signal reaches the base rate,
    so an interval whose lower bound only touches it has not separated the model from chance.
    """
    base_rate = 0.001254
    assert not decide_evaluable(_interval(base_rate, base_rate), 0.01).evaluable
    verdict = decide_axis("care", _verdicts(base_rate, base_rate, 0.01), required=2)
    assert not verdict.evaluable
    assert verdict.clearing == (3,)


def test_an_untrusted_interval_does_not_clear_however_high_its_bound() -> None:
    verdicts = {1: decide_evaluable(_interval(0.5, 0.001254, discarded=200), 0.01)}
    assert not verdicts[1].evaluable
    assert not decide_axis("care", verdicts, required=1).evaluable


def test_decide_axis_refuses_fewer_seeds_than_must_clear() -> None:
    with pytest.raises(ValueError, match="fewer than the 2"):
        decide_axis("care", _verdicts(0.01), required=2)


@pytest.mark.parametrize(
    ("care_clears", "temporal_clears", "h1", "h2", "stop"),
    [
        (True, True, "care", "temporal", False),
        (False, True, "temporal", "temporal", False),
        (True, False, "care", None, False),
        (False, False, None, None, True),
    ],
)
def test_the_assignment_is_the_one_adr_0022_section_4_writes_out(
    care_clears: bool, temporal_clears: bool, h1: str | None, h2: str | None, stop: bool
) -> None:
    care = decide_axis("care", _verdicts(0.01 if care_clears else 0.0005), required=1)
    temporal = decide_axis(
        "temporal",
        _verdicts(0.06 if temporal_clears else 0.01, base_rate=0.0388),
        required=1,
    )
    assignment = assign_hypotheses(care, temporal)
    assert (assignment.h1, assignment.h2, assignment.stop) == (h1, h2, stop)


def _record() -> AxisGateRecord:
    """A record with one cell of every kind the report renders."""
    interval = _interval(0.01, 0.001254)
    verdict = decide_evaluable(interval, 0.01)
    care = decide_axis("care", {1: verdict}, required=1)
    temporal = decide_axis("temporal", {1: verdict}, required=1)
    return AxisGateRecord(
        config_hash="deadbeef",
        gating="final_step",
        rows=(
            AxisRow("care", 1, "final_step", True, interval, verdict),
            AxisRow("temporal", 1, "selected", False, interval, verdict),
        ),
        reported=(
            ReportedRow("farm_a", "care", 1, "final_step", 0.0015, interval, "a farm"),
            ReportedRow("hill_of_towie", "held_out", 1, "selected", 0.03325, interval, "read"),
        ),
        verdicts={"care": care, "temporal": temporal},
        reported_verdicts={"care": care, "temporal": temporal},
        assignment=assign_hypotheses(care, temporal),
        absence={
            "farm_a": ChannelAbsence("farm_a", 96_694, ("main_bearing_temp_c",), 0.0835, 0.0835)
        },
        counts={"care": IndexCounts(430_506, 540, 18_193, 67)},
        without_messages={"label": "narrow_within_24h_without", "care_events_removed": 0},
        seconds=12.5,
        gpu_seconds=7200.0,
        computed=("one",),
        resumed=("two", "three"),
    )


def test_the_report_loader_round_trips_the_json() -> None:
    """Every typed field survives the trip through the record's JSON, not just its scalars."""
    original = _record()
    through = load_record(json.loads(json.dumps(record_payload(original))))
    assert through == original
    assert isinstance(through.rows[0].interval, AuprcInterval)
    assert isinstance(through.rows[0].verdict, GateVerdict)
    assert through.absence["farm_a"].absent == ("main_bearing_temp_c",)
    assert through.counts["care"].base_rate == pytest.approx(0.001254, abs=5e-7)
