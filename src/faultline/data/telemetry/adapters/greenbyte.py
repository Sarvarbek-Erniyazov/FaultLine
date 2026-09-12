"""Greenbyte exports: the one layout behind Kelmarsh and Penmanshiel.

Both records are published by Cubico through the same Greenbyte export, and the M0
inspection confirmed the same layout in both: per turbine-year, a ``Turbine_Data_*.csv``
of 10-minute SCADA and a ``Status_*.csv`` of status events, each behind a commented
preamble. The two file kinds disagree about that preamble -- in the status files a
clean header follows it, in the turbine-data files the last preamble line *is* the
header -- and the preamble is not noise: it carries the turbine name and the timezone.

The SCADA loader reads only the mapped channels, then applies the repeated-label
rule (:mod:`faultline.data.telemetry.collapse`), because the Kelmarsh 2023 and 2024
exports repeat every label about 41 times. The rule runs on every file, repeated or
not, and every file reports its row accounting.
"""

from __future__ import annotations

import json
from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from faultline.data.telemetry.adapters.base import (
    BaseAdapter,
    FileAccount,
    MemberKind,
    RawMember,
    header_columns,
    read_csv_member,
    read_csv_member_columns,
    read_preamble,
)
from faultline.data.telemetry.collapse import collapse_repeated_labels
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
class GreenbyteAdapter(BaseAdapter):
    """Reads a Greenbyte export into the canonical schema."""

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

    def load_scada_with_stats(self, member: RawMember) -> tuple[pd.DataFrame, FileAccount]:
        """Read one Greenbyte turbine-data member, collapsing repeated labels.

        Only the mapped channels are read: the export carries around 300 columns, most
        of them per-signal aggregates. A row null in every mapped channel is dropped,
        the remaining repeats are proven disjoint, and the file collapses to one row per
        label (:func:`collapse_repeated_labels`).

        Args:
            member: Member classified as SCADA.

        Returns:
            A canonical wide table with one column per resolved canonical channel, and
            the file's row accounting.

        Raises:
            RuntimeError: If the channel map is empty, or the timestamp column is
                missing from the member.
            RepeatedLabelConflictError: If a label carries two values for one channel.
        """
        if not self.channel_map:
            raise RuntimeError(
                f"{self.source_id}: the channel map is empty; fill "
                f"configs/data/channel_map/{self.source_id}.yaml before ingesting"
            )
        wanted = {source: canonical for canonical, source in self.channel_map.items()}
        available = header_columns(member)
        if SCADA_TIMESTAMP not in available:
            raise RuntimeError(f"{member.label}: no {SCADA_TIMESTAMP!r} column")
        present = [column for column in wanted if column in available]
        absent = sorted(set(wanted) - set(present))
        if absent:
            # A channel missing from one year is normal -- instrumentation changes --
            # and it must show up as missing data, not as a crash.
            logger.info("%s: %d mapped channels absent: %s", member.label, len(absent), absent)

        frame = read_csv_member_columns(member, [SCADA_TIMESTAMP, *present])
        for column in present:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        collapsed, stats = collapse_repeated_labels(frame, [SCADA_TIMESTAMP], present)

        result = collapsed.rename(
            columns={SCADA_TIMESTAMP: "timestamp_utc", **{c: wanted[c] for c in present}}
        )
        # The preamble states the timezone; for Kelmarsh it is also measured UTC.
        result["timestamp_utc"] = pd.to_datetime(result["timestamp_utc"], errors="coerce", utc=True)
        result = result[result["timestamp_utc"].notna()]

        turbine = self.turbine_id(member)
        result.insert(0, "turbine_id", turbine)
        result.insert(0, "site", self.site_name)
        result.insert(0, "source", self.source_id)
        result = self.to_canonical_units(result)
        return result.reset_index(drop=True), FileAccount(member.label, turbine, stats)

    def load_events(self, member: RawMember) -> pd.DataFrame | None:
        """Read one Greenbyte status member into the canonical events schema.

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
                # a labelling decision that belongs to the configured mapping
                # (configs/data/events_v1.yaml), not to the reader (ADR-0006).
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
