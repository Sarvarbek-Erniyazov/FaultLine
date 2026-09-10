"""Hill of Towie's ShutdownDuration: the held-out site's label source, read in chunks.

``Hill_of_Towie_ShutdownDuration.zip`` holds one CSV, ``ShutdownDuration.csv``, of
three columns -- ``TimeStamp_StartFormat``, ``TurbineName``, ``ShutdownDuration`` --
one row per turbine per 10-minute step: the seconds of downtime in that step. It is
316.8 MB uncompressed, over the 200 MB inspection cap, and it is the label source for
the held-out site, so it cannot be skipped.

The cap is not raised. A cap exists to bound memory, and raising it for one file
bounds nothing. The file is streamed in fixed-size chunks instead, and every figure
here is accumulated across chunks: the schema, the row count, per-turbine coverage and
the distribution of non-zero downtime. The file is never held whole.

The same reader supplies the downtime series to event labelling
(:func:`read_downtime`), restricted to the years a caller asks for.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from faultline.data.common.report import kv_table, section, table
from faultline.data.telemetry.adapters import get_adapter
from faultline.data.telemetry.adapters.base import RawMember, open_member
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

TIMESTAMP = "TimeStamp_StartFormat"
TURBINE = "TurbineName"
DOWNTIME = "ShutdownDuration"
COLUMNS: tuple[str, ...] = (TIMESTAMP, TURBINE, DOWNTIME)

#: Rows per chunk: about 30 MB of CSV, a few tens of MB in memory.
CHUNK_ROWS = 1_000_000

#: Seconds in one grid step. Downtime above this is not possible in a 10-minute step.
STEP_SECONDS = 600

#: Bucket edges for the non-zero downtime histogram, in seconds.
BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0, 60, "(0, 60] s"),
    (60, 300, "(60, 300] s"),
    (300, 599, "(300, 599] s"),
    (599, 600, "600 s (the whole step)"),
    (600, float("inf"), "> 600 s (impossible in one step)"),
)


def iter_downtime(member: RawMember, chunk_rows: int = CHUNK_ROWS) -> Iterator[pd.DataFrame]:
    """Stream the downtime series in chunks, parsed.

    Args:
        member: The ``ShutdownDuration.csv`` member.
        chunk_rows: Rows per chunk.

    Yields:
        Chunks with a UTC ``timestamp_utc``, a ``turbine_id`` and ``downtime_s``.

    Raises:
        RuntimeError: If the member lacks one of the three published columns.
    """
    with open_member(member) as handle:
        reader = pd.read_csv(handle, chunksize=chunk_rows, dtype={TURBINE: "string"})
        for chunk in reader:
            missing = [column for column in COLUMNS if column not in chunk.columns]
            if missing:
                raise RuntimeError(f"{member.label}: missing columns {missing}")
            yield pd.DataFrame(
                {
                    # The column name says interval start, and the values carry +00:00.
                    "timestamp_utc": pd.to_datetime(chunk[TIMESTAMP], errors="coerce", utc=True),
                    "turbine_id": chunk[TURBINE].str.strip(),
                    "downtime_s": pd.to_numeric(chunk[DOWNTIME], errors="coerce"),
                }
            )


def read_downtime(member: RawMember, years: Iterable[int] | None = None) -> pd.DataFrame:
    """Read the downtime series, keeping only the years asked for.

    Args:
        member: The ``ShutdownDuration.csv`` member.
        years: Calendar years to keep; all of them when omitted.

    Returns:
        ``timestamp_utc``, ``turbine_id``, ``downtime_s``, sorted by turbine and time.
    """
    wanted = None if years is None else set(years)
    parts = []
    for chunk in iter_downtime(member):
        if wanted is not None:
            chunk = chunk[chunk["timestamp_utc"].dt.year.isin(wanted)]
        parts.append(chunk)
    frame = (
        pd.concat(parts, ignore_index=True)
        if parts
        else pd.DataFrame(columns=["timestamp_utc", "turbine_id", "downtime_s"])
    )
    return frame.sort_values(["turbine_id", "timestamp_utc"]).reset_index(drop=True)


@dataclass
class TurbineCoverage:
    """One turbine's rows in the downtime series.

    Attributes:
        rows: Rows read.
        first: Earliest timestamp.
        last: Latest timestamp.
        missing_values: Rows whose downtime did not parse.
        nonzero: Rows with downtime above zero.
        full_step: Rows with a whole step down (600 s).
        downtime_s: Total downtime, in seconds.
        labels: Distinct timestamps, for the duplicate count.
    """

    rows: int = 0
    first: pd.Timestamp | None = None
    last: pd.Timestamp | None = None
    missing_values: int = 0
    nonzero: int = 0
    full_step: int = 0
    downtime_s: float = 0.0
    labels: set[int] = field(default_factory=set)

    def expected_steps(self) -> int:
        """Steps between the first and last timestamp, both included."""
        if self.first is None or self.last is None:
            return 0
        return int((self.last - self.first) / pd.Timedelta(seconds=STEP_SECONDS)) + 1


@dataclass
class DowntimeProfile:
    """Everything measured in one streamed pass.

    Attributes:
        member: Member label.
        size_bytes: Uncompressed size.
        columns: Column names as published.
        chunks: Chunks read.
        rows: Rows read.
        unparsed_timestamps: Rows whose timestamp did not parse.
        off_grid: Timestamps not on a 10-minute boundary.
        per_turbine: Coverage per turbine.
        values: Row count per distinct non-zero downtime value.
        negative: Rows with negative downtime.
    """

    member: str
    size_bytes: int
    columns: list[str]
    chunks: int = 0
    rows: int = 0
    unparsed_timestamps: int = 0
    off_grid: int = 0
    per_turbine: dict[str, TurbineCoverage] = field(default_factory=dict)
    values: Counter[float] = field(default_factory=Counter)
    negative: int = 0


def profile_downtime(member: RawMember, chunk_rows: int = CHUNK_ROWS) -> DowntimeProfile:
    """Stream the downtime series once and measure it.

    Args:
        member: The ``ShutdownDuration.csv`` member.
        chunk_rows: Rows per chunk.

    Returns:
        The accumulated profile.
    """
    with open_member(member) as handle:
        header = handle.readline().decode("utf-8", errors="replace").strip().split(",")
    profile = DowntimeProfile(member=member.label, size_bytes=member.size, columns=header)
    for chunk in iter_downtime(member, chunk_rows):
        profile.chunks += 1
        profile.rows += len(chunk)
        stamps = chunk["timestamp_utc"]
        profile.unparsed_timestamps += int(stamps.isna().sum())
        valid = chunk[stamps.notna()]
        # Floor rather than integer arithmetic: the timestamp resolution differs between
        # pandas versions (ns before 3.0, us after), and a modulo in the wrong unit
        # reports every timestamp as off the grid.
        grid = valid["timestamp_utc"].dt.floor(f"{STEP_SECONDS}s")
        profile.off_grid += int((valid["timestamp_utc"] != grid).sum())
        down = valid["downtime_s"]
        profile.negative += int((down < 0).sum())
        nonzero = down[down > 0]
        profile.values.update(Counter(nonzero.round(3).tolist()))
        for turbine, group in valid.groupby("turbine_id"):
            cover = profile.per_turbine.setdefault(str(turbine), TurbineCoverage())
            values = group["downtime_s"]
            cover.rows += len(group)
            first, last = group["timestamp_utc"].min(), group["timestamp_utc"].max()
            cover.first = first if cover.first is None else min(cover.first, first)
            cover.last = last if cover.last is None else max(cover.last, last)
            cover.missing_values += int(values.isna().sum())
            cover.nonzero += int((values > 0).sum())
            cover.full_step += int((values >= STEP_SECONDS).sum())
            cover.downtime_s += float(values.clip(lower=0).sum())
            cover.labels.update(group["timestamp_utc"].astype("int64").tolist())
        logger.info("%s: chunk %d, %d rows so far", member.label, profile.chunks, profile.rows)
    return profile


def _quantiles(values: Counter[float], quantiles: Iterable[float]) -> list[float]:
    """Exact quantiles of a value distribution given as counts."""
    if not values:
        return []
    keys = np.array(sorted(values))
    counts = np.array([values[key] for key in keys], dtype=np.int64)
    cumulative = np.cumsum(counts)
    total = cumulative[-1]
    return [float(keys[np.searchsorted(cumulative, q * total, side="left")]) for q in quantiles]


def render_downtime_report(profile: DowntimeProfile, repo_root: Path) -> str:
    """Render the downtime profile as a tracked Markdown report.

    Args:
        profile: What the streamed pass measured.
        repo_root: Repository root, for the git SHA.

    Returns:
        A Markdown document.
    """
    nonzero = sum(profile.values.values())
    per = profile.per_turbine
    duplicates = sum(cover.rows - len(cover.labels) for cover in per.values())
    parts = [
        "# Downtime series: hill_of_towie\n\n",
        kv_table(
            {
                "member": profile.member,
                "uncompressed (MB)": round(profile.size_bytes / 1e6, 1),
                "read": f"streamed in {profile.chunks} chunks of up to {CHUNK_ROWS:,} rows; "
                "never held whole, and the 200 MB inspection cap was not raised",
                "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "git_sha": git_sha(repo_root),
                "generated by": "faultline inspect downtime",
            }
        ),
    ]
    first = min((c.first for c in per.values() if c.first is not None), default=None)
    last = max((c.last for c in per.values() if c.last is not None), default=None)
    parts.append(
        section(
            "Schema and size",
            kv_table(
                {
                    "columns": ", ".join(f"`{c}`" for c in profile.columns),
                    "rows": profile.rows,
                    "turbines": len(per),
                    "first timestamp": str(first) if first is not None else "-",
                    "last timestamp": str(last) if last is not None else "-",
                    "timestamps that did not parse": profile.unparsed_timestamps,
                    "timestamps off the 10-minute grid": profile.off_grid,
                    "repeated (turbine, timestamp) rows": duplicates,
                    "downtime values that did not parse": sum(
                        c.missing_values for c in per.values()
                    ),
                    "negative downtime values": profile.negative,
                }
            )
            + "\nThe timestamps carry an explicit `+00:00` and the column is named "
            "`TimeStamp_StartFormat`: each row is the 10-minute interval that opens at its "
            "timestamp, the convention every canonical timestamp in this project follows.",
        )
    )
    parts.append(
        section(
            "Coverage per turbine",
            table(
                [
                    "turbine",
                    "rows",
                    "first",
                    "last",
                    "steps first to last",
                    "coverage",
                    "rows with downtime",
                    "whole step down",
                    "downtime (days)",
                ],
                [
                    (
                        turbine,
                        cover.rows,
                        str(cover.first),
                        str(cover.last),
                        cover.expected_steps(),
                        f"{len(cover.labels) / max(cover.expected_steps(), 1) * 100:.2f}%",
                        cover.nonzero,
                        cover.full_step,
                        round(cover.downtime_s / 86_400, 1),
                    )
                    for turbine, cover in sorted(per.items())
                ],
            ),
        )
    )
    buckets = [
        (label, sum(n for v, n in profile.values.items() if low < v <= high))
        for low, high, label in BUCKETS
    ]
    qs = (0.05, 0.25, 0.5, 0.75, 0.95)
    parts.append(
        section(
            "Distribution of non-zero downtime",
            kv_table(
                {
                    "rows with downtime > 0": f"{nonzero:,} of {profile.rows:,} "
                    f"({nonzero / max(profile.rows, 1) * 100:.2f}%)",
                    "distinct non-zero values": len(profile.values),
                    **{
                        f"p{int(q * 100)} (s)": value
                        for q, value in zip(qs, _quantiles(profile.values, qs), strict=False)
                    },
                }
            )
            + "\n"
            + table(
                ["downtime in the step", "rows", "share of non-zero rows"],
                [
                    (label, count, f"{count / max(nonzero, 1) * 100:.2f}%")
                    for label, count in buckets
                ],
            ),
        )
    )
    return "".join(parts)


def inspect_downtime(paths: ProjectPaths, source: str = "hill_of_towie") -> Path:
    """Profile the staged downtime series and write its report.

    Args:
        paths: Resolved project paths.
        source: Source whose downtime series is profiled.

    Returns:
        The path of the written report.

    Raises:
        FileNotFoundError: If the source stages no downtime series.
    """
    adapter = get_adapter(source, paths.configs_dir)
    members = [
        member
        for member in adapter.discover(paths.source_dir("raw", "telemetry", source))
        if member.kind == "downtime_series"
    ]
    if not members:
        raise FileNotFoundError(f"{source}: no downtime series is staged")
    profile = profile_downtime(members[0])
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d")
    destination = paths.data_reports_dir / f"downtime_{source}_{stamp}.md"
    destination.write_text(render_downtime_report(profile, paths.repo_root), encoding="utf-8")
    logger.info("wrote %s", destination)
    return destination
