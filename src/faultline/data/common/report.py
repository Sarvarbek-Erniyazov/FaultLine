"""Markdown building blocks shared by every stage report.

Reports are the audit trail of a pipeline run: a number that appears in a paper or
a README must be traceable to one of these tables. All helpers are pure functions
returning Markdown fragments.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import numpy as np

from faultline.config import RunMeta

PERCENTILES: tuple[int, ...] = (1, 5, 25, 50, 75, 95, 99)


def _fmt(value: Any) -> str:
    """Format a cell value for Markdown.

    Args:
        value: Any scalar.

    Returns:
        A compact string: thousands-separated integers, 4-significant-digit floats.
    """
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if value != value:  # NaN
            return "n/a"
        return f"{value:,.4g}"
    return str(value)


def header_block(meta: RunMeta, stage: str, title: str | None = None) -> str:
    """Render the standard report header identifying the run.

    Args:
        meta: Run identity.
        stage: Stage name.
        title: Optional document title; a default is derived from the stage name.

    Returns:
        A Markdown heading followed by the run identity table.
    """
    heading = title or f"{stage.capitalize()} stage report"
    rows = {
        "run_id": meta.run_id,
        "stage": stage,
        "config": meta.config_path,
        "config_hash": meta.config_hash,
        "git_sha": meta.git_sha,
        "created_at (UTC)": meta.created_at.isoformat(timespec="seconds"),
    }
    return f"# {heading}\n\n" + kv_table(rows)


def kv_table(
    mapping: Mapping[str, Any], key_header: str = "field", value_header: str = "value"
) -> str:
    """Render a two-column key/value table.

    Args:
        mapping: Rows to render, in insertion order.
        key_header: Header for the key column.
        value_header: Header for the value column.

    Returns:
        A Markdown table, or a placeholder line when the mapping is empty.
    """
    if not mapping:
        return "_(no entries)_\n"
    lines = [f"| {key_header} | {value_header} |", "| --- | --- |"]
    lines += [f"| {key} | {_fmt(value)} |" for key, value in mapping.items()]
    return "\n".join(lines) + "\n"


def table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Render an arbitrary Markdown table.

    Args:
        headers: Column headers.
        rows: Row values; each row must match the header length.

    Returns:
        A Markdown table, or a placeholder line when there are no rows.
    """
    body = [f"| {' | '.join(_fmt(cell) for cell in row)} |" for row in rows]
    if not body:
        return "_(no rows)_\n"
    head = f"| {' | '.join(headers)} |"
    sep = f"| {' | '.join('---' for _ in headers)} |"
    return "\n".join([head, sep, *body]) + "\n"


def counts_table(rows: Iterable[tuple[str, int, int]]) -> str:
    """Render before/after record counts with absolute and relative deltas.

    Args:
        rows: Tuples of ``(label, rows_in, rows_out)``.

    Returns:
        A Markdown table with dropped counts and retention percentages.
    """
    rendered: list[tuple[str, int, int, int, str]] = []
    for label, rows_in, rows_out in rows:
        retention = f"{rows_out / rows_in * 100:.2f}%" if rows_in else "n/a"
        rendered.append((label, rows_in, rows_out, rows_in - rows_out, retention))
    return table(["step", "in", "out", "dropped", "retained"], rendered)


def drop_reasons_table(counters: Mapping[str, int], total: int) -> str:
    """Render per-rule drop counts as a share of the stage input.

    Args:
        counters: Mapping from rule name to number of records it dropped.
        total: Number of records the stage read.

    Returns:
        A Markdown table sorted by descending drop count.
    """
    rows = [
        (name, count, f"{count / total * 100:.3f}%" if total else "n/a")
        for name, count in sorted(counters.items(), key=lambda item: (-item[1], item[0]))
    ]
    return table(["rule", "dropped", "share of input"], rows)


def percentile_summary(values: Sequence[float] | np.ndarray, label: str = "value") -> str:
    """Render count/mean plus the p1-p99 percentile spread of a numeric series.

    Args:
        values: Numeric values; NaNs are ignored.
        label: Name of the quantity, used in the first column.

    Returns:
        A Markdown table with one row per statistic.
    """
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return f"_(no finite values for {label})_\n"
    stats: dict[str, Any] = {
        "count": int(array.size),
        "mean": float(array.mean()),
        "std": float(array.std(ddof=0)),
        "min": float(array.min()),
    }
    for pct, value in zip(PERCENTILES, np.percentile(array, PERCENTILES), strict=True):
        stats[f"p{pct}"] = float(value)
    stats["max"] = float(array.max())
    return kv_table(stats, key_header=f"{label} statistic", value_header="value")


def top_values_table(
    counts: Mapping[str, int], n: int = 20, label: str = "value", max_len: int = 120
) -> str:
    """Render the ``n`` most frequent values of a categorical series.

    Args:
        counts: Mapping from value to frequency.
        n: Number of rows to keep.
        label: Header for the value column.
        max_len: Truncation length for long strings.

    Returns:
        A Markdown table sorted by descending frequency.
    """
    total = sum(counts.values())
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:n]
    rows = [
        (
            truncate(str(value), max_len),
            count,
            f"{count / total * 100:.2f}%" if total else "n/a",
        )
        for value, count in ordered
    ]
    return table([label, "count", "share"], rows)


def truncate(text: str, limit: int) -> str:
    """Shorten a string for table display, collapsing newlines.

    Args:
        text: Input string.
        limit: Maximum number of characters to keep.

    Returns:
        The escaped, single-line, possibly truncated string.
    """
    flat = text.replace("\n", "\\n").replace("|", "\\|")
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def section(title: str, body: str, level: int = 2) -> str:
    """Wrap a Markdown fragment in a heading.

    Args:
        title: Section title.
        body: Section body.
        level: Heading level.

    Returns:
        The heading followed by the body and a trailing blank line.
    """
    return f"\n{'#' * level} {title}\n\n{body.rstrip()}\n"
