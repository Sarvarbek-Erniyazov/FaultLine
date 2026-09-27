"""Seeded text generation under five decoding strategies (Course Lesson 11 output).

Eight prompts (``evaluation/prompts.txt``: four status-string style, four narrative style), five
strategies, one seeded sample each, through :meth:`inference.engine.Engine.generate_text` (CPU,
float32, constrained to text ids; ``<sep>`` ends the document). Per strategy, over its eight
samples: distinct-1 and distinct-2 (unique n-grams over all n-grams, token ids) and the
repeated-4-gram rate (4-grams that already occurred earlier in the same sample, over all
4-grams). No reference texts exist, so no BLEU or ROUGE.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from inference.engine import Engine
from inference.sampling import SamplingParams

PROMPTS_FILE = Path(__file__).resolve().parent / "prompts.txt"

#: Tokens each sample may emit.
MAX_NEW_TOKENS = 48

#: The draw's seed; sample ``i`` of a strategy uses ``SEED + i``.
SEED = 20260927


@dataclass(frozen=True)
class Strategy:
    """One decoding strategy.

    Attributes:
        name: Its label.
        params: Everything but the seed.
    """

    name: str
    params: SamplingParams


STRATEGIES = (
    Strategy("greedy", SamplingParams(temperature=0.0)),
    Strategy("T0.8_top_k50", SamplingParams(temperature=0.8, top_k=50)),
    Strategy("T0.8_top_p0.9", SamplingParams(temperature=0.8, top_p=0.9)),
    Strategy("T1.2_top_p0.9", SamplingParams(temperature=1.2, top_p=0.9)),
    Strategy("greedy_penalty1.3", SamplingParams(temperature=0.0, repetition_penalty=1.3)),
)


def read_prompts(path: Path = PROMPTS_FILE) -> list[tuple[str, str]]:
    """``(style, prompt)`` pairs, comments and blank lines skipped."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        style, prompt = line.split("\t", 1)
        out.append((style, prompt))
    return out


def ngrams(ids: Sequence[int], n: int) -> list[tuple[int, ...]]:
    """The n-grams of a sequence, in order."""
    return [tuple(ids[i : i + n]) for i in range(len(ids) - n + 1)]


def distinct(samples: Sequence[Sequence[int]], n: int) -> float:
    """Unique n-grams over all n-grams, pooled over samples; ``nan`` if there are none."""
    grams = [g for s in samples for g in ngrams(s, n)]
    return len(set(grams)) / len(grams) if grams else float("nan")


def repeated_4gram_rate(samples: Sequence[Sequence[int]]) -> float:
    """4-grams already seen earlier in their own sample, over all 4-grams; ``nan`` if none."""
    repeated = total = 0
    for sample in samples:
        seen: set[tuple[int, ...]] = set()
        for gram in ngrams(sample, 4):
            total += 1
            repeated += gram in seen
            seen.add(gram)
    return repeated / total if total else float("nan")


def run_generation(engine: Engine, prompts: list[tuple[str, str]]) -> dict[str, Any]:
    """Every strategy on every prompt, with the statistics.

    Args:
        engine: The serving engine.
        prompts: ``(style, prompt)`` pairs.

    Returns:
        Settings, and per strategy its samples and statistics.
    """
    strategies = {}
    for strategy in STRATEGIES:
        samples, ids = [], []
        for i, (style, prompt) in enumerate(prompts):
            params = SamplingParams(**{**asdict(strategy.params), "seed": SEED + i})
            out = engine.generate_text(prompt, params, max_new_tokens=MAX_NEW_TOKENS)
            ids.append(out.token_ids)
            samples.append(
                {
                    "style": style,
                    "prompt": prompt,
                    "seed": params.seed,
                    "continuation": out.text,
                    "tokens": len(out.token_ids),
                    "stop_reason": out.stop_reason,
                }
            )
        strategies[strategy.name] = {
            "params": asdict(strategy.params) | {"seed": f"{SEED} + prompt index"},
            "distinct_1": distinct(ids, 1),
            "distinct_2": distinct(ids, 2),
            "repeated_4gram_rate": repeated_4gram_rate(ids),
            "mean_tokens": sum(len(s) for s in ids) / len(ids),
            "samples": samples,
        }
    return {
        "max_new_tokens": MAX_NEW_TOKENS,
        "device": "cpu",
        "precision": "float32",
        "allowed_ids": "text block [1184, 33952) plus <sep> (8) as the stop token",
        "statistics_over": "token ids of the emitted continuation, prompt excluded",
        "strategies": strategies,
    }
