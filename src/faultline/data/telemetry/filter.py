"""Telemetry filtering: coverage thresholds and gap segmentation.

A sequence model cannot train across a three-month outage as if it were a single
continuous history, and a channel that is absent for most of a turbine-year is
noise in the vocabulary. This module answers both questions with explicit,
configured thresholds and reports what each one removed.

Segments are the unit the model actually consumes: a maximal run of grid steps with
no gap longer than ``segment_break_steps``. Windows are drawn inside a segment and
never across a break.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from faultline.config import StrictModel
from faultline.logging_utils import get_logger

logger = get_logger(__name__)


class TelemetryFilterConfig(StrictModel):
    """Coverage and segmentation thresholds.

    Attributes:
        min_channel_nonnull_frac: Minimum non-null fraction for a channel to be kept
            within a turbine-year.
        min_turbine_year_nonnull_frac: Minimum mean non-null fraction across kept
            channels for a turbine-year to be kept at all.
        segment_break_steps: Number of consecutive missing grid steps that starts a
            new segment.
        min_segment_steps: Minimum length of a retained segment, in grid steps.
    """

    min_channel_nonnull_frac: float = 0.50
    min_turbine_year_nonnull_frac: float = 0.30
    segment_break_steps: int = 6
    min_segment_steps: int = 144


def channel_coverage(frame: pd.DataFrame, channels: list[str]) -> dict[str, float]:
    """Compute the non-null fraction of each channel.

    Args:
        frame: Wide telemetry table.
        channels: Channels to measure; absent ones report 0.0.

    Returns:
        A mapping from channel name to non-null fraction in ``[0, 1]``.
    """
    if frame.empty:
        return dict.fromkeys(channels, 0.0)
    return {
        name: (float(frame[name].notna().mean()) if name in frame.columns else 0.0)
        for name in channels
    }


def select_channels(
    frame: pd.DataFrame, channels: list[str], config: TelemetryFilterConfig
) -> tuple[list[str], dict[str, float]]:
    """Choose the channels whose coverage clears the threshold.

    Args:
        frame: Wide telemetry table.
        channels: Candidate channels.
        config: Coverage thresholds.

    Returns:
        The kept channel names and the coverage of every candidate.
    """
    coverage = channel_coverage(frame, channels)
    kept = [name for name in channels if coverage[name] >= config.min_channel_nonnull_frac]
    dropped = [name for name in channels if name not in kept]
    if dropped:
        logger.info("dropping %d channels below coverage threshold: %s", len(dropped), dropped)
    return kept, coverage


def turbine_year_coverage(frame: pd.DataFrame, channels: list[str]) -> float:
    """Compute the mean non-null fraction across a set of channels.

    Args:
        frame: Wide telemetry table for one turbine-year.
        channels: Channels to average over.

    Returns:
        The mean coverage in ``[0, 1]``; 0.0 when no channel is present.
    """
    coverage = channel_coverage(frame, channels)
    values = [value for name, value in coverage.items() if name in frame.columns]
    return float(np.mean(values)) if values else 0.0


def segment_ids(
    frame: pd.DataFrame,
    channels: list[str],
    config: TelemetryFilterConfig,
    freq: str = "10min",
    column: str = "timestamp_utc",
) -> pd.Series[Any]:
    """Label each row with the identifier of its continuous segment.

    A row counts as present when at least one configured channel is non-null. A run of
    ``segment_break_steps`` or more absent steps starts a new segment. A shorter run of
    absent steps stays *inside* its segment and carries the segment's identifier: it is
    the short gap ADR-0006 says imputation fills, so it must reach imputation as a row
    rather than be dropped with the long gaps. Absent rows outside every segment -- a
    long gap, or before the first and after the last present row -- are labelled ``-1``.

    Args:
        frame: Wide telemetry table on a regular grid, sorted by time.
        channels: Channels that define presence.
        config: Segmentation thresholds.
        freq: Grid resolution, used to convert gaps into step counts.
        column: Timestamp column name.

    Returns:
        An integer Series of segment identifiers aligned with ``frame.index``.
    """
    if frame.empty:
        return pd.Series([], dtype="int64", name="segment_id")

    present_columns = [name for name in channels if name in frame.columns]
    present = (
        frame[present_columns].notna().any(axis=1).to_numpy()
        if present_columns
        else np.zeros(len(frame), dtype=bool)
    )
    ids = np.full(len(frame), -1, dtype=np.int64)
    positions = np.flatnonzero(present)
    if positions.size == 0:
        return pd.Series(ids, index=frame.index, name="segment_id")

    stamps = pd.to_datetime(frame[column], utc=True)
    step = pd.Timedelta(freq)
    elapsed = (stamps.iloc[positions].diff() / step).to_numpy()[1:]
    starts = np.r_[True, elapsed > config.segment_break_steps]
    ids[positions] = np.cumsum(starts) - 1

    # An absent row between two present rows of one segment belongs to that segment.
    marked = pd.Series(np.where(present, ids, np.nan))
    before = marked.ffill().to_numpy()
    after = marked.bfill().to_numpy()
    inside = ~present & ~np.isnan(before) & (before == after)
    ids[inside] = before[inside].astype(np.int64)
    return pd.Series(ids, index=frame.index, name="segment_id")


def segment_lengths(ids: pd.Series[Any]) -> dict[int, int]:
    """Count the rows in each segment.

    Args:
        ids: Segment identifiers from :func:`segment_ids`.

    Returns:
        A mapping from segment identifier to length, excluding the absent label.
    """
    counts = ids[ids >= 0].value_counts().to_dict()
    return {int(str(key)): int(value) for key, value in counts.items()}


def drop_short_segments(
    frame: pd.DataFrame, ids: pd.Series[Any], config: TelemetryFilterConfig
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Remove rows belonging to segments shorter than the minimum length.

    Args:
        frame: Wide telemetry table.
        ids: Segment identifiers aligned with the table.
        config: Segmentation thresholds.

    Returns:
        The filtered table (with a ``segment_id`` column) and counters describing
        how many segments and rows were dropped.
    """
    lengths = segment_lengths(ids)
    keep = {key for key, length in lengths.items() if length >= config.min_segment_steps}
    mask = ids.isin(keep)
    counters = {
        "segments_total": len(lengths),
        "segments_kept": len(keep),
        "segments_dropped_short": len(lengths) - len(keep),
        "rows_dropped_unsegmented": int((~mask).sum()),
    }
    result = frame.loc[mask].copy()
    result["segment_id"] = ids.loc[mask].to_numpy()
    return result.reset_index(drop=True), counters
