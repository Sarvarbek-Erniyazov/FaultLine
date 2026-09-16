"""Loss-versus-tokens curves and terminal slopes for the text ladder, from its record.

No model is loaded and nothing is retrained. The S2 and S3 pretraining runs wrote every
validation measurement they took to ``reports/data/text_pretrain_v1_*.json`` (``history``:
optimiser step and validation next-token loss on the fixed selection subsample). Tokens
seen at a measurement are its step times the run's tokens per step, which the record
fixes exactly: total training tokens over the last step.

**Terminal slope, defined before it was read.** The *terminal slope* is the change in
validation loss per million training tokens over the last full measurement interval, the
last two measurements an equal interval apart. The final interval (the three steps to the
end of the run) is also reported, but it is short, so single-seed noise dominates it. Per-step
training loss was logged to the console and not saved for these two runs, so it is not
available for them. Every run since the M3 pre-run brief (E4) writes it beside its checkpoint
(``*.steps.csv``, :func:`faultline.training.loop.write_step_log`).

**What a terminal slope cannot say.** Both runs used a cosine schedule that decays to
:data:`faultline.training.loop.LR_FLOOR` of the peak rate by the last step. A terminal
slope is therefore the slope at a decayed learning rate, not the slope a longer run would
have. Extrapolating two such slopes to a crossover point is not valid, so no crossover is
computed. Whether S3 would cross S2 is an open question.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faultline.data.common.report import kv_table, section, table
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.loop import LR_FLOOR

logger = get_logger(__name__)

#: Tokens per slope unit: slopes are nats per million training tokens.
SLOPE_TOKENS = 1_000_000

#: Categorical slots 1 and 2 of the validated reference palette, on its light surface.
SERIES_COLOURS: tuple[str, ...] = ("#2a78d6", "#eb6834")


@dataclass(frozen=True)
class CurvePoint:
    """One validation measurement.

    Attributes:
        step: Optimiser steps taken.
        tokens: Training tokens seen.
        loss: Validation next-token loss, nats.
    """

    step: int
    tokens: int
    loss: float


@dataclass(frozen=True)
class RungCurve:
    """One rung's validation curve.

    Attributes:
        rung: The rung's name.
        parameters: Total parameters.
        tokens: Training tokens the run spent.
        points: Measurements in step order.
    """

    rung: str
    parameters: int
    tokens: int
    points: list[CurvePoint]

    def slope(self, first: int, second: int) -> float:
        """Loss change per million tokens between two measurements, by index."""
        a, b = self.points[first], self.points[second]
        return (b.loss - a.loss) / (b.tokens - a.tokens) * SLOPE_TOKENS

    def terminal_index(self) -> int:
        """Index of the last measurement that closes a full interval.

        Returns:
            The last index whose step gap to its predecessor equals the first gap.

        Raises:
            ValueError: If the curve has fewer than two measurements.
        """
        if len(self.points) < 2:
            raise ValueError(f"{self.rung}: a slope needs at least two measurements")
        full = self.points[1].step - self.points[0].step
        return max(
            i
            for i in range(1, len(self.points))
            if self.points[i].step - self.points[i - 1].step == full
        )

    def terminal_slope(self) -> float:
        """The terminal slope: the last full measurement interval."""
        end = self.terminal_index()
        return self.slope(end - 1, end)

    def final_slope(self) -> float:
        """The slope over the run's last interval, whatever its length."""
        return self.slope(len(self.points) - 2, len(self.points) - 1)


def curves_from_record(records: list[dict[str, Any]]) -> list[RungCurve]:
    """Rebuild each rung's curve from a pretraining record.

    Args:
        records: The parsed ``text_pretrain_v*.json``.

    Returns:
        One curve per rung, in record order.

    Raises:
        ValueError: If a run's tokens are not a whole number of tokens per step.
    """
    curves = []
    for record in records:
        history = sorted(record["history"], key=lambda m: m["step"])
        last_step = int(history[-1]["step"])
        tokens = int(record["tokens"])
        if tokens % last_step:
            raise ValueError(f"{record['rung']}: {tokens} tokens over {last_step} steps")
        per_step = tokens // last_step
        curves.append(
            RungCurve(
                rung=str(record["rung"]),
                parameters=int(record["params"]["total"]),
                tokens=tokens,
                points=[
                    CurvePoint(int(m["step"]), int(m["step"]) * per_step, float(m["value"]))
                    for m in history
                ],
            )
        )
    return curves


def render_svg(curves: list[RungCurve]) -> str:
    """Draw validation loss against tokens seen, one line per rung.

    One y-axis, a light surface painted explicitly, markers of different shapes and a
    direct label per rung, so a rung is never identified by colour alone.

    Args:
        curves: The curves, at most :data:`SERIES_COLOURS` of them.

    Returns:
        A standalone SVG document.
    """
    width, height = 640, 380
    left, right, top, bottom = 64, 72, 40, 52
    max_tokens = max(p.tokens for c in curves for p in c.points)
    losses = [p.loss for c in curves for p in c.points]
    low, high = 6.0, max(losses) + 0.1
    low = min(low, min(losses) - 0.1)

    def x(tokens: int) -> float:
        return left + tokens / max_tokens * (width - left - right)

    def y(loss: float) -> float:
        return top + (high - loss) / (high - low) * (height - top - bottom)

    ink, muted, grid, surface = "#1a1a19", "#5f5e58", "#e4e3dd", "#fcfcfb"
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="system-ui, sans-serif" font-size="12">',
        f"<title>Validation loss against training tokens seen, {', '.join(c.rung for c in curves)}"
        "</title>",
        f'<rect width="{width}" height="{height}" fill="{surface}"/>',
        f'<text x="{left}" y="22" fill="{ink}" font-size="14" font-weight="600">'
        "Validation loss (nats) vs tokens seen</text>",
    ]
    tick = 0.25
    value = round(low / tick) * tick
    while value <= high:
        if value >= low:
            out.append(
                f'<line x1="{left}" x2="{width - right}" y1="{y(value):.1f}" y2="{y(value):.1f}" '
                f'stroke="{grid}" stroke-width="1"/>'
                f'<text x="{left - 8}" y="{y(value) + 4:.1f}" fill="{muted}" '
                f'text-anchor="end">{value:.2f}</text>'
            )
        value += tick
    for million in range(0, max_tokens // 1_000_000 + 1, 2):
        tokens = million * 1_000_000
        out.append(
            f'<text x="{x(tokens):.1f}" y="{height - bottom + 18}" fill="{muted}" '
            f'text-anchor="middle">{million}M</text>'
        )
    out.append(
        f'<text x="{(left + width - right) / 2:.0f}" y="{height - 12}" fill="{muted}" '
        'text-anchor="middle">training tokens seen</text>'
    )

    def marker(index: int, cx: float, cy: float, colour: str) -> str:
        if index == 0:
            return (
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.5" fill="{colour}" '
                f'stroke="{surface}" stroke-width="2"/>'
            )
        return (
            f'<rect x="{cx - 4.5:.1f}" y="{cy - 4.5:.1f}" width="9" height="9" rx="1.5" '
            f'fill="{colour}" stroke="{surface}" stroke-width="2"/>'
        )

    highest_end = max(c.points[-1].loss for c in curves)
    for index, (curve, colour) in enumerate(zip(curves, SERIES_COLOURS, strict=False)):
        legend_x = width - 250 + index * 125
        out.append(marker(index, legend_x, 18, colour))
        out.append(
            f'<text x="{legend_x + 10}" y="22" fill="{ink}">{curve.rung} '
            f"({curve.parameters / 1e6:.1f}M params)</text>"
        )
        path = " ".join(f"{x(p.tokens):.1f},{y(p.loss):.1f}" for p in curve.points)
        out.append(
            f'<polyline points="{path}" fill="none" stroke="{colour}" stroke-width="2" '
            'stroke-linejoin="round"/>'
        )
        for p in curve.points:
            out.append(marker(index, x(p.tokens), y(p.loss), colour))
        end = curve.points[-1]
        # the higher end sits higher on the plot: its label goes above, the other's below
        offset = -8 if end.loss == highest_end else 16
        out.append(
            f'<text x="{x(end.tokens) + 8:.1f}" y="{y(end.loss) + offset:.1f}" fill="{ink}">'
            f"{curve.rung} {end.loss:.3f}</text>"
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def render_report(
    curves: list[RungCurve], record_path: str, figure_name: str, paths: ProjectPaths
) -> str:
    """Render the curves report.

    Args:
        curves: The curves.
        record_path: The pretraining record they came from.
        figure_name: The SVG written beside the report.
        paths: Resolved project paths.

    Returns:
        The Markdown report.
    """
    parts = [
        "# Text ladder: loss against tokens seen, and terminal slopes\n\n",
        kv_table(
            {
                "source record": record_path,
                "retraining": "none; every number is read from the record",
                "measurement": "validation next-token loss on the fixed selection subsample",
                "slope unit": "nats per million training tokens",
                "terminal slope": "the last full measurement interval (defined in "
                "src/faultline/evaluation/text_curves.py before it was read)",
                "schedule": f"cosine to {LR_FLOOR:g} of the peak rate at the last step",
                "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "git_sha": git_sha(paths.repo_root),
                "generated by": "faultline model text-curves",
            }
        ),
        f"\n![Validation loss against training tokens seen]({figure_name})\n",
    ]
    steps = [p.step for p in curves[0].points]
    rows = []
    for i, step in enumerate(steps):
        row = [str(step), f"{curves[0].points[i].tokens:,}"]
        row += [f"{c.points[i].loss:.4f}" for c in curves]
        if len(curves) == 2:
            row.append(f"{curves[1].points[i].loss - curves[0].points[i].loss:+.4f}")
        rows.append(row)
    headers = ["step", "tokens seen", *(f"{c.rung} loss" for c in curves)]
    if len(curves) == 2:
        headers.append(f"{curves[1].rung} - {curves[0].rung}")
    parts.append(section("1. The curves", table(headers, rows)))

    slope_rows = []
    for i in range(1, len(steps)):
        row = [
            f"{steps[i - 1]} -> {steps[i]}",
            f"{curves[0].points[i].tokens - curves[0].points[i - 1].tokens:,}",
        ]
        row += [f"{c.slope(i - 1, i):+.4f}" for c in curves]
        slope_rows.append(row)
    parts.append(
        section(
            "2. Slope per interval (nats per million tokens)",
            table(["interval (steps)", "tokens", *(c.rung for c in curves)], slope_rows),
        )
    )

    terminal = [
        [
            c.rung,
            f"{c.parameters:,}",
            f"{c.tokens:,}",
            f"{c.tokens / c.parameters:.2f}",
            f"{c.terminal_slope():+.4f}",
            f"{c.final_slope():+.4f}",
        ]
        for c in curves
    ]
    body = table(
        [
            "rung",
            "parameters",
            "tokens",
            "tokens per parameter",
            "terminal slope (last full interval)",
            "final interval",
        ],
        terminal,
    )
    if len(curves) == 2:
        a, b = curves
        steeper = abs(b.terminal_slope()) > abs(a.terminal_slope())
        crossings = [
            f"between {a.points[i - 1].tokens:,} and {a.points[i].tokens:,} tokens, where "
            f"{b.rung} goes from {'below' if b.points[i].loss > a.points[i].loss else 'above'} "
            f"{a.rung} to {'above' if b.points[i].loss > a.points[i].loss else 'below'} it"
            for i in range(1, len(a.points))
            if (b.points[i - 1].loss - a.points[i - 1].loss) * (b.points[i].loss - a.points[i].loss)
            < 0
        ]
        crossed = (
            f"The measured curves already cross {len(crossings)} time(s): "
            + "; ".join(crossings)
            + ". That is observed, not extrapolated, and it says nothing about a later crossing. "
            if crossings
            else ""
        )
        body += (
            f"\n**Is {b.rung}'s terminal slope steeper than {a.rung}'s? "
            f"{'Yes' if steeper else 'No'}:** {b.terminal_slope():+.4f} against "
            f"{a.terminal_slope():+.4f} nats per million tokens "
            f"({abs(b.terminal_slope()) / abs(a.terminal_slope()):.2f}x). Over the final interval: "
            f"{b.final_slope():+.4f} against {a.final_slope():+.4f}. This is one seed per rung, "
            "and no seed spread exists to set it against.\n\n"
            "**The crossover question is open.** "
            + crossed
            + "Whether the larger rung would reach a "
            "lower loss than the smaller one with more tokens is not resolved either way by "
            "these curves. Both slopes were read at a learning rate decayed to "
            f"{LR_FLOOR:g} of its peak, so they are not the slopes a longer run would have. A "
            "linear extrapolation to a crossing point would treat them as if they were, so none "
            "is computed. Answering it needs runs whose schedules are sized for a larger token "
            "budget, and a corpus to supply those tokens.\n"
        )
    parts.append(section("3. Terminal slopes", body))
    return "".join(parts)


def write_text_curves(paths: ProjectPaths, record: Path) -> tuple[Path, Path]:
    """Read a pretraining record, and write the curves report and its figure.

    Args:
        paths: Resolved project paths.
        record: The ``text_pretrain_v*.json`` to read.

    Returns:
        The Markdown report and the SVG figure.
    """
    curves = curves_from_record(json.loads(record.read_text(encoding="utf-8")))
    stem = record.stem.replace("text_pretrain_", "text_pretrain_curves_")
    figure = paths.data_reports_dir / f"{stem}.svg"
    figure.write_text(render_svg(curves), encoding="utf-8", newline="\n")
    report = paths.data_reports_dir / f"{stem}.md"
    relative = (
        record.relative_to(paths.repo_root).as_posix()
        if record.is_relative_to(paths.repo_root)
        else record.as_posix()
    )
    report.write_text(
        render_report(curves, relative, figure.name, paths), encoding="utf-8", newline="\n"
    )
    logger.info("wrote %s and %s", report, figure)
    return report, figure
