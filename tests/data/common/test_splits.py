"""Site and time split assignment on synthetic rows."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from faultline.config import load_config
from faultline.data.common.splits import SplitsConfig, assign_splits, split_counts
from faultline.data.telemetry.schemas import CORE_CHANNELS, EXTENDED_CHANNELS


def config(**overrides: object) -> SplitsConfig:
    payload: dict[str, object] = {
        "holdout_sites": ["hill_of_towie"],
        "time": {"train_until": "2021-12-31T23:59:59Z", "val_until": "2022-12-31T23:59:59Z"},
    }
    payload.update(overrides)
    return SplitsConfig.model_validate(payload)


def care_rows() -> pd.DataFrame:
    """Rows from a mix of sources, including the evaluation-only one."""
    return pd.DataFrame(
        {
            "source": ["kelmarsh", "care", "care", "care", "penmanshiel"],
            "site": ["kelmarsh", "farm_a", "farm_b", "farm_c", "penmanshiel"],
            "timestamp_utc": pd.to_datetime(
                [
                    "2019-06-01",  # train period
                    "2019-06-01",  # train period, but CARE
                    "2022-06-01",  # val period, but CARE
                    "2023-06-01",  # already test
                    "2019-06-01",  # train period
                ],
                utc=True,
            ),
        }
    )


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
    # The shipped config holds a site out, so it must read core channels only.
    assert loaded.eval_channels
    assert set(loaded.eval_channels) <= set(CORE_CHANNELS)


def test_leave_site_out_rejects_extended_channels() -> None:
    # An extended channel is not published by every training site, so a held-out-site
    # score computed over it measures instrumentation as well as transfer.
    with pytest.raises(ValidationError, match="extended channels"):
        config(eval_channels=[CORE_CHANNELS[0], EXTENDED_CHANNELS[0]])


def test_core_channels_are_accepted_for_leave_site_out() -> None:
    spec = config(eval_channels=list(CORE_CHANNELS))
    assert spec.eval_channels == list(CORE_CHANNELS)


def test_extended_channels_are_allowed_when_no_site_is_held_out() -> None:
    # Without a held-out site the rule does not apply: a within-site evaluation may
    # read whatever that site publishes.
    spec = config(holdout_sites=[], eval_channels=list(EXTENDED_CHANNELS))
    assert spec.eval_channels == list(EXTENDED_CHANNELS)


def test_unknown_eval_channel_is_rejected_either_way() -> None:
    for holdout in ([], ["hill_of_towie"]):
        with pytest.raises(ValidationError, match="not canonical channels"):
            config(holdout_sites=holdout, eval_channels=["gearbox_bearing_temp"])


def test_eval_channels_defaults_to_empty() -> None:
    assert config().eval_channels == []


# -- evaluation-only sources (ADR-0004, docs/DATA_LICENSES.md) ------------------------


def test_the_shipped_config_keeps_care_out_of_training(repo_root: Path) -> None:
    loaded = load_config(repo_root / "configs" / "data" / "splits_v0.yaml", SplitsConfig)
    assert loaded.eval_only_sources == ["care"]
    assert loaded.source_column == "source"


def test_an_eval_only_source_never_enters_train_or_val() -> None:
    spec = config(eval_only_sources=["care"], holdout_sites=[])
    labels = assign_splits(care_rows(), spec)
    assert list(labels) == ["train", "test", "test", "test", "train"]
    # the licence claim, stated the way the licence states it
    care = care_rows()["source"] == "care"
    assert set(labels[care.to_numpy()]) == {"test"}


def test_the_eval_only_rule_overrides_both_other_axes() -> None:
    # A CARE row sitting in the training period at a site that is not held out would
    # be train on every other axis. It is test anyway.
    spec = config(eval_only_sources=["care"], holdout_sites=["hill_of_towie"])
    labels = assign_splits(care_rows(), spec)
    assert labels.iloc[1] == "test"
    assert split_counts(labels) == {"train": 2, "val": 0, "test": 3}


def test_a_missing_source_column_is_fatal_when_the_rule_is_configured() -> None:
    # The failure mode worth guarding against is not a wrong label; it is a licence
    # constraint that quietly did not run.
    with pytest.raises(KeyError, match="licence constraint"):
        assign_splits(rows(), config(eval_only_sources=["care"]))


def test_no_source_column_is_needed_when_the_rule_is_not_configured() -> None:
    assert len(assign_splits(rows(), config())) == len(rows())


def test_an_unlisted_source_is_unaffected() -> None:
    spec = config(eval_only_sources=["care"], holdout_sites=[])
    labels = assign_splits(care_rows(), spec)
    assert labels.iloc[0] == "train"  # kelmarsh
    assert labels.iloc[4] == "train"  # penmanshiel


def test_eval_only_sources_defaults_to_empty() -> None:
    assert config().eval_only_sources == []


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
