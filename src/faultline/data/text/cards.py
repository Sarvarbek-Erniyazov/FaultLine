"""Dataset cards for the text sources (M2), generated from evidence.

The telemetry cards (:mod:`faultline.data.common.cards`) are built from a Zenodo record,
a manifest and an inventory report. A text source has no Zenodo record and no
inventory report; its evidence is the source specification in
``configs/data/sources_text.yaml`` (identity, licence, access route -- copied, and the
card says so), the checksum manifest (staging), and the finished corpus a text pipeline
run produced (what survived cleaning, filtering, dedup and PII masking, per split).
The card follows ``docs/DATASET_CARD_TEMPLATE.md``'s rule: a field is filled from that
evidence or marked ``UNVERIFIED``; telemetry-only fields (turbines, channels, timezone)
are stated as not applicable rather than left out silently.

The free-text verdict uses the template's own labels and thresholds, measured on the
source's documents in the finished corpus: more than 500 distinct strings is
``VERIFIED yes``.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from faultline.data.common.manifest import load_manifest
from faultline.data.common.report import kv_table, section, table
from faultline.data.text.pipeline import TextPipelineConfig, load_text_config
from faultline.download.nrc_text import (
    CodeBookSpec,
    EventNotificationsSpec,
    GenericCommSpec,
    SocrataAttachmentsSpec,
    TextSourceSpec,
)
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

UNVERIFIED = "UNVERIFIED"

#: The template's open-ended-text threshold: more than this many distinct strings.
OPEN_TEXT_DISTINCT = 500

#: Title marker of an NRC event notification reported by an Agreement State.
AGREEMENT_STATE = "AGREEMENT STATE"


def _final_documents(paths: ProjectPaths, corpus_name: str, source: str) -> dict[str, list[str]]:
    """Every finished document of one source, per split.

    Args:
        paths: Resolved project paths.
        corpus_name: The finished corpus.
        source: Source id.

    Returns:
        Per split name, the source's document texts.
    """
    out: dict[str, list[str]] = {}
    final_dir = paths.stage_dir("final", "text") / corpus_name
    for shard in sorted(final_dir.glob("*-*.jsonl")):
        split = shard.name.split("-", 1)[0]
        for line in shard.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            record = json.loads(line)
            if record.get("source") == source:
                out.setdefault(split, []).append(str(record["text"]))
    return out


def _route(spec: TextSourceSpec) -> str:
    """Where the source's documents are fetched from, as the specification states it."""
    if isinstance(spec, EventNotificationsSpec):
        return f"{spec.base_url} (years {spec.year_start}-{spec.year_end})"
    if isinstance(spec, GenericCommSpec):
        return f"{spec.index_url} (years {spec.year_start}-{spec.year_end})"
    if isinstance(spec, SocrataAttachmentsSpec):
        return (
            f"data.transportation.gov view {spec.view}, {len(spec.attachments)} attachments; "
            f"column {spec.narrative_column}, one document per {spec.id_column}"
        )
    return "not fetched over the network"


def _excluded(spec: TextSourceSpec) -> str:
    """What the source's access route deliberately leaves out, per its specification."""
    if isinstance(spec, GenericCommSpec) and spec.pdf_excluded:
        return (
            "documents published only as PDF (the /docs/ ADAMS path, blocked at the edge, and "
            "/sites/default/files/doc_library/); counts per collection in ADR-0016"
        )
    if isinstance(spec, SocrataAttachmentsSpec):
        return (
            "every column but the narrative; pre-2010 files (the pre-registered rule names "
            "2010-onward only); the flagged-incidents derivative file (ADR-0016)"
        )
    if isinstance(spec, EventNotificationsSpec):
        return "nothing by route; earlier revisions of an event (keyed dedup keeps the latest)"
    return "none recorded"


def build_text_card(
    source: str,
    spec: TextSourceSpec,
    paths: ProjectPaths,
    text_config_path: Path,
) -> Path:
    """Render one text source's dataset card.

    Args:
        source: Source id.
        spec: The source's specification.
        paths: Resolved project paths.
        text_config_path: The text pipeline configuration whose finished corpus is read.

    Returns:
        The written card's path.

    Raises:
        ValueError: For the code-book source, which is carded with the telemetry it is
            drawn from rather than here.
    """
    if isinstance(spec, CodeBookSpec):
        raise ValueError(f"{source}: the status code book is not a narrative source")
    config: TextPipelineConfig = load_text_config(text_config_path)
    manifest = load_manifest(paths.manifests_dir, source)
    documents = _final_documents(paths, config.io.corpus_name, source)
    everything = [text for texts in documents.values() for text in texts]
    fractions = config.final.fractions_for(source)

    parts = [f"# {source}\n\n"]
    parts.append(
        section(
            "Identity",
            kv_table(
                {
                    "source id": source,
                    "provider": spec.provider,
                    "licence": spec.license,
                    "attribution": spec.attribution,
                    "access route": _route(spec),
                    "robots.txt basis": getattr(spec, "robots_basis", "not applicable"),
                    "version-pinned record / DOI": "not applicable: a live government "
                    "publication, pinned by the manifest's per-document sha256 and retrieval "
                    "time instead",
                    "provenance chain": "first-party publication; nothing republished",
                }
            )
            + "\n_Identity fields are copied from `configs/data/sources_text.yaml`._\n",
        )
    )

    if manifest is not None and manifest.files:
        retrieved = sorted(record.retrieved_at for record in manifest.files)
        eras = Counter(record.template_era for record in manifest.files if record.template_era)
        staging: dict[str, object] = {
            "documents staged": len(manifest.files),
            "total size (MB)": round(sum(r.size_bytes for r in manifest.files) / 1e6, 2),
            "first retrieval (UTC)": retrieved[0].isoformat(timespec="seconds"),
            "last retrieval (UTC)": retrieved[-1].isoformat(timespec="seconds"),
            "every document hashed and verified": "yes"
            if all(r.verified and r.sha256 for r in manifest.files)
            else "no",
            "manifest": f"data/cards/manifests/{source}.json",
        }
        if eras:
            staging["HTML template era (documents)"] = ", ".join(
                f"{era} {count:,}" for era, count in sorted(eras.items())
            )
        staging_body = kv_table(staging)
    else:
        staging_body = f"{UNVERIFIED} - no manifest: the source has not been staged.\n"
    if isinstance(spec, SocrataAttachmentsSpec):
        archives = load_manifest(paths.manifests_dir, spec.archive_source)
        if archives is not None:
            staging_body += "\n" + table(
                ["archive", "bytes", "sha256", "retrieved (UTC)"],
                [
                    (
                        r.filename,
                        r.size_bytes,
                        r.sha256 or "",
                        r.retrieved_at.isoformat(timespec="seconds"),
                    )
                    for r in archives.files
                ],
            )
    parts.append(section("Staging", staging_body))

    if everything:
        distinct = Counter(everything)
        once = sum(1 for count in distinct.values() if count == 1)
        mean_chars = sum(len(t) for t in everything) / len(everything)
        verdict = (
            "VERIFIED yes"
            if len(distinct) > OPEN_TEXT_DISTINCT
            else (
                "VERIFIED short written descriptions" if once > len(distinct) / 2 else "VERIFIED no"
            )
        )
        split_rows = [
            (
                split,
                f"{fractions.get(split, 0.0):.0%}",
                len(texts),
                sum(len(t.split()) for t in texts),
            )
            for split, texts in sorted(documents.items())
        ]
        contents = (
            kv_table(
                {
                    "finished corpus": f"{config.io.corpus_name} ({text_config_path.as_posix()})",
                    "documents after the pipeline": len(everything),
                    "distinct documents": len(distinct),
                    "share of distinct documents occurring once": f"{once / len(distinct):.1%}",
                    "mean length (characters)": f"{mean_chars:,.0f}",
                    "language": "English",
                }
            )
            + "\n"
            + table(["split", "configured share", "documents", "whitespace words"], split_rows)
            + f"\n**Free-text verdict: {verdict}** - {len(distinct):,} distinct documents "
            f"(template threshold: more than {OPEN_TEXT_DISTINCT}), mean "
            f"{mean_chars:,.0f} characters.\n"
        )
        if isinstance(spec, EventNotificationsSpec):
            agreement = sum(1 for t in everything if AGREEMENT_STATE in t.split("\n", 1)[0].upper())
            contents += (
                f"\n{agreement:,} of {len(everything):,} documents "
                f'({agreement / len(everything):.1%}) carry "{AGREEMENT_STATE}" in their title '
                "line: reports from radioactive-materials licensees, not plant events.\n"
            )
    else:
        contents = f"{UNVERIFIED} - no documents of this source in the finished corpus.\n"
    parts.append(section("Contents after the text pipeline", contents))

    pii = config.pii
    parts.append(
        section(
            "Use in FaultLine",
            kv_table(
                {
                    "intended role": "text-only pretraining corpus (M2), with its own val and "
                    "test split so loss is reported per source, never pooled",
                    "PII policy (ADR-0005)": f"emails masked: {pii.mask_emails}; phones masked: "
                    f"{pii.mask_phones} (pattern {pii.phone_pattern}); digit runs masked: "
                    f"{pii.mask_digits} (quantities are the technical content)",
                    "excluded from this source": _excluded(spec),
                    "not applicable": "turbines, channels, timezone, sampling resolution "
                    "(telemetry-only template fields)",
                }
            ),
        )
    )
    parts.append(
        section(
            "Caveats",
            "**From the provider.** none recorded in the specification.\n\n"
            "**Found during staging and inspection.** ADR-0016 in `docs/DECISIONS.md` carries "
            "every measurement behind this source's admission, route and exclusions.\n\n"
            f"**Known limits of this card.** Every field marked `{UNVERIFIED}` is an open "
            "question, not an absence of a problem.\n",
        )
    )
    parts.append(
        section(
            "Generation",
            kv_table(
                {
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline cards text",
                    "template": "docs/DATASET_CARD_TEMPLATE.md",
                    "generated from": "the manifest (staging), the finished corpus "
                    f"{config.io.corpus_name} (contents, verdict), the text pipeline "
                    "configuration (splits, PII)",
                    "hand-written": "identity and access route, copied from "
                    "configs/data/sources_text.yaml",
                }
            ),
        )
    )
    destination = paths.cards_dir / f"{source}.md"
    destination.write_text("".join(parts), encoding="utf-8", newline="\n")
    logger.info("%s: wrote %s", source, destination)
    return destination
