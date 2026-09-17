"""`tel_only` seeds 2 and 3, each paired against random init under the in-force protocol (F3).

G1's pass rests on one pretraining seed. This module pretrains seeds 2 and 3 exactly as the gate
run pretrained seed 1. It probes each under the in-force protocol: §a, G3's cadence, and scoring
on the stride-12 pooled training-site test split. It re-trains the three random-init probes under
the same protocol, so no comparison mixes two selection cadences. It then applies ADR-0024's
criterion to each trained seed, seed 1's step-200 probe included.

**Resume is per artefact, never per run.** A backbone, a probe, a record or a score file already
on disk is read, not recomputed. A probe whose record was never written (the first invocation
stopped while scoring one) is recovered from its saved state and the run log.

**Reported beside the criterion (ADR-0024 F3 additions).** Calibration on the 2021 validation
split, the selection split's size with an interval on selection AUPRC, and every probe's
final-step checkpoint beside its selected one. A final state that was never saved is recovered by
a seeded re-run of the probe stage. The re-run is accepted only if it reproduces the saved
selection and training log exactly.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from pydantic import Field

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.evaluation.calibration import at_natural_rate, balanced_shift, mean_predicted_rate
from faultline.evaluation.gate_check import BootstrapConfig, GateCheckConfig
from faultline.evaluation.ladder import SplitEval, balanced_training_sampler, build_split
from faultline.evaluation.paired_control import (
    SECTION,
    PairedControlConfig,
    decide_paired,
    load_saved_probe,
    paired_rows,
    save_split_scores,
    score_saved_probe,
)
from faultline.evaluation.prior_band import PriorBandConfig, balanced_logits, decide_band
from faultline.evaluation.probe_cadence import ProbeCadenceConfig
from faultline.evaluation.probe_control import (
    HEAD_LAYERS,
    POOLING,
    UNFROZEN_BLOCKS,
    ScoredWindows,
)
from faultline.evaluation.variance_probe import (
    ProbeInputs,
    open_probe_inputs,
    pretrain_tel,
    probe_and_score,
)
from faultline.logging_utils import get_logger
from faultline.model.checkpoints import read_checkpoint
from faultline.model.risk import prior_correction
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)


class SeedReplicationConfig(StrictModel):
    """Top level of ``configs/train/seed_replication_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        gate_config: The gate run: pretraining protocol, inputs, bootstrap.
        paired_config: The paired control: the stride.
        cadence_config: G3's cadence, and where seed 1's step-200 probe lives.
        prior_band_config: F2's balanced draw and band.
        bag_of_tokens_dir: The comparator's checkpoint directory, for its stride-12 scores.
        design: The probe design in force.
        new_seeds: The pretraining seeds this step adds.
        init_seeds: The random-init seeds.
        pooled_sources: The training sites pooled.
    """

    version: int = 0
    gate_config: str
    paired_config: str
    cadence_config: str
    prior_band_config: str
    bag_of_tokens_dir: str
    design: str
    new_seeds: list[int] = Field(min_length=1)
    init_seeds: list[int] = Field(min_length=1)
    pooled_sources: list[str] = Field(min_length=1)


def history_from_log(logs: list[Path], label: str) -> list[tuple[int, float]]:
    """A probe's validation measurements, read back from the lines the training loop logged.

    Args:
        logs: Run log files, searched in order.
        label: The run's label in the training log.

    Returns:
        Every (step, validation AUPRC) of the label's last run in the logs, step 0 included.
    """
    pattern = re.compile(re.escape(label) + r" step (\d+)/\d+ .*?validation ([0-9.]+|nan)")
    found: list[tuple[int, float]] = []
    for log in logs:
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            match = pattern.search(line)
            if match is None:
                continue
            step = int(match.group(1))
            if step == 0:
                found = []
            found.append((step, float(match.group(2))))
    return found


def same_step_logs(first: Path, second: Path) -> bool:
    """Whether two per-step training logs match row for row."""
    return first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def run_seed_replication(
    paths: ProjectPaths, config_path: Path, device_name: str | None = None
) -> tuple[Path, Path]:
    """Pretrain, probe, score and pair, resuming from whatever is already on disk.

    Args:
        paths: Resolved project paths.
        config_path: The F3 configuration.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The report and its JSON record.
    """
    config = load_config(config_path, SeedReplicationConfig)
    gate = load_config(paths.repo_root / config.gate_config, GateCheckConfig)
    paired = load_config(paths.repo_root / config.paired_config, PairedControlConfig)
    cadence = load_config(paths.repo_root / config.cadence_config, ProbeCadenceConfig)
    band = load_config(paths.repo_root / config.prior_band_config, PriorBandConfig)
    design, pooled, bootstrap = config.design, config.pooled_sources, gate.bootstrap
    out_dir = paths.checkpoints_dir / f"seed_replication_v{config.version}_{config_hash(config)}"
    log_dir = paths.data_reports_dir / f"seed_replication_v{config.version}_steps"
    cadence_dir = paths.checkpoints_dir / f"probe_cadence_v{cadence.version}_{config_hash(cadence)}"
    cadence_logs = paths.data_reports_dir / f"probe_cadence_v{cadence.version}_steps"
    run_logs = sorted((paths.checkpoints_dir / "logs").glob("seed_replication_v0_*.log"))
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    opened: list[ProbeInputs] = []
    splits: dict[str, SplitEval] = {}

    def inputs() -> ProbeInputs:
        if not opened:
            opened.append(
                open_probe_inputs(
                    paths,
                    gate.mixture_config,
                    gate.ladder_config,
                    gate.arm,
                    gate.rung,
                    gate.selection_windows,
                    gate.held_out_source,
                    device_name,
                )
            )
        return opened[0]

    def split(which: str) -> SplitEval:
        if which == "selection":
            selection: SplitEval = inputs().splits["selection"]
            return selection
        if which not in splits:
            evaluation = inputs().ladder.evaluation
            splits[which] = build_split(
                inputs().telemetry,
                which,
                None,
                paired.stride,
                evaluation.seed,
                evaluation.batch_windows,
                inputs().ladder.risk.label,
                sources=pooled,
            )
        return splits[which]

    def scores(path: Path, probe: Path, which: str, offset: float) -> ScoredWindows:
        if path.exists():
            return ScoredWindows.load(path)
        logger.info("scoring %s into %s", probe.name, path.name)
        return save_split_scores(
            path, score_saved_probe(probe, design, inputs(), split(which)), split(which), offset
        )

    def total_steps() -> int:
        return int(inputs().ladder.risk.budget("probe").steps)  # type: ignore[union-attr]

    # -- pretraining -----------------------------------------------------------------------
    pretraining: dict[int, dict[str, Any]] = {}
    for seed in config.new_seeds:
        backbone = out_dir / f"{gate.rung}_{gate.arm}_seed{seed}.pt"
        record_file = out_dir / f"{gate.rung}_{gate.arm}_seed{seed}_lm.json"
        if not record_file.exists():
            logger.info("=== pretraining %s seed %d ===", gate.arm, seed)
            lm = pretrain_tel(seed, gate, inputs(), out_dir, log_dir)
            record_file.write_text(
                json.dumps(
                    {
                        "tokens": lm.lm_tokens,
                        "steps": lm.lm_steps,
                        "seconds": lm.lm_seconds,
                        "selected": list(lm.lm_selected),
                        "history": lm.lm_history,
                        "final_train_loss": lm.lm_final_train_loss,
                        "checkpoint": backbone.relative_to(paths.repo_root).as_posix(),
                    },
                    indent=1,
                )
                + "\n",
                encoding="utf-8",
            )
        pretraining[seed] = json.loads(record_file.read_text(encoding="utf-8"))

    # -- probes under the in-force protocol --------------------------------------------------
    def train_probe(
        seed: int,
        checkpoint: Path | None,
        save_to: Path | None,
        final_to: Path,
        step_log: Path,
        label: str,
    ) -> tuple[dict[str, Any], Any]:
        probe = probe_and_score(
            seed,
            checkpoint,
            inputs(),
            gate.held_out_source,
            step_log,
            label,
            save_to=save_to,
            pooling=POOLING[design],
            head_layers=HEAD_LAYERS[design],
            unfrozen_blocks=UNFROZEN_BLOCKS[design],
            measure_steps=cadence.steps(total_steps()),
            measure_initial=cadence.measure_initial,
            save_final_to=final_to,
        )
        record = {
            "seed": seed,
            "selected": list(probe.probe_selected),
            "history": probe.probe_history,
            "prior_offset": probe.prior_offset,
            "natural_rate": probe.natural_rate,
            "seconds": probe.probe_seconds,
        }
        return record, probe

    def probe_entry(
        name: str,
        seed: int,
        checkpoint: Path | None,
        selected_file: Path,
        record_file: Path,
        saved_step_log: Path,
        label: str,
    ) -> dict[str, Any]:
        final_file = out_dir / f"{name}_final_probe.pt"
        if not selected_file.exists():
            logger.info("=== probing %s under the G3 cadence ===", name)
            fresh, result = train_probe(
                seed, checkpoint, selected_file, final_file, saved_step_log, label
            )
            record_file.write_text(json.dumps(fresh, indent=1) + "\n", encoding="utf-8")
            save_split_scores(
                out_dir / f"{name}_test_scores.npz",
                (result.logits, result.labels),
                inputs().splits["test"],
                result.prior_offset,
            )
        if not record_file.exists():
            payload = read_checkpoint(selected_file)
            logger.info("recovering %s's record from its saved probe and the run log", name)
            record_file.write_text(
                json.dumps(
                    {
                        "seed": seed,
                        "selected": list(payload["selected"]),
                        "history": history_from_log(run_logs, label),
                        "history_source": "recovered from the run log",
                        "prior_offset": prior_correction(
                            payload["train_rate"], payload["natural_rate"]
                        ),
                        "natural_rate": payload["natural_rate"],
                        "seconds": None,
                    },
                    indent=1,
                )
                + "\n",
                encoding="utf-8",
            )
        record: dict[str, Any] = json.loads(record_file.read_text(encoding="utf-8"))
        mismatch_file = out_dir / f"{name}_final_mismatch.txt"
        final: dict[str, Any]
        if record["selected"][0] == total_steps():
            final = {"file": selected_file, "note": "selected the last step"}
        elif final_file.exists():
            final = {"file": final_file, "note": "saved final state"}
        elif mismatch_file.exists():
            final = {"file": None, "note": mismatch_file.read_text(encoding="utf-8").strip()}
        else:
            logger.info("=== re-running %s's probe stage for its final state ===", name)
            rerun_log = log_dir / f"{name}_rerun_probe.steps.csv"
            rerun, _ = train_probe(seed, checkpoint, None, final_file, rerun_log, f"{label}/rerun")
            logs_match = same_step_logs(rerun_log, saved_step_log)
            if rerun["selected"] == record["selected"] and logs_match:
                final = {"file": final_file, "note": "recovered by a seeded re-run that reproduced"}
            else:
                final_file.unlink(missing_ok=True)
                note = (
                    f"re-run did not reproduce: selected {rerun['selected']} against "
                    f"{record['selected']}, step logs equal {logs_match}"
                )
                mismatch_file.write_text(note + "\n", encoding="utf-8")
                final = {"file": None, "note": note}
        record["final"] = final
        record["probe"] = selected_file
        record["stride"] = scores(
            out_dir / f"{name}_stride{paired.stride}_scores.npz",
            selected_file,
            "test",
            record["prior_offset"],
        )
        if final["file"] is None:
            record["final_stride"] = None
        elif final["file"] == selected_file:
            record["final_stride"] = record["stride"]
        else:
            record["final_stride"] = scores(
                out_dir / f"{name}_final_stride{paired.stride}_scores.npz",
                final["file"],
                "test",
                record["prior_offset"],
            )
        return record

    name1 = f"{gate.rung}_trained_seed{gate.seed}"
    seed1_record = out_dir / f"{name1}_probe.json"
    if not seed1_record.exists():
        found = sorted(paths.data_reports_dir.glob(f"probe_cadence_v{cadence.version}_[0-9]*.json"))
        g3 = json.loads(found[-1].read_text(encoding="utf-8"))
        seed1_record.write_text(
            json.dumps(
                {
                    "seed": gate.seed,
                    "selected": g3["selected"],
                    "history": g3["history"],
                    "prior_offset": g3["prior_offset"],
                    "natural_rate": g3["natural_rate"],
                    "seconds": None,
                    "source": found[-1].name,
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
    trained: dict[int, dict[str, Any]] = {
        gate.seed: probe_entry(
            name1,
            gate.seed,
            trained_backbone(paths, gate),
            cadence_dir / f"{name1}_probe.pt",
            seed1_record,
            cadence_logs / f"{name1}_probe.steps.csv",
            f"cadence/{design}/{name1}",
        )
    }
    trained[gate.seed]["subsample"] = ScoredWindows.load(cadence_dir / f"{name1}_test_scores.npz")
    for seed in config.new_seeds:
        name = f"{gate.rung}_trained_seed{seed}"
        trained[seed] = probe_entry(
            name,
            seed,
            out_dir / f"{gate.rung}_{gate.arm}_seed{seed}.pt",
            out_dir / f"{name}_probe.pt",
            out_dir / f"{name}_probe.json",
            log_dir / f"{name}_probe.steps.csv",
            f"f3/{name}",
        )
        trained[seed]["subsample"] = ScoredWindows.load(out_dir / f"{name}_test_scores.npz")
    random: dict[int, dict[str, Any]] = {}
    for seed in config.init_seeds:
        name = f"{gate.rung}_random_seed{seed}"
        random[seed] = probe_entry(
            name,
            seed,
            None,
            out_dir / f"{name}_probe.pt",
            out_dir / f"{name}_probe.json",
            log_dir / f"{name}_probe.steps.csv",
            f"f3/{name}",
        )

    # -- F2 per new trained seed -----------------------------------------------------------
    band_file = out_dir / "prior_band.json"
    if not band_file.exists():
        opened_inputs = inputs()
        stage = opened_inputs.ladder.risk
        batch = stage.budget("probe").batch_windows  # type: ignore[union-attr]
        sampler = balanced_training_sampler(
            opened_inputs.telemetry,
            opened_inputs.ladder,
            stage,  # type: ignore[arg-type]
            batch,
        )
        autocast = torch.autocast(
            device_type=opened_inputs.device.type,
            dtype=torch.bfloat16,
            enabled=opened_inputs.ladder.optimiser.precision == "bf16"
            and opened_inputs.device.type == "cuda",
        )
        measured: dict[str, Any] = {}
        for seed in config.new_seeds:
            logits, _ = balanced_logits(
                load_saved_probe(trained[seed]["probe"], design, opened_inputs),
                sampler,
                band.sampler_seed,
                band.batches,
                opened_inputs.device,
                autocast,
            )
            mean_rate = float(np.mean(1.0 / (1.0 + np.exp(-logits.astype(np.float64)))))
            band_verdict = decide_band(
                mean_rate,
                balanced_shift(logits, sampler.positives_per_batch / batch),
                band.band_low,
                band.band_high,
            )
            measured[str(seed)] = {"balanced_mean_rate": mean_rate, **asdict(band_verdict)}
        band_file.write_text(json.dumps(measured, indent=1) + "\n", encoding="utf-8")
    bands: dict[str, Any] = json.loads(band_file.read_text(encoding="utf-8"))
    # Seed 1's step-200 head was measured by F2 itself; its deciding row is read, not re-measured.
    band_record = sorted(paths.data_reports_dir.glob(f"prior_band_v{band.version}_[0-9]*.json"))
    f2 = next(
        r for r in json.loads(band_record[-1].read_text(encoding="utf-8"))["rows"] if r["decides"]
    )
    bands.setdefault(
        str(gate.seed), {"balanced_mean_rate": f2["balanced_mean_rate"], **f2["verdict"]}
    )

    # -- additions 1 and 2: the validation split and the selection split ---------------------
    for seed, entry in trained.items():
        name = f"{gate.rung}_trained_seed{seed}"
        entry["val"] = scores(
            out_dir / f"{name}_val_stride{paired.stride}_scores.npz",
            entry["probe"],
            "val",
            entry["prior_offset"],
        )
        entry["selection"] = scores(
            out_dir / f"{name}_selection_scores.npz",
            entry["probe"],
            "selection",
            entry["prior_offset"],
        )

    # -- the criterion and the reported rows ---------------------------------------------------
    bag = ScoredWindows.load(
        paths.repo_root
        / config.bag_of_tokens_dir
        / f"bag_of_tokens_stride{paired.stride}_scores.npz"
    )
    random_scores = [random[k]["stride"] for k in config.init_seeds]
    rows: list[dict[str, Any]] = []
    for seed in sorted(trained):
        entry = trained[seed]
        logger.info("bootstrapping trained seed %d", seed)
        deltas = paired_rows(entry["stride"], random_scores, pooled, bootstrap)
        verdict = decide_paired(deltas, bootstrap.max_discarded_share)
        logger.info(
            "F3 seed %d: %s -- %s", seed, "PASS" if verdict.sensitive else "FAIL", verdict.reason
        )
        shift = float(bands[str(seed)]["shift"])
        natural = float(entry["natural_rate"])
        rows.append(
            {
                "seed": seed,
                "pretraining": pretraining.get(seed),
                "selected": entry["selected"],
                "natural_rate": natural,
                "pooled": asdict(entry["stride"].interval(pooled, bootstrap)),
                "held_out": asdict(entry["subsample"].interval([gate.held_out_source], bootstrap)),
                "paired": [asdict(d) for d in deltas],
                "verdict": asdict(verdict),
                "versus_bag_of_tokens": asdict(
                    paired_rows(entry["stride"], [bag], pooled, bootstrap)[0]
                ),
                "prior_band": bands[str(seed)],
                "calibration": {
                    "test": _corrected(entry["stride"], pooled, natural, shift),
                    "val": _corrected(entry["val"], pooled, natural, shift),
                },
                "selection": asdict(entry["selection"].interval(pooled, bootstrap)),
                "final": _final(entry, pooled, bootstrap, total_steps),
            }
        )
    random_rows = [
        {
            "seed": k,
            "selected": random[k]["selected"],
            "pooled": asdict(random[k]["stride"].interval(pooled, bootstrap)),
            "final": _final(random[k], pooled, bootstrap, total_steps),
        }
        for k in config.init_seeds
    ]
    seconds = time.perf_counter() - started
    stem = f"seed_replication_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(
        render_report(config, config_path, gate.held_out_source, rows, random_rows, seconds, paths),
        encoding="utf-8",
        newline="\n",
    )
    record = paths.data_reports_dir / f"{stem}.json"
    payload = {
        "config": config.model_dump(mode="json"),
        "config_hash": config_hash(config),
        "seconds": seconds,
        "trained": rows,
        "random": random_rows,
    }
    record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record)
    return report, record


def trained_backbone(paths: ProjectPaths, gate: GateCheckConfig) -> Path:
    """The gate run's saved seed-1 backbone."""
    return (
        paths.checkpoints_dir
        / f"gate_check_v{gate.version}_{config_hash(gate)}"
        / f"{gate.rung}_{gate.arm}_seed{gate.seed}.pt"
    )


def _corrected(
    windows: ScoredWindows, pooled: list[str], natural_rate: float, shift: float
) -> dict[str, float]:
    mask = windows.chosen(pooled)
    scores = at_natural_rate(windows.logits[mask], 0.5, natural_rate, balanced_shift=shift)
    return {
        "windows": float(mask.sum()),
        "base_rate": float(windows.labels[mask].mean()),
        "corrected_mean_rate": mean_predicted_rate(scores),
    }


def _final(
    entry: dict[str, Any],
    pooled: list[str],
    bootstrap: BootstrapConfig,
    total_steps: Callable[[], int],
) -> dict[str, Any]:
    last = total_steps()
    history = {int(step): value for step, value in entry["history"]}
    final_stride = entry["final_stride"]
    return {
        "step": last,
        "validation_auprc": history.get(last),
        "note": entry["final"]["note"],
        "pooled": None
        if final_stride is None
        else asdict(final_stride.interval(pooled, bootstrap)),
    }


def _iv(d: dict[str, Any] | None) -> str:
    if d is None:
        return "unavailable"
    return f"{d['auprc']:.4f} [{d['low']:.4f}, {d['high']:.4f}]"


def _dv(d: dict[str, Any]) -> str:
    return f"{d['delta']:+.4f} [{d['low']:+.4f}, {d['high']:+.4f}]"


def render_report(
    config: SeedReplicationConfig,
    config_path: Path,
    held_out_source: str,
    rows: list[dict[str, Any]],
    random_rows: list[dict[str, Any]],
    seconds: float,
    paths: ProjectPaths,
) -> str:
    """Render the F3 report.

    Args:
        config: The F3 configuration.
        config_path: Where it was read from.
        held_out_source: The held-out site.
        rows: Per trained seed, its intervals, paired comparisons, verdict and additions.
        random_rows: Per random-init seed, its selection, interval and final step.
        seconds: Wall clock of this invocation.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    relative = config_path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    verdict_rows = [
        (
            str(r["seed"]),
            *(_dv(d) for d in r["paired"]),
            "PASS" if r["verdict"]["sensitive"] else "FAIL",
        )
        for r in rows
    ]
    seed_rows = [
        (
            str(r["seed"]),
            "(gate run)"
            if r["pretraining"] is None
            else f"{r['pretraining']['selected'][1]:.4f} at step {r['pretraining']['selected'][0]}",
            f"{r['selected'][1]:.4f} at step {r['selected'][0]}",
            _iv(r["pooled"]),
            _iv(r["held_out"]),
            _dv(r["versus_bag_of_tokens"]),
            f"{r['prior_band']['balanced_mean_rate']:.4f} "
            + ("(inside)" if r["prior_band"]["inside"] else "(outside)"),
        )
        for r in rows
    ]
    calibration_rows = [
        (
            str(r["seed"]),
            f"{r['natural_rate']:.4f}",
            f"{int(r['calibration']['val']['windows']):,}",
            f"{r['calibration']['val']['base_rate']:.4f}",
            f"{r['calibration']['val']['corrected_mean_rate']:.4f}",
            f"{r['calibration']['test']['base_rate']:.4f}",
            f"{r['calibration']['test']['corrected_mean_rate']:.4f}",
        )
        for r in rows
    ]
    first = rows[0]["selection"]
    selection_rows = [
        (
            str(r["seed"]),
            str(r["selected"][0]),
            f"{r['selection']['auprc']:.4f}",
            f"[{r['selection']['low']:.4f}, {r['selection']['high']:.4f}]",
        )
        for r in rows
    ]
    final_rows = [
        (
            f"{kind} seed {r['seed']}",
            f"step {r['selected'][0]} ({r['selected'][1]:.4f})",
            _iv(r["pooled"]),
            "n/a"
            if r["final"]["validation_auprc"] is None
            else f"step {r['final']['step']} ({r['final']['validation_auprc']:.4f})",
            _iv(r["final"]["pooled"]),
            r["final"]["note"],
        )
        for kind, group in (("trained", rows), ("random", random_rows))
        for r in group
    ]
    points = [r["pooled"]["auprc"] for r in rows]
    return "".join(
        [
            "# tel_only seed replication\n\n",
            kv_table(
                {
                    "configuration": f"{relative} (hash {config_hash(config)})",
                    "decision record": "docs/DECISIONS.md, ADR-0024 F3 addendum (0d6d6b4) and "
                    "its additions (b2ad4a7), registered before this code",
                    "probe": f"{SECTION[config.design]} {config.design}, G3 cadence, both sides",
                    "new seeds": ", ".join(str(s) for s in config.new_seeds),
                    "pooled stride-12 AUPRC across trained seeds": f"{min(points):.4f} to "
                    f"{max(points):.4f} (spread {max(points) - min(points):.4f})",
                    "wall clock (this invocation)": f"{seconds / 3600:.2f} h",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model seed-replication",
                }
            ),
            section(
                "1. The criterion per trained seed: paired Δ AUPRC against each random-init seed",
                table(
                    ["trained seed", *(f"Δ vs random {k}" for k in config.init_seeds), "verdict"],
                    verdict_rows,
                ),
            ),
            section(
                "2. Trained seeds (reported)",
                table(
                    [
                        "seed",
                        "pretraining val loss",
                        "probe selected (val AUPRC)",
                        "pooled stride-12 AUPRC",
                        f"{held_out_source} (12,000)",
                        "Δ vs bag of tokens",
                        "F2 balanced mean rate",
                    ],
                    seed_rows,
                ),
            ),
            section(
                "3. Corrected mean predicted rate: 2021 validation split against 2022-2024 test",
                table(
                    [
                        "seed",
                        "training natural rate",
                        "val windows (stride 12)",
                        "val base rate",
                        "val corrected mean",
                        "test base rate",
                        "test corrected mean",
                    ],
                    calibration_rows,
                ),
            ),
            section(
                "4. The selection split and an interval on selection AUPRC",
                f"{first['windows']:,} windows, {first['positives']:,} positive, "
                f"{first['positive_blocks']:,} of {first['blocks']:,} occupied 48-hour blocks "
                "holding a positive.\n\n"
                + table(
                    ["seed", "selected step", "selection AUPRC", "95% block interval"],
                    selection_rows,
                ),
            ),
            section(
                "5. Selected against final-step checkpoints, pooled stride-12 test AUPRC",
                table(
                    [
                        "probe",
                        "selected (val AUPRC)",
                        "selected test AUPRC",
                        "final (val AUPRC)",
                        "final test AUPRC",
                        "note",
                    ],
                    final_rows,
                ),
            ),
        ]
    )
