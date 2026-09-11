"""The telemetry tokenizer fit (M1b step 11), on synthetic final tables."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from faultline.config import load_config
from faultline.data.telemetry.bins import (
    QuantileBinsConfig,
    channel_fit,
    excluded_channel,
    out_of_range,
    split_values,
)
from faultline.data.telemetry.pipeline import stage_source_dir
from faultline.data.telemetry.schemas import CORE_CHANNELS, IMPUTED_SUFFIX
from faultline.paths import ProjectPaths
from faultline.tokenizers.quantile_bins import QuantileBinTokenizer


def config(**overrides: object) -> QuantileBinsConfig:
    payload: dict[str, object] = {
        "telemetry_config": "configs/data/telemetry_v3.yaml",
        "channels": list(CORE_CHANNELS),
        "candidates": [64, 128, 256],
        "n_bins": 256,
        "n_bins_reason": "the finest candidate",
    }
    payload.update(overrides)
    return QuantileBinsConfig.model_validate(payload)


def test_the_shipped_configuration_loads(repo_root: Path) -> None:
    shipped = load_config(
        repo_root / "configs" / "tokenizer" / "quantile_bins_v0.yaml", QuantileBinsConfig
    )
    assert shipped.fit_split == "train"
    assert shipped.n_bins == 256
    assert shipped.channels == list(CORE_CHANNELS)
    assert shipped.excluded == {"care": ["power_kw"]}


def test_the_configuration_refuses_what_the_fit_could_not_honour() -> None:
    with pytest.raises(ValidationError, match="not one of the candidates"):
        config(n_bins=512)
    with pytest.raises(ValidationError, match="do not fit the bin block"):
        config(candidates=[64, 2048], n_bins=64)
    with pytest.raises(ValidationError, match="every core channel in identifier order"):
        config(channels=list(reversed(CORE_CHANNELS)))
    with pytest.raises(ValidationError, match="every core channel"):
        config(channels=[*CORE_CHANNELS, "wind_direction_deg"])
    with pytest.raises(ValidationError, match="needs a reason"):
        config(excluded={"care": ["power_kw"]})
    with pytest.raises(ValidationError, match="not fitted"):
        config(excluded={"care": ["wind_direction_deg"]}, exclusion_reasons={"care": "x"})
    with pytest.raises(ValidationError):
        config(fit_split="val")


def write_final(paths: ProjectPaths, source: str, frame: pd.DataFrame, name: str) -> None:
    destination = stage_source_dir(paths, "final", source)
    frame.to_parquet(destination / name, index=False)


def test_only_the_split_asked_for_is_gathered_and_imputed_values_are_not(
    repo_paths: ProjectPaths,
) -> None:
    frame = pd.DataFrame(
        {
            "split": ["train", "train", "train", "val"],
            "power_kw": [1.0, 2.0, np.nan, 9.0],
            f"power_kw{IMPUTED_SUFFIX}": [False, True, False, False],
        }
    )
    write_final(repo_paths, "kelmarsh", frame, "K1__2019.parquet")
    gathered = split_values(repo_paths, ["kelmarsh"], ["power_kw"], "train")
    assert gathered.values["power_kw"].tolist() == [1.0]
    assert gathered.imputed == {"power_kw": 1}
    assert gathered.rows == {"kelmarsh": 3}
    both = split_values(repo_paths, ["kelmarsh"], ["power_kw"], "train", include_imputed=True)
    assert both.values["power_kw"].tolist() == [1.0, 2.0]


def test_a_channel_fit_measures_errors_masses_and_end_bins() -> None:
    rng = np.random.default_rng(6)
    train = np.concatenate([np.zeros(4000), np.round(rng.uniform(1, 90, 6000), 2)])
    val = np.concatenate([np.zeros(400), np.round(rng.uniform(1, 90, 600), 2)])
    tokenizer = QuantileBinTokenizer.fit_values(
        {"pitch": train}, ["pitch"], n_bins=16, point_masses=True
    )
    fit = channel_fit(tokenizer, "pitch", train, val)
    assert fit.masses == [(0.0, pytest.approx(0.4))]
    assert fit.bins <= 16
    assert 0 < fit.train_error < 1
    assert fit.first == pytest.approx(0.4)  # the mass is the lowest value, so the first bin


def test_values_outside_the_training_range_are_counted_per_year(
    repo_paths: ProjectPaths,
) -> None:
    tokenizer = QuantileBinTokenizer.fit_values(
        {"pitch_angle_deg": np.linspace(0, 90, 100)}, ["pitch_angle_deg"], n_bins=8
    )
    frame = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(
                ["2019-01-01", "2019-06-01", "2023-01-01", "2023-06-01"], utc=True
            ),
            "pitch_angle_deg": [-1.5, 10.0, -1.0, 95.0],
        }
    )
    write_final(repo_paths, "hill_of_towie", frame, "T01__2019.parquet")
    tally = out_of_range(repo_paths, "hill_of_towie", tokenizer)
    assert tally.years() == [2019, 2023]
    assert tally.below[("pitch_angle_deg", 2019)] == 1
    assert tally.above[("pitch_angle_deg", 2019)] == 0
    assert (tally.below[("pitch_angle_deg", 2023)], tally.above[("pitch_angle_deg", 2023)]) == (
        1,
        1,
    )


def test_normalised_power_would_read_as_idle(repo_paths: ProjectPaths) -> None:
    tokenizer = QuantileBinTokenizer.fit_values(
        {"power_kw": np.linspace(-20, 2050, 1000)}, ["power_kw"], n_bins=64
    )
    write_final(
        repo_paths,
        "care",
        pd.DataFrame({"power_kw": [0.0, 0.5, 1.05, np.nan]}),
        "farm_a__2022.parquet",
    )
    check = excluded_channel(repo_paths, "care", "power_kw", tokenizer)
    assert (check.values, check.low, check.high) == (3, 0.0, 1.05)
    assert check.idle == 1.0
