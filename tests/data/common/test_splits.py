"""Site and time split assignment on synthetic rows."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from faultline.config import load_config
from faultline.data.common.splits import (
    SplitsConfig,
    assign_splits,
    check_eval_channels_against_maps,
    in_training_exclusion,
    split_counts,
)
from faultline.data.telemetry.adapters import ADAPTERS
from faultline.data.telemetry.schemas import CORE_CHANNELS, EXTENDED_CHANNELS


def config(**overrides: object) -> SplitsConfig:
    payload: dict[str, object] = {
        "holdout_sites": ["hill_of_towie"],
        "time": {"train_until": "2021-12-31T23:59:59Z", "val_until": "2022-12-31T23:59:59Z"},
    }
    payload.update(overrides)
    return SplitsConfig.model_validate(payload)


def exclusion(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": "penmanshiel",
        "start": "2018-03-01T00:00:00Z",
        "end": "2018-04-05T13:40:00Z",
        "channels": ["ambient_temp_c", "nacelle_temp_c"],
        "reason": "site-wide outage",
    }
    payload.update(overrides)
    return payload


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


def test_the_shipped_split_config_loads(repo_root: Path) -> None:
    loaded = load_config(repo_root / "configs" / "data" / "splits_v2.yaml", SplitsConfig)
    assert loaded.holdout_sites == ["hill_of_towie"]
    assert loaded.time.val_until > loaded.time.train_until
    # The shipped config holds a site out, so it must read core channels only.
    assert loaded.eval_channels == list(CORE_CHANNELS)
    assert "wind_direction_deg" not in loaded.eval_channels
    assert loaded.per_year_sites == ["hill_of_towie"]
    assert loaded.report_without_messages == ["anemometer defect"]


@pytest.mark.parametrize("name", ["splits_v0.yaml", "splits_v1.yaml"])
def test_a_split_that_evaluates_wind_direction_is_rejected(repo_root: Path, name: str) -> None:
    # M1b step 10: wind direction is extended (0% of the held-out site's 2019 grid). v0 and
    # v1 are left as they were written, and a leave-site-out evaluation reading it fails.
    with pytest.raises(ValidationError, match="wind_direction_deg"):
        load_config(repo_root / "configs" / "data" / name, SplitsConfig)


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


# -- the leave-site-out rule, on the real channel maps ---------------------------------


def test_the_v2_split_passes_the_leave_site_out_rule_on_the_real_maps(repo_root: Path) -> None:
    spec = load_config(repo_root / "configs" / "data" / "splits_v2.yaml", SplitsConfig)
    mappable = check_eval_channels_against_maps(spec, repo_root / "configs", list(ADAPTERS))
    # the maps are necessary, not sufficient: every mappable channel is evaluated except
    # the one the coverage rule demotes
    assert set(mappable) - set(spec.eval_channels) == {"wind_direction_deg"}
    assert spec.eval_channels == [c for c in mappable if c != "wind_direction_deg"]
    assert spec.site_column == "source"


def test_a_channel_the_held_out_site_cannot_map_fails_on_the_maps(
    tmp_path: Path, repo_root: Path
) -> None:
    # schemas.py still declares main_bearing_temp_c core; the maps now say the held-out
    # site does not publish it. The map check must win over the declaration.
    maps_dir = tmp_path / "configs" / "data" / "channel_map"
    shutil.copytree(repo_root / "configs" / "data" / "channel_map", maps_dir)
    path = maps_dir / "hill_of_towie.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["channels"]["main_bearing_temp_c"] = None
    payload["evidence"].pop("main_bearing_temp_c")
    payload["verified_absent"] = {"main_bearing_temp_c": "not in the lookup"}
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    spec = config(eval_channels=["wind_speed_ms", "main_bearing_temp_c"])
    with pytest.raises(ValueError, match=r"\['main_bearing_temp_c'\]"):
        check_eval_channels_against_maps(spec, tmp_path / "configs", list(ADAPTERS))


def adapter_rows() -> pd.DataFrame:
    """Rows shaped as the adapters write them: source id verbatim, human site name."""
    return pd.DataFrame(
        {
            "source": ["kelmarsh", "hill_of_towie"],
            "site": ["Kelmarsh", "Hill of Towie"],
            "timestamp_utc": pd.to_datetime(["2019-06-01", "2019-06-01"], utc=True),
        }
    )


def test_the_v0_split_bug_fails_loudly_instead_of_training_on_the_held_out_site(
    repo_root: Path,
) -> None:
    # Regression, M1a step 6c. splits_v0.yaml matches "hill_of_towie" against the site
    # column, which reads "Hill of Towie": the rule matches nothing, and before this check
    # the held-out site's 2019 rows were silently assigned to train. v0 no longer loads as
    # written (it evaluates wind direction), so its site rule is tested without that list.
    payload = yaml.safe_load(
        (repo_root / "configs" / "data" / "splits_v0.yaml").read_text(encoding="utf-8")
    )
    payload["eval_channels"] = [c for c in payload["eval_channels"] if c in CORE_CHANNELS]
    v0 = SplitsConfig.model_validate(payload)
    with pytest.raises(ValueError, match="would be left in training"):
        assign_splits(adapter_rows(), v0)


def test_the_v2_split_holds_the_same_rows_out(repo_root: Path) -> None:
    v2 = load_config(repo_root / "configs" / "data" / "splits_v2.yaml", SplitsConfig)
    labels = assign_splits(adapter_rows(), v2)
    assert list(labels) == ["train", "test"]


def test_a_held_out_site_that_names_no_source_is_rejected(repo_root: Path) -> None:
    # The v0 site-column mismatch in miniature: "Hill of Towie" matches no source id.
    spec = config(holdout_sites=["Hill of Towie"])
    with pytest.raises(KeyError, match="name no source"):
        check_eval_channels_against_maps(spec, repo_root / "configs", list(ADAPTERS))


# -- per-year reporting and the late test's second number ------------------------------


def test_a_per_year_site_must_be_held_out() -> None:
    assert config(per_year_sites=["hill_of_towie"]).per_year_sites == ["hill_of_towie"]
    with pytest.raises(ValidationError, match="not held out"):
        config(per_year_sites=["kelmarsh"])


# -- training exclusions (ADR-0008) ---------------------------------------------------


def test_the_shipped_exclusions_are_the_two_measured_spans(repo_root: Path) -> None:
    v2 = load_config(repo_root / "configs" / "data" / "splits_v2.yaml", SplitsConfig)
    spans = [(e.source, e.start_utc, e.end_utc) for e in v2.training_exclusions]
    assert spans == [
        (
            "penmanshiel",
            pd.Timestamp("2018-03-01T00:00Z"),
            pd.Timestamp("2018-04-05T13:40Z"),
        ),
        (
            "penmanshiel",
            pd.Timestamp("2018-04-21T05:40Z"),
            pd.Timestamp("2018-05-16T10:10Z"),
        ),
    ]
    assert all(len(e.channels) >= 2 and e.reason.strip() for e in v2.training_exclusions)


def test_an_exclusion_of_one_channel_is_not_an_outage() -> None:
    # A single channel's gap passes condition (c) or demotes the channel; it is never
    # excluded.
    with pytest.raises(ValidationError, match="at least two channels"):
        config(training_exclusions=[exclusion(channels=["ambient_temp_c"])])
    with pytest.raises(ValidationError, match="at least two channels"):
        config(training_exclusions=[exclusion(channels=["ambient_temp_c", "ambient_temp_c"])])


def test_an_exclusion_must_be_a_span_with_a_stated_reason() -> None:
    with pytest.raises(ValidationError, match="end after it starts"):
        config(training_exclusions=[exclusion(end="2018-03-01T00:00:00Z")])
    with pytest.raises(ValidationError, match="instrumentation fact"):
        config(training_exclusions=[exclusion(reason="  ")])
    with pytest.raises(ValidationError, match="not canonical"):
        config(training_exclusions=[exclusion(channels=["ambient_temp_c", "ambient"])])


def test_an_exclusion_never_touches_an_evaluation_site_or_period() -> None:
    with pytest.raises(ValidationError, match="never trains"):
        config(training_exclusions=[exclusion(source="hill_of_towie")])
    with pytest.raises(ValidationError, match="never trains"):
        config(eval_only_sources=["care"], training_exclusions=[exclusion(source="care")])
    with pytest.raises(ValidationError, match="past train_until"):
        config(
            training_exclusions=[
                exclusion(start="2022-03-01T00:00:00Z", end="2022-04-01T00:00:00Z")
            ]
        )


def test_rows_inside_an_exclusion_are_those_of_its_source_and_span() -> None:
    spec = config(site_column="source", training_exclusions=[exclusion()])
    frame = pd.DataFrame(
        {
            "source": ["penmanshiel", "penmanshiel", "penmanshiel", "kelmarsh"],
            "timestamp_utc": pd.to_datetime(
                [
                    "2018-02-28T23:50Z",
                    "2018-03-01T00:00Z",
                    "2018-04-05T13:40Z",
                    "2018-03-15T00:00Z",
                ],
                utc=True,
            ),
        }
    )
    assert in_training_exclusion(frame, spec).tolist() == [False, True, True, False]
    with pytest.raises(KeyError, match="cannot be matched"):
        in_training_exclusion(frame.drop(columns=["source"]).assign(site="x"), spec)


# -- evaluation-only sources (ADR-0004, docs/DATA_LICENSES.md) ------------------------


def test_the_shipped_config_keeps_care_out_of_training(repo_root: Path) -> None:
    loaded = load_config(repo_root / "configs" / "data" / "splits_v2.yaml", SplitsConfig)
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
