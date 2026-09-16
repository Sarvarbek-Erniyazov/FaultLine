"""H3' measured behaviourally: the replacement for token-level coverage (audit entry 11)."""

from __future__ import annotations

from collections import Counter

import numpy as np
import pytest
import torch

from faultline.data.text.code_book import every_token_frequent, words
from faultline.evaluation.status_nll import (
    ABSENT,
    FREQUENT,
    RARE,
    WordForm,
    coverage_class,
    paired_effect,
    sequence_nll,
    single_token_word_rate,
    word_forms,
    word_status,
)
from faultline.model.transformer import ModelSpec, TelemetryDecoder
from faultline.tokenizers.text_bpe import TextBPETokenizer

#: Prose in which " wind" and " error" are frequent, " y" and "aw" occur, and "yaw" never does.
PROSE = [" the wind error was high, y-aw and y-aw, an error at the wind farm"] * 40


@pytest.fixture(scope="module")
def tokenizer() -> TextBPETokenizer:
    return TextBPETokenizer.fit(PROSE, vocab_size=300)


def _frequency(tokenizer: TextBPETokenizer) -> np.ndarray:
    counts = np.zeros(tokenizer.vocab_size, dtype=np.int64)
    for text in PROSE:
        for token in tokenizer.encode(text):
            counts[token] += 1
    return counts


def test_a_word_absent_from_the_corpus_is_covered_by_tokens_and_is_not_one_token(
    tokenizer: TextBPETokenizer,
) -> None:
    # the defect of audit entry 11, pinned: every piece of " yaw error" is frequent, and
    # "yaw" never occurs
    frequency = _frequency(tokenizer)
    word_frequency = Counter(w for text in PROSE for w in words(text))
    forms = word_forms("Yaw error", tokenizer.id_of_bytes, tokenizer.encode, word_frequency)
    assert [f.surface for f in forms] == [" yaw", " error"]
    assert word_frequency["yaw"] == 0
    assert not forms[0].in_vocabulary and forms[1].in_vocabulary
    assert single_token_word_rate(forms) == 0.5
    # the old metric reads covered: " y" and "aw" are frequent pieces, as in the real corpus
    assert every_token_frequent(tokenizer.encode(" yaw error"), frequency, 40)


def test_one_token_means_an_exact_vocabulary_entry_not_an_encoder_accident(
    tokenizer: TextBPETokenizer,
) -> None:
    wind = tokenizer.id_of_bytes(b" wind")
    assert wind is not None
    assert tokenizer.decode_bytes([wind]) == b" wind"
    assert tokenizer.id_of_bytes(b" win") != wind
    assert tokenizer.id_of_bytes(b" yaw") is None
    assert tokenizer.id_of_bytes(b"") is None


def test_words_are_letter_chunks_with_their_space_and_digits_are_not_words(
    tokenizer: TextBPETokenizer,
) -> None:
    forms = word_forms("Wind run-up 24h", tokenizer.id_of_bytes, tokenizer.encode, Counter())
    assert [f.surface for f in forms] == [" wind", " run", "up", "h"]


def test_a_string_without_a_word_has_no_rate() -> None:
    assert np.isnan(single_token_word_rate([]))


def test_word_status_reads_the_rarest_word() -> None:
    def form(count: int) -> WordForm:
        return WordForm(surface=" w", in_vocabulary=True, encoded_tokens=1, corpus_count=count)

    assert word_status([form(500), form(100)]) == FREQUENT
    assert word_status([form(500), form(99)]) == RARE
    assert word_status([form(99), form(0)]) == ABSENT


def test_the_four_stage_a_classes() -> None:
    assert coverage_class(True, True) == "covered, both levels"
    assert coverage_class(True, False) == "covered, token level only"
    assert coverage_class(False, True) == "residual, below the word level"
    assert coverage_class(False, False) == "residual, vocabulary-absent"


def _decoder() -> TelemetryDecoder:
    torch.manual_seed(0)
    spec = ModelSpec(name="T", d_model=32, n_layer=2, n_head=4, context=32, vocab_size=50)
    return TelemetryDecoder(spec, fused=False).eval()


def test_sequence_nll_is_the_models_own_next_token_loss_and_padding_changes_nothing() -> None:
    model = _decoder()
    sequences = [[3, 4, 5, 6, 7], [9, 2], [11, 12, 13]]
    batched = sequence_nll(model, [49], sequences, torch.device("cpu"), batch=3)
    for sequence, nll in zip(sequences, batched, strict=True):
        alone = torch.tensor([[49, *sequence]])
        expected = model.loss(alone).item() * len(sequence)
        assert nll.shape == (len(sequence),)
        assert nll.sum() == pytest.approx(expected, rel=1e-5)


def test_a_longer_prefix_conditions_the_first_token() -> None:
    model = _decoder()
    short = sequence_nll(model, [49], [[5, 6]], torch.device("cpu"))[0]
    long = sequence_nll(model, [49, 1, 2], [[5, 6]], torch.device("cpu"))[0]
    assert not np.allclose(short, long)


def test_an_empty_prefix_is_refused() -> None:
    with pytest.raises(ValueError, match="prefix"):
        sequence_nll(_decoder(), [], [[1, 2]], torch.device("cpu"))


def test_the_paired_effect_is_the_mean_difference_inside_its_interval() -> None:
    a = np.array([10.0, 12.0, 8.0, 11.0])
    b = a - np.array([1.0, 2.0, 1.5, 0.5])
    mean, low, high = paired_effect(a, b)
    assert mean == pytest.approx(-1.25)
    assert low <= mean <= high
