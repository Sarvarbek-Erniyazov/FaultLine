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
                [
                    "source",
                    "members discovered",
                    "rows loaded",
                    "turbines",
                    "events",
                    "identical cross-file copies dropped",
                    "differing cross-file repeats left for the clean stage",
                ],
                [
                    (
                        source,
                        info.get("members", 0),
                        info.get("loaded", 0),
                        info.get("turbines", 0),
                        info.get("events", 0),
                        info.get("identical_copies_dropped", 0),
                        info.get("differing_copies_kept", 0),
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
    files = details.get("files", [])
    units = details.get("units", [])
    if files:
        repeated = [row for row in files if row[3] > row[5]]
        unequal = [row for row in files if not row[3] == row[4] == row[5]]
        joined = [row for row in units if row[2] > 1]
        sources = details.get("sources", {})
        copies = sum(info.get("identical_copies_dropped", 0) for info in sources.values())
        loaded = sum(info.get("loaded", 0) for info in sources.values())
        unit_rows = sum(row[3] for row in units)
        parts.append(
            section(
                "Row accounting per file",
                "Every SCADA file goes through the repeated-label rule: drop the rows null in "
                "every ingested channel, assert that no (label, column) then holds two "
                "distinct values, and collapse to one row per label. `rows_raw` is rows "
                "read, `rows_after_null_drop` is rows carrying any ingested value, "
                "`labels_distinct` is distinct labels read (label and station, where one "
                "file holds every turbine), `rows_out` is rows kept from that file. A file "
                "that does not repeat shows `rows_raw == labels_distinct`; a file whose three "
                "counts agree also had no row without an ingested value. The assertion held "
                "for every file below, or the run would have stopped.\n\n"
                "Where a loader joins several files into one unit -- a Hill of Towie month is "
                "three tables joined on (label, station) -- the files' `rows_out` describe "
                "the same rows three times and do not add up; the unit's joined rows do. The "
                "total below is over units.\n\n"
                + kv_table(
                    {
                        "files": len(files),
                        "files that repeat labels (rows_raw > labels_distinct)": len(repeated),
                        "files where the three counts agree": len(files) - len(unequal),
                        "rows_raw": sum(row[3] for row in files),
                        "rows_after_null_drop": sum(row[4] for row in files),
                        "units read": len(units),
                        "units joining several files": len(joined),
                        "rows_out, over units (after each unit's join)": unit_rows,
                        "identical cross-file copies dropped": copies,
                        "rows loaded (rows_out over units, less the copies)": loaded,
                        "rows_out over units less the copies equals rows loaded": (
                            unit_rows - copies == loaded
                        ),
                    }
                )
                + "\n"
                + (
                    "**Units that join several files**\n\n"
                    + table(["source", "unit", "files", "rows after the join"], joined)
                    + "\n"
                    if joined
                    else ""
                )
                + table(
                    [
                        "source",
                        "file",
                        "turbine",
                        "rows_raw",
                        "rows_after_null_drop",
                        "labels_distinct",
                        "rows_out",
                    ],
                    files,
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
    sentinels = {
        key.removeprefix("sentinel:"): value
        for key, value in result.counters.items()
        if key.startswith("sentinel:")
    }
    if sentinels:
        parts.append(
            section(
                "Missing-value codes per channel (sentinels, values set to NaN)",
                "Values the provider writes where it has no reading, listed per source in "
                "the configuration's `clean.sentinels` and removed before duplicates are "
                "resolved or bounds applied. A code is not a reading, so it is not counted "
                "as out of bounds below.\n\n" + drop_reasons_table(sentinels, result.rows_in),
            )
        )
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
    if details.get("split_spec"):
        parts.append(_splits_section(details))
    parts.append(
        section(
            "Outputs",
            table(["file", "rows"], sorted(details.get("outputs", {}).items())),
        )
    )
    return "".join(parts)


def _horizon_label(steps: int) -> str:
    minutes = steps * 10
    return f"{minutes // 60}h" if minutes % 60 == 0 else f"{minutes}min"


def _splits_section(details: dict[str, Any]) -> str:
    """The split specification, the leakage checks, and windows and events per split."""
    spec = details["split_spec"]
    horizons: list[int] = details.get("horizons_steps", [])
    windows: dict[tuple[str, str], dict[str, int]] = details.get("split_windows", {})
    events: dict[tuple[str, str], dict[str, int]] = details.get("split_events", {})
    checked: dict[str, int] = details.get("checked", {})
    keys = sorted(
        set(windows) | set(events), key=lambda k: (("train", "val", "test").index(k[0]), k[1])
    )
    body = kv_table(
        {
            "held out (every row test)": ", ".join(spec.get("holdout_sites", [])) or "none",
            "evaluation only (every row test)": ", ".join(spec.get("eval_only_sources", []))
            or "none",
            "train up to": spec["time"]["train_until"],
            "val up to": spec["time"]["val_until"],
            "after that": spec.get("late_period_split", "test"),
            "window": f"{spec['windows']['context_steps']} steps of context ending at t, "
            f"stride {spec['windows']['stride_steps']}; the horizon (t, t + H] inside t's split",
            "segments checked: none spans two splits": checked.get("segments", 0),
            "windows checked: no context or horizon crosses a split boundary": checked.get(
                "windows", 0
            ),
        }
    )
    body += (
        "\nSegments are cut where the split changes, and every window is re-checked from "
        "its timestamps alone: the split at its first context step and at the end of its "
        "horizon must equal the split at t. A violation stops the stage "
        "(`windows.LeakageError`), so the counts above are of windows that passed.\n"
    )
    for label_set in ("narrow", "broad"):
        rows = []
        for key in keys:
            counts = windows.get(key, {})
            cells: list[Any] = [
                key[0],
                key[1],
                counts.get("rows", 0),
                counts.get("segments", 0),
                events.get(key, {}).get(label_set, 0),
            ]
            for steps in horizons:
                column = f"{label_set}_within_{_horizon_label(steps)}"
                total = counts.get(f"windows {column}", 0)
                positive = counts.get(f"positive {column}", 0)
                share = f" ({positive / total * 100:.2f}%)" if total else ""
                cells += [total, f"{positive:,}{share}"]
            rows.append(tuple(cells))
        headers = ["split", "source", "rows", "segments", f"{label_set} events"]
        for steps in horizons:
            headers += [f"windows {_horizon_label(steps)}", f"positive {_horizon_label(steps)}"]
        body += f"\n**{label_set.capitalize()} label**\n\n" + table(headers, rows)
    return section("Splits: windows and events per split", body)


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
