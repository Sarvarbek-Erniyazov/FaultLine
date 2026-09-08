"""The joint vocabulary: one id space over both modalities."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from faultline.tokenizers.joint import JointVocab
from faultline.tokenizers.layout import VocabLayout
from faultline.tokenizers.quantile_bins import QuantileBinTokenizer
from faultline.tokenizers.text_bpe import TextBPETokenizer

CHANNELS = ["wind_speed_ms", "power_kw"]


class FakeTextTokenizer:
    """Stands in for the M2 byte-level BPE tokenizer."""

    def __init__(self, vocab_size: int = 100) -> None:
        self.vocab_size = vocab_size

    def encode(self, text: str) -> list[int]:
        return [ord(char) % self.vocab_size for char in text]

    def decode(self, ids: list[int]) -> str:
        return "".join(chr(value) for value in ids)


@pytest.fixture
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    return pd.DataFrame(
        {
            "wind_speed_ms": rng.uniform(0, 25, 500),
            "power_kw": rng.uniform(0, 2050, 500),
        }
    )


@pytest.fixture
def bin_tokenizer(frame: pd.DataFrame) -> QuantileBinTokenizer:
    return QuantileBinTokenizer.fit(frame, CHANNELS, n_bins=8)


@pytest.fixture
def vocab(bin_tokenizer: QuantileBinTokenizer) -> JointVocab:
    layout = VocabLayout.from_sizes(v_text=100, n_channels=len(CHANNELS), n_bins=8)
    return JointVocab(layout, FakeTextTokenizer(100), bin_tokenizer)


def test_sizes_sum_correctly(vocab: JointVocab) -> None:
    assert vocab.size == 32 + 100 + 2 + 8
    assert vocab.size == vocab.layout.total_size


def test_layout_and_tokenizer_must_agree(bin_tokenizer: QuantileBinTokenizer) -> None:
    with pytest.raises(ValueError, match="bins"):
        JointVocab(VocabLayout.from_sizes(100, 2, 64), bin_tokenizer=bin_tokenizer)
    with pytest.raises(ValueError, match="channels"):
        JointVocab(VocabLayout.from_sizes(100, 5, 8), bin_tokenizer=bin_tokenizer)


def test_encode_text_is_wrapped_and_in_range(vocab: JointVocab) -> None:
    ids = vocab.encode_text("abc")
    assert ids[0] == vocab.special("<txt>")
    assert ids[-1] == vocab.special("</txt>")
    for value in ids[1:-1]:
        assert vocab.decode(value).kind == "text"


def test_encode_text_unwrapped(vocab: JointVocab) -> None:
    assert len(vocab.encode_text("abc", wrap=False)) == 3


def test_encode_telemetry_interleaves_channel_and_bin(
    vocab: JointVocab, frame: pd.DataFrame
) -> None:
    window = frame.head(4)
    ids = vocab.encode_telemetry(window)

    assert ids[0] == vocab.special("<tel>")
    assert ids[-1] == vocab.special("</tel>")
    body = ids[1:-1]
    assert len(body) == len(window) * len(CHANNELS) * 2

    kinds = [vocab.decode(value).kind for value in body]
    assert kinds[0::2] == ["channel"] * (len(body) // 2)
    assert all(kind in ("bin", "special") for kind in kinds[1::2])


def test_channel_tokens_follow_the_fitted_order(vocab: JointVocab, frame: pd.DataFrame) -> None:
    body = vocab.encode_telemetry(frame.head(1))[1:-1]
    channels = [vocab.decode(value).local_id for value in body[0::2]]
    assert channels == [0, 1]


def test_missing_values_become_the_nan_token(vocab: JointVocab, frame: pd.DataFrame) -> None:
    window = frame.head(2).copy()
    window.loc[window.index[0], "wind_speed_ms"] = np.nan
    body = vocab.encode_telemetry(window)[1:-1]
    assert body[1] == vocab.special("<nan>")
    assert vocab.decode(body[1]).name == "<nan>"


def test_channel_subset_encoding(vocab: JointVocab, frame: pd.DataFrame) -> None:
    body = vocab.encode_telemetry(frame.head(3), channels=["power_kw"])[1:-1]
    assert len(body) == 3 * 2
    assert {vocab.decode(value).local_id for value in body[0::2]} == {1}


def test_every_id_decodes_to_one_pair(vocab: JointVocab) -> None:
    pairs = {(vocab.decode(i).kind, vocab.decode(i).local_id) for i in range(vocab.size)}
    assert len(pairs) == vocab.size


def test_text_encoding_requires_a_text_tokenizer(bin_tokenizer: QuantileBinTokenizer) -> None:
    # M1 is telemetry-only: asking for text must fail loudly, not return nothing.
    vocab = JointVocab(VocabLayout.from_sizes(0, 2, 8), bin_tokenizer=bin_tokenizer)
    with pytest.raises(RuntimeError, match="M2"):
        vocab.encode_text("hello")


def test_telemetry_encoding_requires_a_bin_tokenizer() -> None:
    vocab = JointVocab(VocabLayout.from_sizes(100, 0, 0), FakeTextTokenizer(100))
    with pytest.raises(RuntimeError, match="bin tokenizer"):
        vocab.encode_telemetry(pd.DataFrame())


def test_describe_reports_both_sides(vocab: JointVocab) -> None:
    described = vocab.describe()
    assert "text tokenizer: bound" in described
    assert "bin tokenizer: bound" in described


def test_text_bpe_stub_is_honest_about_being_a_stub() -> None:
    tokenizer = TextBPETokenizer()
    for call in (
        lambda: tokenizer.train(["a"]),
        lambda: tokenizer.encode("a"),
        lambda: tokenizer.decode([1]),
    ):
        with pytest.raises(NotImplementedError, match="m2"):
            call()
