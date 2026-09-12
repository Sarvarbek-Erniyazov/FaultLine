"""The M2b pre-registered near-duplicate trigger."""

from __future__ import annotations

from faultline.data.text.near_duplicates import jaccard, measure_near_duplicates, shingles


def test_shingles_of_a_short_document_is_the_whole_document() -> None:
    assert shingles("one two", k=5) == frozenset({hash("one two")})


def test_shingles_slides_one_word_at_a_time() -> None:
    result = shingles("a b c d e f", k=5)
    assert len(result) == 2  # "a b c d e" and "b c d e f"


def test_jaccard_of_identical_sets_is_one() -> None:
    s = shingles("the reactor coolant pump tripped today")
    assert jaccard(s, s) == 1.0


def test_jaccard_of_two_empty_sets_is_one_not_undefined() -> None:
    assert jaccard(frozenset(), frozenset()) == 1.0


def test_jaccard_of_disjoint_sets_is_zero() -> None:
    assert (
        jaccard(shingles("alpha beta gamma delta epsilon"), shingles("zeta eta theta iota kappa"))
        == 0.0
    )


def test_no_trigger_on_a_corpus_of_genuinely_distinct_documents() -> None:
    documents = [
        f"event number {i} occurred at facility {i % 7} on day {i % 30} with cause code {i % 11}"
        for i in range(300)
    ]
    result = measure_near_duplicates(documents, sample_size=300, seed=1)
    assert result.sample_size == 300
    assert result.pairs_compared == 300 * 299 // 2
    assert not result.trigger_fires
    assert result.share_above_threshold < result.trigger_share


def test_trigger_fires_when_most_documents_are_near_duplicates() -> None:
    base = "the reactor coolant pump tripped on high vibration at the plant today"
    # near-duplicates: the same sentence with one word changed
    documents = [base.replace("today", f"today number {i}") for i in range(200)]
    result = measure_near_duplicates(documents, sample_size=200, seed=1)
    assert result.trigger_fires
    assert result.share_above_threshold > result.trigger_share
    assert result.example_pairs
    assert result.example_pairs[0][2] > 0.8


def test_sample_size_caps_at_the_corpus_size() -> None:
    documents = [f"document {i}" for i in range(50)]
    result = measure_near_duplicates(documents, sample_size=2000, seed=1)
    assert result.sample_size == 50
    assert result.pairs_compared == 50 * 49 // 2


def test_measurement_is_reproducible_for_a_given_seed() -> None:
    documents = [f"event {i} at site {i % 5}" for i in range(500)]
    first = measure_near_duplicates(documents, sample_size=100, seed=7)
    second = measure_near_duplicates(documents, sample_size=100, seed=7)
    assert first == second
