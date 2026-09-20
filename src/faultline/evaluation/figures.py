"""The programme's figures, drawn from the committed record and nothing else.

No model is loaded, nothing is scored and nothing is retrained. Every value on every
figure is read from a tracked file under ``reports/data/`` -- the gate reports' JSON, the
per-step training logs' CSV -- or from the registered evaluation configuration that fixes
the smallest effect of interest. **No measured number is written into this module.** The
ledger adds one more source of the same kind: the repository's own history, asked by
``git log`` which commit wrote a given outcome section, so no hash is transcribed here
either. A figure whose source file is missing is skipped and named in the index, so a
partial record produces a partial set rather than a wrong one.

**The split's name.** Six of the seven outputs read the forward-in-time split. It is
*tested on 2022 onward (Kelmarsh through 2024, Penmanshiel 2022 only)* -- Penmanshiel's
test shard holds no year after 2022, so the span is never written "2022-2024". Every
figure drawn from it carries :data:`FORWARD_CAVEAT` in its caption: it is the
in-distribution temporal split at the training sites, and no result read from it is a
site-shift result.

**Rendering.** SVG is written by hand, as
:mod:`faultline.evaluation.text_curves` writes it, so the figures add no dependency. Marks
differ in shape and fill as well as colour, and every series carries a direct text label,
so nothing is identified by colour alone.
"""

from __future__ import annotations

import csv
import json
import math
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from faultline.data.common.report import kv_table, section, table
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

#: The caveat every figure drawn from the forward-in-time split carries.
FORWARD_CAVEAT = "forward-in-time, same sites; not a site-shift result"

#: How the forward-in-time split's span is named, everywhere.
FORWARD_SPAN = "tested on 2022 onward (Kelmarsh through 2024, Penmanshiel 2022 only)"

#: Categorical slots of the validated reference palette, on its light surface.
PALETTE: tuple[str, ...] = ("#2a78d6", "#eb6834", "#3f8f5b", "#8a5cd0", "#b5893a", "#c2475f")

INK, MUTED, GRID, SURFACE = "#1a1a19", "#5f5e58", "#e4e3dd", "#fcfcfb"
BAND = "#ece9f5"

#: Row pitch and panel geometry, in SVG user units.
ROW_HEIGHT = 21.0
PANEL_PAD = 30.0


@dataclass(frozen=True)
class Row:
    """One measured point with its interval, as a figure draws it.

    Attributes:
        label: The series name, written beside the mark.
        value: The point estimate.
        low: Lower bound of the 95% interval.
        high: Upper bound of the 95% interval.
        colour: Mark colour.
        hollow: Draw the mark unfilled, for a secondary or control series.
        note: A short verdict written at the right of the row, or empty.
    """

    label: str
    value: float
    low: float
    high: float
    colour: str = PALETTE[0]
    hollow: bool = False
    note: str = ""


@dataclass(frozen=True)
class Panel:
    """A group of rows under one heading.

    Attributes:
        title: The heading written above the rows.
        rows: The rows, drawn top to bottom in order.
    """

    title: str
    rows: list[Row]


@dataclass(frozen=True)
class Marker:
    """A vertical reference line.

    Attributes:
        value: Where on the value axis the line sits.
        label: The text written at the top of the line.
        dashed: Draw it dashed rather than solid.
    """

    value: float
    label: str
    dashed: bool = False


@dataclass
class Figure:
    """One built output.

    Attributes:
        stem: File stem, without extension.
        title: The figure's title.
        sentence: The one sentence the figure supports.
        sources: Repository-relative source paths.
        svg: The rendered SVG, or ``None`` for a Markdown-only output.
        markdown: Extra Markdown body, for the ledger.
        caption: The caption written under the figure in the index.
        missing: Source paths that were wanted and not found.
    """

    stem: str
    title: str
    sentence: str
    sources: list[str]
    svg: str | None = None
    markdown: str = ""
    caption: str = ""
    missing: list[str] = field(default_factory=list)


class RecordSet:
    """The tracked record, read once and handed to every figure.

    Attributes:
        paths: Resolved project paths.
        missing: Record names asked for and not found, in ask order.
    """

    def __init__(self, paths: ProjectPaths) -> None:
        """Bind the record set to a repository.

        Args:
            paths: Resolved project paths.
        """
        self.paths = paths
        self.missing: list[str] = []
        self._cache: dict[str, Any] = {}

    def json(self, name: str) -> Any | None:
        """Read a tracked JSON record under ``reports/data/``.

        Args:
            name: The file name, with extension.

        Returns:
            The parsed record, or ``None`` when the file is absent.
        """
        if name in self._cache:
            return self._cache[name]
        path = self.paths.data_reports_dir / name
        if not path.is_file():
            self.missing.append(f"reports/data/{name}")
            return None
        parsed = json.loads(path.read_text(encoding="utf-8"))
        self._cache[name] = parsed
        return parsed

    def steps(self, relative: str) -> list[dict[str, str]] | None:
        """Read a per-step training log under ``reports/data/``.

        Args:
            relative: Path relative to ``reports/data/``.

        Returns:
            The CSV rows, or ``None`` when the file is absent.
        """
        path = self.paths.data_reports_dir / relative
        if not path.is_file():
            self.missing.append(f"reports/data/{relative}")
            return None
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def config(self, relative: str) -> Any | None:
        """Read a tracked YAML configuration.

        Args:
            relative: Path relative to the repository root.

        Returns:
            The parsed configuration, or ``None`` when the file is absent.
        """
        path = self.paths.repo_root / relative
        if not path.is_file():
            self.missing.append(relative)
            return None
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def text(self, relative: str) -> str | None:
        """Read a tracked text file.

        Args:
            relative: Path relative to the repository root.

        Returns:
            The file's text, or ``None`` when it is absent.
        """
        path = self.paths.repo_root / relative
        if not path.is_file():
            self.missing.append(relative)
            return None
        return path.read_text(encoding="utf-8")


def interval(block: Any) -> tuple[float, float, float]:
    """Point estimate and 95% bounds from a recorded AUPRC interval.

    Args:
        block: A record block carrying ``auprc``, ``low`` and ``high``.

    Returns:
        The point estimate, the lower bound and the upper bound.
    """
    return float(block["auprc"]), float(block["low"]), float(block["high"])


def delta(block: Any) -> tuple[float, float, float]:
    """Point estimate and 95% bounds from a recorded paired delta.

    Args:
        block: A record block carrying ``delta``, ``low`` and ``high``.

    Returns:
        The point estimate, the lower bound and the upper bound.
    """
    return float(block["delta"]), float(block["low"]), float(block["high"])


def _escape(value: str) -> str:
    """Escape text for an SVG text node.

    Args:
        value: The text.

    Returns:
        The text with XML metacharacters replaced.
    """
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mark(cx: float, cy: float, colour: str, hollow: bool) -> str:
    """One point mark: filled disc, or a hollow ring for a control series.

    Args:
        cx: Centre x.
        cy: Centre y.
        colour: Mark colour.
        hollow: Draw a ring instead of a disc.

    Returns:
        The SVG fragment.
    """
    if hollow:
        return (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{SURFACE}" '
            f'stroke="{colour}" stroke-width="2"/>'
        )
    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.5" fill="{colour}" '
        f'stroke="{SURFACE}" stroke-width="1.5"/>'
    )


def _ticks(low: float, high: float) -> list[float]:
    """Choose round axis ticks spanning a range.

    Args:
        low: Range minimum.
        high: Range maximum.

    Returns:
        Tick values in ascending order, at least two of them.
    """
    span = high - low
    if span <= 0:
        return [low]
    raw = span / 6.0
    power = 10.0 ** math.floor(math.log10(raw))
    step = min((m * power for m in (1.0, 2.0, 2.5, 5.0, 10.0) if m * power >= raw), default=raw)
    first = math.ceil(low / step) * step
    out, value = [], first
    while value <= high + step * 1e-6:
        out.append(round(value, 10))
        value += step
    return out or [low, high]


def render_intervals(
    panels: Sequence[Panel],
    *,
    title: str,
    subtitle: str,
    markers: Sequence[Marker] = (),
    band: tuple[float, float] | None = None,
    band_label: str = "",
    value_label: str,
    label_width: float = 210.0,
    note_width: float = 96.0,
) -> str:
    """Draw grouped point-and-interval rows against a shared horizontal value axis.

    Args:
        panels: The groups, drawn top to bottom.
        title: The figure title.
        subtitle: One line under the title.
        markers: Vertical reference lines.
        band: A shaded value band, as ``(low, high)``.
        band_label: Text written under the band's upper edge.
        value_label: The value axis label.
        label_width: Width reserved for row labels.
        note_width: Width reserved for row notes.

    Returns:
        A standalone SVG document.
    """
    rows_total = sum(len(p.rows) for p in panels)
    # A continuation panel carries no title of its own: it sits under one that does.
    head = 58.0 if title else 24.0
    height = head + 18.0 + rows_total * ROW_HEIGHT + len(panels) * PANEL_PAD + 34.0
    width = label_width + 430.0 + note_width
    left, right = label_width, width - note_width
    values = [v for p in panels for r in p.rows for v in (r.low, r.high, r.value)]
    values += [m.value for m in markers]
    if band:
        values += [band[0], band[1]]
    low, high = min(values), max(values)
    pad = (high - low) * 0.08 or 0.01
    low, high = low - pad, high + pad

    def x(value: float) -> float:
        return left + (value - low) / (high - low) * (right - left)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="system-ui, sans-serif" '
        'font-size="12">',
        f"<title>{_escape(title or panels[0].title)}</title>",
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="{SURFACE}"/>',
    ]
    if title:
        out.append(
            f'<text x="16" y="24" fill="{INK}" font-size="15" font-weight="600">'
            f"{_escape(title)}</text>"
        )
    if subtitle:
        out.append(f'<text x="16" y="43" fill="{MUTED}">{_escape(subtitle)}</text>')
    top, bottom = head, height - 34.0
    if band:
        out.append(
            f'<rect x="{x(band[0]):.1f}" y="{top:.1f}" width="{x(band[1]) - x(band[0]):.1f}" '
            f'height="{bottom - top:.1f}" fill="{BAND}"/>'
        )
        if band_label:
            out.append(
                f'<text x="{x(band[1]) + 4:.1f}" y="{top + 11:.1f}" fill="{MUTED}" '
                f'font-size="11">{_escape(band_label)}</text>'
            )
    for tick in _ticks(low, high):
        out.append(
            f'<line x1="{x(tick):.1f}" x2="{x(tick):.1f}" y1="{top:.1f}" y2="{bottom:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
            f'<text x="{x(tick):.1f}" y="{bottom + 16:.1f}" fill="{MUTED}" '
            f'text-anchor="middle">{tick:.4g}</text>'
        )
    for marker in markers:
        dash = ' stroke-dasharray="4 3"' if marker.dashed else ""
        out.append(
            f'<line x1="{x(marker.value):.1f}" x2="{x(marker.value):.1f}" y1="{top - 6:.1f}" '
            f'y2="{bottom:.1f}" stroke="{INK}" stroke-width="1.5"{dash}/>'
            f'<text x="{x(marker.value):.1f}" y="{top - 10:.1f}" fill="{INK}" font-size="11" '
            f'text-anchor="middle">{_escape(marker.label)}</text>'
        )
    y = top + 8.0
    for panel in panels:
        y += 14.0
        out.append(
            f'<text x="16" y="{y:.1f}" fill="{INK}" font-size="12" font-weight="600">'
            f"{_escape(panel.title)}</text>"
        )
        y += 8.0
        for row in panel.rows:
            y += ROW_HEIGHT
            centre = y - ROW_HEIGHT / 2 + 4
            out.append(
                f'<text x="{left - 10:.1f}" y="{centre:.1f}" fill="{INK}" '
                f'text-anchor="end">{_escape(row.label)}</text>'
                f'<line x1="{x(row.low):.1f}" x2="{x(row.high):.1f}" '
                f'y1="{centre - 4:.1f}" y2="{centre - 4:.1f}" stroke="{row.colour}" '
                'stroke-width="2" stroke-linecap="round"/>'
            )
            out.append(_mark(x(row.value), centre - 4, row.colour, row.hollow))
            if row.note:
                out.append(
                    f'<text x="{right + 10:.1f}" y="{centre:.1f}" fill="{MUTED}" '
                    f'font-size="11">{_escape(row.note)}</text>'
                )
        y += PANEL_PAD - 22.0
    out.append(
        f'<text x="{(left + right) / 2:.0f}" y="{height - 8:.0f}" fill="{MUTED}" '
        f'text-anchor="middle">{_escape(value_label)}</text>'
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


@dataclass(frozen=True)
class Series:
    """A labelled curve for the training-diagnostics figure.

    Attributes:
        label: The series name.
        points: ``(x, y)`` pairs in x order.
        colour: Line colour.
        dashed: Draw the line dashed.
    """

    label: str
    points: list[tuple[float, float]]
    colour: str
    dashed: bool = False


def render_curves(
    left_series: Sequence[Series],
    right_series: Sequence[Series],
    *,
    title: str,
    subtitle: str,
    left_title: str,
    right_title: str,
    left_x_label: str,
    right_x_label: str,
    left_marker: tuple[float, str] | None = None,
    right_band: tuple[float, float, str] | None = None,
) -> str:
    """Draw two line panels side by side.

    Args:
        left_series: Curves for the left panel.
        right_series: Curves for the right panel.
        title: The figure title.
        subtitle: One line under the title.
        left_title: Heading over the left panel.
        right_title: Heading over the right panel.
        left_x_label: Left panel's x-axis label.
        right_x_label: Right panel's x-axis label.
        left_marker: A horizontal reference line on the left panel, as ``(y, label)``.
        right_band: A shaded horizontal band on the right panel, as ``(low, high, label)``.

    Returns:
        A standalone SVG document.
    """
    width, height = 900.0, 400.0
    top, bottom = 84.0, height - 52.0
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="system-ui, sans-serif" '
        'font-size="12">',
        f"<title>{_escape(title)}</title>",
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="{SURFACE}"/>',
        f'<text x="16" y="24" fill="{INK}" font-size="15" font-weight="600">'
        f"{_escape(title)}</text>",
        f'<text x="16" y="43" fill="{MUTED}">{_escape(subtitle)}</text>',
    ]
    panels: list[tuple[Sequence[Series], float, float, str, str, Any, Any]] = [
        (left_series, 54.0, 430.0, left_title, left_x_label, left_marker, None),
        (right_series, 508.0, 884.0, right_title, right_x_label, None, right_band),
    ]
    for series, left, right, heading, x_label, marker, band in panels:
        if not series:
            continue
        xs = [p[0] for s in series for p in s.points]
        ys = [p[1] for s in series for p in s.points]
        if marker:
            ys.append(marker[0])
        if band:
            ys += [band[0], band[1]]
        x_low, x_high = min(xs), max(xs)
        y_low, y_high = min(ys), max(ys)
        y_pad = (y_high - y_low) * 0.1 or 0.01
        y_low, y_high = y_low - y_pad, y_high + y_pad

        def px(
            value: float,
            left: float = left,
            right: float = right,
            lo: float = x_low,
            hi: float = x_high,
        ) -> float:
            return left + (value - lo) / (hi - lo or 1.0) * (right - left)

        def py(value: float, lo: float = y_low, hi: float = y_high) -> float:
            return top + (hi - value) / (hi - lo) * (bottom - top)

        out.append(
            f'<text x="{left:.0f}" y="{top - 16:.0f}" fill="{INK}" font-weight="600">'
            f"{_escape(heading)}</text>"
        )
        if band:
            out.append(
                f'<rect x="{left:.1f}" y="{py(band[1]):.1f}" width="{right - left:.1f}" '
                f'height="{py(band[0]) - py(band[1]):.1f}" fill="{BAND}"/>'
                f'<text x="{right - 4:.1f}" y="{py(band[1]) + 12:.1f}" fill="{MUTED}" '
                f'font-size="11" text-anchor="end">{_escape(band[2])}</text>'
            )
        for tick in _ticks(y_low, y_high):
            out.append(
                f'<line x1="{left:.1f}" x2="{right:.1f}" y1="{py(tick):.1f}" '
                f'y2="{py(tick):.1f}" stroke="{GRID}" stroke-width="1"/>'
                f'<text x="{left - 8:.1f}" y="{py(tick) + 4:.1f}" fill="{MUTED}" '
                f'text-anchor="end">{tick:.4g}</text>'
            )
        for tick in _ticks(x_low, x_high):
            out.append(
                f'<text x="{px(tick):.1f}" y="{bottom + 16:.1f}" fill="{MUTED}" '
                f'text-anchor="middle">{tick:.0f}</text>'
            )
        if marker:
            out.append(
                f'<line x1="{left:.1f}" x2="{right:.1f}" y1="{py(marker[0]):.1f}" '
                f'y2="{py(marker[0]):.1f}" stroke="{INK}" stroke-width="1.5" '
                'stroke-dasharray="5 3"/>'
                f'<text x="{left + 6:.1f}" y="{py(marker[0]) - 5:.1f}" fill="{INK}" '
                f'font-size="11">{_escape(marker[1])}</text>'
            )
        for index, curve in enumerate(series):
            dash = ' stroke-dasharray="5 3"' if curve.dashed else ""
            path = " ".join(f"{px(p[0]):.1f},{py(p[1]):.1f}" for p in curve.points)
            out.append(
                f'<polyline points="{path}" fill="none" stroke="{curve.colour}" '
                f'stroke-width="1.8" stroke-linejoin="round"{dash}/>'
            )
            end = curve.points[-1]
            out.append(
                f'<text x="{left + 8:.1f}" y="{top + 14 + index * 14:.1f}" '
                f'fill="{curve.colour}" font-size="11">{_escape(curve.label)}</text>'
                if len(series) > 3
                else f'<text x="{px(end[0]) + 6:.1f}" y="{py(end[1]) + 4:.1f}" '
                f'fill="{curve.colour}" font-size="11">{_escape(curve.label)}</text>'
            )
        out.append(
            f'<text x="{(left + right) / 2:.0f}" y="{height - 14:.0f}" fill="{MUTED}" '
            f'text-anchor="middle">{_escape(x_label)}</text>'
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def build_f4(records: RecordSet) -> Figure | None:
    """F4: the H1/H1' mechanism, one panel per seed.

    Args:
        records: The record set.

    Returns:
        The figure, or ``None`` when a source record is missing.
    """
    gate = records.json("h1_gate_v0_20260919.json")
    readout = records.json("readout_v0_20260920.json")
    controls = records.json("h1_controls_v0_20260918.json")
    bag = records.json("bag_of_tokens_v0_20260917.json")
    if gate is None or readout is None or controls is None or bag is None:
        return None
    tel_bag = interval(bag["rows"]["stride 12"]["bag"])
    status_bag = interval(controls["rows"]["status_only_R0"]["pooled"]["control"])
    base = float(gate["B1"]["1"]["joint"]["base_rate"])
    panels = []
    for seed in sorted(gate["B1"]):
        cell, read = gate["B1"][seed], readout["B1"][seed]
        rows = [
            Row("tel_only (a)", *interval(cell["tel_only"]), PALETTE[0]),
            Row("joint (a)", *interval(cell["joint"]), PALETTE[1]),
            Row("telemetry bag-of-tokens", *tel_bag, PALETTE[4]),
            Row("status-only bag-of-tokens", *status_bag, PALETTE[5]),
            Row("(d) joint, text-aware", *interval(read["d_joint"]), PALETTE[2]),
            Row(
                "(d) random-init backbone",
                *interval(readout["B7"][seed]["d_rand"]),
                PALETTE[3],
                hollow=True,
                note="gate floor",
            ),
            Row(
                "(d) tel_only backbone",
                *interval(readout["B2"][seed]["d_ctrl"]),
                PALETTE[3],
                hollow=True,
                note="collapsed rows",
            ),
        ]
        panels.append(Panel(f"seed {seed}", rows))
    svg = render_intervals(
        panels,
        title="F4. The text carries the signal; the read-out decides whether it is reached",
        subtitle=f"AUPRC with 95% block-bootstrap intervals, {FORWARD_SPAN}",
        markers=[Marker(base, f"base rate {base:.4f}")],
        value_label="AUPRC (higher is better)",
    )
    return Figure(
        stem="fig4_readout_mechanism",
        title="F4. The H1/H1' mechanism",
        sentence=(
            "The text carries the signal, the last-position read-out could not reach it, the "
            "text-aware read-out can, and the result lands level with counting the strings."
        ),
        sources=[
            "reports/data/h1_gate_v0_20260919.json",
            "reports/data/h1_controls_v0_20260918.json",
            "reports/data/readout_v0_20260920.json",
            "reports/data/bag_of_tokens_v0_20260917.json",
        ],
        svg=svg,
        caption=(
            "Design (a) is the registered last-position probe; design (d) is ADR-0026's "
            "text-aware read-out. The two hollow rows are (d)'s controls: the random-init "
            "backbone is the floor the gate had to clear, and the telemetry-only backbone, whose "
            f"text embedding rows collapsed onto one shared vector, is read with the same head. "
            f"{FORWARD_CAVEAT}."
        ),
    )


def build_f1(records: RecordSet) -> Figure | None:
    """F1: the site-shift gate on all three axes.

    Args:
        records: The record set.

    Returns:
        The figure, or ``None`` when a source record is missing.
    """
    replication = records.json("seed_replication_v0_20260917.json")
    axis = records.json("axis_gate_v0_20260918.json")
    if replication is None or axis is None:
        return None
    towie_rows = []
    for entry in replication["trained"]:
        point, low, high = interval(entry["held_out"])
        line = float(entry["held_out"]["base_rate"])
        towie_rows.append(
            Row(
                f"seed {entry['seed']}",
                point,
                low,
                high,
                PALETTE[0],
                note="clears" if low > line else "does not clear",
            )
        )
    towie_line = float(replication["trained"][0]["held_out"]["base_rate"])

    def axis_rows(name: str, colour: str) -> tuple[list[Row], float]:
        rows, line = [], 0.0
        for row in axis["rows"]:
            if row["axis"] != name or not row["gating"]:
                continue
            point, low, high = interval(row["interval"])
            line = float(row["interval"]["base_rate"])
            rows.append(
                Row(
                    f"seed {row['seed']}",
                    point,
                    low,
                    high,
                    colour,
                    note="clears" if row["verdict"]["evaluable"] else "does not clear",
                )
            )
        return rows, line

    care_rows, care_line = axis_rows("care", PALETTE[1])
    temporal_rows, temporal_line = axis_rows("temporal", PALETTE[2])
    parts = [
        render_intervals(
            [Panel("Hill of Towie: held-out site, same country, different OEM", towie_rows)],
            title="F1. Two pre-registered site-shift negatives, and the one evaluable axis",
            subtitle=(
                "AUPRC with 95% block-bootstrap intervals. Each axis has its own value scale "
                "and its own base rate: the three are never compared by eye."
            ),
            markers=[Marker(towie_line, f"base rate {towie_line:g}")],
            value_label="AUPRC on Hill of Towie (higher is better)",
        ),
        render_intervals(
            [Panel("CARE: three anonymised farms, other manufacturers", care_rows)],
            title="",
            subtitle="",
            markers=[Marker(care_line, f"base rate {care_line:.6g}")],
            value_label="AUPRC on CARE (higher is better)",
        ),
        render_intervals(
            [Panel(f"Forward in time at the training sites: {FORWARD_SPAN}", temporal_rows)],
            title="",
            subtitle="",
            markers=[Marker(temporal_line, f"base rate {temporal_line:g}")],
            value_label="AUPRC on the forward-in-time split (higher is better)",
        ),
    ]
    svg = stack(parts)
    return Figure(
        stem="fig1_site_shift",
        title="F1. The site-shift gate",
        sentence="Two pre-registered site-shift negatives; one evaluable axis.",
        sources=[
            "reports/data/seed_replication_v0_20260917.json",
            "reports/data/axis_gate_v0_20260918.json",
        ],
        svg=svg,
        caption=(
            "A seed clears when its 95% lower bound is strictly above the scored set's own base "
            "rate. Hill of Towie clears on one seed of three and CARE on none, so neither axis "
            "is evaluable; the forward-in-time split clears on all three. The three base rates "
            "differ by more than a factor of thirty, so each panel is drawn on its own value "
            "scale against its own base-rate line, and the three are never compared by eye."
        ),
    )


def build_f3(records: RecordSet) -> Figure | None:
    """F3: every paired comparison in the record, as one forest.

    Args:
        records: The record set.

    Returns:
        The figure, or ``None`` when a source record is missing.
    """
    replication = records.json("seed_replication_v0_20260917.json")
    gate = records.json("h1_gate_v0_20260919.json")
    readout = records.json("readout_v0_20260920.json")
    rule = records.config("configs/eval/readout_v0.yaml")
    if replication is None or gate is None or readout is None or rule is None:
        return None
    effect = float(rule["rule"]["smallest_effect"])

    control_rows = [
        Row(f"trained {entry['seed']} vs random {index + 1}", *delta(cell), PALETTE[0])
        for entry in replication["trained"]
        for index, cell in enumerate(entry["paired"])
    ]
    bag_rows = [
        Row(f"seed {entry['seed']}", *delta(entry["versus_bag_of_tokens"]), PALETTE[4])
        for entry in replication["trained"]
    ]
    h1_rows = [
        Row(f"seed {seed}", *delta(gate["B1"][seed]["delta"]), PALETTE[1])
        for seed in sorted(gate["B1"])
    ]
    decomposition_rows = []
    for seed in sorted(gate["B2"]):
        cell = gate["B2"][seed]
        decomposition_rows.append(
            Row(f"seed {seed}: joint - (iii)", *delta(cell["joint_minus_iii"]), PALETTE[2])
        )
        decomposition_rows.append(
            Row(
                f"seed {seed}: (iii) - tel_only",
                *delta(cell["iii_minus_tel_only"]),
                PALETTE[5],
            )
        )
    gate_rows = [
        Row(name.replace("_", " vs "), *delta(readout["G"][name]), PALETTE[3])
        for name in sorted(readout["G"])
    ]
    prime_rows = [
        Row(f"seed {seed}", *delta(readout["B1"][seed]["delta"]), PALETTE[2])
        for seed in sorted(readout["B1"])
    ]
    panels = [
        Panel("ADR-0024: trained backbone vs random init (nine cells)", control_rows),
        Panel("ADR-0024: probe vs telemetry bag-of-tokens", bag_rows),
        Panel("H1 (ADR-0025): joint vs tel_only, last-position read-out", h1_rows),
        Panel("H1 decomposition (B2): pretraining, and the window change", decomposition_rows),
        Panel("H1' gate (ADR-0026): joint vs random init, text-aware read-out", gate_rows),
        Panel("H1' (ADR-0026): joint vs tel_only, text-aware read-out", prime_rows),
    ]
    svg = render_intervals(
        panels,
        title="F3. What this evaluation could and could not resolve",
        subtitle=(f"Paired block-bootstrap deltas with 95% intervals, {FORWARD_SPAN}"),
        markers=[Marker(0.0, "no difference")],
        band=(-effect, effect),
        band_label=f"+/-{effect:g}, the smallest effect of interest",
        value_label="paired difference in AUPRC",
        label_width=250.0,
    )
    return Figure(
        stem="fig3_paired_deltas",
        title="F3. Every paired comparison in the record",
        sentence="What this evaluation could and could not resolve.",
        sources=[
            "reports/data/seed_replication_v0_20260917.json",
            "reports/data/h1_gate_v0_20260919.json",
            "reports/data/readout_v0_20260920.json",
            "configs/eval/readout_v0.yaml",
        ],
        svg=svg,
        caption=(
            "Every model-versus-model comparison in the record is paired on the same resampled "
            "blocks. The shaded band is the registered smallest effect of interest. The H1 "
            "cluster sits inside it on all three seeds, which is what INCONCLUSIVE means here; "
            "the H1' cluster sits wholly outside it, as does its nine-cell instrument gate. "
            f"{FORWARD_CAVEAT}."
        ),
    )


def build_ledger(records: RecordSet) -> Figure | None:
    """The gate ledger: one row per pre-registered gate, read from ``DECISIONS.md``.

    A rule's commit is taken from the sentence that asserts it, because the rule was
    committed before the run and its own section can therefore name it: the record's
    ``Commit:`` block, or a sentence saying the rule was *registered in* it. An outcome's
    commit is not asserted anywhere -- the commit that writes an outcome cannot cite its
    own hash -- so it is found instead by asking ``git log`` which commit added that
    outcome's heading to ``DECISIONS.md``. An empty cell means the log found no such
    commit, never that none exists.

    Args:
        records: The record set.

    Returns:
        The ledger, or ``None`` when ``DECISIONS.md`` is missing.
    """
    text = records.text(DECISIONS)
    if text is None:
        return None
    heads = list(re.finditer(r"^## (ADR-\d{4}) (.+)$", text, flags=re.MULTILINE))
    rows, gates = [], []
    for index, head in enumerate(heads):
        number = head.group(1)
        if not FIRST_GATE <= number <= LAST_GATE:
            continue
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        body = text[head.end() : end]
        outcome = _own_outcome(body)
        heading = outcome.group(1) if outcome else ""
        verdict = heading.split("--", 1)[1].strip() if "--" in heading else heading.strip()
        status = re.search(r"\*\*Status:\*\*[^\n]*?((?:pre-)?registered \d{4}-\d{2}-\d{2})", body)
        rows.append(
            [
                number,
                _shorten(head.group(2)),
                status.group(1) if status else "-",
                _cell(_registering_hash(body)),
                _shorten(verdict) or "-",
                _cell(_writing_commit(records.paths.repo_root, heading)),
            ]
        )
        gates.append(number)
    if not gates:
        return None
    return Figure(
        stem="ledger_gates",
        title="Ledger. The pre-registered gates",
        sentence="Every rule was committed before the run it governs.",
        sources=[DECISIONS],
        markdown=table(
            ["ADR", "question", "registered", "registering commit", "outcome", "outcome commit"],
            rows,
        ),
        caption=(
            f"{len(gates)} gates, {gates[0]} through {gates[-1]}, each read from its section of "
            "`docs/DECISIONS.md`. The rule was written into that file and committed in its own "
            "commit before the run it governs; the outcome was written under the rule "
            "afterwards. The outcome commit is the commit that wrote the outcome section, "
            "found by log rather than self-cited."
        ),
    )


#: The decision record the ledger reads, and asks the log about.
DECISIONS = "docs/DECISIONS.md"

#: The first and last gate the ledger reports, by ADR number.
FIRST_GATE, LAST_GATE = "ADR-0021", "ADR-0026"

#: A backticked commit hash.
_HASH = re.compile(r"`([0-9a-f]{7,40})`")

#: A line that asserts where a rule was registered.
_REGISTERED = re.compile(r"regist\w*\s+(?:in|at)\b|fixed in commit", re.IGNORECASE)

#: A line holding a backticked hash.
_HASH_LINE = re.compile(r"^[^\n]*`[0-9a-f]{7,40}`[^\n]*$", re.MULTILINE)


def _own_outcome(body: str) -> re.Match[str] | None:
    """The ADR's own outcome heading, skipping any addendum's.

    Args:
        body: The ADR section's Markdown.

    Returns:
        The heading match, or ``None`` when the section records no outcome.
    """
    for found in re.finditer(r"^### ((?:Outcome|Result)[^\n]*)$", body, flags=re.MULTILINE):
        if "addendum" not in found.group(1).lower():
            return found
    return None


def _registering_hash(body: str) -> str:
    """The commit that registered a rule, as its own section asserts it.

    Args:
        body: The ADR section's Markdown.

    Returns:
        The hash, or an empty string when the section asserts none.
    """
    block = re.search(r"\*\*Commit:\*\*(.*?)(?:\n\n|\Z)", body, flags=re.DOTALL)
    if block:
        found = _HASH.search(block.group(1))
        if found:
            return found.group(1)
    for line in _HASH_LINE.findall(body):
        if _REGISTERED.search(line):
            found = _HASH.search(line)
            if found:
                return found.group(1)
    return ""


def _writing_commit(repo_root: Path, heading: str) -> str:
    """The commit that wrote an outcome section, as the repository's history records it.

    The heading line is the section's fingerprint -- it carries the date and the verdict --
    so the commit that added it is the commit that wrote the outcome. It is found by
    pickaxe over ``DECISIONS.md``, and the oldest match is taken: the commit that
    introduced the line rather than a later one that moved it.

    Args:
        repo_root: The repository to ask.
        heading: The outcome heading, without its ``###`` marker.

    Returns:
        The abbreviated hash, or an empty string when the section records no outcome, the
        log names no commit, or git cannot be run.
    """
    if not heading:
        return ""
    command = ["git", "log", "--reverse", "--format=%h", f"-S### {heading}", "--", DECISIONS]
    try:
        completed = subprocess.run(
            command,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        logger.warning("ledger: git log could not be run; the outcome commit is left empty")
        return ""
    if completed.returncode != 0:
        logger.warning("ledger: git log failed; the outcome commit is left empty")
        return ""
    found = completed.stdout.split()
    return found[0] if found else ""


def _cell(value: str) -> str:
    """Format a hash for a table cell.

    Args:
        value: The hash, possibly empty.

    Returns:
        The backticked hash, or a dash.
    """
    return f"`{value}`" if value else "-"


def _shorten(value: str, limit: int = 96) -> str:
    """Collapse a heading to one short line.

    Args:
        value: The heading text.
        limit: Maximum length before truncation.

    Returns:
        The shortened text.
    """
    flat = " ".join(value.replace("|", "/").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "..."


def build_f2(records: RecordSet) -> Figure | None:
    """F2: the probe ladder on the forward-in-time split.

    Args:
        records: The record set.

    Returns:
        The figure, or ``None`` when a source record is missing.
    """
    replication = records.json("seed_replication_v0_20260917.json")
    controls = records.json("h1_controls_v0_20260918.json")
    bag = records.json("bag_of_tokens_v0_20260917.json")
    if replication is None or controls is None or bag is None:
        return None
    tel_bag = interval(bag["rows"]["stride 12"]["bag"])
    status_bag = interval(controls["rows"]["status_only_R0"]["pooled"]["control"])
    randoms = {entry["seed"]: entry for entry in replication["random"]}
    base = float(replication["trained"][0]["final"]["pooled"]["base_rate"])
    panels = []
    for entry in replication["trained"]:
        seed = entry["seed"]
        rows = [
            Row("random-init backbone", *interval(randoms[seed]["pooled"]), PALETTE[3], True),
            Row("trained tel_only", *interval(entry["final"]["pooled"]), PALETTE[0]),
            Row("telemetry bag-of-tokens", *tel_bag, PALETTE[4]),
            Row("status-only bag-of-tokens", *status_bag, PALETTE[5]),
        ]
        panels.append(Panel(f"seed {seed}", rows))
    svg = render_intervals(
        panels,
        title="F2. Pretraining buys a little, order buys nothing, the strings carry more",
        subtitle=f"AUPRC with 95% block-bootstrap intervals, {FORWARD_SPAN}",
        markers=[Marker(base, f"base rate {base:.4f}")],
        value_label="AUPRC (higher is better)",
    )
    return Figure(
        stem="fig2_probe_ladder",
        title="F2. The probe ladder",
        sentence=(
            "Pretraining buys a little, order buys nothing, the strings carry more than the "
            "telemetry."
        ),
        sources=[
            "reports/data/seed_replication_v0_20260917.json",
            "reports/data/bag_of_tokens_v0_20260917.json",
            "reports/data/h1_controls_v0_20260918.json",
        ],
        svg=svg,
        caption=(
            "The random-init row is the same probe design on an untrained backbone of the same "
            "size; the gap to the trained row is what fifty million tokens of telemetry "
            "pretraining bought. The telemetry bag-of-tokens ignores token order entirely and "
            "is within noise of the trained probe. The status-only bag-of-tokens, a histogram "
            "of the window's status strings with no model at all, is above every telemetry row. "
            "The two bag rows are single fits, not per-seed, and repeat in each panel as a "
            f"reference. {FORWARD_CAVEAT}."
        ),
    )


def _dimensions(svg: str) -> tuple[float, float]:
    """Read a rendered SVG's declared width and height.

    Args:
        svg: The SVG document.

    Returns:
        Width and height in user units.

    Raises:
        ValueError: If the document declares neither.
    """
    found = re.search(r'width="([\d.]+)" height="([\d.]+)"', svg)
    if not found:
        raise ValueError("rendered SVG declares no width and height")
    return float(found.group(1)), float(found.group(2))


def stack(parts: Sequence[str]) -> str:
    """Stack rendered SVG documents vertically, each keeping its own value axis.

    Args:
        parts: The documents, drawn top to bottom.

    Returns:
        A standalone SVG document holding the others as nested elements.
    """
    sizes = [_dimensions(part) for part in parts]
    width = max(size[0] for size in sizes)
    height = sum(size[1] for size in sizes)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="system-ui, sans-serif" '
        'font-size="12">',
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="{SURFACE}"/>',
    ]
    offset = 0.0
    for part, (part_width, part_height) in zip(parts, sizes, strict=True):
        inner = part.split("\n", 1)[1].rsplit("</svg>", 1)[0]
        out.append(
            f'<svg x="0" y="{offset:.0f}" width="{part_width:.0f}" '
            f'height="{part_height:.0f}" viewBox="0 0 {part_width:.0f} {part_height:.0f}">'
            f"{inner}</svg>"
        )
        offset += part_height
    out.append("</svg>")
    return "\n".join(out) + "\n"


def build_f5(records: RecordSet) -> Figure | None:
    """F5: the CARE attribution, the masking test above and CARE per farm below.

    Args:
        records: The record set.

    Returns:
        The figure, or ``None`` when a source record is missing.
    """
    attribution = records.json("care_attribution_v0_20260918.json")
    axis = records.json("axis_gate_v0_20260918.json")
    if attribution is None or axis is None:
        return None
    masking_line = float(attribution["config"]["masking"]["base_rate"])
    farms = sorted(attribution["farm_readings"])
    colours = {farm: PALETTE[index] for index, farm in enumerate(farms)}
    masked = []
    for row in attribution["masked"]:
        count = len(row["channels"])
        masked.append(
            Row(
                f"{row['farm']} pattern, seed {row['seed']} "
                f"({count} channel{'' if count == 1 else 's'})",
                *interval(row["interval"]),
                colours.get(row["farm"], PALETTE[0]),
                note=str(row["position"]),
            )
        )
    upper = render_intervals(
        [Panel("each CARE farm's absent channels, imposed on the training-site split", masked)],
        title="F5. The channel gaps do not explain the cross-OEM null",
        subtitle=f"AUPRC with 95% block-bootstrap intervals, {FORWARD_SPAN}",
        markers=[Marker(masking_line, f"base rate {masking_line:g}")],
        value_label="AUPRC on the training-site split (higher is better)",
        label_width=260.0,
    )
    bags = {entry["group"]: entry for entry in attribution["bag"]}
    panels, worst = [], 0.0
    for farm in farms:
        rows, line = [], 0.0
        for row in axis["reported"]:
            if row.get("group") != farm or row["checkpoint"] != axis["gating"]:
                continue
            line = float(row["base_rate"])
            share = float(row["interval"]["discarded"]) / float(row["interval"]["replicates"])
            worst = max(worst, share)
            rows.append(
                Row(
                    f"probe, seed {row['seed']}",
                    *interval(row["interval"]),
                    colours[farm],
                    note=f"discarded {share:.2%}" if share else "",
                )
            )
        if farm in bags:
            rows.append(
                Row("bag-of-tokens", *interval(bags[farm]["interval"]), PALETTE[4], hollow=True)
            )
        panels.append((farm, line, rows))
    lower = [
        render_intervals(
            [Panel(f"CARE {farm}: the probe on three seeds, and the comparator", rows)],
            title=(
                "CARE per farm: the probe and the order-blind comparator alike"
                if index == 0
                else ""
            ),
            subtitle=(
                "AUPRC with 95% intervals, held-out cross-OEM evaluation; one value scale a farm"
                if index == 0
                else ""
            ),
            markers=[Marker(line, f"base rate {line:.6g}")],
            value_label=f"AUPRC on CARE {farm} (higher is better)",
            label_width=260.0,
        )
        for index, (farm, line, rows) in enumerate(panels)
    ]
    low = min(row.value for _, _, rows in panels for row in rows if not row.hollow)
    high = max(row.value for _, _, rows in panels for row in rows if not row.hollow)
    return Figure(
        stem="fig5_care_attribution",
        title="F5. CARE attribution",
        sentence="The channel gaps do not explain the cross-OEM null; the token stream does.",
        sources=[
            "reports/data/care_attribution_v0_20260918.json",
            "reports/data/axis_gate_v0_20260918.json",
        ],
        svg=stack([upper, *lower]),
        caption=(
            "Above: imposing each CARE farm's absent core channels on the training-site test "
            "split leaves the probe clear of the base rate on all nine farm-by-seed cells, so "
            "the channel gaps are not what nulls it. Below: on CARE itself the probe and the "
            "order-blind comparator both sit at each farm's own base rate, over a per-farm "
            f"range of {low:.4f} to {high:.4f} AUPRC. The worst discarded-replicate share "
            f"anywhere below is {worst:.2%}, at farm_b, whose positives fall in the fewest "
            "blocks of the three; the pooled rows the rule actually reads discard nothing. "
            "Every panel has its own value scale and its own base-rate line, because CARE's "
            "base rates are about a thirtieth of the training sites'."
        ),
    )


def build_f6(records: RecordSet) -> Figure | None:
    """F6: training diagnostics, pretraining loss and probe selection.

    Args:
        records: The record set.

    Returns:
        The figure, or ``None`` when a source log is missing.
    """
    controls = records.json("h1_controls_v0_20260918.json")
    cadence = records.json("probe_cadence_v0_20260917.json")
    replication = records.json("seed_replication_v0_20260917.json")
    if controls is None or cadence is None or replication is None:
        return None
    wanted = [
        ("tel_only seed 1", "gate_check_v0_steps/S2_tel_only_seed1_lm.steps.csv", PALETTE[0], True),
        (
            "tel_only seed 2",
            "seed_replication_v0_steps/S2_tel_only_seed2_lm.steps.csv",
            PALETTE[0],
            True,
        ),
        (
            "tel_only seed 3",
            "seed_replication_v0_steps/S2_tel_only_seed3_lm.steps.csv",
            PALETTE[0],
            True,
        ),
        ("joint seed 1", "h1_arms_v0_steps/S2_joint_seed1_lm.steps.csv", PALETTE[1], False),
        ("joint seed 2", "h1_arms_v0_steps/S2_joint_seed2_lm.steps.csv", PALETTE[1], False),
        ("joint seed 3", "h1_arms_v0_steps/S2_joint_seed3_lm.steps.csv", PALETTE[1], False),
    ]
    curves, absent = [], []
    for label, relative, colour, dashed in wanted:
        rows = records.steps(relative)
        if rows is None:
            absent.append(f"reports/data/{relative}")
            continue
        curves.append(
            Series(
                label,
                [(float(row["step"]), float(row["loss"])) for row in rows],
                colour,
                dashed,
            )
        )
    if not curves:
        return None
    uniform = math.log(float(controls["config"]["vocab_size"]))
    history = [(float(step), float(value)) for step, value in cadence["history"]]
    selection = replication["trained"][0]["selection"]
    svg = render_curves(
        curves,
        [Series("probe validation AUPRC", history, PALETTE[2])],
        title="F6. The initial-loss check is visible, and checkpoint selection is noise",
        subtitle="Every point is a per-step training log or a recorded validation measurement",
        left_title="Pretraining training loss per optimiser step",
        right_title="Probe validation AUPRC per step, G3 cadence",
        left_x_label="optimiser step",
        right_x_label="probe step",
        left_marker=(uniform, f"ln(V) = {uniform:.4f}, the uniform-prediction loss"),
        right_band=(
            float(selection["low"]),
            float(selection["high"]),
            f"95% interval of the selection split ({selection['positives']} positives)",
        ),
    )
    figure = Figure(
        stem="fig6_training",
        title="F6. Training diagnostics",
        sentence=(
            "The initial-loss check is visible, and checkpoint selection on "
            f"{selection['positives']} positives is noise."
        ),
        sources=[
            *(f"reports/data/{relative}" for _, relative, _, _ in wanted),
            "reports/data/probe_cadence_v0_20260917.json",
            "reports/data/seed_replication_v0_20260917.json",
            "reports/data/h1_controls_v0_20260918.json",
        ],
        svg=svg,
        caption=(
            "Left: the per-step logs record **training** loss, not validation loss, so that is "
            "what is drawn; every run starts within a tenth of a nat of ln(V) over the joint "
            "vocabulary, which is the fail-fast guard passing in plain sight. Right: the G3 "
            "cadence's twenty validation measurements. The step-0 point is the untrained head, "
            "and it sits inside the selection split's own 95% interval, as does every later "
            "measurement -- which is why the fixed-final-step rule replaced validation-based "
            "checkpoint selection."
        ),
        missing=absent,
    )
    return figure


#: The set, in the order it is built and indexed.
BUILDERS: tuple[tuple[str, Any], ...] = (
    ("F4", build_f4),
    ("F1", build_f1),
    ("F3", build_f3),
    ("ledger", build_ledger),
    ("F2", build_f2),
    ("F5", build_f5),
    ("F6", build_f6),
)


def render_index(figures: Sequence[Figure], records: RecordSet, paths: ProjectPaths) -> str:
    """Render the index that lists every output, its sources and its sentence.

    Args:
        figures: The outputs that were built.
        records: The record set, for the files it could not find.
        paths: Resolved project paths.

    Returns:
        The Markdown index.
    """
    parts = [
        "# Figures for the closed experimental programme\n\n",
        kv_table(
            {
                "what this is": "every figure in the write-up, drawn from the committed record",
                "retraining": "none; every value is read from a tracked file",
                "test split": FORWARD_SPAN,
                "standing caveat": FORWARD_CAVEAT,
                "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "git_sha": git_sha(paths.repo_root),
                "generated by": "faultline model figures",
            }
        ),
    ]
    rows = [
        [
            figure.title,
            f"`{figure.stem}.svg`" if figure.svg else f"`{figure.stem}.md`",
            figure.sentence,
        ]
        for figure in figures
    ]
    parts.append(section("1. The set", table(["figure", "file", "the sentence it supports"], rows)))
    body = ""
    for figure in figures:
        body += f"### {figure.title}\n\n"
        if figure.svg:
            body += f"![{figure.title}]({figure.stem}.svg)\n\n"
        if figure.markdown:
            body += figure.markdown + "\n"
        body += f"**{figure.sentence}**\n\n{figure.caption}\n\n"
        body += "Sources:\n\n"
        for source in figure.sources:
            body += f"- `{source}`\n"
        if figure.missing:
            body += "\nNot found, and left out of this figure:\n\n"
            for source in figure.missing:
                body += f"- `{source}`\n"
        body += "\n"
    parts.append(section("2. Each figure, its sources and its caption", body))
    if records.missing:
        unique = sorted(set(records.missing))
        parts.append(
            section(
                "3. Record files asked for and not found",
                "\n".join(f"- `{name}`" for name in unique)
                + "\n\nA figure whose source is missing is skipped rather than drawn from a "
                "substitute.\n",
            )
        )
    return "".join(parts)


def write_figures(paths: ProjectPaths, out_dir: Path | None = None) -> list[Path]:
    """Build every figure the record supports and write it under ``reports/data/``.

    Args:
        paths: Resolved project paths, which is where every value is read from.
        out_dir: Where to write; ``reports/data/`` when omitted. The test suite passes a
            scratch directory, so building a figure never rewrites the committed set.

    Returns:
        The files written, the index last.
    """
    target_dir = out_dir or paths.data_reports_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    records = RecordSet(paths)
    figures: list[Figure] = []
    for name, builder in BUILDERS:
        figure = builder(records)
        if figure is None:
            logger.warning("%s: a source record is missing; skipped", name)
            continue
        figures.append(figure)
    written: list[Path] = []
    for figure in figures:
        if figure.svg is not None:
            target = target_dir / f"{figure.stem}.svg"
            target.write_text(figure.svg, encoding="utf-8", newline="\n")
            written.append(target)
        if figure.markdown:
            target = target_dir / f"{figure.stem}.md"
            target.write_text(
                f"# {figure.title}\n\n{figure.sentence}\n\n{figure.markdown}\n{figure.caption}\n",
                encoding="utf-8",
                newline="\n",
            )
            written.append(target)
    index = target_dir / "figures_index.md"
    index.write_text(render_index(figures, records, paths), encoding="utf-8", newline="\n")
    written.append(index)
    logger.info("wrote %d files under %s", len(written), target_dir)
    return written
