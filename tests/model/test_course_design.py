"""Course Lesson 7: the design view must equal the S2 record it was derived from."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from faultline.config import load_config as load_repo_config
from faultline.model.design import (
    GATE_RUN_GPU_HOURS,
    MEASURED_BACKBONE_PARAMETERS,
    MEASURED_TOTAL_PARAMETERS,
    TELEMETRY_TRAIN_STEPS,
    TELEMETRY_TRAIN_TOKENS,
    TEXT_TRAIN_TOKENS,
    ModelConfig,
    load_config,
)
from faultline.model.transformer import ModelSpec
from faultline.tokenizers.layout import TEXT_CAPACITY, TEXT_OFFSET
from faultline.training.config import LadderModel
from faultline.training.mixture import JointMixtureConfig

REPO = Path(__file__).resolve().parents[2]
COURSE = REPO / "configs/model/course/run_01.yaml"
LADDER = REPO / "configs/model/ladder_v0.yaml"
JOINT = REPO / "configs/train/joint_v0.yaml"


def s2() -> tuple[ModelConfig, LadderModel, JointMixtureConfig]:
    ladder = load_repo_config(LADDER, LadderModel)
    joint = load_repo_config(JOINT, JointMixtureConfig)
    return load_config(COURSE), ladder, joint


def test_every_field_equals_the_s2_record() -> None:
    course, ladder, joint = s2()
    rung = next(r for r in ladder.rungs if r.name == "S2")
    # template field <- repository key
    assert course.n_embd == rung.d_model
    assert course.n_layer == rung.n_layer
    assert course.n_head == rung.n_head
    assert course.dropout == ladder.dropout
    assert course.block_size == joint.context_tokens
    assert course.vocab_size == TEXT_OFFSET + TEXT_CAPACITY
    ffn_source = "src/faultline/model/transformer.py builds the MLP as Linear(d_model, 4 * d_model)"
    tie_source = "src/faultline/model/transformer.py ties the output head to the token embedding"
    assert course.ffn_mult == 4, ffn_source
    assert course.tie_weights is True, tie_source
    # the dataclass defaults are the same view
    assert course == ModelConfig()


def test_vocab_size_is_the_full_joint_layout_not_the_telemetry_prefix() -> None:
    course, _, _ = s2()
    assert course.vocab_size == TEXT_OFFSET + TEXT_CAPACITY == 33_952
    assert course.vocab_size > TEXT_OFFSET  # the 1,184-id telemetry prefix is not what S2 embeds
    course.check()  # fits uint16


def test_block_size_is_the_joint_context_not_the_144_step_window() -> None:
    course, ladder, joint = s2()
    assert course.block_size == joint.context_tokens
    tokens_per_step = 13  # <sep> and the twelve core channels (docs/ROADMAP.md, M1b step 12)
    assert course.block_size != ladder.context_steps * tokens_per_step


def test_ladder_table_is_the_ladder_config_in_order() -> None:
    course, ladder, _ = s2()
    rows = course.ladder_table(LADDER)
    assert [r["rung"] for r in rows] == [r.name for r in ladder.rungs]
    for row, rung in zip(rows, ladder.rungs, strict=True):
        assert (row["d"], row["L"], row["heads"]) == (rung.d_model, rung.n_layer, rung.n_head)
        assert row["non_embedding"] == 12 * rung.n_layer * rung.d_model**2


def test_the_recorded_figures_match_their_artefacts_and_the_code() -> None:
    course, _, joint = s2()
    spec = ModelSpec(
        name="S2",
        d_model=course.n_embd,
        n_layer=course.n_layer,
        n_head=course.n_head,
        context=joint.context_tokens,
        vocab_size=course.vocab_size,
    )
    assert spec.backbone_params == MEASURED_BACKBONE_PARAMETERS
    embeddings = (course.vocab_size + course.block_size) * course.n_embd
    assert spec.backbone_params + embeddings == MEASURED_TOTAL_PARAMETERS
    gap = MEASURED_TOTAL_PARAMETERS - course.estimate_parameters()["total"]
    assert gap == 2 * course.n_embd * course.n_layer + course.n_embd  # the RMSNorm weights
    reports = REPO / "reports/data"
    assert f"| training steps | {TELEMETRY_TRAIN_STEPS:,} |" in (
        reports / "shards_v2_20260912.md"
    ).read_text(encoding="utf-8")
    assert TELEMETRY_TRAIN_STEPS * 13 == TELEMETRY_TRAIN_TOKENS
    assert f"{TELEMETRY_TRAIN_TOKENS:,} training tokens" in (REPO / "docs/ROADMAP.md").read_text(
        encoding="utf-8"
    )
    assert f"{TEXT_TRAIN_TOKENS:,} train" in (reports / "m2_gate6_20260916.md").read_text(
        encoding="utf-8"
    )
    assert f"| wall clock | {GATE_RUN_GPU_HOURS} GPU-hours |" in (
        reports / "gate_check_v0_20260916.md"
    ).read_text(encoding="utf-8")
    assert f"{MEASURED_BACKBONE_PARAMETERS:,}" in LADDER.read_text(encoding="utf-8")


def test_the_design_script_runs_and_prints_what_was_measured() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts/design_model.py")],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "measured" in result.stdout
