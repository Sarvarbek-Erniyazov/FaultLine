"""The CPU streaming trace: the deployment path over one held-out turbine-year."""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from faultline.deployment import stream
from faultline.deployment.selection import (
    MOST_EVENTS,
    RULE_NAMES,
    RULES,
    TRACE_RECORD,
    TYPICAL_RATE,
    read_traces,
    rules_block,
    write_trace,
)
from faultline.deployment.stream import (
    BLOCK_STEPS,
    BOOTSTRAP_SEED,
    CONFIDENCE,
    DESIGN,
    HORIZON_HOURS,
    LABEL_FONT,
    REPLICATES,
    SEED,
    SelectionField,
    StreamTrace,
    TurbineChoice,
    TurbineYear,
    caption,
    choose_turbine,
    comparability,
    event_counts,
    hours_to_next_event,
    label_width,
    render_report,
    render_stream_traces,
    render_svg,
    trace_turbine_year,
    turbine_years,
    write_csv,
    write_stream_traces,
)
from faultline.evaluation import calibration
from faultline.evaluation.bootstrap import bootstrap_auprc, window_blocks
from faultline.paths import ProjectPaths
from faultline.training.config import PositiveAwareRiskStage, PositiveBudget
from faultline.training.windows import WindowSet

SVG = "{http://www.w3.org/2000/svg}"

#: A small turbine-year: four events, hourly windows, enough positives for a bootstrap.
WINDOWS = 240
EVENTS = 4

#: The pooled test base rate the typical-rate rule aims at, as the record carries it.
POOLED = 0.0388

#: The pooled test split's positive windows and positive blocks, which is what makes its
#: interval narrower than any single turbine-year's, and so the ground of the refusal.
POOLED_POSITIVES, POOLED_POSITIVE_BLOCKS = 5312, 497


def _events(counts: dict[str, int], year: int = 2023) -> pd.DataFrame:
    """A narrow event table with a given number of starts per turbine."""
    rows: list[dict[str, Any]] = []
    for turbine, count in counts.items():
        for index in range(count):
            rows.append(
                {
                    "turbine_id": turbine,
                    "start_utc": pd.Timestamp(f"{year}-02-01", tz="UTC") + pd.Timedelta(days=index),
                }
            )
    return pd.DataFrame(rows, columns=["turbine_id", "start_utc"])


def _candidates(spec: dict[str, tuple[int, int, int]]) -> dict[str, TurbineYear]:
    """A field of turbine-years from ``turbine -> (events, windows, positives)``."""
    return {
        turbine: TurbineYear(turbine, events, windows, positives)
        for turbine, (events, windows, positives) in spec.items()
    }


def _trace(rule: str = MOST_EVENTS) -> StreamTrace:
    """A synthetic trace, built without loading a model or reading a shard."""
    stamps = (
        np.datetime64("2023-01-01T00:00:00") + np.arange(WINDOWS) * np.timedelta64(1, "h")
    ).astype("datetime64[ns]")
    ends = np.arange(WINDOWS, dtype=np.int64) * 6 + 143
    # Offset off the first stamp: an event there would have its whole horizon before
    # the traced span, and the band for it would be correctly clipped away.
    starts = np.sort(stamps[WINDOWS // (2 * EVENTS) :: WINDOWS // EVENTS][:EVENTS])
    hours = hours_to_next_event(stamps, starts, HORIZON_HOURS)
    labels = np.isfinite(hours).astype(np.float32)
    rng = np.random.default_rng(0)
    probabilities = np.clip(0.02 + 0.05 * labels + rng.normal(0, 0.005, WINDOWS), 0.0, 1.0)
    interval = bootstrap_auprc(
        probabilities,
        labels,
        window_blocks(ends, np.zeros_like(ends), BLOCK_STEPS),
        replicates=200,
        seed=1,
    )
    positives = int(labels.sum())
    candidates = _candidates(
        {
            # The dense one the most-events rule picks, and a sparse one whose rate sits
            # nearest the pooled base rate, so the two rules genuinely disagree.
            "Kelmarsh 5": (EVENTS, WINDOWS, positives),
            "Kelmarsh 4": (1, WINDOWS, round(POOLED * WINDOWS)),
        }
    )
    choice = choose_turbine(candidates, rule, POOLED)
    return StreamTrace(
        source="kelmarsh",
        year=2023,
        choice=choice,
        stamps=stamps,
        ends=ends,
        probabilities=probabilities,
        labels=labels,
        hours=hours,
        events=starts,
        interval=interval,
        train_rate=0.5,
        natural_rate=0.0221,
        balanced_shift=0.0,
        offset=-3.7921,
        pooled_base_rate=POOLED,
        pooled_auprc=0.0576,
        pooled_low=0.0503,
        pooled_high=0.0670,
        pooled_positives=POOLED_POSITIVES,
        pooled_positive_blocks=POOLED_POSITIVE_BLOCKS,
        seconds=12.0,
        checkpoint="run/S2_tel_only_seed2.pt",
        probe="run/S2_trained_seed2_probe.pt",
    )


def _chance_trace(rule: str = MOST_EVENTS) -> StreamTrace:
    """The same turbine-year with a score that carries nothing, so the interval contains it."""
    trace = _trace(rule)
    rng = np.random.default_rng(7)
    probabilities = rng.uniform(0.0, 0.1, trace.windows)
    interval = bootstrap_auprc(
        probabilities,
        trace.labels,
        window_blocks(trace.ends, np.zeros_like(trace.ends), BLOCK_STEPS),
        replicates=200,
        seed=1,
    )
    return replace(trace, probabilities=probabilities, interval=interval)


# --------------------------------------------------------------------------------------
# The correction is the record's, not a second copy of it


def test_the_module_calls_the_evaluation_correction_itself() -> None:
    """The name the trace applies is the evaluation package's function, not a local one."""
    assert stream.at_natural_rate is calibration.at_natural_rate


def test_the_trace_routes_its_probabilities_through_that_function(
    monkeypatch: pytest.MonkeyPatch, tmp_paths: ProjectPaths
) -> None:
    """The scored logits reach the record's correction, with the registered prior.

    Everything heavy is replaced -- the shards, the probe and the forward pass -- so what
    is left under test is the wiring: which function corrects the logits, and with which
    arguments. A local re-derivation would not call it and would fail here.
    """
    block = {
        "seed": SEED,
        "natural_rate": 0.0221,
        "prior_band": {"shift": 0.25},
        "pooled": {
            "base_rate": 0.0388,
            "auprc": 0.0576,
            "low": 0.0503,
            "high": 0.0670,
            "positives": POOLED_POSITIVES,
            "positive_blocks": POOLED_POSITIVE_BLOCKS,
        },
    }
    logits = np.linspace(-2.0, 2.0, WINDOWS, dtype=np.float32)
    labels = np.zeros(WINDOWS, dtype=np.float32)
    labels[::40] = 1.0
    windows = WindowSet(
        key="kelmarsh__test",
        tokens=np.zeros(0, dtype=np.uint16),
        starts=np.arange(WINDOWS, dtype=np.int64) * 6,
        ends=np.arange(WINDOWS, dtype=np.int64) * 6 + 143,
        labels=labels,
        years=np.full(WINDOWS, 2023, dtype=np.int64),
    )
    risk = PositiveAwareRiskStage(
        label="narrow_within_24h",
        sampling="balanced",
        positive_fraction=0.5,
        probe=PositiveBudget(positives=16, batch_windows=2, accumulate=1, learning_rate=2e-3),
        finetune=PositiveBudget(positives=16, batch_windows=2, accumulate=1, learning_rate=5e-4),
        random=PositiveBudget(positives=16, batch_windows=2, accumulate=1, learning_rate=5e-4),
    )
    inputs = SimpleNamespace(
        ladder=SimpleNamespace(risk=risk, evaluation=SimpleNamespace(batch_windows=8)),
        mixture=SimpleNamespace(window_stride_steps=6),
        telemetry=SimpleNamespace(
            files=lambda: {"kelmarsh__test": {"steps": WINDOWS * 6 + 144}},
            tokens_per_step=13,
            context_steps=144,
        ),
        device="cpu",
    )
    probe = tmp_paths.checkpoints_dir / "run" / "S2_trained_seed2_probe.pt"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_bytes(b"")

    seen: list[dict[str, Any]] = []

    def spy(
        values: np.ndarray, train_rate: float, natural_rate: float, balanced_shift: float = 0.0
    ) -> calibration.NaturalRateScores:
        seen.append(
            {
                "train_rate": train_rate,
                "natural_rate": natural_rate,
                "balanced_shift": balanced_shift,
            }
        )
        return calibration.at_natural_rate(values, train_rate, natural_rate, balanced_shift)

    monkeypatch.setattr(stream, "at_natural_rate", spy)
    monkeypatch.setattr(stream, "read_probe_record", lambda paths, seed: block)
    monkeypatch.setattr(stream, "narrow_event_starts", lambda paths, source: _events({"T1": 3}))
    monkeypatch.setattr(stream, "open_probe_inputs", lambda *a, **k: inputs)
    monkeypatch.setattr(stream, "load_saved_probe", lambda *a, **k: None)
    monkeypatch.setattr(
        stream,
        "known_windows",
        lambda *a, **k: (windows, np.full(WINDOWS, "T1", dtype=object)),
    )
    monkeypatch.setattr(stream, "turbine_year_windows", lambda *a, **k: windows)
    monkeypatch.setattr(
        stream,
        "step_stamps",
        lambda paths, source, split: (
            np.datetime64("2023-01-01T00:00:00")
            + np.arange(WINDOWS * 6 + 144) * np.timedelta64(10, "m")
        ).astype("datetime64[ns]"),
    )
    monkeypatch.setattr(
        stream, "risk_logits", lambda *a, **k: (logits, labels, np.zeros(WINDOWS, np.int64))
    )

    trace = trace_turbine_year(
        tmp_paths,
        "kelmarsh",
        2023,
        "configs/train/joint_v0.yaml",
        "configs/train/telemetry_v1.yaml",
        "S2",
        "run",
    )
    # Called once, with the stage's registered prior and the record's own measured offset.
    assert seen == [{"train_rate": 0.5, "natural_rate": 0.0221, "balanced_shift": 0.25}]
    expected = calibration.at_natural_rate(logits, 0.5, 0.0221, 0.25).probabilities
    assert np.allclose(trace.probabilities, expected)
    # And the two-term rule is genuinely in the number, not an unshifted sigmoid.
    assert not np.allclose(trace.probabilities, 1.0 / (1.0 + np.exp(-logits)))
    # The pooled AUPRC the caption refuses the comparison with comes off the same record.
    assert (trace.pooled_auprc, trace.pooled_low, trace.pooled_high) == (0.0576, 0.0503, 0.0670)


# --------------------------------------------------------------------------------------
# The three outputs agree with what was scored


def test_the_csv_holds_one_row_a_window_scored(tmp_path: Path) -> None:
    trace = _trace()
    lines = (
        write_csv(trace, tmp_path / "trace.csv").read_text(encoding="utf-8").strip().splitlines()
    )
    assert lines[0].split(",") == [
        "timestamp_utc",
        "window_end_step",
        "probability",
        "label",
        "hours_to_next_event",
    ]
    assert len(lines) - 1 == trace.windows == WINDOWS


def test_the_hours_column_is_blank_exactly_where_the_label_is_negative(tmp_path: Path) -> None:
    """The label is true when an event starts in ``(t, t + H]``, so the two agree by rule."""
    trace = _trace()
    rows = (
        write_csv(trace, tmp_path / "trace.csv").read_text(encoding="utf-8").strip().splitlines()
    )[1:]
    for row, label in zip(rows, trace.labels, strict=True):
        assert (row.split(",")[4] == "") == (label == 0)


def test_the_figure_draws_one_marker_an_event() -> None:
    trace = _trace()
    root = ET.fromstring(render_svg(trace))
    markers = [line for line in root.iter(f"{SVG}line") if line.get("class") == "event"]
    assert len(markers) == len(trace.events) == trace.choice.events == EVENTS
    bands = [rect for rect in root.iter(f"{SVG}rect") if rect.get("class") == "horizon"]
    # One shaded horizon a marker: every event here sits far enough into the span to have
    # its whole horizon inside it.
    assert len(bands) == EVENTS


def test_the_figure_draws_both_rate_lines_and_no_operating_point() -> None:
    """The pooled rate and this turbine-year's own, each named in words on its own line."""
    trace = _trace()
    svg = render_svg(trace)
    root = ET.fromstring(svg)
    lines = [line for line in root.iter(f"{SVG}line") if line.get("class") == "reference"]
    assert len(lines) == 2
    # Different dash patterns, so the two are told apart with the colour taken away.
    assert len({line.get("stroke-dasharray") for line in lines}) == 2
    labels = [text.text or "" for text in root.iter(f"{SVG}text")]
    assert any(f"pooled test base rate {trace.pooled_base_rate:.4f}" == label for label in labels)
    assert any(
        label == f"{trace.choice.turbine} {trace.year} positive rate {trace.positive_rate:.4f}"
        for label in labels
    )
    for banned in ("threshold", "alarm", "abstention", "abstain"):
        assert banned not in svg.lower()


def test_the_figure_keeps_both_rate_lines_inside_the_value_axis() -> None:
    """This turbine-year's rate is far above the pooled one and must still be drawn."""
    trace = _trace()
    root = ET.fromstring(render_svg(trace))
    lines = [line for line in root.iter(f"{SVG}line") if line.get("class") == "reference"]
    for line in lines:
        assert 44.0 <= float(line.get("y1") or 0.0) <= 360.0 - 52.0


def _text_boxes(root: ET.Element) -> list[tuple[str, float, float, float, float]]:
    """Every text node's box, measured the way the generator places its plates.

    Args:
        root: The parsed SVG root.

    Returns:
        Per text node its content and its ``(x0, x1, y0, y1)`` box.
    """
    default = float(root.get("font-size") or LABEL_FONT)
    boxes = []
    for node in root.iter(f"{SVG}text"):
        content = node.text or ""
        font = float(node.get("font-size") or default)
        span = label_width(content, font)
        if (node.get("font-weight") or "400") in ("600", "700", "bold"):
            span *= 1.06
        x, y = float(node.get("x") or 0.0), float(node.get("y") or 0.0)
        anchor_at = node.get("text-anchor") or "start"
        x0 = x if anchor_at == "start" else (x - span / 2 if anchor_at == "middle" else x - span)
        boxes.append((content, x0, x0 + span, y - 0.82 * font, y + 0.22 * font))
    return boxes


@pytest.mark.parametrize("build", [_trace, _chance_trace])
def test_no_two_labels_in_the_figure_overlap(build: Any) -> None:
    """Two labels sharing pixels are two labels a reader may read as one word."""
    boxes = _text_boxes(ET.fromstring(render_svg(build())))
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            apart = (
                first[2] <= second[1]
                or second[2] <= first[1]
                or first[4] <= second[3]
                or second[4] <= first[3]
            )
            assert apart, f"{first[0]!r} and {second[0]!r} overlap"


@pytest.mark.parametrize("build", [_trace, _chance_trace])
def test_each_rate_label_is_written_on_a_plate_over_the_trace(build: Any) -> None:
    """The defect this guards is the trace running between a label's letters.

    Kelmarsh 4 2023 put 153 polyline vertices inside the pooled label's box, nine of them
    inside the word "pooled", which two readers read as "pobled". The two labels never
    touched each other; what crossed the words was the score. So each label needs an
    opaque plate, and the plate has to be drawn after the polyline to cover anything.
    """
    svg = render_svg(build())
    root = ET.fromstring(svg)
    plates = [rect for rect in root.iter(f"{SVG}rect") if rect.get("class") == "plate"]
    assert len(plates) == 2
    labels = [box for box in _text_boxes(root) if "rate" in box[0]]
    assert len(labels) == 2
    for _, x0, x1, y0, y1 in labels:
        assert any(
            float(plate.get("x") or 0.0) <= x0
            and float(plate.get("x") or 0.0) + float(plate.get("width") or 0.0) >= x1
            and float(plate.get("y") or 0.0) <= y0
            and float(plate.get("y") or 0.0) + float(plate.get("height") or 0.0) >= y1
            for plate in plates
        ), "a rate label is not covered by any plate"
    assert svg.index("<polyline") < svg.index('class="plate"')


# --------------------------------------------------------------------------------------
# What the caption says, and refuses to say


def test_the_caption_says_what_the_trace_is_not() -> None:
    said = caption(_trace()).lower()
    for term in (
        "illustrative",
        "forward-in-time",
        "same site",
        "single turbine-year",
        "not an evaluation",
        "not comparable with the pooled gate numbers",
        "no threshold",
        "telemetry only",
    ):
        assert term in said


def test_the_caption_reads_the_interval_against_the_turbine_year_s_own_rate() -> None:
    """Not against the pooled base rate, which is a different set's denominator."""
    trace = _trace()
    assert trace.interval.low > trace.positive_rate
    assert trace.clears
    said = caption(trace)
    assert f"CLEARS its own positive rate {trace.positive_rate:.4f}" in said
    assert "CONTAINS" not in said


def test_a_score_at_chance_is_said_to_contain_its_own_rate() -> None:
    """The comparison the caption must make, and the reading it must not hide."""
    trace = _chance_trace()
    assert trace.interval.low <= trace.positive_rate
    assert not trace.clears
    said = caption(trace)
    assert f"CONTAINS its own positive rate {trace.positive_rate:.4f}" in said
    assert "consistent with chance on this turbine-year" in said
    assert "CLEARS" not in said


def test_the_caption_states_the_mean_probability_beside_the_positive_rate() -> None:
    """And why the two differ: it targets the training split's natural rate, not this turbine.

    Not "the training prior" either: section 2 registers that as 0.5, and the rate the
    correction aims at is the natural one.
    """
    trace = _trace()
    said = caption(trace)
    assert f"mean corrected probability is {trace.mean_probability:.4f}" in said
    assert f"targets the training split's natural rate {trace.natural_rate:.4f}" in said
    assert "the training prior" not in said
    assert "not this turbine-year's" in said


def test_the_caption_refuses_the_pooled_comparison_on_the_positive_counts() -> None:
    """The ground is how few positives one turbine-year holds, not its base rate.

    Two sets can share a base rate exactly and still be incomparable, so a ratio of base
    rates is no ground at all. The counts are, and both are stated.
    """
    trace = _trace()
    said = caption(trace)
    assert f"pooled test AUPRC ({trace.pooled_auprc:.4f}" in said
    assert f"{trace.positives:,} against {trace.pooled_positives:,}" in said
    assert f"{trace.positive_rate / trace.pooled_base_rate:.1f}x the pooled" not in said


def test_the_caption_shows_the_measured_widening_beside_the_square_root_guide() -> None:
    """A reader is given both ratios, so neither has to be taken on trust."""
    said = caption(_trace())
    trace = _trace()
    assert f"{trace.widening:.1f} times the width of the pooled one" in said
    assert f"sqrt({trace.pooled_positives:,}/{trace.positives:,})" in said
    assert f"suggests {trace.root_widening:.1f}" in said


def test_a_widening_that_does_not_match_the_guide_is_not_said_to_match_it() -> None:
    """The two ratios need not agree, and the caption says which way it came out."""
    trace = _trace()
    narrow = replace(trace, interval=replace(trace.interval, low=0.05, high=0.06))
    assert narrow.widening < narrow.root_widening
    said = comparability(narrow)
    assert "do not agree" in said
    assert "agree to within" not in said
    wide = replace(trace, interval=replace(trace.interval, low=0.0, high=1.0))
    assert "do not agree" in comparability(wide)


def test_the_caption_observes_what_the_rule_selected_for() -> None:
    dense = caption(_trace(MOST_EVENTS))
    assert "One observation:" in dense
    assert "atypical for the site" in dense
    assert "selects atypical turbine-years by construction" in dense
    typical = caption(_trace(TYPICAL_RATE))
    assert "One observation:" in typical
    assert "least unlike the pooled test split" in typical
    assert "reads no score to do it" in typical


def test_the_caption_names_the_rule_and_the_other_trace() -> None:
    for rule in RULES:
        said = caption(_trace(rule))
        assert f"Selected under the {RULE_NAMES[rule]} rule" in said
        assert "the other trace is shown beside this one" in said
        assert "neither is an evaluation result" in said


def test_the_report_carries_the_caption_s_numbers(tmp_paths: ProjectPaths) -> None:
    trace = _trace()
    report = render_report(trace, tmp_paths)
    for value in (
        f"{trace.interval.auprc:.4f}",
        f"{trace.positive_rate:.4f}",
        f"{trace.windows:,}",
        str(trace.choice.events),
        str(trace.choice.runner_up_events),
        DESIGN,
    ):
        assert value in report
    assert caption(trace) in report


def test_the_report_states_both_rules_side_by_side(tmp_paths: ProjectPaths) -> None:
    """Whichever rule ran, the reader is shown the other one in the same table."""
    for rule in RULES:
        report = render_report(_trace(rule), tmp_paths)
        for name in RULE_NAMES.values():
            assert name in report
        assert "Neither is an evaluation result." in report
        assert f"**This trace ran under the {RULE_NAMES[rule]} rule**" in report
        # Every candidate is listed with both quantities the rules read, so the choice
        # can be checked against the table rather than taken on trust.
        assert "positive-window rate" in report
        assert "Kelmarsh 4" in report and "Kelmarsh 5" in report


# --------------------------------------------------------------------------------------
# Choosing the turbine: two rules, both reading labels and neither reading a score


def test_the_stem_names_the_site_once() -> None:
    """A turbine id repeats its site, and the stem already carries it."""
    assert _trace().stem == "stream_trace_kelmarsh_5_2023"


def test_the_stem_does_not_carry_the_rule() -> None:
    """Two rules landing on one turbine-year would be one trace, not two."""
    assert _trace(MOST_EVENTS).stem == "stream_trace_kelmarsh_5_2023"
    assert _trace(TYPICAL_RATE).stem == "stream_trace_kelmarsh_4_2023"


def test_the_turbine_with_the_most_events_is_chosen_with_its_runner_up() -> None:
    field = _candidates({"T1": (2, 100, 4), "T2": (9, 100, 40), "T3": (5, 100, 4)})
    choice = choose_turbine(field, MOST_EVENTS, POOLED)
    assert (choice.turbine, choice.events) == ("T2", 9)
    assert (choice.runner_up, choice.runner_up_events) == ("T3", 5)
    assert set(choice.candidates) == {"T1", "T2", "T3"}
    assert not choice.tied


def test_the_turbine_nearest_the_pooled_base_rate_is_chosen() -> None:
    """The typical-rate rule reads the positive-window rate and nothing else."""
    field = _candidates({"T1": (2, 1000, 400), "T2": (9, 1000, 39), "T3": (5, 1000, 120)})
    choice = choose_turbine(field, TYPICAL_RATE, POOLED)
    assert choice.turbine == "T2"
    assert choice.chosen.rate == pytest.approx(0.039)
    assert choice.runner_up == "T3"
    # The other rule would have taken a different turbine-year, which is the point of
    # reporting both: the example is a choice, and it is visible as one.
    assert choice.picks(MOST_EVENTS) == "T2"
    assert choose_turbine(field, MOST_EVENTS, POOLED).turbine == "T2"


def test_the_two_rules_disagree_when_the_densest_turbine_year_is_not_the_typical_one() -> None:
    field = _candidates({"T1": (40, 1000, 400), "T2": (3, 1000, 39)})
    assert choose_turbine(field, MOST_EVENTS, POOLED).turbine == "T1"
    assert choose_turbine(field, TYPICAL_RATE, POOLED).turbine == "T2"


def test_a_tie_goes_to_the_lowest_turbine_id() -> None:
    field = _candidates({"T3": (4, 100, 4), "T1": (4, 100, 4), "T2": (1, 100, 90)})
    choice = choose_turbine(field, MOST_EVENTS, POOLED)
    assert choice.turbine == "T1"
    assert choice.tied


def test_a_tie_on_the_rate_goes_to_the_lowest_turbine_id() -> None:
    field = _candidates({"T2": (1, 1000, 39), "T1": (9, 1000, 39)})
    # The same rate, so the same distance, and the event counts the other rule reads are
    # not a tie-break here: the criterion is the rate and the tie-break is the id.
    choice = choose_turbine(field, TYPICAL_RATE, POOLED)
    assert choice.turbine == "T1"
    assert choice.tied


def test_an_unknown_rule_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown selection rule"):
        choose_turbine(_candidates({"T1": (1, 10, 1)}), "prettiest", POOLED)


def test_only_the_year_asked_for_is_counted() -> None:
    events = pd.concat([_events({"T1": 3}, 2023), _events({"T2": 9}, 2022)])
    assert event_counts(events, 2023) == {"T1": 3}


def test_a_year_without_an_event_is_refused() -> None:
    with pytest.raises(ValueError, match="no narrow event starts"):
        event_counts(_events({"T1": 1}, 2023), 2021)


def test_the_rate_is_taken_over_the_windows_the_trace_would_score() -> None:
    """Strided inside the turbine-year, so it is the positive rate the trace reports."""
    labels = np.zeros(12, dtype=np.float32)
    labels[::2] = 1.0
    every = WindowSet(
        key="kelmarsh__test",
        tokens=np.zeros(0, dtype=np.uint16),
        starts=np.arange(12, dtype=np.int64),
        ends=np.arange(12, dtype=np.int64) + 143,
        labels=labels,
        years=np.full(12, 2023, dtype=np.int64),
    )
    turbines = np.array(["T1"] * 6 + ["T2"] * 6, dtype=object)
    field = turbine_years(every, turbines, {"T1": 3, "T2": 4}, 2023, 2)
    # T1 takes rows 0, 2, 4 -- every label at an even row is positive.
    assert field["T1"].windows == 3
    assert field["T1"].rate == pytest.approx(1.0)
    # T2 starts at row 6, which is also even, so its strided rows are positive too.
    assert field["T2"].windows == 3
    assert field["T2"].events == 4


def test_a_turbine_with_events_but_no_window_is_not_a_candidate() -> None:
    every = WindowSet(
        key="kelmarsh__test",
        tokens=np.zeros(0, dtype=np.uint16),
        starts=np.arange(4, dtype=np.int64),
        ends=np.arange(4, dtype=np.int64) + 143,
        labels=np.zeros(4, dtype=np.float32),
        years=np.full(4, 2023, dtype=np.int64),
    )
    field = turbine_years(every, np.array(["T1"] * 4, dtype=object), {"T1": 2, "T2": 7}, 2023, 1)
    assert set(field) == {"T1"}


def test_a_year_with_no_known_window_anywhere_is_refused() -> None:
    every = WindowSet(
        key="kelmarsh__test",
        tokens=np.zeros(0, dtype=np.uint16),
        starts=np.arange(4, dtype=np.int64),
        ends=np.arange(4, dtype=np.int64) + 143,
        labels=np.zeros(4, dtype=np.float32),
        years=np.full(4, 2022, dtype=np.int64),
    )
    with pytest.raises(ValueError, match="no turbine has a known window"):
        turbine_years(every, np.array(["T1"] * 4, dtype=object), {"T1": 2}, 2023, 1)


# --------------------------------------------------------------------------------------
# The shared record, which is how each trace knows about the other


def test_a_second_rule_does_not_drop_the_first_rule_s_trace(tmp_path: Path) -> None:
    record = tmp_path / TRACE_RECORD
    write_trace(record, _trace(MOST_EVENTS).record())
    write_trace(record, _trace(TYPICAL_RATE).record())
    entries = read_traces(record)
    assert [entry["rule"] for entry in entries] == list(RULES)
    assert {entry["turbine"] for entry in entries} == {"Kelmarsh 5", "Kelmarsh 4"}
    # Rerunning one rule replaces its own entry and leaves the other alone.
    write_trace(record, _trace(MOST_EVENTS).record())
    assert [entry["rule"] for entry in read_traces(record)] == list(RULES)
    assert len(json.loads(record.read_text(encoding="utf-8"))["traces"]) == 2


def test_a_record_that_was_never_written_reads_as_nothing(tmp_path: Path) -> None:
    assert read_traces(tmp_path / TRACE_RECORD) == []
    # And the rules are still stated, because they do not depend on a trace existing.
    for name in RULE_NAMES.values():
        assert name in rules_block(())


def test_the_record_carries_the_clears_or_contains_reading() -> None:
    assert _trace().record()["clears_own_base_rate"] is True
    assert _chance_trace().record()["clears_own_base_rate"] is False
    assert _trace().record()["positive_rate"] == pytest.approx(_trace().positive_rate)


def test_both_reports_are_written_from_one_pass_and_name_each_other(
    monkeypatch: pytest.MonkeyPatch, tmp_paths: ProjectPaths, tmp_path: Path
) -> None:
    """A report written between two passes would name a trace that did not exist yet."""
    monkeypatch.setattr(stream, "trace_turbine_year", lambda *a, **k: _trace(a[-1]))
    written = write_stream_traces(tmp_paths, out_dir=tmp_path)
    assert [report.name for _, _, report in written] == [
        "stream_trace_kelmarsh_5_2023.md",
        "stream_trace_kelmarsh_4_2023.md",
    ]
    for _, _, report in written:
        body = report.read_text(encoding="utf-8")
        assert "stream_trace_kelmarsh_5_2023.md" in body
        assert "stream_trace_kelmarsh_4_2023.md" in body
    assert [entry["rule"] for entry in read_traces(tmp_path / TRACE_RECORD)] == list(RULES)


def test_the_report_names_the_other_trace_once_it_exists(tmp_paths: ProjectPaths) -> None:
    tmp_paths.data_reports_dir.mkdir(parents=True, exist_ok=True)
    write_trace(tmp_paths.data_reports_dir / TRACE_RECORD, _trace(TYPICAL_RATE).record())
    report = render_report(_trace(MOST_EVENTS), tmp_paths)
    assert "stream_trace_kelmarsh_4_2023.md" in report


# --------------------------------------------------------------------------------------
# The horizon


def test_the_horizon_is_open_on_the_left_and_closed_on_the_right() -> None:
    stamps = np.array(
        ["2023-01-01T00:00", "2023-01-01T01:00", "2023-01-02T00:00"], dtype="datetime64[ns]"
    )
    starts = np.array(["2023-01-02T00:00"], dtype="datetime64[ns]")
    hours = hours_to_next_event(stamps, starts, HORIZON_HOURS)
    # Exactly 24 h away is inside; 25 h away is not; an event at t itself is not ahead of t.
    assert hours[0] == pytest.approx(24.0)
    assert hours[1] == pytest.approx(23.0)
    # An event at t itself is not ahead of t: the interval is open on the left.
    assert np.isnan(hours[2])


def test_no_event_leaves_every_window_blank() -> None:
    stamps = np.array(["2023-01-01T00:00"], dtype="datetime64[ns]")
    assert np.isnan(hours_to_next_event(stamps, np.array([], dtype="datetime64[ns]"), 24)).all()


def test_the_event_density_is_read_off_the_calendar_year() -> None:
    """The event count is a calendar-year count, so the year is what it is divided by."""
    assert _trace().days_between_events == pytest.approx(365 / EVENTS)


# --------------------------------------------------------------------------------------
# The script


def test_the_script_runs_headless(repo_root: Path) -> None:
    """The wrapper dispatches to the CLI command without a display or a console script."""
    done = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "stream_trace.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": "", "SYSTEMROOT": "C:\\Windows", "MPLBACKEND": "Agg"},
        cwd=repo_root,
    )
    assert done.returncode == 0, done.stderr
    assert "stream-trace" in done.stdout
    # The render-only path is reachable from the same command.
    assert "--render-only" in done.stdout


def test_a_site_year_with_one_turbine_has_no_runner_up() -> None:
    """The choice is still a choice, and it still says what it had to choose from."""
    choice = choose_turbine(_candidates({"T1": (3, 100, 4)}), MOST_EVENTS, POOLED)
    assert isinstance(choice, TurbineChoice)
    # A site-year with one turbine has no runner-up to name.
    assert (choice.runner_up, choice.runner_up_events) == ("-", 0)
    assert not choice.tied


# --------------------------------------------------------------------------------------
# Rendering from the record, which is how a caption is corrected without moving a number


def _registered_trace(rule: str = MOST_EVENTS) -> StreamTrace:
    """The fixture trace with ADR-0021's registered interval, as a written trace carries."""
    trace = _trace(rule)
    return replace(
        trace,
        interval=bootstrap_auprc(
            trace.probabilities,
            trace.labels,
            window_blocks(trace.ends, np.zeros_like(trace.ends), BLOCK_STEPS),
            replicates=REPLICATES,
            seed=BOOTSTRAP_SEED,
            confidence=CONFIDENCE,
        ),
    )


def _written(out: Path, rule: str = MOST_EVENTS) -> StreamTrace:
    """Write one trace's record entry and CSV, as a scoring pass leaves them behind."""
    trace = _registered_trace(rule)
    out.mkdir(parents=True, exist_ok=True)
    write_trace(out / TRACE_RECORD, trace.record())
    write_csv(trace, out / f"{trace.stem}.csv")
    return trace


def _stub_the_field(monkeypatch: pytest.MonkeyPatch, trace: StreamTrace) -> None:
    """Stand in for the shards and the configurations, which a render still opens."""
    risk = PositiveAwareRiskStage(
        label="narrow_within_24h",
        sampling="balanced",
        positive_fraction=trace.train_rate,
        probe=PositiveBudget(positives=16, batch_windows=2, accumulate=1, learning_rate=2e-3),
        finetune=PositiveBudget(positives=16, batch_windows=2, accumulate=1, learning_rate=5e-4),
        random=PositiveBudget(positives=16, batch_windows=2, accumulate=1, learning_rate=5e-4),
    )
    monkeypatch.setattr(
        stream,
        "open_record_inputs",
        lambda *a, **k: SimpleNamespace(
            label=risk.label,
            stride=6,
            telemetry=None,
            ladder=SimpleNamespace(risk=risk),
        ),
    )
    starts = pd.DataFrame(
        {
            "turbine_id": [trace.choice.turbine] * trace.events.size,
            "start_utc": trace.events,
        }
    )
    monkeypatch.setattr(
        stream,
        "selection_field",
        lambda *a, **k: SelectionField(
            key="kelmarsh__test",
            every=None,
            turbines=np.array([], dtype=object),
            starts=starts,
            candidates=trace.choice.candidates,
        ),
    )
    monkeypatch.setattr(
        stream,
        "read_probe_record",
        lambda *a, **k: {
            "seed": SEED,
            "natural_rate": trace.natural_rate,
            "prior_band": {"shift": trace.balanced_shift},
            "pooled": {
                "base_rate": trace.pooled_base_rate,
                "auprc": trace.pooled_auprc,
                "low": trace.pooled_low,
                "high": trace.pooled_high,
                "positives": trace.pooled_positives,
                "positive_blocks": trace.pooled_positive_blocks,
            },
        },
    )


def _render(out: Path, tmp_paths: ProjectPaths) -> list[tuple[Path, Path]]:
    """Run the render-only path over a written trace."""
    return render_stream_traces(tmp_paths, rung="S2", checkpoint_dir="run", out_dir=out)


def test_a_render_only_pass_refuses_when_the_record_is_absent(
    tmp_paths: ProjectPaths, tmp_path: Path
) -> None:
    """There is nothing to render from, and inventing the numbers is the alternative."""
    empty = tmp_path / "nothing_written_yet"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match=TRACE_RECORD):
        _render(empty, tmp_paths)
    assert not list(empty.iterdir())


def test_a_render_only_pass_leaves_the_record_and_the_csv_byte_identical(
    monkeypatch: pytest.MonkeyPatch, tmp_paths: ProjectPaths, tmp_path: Path
) -> None:
    """The record is the input. A pass that rewrote it would be scoring under another name."""
    trace = _written(tmp_path)
    _stub_the_field(monkeypatch, trace)
    record = (tmp_path / TRACE_RECORD).read_bytes()
    rows = (tmp_path / f"{trace.stem}.csv").read_bytes()
    written = _render(tmp_path, tmp_paths)
    assert [path.name for pair in written for path in pair] == [
        f"{trace.stem}.svg",
        f"{trace.stem}.md",
    ]
    assert (tmp_path / TRACE_RECORD).read_bytes() == record
    assert (tmp_path / f"{trace.stem}.csv").read_bytes() == rows


def test_a_render_only_pass_prints_the_record_s_own_numbers(
    monkeypatch: pytest.MonkeyPatch, tmp_paths: ProjectPaths, tmp_path: Path
) -> None:
    """Every figure the record carries reaches the report and the figure unchanged."""
    trace = _written(tmp_path)
    _stub_the_field(monkeypatch, trace)
    _render(tmp_path, tmp_paths)
    entry = read_traces(tmp_path / TRACE_RECORD)[0]
    report = (tmp_path / f"{trace.stem}.md").read_text(encoding="utf-8")
    figure = (tmp_path / f"{trace.stem}.svg").read_text(encoding="utf-8")
    for key in ("auprc", "low", "high", "positive_rate", "mean_probability"):
        assert f"{float(entry[key]):.4f}" in report, key
    assert f"{int(entry['windows']):,}" in report
    assert f"{float(entry['seconds']):.1f} s" in report
    # The figure's own reference line is the record's positive rate, to the same digits.
    assert f"positive rate {float(entry['positive_rate']):.4f}" in figure
    assert f"{int(entry['windows']):,} windows" in figure


def test_a_render_only_pass_refuses_a_rebuild_that_disagrees_with_the_record(
    monkeypatch: pytest.MonkeyPatch, tmp_paths: ProjectPaths, tmp_path: Path
) -> None:
    """A CSV and a record that no longer agree are a corruption, not a rendering job."""
    trace = _written(tmp_path)
    _stub_the_field(monkeypatch, trace)
    record = tmp_path / TRACE_RECORD
    parsed = json.loads(record.read_text(encoding="utf-8"))
    parsed["traces"][0]["auprc"] = float(parsed["traces"][0]["auprc"]) + 0.5
    record.write_text(json.dumps(parsed, indent=2) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="auprc"):
        _render(tmp_path, tmp_paths)
    # And nothing was written: the report still says what the last honest pass said.
    assert not (tmp_path / f"{trace.stem}.md").exists()


def test_a_render_only_pass_refuses_a_trace_whose_csv_is_gone(
    monkeypatch: pytest.MonkeyPatch, tmp_paths: ProjectPaths, tmp_path: Path
) -> None:
    """The per-window scores are part of the record too, and are never re-derived."""
    trace = _written(tmp_path)
    _stub_the_field(monkeypatch, trace)
    (tmp_path / f"{trace.stem}.csv").unlink()
    with pytest.raises(FileNotFoundError, match="part of the record"):
        _render(tmp_path, tmp_paths)


def test_both_rules_are_rendered_from_one_record(
    monkeypatch: pytest.MonkeyPatch, tmp_paths: ProjectPaths, tmp_path: Path
) -> None:
    """A render reads the record for which traces exist, not a --rule the caller passes."""
    first = _written(tmp_path, MOST_EVENTS)
    second = _written(tmp_path, TYPICAL_RATE)
    _stub_the_field(monkeypatch, first)
    written = _render(tmp_path, tmp_paths)
    assert [report.name for _, report in written] == [
        f"{first.stem}.md",
        f"{second.stem}.md",
    ]
    for _, report in written:
        body = report.read_text(encoding="utf-8")
        assert f"{first.stem}.md" in body
        assert f"{second.stem}.md" in body
