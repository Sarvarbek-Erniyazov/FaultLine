"""Joint vocabulary layout invariants (ADR-0003)."""

from __future__ import annotations

from itertools import pairwise

import pytest

from faultline.tokenizers.layout import (
    BIN_CAPACITY,
    BIN_OFFSET,
    CHANNEL_CAPACITY,
    CHANNEL_OFFSET,
    SPECIAL_TOKENS,
    SPECIALS_CAPACITY,
    TELEMETRY_PREFIX_SIZE,
    TEXT_CAPACITY,
    TEXT_OFFSET,
    TIME_CAPACITY,
    TIME_OFFSET,
    VocabLayout,
)


@pytest.fixture
def layout() -> VocabLayout:
    return VocabLayout.from_sizes(v_text=1000, n_channels=13, n_bins=64, n_time=24)


def test_block_offsets_are_the_values_adr_0003_states(layout: VocabLayout) -> None:
    assert (SPECIALS_CAPACITY, CHANNEL_OFFSET, BIN_OFFSET, TIME_OFFSET, TEXT_OFFSET) == (
        32,
        32,
        96,
        1120,
        1184,
    )
    assert (CHANNEL_CAPACITY, BIN_CAPACITY, TIME_CAPACITY, TEXT_CAPACITY) == (64, 1024, 64, 32768)
    assert layout.channel_offset == 32
    assert layout.bin_offset == 96
    assert layout.time_offset == 1120
    assert layout.text_offset == 1184
    assert layout.total_size == 1184 + 1000


def test_offsets_are_invariant_to_the_number_of_channels_and_bins() -> None:
    # The whole point of fixed capacities: an M1 shard tokenized with 13 channels and
    # 64 bins keeps its identifiers when a later fit uses 40 channels and 256 bins.
    small = VocabLayout.from_sizes(v_text=0, n_channels=13, n_bins=64)
    large = VocabLayout.from_sizes(v_text=1000, n_channels=40, n_bins=256, n_time=64)
    for attribute in ("channel_offset", "bin_offset", "time_offset", "text_offset"):
        assert getattr(small, attribute) == getattr(large, attribute)
    assert small.channel_id(5) == large.channel_id(5)
    assert small.bin_id(63) == large.bin_id(63)


def test_the_telemetry_prefix_is_the_whole_m1_vocabulary() -> None:
    telemetry_only = VocabLayout.from_sizes(v_text=0, n_channels=13, n_bins=64, n_time=24)
    assert telemetry_only.total_size == TELEMETRY_PREFIX_SIZE == 1184
    # Adding text at M2 extends the space upward and moves nothing.
    joint = VocabLayout.from_sizes(v_text=16000, n_channels=13, n_bins=64, n_time=24)
    assert joint.total_size == TELEMETRY_PREFIX_SIZE + 16000
    assert joint.ranges["text"][0] == TELEMETRY_PREFIX_SIZE


def test_capacity_overflow_raises() -> None:
    for kwargs in (
        {"v_text": 10, "n_channels": CHANNEL_CAPACITY + 1, "n_bins": 8},
        {"v_text": 10, "n_channels": 4, "n_bins": BIN_CAPACITY + 1},
        {"v_text": 10, "n_channels": 4, "n_bins": 8, "n_time": TIME_CAPACITY + 1},
        {"v_text": TEXT_CAPACITY + 1, "n_channels": 4, "n_bins": 8},
    ):
        with pytest.raises(ValueError, match="exceeds the fixed"):
            VocabLayout.from_sizes(**kwargs)  # type: ignore[arg-type]


def test_exactly_full_blocks_are_allowed() -> None:
    full = VocabLayout.from_sizes(
        v_text=TEXT_CAPACITY,
        n_channels=CHANNEL_CAPACITY,
        n_bins=BIN_CAPACITY,
        n_time=TIME_CAPACITY,
    )
    assert full.total_size == TELEMETRY_PREFIX_SIZE + TEXT_CAPACITY
    assert full.channel_id(CHANNEL_CAPACITY - 1) == BIN_OFFSET - 1


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


def test_reserved_slots_decode_to_their_block(layout: VocabLayout) -> None:
    # A slot past the fitted count is reserved headroom, not a hole: it decodes, and
    # it is not encodable.
    reserved = layout.channel_offset + layout.n_channels
    token = layout.decode(reserved)
    assert token.kind == "channel"
    assert token.local_id == layout.n_channels
    assert token.name is None
    with pytest.raises(IndexError, match="in use"):
        layout.channel_id(layout.n_channels)


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
    token = layout.decode(SPECIALS_CAPACITY - 1)
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


def test_single_modality_layouts_are_valid() -> None:
    # M1 is telemetry-only and M2 is text-only; both must be expressible so the two
    # tokenizers can be fitted independently and concatenated at M3.
    telemetry_only = VocabLayout.from_sizes(v_text=0, n_channels=13, n_bins=64)
    assert telemetry_only.total_size == TELEMETRY_PREFIX_SIZE
    assert telemetry_only.ranges["text"] == (TEXT_OFFSET, TEXT_OFFSET)

    text_only = VocabLayout.from_sizes(v_text=1000, n_channels=0, n_bins=0)
    assert text_only.total_size == TELEMETRY_PREFIX_SIZE + 1000
    # Even with no telemetry fitted, the telemetry blocks keep their identifiers.
    assert text_only.text_offset == TEXT_OFFSET


def test_describe_is_markdown_and_shows_capacity_against_use(layout: VocabLayout) -> None:
    described = layout.describe()
    assert described.startswith("| block |")
    assert "capacity" in described
    assert "in use" in described
    for kind in ("special", "text", "channel", "bin", "time"):
        assert kind in described
    # the bin row: first id 96, last reserved id 1119, capacity 1024, 64 in use
    assert "| bin | 96 | 1,119 | 1,024 | 64 |" in described
