"""ADR-0025 §2 on the real shards: the tail-anchored index is M1's, and tel_only is untouched.

Every test here reads the staged shards and is skipped where they are not staged.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from faultline.config import config_hash, load_config
from faultline.data.telemetry.bins import QuantileBinsConfig
from faultline.data.telemetry.shards import shards_dir, tokenizer_path
from faultline.evaluation.bag_of_tokens import BagOfTokensConfig, BagOfTokensV1Config
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.h1_arms import arms_layout
from faultline.evaluation.h1_gate import H1ArmsConfig
from faultline.evaluation.ladder import balanced_training_sampler
from faultline.evaluation.variance_probe import (
    open_probe_inputs,
    probe_training_sampler,
    tel_status_streams,
)
from faultline.paths import ProjectPaths
from faultline.tokenizers.layout import VocabLayout
from faultline.training.config import LadderConfig, PositiveAwareRiskStage
from faultline.training.joint_windows import (
    SEP_ID,
    JointWindowSet,
    TelStatusStreams,
    message_spans,
    step_offsets,
)
from faultline.training.mixture import JointMixtureConfig
from faultline.training.windows import ShardSet, load_windows

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "configs/train/h1_arms_v0.yaml"
CONTROLS = REPO / "configs/train/bag_of_tokens_v1.yaml"


def _paths() -> ProjectPaths:
    return ProjectPaths.resolve()


def _joint_root() -> Path:
    runner = load_config(RUNNER, H1ArmsConfig)
    mixture = load_config(REPO / runner.mixture_config, JointMixtureConfig)
    return REPO / "data/shards/joint" / f"joint_v{mixture.version}_{config_hash(mixture)}"


STAGED = (_joint_root() / "manifest.json").is_file()
needs_shards = pytest.mark.skipif(not STAGED, reason="the joint_v1 shards are not staged here")


def _telemetry() -> ShardSet:
    runner = load_config(RUNNER, H1ArmsConfig)
    mixture = load_config(REPO / runner.mixture_config, JointMixtureConfig)
    paths = _paths()
    bins = load_config(REPO / mixture.telemetry_tokenizer_config, QuantileBinsConfig)
    return ShardSet.load(shards_dir(paths, tokenizer_path(paths, bins)))


def _streams(telemetry: ShardSet, status_rows: str = "all") -> TelStatusStreams:
    runner = load_config(RUNNER, H1ArmsConfig)
    mixture = load_config(REPO / runner.mixture_config, JointMixtureConfig)
    return tel_status_streams(
        _paths(),
        _joint_root(),
        telemetry,
        "normalized",
        runner.probe.context_tokens,
        status_rows,  # type: ignore[arg-type]
        mixture.training_sources,
    )


@needs_shards
@pytest.mark.parametrize("split", ["test", "train"])
def test_the_tail_anchored_index_is_the_m1_index(split: str) -> None:
    runner = load_config(RUNNER, H1ArmsConfig)
    index = runner.window_index
    keys = index.test_shard_keys if split == "test" else index.train_shard_keys
    stride = index.test_stride if split == "test" else index.train_stride
    telemetry = _telemetry()
    streams = _streams(telemetry)
    windows = positives = 0
    for key in keys:
        m1 = load_windows(telemetry, key, stride=stride, label=runner.probe.label)
        joint = streams.frame(m1)
        # Same rows: key, end step, label and year, in the same order.
        assert joint.key == m1.key
        assert np.array_equal(joint.ends, m1.ends) and np.array_equal(joint.labels, m1.labels)
        assert np.array_equal(joint.years, m1.years)
        # Same steps: the stream's step t is the M1 shard's step t, token for token.
        stream = streams.stream(key)
        offsets = step_offsets(stream)
        width = telemetry.tokens_per_step
        ours = np.asarray(stream)[offsets[joint.ends][:, None] + np.arange(width)]
        theirs = np.asarray(m1.tokens)[joint.ends[:, None] * width + np.arange(width)]
        assert np.array_equal(ours, theirs)
        # The rule: at most 144 steps, never before t - 143, at most 2,048 tokens, from a <sep>.
        assert joint.steps_retained.max() <= telemetry.context_steps
        assert np.all(joint.first >= offsets[joint.ends - telemetry.context_steps + 1])
        assert joint.length.max() <= runner.probe.context_tokens
        whole = ~joint.head_cut
        assert np.all(np.asarray(stream)[joint.first[whole]] == SEP_ID)
        windows += len(joint)
        positives += int((joint.labels > 0.5).sum())
    expected = (
        (index.test_windows, index.test_positives)
        if split == "test"
        else (index.train_windows, index.train_positives)
    )
    assert (windows, positives) == expected


@needs_shards
def test_r2_removes_exactly_the_stop_messages_and_keeps_the_m1_rows() -> None:
    telemetry = _telemetry()
    r0, r2 = _streams(telemetry), _streams(telemetry, "no_stop")
    for key in ("kelmarsh__test", "penmanshiel__test"):
        flags = r2.dropped[key]
        removed = message_spans(r0.stream(key))[0].size - message_spans(r2.stream(key))[0].size
        assert removed == int(flags.sum()) > 0
        m1 = load_windows(telemetry, key, stride=12, label="narrow_within_24h")
        a, b = r0.frame(m1), r2.frame(m1)
        assert np.array_equal(a.labels, b.labels) and np.array_equal(a.ends, b.ends)
        assert int(b.status_tokens.sum()) < int(a.status_tokens.sum())


@needs_shards
def test_tel_onlys_probe_input_is_bit_identical_after_the_change() -> None:
    gate = load_config(REPO / "configs/train/gate_check_v0.yaml", GateCheckConfig)
    inputs = open_probe_inputs(
        _paths(),
        gate.mixture_config,
        gate.ladder_config,
        gate.arm,
        gate.rung,
        gate.selection_windows,
        gate.held_out_source,
        "cpu",
    )
    assert inputs.pad_id is None and inputs.window_tokens == 1872
    # The evaluation windows: the M1 memmap slice, as WindowSampler has always read it.
    sampler = inputs.splits["selection"].sampler
    tokens, _, _ = next(sampler.epoch())
    first = sampler.sets[0]
    width = sampler.context_steps * sampler.tokens_per_step
    for position in range(tokens.shape[0]):
        start = int(first.starts[position]) * sampler.tokens_per_step
        expected = torch.from_numpy(np.asarray(first.tokens[start : start + width], np.int64))
        assert torch.equal(tokens[position], expected)
    # The training sampler: balanced_training_sampler's own batches, at the same seed.
    ladder = load_config(REPO / gate.ladder_config, LadderConfig)
    stage = ladder.risk
    assert isinstance(stage, PositiveAwareRiskStage)
    ours = probe_training_sampler(inputs, stage, 16).forever(1)
    theirs = balanced_training_sampler(inputs.telemetry, ladder, stage, 16).forever(1)
    for _ in range(5):
        a, b = next(ours), next(theirs)
        assert torch.equal(a[0], b[0]) and torch.equal(a[1], b[1])


@needs_shards
def test_the_joint_probe_draws_the_m1_probes_rows_at_the_same_seed() -> None:
    telemetry = _telemetry()
    runner = load_config(RUNNER, H1ArmsConfig)
    ladder = load_config(REPO / runner.ladder_config, LadderConfig)
    stage = ladder.risk
    assert isinstance(stage, PositiveAwareRiskStage)
    m1 = balanced_training_sampler(telemetry, ladder, stage, 16)
    streams = _streams(telemetry)
    joint = type("Inputs", (), {"telemetry": telemetry, "ladder": ladder, "tel_status": streams})
    sampler = probe_training_sampler(joint, stage, 16)  # type: ignore[arg-type]
    assert all(isinstance(s, JointWindowSet) for s in sampler.sets)
    ours, theirs = sampler.forever(3), m1.forever(3)
    for _ in range(5):
        a, b = next(ours), next(theirs)
        assert torch.equal(a[1], b[1]) and np.array_equal(a[2], b[2])
        assert a[0].shape == (16, 2048)


def test_the_controls_configuration_is_adr_0025s_and_leaves_v0_alone() -> None:
    config = load_config(CONTROLS, BagOfTokensV1Config)
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    adr = decisions[decisions.index("## ADR-0025 ") :]
    assert f"`{config.registered_in}`" in adr[: adr.index("\n### ")]
    assert config.vocab_size == VocabLayout.from_sizes(32768, 14, 256).total_size == 33952
    assert [c.mode for c in config.controls] == ["all", "status_only"]
    assert config.status_rows == ["all", "no_stop"] and config.device == "cpu"
    v0 = load_config(REPO / config.reference_config, BagOfTokensConfig)
    assert config_hash(v0) == "2b2827a9"  # the directory v0's saved scores live in
    assert config.runner_config == "configs/train/h1_arms_v0.yaml"


def test_the_f6_2_layout_names_its_markers() -> None:
    paths = _paths()
    layout = arms_layout(paths, RUNNER, REPO / "configs/eval/h1_gate_v0.yaml")
    assert layout.out_dir.name == "h1_arms_v0_03629ab1"
    assert layout.lm_record(2).name == "S2_joint_seed2_lm.json"
    assert layout.probe_record(2, False).name == "S2_joint_seed2_probe.json"
    assert layout.probe_record(2, True).name == "S2_tel_only_seed2_on_joint_probe.json"
    assert layout.tel_only[1].parent.name == "gate_check_v0_9697a266"
    assert layout.tel_only[3].parent.name == "seed_replication_v0_424c4f33"
