"""The joint vocabulary: one id space over both modalities."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from faultline.tokenizers.joint import JointVocab
from faultline.tokenizers.layout import TELEMETRY_PREFIX_SIZE, VocabLayout
from faultline.tokenizers.quantile_bins import QuantileBinTokenizer
from faultline.tokenizers.text_bpe import TextBPETokenizer

CHANNELS = ["wind_speed_ms", "power_pu"]


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
            "power_pu": rng.uniform(0, 2050, 500),
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
    # ADR-0003 v2: the telemetry blocks are a fixed-capacity prefix, so the size
    # depends on the text vocabulary alone -- not on how many channels or bins the
    # bin tokenizer happened to fit.
    assert vocab.size == TELEMETRY_PREFIX_SIZE + 100
    assert vocab.size == vocab.layout.total_size


def test_layout_and_tokenizer_must_agree(bin_tokenizer: QuantileBinTokenizer) -> None:
    with pytest.raises(ValueError, match="bins"):
        JointVocab(VocabLayout.from_sizes(100, 2, 64), bin_tokenizer=bin_tokenizer)
    # power_pu is canonical channel 1, so a layout of one channel identifier cannot hold it
    with pytest.raises(ValueError, match="channel identifiers"):
        JointVocab(VocabLayout.from_sizes(100, 1, 8), bin_tokenizer=bin_tokenizer)
    # a layout with room to spare is fine: channel identifiers are canonical positions
    JointVocab(VocabLayout.from_sizes(100, 14, 8), bin_tokenizer=bin_tokenizer)


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


def test_channel_tokens_are_canonical_positions_not_the_fitted_order(frame: pd.DataFrame) -> None:
    # ADR-0003: the canonical channel list fixes channel identifiers. A tokenizer fitted in
    # another order must not renumber them (the M0 encoder took the tokenizer's position).
    reordered = QuantileBinTokenizer.fit(frame, ["power_pu", "wind_speed_ms"], n_bins=8)
    vocab = JointVocab(VocabLayout.from_sizes(0, 2, 8), bin_tokenizer=reordered)
    body = vocab.encode_telemetry(frame.head(1))[1:-1]
    channels = [vocab.decode(value).local_id for value in body[0::2]]
    assert channels == [1, 0]  # power_pu is canonical 1, wind_speed_ms canonical 0


def test_the_fixed_order_stream_is_a_delimiter_and_one_bin_token_a_channel(
    vocab: JointVocab, frame: pd.DataFrame
) -> None:
    window = frame.head(5).copy()
    window.loc[window.index[2], "power_pu"] = np.nan
    steps = vocab.encode_steps(window)
    assert steps.dtype == np.uint16
    assert steps.shape == (5, 1 + len(CHANNELS))
    assert (steps[:, 0] == vocab.special("<sep>")).all()
    # no channel token anywhere: position in the step is the channel
    kinds = {vocab.decode(int(value)).kind for value in steps[:, 1:].ravel()}
    assert kinds <= {"bin", "special"}
    assert steps[2, 2] == vocab.special("<nan>")
    # the same bins the tokenizer assigns
    assert vocab.bin_tokenizer is not None
    expected = vocab.bin_tokenizer.transform(window.head(1))[0]
    assert [vocab.decode(int(v)).local_id for v in steps[0, 1:]] == list(expected)


def test_a_masked_channel_is_nan_whatever_its_value(vocab: JointVocab, frame: pd.DataFrame) -> None:
    steps = vocab.encode_steps(frame.head(3), masked=["power_pu"])
    assert (steps[:, 2] == vocab.special("<nan>")).all()
    assert (steps[:, 1] != vocab.special("<nan>")).all()
    with pytest.raises(KeyError, match="not fitted"):
        vocab.encode_steps(frame.head(3), masked=["wind_direction_deg"])


def test_missing_values_become_the_nan_token(vocab: JointVocab, frame: pd.DataFrame) -> None:
    window = frame.head(2).copy()
    window.loc[window.index[0], "wind_speed_ms"] = np.nan
    body = vocab.encode_telemetry(window)[1:-1]
    assert body[1] == vocab.special("<nan>")
    assert vocab.decode(body[1]).name == "<nan>"


def test_channel_subset_encoding(vocab: JointVocab, frame: pd.DataFrame) -> None:
    body = vocab.encode_telemetry(frame.head(3), channels=["power_pu"])[1:-1]
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
