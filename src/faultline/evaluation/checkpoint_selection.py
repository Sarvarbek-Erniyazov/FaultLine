"""ADR-0022's addendum: does fixed-final-step selection cost anything on the arm runs?

F3 selected each probe's checkpoint on a 6,000-window validation split whose interval on
selection AUPRC is about as wide as the quantity it ranks, and inside which the untrained
step-0 head sits for all three seeds. Selection there is selection on noise. The addendum asks
the only question that can retire it: does taking the last step instead **lose** any test AUPRC,
and does the pretraining effect itself survive the switch?

**Nothing is trained and nothing is scored.** Every input is a ``.npz`` of saved logits written
by F3 under ``checkpoints/seed_replication_v0_424c4f33/``. This module reads them, runs eleven
paired block bootstraps on the CPU, and applies the registered rule:

    Fixed-final-step selection is adopted unless, on any trained seed, the paired 95% interval of
    Δ = AUPRC(final) − AUPRC(selected) lies entirely below zero; and only if ADR-0024's F3
    criterion, recomputed with final-step checkpoints on BOTH sides, passes nine of nine.

A trained seed that selected the last step has one checkpoint, so its Δ is identically zero. It
is stated, never bootstrapped: a degenerate resample would report an interval where there is no
quantity to estimate.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faultline.config import config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.evaluation.bootstrap import DeltaInterval
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.paired_control import (
    PairedControlConfig,
    PairedVerdict,
    decide_paired,
    paired_rows_cached,
)
from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.seed_replication import SeedReplicationConfig
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

#: The rule names the axis-gate configuration's ``checkpoints.gating`` takes.
FIXED_FINAL = "final_step"
SELECTED = "selected"


# =====================================================================================
# the checkpoints a seed has
# =====================================================================================


@dataclass(frozen=True)
class SeedCheckpoints:
    """One probe's selected and final-step scores on the deciding split.

    Attributes:
        name: The probe's file stem under the F3 checkpoints directory.
        selected_step: The step its validation measurement selected.
        last_step: The last step measured, which the final-step checkpoint is at.
        selected: Scores at the selected checkpoint.
        final: Scores at the final-step checkpoint; the same object when the two coincide.
    """

    name: str
    selected_step: int
    last_step: int
    selected: ScoredWindows
    final: ScoredWindows

    @property
    def identical(self) -> bool:
        """Whether the selected checkpoint **is** the final-step checkpoint."""
        return self.selected_step == self.last_step


def read_checkpoints(out_dir: Path, name: str, stride: int) -> SeedCheckpoints:
    """Read one probe's selected and final-step stride-``stride`` scores from disk.

    The final-step file exists if and only if the probe selected a step before the last one:
    F3 wrote no separate final state for a probe whose selection already was its last step.
    That agreement is checked rather than assumed, because a missing file would otherwise be
    read silently as a zero difference.

    Args:
        out_dir: The F3 checkpoints directory.
        name: The probe's file stem, such as ``S2_trained_seed1``.
        stride: The deciding split's stride.

    Returns:
        The probe's two reads.

    Raises:
        FileNotFoundError: If the probe's record or its selected scores are missing.
        ValueError: If the final-step file disagrees with the record's selected step.
    """
    record_file = out_dir / f"{name}_probe.json"
    if not record_file.is_file():
        raise FileNotFoundError(f"{record_file} is missing; F3's outputs are not on this machine")
    record: dict[str, Any] = json.loads(record_file.read_text(encoding="utf-8"))
    selected_step = int(record["selected"][0])
    last_step = max(int(step) for step, _ in record["history"])
    selected_file = out_dir / f"{name}_stride{stride}_scores.npz"
    if not selected_file.is_file():
        raise FileNotFoundError(f"{selected_file} is missing; F3's outputs are not on this machine")
    selected = ScoredWindows.load(selected_file)
    final_file = out_dir / f"{name}_final_stride{stride}_scores.npz"
    if selected_step == last_step:
        if final_file.is_file():
            raise ValueError(
                f"{name} selected the last step ({last_step}) yet {final_file.name} exists"
            )
        return SeedCheckpoints(name, selected_step, last_step, selected, selected)
    if not final_file.is_file():
        raise ValueError(
            f"{name} selected step {selected_step} of {last_step}, so {final_file.name} must "
            "exist; F3 reports its final-step row as unavailable without it"
        )
    return SeedCheckpoints(name, selected_step, last_step, selected, ScoredWindows.load(final_file))


# =====================================================================================
# the criterion
# =====================================================================================


@dataclass(frozen=True)
class SelectionVerdict:
    """The addendum's rule, applied.

    Attributes:
        rule: The selection rule adopted for the arm runs, ``final_step`` or ``selected``.
        reason: One sentence saying why.
    """

    rule: str
    reason: str

    @property
    def fixed_final(self) -> bool:
        """Whether fixed-final-step selection is adopted."""
        return self.rule == FIXED_FINAL


def decide_selection(
    deltas: dict[int, DeltaInterval | None], nine: dict[int, PairedVerdict]
) -> SelectionVerdict:
    """Apply ADR-0022's addendum to the two measurements it registered.

    Args:
        deltas: Per trained seed, the paired interval on final minus selected, or ``None`` for a
            seed whose two checkpoints are the same and whose Δ is therefore identically zero.
        nine: Per trained seed, ADR-0024's verdict recomputed with final-step checkpoints on
            both sides.

    Returns:
        The rule in force for the arm runs, and why.

    Raises:
        ValueError: If either measurement is empty.
    """
    if not deltas or not nine:
        raise ValueError("the rule reads a Δ interval and a nine-cell verdict for every seed")
    worse = sorted(seed for seed, d in deltas.items() if d is not None and d.high < 0.0)
    if worse:
        return SelectionVerdict(
            SELECTED,
            f"the final step is significantly worse on seed(s) {', '.join(map(str, worse))}: "
            "the paired interval lies entirely below zero, so the ADR-0024 rule stays",
        )
    failing = sorted(seed for seed, v in nine.items() if not v.sensitive)
    if failing:
        return SelectionVerdict(
            SELECTED,
            f"recomputed with final-step checkpoints on both sides, ADR-0024's criterion fails "
            f"on seed(s) {', '.join(map(str, failing))}, so the ADR-0024 rule stays",
        )
    lowest = min(v.lowest for v in nine.values())
    return SelectionVerdict(
        FIXED_FINAL,
        "no trained seed's paired interval lies below zero and the final-vs-final recomputation "
        f"passes nine of nine (lowest lower bound {lowest:+.4f}): fixed-final-step selection is "
        "adopted for the arm runs",
    )


# =====================================================================================
# the run
# =====================================================================================


def run_checkpoint_selection(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """Measure ADR-0022's addendum on F3's saved scores and write its report.

    Args:
        paths: Resolved project paths.
        config_path: The F3 configuration, which names the checkpoints and the interval.

    Returns:
        The report and its JSON record.
    """
    config = load_config(config_path, SeedReplicationConfig)
    gate = load_config(paths.repo_root / config.gate_config, GateCheckConfig)
    paired = load_config(paths.repo_root / config.paired_config, PairedControlConfig)
    bootstrap, pooled = gate.bootstrap, config.pooled_sources
    out_dir = paths.checkpoints_dir / f"seed_replication_v{config.version}_{config_hash(config)}"
    started = time.perf_counter()
    trained_seeds = [gate.seed, *config.new_seeds]
    # Resume-safety is only honest if the report says what this invocation actually paid for.
    resumed: list[str] = []
    computed: list[str] = []

    def cached(
        cache: Path, first: ScoredWindows, others: list[ScoredWindows]
    ) -> list[DeltaInterval]:
        (resumed if cache.exists() else computed).append(cache.stem)
        return paired_rows_cached(cache, first, others, pooled, bootstrap)

    trained = {
        seed: read_checkpoints(out_dir, f"{gate.rung}_trained_seed{seed}", paired.stride)
        for seed in trained_seeds
    }
    random = {
        seed: read_checkpoints(out_dir, f"{gate.rung}_random_seed{seed}", paired.stride)
        for seed in config.init_seeds
    }

    # -- Δ = final − selected, per trained seed --------------------------------------------
    deltas: dict[int, DeltaInterval | None] = {}
    for seed in trained_seeds:
        entry = trained[seed]
        if entry.identical:
            logger.info(
                "trained seed %d selected step %d, its last: Δ is identically 0, not bootstrapped",
                seed,
                entry.selected_step,
            )
            deltas[seed] = None
            continue
        logger.info("bootstrapping Δ(final − selected) for trained seed %d", seed)
        deltas[seed] = cached(
            out_dir / f"{entry.name}_final_minus_selected_delta.json",
            entry.final,
            [entry.selected],
        )[0]

    # -- ADR-0024's criterion, final-step checkpoints on both sides -------------------------
    cells: dict[int, list[DeltaInterval]] = {}
    nine: dict[int, PairedVerdict] = {}
    for seed in trained_seeds:
        entry = trained[seed]
        logger.info("bootstrapping the final-vs-final row for trained seed %d", seed)
        cells[seed] = cached(
            out_dir / f"{entry.name}_final_vs_random_final_delta.json",
            entry.final,
            [random[k].final for k in config.init_seeds],
        )
        nine[seed] = decide_paired(cells[seed], bootstrap.max_discarded_share)
        logger.info(
            "final-vs-final seed %d: %s -- %s",
            seed,
            "PASS" if nine[seed].sensitive else "FAIL",
            nine[seed].reason,
        )

    verdict = decide_selection(deltas, nine)
    logger.info("ADR-0022 addendum: %s -- %s", verdict.rule, verdict.reason)
    seconds = time.perf_counter() - started

    stem = f"checkpoint_selection_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(
        render_report(
            config,
            config_path,
            trained,
            random,
            deltas,
            cells,
            nine,
            verdict,
            seconds,
            (len(computed), len(resumed)),
            paths,
        ),
        encoding="utf-8",
        newline="\n",
    )
    record = paths.data_reports_dir / f"{stem}.json"
    record.write_text(
        json.dumps(
            {
                "config": config.model_dump(mode="json"),
                "config_hash": config_hash(config),
                "bootstrap": bootstrap.model_dump(),
                "seconds": seconds,
                "bootstraps_computed": computed,
                "bootstraps_resumed": resumed,
                "delta_final_minus_selected": {
                    str(seed): None if d is None else asdict(d) for seed, d in deltas.items()
                },
                "identical_checkpoint": {
                    str(seed): trained[seed].identical for seed in trained_seeds
                },
                "final_vs_final": {
                    str(seed): {
                        "cells": [asdict(d) for d in cells[seed]],
                        "verdict": asdict(nine[seed]),
                    }
                    for seed in trained_seeds
                },
                "verdict": asdict(verdict),
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    logger.info("wrote %s and %s", report, record)
    return report, record


def _delta(interval: DeltaInterval | None, identical: bool) -> str:
    if interval is None:
        return "0 exactly (one checkpoint)" if identical else "unavailable"
    return f"{interval.delta:+.4f} [{interval.low:+.4f}, {interval.high:+.4f}]"


def render_report(
    config: SeedReplicationConfig,
    config_path: Path,
    trained: dict[int, SeedCheckpoints],
    random: dict[int, SeedCheckpoints],
    deltas: dict[int, DeltaInterval | None],
    cells: dict[int, list[DeltaInterval]],
    nine: dict[int, PairedVerdict],
    verdict: SelectionVerdict,
    seconds: float,
    bootstraps: tuple[int, int],
    paths: ProjectPaths,
) -> str:
    """Render the addendum's report.

    Args:
        config: The F3 configuration read.
        config_path: Where it was read from.
        trained: Per trained seed, its two checkpoints.
        random: Per random-init seed, its two checkpoints.
        deltas: Per trained seed, the paired interval on final minus selected, or ``None``.
        cells: Per trained seed, its three final-vs-final intervals.
        nine: Per trained seed, ADR-0024's recomputed verdict.
        verdict: The rule adopted.
        seconds: Wall clock of this invocation.
        bootstraps: How many paired bootstraps this invocation computed, and how many it read
            back from a cache a previous invocation had written.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    relative = config_path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    seeds = sorted(trained)
    delta_rows = [
        (
            str(seed),
            f"step {trained[seed].selected_step}",
            f"step {trained[seed].last_step}",
            _delta(interval, trained[seed].identical),
            "YES" if interval is not None and interval.high < 0.0 else "no",
        )
        for seed, interval in ((seed, deltas[seed]) for seed in seeds)
    ]
    cell_rows = [
        (
            str(seed),
            *(f"{d.delta:+.4f} [{d.low:+.4f}, {d.high:+.4f}]" for d in cells[seed]),
            "PASS" if nine[seed].sensitive else "FAIL",
        )
        for seed in seeds
    ]
    return "".join(
        [
            "# ADR-0022 addendum: arm-run checkpoint selection\n\n",
            kv_table(
                {
                    "configuration": f"{relative} (hash {config_hash(config)})",
                    "decision record": "docs/DECISIONS.md, ADR-0022 addendum of 2026-09-18, "
                    "registered before this code and before any bootstrap of it ran",
                    "inputs": "F3's saved stride-12 scores; nothing trained, nothing re-scored",
                    "device": "CPU",
                    "paired bootstraps": f"{bootstraps[0]} computed in this invocation, "
                    f"{bootstraps[1]} resumed from their cached JSON",
                    "wall clock (this invocation)": f"{seconds / 60:.1f} min",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model checkpoint-selection",
                }
            ),
            section(
                "1. Δ = AUPRC(final) − AUPRC(selected), paired, pooled stride-12 split",
                table(
                    [
                        "trained seed",
                        "selected",
                        "final",
                        "Δ final − selected, 95% paired interval",
                        "entirely below zero",
                    ],
                    delta_rows,
                ),
            ),
            section(
                "2. ADR-0024's criterion with final-step checkpoints on both sides",
                table(
                    [
                        "trained seed (final)",
                        *(f"Δ vs random {k} (final)" for k in config.init_seeds),
                        "verdict",
                    ],
                    cell_rows,
                )
                + "\nRandom-init final steps: "
                + ", ".join(
                    f"seed {k} step {random[k].last_step}"
                    + ("" if random[k].identical else f" (selected {random[k].selected_step})")
                    for k in config.init_seeds
                )
                + ".\n",
            ),
            section(
                "3. Verdict",
                f"**The rule in force for the arm runs and for F5: `{verdict.rule}`.**\n\n"
                f"{verdict.reason[:1].upper()}{verdict.reason[1:]}.\n",
            ),
        ]
    )
