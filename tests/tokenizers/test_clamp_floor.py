"""The population floor on the outermost bin (ADR-0015), rule by rule.

The rule was fixed before the v2 fit, so each clause is a test rather than an observation
about the tables that came out. The clause under test is the one ADR-0014 could not have
written: a fixed-width tail gives its outermost bin a *nominal* width, and the outermost
bin is the clamp target for every value beyond the training range, so its *effective*
width is unbounded. A catch-all that is also the rarest token is the defect.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from faultline.config import load_config
from faultline.data.telemetry.bins import QuantileBinsConfig
from faultline.data.telemetry.schemas import CORE_CHANNELS
from faultline.tokenizers.quantile_bins import ChannelBins, QuantileBinTokenizer, fit_channel

N_BINS = 64
N_TAIL = 8
FLOOR = 0.001


def skewed(seed: int = 7) -> np.ndarray:
    """A heavy-tailed channel with no point mass: a temperature that occasionally spikes."""
    rng = np.random.default_rng(seed)
    return np.concatenate([rng.normal(60.0, 3.0, 50_000), rng.normal(95.0, 12.0, 400)])


def occupancy(fitted: ChannelBins, values: np.ndarray) -> np.ndarray:
    """Training values per bin, binned exactly as the tokenizer bins them."""
    interior = np.asarray(fitted.edges[1:-1], dtype=float)
    ids = np.clip(np.searchsorted(interior, values, side="right"), 0, len(fitted.edges) - 2)
    return np.bincount(ids, minlength=len(fitted.edges) - 1)


def test_the_floor_fills_both_clamp_bins() -> None:
    values = skewed()
    floor = int(np.ceil(FLOOR * values.size))
    laid = occupancy(fit_channel(values, N_BINS, point_masses=True, n_tail=N_TAIL), values)
    floored = fit_channel(values, N_BINS, point_masses=True, n_tail=N_TAIL, clamp_floor=FLOOR)
    held = occupancy(floored, values)
    # the defect, and its repair: the clamp bins were the rarest tokens of the channel
    assert laid[0] < floor and laid[-1] < floor
    assert held[0] >= floor and held[-1] >= floor


def test_the_floor_merges_only_inward_and_never_eats_the_middle() -> None:
    # However high the floor, the boundary with the quantile middle survives, so each
    # tail keeps at least one bin and the middle keeps every bin it was given.
    values = skewed()
    greedy = fit_channel(values, N_BINS, point_masses=True, n_tail=N_TAIL, clamp_floor=0.4)
    assert greedy.tail_bins == (1, 1)
    assert greedy.clamp_merges == (N_TAIL - 1, N_TAIL - 1)
    assert greedy.edges[1] == pytest.approx(greedy.tail_edges[0])
    assert greedy.edges[-2] == pytest.approx(greedy.tail_edges[1])


def test_a_floor_of_zero_lays_the_bins_exactly_as_v1_did() -> None:
    values = skewed()
    v1 = fit_channel(values, N_BINS, point_masses=True, n_tail=N_TAIL)
    v2_off = fit_channel(values, N_BINS, point_masses=True, n_tail=N_TAIL, clamp_floor=0.0)
    assert v2_off.edges == v1.edges
    assert v2_off.clamp_merges == (0, 0)


def test_what_the_floor_merges_away_goes_back_to_the_middle() -> None:
    # The bins are not lost, exactly as rule 5 of ADR-0014 does not lose them: the channel
    # still spends its whole budget, and the middle is finer for it.
    values = skewed()
    laid = fit_channel(values, N_BINS, point_masses=True, n_tail=N_TAIL)
    floored = fit_channel(values, N_BINS, point_masses=True, n_tail=N_TAIL, clamp_floor=FLOOR)
    assert len(floored.edges) == len(laid.edges) == N_BINS + 1
    assert sum(floored.clamp_merges) > 0

    def middle_bins(fitted: ChannelBins) -> int:
        lo, hi = fitted.tail_edges
        inside = np.asarray(fitted.edges)
        return len(inside[(inside >= lo) & (inside <= hi)]) - 1

    assert middle_bins(floored) == middle_bins(laid) + sum(floored.clamp_merges)


def test_a_point_mass_bounding_the_clamp_bin_stops_the_merge() -> None:
    # A point mass keeps its exact bin whatever the floor wants (rule 1 outranks the
    # floor). Where one lies below the outermost bin's boundary it caps that bin's width,
    # so merging further would widen nothing, and the merge stops there.
    rng = np.random.default_rng(11)
    values = np.concatenate(
        [np.linspace(0.0, 0.4, 210), np.full(790, 0.45), rng.uniform(0.5, 100.0, 199_000)]
    )
    fitted = fit_channel(values, 256, point_masses=True, n_tail=4, clamp_floor=FLOOR)
    assert fitted.point_masses == [0.45]
    held = occupancy(fitted, values)
    assert held[1] == 790  # the mass keeps its own bin, unmerged
    assert held[0] == 210  # and bounds the clamp bin, which is not merged across it
    assert fitted.clamp_merges[0] == 3


def test_the_fit_records_what_the_floor_merged() -> None:
    tokenizer = QuantileBinTokenizer.fit_values(
        {"t": skewed()}, ["t"], N_BINS, point_masses=True, n_tail=N_TAIL, clamp_floor=FLOOR
    )
    assert tokenizer.meta["clamp_floor"] == FLOOR
    tails = tokenizer.meta["tails"]["t"]
    assert tails["lower_merged"] + tails["upper_merged"] > 0
    assert tails["lower_bins"] == N_TAIL - tails["lower_merged"]
    assert tails["upper_bins"] == N_TAIL - tails["upper_merged"]


def _payload(**overrides: object) -> dict[str, object]:
    return {
        "telemetry_config": "configs/data/telemetry_v4.yaml",
        "channels": list(CORE_CHANNELS),
        "candidates": [256],
        "n_bins": 256,
        "n_bins_reason": "test",
        "n_tail": 4,
        "clamp_floor": FLOOR,
        **overrides,
    }


def test_the_configuration_refuses_a_floor_without_tails() -> None:
    with pytest.raises(ValidationError, match="needs n_tail > 0"):
        QuantileBinsConfig.model_validate(_payload(n_tail=0))


def test_the_configuration_refuses_a_reference_fit_already_measured() -> None:
    # The pure-quantile control is always measured, and so is the chosen fit; listing
    # either again would print the same column twice and read as corroboration.
    duplicates = (
        {"label": "again", "n_tail": 0, "clamp_floor": 0.0},
        {"label": "again", "n_tail": 4, "clamp_floor": FLOOR},
    )
    for repeat in duplicates:
        with pytest.raises(ValidationError, match="repeats a fit already measured"):
            QuantileBinsConfig.model_validate(_payload(reference_fits=[repeat]))


def test_the_configuration_refuses_a_curve_that_omits_the_chosen_n_tail() -> None:
    with pytest.raises(ValidationError, match="does not measure the chosen n_tail"):
        QuantileBinsConfig.model_validate(_payload(tail_curve=[16, 8, 2]))


def test_the_shipped_configuration_carries_the_rule(repo_root: Path) -> None:
    shipped = load_config(
        repo_root / "configs" / "tokenizer" / "quantile_bins_v2.yaml", QuantileBinsConfig
    )
    assert shipped.n_tail == 4
    assert shipped.clamp_floor == FLOOR
    assert shipped.tail_quantile == 0.005
    assert [r.n_tail for r in shipped.reference_fits] == [16]
    assert shipped.tail_curve == [16, 12, 8, 4, 2]


def test_the_superseded_configuration_is_untouched(repo_root: Path) -> None:
    # v1 is the fit v2 supersedes and the one the report compares against; a config a run
    # has read is never edited, so it may not acquire the floor. (v0 is older still and no
    # longer loads at all: it names `power_kw`, which ADR-0013 renamed -- ADR-0011 records
    # that, and it is why the comparison is made by refitting rather than by re-running.)
    shipped = load_config(
        repo_root / "configs" / "tokenizer" / "quantile_bins_v1.yaml", QuantileBinsConfig
    )
    assert shipped.n_tail == 16
    assert shipped.clamp_floor == 0.0
    assert shipped.reference_fits == []
    assert shipped.tail_curve == []
