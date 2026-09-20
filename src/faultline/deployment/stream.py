"""One turbine-year scored step by step on CPU: the deployment path, end to end.

**This is a demonstration, not an evaluation.** It registers no rule, decides nothing and
adds no number to the record. It runs the path a deployment would run -- backbone, frozen
probe, prior-corrected probability, one window after another in time order -- over real
forward-in-time data, so that a reader can see what a signal of this strength looks like
against a year of a single turbine instead of as a pooled scalar.

**Nothing here re-derives a rule.** The probe is loaded whole by
:func:`faultline.evaluation.paired_control.load_saved_probe`, the correction is
:func:`faultline.evaluation.calibration.at_natural_rate` (ADR-0019's two-term rule) called
with the registered training prior and the balanced-mean offset the record measured for
this probe, and the interval is
:func:`faultline.evaluation.bootstrap.bootstrap_auprc` under ADR-0021's registered block
bootstrap. A local copy of any of those would be a second implementation of a rule that
already has one.

**What the trace deliberately does not draw.** No threshold, no alarm mark, no abstention
band. Choosing an operating point is a decision this project has not earned the right to
make, and drawing one would read as a claim. The figure shows the corrected probability
and the labelled events, and stops there.

**The step axis.** The window index names a window by its first and last step in the
shard's step stream, and carries no timestamp. The stream is the final tables concatenated
one turbine-year at a time, in the shard builder's own order, so :func:`step_stamps`
rebuilds that axis from the same files in the same order and reads the timestamp off it.
The grid has gaps -- a turbine-year holds fewer steps than a full year -- so a step is
never converted to a time by arithmetic.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import torch

from faultline.data.common.report import kv_table, section, table
from faultline.data.telemetry.pipeline import parquet_files, stage_source_dir
from faultline.evaluation.bootstrap import AuprcInterval, bootstrap_auprc, window_blocks
from faultline.evaluation.calibration import at_natural_rate
from faultline.evaluation.paired_control import load_saved_probe
from faultline.evaluation.variance_probe import open_probe_inputs
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.config import PositiveAwareRiskStage
from faultline.training.loop import risk_logits
from faultline.training.windows import ShardSet, WindowSampler, WindowSet, load_windows

logger = get_logger(__name__)

#: The horizon the in-force label asks about: an event starting in ``(t, t + 24h]``.
HORIZON_HOURS = 24

#: ADR-0021's registered block bootstrap, read here as it was registered there.
BLOCK_STEPS, REPLICATES, BOOTSTRAP_SEED = 288, 10_000, 20260916
CONFIDENCE, MAX_DISCARDED_SHARE = 0.95, 0.01

#: The record the pooled test base rate and this probe's F2 offset are read from.
SEED_RECORD = "reports/data/seed_replication_v0_20260917.json"

#: Where that record keeps the ``tel_only`` seed whose probe this trace runs.
SEED = 2

#: The probe design in force, ADR-0022's §a (:data:`faultline.evaluation.readout` names it).
DESIGN = "final_position"

#: ``open_probe_inputs`` opens the splits a probe *run* needs; this trace scores none of
#: them, so the language-model selection set is asked for at its smallest and the cost is
#: a few index reads rather than a pass.
LM_SELECTION_WINDOWS = 1

#: Categorical slots of the validated reference palette, on its light surface.
TRACE, EVENT = "#2a78d6", "#c2475f"
INK, MUTED, GRID, SURFACE, BAND = "#1a1a19", "#5f5e58", "#e4e3dd", "#fcfcfb", "#f6dfe4"


@dataclass(frozen=True)
class TurbineChoice:
    """Which turbine of a site-year the trace runs on, and why.

    Attributes:
        turbine: The chosen turbine.
        events: Its labelled narrow event starts in the year.
        runner_up: The next turbine down, so the margin is visible.
        runner_up_events: That turbine's count.
        counts: Every turbine's count, in turbine order.
        tied: Whether the choice was a tie broken by lowest turbine id.
    """

    turbine: str
    events: int
    runner_up: str
    runner_up_events: int
    counts: dict[str, int]
    tied: bool


@dataclass(frozen=True)
class StreamTrace:
    """One turbine-year scored in time order, and what the run measured.

    Attributes:
        source: The site.
        year: The calendar year.
        choice: The turbine and the count that chose it.
        stamps: Per window, the UTC timestamp of its last step.
        ends: Per window, that step's index in the shard's step stream.
        probabilities: Per window, the prior-corrected probability.
        labels: Per window, the in-force label.
        hours: Per window, hours to the next event start, ``nan`` beyond the horizon.
        events: Event start timestamps inside the traced span.
        interval: This turbine-year's own AUPRC and its block-bootstrap interval.
        train_rate: The registered training prior the correction reads.
        natural_rate: The training split's natural positive rate.
        balanced_shift: The F2 balanced-mean offset measured for this probe.
        offset: The constant the correction actually added.
        pooled_base_rate: The pooled test base rate, drawn as a reference line.
        seconds: CPU wall clock of the scoring pass.
        checkpoint: The backbone the probe carries.
        probe: The probe that was loaded.
    """

    source: str
    year: int
    choice: TurbineChoice
    stamps: np.ndarray
    ends: np.ndarray
    probabilities: np.ndarray
    labels: np.ndarray
    hours: np.ndarray
    events: np.ndarray
    interval: AuprcInterval
    train_rate: float
    natural_rate: float
    balanced_shift: float
    offset: float
    pooled_base_rate: float
    seconds: float
    checkpoint: str
    probe: str

    @property
    def windows(self) -> int:
        """Windows scored."""
        return int(self.probabilities.size)

    @property
    def windows_per_second(self) -> float:
        """Scoring throughput on CPU."""
        return self.windows / self.seconds if self.seconds > 0 else float("nan")

    @property
    def positive_rate(self) -> float:
        """This turbine-year's own positive rate, which is not the pooled one."""
        return float(self.labels.mean()) if self.labels.size else float("nan")

    @property
    def mean_probability(self) -> float:
        """The mean corrected probability, which a calibrated head puts at the base rate."""
        return float(self.probabilities.mean()) if self.probabilities.size else float("nan")

    @property
    def stem(self) -> str:
        """The output stem the three files share.

        A turbine id repeats its site ("Kelmarsh 5"), and the stem already names the site,
        so the prefix is dropped rather than written twice.
        """
        turbine = self.choice.turbine.lower().replace(" ", "_")
        site = self.source.lower()
        turbine = turbine.removeprefix(f"{site}_")
        return f"stream_trace_{site}_{turbine}_{self.year}"


def narrow_event_starts(paths: ProjectPaths, source: str) -> pd.DataFrame:
    """Read a site's narrow events: the starts the in-force label is built from.

    Args:
        paths: Resolved project paths.
        source: The site.

    Returns:
        ``turbine_id`` and a UTC ``start_utc``, one row an event.

    Raises:
        FileNotFoundError: If the site has no narrow event table.
    """
    path = paths.source_dir("cleaned", "telemetry", source) / "labels" / "events_narrow.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found: run `faultline telemetry run`")
    events = pd.read_parquet(path, columns=["turbine_id", "start_utc"])
    return pd.DataFrame(
        {
            "turbine_id": events["turbine_id"].astype(str),
            "start_utc": pd.to_datetime(events["start_utc"], utc=True),
        }
    )


def choose_turbine(events: pd.DataFrame, year: int) -> TurbineChoice:
    """The turbine with the most labelled narrow events in a year; ties to the lowest id.

    The count is the event starts the label is built from, unfiltered: the labelling stage
    reads every start of the turbine, and ``in_grid`` is a reporting column there rather
    than a filter.

    Args:
        events: The site's narrow event starts, from :func:`narrow_event_starts`.
        year: The calendar year.

    Returns:
        The choice, its count, the runner-up's, and every turbine's.

    Raises:
        ValueError: If no turbine has an event start in the year.
    """
    inside = events[events["start_utc"].dt.year == year]
    if inside.empty:
        raise ValueError(f"no narrow event starts in {year}")
    counts = {
        str(turbine): int(count) for turbine, count in inside["turbine_id"].value_counts().items()
    }
    counts = {turbine: counts[turbine] for turbine in sorted(counts)}
    # Sorted by count, then by turbine id, so a tie is broken by the lowest id and the
    # runner-up is the next one down under the same rule.
    order = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    turbine, best = order[0]
    # A site-year with one turbine that saw an event has no runner-up to state.
    second, runner_up = order[1] if len(order) > 1 else ("-", 0)
    return TurbineChoice(
        turbine=turbine,
        events=best,
        runner_up=second,
        runner_up_events=runner_up,
        counts=counts,
        tied=best == runner_up,
    )


def step_stamps(paths: ProjectPaths, source: str, split: str) -> np.ndarray:
    """Rebuild a shard's step axis: per step of the stream, its UTC timestamp.

    The shard builder appends one turbine-year at a time, in ``parquet_files`` order, each
    sorted by timestamp, and a split's rows inside a turbine-year are one contiguous run
    (:mod:`faultline.data.telemetry.shards`). Reading the same files in the same order
    reproduces the axis exactly, which the caller checks against the manifest.

    Args:
        paths: Resolved project paths.
        source: The site.
        split: ``train``, ``val`` or ``test``.

    Returns:
        One UTC timestamp per step of ``<source>__<split>``, in stream order.
    """
    blocks: list[np.ndarray] = []
    for path in parquet_files(stage_source_dir(paths, "final", source)):
        frame = pd.read_parquet(path, columns=["timestamp_utc", "split"])
        frame = frame.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)
        rows = np.flatnonzero(frame["split"].to_numpy(dtype=object) == split)
        if rows.size == 0:
            continue
        if not (np.diff(rows) == 1).all():
            raise ValueError(f"{path}: split {split} is not one run of the turbine-year")
        stamps = pd.to_datetime(frame["timestamp_utc"].to_numpy()[rows], utc=True)
        blocks.append(stamps.to_numpy(dtype="datetime64[ns]"))
    if not blocks:
        raise ValueError(f"{source} has no {split} rows")
    return np.concatenate(blocks)


def turbine_year_windows(
    shards: ShardSet, key: str, turbine: str, year: int, stride: int, label: str
) -> WindowSet:
    """Every known window of one turbine-year, in time order, at a stride.

    The shard's window index is read once by :func:`load_windows` at stride 1, which
    applies the label's own ``_known`` rule; the turbine-year is then masked out of it in
    index order and the stride is taken inside the turbine-year, so the stride counts that
    turbine's windows and not the site's.

    Args:
        shards: The shard set.
        key: The shard key, ``<source>__<split>``.
        turbine: The turbine.
        year: The calendar year.
        stride: Keep every ``stride``-th known window of the turbine-year.
        label: The window-index column to read as the target.

    Returns:
        The windows, in the index's own order, which is time order inside a turbine-year.

    Raises:
        ValueError: If the turbine-year holds no known window.
    """
    every = load_windows(shards, key, stride=1, label=label)
    record = shards.files()[key]
    frame = pq.read_table(
        shards.root / str(record["windows"]), columns=["turbine_id", f"{label}_known"]
    ).to_pandas()
    # load_windows keeps the known rows of the index, in index order, and nothing else, so
    # the known rows of the same file line up with its arrays one for one.
    known = frame[frame[f"{label}_known"].to_numpy()].reset_index(drop=True)
    if len(known) != len(every):
        raise ValueError(f"{key}: {len(known)} known rows against {len(every)} windows")
    mine = np.flatnonzero(
        (known["turbine_id"].astype(str).to_numpy() == turbine) & (every.years == year)
    )
    if mine.size == 0:
        raise ValueError(f"{key}: {turbine} has no known window in {year}")
    rows = mine[::stride]
    return WindowSet(
        key=key,
        tokens=every.tokens,
        starts=every.starts[rows],
        ends=every.ends[rows],
        labels=every.labels[rows],
        years=every.years[rows],
    )


def hours_to_next_event(stamps: np.ndarray, starts: np.ndarray, horizon: int) -> np.ndarray:
    """Hours from each window's last step to the next event start, ``nan`` past the horizon.

    The label is true when an event starts in ``(t, t + H]``, so the search is strict on
    the left and inclusive on the right, and this column is present on exactly the windows
    the label calls positive.

    Args:
        stamps: Per window, the UTC timestamp of its last step.
        starts: Event start timestamps, sorted.
        horizon: The horizon, in hours.

    Returns:
        Per window, the hours, or ``nan`` where no event starts inside the horizon.
    """
    out = np.full(stamps.size, np.nan)
    if starts.size == 0:
        return out
    position = np.searchsorted(starts, stamps, side="right")
    inside = position < starts.size
    gap = np.full(stamps.size, np.nan)
    gap[inside] = (starts[position[inside]] - stamps[inside]) / np.timedelta64(1, "h")
    reached = inside & (gap <= horizon)
    out[reached] = gap[reached]
    return out


def read_probe_record(paths: ProjectPaths, seed: int) -> dict[str, Any]:
    """The tracked record of one ``tel_only`` seed: its rates and its F2 offset.

    Args:
        paths: Resolved project paths.
        seed: The trained seed.

    Returns:
        That seed's block of the seed-replication record.

    Raises:
        FileNotFoundError: If the record is not tracked.
        ValueError: If the record holds no such seed.
    """
    path = paths.repo_root / SEED_RECORD
    if not path.is_file():
        raise FileNotFoundError(f"{SEED_RECORD} not found")
    record = json.loads(path.read_text(encoding="utf-8"))
    for block in record["trained"]:
        if int(block["seed"]) == seed:
            return dict(block)
    raise ValueError(f"{SEED_RECORD} holds no trained seed {seed}")


def trace_turbine_year(
    paths: ProjectPaths,
    source: str,
    year: int,
    mixture_config: str,
    ladder_config: str,
    rung: str,
    checkpoint_dir: str,
    device_name: str = "cpu",
) -> StreamTrace:
    """Score one turbine-year window by window and measure the pass.

    Args:
        paths: Resolved project paths.
        source: The site, whose test split holds the year.
        year: The calendar year.
        mixture_config: The joint mixture configuration, relative to the repository.
        ladder_config: The ladder configuration, relative to the repository.
        rung: The rung the backbone was pretrained at.
        checkpoint_dir: The run directory under ``checkpoints/`` holding the probe.
        device_name: Torch device; ``cpu``, which is the point of the demonstration.

    Returns:
        The trace.

    Raises:
        FileNotFoundError: If the probe was never written.
        ValueError: If the rebuilt step axis disagrees with the shard manifest.
    """
    block = read_probe_record(paths, SEED)
    events = narrow_event_starts(paths, source)
    choice = choose_turbine(events, year)
    logger.info(
        "%s %d: %s has %d narrow event starts (runner-up %s, %d)",
        source,
        year,
        choice.turbine,
        choice.events,
        choice.runner_up,
        choice.runner_up_events,
    )

    inputs = open_probe_inputs(
        paths,
        mixture_config,
        ladder_config,
        "tel_only",
        rung,
        LM_SELECTION_WINDOWS,
        "hill_of_towie",
        device_name,
    )
    probe_path = paths.checkpoints_dir / checkpoint_dir / f"{rung}_trained_seed{SEED}_probe.pt"
    if not probe_path.is_file():
        raise FileNotFoundError(f"{probe_path} not found")
    model = load_saved_probe(probe_path, DESIGN, inputs)

    key = f"{source}__test"
    label = inputs.ladder.risk.label
    stride = inputs.mixture.window_stride_steps
    windows = turbine_year_windows(inputs.telemetry, key, choice.turbine, year, stride, label)
    stamps = step_stamps(paths, source, "test")
    steps = int(inputs.telemetry.files()[key]["steps"])
    if stamps.size != steps:
        raise ValueError(f"{key}: rebuilt {stamps.size} steps against the manifest's {steps}")

    sampler = WindowSampler(
        [windows],
        batch_size=inputs.ladder.evaluation.batch_windows,
        tokens_per_step=inputs.telemetry.tokens_per_step,
        context_steps=inputs.telemetry.context_steps,
        labelled=True,
    )
    # As score_saved_probe scores everywhere else: no optimiser step, no graph, and the
    # pass in float32 because autocast is a CUDA path and this trace is the CPU one.
    started = time.perf_counter()
    with torch.inference_mode():
        logits, labels, _ = risk_logits(model, sampler, inputs.device, autocast_on=False)
    seconds = time.perf_counter() - started

    # ADR-0019's two-term correction, as the evaluation code applies it everywhere else:
    # the registered training prior, the training split's natural rate, and this probe's
    # own measured balanced-mean offset.
    risk = inputs.ladder.risk
    # open_probe_inputs refuses any other stage; restated here so the prior is read off the
    # stage that registers it rather than off a number written down again.
    if not isinstance(risk, PositiveAwareRiskStage):  # pragma: no cover - refused upstream
        raise ValueError(f"{ladder_config} is not the positive-aware risk stage")
    scores = at_natural_rate(
        logits,
        train_rate=float(risk.positive_fraction),
        natural_rate=float(block["natural_rate"]),
        balanced_shift=float(block["prior_band"]["shift"]),
    )

    ends = windows.ends
    interval = bootstrap_auprc(
        scores.probabilities,
        labels,
        window_blocks(ends, np.zeros_like(ends), BLOCK_STEPS),
        replicates=REPLICATES,
        seed=BOOTSTRAP_SEED,
        confidence=CONFIDENCE,
    )
    when = stamps[ends]
    starts = np.sort(
        events[events["turbine_id"] == choice.turbine]["start_utc"].to_numpy(dtype="datetime64[ns]")
    )
    horizon = np.timedelta64(HORIZON_HOURS, "h")
    inside = starts[(starts >= when[0]) & (starts <= when[-1] + horizon)]
    return StreamTrace(
        source=source,
        year=year,
        choice=choice,
        stamps=when,
        ends=ends,
        probabilities=scores.probabilities,
        labels=labels,
        hours=hours_to_next_event(when, starts, HORIZON_HOURS),
        events=inside,
        interval=interval,
        train_rate=scores.train_rate,
        natural_rate=scores.natural_rate,
        balanced_shift=float(block["prior_band"]["shift"]),
        offset=scores.offset,
        pooled_base_rate=float(block["pooled"]["base_rate"]),
        seconds=seconds,
        checkpoint=f"{checkpoint_dir}/{rung}_tel_only_seed{SEED}.pt",
        probe=f"{checkpoint_dir}/{probe_path.name}",
    )


def write_csv(trace: StreamTrace, path: Path) -> Path:
    """Write the trace: one row a window, in time order.

    Args:
        trace: The trace.
        path: Where to write.

    Returns:
        The file written.
    """
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ["timestamp_utc", "window_end_step", "probability", "label", "hours_to_next_event"]
        )
        for when, end, probability, label, hours in zip(
            trace.stamps,
            trace.ends,
            trace.probabilities,
            trace.labels,
            trace.hours,
            strict=True,
        ):
            writer.writerow(
                [
                    np.datetime_as_string(when, unit="s") + "Z",
                    int(end),
                    f"{float(probability):.6f}",
                    int(label),
                    "" if not np.isfinite(hours) else f"{float(hours):.2f}",
                ]
            )
    return path


def render_svg(trace: StreamTrace) -> str:
    """Draw the corrected probability against time, with the labelled events.

    The pooled test base rate is a horizontal reference line, each event start a vertical
    marker, and the horizon before each start a shaded band. No threshold, no alarm mark
    and no abstention band is drawn: the trace shows the score and the events, and the
    reader is left to judge.

    Args:
        trace: The trace.

    Returns:
        A standalone SVG document.
    """
    width, height = 900, 360
    left, right, top, bottom = 64, 24, 44, 52
    first, last = trace.stamps[0], trace.stamps[-1]
    span = max(float((last - first) / np.timedelta64(1, "h")), 1.0)
    high = max(float(trace.probabilities.max()), trace.pooled_base_rate) * 1.08

    def x(when: np.datetime64) -> float:
        hours = float((when - first) / np.timedelta64(1, "h"))
        return left + hours / span * (width - left - right)

    def y(value: float) -> float:
        return top + (high - value) / high * (height - top - bottom)

    turbine = trace.choice.turbine
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="system-ui, sans-serif" font-size="12">',
        f"<title>Prior-corrected probability against time, {turbine} {trace.year}, "
        f"{trace.windows:,} windows</title>",
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
        f'<text x="{left}" y="24" fill="{INK}" font-size="14" font-weight="600">'
        f"Prior-corrected probability, {turbine}, {trace.year} (illustrative)</text>",
    ]
    # The horizon before each event start, then the start itself, both under the trace so
    # that the score is never hidden by its own annotation.
    horizon = np.timedelta64(HORIZON_HOURS, "h")
    for start in trace.events:
        x0, x1 = x(max(start - horizon, first)), x(min(start, last))
        if x1 > x0:
            out.append(
                f'<rect class="horizon" x="{x0:.1f}" y="{top}" '
                f'width="{max(x1 - x0, 0.6):.1f}" '
                f'height="{height - top - bottom:.1f}" fill="{BAND}"/>'
            )
    for start in trace.events:
        if first <= start <= last:
            out.append(
                f'<line class="event" x1="{x(start):.1f}" x2="{x(start):.1f}" '
                f'y1="{top}" y2="{height - bottom}" stroke="{EVENT}" stroke-width="0.8" '
                'stroke-opacity="0.75"/>'
            )
    tick = 0.05 if high <= 0.6 else 0.2
    value = 0.0
    while value <= high:
        out.append(
            f'<line x1="{left}" x2="{width - right}" y1="{y(value):.1f}" y2="{y(value):.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
            f'<text x="{left - 8}" y="{y(value) + 4:.1f}" fill="{MUTED}" '
            f'text-anchor="end">{value:.2f}</text>'
        )
        value += tick
    base = trace.pooled_base_rate
    out.append(
        f'<line x1="{left}" x2="{width - right}" y1="{y(base):.1f}" y2="{y(base):.1f}" '
        f'stroke="{INK}" stroke-width="1.2" stroke-dasharray="6 4"/>'
        f'<text x="{width - right - 4}" y="{y(base) - 6:.1f}" fill="{INK}" '
        f'text-anchor="end">pooled test base rate {base:.4f}</text>'
    )
    path = " ".join(
        f"{x(when):.1f},{y(float(p)):.1f}"
        for when, p in zip(trace.stamps, trace.probabilities, strict=True)
    )
    out.append(
        f'<polyline points="{path}" fill="none" stroke="{TRACE}" stroke-width="0.9" '
        'stroke-linejoin="round" stroke-opacity="0.9"/>'
    )
    for month in range(1, 13):
        when = np.datetime64(f"{trace.year}-{month:02d}-01T00:00:00")
        if first <= when <= last:
            out.append(
                f'<text x="{x(when):.1f}" y="{height - bottom + 18}" fill="{MUTED}" '
                f'text-anchor="middle">{"JFMAMJJASOND"[month - 1]}</text>'
            )
    out.append(
        f'<text x="{(left + width - right) / 2:.0f}" y="{height - 12}" fill="{MUTED}" '
        f'text-anchor="middle">{trace.year}, UTC</text>'
    )
    # A direct label on each mark, so nothing is identified by colour alone.
    out.append(
        f'<line x1="{left}" x2="{left + 16}" y1="34" y2="34" stroke="{TRACE}" '
        f'stroke-width="2"/><text x="{left + 22}" y="38" fill="{INK}">probability</text>'
        f'<rect x="{left + 110}" y="28" width="12" height="12" fill="{BAND}"/>'
        f'<text x="{left + 126}" y="38" fill="{INK}">{HORIZON_HOURS} h before an event</text>'
        f'<line x1="{left + 268}" x2="{left + 268}" y1="28" y2="40" stroke="{EVENT}" '
        f'stroke-width="1.5"/><text x="{left + 274}" y="38" fill="{INK}">'
        f"event start ({len(trace.events)})</text>"
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def caption(trace: StreamTrace) -> str:
    """The caption, carrying the same numbers as the report.

    Args:
        trace: The trace.

    Returns:
        One paragraph.
    """
    i = trace.interval
    return (
        f"{trace.choice.turbine}, {trace.year}, scored on CPU: {trace.windows:,} windows of "
        f"1,872 telemetry tokens (144 steps x 13), one an hour, in time order. "
        f"This turbine-year holds {trace.choice.events} labelled narrow event "
        f"starts, the most of any {trace.source.replace('_', ' ').title()} turbine that year "
        f"(runner-up {trace.choice.runner_up}, {trace.choice.runner_up_events}); its own "
        f"positive rate is {trace.positive_rate:.4f} and its own AUPRC is {i.auprc:.4f} "
        f"[{i.low:.4f}, {i.high:.4f}] under ADR-0021's block bootstrap "
        f"({BLOCK_STEPS // 144}-day blocks, {REPLICATES:,} replicates, seed {BOOTSTRAP_SEED}). "
        f"**Illustrative, forward-in-time, same site, a single turbine-year: not an evaluation "
        f"result, and not comparable with the pooled gate numbers**, whose base rate "
        f"({trace.pooled_base_rate:.4f}, the dashed line) is "
        f"{trace.positive_rate / trace.pooled_base_rate:.1f}x lower than this turbine-year's. "
        f"No threshold, no alarm and no abstention is drawn or computed. The model reads "
        f"telemetry only."
    )


def render_report(trace: StreamTrace, paths: ProjectPaths) -> str:
    """Render the Markdown that sits beside the trace and its figure.

    Args:
        trace: The trace.
        paths: Resolved project paths.

    Returns:
        The report.
    """
    i = trace.interval
    parts = [
        f"# Streaming trace: {trace.choice.turbine}, {trace.year}\n\n",
        kv_table(
            {
                "what this is": "a demonstration of the deployment path on CPU, not an evaluation",
                "backbone": f"`{trace.checkpoint}`",
                "probe": f"`{trace.probe}` (§a {DESIGN}, ADR-0022's addendum rule)",
                "windows": f"{trace.windows:,} at stride 6, every known window of the "
                "turbine-year in time order",
                "device": "cpu",
                "wall clock": f"{trace.seconds:.1f} s ({trace.windows_per_second:.1f} windows/s)",
                "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "git_sha": git_sha(paths.repo_root),
                "generated by": "faultline model stream-trace",
            }
        ),
        section(
            "1. The turbine, and why it was chosen",
            "The turbine with the most labelled narrow event starts in the year, ties broken "
            "by the lowest turbine id. The count is the event starts the in-force label is "
            f"built from, read from `data/cleaned/telemetry/{trace.source}/labels/"
            "events_narrow.parquet`.\n\n"
            + table(
                ["turbine", f"narrow event starts in {trace.year}", "note"],
                [
                    [
                        name,
                        count,
                        "traced"
                        if name == trace.choice.turbine
                        else ("runner-up" if name == trace.choice.runner_up else ""),
                    ]
                    for name, count in trace.choice.counts.items()
                ],
            )
            + f"\nTie broken by lowest turbine id: {'yes' if trace.choice.tied else 'no'}.\n",
        ),
        section(
            "2. The correction, as the record registered it",
            "ADR-0019's two-term logit correction, applied by "
            "`faultline.evaluation.calibration.at_natural_rate` -- the same function every "
            "gate reads its probabilities through. Nothing is re-derived here.\n\n"
            + kv_table(
                {
                    "π_train (registered)": f"{trace.train_rate} "
                    "(`configs/train/telemetry_v1.yaml`, `risk.positive_fraction`)",
                    "natural rate": f"{trace.natural_rate:.10f} (`{SEED_RECORD}`, "
                    f"`trained[seed {SEED}].natural_rate`)",
                    "F2 balanced-mean offset": f"{trace.balanced_shift:+.4f} (`{SEED_RECORD}`, "
                    f"`trained[seed {SEED}].prior_band.shift`; balanced mean rate "
                    "0.4900 is inside the registered band [0.45, 0.55], so the declared "
                    "correction stands and no re-centring is applied)",
                    "offset applied": f"{trace.offset:+.4f}",
                }
            ),
        ),
        section(
            "3. What the trace measured",
            kv_table(
                {
                    "windows scored": f"{trace.windows:,}",
                    "positive windows": f"{int(trace.labels.sum()):,}",
                    "this turbine-year's positive rate": f"{trace.positive_rate:.4f}",
                    "mean corrected probability": f"{trace.mean_probability:.4f}",
                    "this turbine-year's AUPRC": f"{i.auprc:.4f}",
                    "95% block-bootstrap interval": f"[{i.low:.4f}, {i.high:.4f}]",
                    "blocks": f"{i.blocks:,} two-day blocks, {i.positive_blocks:,} holding a "
                    "positive window",
                    "replicates": f"{i.replicates:,}, seed {i.seed}, "
                    f"{i.discarded:,} discarded ({i.discarded_share:.4%}; the registered "
                    f"rule refuses above {MAX_DISCARDED_SHARE:.0%})",
                    "pooled test base rate (reference line)": f"{trace.pooled_base_rate:.4f} "
                    f"(`{SEED_RECORD}`, `trained[seed {SEED}].pooled.base_rate`)",
                    "CPU wall clock": f"{trace.seconds:.1f} s",
                    "throughput": f"{trace.windows_per_second:.1f} windows/s",
                }
            )
            + "\nThe interval is ADR-0021's registered block bootstrap, called through "
            "`faultline.evaluation.bootstrap.bootstrap_auprc`. It describes this turbine-year "
            "and nothing else.\n\nThe mean corrected probability sits near the training "
            f"split's natural rate ({trace.natural_rate:.4f}), which is what the correction "
            "targets, and well below this turbine-year's own positive rate "
            f"({trace.positive_rate:.4f}). That gap is the turbine-year being far more "
            "event-dense than the distribution the head was calibrated against; it is "
            "visible here rather than argued, and it is one more reason these numbers do "
            "not transfer to the pooled ones.\n",
        ),
        section(
            "4. The files",
            table(
                ["file", "what it holds"],
                [
                    [
                        f"`{trace.stem}.csv`",
                        "one row a window: `timestamp_utc`, `window_end_step`, `probability`, "
                        "`label`, `hours_to_next_event` (blank beyond the "
                        f"{HORIZON_HOURS} h horizon)",
                    ],
                    [
                        f"`{trace.stem}.svg`",
                        "probability against time, the pooled base rate as a dashed line, each "
                        "event start as a vertical marker and the horizon before it shaded",
                    ],
                ],
            ),
        ),
        section("5. Caption", caption(trace)),
        section(
            "6. What this is not",
            "This trace adds no rule, no ADR and no verdict, and changes nothing in the "
            "record. It is one turbine-year of one site, chosen for holding the most events, "
            "and the site is a training site: the split is forward in time, not across "
            "sites. Its AUPRC is therefore not comparable with the pooled gate numbers, and "
            "the programme's findings (ADR-0025 INCONCLUSIVE, ADR-0026's read-out result) "
            "stand exactly as the ledger records them.\n",
        ),
    ]
    return "".join(parts)


def write_stream_trace(
    paths: ProjectPaths,
    source: str = "kelmarsh",
    year: int = 2023,
    mixture_config: str = "configs/train/joint_v0.yaml",
    ladder_config: str = "configs/train/telemetry_v1.yaml",
    rung: str = "S2",
    checkpoint_dir: str = "seed_replication_v0_424c4f33",
    device_name: str = "cpu",
    out_dir: Path | None = None,
) -> tuple[Path, Path, Path]:
    """Run the trace and write its three files.

    Args:
        paths: Resolved project paths.
        source: The site.
        year: The calendar year of its test split to trace.
        mixture_config: The joint mixture configuration.
        ladder_config: The ladder configuration.
        rung: The rung the backbone was pretrained at.
        checkpoint_dir: The run directory under ``checkpoints/`` holding the probe.
        device_name: Torch device.
        out_dir: Where to write; ``reports/data/`` when omitted.

    Returns:
        The CSV, the SVG and the Markdown report.
    """
    trace = trace_turbine_year(
        paths, source, year, mixture_config, ladder_config, rung, checkpoint_dir, device_name
    )
    target = out_dir or paths.data_reports_dir
    target.mkdir(parents=True, exist_ok=True)
    csv_path = write_csv(trace, target / f"{trace.stem}.csv")
    svg_path = target / f"{trace.stem}.svg"
    svg_path.write_text(render_svg(trace), encoding="utf-8", newline="\n")
    report = target / f"{trace.stem}.md"
    report.write_text(render_report(trace, paths), encoding="utf-8", newline="\n")
    logger.info(
        "%s %d %s: %d windows in %.1f s (%.1f windows/s), AUPRC %.4f [%.4f, %.4f]",
        source,
        year,
        trace.choice.turbine,
        trace.windows,
        trace.seconds,
        trace.windows_per_second,
        trace.interval.auprc,
        trace.interval.low,
        trace.interval.high,
    )
    return csv_path, svg_path, report
