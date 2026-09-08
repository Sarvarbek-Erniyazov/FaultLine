"""Markdown reports for the telemetry pipeline stages.

Where the text reports count documents, these count timesteps, turbines and holes.
The recurring question is coverage: which turbine-years are usable, which channels
are effectively absent, how much of the record is gaps, and how much of what the
model will read was imputed rather than measured.
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
    top_values_table,
)
from faultline.data.common.stage import StageResult


def _coverage_table(coverage: dict[str, float]) -> str:
    """Render per-channel coverage as a Markdown table.

    Args:
        coverage: Mapping from channel name to non-null fraction.

    Returns:
        A Markdown table sorted by ascending coverage, worst first.
    """
    rows = [
        (name, f"{value * 100:.2f}%")
        for name, value in sorted(coverage.items(), key=lambda item: item[1])
    ]
    return table(["channel", "non-null"], rows)


def ingest_report(meta: RunMeta, result: StageResult) -> str:
    """Render the ingest stage report.

    Args:
        meta: Run identity.
        result: Result of the ingest stage.

    Returns:
        A Markdown document.
    """
    details = result.details
    parts = [header_block(meta, result.name, "Telemetry pipeline - ingest")]
    parts.append(section("Rows", counts_table([("ingest", result.rows_in, result.rows_out)])))
    parts.append(
        section(
            "Sources",
            table(
                ["source", "members discovered", "members loaded", "turbines", "events"],
                [
                    (
                        source,
                        info.get("members", 0),
                        info.get("loaded", 0),
                        info.get("turbines", 0),
                        info.get("events", 0),
                    )
                    for source, info in sorted(details.get("sources", {}).items())
                ],
            ),
        )
    )
    parts.append(
        section(
            "Members by kind",
            table(
                ["kind", "members"],
                sorted(details.get("member_kinds", {}).items()),
            ),
        )
    )
    if details.get("not_implemented"):
        parts.append(
            section(
                "Adapters not yet implemented",
                "These sources were discovered but not loaded. This is expected at M0: a loader "
                "is written only once the raw inventory report confirms the member layout.\n\n"
                + table(
                    ["source", "reason"],
                    sorted(details["not_implemented"].items()),
                ),
            )
        )
    return "".join(parts)


def clean_report(meta: RunMeta, result: StageResult) -> str:
    """Render the cleaning stage report.

    Args:
        meta: Run identity.
        result: Result of the cleaning stage.

    Returns:
        A Markdown document.
    """
    details = result.details
    parts = [header_block(meta, result.name, "Telemetry pipeline - cleaning")]
    parts.append(section("Rows", counts_table([("clean", result.rows_in, result.rows_out)])))
    parts.append(
        section(
            "Timestamp handling",
            kv_table(
                {
                    "duplicate timestamps collapsed": result.counters.get(
                        "duplicate_timestamps", 0
                    ),
                    "unparseable timestamps dropped": result.counters.get(
                        "unparseable_timestamps", 0
                    ),
                    "grid rows inserted": result.counters.get("grid_rows_inserted", 0),
                    "grid resolution": details.get("freq", "unknown"),
                    "timezone assumed": details.get("timezone", "unknown"),
                }
            ),
        )
    )
    bounds = {
        key.removeprefix("bounds:"): value
        for key, value in result.counters.items()
        if key.startswith("bounds:")
    }
    parts.append(
        section(
            "Plausibility flags per channel (values set to NaN)",
            drop_reasons_table(bounds, result.rows_in),
        )
    )
    parts.append(
        section(
            "Channel coverage after cleaning",
            _coverage_table(details.get("coverage", {})),
        )
    )
    parts.append(
        section(
            "Per-turbine coverage",
            table(
                ["turbine", "rows", "first timestamp", "last timestamp", "mean coverage"],
                details.get("turbine_rows", []),
            ),
        )
    )
    return "".join(parts)


def filter_report(meta: RunMeta, result: StageResult) -> str:
    """Render the filtering stage report.

    Args:
        meta: Run identity.
        result: Result of the filtering stage.

    Returns:
        A Markdown document.
    """
    details = result.details
    parts = [header_block(meta, result.name, "Telemetry pipeline - filtering")]
    parts.append(section("Rows", counts_table([("filter", result.rows_in, result.rows_out)])))
    parts.append(section("Thresholds applied", kv_table(details.get("thresholds", {}))))
    parts.append(
        section(
            "Channels kept and dropped",
            table(
                ["channel", "non-null", "kept"],
                [
                    (name, f"{value * 100:.2f}%", name in details.get("channels_kept", []))
                    for name, value in sorted(details.get("coverage", {}).items())
                ],
            ),
        )
    )
    parts.append(
        section(
            "Segments",
            kv_table(
                {
                    "segments found": result.counters.get("segments_total", 0),
                    "segments kept": result.counters.get("segments_kept", 0),
                    "segments dropped (too short)": result.counters.get(
                        "segments_dropped_short", 0
                    ),
                    "rows dropped (unsegmented or short)": result.counters.get(
                        "rows_dropped_unsegmented", 0
                    ),
                }
            ),
        )
    )
    parts.append(
        section(
            "Segment length (grid steps)",
            percentile_summary(details.get("segment_lengths", []), "segment length"),
        )
    )
    return "".join(parts)


def final_report(meta: RunMeta, result: StageResult) -> str:
    """Render the final stage report.

    Args:
        meta: Run identity.
        result: Result of the final stage.

    Returns:
        A Markdown document.
    """
    details = result.details
    parts = [header_block(meta, result.name, "Telemetry pipeline - final")]
    parts.append(section("Rows", counts_table([("final", result.rows_in, result.rows_out)])))
    parts.append(
        section(
            "Imputation (each channel carries a companion mask column, ADR-0006)",
            table(
                ["channel", "steps imputed", "share of rows"],
                [
                    (
                        name,
                        count,
                        f"{count / result.rows_out * 100:.3f}%" if result.rows_out else "n/a",
                    )
                    for name, count in sorted(details.get("imputed", {}).items())
                ],
            ),
        )
    )
    parts.append(
        section(
            "Split assignment",
            table(
                ["split", "rows", "share"],
                [
                    (
                        split,
                        count,
                        f"{count / result.rows_out * 100:.2f}%" if result.rows_out else "n/a",
                    )
                    for split, count in sorted(details.get("splits", {}).items())
                ],
            ),
        )
    )
    parts.append(
        section(
            "Outputs",
            table(["file", "rows"], sorted(details.get("outputs", {}).items())),
        )
    )
    return "".join(parts)


def events_section(summary: dict[str, Any], top_messages: dict[str, int]) -> str:
    """Render the events summary shared by several reports.

    Args:
        summary: Output of :func:`faultline.data.telemetry.events.event_summary`.
        top_messages: Message frequencies for the top-N table.

    Returns:
        A Markdown section.
    """
    body = kv_table(
        {
            "events": summary.get("events", 0),
            "unique codes": summary.get("unique_codes", 0),
            "unique messages": summary.get("unique_messages", 0),
            "rows with non-empty message": f"{summary.get('free_text_fraction', 0.0) * 100:.2f}%",
            "events flagged as faults": summary.get("fault_events", 0),
            "events with unknown fault status": summary.get("unknown_fault_status", 0),
        }
    )
    if top_messages:
        body += "\n" + top_values_table(top_messages, n=20, label="message")
    return section("Events", body)


#: Report renderer for each stage name.
RENDERERS = {
    "ingest": ingest_report,
    "clean": clean_report,
    "filter": filter_report,
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
