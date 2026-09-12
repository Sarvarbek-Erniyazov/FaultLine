"""The hybrid tail rule (ADR-0014), rule by rule.

The six rules the record states are fixed before the fit, so each one is a test rather
than an observation about the tables that came out.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from faultline.config import load_config
from faultline.data.telemetry.bins import (
    STARVED_TAIL_BIN,
    QuantileBinsConfig,
    tail_occupancy,
)
from faultline.data.telemetry.schemas import CORE_CHANNELS
from faultline.tokenizers.quantile_bins import QuantileBinTokenizer, fit_channel

N_BINS = 64
N_TAIL = 8


def skewed(seed: int = 7) -> np.ndarray:
    """A heavy-tailed channel with no point mass: a temperature that occasionally spikes."""
    rng = np.random.default_rng(seed)
    return np.concatenate([rng.normal(60.0, 3.0, 50_000), rng.normal(95.0, 12.0, 400)])


def test_each_tail_gets_exactly_n_tail_bins_of_equal_width() -> None:
    fitted = fit_channel(skewed(), N_BINS, point_masses=True, n_tail=N_TAIL)
    edges = np.array(fitted.edges)
    assert fitted.tail_bins == (N_TAIL, N_TAIL)
    lower, upper = edges[: N_TAIL + 1], edges[-(N_TAIL + 1) :]
    for widths in (np.diff(lower), np.diff(upper)):
        assert np.allclose(widths, widths[0])
    # and they meet the middle exactly at the training p0.5 and p99.5
    assert lower[-1] == pytest.approx(fitted.tail_edges[0])
    assert upper[0] == pytest.approx(fitted.tail_edges[1])


def test_the_tail_boundaries_are_the_training_half_percentiles() -> None:
    values = skewed()
    fitted = fit_channel(values, N_BINS, point_masses=True, n_tail=N_TAIL, tail_quantile=0.005)
    expected = np.quantile(values, [0.005, 0.995])
    assert fitted.tail_edges[0] == pytest.approx(expected[0])
    assert fitted.tail_edges[1] == pytest.approx(expected[1])


def test_the_channel_still_uses_at_most_n_bins() -> None:
    for n_tail in (0, 4, 8, 16):
        fitted = fit_channel(skewed(), N_BINS, point_masses=True, n_tail=n_tail)
        assert len(fitted.edges) - 1 <= N_BINS


def test_the_hybrid_narrows_the_extreme_bins_and_costs_the_middle() -> None:
    # The trade ADR-0014 pre-registers, as a mechanism rather than as an outcome on one
    # distribution: the extreme bins get much narrower, and the middle pays for it with
    # 2 * n_tail fewer quantile bins.
    values = skewed()
    plain = fit_channel(values, N_BINS, point_masses=True, n_tail=0)
    hybrid = fit_channel(values, N_BINS, point_masses=True, n_tail=N_TAIL)
    assert np.diff(hybrid.edges)[-1] < np.diff(plain.edges)[-1] / 3
    assert np.diff(hybrid.edges)[0] < np.diff(plain.edges)[0]

    lo, hi = hybrid.tail_edges

    def middle_bins(bins: list[float]) -> int:
        inside = np.array(bins)
        return len(inside[(inside >= lo) & (inside <= hi)]) - 1

    # Both fits spend the whole budget; the hybrid spends 2 * n_tail of it on the tails,
    # where pure quantiles spent barely one bin a side.
    assert len(hybrid.edges) == len(plain.edges) == N_BINS + 1
    assert middle_bins(hybrid.edges) == N_BINS - 2 * N_TAIL
    assert middle_bins(plain.edges) > middle_bins(hybrid.edges)


def test_a_tail_with_no_width_gives_its_bins_back_to_the_middle() -> None:
    # Rule 5. Half the values sit at exactly 0, so the training p0.5 is 0, which is the
    # range edge and a point mass at once: there is no lower tail to cut.
    values = np.concatenate([np.zeros(5_000), np.linspace(0.1, 50.0, 5_000)])
    fitted = fit_channel(values, N_BINS, point_masses=True, n_tail=N_TAIL)
    assert fitted.tail_bins[0] == 0
    assert fitted.tail_bins[1] == N_TAIL
    assert fitted.point_masses == [0.0]
    # the bins the absent tail would have taken are spent in the middle, not lost
    plain = fit_channel(values, N_BINS, point_masses=True, n_tail=0)
    assert len(fitted.edges) == len(plain.edges)


def test_a_value_outside_the_training_range_still_clamps_to_the_extreme_bin() -> None:
    # Rule 6, unchanged from v0.
    tokenizer = QuantileBinTokenizer.fit_values(
        {"t": skewed()}, ["t"], N_BINS, point_masses=True, n_tail=N_TAIL
    )
    ids = tokenizer.transform_channel(np.array([-500.0, 500.0]), "t")
    assert ids.tolist() == [0, tokenizer.bins_in_use("t") - 1]


def test_point_masses_are_carved_before_the_tails() -> None:
    # Rule 1. The mass keeps its exact bin whatever the tail rule does around it.
    rng = np.random.default_rng(3)
    values = np.concatenate([np.full(3_000, 17.1), rng.uniform(0.0, 40.0, 20_000)])
    fitted = fit_channel(values, N_BINS, point_masses=True, n_tail=N_TAIL)
    assert 17.1 in fitted.point_masses
    edges = np.array(fitted.edges)
    index = int(np.searchsorted(edges[1:-1], 17.1, side="right"))
    assert fitted.representatives[index] == pytest.approx(17.1)


def test_the_fit_records_what_each_tail_got() -> None:
    tokenizer = QuantileBinTokenizer.fit_values(
        {"t": skewed()}, ["t"], N_BINS, point_masses=True, n_tail=N_TAIL
    )
    assert tokenizer.meta["n_tail"] == N_TAIL
    assert tokenizer.meta["tails"]["t"]["lower_bins"] == N_TAIL
    occupancy = tail_occupancy(tokenizer, "t", skewed())
    assert len(occupancy.lower) == N_TAIL
    assert len(occupancy.upper) == N_TAIL
    assert occupancy.starved == sum(
        1 for c in [*occupancy.lower, *occupancy.upper] if c < STARVED_TAIL_BIN
    )


def test_tail_occupancy_of_a_channel_fitted_without_tails_is_empty() -> None:
    tokenizer = QuantileBinTokenizer.fit_values({"t": skewed()}, ["t"], N_BINS, point_masses=True)
    occupancy = tail_occupancy(tokenizer, "t", skewed())
    assert occupancy.lower == []
    assert occupancy.upper == []


def test_fixed_bins_that_cannot_fit_the_budget_are_refused() -> None:
    with pytest.raises(ValueError, match="do not fit"):
        fit_channel(skewed(), 8, point_masses=True, n_tail=8)


def test_the_configuration_refuses_tails_that_leave_no_quantile_bins() -> None:
    payload = {
        "telemetry_config": "configs/data/telemetry_v4.yaml",
        "channels": list(CORE_CHANNELS),
        "candidates": [64],
        "n_bins": 64,
        "n_bins_reason": "test",
        "n_tail": 32,
        "max_point_masses": 16,
    }
    with pytest.raises(ValidationError, match="leaves no quantile bins"):
        QuantileBinsConfig.model_validate(payload)


def test_the_shipped_configuration_carries_the_rule(repo_root: Path) -> None:
    shipped = load_config(
        repo_root / "configs" / "tokenizer" / "quantile_bins_v1.yaml", QuantileBinsConfig
    )
    assert shipped.n_tail == 16
    assert shipped.tail_quantile == 0.005
    assert shipped.point_masses is True
