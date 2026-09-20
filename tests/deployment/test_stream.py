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
    DESIGN,
    HORIZON_HOURS,
    SEED,
    StreamTrace,
    TurbineChoice,
    TurbineYear,
    caption,
    choose_turbine,
    event_counts,
    hours_to_next_event,
    render_report,
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
        "pooled": {"base_rate": 0.0388, "auprc": 0.0576, "low": 0.0503, "high": 0.0670},
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
    """And why the two differ: the correction targets the training prior, not this turbine."""
    trace = _trace()
    said = caption(trace)
    assert f"mean corrected probability is {trace.mean_probability:.4f}" in said
    assert f"targets the training prior {trace.natural_rate:.4f}" in said
    assert "not this turbine-year's" in said


def test_the_caption_refuses_the_pooled_comparison_with_both_numbers() -> None:
    trace = _trace()
    said = caption(trace)
    ratio = trace.positive_rate / trace.pooled_base_rate
    assert f"pooled test AUPRC ({trace.pooled_auprc:.4f}" in said
    assert f"{ratio:.1f}x the pooled {trace.pooled_base_rate:.4f}" in said


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


def test_a_site_year_with_one_turbine_has_no_runner_up() -> None:
    """The choice is still a choice, and it still says what it had to choose from."""
    choice = choose_turbine(_candidates({"T1": (3, 100, 4)}), MOST_EVENTS, POOLED)
    assert isinstance(choice, TurbineChoice)
    # A site-year with one turbine has no runner-up to name.
    assert (choice.runner_up, choice.runner_up_events) == ("-", 0)
    assert not choice.tied
