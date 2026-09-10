"""Channel map status: what each source publishes for each canonical channel.

A channel map records one of three findings per canonical channel, and each finding
carries its evidence:

* **resolved**: a source column measures this channel. The provider's own description
  of that column, from its lookup file, is the evidence.
* **verified absent**: the provider's lookup was read in full and nothing in it
  measures this channel.
* **ambiguous**: candidate columns exist, but the lookup does not say which one is the
  canonical channel. Picking one would be a guess.

Anything else is **unresolved**, which is an open question and not a finding. The
core channel set is derived from these statuses (:func:`derive_core`), not declared.
The distinction between "absent" and "unresolved" is what makes that derivation
honest: a channel cannot be demoted for an absence nobody has checked.

A map is flat -- one column per channel -- except where a record publishes several
farms with different sensor sets. CARE does, so its map carries one block per farm
under ``farms:``, each naming the archive directory its datasets live in.

Every resolved column is also checked against the headers of the staged archives,
because a lookup can describe a field that an export does not carry. Hill of Towie's
wind direction is such a field: it is described, and it is present in 2023 and absent
from every month of 2019.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from faultline.data.common.report import kv_table, section, table
from faultline.data.telemetry.adapters import get_adapter
from faultline.data.telemetry.adapters.base import BaseAdapter, RawMember, header_columns
from faultline.data.telemetry.schemas import CHANNEL_NAMES, CHANNELS_BY_NAME
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

ChannelStatus = Literal["resolved", "verified absent", "ambiguous", "unresolved"]

#: Short forms used in the summary matrix.
STATUS_ABBREVIATIONS: dict[str, str] = {
    "resolved": "resolved",
    "verified absent": "absent",
    "ambiguous": "ambiguous",
    "unresolved": "OPEN",
}

_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


@dataclass(frozen=True)
class ChannelEntry:
    """One canonical channel as one source, or one farm of it, publishes it.

    Attributes:
        channel: Canonical channel name.
        status: What the map found.
        column: Source column, when resolved.
        evidence: The provider's description for a resolved channel, or the reason it
            is absent or ambiguous.
        unit_note: Set when the column is not in the canonical unit.
    """

    channel: str
    status: ChannelStatus
    column: str | None
    evidence: str
    unit_note: str | None = None


@dataclass(frozen=True)
class ChannelGroup:
    """A unit that is mapped as a whole: a source, or one farm of a multi-farm source.

    Attributes:
        name: Farm identifier, or an empty string for a flat map.
        directory: Archive directory holding the group's members, for a farm.
        entries: One entry per canonical channel, in canonical order.
    """

    name: str
    directory: str | None
    entries: dict[str, ChannelEntry]

    @property
    def label(self) -> str:
        """The group's name, or ``all`` for a flat map."""
        return self.name or "all"


@dataclass(frozen=True)
class ChannelMapDoc:
    """A parsed and validated channel map file.

    Attributes:
        source: Source identifier.
        path: File the map was read from.
        mapping_status: The file's own one-line summary.
        groups: One group for a flat map, one per farm otherwise.
    """

    source: str
    path: Path
    mapping_status: str
    groups: tuple[ChannelGroup, ...]

    def resolved_everywhere(self) -> set[str]:
        """Channels resolved in every group of this map.

        Returns:
            Canonical channel names.
        """
        return {
            channel
            for channel in CHANNEL_NAMES
            if all(group.entries[channel].status == "resolved" for group in self.groups)
        }

    def status(self, channel: str) -> ChannelStatus:
        """The status of a channel, when every group agrees on it.

        Args:
            channel: Canonical channel name.

        Returns:
            The shared status, or ``ambiguous`` when the groups disagree.
        """
        statuses = {group.entries[channel].status for group in self.groups}
        return statuses.pop() if len(statuses) == 1 else "ambiguous"


@dataclass(frozen=True)
class Presence:
    """Where a resolved column appears in the staged archive headers.

    Attributes:
        members: Members the column could appear in.
        present: Members whose header carries it.
        by_period: The same two counts per year, where member names carry a year.
    """

    members: int
    present: int
    by_period: dict[str, tuple[int, int]]

    def describe(self) -> str:
        """One cell of the report: ``present/members``, split by year when that differs.

        Returns:
            A short string.
        """
        if self.members == 0:
            return "no members staged"
        if self.present == self.members or len(self.by_period) < 2:
            return f"{self.present}/{self.members}"
        return ", ".join(
            f"{period}: {hit}/{total}" for period, (hit, total) in self.by_period.items()
        )


def _mapping(block: Mapping[str, Any], key: str, where: str) -> dict[str, Any]:
    """Read an optional per-channel mapping from a map block, rejecting unknown channels.

    Args:
        block: The map, or one farm of it.
        key: Section name.
        where: Location for error messages.

    Returns:
        The section, empty when absent.

    Raises:
        ValueError: If the section names a channel that is not canonical.
    """
    value = block.get(key) or {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{where}: {key} must be a mapping of channel to text")
    unknown = sorted(str(name) for name in value if name not in CHANNELS_BY_NAME)
    if unknown:
        raise ValueError(f"{where}: {key} names non-canonical channels {unknown}")
    return {str(name): text for name, text in value.items()}


def _parse_group(name: str, block: Mapping[str, Any], where: str) -> ChannelGroup:
    """Parse and validate one mapped unit.

    Args:
        name: Farm identifier, or an empty string.
        block: The map, or one farm of it.
        where: Location for error messages.

    Returns:
        The validated group.

    Raises:
        ValueError: If a canonical channel is undeclared, a resolved channel carries no
            evidence, or a channel is given two statuses at once.
    """
    channels = _mapping(block, "channels", where)
    missing = [channel for channel in CHANNEL_NAMES if channel not in channels]
    if missing:
        raise ValueError(
            f"{where}: every canonical channel must be declared, even as null; missing {missing}"
        )
    evidence = _mapping(block, "evidence", where)
    absent = _mapping(block, "verified_absent", where)
    ambiguous = _mapping(block, "ambiguous", where)
    units = _mapping(block, "units", where)

    entries: dict[str, ChannelEntry] = {}
    for channel in CHANNEL_NAMES:
        raw = channels[channel]
        column = None if raw is None or str(raw).startswith("TODO") else str(raw)
        status: ChannelStatus
        if column is not None:
            if channel in absent or channel in ambiguous:
                raise ValueError(
                    f"{where}: {channel} is mapped to {column!r} and also listed as "
                    "absent or ambiguous"
                )
            text = str(evidence.get(channel, "")).strip()
            if not text:
                raise ValueError(
                    f"{where}: {channel} is mapped to {column!r} with no evidence; quote the "
                    "provider's description of the column under evidence:"
                )
            status = "resolved"
        elif channel in absent and channel in ambiguous:
            raise ValueError(f"{where}: {channel} is listed as both absent and ambiguous")
        elif channel in absent:
            status, text = "verified absent", str(absent[channel]).strip()
        elif channel in ambiguous:
            status, text = "ambiguous", str(ambiguous[channel]).strip()
        else:
            status, text = "unresolved", ""
        note = units.get(channel)
        entries[channel] = ChannelEntry(
            channel=channel,
            status=status,
            column=column,
            evidence=text,
            unit_note=None if note is None else str(note),
        )
    directory = block.get("directory")
    return ChannelGroup(
        name=name, directory=None if directory is None else str(directory), entries=entries
    )


def parse_channel_map(path: Path) -> ChannelMapDoc:
    """Read and validate a channel map file.

    Args:
        path: Path to ``configs/data/channel_map/<source>.yaml``.

    Returns:
        The parsed map.

    Raises:
        ValueError: If the map breaks any rule in :func:`_parse_group`.
    """
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    farms = payload.get("farms")
    if farms:
        groups = tuple(
            _parse_group(str(name), block, f"{path.name} [{name}]") for name, block in farms.items()
        )
    else:
        groups = (_parse_group("", payload, path.name),)
    return ChannelMapDoc(
        source=str(payload.get("source", path.stem)),
        path=path,
        mapping_status=str(payload.get("mapping_status", "")).strip(),
        groups=groups,
    )


def load_channel_maps(configs_dir: Path, sources: Iterable[str]) -> dict[str, ChannelMapDoc]:
    """Parse the channel maps of several sources.

    Args:
        configs_dir: The repository ``configs`` directory.
        sources: Source identifiers.

    Returns:
        Parsed maps keyed by source.
    """
    root = configs_dir / "data" / "channel_map"
    return {source: parse_channel_map(root / f"{source}.yaml") for source in sources}


def derive_core(
    maps: Mapping[str, ChannelMapDoc], training: Sequence[str], holdout: Sequence[str]
) -> tuple[list[str], list[str]]:
    """Derive the core channel set from resolved maps.

    Core means resolved at every training source and mappable at every held-out source,
    so a leave-site-out evaluation can read it on both sides of the split. Everything
    else is extended.

    Args:
        maps: Parsed channel maps keyed by source.
        training: Sources a model is trained on.
        holdout: Sources held out whole.

    Returns:
        Core and extended channel names, each in canonical order.

    Raises:
        KeyError: If a named source has no map.
    """
    required = [*training, *holdout]
    absent = [source for source in required if source not in maps]
    if absent:
        raise KeyError(f"no channel map for {absent}")
    core = [
        channel
        for channel in CHANNEL_NAMES
        if all(channel in maps[source].resolved_everywhere() for source in required)
    ]
    return core, [channel for channel in CHANNEL_NAMES if channel not in core]


def _period(member: RawMember) -> str:
    """The year a member's name carries, or an empty string."""
    match = _YEAR.search(member.name.rsplit("/", 1)[-1] or member.archive.name)
    return match.group(1) if match else ""


def header_presence(
    doc: ChannelMapDoc, adapter: BaseAdapter, members: Sequence[RawMember]
) -> dict[tuple[str, str], Presence]:
    """Check every resolved column against the headers of the staged SCADA members.

    Args:
        doc: Parsed channel map.
        adapter: The source's adapter, which says how a column names its table.
        members: Members discovered for the source.

    Returns:
        Presence keyed by ``(group label, channel)``, for resolved channels only.
    """
    scada = [member for member in members if member.kind == "scada_10min" and member.size > 0]
    headers: dict[tuple[Path, str], set[str]] = {}

    def columns_of(member: RawMember) -> set[str]:
        key = (member.archive, member.name)
        if key not in headers:
            headers[key] = set(header_columns(member))
        return headers[key]

    result: dict[tuple[str, str], Presence] = {}
    for group in doc.groups:
        in_group = [
            member
            for member in scada
            if group.directory is None or f"/{group.directory}/" in f"/{member.name}"
        ]
        for entry in group.entries.values():
            if entry.column is None:
                continue
            table_name, field = adapter.split_channel_column(entry.column)
            relevant = [
                member
                for member in in_group
                if table_name is None
                or (member.name.rsplit("/", 1)[-1] or member.archive.name).startswith(
                    f"{table_name}_"
                )
            ]
            by_period: dict[str, list[int]] = {}
            present = 0
            for member in relevant:
                hit = field in columns_of(member)
                present += hit
                counts = by_period.setdefault(_period(member), [0, 0])
                counts[0] += hit
                counts[1] += 1
            result[(group.label, entry.channel)] = Presence(
                members=len(relevant),
                present=present,
                by_period={
                    period: (hit, total) for period, (hit, total) in sorted(by_period.items())
                },
            )
    return result


def render_channel_report(
    maps: Mapping[str, ChannelMapDoc],
    presence: Mapping[str, Mapping[tuple[str, str], Presence]],
    training: Sequence[str],
    holdout: Sequence[str],
    repo_root: Path,
) -> str:
    """Render the per-source channel status report.

    Args:
        maps: Parsed channel maps keyed by source.
        presence: Header presence per source, from :func:`header_presence`.
        training: Training sources, for the cross-site findings.
        holdout: Held-out sources, for the cross-site findings.
        repo_root: Repository root, for the git SHA.

    Returns:
        A Markdown document.
    """
    parts = [
        "# Channel maps\n\n",
        kv_table(
            {
                "canonical channels": len(CHANNEL_NAMES),
                "sources": ", ".join(maps),
                "training sources": ", ".join(training),
                "held-out sources": ", ".join(holdout),
                "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "git_sha": git_sha(repo_root),
                "generated by": "faultline inspect channels",
            }
        ),
        "\nOne row per canonical channel and source. **resolved**: a source column measures "
        "the channel, and the evidence is the provider's own description of that column. "
        "**verified absent**: the provider's lookup was read in full and nothing in it "
        "measures the channel. **ambiguous**: candidates exist but the lookup does not say "
        "which one is meant. `staged headers` counts the staged SCADA members whose header "
        "carries the column, by year where that differs; a lookup can describe a field an "
        "export does not carry.\n",
    ]

    groups = [(source, group) for source, doc in maps.items() for group in doc.groups]
    matrix_headers = ["channel", *(f"{s} {g.name}".strip() for s, g in groups)]
    parts.append(
        section(
            "Summary",
            table(
                matrix_headers,
                [
                    (
                        channel,
                        *(
                            STATUS_ABBREVIATIONS[group.entries[channel].status]
                            for _, group in groups
                        ),
                    )
                    for channel in CHANNEL_NAMES
                ],
            ),
        )
    )

    findings = []
    for channel in CHANNEL_NAMES:
        at_holdout = all(maps[s].status(channel) == "resolved" for s in holdout if s in maps)
        absent_in_training = all(
            maps[s].status(channel) == "verified absent" for s in training if s in maps
        )
        if holdout and training and at_holdout and absent_in_training:
            findings.append(
                f"- `{channel}` is published at the held-out site ({', '.join(holdout)}) and "
                f"verified absent at every training site ({', '.join(training)}). A model "
                "trained on the training sites has never seen it."
            )
    for source in maps:
        for (group_label, channel), where in presence.get(source, {}).items():
            if where.members and where.present < where.members:
                label = f"{source} {group_label}".replace(" all", "")
                findings.append(
                    f"- `{channel}` at {label} is resolved but missing from some staged "
                    f"exports: {where.describe()}. Those periods read it as missing data."
                )
    if findings:
        parts.append(section("Findings across sources", "\n".join(findings)))

    for source, doc in maps.items():
        for group in doc.groups:
            title = f"{source}" + (f" - {group.name}" if group.name else "")
            rows = []
            for entry in group.entries.values():
                seen = presence.get(source, {}).get((group.label, entry.channel))
                rows.append(
                    (
                        entry.channel,
                        CHANNELS_BY_NAME[entry.channel].tier,
                        f"**{entry.status}**",
                        f"`{entry.column}`" if entry.column else "-",
                        entry.evidence or "-",
                        entry.unit_note or "-",
                        seen.describe() if seen is not None else "-",
                    )
                )
            summary = kv_table(
                {
                    "map": doc.path.name,
                    "stated status": doc.mapping_status or "-",
                    "archive directory": group.directory or "-",
                    "resolved": sum(e.status == "resolved" for e in group.entries.values()),
                    "verified absent": sum(
                        e.status == "verified absent" for e in group.entries.values()
                    ),
                    "ambiguous": sum(e.status == "ambiguous" for e in group.entries.values()),
                    "unresolved": sum(e.status == "unresolved" for e in group.entries.values()),
                }
            )
            parts.append(
                section(
                    title,
                    summary
                    + "\n"
                    + table(
                        [
                            "channel",
                            "declared tier",
                            "status",
                            "source column",
                            "evidence",
                            "unit",
                            "staged headers",
                        ],
                        rows,
                    ),
                )
            )
    return "".join(parts)


def inspect_channels(
    paths: ProjectPaths, sources: Sequence[str], training: Sequence[str], holdout: Sequence[str]
) -> Path:
    """Parse every channel map, check it against the staged headers and write the report.

    Args:
        paths: Resolved project paths.
        sources: Sources to report on.
        training: Training sources.
        holdout: Held-out sources.

    Returns:
        The path of the written report.
    """
    maps = load_channel_maps(paths.configs_dir, sources)
    presence: dict[str, dict[tuple[str, str], Presence]] = {}
    for source in sources:
        adapter = get_adapter(source, paths.configs_dir)
        members = adapter.discover(paths.source_dir("raw", "telemetry", source))
        presence[source] = header_presence(maps[source], adapter, members)
        logger.info("%s: checked %d resolved columns", source, len(presence[source]))
    report = render_channel_report(maps, presence, training, holdout, paths.repo_root)
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d")
    destination = paths.data_reports_dir / f"channel_maps_{stamp}.md"
    destination.write_text(report, encoding="utf-8")
    logger.info("wrote %s", destination)
    return destination
