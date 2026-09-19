"""F6-3's scoring (ADR-0025 §5, §3, §6): the plan, the channel masks, and the atomic write."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from faultline.data.joint.mixture_shards import interleave
from faultline.evaluation.checkpoint_selection import FIXED_FINAL, SELECTED
from faultline.evaluation.h1_scoring import (
    MaskedJointSampler,
    masked_joint_split,
    save_atomically,
    scoring_layout,
    scoring_plan,
    timing_path,
    window_mask_positions,
)
from faultline.evaluation.ladder import SplitEval
from faultline.evaluation.probe_control import ScoredWindows
from faultline.paths import ProjectPaths
from faultline.training.joint_windows import (
    SEP_ID,
    TXT_CLOSE_ID,
    TXT_OPEN_ID,
    JointWindowSampler,
    JointWindowSet,
    step_offsets,
)
from faultline.training.windows import WindowSet

REPO = Path(__file__).resolve().parents[2]
WIDTH = 13
STEPS = 144
CONTEXT = 2048
NAN_ID = 9
VALUE_IDS = 1184


def _stream(n: int, messages: dict[int, int]) -> np.ndarray:
    """``n`` telemetry steps (bin ids 96..1119), with one message of the given length on some."""
    block = np.zeros((n, WIDTH), dtype=np.int64)
    block[:, 0] = SEP_ID
    block[:, 1:] = 96 + (np.arange(n)[:, None] * 12 + np.arange(12)) % 1024
    steps = np.array(sorted(messages), dtype=np.int64)
    texts = [
        np.concatenate([[TXT_OPEN_ID], 2000 + np.arange(messages[s]), [TXT_CLOSE_ID]])
        for s in steps
    ]
    tokens, _ = interleave(block, steps, texts)
    return np.asarray(tokens)


def _split(tokens: np.ndarray, ends: np.ndarray, n: int) -> SplitEval:
    m1 = WindowSet(
        key="site__test",
        tokens=np.zeros(0, np.uint16),  # type: ignore[arg-type]
        starts=ends - STEPS + 1,
        ends=ends,
        labels=(ends % 2).astype(np.float32),
        years=np.full(ends.size, 2022),
    )
    window = JointWindowSet.frame(m1, tokens, STEPS, CONTEXT, WIDTH, n)
    sampler = JointWindowSampler(
        [window], batch_size=2, tokens_per_step=WIDTH, context_steps=STEPS, labelled=True
    )
    return SplitEval(
        sampler=sampler,
        sources=["site"],
        shares={"site": 0.0},
        years=np.full(ends.size, 2022),
        sets=np.zeros(ends.size, dtype=np.int64),
    )


def test_the_plan_is_the_briefs_27_scorings_in_order() -> None:
    plan = scoring_plan([1, 2, 3], ["farm_a", "farm_b", "farm_c"])
    assert len(plan) == 27 and len({s.name for s in plan}) == 27
    assert [s.stage for s in plan] == ["S1"] * 3 + ["S2"] * 3 + ["S3"] * 3 + ["S4"] * 3 + [
        "S5"
    ] * 9 + ["S6"] * 6
    assert [s.control for s in plan if s.stage == "S2"] == [True] * 3
    assert {s.windows for s in plan if s.stage == "S3"} == {"R2"}
    assert {s.windows for s in plan if s.stage == "S4"} == {"m1"}
    masks = [(s.seed, s.farm) for s in plan if s.stage == "S5"]
    assert masks == [(k, f) for k in (1, 2, 3) for f in ("farm_a", "farm_b", "farm_c")]
    s6 = [s for s in plan if s.stage == "S6"]
    assert [(s.seed, s.control) for s in s6] == [(1, False), (2, False), (3, False)] + [
        (1, True),
        (2, True),
        (3, True),
    ]
    assert {s.role for s in s6} == {SELECTED}
    assert {s.role for s in plan if s.stage != "S6"} == {FIXED_FINAL}
    assert plan[0].name == "S2_joint_seed1_final_R0"
    assert plan[3].name == "S2_tel_only_seed1_on_joint_final_R0"


def test_a_mask_overwrites_exactly_the_channel_slots_of_retained_steps_and_never_text() -> None:
    tokens = _stream(400, {150: 300, 260: 40, 399: 900})
    split = _split(tokens, np.array([200, 399]), 400)
    channels = np.array([8, 10, 11])
    view = masked_joint_split(split, channels, NAN_ID, VALUE_IDS)
    base, _, _ = next(split.sampler.epoch())
    masked, _, _ = next(view.sampler.epoch())
    window = split.sampler.sets[0]
    assert isinstance(window, JointWindowSet) and isinstance(view.sampler, MaskedJointSampler)
    for row in range(2):
        first, length = int(window.first[row]), int(window.length[row])
        seps = step_offsets(tokens[first : first + length])
        expected = np.zeros(CONTEXT, dtype=bool)
        expected[(seps[:, None] + channels[None, :]).ravel()] = True
        changed = (masked[row] != base[row]).numpy()
        assert np.array_equal(changed, expected)
        assert torch.all(masked[row, torch.from_numpy(expected)] == NAN_ID)
        text = (base[row] >= VALUE_IDS).numpy()
        assert text.any() and not (changed & text).any()
    retained = int(window.steps_retained.sum())
    assert view.sampler.masked == retained * channels.size


def test_a_head_cut_window_masks_only_the_slots_that_reach_into_it() -> None:
    offsets = np.array([0, 13, 26], dtype=np.int64)
    # The window starts inside step 1's telemetry: only step 1's slot 12 (token 25) is inside.
    positions = window_mask_positions(offsets, 18, 10, np.array([3, 12]), WIDTH)
    assert positions.tolist() == [25 - 18]


def test_a_mask_refuses_to_overwrite_a_non_telemetry_token() -> None:
    tokens = _stream(300, {250: 20})
    split = _split(tokens, np.array([299]), 300)
    view = masked_joint_split(split, np.array([1]), NAN_ID, value_ids=100)
    with pytest.raises(ValueError, match="non-telemetry"):
        next(view.sampler.epoch())


def test_scores_are_renamed_last_and_always_carry_their_sidecar(tmp_path: Path) -> None:
    tokens = _stream(300, {250: 20})
    split = _split(tokens, np.array([200, 299]), 300)
    path = tmp_path / "x_stride12_scores.npz"
    logits = np.array([0.5, -0.5], dtype=np.float32)
    labels = np.array([0.0, 1.0], dtype=np.float32)
    written = save_atomically(path, (logits, labels), split, -3.0, {"seconds": 1.5})
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "x_stride12_scores.npz",
        "x_stride12_scores.timing.json",
    ]
    assert json.loads(timing_path(path).read_text(encoding="utf-8"))["seconds"] == 1.5
    assert written.ends.tolist() == [200, 299] and written.prior_offset == -3.0
    assert ScoredWindows.load(path).same_windows(written)


RUNS = REPO / "checkpoints/h1_arms_v0_03629ab1/h1_arms_status.json"


@pytest.mark.skipif(not RUNS.is_file(), reason="F6-2's probes are not on this machine")
def test_the_layout_reads_f6_2s_probes_and_f3s_final_scores() -> None:
    layout = scoring_layout(ProjectPaths.resolve(), REPO / "configs/eval/h1_gate_v0.yaml")
    first, iii, selected = layout.plan[0], layout.plan[3], layout.plan[-1]
    assert layout.probe(first).name == "S2_joint_seed1_final_probe.pt"
    assert layout.probe(iii).name == "S2_tel_only_seed1_on_joint_final_probe.pt"
    assert layout.probe(selected).name == "S2_tel_only_seed3_on_joint_probe.pt"
    names = [layout.tel_only_scores(k).name for k in (1, 2, 3)]
    assert names == [
        "S2_trained_seed1_final_stride12_scores.npz",
        "S2_trained_seed2_stride12_scores.npz",  # seed 2 selected its last step
        "S2_trained_seed3_final_stride12_scores.npz",
    ]
    assert layout.out_dir.name == "h1_gate_v0_a3f6606a"
    assert list(layout.patterns) == ["farm_a", "farm_b", "farm_c"]
