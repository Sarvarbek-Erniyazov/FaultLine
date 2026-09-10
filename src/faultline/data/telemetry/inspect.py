"""Raw archive inventory.

This module answers the question the whole text side of the project depends on:
**do the public SCADA event logs contain free text, or only template strings?**
ADR-0001 asserts they are template-like, and this is where that assertion is
either confirmed or overturned with evidence rather than belief.

Nothing is extracted to disk. Archives are listed and sampled in place, headers are
sniffed from the first lines of one member per class, and every status, alarm or
event table found is profiled: row count, unique codes, unique messages, the share
of rows carrying non-empty free text, and the twenty most frequent messages. The
text is then pooled across every parsed table, because providers cut their tables
differently -- a turbine-year, a site-month, a farm -- and a per-table figure is not
comparable across those cuts. Where the provider documents its event codes in a
separate file, that file is read too, and the report measures how much of the event
log it actually describes.

The output is one Markdown report per source under ``reports/data/``, which is
tracked, so the verdict is auditable without re-downloading the archives. For a
share-alike record the report quotes no more of the record than the measurement
needs: header samples are cut to column names and per-table listings are omitted.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
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

#: Column-name substrings that plausibly hold an event code. ``id`` is deliberately
#: not one of them: an ``event_id`` or ``asset_id`` names a row or a turbine, not an
#: event type, and reading one as a code reports nonsense code counts.
CODE_HINTS: tuple[str, ...] = ("code", "number", "alarm", "status")

#: Members larger than this (uncompressed) are not parsed during inspection.
MAX_PARSE_BYTES = 200 * 1024 * 1024

#: Row cap when profiling one event table.
MAX_PARSE_ROWS = 500_000

#: Cap on the number of event members parsed per source. Every member is still
#: listed, and every event member left unparsed is reported with the reason, so the
#: cap bounds the work without hiding what it skipped.
MAX_EVENT_MEMBERS = 200

#: Per-table "top messages" sections rendered in a report. The pooled measurements
#: cover every parsed table; this only keeps a 98-table report readable.
MAX_TOP_SECTIONS = 12

#: Suffixes whose leading bytes are worth printing as a header sample. A workbook or
#: a nested archive decodes to noise.
TEXT_SUFFIXES: tuple[str, ...] = (".csv", ".txt", ".md", ".json")

#: Heuristic thresholds for the free-text verdict. These classify, they do not
#: decide: the raw counts are printed next to the verdict in every report.
TEMPLATE_MAX_UNIQUE = 500
TEMPLATE_MAX_MEAN_CHARS = 60


@dataclass
class EventEvidence:
    """What the inspection read from a source's event members, and what it did not.

    Attributes:
        profiles: One profile per parsed event table.
        candidates: Event members discovered, parsed or not.
        skipped: Event members that were not parsed, each with the reason.
        cap: The member cap that was in force.
        code_file: The provider file documenting event codes, when the adapter names one.
        code_table: That file as published, or ``None`` when it is not staged.
    """

    profiles: list[dict[str, Any]]
    candidates: int
    skipped: list[tuple[RawMember, str]]
    cap: int
    code_file: str | None = None
    code_table: pd.DataFrame | None = None


@dataclass(frozen=True)
class TextMeasurements:
    """Message text pooled over every parsed event table of a source.

    The per-table maxima are kept alongside the pooled figures for continuity with
    the first inventories, which reported only those.

    Attributes:
        tables: Event tables parsed.
        rows: Rows across those tables.
        text_rows: Rows carrying a non-empty message.
        distinct: Distinct non-empty messages.
        mean_chars: Mean message length in characters, over rows with text.
        mean_words: Mean message length in whitespace-separated words, over rows with text.
        once_share: Share of the distinct messages that occur exactly once.
        max_table_distinct: Most distinct messages found in any single table.
        max_table_mean_chars: Longest mean message length of any single table.
        counts: Row count of every distinct message.
    """

    tables: int
    rows: int
    text_rows: int
    distinct: int
    mean_chars: float
    mean_words: float
    once_share: float
    max_table_distinct: int
    max_table_mean_chars: float
    counts: Counter[str]


def is_share_alike(licence: str) -> bool:
    """Tell whether a licence identifier carries a share-alike condition.

    Args:
        licence: SPDX-style identifier, such as ``CC-BY-SA-4.0``.

    Returns:
        ``True`` when ``SA`` is one of the identifier's components.
    """
    return "SA" in re.split(r"[-_ ]", licence.upper())


def sniff_lines(member: RawMember, n_lines: int = 30, max_bytes: int = 64_000) -> list[str]:
    """Read the first lines of a member as text.

    Args:
        member: Member to sample.
        n_lines: Maximum number of lines to return.
        max_bytes: Maximum number of bytes to read.

    Returns:
        Decoded lines with trailing whitespace removed and undecodable bytes replaced.
    """
    try:
        with open_member(member) as handle:
            blob = handle.read(max_bytes)
    except (OSError, KeyError) as exc:
        logger.warning("cannot sniff %s: %s", member.label, exc)
        return []
    text = blob.decode("utf-8", errors="replace")
    return [line.rstrip() for line in text.splitlines()[:n_lines]]


def sample_headers(members: list[RawMember], n_lines: int = 30) -> dict[str, list[str]]:
    """Sample the leading lines of the first text member of each kind.

    Args:
        members: Discovered members.
        n_lines: Lines to keep per sample.

    Returns:
        Header samples keyed by member label.
    """
    sniffs: dict[str, list[str]] = {}
    seen_kinds: set[str] = set()
    for member in members:
        name = (member.name or member.archive.name).lower()
        if member.kind in seen_kinds or member.size == 0 or not name.endswith(TEXT_SUFFIXES):
            continue
        lines = sniff_lines(member, n_lines=n_lines)
        if lines:
            sniffs[member.label] = lines
            seen_kinds.add(member.kind)
    return sniffs


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


def normalise_code(value: object) -> str:
    """Render an event code the same way whichever file it was read from.

    pandas reads an integer column as float as soon as it holds a gap, so the same
    code arrives as ``127`` from one file and ``127.0`` from another. Both must count
    as one code, and both must match the provider's description of code 127.

    Args:
        value: A code as parsed.

    Returns:
        The code as text, with integral numbers rendered without a decimal part.
    """
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else text


def profile_event_table(member: RawMember, frame: pd.DataFrame) -> dict[str, Any]:
    """Profile one candidate event table.

    Args:
        member: The member the table came from.
        frame: The parsed table.

    Returns:
        A mapping of profile statistics, including the columns chosen as the
        message and code columns, the twenty most frequent messages, and the full
        count of every message and code so that both can be pooled across tables.
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
        "message_counts": Counter(),
        "code_counts": Counter(),
    }
    if code_column is not None:
        profile["unique_codes"] = int(frame[code_column].nunique(dropna=True))
        profile["code_counts"] = Counter(
            normalise_code(value) for value in frame[code_column].dropna().tolist()
        )
    if message_column is None:
        return profile

    # Drop missing values before converting to text. Under pandas 3 a missing value
    # survives ``astype(str)`` as a missing value rather than the string "nan", so the
    # string filter below never saw it: every empty CARE description was counted as a
    # row with text and listed as the message "nan".
    messages = frame[message_column].dropna().astype(str).str.strip()
    non_empty = messages[(messages != "") & (messages.str.lower() != "nan")]
    counts: Counter[str] = Counter(non_empty.tolist())
    profile["unique_messages"] = len(counts)
    profile["free_text_fraction"] = float(len(non_empty) / len(frame)) if len(frame) else 0.0
    profile["mean_message_chars"] = float(non_empty.str.len().mean()) if len(non_empty) else 0.0
    profile["top_messages"] = dict(counts.most_common(20))
    profile["message_counts"] = counts
    return profile


def pooled_codes(profiles: list[dict[str, Any]]) -> Counter[str]:
    """Pool the event codes of every parsed table.

    Args:
        profiles: Profiles produced by :func:`profile_event_table`.

    Returns:
        Row counts per code across all tables.
    """
    codes: Counter[str] = Counter()
    for profile in profiles:
        codes.update(profile.get("code_counts", {}))
    return codes


def measure_text(profiles: list[dict[str, Any]]) -> TextMeasurements:
    """Pool the message text of every parsed table into one set of measurements.

    Args:
        profiles: Profiles produced by :func:`profile_event_table`.

    Returns:
        The pooled measurements.
    """
    counts: Counter[str] = Counter()
    for profile in profiles:
        counts.update(profile.get("message_counts", {}))
    text_rows = sum(counts.values())
    chars = sum(len(message) * count for message, count in counts.items())
    words = sum(len(message.split()) * count for message, count in counts.items())
    with_text = [profile for profile in profiles if profile.get("unique_messages", 0) > 0]
    return TextMeasurements(
        tables=len(profiles),
        rows=sum(int(profile.get("rows", 0)) for profile in profiles),
        text_rows=text_rows,
        distinct=len(counts),
        mean_chars=chars / text_rows if text_rows else 0.0,
        mean_words=words / text_rows if text_rows else 0.0,
        once_share=(
            sum(1 for count in counts.values() if count == 1) / len(counts) if counts else 0.0
        ),
        max_table_distinct=max((int(p["unique_messages"]) for p in with_text), default=0),
        max_table_mean_chars=max((float(p["mean_message_chars"]) for p in with_text), default=0.0),
        counts=counts,
    )


def read_code_table(adapter: BaseAdapter, members: list[RawMember]) -> pd.DataFrame | None:
    """Read the provider's own description of its event codes, if it ships one.

    Args:
        adapter: Source adapter; its ``CODE_DESCRIPTIONS`` names the file.
        members: Discovered members.

    Returns:
        The file as published, or ``None`` when the adapter names no such file or it
        is not staged.
    """
    wanted = adapter.CODE_DESCRIPTIONS
    if wanted is None:
        return None
    for member in members:
        name = (member.name or member.archive.name).rsplit("/", 1)[-1]
        if name.lower() == wanted.lower():
            return read_csv_member(member)
    logger.warning("%s: code description file %s is not staged", adapter.source_id, wanted)
    return None


def code_description_map(frame: pd.DataFrame | None) -> dict[str, str]:
    """Map each documented code to its description.

    Args:
        frame: A provider code description table, or ``None``.

    Returns:
        Descriptions keyed by normalised code; empty when the table is absent or has
        no recognisable code and description columns.
    """
    if frame is None:
        return {}
    columns = [str(name) for name in frame.columns]
    code_column = pick_column(columns, ("code",))
    text_column = pick_column(columns, ("description", "text", "message"))
    if code_column is None or text_column is None:
        return {}
    rows = frame[[code_column, text_column]].dropna()
    return {
        normalise_code(code): str(text).strip()
        for code, text in rows.itertuples(index=False, name=None)
    }


def collect_event_evidence(
    adapter: BaseAdapter, members: list[RawMember], max_event_members: int = MAX_EVENT_MEMBERS
) -> EventEvidence:
    """Parse every event member within the caps, and record the ones left unparsed.

    Args:
        adapter: Source adapter.
        members: Discovered members.
        max_event_members: Cap on the number of event members parsed.

    Returns:
        The profiles, the members skipped with their reasons, and the provider's code
        description table when the adapter names one.
    """
    candidates = [member for member in members if member.kind in EVENT_KINDS]
    profiles: list[dict[str, Any]] = []
    skipped: list[tuple[RawMember, str]] = []
    for index, member in enumerate(candidates):
        if index >= max_event_members:
            skipped.append((member, f"beyond the cap of {max_event_members} members"))
            continue
        if member.size > MAX_PARSE_BYTES:
            skipped.append(
                (
                    member,
                    f"{member.size / 1e6:.1f} MB exceeds the parse cap of "
                    f"{MAX_PARSE_BYTES / 1e6:.1f} MB",
                )
            )
            continue
        frame = read_member_table(member)
        if frame is None or frame.empty:
            skipped.append(
                (member, "not a parseable CSV table" if frame is None else "parsed as empty")
            )
            continue
        profiles.append(profile_event_table(member, frame))
    return EventEvidence(
        profiles=profiles,
        candidates=len(candidates),
        skipped=skipped,
        cap=max_event_members,
        code_file=adapter.CODE_DESCRIPTIONS,
        code_table=read_code_table(adapter, members),
    )


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


def text_section(measurements: TextMeasurements, licence_note: str | None = None) -> str:
    """Render the message text pooled over every parsed table.

    Args:
        measurements: Pooled measurements.
        licence_note: Statement to print above quoted text from a share-alike record.

    Returns:
        A Markdown section.
    """
    m = measurements
    text_share = f"{m.text_rows / m.rows * 100:.1f}%" if m.rows else "n/a"
    body = kv_table(
        {
            "event tables parsed": m.tables,
            "rows": m.rows,
            "rows with a non-empty message": f"{m.text_rows:,} ({text_share})",
            "distinct messages": m.distinct,
            "mean length (characters)": round(m.mean_chars, 1),
            "mean length (words)": round(m.mean_words, 1),
            "distinct messages occurring exactly once": f"{m.once_share * 100:.1f}%",
            "most distinct messages in one table": m.max_table_distinct,
            "longest mean length in one table (characters)": round(m.max_table_mean_chars, 1),
        }
    )
    if m.counts:
        if licence_note:
            body += f"\n_{licence_note}_\n"
        body += "\n**Top 20 messages** (share of rows with a message)\n\n" + top_values_table(
            m.counts, n=20, label="message"
        )
    return section("Text measurements (all parsed tables pooled)", body)


def codes_section(evidence: EventEvidence, codes: Counter[str]) -> str:
    """Render the event codes pooled over every parsed table.

    Args:
        evidence: Event evidence for the source.
        codes: Pooled code counts.

    Returns:
        A Markdown section, or an empty string when no table carries a code column.
    """
    if not codes:
        return ""
    described = code_description_map(evidence.code_table)
    total = sum(codes.values())
    with_codes = sum(1 for profile in evidence.profiles if profile["code_column"])
    summary = kv_table(
        {
            "tables with a code column": f"{with_codes} of {len(evidence.profiles)}",
            "rows carrying a code": total,
            "distinct codes": len(codes),
        }
    )
    headers = ["code", "rows", "share"]
    rows: list[tuple[object, ...]] = []
    for code, count in codes.most_common(20):
        row: tuple[object, ...] = (code, count, f"{count / total * 100:.2f}%")
        if evidence.code_file is not None:
            row = (*row, truncate(described.get(code, "-"), 60))
        rows.append(row)
    if evidence.code_file is not None:
        headers.append(f"description in {evidence.code_file}")
    return section(
        "Event codes (all parsed tables pooled)",
        summary + "\n**Top 20 codes**\n\n" + table(headers, rows),
    )


def code_descriptions_section(evidence: EventEvidence, codes: Counter[str]) -> str:
    """Render the provider's code description file and how much of the log it covers.

    Args:
        evidence: Event evidence for the source.
        codes: Pooled code counts.

    Returns:
        A Markdown section, or an empty string when the adapter names no such file.
    """
    if evidence.code_file is None:
        return ""
    if evidence.code_table is None:
        return section(
            "Provider code descriptions",
            f"_`{evidence.code_file}` is named by the adapter but is not staged._",
        )
    frame = evidence.code_table
    described = code_description_map(frame)
    total = sum(codes.values())
    covered = sum(count for code, count in codes.items() if code in described)
    lengths = [len(text) for text in described.values()]
    summary = kv_table(
        {
            "file": evidence.code_file,
            "rows in the file": len(frame),
            "codes described": len(described),
            "distinct descriptions": len(set(described.values())),
            "mean description length (chars)": round(sum(lengths) / len(lengths), 1)
            if lengths
            else 0.0,
            "parsed event rows carrying a described code": (
                f"{covered:,} of {total:,} ({covered / total * 100:.1f}%)" if total else "n/a"
            ),
            "distinct codes in the parsed tables that it describes": (
                f"{len(set(described) & set(codes))} of {len(codes)}"
            ),
        }
    )
    columns = [str(name) for name in frame.columns]
    code_column = pick_column(columns, ("code",))
    listing = table(
        [*columns, "rows in parsed tables"],
        [
            (
                *(truncate(str(value), 60) for value in record),
                codes.get(normalise_code(record[columns.index(code_column)]), 0)
                if code_column is not None
                else "-",
            )
            for record in frame.itertuples(index=False, name=None)
        ],
    )
    return section(
        "Provider code descriptions",
        summary + "\n**The file as published**\n\n" + listing,
    )


def build_report(
    source: str,
    spec: SourceSpec,
    raw_dir: Path,
    members: list[RawMember],
    evidence: EventEvidence,
    sniffs: dict[str, list[str]],
    max_members: int,
    repo_root: Path,
    classification: str,
) -> str:
    """Render the raw inventory report.

    Args:
        source: Source identifier.
        spec: Source specification from the download config.
        raw_dir: Directory the archives were read from.
        members: Discovered members.
        evidence: What was read from the event members.
        sniffs: Header samples, keyed by member label.
        max_members: Cap applied to the per-member listing.
        repo_root: Repository root, used to record the commit.
        classification: Where the adapter's member classification comes from.

    Returns:
        A Markdown document.
    """
    profiles = evidence.profiles
    verdict, rationale = free_text_verdict(profiles, members_staged=len(members))
    archives = sorted({member.archive for member in members})
    by_kind: Counter[str] = Counter(member.kind for member in members)
    codes = pooled_codes(profiles)
    share_alike = is_share_alike(spec.license)
    licence_note = (
        f"Quoted messages are the provider's text under {spec.license} ({spec.attribution}). "
        "They are quoted because the measurement needs them; this report otherwise "
        "reproduces none of the record: header samples are cut to their first line and "
        "per-table message listings are omitted."
        if share_alike
        else None
    )

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
                "member classification": classification,
                "event members parsed": (
                    f"{len(profiles)} of {evidence.candidates} (caps: {evidence.cap} members, "
                    f"{MAX_PARSE_BYTES / 1e6:.1f} MB and {MAX_PARSE_ROWS:,} rows per member)"
                ),
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

    if profiles:
        parts.append(text_section(measure_text(profiles), licence_note))
    parts.append(codes_section(evidence, codes))
    parts.append(code_descriptions_section(evidence, codes))

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
        with_top = [profile for profile in profiles if profile["message_counts"]]
        if share_alike:
            if with_top:
                parts.append(
                    "\n_Per-table message listings are omitted for this share-alike record; "
                    "the pooled top 20 above is the only text quoted._\n"
                )
        else:
            for profile in with_top[:MAX_TOP_SECTIONS]:
                parts.append(
                    section(
                        f"Top messages: {truncate(str(profile['member']), 60)}",
                        top_values_table(profile["message_counts"], n=20, label="message"),
                        level=3,
                    )
                )
            if len(with_top) > MAX_TOP_SECTIONS:
                parts.append(
                    f"\n_Per-table top messages are shown for the first {MAX_TOP_SECTIONS} of "
                    f"{len(with_top)} tables with messages; the pooled measurements above "
                    "cover all of them._\n"
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

    if evidence.skipped:
        parts.append(
            section(
                "Event members not parsed",
                table(
                    ["member", "uncompressed (MB)", "reason"],
                    [
                        (truncate(member.label, 80), round(member.size / 1e6, 1), reason)
                        for member, reason in evidence.skipped
                    ],
                ),
            )
        )

    if sniffs:
        body = []
        if share_alike:
            body.append("_Share-alike record: each sample is cut to its first line._\n")
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
    max_event_members: int = MAX_EVENT_MEMBERS,
) -> Path:
    """Inventory one source's staged archives and write its report.

    Args:
        source: Source identifier.
        spec: Source specification from the download config.
        paths: Resolved project paths.
        max_members: Cap on the member listing in the report.
        max_event_members: Cap on the number of event tables parsed.

    Returns:
        The path of the written report.
    """
    adapter = get_adapter(source, paths.configs_dir)
    raw_dir = paths.source_dir("raw", "telemetry", source)
    members = inventory_members(adapter, raw_dir)
    evidence = collect_event_evidence(adapter, members, max_event_members)
    sample_lines = 1 if is_share_alike(spec.license) else 30

    report = build_report(
        source=source,
        spec=spec,
        raw_dir=raw_dir,
        members=members,
        evidence=evidence,
        sniffs=sample_headers(members, n_lines=sample_lines),
        max_members=max_members,
        repo_root=paths.repo_root,
        classification=adapter.CLASSIFICATION_SOURCE,
    )
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d")
    destination = paths.data_reports_dir / f"raw_inventory_{source}_{stamp}.md"
    destination.write_text(report, encoding="utf-8")
    logger.info("%s: wrote %s", source, destination)
    return destination
