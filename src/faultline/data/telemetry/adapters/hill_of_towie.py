"""Hill of Towie wind farm adapter (RES on behalf of TRIG, CC BY 4.0).

Twenty-one Siemens SWT-2.3-VS-82 turbines, 2016 to mid-2024, published as one
zip per year plus a set of description CSVs and a separate shutdown-duration
archive.

This is the held-out site, and it carries a regime change by construction:
AeroUp retrofits between 2021 and 2023 and a TuneUp in 2024, with install dates
published per turbine. Tier 1 therefore stages one pre-retrofit year (2019) and
one post-retrofit year (2023).

The record publishes ``Hill_of_Towie_tables_description.csv``, which names every
table in the SCADA backup, and member classification follows those names rather
than generic substrings. Read on 2026-09-10: ``tblAlarmLog`` is the alarm log ("Log
of stopping and non-stopping events/alarms"), one file per month, and it carries
only ``TimeOn``, ``TimeOff``, ``StationNr`` and ``Alarmcode`` -- no message text.
The only text attached to those codes is ``Hill_of_Towie_alarms_description.csv``,
which describes a handful of them, not the full code book.
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

    #: Built from the table names in Hill_of_Towie_tables_description.csv. The generic
    #: substrings these replace sent tblSCTurGrid -- the turbine table that carries
    #: active power -- to "other" because its name contains "grid", and let
    #: tblDailySummary fall through to 10-minute SCADA although it is daily.
    PATTERNS: ClassVar[tuple[tuple[str, MemberKind], ...]] = (
        ("tables_description", "metadata"),
        ("fields_description", "metadata"),
        ("alarms_description", "metadata"),
        ("turbine_metadata", "metadata"),
        ("install_dates", "metadata"),
        # "Log of stopping and non-stopping events/alarms"
        ("tblalarmlog", "alarm_log"),
        # tblSCTurbine, tblSCTurGrid, tblSCTurTemp, ..., all "[10min]" turbine tables.
        # tblSCTurFlag ("Turbine status information") is 10-minute counters and
        # time-on durations, not events, so it belongs here too.
        ("tblsctur", "scada_10min"),
        # "Daily aggregations of turbine signals"
        ("tbldailysummary", "other"),
        # tblGrid and tblGridScientific: grid monitoring stations, not turbines.
        ("tblgrid", "other"),
        # Not in the table description. Its header (TimeStamp_StartFormat, TurbineName,
        # ShutdownDuration) makes it a per-turbine shutdown series: a label source with
        # no text in it.
        ("shutdownduration", "status_events"),
    )

    CLASSIFICATION_SOURCE: ClassVar[str] = (
        "provider table names, as defined in Hill_of_Towie_tables_description.csv "
        "(tblAlarmLog: 'Log of stopping and non-stopping events/alarms'); "
        "ShutdownDuration.csv is not in that file and is classified from its header"
    )

    CODE_DESCRIPTIONS: ClassVar[str | None] = "Hill_of_Towie_alarms_description.csv"

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
