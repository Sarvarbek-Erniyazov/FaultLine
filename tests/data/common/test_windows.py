"""Windows inside segments and splits, and the leakage checks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from faultline.data.common.splits import SplitsConfig, assign_splits
from faultline.data.common.windows import (
    LeakageError,
    assert_segments_within_splits,
    assert_windows_within_splits,
    cut_segments_at_splits,
    window_ends,
)

STEP = pd.Timedelta(minutes=10)
CUT = pd.Timestamp("2020-12-31T23:59:59Z")


def config(context: int = 3) -> SplitsConfig:
    return SplitsConfig.model_validate(
        {
            "site_column": "source",
            "time": {"train_until": "2020-12-31T23:59:59Z", "val_until": "2021-12-31T23:59:59Z"},
            "windows": {"context_steps": context},
        }
    )


def rows_across_the_cut(steps: int = 12) -> pd.DataFrame:
    """One turbine, one continuous stretch that runs from train into val."""
    stamps = [pd.Timestamp("2020-12-31T23:00Z") + STEP * i for i in range(steps)]
    frame = pd.DataFrame({"source": "kelmarsh", "timestamp_utc": stamps, "segment_id": 0})
    frame["split"] = assign_splits(frame, config()).to_numpy()
    return frame


def test_a_segment_through_the_cut_is_cut_in_two() -> None:
    frame = rows_across_the_cut()
    with pytest.raises(LeakageError, match="span two splits"):
        assert_segments_within_splits(frame["segment_id"].to_numpy(), frame["split"].to_numpy())
    cut = cut_segments_at_splits(frame["segment_id"].to_numpy(), frame["split"].to_numpy())
    assert sorted(set(cut)) == [0, 1]
    assert assert_segments_within_splits(cut, frame["split"].to_numpy()) == 2


def test_outside_rows_stay_outside() -> None:
    cut = cut_segments_at_splits(np.array([-1, 0, 0, -1, 1]), np.array(["train"] * 5))
    assert cut.tolist() == [-1, 0, 0, -1, 1]


def test_a_window_needs_its_context_in_one_segment_and_its_horizon_in_its_split() -> None:
    frame = rows_across_the_cut()
    frame["segment_id"] = cut_segments_at_splits(
        frame["segment_id"].to_numpy(), frame["split"].to_numpy()
    )
    ends = window_ends(frame, config(context=3), horizon_steps=2)
    # train runs 23:00-23:50 (6 steps): ends need 2 steps of context before them and
    # a horizon ending by 23:59:59, so 23:20 and 23:30 qualify, 23:40 does not
    assert frame.loc[ends, "timestamp_utc"].dt.strftime("%m-%d %H:%M").tolist()[:2] == [
        "12-31 23:20",
        "12-31 23:30",
    ]
    # val begins a fresh segment: its first window ends two steps in
    val_ends = frame.loc[ends & (frame["split"] == "val").to_numpy(), "timestamp_utc"]
    assert val_ends.iloc[0] == pd.Timestamp("2021-01-01T00:20Z")
    assert assert_windows_within_splits(frame, ends, config(context=3), horizon_steps=2) == len(
        frame.loc[ends]
    )


def test_a_window_whose_horizon_crosses_the_cut_is_caught() -> None:
    frame = rows_across_the_cut()
    frame["segment_id"] = cut_segments_at_splits(
        frame["segment_id"].to_numpy(), frame["split"].to_numpy()
    )
    ends = np.zeros(len(frame), dtype=bool)
    ends[5] = True  # 23:50 in train, horizon reaching into 2021
    with pytest.raises(LeakageError, match="cross a split boundary"):
        assert_windows_within_splits(frame, ends, config(context=1), horizon_steps=2)


def test_a_window_whose_context_leaves_its_segment_is_caught() -> None:
    frame = rows_across_the_cut()
    frame["segment_id"] = cut_segments_at_splits(
        frame["segment_id"].to_numpy(), frame["split"].to_numpy()
    )
    ends = np.zeros(len(frame), dtype=bool)
    ends[7] = True  # 00:10 in val, three steps of context reach back into train
    with pytest.raises(LeakageError):
        assert_windows_within_splits(frame, ends, config(context=3), horizon_steps=1)


def test_the_stride_thins_the_window_ends() -> None:
    frame = rows_across_the_cut(steps=6)
    spec = SplitsConfig.model_validate(
        {
            "site_column": "source",
            "time": {"train_until": "2021-12-31T23:59:59Z", "val_until": "2022-12-31T23:59:59Z"},
            "windows": {"context_steps": 1, "stride_steps": 2},
        }
    )
    frame["split"] = assign_splits(frame, spec).to_numpy()
    assert window_ends(frame, spec, horizon_steps=1).sum() == 3
