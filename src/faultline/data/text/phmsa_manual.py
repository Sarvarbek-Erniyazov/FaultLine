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
a narrative-shaped hint (``narrative``, ``description``, ``summary``, ``comment``,
``remark``, ``additional_info``, ``detail``) **and** whose distinct-value ratio exceeds
:data:`DISTINCT_RATIO_THRESHOLD` is one candidate; any string-typed column whose values
average longer than :data:`MEAN_LENGTH_NARRATIVE_THRESHOLD` characters **and** whose
distinct-value ratio exceeds :data:`DISTINCT_RATIO_THRESHOLD` is another, independent of
its name. Both are reported, because a name-only search would miss a narrative field
PHMSA happens to call something else, and a length-only search would miss a short but
genuinely free-text field. The ratio guard is the OE-417 lesson (ADR-0016): a long coded
field -- a closed set of category sentences repeated across rows -- passes on mean length
alone, and is a code book, not narrative.

*Amended 2026-09-16.* The guard now applies to the name branch too. As first written the
name branch admitted any matching column whatever its ratio, which let closed code sets
named ``*_DETAILS`` through (``CAUSE_DETAILS``: distinct ratio 0.007) --
``docs/INSTRUMENT_AUDIT.md``, entry 4.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

from faultline.data.common.manifest import (
    FileRecord,
    SourceManifest,
    hash_file,
    manifest_path,
    read_manifest,
    write_manifest,
)
from faultline.data.common.report import kv_table, section, table
from faultline.download.nrc_text import FetchedDocument, NrcTextClient, SocrataAttachmentsSpec
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths

logger = get_logger(__name__)

SOURCE = "phmsa"
RETRIEVAL_METHOD = "manual, author, browser"

#: DOT's Socrata attachment route for the ``27nc-rsge`` incident-data record
#: (ADR-0016, 2026-09-16 correction): not disallowed by
#: ``data.transportation.gov/robots.txt``, fetched through the robots-gated client.
SOCRATA_ATTACHMENT_URL = (
    "https://data.transportation.gov/api/views/{view}/files/{asset_id}"
    "?download=true&filename={filename}"
)

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

#: ...and whose distinct non-null values exceed this share of its non-null values.
#: Pre-registered in ADR-0016's 2026-09-16 PHMSA decision rule, before any PHMSA file
#: was read.
DISTINCT_RATIO_THRESHOLD = 0.5

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


@dataclass(frozen=True)
class ColumnVerdict:
    """Why one column qualified as free text, with the numbers the rule reads.

    Attributes:
        column: Column name.
        test: ``"name"`` (a narrative hint in the name) or ``"length+ratio"``.
        non_null: Non-null values.
        mean_length: Mean character length of the non-null values.
        distinct_ratio: Distinct non-null values over non-null values.
        tokens: Whitespace-delimited tokens across the non-null values.
    """

    column: str
    test: str
    non_null: int
    mean_length: float
    distinct_ratio: float
    tokens: int


@dataclass
class MemberProfile:
    """One archive member's profile.

    Attributes:
        name: Member path inside the archive.
        classification: Best-effort pipeline-type / form-generation guess.
        rows: Rows read.
        columns: Column names as read.
        narrative_columns: Columns flagged as narrative, by name hint, or by mean length
            together with distinct-value ratio.
        narrative_tokens: Whitespace-delimited tokens summed across narrative columns.
        samples: A few sample values from the narrative column holding the most tokens.
        verdicts: Per qualifying column, the numbers behind its qualification.
        encoding: Text encoding the member decoded under (``""`` for Excel).
        delimiter: Field delimiter used (``""`` for Excel).
        physical_rows: Data lines in the member (non-blank lines after the header), so
            rows a parser skipped are visible beside ``rows`` (``-1`` for Excel).
    """

    name: str
    classification: str
    rows: int
    columns: list[str]
    narrative_columns: list[str]
    narrative_tokens: int
    samples: list[str] = field(default_factory=list)
    verdicts: list[ColumnVerdict] = field(default_factory=list)
    encoding: str = ""
    delimiter: str = ""
    physical_rows: int = -1


class ArchiveParseError(ValueError):
    """The archive, or a tabular member inside it, could not be read.

    Raised rather than logged: a file that does not parse is not verified data, and the
    manifest record that says ``verified=True`` must never be written for one (an HTML
    error page saved under a ``.zip`` name was the concrete case).
    """


#: Encodings tried, in order, for a delimited-text member. PHMSA's 2010-onward
#: hazardous-liquid flat file is Windows-1252 (a section sign as byte 0xA7, curly
#: quotes as 0x93/0x94), not UTF-8.
TEXT_ENCODINGS: tuple[str, ...] = ("utf-8", "cp1252")


@dataclass(frozen=True)
class _ReadMember:
    frame: pd.DataFrame
    encoding: str
    delimiter: str
    physical_rows: int


def _decode(name: str, raw: bytes) -> tuple[str, str]:
    """Decode under the first of :data:`TEXT_ENCODINGS` that succeeds."""
    for encoding in TEXT_ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ArchiveParseError(f"{name}: not decodable as any of {TEXT_ENCODINGS}")


def _read_member(name: str, raw: bytes) -> _ReadMember | None:
    """Read one archive member as a table, or ``None`` if it is not a tabular member.

    Delimited text is decoded under the first of :data:`TEXT_ENCODINGS` that succeeds,
    and split on a tab when the header line holds more tabs than commas (PHMSA's flat
    files are tab-delimited despite a ``.txt`` suffix). A tab-delimited file is read
    with quoting off: a free-text field holding a lone ``"`` would otherwise swallow
    the following lines into one cell.

    Args:
        name: Member path inside the archive.
        raw: The member's raw bytes.

    Returns:
        The parsed table with how it was read, or ``None`` for a non-tabular suffix.

    Raises:
        ArchiveParseError: If a member with a tabular suffix does not parse.
    """
    suffix = Path(name).suffix.lower()
    if suffix not in TABULAR_SUFFIXES:
        return None
    if suffix not in (".csv", ".txt"):
        try:
            return _ReadMember(pd.read_excel(io.BytesIO(raw)), "", "", -1)
        except ValueError as exc:
            raise ArchiveParseError(f"{name}: could not parse as tabular data: {exc}") from exc
    text, encoding = _decode(name, raw)
    lines = text.splitlines()
    header = lines[0] if lines else ""
    delimiter = "\t" if header.count("\t") > header.count(",") else ","
    try:
        frame = pd.read_csv(
            io.StringIO(text),
            sep=delimiter,
            low_memory=False,
            on_bad_lines="skip",
            quoting=csv.QUOTE_NONE if delimiter == "\t" else csv.QUOTE_MINIMAL,
        )
    except (ValueError, pd.errors.ParserError) as exc:
        raise ArchiveParseError(f"{name}: could not parse as tabular data: {exc}") from exc
    physical = sum(1 for line in lines[1:] if line.strip())
    return _ReadMember(frame, encoding, delimiter, physical)


def profile_member(name: str, raw: bytes) -> MemberProfile | None:
    """Profile one archive member: rows, columns, and any narrative content.

    Args:
        name: Member path inside the archive.
        raw: The member's raw bytes.

    Returns:
        The profile, or ``None`` if the member's suffix is not tabular.

    Raises:
        ArchiveParseError: If a member with a tabular suffix does not parse.
    """
    read = _read_member(name, raw)
    if read is None:
        return None
    frame = read.frame
    columns = [str(c) for c in frame.columns]
    narrative_columns: list[str] = []
    verdicts: list[ColumnVerdict] = []
    for column in columns:
        values = frame[column].dropna().astype(str)
        mean_length = float(values.str.len().mean()) if len(values) else 0.0
        ratio = values.nunique() / len(values) if len(values) else 0.0
        textual = pd.api.types.is_string_dtype(frame[column]) or pd.api.types.is_object_dtype(
            frame[column]
        )
        test = ""
        if (
            any(hint in column.lower() for hint in NARRATIVE_HINTS)
            and ratio > DISTINCT_RATIO_THRESHOLD
        ):
            test = "name"
        elif (
            textual
            and mean_length > MEAN_LENGTH_NARRATIVE_THRESHOLD
            and ratio > DISTINCT_RATIO_THRESHOLD
        ):
            test = "length+ratio"
        if test:
            narrative_columns.append(column)
            verdicts.append(
                ColumnVerdict(
                    column=column,
                    test=test,
                    non_null=len(values),
                    mean_length=mean_length,
                    distinct_ratio=ratio,
                    tokens=_whitespace_tokens(frame[column]),
                )
            )
    tokens = sum(verdict.tokens for verdict in verdicts)
    samples: list[str] = []
    if narrative_columns:
        richest = max(verdicts, key=lambda verdict: verdict.tokens).column
        values = frame[richest].dropna().astype(str)
        samples = values.head(3).tolist()
    return MemberProfile(
        name=name,
        classification=classify_member(name),
        rows=len(frame),
        columns=columns,
        narrative_columns=narrative_columns,
        narrative_tokens=tokens,
        samples=samples,
        verdicts=verdicts,
        encoding=read.encoding,
        delimiter={"\t": "tab", ",": "comma"}.get(read.delimiter, ""),
        physical_rows=read.physical_rows,
    )


def inspect_archive(zip_path: Path) -> list[MemberProfile]:
    """Profile every tabular member of the archive, read-only.

    Args:
        zip_path: The retrieved zip file.

    Returns:
        One profile per tabular member, in archive order.

    Raises:
        ArchiveParseError: If the file is not a readable zip, a tabular member does not
            parse, or no member is tabular at all.
    """
    profiles = []
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                raw = archive.read(info.filename)
                profile = profile_member(info.filename, raw)
                if profile is not None:
                    profiles.append(profile)
                else:
                    logger.info("%s: not a tabular member; skipped", info.filename)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as exc:
        raise ArchiveParseError(f"{zip_path}: not a readable zip archive: {exc}") from exc
    if not profiles:
        raise ArchiveParseError(f"{zip_path}: no tabular member ({', '.join(TABULAR_SUFFIXES)})")
    return profiles


def fetch_socrata_attachment(
    client: NrcTextClient, paths: ProjectPaths, view: str, asset_id: str, filename: str
) -> tuple[Path, str]:
    """Download one Socrata attachment through the robots-gated client.

    Args:
        client: The paced, robots.txt-gated client.
        paths: Resolved project paths.
        view: The Socrata view id (``27nc-rsge``).
        asset_id: The attachment's ``assetId`` from the view's ``metadata.attachments``.
        filename: The attachment's ``filename``, as the file is saved.

    Returns:
        The saved file and the URL it was fetched from.

    Raises:
        requests.HTTPError: If the client refused the URL (robots.txt) or the server
            did not answer ``200``; nothing is written.
    """
    url = SOCRATA_ATTACHMENT_URL.format(view=view, asset_id=asset_id, filename=quote(filename))
    response = client.get(url, timeout=300)
    if response is None:
        raise requests.HTTPError(f"{url}: refused by robots.txt or not 200; nothing written")
    destination = paths.stage_dir("raw", "text") / SOURCE / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    return destination, url


def record_manual_retrieval(
    paths: ProjectPaths,
    zip_path: Path,
    url: str,
    retrieved_at: datetime,
    license: str = "public domain (17 U.S.C. 105); usa.gov public-domain label",
    retrieval_method: str | None = RETRIEVAL_METHOD,
) -> SourceManifest:
    """Hash a retrieved, already-parsed file and record it in the source's manifest.

    Args:
        paths: Resolved project paths.
        zip_path: The retrieved file.
        url: The URL it was downloaded from.
        retrieved_at: When it was retrieved (for a manual download, the human's own
            record, not this process's clock).
        license: Licence statement for the manifest.
        retrieval_method: ``"manual, author, browser"`` for a human download;
            ``None`` for this project's own robots-gated client, per
            :class:`~faultline.data.common.manifest.FileRecord`.

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
            retrieval_method=retrieval_method,
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
            "retrieval method": record.retrieval_method or "automated, robots.txt-gated client",
            "retrieved (recorded)": record.retrieved_at.isoformat(),
            "licence": record.license,
        }
    )
    member_rows = [
        (
            p.name,
            p.classification,
            f"{p.encoding or '-'} / {p.delimiter or '-'}",
            p.rows,
            p.physical_rows if p.physical_rows >= 0 else "-",
            len(p.columns),
            ", ".join(p.narrative_columns) or "none",
        )
        for p in profiles
    ]
    members_section = section(
        "Members, by pipeline type and form generation (best-effort, from filenames)",
        table(
            [
                "member",
                "classification (guessed)",
                "encoding / delimiter",
                "rows read",
                "data lines",
                "columns",
                "narrative column(s)",
            ],
            member_rows,
        ),
    )
    verdict_rows = [
        (
            p.name,
            v.column,
            v.test,
            v.non_null,
            f"{v.mean_length:.1f}",
            f"{v.distinct_ratio:.3f}",
            v.tokens,
        )
        for p in profiles
        for v in sorted(p.verdicts, key=lambda v: -v.tokens)
    ]
    verdicts_section = section(
        "Qualifying columns: which free-text test each passed, and its numbers",
        table(
            ["member", "column", "test", "non-null", "mean chars", "distinct ratio", "tokens"],
            verdict_rows,
        )
        if verdict_rows
        else "_(no column passes either test)_\n",
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
        "# PHMSA incident file: read-only inspection\n\n"
        + header
        + "\n"
        + members_section
        + verdicts_section
        + totals_section
        + samples_section
    )


def unquote_field(value: str) -> str:
    """Undo CSV-style quoting a tab-delimited export left on a free-text field.

    PHMSA's flat files are read with quoting off (see :func:`_read_member`), so a
    narrative the exporter quoted arrives as ``"..."`` with inner quotes doubled.

    Args:
        value: The raw cell.

    Returns:
        The cell with one enclosing quote pair removed and ``""`` restored to ``"``,
        or unchanged when it is not enclosed in quotes.
    """
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('""', '"')
    return value


def _archive_is_recorded(paths: ProjectPaths, source: str, path: Path) -> bool:
    """Whether a zip on disk matches the hash its manifest records."""
    manifest = read_manifest(manifest_path(paths.manifests_dir, source))
    record = manifest.by_filename().get(path.name) if manifest else None
    return record is not None and path.is_file() and record.sha256 == hash_file(path, "sha256")


def _narrative_tables(archive: Path, spec: SocrataAttachmentsSpec) -> list[pd.DataFrame]:
    """Every tabular member of an archive, checked for the configured columns.

    Args:
        archive: The zip file.
        spec: The source specification naming the id and narrative columns.

    Returns:
        One frame per tabular member.

    Raises:
        ArchiveParseError: If the archive does not parse, holds no tabular member, or a
            member lacks the id or narrative column.
    """
    inspect_archive(archive)  # the same checks `inspect phmsa` applies
    frames = []
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            read = _read_member(info.filename, bundle.read(info.filename))
            if read is None:
                continue
            missing = {spec.narrative_column, spec.id_column} - set(map(str, read.frame.columns))
            if missing:
                raise ArchiveParseError(f"{info.filename}: missing columns {sorted(missing)}")
            frames.append(read.frame)
    return frames


def fetch_incident_narratives(
    client: NrcTextClient, spec: SocrataAttachmentsSpec, paths: ProjectPaths
) -> Iterator[FetchedDocument]:
    """Fetch, verify and record each attachment, then yield one document per narrative.

    An archive already on disk whose hash matches its manifest record is reused; any
    other is fetched through the robots-gated client. Every archive is parsed before it
    is recorded (``verified=True`` is only written for a file that parsed), and it is
    recorded under ``spec.archive_source`` with ``retrieval_method`` left ``None``, the
    manifest's marker for this project's own automated client.

    Args:
        client: The paced, robots.txt-gated client.
        spec: The source specification.
        paths: Resolved project paths.

    Yields:
        One document per row with a non-empty narrative, id
        ``{pipeline_type}_{report number}``.

    Raises:
        ArchiveParseError: If an archive does not parse, or lacks the configured columns.
    """
    for attachment in spec.attachments:
        archive = paths.stage_dir("raw", "text") / spec.archive_source / attachment.filename
        url = SOCRATA_ATTACHMENT_URL.format(
            view=spec.view, asset_id=attachment.asset_id, filename=quote(attachment.filename)
        )
        fetched = not _archive_is_recorded(paths, spec.archive_source, archive)
        if fetched:
            archive, url = fetch_socrata_attachment(
                client, paths, spec.view, attachment.asset_id, attachment.filename
            )
        frames = _narrative_tables(archive, spec)  # parses every member; raises before recording
        if fetched:
            record_manual_retrieval(
                paths,
                archive,
                url=url,
                retrieved_at=datetime.now(tz=UTC),
                license=spec.license,
                retrieval_method=None,
            )
        count = 0
        for frame in frames:
            for report, narrative in zip(
                frame[spec.id_column], frame[spec.narrative_column], strict=True
            ):
                if pd.isna(narrative) or pd.isna(report):
                    continue
                text = unquote_field(str(narrative)).strip()
                if not text:
                    continue
                count += 1
                yield FetchedDocument(
                    doc_id=f"{attachment.pipeline_type}_{report}",
                    url=f"{url}#{spec.id_column}={report}",
                    text=text,
                )
        logger.info("%s: %d narratives", attachment.filename, count)
