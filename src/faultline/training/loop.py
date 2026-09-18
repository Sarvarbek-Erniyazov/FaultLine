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

#: The fail-fast band on a pretraining run's first batch loss, around ln(vocabulary). Registered
#: 2026-09-18 by "test(model): causality under padding at the real spec; initial-loss assertion and
#: fail-fast guard". A decoder at initialisation (std 0.02, tied head) predicts almost uniformly,
#: so its first loss sits at ln(V): ln(33,952) = 10.4327, and every recorded S2 first step lies in
#: 10.4175..10.4639. Above ln(V) + 0.10 the logits are not near zero (a scale or tying defect).
#: Below ln(V) - 0.50 the model predicts before it has learned (a leak, a shifted target, or a
#: vocabulary smaller than the one declared).
INITIAL_LOSS_ABOVE = 0.10
INITIAL_LOSS_BELOW = 0.50


class InitialLossError(RuntimeError):
    """A pretraining run's first batch loss is outside the band around ln(vocabulary)."""


def check_initial_loss(loss: float, vocab_size: int, label: str = "") -> None:
    """Refuse a pretraining run whose first batch loss is not near ln(vocabulary).

    Args:
        loss: The first batch's mean next-token loss, before any update.
        vocab_size: The decoder's vocabulary.
        label: The run's name, for the log.

    Raises:
        InitialLossError: If the loss exceeds ``ln(V) + INITIAL_LOSS_ABOVE`` or falls below
            ``ln(V) - INITIAL_LOSS_BELOW``, or is not finite. It is logged at ERROR first.
    """
    expected = math.log(vocab_size)
    low, high = expected - INITIAL_LOSS_BELOW, expected + INITIAL_LOSS_ABOVE
    if not (math.isfinite(loss) and low <= loss <= high):
        message = (
            f"{label}: first-batch loss {loss:.4f} is outside [{low:.4f}, {high:.4f}] around "
            f"ln({vocab_size:,}) = {expected:.4f}; aborting before the first update"
        )
        logger.error(message)
        raise InitialLossError(message)


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
    scale_of = getattr(module, "parameter_lr_scale", None)
    named = [(n, p) for n, p in module.named_parameters() if p.requires_grad]
    scales = {n: float(scale_of(n)) if callable(scale_of) else 1.0 for n, _ in named}
    groups: list[dict[str, Any]] = []
    # One pair of groups a learning-rate scale. A module without scales gets exactly the two
    # groups it always had, in the same order, so every earlier run's optimiser is unchanged.
    for scale in sorted(set(scales.values()) | {1.0}, reverse=True):
        decay = [p for n, p in named if scales[n] == scale and p.dim() >= 2]
        plain = [p for n, p in named if scales[n] == scale and p.dim() < 2]
        if scale != 1.0 and not decay and not plain:
            continue
        groups.append({"params": decay, "weight_decay": weight_decay, "lr_scale": scale})
        groups.append({"params": plain, "weight_decay": 0.0, "lr_scale": scale})
    return groups


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
        final_state: The parameters after the last step, on the CPU, when asked for.
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
    final_state: dict[str, Tensor] | None = None


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
    measure_steps: Sequence[int] | None = None,
    measure_initial: bool = False,
    keep_final: bool = False,
    initial_loss_vocab: int | None = None,
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
        measure_steps: The optimiser steps (counted from one) after which to measure, in place
            of ``budget.evaluations`` evenly spaced ones (ADR-0024's G3 cadence).
        measure_initial: Also measure before the first step. That measurement is kept in the
            history as a reference and can never be selected.
        keep_final: Also return the parameters after the last step, beside the selected ones.
        initial_loss_vocab: For a pretraining run, the vocabulary its first batch loss is checked
            against (:func:`check_initial_loss`) before the first update. ``None`` for a head.

    Returns:
        The run's history, its selected checkpoint and what it spent.

    Raises:
        ValueError: If a measurement step lies outside the run.
        InitialLossError: If a pretraining run's first batch loss is outside its band.
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
    if measure_steps is not None and any(not 1 <= s <= total for s in measure_steps):
        raise ValueError(f"measurement steps must lie in 1..{total}: {sorted(measure_steps)}")
    chosen_steps = None if measure_steps is None else set(measure_steps)
    trainable = [p for group in groups for p in group["params"]]

    history: list[Measurement] = []
    best: Measurement | None = None
    state = _snapshot(module)
    recent: list[float] = []
    tail = max(1, total // 10)
    started = time.perf_counter()
    windows = 0
    step_log: list[StepLog] = []

    if measure_initial:
        # A measurement is an evaluation-mode pass: it takes no step and draws no training
        # randomness, so looking earlier does not change the trajectory.
        module.eval()
        initial = measure(module)
        initial.step, initial.windows = 0, 0
        initial.extra["reference"] = 1.0
        module.train()
        history.append(initial)
        logger.info("%s step 0/%d validation %.4f (reference)", label, total, initial.value)

    for step in range(total):
        rate = learning_rate(step, total, budget.learning_rate, optimiser.warmup_fraction)
        for group in opt.param_groups:
            group["lr"] = rate * group.get("lr_scale", 1.0)
        opt.zero_grad(set_to_none=True)
        step_losses: list[float] = []
        for _ in range(budget.accumulate):
            tokens, labels, _ = next(batches)
            tokens, labels = tokens.to(device, non_blocking=True), labels.to(device)
            with autocast:
                loss = loss_fn(module, tokens, labels) / budget.accumulate
            if initial_loss_vocab is not None and step == 0 and not step_losses:
                check_initial_loss(
                    float(loss.detach()) * budget.accumulate, initial_loss_vocab, label
                )
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
        due = (
            (step + 1) % measure_every == 0 or last
            if chosen_steps is None
            else step + 1 in chosen_steps
        )
        if due:
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
        final_state=_snapshot(module) if keep_final else None,
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
