"""The joint vocabulary checks: each one passes on a sound input and FAILS on a broken one.

A check that cannot fail measures nothing (docs/INSTRUMENT_AUDIT.md), so every check here
is given a deliberately broken input as well as a sound one.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from faultline.tokenizers.joint import JointVocab
from faultline.tokenizers.joint_check import (
    check_checkpoint_rows,
    check_no_collision,
    check_prefix_decodes_identically,
    check_round_trip,
    check_shard_ids,
    check_shard_prefix,
    check_text_region_full,
    joint_layout,
    m1_layout,
)
from faultline.tokenizers.layout import TEXT_CAPACITY, Token, VocabLayout
from faultline.tokenizers.quantile_bins import QuantileBinTokenizer
from faultline.tokenizers.text_bpe import TextBPETokenizer

CHANNELS = ["wind_speed_ms", "power_pu"]


@pytest.fixture
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(5)
    return pd.DataFrame(
        {"wind_speed_ms": rng.uniform(0, 25, 200), "power_pu": rng.uniform(0, 1, 200)}
    )


@pytest.fixture
def bins(frame: pd.DataFrame) -> QuantileBinTokenizer:
    return QuantileBinTokenizer.fit(frame, CHANNELS, n_bins=8)


@pytest.fixture
def text() -> TextBPETokenizer:
    return TextBPETokenizer.fit(["the wind turbine tripped on low wind"] * 5, vocab_size=270)


def test_the_layouts_agree_and_do_not_collide(bins: QuantileBinTokenizer) -> None:
    assert check_no_collision(joint_layout(bins, 300)).passed
    assert check_prefix_decodes_identically(m1_layout(bins), joint_layout(bins, 300)).passed


def test_a_layout_that_decodes_text_into_the_prefix_fails(bins: QuantileBinTokenizer) -> None:
    class Leaky(VocabLayout):
        def decode(self, global_id: int) -> Token:
            return Token("text", 0) if global_id == 40 else super().decode(global_id)

    assert not check_no_collision(Leaky(n_text=300, n_channels=14, n_bins=8)).passed
    assert not check_prefix_decodes_identically(
        m1_layout(bins), Leaky(n_text=300, n_channels=14, n_bins=8)
    ).passed


def test_a_checkpoint_with_a_renumbered_prefix_fails(tmp_path: Path) -> None:
    good, bad = tmp_path / "a.pt", tmp_path / "b.pt"
    torch.save({"state": {"tokens.weight": torch.zeros(1184, 4)}}, good)
    torch.save({"state": {"backbone.tokens.weight": torch.zeros(1185, 4)}}, bad)
    assert check_checkpoint_rows([good]).passed
    assert not check_checkpoint_rows([good, bad]).passed
    assert not check_checkpoint_rows([]).passed


def test_shard_bytes_that_differ_by_one_id_fail(
    bins: QuantileBinTokenizer, text: TextBPETokenizer, frame: pd.DataFrame
) -> None:
    m1 = JointVocab(m1_layout(bins), bin_tokenizer=bins)
    joint = JointVocab(joint_layout(bins, text.vocab_size), text, bins)
    on_disk = m1.encode_steps(frame)
    assert check_shard_prefix(m1, joint, frame, [], on_disk).passed
    corrupted = on_disk.copy()
    corrupted[17, 1] += 1
    assert not check_shard_prefix(m1, joint, frame, [], corrupted).passed
    assert not check_shard_prefix(m1, joint, frame, [], on_disk[:-1]).passed


def test_a_shard_id_in_the_text_region_fails(tmp_path: Path) -> None:
    good, bad = tmp_path / "a.bin", tmp_path / "b.bin"
    np.array([8, 96, 351], dtype=np.uint16).tofile(good)
    np.array([8, 1184], dtype=np.uint16).tofile(bad)
    assert check_shard_ids([good]).passed
    assert not check_shard_ids([good, bad]).passed


def test_a_text_region_short_of_capacity_fails(
    bins: QuantileBinTokenizer, text: TextBPETokenizer
) -> None:
    # the fixture tokenizer is 270 ids, far short of the 32,768 capacity
    assert text.vocab_size < TEXT_CAPACITY
    check = check_text_region_full(joint_layout(bins, text.vocab_size), text)
    assert not check.passed
    assert "270 ids" in check.detail


def test_the_round_trip_passes_and_a_lossy_text_tokenizer_fails(
    bins: QuantileBinTokenizer, text: TextBPETokenizer, frame: pd.DataFrame
) -> None:
    m1 = JointVocab(m1_layout(bins), bin_tokenizer=bins)
    joint = JointVocab(joint_layout(bins, text.vocab_size), text, bins)
    documents = [" wind < start wind", "the turbine tripped"]
    assert check_round_trip(m1, joint, text, frame.head(4), documents).passed

    class Lossy(TextBPETokenizer):
        def decode(self, ids: list[int]) -> str:
            return super().decode(ids).upper()

    lossy = Lossy.fit(["the wind turbine tripped on low wind"] * 5, vocab_size=270)
    joint_lossy = JointVocab(joint_layout(bins, lossy.vocab_size), lossy, bins)
    assert not check_round_trip(m1, joint_lossy, lossy, frame.head(4), documents).passed
