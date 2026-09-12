"""The source adapter contract.

An adapter is the only place that knows a provider's file names, column vocabulary
and quirks. Everything downstream sees the canonical schema, so supporting a fifth
site is a new adapter plus a channel map -- not a change to the pipeline.

Adapters read **inside** archives. A staged tier-1 corpus is about 17 GB compressed
and many times that extracted -- the Kelmarsh SCADA members alone inflate from 3.7 GB
to 41.5 GB -- and extracting buys nothing, since ``zipfile`` gives pandas a perfectly
good file object.

At M0 ``discover`` is implemented for every source and the loaders are implemented
only where the member format has been confirmed by inspection. An unconfirmed
loader raises rather than guessing at a column layout.

An adapter is also the only place a **unit conversion** happens, because a unit is part
of what a provider publishes. CARE's generator speed is divided by 60/(2*pi) to reach rpm
from rad/s, and since M1c every source's power is divided by the nameplate rating of its
machine to reach per unit of rated power (:meth:`BaseAdapter.to_canonical_units`,
ADR-0013). Both divisors are declared in configuration and cited: a nameplate is a
published fact about a machine, never a quantity fitted from the data.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Collection, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, ClassVar, Literal, Protocol, runtime_checkable

import pandas as pd
import yaml

from faultline.data.telemetry.collapse import CollapseStats
from faultline.download.zenodo import load_sources_config
from faultline.logging_utils import get_logger

logger = get_logger(__name__)

#: ``downtime_series`` is a regular per-turbine series of downtime per step -- a label
#: source, not an event log and not telemetry (Hill of Towie's ShutdownDuration).
MemberKind = Literal[
    "scada_10min", "status_events", "alarm_log", "downtime_series", "metadata", "other"
]


@dataclass(frozen=True)
class FileAccount:
    """Row accounting for one source file, as the ingest report prints it.

    Attributes:
        member: Member label.
        turbine: Turbine the file belongs to, or a station count where one file holds
            every turbine.
        stats: The repeated-label arithmetic for the file.
    """

    member: str
    turbine: str
    stats: CollapseStats


#: The canonical power channel, held in per unit of rated power (ADR-0013). Named here
#: rather than imported from the schema so that the adapter layer keeps one import edge.
POWER_CHANNEL = "power_pu"

#: Archive extensions treated as containers.
ARCHIVE_SUFFIXES: frozenset[str] = frozenset({".zip"})

#: Loose file extensions worth listing as members in their own right.
LOOSE_SUFFIXES: frozenset[str] = frozenset({".csv", ".xlsx", ".xls", ".txt", ".md", ".json"})


@dataclass(frozen=True)
class RawMember:
    """One readable unit of staged data.

    Attributes:
        archive: The staged file: a zip container, or the data file itself.
        name: Member path inside the archive; empty for a loose file.
        kind: Classification used to route the member to a loader.
        size: Uncompressed size in bytes.
        compressed_size: Stored size in bytes; equal to ``size`` for loose files.
        in_archive: Whether ``name`` refers to a member inside ``archive``.
    """

    archive: Path
    name: str
    kind: MemberKind
    size: int
    compressed_size: int
    in_archive: bool

    @property
    def label(self) -> str:
        """Human-readable identifier used in reports."""
        return f"{self.archive.name}::{self.name}" if self.in_archive else self.archive.name


@runtime_checkable
class SourceAdapter(Protocol):
    """What every source adapter must provide."""

    source_id: str
    site_name: str

    def discover(self, raw_dir: Path) -> list[RawMember]:
        """List and classify every readable member staged for this source.

        Args:
            raw_dir: Directory holding the staged archives.

        Returns:
            The classified members.
        """
        ...

    def turbine_id(self, member: RawMember) -> str:
        """Identify the turbine a member belongs to.

        Args:
            member: Member to identify.

        Returns:
            The turbine identifier.
        """
        ...

    def load_scada(self, member: RawMember) -> pd.DataFrame:
        """Read one SCADA member into the canonical wide schema.

        Args:
            member: Member classified as SCADA.

        Returns:
            A canonical wide table.
        """
        ...

    def load_events(self, member: RawMember) -> pd.DataFrame | None:
        """Read one status, alarm or event member into the canonical events schema.

        Args:
            member: Member classified as an event table.

        Returns:
            A canonical events table, or ``None`` when the member holds no events.
        """
        ...


def load_channel_map(path: Path) -> dict[str, str]:
    """Load a canonical-to-source channel mapping.

    Args:
        path: Path to ``configs/data/channel_map/<source>.yaml``.

    Returns:
        A mapping from canonical channel name to source column name, with
        unresolved (``TODO``) entries omitted.
    """
    if not path.is_file():
        logger.warning("channel map not found: %s", path)
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    channels = payload.get("channels", {}) or {}
    resolved: dict[str, str] = {}
    for canonical, source_column in channels.items():
        # A per-farm map (CARE) keeps its columns under `farms:`, not here; a nested
        # value is never a column name, and stringifying one would invent a column.
        if source_column is None or isinstance(source_column, dict):
            continue
        text = str(source_column)
        if text.startswith("TODO"):
            continue
        resolved[str(canonical)] = text
    return resolved


def load_rated_power_kw(configs_dir: Path, source: str) -> float | None:
    """Load a source's nameplate rated power per turbine, in kW.

    Args:
        configs_dir: The repository ``configs`` directory.
        source: Source identifier.

    Returns:
        The rating in kW, or ``None`` where the specification declares none -- which
        is how a source that publishes power already per unit says so (ADR-0013).
    """
    path = configs_dir / "data" / "sources_telemetry.yaml"
    if not path.is_file():
        logger.warning("source specification not found: %s", path)
        return None
    spec = load_sources_config(path).sources.get(source)
    rated = spec.rated_power_kw if spec is not None else None
    return float(rated.value) if rated is not None else None


def load_farm_blocks(path: Path) -> dict[str, dict[str, Any]]:
    """Load the per-farm blocks of a channel map that maps each farm separately.

    Args:
        path: Path to ``configs/data/channel_map/<source>.yaml``.

    Returns:
        Each farm's block, keyed by farm id; empty for a flat map or a missing file.
    """
    if not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    farms = payload.get("farms") or {}
    return {str(farm): dict(block or {}) for farm, block in farms.items()}


def resolved_columns(block: dict[str, Any]) -> dict[str, str]:
    """Return the mapped columns of one map block, skipping null and TODO entries.

    Args:
        block: A channel map, or one farm of it.

    Returns:
        Canonical channel name to source column.
    """
    channels = block.get("channels") or {}
    return {
        str(canonical): str(column)
        for canonical, column in channels.items()
        if isinstance(column, str) and not column.startswith("TODO")
    }


@contextmanager
def open_member(member: RawMember) -> Iterator[IO[bytes]]:
    """Open a member for reading without extracting the archive.

    Args:
        member: Member to open.

    Yields:
        A binary stream positioned at the start of the member.
    """
    if member.in_archive:
        with zipfile.ZipFile(member.archive) as archive, archive.open(member.name) as handle:
            yield handle
    else:
        with member.archive.open("rb") as handle:
            yield handle


@dataclass
class BaseAdapter:
    """Shared discovery and classification logic for source adapters.

    Subclasses set the identity fields and may extend :attr:`PATTERNS` where a
    provider names things unusually.

    Attributes:
        channel_map: Canonical-to-source column mapping loaded from configs.
        rated_power_kw: Nameplate rated power per turbine in kW, the divisor that puts
            the canonical power channel in per unit. ``None`` where the source publishes
            power already per unit, or declares no rating.
        source_id: Source identifier.
        site_name: Human-readable site name.
    """

    channel_map: dict[str, str] = field(default_factory=dict)
    rated_power_kw: float | None = None

    source_id: ClassVar[str] = "base"
    site_name: ClassVar[str] = "base"

    #: Substring rules applied to the lowercased member name, in order. The first
    #: match wins, so more specific rules must come first.
    PATTERNS: ClassVar[tuple[tuple[str, MemberKind], ...]] = (
        ("alarm", "alarm_log"),
        ("status", "status_events"),
        ("event", "status_events"),
        ("shutdown", "status_events"),
        ("fault", "status_events"),
        ("description", "metadata"),
        ("metadata", "metadata"),
        ("mapping", "metadata"),
        ("static", "metadata"),
        ("readme", "metadata"),
        ("turbine_data", "scada_10min"),
        ("scada", "scada_10min"),
    )

    #: Where :attr:`PATTERNS` come from. Every inventory report prints it, so a reader
    #: can tell a classification taken from the provider's own documentation from one
    #: inferred from file names.
    CLASSIFICATION_SOURCE: ClassVar[str] = "file-name substring patterns in the adapter"

    #: A loose file in which the provider documents its event codes, if it ships one.
    #: The inventory reads it and measures how much of the event log it describes.
    CODE_DESCRIPTIONS: ClassVar[str | None] = None

    @classmethod
    def from_configs(cls, configs_dir: Path) -> BaseAdapter:
        """Build an adapter with its channel map loaded from the configs directory.

        Args:
            configs_dir: The repository ``configs`` directory.

        Returns:
            A configured adapter.
        """
        path = configs_dir / "data" / "channel_map" / f"{cls.source_id}.yaml"
        return cls(
            channel_map=load_channel_map(path),
            rated_power_kw=load_rated_power_kw(configs_dir, cls.source_id),
        )

    def classify(self, name: str) -> MemberKind:
        """Classify a member by its name.

        Args:
            name: Member path or file name.

        Returns:
            The member kind, ``other`` when no rule matches.
        """
        lowered = name.lower()
        for needle, kind in self.PATTERNS:
            if needle in lowered:
                return kind
        if lowered.endswith(".csv"):
            return "scada_10min"
        return "other"

    def discover(self, raw_dir: Path) -> list[RawMember]:
        """List and classify every readable member staged for this source.

        Args:
            raw_dir: Directory holding the staged archives.

        Returns:
            Members sorted by archive name and member name.
        """
        if not raw_dir.is_dir():
            logger.warning("%s: nothing staged at %s", self.source_id, raw_dir)
            return []
        members: list[RawMember] = []
        for path in sorted(raw_dir.iterdir()):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in ARCHIVE_SUFFIXES:
                members.extend(self._members_of_archive(path))
            elif suffix in LOOSE_SUFFIXES:
                size = path.stat().st_size
                members.append(
                    RawMember(
                        archive=path,
                        name="",
                        kind=self.classify(path.name),
                        size=size,
                        compressed_size=size,
                        in_archive=False,
                    )
                )
        return members

    def _members_of_archive(self, path: Path) -> list[RawMember]:
        """List the members of one archive.

        Args:
            path: Archive to read.

        Returns:
            The archive's classified members, empty if it cannot be opened.
        """
        try:
            with zipfile.ZipFile(path) as archive:
                return [
                    RawMember(
                        archive=path,
                        name=info.filename,
                        kind=self.classify(info.filename),
                        size=info.file_size,
                        compressed_size=info.compress_size,
                        in_archive=True,
                    )
                    for info in archive.infolist()
                    if not info.is_dir()
                ]
        except (zipfile.BadZipFile, OSError) as exc:
            logger.error("cannot read archive %s: %s", path.name, exc)
            return []

    def split_channel_column(self, column: str) -> tuple[str | None, str]:
        """Split a channel-map column into the table it lives in and its field name.

        Most providers publish one table per turbine, so by default a column names a
        field and no table. A provider that spreads a turbine's signals over several
        tables overrides this.

        Args:
            column: Column as written in the channel map.

        Returns:
            The table name, or ``None``, and the field name.
        """
        return None, column

    def to_canonical_units(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Put a loaded table's channels in their canonical units.

        Power is canonically **per unit of the machine's rated power**, so a source that
        publishes kW is divided by its nameplate rating (ADR-0013). This is a unit
        conversion like CARE's rad/s to rpm, and it belongs here for the same reason: the
        unit is part of what the provider published, and everything downstream of an
        adapter is meant to read one schema in one set of units.

        Args:
            frame: A canonical wide table as the loader built it.

        Returns:
            The table in canonical units. Unchanged where the source declares no rating,
            which is how a source already publishing per unit says so.
        """
        if self.rated_power_kw is None or POWER_CHANNEL not in frame.columns:
            return frame
        result = frame.copy()
        result[POWER_CHANNEL] = (
            pd.to_numeric(result[POWER_CHANNEL], errors="coerce") / self.rated_power_kw
        )
        return result

    def turbine_id(self, member: RawMember) -> str:
        """Identify the turbine a member belongs to.

        The default falls back to the member's file stem. A provider that states the
        turbine inside the file -- as the Greenbyte exports do in their preamble --
        should override this, because a file name is a naming convention and a
        preamble line is data.

        Args:
            member: Member to identify.

        Returns:
            The turbine identifier.
        """
        stem = (member.name or member.archive.name).rsplit("/", 1)[-1]
        return stem.removesuffix(".csv")

    def scada_units(self, members: Sequence[RawMember]) -> list[list[RawMember]]:
        """Group the SCADA members into the units a loader reads together.

        Most providers publish one turbine-year per file, so by default each member is
        its own unit. A provider that splits one turbine's signals over several files
        overrides this.

        Args:
            members: Members discovered for the source.

        Returns:
            One list of members per unit, in a stable order.
        """
        return [[member] for member in members if member.kind == "scada_10min" and member.size > 0]

    def load_scada_unit(self, unit: Sequence[RawMember]) -> tuple[pd.DataFrame, list[FileAccount]]:
        """Read one unit of SCADA members into the canonical wide schema.

        Args:
            unit: Members that are read together.

        Returns:
            The canonical wide table and one account per file read.
        """
        frames: list[pd.DataFrame] = []
        accounts: list[FileAccount] = []
        for member in unit:
            frame, account = self.load_scada_with_stats(member)
            frames.append(frame)
            accounts.append(account)
        return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), accounts

    def load_scada_with_stats(self, member: RawMember) -> tuple[pd.DataFrame, FileAccount]:
        """Read one SCADA member, and account for every row it had.

        Args:
            member: Member classified as SCADA.

        Returns:
            A canonical wide table and the file's row accounting.

        Raises:
            NotImplementedError: In the base adapter.
        """
        raise NotImplementedError(f"{self.source_id}: load_scada is not implemented")

    def load_scada(self, member: RawMember) -> pd.DataFrame:
        """Read one SCADA member into the canonical wide schema.

        Args:
            member: Member classified as SCADA.

        Returns:
            A canonical wide table.
        """
        return self.load_scada_with_stats(member)[0]

    def load_events(self, member: RawMember) -> pd.DataFrame | None:
        """Read one event member into the canonical events schema.

        Args:
            member: Member classified as an event table.

        Returns:
            A canonical events table, or ``None``.

        Raises:
            NotImplementedError: In the base adapter.
        """
        raise NotImplementedError(f"{self.source_id}: load_events is not implemented")

    def read_stop_classes(
        self,
        members: Sequence[RawMember],
        years: Collection[int],
        table: str,
        fields: Sequence[str],
    ) -> pd.DataFrame:
        """Read a provider's per-step stop-class timers, for a source that publishes them.

        Args:
            members: Members discovered for the source.
            years: Calendar years to read.
            table: The table holding the timers.
            fields: Timer fields to keep.

        Returns:
            ``turbine_id``, ``timestamp_utc`` and one column per field.

        Raises:
            NotImplementedError: In the base adapter: the source publishes no such table.
        """
        raise NotImplementedError(f"{self.source_id}: publishes no stop-class timers")


def sniff_csv_layout(blob: bytes, probe_lines: int = 40) -> tuple[int, list[str] | None]:
    """Work out where the real header of a CSV member starts.

    Several providers prefix an export with a commented preamble, and they do not
    agree on what follows it. Greenbyte exports (Kelmarsh, Penmanshiel) put a
    ``#`` block of provenance lines at the top; in the status tables a clean header
    row follows, while in the turbine-data tables the **last comment line is itself
    the header**, prefixed with ``# ``.

    Getting this wrong is not a loud failure. The preamble parses as data, the
    columns come out as nonsense, and an inspection concludes that a table has no
    message column when it plainly does -- which is exactly the kind of false
    negative this whole module exists to avoid.

    Args:
        blob: Leading bytes of the member.
        probe_lines: How many lines to examine.

    Returns:
        A tuple of the number of leading lines to skip, and explicit column names
        when the header had to be recovered from a comment line.
    """
    lines = blob.decode("utf-8", errors="replace").splitlines()[:probe_lines]
    comments = 0
    for line in lines:
        if line.startswith("#"):
            comments += 1
        else:
            break
    if comments == 0:
        return 0, None

    header_candidate = lines[comments - 1].lstrip("#").strip()
    following = lines[comments] if len(lines) > comments else ""
    # Quote-aware on both sides: these headers quote any field containing a comma
    # ("Wind speed, Maximum (m/s)"), so counting raw commas overstates the width and
    # the header would be missed.
    candidate_fields = _split_csv_header(header_candidate)
    if len(candidate_fields) > 2 and len(candidate_fields) == len(_split_csv_header(following)):
        return comments, [name.strip() for name in candidate_fields]
    return comments, None


def _split_csv_header(line: str) -> list[str]:
    """Split a header line on commas that are not inside double quotes.

    Args:
        line: Raw header line.

    Returns:
        The field names, still carrying their surrounding quotes if any.
    """
    fields: list[str] = []
    current: list[str] = []
    quoted = False
    for char in line:
        if char == '"':
            quoted = not quoted
            continue
        if char == "," and not quoted:
            fields.append("".join(current))
            current = []
            continue
        current.append(char)
    fields.append("".join(current))
    return fields


def header_columns(member: RawMember, probe_bytes: int = 65_536) -> list[str]:
    """Read the column names of a CSV member without parsing a single row.

    Handles the same layouts as :func:`read_csv_member`: a plain header, a commented
    preamble followed by a header, and a preamble whose last comment line is the header.
    The separator is whichever of comma, semicolon or tab the header line uses most.

    Args:
        member: Member to read.
        probe_bytes: Leading bytes to examine; a header longer than this is truncated.

    Returns:
        The column names, stripped of surrounding whitespace and quotes.
    """
    with open_member(member) as handle:
        head = handle.read(probe_bytes)
    skiprows, names = sniff_csv_layout(head)
    if names is not None:
        return names
    lines = head.decode("utf-8", errors="replace").splitlines()
    if len(lines) <= skiprows:
        return []
    line = lines[skiprows]
    separator = max(",;\t", key=line.count)
    fields = _split_csv_header(line) if separator == "," else line.split(separator)
    return [name.strip().strip('"') for name in fields]


def read_csv_member(
    member: RawMember, nrows: int | None = None, usecols: list[str] | None = None
) -> pd.DataFrame:
    """Read a CSV member into a DataFrame, honouring the provider preamble.

    Args:
        member: Member to read.
        nrows: Row cap, or ``None`` for the whole member.
        usecols: Columns to keep; all of them when omitted.

    Returns:
        The parsed table.
    """
    with open_member(member) as handle:
        blob = handle.read()
    skiprows, names = sniff_csv_layout(blob[:65_536])
    return pd.read_csv(
        io.BytesIO(blob),
        sep=None,
        engine="python",
        skiprows=skiprows,
        names=names,
        header=None if names else "infer",
        usecols=usecols,
        nrows=nrows,
        on_bad_lines="skip",
        encoding_errors="replace",
    )


def read_csv_member_columns(
    member: RawMember, columns: list[str], probe_bytes: int = 65_536
) -> pd.DataFrame:
    """Stream selected columns out of a CSV member without materializing it.

    :func:`read_csv_member` reads the whole member into memory and lets pandas sniff
    the separator. That is right for a status table of a few thousand rows and wrong
    for a turbine-year of 10-minute SCADA: those members are several hundred
    megabytes uncompressed and 299 columns wide, and a pass that needs two of those
    columns should not pay for the other 297.

    Columns the member does not have are skipped rather than raising, because a
    provider dropping a signal in one year is normal and must surface as absent
    data.

    Args:
        member: Member to read.
        columns: Column names to keep, in the caller's order.
        probe_bytes: Leading bytes used to work out the header layout.

    Returns:
        The requested columns that exist, in the member's own column order.
    """
    with open_member(member) as handle:
        head = handle.read(probe_bytes)
    skiprows, names = sniff_csv_layout(head)
    lines = head.decode("utf-8", errors="replace").splitlines()
    # The header is the last comment line when names were recovered from it, and the
    # first line after the preamble otherwise. Reading the separator off the wrong line
    # would take it from a comment.
    header_line = lines[max(skiprows - 1, 0)] if names is not None else lines[skiprows]
    separator = max(",;\t", key=header_line.count)

    available = header_columns(member, probe_bytes)
    wanted = [name for name in columns if name in available]
    if not wanted:
        return pd.DataFrame()

    with open_member(member) as handle:
        return pd.read_csv(
            handle,
            sep=separator,
            skiprows=skiprows,
            names=names,
            header=None if names else "infer",
            usecols=wanted,
            on_bad_lines="skip",
            encoding="utf-8",
            encoding_errors="replace",
        )


def read_preamble(member: RawMember, probe_bytes: int = 8192) -> dict[str, str]:
    """Extract the ``# key: value`` provenance lines a provider prepends to an export.

    Greenbyte exports state the turbine, the turbine type and -- importantly -- the
    timezone this way. Reading it beats inferring any of them from a file name.

    Args:
        member: Member to read.
        probe_bytes: How many leading bytes to examine.

    Returns:
        A mapping of the key/value comment lines found, keys lowercased.
    """
    with open_member(member) as handle:
        blob = handle.read(probe_bytes)
    fields: dict[str, str] = {}
    for line in blob.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("#"):
            break
        body = line.lstrip("#").strip()
        if ":" in body:
            key, _, value = body.partition(":")
            if key.strip() and value.strip() and len(key) < 40:
                fields[key.strip().lower()] = value.strip()
    return fields
