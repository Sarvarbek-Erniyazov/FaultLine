"""Text ladder curves and terminal slopes, rebuilt from a pretraining record."""

from __future__ import annotations

import math
from typing import Any

import pytest

from faultline.evaluation.text_curves import curves_from_record, render_report, render_svg
from faultline.paths import ProjectPaths


def _record(rung: str, losses: list[tuple[int, float]], tokens: int) -> dict[str, Any]:
    return {
        "rung": rung,
        "params": {"total": 1_000_000},
        "tokens": tokens,
        "history": [{"step": s, "value": v} for s, v in losses],
    }


# 100 tokens a step; measurements every 10 steps, then a 3-step tail
SMALL = _record("S2", [(10, 7.0), (20, 6.5), (30, 6.3), (33, 6.28)], 3_300)
LARGE = _record("S3", [(10, 7.2), (20, 6.6), (30, 6.35), (33, 6.32)], 3_300)


def test_tokens_are_step_times_tokens_per_step() -> None:
    (curve,) = curves_from_record([SMALL])
    assert [p.tokens for p in curve.points] == [1_000, 2_000, 3_000, 3_300]


def test_terminal_slope_is_the_last_full_interval_not_the_short_tail() -> None:
    (curve,) = curves_from_record([SMALL])
    assert curve.terminal_index() == 2
    # (6.3 - 6.5) over 1,000 tokens, per million tokens
    assert math.isclose(curve.terminal_slope(), -0.2 / 1_000 * 1_000_000)
    assert math.isclose(curve.final_slope(), -0.02 / 300 * 1_000_000)


def test_a_record_with_a_fractional_step_is_refused() -> None:
    with pytest.raises(ValueError, match="tokens over"):
        curves_from_record([_record("S2", [(10, 7.0), (33, 6.0)], 3_301)])


def test_report_answers_steeper_and_leaves_crossover_open(tmp_paths: ProjectPaths) -> None:
    curves = curves_from_record([SMALL, LARGE])
    report = render_report(curves, "record.json", "figure.svg", tmp_paths)
    assert "Is S3's terminal slope steeper than S2's? Yes" in report
    assert "The crossover question is open." in report
    assert "![Validation loss against training tokens seen](figure.svg)" in report


def test_svg_labels_each_rung_directly_and_paints_its_surface() -> None:
    svg = render_svg(curves_from_record([SMALL, LARGE]))
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "S2 6.280" in svg and "S3 6.320" in svg
    assert '<rect width="640" height="380" fill="#fcfcfb"/>' in svg
