"""Windows inside segments and splits, and the checks that none of them leaks.

A model reads a window of ``context_steps`` steps ending at ``t`` and is scored on
whether an event starts in ``(t, t + H]``. Two things can carry information across a
split boundary, and both are checked here rather than trusted:

1. **A segment that runs through a split boundary.** A continuous stretch of telemetry
   that is half train and half validation lets a window drawn near the cut read the
   other split's steps. Segments are therefore cut where the split changes
   (:func:`cut_segments_at_splits`), and :func:`assert_segments_within_splits` fails if
   any segment still holds two splits.
2. **A window whose context or horizon crosses the boundary.** The context must lie in
   one segment, and the horizon must end before the split does: a training window whose
   24-hour horizon reaches into validation would be labelled by a validation event.
   :func:`window_ends` only admits windows that satisfy both, and
   :func:`assert_windows_within_splits` re-derives the split at each window's first
   step and last horizon step from the timestamps alone, independently of how the
   windows were chosen, and fails on any disagreement.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from faultline.data.common.splits import SplitsConfig, assign_splits

STEP_SECONDS = 600
_EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


class LeakageError(RuntimeError):
    """A segment or a window spans two splits."""


def _seconds(stamps: pd.Series[Any]) -> np.ndarray:
    return ((pd.to_datetime(stamps, utc=True) - _EPOCH) // pd.Timedelta(seconds=1)).to_numpy(
        dtype=np.int64
    )


def cut_segments_at_splits(segment_id: np.ndarray, split: np.ndarray) -> np.ndarray:
    """Start a new segment wherever the split changes inside one.

    Args:
        segment_id: Segment identifier per row, ``-1`` outside every segment.
        split: Split label per row.

    Returns:
        Identifiers that change whenever the segment or the split does; ``-1`` stays.
    """
    segment = np.asarray(segment_id, dtype=np.int64)
    labels = np.asarray(split, dtype=object)
    if len(segment) == 0:
        return segment.copy()
    inside = segment >= 0
    change = np.r_[True, (segment[1:] != segment[:-1]) | (labels[1:] != labels[:-1])]
    result = np.cumsum(change & inside) - 1
    result[~inside] = -1
    return result.astype(np.int64)


def assert_segments_within_splits(segment_id: np.ndarray, split: np.ndarray) -> int:
    """Fail if any segment holds rows of two splits.

    Args:
        segment_id: Segment identifier per row.
        split: Split label per row.

    Returns:
        The number of segments checked.

    Raises:
        LeakageError: If a segment spans two splits.
    """
    frame = pd.DataFrame({"segment": segment_id, "split": split})
    frame = frame[frame["segment"] >= 0]
    splits_per_segment = frame.groupby("segment")["split"].nunique()
    bad = splits_per_segment[splits_per_segment > 1]
    if not bad.empty:
        raise LeakageError(
            f"{len(bad)} segment(s) span two splits (for example {list(bad.index[:3])}); "
            "a window drawn near the cut would read the other split"
        )
    return int(len(splits_per_segment))


def _split_end(split: np.ndarray, config: SplitsConfig) -> np.ndarray:
    """The last second each row's split runs to, in integer seconds; no end for test."""
    train = _seconds(pd.Series([pd.Timestamp(config.time.train_until)]))[0]
    val = _seconds(pd.Series([pd.Timestamp(config.time.val_until)]))[0]
    ends = np.full(len(split), np.iinfo(np.int64).max, dtype=np.int64)
    ends[split == "train"] = train
    ends[split == "val"] = val
    return ends


def window_ends(
    frame: pd.DataFrame,
    config: SplitsConfig,
    horizon_steps: int,
    segment_column: str = "segment_id",
) -> np.ndarray:
    """Which rows can end a window whose context and horizon stay in bounds.

    A row ends a window when it lies in a segment, the ``context_steps`` steps ending at
    it lie in that segment, the step lands on the configured stride, and its horizon
    ``(t, t + H]`` ends before its split does.

    Args:
        frame: One turbine's rows, sorted by time, with the split, time and segment
            columns.
        config: The split specification.
        horizon_steps: The horizon, in steps.
        segment_column: Column holding the segment identifiers.

    Returns:
        A boolean array aligned with ``frame``.
    """
    if frame.empty:
        return np.zeros(0, dtype=bool)
    t = _seconds(frame[config.time_column])
    segment = frame[segment_column].to_numpy(dtype=np.int64)
    split = frame["split"].to_numpy(dtype=object)
    first = pd.Series(t).groupby(segment).transform("min").to_numpy()
    context = config.windows.context_steps
    ok = (segment >= 0) & (t - (context - 1) * STEP_SECONDS >= first)
    ok &= ((t // STEP_SECONDS) % config.windows.stride_steps) == 0
    ok &= t + horizon_steps * STEP_SECONDS <= _split_end(split, config)
    return np.asarray(ok, dtype=bool)


def assert_windows_within_splits(
    frame: pd.DataFrame,
    ends: np.ndarray,
    config: SplitsConfig,
    horizon_steps: int,
    segment_column: str = "segment_id",
) -> int:
    """Re-derive the split at each window's first step and horizon end, and compare.

    Args:
        frame: The rows the windows were drawn from.
        ends: Which rows end a window.
        config: The split specification.
        horizon_steps: The horizon, in steps.
        segment_column: Column holding the segment identifiers.

    Returns:
        The number of windows checked.

    Raises:
        LeakageError: If a window's context leaves its segment, or its first step or the
            end of its horizon lies in another split than its last step.
    """
    chosen = frame.loc[ends]
    if chosen.empty:
        return 0
    stamps = pd.to_datetime(chosen[config.time_column], utc=True)
    context = pd.Timedelta(minutes=10) * (config.windows.context_steps - 1)
    horizon = pd.Timedelta(minutes=10) * horizon_steps
    columns = list(dict.fromkeys([config.site_column, config.source_column]))
    columns = [c for c in columns if c in chosen.columns]
    probes = {}
    for name, when in (("start", stamps - context), ("horizon", stamps + horizon)):
        probe = chosen[columns].copy()
        probe[config.time_column] = when.to_numpy()
        probes[name] = assign_splits(probe, config).to_numpy()
    at_end = chosen["split"].to_numpy(dtype=object)
    crossing = (probes["start"] != at_end) | (probes["horizon"] != at_end)
    all_t = _seconds(frame[config.time_column])
    segment = frame[segment_column].to_numpy(dtype=np.int64)
    first = pd.Series(all_t).groupby(segment).transform("min").to_numpy()[ends]
    outside = _seconds(stamps - context) < first
    if crossing.any() or outside.any():
        raise LeakageError(
            f"{int(crossing.sum())} window(s) cross a split boundary and "
            f"{int(outside.sum())} leave their segment, at horizon {horizon_steps} steps"
        )
    return int(len(chosen))
