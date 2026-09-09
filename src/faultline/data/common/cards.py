"""Dataset card rendering.

A card is the human-readable half of the provenance record; the manifest is the
machine-readable half. Together they are what lets someone reconstruct the corpus
from this repository plus the public archive, without the 20 GB ever being
committed.

Cards are generated, not written by hand, so they cannot drift from the manifest.
Any field the evidence does not support is rendered as an explicit
``UNVERIFIED - TODO(m1): ...`` rather than left blank or filled with a plausible
guess, because a card that quietly asserts something unchecked is worse than no
card at all.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

from faultline.data.common.manifest import SourceManifest, manifest_path, read_manifest
from faultline.data.common.report import kv_table, section, table
from faultline.data.telemetry.adapters.base import load_channel_map
from faultline.download.zenodo import SourceSpec
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

#: Marker used wherever the evidence does not support a field.
UNVERIFIED = "UNVERIFIED"

_VERDICT_LINE = re.compile(r"^\*\*(VERIFIED yes|VERIFIED no|UNVERIFIED)\*\*\s*-\s*(.*)$", re.M)

#: A ``## Question`` heading followed by the ``**VERDICT x** - why`` line under it,
#: as ``faultline inspect resolve`` writes them.
_RESOLUTION = re.compile(
    r"^## (?P<question>.+?)\n+\*\*VERDICT (?P<verdict>[^*]+?)\*\*\s*-\s*(?P<why>.+?)$", re.M
)


def latest_inventory(reports_dir: Path, source: str) -> Path | None:
    """Find the most recent raw inventory report for a source.

    Args:
        reports_dir: The ``reports/data`` directory.
        source: Source identifier.

    Returns:
        The newest matching report, or ``None`` when the source has not been
        inspected yet.
    """
    candidates = sorted(reports_dir.glob(f"raw_inventory_{source}_*.md"))
    return candidates[-1] if candidates else None


def extract_verdict(report_path: Path | None) -> tuple[str, str]:
    """Read the free-text verdict out of an inventory report.

    Args:
        report_path: Report to read, or ``None``.

    Returns:
        A ``(verdict, rationale)`` pair; ``UNVERIFIED`` when there is no report.
    """
    if report_path is None or not report_path.is_file():
        return (
            UNVERIFIED,
            "no raw inventory report exists yet; run `faultline inspect telemetry` "
            "once the archives are staged",
        )
    match = _VERDICT_LINE.search(report_path.read_text(encoding="utf-8"))
    if match is None:
        return UNVERIFIED, f"no verdict line found in {report_path.name}"
    return match.group(1), match.group(2).strip()


def latest_resolution(reports_dir: Path, source: str) -> Path | None:
    """Find the most recent resolution report for a source.

    Args:
        reports_dir: The ``reports/data`` directory.
        source: Source identifier.

    Returns:
        The newest matching report, or ``None`` when nothing has been measured yet.
    """
    candidates = sorted(reports_dir.glob(f"resolved_{source}_*.md"))
    return candidates[-1] if candidates else None


def extract_resolutions(report_path: Path | None) -> list[tuple[str, str, str]]:
    """Read the measured verdicts out of a resolution report.

    Args:
        report_path: Report to read, or ``None``.

    Returns:
        ``(question, verdict, rationale)`` triples, empty when nothing was measured.
    """
    if report_path is None or not report_path.is_file():
        return []
    text = report_path.read_text(encoding="utf-8")
    return [
        (
            match.group("question").strip(),
            match.group("verdict").strip(),
            match.group("why").strip(),
        )
        for match in _RESOLUTION.finditer(text)
    ]


def _staging_rows(manifest: SourceManifest | None) -> list[tuple[str, object, object, object]]:
    """Build the per-file staging table rows.

    Args:
        manifest: The source manifest, or ``None``.

    Returns:
        Rows of ``(filename, size MB, md5 present, verified)``.
    """
    if manifest is None:
        return []
    return [
        (
            record.filename,
            round(record.size_bytes / 1e6, 1),
            "yes" if record.md5 else "no",
            "yes" if record.verified else "no",
        )
        for record in manifest.files
    ]


def channel_map_status(path: Path) -> dict[str, object]:
    """Summarize how far a source's channel map has been resolved.

    Read from the file rather than asserted, so a card cannot claim a mapping is
    outstanding after it has been done, or done while it is still outstanding.

    Args:
        path: Path to ``configs/data/channel_map/<source>.yaml``.

    Returns:
        Rows describing the mapping state, ready for a key/value table.
    """
    if not path.is_file():
        return {"mapping status": f"{UNVERIFIED} - no channel map file exists"}
    resolved = load_channel_map(path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    declared = payload.get("channels", {}) or {}
    stated = str(payload.get("mapping_status", "")).strip()
    rows: dict[str, object] = {
        "channels mapped": f"{len(resolved)} of {len(declared)}",
        "mapping status": stated
        or (f"{UNVERIFIED} - TODO(m1): fill the channel map from the provider signal-mapping file"),
    }
    if not resolved:
        rows["mapping status"] = (
            f"{UNVERIFIED} - every entry is still TODO(m1); the adapter skips this "
            "source rather than guessing at column names"
        )
    if timezone := payload.get("timezone"):
        rows["timezone (from the data files)"] = str(timezone)
    return rows


def build_card(source: str, spec: SourceSpec, paths: ProjectPaths) -> Path:
    """Render one dataset card from the specification, manifest and inventory.

    Args:
        source: Source identifier.
        spec: Source specification from the download config.
        paths: Resolved project paths.

    Returns:
        The path of the written card.
    """
    manifest = read_manifest(manifest_path(paths.manifests_dir, source))
    inventory = latest_inventory(paths.data_reports_dir, source)
    verdict, rationale = extract_verdict(inventory)
    resolution = latest_resolution(paths.data_reports_dir, source)
    resolutions = extract_resolutions(resolution)
    channel_map = paths.configs_dir / "data" / "channel_map" / f"{source}.yaml"

    staged = _staging_rows(manifest)
    retrieved = (
        min((record.retrieved_at for record in manifest.files), default=None) if manifest else None
    )

    parts = [f"# Dataset card: {spec.site.name}\n\n"]
    parts.append(
        section(
            "Identity",
            kv_table(
                {
                    "source id": source,
                    "provider": spec.provider,
                    "version-pinned record": f"https://zenodo.org/records/{spec.zenodo_record}",
                    "concept DOI": spec.concept_doi or f"{UNVERIFIED} - not configured",
                    "version DOI": (manifest.version_doi if manifest else None)
                    or f"{UNVERIFIED} - not recorded; requires a completed download",
                    "licence": spec.license,
                    "attribution": spec.attribution,
                    "accompanying publication": spec.cite or "none",
                }
            ),
        )
    )

    parts.append(
        section(
            "Contents as published",
            kv_table(
                {
                    "site": spec.site.name,
                    "country": spec.site.country or f"{UNVERIFIED}",
                    "turbine model": spec.site.oem or f"{UNVERIFIED}",
                    "turbines": spec.site.n_turbines or f"{UNVERIFIED}",
                    "rated power (kW)": spec.site.rated_kw
                    or f"{UNVERIFIED} - not published per farm",
                    "period": spec.site.period or f"{UNVERIFIED}",
                    "resolution": "10 min (as published)",
                    "timezone": spec.timezone or f"{UNVERIFIED}",
                    "provider note": spec.site.note or "none",
                }
            ),
        )
    )

    parts.append(
        section(
            "Staging",
            kv_table(
                {
                    "files retrieved": len(staged),
                    "total size (MB)": round(manifest.total_bytes / 1e6, 1) if manifest else 0,
                    "all checksums verified": "yes"
                    if manifest and manifest.all_verified
                    else f"no - {UNVERIFIED}",
                    "first retrieved (UTC)": retrieved.isoformat(timespec="seconds")
                    if retrieved
                    else f"{UNVERIFIED} - nothing staged yet",
                    "manifest": f"data/cards/manifests/{source}.json",
                    "raw inventory report": f"reports/data/{inventory.name}"
                    if inventory
                    else f"{UNVERIFIED} - not inspected yet",
                }
            )
            + "\n"
            + table(["file", "size (MB)", "md5 recorded", "verified"], staged),
        )
    )

    parts.append(
        section(
            "Event, alarm and status logs",
            f"**Free text present: {verdict}**\n\n{rationale}\n\n"
            "This is the field that decides whether the paired text in this record can carry "
            "a language model, or whether it is a controlled vocabulary that only supplies "
            "labels and structure (ADR-0001). The evidence is the raw inventory report named "
            "above; do not edit this field by hand.",
        )
    )

    if resolutions and resolution is not None:
        resolved_body = (
            table(
                ["question", "verdict", "evidence"],
                [(question, f"**{answer}**", why) for question, answer, why in resolutions],
            )
            + "\nThese are questions the provider metadata could not settle, because it either "
            "contradicted itself or asserted without evidence. They were measured from the "
            "staged archives by `faultline inspect resolve`; the per-turbine-year tables behind "
            f"each verdict are in `reports/data/{resolution.name}`. Do not edit this section by "
            "hand."
        )
    else:
        resolved_body = (
            f"{UNVERIFIED} - nothing has been measured for this source yet. Run "
            f"`faultline inspect resolve --source {source}` once its archives are staged."
        )
    parts.append(section("Questions resolved by measurement", resolved_body))

    parts.append(
        section(
            "Channels",
            kv_table(
                {
                    "channel map": f"configs/data/channel_map/{source}.yaml",
                    **channel_map_status(channel_map),
                }
            ),
        )
    )

    parts.append(
        section(
            "Use in FaultLine",
            kv_table(
                {
                    "intended use": spec.intended_use or f"{UNVERIFIED}",
                    "PII policy": "not applicable - telemetry and coded event logs; the text "
                    "policy in ADR-0005 applies to narrative corpora only",
                    "exclusions": "tier 2 files are specified but not staged at M0 "
                    "(grid meter, phasor measurement, geographic overlays)",
                }
            ),
        )
    )

    parts.append(
        section(
            "Caveats",
            "**From the provider.** "
            + (spec.site.note or "none recorded in the record metadata")
            + "\n\n**Found during inspection.** "
            + (
                f"See `reports/data/{inventory.name}`."
                if inventory
                else f"{UNVERIFIED} - the archives have not been inspected yet."
            )
            + "\n\n**Known limits of this card.** Every field marked "
            f"`{UNVERIFIED}` is an open question, not an absence of a problem.",
        )
    )

    parts.append(
        section(
            "Generation",
            kv_table(
                {
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline cards build",
                    "template": "docs/DATASET_CARD_TEMPLATE.md",
                }
            ),
        )
    )

    destination = paths.cards_dir / f"{source}.md"
    destination.write_text("".join(parts), encoding="utf-8")
    logger.info("%s: wrote %s", source, destination)
    return destination
