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
from typing import Literal

import pandas as pd
import pyarrow as pa

#: Columns identifying a SCADA row, in canonical order.
INDEX_COLUMNS: tuple[str, ...] = ("source", "site", "turbine_id", "timestamp_utc")

#: Suffix marking the boolean companion column of an imputed channel.
IMPUTED_SUFFIX = "__imputed"


#: Whether a channel may be depended on by an evaluation that holds a whole site out.
ChannelTier = Literal["core", "extended"]


@dataclass(frozen=True)
class ChannelSpec:
    """One canonical SCADA channel.

    Attributes:
        name: Canonical channel name used everywhere downstream.
        unit: Physical unit of the values.
        description: What the channel measures.
        group: Coarse grouping, used for reports and for modality-drop experiments.
        tier: ``core`` if the channel is published by every training site, so a
            leave-site-out evaluation can depend on it; ``extended`` otherwise. A
            channel is ``extended`` until its presence at every training site is
            verified, which is why a newly added channel starts there.
    """

    name: str
    unit: str
    description: str
    group: str
    tier: ChannelTier


#: The canonical channel list for M1, with the tier each channel is declared at.
#:
#: **Order is identity.** Position in this tuple fixes the channel token identifier
#: (ADR-0003), so a channel is only ever appended -- never inserted, never reordered.
#:
#: The core/extended split is a *declaration*, checked at M1 rather than assumed:
#: core is the set a leave-site-out evaluation is allowed to depend on, and the M1
#: ingest fails if a core channel turns out to be absent at a training site. Only
#: Kelmarsh's channel map is resolved at M0, so the one evidence-backed assignment
#: today is a negative: Kelmarsh publishes no gearbox bearing temperature at all,
#: which puts that channel in extended whatever the other sites carry.
#: TODO(m1): re-derive the tiers from the resolved Penmanshiel and Hill of Towie
#: maps, and demote any core channel not actually present at every training site.
CANONICAL_CHANNELS: tuple[ChannelSpec, ...] = (
    ChannelSpec("wind_speed_ms", "m/s", "Nacelle anemometer wind speed", "environment", "core"),
    ChannelSpec("power_kw", "kW", "Active power output", "production", "core"),
    ChannelSpec("rotor_speed_rpm", "rpm", "Rotor rotational speed", "drivetrain", "core"),
    ChannelSpec("generator_speed_rpm", "rpm", "Generator rotational speed", "drivetrain", "core"),
    ChannelSpec("pitch_angle_deg", "deg", "Blade pitch angle", "control", "core"),
    ChannelSpec("nacelle_position_deg", "deg", "Nacelle yaw position", "control", "core"),
    ChannelSpec("wind_direction_deg", "deg", "Wind direction", "environment", "core"),
    ChannelSpec("ambient_temp_c", "degC", "Ambient air temperature", "environment", "core"),
    # Below here is drivetrain and enclosure instrumentation, which is where SCADA
    # records stop agreeing with each other: what a machine measures depends on its
    # gearbox, its generator and its vintage.
    ChannelSpec(
        "nacelle_temp_c", "degC", "Nacelle internal temperature", "environment", "extended"
    ),
    ChannelSpec(
        "gearbox_bearing_temp_c", "degC", "Gearbox bearing temperature", "temperature", "extended"
    ),
    ChannelSpec("gearbox_oil_temp_c", "degC", "Gearbox oil temperature", "temperature", "extended"),
    ChannelSpec(
        "generator_bearing_temp_c",
        "degC",
        "Generator bearing temperature",
        "temperature",
        "extended",
    ),
    ChannelSpec(
        "generator_winding_temp_c",
        "degC",
        "Generator winding temperature",
        "temperature",
        "extended",
    ),
    # Appended 2026-09-09, after the Kelmarsh signal-mapping cross-check found a
    # published main-shaft bearing temperature the canonical list was discarding
    # (signal 447, "Temperature of rotor bearing"). Appended rather than filed with
    # the other bearing channels, because position is identity.
    ChannelSpec(
        "main_bearing_temp_c", "degC", "Main shaft bearing temperature", "drivetrain", "extended"
    ),
)

#: Canonical channel names in identifier order. This order fixes the channel token
#: identifiers in the joint vocabulary, so it must not be reordered after M1.
CHANNEL_NAMES: tuple[str, ...] = tuple(spec.name for spec in CANONICAL_CHANNELS)

CHANNELS_BY_NAME: dict[str, ChannelSpec] = {spec.name: spec for spec in CANONICAL_CHANNELS}

#: Channels a leave-site-out evaluation may depend on, in identifier order.
CORE_CHANNELS: tuple[str, ...] = tuple(
    spec.name for spec in CANONICAL_CHANNELS if spec.tier == "core"
)

#: Channels that are not published everywhere, in identifier order.
EXTENDED_CHANNELS: tuple[str, ...] = tuple(
    spec.name for spec in CANONICAL_CHANNELS if spec.tier == "extended"
)


def channel_tier(name: str) -> ChannelTier:
    """Return the tier a canonical channel is declared at.

    Args:
        name: Canonical channel name.

    Returns:
        ``core`` or ``extended``.

    Raises:
        KeyError: If the name is not a canonical channel. Treating an unknown name
            as extended would let a typo quietly disable the core-only rule.
    """
    try:
        return CHANNELS_BY_NAME[name].tier
    except KeyError as exc:
        raise KeyError(
            f"{name!r} is not a canonical channel; known channels: {', '.join(CHANNEL_NAMES)}"
        ) from exc


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
