"""Raw archive inventory.

This module answers the question the whole text side of the project depends on:
**do the public SCADA event logs contain free text, or only template strings?**
ADR-0001 asserts they are template-like, and this is where that assertion is
either confirmed or overturned with evidence rather than belief.

Nothing is extracted to disk. Archives are listed and sampled in place, headers are
sniffed from the first lines of one member per class, and every status, alarm or
event table found is profiled: row count, unique codes, unique messages, the share
of rows carrying non-empty free text, and the twenty most frequent messages.

The output is one Markdown report per source under ``reports/data/``, which is
tracked, so the verdict is auditable without re-downloading 20 GB.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from faultline.data.common.report import kv_table, section, table, top_values_table, truncate
from faultline.data.telemetry.adapters import get_adapter
from faultline.data.telemetry.adapters.base import (
    BaseAdapter,
    MemberKind,
    RawMember,
    open_member,
    read_csv_member,
)
from faultline.download.zenodo import SourceSpec
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

#: Member kinds that may carry event text.
EVENT_KINDS: tuple[MemberKind, ...] = ("status_events", "alarm_log")

#: Column-name substrings that plausibly hold event message text, most specific first.
MESSAGE_HINTS: tuple[str, ...] = (
    "message",
    "description",
    "alarm_text",
    "status_text",
    "text",
    "reason",
    "comment",
    "event",
    "status",
)

#: Column-name substrings that plausibly hold an event code.
CODE_HINTS: tuple[str, ...] = ("code", "id", "number", "alarm", "status")

#: Members larger than this (uncompressed) are not parsed during inspection.
MAX_PARSE_BYTES = 200 * 1024 * 1024

#: Row cap when profiling one event table.
MAX_PARSE_ROWS = 500_000

#: Heuristic thresholds for the free-text verdict. These classify, they do not
#: decide: the raw counts are printed next to the verdict in every report.
TEMPLATE_MAX_UNIQUE = 500
TEMPLATE_MAX_MEAN_CHARS = 60


def sniff_lines(member: RawMember, n_lines: int = 30, max_bytes: int = 64_000) -> list[str]:
    """Read the first lines of a member as text.

    Args:
        member: Member to sample.
        n_lines: Maximum number of lines to return.
        max_bytes: Maximum number of bytes to read.

    Returns:
        Decoded lines, with undecodable bytes replaced.
    """
    try:
        with open_member(member) as handle:
            blob = handle.read(max_bytes)
    except (OSError, KeyError) as exc:
        logger.warning("cannot sniff %s: %s", member.label, exc)
        return []
    text = blob.decode("utf-8", errors="replace")
    return text.splitlines()[:n_lines]


def read_member_table(member: RawMember, nrows: int | None = MAX_PARSE_ROWS) -> pd.DataFrame | None:
    """Parse a CSV member into a DataFrame, applying the inspection size caps.

    Args:
        member: Member to parse.
        nrows: Row cap, or ``None`` to read the whole member.

    Returns:
        The parsed table, or ``None`` when the member is too large or unparseable.
    """
    if member.size > MAX_PARSE_BYTES:
        logger.info(
            "skipping %s: %.1f MB exceeds the inspection cap", member.label, member.size / 1e6
        )
        return None
    if not member.name.lower().endswith((".csv", ".txt")) and member.in_archive:
        return None
    return read_csv_member(member, nrows=nrows)


def pick_column(columns: list[str], hints: tuple[str, ...]) -> str | None:
    """Choose the first column whose name matches a hint.

    Args:
        columns: Column names of the table.
        hints: Substrings to look for, most specific first.

    Returns:
        The chosen column name, or ``None`` when nothing matches.
    """
    lowered = {name: str(name).lower() for name in columns}
    for hint in hints:
        for name, lower in lowered.items():
            if hint in lower:
                return name
    return None


def profile_event_table(member: RawMember, frame: pd.DataFrame) -> dict[str, Any]:
    """Profile one candidate event table.

    Args:
        member: The member the table came from.
        frame: The parsed table.

    Returns:
        A mapping of profile statistics, including the columns chosen as the
        message and code columns and the twenty most frequent messages.
    """
    columns = [str(name) for name in frame.columns]
    message_column = pick_column(columns, MESSAGE_HINTS)
    code_column = pick_column(columns, CODE_HINTS)

    profile: dict[str, Any] = {
        "member": member.label,
        "rows": int(len(frame)),
        "columns": len(columns),
        "column_names": columns,
        "message_column": message_column,
        "code_column": code_column,
        "unique_codes": 0,
        "unique_messages": 0,
        "free_text_fraction": 0.0,
        "mean_message_chars": 0.0,
        "top_messages": {},
    }
    if code_column is not None:
        profile["unique_codes"] = int(frame[code_column].nunique(dropna=True))
    if message_column is None:
        return profile

    messages = frame[message_column].astype(str).str.strip()
    non_empty = messages[(messages != "") & (messages.str.lower() != "nan")]
    profile["unique_messages"] = int(non_empty.nunique())
    profile["free_text_fraction"] = float(len(non_empty) / len(frame)) if len(frame) else 0.0
    profile["mean_message_chars"] = float(non_empty.str.len().mean()) if len(non_empty) else 0.0
    profile["top_messages"] = dict(Counter(non_empty.tolist()).most_common(20))
    return profile


def free_text_verdict(
    profiles: list[dict[str, Any]], members_staged: int | None = None
) -> tuple[str, str]:
    """Decide what the inspected event tables say about free text.

    Args:
        profiles: Profiles produced by :func:`profile_event_table`.
        members_staged: How many members were discovered for the source. Pass it so
            that "nothing is staged" is not reported as "searched and found nothing":
            the two read almost identically and mean entirely different things.

    Returns:
        A ``(verdict, rationale)`` pair, where the verdict is one of
        ``VERIFIED yes``, ``VERIFIED no`` or ``UNVERIFIED``.
    """
    if members_staged == 0:
        return (
            "UNVERIFIED",
            "nothing is staged for this source, so no conclusion is possible either way. "
            "This is an absence of evidence, not evidence of absence. Run "
            "`faultline download telemetry --tier 1 --source <id>` and inspect again",
        )
    if not profiles:
        return (
            "UNVERIFIED",
            "archives are staged, but no status, alarm or event member was found in them; "
            "either this record publishes none, or the classification patterns missed it",
        )
    with_messages = [p for p in profiles if p["message_column"] and p["unique_messages"] > 0]
    if not with_messages:
        return (
            "VERIFIED no",
            "event tables were found and parsed, but none carries a non-empty message column",
        )
    unique = max(p["unique_messages"] for p in with_messages)
    mean_chars = max(p["mean_message_chars"] for p in with_messages)
    if unique <= TEMPLATE_MAX_UNIQUE and mean_chars <= TEMPLATE_MAX_MEAN_CHARS:
        return (
            "VERIFIED no",
            f"messages are present but template-like: at most {unique} distinct strings "
            f"with a mean length of {mean_chars:.1f} characters, which is a controlled "
            "vocabulary rather than open-ended language (ADR-0001 holds)",
        )
    return (
        "VERIFIED yes",
        f"messages look open-ended: up to {unique} distinct strings with a mean length of "
        f"{mean_chars:.1f} characters; revisit ADR-0001, the paired text may be usable",
    )


def inventory_members(adapter: BaseAdapter, raw_dir: Path) -> list[RawMember]:
    """Discover and log the members staged for a source.

    Args:
        adapter: Source adapter.
        raw_dir: Directory holding the staged archives.

    Returns:
        The discovered members.
    """
    members = adapter.discover(raw_dir)
    logger.info(
        "%s: %d members across %d files",
        adapter.source_id,
        len(members),
        len({m.archive for m in members}),
    )
    return members


def build_report(
    source: str,
    spec: SourceSpec,
    raw_dir: Path,
    members: list[RawMember],
    profiles: list[dict[str, Any]],
    sniffs: dict[str, list[str]],
    max_members: int,
    repo_root: Path,
) -> str:
    """Render the raw inventory report.

    Args:
        source: Source identifier.
        spec: Source specification from the download config.
        raw_dir: Directory the archives were read from.
        members: Discovered members.
        profiles: Event table profiles.
        sniffs: Header samples, keyed by member label.
        max_members: Cap applied to the per-member listing.
        repo_root: Repository root, used to record the commit.

    Returns:
        A Markdown document.
    """
    verdict, rationale = free_text_verdict(profiles, members_staged=len(members))
    archives = sorted({member.archive for member in members})
    by_kind: Counter[str] = Counter(member.kind for member in members)

    parts = [
        f"# Raw inventory: {source}\n\n",
        kv_table(
            {
                "source": source,
                "provider": spec.provider,
                "licence": spec.license,
                "zenodo record": spec.zenodo_record,
                "concept DOI": spec.concept_doi or "n/a",
                "staged directory": str(raw_dir),
                "files staged": len(archives),
                "members discovered": len(members),
                "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "git_sha": git_sha(repo_root),
            }
        ),
    ]

    parts.append(
        section(
            "Free-text verdict",
            f"**{verdict}** - {rationale}\n\n"
            "This is the evidence behind ADR-0001: whether the paired text in this record is "
            "open-ended language or a controlled vocabulary.",
        )
    )

    parts.append(
        section(
            "Staged files",
            table(
                ["file", "size (MB)", "members"],
                [
                    (
                        path.name,
                        round(path.stat().st_size / 1e6, 1) if path.is_file() else 0.0,
                        sum(1 for member in members if member.archive == path),
                    )
                    for path in archives
                ],
            ),
        )
    )

    parts.append(
        section(
            "Members by kind",
            table(
                ["kind", "members", "uncompressed (MB)"],
                [
                    (
                        kind,
                        count,
                        round(
                            sum(m.size for m in members if m.kind == kind) / 1e6,
                            1,
                        ),
                    )
                    for kind, count in sorted(by_kind.items())
                ],
            ),
        )
    )

    if profiles:
        parts.append(
            section(
                "Event tables found",
                table(
                    [
                        "member",
                        "rows",
                        "columns",
                        "code column",
                        "message column",
                        "unique codes",
                        "unique messages",
                        "free-text share",
                        "mean chars",
                    ],
                    [
                        (
                            truncate(str(profile["member"]), 60),
                            profile["rows"],
                            profile["columns"],
                            profile["code_column"] or "-",
                            profile["message_column"] or "-",
                            profile["unique_codes"],
                            profile["unique_messages"],
                            f"{profile['free_text_fraction'] * 100:.1f}%",
                            round(float(profile["mean_message_chars"]), 1),
                        )
                        for profile in profiles
                    ],
                ),
            )
        )
        for profile in profiles:
            if profile["top_messages"]:
                parts.append(
                    section(
                        f"Top messages: {truncate(str(profile['member']), 60)}",
                        top_values_table(profile["top_messages"], n=20, label="message"),
                        level=3,
                    )
                )
    else:
        parts.append(
            section(
                "Event tables found",
                "_None. Either this record publishes no status, alarm or event table, or the "
                "adapter classification patterns did not recognise it. TODO(m1): confirm "
                "against the provider README before concluding the record has no events._",
            )
        )

    if sniffs:
        body = []
        for label, lines in sniffs.items():
            body.append(f"**{label}**\n")
            body.append("```text")
            body.extend(line[:200] for line in lines)
            body.append("```\n")
        parts.append(section("Header samples (first lines, one member per kind)", "\n".join(body)))

    listing = members[:max_members]
    parts.append(
        section(
            f"Member listing ({len(listing)} of {len(members)})",
            table(
                ["archive", "member", "kind", "uncompressed (MB)", "compressed (MB)"],
                [
                    (
                        member.archive.name,
                        truncate(member.name or "(loose file)", 80),
                        member.kind,
                        round(member.size / 1e6, 3),
                        round(member.compressed_size / 1e6, 3),
                    )
                    for member in listing
                ],
            ),
        )
    )
    return "".join(parts)


def inspect_source(
    source: str,
    spec: SourceSpec,
    paths: ProjectPaths,
    max_members: int = 5000,
    max_event_members: int = 12,
) -> Path:
    """Inventory one source's staged archives and write its report.

    Args:
        source: Source identifier.
        spec: Source specification from the download config.
        paths: Resolved project paths.
        max_members: Cap on the member listing in the report.
        max_event_members: Cap on the number of event tables profiled.

    Returns:
        The path of the written report.
    """
    adapter = get_adapter(source, paths.configs_dir)
    raw_dir = paths.source_dir("raw", "telemetry", source)
    members = inventory_members(adapter, raw_dir)

    sniffs: dict[str, list[str]] = {}
    seen_kinds: set[str] = set()
    for member in members:
        if member.kind in seen_kinds or member.size == 0:
            continue
        lines = sniff_lines(member)
        if lines:
            sniffs[member.label] = lines
            seen_kinds.add(member.kind)

    profiles: list[dict[str, Any]] = []
    for member in [m for m in members if m.kind in EVENT_KINDS][:max_event_members]:
        frame = read_member_table(member)
        if frame is None or frame.empty:
            continue
        profiles.append(profile_event_table(member, frame))

    report = build_report(
        source=source,
        spec=spec,
        raw_dir=raw_dir,
        members=members,
        profiles=profiles,
        sniffs=sniffs,
        max_members=max_members,
        repo_root=paths.repo_root,
    )
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d")
    destination = paths.data_reports_dir / f"raw_inventory_{source}_{stamp}.md"
    destination.write_text(report, encoding="utf-8")
    logger.info("%s: wrote %s", source, destination)
    return destination
