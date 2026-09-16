"""The M3 mixture: stream interleaving, the attachment rule, runs, windows and the config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from faultline.config import load_config
from faultline.data.joint.mixture_shards import (
    attach_steps,
    contiguous_runs,
    interleave,
    nanoseconds,
    windows_in_run,
)
from faultline.training.mixture import STREAMS, JointMixtureConfig

REPO = Path(__file__).resolve().parents[3]


def test_messages_follow_their_step_in_order() -> None:
    steps = np.array([[8, 100], [8, 101], [8, 102]], dtype=np.uint16)
    messages = [np.array([4, 2000, 5]), np.array([4, 2001, 2002, 5]), np.array([4, 2003, 5])]
    # two messages on step 0, none on step 1, one on step 2
    tokens, offsets = interleave(steps, np.array([0, 0, 2]), messages)
    assert tokens.tolist() == [
        8, 100, 4, 2000, 5, 4, 2001, 2002, 5,
        8, 101,
        8, 102, 4, 2003, 5,
    ]  # fmt: skip
    assert offsets.tolist() == [0, 9, 11]


def test_a_run_without_messages_is_its_telemetry() -> None:
    steps = np.arange(12, dtype=np.uint16).reshape(4, 3)
    tokens, offsets = interleave(steps, np.zeros(0, dtype=np.int64), [])
    assert tokens.tolist() == list(range(12))
    assert offsets.tolist() == [0, 3, 6, 9]


def test_a_message_is_attached_to_the_first_step_at_or_after_its_start() -> None:
    grid = nanoseconds(pd.date_range("2020-01-01 12:00", periods=4, freq="10min", tz="UTC"))
    starts = pd.Series(
        pd.to_datetime(
            [
                "2020-01-01 12:13",  # rounds UP to 12:20, never down to 12:10
                "2020-01-01 12:10",  # exactly on a step stays on it
                "2020-01-01 12:31",  # 12:40 is not in the rows
            ],
            utc=True,
        )
    )
    assert attach_steps(starts, grid).tolist() == [2, 1, -1]


def test_runs_break_at_a_split_or_a_segment_change() -> None:
    frame = pd.DataFrame(
        {"split": ["train", "train", "train", "val", "val"], "segment_id": [0, 0, 1, 1, 1]}
    )
    runs = [(split, segment, rows.tolist()) for split, segment, rows in contiguous_runs(frame)]
    assert runs == [("train", 0, [0, 1]), ("train", 1, [2]), ("val", 1, [3, 4])]


def test_windows_start_on_stride_steps_and_end_inside_the_run() -> None:
    # 10 steps of 13 tokens: 130 tokens; a 52-token window starting at stride 2
    offsets = np.arange(10) * 13
    # starts 0, 26, 52, 78, 104; the last would end at 156 > 130
    assert windows_in_run(offsets, 130, 52, 2) == 4


def arms() -> list[dict[str, Any]]:
    mixture = {"tel": 0.3, "txt": 0.2, "tel+status": 0.5}
    payload = [
        {"name": "joint", "role": "default", "mixture": mixture},
        {"name": "raw", "role": "ablation", "mixture": mixture, "status_convention": "raw"},
    ]
    return payload


def config_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "telemetry_tokenizer_config": "t.yaml",
        "text_shards_config": "x.yaml",
        "status_sources": ["kelmarsh"],
        "training_sources": ["kelmarsh"],
        "context_tokens": 2048,
        "window_stride_steps": 6,
        "tokens_per_arm": 1000,
        "arms": arms(),
    }
    payload.update(overrides)
    return payload


def test_the_v0_file_names_the_three_streams_and_equal_budgets() -> None:
    config = load_config(REPO / "configs/train/joint_v0.yaml", JointMixtureConfig)
    assert STREAMS == ("tel", "txt", "tel+status")
    for arm in config.arms:
        assert sum(config.stream_tokens(arm).values()) == config.tokens_per_arm
    by_name = {arm.name: arm for arm in config.arms}
    assert by_name["joint"].status_convention == "normalized"
    assert by_name["joint_status_raw"].status_convention == "raw"


def test_a_mixture_that_does_not_sum_to_one_is_refused() -> None:
    payload = config_payload()
    payload["arms"][0]["mixture"] = {"tel": 0.5, "txt": 0.2}
    with pytest.raises(ValidationError, match="sum to"):
        JointMixtureConfig.model_validate(payload)


def test_a_raw_arm_without_a_normalized_twin_is_refused() -> None:
    payload = config_payload()
    payload["arms"][1]["mixture"] = {"tel": 0.5, "txt": 0.0, "tel+status": 0.5}
    with pytest.raises(ValidationError, match="normalized arm with the same"):
        JointMixtureConfig.model_validate(payload)


def test_a_wall_clock_bound_cannot_be_declared() -> None:
    with pytest.raises(ValidationError):
        JointMixtureConfig.model_validate(config_payload(gpu_hour_budget=4.0))


def test_an_unknown_stream_name_is_refused() -> None:
    payload = config_payload()
    payload["arms"][0]["mixture"] = {"telemetry": 1.0}
    with pytest.raises(ValidationError):
        JointMixtureConfig.model_validate(payload)
