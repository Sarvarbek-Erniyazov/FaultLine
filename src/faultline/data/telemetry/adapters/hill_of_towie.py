"""Hill of Towie wind farm adapter (RES on behalf of TRIG, CC BY 4.0).

Twenty-one Siemens SWT-2.3-VS-82 turbines, 2016 to mid-2024, published as one
zip per year plus a set of description CSVs and a separate shutdown-duration
archive.

This is the held-out site, and it carries a regime change by construction:
AeroUp retrofits between 2021 and 2023 and a TuneUp in 2024, with install dates
published per turbine. Tier 1 therefore stages one pre-retrofit year (2019) and
one post-retrofit year (2023).

The record publishes a table-description CSV that names the alarm table, so the
member layout is discoverable rather than guessable -- but it still has to be
read before the loaders can be written.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pandas as pd

from faultline.data.telemetry.adapters.base import BaseAdapter, MemberKind, RawMember


@dataclass
class HillOfTowieAdapter(BaseAdapter):
    """Reads the Hill of Towie record into the canonical schema."""

    source_id: ClassVar[str] = "hill_of_towie"
    site_name: ClassVar[str] = "Hill of Towie"

    PATTERNS: ClassVar[tuple[tuple[str, MemberKind], ...]] = (
        ("tables_description", "metadata"),
        ("fields_description", "metadata"),
        ("alarms_description", "metadata"),
        ("turbine_metadata", "metadata"),
        ("install_dates", "metadata"),
        ("alarm", "alarm_log"),
        ("shutdown", "status_events"),
        ("status", "status_events"),
        ("event", "status_events"),
        ("grid", "other"),
    )

    def load_scada(self, member: RawMember) -> pd.DataFrame:
        """Read one Hill of Towie SCADA member.

        Args:
            member: Member classified as SCADA.

        Returns:
            A canonical wide table.

        Raises:
            NotImplementedError: Until the member layout is confirmed by inspection.
        """
        raise NotImplementedError(
            "TODO(m1): read Hill_of_Towie_tables_description.csv and "
            "Hill_of_Towie_turbine_fields_description.csv, then implement; see "
            "data/cards/hill_of_towie.md"
        )

    def load_events(self, member: RawMember) -> pd.DataFrame | None:
        """Read one Hill of Towie event member.

        Args:
            member: Member classified as an event table.

        Returns:
            A canonical events table, or ``None``.

        Raises:
            NotImplementedError: Until the member layout is confirmed by inspection.
        """
        raise NotImplementedError(
            "TODO(m1): locate the alarm table named by Hill_of_Towie_tables_description.csv and "
            "confirm whether its messages are free text; see data/cards/hill_of_towie.md"
        )
