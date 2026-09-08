"""Quantile bin tokenizer: monotonicity, coverage, NaN routing, round trip."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from faultline.tokenizers.quantile_bins import MISSING_BIN, QuantileBinTokenizer

CHANNELS = ["wind_speed_ms", "power_kw"]


@pytest.fixture
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(20260909)
    return pd.DataFrame(
        {
            "wind_speed_ms": rng.uniform(0, 25, 5000),
            "power_kw": rng.uniform(0, 2050, 5000),
        }
    )


@pytest.fixture
def tokenizer(frame: pd.DataFrame) -> QuantileBinTokenizer:
    return QuantileBinTokenizer.fit(frame, CHANNELS, n_bins=16)


def test_fit_produces_monotonic_edges(tokenizer: QuantileBinTokenizer) -> None:
    for channel in CHANNELS:
        edges = tokenizer.edges[channel]
        assert len(edges) == tokenizer.n_bins + 1
        assert all(a <= b for a, b in pairwise(edges))


def test_fit_records_provenance(tokenizer: QuantileBinTokenizer) -> None:
    assert tokenizer.is_fitted
    assert tokenizer.meta["n_bins"] == 16
    assert tokenizer.meta["fit_rows"] == 5000
    assert len(tokenizer.meta["config_hash"]) == 8
    assert "fitted_at" in tokenizer.meta


def test_bins_are_roughly_equal_occupancy(tokenizer: QuantileBinTokenizer, frame) -> None:
    binned = tokenizer.transform(frame)
    counts = np.bincount(binned[:, 0], minlength=tokenizer.n_bins)
    expected = len(frame) / tokenizer.n_bins
    # quantile binning, so occupancy should be within a few percent of uniform
    assert counts.min() > expected * 0.8
    assert counts.max() < expected * 1.2


def test_every_value_lands_in_range(tokenizer: QuantileBinTokenizer, frame) -> None:
    binned = tokenizer.transform(frame)
    assert binned.shape == (len(frame), len(CHANNELS))
    assert binned.min() >= 0
    assert binned.max() <= tokenizer.n_bins - 1


def test_values_outside_the_fitted_range_clamp(tokenizer: QuantileBinTokenizer) -> None:
    values = np.array([-1e9, 1e9])
    binned = tokenizer.transform_channel(values, "wind_speed_ms")
    assert binned[0] == 0
    assert binned[1] == tokenizer.n_bins - 1


def test_monotonic_values_give_monotonic_bins(tokenizer: QuantileBinTokenizer) -> None:
    values = np.linspace(0, 25, 200)
    binned = tokenizer.transform_channel(values, "wind_speed_ms")
    assert all(a <= b for a, b in pairwise(binned))


def test_missing_values_route_to_the_sentinel(tokenizer: QuantileBinTokenizer) -> None:
    values = np.array([5.0, np.nan, np.inf, -np.inf, 10.0])
    binned = tokenizer.transform_channel(values, "wind_speed_ms")
    assert binned[1] == MISSING_BIN
    assert binned[2] == MISSING_BIN
    assert binned[3] == MISSING_BIN
    assert binned[0] != MISSING_BIN
    assert binned[4] != MISSING_BIN


def test_absent_channel_becomes_all_missing(tokenizer: QuantileBinTokenizer) -> None:
    partial = pd.DataFrame({"wind_speed_ms": [1.0, 2.0, 3.0]})
    binned = tokenizer.transform(partial)
    assert (binned[:, 1] == MISSING_BIN).all()
    assert (binned[:, 0] != MISSING_BIN).all()


def test_inverse_returns_midpoints_and_nan(tokenizer: QuantileBinTokenizer) -> None:
    ids = np.array([0, 5, MISSING_BIN, tokenizer.n_bins - 1])
    values = tokenizer.inverse(ids, "wind_speed_ms")
    assert np.isnan(values[2])
    assert not np.isnan(values[0])
    assert values[0] < values[1] < values[3]


def test_round_trip_lands_in_the_same_bin(tokenizer: QuantileBinTokenizer) -> None:
    original = np.array([3.0, 8.0, 14.0, 21.0])
    ids = tokenizer.transform_channel(original, "wind_speed_ms")
    midpoints = tokenizer.inverse(ids, "wind_speed_ms")
    assert list(tokenizer.transform_channel(midpoints, "wind_speed_ms")) == list(ids)


def test_channel_index_is_the_fit_order(tokenizer: QuantileBinTokenizer) -> None:
    assert tokenizer.channel_index("wind_speed_ms") == 0
    assert tokenizer.channel_index("power_kw") == 1
    with pytest.raises(KeyError):
        tokenizer.channel_index("absent")


def test_save_and_load_round_trip(tokenizer: QuantileBinTokenizer, tmp_path: Path) -> None:
    path = tokenizer.save(tmp_path / "bins.json")
    restored = QuantileBinTokenizer.load(path)
    assert restored.channels == tokenizer.channels
    assert restored.n_bins == tokenizer.n_bins
    assert restored.edges == tokenizer.edges
    assert restored.meta["config_hash"] == tokenizer.meta["config_hash"]

    values = np.array([2.0, 12.0, np.nan])
    assert list(restored.transform_channel(values, "wind_speed_ms")) == list(
        tokenizer.transform_channel(values, "wind_speed_ms")
    )


def test_unfitted_tokenizer_refuses_to_transform() -> None:
    with pytest.raises(RuntimeError, match="not fitted"):
        QuantileBinTokenizer(channels=CHANNELS, n_bins=8).transform(pd.DataFrame())


def test_too_few_bins_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        QuantileBinTokenizer(channels=CHANNELS, n_bins=1)


def test_missing_channel_at_fit_time_is_rejected(frame: pd.DataFrame) -> None:
    with pytest.raises(KeyError, match="missing from the fit table"):
        QuantileBinTokenizer.fit(frame, [*CHANNELS, "absent"], n_bins=8)


def test_all_missing_channel_is_rejected() -> None:
    frame = pd.DataFrame({"a": [np.nan, np.nan]})
    with pytest.raises(ValueError, match="no finite values"):
        QuantileBinTokenizer.fit(frame, ["a"], n_bins=4)


def test_sampling_caps_the_fit_rows(frame: pd.DataFrame) -> None:
    tokenizer = QuantileBinTokenizer.fit(frame, CHANNELS, n_bins=8, sample_rows=100)
    assert tokenizer.meta["fit_rows"] == 100
    assert tokenizer.meta["fit_rows_available"] == 5000


def test_constant_channel_still_bins() -> None:
    # Duplicate edges are legal: some bins are simply empty. The id space stays the
    # configured width so the vocabulary layout does not change per channel.
    frame = pd.DataFrame({"a": [4.0] * 100})
    tokenizer = QuantileBinTokenizer.fit(frame, ["a"], n_bins=8)
    binned = tokenizer.transform_channel(np.array([4.0]), "a")
    assert 0 <= binned[0] <= 7
