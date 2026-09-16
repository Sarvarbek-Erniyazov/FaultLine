"""The training loop, shared by the four runs of the ladder (M1e).

One loop drives all four, because the ablation is only an ablation if the runs differ in
what the configuration says they differ in and in nothing else. The language model and the
three risk runs hand the loop a different per-batch loss and a different validation
measurement; the schedule, the clipping, the precision, the shuffling and the selection
rule are the same code for all of them.

**Runs are budgeted in windows, not epochs.** A rung's epoch is a different amount of work
at every size, and the comparison is between rungs. **Selection is on validation, always.**
The best checkpoint of a run is the best of its periodic validation measurements, and the
test split is never read here at all.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import numpy as np
import torch
from torch import Tensor, nn

from faultline.logging_utils import get_logger
from faultline.training.config import Budget, Optimiser
from faultline.training.windows import Batch, WindowSampler

logger = get_logger(__name__)

#: Fraction of the peak learning rate the cosine schedule decays to.
LR_FLOOR = 0.1


def learning_rate(step: int, total: int, peak: float, warmup_fraction: float) -> float:
    """The learning rate at one optimiser step: linear warmup, then cosine decay.

    Args:
        step: The step about to be taken, counted from zero.
        total: Steps in the whole run.
        peak: Peak learning rate.
        warmup_fraction: Share of the run spent warming up.

    Returns:
        The learning rate for this step.
    """
    warmup = max(1, int(round(warmup_fraction * total)))
    if step < warmup:
        return peak * (step + 1) / warmup
    progress = min(1.0, (step - warmup) / max(1, total - warmup))
    return peak * (LR_FLOOR + (1 - LR_FLOOR) * 0.5 * (1 + math.cos(math.pi * progress)))


def parameter_groups(module: nn.Module, weight_decay: float) -> list[dict[str, Any]]:
    """Split trainable parameters into the decayed and the undecayed.

    Matrices are decayed; norms, biases and anything else one-dimensional are not, which
    is the usual rule and is stated here because it is a choice.

    Args:
        module: The model.
        weight_decay: Decay applied to the matrices.

    Returns:
        Two parameter groups, either of which may be empty.
    """
    decay = [p for p in module.parameters() if p.requires_grad and p.dim() >= 2]
    plain = [p for p in module.parameters() if p.requires_grad and p.dim() < 2]
    return [
        {"params": decay, "weight_decay": weight_decay},
        {"params": plain, "weight_decay": 0.0},
    ]


@dataclass
class Measurement:
    """One validation measurement taken during a run.

    Attributes:
        step: The optimiser step it was taken after.
        windows: Training windows consumed by then.
        value: The selection metric.
        extra: Anything else worth keeping, such as the loss beside an AUPRC.
    """

    step: int
    windows: int
    value: float
    extra: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class StepLog:
    """One optimiser step's training record, kept for every step of every run.

    Validation is measured a handful of times a run, and at a 50M-token arm that is too few
    points to read a curve from. The training loss is computed at every step anyway, and
    once a run ends it cannot be recovered, so it is kept.

    Attributes:
        step: The optimiser step, counted from one.
        windows: Training windows consumed by the end of the step.
        learning_rate: The rate the step was taken at.
        loss: Mean training loss over the step's forward passes.
        grad_norm: Global gradient norm before clipping.
    """

    step: int
    windows: int
    learning_rate: float
    loss: float
    grad_norm: float


STEP_LOG_COLUMNS: tuple[str, ...] = ("step", "windows", "learning_rate", "loss", "grad_norm")


def write_step_log(log: Sequence[StepLog], path: Path) -> Path:
    """Write a run's per-step log as CSV, one row a step.

    Args:
        log: The run's step log.
        path: Destination.

    Returns:
        The path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(STEP_LOG_COLUMNS)]
    lines += [
        f"{s.step},{s.windows},{s.learning_rate:.8g},{s.loss:.8g},{s.grad_norm:.8g}" for s in log
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def read_step_log(path: Path) -> list[StepLog]:
    """Read a per-step log written by :func:`write_step_log`."""
    rows = path.read_text(encoding="utf-8").splitlines()[1:]
    out = []
    for row in rows:
        step, windows, rate, loss, norm = row.split(",")
        out.append(StepLog(int(step), int(windows), float(rate), float(loss), float(norm)))
    return out


@dataclass
class TrainingResult:
    """What one run produced.

    Attributes:
        history: Every validation measurement, in order.
        best: The selected measurement.
        state: The selected checkpoint's parameters, on the CPU.
        steps: Optimiser steps taken.
        windows: Training windows consumed.
        tokens: Training tokens consumed.
        seconds: Wall-clock seconds spent, measurement included.
        final_train_loss: Mean training loss over the last tenth of the run.
        step_log: Every optimiser step's training loss, rate and gradient norm, in order.
    """

    history: list[Measurement]
    best: Measurement
    state: dict[str, Tensor]
    steps: int
    windows: int
    tokens: int
    seconds: float
    final_train_loss: float
    step_log: list[StepLog] = field(default_factory=list)


def _snapshot(module: nn.Module) -> dict[str, Tensor]:
    """Copy the model's parameters to the CPU, detached."""
    return {name: value.detach().to("cpu").clone() for name, value in module.state_dict().items()}


def train(
    module: nn.Module,
    batches: Iterator[Batch],
    budget: Budget,
    optimiser: Optimiser,
    device: torch.device,
    loss_fn: Callable[[nn.Module, Tensor, Tensor], Tensor],
    measure: Callable[[nn.Module], Measurement],
    higher_is_better: bool,
    tokens_per_window: int,
    label: str = "",
) -> TrainingResult:
    """Train one model to its budget, selecting on periodic validation measurements.

    Args:
        module: The model, already on ``device``.
        batches: An endless stream of training batches.
        budget: How much the run may spend and how often it is measured.
        optimiser: The optimiser and schedule, shared by every run.
        device: Where the model lives.
        loss_fn: Given the model, a batch's tokens and its labels, the loss to descend.
        measure: Given the model in evaluation mode, one validation measurement.
        higher_is_better: Whether a larger measurement is a better one.
        tokens_per_window: Tokens a window contributes, for the token count.
        label: Name of the run, for the log.

    Returns:
        The run's history, its selected checkpoint and what it spent.
    """
    module.train()
    groups = parameter_groups(module, optimiser.weight_decay)
    opt = torch.optim.AdamW(
        groups, lr=budget.learning_rate, betas=(optimiser.beta1, optimiser.beta2)
    )
    autocast = torch.autocast(
        device_type=device.type,
        dtype=torch.bfloat16,
        enabled=optimiser.precision == "bf16" and device.type == "cuda",
    )
    total = budget.steps
    measure_every = max(1, total // budget.evaluations)
    trainable = [p for group in groups for p in group["params"]]

    history: list[Measurement] = []
    best: Measurement | None = None
    state = _snapshot(module)
    recent: list[float] = []
    tail = max(1, total // 10)
    started = time.perf_counter()
    windows = 0
    step_log: list[StepLog] = []

    for step in range(total):
        rate = learning_rate(step, total, budget.learning_rate, optimiser.warmup_fraction)
        for group in opt.param_groups:
            group["lr"] = rate
        opt.zero_grad(set_to_none=True)
        step_losses: list[float] = []
        for _ in range(budget.accumulate):
            tokens, labels, _ = next(batches)
            tokens, labels = tokens.to(device, non_blocking=True), labels.to(device)
            with autocast:
                loss = loss_fn(module, tokens, labels) / budget.accumulate
            loss.backward()  # type: ignore[no-untyped-call]
            windows += int(tokens.shape[0])
            step_losses.append(float(loss.detach()) * budget.accumulate)
        recent.extend(step_losses)
        norm = torch.nn.utils.clip_grad_norm_(trainable, optimiser.grad_clip)
        opt.step()
        step_log.append(
            StepLog(
                step=step + 1,
                windows=windows,
                learning_rate=rate,
                loss=float(np.mean(step_losses)),
                grad_norm=float(norm),
            )
        )
        if len(recent) > tail * budget.accumulate:
            recent = recent[-tail * budget.accumulate :]

        last = step == total - 1
        if (step + 1) % measure_every == 0 or last:
            module.eval()
            taken = measure(module)
            taken.step, taken.windows = step + 1, windows
            module.train()
            history.append(taken)
            better = best is None or (
                taken.value > best.value if higher_is_better else taken.value < best.value
            )
            if better and not math.isnan(taken.value):
                best, state = taken, _snapshot(module)
            logger.info(
                "%s step %d/%d lr %.2e loss %.4f validation %.4f%s",
                label,
                step + 1,
                total,
                rate,
                float(np.mean(recent[-64:])) if recent else math.nan,
                taken.value,
                " *" if better else "",
            )

    if best is None:  # pragma: no cover - only when every measurement was nan
        best = Measurement(step=total, windows=windows, value=math.nan)
    return TrainingResult(
        history=history,
        best=best,
        state=state,
        steps=total,
        windows=windows,
        tokens=windows * tokens_per_window,
        seconds=time.perf_counter() - started,
        final_train_loss=float(np.mean(recent)) if recent else math.nan,
        step_log=step_log,
    )


@torch.no_grad()
def language_model_loss(
    module: nn.Module, sampler: WindowSampler, device: torch.device, autocast_on: bool
) -> float:
    """Mean next-token cross entropy over one pass of a sampler.

    Args:
        module: The decoder, in evaluation mode.
        sampler: The windows to score.
        device: Where the model lives.
        autocast_on: Whether to run the pass in bfloat16.

    Returns:
        The mean loss per predicted token.
    """
    autocast = torch.autocast(
        device_type=device.type, dtype=torch.bfloat16, enabled=autocast_on and device.type == "cuda"
    )
    total, counted = 0.0, 0
    for tokens, _, _ in sampler.epoch():
        tokens = tokens.to(device, non_blocking=True)
        with autocast:
            loss = cast(Tensor, module.loss(tokens))  # type: ignore[operator]
        predicted = tokens.shape[0] * (tokens.shape[1] - 1)
        total += float(loss) * predicted
        counted += predicted
    return total / counted if counted else math.nan


@torch.no_grad()
def risk_logits(
    module: nn.Module, sampler: WindowSampler, device: torch.device, autocast_on: bool
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Score every window of a sampler.

    Args:
        module: The risk model, in evaluation mode.
        sampler: The windows to score.
        device: Where the model lives.
        autocast_on: Whether to run the pass in bfloat16.

    Returns:
        The logits, the labels and the index of the window set each window came from, so
        that the caller can score per source without pooling what must not be pooled.
    """
    autocast = torch.autocast(
        device_type=device.type, dtype=torch.bfloat16, enabled=autocast_on and device.type == "cuda"
    )
    logits: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    which: list[np.ndarray] = []
    for tokens, target, sets in sampler.epoch():
        tokens = tokens.to(device, non_blocking=True)
        with autocast:
            scored = module(tokens)
        logits.append(scored.float().cpu().numpy())
        labels.append(target.numpy())
        which.append(sets)
    if not logits:  # pragma: no cover - an empty split is refused when the sampler is built
        empty = np.zeros(0, dtype=np.float32)
        return empty, empty, np.zeros(0, dtype=np.int64)
    return np.concatenate(logits), np.concatenate(labels), np.concatenate(which)
