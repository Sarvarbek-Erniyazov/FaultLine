"""The balanced mean rate of the in-force probe, and the π_train its correction uses (ADR-0019 F2).

The prior correction assumes the head learned the positive fraction of its balanced batches,
0.5. An early checkpoint may not have. On the probe's own balanced training distribution, this
module measures the head's mean uncorrected prediction. Inside the registered band, the declared
correction stands. Outside it, a shift re-centres the head on 0.5 before the correction. It then
reports the corrected mean rate and ECE under both offsets. AUPRC is untouched either way.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from pydantic import Field, model_validator

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.evaluation.calibration import (
    at_natural_rate,
    balanced_shift,
    expected_calibration_error,
    mean_predicted_rate,
)
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.ladder import balanced_training_sampler
from faultline.evaluation.paired_control import SECTION, load_saved_probe
from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.variance_probe import open_probe_inputs
from faultline.logging_utils import get_logger
from faultline.model.checkpoints import read_checkpoint
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.windows import BalancedWindowSampler

logger = get_logger(__name__)


class ProbeUnderCheck(StrictModel):
    """One saved probe and the scores it already wrote.

    Attributes:
        name: A label for the report.
        probe: The saved probe state.
        stride_scores: Its pooled training-site test scores at the deciding stride.
        subsample_scores: Its scores on the seeded subsample (Hill of Towie included).
        decides: Whether the rule is applied to it (only the in-force checkpoint).
    """

    name: str
    probe: str
    stride_scores: str
    subsample_scores: str
    decides: bool


class PriorBandConfig(StrictModel):
    """Top level of ``configs/train/prior_band_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        gate_config: The gate run whose inputs the probes read.
        design: The probe design in force.
        probes: The probes measured; exactly one decides.
        sampler_seed: Seed of the balanced draw.
        batches: Balanced batches drawn.
        band_low: The band's lower edge on the balanced mean rate.
        band_high: Its upper edge.
        bootstrap_resamples: Window resamples for the interval on the balanced mean rate.
        bootstrap_seed: Their seed.
        held_out_source: The held-out site, reported.
        pooled_sources: The training sites, reported.
    """

    version: int = 0
    gate_config: str
    design: str
    probes: list[ProbeUnderCheck] = Field(min_length=1)
    sampler_seed: int
    batches: int = Field(gt=0)
    band_low: float = Field(gt=0.0, lt=1.0)
    band_high: float = Field(gt=0.0, lt=1.0)
    bootstrap_resamples: int = Field(gt=0)
    bootstrap_seed: int
    held_out_source: str
    pooled_sources: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_decides(self) -> PriorBandConfig:
        """Refuse a band that is empty or a probe list without exactly one deciding probe.

        Raises:
            ValueError: If the band is empty or not exactly one probe decides.
        """
        if not self.band_low < self.band_high:
            raise ValueError(f"empty band [{self.band_low}, {self.band_high}]")
        if sum(p.decides for p in self.probes) != 1:
            raise ValueError("exactly one probe decides")
        return self


@dataclass(frozen=True)
class BandVerdict:
    """The F2 rule, applied.

    Attributes:
        inside: Whether the balanced mean rate lies in the band.
        shift: The re-centring shift in force: zero inside the band, measured outside it.
        reason: One sentence saying why.
    """

    inside: bool
    shift: float
    reason: str


def decide_band(mean_rate: float, measured_shift: float, low: float, high: float) -> BandVerdict:
    """Apply the F2 rule: inside the closed band the declared π_train stands.

    Args:
        mean_rate: The head's balanced mean rate.
        measured_shift: The shift that re-centres it on 0.5.
        low: The band's lower edge.
        high: Its upper edge.

    Returns:
        The verdict.
    """
    if low <= mean_rate <= high:
        return BandVerdict(
            True, 0.0, f"balanced mean rate {mean_rate:.4f} is inside [{low}, {high}]"
        )
    return BandVerdict(
        False,
        measured_shift,
        f"balanced mean rate {mean_rate:.4f} is outside [{low}, {high}]; the measured shift "
        f"{measured_shift:+.4f} nats is applied",
    )


def balanced_logits(
    model: torch.nn.Module,
    sampler: BalancedWindowSampler,
    seed: int,
    batches: int,
    device: torch.device,
    autocast: torch.autocast,
) -> tuple[np.ndarray, np.ndarray]:
    """A head's uncorrected logits and the labels over a seeded balanced draw.

    Args:
        model: The probe, in evaluation mode.
        sampler: The balanced training sampler.
        seed: Seed of the draw; the same seed gives every head the same windows.
        batches: Batches drawn.
        device: Where the model lives.
        autocast: The precision context of a forward pass.

    Returns:
        Per window, its logit and its label.
    """
    logits, labels = [], []
    draws = sampler.forever(seed)
    with torch.inference_mode():
        for _ in range(batches):
            tokens, batch_labels, _ = next(draws)
            with autocast:
                scored = model(tokens.to(device))
            logits.append(scored.float().cpu().numpy())
            labels.append(batch_labels.numpy())
    return np.concatenate(logits), np.concatenate(labels)


def _calibration(
    logits: np.ndarray, labels: np.ndarray, train_rate: float, natural_rate: float, shift: float
) -> dict[str, float]:
    scores = at_natural_rate(logits, train_rate, natural_rate, balanced_shift=shift)
    return {
        "mean_predicted_rate": mean_predicted_rate(scores),
        "expected_calibration_error": expected_calibration_error(scores, labels),
        "base_rate": float(np.mean(labels)),
        "windows": float(labels.size),
    }


def run_prior_band(
    paths: ProjectPaths, config_path: Path, device_name: str | None = None
) -> tuple[Path, Path]:
    """Measure each probe's balanced mean rate, apply the rule, and report calibration.

    Args:
        paths: Resolved project paths.
        config_path: The F2 configuration.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The report and its JSON record.
    """
    config = load_config(config_path, PriorBandConfig)
    gate = load_config(paths.repo_root / config.gate_config, GateCheckConfig)
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
    batch = stage.budget("probe").batch_windows  # type: ignore[union-attr]
    sampler = balanced_training_sampler(
        inputs.telemetry,
        inputs.ladder,
        stage,  # type: ignore[arg-type]
        batch,
    )
    train_rate = sampler.positives_per_batch / batch
    autocast = torch.autocast(
        device_type=inputs.device.type,
        dtype=torch.bfloat16,
        enabled=inputs.ladder.optimiser.precision == "bf16" and inputs.device.type == "cuda",
    )
    rows: list[dict[str, Any]] = []
    for under in config.probes:
        probe_path = paths.repo_root / under.probe
        natural_rate = float(read_checkpoint(probe_path)["natural_rate"])
        logits, labels = balanced_logits(
            load_saved_probe(probe_path, config.design, inputs),
            sampler,
            config.sampler_seed,
            config.batches,
            inputs.device,
            autocast,
        )
        probabilities = 1.0 / (1.0 + np.exp(-logits.astype(np.float64)))
        generator = np.random.default_rng(config.bootstrap_seed)
        resampled = [
            float(
                probabilities[generator.integers(0, probabilities.size, probabilities.size)].mean()
            )
            for _ in range(config.bootstrap_resamples)
        ]
        low, high = np.quantile(resampled, [0.025, 0.975])
        mean_rate = float(probabilities.mean())
        shift = balanced_shift(logits, train_rate)
        verdict = decide_band(mean_rate, shift, config.band_low, config.band_high)
        logger.info("F2 %s: %s", under.name, verdict.reason)

        stride = ScoredWindows.load(paths.repo_root / under.stride_scores)
        subsample = ScoredWindows.load(paths.repo_root / under.subsample_scores)
        sets: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        pooled_mask = stride.chosen(config.pooled_sources)
        sets["pooled training-site test, stride 12"] = (
            stride.logits[pooled_mask],
            stride.labels[pooled_mask],
        )
        for source in config.pooled_sources:
            mask = stride.chosen([source])
            sets[f"{source} test, stride 12"] = (stride.logits[mask], stride.labels[mask])
        held = subsample.chosen([config.held_out_source])
        sets[f"{config.held_out_source} test, 12,000-window subsample"] = (
            subsample.logits[held],
            subsample.labels[held],
        )
        calibration = {
            name: {
                "declared": _calibration(z, y, train_rate, natural_rate, 0.0),
                "measured": _calibration(z, y, train_rate, natural_rate, shift),
            }
            for name, (z, y) in sets.items()
        }
        rows.append(
            {
                "name": under.name,
                "probe": under.probe,
                "decides": under.decides,
                "balanced_windows": int(labels.size),
                "balanced_positives": int(labels.sum()),
                "balanced_mean_rate": mean_rate,
                "interval": [float(low), float(high)],
                "mean_on_positives": float(probabilities[labels > 0].mean()),
                "mean_on_negatives": float(probabilities[labels == 0].mean()),
                "measured_shift": shift,
                "verdict": verdict.__dict__,
                "natural_rate": natural_rate,
                "train_rate": train_rate,
                "declared_offset": float(
                    at_natural_rate(np.zeros(1), train_rate, natural_rate).offset
                ),
                "calibration": calibration,
            }
        )
    seconds = time.perf_counter() - started
    stem = f"prior_band_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(
        render_report(config, config_path, rows, seconds, paths), encoding="utf-8", newline="\n"
    )
    record = paths.data_reports_dir / f"{stem}.json"
    payload = {
        "config": config.model_dump(mode="json"),
        "config_hash": config_hash(config),
        "seconds": seconds,
        "rows": rows,
    }
    record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record)
    return report, record


def render_report(
    config: PriorBandConfig,
    config_path: Path,
    rows: list[dict[str, Any]],
    seconds: float,
    paths: ProjectPaths,
) -> str:
    """Render the F2 report.

    Args:
        config: The F2 configuration.
        config_path: Where it was read from.
        rows: Per probe, its measurement, verdict and calibration.
        seconds: Wall clock.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    relative = config_path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    band_rows = [
        (
            row["name"] + (" (decides)" if row["decides"] else " (reported)"),
            f"{row['balanced_mean_rate']:.4f}",
            f"[{row['interval'][0]:.4f}, {row['interval'][1]:.4f}]",
            f"{row['mean_on_positives']:.4f} / {row['mean_on_negatives']:.4f}",
            f"{row['measured_shift']:+.4f}",
            "inside" if row["verdict"]["inside"] else "outside",
        )
        for row in rows
    ]
    calibration_rows = []
    for row in rows:
        for name, both in row["calibration"].items():
            declared, measured = both["declared"], both["measured"]
            calibration_rows.append(
                (
                    row["name"],
                    name,
                    f"{declared['base_rate']:.4f}",
                    f"{declared['mean_predicted_rate']:.4f}",
                    f"{declared['expected_calibration_error']:.4f}",
                    f"{measured['mean_predicted_rate']:.4f}",
                    f"{measured['expected_calibration_error']:.4f}",
                )
            )
    deciding = next(row for row in rows if row["decides"])
    return "".join(
        [
            "# Balanced mean rate and π_train\n\n",
            kv_table(
                {
                    "configuration": f"{relative} (hash {config_hash(config)})",
                    "decision record": "docs/DECISIONS.md, ADR-0019 F2 addendum (registered in "
                    "38fef95, before this code)",
                    "probe design": f"{SECTION[config.design]} {config.design}",
                    "balanced draw": f"training split, {config.batches:,} balanced batches, "
                    f"sampler seed {config.sampler_seed}",
                    "band": f"[{config.band_low}, {config.band_high}]",
                    "training natural rate": f"{deciding['natural_rate']:.4f}",
                    "declared offset": f"{deciding['declared_offset']:+.4f}",
                    "wall clock": f"{seconds / 60:.1f} min",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model prior-band",
                }
            ),
            section(
                "1. The rule",
                f"**{deciding['name']}: {deciding['verdict']['reason']}.**\n",
            ),
            section(
                "2. Balanced mean rate (uncorrected mean prediction on balanced training windows)",
                table(
                    [
                        "probe",
                        "mean rate",
                        "95% interval",
                        "on positives / negatives",
                        "shift to 0.5",
                        "band",
                    ],
                    band_rows,
                ),
            ),
            section(
                "3. Corrected calibration, declared and measured offsets (reported)",
                table(
                    [
                        "probe",
                        "windows",
                        "base rate",
                        "declared: mean rate",
                        "declared: ECE",
                        "measured: mean rate",
                        "measured: ECE",
                    ],
                    calibration_rows,
                ),
            ),
        ]
    )
