"""The M2b pre-registered near-duplicate trigger, measured before anything is built.

Exact deduplication (``dedup.py``) catches identical documents; it does not catch the
same incident republished with small edits, which the M2 brief expects in an
operator-narrative corpus. Rather than build MinHash-LSH speculatively, the brief
pre-registers a measurement that decides whether it is needed: on a 2,000-document
sample (after exact dedup), 5-shingle Jaccard overlap between every pair. If more than
5% of pairs above 0.8 survive exact dedup, MinHash-LSH is implemented as a second
strategy and both are reported; if not, the measurement itself is the record and
exact dedup stays the whole story.

All-pairs Jaccard over a 2,000-document sample is about two million comparisons --
feasible directly, which is exactly why the trigger is measured on a bounded sample
rather than the full corpus (where all-pairs comparison is what MinHash-LSH exists to
avoid). Shingles are hashed to integers before comparison, not compared as strings,
which is what keeps two million set intersections fast enough to run as a
pre-registered check rather than a project of its own.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


def shingles(text: str, k: int = 5) -> frozenset[int]:
    """The hashed set of ``k``-word shingles in a document.

    Args:
        text: Document body.
        k: Shingle width in whitespace-separated words.

    Returns:
        Hashed shingles; the whole (hashed) document if it holds fewer than ``k``
        words, so a short document is still comparable rather than contributing an
        empty set to every pairwise union.
    """
    words = text.split()
    if len(words) < k:
        return frozenset({hash(text)})
    return frozenset(hash(" ".join(words[i : i + k])) for i in range(len(words) - k + 1))


def jaccard(a: frozenset[int], b: frozenset[int]) -> float:
    """Jaccard similarity of two shingle sets.

    Args:
        a: First document's shingles.
        b: Second document's shingles.

    Returns:
        ``|a & b| / |a | b|``, or ``1.0`` if both are empty (two empty documents are
        identical, not incomparable).
    """
    if not a and not b:
        return 1.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


@dataclass(frozen=True)
class NearDuplicateMeasurement:
    """The pre-registered measurement's result.

    Attributes:
        sample_size: Documents actually sampled (at most the requested size).
        pairs_compared: Distinct pairs compared, ``sample_size choose 2``.
        pairs_above_threshold: Pairs whose Jaccard similarity exceeds the threshold.
        share_above_threshold: ``pairs_above_threshold / pairs_compared``.
        threshold: The similarity threshold used.
        trigger_fires: Whether ``share_above_threshold`` exceeds ``trigger_share``.
        trigger_share: The pre-registered firing threshold (0.05, per the M2 brief).
        example_pairs: A few of the highest-similarity pairs found, as
            ``(index_a, index_b, similarity)``, for the report to show evidence rather
            than only a percentage.
    """

    sample_size: int
    pairs_compared: int
    pairs_above_threshold: int
    share_above_threshold: float
    threshold: float
    trigger_fires: bool
    trigger_share: float
    example_pairs: list[tuple[int, int, float]] = field(default_factory=list)


def measure_near_duplicates(
    documents: list[str],
    sample_size: int = 2000,
    shingle_width: int = 5,
    similarity_threshold: float = 0.8,
    trigger_share: float = 0.05,
    seed: int = 20260913,
    example_count: int = 10,
) -> NearDuplicateMeasurement:
    """Run the M2b pre-registered near-duplicate trigger on a corpus already exact-deduped.

    Args:
        documents: Documents to sample from (post-exact-dedup, per the brief).
        sample_size: Documents to sample; the whole corpus if it holds fewer.
        shingle_width: Words per shingle (5, per the brief).
        similarity_threshold: Jaccard similarity a pair must exceed to count (0.8).
        trigger_share: Share of compared pairs above threshold that fires the trigger
            (0.05, per the brief).
        seed: Seed of the sample draw, so the measurement is reproducible.
        example_count: Highest-similarity pairs to keep as evidence in the report.

    Returns:
        The measurement.
    """
    rng = random.Random(seed)
    indices = list(range(len(documents)))
    if len(indices) > sample_size:
        indices = rng.sample(indices, sample_size)
    sample = [documents[i] for i in indices]
    shingle_sets = [shingles(doc, shingle_width) for doc in sample]

    pairs_compared = 0
    above = 0
    best: list[tuple[int, int, float]] = []
    for i in range(len(sample)):
        for j in range(i + 1, len(sample)):
            pairs_compared += 1
            similarity = jaccard(shingle_sets[i], shingle_sets[j])
            if similarity > similarity_threshold:
                above += 1
                best.append((i, j, similarity))
    best.sort(key=lambda item: item[2], reverse=True)

    share = above / pairs_compared if pairs_compared else 0.0
    return NearDuplicateMeasurement(
        sample_size=len(sample),
        pairs_compared=pairs_compared,
        pairs_above_threshold=above,
        share_above_threshold=share,
        threshold=similarity_threshold,
        trigger_fires=share > trigger_share,
        trigger_share=trigger_share,
        example_pairs=best[:example_count],
    )
