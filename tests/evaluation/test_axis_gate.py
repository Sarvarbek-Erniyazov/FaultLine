"""The shipped axis-gate configuration is ADR-0022's, and agrees with ADR-0021 and ADR-0024."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from faultline.config import load_config
from faultline.evaluation.bootstrap import window_blocks
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
