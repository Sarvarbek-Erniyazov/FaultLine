"""Kelmarsh wind farm adapter (Cubico Sustainable Investments, CC BY 4.0).

Six Senvion MM92 turbines, 2016-2024, published as one zip per year plus a signal
mapping and a static metadata CSV. Each yearly archive holds, per turbine, a
``Turbine_Data_*.csv`` of 10-minute SCADA and a ``Status_*.csv`` of status events.

Both file kinds are Greenbyte exports with a commented preamble, and the two do not
share a layout: in the status files a clean header follows the preamble, while in the
turbine-data files the last preamble line *is* the header. The preamble is not noise
either -- it carries the turbine name and the timezone, which is where the UTC
confirmation for this record comes from.

The loaders were written against the staged archives after inspection confirmed all
of this (``reports/data/raw_inventory_kelmarsh_20260908.md``), not from the file names.
"""

from __future__ import annotations

import json
from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from faultline.data.telemetry.adapters.base import (
    BaseAdapter,
    MemberKind,
    RawMember,
    read_csv_member,
    read_preamble,
)
from faultline.data.telemetry.schemas import EVENT_COLUMNS
from faultline.logging_utils import get_logger

logger = get_logger(__name__)

#: Timestamp column of the turbine-data export.
SCADA_TIMESTAMP = "Date and time"

#: Status export columns, confirmed against the staged archives.
STATUS_START = "Timestamp start"
STATUS_END = "Timestamp end"
STATUS_CODE = "Code"
STATUS_MESSAGE = "Message"
STATUS_CATEGORY = "Status"


@dataclass
class KelmarshAdapter(BaseAdapter):
    """Reads the Kelmarsh record into the canonical schema."""

    source_id: ClassVar[str] = "kelmarsh"
    site_name: ClassVar[str] = "Kelmarsh"

    PATTERNS: ClassVar[tuple[tuple[str, MemberKind], ...]] = (
        ("datasignalmapping", "metadata"),
        ("wt_static", "metadata"),
        ("alarm", "alarm_log"),
        ("status", "status_events"),
        ("event", "status_events"),
        ("turbine_data", "scada_10min"),
        ("scada", "scada_10min"),
        ("grid", "other"),
        ("pmu", "other"),
        (".kmz", "other"),
    )

    def turbine_id(self, member: RawMember) -> str:
        """Identify the turbine a member belongs to.

        The preamble states it explicitly (``# Turbine: Kelmarsh 1``), which is more
        reliable than parsing the file name.

        Args:
            member: Member to identify.

        Returns:
            The turbine name, falling back to the member stem when the preamble has
            no turbine line.
        """
        preamble = read_preamble(member)
        turbine = preamble.get("turbine")
        if turbine:
            return turbine
        logger.warning(
            "%s: no turbine line in the preamble; falling back to the name", member.label
        )
        return member.name.rsplit("/", 1)[-1].removesuffix(".csv")

    def load_scada(self, member: RawMember) -> pd.DataFrame:
        """Read one Kelmarsh SCADA member into the canonical wide schema.

        Only the mapped channels are read. The export carries 299 columns, most of
        them per-signal aggregates, and pulling all of them for every turbine-year
        would cost far more memory than the pipeline budget allows.

        Args:
            member: Member classified as SCADA.

        Returns:
            A canonical wide table with one column per resolved canonical channel.

        Raises:
            RuntimeError: If the channel map is empty, or the timestamp column is
                missing from the member.
        """
        if not self.channel_map:
            raise RuntimeError(
                "kelmarsh: the channel map is empty; fill "
                "configs/data/channel_map/kelmarsh.yaml before ingesting"
            )
        wanted = {source: canonical for canonical, source in self.channel_map.items()}
        frame = read_csv_member(member)
        if SCADA_TIMESTAMP not in frame.columns:
            raise RuntimeError(f"{member.label}: no {SCADA_TIMESTAMP!r} column")

        present = [column for column in wanted if column in frame.columns]
        absent = sorted(set(wanted) - set(present))
        if absent:
            # A channel missing from one year is normal -- instrumentation changes --
            # and it must show up as missing data, not as a crash.
            logger.info("%s: %d mapped channels absent: %s", member.label, len(absent), absent)

        result = frame[[SCADA_TIMESTAMP, *present]].rename(
            columns={SCADA_TIMESTAMP: "timestamp_utc", **{c: wanted[c] for c in present}}
        )
        # The preamble states the timezone; the record uses UTC.
        result["timestamp_utc"] = pd.to_datetime(result["timestamp_utc"], errors="coerce", utc=True)
        result = result[result["timestamp_utc"].notna()]
        for column in present:
            canonical = wanted[column]
            result[canonical] = pd.to_numeric(result[canonical], errors="coerce")

        result.insert(0, "turbine_id", self.turbine_id(member))
        result.insert(0, "site", self.site_name)
        result.insert(0, "source", self.source_id)
        return result.reset_index(drop=True)

    def load_events(self, member: RawMember) -> pd.DataFrame | None:
        """Read one Kelmarsh status member into the canonical events schema.

        Args:
            member: Member classified as an event table.

        Returns:
            A canonical events table, or ``None`` when the member carries no rows.

        Raises:
            RuntimeError: If the expected status columns are absent.
        """
        frame = read_csv_member(member)
        if frame.empty:
            return None
        missing = [c for c in (STATUS_START, STATUS_CODE, STATUS_MESSAGE) if c not in frame.columns]
        if missing:
            raise RuntimeError(f"{member.label}: status member is missing columns {missing}")

        events = pd.DataFrame(
            {
                "source": self.source_id,
                "site": self.site_name,
                "turbine_id": self.turbine_id(member),
                "start_utc": pd.to_datetime(frame[STATUS_START], errors="coerce", utc=True),
                "end_utc": pd.to_datetime(
                    frame.get(STATUS_END, pd.Series(dtype="object")), errors="coerce", utc=True
                ),
                "code": frame[STATUS_CODE].astype("string"),
                "message": frame[STATUS_MESSAGE].astype("string"),
                "category": frame.get(STATUS_CATEGORY, pd.Series(dtype="object")).astype("string"),
                # is_fault stays unset here. Mapping a provider status onto "fault" is
                # a labelling decision that belongs to the configured code mapping, not
                # to the reader (ADR-0006).
                "is_fault": pd.Series([None] * len(frame), dtype="object"),
                "raw": [_raw_row(row) for row in frame.to_dict(orient="records")],
            }
        )
        events = events[events["start_utc"].notna()]
        return events[list(EVENT_COLUMNS)].reset_index(drop=True)


def _raw_row(row: Mapping[Hashable, Any]) -> str:
    """Serialize a provider row so normalization loses nothing.

    Args:
        row: The provider row as a mapping, as pandas hands it back.

    Returns:
        A compact JSON string.
    """
    return json.dumps(row, sort_keys=True, default=str, separators=(",", ":"))
