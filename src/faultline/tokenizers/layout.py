"""The joint vocabulary layout (ADR-0003).

One decoder reads both modalities, so both must live in one identifier space. That
space is partitioned into blocks of **fixed capacity**, in this order::

    specials  [0, 32)          channel  [32, 96)        bin  [96, 1120)
    time      [1120, 1184)     text     [1184, 1184 + 32768)

Every offset in that table is derived from the *capacities* above and never from the
number of channels, bins or text tokens actually in use. A layout fitted with 13
channels and one fitted with 40 put the bin block at the same identifier, so a shard
tokenized at M1 is still readable at M3 -- the telemetry blocks are a stable prefix
of the joint vocabulary, and text, the block whose size is not known until M2, is
last precisely because it is the only one allowed to grow.

Unused slots inside a block are reserved, not free: they decode to their block with
no name, exactly as the spare specials always have. Asking for a local identifier
beyond the number in use is an error, because that is a fitting mistake rather than
a spare slot.

Sharing one bin range across every channel keeps the used vocabulary small; the
channel is recovered from the channel token that immediately precedes each bin
token. The rejected alternative -- ``N_channels x N_bins`` distinct bin identifiers
-- is recorded in ADR-0003 and stays on the table for M3 if channel conditioning
proves too weak.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from faultline.data.common.report import table

TokenKind = Literal["special", "text", "channel", "bin", "time"]

#: Structural tokens, in identifier order. Positions are part of the format.
SPECIAL_TOKENS: tuple[str, ...] = (
    "<pad>",
    "<bos>",
    "<eos>",
    "<unk>",
    "<txt>",
    "</txt>",
    "<tel>",
    "</tel>",
    "<sep>",
    "<nan>",
    "<mask>",
)

# -- fixed block capacities (ADR-0003 v2) ----------------------------------------------
#
# These five numbers, and the order of the block list below, are the format. Changing
# any of them after M1 invalidates every checkpoint and every tokenized shard, so a
# change supersedes ADR-0003 rather than editing a constant.

#: Structural tokens plus reserved slots for structural tokens added later.
SPECIALS_CAPACITY = 32
#: Canonical SCADA channels. 13 are defined today; the headroom covers channels a
#: later site publishes that the current canonical list does not carry.
CHANNEL_CAPACITY = 64
#: Quantile bins, shared across channels. 64 are configured today; the headroom
#: covers a finer binning without moving the blocks after it.
BIN_CAPACITY = 1024
#: Reserved time markers.
TIME_CAPACITY = 64
#: Byte-level BPE text tokens. Sized at M0 so the M2 tokenizer can be trained to any
#: size up to this without renumbering telemetry.
TEXT_CAPACITY = 32768

#: Blocks in identifier order. Structure and telemetry first, text last.
BLOCK_ORDER: tuple[TokenKind, ...] = ("special", "channel", "bin", "time", "text")

#: Capacity of every block, keyed by kind.
CAPACITIES: dict[TokenKind, int] = {
    "special": SPECIALS_CAPACITY,
    "channel": CHANNEL_CAPACITY,
    "bin": BIN_CAPACITY,
    "time": TIME_CAPACITY,
    "text": TEXT_CAPACITY,
}

#: First identifier of each block, accumulated from the capacities above.
CHANNEL_OFFSET = SPECIALS_CAPACITY
BIN_OFFSET = CHANNEL_OFFSET + CHANNEL_CAPACITY
TIME_OFFSET = BIN_OFFSET + BIN_CAPACITY
TEXT_OFFSET = TIME_OFFSET + TIME_CAPACITY

#: Size of the block prefix carrying structure and telemetry. Identifiers below this
#: are fixed for the life of the project: an M1 telemetry-only vocabulary is exactly
#: this prefix, and M3 extends it with text rather than renumbering it.
TELEMETRY_PREFIX_SIZE = TEXT_OFFSET

if len(SPECIAL_TOKENS) > SPECIALS_CAPACITY:  # pragma: no cover - a coding error, not input
    raise ValueError(
        f"{len(SPECIAL_TOKENS)} structural tokens do not fit a specials block of "
        f"{SPECIALS_CAPACITY}"
    )


@dataclass(frozen=True)
class Token:
    """One decoded identifier.

    Attributes:
        kind: Which block the identifier fell in.
        local_id: Index within that block.
        name: Token name for specials, otherwise ``None``.
    """

    kind: TokenKind
    local_id: int
    name: str | None = None


@dataclass(frozen=True)
class VocabLayout:
    """How much of each fixed-capacity block a fitted vocabulary uses.

    The block offsets are module constants; this object records only how many
    identifiers in each block are in use, which is what bounds encoding and what the
    reports have to state.

    Attributes:
        n_text: Number of text BPE tokens in use.
        n_channels: Number of canonical telemetry channels in use.
        n_bins: Number of quantile bins in use, shared across channels.
        n_time: Number of time-marker tokens in use.
    """

    n_text: int
    n_channels: int
    n_bins: int
    n_time: int = 0

    def __post_init__(self) -> None:
        """Validate that every block size fits its fixed capacity.

        Raises:
            ValueError: If a block size is negative or exceeds its capacity. An
                overflow is fatal rather than a quiet resize, because resizing a
                block moves every block after it.
        """
        checks: tuple[tuple[str, TokenKind, int], ...] = (
            ("n_channels", "channel", self.n_channels),
            ("n_bins", "bin", self.n_bins),
            ("n_time", "time", self.n_time),
            ("n_text", "text", self.n_text),
        )
        for name, kind, size in checks:
            if size < 0:
                raise ValueError(f"{name} must be non-negative, got {size}")
            capacity = CAPACITIES[kind]
            if size > capacity:
                raise ValueError(
                    f"{name}={size} exceeds the fixed {kind} capacity of {capacity}; "
                    "raising a capacity moves every later block and invalidates every "
                    "checkpoint, so it supersedes ADR-0003 rather than editing a constant"
                )

    @classmethod
    def from_sizes(cls, v_text: int, n_channels: int, n_bins: int, n_time: int = 0) -> VocabLayout:
        """Build a layout from the four block sizes.

        Args:
            v_text: Text BPE vocabulary size.
            n_channels: Number of canonical channels.
            n_bins: Number of quantile bins per channel.
            n_time: Number of reserved time markers.

        Returns:
            The corresponding layout.
        """
        return cls(n_text=v_text, n_channels=n_channels, n_bins=n_bins, n_time=n_time)

    # -- offsets ------------------------------------------------------------------
    #
    # Every one of these is a constant. They stay properties so that callers keep
    # reading offsets from the layout instead of hardcoding them.

    @property
    def n_specials(self) -> int:
        """Capacity of the specials block."""
        return SPECIALS_CAPACITY

    @property
    def channel_offset(self) -> int:
        """First identifier of the channel block."""
        return CHANNEL_OFFSET

    @property
    def bin_offset(self) -> int:
        """First identifier of the bin block."""
        return BIN_OFFSET

    @property
    def time_offset(self) -> int:
        """First identifier of the time-marker block."""
        return TIME_OFFSET

    @property
    def text_offset(self) -> int:
        """First identifier of the text block."""
        return TEXT_OFFSET

    @property
    def total_size(self) -> int:
        """Number of identifiers allocated: the fixed prefix plus the text in use.

        Text is the last block, so a telemetry-only vocabulary is exactly
        :data:`TELEMETRY_PREFIX_SIZE` and grows at M2 without renumbering anything.
        """
        return TEXT_OFFSET + self.n_text

    @property
    def counts(self) -> dict[TokenKind, int]:
        """Number of identifiers in use per block."""
        return {
            "special": len(SPECIAL_TOKENS),
            "channel": self.n_channels,
            "bin": self.n_bins,
            "time": self.n_time,
            "text": self.n_text,
        }

    @property
    def ranges(self) -> dict[TokenKind, tuple[int, int]]:
        """Half-open ``[start, end)`` identifier range of every block.

        The four fixed blocks span their whole capacity, reserved slots included.
        The text block, being last and open-ended, spans only what is allocated.
        """
        return {
            "special": (0, CHANNEL_OFFSET),
            "channel": (CHANNEL_OFFSET, BIN_OFFSET),
            "bin": (BIN_OFFSET, TIME_OFFSET),
            "time": (TIME_OFFSET, TEXT_OFFSET),
            "text": (TEXT_OFFSET, self.total_size),
        }

    # -- encoding -----------------------------------------------------------------

    def special_id(self, name: str) -> int:
        """Return the identifier of a structural token.

        Args:
            name: Token name, for example ``<bos>``.

        Returns:
            Its global identifier.

        Raises:
            KeyError: If the name is not a structural token.
        """
        try:
            return SPECIAL_TOKENS.index(name)
        except ValueError as exc:
            raise KeyError(f"unknown special token {name!r}") from exc

    def _shift(self, kind: TokenKind, local_id: int) -> int:
        """Map a local identifier into the global space.

        Bounded by the number of identifiers *in use*, not by the block capacity: a
        reserved slot is not an encodable token, and reaching one means the caller
        and the fitted tokenizer disagree.

        Args:
            kind: Target block.
            local_id: Index within the block.

        Returns:
            The global identifier.

        Raises:
            IndexError: If the local identifier is outside the block's used range.
        """
        used = self.counts[kind]
        if not 0 <= local_id < used:
            raise IndexError(f"{kind} id {local_id} outside the {used} in use")
        return self.ranges[kind][0] + local_id

    def text_id(self, local_id: int) -> int:
        """Map a text BPE identifier into the joint space.

        Args:
            local_id: Identifier within the text tokenizer.

        Returns:
            The global identifier.
        """
        return self._shift("text", local_id)

    def channel_id(self, local_id: int) -> int:
        """Map a channel index into the joint space.

        Args:
            local_id: Index of the channel in the canonical channel list.

        Returns:
            The global identifier.
        """
        return self._shift("channel", local_id)

    def bin_id(self, local_id: int) -> int:
        """Map a quantile bin index into the joint space.

        Args:
            local_id: Bin index within a channel.

        Returns:
            The global identifier.
        """
        return self._shift("bin", local_id)

    def time_id(self, local_id: int) -> int:
        """Map a time-marker index into the joint space.

        Args:
            local_id: Index within the time-marker block.

        Returns:
            The global identifier.
        """
        return self._shift("time", local_id)

    # -- decoding -----------------------------------------------------------------

    def decode(self, global_id: int) -> Token:
        """Resolve a global identifier to its block and local index.

        An identifier landing on a reserved slot decodes to its block with no name,
        the way a spare specials slot always has: that is part of the format, not an
        error.

        Args:
            global_id: Identifier in the joint vocabulary.

        Returns:
            The decoded token.

        Raises:
            IndexError: If the identifier is outside the allocated vocabulary.
        """
        if not 0 <= global_id < self.total_size:
            raise IndexError(f"id {global_id} outside vocabulary of size {self.total_size}")
        for kind, (start, end) in self.ranges.items():
            if start <= global_id < end:
                local = global_id - start
                name = (
                    SPECIAL_TOKENS[local]
                    if kind == "special" and local < len(SPECIAL_TOKENS)
                    else None
                )
                return Token(kind=kind, local_id=local, name=name)
        raise IndexError(f"id {global_id} fell in no block; layout is inconsistent")

    def describe(self) -> str:
        """Render the layout as a Markdown table for reports and cards.

        Both the reserved extent and the number in use are shown, because the gap
        between them is exactly the headroom that keeps the offsets stable.

        Returns:
            A Markdown table with one row per block.
        """
        rows = [
            (
                kind,
                self.ranges[kind][0],
                self.ranges[kind][0] + CAPACITIES[kind] - 1,
                CAPACITIES[kind],
                self.counts[kind],
            )
            for kind in BLOCK_ORDER
        ]
        return table(["block", "first id", "last reserved id", "capacity", "in use"], rows)
