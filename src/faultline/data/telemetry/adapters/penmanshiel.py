"""Penmanshiel wind farm adapter (Cubico Sustainable Investments, CC BY 4.0).

Fourteen Senvion MM82 turbines, 2016-2024, published as zips split by turbine
range as well as by year, so a single year spans two archives. Turbine WT03 is
absent from the record.

Same publisher as Kelmarsh and, on the published file names, the same layout --
but the signal mapping ships as .xlsx here rather than .csv, so the channel map
could not be filled at M0 without opening the workbook. Discovery is implemented;
the loaders wait on inspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pandas as pd

from faultline.data.telemetry.adapters.base import BaseAdapter, MemberKind, RawMember


@dataclass
class PenmanshielAdapter(BaseAdapter):
    """Reads the Penmanshiel record into the canonical schema."""

    source_id: ClassVar[str] = "penmanshiel"
    site_name: ClassVar[str] = "Penmanshiel"

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

    def load_scada(self, member: RawMember) -> pd.DataFrame:
        """Read one Penmanshiel SCADA member.

        Args:
            member: Member classified as SCADA.

        Returns:
            A canonical wide table.

        Raises:
            NotImplementedError: Until the member layout is confirmed by inspection.
        """
        raise NotImplementedError(
            "TODO(m1): confirm the Penmanshiel SCADA member layout and whether it matches "
            "Kelmarsh exactly; see data/cards/penmanshiel.md"
        )

    def load_events(self, member: RawMember) -> pd.DataFrame | None:
        """Read one Penmanshiel event member.

        Args:
            member: Member classified as an event table.

        Returns:
            A canonical events table, or ``None``.

        Raises:
            NotImplementedError: Until the member layout is confirmed by inspection.
        """
        raise NotImplementedError(
            "TODO(m1): confirm whether the Penmanshiel archives carry a status/event table and "
            "whether its messages are free text; see data/cards/penmanshiel.md"
        )
