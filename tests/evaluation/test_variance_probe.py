"""The seed-variance probe: the pre-registered rule, the configuration, and the tel windows."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from pydantic import ValidationError

from faultline.config import load_config
from faultline.evaluation.variance_probe import VarianceProbeConfig, decide, tel_windows
from faultline.training.mixture import JointMixtureConfig
from faultline.training.windows import ShardSet

REPO = Path(__file__).resolve().parents[2]
SHIPPED = REPO / "configs/train/variance_probe_v0.yaml"


# ------------------------------------------------------------------ the rule


def test_a_gap_at_the_line_makes_one_seed_arms_uninformative() -> None:
    verdict = decide(0.040, 0.030, 0.010)
    assert verdict.gap == pytest.approx(0.010)
    assert verdict.uninformative
    assert "three seeds" in verdict.design


def test_a_gap_below_the_line_keeps_three_arms() -> None:
    verdict = decide(0.0351, 0.0300, 0.010)
    assert not verdict.uninformative
    assert "three arms" in verdict.design


def test_the_gap_is_absolute_whichever_seed_is_higher() -> None:
    assert decide(0.03, 0.05, 0.01).gap == decide(0.05, 0.03, 0.01).gap


def test_a_nan_auprc_cannot_be_read_by_the_rule() -> None:
    with pytest.raises(ValueError, match="nan"):
        decide(float("nan"), 0.03, 0.01)


# ------------------------------------------------------------------ the configuration


def test_the_shipped_line_is_the_one_registered_in_adr_0020() -> None:
    config = load_config(SHIPPED, VarianceProbeConfig)
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert config.smallest_claimable_auprc_difference == 0.010
    assert "**The line: 0.010 absolute AUPRC on Hill of Towie test.**" in decisions
    assert config.held_out_source == "hill_of_towie"


def test_the_shipped_probe_is_half_the_arm_budget_rounded_up_to_a_step() -> None:
    config = load_config(SHIPPED, VarianceProbeConfig)
    mixture = load_config(REPO / config.mixture_config, JointMixtureConfig)
    assert config.tokens * 2 == mixture.tokens_per_arm
    budget = config.budget(mixture.context_tokens)
    per_step = 32 * mixture.context_tokens
    assert budget.batch_windows * budget.accumulate == 32
    assert budget.steps == 382
    tokens = budget.windows * mixture.context_tokens
    assert config.tokens <= tokens < config.tokens + per_step
    assert config.rung == "S2" and config.arm == "tel_only"


def test_two_equal_seeds_are_refused() -> None:
    payload: dict[str, Any] = yaml.safe_load(SHIPPED.read_text(encoding="utf-8"))
    broken = copy.deepcopy(payload)
    broken["seeds"] = [1, 1]
    with pytest.raises(ValidationError, match="differ in seed"):
        VarianceProbeConfig.model_validate(broken)
    broken["seeds"] = [1, 2, 3]
    with pytest.raises(ValidationError):
        VarianceProbeConfig.model_validate(broken)


# ------------------------------------------------------------------ the tel windows


def _fixture(root: Path) -> tuple[Path, ShardSet]:
    """An M1 shard of two runs (10 and 7 steps of 13 tokens) and its tel run index."""
    telemetry = root / "telemetry"
    telemetry.mkdir(parents=True)
    tokens = np.arange(17 * 13, dtype=np.uint16)
    tokens.tofile(telemetry / "alpha__train.bin")
    manifest = {
        "tokens_per_step": 13,
        "context_steps": 4,
        "vocabulary_size": 1184,
        "specials": {"<sep>": 8, "<nan>": 9},
        "files": {"alpha__train": {"tokens": "alpha__train.bin", "steps": 17, "windows": "-"}},
    }
    (telemetry / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    joint = root / "joint"
    (joint / "tel").mkdir(parents=True)
    runs = [
        {"steps": 10, "first_token": 0, "tokens": 130},
        {"steps": 7, "first_token": 130, "tokens": 91},
    ]
    pq.write_table(pa.Table.from_pylist(runs), joint / "tel" / "alpha__train.runs.parquet")
    return joint, ShardSet.load(telemetry)


def test_tel_windows_start_on_a_stride_step_and_never_cross_a_run(tmp_path: Path) -> None:
    joint, shards = _fixture(tmp_path)
    windows = tel_windows(joint, shards, "train", ["alpha"], context=39, stride_steps=2)
    starts = windows.index[:, 1].tolist()
    # run 1: steps 0,2,4,6 fit 3 steps (39 tokens) inside 130; step 8 would end at 143
    # run 2: steps 0,2,4 from token 130 fit inside 221
    assert starts == [0, 26, 52, 78, 130, 156, 182]
    assert all(start % 13 == 0 for start in starts)
    tokens, _, _ = next(windows.epoch(batch=7))
    assert tokens.shape == (7, 39)
    assert tokens[4, 0].item() == 130 and tokens[4, -1].item() == 168


def test_tel_windows_cap_is_seeded(tmp_path: Path) -> None:
    joint, shards = _fixture(tmp_path)
    first = tel_windows(joint, shards, "train", ["alpha"], 39, 1, limit=4, seed=5)
    again = tel_windows(joint, shards, "train", ["alpha"], 39, 1, limit=4, seed=5)
    assert len(first) == 4
    assert first.index.tolist() == again.index.tolist()


def test_the_training_stream_reshuffles_and_yields_whole_batches(tmp_path: Path) -> None:
    joint, shards = _fixture(tmp_path)
    windows = tel_windows(joint, shards, "train", ["alpha"], 39, 1)
    stream = windows.forever(seed=0, batch=3)
    batches = [next(stream)[0] for _ in range(10)]
    assert all(b.shape == (3, 39) for b in batches)
