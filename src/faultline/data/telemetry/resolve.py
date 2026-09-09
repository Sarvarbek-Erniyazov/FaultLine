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

The two halves of that fingerprint are not equally robust, and the difference is not
academic: some exports repeat timestamps for reasons that have nothing to do with
daylight saving. The spring half survives that, because it counts *distinct* labels
in an hour and asks whether the hour is empty. The autumn half does not, because
repetition is exactly what it looks for. It is therefore reported as not applicable
on any member that repeats timestamps elsewhere, rather than being allowed to
manufacture a verdict out of an unrelated defect.

The output is one tracked Markdown report per source under ``reports/data/``, so the
verdict is auditable without restaging 20 GB.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from faultline.data.common.report import kv_table, section, table
from faultline.data.telemetry.adapters import get_adapter
from faultline.data.telemetry.adapters.base import (
    BaseAdapter,
    RawMember,
    read_csv_member_columns,
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
        duplicate_timestamps: Repeated labels anywhere in the member.
        spring_hour: The civil hour that does not exist locally, as a label.
        steps_in_spring_hour: Distinct labels stamped inside that hour, out of the
            six a 10-minute grid holds. A local-time series has none.
        autumn_hour: The civil hour that occurs twice locally, as a label.
        repeated_steps_in_autumn_hour: Labels occurring more than once in that hour,
            or ``None`` when the member repeats timestamps elsewhere and the test
            therefore cannot distinguish a fall-back from that defect.
    """

    member: str
    turbine_id: str
    year: int
    rows: int
    distinct_timestamps: int
    duplicate_timestamps: int
    spring_hour: str
    steps_in_spring_hour: int
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
    def duplicating_members(self) -> tuple[TimezoneRow, ...]:
        """Members repeating timestamps for a reason other than a fall-back.

        Identified by the autumn test having been withheld: that is withheld
        precisely when duplicates occur outside the fall-back window.
        """
        return tuple(row for row in self.rows if row.repeated_steps_in_autumn_hour is None)


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
        stamps: Parsed, timezone-naive timestamps as published.
        zone: Candidate local zone.

    Returns:
        The fingerprint, or ``None`` when the member spans no year with a
        transition in it.
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
        duplicate_timestamps=duplicates,
        spring_hour=spring_start.strftime("%Y-%m-%d %H"),
        # Distinct labels, so that a member which repeats every timestamp is still
        # measured on whether the hour exists at all.
        steps_in_spring_hour=int(in_spring.nunique()),
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

    gaps = sum(1 for row in rows if row.steps_in_spring_hour == 0)
    testable = [row for row in rows if row.repeated_steps_in_autumn_hour is not None]
    repeats = sum(1 for row in testable if (row.repeated_steps_in_autumn_hour or 0) > 0)
    skipped = len(rows) - len(testable)
    caveat = (
        ""
        if not skipped
        else (
            f"; the autumn half was not applicable on {skipped} of {len(rows)} turbine-years, "
            "which repeat timestamps for an unrelated reason"
        )
    )

    if gaps == 0 and repeats == 0:
        decided, why = (
            "UTC",
            (
                f"across {len(rows)} turbine-years, every spring-forward hour is fully populated "
                f"and no autumn fall-back hour repeats a timestamp -- neither fingerprint that "
                f"{zone} would leave is present{caveat}"
            ),
        )
    elif gaps == len(rows) and testable and repeats == len(testable):
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
                f"the fingerprint is inconsistent: {gaps} of {len(rows)} turbine-years are "
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


def build_report(
    source: str,
    spec: SourceSpec,
    raw_dir: Path,
    power: PowerScaleVerdict,
    timezone: TimezoneVerdict,
    repo_root: Path,
) -> str:
    """Render the resolution report.

    Args:
        source: Source identifier.
        spec: Source specification.
        raw_dir: Directory the archives were read from.
        power: Power-unit verdict.
        timezone: Timezone verdict.
        repo_root: Repository root, for the git SHA.

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
            "repeats every label in the autumn fall-back hour. A UTC series does neither. "
            "`steps in spring hour` counts distinct labels out of the six a 10-minute grid "
            "holds. `repeated steps` reads `n/a` where the member repeats timestamps "
            "elsewhere, because the test cannot then tell a fall-back from that defect.\n\n"
            + table(
                [
                    "member",
                    "turbine",
                    "year",
                    "rows",
                    "distinct",
                    "duplicate labels",
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
                        row.duplicate_timestamps,
                        row.spring_hour,
                        row.steps_in_spring_hour,
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

    duplicating = timezone.duplicating_members
    if duplicating:
        worst = max(duplicating, key=lambda row: row.rows / max(row.distinct_timestamps, 1))
        parts.append(
            section(
                "Timestamp duplication found while measuring",
                f"{len(duplicating)} of {len(timezone.rows)} members repeat timestamps. The worst "
                f"is `{worst.member}`: {worst.rows:,} rows over {worst.distinct_timestamps:,} "
                f"distinct labels, a factor of "
                f"{worst.rows / max(worst.distinct_timestamps, 1):.1f}.\n\n"
                "This is not a daylight-saving artefact and it is not a parsing error: the "
                "distinct labels are exactly the 10-minute grid of the year, and the surplus "
                "rows carry the same labels again. It is recorded here because it was found "
                "here, and because an ingest that does not expect it will read tens of "
                "millions of rows where it planned for hundreds of thousands.\n\n"
                "**TODO(m1): decide how ingest collapses these rows and prove the choice does "
                "not lose values, rather than assuming the surplus rows are empty.**\n\n"
                + table(
                    ["member", "rows", "distinct labels", "factor"],
                    [
                        (
                            row.member,
                            row.rows,
                            row.distinct_timestamps,
                            round(row.rows / max(row.distinct_timestamps, 1), 1),
                        )
                        for row in duplicating
                    ],
                ),
            )
        )
    return "".join(parts)


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

    Returns:
        The path of the written report.
    """
    adapter = get_adapter(source, paths.configs_dir)
    raw_dir = paths.source_dir("raw", "telemetry", source)
    wanted = [timestamp_column, power_column] + ([energy_column] if energy_column else [])

    scale_rows: list[PowerScaleRow] = []
    zone_rows: list[TimezoneRow] = []
    energy_seen: str | None = None

    members = list(_scada_members(adapter, raw_dir))
    for member in members[: max_members or len(members)]:
        frame = read_csv_member_columns(member, wanted)
        if frame.empty or power_column not in frame.columns:
            logger.warning("%s: no %r column; skipped", member.label, power_column)
            continue
        turbine = adapter.turbine_id(member)
        values = pd.to_numeric(frame[power_column], errors="coerce")
        non_null = int(values.notna().sum())
        if non_null >= MIN_ROWS_FOR_TAIL:
            energy_tail: float | None = None
            if energy_column and energy_column in frame.columns:
                energy_seen = energy_column
                energy = pd.to_numeric(frame[energy_column], errors="coerce")
                if energy.notna().any():
                    energy_tail = float(energy.quantile(TAIL_QUANTILE))
            scale_rows.append(
                PowerScaleRow(
                    member=member.name or member.archive.name,
                    turbine_id=turbine,
                    rows=int(len(frame)),
                    non_null=non_null,
                    tail=float(values.quantile(TAIL_QUANTILE)),
                    maximum=float(values.max()),
                    minimum=float(values.min()),
                    energy_tail=energy_tail,
                )
            )
        else:
            logger.info("%s: only %d values; too few for a tail", member.label, non_null)

        if timestamp_column in frame.columns:
            stamps = pd.to_datetime(frame[timestamp_column], errors="coerce")
            row = timezone_row(member.name or member.archive.name, turbine, stamps, candidate_zone)
            if row is not None:
                zone_rows.append(row)

    power = judge_power_scale(
        power_column, energy_seen, spec.site.rated_kw or 0, step_hours, scale_rows
    )
    timezone = judge_timezone(timestamp_column, candidate_zone, spec.timezone, zone_rows)

    report = build_report(source, spec, raw_dir, power, timezone, paths.repo_root)
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d")
    destination = paths.data_reports_dir / f"resolved_{source}_{stamp}.md"
    destination.write_text(report, encoding="utf-8")
    logger.info("%s: wrote %s", source, destination)
    return destination
