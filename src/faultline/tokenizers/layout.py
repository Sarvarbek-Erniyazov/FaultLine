"""The joint vocabulary layout (ADR-0003).

One decoder reads both modalities, so both must live in one identifier space. The
space is partitioned into contiguous, disjoint ranges:

``[0, 32)`` specials, ``[32, 32 + V_text)`` text BPE, then channel identifiers, then
bin identifiers shared across channels, then reserved time markers.

Sharing one bin range across every channel keeps the vocabulary small; the channel
is recovered from the channel token that immediately precedes each bin token. The
rejected alternative -- ``N_channels x N_bins`` distinct bin identifiers -- is
recorded in ADR-0003 and stays on the table for M3 if channel conditioning proves
too weak.

Because the ranges are laid out by size and not interleaved, the M1 telemetry
tokenizer and the M2 text tokenizer are fitted independently against local
identifiers and concatenated at M3 without retokenizing anything.
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

#: Size of the reserved specials block. Unused slots are padding for future
#: structural tokens, so adding one never shifts the text or telemetry ranges.
SPECIALS_BLOCK = 32


@dataclass(frozen=True)
class Token:
    """One decoded identifier.

    Attributes:
        kind: Which range the identifier fell in.
        local_id: Index within that range.
        name: Token name for specials, otherwise ``None``.
    """

    kind: TokenKind
    local_id: int
    name: str | None = None


@dataclass(frozen=True)
class VocabLayout:
    """Sizes and offsets of every block in the joint vocabulary.

    Attributes:
        n_text: Number of text BPE tokens.
        n_channels: Number of canonical telemetry channels.
        n_bins: Number of quantile bins shared across channels.
        n_time: Number of reserved time-marker tokens.
        n_specials: Size of the specials block.
    """

    n_text: int
    n_channels: int
    n_bins: int
    n_time: int = 0
    n_specials: int = SPECIALS_BLOCK

    def __post_init__(self) -> None:
        """Validate that the layout is well formed.

        Raises:
            ValueError: If any block size is negative, or the specials block is too
                small to hold the structural tokens.
        """
        if self.n_specials < len(SPECIAL_TOKENS):
            raise ValueError(
                f"specials block of {self.n_specials} cannot hold {len(SPECIAL_TOKENS)} tokens"
            )
        for name, size in (
            ("n_text", self.n_text),
            ("n_channels", self.n_channels),
            ("n_bins", self.n_bins),
            ("n_time", self.n_time),
        ):
            if size < 0:
                raise ValueError(f"{name} must be non-negative, got {size}")

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

    @property
    def text_offset(self) -> int:
        """First identifier of the text block."""
        return self.n_specials

    @property
    def channel_offset(self) -> int:
        """First identifier of the channel block."""
        return self.text_offset + self.n_text

    @property
    def bin_offset(self) -> int:
        """First identifier of the bin block."""
        return self.channel_offset + self.n_channels

    @property
    def time_offset(self) -> int:
        """First identifier of the time-marker block."""
        return self.bin_offset + self.n_bins

    @property
    def total_size(self) -> int:
        """Total number of identifiers in the joint vocabulary."""
        return self.time_offset + self.n_time

    @property
    def ranges(self) -> dict[TokenKind, tuple[int, int]]:
        """Half-open ``[start, end)`` identifier range of every block."""
        return {
            "special": (0, self.n_specials),
            "text": (self.text_offset, self.channel_offset),
            "channel": (self.channel_offset, self.bin_offset),
            "bin": (self.bin_offset, self.time_offset),
            "time": (self.time_offset, self.total_size),
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

        Args:
            kind: Target block.
            local_id: Index within the block.

        Returns:
            The global identifier.

        Raises:
            IndexError: If the local identifier is outside the block.
        """
        start, end = self.ranges[kind]
        if not 0 <= local_id < end - start:
            raise IndexError(f"{kind} id {local_id} outside block of size {end - start}")
        return start + local_id

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

        Args:
            global_id: Identifier in the joint vocabulary.

        Returns:
            The decoded token.

        Raises:
            IndexError: If the identifier is outside the vocabulary.
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

        Returns:
            A Markdown table with one row per block.
        """
        rows = [
            (kind, start, end - 1 if end > start else start, end - start)
            for kind, (start, end) in self.ranges.items()
        ]
        return table(["block", "first id", "last id", "size"], rows)
