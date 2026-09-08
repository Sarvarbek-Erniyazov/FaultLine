"""Canonical telemetry and event schemas (ADR-0006).

Four providers publish four different column vocabularies, sampling conventions and
file layouts. Everything downstream of the adapters speaks one schema instead, so
that adding a fifth site is an adapter and a channel map, not a change to the model.

Two shapes are canonical:

* **SCADA**, stored *wide* per ``(source, turbine, year)`` Parquet file -- one row
  per timestep, one column per channel -- because that is the layout a windowed
  sequence model reads. The *long* form is defined too, since inspection and
  per-channel statistics are far easier over it.
* **Events**, one row per alarm, status or shutdown record, with the raw provider
  payload preserved in a ``raw`` column so that nothing is lost in normalization.

Imputed values always travel with a companion ``<channel>__imputed`` boolean
column. Missingness is a shift signal in its own right: sensors drop out precisely
when something is wrong, so silently filling gaps would erase evidence the model is
supposed to use.

Plausibility bounds live in ``configs/data/telemetry_v0.yaml``, never here -- they
are provisional physical judgements, not code.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pyarrow as pa

#: Columns identifying a SCADA row, in canonical order.
INDEX_COLUMNS: tuple[str, ...] = ("source", "site", "turbine_id", "timestamp_utc")

#: Suffix marking the boolean companion column of an imputed channel.
IMPUTED_SUFFIX = "__imputed"


@dataclass(frozen=True)
class ChannelSpec:
    """One canonical SCADA channel.

    Attributes:
        name: Canonical channel name used everywhere downstream.
        unit: Physical unit of the values.
        description: What the channel measures.
        group: Coarse grouping, used for reports and for modality-drop experiments.
    """

    name: str
    unit: str
    description: str
    group: str


#: The canonical channel list for M1. Chosen as the intersection that the three
#: named sources plausibly share; CARE is anonymised and is mapped separately.
CANONICAL_CHANNELS: tuple[ChannelSpec, ...] = (
    ChannelSpec("wind_speed_ms", "m/s", "Nacelle anemometer wind speed", "environment"),
    ChannelSpec("power_kw", "kW", "Active power output", "production"),
    ChannelSpec("rotor_speed_rpm", "rpm", "Rotor rotational speed", "drivetrain"),
    ChannelSpec("generator_speed_rpm", "rpm", "Generator rotational speed", "drivetrain"),
    ChannelSpec("pitch_angle_deg", "deg", "Blade pitch angle", "control"),
    ChannelSpec("nacelle_position_deg", "deg", "Nacelle yaw position", "control"),
    ChannelSpec("wind_direction_deg", "deg", "Wind direction", "environment"),
    ChannelSpec("ambient_temp_c", "degC", "Ambient air temperature", "environment"),
    ChannelSpec("nacelle_temp_c", "degC", "Nacelle internal temperature", "environment"),
    ChannelSpec("gearbox_bearing_temp_c", "degC", "Gearbox bearing temperature", "temperature"),
    ChannelSpec("gearbox_oil_temp_c", "degC", "Gearbox oil temperature", "temperature"),
    ChannelSpec("generator_bearing_temp_c", "degC", "Generator bearing temperature", "temperature"),
    ChannelSpec("generator_winding_temp_c", "degC", "Generator winding temperature", "temperature"),
)

#: Canonical channel names in identifier order. This order fixes the channel token
#: identifiers in the joint vocabulary, so it must not be reordered after M1.
CHANNEL_NAMES: tuple[str, ...] = tuple(spec.name for spec in CANONICAL_CHANNELS)

CHANNELS_BY_NAME: dict[str, ChannelSpec] = {spec.name: spec for spec in CANONICAL_CHANNELS}

#: Long-format SCADA: one row per (turbine, timestamp, channel).
SCADA_LONG_SCHEMA = pa.schema(
    [
        pa.field("source", pa.string(), nullable=False),
        pa.field("site", pa.string(), nullable=False),
        pa.field("turbine_id", pa.string(), nullable=False),
        pa.field("timestamp_utc", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("channel", pa.string(), nullable=False),
        pa.field("value", pa.float64(), nullable=True),
    ]
)

#: Canonical events: one row per alarm, status or shutdown record.
EVENTS_SCHEMA = pa.schema(
    [
        pa.field("source", pa.string(), nullable=False),
        pa.field("site", pa.string(), nullable=False),
        pa.field("turbine_id", pa.string(), nullable=False),
        pa.field("start_utc", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("end_utc", pa.timestamp("us", tz="UTC"), nullable=True),
        pa.field("code", pa.string(), nullable=True),
        pa.field("message", pa.string(), nullable=True),
        pa.field("category", pa.string(), nullable=True),
        pa.field("is_fault", pa.bool_(), nullable=True),
        pa.field("raw", pa.string(), nullable=True),
    ]
)

#: Column order of the canonical events table.
EVENT_COLUMNS: tuple[str, ...] = tuple(EVENTS_SCHEMA.names)


def wide_schema(channels: tuple[str, ...] = CHANNEL_NAMES, with_masks: bool = True) -> pa.Schema:
    """Build the wide SCADA schema for a channel set.

    Args:
        channels: Canonical channel names to include, in order.
        with_masks: Include the boolean ``<channel>__imputed`` companion columns.

    Returns:
        The pyarrow schema of the wide table.
    """
    fields = [
        pa.field("source", pa.string(), nullable=False),
        pa.field("site", pa.string(), nullable=False),
        pa.field("turbine_id", pa.string(), nullable=False),
        pa.field("timestamp_utc", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
    fields += [pa.field(name, pa.float64(), nullable=True) for name in channels]
    if with_masks:
        fields += [
            pa.field(f"{name}{IMPUTED_SUFFIX}", pa.bool_(), nullable=False) for name in channels
        ]
    return pa.schema(fields)


def empty_wide_frame(channels: tuple[str, ...] = CHANNEL_NAMES) -> pd.DataFrame:
    """Return an empty wide SCADA table with the canonical columns.

    Args:
        channels: Canonical channel names to include.

    Returns:
        An empty, correctly typed DataFrame.
    """
    frame = pd.DataFrame(columns=[*INDEX_COLUMNS, *channels])
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    for name in channels:
        frame[name] = frame[name].astype(float)
    return frame


def empty_events_frame() -> pd.DataFrame:
    """Return an empty canonical events table.

    Returns:
        An empty DataFrame with the canonical event columns.
    """
    frame = pd.DataFrame(columns=list(EVENT_COLUMNS))
    frame["start_utc"] = pd.to_datetime(frame["start_utc"], utc=True)
    frame["end_utc"] = pd.to_datetime(frame["end_utc"], utc=True)
    frame["is_fault"] = frame["is_fault"].astype("boolean")
    return frame


def missing_columns(frame: pd.DataFrame, required: tuple[str, ...]) -> list[str]:
    """List the required columns a table does not have.

    Args:
        frame: Table to check.
        required: Column names that must be present.

    Returns:
        The missing column names, in the required order.
    """
    return [name for name in required if name not in frame.columns]


def validate_wide(frame: pd.DataFrame, channels: tuple[str, ...] = CHANNEL_NAMES) -> None:
    """Check that a table satisfies the wide SCADA contract.

    Args:
        frame: Table to validate.
        channels: Canonical channels expected to be present.

    Raises:
        ValueError: If index columns are missing, the timestamp is not UTC-aware, or
            a channel column is not numeric.
    """
    absent = missing_columns(frame, INDEX_COLUMNS)
    if absent:
        raise ValueError(f"wide SCADA table is missing index columns: {absent}")
    stamps = frame["timestamp_utc"]
    if not pd.api.types.is_datetime64_any_dtype(stamps):
        raise ValueError("timestamp_utc must be a datetime column")
    if getattr(stamps.dtype, "tz", None) is None:
        raise ValueError("timestamp_utc must be timezone-aware and in UTC")
    for name in channels:
        if name in frame.columns and not pd.api.types.is_numeric_dtype(frame[name]):
            raise ValueError(f"channel column {name!r} must be numeric")


def validate_events(frame: pd.DataFrame) -> None:
    """Check that a table satisfies the canonical events contract.

    Args:
        frame: Table to validate.

    Raises:
        ValueError: If required columns are missing or timestamps are not UTC-aware.
    """
    absent = missing_columns(frame, ("source", "site", "turbine_id", "start_utc"))
    if absent:
        raise ValueError(f"events table is missing columns: {absent}")
    if not pd.api.types.is_datetime64_any_dtype(frame["start_utc"]):
        raise ValueError("start_utc must be a datetime column")
    if getattr(frame["start_utc"].dtype, "tz", None) is None:
        raise ValueError("start_utc must be timezone-aware and in UTC")


def to_long(frame: pd.DataFrame, channels: tuple[str, ...] = CHANNEL_NAMES) -> pd.DataFrame:
    """Melt a wide SCADA table into the long canonical form.

    Args:
        frame: Wide table.
        channels: Channels to melt; absent ones are skipped.

    Returns:
        A long table with ``channel`` and ``value`` columns.
    """
    present = [name for name in channels if name in frame.columns]
    long = frame.melt(
        id_vars=list(INDEX_COLUMNS),
        value_vars=present,
        var_name="channel",
        value_name="value",
    )
    return long.sort_values([*INDEX_COLUMNS, "channel"], ignore_index=True)
