"""Read-only inspection of the manually retrieved PHMSA flagged-incidents file.

ADR-0016: PHMSA's automated route is blocked from every host and every client tried
(the project's own downloader, and separately Claude's `WebFetch`), but the licence is
confirmed public domain and the manual route is open -- a human downloading the file
in a browser is ordinary provenance, not a workaround, distinct from an automated
client presenting itself as something it is not. This module does the part that
follows once that download exists: hash the file, record it in the manifest with its
retrieval method stated rather than left to be inferred from the silence every
automated record's absence of that field would otherwise be, and profile what is
inside it -- read-only, no pipeline stage run against it yet, per the checkpoint that
asked for this.

**Classification of what each member file covers (pipeline type, form generation) is a
best-effort read of PHMSA's own filenames, not a guarantee.** PHMSA split its incident
report schema at a 2010 form-revision boundary, and different pipeline types
(distribution, transmission, gathering, hazardous liquid, LNG) are typically published
as separate files; the exact names cannot be predicted without the archive in hand, so
this reports both the raw member name and the classification guessed from it, so a
wrong guess is visible instead of silently trusted.

**Narrative columns are found two ways, not one guess.** A column whose name contains
a narrative-shaped hint (``narrative``, ``description``, ``summary``, ``cause``,
``comment``, ``remark``, ``additional_info``, ``detail``) is one candidate; any
string-typed column whose values average longer than
:data:`MEAN_LENGTH_NARRATIVE_THRESHOLD` characters is another, independent of its
name. Both are reported, because a name-only search would miss a narrative field
PHMSA happens to call something else, and a length-only search would miss a short but
genuinely free-text field.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from faultline.data.common.manifest import (
    FileRecord,
    SourceManifest,
    hash_file,
    manifest_path,
    read_manifest,
    write_manifest,
)
from faultline.data.common.report import kv_table, section, table
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths

logger = get_logger(__name__)

SOURCE = "phmsa"
RETRIEVAL_METHOD = "manual, author, browser"

#: Column-name substrings that plausibly hold free-text narrative content, most
#: specific first. Deliberately excludes "cause": PHMSA's incident data typically
#: carries a short coded "CAUSE" category (CORROSION, EXCAVATION DAMAGE, ...), not a
#: narrative -- a genuinely long cause-description field is still caught by the
#: length-based check below, on its own values rather than a guess from its name.
NARRATIVE_HINTS: tuple[str, ...] = (
    "narrative",
    "description",
    "summary",
    "comment",
    "remark",
    "additional_info",
    "detail",
)

#: A string column whose values average longer than this many characters is a
#: narrative candidate regardless of its name.
MEAN_LENGTH_NARRATIVE_THRESHOLD = 80

#: Member suffixes this module knows how to read as tabular data.
TABULAR_SUFFIXES: tuple[str, ...] = (".csv", ".txt", ".xlsx", ".xls")

#: Filename substrings this module's best-effort pipeline-type guess checks for, in
#: order; the first match wins. Not exhaustive, and not trusted blindly -- the raw
#: member name is always reported beside the guess.
PIPELINE_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    ("distribution", "gas distribution"),
    ("transmission", "gas transmission"),
    ("gathering", "gas gathering"),
    ("hazardous_liquid", "hazardous liquid"),
    ("hazardousliquid", "hazardous liquid"),
    ("liquid", "hazardous liquid"),
    ("lng", "LNG"),
    ("ungs", "underground gas storage"),
    ("storage", "underground gas storage"),
)

#: Filename substrings suggesting which incident-report form generation a member
#: covers; PHMSA revised its reporting form in 2010.
FORM_GENERATION_HINTS: tuple[tuple[str, str], ...] = (
    ("2010", "2010-present form"),
    ("present", "2010-present form"),
    ("1970", "pre-2010 form"),
    ("1986", "pre-2010 form"),
    ("1990", "pre-2010 form"),
    ("2000", "pre-2010 form"),
    ("2002", "pre-2010 form"),
    ("2003", "pre-2010 form"),
)


def classify_member(name: str) -> str:
    """Best-effort pipeline-type / form-generation label from a member's filename.

    Args:
        name: The member's path inside the archive.

    Returns:
        ``"<pipeline type> / <form generation>"``, either half ``"unknown"`` when no
        hint matches. Always reported beside the raw name, never in place of it.
    """
    lower = name.lower()
    pipeline_type = next((label for key, label in PIPELINE_TYPE_HINTS if key in lower), "unknown")
    generation = next((label for key, label in FORM_GENERATION_HINTS if key in lower), "unknown")
    return f"{pipeline_type} / {generation}"


def _whitespace_tokens(series: pd.Series) -> int:
    """Total whitespace-delimited tokens across a column's non-null values."""
    text = series.dropna().astype(str)
    if text.empty:
        return 0
    return int(text.map(lambda value: len(value.split())).sum())


@dataclass
class MemberProfile:
    """One archive member's profile.

    Attributes:
        name: Member path inside the archive.
        classification: Best-effort pipeline-type / form-generation guess.
        rows: Rows read.
        columns: Column names as read.
        narrative_columns: Columns flagged as narrative, by name hint or mean length.
        narrative_tokens: Whitespace-delimited tokens summed across narrative columns.
        samples: A few sample values from the first narrative column found, verbatim.
    """

    name: str
    classification: str
    rows: int
    columns: list[str]
    narrative_columns: list[str]
    narrative_tokens: int
    samples: list[str] = field(default_factory=list)


def _read_member(name: str, raw: bytes) -> pd.DataFrame | None:
    """Read one archive member as a table, or ``None`` if it is not one.

    Args:
        name: Member path inside the archive.
        raw: The member's raw bytes.

    Returns:
        The parsed table, or ``None`` for an unreadable or non-tabular member.
    """
    suffix = Path(name).suffix.lower()
    if suffix not in TABULAR_SUFFIXES:
        return None
    try:
        if suffix in (".csv", ".txt"):
            return pd.read_csv(io.BytesIO(raw), low_memory=False, on_bad_lines="skip")
        return pd.read_excel(io.BytesIO(raw))
    except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as exc:
        logger.warning("%s: could not parse as tabular data: %s", name, exc)
        return None


def profile_member(name: str, raw: bytes) -> MemberProfile | None:
    """Profile one archive member: rows, columns, and any narrative content.

    Args:
        name: Member path inside the archive.
        raw: The member's raw bytes.

    Returns:
        The profile, or ``None`` if the member is not readable tabular data.
    """
    frame = _read_member(name, raw)
    if frame is None:
        return None
    columns = [str(c) for c in frame.columns]
    narrative_columns: list[str] = []
    for column in columns:
        lower = column.lower()
        if any(hint in lower for hint in NARRATIVE_HINTS):
            narrative_columns.append(column)
            continue
        if pd.api.types.is_string_dtype(frame[column]) or pd.api.types.is_object_dtype(
            frame[column]
        ):
            values = frame[column].dropna().astype(str)
            if len(values) and values.str.len().mean() > MEAN_LENGTH_NARRATIVE_THRESHOLD:
                narrative_columns.append(column)
    tokens = sum(_whitespace_tokens(frame[column]) for column in narrative_columns)
    samples: list[str] = []
    if narrative_columns:
        values = frame[narrative_columns[0]].dropna().astype(str)
        samples = values.head(3).tolist()
    return MemberProfile(
        name=name,
        classification=classify_member(name),
        rows=len(frame),
        columns=columns,
        narrative_columns=narrative_columns,
        narrative_tokens=tokens,
        samples=samples,
    )


def inspect_archive(zip_path: Path) -> list[MemberProfile]:
    """Profile every tabular member of the archive, read-only.

    Args:
        zip_path: The retrieved zip file.

    Returns:
        One profile per readable tabular member, in archive order.
    """
    profiles = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            raw = archive.read(info.filename)
            profile = profile_member(info.filename, raw)
            if profile is not None:
                profiles.append(profile)
            else:
                logger.info(
                    "%s: not read as tabular data (unsupported or unparseable)", info.filename
                )
    return profiles


def record_manual_retrieval(
    paths: ProjectPaths,
    zip_path: Path,
    url: str,
    retrieved_at: datetime,
    license: str = "public domain (17 U.S.C. 105); usa.gov public-domain label",
) -> SourceManifest:
    """Hash the manually retrieved file and record it in the source's manifest.

    Args:
        paths: Resolved project paths.
        zip_path: The retrieved file.
        url: The URL it was downloaded from.
        retrieved_at: When the human retrieved it (their own record, not this
            process's clock -- a manual download did not happen when this function
            ran).
        license: Licence statement for the manifest.

    Returns:
        The updated manifest.
    """
    digest = hash_file(zip_path, "sha256")
    path = manifest_path(paths.manifests_dir, SOURCE)
    manifest = read_manifest(path) or SourceManifest(
        source=SOURCE,
        provider="Pipeline and Hazardous Materials Safety Administration",
        license=license,
    )
    manifest.upsert(
        FileRecord(
            filename=zip_path.name,
            relative_path=f"raw/text/{SOURCE}/{zip_path.name}",
            size_bytes=zip_path.stat().st_size,
            sha256=digest,
            url=url,
            license=license,
            retrieved_at=retrieved_at,
            verified=True,
            retrieval_method=RETRIEVAL_METHOD,
        )
    )
    manifest.generated_at = datetime.now(tz=UTC)
    write_manifest(path, manifest)
    return manifest


def render_report(zip_path: Path, manifest: SourceManifest, profiles: list[MemberProfile]) -> str:
    """Render the read-only inspection report.

    Args:
        zip_path: The retrieved file.
        manifest: Its manifest entry (for the recorded hash and retrieval method).
        profiles: Every member's profile.

    Returns:
        The report, as Markdown.
    """
    record = manifest.by_filename()[zip_path.name]
    header = kv_table(
        {
            "file": zip_path.name,
            "size (MB)": f"{record.size_bytes / 1e6:.1f}",
            "sha256": record.sha256 or "",
            "url": record.url,
            "retrieval method": record.retrieval_method or "",
            "retrieved (recorded)": record.retrieved_at.isoformat(),
            "licence": record.license,
        }
    )
    member_rows = [
        (p.name, p.classification, p.rows, len(p.columns), ", ".join(p.narrative_columns) or "none")
        for p in profiles
    ]
    members_section = section(
        "Members, by pipeline type and form generation (best-effort, from filenames)",
        table(
            ["member", "classification (guessed)", "rows", "columns", "narrative column(s)"],
            member_rows,
        ),
    )
    total_rows = sum(p.rows for p in profiles)
    total_tokens = sum(p.narrative_tokens for p in profiles)
    narrative_members = [p for p in profiles if p.narrative_columns]
    totals_section = section(
        "Totals",
        kv_table(
            {
                "members read as tabular data": len(profiles),
                "members with a narrative column found": len(narrative_members),
                "total rows": total_rows,
                "total whitespace-token estimate, all narrative columns": total_tokens,
            }
        ),
    )
    sample_rows = []
    for p in profiles:
        for value in p.samples:
            sample_rows.append((p.name, value[:300]))
    samples_section = section(
        "Sampled narrative values, verbatim (truncated to 300 characters)",
        table(["member", "sample"], sample_rows)
        if sample_rows
        else "_(no narrative column found)_\n",
    )
    return (
        "# PHMSA flagged-incidents file: read-only inspection\n\n"
        + header
        + "\n"
        + members_section
        + totals_section
        + samples_section
    )
