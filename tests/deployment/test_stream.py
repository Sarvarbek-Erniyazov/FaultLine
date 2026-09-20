"""The CPU streaming trace: the deployment path over one held-out turbine-year."""

from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from faultline.deployment import stream
from faultline.deployment.stream import (
    BLOCK_STEPS,
    DESIGN,
    HORIZON_HOURS,
    SEED,
    StreamTrace,
    TurbineChoice,
    caption,
    choose_turbine,
    hours_to_next_event,
    render_report,
    render_svg,
    trace_turbine_year,
    write_csv,
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


def _trace() -> StreamTrace:
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
    return StreamTrace(
        source="kelmarsh",
        year=2023,
        choice=TurbineChoice("Kelmarsh 5", EVENTS, "Kelmarsh 4", 1, {"Kelmarsh 5": EVENTS}, False),
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
        pooled_base_rate=0.0388,
        seconds=12.0,
        checkpoint="run/S2_tel_only_seed2.pt",
        probe="run/S2_trained_seed2_probe.pt",
    )


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
        "pooled": {"base_rate": 0.0388},
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


def test_the_figure_draws_the_base_rate_and_no_operating_point() -> None:
    trace = _trace()
    svg = render_svg(trace)
    assert f"{trace.pooled_base_rate:.4f}" in svg
    for banned in ("threshold", "alarm", "abstention", "abstain"):
        assert banned not in svg.lower()


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


# --------------------------------------------------------------------------------------
# Choosing the turbine, and reading the horizon


def test_the_stem_names_the_site_once() -> None:
    """A turbine id repeats its site, and the stem already carries it."""
    assert _trace().stem == "stream_trace_kelmarsh_5_2023"


def test_the_turbine_with_the_most_events_is_chosen_with_its_runner_up() -> None:
    choice = choose_turbine(_events({"T1": 2, "T2": 9, "T3": 5}), 2023)
    assert (choice.turbine, choice.events) == ("T2", 9)
    assert (choice.runner_up, choice.runner_up_events) == ("T3", 5)
    assert choice.counts == {"T1": 2, "T2": 9, "T3": 5}
    assert not choice.tied


def test_a_tie_goes_to_the_lowest_turbine_id() -> None:
    choice = choose_turbine(_events({"T3": 4, "T1": 4, "T2": 1}), 2023)
    assert choice.turbine == "T1"
    assert choice.tied


def test_only_the_year_asked_for_is_counted() -> None:
    events = pd.concat([_events({"T1": 3}, 2023), _events({"T2": 9}, 2022)])
    choice = choose_turbine(events, 2023)
    assert (choice.turbine, choice.events) == ("T1", 3)
    # The other turbine saw nothing that year, so there is no runner-up to name.
    assert (choice.runner_up, choice.runner_up_events) == ("-", 0)


def test_a_year_without_an_event_is_refused() -> None:
    with pytest.raises(ValueError, match="no narrow event starts"):
        choose_turbine(_events({"T1": 1}, 2023), 2021)


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
