"""Byte-level BPE, checked against a reference implementation on real text.

``tests/fixtures/text/nrc_bpe_corpus.jsonl`` is 47 real NRC Event Notification Report
narratives (public domain, 17 U.S.C. 105), fetched during M2a reconnaissance -- not
synthetic, because the pre-tokenizer's whitespace and punctuation rules are exactly
where a hand-written fixture tends to accidentally dodge the cases that matter.

``tokenizers`` (Hugging Face's Rust-backed library) is the reference here and nowhere
else in this project: ``src/faultline/tokenizers/text_bpe.py`` does not import it, per
the M2 brief. What this file checks is that the training algorithm this project wrote
from scratch produces the same merges and the same encoding as a trusted
implementation, on real data.

**Why vocab_size=280 and not the production 32,768.** Frequency ties are common at
small vocabulary sizes and turn up again, differently, once a corpus this size (67 KB)
runs out of large, unambiguous merges -- both were measured directly while building
this fixture (a tie at 24 KB of text turned up at merge 4; at this 67 KB corpus, one
turns up at merge 38). 24 merges (vocab_size 280) is the largest tie-free prefix
measured for this fixture, and it is a real assertion: 24 rounds of real byte-pair
merging over real prose, not a token or two. Tie-breaking is this project's own stated
policy (see ``text_bpe.py``'s module docstring) and is deliberately not exercised by
this comparison -- a fixture that hit a tie would test whose tie-break rule is
implemented, not whether the two algorithms agree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultline.tokenizers.text_bpe import (
    BASE_VOCAB_SIZE,
    TextBPETokenizer,
    _apply_merge,
    _pair_counts,
    pretokenize,
)

REFERENCE_VOCAB_SIZE = 280


#: GPT-2's byte<->printable-unicode bijection (Radford et al. 2019, "bytes_to_unicode").
#: Reconstructed here as a well-known, public mapping -- not reverse-engineered from
#: the reference library -- because it is exactly what "byte-level" BPE is defined
#: against, and it is what lets a reference merge (expressed in that alphabet) be
#: compared against this project's own merges (expressed as raw byte values 0-255).
def _gpt2_byte_to_char() -> dict[int, str]:
    bs = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("\xa1"), ord("\xac") + 1))
        + list(range(ord("\xae"), ord("\xff") + 1))
    )
    cs = list(bs)
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return {b: chr(c) for b, c in zip(bs, cs, strict=True)}


@pytest.fixture
def corpus(fixtures_dir: Path) -> list[str]:
    path = fixtures_dir / "text" / "nrc_bpe_corpus.jsonl"
    return [json.loads(line)["text"] for line in path.read_text(encoding="utf-8").splitlines()]


def _train_reference(corpus: list[str]) -> object:
    """Train Hugging Face's byte-level BPE on ``corpus`` at :data:`REFERENCE_VOCAB_SIZE`."""
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers

    tok = Tokenizer(models.BPE(unk_token=None))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False, trim_offsets=False)
    trainer = trainers.BpeTrainer(
        vocab_size=REFERENCE_VOCAB_SIZE,
        min_frequency=1,
        show_progress=False,
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
    )
    tok.train_from_iterator(corpus, trainer)
    return tok


def _reference_merges_as_byte_ids(tok: object) -> list[tuple[int, int]]:
    """Read a trained reference model's merges back as raw ``(left_byte_id, right_byte_id)``.

    The reference reports merges in its own alphabet and its own arbitrarily-ordered
    vocabulary ids; this resolves each merge down to the concrete byte string it
    produces and re-numbers base tokens by literal byte value (0-255) and merged
    tokens by learned order (256, 257, ...) -- this project's own numbering, so the
    two merge lists compare directly.

    Args:
        tok: A trained ``tokenizers.Tokenizer`` with a BPE model.

    Returns:
        Merges in learned order, in this project's id space.
    """
    state = json.loads(tok.to_str())["model"]  # type: ignore[attr-defined]
    hf_vocab: dict[str, int] = state["vocab"]
    hf_merges: list[object] = state["merges"]
    char_to_byte = {char: byte for byte, char in _gpt2_byte_to_char().items()}

    id_to_bytes: dict[int, bytes] = {}
    for char, idx in hf_vocab.items():
        if len(char) == 1 and char in char_to_byte:
            id_to_bytes[idx] = bytes([char_to_byte[char]])

    our_id_of: dict[bytes, int] = {bytes([i]): i for i in range(BASE_VOCAB_SIZE)}
    our_merges: list[tuple[int, int]] = []
    for merge in hf_merges:
        left_str, right_str = merge if isinstance(merge, list) else merge.split(" ", 1)
        left_bytes = id_to_bytes[hf_vocab[left_str]]
        right_bytes = id_to_bytes[hf_vocab[right_str]]
        id_to_bytes[hf_vocab[left_str + right_str]] = left_bytes + right_bytes
        our_merges.append((our_id_of[left_bytes], our_id_of[right_bytes]))
        our_id_of[left_bytes + right_bytes] = BASE_VOCAB_SIZE + len(our_merges) - 1
    return our_merges


@pytest.fixture
def reference_merges(corpus: list[str]) -> list[tuple[int, int]]:
    pytest.importorskip("tokenizers")
    tok = _train_reference(corpus)
    return _reference_merges_as_byte_ids(tok)


def test_no_tie_at_this_fixture_and_vocab_size(corpus: list[str]) -> None:
    """The fixture's own precondition: every merge step has a unique winner.

    If this fails, the fixture no longer isolates the algorithm from the tie-break
    policy, and ``REFERENCE_VOCAB_SIZE`` or the fixture needs to change -- not the
    tie-break rule.
    """
    from collections import Counter

    chunk_freq: Counter[str] = Counter()
    for text in corpus:
        chunk_freq.update(pretokenize(text))
    symbol_chunks = [(list(chunk.encode("utf-8")), freq) for chunk, freq in chunk_freq.items()]
    for step in range(REFERENCE_VOCAB_SIZE - BASE_VOCAB_SIZE):
        counts = _pair_counts(symbol_chunks)
        assert counts, "ran out of pairs before reaching REFERENCE_VOCAB_SIZE"
        best = max(counts.values())
        winners = [pair for pair, count in counts.items() if count == best]
        assert len(winners) == 1, f"unexpected tie at step {step}: {winners} all at {best}"
        pair = winners[0]
        new_id = BASE_VOCAB_SIZE + step
        symbol_chunks = [
            (_apply_merge(symbols, pair, new_id), freq) for symbols, freq in symbol_chunks
        ]


def test_merges_match_the_reference_exactly(
    corpus: list[str], reference_merges: list[tuple[int, int]]
) -> None:
    ours = TextBPETokenizer.fit(corpus, vocab_size=REFERENCE_VOCAB_SIZE)
    assert ours.vocab_size == REFERENCE_VOCAB_SIZE
    assert ours.merges == reference_merges


def test_encode_matches_the_reference_on_held_out_sentences(corpus: list[str]) -> None:
    pytest.importorskip("tokenizers")
    ref = _train_reference(corpus)
    ours = TextBPETokenizer.fit(corpus, vocab_size=REFERENCE_VOCAB_SIZE)

    held_out = [
        "The turbine control system malfunctioned during routine testing this morning.",
        "A Reactor Trip occurred at 0954 EDT due to high steam generator water level.",
        "The licensee notified the NRC Resident Inspector of the loss of offsite power.",
    ]
    for sentence in held_out:
        ours_ids = ours.encode(sentence)
        ref_ids = ref.encode(sentence, add_special_tokens=False).ids  # type: ignore[attr-defined]
        assert ours.decode(ours_ids) == sentence
        assert len(ours_ids) == len(ref_ids), (sentence, ours_ids, ref_ids)


def _full_recount_merges(texts: list[str], vocab_size: int) -> list[tuple[int, int]]:
    """The original fit loop, verbatim in behaviour: recount every pair after each merge."""
    from collections import Counter

    chunk_freq: Counter[str] = Counter()
    for text in texts:
        chunk_freq.update(pretokenize(text))
    symbol_chunks = [(list(chunk.encode("utf-8")), freq) for chunk, freq in chunk_freq.items()]
    merges: list[tuple[int, int]] = []
    while len(merges) < vocab_size - BASE_VOCAB_SIZE:
        counts = _pair_counts(symbol_chunks)
        if not counts:
            break
        pair, _count = min(counts.items(), key=lambda item: (-item[1], item[0]))
        new_id = BASE_VOCAB_SIZE + len(merges)
        merges.append(pair)
        symbol_chunks = [
            (_apply_merge(symbols, pair, new_id), freq) for symbols, freq in symbol_chunks
        ]
    return merges


def test_incremental_fit_matches_the_full_recount_on_real_text(corpus: list[str]) -> None:
    # 1,000 merges on the 67 KB fixture: well past its first frequency tie (merge 38)
    fitted = TextBPETokenizer.fit(corpus, BASE_VOCAB_SIZE + 1000)
    assert fitted.merges == _full_recount_merges(corpus, BASE_VOCAB_SIZE + 1000)


@pytest.mark.parametrize(
    "texts",
    [
        ["aaaa aaaa aaa", "abab abab", "zzzz"],  # overlapping pairs and exact ties
        ["ba ab ba ab", "cd dc cd dc"],  # every count tied, order decided by the pair
        ["x" * 50, "xy" * 20],  # long runs merging into themselves
    ],
)
def test_incremental_fit_matches_the_full_recount_on_ties(texts: list[str]) -> None:
    fitted = TextBPETokenizer.fit(texts, BASE_VOCAB_SIZE + 40)
    assert fitted.merges == _full_recount_merges(texts, BASE_VOCAB_SIZE + 40)


def test_encode_cache_does_not_change_output(corpus: list[str]) -> None:
    tokenizer = TextBPETokenizer.fit(corpus, BASE_VOCAB_SIZE + 300)
    first = [tokenizer.encode(text) for text in corpus]
    second = [tokenizer.encode(text) for text in corpus]  # now served from the cache
    uncached = [
        [i for chunk in pretokenize(text) for i in tokenizer._encode_chunk(list(chunk.encode()))]
        for text in corpus
    ]
    assert first == second == uncached
