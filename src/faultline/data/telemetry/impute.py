"""Short-gap imputation with mandatory missingness masks (ADR-0006).

Only gaps up to ``max_impute_steps`` are filled. A longer hole is left missing and
is handled by segmentation instead, because interpolating across hours of silence
manufactures a plausible machine that was not running.

Every imputed channel gains a boolean ``<channel>__imputed`` companion column. That
column is not bookkeeping: it is a model input. Sensor dropouts cluster around the
events this project predicts, and a model that cannot see which values were
invented would be scored on its own guesses under modality shift.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from faultline.config import StrictModel
from faultline.data.telemetry.schemas import IMPUTED_SUFFIX
from faultline.logging_utils import get_logger

logger = get_logger(__name__)


class ImputeConfig(StrictModel):
    """Short-gap imputation settings.

    Attributes:
        max_impute_steps: Longest run of consecutive missing steps that is filled.
        method: ``linear`` interpolates between the bracketing values, ``ffill``
            carries the last observation forward.
    """

    max_impute_steps: int = 3
    method: str = "linear"


def gap_lengths(mask: pd.Series[Any]) -> pd.Series[Any]:
    """Compute, for each missing entry, the length of the run it belongs to.

    Args:
        mask: Boolean Series that is ``True`` where the value is missing.

    Returns:
        An integer Series holding the run length at every missing position and 0
        elsewhere.
    """
    values = mask.to_numpy(dtype=bool)
    lengths = np.zeros(values.shape[0], dtype=np.int64)
    if not values.any():
        return pd.Series(lengths, index=mask.index)
    start = 0
    while start < len(values):
        if not values[start]:
            start += 1
            continue
        end = start
        while end < len(values) and values[end]:
            end += 1
        lengths[start:end] = end - start
        start = end
    return pd.Series(lengths, index=mask.index)


def impute_channel(
    values: pd.Series[Any], config: ImputeConfig
) -> tuple[pd.Series[Any], pd.Series[Any]]:
    """Fill short gaps in one channel and report which entries were filled.

    Args:
        values: Channel values, ordered on the regular time grid.
        config: Imputation settings.

    Returns:
        The filled series and a boolean series marking imputed positions.

    Raises:
        ValueError: If the method is not recognised.
    """
    if config.method not in {"linear", "ffill"}:
        raise ValueError(f"impute.method must be linear or ffill, got {config.method!r}")

    numeric = pd.to_numeric(values, errors="coerce")
    missing = numeric.isna()
    if not missing.any() or config.max_impute_steps <= 0:
        return numeric, pd.Series(False, index=values.index)

    short = missing & (gap_lengths(missing) <= config.max_impute_steps)
    if config.method == "linear":
        filled = numeric.interpolate(method="linear", limit_area="inside")
    else:
        filled = numeric.ffill()

    result = numeric.copy()
    result[short] = filled[short]
    imputed = short & result.notna()
    return result, imputed


def impute_frame(
    frame: pd.DataFrame, channels: list[str], config: ImputeConfig
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Impute short gaps across a set of channels, adding the mask columns.

    Args:
        frame: Wide telemetry table on a regular grid.
        channels: Channels to impute; absent ones are skipped.
        config: Imputation settings.

    Returns:
        The table with filled values and ``<channel>__imputed`` columns, and the
        number of imputed steps per channel.
    """
    result = frame.copy()
    counts: dict[str, int] = {}
    for name in channels:
        if name not in result.columns:
            continue
        filled, imputed = impute_channel(result[name], config)
        result[name] = filled
        result[f"{name}{IMPUTED_SUFFIX}"] = imputed.fillna(False).astype(bool)
        counts[name] = int(imputed.sum())
    total = sum(counts.values())
    if total:
        logger.info("imputed %d values across %d channels", total, len(counts))
    return result, counts
