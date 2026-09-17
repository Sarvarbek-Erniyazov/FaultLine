"""The schedule, the parameter groups, and that a run actually descends its loss."""

from __future__ import annotations

import numpy as np
import pytest
import torch
from torch import Tensor, nn

from faultline.model.transformer import ModelSpec, TelemetryDecoder
from faultline.training.config import Budget, Optimiser
from faultline.training.loop import (
    LR_FLOOR,
    Measurement,
    StepLog,
    learning_rate,
    parameter_groups,
    read_step_log,
    train,
    write_step_log,
)
from faultline.training.windows import Batch

CONTEXT = 52
VOCAB = 64


def spec() -> ModelSpec:
    return ModelSpec(name="T", d_model=32, n_layer=2, n_head=4, context=CONTEXT, vocab_size=VOCAB)


def test_the_schedule_warms_up_then_decays_to_the_floor() -> None:
    total, peak = 100, 1e-3
    rates = [learning_rate(step, total, peak, 0.1) for step in range(total)]
    warmup = 10
    assert rates[0] == pytest.approx(peak / warmup)
    assert rates[warmup - 1] == pytest.approx(peak)
    assert rates[:warmup] == sorted(rates[:warmup])
    # cosine from the peak down to the floor, monotonically
    assert rates[warmup:] == sorted(rates[warmup:], reverse=True)
    assert rates[-1] == pytest.approx(peak * LR_FLOOR, rel=0.02)
    assert min(rates) >= peak * LR_FLOOR * 0.99


def test_the_warmup_is_never_zero_steps_even_on_a_short_run() -> None:
    # A run short enough to round the warmup to nothing must still not start at the peak
    # of a schedule it never warmed into.
    assert learning_rate(0, 3, 1e-3, 0.02) == pytest.approx(1e-3)
    assert learning_rate(0, 1000, 1e-3, 0.0) == pytest.approx(1e-3)


def test_only_matrices_are_decayed() -> None:
    model = TelemetryDecoder(spec())
    decayed, plain = parameter_groups(model, 0.1)
    assert decayed["weight_decay"] == 0.1 and plain["weight_decay"] == 0.0
    assert all(p.dim() >= 2 for p in decayed["params"])
    assert all(p.dim() < 2 for p in plain["params"])
    assert len(decayed["params"]) + len(plain["params"]) == len(list(model.parameters()))


def test_a_frozen_parameter_never_reaches_the_optimiser() -> None:
    model = TelemetryDecoder(spec())
    for parameter in model.blocks.parameters():
        parameter.requires_grad_(False)
    groups = parameter_groups(model, 0.1)
    given = {id(p) for group in groups for p in group["params"]}
    assert not any(id(p) in given for p in model.blocks.parameters())


def batches(seed: int = 0) -> Batch:
    """An endless stream of one repeated, learnable batch."""
    rng = np.random.default_rng(seed)
    pattern = torch.from_numpy(rng.integers(0, VOCAB, size=(4, CONTEXT)).astype(np.int64))
    labels = torch.zeros(4)
    while True:
        yield pattern, labels, np.zeros(4, dtype=np.int64)


def test_a_run_descends_its_loss_and_reports_what_it_spent() -> None:
    torch.manual_seed(0)
    model = TelemetryDecoder(spec())
    seen: list[float] = []

    def loss_fn(module: nn.Module, tokens: Tensor, _: Tensor) -> Tensor:
        return module.loss(tokens)

    def measure(module: nn.Module) -> Measurement:
        with torch.no_grad():
            value = float(module.loss(next(batches())[0]))
        seen.append(value)
        return Measurement(step=0, windows=0, value=value)

    budget = Budget(windows=80, batch_windows=4, accumulate=1, learning_rate=3e-3, evaluations=4)
    result = train(
        module=model,
        batches=batches(),
        budget=budget,
        optimiser=Optimiser(),
        device=torch.device("cpu"),
        loss_fn=loss_fn,
        measure=measure,
        higher_is_better=False,
        tokens_per_window=CONTEXT,
        label="test",
    )
    assert result.steps == 20
    assert result.windows == 80
    assert result.tokens == 80 * CONTEXT
    assert len(result.history) == 4
    assert seen[-1] < seen[0]
    assert result.best.value == min(seen)
    assert result.seconds > 0


def test_the_selected_checkpoint_is_the_best_measurement_not_the_last() -> None:
    # Selection is on validation, and a run that ends worse than it peaked must keep the
    # peak. The measurement here is scripted so the best is deliberately not the last.
    torch.manual_seed(0)
    model = TelemetryDecoder(spec())
    scripted = iter([0.9, 0.2, 0.5, 0.7])

    def loss_fn(module: nn.Module, tokens: Tensor, _: Tensor) -> Tensor:
        return module.loss(tokens)

    def measure(_: nn.Module) -> Measurement:
        return Measurement(step=0, windows=0, value=next(scripted))

    result = train(
        module=model,
        batches=batches(),
        budget=Budget(windows=32, batch_windows=4, accumulate=1, learning_rate=1e-3, evaluations=4),
        optimiser=Optimiser(),
        device=torch.device("cpu"),
        loss_fn=loss_fn,
        measure=measure,
        higher_is_better=False,
        tokens_per_window=CONTEXT,
    )
    assert result.best.value == pytest.approx(0.2)
    assert [m.value for m in result.history] == [0.9, 0.2, 0.5, 0.7]


def test_higher_is_better_selects_the_other_way() -> None:
    torch.manual_seed(0)
    model = TelemetryDecoder(spec())
    scripted = iter([0.1, 0.4, 0.3, 0.2])

    def loss_fn(module: nn.Module, tokens: Tensor, _: Tensor) -> Tensor:
        return module.loss(tokens)

    def measure(_: nn.Module) -> Measurement:
        return Measurement(step=0, windows=0, value=next(scripted))

    result = train(
        module=model,
        batches=batches(),
        budget=Budget(windows=32, batch_windows=4, accumulate=1, learning_rate=1e-3, evaluations=4),
        optimiser=Optimiser(),
        device=torch.device("cpu"),
        loss_fn=loss_fn,
        measure=measure,
        higher_is_better=True,
        tokens_per_window=CONTEXT,
    )
    assert result.best.value == pytest.approx(0.4)


def test_accumulation_takes_the_same_number_of_windows_in_fewer_steps() -> None:
    torch.manual_seed(0)

    def loss_fn(module: nn.Module, tokens: Tensor, _: Tensor) -> Tensor:
        return module.loss(tokens)

    def measure(_: nn.Module) -> Measurement:
        return Measurement(step=0, windows=0, value=0.0)

    plain = train(
        module=TelemetryDecoder(spec()),
        batches=batches(),
        budget=Budget(windows=32, batch_windows=4, accumulate=1, learning_rate=1e-3),
        optimiser=Optimiser(),
        device=torch.device("cpu"),
        loss_fn=loss_fn,
        measure=measure,
        higher_is_better=False,
        tokens_per_window=CONTEXT,
    )
    accumulated = train(
        module=TelemetryDecoder(spec()),
        batches=batches(),
        budget=Budget(windows=32, batch_windows=4, accumulate=2, learning_rate=1e-3),
        optimiser=Optimiser(),
        device=torch.device("cpu"),
        loss_fn=loss_fn,
        measure=measure,
        higher_is_better=False,
        tokens_per_window=CONTEXT,
    )
    assert plain.windows == accumulated.windows == 32
    assert accumulated.steps * 2 == plain.steps


def test_every_optimiser_step_is_logged_with_its_loss_rate_and_windows(tmp_path) -> None:
    torch.manual_seed(0)
    losses: list[float] = []

    def loss_fn(module: nn.Module, tokens: Tensor, _: Tensor) -> Tensor:
        loss = module.loss(tokens)
        losses.append(float(loss.detach()))
        return loss

    def measure(_: nn.Module) -> Measurement:
        return Measurement(step=0, windows=0, value=0.0)

    budget = Budget(windows=48, batch_windows=4, accumulate=3, learning_rate=1e-3, evaluations=2)
    result = train(
        module=TelemetryDecoder(spec()),
        batches=batches(),
        budget=budget,
        optimiser=Optimiser(),
        device=torch.device("cpu"),
        loss_fn=loss_fn,
        measure=measure,
        higher_is_better=False,
        tokens_per_window=CONTEXT,
    )
    log = result.step_log
    # one row a step, not one a validation measurement
    assert [row.step for row in log] == list(range(1, budget.steps + 1)) == list(range(1, 5))
    assert [row.windows for row in log] == [12, 24, 36, 48]
    for index, row in enumerate(log):
        # the step's loss is the mean of its accumulated forward passes, unscaled
        assert row.loss == pytest.approx(np.mean(losses[3 * index : 3 * index + 3]), rel=1e-5)
        assert row.learning_rate == pytest.approx(
            learning_rate(index, budget.steps, budget.learning_rate, Optimiser().warmup_fraction)
        )
        assert row.grad_norm > 0
    path = write_step_log(log, tmp_path / "run.steps.csv")
    back = read_step_log(path)
    assert [r.step for r in back] == [r.step for r in log]
    assert [r.loss for r in back] == pytest.approx([r.loss for r in log], rel=1e-7)
    assert isinstance(back[0], StepLog)


def test_a_scaled_parameter_gets_its_own_groups_and_a_plain_module_keeps_two() -> None:
    from faultline.model.risk import RiskModel, RiskSpec

    assert len(parameter_groups(TelemetryDecoder(spec()), 0.1)) == 2
    model = RiskModel(spec(), RiskSpec(), frozen=True, unfrozen_blocks=1, backbone_lr_scale=0.25)
    groups = parameter_groups(model, 0.1)
    assert [g["lr_scale"] for g in groups] == [1.0, 1.0, 0.25, 0.25]
    scaled = {id(p) for g in groups if g["lr_scale"] == 0.25 for p in g["params"]}
    assert scaled == {id(p) for p in model.backbone.blocks[-1].parameters()}


def test_named_measurement_steps_replace_the_even_spacing_and_step_zero_is_never_selected() -> None:
    # ADR-0024 G3: measure at chosen steps, and at step 0 as a reference that cannot win.
    def run(steps: list[int] | None, initial: bool) -> tuple[list[int], int, list[Tensor]]:
        torch.manual_seed(0)
        model = TelemetryDecoder(spec())
        scripted = iter([0.99, 0.1, 0.5, 0.2, 0.25, 0.4, 0.15])

        def loss_fn(module: nn.Module, tokens: Tensor, _: Tensor) -> Tensor:
            return module.loss(tokens)

        def measure(_: nn.Module) -> Measurement:
            return Measurement(step=0, windows=0, value=next(scripted))

        result = train(
            module=model,
            batches=batches(),
            budget=Budget(windows=80, batch_windows=4, learning_rate=1e-3, evaluations=4),
            optimiser=Optimiser(),
            device=torch.device("cpu"),
            loss_fn=loss_fn,
            measure=measure,
            higher_is_better=True,
            tokens_per_window=CONTEXT,
            label="test",
            measure_steps=steps,
            measure_initial=initial,
        )
        return [m.step for m in result.history], result.best.step, list(model.parameters())

    steps, best, dense = run([2, 4, 6, 10, 20], initial=True)
    assert steps == [0, 2, 4, 6, 10, 20]
    assert best == 4  # 0.99 at step 0 is the highest and is not selectable
    _, _, even = run(None, initial=False)
    # measuring more often does not change the trajectory
    assert all(torch.equal(a, b) for a, b in zip(dense, even, strict=True))
    with pytest.raises(ValueError, match="measurement steps"):
        run([0, 5], initial=False)
