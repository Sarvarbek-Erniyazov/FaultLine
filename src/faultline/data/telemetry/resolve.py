"""Resolving open unit and timezone questions against the staged archives.

Two questions were left open at M0 with a ``TODO(m1)`` because they could not be
answered from provider metadata:

1. **What unit is the power column in?** The Kelmarsh SCADA header says
   ``Power (kW)`` while the provider's own signal mapping records the unit of the
   same signal as ``kWh``. One of those is wrong, and which one is wrong changes the
   plausibility bound by a factor of six.
2. **What timezone are the timestamps in?** A Greenbyte preamble line stating
   ``Time zone: UTC`` is a claim by the exporter, not a property of the data.

Neither is settled by reading more metadata: the metadata is what disagrees. Both
are settled here by measuring the data.

**The power question** is decided by a scale test. A 10-minute mean of active power
from a machine rated at *R* kW tops out near *R*; a 10-minute energy total from the
same machine tops out near *R/6*. Those differ by 6x, so the upper tail of the
column lands unambiguously on one of them. The tail statistic is p99.5 rather than
the maximum, which a single spike would decide on its own.

**The timezone question** is decided by looking for the fingerprint local civil time
leaves behind and UTC cannot. A series stamped in UK local time has, once a year, an
hour in late March that contains no observations, and an hour in late October whose
labels each occur twice. A series stamped in UTC has neither, in any year. The test
runs per turbine-year at the real transition instants for the zone, taken from the
tz database rather than assumed to be the last Sunday of the month.

The two halves of that fingerprint are not equally robust. The spring half counts
*distinct* labels in an hour and asks whether the hour is empty, so it survives an
export that repeats labels. The autumn half looks for repetition, so an export that
repeats labels for another reason would fool it. At M0 it therefore abstained on the
Kelmarsh 2023 and 2024 exports, which repeat every label about 41 times.

**Since M1a the test reads what the ingest reads.** Rows carrying no value in any
ingested channel are dropped first -- the same null drop the ingest applies before
collapsing (:mod:`faultline.data.telemetry.collapse`). An export whose repeats are
empty then has one row per label, and the autumn half gives a verdict on it. A member
that still repeats a label after the drop is one the ingest would refuse, and the
autumn half still abstains there. For every member that repeats labels, the report
also reads every column of the file and records which columns the repeated rows carry
values in, and whether any of those values disagree.

**Two provider layouts.** A Greenbyte export is one turbine-year per file. Hill of
Towie publishes one file per table per month holding all 21 turbines and labels the end
of each interval; ``station_column``, ``member_prefix`` and ``label_offset_minutes``
measure it per station-year, on labels shifted to interval start.

The output is one tracked Markdown report per source under ``reports/data/``, so the
verdict is auditable without restaging 20 GB.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from faultline.data.common.report import kv_table, section, table
from faultline.data.telemetry.adapters import get_adapter
from faultline.data.telemetry.adapters.base import (
    BaseAdapter,
    RawMember,
    open_member,
    read_csv_member_columns,
    sniff_csv_layout,
)
from faultline.download.zenodo import SourceSpec
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

#: Tail quantile used for the scale test. High enough to sit at the rated ceiling of
#: a well-behaved turbine-year, low enough that one spike cannot decide the verdict.
TAIL_QUANTILE = 0.995

#: A measured tail within this factor of a reference is treated as agreeing with it.
#: The two candidate references differ by 6x, so a factor of 2 separates them with
#: room to spare while still tolerating a curtailed or derated year.
SCALE_TOLERANCE = 2.0

#: Fewer non-null values than this in a turbine-year and its tail is not evidence.
MIN_ROWS_FOR_TAIL = 1000

#: Rows per chunk when reading every column of a large export.
CHUNK_ROWS = 200_000

_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


@dataclass(frozen=True)
class PowerScaleRow:
    """The upper tail of one turbine-year's power column.

    Attributes:
        member: Archive member the values came from.
        turbine_id: Turbine the member belongs to.
        rows: Rows read.
        non_null: Rows with a value.
        tail: Value at :data:`TAIL_QUANTILE`.
        maximum: Largest value seen.
        minimum: Smallest value seen.
        energy_tail: Same quantile of the separate energy column, when the record
            publishes one.
    """

    member: str
    turbine_id: str
    rows: int
    non_null: int
    tail: float
    maximum: float
    minimum: float
    energy_tail: float | None


@dataclass(frozen=True)
class PowerScaleVerdict:
    """What the measured tails say about the unit of the power column.

    Attributes:
        column: Power column that was measured.
        energy_column: Separate energy column found in the same export, if any.
        rated_kw: Rated power of the machine, from the source specification.
        step_hours: Length of one sampling step in hours.
        rows: One entry per turbine-year measured.
        verdict: ``kW``, ``kWh per step``, or ``unresolved``.
        rationale: One sentence stating what decided it.
    """

    column: str
    energy_column: str | None
    rated_kw: int
    step_hours: float
    rows: tuple[PowerScaleRow, ...]
    verdict: str
    rationale: str

    @property
    def kw_reference(self) -> float:
        """Tail expected if the column is a mean active power in kW."""
        return float(self.rated_kw)

    @property
    def kwh_reference(self) -> float:
        """Tail expected if the column is an energy total in kWh per step."""
        return self.rated_kw * self.step_hours

    @property
    def median_tail(self) -> float:
        """Median of the per-turbine-year tails, or NaN when nothing was measured."""
        tails = sorted(row.tail for row in self.rows)
        if not tails:
            return float("nan")
        middle = len(tails) // 2
        if len(tails) % 2:
            return tails[middle]
        return (tails[middle - 1] + tails[middle]) / 2


@dataclass(frozen=True)
class TimezoneRow:
    """The DST fingerprint of one turbine-year.

    Attributes:
        member: Archive member the timestamps came from.
        turbine_id: Turbine the member belongs to.
        year: Calendar year of the transition tested.
        rows: Timestamps read.
        distinct_timestamps: Distinct labels among them.
        rows_after_null_drop: Rows left once those with no ingested value are dropped;
            the test below runs on these.
        duplicate_timestamps: Repeated labels among those rows.
        spring_hour: The civil hour that does not exist locally, as a label.
        steps_in_spring_hour: Distinct labels stamped inside that hour, out of the
            six a 10-minute grid holds. A local-time series has none. ``None`` when
            the hour is empty and the series does not run through it (no data in the
            hour before or the hour after), so the emptiness is a gap, not a clock.
        autumn_hour: The civil hour that occurs twice locally, as a label.
        repeated_steps_in_autumn_hour: Labels occurring more than once in that hour,
            or ``None`` when labels repeat elsewhere too and the test therefore cannot
            distinguish a fall-back from that.
    """

    member: str
    turbine_id: str
    year: int
    rows: int
    distinct_timestamps: int
    rows_after_null_drop: int
    duplicate_timestamps: int
    spring_hour: str
    steps_in_spring_hour: int | None
    autumn_hour: str
    repeated_steps_in_autumn_hour: int | None


@dataclass(frozen=True)
class TimezoneVerdict:
    """What the DST fingerprint says about the timezone of the timestamps.

    Attributes:
        column: Timestamp column that was measured.
        candidate_zone: Local zone tested against, from the site's country.
        declared: Timezone the source specification declares.
        rows: One entry per turbine-year measured.
        verdict: ``UTC``, the candidate zone's name, or ``unresolved``.
        rationale: One sentence stating what decided it.
    """

    column: str
    candidate_zone: str
    declared: str | None
    rows: tuple[TimezoneRow, ...]
    verdict: str
    rationale: str

    @property
    def repeating_members(self) -> tuple[TimezoneRow, ...]:
        """Members whose published labels repeat, before any row is dropped."""
        return tuple(row for row in self.rows if row.rows > row.distinct_timestamps)


@dataclass(frozen=True)
class RepeatCheck:
    """Every column of an export that repeats labels, read for values in the repeats.

    Attributes:
        member: Archive member read.
        rows: Rows read.
        labels: Distinct labels.
        columns: Value columns read.
        repeating: Columns holding a value on more than one of a label's rows.
        conflicting: Columns holding two distinct values for one label: where the
            ingest's assertion fails.
        non_numeric: Columns holding a non-null cell that is not a number, which the
            by-value comparison cannot check.
    """

    member: str
    rows: int
    labels: int
    columns: int
    repeating: tuple[str, ...]
    conflicting: tuple[str, ...]
    non_numeric: tuple[str, ...] = ()


def dst_transitions(year: int, zone: str) -> tuple[datetime, datetime] | None:
    """Find a zone's two DST transition instants in a year.

    Read from the tz database by scanning for a change in UTC offset, rather than
    assuming a rule such as "the last Sunday in March": the rule has changed before
    and differs between zones, and this check is worthless if it looks in the wrong
    hour.

    Args:
        year: Calendar year.
        zone: IANA zone name.

    Returns:
        The spring-forward and fall-back instants as UTC-aware datetimes, or
        ``None`` when the zone has no transitions that year.
    """
    tz = ZoneInfo(zone)
    changes: list[datetime] = []
    moment = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC)
    previous = moment.astimezone(tz).utcoffset()
    while moment < end:
        moment += timedelta(hours=1)
        offset = moment.astimezone(tz).utcoffset()
        if offset != previous:
            changes.append(moment)
            previous = offset
    if len(changes) != 2:
        return None
    return changes[0], changes[1]


def _shift(instant: datetime, zone: str) -> timedelta:
    """Return how far a zone's UTC offset moves at a transition instant.

    Args:
        instant: The transition instant, in UTC.
        zone: IANA zone name.

    Returns:
        The offset after the transition minus the offset before it.
    """
    tz = ZoneInfo(zone)
    after = instant.astimezone(tz).utcoffset() or timedelta()
    before = (instant - timedelta(minutes=1)).astimezone(tz).utcoffset() or timedelta()
    return after - before


def affected_local_window(instant: datetime, zone: str) -> tuple[datetime, timedelta]:
    """Return the span of local labels a transition skips or repeats.

    The test compares *labels*, because that is all a naive timestamp column
    carries. Both fingerprints therefore have to be expressed in local civil time:
    at a spring forward the labels in ``[local_after - shift, local_after)`` never
    occur, and at a fall back the labels in ``[local_after, local_after + |shift|)``
    occur twice.

    Args:
        instant: The transition instant, in UTC.
        zone: IANA zone name.

    Returns:
        A naive local start label and the width of the affected span.
    """
    tz = ZoneInfo(zone)
    shift = _shift(instant, zone)
    local_after = instant.astimezone(tz).replace(tzinfo=None)
    if shift > timedelta():  # spring forward: the labels before this never happen
        return local_after - shift, shift
    return local_after, -shift  # fall back: the labels from here repeat


def timezone_row(member: str, turbine_id: str, stamps: pd.Series, zone: str) -> TimezoneRow | None:
    """Test one member's timestamps for the local-time DST fingerprint.

    Args:
        member: Member label, for the report.
        turbine_id: Turbine the member belongs to.
        stamps: Parsed, timezone-naive timestamps -- the rows that carry a value.
        zone: Candidate local zone.

    Returns:
        The fingerprint, or ``None`` when the member spans no year with a
        transition in it. ``rows`` and ``distinct_timestamps`` describe ``stamps``;
        the caller replaces them with the counts before any row was dropped.
    """
    stamps = stamps.dropna()
    if stamps.empty:
        return None
    year = int(stamps.dt.year.mode().iloc[0])
    transitions = dst_transitions(year, zone)
    if transitions is None:
        return None
    spring, autumn = transitions
    spring_start, spring_width = affected_local_window(spring, zone)
    autumn_start, autumn_width = affected_local_window(autumn, zone)

    in_spring = stamps[(stamps >= spring_start) & (stamps < spring_start + spring_width)]
    in_autumn = stamps[(stamps >= autumn_start) & (stamps < autumn_start + autumn_width)]
    # An empty spring hour is local time's fingerprint only when the series runs
    # through it: data in the hour before and the hour after. A turbine that was not yet
    # reporting -- all 14 Penmanshiel turbines start in June or July 2016 -- or an outage
    # spanning the hour leaves it empty for reasons that say nothing about the clock.
    hour = timedelta(hours=1)
    flanked = bool(
        ((stamps >= spring_start - hour) & (stamps < spring_start)).any()
        and (
            (stamps >= spring_start + spring_width) & (stamps < spring_start + spring_width + hour)
        ).any()
    )
    duplicates = int(stamps.duplicated().sum())
    # A fall-back produces duplicates *only* inside the autumn window. Duplicates
    # anywhere else mean the member repeats labels for some other reason, and the
    # autumn half of the test can no longer tell the two apart.
    repeated_in_autumn = int(in_autumn.duplicated().sum())
    duplicates_elsewhere = duplicates - repeated_in_autumn

    return TimezoneRow(
        member=member,
        turbine_id=turbine_id,
        year=year,
        rows=int(len(stamps)),
        distinct_timestamps=int(stamps.nunique()),
        rows_after_null_drop=int(len(stamps)),
        duplicate_timestamps=duplicates,
        spring_hour=spring_start.strftime("%Y-%m-%d %H"),
        # Distinct labels, so that a member which repeats every timestamp is still
        # measured on whether the hour exists at all. Withheld when the hour is empty
        # but not flanked by data: the test cannot tell a clock from a gap there.
        steps_in_spring_hour=(int(in_spring.nunique()) if (len(in_spring) or flanked) else None),
        autumn_hour=autumn_start.strftime("%Y-%m-%d %H"),
        # Withheld where repetition is already happening for another reason: this
        # test cannot tell a fall-back apart from that.
        repeated_steps_in_autumn_hour=None if duplicates_elsewhere else repeated_in_autumn,
    )


def judge_power_scale(
    column: str,
    energy_column: str | None,
    rated_kw: int,
    step_hours: float,
    rows: list[PowerScaleRow],
) -> PowerScaleVerdict:
    """Decide the unit of a power column from the measured tails.

    Args:
        column: Power column measured.
        energy_column: Separate energy column found, if any.
        rated_kw: Rated power per turbine in kW.
        step_hours: Length of one sampling step in hours.
        rows: Per-turbine-year tails.

    Returns:
        The verdict, ``unresolved`` when nothing was measured or the tails sit
        between the two references rather than on one of them.
    """
    verdict = PowerScaleVerdict(
        column=column,
        energy_column=energy_column,
        rated_kw=rated_kw,
        step_hours=step_hours,
        rows=tuple(rows),
        verdict="unresolved",
        rationale="no turbine-year carried enough values to measure a tail",
    )
    if not rows or not rated_kw:
        return verdict

    tail = verdict.median_tail
    near_kw = (
        verdict.kw_reference / SCALE_TOLERANCE <= tail <= verdict.kw_reference * SCALE_TOLERANCE
    )
    near_kwh = (
        verdict.kwh_reference / SCALE_TOLERANCE <= tail <= verdict.kwh_reference * SCALE_TOLERANCE
    )
    if near_kw and not near_kwh:
        decided, why = (
            "kW",
            (
                f"the median per-turbine-year p{TAIL_QUANTILE * 100:g} is {tail:,.1f}, which sits "
                f"on the rated power of {verdict.kw_reference:,.0f} kW and is "
                f"{tail / verdict.kwh_reference:.1f}x the {verdict.kwh_reference:,.1f} kWh a "
                f"{step_hours * 60:.0f}-minute energy total would reach"
            ),
        )
    elif near_kwh and not near_kw:
        decided, why = (
            "kWh per step",
            (
                f"the median per-turbine-year p{TAIL_QUANTILE * 100:g} is {tail:,.1f}, which sits "
                f"on the {verdict.kwh_reference:,.1f} kWh a {step_hours * 60:.0f}-minute energy "
                f"total would reach rather than the rated {verdict.kw_reference:,.0f} kW"
            ),
        )
    else:
        decided, why = (
            "unresolved",
            (
                f"the median per-turbine-year p{TAIL_QUANTILE * 100:g} is {tail:,.1f}, not "
                f"within a factor of {SCALE_TOLERANCE:g} of exactly one of "
                f"{verdict.kw_reference:,.0f} kW and {verdict.kwh_reference:,.1f} kWh"
            ),
        )
    return PowerScaleVerdict(
        column=column,
        energy_column=energy_column,
        rated_kw=rated_kw,
        step_hours=step_hours,
        rows=tuple(rows),
        verdict=decided,
        rationale=why,
    )


def judge_timezone(
    column: str, zone: str, declared: str | None, rows: list[TimezoneRow]
) -> TimezoneVerdict:
    """Decide the timezone of a timestamp column from the DST fingerprint.

    Args:
        column: Timestamp column measured.
        zone: Candidate local zone tested against.
        declared: Timezone the source specification declares.
        rows: Per-turbine-year fingerprints.

    Returns:
        The verdict, ``unresolved`` when the turbine-years disagree with each other.
    """
    base = TimezoneVerdict(
        column=column,
        candidate_zone=zone,
        declared=declared,
        rows=tuple(rows),
        verdict="unresolved",
        rationale="no turbine-year covered a daylight-saving transition",
    )
    if not rows:
        return base

    spring_testable = [row for row in rows if row.steps_in_spring_hour is not None]
    gaps = sum(1 for row in spring_testable if row.steps_in_spring_hour == 0)
    testable = [row for row in rows if row.repeated_steps_in_autumn_hour is not None]
    repeats = sum(1 for row in testable if (row.repeated_steps_in_autumn_hour or 0) > 0)
    skipped = len(rows) - len(testable)
    spring_skipped = len(rows) - len(spring_testable)
    notes = []
    if spring_skipped:
        notes.append(
            f"the spring half was not applicable on {spring_skipped} of {len(rows)} "
            "turbine-years, whose series does not run through the hour (no data in the "
            "hour before or after it)"
        )
    if skipped:
        notes.append(
            f"the autumn half was not applicable on {skipped} of {len(rows)} turbine-years, "
            "which still repeat labels after the rows without an ingested value are dropped"
        )
    caveat = "; " + "; ".join(notes) if notes else "; both halves applied to every turbine-year"

    if not spring_testable and not testable:
        return base
    if gaps == 0 and repeats == 0:
        decided, why = (
            "UTC",
            (
                f"across {len(rows)} turbine-years, every spring-forward hour is fully populated "
                f"and no autumn fall-back hour repeats a timestamp -- neither fingerprint that "
                f"{zone} would leave is present{caveat}"
            ),
        )
    elif spring_testable and gaps == len(spring_testable) and testable and repeats == len(testable):
        decided, why = (
            zone,
            (
                f"all {len(rows)} turbine-years are missing the spring-forward hour and repeat the "
                f"autumn fall-back hour, which is the fingerprint of civil time in {zone}{caveat}"
            ),
        )
    else:
        decided, why = (
            "unresolved",
            (
                f"the fingerprint is inconsistent: {gaps} of {len(spring_testable)} testable "
                "turbine-years are "
                f"missing the spring-forward hour and {repeats} of {len(testable)} testable ones "
                f"repeat the autumn fall-back hour, so the record is neither uniformly UTC nor "
                f"uniformly local{caveat}"
            ),
        )
    return TimezoneVerdict(
        column=column,
        candidate_zone=zone,
        declared=declared,
        rows=tuple(rows),
        verdict=decided,
        rationale=why,
    )


def check_repeated_columns(
    member: RawMember, label_column: str, chunk_rows: int = CHUNK_ROWS
) -> RepeatCheck:
    """Read every column of an export and find the values its repeated labels carry.

    Streams the member in chunks and keeps, per label and column, the count of non-null
    cells and their minimum and maximum. A column holding a value on more than one of a
    label's rows is *repeating*; one whose repeated values differ is *conflicting*, which
    is exactly where the ingest's assertion -- at most one distinct non-null value per
    (label, column) -- fails. The comparison is by value, so a cell that is not a number
    cannot take part in it; such columns are counted, never silently read as empty.

    Args:
        member: Member to read.
        label_column: The timestamp label column.
        chunk_rows: Rows per chunk.

    Returns:
        The columns that repeat, and those that conflict.
    """
    with open_member(member) as handle:
        head = handle.read(65_536)
    skiprows, names = sniff_csv_layout(head)
    counts: pd.DataFrame | None = None
    low: pd.DataFrame | None = None
    high: pd.DataFrame | None = None
    text_cells: pd.Series[Any] | None = None
    rows = 0
    with open_member(member) as handle:
        reader = pd.read_csv(
            handle,
            skiprows=skiprows,
            names=names,
            header=None if names else "infer",
            chunksize=chunk_rows,
            low_memory=False,
        )
        for chunk in reader:
            rows += len(chunk)
            labels = chunk.pop(label_column).to_numpy()
            values = chunk.apply(pd.to_numeric, errors="coerce")
            lost = (chunk.notna() & values.isna()).sum()
            text_cells = lost if text_cells is None else text_cells.add(lost, fill_value=0)
            grouped = values.groupby(labels)
            c, lo, hi = grouped.count(), grouped.min(), grouped.max()
            if counts is None or low is None or high is None:
                counts, low, high = c, lo, hi
            else:
                counts = counts.add(c, fill_value=0)
                low = pd.concat([low, lo]).groupby(level=0).min()
                high = pd.concat([high, hi]).groupby(level=0).max()
    if counts is None or low is None or high is None:
        return RepeatCheck(member.label, 0, 0, 0, (), ())
    repeating = [str(column) for column in counts.columns if bool((counts[column] > 1).any())]
    spread = (high - low).abs()
    conflicting = [str(column) for column in repeating if bool((spread[column] > 1e-9).any())]
    non_numeric = (
        [str(column) for column, cells in text_cells.items() if cells > 0]
        if text_cells is not None
        else []
    )
    return RepeatCheck(
        member=member.name or member.archive.name,
        rows=rows,
        labels=len(counts),
        columns=len(counts.columns),
        repeating=tuple(repeating),
        conflicting=tuple(conflicting),
        non_numeric=tuple(non_numeric),
    )


def _scada_members(adapter: BaseAdapter, raw_dir: Path) -> Iterator[RawMember]:
    """Yield the SCADA members staged for a source, in archive order.

    Args:
        adapter: Source adapter.
        raw_dir: Directory holding the staged archives.

    Yields:
        Members classified as 10-minute SCADA.
    """
    for member in adapter.discover(raw_dir):
        if member.kind == "scada_10min" and member.size > 0:
            yield member


def _basename(member: RawMember) -> str:
    """The member's file name without its archive path."""
    return member.name.rsplit("/", 1)[-1] or member.archive.name


def ingested_columns(adapter: BaseAdapter, member_prefix: str | None) -> list[str]:
    """The columns the ingest reads from this source's members.

    Args:
        adapter: Source adapter, with its channel map loaded.
        member_prefix: For a provider that splits signals over tables, the table the
            measured members belong to; only that table's fields are returned.

    Returns:
        Source column names, as they appear in the members' headers.
    """
    columns = []
    for column in adapter.channel_map.values():
        table_name, field_name = adapter.split_channel_column(column)
        if table_name is None or (member_prefix and member_prefix.startswith(table_name)):
            columns.append(field_name)
    return columns


@dataclass
class _Measurement:
    """What one pass over a source's members collected."""

    scale_rows: list[PowerScaleRow]
    zone_rows: list[TimezoneRow]
    repeating: list[RawMember]
    energy_seen: str | None = None
    boundary_copies: int = 0


def _power_row(
    label: str,
    turbine: str,
    frame: pd.DataFrame,
    power_column: str,
    energy_column: str | None,
    measured: _Measurement,
) -> None:
    """Append one turbine-year's power tail, when it has enough values."""
    values = pd.to_numeric(frame[power_column], errors="coerce")
    non_null = int(values.notna().sum())
    if non_null < MIN_ROWS_FOR_TAIL:
        logger.info("%s: only %d values; too few for a tail", label, non_null)
        return
    energy_tail: float | None = None
    if energy_column and energy_column in frame.columns:
        measured.energy_seen = energy_column
        energy = pd.to_numeric(frame[energy_column], errors="coerce")
        if energy.notna().any():
            energy_tail = float(energy.quantile(TAIL_QUANTILE))
    measured.scale_rows.append(
        PowerScaleRow(
            member=label,
            turbine_id=turbine,
            rows=int(len(frame)),
            non_null=non_null,
            tail=float(values.quantile(TAIL_QUANTILE)),
            maximum=float(values.max()),
            minimum=float(values.min()),
            energy_tail=energy_tail,
        )
    )


def _zone_row(
    label: str,
    turbine: str,
    stamps: pd.Series,
    kept: pd.Series,
    offset: pd.Timedelta,
    zone: str,
    measured: _Measurement,
) -> None:
    """Append one turbine-year's DST fingerprint, measured on the rows with a value."""
    row = timezone_row(label, turbine, stamps[kept] + offset, zone)
    if row is None:
        return
    published = stamps.dropna()
    measured.zone_rows.append(
        replace(row, rows=int(len(published)), distinct_timestamps=int(published.nunique()))
    )


def resolve_source(
    source: str,
    spec: SourceSpec,
    paths: ProjectPaths,
    timestamp_column: str,
    power_column: str,
    energy_column: str | None = None,
    candidate_zone: str = "Europe/London",
    step_hours: float = 1 / 6,
    max_members: int | None = None,
    value_columns: Sequence[str] | None = None,
    station_column: str | None = None,
    member_prefix: str | None = None,
    label_offset_minutes: int = 0,
    check_repeats: bool = True,
) -> Path:
    """Measure a source's power scale and DST fingerprint, and write the report.

    Args:
        source: Source identifier.
        spec: Source specification from the download config.
        paths: Resolved project paths.
        timestamp_column: Timestamp column as published.
        power_column: Power column as published.
        energy_column: Separate energy column, when the export publishes one.
        candidate_zone: Local zone to test the timestamps against.
        step_hours: Length of one sampling step in hours.
        max_members: Cap on the number of members read; all of them when omitted.
        value_columns: Columns whose all-null rows are dropped before the timezone
            test; the ingested channels when omitted.
        station_column: When one member holds every turbine, the column naming the
            turbine; rows are then measured per station and year across members.
        member_prefix: Read only members whose file name starts with this.
        label_offset_minutes: Added to every label before testing; ``-10`` turns
            interval-end labels into interval-start ones.
        check_repeats: Read every column of members that repeat labels.

    Returns:
        The path of the written report.
    """
    adapter = get_adapter(source, paths.configs_dir)
    raw_dir = paths.source_dir("raw", "telemetry", source)
    energy = energy_column or None
    values = (
        list(value_columns)
        if value_columns is not None
        else ingested_columns(adapter, member_prefix)
    )
    if power_column not in values:
        values.append(power_column)
    offset = pd.Timedelta(minutes=label_offset_minutes)

    members = [
        member
        for member in _scada_members(adapter, raw_dir)
        if member_prefix is None or _basename(member).startswith(member_prefix)
    ]
    members = members[: max_members or len(members)]
    measured = _Measurement(scale_rows=[], zone_rows=[], repeating=[])

    if station_column is None:
        for member in members:
            wanted = list(dict.fromkeys([timestamp_column, power_column, *values]))
            if energy:
                wanted.append(energy)
            frame = read_csv_member_columns(member, wanted)
            if frame.empty or power_column not in frame.columns:
                logger.warning("%s: no %r column; skipped", member.label, power_column)
                continue
            label = member.name or member.archive.name
            turbine = adapter.turbine_id(member)
            _power_row(label, turbine, frame, power_column, energy, measured)
            if timestamp_column not in frame.columns:
                continue
            stamps = pd.to_datetime(frame[timestamp_column], errors="coerce")
            present = [column for column in values if column in frame.columns]
            kept = frame[present].apply(pd.to_numeric, errors="coerce").notna().any(axis=1)
            _zone_row(label, turbine, stamps, kept, offset, candidate_zone, measured)
            if stamps.dropna().duplicated().any():
                measured.repeating.append(member)
    else:
        names: dict[int, str] = {}
        station_names: Any = getattr(adapter, "station_names", None)
        if callable(station_names) and members:
            names = dict(station_names(members[0]))
        by_year: dict[str, list[pd.DataFrame]] = {}
        for member in members:
            frame = read_csv_member_columns(
                member, list(dict.fromkeys([timestamp_column, station_column, *values]))
            )
            if frame.empty or station_column not in frame.columns:
                continue
            match = _YEAR.search(_basename(member))
            by_year.setdefault(match.group(1) if match else "", []).append(frame)
        for year, parts in sorted(by_year.items()):
            frame = pd.concat(parts, ignore_index=True)
            # Consecutive monthly files both carry the label on their shared boundary
            # (a January file ends at 1 February 00:00 and the February file starts
            # there). A copy whose values are identical is one observation read twice,
            # and it is dropped here so it cannot pass for a fall-back repeat; a copy
            # whose values differ stays, and the autumn half abstains on it.
            before = len(frame)
            frame = frame.drop_duplicates(
                subset=list(dict.fromkeys([timestamp_column, station_column, *values]))
            )
            measured.boundary_copies += before - len(frame)
            for station, group in frame.groupby(station_column):
                label = f"{member_prefix or ''}{year}_* station {station}"
                station_id = int(float(str(station)))
                turbine = names.get(station_id, str(station_id))
                _power_row(label, turbine, group, power_column, None, measured)
                stamps = pd.to_datetime(group[timestamp_column], errors="coerce")
                kept = group[values].apply(pd.to_numeric, errors="coerce").notna().any(axis=1)
                _zone_row(label, turbine, stamps, kept, offset, candidate_zone, measured)

    repeats = (
        [check_repeated_columns(member, timestamp_column) for member in measured.repeating]
        if check_repeats
        else []
    )
    power = judge_power_scale(
        power_column, measured.energy_seen, spec.site.rated_kw or 0, step_hours, measured.scale_rows
    )
    timezone = judge_timezone(timestamp_column, candidate_zone, spec.timezone, measured.zone_rows)

    report = build_report(
        source,
        spec,
        raw_dir,
        power,
        timezone,
        paths.repo_root,
        repeats=repeats,
        method={
            "timestamp column": timestamp_column,
            "rows tested": "rows carrying a value in at least one of "
            f"{len(values)} ingested columns",
            "station column": station_column or "none: one turbine per member",
            "value-identical copies of a label dropped across files": (
                f"{measured.boundary_copies:,} (the shared boundary label of consecutive "
                "monthly files)"
                if station_column
                else "not applicable"
            ),
            "members read": f"{len(members)}" + (f" ({member_prefix}*)" if member_prefix else ""),
            "label offset applied": f"{label_offset_minutes} min"
            + (" (interval-end labels moved to interval start)" if label_offset_minutes else ""),
        },
    )
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d")
    destination = paths.data_reports_dir / f"resolved_{source}_{stamp}.md"
    destination.write_text(report, encoding="utf-8")
    logger.info("%s: wrote %s", source, destination)
    return destination


def build_report(
    source: str,
    spec: SourceSpec,
    raw_dir: Path,
    power: PowerScaleVerdict,
    timezone: TimezoneVerdict,
    repo_root: Path,
    repeats: Sequence[RepeatCheck] = (),
    method: dict[str, str] | None = None,
) -> str:
    """Render the resolution report.

    Args:
        source: Source identifier.
        spec: Source specification.
        raw_dir: Directory the archives were read from.
        power: Power-unit verdict.
        timezone: Timezone verdict.
        repo_root: Repository root, for the git SHA.
        repeats: All-column checks of the members that repeat labels.
        method: How the measurement was taken, for the header table.

    Returns:
        The Markdown report.
    """
    parts = [
        f"# Resolved questions: {source}\n\n",
        kv_table(
            {
                "source": source,
                "provider": spec.provider,
                "staged directory": str(raw_dir),
                "turbine-years measured": len(power.rows),
                **(method or {}),
                "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "git_sha": git_sha(repo_root),
            }
        ),
    ]

    parts.append(
        section(
            "Power column unit",
            f"**VERDICT {power.verdict}** - {power.rationale}\n\n"
            + kv_table(
                {
                    "column measured": power.column,
                    "separate energy column": power.energy_column or "none found in this export",
                    "rated power (kW)": power.rated_kw,
                    "if the column is kW, the tail should be near": f"{power.kw_reference:,.0f}",
                    "if it is kWh per step, near": f"{power.kwh_reference:,.1f}",
                    f"measured median p{TAIL_QUANTILE * 100:g}": f"{power.median_tail:,.1f}",
                }
            )
            + "\n"
            + table(
                [
                    "member",
                    "turbine",
                    "rows",
                    "with a value",
                    f"p{TAIL_QUANTILE * 100:g}",
                    "max",
                    "min",
                    f"energy p{TAIL_QUANTILE * 100:g}",
                ],
                [
                    (
                        row.member,
                        row.turbine_id,
                        row.rows,
                        row.non_null,
                        row.tail,
                        row.maximum,
                        row.minimum,
                        "n/a" if row.energy_tail is None else row.energy_tail,
                    )
                    for row in power.rows
                ],
            ),
        )
    )

    parts.append(
        section(
            "Timestamp timezone",
            f"**VERDICT {timezone.verdict}** - {timezone.rationale}\n\n"
            + kv_table(
                {
                    "column measured": timezone.column,
                    "candidate local zone": timezone.candidate_zone,
                    "declared in the source specification": timezone.declared or "not declared",
                }
            )
            + "\n"
            + "A local-time series is missing every observation in the spring-forward hour and "
            "repeats every label in the autumn fall-back hour. A UTC series does neither. The "
            "test runs on the rows that carry a value in at least one ingested column, which "
            "is what the ingest keeps. `steps in spring hour` counts distinct labels out of the "
            "six a 10-minute grid holds. `repeated steps` reads `n/a` where labels still repeat "
            "outside the fall-back hour after that drop, because the test cannot then tell a "
            "fall-back from that.\n\n"
            + table(
                [
                    "member",
                    "turbine",
                    "year",
                    "rows",
                    "distinct",
                    "rows with a value",
                    "duplicate labels among them",
                    "spring hour (local)",
                    "steps in spring hour",
                    "autumn hour (local)",
                    "repeated steps",
                ],
                [
                    (
                        row.member,
                        row.turbine_id,
                        row.year,
                        row.rows,
                        row.distinct_timestamps,
                        row.rows_after_null_drop,
                        row.duplicate_timestamps,
                        row.spring_hour,
                        "n/a" if row.steps_in_spring_hour is None else row.steps_in_spring_hour,
                        row.autumn_hour,
                        "n/a"
                        if row.repeated_steps_in_autumn_hour is None
                        else row.repeated_steps_in_autumn_hour,
                    )
                    for row in timezone.rows
                ],
            ),
        )
    )

    repeating = timezone.repeating_members
    if repeating:
        worst = max(repeating, key=lambda row: row.rows / max(row.distinct_timestamps, 1))
        columns = sorted({name for check in repeats for name in check.repeating})
        conflicts = sorted({name for check in repeats for name in check.conflicting})
        textual = sorted({name for check in repeats for name in check.non_numeric})
        widths = sorted({check.columns for check in repeats})
        read_all = (
            "The ingest's assertion, tightened at M1a step 6c, is that no (label, column) "
            "holds more than one *distinct* non-null value. Applied to every column of every "
            f"file that repeats labels ({len(repeats)} files, "
            f"{' or '.join(str(w) for w in widths)} value columns each), "
            + (
                "it holds everywhere: no label carries two different values in any column."
                if not conflicts
                else f"it fails in {len(conflicts)} column(s): "
                f"{', '.join(f'`{c}`' for c in conflicts)}."
            )
            + f" {len(columns)} column(s) carry a value on several rows of a label -- "
            f"{', '.join(f'`{c}`' for c in columns) or 'none'} -- which the assertion allows "
            "when the value is the same, and the collapse keeps once. "
            + (
                f"{len(textual)} column(s) hold cells that are not numbers and cannot be "
                f"compared by value: {', '.join(f'`{c}`' for c in textual)}.\n\n"
                if textual
                else "Every value column is numeric, so every one was compared by value.\n\n"
            )
            if repeats
            else ""
        )
        parts.append(
            section(
                "Repeated timestamp labels",
                f"{len(repeating)} of {len(timezone.rows)} members repeat their timestamp "
                f"labels. The worst is `{worst.member}`: {worst.rows:,} rows over "
                f"{worst.distinct_timestamps:,} distinct labels, a factor of "
                f"{worst.rows / max(worst.distinct_timestamps, 1):.1f}.\n\n"
                "This is an export-format change and not duplicated data. Once the rows that "
                "carry no ingested value are dropped, "
                + (
                    "every label occurs once (`rows with a value` equals `distinct`, and there "
                    "are no duplicate labels among them), so the autumn half of the test above "
                    "applies to these members as well. "
                    if all(row.duplicate_timestamps == 0 for row in repeating)
                    else "some labels still repeat, and the autumn half abstains on those. "
                )
                + read_all
                + "The ingest collapses these files only after asserting the same thing for "
                "the channels it reads (`src/faultline/data/telemetry/collapse.py`), and stops "
                "if a label carries two different values.\n\n"
                + table(
                    ["member", "rows", "distinct labels", "factor", "rows with a value"],
                    [
                        (
                            row.member,
                            row.rows,
                            row.distinct_timestamps,
                            round(row.rows / max(row.distinct_timestamps, 1), 1),
                            row.rows_after_null_drop,
                        )
                        for row in repeating
                    ],
                )
                + (
                    "\n"
                    + table(
                        [
                            "member",
                            "columns read",
                            "columns with a value on several rows of a label",
                            "columns with two distinct values for a label (assertion fails)",
                            "columns with non-numeric cells",
                        ],
                        [
                            (
                                check.member,
                                check.columns,
                                len(check.repeating),
                                len(check.conflicting),
                                len(check.non_numeric),
                            )
                            for check in repeats
                        ],
                    )
                    if repeats
                    else ""
                ),
            )
        )
    return "".join(parts)
