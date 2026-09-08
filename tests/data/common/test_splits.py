"""Site and time split assignment on synthetic rows."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from faultline.config import load_config
from faultline.data.common.splits import SplitsConfig, assign_splits, split_counts


def config(**overrides: object) -> SplitsConfig:
    payload: dict[str, object] = {
        "holdout_sites": ["hill_of_towie"],
        "time": {"train_until": "2021-12-31T23:59:59Z", "val_until": "2022-12-31T23:59:59Z"},
    }
    payload.update(overrides)
    return SplitsConfig.model_validate(payload)


def rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site": [
                "kelmarsh",
                "kelmarsh",
                "kelmarsh",
                "penmanshiel",
                "hill_of_towie",
                "hill_of_towie",
            ],
            "timestamp_utc": pd.to_datetime(
                [
                    "2019-06-01",
                    "2022-06-01",
                    "2023-06-01",
                    "2020-01-01",
                    "2019-06-01",  # a held-out site inside the training period
                    "2023-06-01",
                ],
                utc=True,
            ),
        }
    )


def test_shipped_split_config_loads(repo_root: Path) -> None:
    loaded = load_config(repo_root / "configs" / "data" / "splits_v0.yaml", SplitsConfig)
    assert loaded.holdout_sites == ["hill_of_towie"]
    assert loaded.time.val_until > loaded.time.train_until


def test_site_holdout_dominates_the_time_cut() -> None:
    labels = assign_splits(rows(), config())
    # a held-out site row inside the training period is still test
    assert list(labels) == ["train", "val", "test", "train", "test", "test"]


def test_split_counts_reports_all_three_labels() -> None:
    counts = split_counts(assign_splits(rows(), config()))
    assert counts == {"train": 2, "val": 1, "test": 3}


def test_no_holdout_sites_leaves_the_time_cut_alone() -> None:
    labels = assign_splits(rows(), config(holdout_sites=[]))
    assert list(labels)[-2:] == ["train", "test"]


def test_naive_config_timestamps_are_read_as_utc() -> None:
    spec = SplitsConfig.model_validate(
        {"time": {"train_until": "2021-12-31T23:59:59", "val_until": "2022-12-31T23:59:59"}}
    )
    labels = assign_splits(rows(), spec)
    assert list(labels)[:3] == ["train", "val", "test"]


def test_boundaries_are_inclusive() -> None:
    frame = pd.DataFrame(
        {
            "site": ["kelmarsh", "kelmarsh"],
            "timestamp_utc": pd.to_datetime(
                ["2021-12-31T23:59:59Z", "2022-12-31T23:59:59Z"], utc=True
            ),
        }
    )
    assert list(assign_splits(frame, config())) == ["train", "val"]


def test_validation_must_follow_training() -> None:
    with pytest.raises(ValidationError, match="strictly after"):
        SplitsConfig.model_validate(
            {"time": {"train_until": "2022-01-01T00:00:00Z", "val_until": "2021-01-01T00:00:00Z"}}
        )


def test_missing_columns_are_reported() -> None:
    with pytest.raises(KeyError, match="site"):
        assign_splits(pd.DataFrame({"timestamp_utc": []}), config())


def test_custom_column_names() -> None:
    frame = rows().rename(columns={"site": "farm", "timestamp_utc": "ts"})
    labels = assign_splits(frame, config(site_column="farm", time_column="ts"))
    assert len(labels) == len(frame)


def test_late_period_label_is_configurable() -> None:
    labels = assign_splits(rows(), config(late_period_split="val", holdout_sites=[]))
    assert list(labels)[2] == "val"


def test_labels_align_with_the_frame_index() -> None:
    frame = rows()
    frame.index = pd.RangeIndex(start=100, stop=106)
    labels = assign_splits(frame, config())
    assert list(labels.index) == list(frame.index)
