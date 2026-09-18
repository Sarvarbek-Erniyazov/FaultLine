"""Pretraining never pads, and a pretraining run stops before its first update on a wrong loss.

The pretraining loss (``TelemetryDecoder.loss``) has no ignore-index path, so the property it rests
on is tested here instead: no sampler yields a window shorter than the context or holding ``<pad>``.
The fail-fast guard on the first batch loss is tested at both edges of its band, against every
recorded pretraining run's first step, and inside ``train``.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import pytest
import torch
from torch import Tensor, nn

from faultline.training.config import Budget, Optimiser
from faultline.training.joint_windows import (
    PAD_ID,
    MixtureSampler,
    StreamWindows,
    run_step_starts,
    tile_starts,
)
from faultline.training.loop import (
    INITIAL_LOSS_ABOVE,
    INITIAL_LOSS_BELOW,
    InitialLossError,
    Measurement,
    check_initial_loss,
    read_step_log,
    train,
)

REPO = Path(__file__).resolve().parents[2]
VOCAB = 33952
LN = math.log(VOCAB)

#: Every pretraining run on record: its per-step log, whose step 1 is its first optimiser step.
RECORDED = [
    "reports/data/gate_check_v0_steps/S2_tel_only_seed1_lm.steps.csv",
    "reports/data/seed_replication_v0_steps/S2_tel_only_seed2_lm.steps.csv",
    "reports/data/seed_replication_v0_steps/S2_tel_only_seed3_lm.steps.csv",
    "reports/data/variance_probe_v0_steps/S2_tel_only_seed1_lm.steps.csv",
    "reports/data/variance_probe_v0_steps/S2_tel_only_seed2_lm.steps.csv",
]


# =====================================================================================
# no short window, no padding
# =====================================================================================


def test_every_admitted_start_leaves_a_whole_window_inside_its_run() -> None:
    rng = np.random.default_rng(0)
    for _ in range(200):
        context = int(rng.integers(8, 64))
        tokens = int(rng.integers(0, 400))
        starts = tile_starts(tokens, context)
        assert np.all(starts + context <= tokens)
        assert starts.size == tokens // context
        lengths = rng.integers(3, 30, 60)
        offsets = np.concatenate([[0], np.cumsum(lengths)[:-1]])
        first = int(offsets[int(rng.integers(0, 20))])
        run = int(offsets[int(rng.integers(20, 60))]) - first
        admitted = run_step_starts(offsets, first, run, int(rng.integers(1, 7)), context)
        assert np.all(admitted >= first) and np.all(admitted + context <= first + run)


def test_the_mixture_never_yields_a_short_or_padded_window() -> None:
    context = 32

    def pool(name: str, sizes: list[int], seed: int) -> StreamWindows:
        streams = {
            f"{name}{k}": np.random.default_rng([seed, k]).integers(1, 30000, n)
            for k, n in enumerate(sizes)
        }
        index = np.concatenate(
            [
                np.stack([np.full(t.size, k), t], axis=1)
                for k, t in enumerate(tile_starts(n, context) for n in sizes)
            ]
        )
        return StreamWindows(
            streams=streams,  # type: ignore[arg-type]
            keys=list(streams),
            index=index.astype(np.int64),
            context=context,
            train_tokens=sum(sizes),
        )

    sampler = MixtureSampler(
        pools={  # type: ignore[arg-type]
            "tel": pool("tel", [1000, 33], 1),
            "txt": pool("txt", [95, 64, 700], 2),
            "tel+status": pool("ts", [2000, 31], 3),
        },
        shares={"tel": 0.3, "txt": 0.2, "tel+status": 0.5},  # type: ignore[dict-item]
        seed=5,
        batch=4,
    )
    batches = sampler.forever()
    for _ in range(100):  # 400 windows: more than one pass over txt's 26 tiles
        tokens, _, _ = next(batches)
        assert tokens.shape == (4, context)
        assert not torch.any(tokens == PAD_ID)


def _joint_root() -> Path | None:
    found = sorted((REPO / "data/shards/joint").glob("joint_v1_*/manifest.json"))
    return found[-1].parent if found else None


@pytest.mark.skipif(_joint_root() is None, reason="the joint_v1 shards are not staged here")
def test_the_real_pools_admit_only_whole_windows_and_hold_no_padding() -> None:
    from faultline.config import load_config
    from faultline.evaluation.gate_check import GateCheckConfig
    from faultline.evaluation.h1_gate import H1ArmsConfig
    from faultline.evaluation.variance_probe import mixture_pools, open_probe_inputs
    from faultline.paths import ProjectPaths

    runner = load_config(REPO / "configs/train/h1_arms_v0.yaml", H1ArmsConfig)
    gate = load_config(REPO / runner.gate_config, GateCheckConfig)
    inputs = open_probe_inputs(
        ProjectPaths.resolve(),
        runner.mixture_config,
        runner.ladder_config,
        runner.arm,
        runner.rung,
        8,
        gate.held_out_source,
        "cpu",
        window_rule=runner.probe.window_rule,
    )
    arm = next(a for a in inputs.mixture.arms if a.name == runner.arm)
    pools = mixture_pools(inputs, arm)
    assert set(pools) == {"tel", "txt", "tel+status"}
    for pool in pools.values():
        sizes = np.array([pool.streams[k].size for k in pool.keys])
        assert np.all(pool.index[:, 1] + pool.context <= sizes[pool.index[:, 0]])
        for stream in pool.streams.values():
            assert not np.any(np.asarray(stream) == PAD_ID)


# =====================================================================================
# the fail-fast guard
# =====================================================================================


@pytest.mark.parametrize(
    ("loss", "fails"),
    [
        (LN, False),
        (LN + INITIAL_LOSS_ABOVE - 1e-4, False),
        (LN + INITIAL_LOSS_ABOVE + 1e-4, True),
        (LN - INITIAL_LOSS_BELOW + 1e-4, False),
        (LN - INITIAL_LOSS_BELOW - 1e-4, True),
        (float("nan"), True),
        (float("inf"), True),
    ],
)
def test_the_guard_refuses_a_first_loss_outside_its_band(
    loss: float, fails: bool, caplog: pytest.LogCaptureFixture
) -> None:
    assert (INITIAL_LOSS_ABOVE, INITIAL_LOSS_BELOW) == (0.10, 0.50)
    with caplog.at_level(logging.ERROR, logger="faultline.training.loop"):
        if fails:
            with pytest.raises(InitialLossError, match="aborting before the first update"):
                check_initial_loss(loss, VOCAB, "run")
            message = caplog.records[-1]
            assert message.levelno == logging.ERROR
            assert f"{LN:.4f}" in message.getMessage()
        else:
            check_initial_loss(loss, VOCAB, "run")
            assert not caplog.records


@pytest.mark.parametrize("log", RECORDED)
def test_the_guard_passes_every_recorded_first_step(log: str) -> None:
    first = read_step_log(REPO / log)[0]
    assert first.step == 1
    check_initial_loss(first.loss, VOCAB, log)


class _Constant(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.ones(2, 2))

    def loss(self, value: float) -> Tensor:
        return self.weight.sum() * 0.0 + value


def _batches() -> object:
    while True:
        yield torch.zeros(2, 4, dtype=torch.long), torch.zeros(2), np.zeros(2)


@pytest.mark.parametrize(("value", "fails"), [(LN, False), (LN + 0.2, True), (LN - 0.6, True)])
def test_train_stops_before_its_first_update_on_a_wrong_first_loss(
    value: float, fails: bool
) -> None:
    module = _Constant()
    start = module.weight.detach().clone()
    budget = Budget(windows=4, batch_windows=2, accumulate=2, learning_rate=0.1, evaluations=1)
    optimiser = Optimiser(
        weight_decay=0.1,
        beta1=0.9,
        beta2=0.95,
        warmup_fraction=0.02,
        grad_clip=1.0,
        precision="fp32",
    )

    def run() -> None:
        train(
            module=module,
            batches=_batches(),  # type: ignore[arg-type]
            budget=budget,
            optimiser=optimiser,
            device=torch.device("cpu"),
            loss_fn=lambda m, t, y: m.loss(value),  # type: ignore[operator]
            measure=lambda m: Measurement(step=0, windows=0, value=0.0),
            higher_is_better=False,
            tokens_per_window=4,
            initial_loss_vocab=VOCAB,
        )

    if fails:
        with pytest.raises(InitialLossError):
            run()
        assert torch.equal(module.weight.detach(), start)  # no update was taken
    else:
        run()
    # A head's run passes no vocabulary and is never checked.
    train(
        module=_Constant(),
        batches=_batches(),  # type: ignore[arg-type]
        budget=budget,
        optimiser=optimiser,
        device=torch.device("cpu"),
        loss_fn=lambda m, t, y: m.loss(0.69),  # type: ignore[operator]
        measure=lambda m: Measurement(step=0, windows=0, value=0.0),
        higher_is_better=False,
        tokens_per_window=4,
    )
