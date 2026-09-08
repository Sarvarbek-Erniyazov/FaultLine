"""Markdown reports for the text pipeline stages.

Every stage answers the same three questions in the same order: how many documents
went in and out, why the missing ones were dropped, and what the surviving
distribution looks like. The filter stage additionally prints a random sample of
*removed* documents, which is the only cheap way to notice a threshold that is
quietly deleting good text.
"""

from __future__ import annotations

from typing import Any

from faultline.config import RunMeta
from faultline.data.common.report import (
    counts_table,
    drop_reasons_table,
    header_block,
    kv_table,
    percentile_summary,
    section,
    table,
    truncate,
)
from faultline.data.common.stage import StageResult


def _samples_section(details: dict[str, Any], key: str, title: str, note: str) -> str:
    """Render a sample of documents as a numbered list.

    Args:
        details: Stage details dictionary.
        key: Key holding the list of sample strings.
        title: Section heading.
        note: Sentence explaining what the sample is for.

    Returns:
        A Markdown section, or a placeholder when no samples were collected.
    """
    samples: list[str] = list(details.get(key, []))
    if not samples:
        return section(title, "_(no samples collected)_")
    body = [note, ""]
    body += [f"{index}. `{truncate(text, 200)}`" for index, text in enumerate(samples, start=1)]
    return section(title, "\n".join(body))


def clean_report(meta: RunMeta, result: StageResult) -> str:
    """Render the cleaning stage report.

    Args:
        meta: Run identity.
        result: Result of the cleaning stage.

    Returns:
        A Markdown document.
    """
    parts = [header_block(meta, result.name, "Text pipeline - cleaning")]
    parts.append(section("Documents", counts_table([("clean", result.rows_in, result.rows_out)])))
    parts.append(section("Drop reasons", drop_reasons_table(result.counters, result.rows_in)))
    parts.append(
        section(
            "Characters",
            kv_table(
                {
                    "characters in": result.details.get("chars_in", 0),
                    "characters out": result.details.get("chars_out", 0),
                    "characters removed": result.details.get("chars_in", 0)
                    - result.details.get("chars_out", 0),
                }
            ),
        )
    )
    parts.append(
        section(
            "Document length after cleaning (characters)",
            percentile_summary(result.details.get("lengths", []), "length"),
        )
    )
    parts.append(
        _samples_section(
            result.details,
            "samples",
            "Sampled documents (before -> after)",
            "Random sample of cleaned documents, truncated to 200 characters.",
        )
    )
    return "".join(parts)


def filter_report(meta: RunMeta, result: StageResult) -> str:
    """Render the quality filtering stage report.

    Args:
        meta: Run identity.
        result: Result of the filtering stage.

    Returns:
        A Markdown document.
    """
    parts = [header_block(meta, result.name, "Text pipeline - quality filtering")]
    parts.append(section("Documents", counts_table([("filter", result.rows_in, result.rows_out)])))
    parts.append(
        section(
            "Thresholds applied",
            kv_table(result.details.get("thresholds", {})),
        )
    )
    parts.append(
        section(
            "Drop reasons (first failing rule)", drop_reasons_table(result.counters, result.rows_in)
        )
    )
    parts.append(
        section(
            "Document length, kept documents (characters)",
            percentile_summary(result.details.get("lengths", []), "length"),
        )
    )
    parts.append(
        section(
            "Alphabetic ratio, kept documents",
            percentile_summary(result.details.get("alpha_ratios", []), "alphabetic ratio"),
        )
    )
    parts.append(
        section(
            "Repeated-line ratio, kept documents",
            percentile_summary(result.details.get("repeated_ratios", []), "repeated-line ratio"),
        )
    )
    parts.append(
        _samples_section(
            result.details,
            "removed_samples",
            "Sampled removed documents",
            "Random sample of documents the filters dropped, truncated to 200 characters. "
            "Read these before trusting the thresholds.",
        )
    )
    return "".join(parts)


def dedup_report(meta: RunMeta, result: StageResult) -> str:
    """Render the deduplication stage report.

    Args:
        meta: Run identity.
        result: Result of the deduplication stage.

    Returns:
        A Markdown document.
    """
    parts = [header_block(meta, result.name, "Text pipeline - deduplication")]
    parts.append(section("Documents", counts_table([("dedup", result.rows_in, result.rows_out)])))
    parts.append(
        section(
            "Settings",
            kv_table(result.details.get("settings", {})),
        )
    )
    parts.append(
        section(
            "Duplicates",
            kv_table(
                {
                    "exact duplicates removed": result.counters.get("duplicate", 0),
                    "unique documents": result.rows_out,
                    "duplicate rate": (
                        result.counters.get("duplicate", 0) / result.rows_in
                        if result.rows_in
                        else 0.0
                    ),
                }
            ),
        )
    )
    parts.append(
        _samples_section(
            result.details,
            "duplicate_samples",
            "Sampled duplicate documents",
            "Random sample of documents removed as exact duplicates.",
        )
    )
    return "".join(parts)


def pii_report(meta: RunMeta, result: StageResult) -> str:
    """Render the PII scrubbing stage report.

    Args:
        meta: Run identity.
        result: Result of the PII stage.

    Returns:
        A Markdown document.
    """
    parts = [header_block(meta, result.name, "Text pipeline - PII scrubbing")]
    parts.append(section("Documents", counts_table([("pii", result.rows_in, result.rows_out)])))
    parts.append(
        section(
            "Policy (ADR-0005)",
            kv_table(result.details.get("policy", {})),
        )
    )
    parts.append(
        section(
            "Replacements",
            table(
                ["class", "replacements", "documents touched"],
                [
                    (
                        kind,
                        result.counters.get(kind, 0),
                        result.details.get("docs_touched", {}).get(kind, 0),
                    )
                    for kind in ("email", "phone", "digits")
                ],
            ),
        )
    )
    parts.append(
        _samples_section(
            result.details,
            "samples",
            "Sampled scrubbed documents",
            "Random sample of documents in which at least one replacement was made.",
        )
    )
    return "".join(parts)


def final_report(meta: RunMeta, result: StageResult) -> str:
    """Render the final corpus stage report.

    Args:
        meta: Run identity.
        result: Result of the final stage.

    Returns:
        A Markdown document.
    """
    parts = [header_block(meta, result.name, "Text pipeline - final corpus")]
    parts.append(section("Documents", counts_table([("final", result.rows_in, result.rows_out)])))
    parts.append(
        section(
            "Split assignment",
            table(
                ["split", "documents", "share", "shards"],
                [
                    (
                        split,
                        count,
                        f"{count / result.rows_out * 100:.2f}%" if result.rows_out else "n/a",
                        result.details.get("shards", {}).get(split, 0),
                    )
                    for split, count in sorted(result.details.get("splits", {}).items())
                ],
            ),
        )
    )
    parts.append(
        section(
            "Document length, final corpus (characters)",
            percentile_summary(result.details.get("lengths", []), "length"),
        )
    )
    parts.append(
        section(
            "Outputs",
            table(["file", "documents"], sorted(result.details.get("outputs", {}).items())),
        )
    )
    return "".join(parts)


#: Report renderer for each stage name.
RENDERERS = {
    "clean": clean_report,
    "filter": filter_report,
    "dedup": dedup_report,
    "pii": pii_report,
    "final": final_report,
}


def render(meta: RunMeta, result: StageResult) -> str:
    """Render the report belonging to a stage result.

    Args:
        meta: Run identity.
        result: Stage result to describe.

    Returns:
        A Markdown document.

    Raises:
        KeyError: If the stage has no registered renderer.
    """
    return RENDERERS[result.name](meta, result)
