"""The source adapter contract.

An adapter is the only place that knows a provider's file names, column vocabulary
and quirks. Everything downstream sees the canonical schema, so supporting a fifth
site is a new adapter plus a channel map -- not a change to the pipeline.

Adapters read **inside** archives. A staged tier-1 corpus is around 20 GB
compressed; extracting it would double that for no benefit, since ``zipfile`` gives
pandas a perfectly good file object.

At M0 ``discover`` is implemented for every source and the loaders are implemented
only where the member format has been confirmed by inspection. An unconfirmed
loader raises rather than guessing at a column layout.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, ClassVar, Literal, Protocol, runtime_checkable

import pandas as pd
import yaml

from faultline.logging_utils import get_logger

logger = get_logger(__name__)

MemberKind = Literal["scada_10min", "status_events", "alarm_log", "metadata", "other"]

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
        if source_column is None:
            continue
        text = str(source_column)
        if text.startswith("TODO"):
            continue
        resolved[str(canonical)] = text
    return resolved


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
        source_id: Source identifier.
        site_name: Human-readable site name.
    """

    channel_map: dict[str, str] = field(default_factory=dict)

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

    @classmethod
    def from_configs(cls, configs_dir: Path) -> BaseAdapter:
        """Build an adapter with its channel map loaded from the configs directory.

        Args:
            configs_dir: The repository ``configs`` directory.

        Returns:
            A configured adapter.
        """
        path = configs_dir / "data" / "channel_map" / f"{cls.source_id}.yaml"
        return cls(channel_map=load_channel_map(path))

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

    def load_scada(self, member: RawMember) -> pd.DataFrame:
        """Read one SCADA member into the canonical wide schema.

        Args:
            member: Member classified as SCADA.

        Returns:
            A canonical wide table.

        Raises:
            NotImplementedError: In the base adapter.
        """
        raise NotImplementedError(f"{self.source_id}: load_scada is not implemented")

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
