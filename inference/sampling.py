"""Next-token sampling as pure functions on a logit vector (Course Lesson 11).

The pipeline runs in a fixed order, and each stage is its own function so each can be tested
alone:

1. **allowed-id mask** -- constrained decoding: every id outside the allowed set gets ``-inf``,
   so no later stage can bring it back;
2. **repetition penalty** -- CTRL's rule (Keskar et al., 2019): a logit of an id already in the
   history is divided by the penalty when positive and multiplied by it when negative, so the
   penalty always makes a seen id less likely, whatever the sign;
3. **temperature** -- logits divided by ``T``; ``T == 0`` means greedy and skips the rest;
4. **top-k** -- keep exactly the ``k`` highest logits;
5. **top-p** -- keep the smallest prefix of the sorted distribution whose mass reaches ``p``,
   and always the top token;
6. **softmax**, then 7. a **seeded** draw from a ``torch.Generator``.

Nothing here reads a model: the functions take a 1-D logit tensor and return one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import torch
from torch import Tensor

#: The ranges the parameters are checked against (the slide's, with ``T == 0`` meaning greedy).
TEMPERATURE_RANGE = (0.0, 2.0)
PENALTY_RANGE = (1.0, 2.0)


@dataclass(frozen=True)
class SamplingParams:
    """One decoding strategy.

    Attributes:
        temperature: In ``[0, 2]``; ``0`` is greedy.
        top_k: Keep this many highest logits; ``0`` disables the filter.
        top_p: Nucleus mass in ``(0, 1]``; ``1`` disables the filter.
        repetition_penalty: In ``[1, 2]``; ``1`` disables it.
        seed: Seed of the draw.
    """

    temperature: float = 1.0
    top_k: int = 0
    top_p: float = 1.0
    repetition_penalty: float = 1.0
    seed: int = 0

    def __post_init__(self) -> None:
        """Refuse a parameter outside its range.

        Raises:
            ValueError: If any parameter is out of range.
        """
        low, high = TEMPERATURE_RANGE
        if not low <= self.temperature <= high:
            raise ValueError(f"temperature must be in [{low}, {high}], got {self.temperature}")
        if self.top_k < 0:
            raise ValueError(f"top_k must be >= 0, got {self.top_k}")
        if not 0.0 < self.top_p <= 1.0:
            raise ValueError(f"top_p must be in (0, 1], got {self.top_p}")
        low, high = PENALTY_RANGE
        if not low <= self.repetition_penalty <= high:
            raise ValueError(
                f"repetition_penalty must be in [{low}, {high}], got {self.repetition_penalty}"
            )

    @property
    def greedy(self) -> bool:
        """Whether this strategy is greedy decoding."""
        return self.temperature == 0.0


def _check_vector(logits: Tensor) -> None:
    if logits.dim() != 1:
        raise ValueError(f"logits must be 1-D, got shape {tuple(logits.shape)}")


def mask_allowed(logits: Tensor, allowed: Tensor) -> Tensor:
    """Constrained decoding: every id outside ``allowed`` gets ``-inf``.

    Args:
        logits: ``(vocab,)`` logits.
        allowed: ``(vocab,)`` boolean mask of the ids that may be emitted.

    Returns:
        The masked logits, a new tensor.

    Raises:
        ValueError: If the shapes differ or nothing is allowed.
    """
    _check_vector(logits)
    if allowed.shape != logits.shape or allowed.dtype != torch.bool:
        raise ValueError("allowed must be a boolean mask of the logits' shape")
    if not bool(allowed.any()):
        raise ValueError("the allowed set is empty")
    return logits.masked_fill(~allowed, float("-inf"))


def repetition_penalty(logits: Tensor, previous: Sequence[int], penalty: float) -> Tensor:
    """CTRL's repetition penalty: seen ids are divided (positive) or multiplied (negative).

    Args:
        logits: ``(vocab,)`` logits.
        previous: Ids already in the sequence; repeats count once.
        penalty: In ``[1, 2]``; ``1`` returns the logits unchanged.

    Returns:
        The penalised logits, a new tensor.

    Raises:
        ValueError: If the penalty is out of range.
    """
    _check_vector(logits)
    low, high = PENALTY_RANGE
    if not low <= penalty <= high:
        raise ValueError(f"repetition_penalty must be in [{low}, {high}], got {penalty}")
    out = logits.clone()
    if penalty == 1.0 or not previous:
        return out
    seen = torch.tensor(sorted(set(previous)), dtype=torch.long, device=logits.device)
    values = out[seen]
    out[seen] = torch.where(values > 0, values / penalty, values * penalty)
    return out


def apply_temperature(logits: Tensor, temperature: float) -> Tensor:
    """Divide by the temperature; ``0`` (greedy) returns the logits unchanged.

    Args:
        logits: ``(vocab,)`` logits.
        temperature: In ``[0, 2]``.

    Returns:
        The scaled logits.

    Raises:
        ValueError: If the temperature is out of range.
    """
    _check_vector(logits)
    low, high = TEMPERATURE_RANGE
    if not low <= temperature <= high:
        raise ValueError(f"temperature must be in [{low}, {high}], got {temperature}")
    return logits.clone() if temperature == 0.0 else logits / temperature


def top_k_filter(logits: Tensor, k: int) -> Tensor:
    """Keep exactly the ``k`` highest logits; the rest get ``-inf``.

    Ties at the boundary are broken by ``torch.topk``, so exactly ``k`` survive.

    Args:
        logits: ``(vocab,)`` logits.
        k: How many to keep; ``0``, or ``k`` at or above the vocabulary, keeps all.

    Returns:
        The filtered logits.

    Raises:
        ValueError: If ``k`` is negative.
    """
    _check_vector(logits)
    if k < 0:
        raise ValueError(f"top_k must be >= 0, got {k}")
    if k == 0 or k >= logits.numel():
        return logits.clone()
    keep = torch.topk(logits, k).indices
    out = torch.full_like(logits, float("-inf"))
    out[keep] = logits[keep]
    return out


def top_p_filter(logits: Tensor, p: float) -> Tensor:
    """Nucleus filter: the smallest sorted prefix whose probability mass reaches ``p``.

    The top token is always kept, so even a ``p`` below its probability leaves one token.

    Args:
        logits: ``(vocab,)`` logits.
        p: Mass in ``(0, 1]``; ``1`` keeps every finite logit.

    Returns:
        The filtered logits.

    Raises:
        ValueError: If ``p`` is out of range.
    """
    _check_vector(logits)
    if not 0.0 < p <= 1.0:
        raise ValueError(f"top_p must be in (0, 1], got {p}")
    if p == 1.0:
        return logits.clone()
    ordered, order = torch.sort(logits, descending=True)
    probabilities = torch.softmax(ordered, dim=-1)
    before = torch.cumsum(probabilities, dim=-1) - probabilities
    # A token is kept while the mass before it is still short of p; the first always is.
    drop = before >= p
    drop[0] = False
    out = logits.clone()
    out[order[drop]] = float("-inf")
    return out


def sample_next(
    logits: Tensor,
    params: SamplingParams,
    previous: Sequence[int] = (),
    allowed: Tensor | None = None,
    generator: torch.Generator | None = None,
) -> int:
    """Run the whole pipeline on one logit vector and return the chosen id.

    Args:
        logits: ``(vocab,)`` logits, any float dtype; computed in float32.
        params: The strategy.
        previous: Ids already in the sequence, for the repetition penalty.
        allowed: Boolean mask of emittable ids, or ``None`` for every id.
        generator: The seeded generator the draw reads; ignored when greedy.

    Returns:
        The chosen id.
    """
    x = logits.float()
    if allowed is not None:
        x = mask_allowed(x, allowed)
    x = repetition_penalty(x, previous, params.repetition_penalty)
    if params.greedy:
        return int(torch.argmax(x).item())
    x = apply_temperature(x, params.temperature)
    x = top_k_filter(x, params.top_k)
    x = top_p_filter(x, params.top_p)
    probabilities = torch.softmax(x, dim=-1)
    return int(torch.multinomial(probabilities, 1, generator=generator).item())


def seeded_generator(seed: int) -> torch.Generator:
    """A CPU generator at a seed, so a strategy's draws repeat exactly.

    Args:
        seed: The seed.

    Returns:
        The generator.
    """
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    return generator
