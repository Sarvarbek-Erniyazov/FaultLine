"""Short-gap imputation and the mandatory mask columns (ADR-0006)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from faultline.data.telemetry.impute import ImputeConfig, gap_lengths, impute_channel, impute_frame
from faultline.data.telemetry.schemas import IMPUTED_SUFFIX


def test_gap_lengths() -> None:
    mask = pd.Series([False, True, True, False, True, False])
    assert list(gap_lengths(mask)) == [0, 2, 2, 0, 1, 0]


def test_gap_lengths_no_gaps() -> None:
    assert list(gap_lengths(pd.Series([False, False]))) == [0, 0]


def test_short_gap_is_filled_long_gap_is_not() -> None:
    values = pd.Series([0.0, np.nan, 2.0, np.nan, np.nan, np.nan, np.nan, 7.0])
    filled, imputed = impute_channel(values, ImputeConfig(max_impute_steps=3))

    assert filled[1] == pytest.approx(1.0)  # 2-step bracket, linearly interpolated
    assert imputed[1]
    assert filled[3:7].isna().all()  # 4-step gap exceeds the limit
    assert not imputed[3:7].any()
    assert int(imputed.sum()) == 1


def test_ffill_method() -> None:
    values = pd.Series([5.0, np.nan, np.nan, 9.0])
    filled, imputed = impute_channel(values, ImputeConfig(max_impute_steps=2, method="ffill"))
    assert filled[1] == 5.0
    assert filled[2] == 5.0
    assert int(imputed.sum()) == 2


def test_leading_gap_is_not_invented() -> None:
    # limit_area="inside" means a gap with no left-hand value stays missing rather
    # than being back-filled from the future.
    values = pd.Series([np.nan, np.nan, 3.0, 4.0])
    filled, imputed = impute_channel(values, ImputeConfig(max_impute_steps=3))
    assert filled[0:2].isna().all()
    assert not imputed.any()


def test_zero_limit_disables_imputation() -> None:
    values = pd.Series([1.0, np.nan, 3.0])
    filled, imputed = impute_channel(values, ImputeConfig(max_impute_steps=0))
    assert filled.isna().sum() == 1
    assert not imputed.any()


def test_method_is_validated() -> None:
    with pytest.raises(ValueError, match="linear or ffill"):
        impute_channel(pd.Series([1.0, np.nan]), ImputeConfig(method="spline"))


def test_impute_frame_emits_mask_columns() -> None:
    frame = pd.DataFrame(
        {
            "wind_speed_ms": [1.0, np.nan, 3.0, 4.0],
            "power_kw": [10.0, 20.0, np.nan, 40.0],
        }
    )
    imputed, counts = impute_frame(frame, ["wind_speed_ms", "power_kw"], ImputeConfig())

    for channel in ("wind_speed_ms", "power_kw"):
        mask = f"{channel}{IMPUTED_SUFFIX}"
        assert mask in imputed.columns
        assert imputed[mask].dtype == bool
    assert counts == {"wind_speed_ms": 1, "power_kw": 1}
    assert imputed["wind_speed_ms"][1] == pytest.approx(2.0)
    assert imputed.loc[1, "wind_speed_ms" + IMPUTED_SUFFIX]
    assert not imputed.loc[0, "wind_speed_ms" + IMPUTED_SUFFIX]


def test_absent_channels_are_skipped() -> None:
    frame = pd.DataFrame({"wind_speed_ms": [1.0, np.nan, 3.0]})
    imputed, counts = impute_frame(frame, ["wind_speed_ms", "absent"], ImputeConfig())
    assert "absent" not in counts
    assert f"absent{IMPUTED_SUFFIX}" not in imputed.columns
