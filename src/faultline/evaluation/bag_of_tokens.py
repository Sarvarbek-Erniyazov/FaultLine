"""The bag-of-tokens comparator (ADR-0024 §6): a risk classifier that ignores token order.

A trained linear head on a random projection of the token embeddings already scores above base
rate (ADR-0023). So "does the sequence model beat base rate" is not the question the dissertation
needs answered. The question is whether it beats a classifier that sees only which quantile bins
occurred in the window, not when. This module is that classifier: logistic regression on each
window's token-count histogram, divided by the window's steps. It is trained by the probe
stage's own loop, with the same balanced sampler, budget, rate, schedule and selection split. It
is scored on the same test windows, with the same block bootstrap. It decides nothing. It is
reported beside the probe in force.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.evaluation.bootstrap import (
    AuprcInterval,
    DeltaInterval,
    bootstrap_auprc,
    paired_bootstrap_deltas,
    window_blocks,
)
from faultline.evaluation.gate_check import GateCheckConfig, save_scores
from faultline.evaluation.ladder import balanced_training_sampler, build_split
from faultline.evaluation.metrics import score_source
from faultline.evaluation.paired_control import (
    SECTION,
    PairedControlConfig,
    _restricted,
    save_split_scores,
)
from faultline.evaluation.probe_control import (
    ProbeControlConfig,
    ScoredWindows,
    trained_scores_path,
)
from faultline.evaluation.variance_probe import ProbeResult, open_probe_inputs
from faultline.logging_utils import get_logger
from faultline.model.risk import prior_correction
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.seed import seed_everything
from faultline.training.config import PositiveAwareRiskStage
from faultline.training.loop import Measurement, risk_logits, train, write_step_log

logger = get_logger(__name__)


class BagOfTokensConfig(StrictModel):
    """Top level of ``configs/train/bag_of_tokens_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        paired_config: The paired control whose design in force, windows and stride it is set
            beside.
        seed: Seeds the sampler and the run, as the trained probe's seed does.
        device: Where it trains: the CPU, as registered.
    """

    version: int = 0
    paired_config: str
    seed: int
    device: str


class BagOfTokens(nn.Module):
    """Logistic regression on a window's token histogram, counts per step.

    Attributes:
        vocab_size: Token ids counted.
        steps: Steps in a window; the counts are divided by it, so each channel's bins sum to 1.
        linear: The one layer, ``vocab_size`` to 1, initialised to zero.
    """

    def __init__(self, vocab_size: int, steps: int) -> None:
        """Build the classifier.

        Args:
            vocab_size: Token ids counted.
            steps: Steps in a window.
        """
        super().__init__()
        self.vocab_size = vocab_size
        self.steps = steps
        self.linear = nn.Linear(vocab_size, 1)
        nn.init.zeros_(self.linear.weight)
        nn.init.zeros_(self.linear.bias)

    def features(self, tokens: Tensor) -> Tensor:
        """Per window, each token id's count divided by the window's steps.

        Args:
            tokens: Token identifiers of shape ``(batch, time)``.

        Returns:
            Frequencies of shape ``(batch, vocab_size)``.
        """
        counts = torch.zeros(
            tokens.shape[0], self.vocab_size, device=tokens.device, dtype=torch.float32
        )
        counts.scatter_add_(1, tokens.long(), torch.ones_like(tokens, dtype=torch.float32))
        return counts / self.steps

    def forward(self, tokens: Tensor) -> Tensor:
        """One risk logit per window, of shape ``(batch,)``."""
        return cast(Tensor, self.linear(self.features(tokens))).squeeze(-1)

    def loss(self, tokens: Tensor, labels: Tensor, positive_weight: float = 1.0) -> Tensor:
        """Binary cross entropy of the logits against the labels, as the probe's."""
        logits = self(tokens).float()
        weight = torch.as_tensor(positive_weight, device=logits.device, dtype=logits.dtype)
        return F.binary_cross_entropy_with_logits(logits, labels.float(), pos_weight=weight)


def _newest_record(paths: ProjectPaths, stem: str) -> dict[str, Any]:
    found = sorted(paths.data_reports_dir.glob(f"{stem}_[0-9]*.json"))
    if not found:
        raise FileNotFoundError(f"no {stem}_<date>.json record")
    record: dict[str, Any] = json.loads(found[-1].read_text(encoding="utf-8"))
    return record


def run_bag_of_tokens(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """Train the comparator, score it, and set it beside the probe in force.

    Args:
        paths: Resolved project paths.
        config_path: The comparator configuration.

    Returns:
        The report and its JSON record.

    Raises:
        RuntimeError: If no probe design is in force under ADR-0024.
    """
    config = load_config(config_path, BagOfTokensConfig)
    paired = load_config(paths.repo_root / config.paired_config, PairedControlConfig)
    paired_record = _newest_record(paths, f"paired_control_v{paired.version}")
    design = paired_record["in_force"]
    if design is None:
        raise RuntimeError("no probe design is in force under ADR-0024; G1 stopped the work")
    control_path = next(
        c
        for c in paired.control_configs
        if load_config(paths.repo_root / c, ProbeControlConfig).design == design
    )
    control = load_config(paths.repo_root / control_path, ProbeControlConfig)
    gate = load_config(paths.repo_root / control.gate_config, GateCheckConfig)
    pooled, bootstrap = control.pooled_sources, gate.bootstrap
    digest = config_hash(config)
    out_dir = paths.checkpoints_dir / f"bag_of_tokens_v{config.version}_{digest}"
    log_dir = paths.data_reports_dir / f"bag_of_tokens_v{config.version}_steps"
    started = time.perf_counter()

    inputs = open_probe_inputs(
        paths,
        gate.mixture_config,
        gate.ladder_config,
        gate.arm,
        gate.rung,
        gate.selection_windows,
        gate.held_out_source,
        config.device,
    )
    stage, telemetry, device = inputs.ladder.risk, inputs.telemetry, inputs.device
    assert isinstance(stage, PositiveAwareRiskStage)
    seed_everything(config.seed)
    torch.manual_seed(config.seed)
    budget = stage.budget("probe")
    model = BagOfTokens(telemetry.vocab_size, telemetry.context_steps).to(device)
    sampler = balanced_training_sampler(telemetry, inputs.ladder, stage, budget.batch_windows)
    train_rate = sampler.positives_per_batch / budget.batch_windows
    offset = prior_correction(train_rate, sampler.natural_rate)

    def measure(module: nn.Module) -> Measurement:
        logits, labels, _ = risk_logits(module, inputs.splits["selection"].sampler, device, False)
        scored = score_source("validation", logits + offset, labels, math.nan)
        return Measurement(
            step=0, windows=0, value=scored.auprc, extra={"base_rate": scored.base_rate}
        )

    run = train(
        module=model,
        batches=sampler.forever(config.seed),
        budget=budget,
        optimiser=inputs.ladder.optimiser,
        device=device,
        loss_fn=lambda m, t, y: m.loss(t, y, 1.0),  # type: ignore[operator]
        measure=measure,
        higher_is_better=True,
        tokens_per_window=telemetry.context_tokens,
        label="bag_of_tokens",
    )
    step_log = write_step_log(run.step_log, log_dir / "bag_of_tokens.steps.csv")
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"kind": "bag_of_tokens", "seed": config.seed, "state": run.state},
        out_dir / "bag_of_tokens.pt",
    )
    model.load_state_dict(run.state)
    model.eval()

    # -- the subsample, as every probe scored it -------------------------------------------
    test = inputs.splits["test"]
    logits, labels, which = risk_logits(model, test.sampler, device, False)
    subsample = ScoredWindows.load(
        save_scores(
            out_dir / "bag_of_tokens_test_scores.npz",
            ProbeResult(
                probe_positives_seen=sampler.positives_seen,
                probe_seconds=run.seconds,
                probe_selected=(run.best.step, run.best.value),
                prior_offset=offset,
                natural_rate=sampler.natural_rate,
                test=[],
                held_out_calibration={},
                step_log=step_log,
                logits=logits,
                labels=labels,
                which=which,
            ),
            test,
        )
    )
    # -- the deciding stride ----------------------------------------------------------------
    evaluation = inputs.ladder.evaluation
    split = build_split(
        telemetry,
        "test",
        None,
        paired.stride,
        evaluation.seed,
        evaluation.batch_windows,
        stage.label,
        sources=pooled,
    )
    stride_logits, stride_labels, _ = risk_logits(model, split.sampler, device, False)
    deciding = save_split_scores(
        out_dir / f"bag_of_tokens_stride{paired.stride}_scores.npz",
        (stride_logits, stride_labels),
        split,
        offset,
    )

    # -- the probe in force, on the same windows -----------------------------------------------
    trained_subsample = ScoredWindows.load(
        trained_scores_path(paths, gate)
        if design == "final_position"
        else paths.checkpoints_dir
        / f"probe_control_v{control.version}_{config_hash(control)}"
        / f"{gate.rung}_trained_seed{gate.seed}_test_scores.npz"
    )
    trained_deciding = ScoredWindows.load(
        paths.checkpoints_dir
        / f"paired_control_v{paired.version}_{config_hash(paired)}"
        / design
        / f"{gate.rung}_trained_seed{gate.seed}_stride{paired.stride}_scores.npz"
    )
    rows: dict[str, dict[str, Any]] = {}
    for name, bag, probe in (
        (f"stride {paired.stride}", deciding, trained_deciding),
        (
            "24,000-window subsample",
            _restricted(subsample, pooled),
            _restricted(trained_subsample, pooled),
        ),
    ):
        if not bag.same_windows(probe):
            raise ValueError(f"{name}: the comparator and the probe scored other windows")
        blocks = window_blocks(bag.ends, bag.which, bootstrap.block_steps)
        args = (bootstrap.replicates, bootstrap.seed, bootstrap.confidence)
        rows[name] = {
            "bag": bootstrap_auprc(bag.logits + bag.prior_offset, bag.labels, blocks, *args),
            "probe": bootstrap_auprc(
                probe.logits + probe.prior_offset, probe.labels, blocks, *args
            ),
            "delta": paired_bootstrap_deltas(
                probe.logits + probe.prior_offset,
                [bag.logits + bag.prior_offset],
                bag.labels,
                blocks,
                *args,
            )[0],
        }
    seconds = time.perf_counter() - started
    history = [(m.step, m.value) for m in run.history]
    stem = f"bag_of_tokens_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(
        render_report(config, config_path, design, run.best, history, run, rows, seconds, paths),
        encoding="utf-8",
        newline="\n",
    )
    record = paths.data_reports_dir / f"{stem}.json"
    payload = {
        "config": config.model_dump(mode="json"),
        "config_hash": digest,
        "design_in_force": design,
        "seconds": seconds,
        "selected": [run.best.step, run.best.value],
        "history": history,
        "final_train_loss": run.final_train_loss,
        "prior_offset": offset,
        "rows": {k: {part: asdict(v) for part, v in row.items()} for k, row in rows.items()},
    }
    record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record)
    return report, record


def render_report(
    config: BagOfTokensConfig,
    config_path: Path,
    design: str,
    best: Measurement,
    history: list[tuple[int, float]],
    run: Any,
    rows: dict[str, dict[str, Any]],
    seconds: float,
    paths: ProjectPaths,
) -> str:
    """Render the comparator's report.

    Args:
        config: The comparator configuration.
        config_path: Where it was read from.
        design: The probe design in force.
        best: The selected validation measurement.
        history: Every validation measurement, as (step, AUPRC).
        run: The training result.
        rows: Per test set, the comparator's and the probe's intervals and the paired Δ.
        seconds: Wall clock.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """

    def iv(value: AuprcInterval) -> str:
        return f"{value.auprc:.4f} [{value.low:.4f}, {value.high:.4f}]"

    def dv(value: DeltaInterval) -> str:
        return f"{value.delta:+.4f} [{value.low:+.4f}, {value.high:+.4f}]"

    body = [
        (
            name,
            f"{row['bag'].windows:,} / {row['bag'].positives:,}",
            iv(row["probe"]),
            iv(row["bag"]),
            dv(row["delta"]),
        )
        for name, row in rows.items()
    ]
    relative = config_path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    return "".join(
        [
            "# Bag-of-tokens comparator\n\n",
            kv_table(
                {
                    "configuration": f"{relative} (hash {config_hash(config)})",
                    "decision record": "docs/DECISIONS.md, ADR-0024 §6 (registered in 79d4e97)",
                    "probe in force": f"{SECTION[design]} {design}",
                    "selected": f"validation AUPRC {best.value:.4f} at step {best.step}",
                    "final training loss": f"{run.final_train_loss:.4f}",
                    "wall clock": f"{seconds / 60:.1f} min on {config.device}",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model bag-of-tokens",
                }
            ),
            section(
                "1. Pooled Kelmarsh + Penmanshiel test AUPRC, 95% block intervals",
                table(
                    [
                        "test set",
                        "windows / positive",
                        "probe in force",
                        "bag of tokens",
                        "Δ probe − bag, paired interval",
                    ],
                    body,
                )
                + "\nReported, deciding nothing (ADR-0024 §6).\n",
            ),
            section(
                "2. Validation measurements",
                table(["step", "validation AUPRC"], [(s, f"{v:.4f}") for s, v in history]),
            ),
        ]
    )
