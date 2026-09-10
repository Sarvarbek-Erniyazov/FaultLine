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
than generic substrings. ``tblAlarmLog`` is the alarm log ("Log of stopping and
non-stopping events/alarms"), one file per month, and it carries only ``TimeOn``,
``TimeOff``, ``StationNr`` and ``Alarmcode`` -- no message text.

The loaders, written 2026-09-10 against the staged 2019 and 2023 archives:

* **SCADA** is one file per table per month, all 21 turbines in each, keyed by
  ``(TimeStamp, StationId)``. The channel map names ``<table>.<field>``, and a month's
  tables are read together and joined. Station ids become turbine names (T01..T21)
  through ``Hill_of_Towie_turbine_metadata.csv``.
* **Timestamps label the end of each interval.** ``wtc_CurTime_endvalue`` -- the turbine
  clock at the end of the interval -- sits a median 2 s before ``TimeStamp`` in every
  station of every month checked (1 to 3 s at p1 and p99). Greenbyte labels the start,
  so this loader subtracts one interval and every canonical timestamp names the
  interval it opens. ShutdownDuration says the same of itself in its column name,
  ``TimeStamp_StartFormat``. The clock is UTC, measured by the daylight-saving
  fingerprint (``reports/data/resolved_hill_of_towie_*.md``).
* **Events** are ``tblAlarmLog`` rows, with the alarm code and no message, because the
  log has none. ``ShutdownDuration.csv`` is a per-turbine downtime series, not an
  event log, and it is its own member kind.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import ClassVar

import pandas as pd

from faultline.data.telemetry.adapters.base import (
    BaseAdapter,
    FileAccount,
    MemberKind,
    RawMember,
    header_columns,
    read_csv_member,
    read_csv_member_columns,
)
from faultline.data.telemetry.collapse import collapse_repeated_labels
from faultline.data.telemetry.schemas import EVENT_COLUMNS
from faultline.logging_utils import get_logger

logger = get_logger(__name__)

TIMESTAMP = "TimeStamp"
STATION = "StationId"

#: One grid interval. The provider labels its end; canonical timestamps name its start.
INTERVAL = pd.Timedelta(minutes=10)

#: The provider file that names each station.
STATIONS_FILE = "Hill_of_Towie_turbine_metadata.csv"

#: The alarm log's columns, all of them.
ALARM_COLUMNS: tuple[str, ...] = ("TimeOn", "TimeOff", "StationNr", "Alarmcode")

_MONTHLY = re.compile(r"^(tbl[A-Za-z]+)_(\d{4})_(\d{2})\.csv$")


def _basename(member: RawMember) -> str:
    """The member's file name without its archive path."""
    return member.name.rsplit("/", 1)[-1] or member.archive.name


def _code(value: object) -> str | None:
    """Render an alarm code as an integer string, whatever pandas parsed it as."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else text


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
        # ShutdownDuration) makes it a per-turbine downtime series: a label source, and
        # neither an event log nor telemetry.
        ("shutdownduration", "downtime_series"),
    )

    CLASSIFICATION_SOURCE: ClassVar[str] = (
        "provider table names, as defined in Hill_of_Towie_tables_description.csv "
        "(tblAlarmLog: 'Log of stopping and non-stopping events/alarms'); "
        "ShutdownDuration.csv is not in that file and is classified from its header "
        "as a per-turbine downtime series"
    )

    CODE_DESCRIPTIONS: ClassVar[str | None] = "Hill_of_Towie_alarms_description.csv"

    _stations: dict[int, str] = field(default_factory=dict, init=False, repr=False)

    def split_channel_column(self, column: str) -> tuple[str | None, str]:
        """Split ``<table>.<field>``, the form this record's channel map is written in.

        The provider spreads one turbine's 10-minute signals over several tables --
        active power is in tblSCTurGrid, wind speed in tblSCTurbine, temperatures in
        tblSCTurTemp -- so a field name alone does not say where to read it.

        Args:
            column: Column as written in the channel map.

        Returns:
            The table name and the field name.
        """
        table_name, _, field_name = column.partition(".")
        return (table_name, field_name) if field_name else (None, column)

    def station_names(self, member: RawMember) -> dict[int, str]:
        """Map station ids to turbine names, from the provider's turbine metadata.

        Args:
            member: Any member of this source; the metadata file is staged beside it.

        Returns:
            Turbine name per station id.

        Raises:
            RuntimeError: If the metadata file is not staged.
        """
        if not self._stations:
            path = member.archive.parent / STATIONS_FILE
            if not path.is_file():
                raise RuntimeError(
                    f"{STATIONS_FILE} is not staged beside {member.archive.name}, so station "
                    "ids cannot be named"
                )
            table = pd.read_csv(path)
            self._stations = {
                int(station): str(name)
                for station, name in zip(table["Station ID"], table["Turbine Name"], strict=True)
            }
        return self._stations

    def _turbines(self, stations: pd.Series, member: RawMember) -> pd.Series:
        """Name the stations of a table, dropping any the metadata does not list.

        Args:
            stations: Station id column.
            member: Member the column came from, for the log.

        Returns:
            Turbine names, missing where the station is not a turbine.
        """
        names = self.station_names(member)
        numeric = pd.to_numeric(stations, errors="coerce")
        unknown = sorted({int(s) for s in numeric.dropna().unique()} - set(names))
        if unknown:
            logger.warning(
                "%s: stations %s are not turbines in %s; their rows are dropped",
                member.label,
                unknown,
                STATIONS_FILE,
            )
        return numeric.map(names)

    def scada_units(self, members: Sequence[RawMember]) -> list[list[RawMember]]:
        """Group the monthly tables the channel map reads into one unit per month.

        Args:
            members: Members discovered for the source.

        Returns:
            One unit per (year, month), holding that month's mapped tables.
        """
        tables = {
            table_name
            for table_name, _ in (self.split_channel_column(c) for c in self.channel_map.values())
            if table_name
        }
        units: dict[tuple[str, str], list[RawMember]] = {}
        for member in members:
            if member.kind != "scada_10min" or member.size == 0:
                continue
            match = _MONTHLY.match(_basename(member))
            if match and match.group(1) in tables:
                units.setdefault((match.group(2), match.group(3)), []).append(member)
        return [sorted(unit, key=_basename) for _, unit in sorted(units.items())]

    def load_scada_unit(self, unit: Sequence[RawMember]) -> tuple[pd.DataFrame, list[FileAccount]]:
        """Read one month's tables, collapse repeats per table, and join them.

        Args:
            unit: The month's mapped tables.

        Returns:
            A canonical wide table for every turbine that month, and one account per
            table file.

        Raises:
            RuntimeError: If the channel map is empty or a table lacks its keys.
            RepeatedLabelConflictError: If a (label, station) carries two values for one
                field.
        """
        if not self.channel_map:
            raise RuntimeError(
                "hill_of_towie: the channel map is empty; fill "
                "configs/data/channel_map/hill_of_towie.yaml before ingesting"
            )
        by_table: dict[str, dict[str, str]] = {}
        for canonical, column in self.channel_map.items():
            table_name, field_name = self.split_channel_column(column)
            by_table.setdefault(table_name or "", {})[field_name] = canonical

        keys = [TIMESTAMP, STATION]
        merged: pd.DataFrame | None = None
        accounts: list[FileAccount] = []
        for member in unit:
            match = _MONTHLY.match(_basename(member))
            fields = by_table.get(match.group(1) if match else "", {})
            available = set(header_columns(member))
            if not set(keys) <= available:
                raise RuntimeError(f"{member.label}: no {TIMESTAMP!r} and {STATION!r} columns")
            present = [name for name in fields if name in available]
            frame = read_csv_member_columns(member, [*keys, *present])
            for name in present:
                frame[name] = pd.to_numeric(frame[name], errors="coerce")
            collapsed, stats = collapse_repeated_labels(frame, keys, present)
            accounts.append(
                FileAccount(member.label, f"{frame[STATION].nunique()} stations", stats)
            )
            collapsed = collapsed.rename(columns={name: fields[name] for name in present})
            merged = collapsed if merged is None else merged.merge(collapsed, on=keys, how="outer")

        if merged is None or merged.empty:
            return pd.DataFrame(), accounts
        stamps = pd.to_datetime(merged[TIMESTAMP], errors="coerce", utc=True) - INTERVAL
        turbines = self._turbines(merged[STATION], unit[0])
        keep = (stamps.notna() & turbines.notna()).to_numpy()
        result = merged.loc[keep].drop(columns=keys)
        result.insert(0, "timestamp_utc", stamps[keep].to_numpy())
        result.insert(0, "turbine_id", turbines[keep].astype(str).to_numpy())
        result.insert(0, "site", self.site_name)
        result.insert(0, "source", self.source_id)
        result["timestamp_utc"] = pd.to_datetime(result["timestamp_utc"], utc=True)
        return result.reset_index(drop=True), accounts

    def load_scada_with_stats(self, member: RawMember) -> tuple[pd.DataFrame, FileAccount]:
        """Read a single table file on its own.

        Args:
            member: One monthly table.

        Returns:
            Its canonical rows and its account.
        """
        frame, accounts = self.load_scada_unit([member])
        return frame, accounts[0]

    def load_events(self, member: RawMember) -> pd.DataFrame | None:
        """Read one monthly alarm log into the canonical events schema.

        The log has no message column, so ``message`` is left empty rather than filled
        from the provider's 12-code description file: that file describes the code, not
        the event, and says nothing at all about 421 of the 429 codes that occur.

        Args:
            member: Member classified as an alarm log.

        Returns:
            A canonical events table, or ``None`` for a member that is not an alarm log.

        Raises:
            RuntimeError: If the alarm log columns are absent.
        """
        if member.kind != "alarm_log":
            return None
        frame = read_csv_member(member)
        missing = [column for column in ALARM_COLUMNS if column not in frame.columns]
        if missing:
            raise RuntimeError(f"{member.label}: alarm log is missing columns {missing}")
        turbines = self._turbines(frame["StationNr"], member)
        raw = frame[list(ALARM_COLUMNS)].to_json(orient="records", lines=True).splitlines()
        events = pd.DataFrame(
            {
                "source": self.source_id,
                "site": self.site_name,
                "turbine_id": turbines,
                # The alarm log shares the SCADA controller's clock, measured UTC. Its
                # times are instants, not interval labels, so nothing is shifted.
                "start_utc": pd.to_datetime(frame["TimeOn"], errors="coerce", utc=True),
                "end_utc": pd.to_datetime(frame["TimeOff"], errors="coerce", utc=True),
                "code": [_code(value) for value in frame["Alarmcode"]],
                "message": None,
                "category": None,
                "is_fault": pd.Series([None] * len(frame), dtype="object"),
                "raw": raw,
            }
        )
        events = events[events["start_utc"].notna() & events["turbine_id"].notna()]
        return events[list(EVENT_COLUMNS)].reset_index(drop=True)
