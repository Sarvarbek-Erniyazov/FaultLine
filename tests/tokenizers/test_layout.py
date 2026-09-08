"""Joint vocabulary layout invariants (ADR-0003)."""

from __future__ import annotations

from itertools import pairwise

import pytest

from faultline.tokenizers.layout import SPECIAL_TOKENS, SPECIALS_BLOCK, VocabLayout


@pytest.fixture
def layout() -> VocabLayout:
    return VocabLayout.from_sizes(v_text=1000, n_channels=13, n_bins=64, n_time=24)


def test_block_offsets(layout: VocabLayout) -> None:
    assert layout.text_offset == SPECIALS_BLOCK
    assert layout.channel_offset == 32 + 1000
    assert layout.bin_offset == 32 + 1000 + 13
    assert layout.time_offset == 32 + 1000 + 13 + 64
    assert layout.total_size == 32 + 1000 + 13 + 64 + 24


def test_ranges_are_contiguous_and_disjoint(layout: VocabLayout) -> None:
    ranges = list(layout.ranges.values())
    assert ranges[0][0] == 0
    for (_, end), (start, _) in pairwise(ranges):
        assert end == start  # contiguous, therefore disjoint with no holes
    assert ranges[-1][1] == layout.total_size


def test_every_id_decodes_to_exactly_one_block(layout: VocabLayout) -> None:
    seen: dict[tuple[str, int], int] = {}
    for global_id in range(layout.total_size):
        token = layout.decode(global_id)
        key = (token.kind, token.local_id)
        assert key not in seen, f"id {global_id} collides with {seen[key]}"
        seen[key] = global_id
    assert len(seen) == layout.total_size


def test_encode_decode_round_trip(layout: VocabLayout) -> None:
    assert layout.decode(layout.text_id(5)) == layout.decode(layout.text_offset + 5)
    for local in range(layout.n_channels):
        token = layout.decode(layout.channel_id(local))
        assert token.kind == "channel"
        assert token.local_id == local
    for local in range(layout.n_bins):
        token = layout.decode(layout.bin_id(local))
        assert token.kind == "bin"
        assert token.local_id == local
    for local in range(layout.n_time):
        assert layout.decode(layout.time_id(local)).kind == "time"


def test_special_tokens_occupy_the_start(layout: VocabLayout) -> None:
    for index, name in enumerate(SPECIAL_TOKENS):
        assert layout.special_id(name) == index
        token = layout.decode(index)
        assert token.kind == "special"
        assert token.name == name


def test_reserved_specials_have_no_name(layout: VocabLayout) -> None:
    token = layout.decode(SPECIALS_BLOCK - 1)
    assert token.kind == "special"
    assert token.name is None


def test_unknown_special_raises(layout: VocabLayout) -> None:
    with pytest.raises(KeyError):
        layout.special_id("<not-a-token>")


def test_out_of_range_ids_raise(layout: VocabLayout) -> None:
    with pytest.raises(IndexError):
        layout.decode(layout.total_size)
    with pytest.raises(IndexError):
        layout.decode(-1)
    with pytest.raises(IndexError):
        layout.channel_id(layout.n_channels)
    with pytest.raises(IndexError):
        layout.bin_id(-1)


def test_negative_block_sizes_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        VocabLayout(n_text=-1, n_channels=1, n_bins=2)


def test_specials_block_must_fit_the_structural_tokens() -> None:
    with pytest.raises(ValueError, match="cannot hold"):
        VocabLayout(n_text=10, n_channels=1, n_bins=2, n_specials=4)


def test_single_modality_layouts_are_valid() -> None:
    # M1 is telemetry-only and M2 is text-only; both must be expressible so the two
    # tokenizers can be fitted independently and concatenated at M3.
    telemetry_only = VocabLayout.from_sizes(v_text=0, n_channels=13, n_bins=64)
    assert telemetry_only.channel_offset == telemetry_only.text_offset
    assert telemetry_only.total_size == 32 + 13 + 64

    text_only = VocabLayout.from_sizes(v_text=1000, n_channels=0, n_bins=0)
    assert text_only.total_size == 32 + 1000


def test_describe_is_markdown(layout: VocabLayout) -> None:
    described = layout.describe()
    assert described.startswith("| block |")
    for kind in ("special", "text", "channel", "bin", "time"):
        assert kind in described
