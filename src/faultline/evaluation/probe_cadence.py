"""The in-force probe re-trained under a finer evaluation cadence (ADR-0024, G3 addendum).

Every trained probe so far selected its first validation measurement, step 166 of 1,000. This
module re-trains the probe in force (§a under G1) on the gate run's backbone with its seed. It
measures at step 0 (a reference that is never selected), every 25 steps through 300, then every
100. A measurement takes no step and draws no training randomness, so the optimiser trajectory is
the one G1 reproduced, and only where it is looked at changes. The checkpoint selected here is the
one F2 measures.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.evaluation.bootstrap import AuprcInterval
from faultline.evaluation.gate_check import GateCheckConfig, save_scores
from faultline.evaluation.ladder import build_split
from faultline.evaluation.paired_control import (
    SECTION,
    PairedControlConfig,
    save_split_scores,
    score_saved_probe,
)
from faultline.evaluation.probe_control import (
    HEAD_LAYERS,
    POOLING,
    UNFROZEN_BLOCKS,
    ProbeControlConfig,
    ScoredWindows,
    trained_scores_path,
)
from faultline.evaluation.variance_probe import open_probe_inputs, probe_and_score
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)


class ProbeCadenceConfig(StrictModel):
    """Top level of ``configs/train/probe_cadence_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        paired_config: The paired control: the design in force, the stride, the gate run.
        measure_initial: Measure the untrained head as a reference.
        dense_every: Steps between measurements in the dense stretch.
        dense_until: The last step of the dense stretch.
        sparse_every: Steps between measurements after it.
    """

    version: int = 0
    paired_config: str
    measure_initial: bool
    dense_every: int = Field(gt=0)
    dense_until: int = Field(gt=0)
    sparse_every: int = Field(gt=0)

    @model_validator(mode="after")
    def _nested(self) -> ProbeCadenceConfig:
        """Refuse a dense stretch that is not a whole number of its own intervals.

        Raises:
            ValueError: If ``dense_until`` is not a multiple of ``dense_every``.
        """
        if self.dense_until % self.dense_every:
            raise ValueError(
                f"dense_until {self.dense_until} is not a multiple of {self.dense_every}"
            )
        return self

    def steps(self, total: int) -> list[int]:
        """The measurement steps, counted from one, within a run of ``total`` steps."""
        dense = range(self.dense_every, min(self.dense_until, total) + 1, self.dense_every)
        sparse = range(self.dense_until + self.sparse_every, total + 1, self.sparse_every)
        return sorted({*dense, *sparse})


def _newest_record(paths: ProjectPaths, stem: str) -> dict[str, Any]:
    found = sorted(paths.data_reports_dir.glob(f"{stem}_[0-9]*.json"))
    if not found:
        raise FileNotFoundError(f"no {stem}_<date>.json record")
    record: dict[str, Any] = json.loads(found[-1].read_text(encoding="utf-8"))
    return record


def run_probe_cadence(
    paths: ProjectPaths, config_path: Path, device_name: str | None = None
) -> tuple[Path, Path]:
    """Re-train the in-force probe under the G3 cadence, score it, and write the report.

    Args:
        paths: Resolved project paths.
        config_path: The cadence configuration.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The report and its JSON record.

    Raises:
        RuntimeError: If no probe design is in force under ADR-0024.
    """
    config = load_config(config_path, ProbeCadenceConfig)
    paired = load_config(paths.repo_root / config.paired_config, PairedControlConfig)
    design = _newest_record(paths, f"paired_control_v{paired.version}")["in_force"]
    if design is None:
        raise RuntimeError("no probe design is in force under ADR-0024")
    control = next(
        c
        for c in (
            load_config(paths.repo_root / p, ProbeControlConfig) for p in paired.control_configs
        )
        if c.design == design
    )
    gate = load_config(paths.repo_root / control.gate_config, GateCheckConfig)
    pooled, bootstrap = control.pooled_sources, gate.bootstrap
    digest = config_hash(config)
    out_dir = paths.checkpoints_dir / f"probe_cadence_v{config.version}_{digest}"
    log_dir = paths.data_reports_dir / f"probe_cadence_v{config.version}_steps"
    name = f"{gate.rung}_trained_seed{gate.seed}"
    started = time.perf_counter()

    inputs = open_probe_inputs(
        paths,
        gate.mixture_config,
        gate.ladder_config,
        gate.arm,
        gate.rung,
        gate.selection_windows,
        gate.held_out_source,
        device_name,
    )
    stage = inputs.ladder.risk
    total = stage.budget("probe").steps  # type: ignore[union-attr]
    measure_steps = config.steps(total)
    backbone = trained_scores_path(paths, gate).with_name(
        f"{gate.rung}_{gate.arm}_seed{gate.seed}.pt"
    )
    probe_file = out_dir / f"{name}_probe.pt"
    probe = probe_and_score(
        gate.seed,
        backbone,
        inputs,
        gate.held_out_source,
        log_dir / f"{name}_probe.steps.csv",
        f"cadence/{design}/{name}",
        save_to=probe_file,
        pooling=POOLING[design],
        head_layers=HEAD_LAYERS[design],
        unfrozen_blocks=UNFROZEN_BLOCKS[design],
        measure_steps=measure_steps,
        measure_initial=config.measure_initial,
    )
    subsample = ScoredWindows.load(
        save_scores(out_dir / f"{name}_test_scores.npz", probe, inputs.splits["test"])
    )
    evaluation = inputs.ladder.evaluation
    split = build_split(
        inputs.telemetry,
        "test",
        None,
        paired.stride,
        evaluation.seed,
        evaluation.batch_windows,
        stage.label,
        sources=pooled,
    )
    stride = save_split_scores(
        out_dir / f"{name}_stride{paired.stride}_scores.npz",
        score_saved_probe(probe_file, design, inputs, split),
        split,
        probe.prior_offset,
    )
    intervals = {
        f"pooled, stride {paired.stride}": stride.interval(pooled, bootstrap),
        "pooled, 24,000-window subsample": subsample.interval(pooled, bootstrap),
        f"{gate.held_out_source}, 12,000-window subsample": subsample.interval(
            [gate.held_out_source], bootstrap
        ),
    }
    seconds = time.perf_counter() - started
    logger.info("PROBE CADENCE: selected step %d, validation %.4f", *probe.probe_selected)

    stem = f"probe_cadence_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(
        render_report(
            config,
            config_path,
            design,
            probe.probe_history,
            probe.probe_selected,
            intervals,
            seconds,
            paths,
        ),
        encoding="utf-8",
        newline="\n",
    )
    record = paths.data_reports_dir / f"{stem}.json"
    payload = {
        "config": config.model_dump(mode="json"),
        "config_hash": digest,
        "design_in_force": design,
        "measure_steps": measure_steps,
        "history": probe.probe_history,
        "selected": list(probe.probe_selected),
        "prior_offset": probe.prior_offset,
        "natural_rate": probe.natural_rate,
        "held_out_calibration": probe.held_out_calibration,
        "intervals": {k: asdict(v) for k, v in intervals.items()},
        "probe_state": probe_file.relative_to(paths.repo_root).as_posix(),
        "seconds": seconds,
    }
    record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record)
    return report, record


def render_report(
    config: ProbeCadenceConfig,
    config_path: Path,
    design: str,
    history: list[tuple[int, float]],
    selected: tuple[int, float],
    intervals: dict[str, AuprcInterval],
    seconds: float,
    paths: ProjectPaths,
) -> str:
    """Render the cadence report.

    Args:
        config: The cadence configuration.
        config_path: Where it was read from.
        design: The probe design in force.
        history: Every validation measurement, as (step, AUPRC).
        selected: The selected step and its validation AUPRC.
        intervals: Per test set, the selected checkpoint's AUPRC interval.
        seconds: Wall clock.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    relative = config_path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    measurement_rows = [
        (
            str(step),
            f"{value:.4f}",
            "reference, not selectable"
            if step == 0
            else ("selected" if step == selected[0] else ""),
        )
        for step, value in history
    ]
    interval_rows = [
        (
            name,
            f"{iv.windows:,} / {iv.positives:,}",
            f"{iv.base_rate:.4f}",
            f"{iv.auprc:.4f}",
            f"[{iv.low:.4f}, {iv.high:.4f}]",
        )
        for name, iv in intervals.items()
    ]
    return "".join(
        [
            "# Probe cadence\n\n",
            kv_table(
                {
                    "configuration": f"{relative} (hash {config_hash(config)})",
                    "decision record": "docs/DECISIONS.md, ADR-0024 G3 addendum (registered in "
                    "577592f, before this code)",
                    "probe in force": f"{SECTION[design]} {design}",
                    "cadence": f"step 0 (reference), every {config.dense_every} to "
                    f"{config.dense_until}, then every {config.sparse_every}",
                    "selected": f"step {selected[0]}, validation AUPRC {selected[1]:.4f}",
                    "wall clock": f"{seconds / 60:.1f} min",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model probe-cadence",
                }
            ),
            section(
                "1. Validation measurements (selection split: kelmarsh + penmanshiel val)",
                table(["step", "validation AUPRC", ""], measurement_rows),
            ),
            section(
                "2. The selected checkpoint's test AUPRC, 95% block intervals",
                table(
                    ["test set", "windows / positive", "base rate", "AUPRC", "95% interval"],
                    interval_rows,
                ),
            ),
        ]
    )
