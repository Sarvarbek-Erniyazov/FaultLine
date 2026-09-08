"""Telemetry cleaning: timestamps, duplicates, a regular grid and plausibility bounds.

This is the telemetry counterpart of the text cleaning stage. Where the text side
strips markup, this side answers: is the time axis regular and unambiguous, and is
each value physically possible for this machine?

Out-of-bounds values become ``NaN`` rather than being clipped. Clipping would
invent a plausible reading where the instrument actually failed, and the difference
matters for a model whose job is to notice failures.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from faultline.config import StrictModel
from faultline.data.telemetry.schemas import INDEX_COLUMNS
from faultline.logging_utils import get_logger

logger = get_logger(__name__)


class BoundSpec(StrictModel):
    """Physically plausible range of one channel.

    Attributes:
        min: Lowest accepted value, inclusive.
        max: Highest accepted value, inclusive.
    """

    min: float
    max: float


class TelemetryCleanConfig(StrictModel):
    """Cleaning switches for the telemetry pipeline.

    Attributes:
        duplicate_timestamps: How to resolve repeated timestamps, ``mean`` or ``first``.
        apply_bounds: Replace out-of-range values with ``NaN``.
        drop_all_nan_rows: Drop timesteps where every channel is missing.
    """

    duplicate_timestamps: str = "mean"
    apply_bounds: bool = True
    drop_all_nan_rows: bool = False


@dataclass
class CleanCounts:
    """Per-stage counters produced while cleaning one turbine-year.

    Attributes:
        rows_in: Rows read.
        rows_out: Rows written.
        duplicate_timestamps: Rows removed by duplicate resolution.
        unparseable_timestamps: Rows dropped because the timestamp did not parse.
        grid_rows_inserted: Empty rows inserted to complete the regular grid.
        bounds_flags: Values set to NaN per channel by the plausibility bounds.
    """

    rows_in: int = 0
    rows_out: int = 0
    duplicate_timestamps: int = 0
    unparseable_timestamps: int = 0
    grid_rows_inserted: int = 0
    bounds_flags: dict[str, int] | None = None

    def as_counters(self) -> dict[str, int]:
        """Flatten the counters for a stage result.

        Returns:
            A flat mapping suitable for ``StageResult.counters``.
        """
        counters = {
            "duplicate_timestamps": self.duplicate_timestamps,
            "unparseable_timestamps": self.unparseable_timestamps,
            "grid_rows_inserted": self.grid_rows_inserted,
        }
        for channel, count in (self.bounds_flags or {}).items():
            counters[f"bounds:{channel}"] = count
        return counters


def parse_timestamps(
    frame: pd.DataFrame, column: str = "timestamp_utc", timezone: str = "UTC"
) -> tuple[pd.DataFrame, int]:
    """Parse a timestamp column to UTC and drop rows that fail to parse.

    Naive timestamps are localized to the source timezone, then converted to UTC.
    A source whose timezone is still unconfirmed keeps ``UTC`` and says so on its
    dataset card, rather than guessing an offset.

    Args:
        frame: Table with a timestamp column.
        column: Name of that column.
        timezone: Timezone of naive timestamps in the source data.

    Returns:
        The table with a UTC-aware timestamp column, and the number of rows dropped.

    Raises:
        KeyError: If the timestamp column is absent.
    """
    if column not in frame.columns:
        raise KeyError(f"timestamp column {column!r} is missing")
    result = frame.copy()
    parsed = pd.to_datetime(result[column], errors="coerce", utc=False)
    if getattr(parsed.dtype, "tz", None) is None:
        parsed = parsed.dt.tz_localize(timezone, ambiguous="NaT", nonexistent="NaT")
    result[column] = parsed.dt.tz_convert("UTC")
    dropped = int(result[column].isna().sum())
    if dropped:
        logger.warning("dropping %d rows with unparseable timestamps", dropped)
        result = result[result[column].notna()]
    return result, dropped


def resolve_duplicate_timestamps(
    frame: pd.DataFrame,
    channels: list[str],
    strategy: str = "mean",
    column: str = "timestamp_utc",
) -> tuple[pd.DataFrame, int]:
    """Collapse repeated timestamps for one turbine.

    Args:
        frame: Table for a single turbine.
        channels: Numeric columns to aggregate.
        strategy: ``mean`` averages the duplicates, ``first`` keeps the first row.
        column: Timestamp column name.

    Returns:
        The de-duplicated table and the number of rows removed.

    Raises:
        ValueError: If the strategy is not recognised.
    """
    if strategy not in {"mean", "first"}:
        raise ValueError(f"duplicate_timestamps must be mean or first, got {strategy!r}")
    duplicated = int(frame.duplicated(subset=[column]).sum())
    if duplicated == 0:
        return frame, 0

    identifiers = [name for name in INDEX_COLUMNS if name != column and name in frame.columns]
    present = [name for name in channels if name in frame.columns]
    if strategy == "first":
        collapsed = frame.sort_values(column).drop_duplicates(subset=[column], keep="first")
    else:
        aggregated = frame.groupby(column, as_index=False)[present].mean()
        constants = frame.drop_duplicates(subset=[column], keep="first")[[column, *identifiers]]
        collapsed = constants.merge(aggregated, on=column, how="left")
    logger.info("collapsed %d duplicate timestamps with strategy %s", duplicated, strategy)
    return collapsed.reset_index(drop=True), duplicated


def reindex_to_grid(
    frame: pd.DataFrame,
    freq: str = "10min",
    column: str = "timestamp_utc",
) -> tuple[pd.DataFrame, int]:
    """Place a turbine's rows on a regular time grid.

    Args:
        frame: Table for a single turbine, with parsed timestamps.
        freq: Pandas offset alias of the target resolution.
        column: Timestamp column name.

    Returns:
        The reindexed table and the number of rows inserted to fill the grid.
    """
    if frame.empty:
        return frame, 0
    ordered = frame.sort_values(column).set_index(column)
    grid = pd.date_range(ordered.index.min(), ordered.index.max(), freq=freq, tz="UTC")
    inserted = int(len(grid) - len(ordered.index.intersection(grid)))
    reindexed = ordered.reindex(grid)
    reindexed.index.name = column
    for name in ("source", "site", "turbine_id"):
        if name in reindexed.columns:
            reindexed[name] = reindexed[name].ffill().bfill()
    return reindexed.reset_index(), inserted


def apply_bounds(
    frame: pd.DataFrame, bounds: dict[str, BoundSpec]
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Replace implausible values with ``NaN`` and count them per channel.

    Args:
        frame: Wide telemetry table.
        bounds: Plausible range per channel.

    Returns:
        The bounded table and the number of values flagged per channel.
    """
    result = frame.copy()
    flags: dict[str, int] = {}
    for channel, spec in bounds.items():
        if channel not in result.columns:
            continue
        values = pd.to_numeric(result[channel], errors="coerce")
        outside = (values < spec.min) | (values > spec.max)
        count = int(outside.sum())
        if count:
            values = values.mask(outside)
            logger.info(
                "channel %s: %d values outside [%g, %g]", channel, count, spec.min, spec.max
            )
        flags[channel] = count
        result[channel] = values
    return result, flags


def clean_turbine_frame(
    frame: pd.DataFrame,
    channels: list[str],
    bounds: dict[str, BoundSpec],
    config: TelemetryCleanConfig,
    freq: str = "10min",
    timezone: str = "UTC",
) -> tuple[pd.DataFrame, CleanCounts]:
    """Run the full cleaning chain over one turbine's table.

    Args:
        frame: Wide table for a single turbine.
        channels: Canonical channels to keep.
        bounds: Plausibility bounds per channel.
        config: Cleaning switches.
        freq: Target grid resolution.
        timezone: Timezone of naive source timestamps.

    Returns:
        The cleaned table and the counters describing what happened.
    """
    counts = CleanCounts(rows_in=len(frame))
    parsed, counts.unparseable_timestamps = parse_timestamps(frame, timezone=timezone)
    collapsed, counts.duplicate_timestamps = resolve_duplicate_timestamps(
        parsed, channels, config.duplicate_timestamps
    )
    gridded, counts.grid_rows_inserted = reindex_to_grid(collapsed, freq=freq)
    if config.apply_bounds:
        gridded, counts.bounds_flags = apply_bounds(gridded, bounds)
    else:
        counts.bounds_flags = {}
    if config.drop_all_nan_rows:
        present = [name for name in channels if name in gridded.columns]
        if present:
            gridded = gridded[~gridded[present].isna().all(axis=1)]
    counts.rows_out = len(gridded)
    return gridded.reset_index(drop=True), counts
