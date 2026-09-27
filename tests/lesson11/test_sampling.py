"""Sampling pipeline: constrained decoding, penalty sign, top-k/top-p, greedy, seeding."""

from __future__ import annotations

import math

import pytest
import torch
from inference.sampling import (
    SamplingParams,
    apply_temperature,
    mask_allowed,
    repetition_penalty,
    sample_next,
    seeded_generator,
    top_k_filter,
    top_p_filter,
)


def test_mask_respected_over_many_draws() -> None:
    logits = torch.randn(50, generator=seeded_generator(0))
    logits[3] = 100.0  # the favourite is not allowed
    allowed = torch.zeros(50, dtype=torch.bool)
    allowed[[10, 11, 12]] = True
    generator = seeded_generator(1)
    params = SamplingParams(temperature=2.0, seed=1)
    drawn = {sample_next(logits, params, allowed=allowed, generator=generator) for _ in range(300)}
    assert drawn <= {10, 11, 12}
    greedy = sample_next(logits, SamplingParams(temperature=0.0), allowed=allowed)
    assert greedy in {10, 11, 12}


def test_mask_refuses_empty_and_misshapen() -> None:
    with pytest.raises(ValueError):
        mask_allowed(torch.zeros(4), torch.zeros(4, dtype=torch.bool))
    with pytest.raises(ValueError):
        mask_allowed(torch.zeros(4), torch.ones(3, dtype=torch.bool))


def test_top_k_keeps_exactly_k_even_with_ties() -> None:
    logits = torch.tensor([1.0, 1.0, 1.0, 1.0, 0.5, 2.0])
    out = top_k_filter(logits, 3)
    assert int(torch.isfinite(out).sum()) == 3
    assert torch.isfinite(out[5])
    assert int(torch.isfinite(top_k_filter(logits, 0)).sum()) == 6
    assert int(torch.isfinite(top_k_filter(logits, 99)).sum()) == 6


def test_top_p_edge_cases() -> None:
    # probabilities 0.5, 0.3, 0.2
    logits = torch.log(torch.tensor([0.2, 0.5, 0.3]))

    def kept(p: float) -> set[int]:
        return set(torch.isfinite(top_p_filter(logits, p)).nonzero().flatten().tolist())

    assert kept(1.0) == {0, 1, 2}
    assert kept(0.01) == {1}  # the top token always survives
    assert kept(0.5) == {1}  # exactly reaching p stops there
    assert kept(0.51) == {1, 2}
    assert kept(0.8) == {1, 2}
    assert kept(0.81) == {0, 1, 2}
    with pytest.raises(ValueError):
        top_p_filter(logits, 0.0)
    with pytest.raises(ValueError):
        top_p_filter(logits, 1.5)


def test_penalty_respects_sign() -> None:
    logits = torch.tensor([2.0, -2.0, 1.0])
    out = repetition_penalty(logits, [0, 1, 1], 2.0)
    assert out.tolist() == [1.0, -4.0, 1.0]  # positive divided, negative multiplied, unseen kept
    assert torch.equal(repetition_penalty(logits, [0], 1.0), logits)
    with pytest.raises(ValueError):
        repetition_penalty(logits, [0], 0.5)


def test_greedy_is_argmax() -> None:
    logits = torch.randn(100, generator=seeded_generator(3))
    params = SamplingParams(temperature=0.0, top_k=5, top_p=0.3)
    assert sample_next(logits, params) == int(torch.argmax(logits))
    assert torch.equal(apply_temperature(logits, 0.0), logits)


def test_seeded_determinism() -> None:
    logits = torch.randn(200, generator=seeded_generator(4))
    params = SamplingParams(temperature=1.2, top_k=50, top_p=0.9, seed=7)

    def run() -> list[int]:
        generator = seeded_generator(params.seed)
        return [sample_next(logits, params, generator=generator) for _ in range(40)]

    first, second = run(), run()
    assert first == second
    assert len(set(first)) > 1  # it is actually sampling


def test_temperature_scales() -> None:
    logits = torch.tensor([1.0, 2.0])
    assert torch.allclose(apply_temperature(logits, 0.5), torch.tensor([2.0, 4.0]))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature": -0.1},
        {"temperature": 2.01},
        {"top_p": 0.0},
        {"top_p": 1.01},
        {"repetition_penalty": 0.99},
        {"repetition_penalty": 2.01},
        {"top_k": -1},
    ],
)
def test_invalid_parameters_raise(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        SamplingParams(**kwargs)  # type: ignore[arg-type]


def test_slide_softmax_sanity() -> None:
    # after top-k 2 on [0, ln 3, -inf...], the draw distribution is 1/4, 3/4
    logits = torch.tensor([0.0, math.log(3.0), -5.0, -6.0])
    generator = seeded_generator(11)
    params = SamplingParams(temperature=1.0, top_k=2, seed=11)
    draws = [sample_next(logits, params, generator=generator) for _ in range(4000)]
    assert set(draws) == {0, 1}
    assert abs(draws.count(1) / len(draws) - 0.75) < 0.03
