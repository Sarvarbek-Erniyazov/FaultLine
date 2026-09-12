"""Text-only pretraining and evaluation (M2d/M2e).

Same decoder, same training loop, same discipline the telemetry ladder used
(``faultline.evaluation.ladder``): budgets in windows, selection on validation only,
the test split read once after selection. Two runs, S2 and S3 -- the same rungs the
telemetry ladder defined, read from the same ``configs/model/ladder_v*.yaml`` rather
than re-typed here, so the two cannot drift apart -- one seed each, at the context
length ``configs/tokenizer/text_shards_v1.yaml`` fixed (2048 tokens).

**The budget is "one pass over the training corpus, or a wall-clock cap, whichever is
smaller" (the M2 brief's 4 GPU-hours), and the run states which one bound it.** The
shared training loop (``training/loop.py``) is budgeted in a fixed window count, not
wall-clock time, and that is not changed here -- a calibration pass measures this
rung's actual throughput first, converts the wall-clock cap to an equivalent window
count, and the smaller of the two window counts is what the loop is handed. Measured,
not assumed: throughput at context 2048 has no reason to match the telemetry ladder's
144-step context.

Evaluation is next-token loss in nats *and* bits-per-byte, per source, never pooled --
the M2 brief's whole evaluation on the text side. Bits-per-byte divides by each
source's own UTF-8 byte count rather than a shared constant, because a byte-level
tokenizer's bytes-per-token compression is not the same at every source (M2c's own
report).
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from pydantic import Field
from torch import nn

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.data.text.bpe_fit import read_split
from faultline.data.text.shards import load_text_shards_config
from faultline.data.text.shards import shards_dir as text_shards_dir
from faultline.data.text.shards import tokenizer_path as text_tokenizer_path
from faultline.logging_utils import get_logger
from faultline.model.transformer import TelemetryDecoder
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.seed import seed_everything
from faultline.training.config import Budget, LadderModel, Optimiser, Rung
from faultline.training.loop import Measurement, TrainingResult, language_model_loss, train
from faultline.training.windows import ShardSet, WindowSampler, load_windows

logger = get_logger(__name__)

SELECTED_RUNGS: tuple[str, ...] = ("S2", "S3")


class TextPretrainConfig(StrictModel):
    """Top level of ``configs/train/text_v1.yaml``.

    Attributes:
        version: Version of this configuration.
        shards_config: The text shards configuration to train over.
        model_config_path: ``configs/model/ladder_v*.yaml``, read for the S2/S3
            architecture only -- its own ``context_steps`` (telemetry's) is not used.
        rungs: Which rungs to run; ``S2`` and ``S3`` by default, per the M2 brief.
        seed: The one seed each rung runs.
        optimiser: Shared optimiser and schedule settings.
        batch_windows: Windows per forward pass.
        accumulate: Forward passes per optimiser step.
        learning_rate: Peak learning rate.
        calibration_steps: Optimiser steps timed before the budgeted run, to measure
            this rung's actual windows/second at this context length.
        gpu_hour_budget: Wall-clock hours the calibration is allowed to imply a window
            budget for; whichever of this or one full pass over the corpus is smaller
            is what the run actually spends.
        evaluations: Validation measurements taken during the budgeted run.
        train_stride: Admissible windows kept, every Nth (telemetry's reason for
            striding -- windows overlapping in all but one step -- applies less to text,
            where documents are short, but the knob is still recorded per run).
        eval_stride: Stride for validation/test scoring; 1, the same discipline as the
            telemetry ladder (a model is scored on every position it would answer at).
        selection_windows: Per-source cap on the windows the periodic validation
            measurement reads.
        validation_windows: Per-source cap on the final validation report.
        test_windows: Per-source cap on the test report.
        eval_seed: Seed of every evaluation subsample.
        dropout: Backbone dropout, the same at every rung.
    """

    version: int = 1
    shards_config: str
    model_config_path: str = "configs/model/ladder_v0.yaml"
    rungs: list[str] = Field(default_factory=lambda: list(SELECTED_RUNGS))
    seed: int = 1
    optimiser: Optimiser = Field(default_factory=Optimiser)
    batch_windows: int = 16
    accumulate: int = 2
    learning_rate: float = 6.0e-4
    calibration_steps: int = 20
    gpu_hour_budget: float = 4.0
    evaluations: int = 6
    train_stride: int = 1
    eval_stride: int = 1
    selection_windows: int = 3000
    validation_windows: int = 15000
    test_windows: int = 12000
    eval_seed: int = 20260913
    dropout: float = 0.0


def load_text_pretrain_config(path: Path) -> TextPretrainConfig:
    """Load and validate a text pretraining configuration.

    Args:
        path: Path to the YAML file.

    Returns:
        The validated configuration.
    """
    return load_config(path, TextPretrainConfig)


def _rungs(paths: ProjectPaths, config: TextPretrainConfig) -> list[Rung]:
    """Read the named rungs' architecture out of the model ladder config.

    Args:
        paths: Resolved project paths.
        config: The pretraining configuration.

    Returns:
        The requested rungs, in the order ``config.rungs`` names them.

    Raises:
        KeyError: If a requested rung is not in the model configuration.
    """
    model_config = load_config(paths.repo_root / config.model_config_path, LadderModel)
    by_name = {rung.name: rung for rung in model_config.rungs}
    missing = [name for name in config.rungs if name not in by_name]
    if missing:
        raise KeyError(f"rung(s) {missing} not in {config.model_config_path}")
    return [by_name[name] for name in config.rungs]


def _training_sampler(shards: ShardSet, stride: int, batch_windows: int) -> WindowSampler:
    """Build the sampler over every training source's admissible windows.

    Args:
        shards: The text shard set.
        stride: Admissible windows kept, every Nth.
        batch_windows: Windows per forward pass.

    Returns:
        A sampler over the whole training split.
    """
    sets = [load_windows(shards, key, stride=stride) for key in shards.keys("train")]
    return WindowSampler(
        [s for s in sets if len(s)],
        batch_size=batch_windows,
        tokens_per_step=shards.tokens_per_step,
        context_steps=shards.context_steps,
        labelled=False,
    )


def _per_source_loss(
    shards: ShardSet,
    split: str,
    sources: list[str],
    per_source_cap: int,
    stride: int,
    seed: int,
    batch_windows: int,
    module: nn.Module,
    device: torch.device,
    autocast_on: bool,
) -> dict[str, float]:
    """Next-token loss per source on one split, never pooled.

    Args:
        shards: The text shard set.
        split: ``val`` or ``test``.
        sources: Sources to score.
        per_source_cap: Windows kept per source after the stride, seeded.
        stride: Stride the windows are taken at before the cap.
        seed: Seed of the subsample.
        batch_windows: Windows per forward pass.
        module: The decoder, in evaluation mode.
        device: Where the model lives.
        autocast_on: Whether to run the pass in bfloat16.

    Returns:
        Per source, the mean loss per predicted token.
    """
    losses: dict[str, float] = {}
    for source in sources:
        key = f"{source}__{split}"
        if key not in shards.files():
            continue
        window_set = load_windows(shards, key, stride=stride, limit=per_source_cap, seed=seed)
        if not len(window_set):
            logger.warning("%s holds no admissible window; it is not scored", key)
            continue
        sampler = WindowSampler(
            [window_set],
            batch_size=batch_windows,
            tokens_per_step=shards.tokens_per_step,
            context_steps=shards.context_steps,
            labelled=False,
        )
        losses[source] = language_model_loss(module, sampler, device, autocast_on)
    return losses


def _bytes_per_source(paths: ProjectPaths, corpus_name: str, split: str) -> dict[str, int]:
    """Total UTF-8 bytes per source in one split of the finished corpus.

    Args:
        paths: Resolved project paths.
        corpus_name: The finished text corpus.
        split: ``val`` or ``test``.

    Returns:
        Per source, total bytes; empty if the split does not exist.
    """
    try:
        documents = read_split(paths, corpus_name, split)
    except FileNotFoundError:
        return {}
    totals: dict[str, int] = {}
    for document in documents:
        totals[document.source] = totals.get(document.source, 0) + len(
            document.text.encode("utf-8")
        )
    return totals


@dataclass
class TextRunRecord:
    """One rung's pretraining run, ready to report.

    Attributes:
        rung: Rung name.
        seed: The seed run.
        params: Parameter counts (``parameter_counts()``).
        train_loss: Mean training loss over the run's last tenth.
        selected: The selected validation measurement.
        history: Every validation measurement.
        validation_loss: Per-source next-token loss (nats) on validation.
        test_loss: Per-source next-token loss (nats) on test.
        validation_bpb: Per-source bits-per-byte on validation.
        test_bpb: Per-source bits-per-byte on test.
        windows: Training windows consumed.
        tokens: Training tokens consumed.
        seconds: Wall-clock seconds spent training (measurement included).
        budget_bound: Which bound the run's window budget hit: ``"one_pass"`` or
            ``"gpu_hours"``.
        one_pass_windows: The training split's size in windows, measured.
        gpu_hour_windows: The wall-clock cap's equivalent window count, measured from
            this rung's own calibrated throughput.
    """

    rung: str
    seed: int
    params: dict[str, int]
    train_loss: float
    selected: Measurement
    history: list[Measurement]
    validation_loss: dict[str, float]
    test_loss: dict[str, float]
    validation_bpb: dict[str, float]
    test_bpb: dict[str, float]
    windows: int
    tokens: int
    seconds: float
    budget_bound: str
    one_pass_windows: int
    gpu_hour_windows: int


def _bits_per_byte(nats_per_token: float, tokens: int, byte_count: int) -> float:
    """Convert a mean next-token loss in nats to bits per byte.

    Args:
        nats_per_token: Mean cross entropy per predicted token, in nats.
        tokens: Predicted tokens the loss was averaged over.
        byte_count: UTF-8 bytes those tokens decode to.

    Returns:
        Bits per byte, or ``nan`` if there are no bytes to divide by.
    """
    if byte_count <= 0 or tokens <= 0:
        return math.nan
    return nats_per_token * tokens / (byte_count * math.log(2))


def run_rung(
    rung: Rung,
    config: TextPretrainConfig,
    shards: ShardSet,
    device: torch.device,
    paths: ProjectPaths,
    corpus_name: str,
) -> TextRunRecord:
    """Pretrain and evaluate one rung.

    Args:
        rung: The architecture to run.
        config: The pretraining configuration.
        shards: The text shard set.
        device: Where the model lives.
        paths: Resolved project paths.
        corpus_name: The finished corpus, for the byte counts bits-per-byte divides by.

    Returns:
        The run's record.
    """
    seed_everything(config.seed)
    torch.manual_seed(config.seed)
    spec = rung.spec(shards.context_tokens, shards.vocab_size, config.dropout)
    autocast_on = config.optimiser.precision == "bf16"

    module = TelemetryDecoder(spec).to(device)
    counts = module.parameter_counts()
    train_sampler = _training_sampler(shards, config.train_stride, config.batch_windows)

    val_sources = sorted({key.rsplit("__", 1)[0] for key in shards.keys("val")})
    selection_sets = [
        load_windows(
            shards,
            f"{source}__val",
            stride=config.eval_stride,
            limit=config.selection_windows,
            seed=config.eval_seed,
        )
        for source in val_sources
    ]
    selection_sampler = WindowSampler(
        [s for s in selection_sets if len(s)],
        batch_size=config.batch_windows,
        tokens_per_step=shards.tokens_per_step,
        context_steps=shards.context_steps,
        labelled=False,
    )

    def loss_fn(model: nn.Module, tokens: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        del labels
        return model.loss(tokens)  # type: ignore[operator,no-any-return]

    def measure(model: nn.Module) -> Measurement:
        value = language_model_loss(model, selection_sampler, device, autocast_on)
        return Measurement(step=0, windows=0, value=value)

    # -- calibrate throughput, then decide the window budget ------------------------
    calibration_windows = config.calibration_steps * config.batch_windows * config.accumulate
    calibration_generator = train_sampler.forever(config.seed)
    started = time.perf_counter()
    calibration_budget = Budget(
        windows=calibration_windows,
        batch_windows=config.batch_windows,
        accumulate=config.accumulate,
        learning_rate=config.learning_rate,
        evaluations=1,
    )
    train(
        module=module,
        batches=calibration_generator,
        budget=calibration_budget,
        optimiser=config.optimiser,
        device=device,
        loss_fn=loss_fn,
        measure=measure,
        higher_is_better=False,
        tokens_per_window=shards.context_tokens,
        label=f"{rung.name}/calibrate",
    )
    calibration_seconds = time.perf_counter() - started
    windows_per_second = (
        calibration_windows / calibration_seconds if calibration_seconds > 0 else 1.0
    )

    one_pass_windows = train_sampler.windows
    gpu_hour_windows = int(windows_per_second * config.gpu_hour_budget * 3600)
    budget_windows = min(one_pass_windows, gpu_hour_windows)
    budget_bound = "one_pass" if one_pass_windows <= gpu_hour_windows else "gpu_hours"
    logger.info(
        "%s: calibrated %.1f windows/s; one pass = %d windows, %.1f GPU-hours = %d windows; "
        "spending %d (%s bound)",
        rung.name,
        windows_per_second,
        one_pass_windows,
        config.gpu_hour_budget,
        gpu_hour_windows,
        budget_windows,
        budget_bound,
    )

    budget = Budget(
        windows=max(1, budget_windows),
        batch_windows=config.batch_windows,
        accumulate=config.accumulate,
        learning_rate=config.learning_rate,
        evaluations=config.evaluations,
    )
    result: TrainingResult = train(
        module=module,
        batches=train_sampler.forever(config.seed),
        budget=budget,
        optimiser=config.optimiser,
        device=device,
        loss_fn=loss_fn,
        measure=measure,
        higher_is_better=False,
        tokens_per_window=shards.context_tokens,
        label=f"{rung.name}/lm",
    )
    module.load_state_dict({k: v.to(device) for k, v in result.state.items()})
    module.eval()

    test_sources = sorted({key.rsplit("__", 1)[0] for key in shards.keys("test")})
    validation_loss = _per_source_loss(
        shards,
        "val",
        val_sources,
        config.validation_windows,
        config.eval_stride,
        config.eval_seed,
        config.batch_windows,
        module,
        device,
        autocast_on,
    )
    test_loss = _per_source_loss(
        shards,
        "test",
        test_sources,
        config.test_windows,
        config.eval_stride,
        config.eval_seed,
        config.batch_windows,
        module,
        device,
        autocast_on,
    )
    val_bytes = _bytes_per_source(paths, corpus_name, "val")
    test_bytes = _bytes_per_source(paths, corpus_name, "test")
    tokens_per_window = shards.context_tokens - 1

    def to_bpb(losses: dict[str, float], byte_totals: dict[str, int]) -> dict[str, float]:
        return {
            source: _bits_per_byte(loss, tokens_per_window, byte_totals.get(source, 0))
            for source, loss in losses.items()
        }

    return TextRunRecord(
        rung=rung.name,
        seed=config.seed,
        params=counts,
        train_loss=result.final_train_loss,
        selected=result.best,
        history=result.history,
        validation_loss=validation_loss,
        test_loss=test_loss,
        validation_bpb=to_bpb(validation_loss, val_bytes),
        test_bpb=to_bpb(test_loss, test_bytes),
        windows=result.windows,
        tokens=result.tokens,
        seconds=result.seconds,
        budget_bound=budget_bound,
        one_pass_windows=one_pass_windows,
        gpu_hour_windows=gpu_hour_windows,
    )


# =====================================================================================
# orchestration and reporting
# =====================================================================================


def _load_shards(paths: ProjectPaths, config: TextPretrainConfig) -> tuple[ShardSet, str]:
    """Open the text shard set a pretraining configuration names.

    Args:
        paths: Resolved project paths.
        config: The pretraining configuration.

    Returns:
        The shard set, and the corpus name (for reading raw byte counts).
    """
    shards_config_path = paths.repo_root / config.shards_config
    shards_config = load_text_shards_config(shards_config_path)
    bpe_config_path = paths.repo_root / shards_config.tokenizer_config
    source_tokenizer = text_tokenizer_path(paths, bpe_config_path)
    root = text_shards_dir(paths, source_tokenizer)
    shards = ShardSet.load(root)
    from faultline.data.text.bpe_fit import load_text_bpe_config

    corpus_name = load_text_bpe_config(bpe_config_path).corpus_name
    return shards, corpus_name


def _render_report(
    config: TextPretrainConfig,
    config_path: Path,
    records: list[TextRunRecord],
    context_tokens: int,
    paths: ProjectPaths,
) -> str:
    """Render the M2d/M2e text pretraining report.

    Args:
        config: The pretraining configuration.
        config_path: Where it lives, for the header.
        records: One record per rung run.
        context_tokens: Context length in tokens, the same for every rung.
        paths: Resolved project paths.

    Returns:
        The report, as Markdown.
    """
    header = kv_table(
        {
            "training config": config_path.as_posix(),
            "config hash": config_hash(config),
            "shards config": config.shards_config,
            "context (tokens)": context_tokens,
            "rungs": ", ".join(r.rung for r in records),
            "seed": config.seed,
            "optimiser": (
                f"AdamW, betas ({config.optimiser.beta1}, {config.optimiser.beta2}), "
                f"weight decay {config.optimiser.weight_decay}, cosine schedule with "
                f"{config.optimiser.warmup_fraction * 100:.0f}% warmup, "
                f"clip {config.optimiser.grad_clip}, {config.optimiser.precision}"
            ),
            "selection": "validation next-token loss",
            "test": "never selected on",
            "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "git_sha": git_sha(paths.repo_root),
            "generated by": "faultline model text-pretrain",
        }
    )

    budget_rows = [
        (
            r.rung,
            r.one_pass_windows,
            r.gpu_hour_windows,
            r.windows,
            r.budget_bound,
            f"{r.seconds / 60:.1f}",
        )
        for r in records
    ]
    budget_section = section(
        "What each rung was allowed to spend, and which bound it hit",
        "Measured, not assumed: the wall-clock bound is this rung's own calibrated "
        "throughput at this context length, not carried over from the telemetry ladder's "
        "144-step context.\n\n"
        + table(
            [
                "rung",
                "one pass (windows)",
                f"{config.gpu_hour_budget:g} GPU-hours (windows)",
                "windows spent",
                "bound hit",
                "wall clock (min)",
            ],
            budget_rows,
        ),
    )

    lm_rows = [
        (r.rung, r.params["total"], f"{r.selected.value:.4f}", f"{r.train_loss:.4f}")
        for r in records
    ]
    lm_section = section(
        "Language modelling: next-token loss (nats)",
        "Selected on validation next-token loss; the mean training loss over the last "
        "tenth of the run is beside it as context, not as a selection criterion.\n\n"
        + table(
            ["rung", "parameters (total)", "validation loss (selected)", "train loss"], lm_rows
        ),
    )

    def per_source_rows(get_loss: Any, get_bpb: Any) -> list[tuple[str, str, str, str]]:
        rows = []
        for r in records:
            for source in sorted(get_loss(r)):
                rows.append(
                    (r.rung, source, f"{get_loss(r)[source]:.4f}", f"{get_bpb(r)[source]:.4f}")
                )
        return rows

    val_section = section(
        "Validation loss and bits-per-byte, per source",
        "Never pooled across sources.\n\n"
        + table(
            ["rung", "source", "loss (nats)", "bits/byte"],
            per_source_rows(lambda r: r.validation_loss, lambda r: r.validation_bpb),
        ),
    )
    test_section = section(
        "Test loss and bits-per-byte, per source",
        "Read once, after selection, never used to select.\n\n"
        + table(
            ["rung", "source", "loss (nats)", "bits/byte"],
            per_source_rows(lambda r: r.test_loss, lambda r: r.test_bpb),
        ),
    )

    return (
        "# Text-only pretraining (M2d/M2e)\n\n"
        + header
        + "\n"
        + budget_section
        + lm_section
        + val_section
        + test_section
    )


def run_text_ladder(
    paths: ProjectPaths, config_path: Path, device_name: str | None = None
) -> tuple[Path, Path]:
    """Run every configured rung and write the machine-readable record and the report.

    Args:
        paths: Resolved project paths.
        config_path: The pretraining configuration.
        device_name: Torch device to run on; chosen automatically when omitted.

    Returns:
        The JSON record path and the report path.
    """
    config = load_text_pretrain_config(config_path)
    shards, corpus_name = _load_shards(paths, config)
    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    rungs = _rungs(paths, config)

    records = []
    for rung in rungs:
        logger.info("running %s", rung.name)
        records.append(run_rung(rung, config, shards, device, paths, corpus_name))

    report = _render_report(config, config_path, records, shards.context_tokens, paths)
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d")
    report_path = paths.data_reports_dir / f"text_pretrain_v{config.version}_{stamp}.md"
    report_path.write_text(report, encoding="utf-8")

    json_path = paths.data_reports_dir / f"text_pretrain_v{config.version}_{stamp}.json"
    json_path.write_text(
        json.dumps(
            [
                {
                    "rung": r.rung,
                    "seed": r.seed,
                    "params": r.params,
                    "train_loss": r.train_loss,
                    "selected": {"step": r.selected.step, "value": r.selected.value},
                    "history": [{"step": m.step, "value": m.value} for m in r.history],
                    "validation_loss": r.validation_loss,
                    "test_loss": r.test_loss,
                    "validation_bpb": r.validation_bpb,
                    "test_bpb": r.test_bpb,
                    "windows": r.windows,
                    "tokens": r.tokens,
                    "seconds": r.seconds,
                    "budget_bound": r.budget_bound,
                    "one_pass_windows": r.one_pass_windows,
                    "gpu_hour_windows": r.gpu_hour_windows,
                }
                for r in records
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    logger.info("wrote %s and %s", json_path, report_path)
    return json_path, report_path
