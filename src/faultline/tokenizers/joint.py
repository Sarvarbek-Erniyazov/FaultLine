"""The joint vocabulary: one identifier space over text and telemetry.

``JointVocab`` is the only place that knows how the two modalities are laid out
next to each other. Either side may be absent: at M1 there is a bin tokenizer and
no text tokenizer, at M2 the reverse, and at M3 both. Encoding a modality that has
no tokenizer is an error rather than a silent no-op.

Telemetry has two encodings:

* :meth:`JointVocab.encode_steps`, the **fixed-order stream** M1 trains on: each step is
  ``<sep>`` followed by one bin token per channel, in the tokenizer's fitted order -- the
  core set in identifier order. No channel token is emitted: a bin token's position in its
  step says which channel it is, so a step of twelve channels costs thirteen tokens.
* :meth:`JointVocab.encode_telemetry`, ``<tel> (channel, bin) ... </tel>``, which carries
  the channel token before each bin token. It is kept for the variable-set ablation over
  extended channels, where a step holds a varying set of channels and position can no
  longer say which is which; the channel block stays allocated and reserved for it
  (ADR-0003). A channel token's identifier is the channel's position in the canonical
  list (``schemas.CHANNEL_NAMES``), never its position in a tokenizer.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import numpy as np
import pandas as pd

from faultline.data.telemetry.schemas import CHANNEL_NAMES
from faultline.tokenizers.layout import Token, VocabLayout
from faultline.tokenizers.quantile_bins import MISSING_BIN, QuantileBinTokenizer


class TextTokenizer(Protocol):
    """Minimal interface the joint vocabulary needs from a text tokenizer."""

    def encode(self, text: str) -> list[int]:
        """Encode text into local text identifiers.

        Args:
            text: Input string.

        Returns:
            Local identifiers within the text block.
        """
        ...

    def decode(self, ids: list[int]) -> str:
        """Decode local text identifiers back into a string.

        Args:
            ids: Local identifiers within the text block.

        Returns:
            The decoded string.
        """
        ...


class JointVocab:
    """Encodes both modalities into one identifier space.

    Attributes:
        layout: Block sizes and offsets.
        text_tokenizer: Text tokenizer, or ``None`` before M2.
        bin_tokenizer: Quantile bin tokenizer, or ``None`` when text-only.
    """

    def __init__(
        self,
        layout: VocabLayout,
        text_tokenizer: TextTokenizer | None = None,
        bin_tokenizer: QuantileBinTokenizer | None = None,
    ) -> None:
        """Bind a layout to the available tokenizers.

        Args:
            layout: Vocabulary layout.
            text_tokenizer: Text tokenizer, if one has been trained.
            bin_tokenizer: Quantile bin tokenizer, if one has been fitted.

        Raises:
            ValueError: If a tokenizer disagrees with the layout it is bound to.
        """
        if bin_tokenizer is not None:
            if bin_tokenizer.n_bins != layout.n_bins:
                raise ValueError(
                    f"bin tokenizer has {bin_tokenizer.n_bins} bins, layout expects {layout.n_bins}"
                )
            unknown = [name for name in bin_tokenizer.channels if name not in CHANNEL_NAMES]
            if unknown:
                raise ValueError(f"bin tokenizer channels {unknown} are not canonical channels")
            needed = max((CHANNEL_NAMES.index(n) for n in bin_tokenizer.channels), default=-1) + 1
            if needed > layout.n_channels:
                raise ValueError(
                    f"bin tokenizer channels need {needed} channel identifiers (their canonical "
                    f"positions, ADR-0003); the layout has {layout.n_channels}"
                )
        self.layout = layout
        self.text_tokenizer = text_tokenizer
        self.bin_tokenizer = bin_tokenizer

    @property
    def size(self) -> int:
        """Total number of identifiers in the joint vocabulary."""
        return self.layout.total_size

    def special(self, name: str) -> int:
        """Return a structural token identifier.

        Args:
            name: Structural token name, for example ``<bos>``.

        Returns:
            Its global identifier.
        """
        return self.layout.special_id(name)

    def encode_text(self, text: str, wrap: bool = True) -> list[int]:
        """Encode a text document into global identifiers.

        Args:
            text: Document to encode.
            wrap: Surround the document with ``<txt>`` and ``</txt>``.

        Returns:
            Global identifiers.

        Raises:
            RuntimeError: If no text tokenizer is bound.
        """
        if self.text_tokenizer is None:
            raise RuntimeError("no text tokenizer is bound; text encoding is available from M2")
        ids = [self.layout.text_id(local) for local in self.text_tokenizer.encode(text)]
        if not wrap:
            return ids
        return [self.special("<txt>"), *ids, self.special("</txt>")]

    def encode_telemetry(
        self, frame: pd.DataFrame, wrap: bool = True, channels: list[str] | None = None
    ) -> list[int]:
        """Encode a window of telemetry into global identifiers.

        Each row becomes an interleaved sequence of channel and bin tokens, in the
        tokenizer's channel order. A channel token's identifier is the channel's canonical
        position, whatever the tokenizer's order. Missing values become ``<nan>``.

        Args:
            frame: Wide telemetry table covering one window.
            wrap: Surround the window with ``<tel>`` and ``</tel>``.
            channels: Subset of channels to emit; all fitted channels when omitted.

        Returns:
            Global identifiers.

        Raises:
            RuntimeError: If no bin tokenizer is bound.
        """
        if self.bin_tokenizer is None:
            raise RuntimeError("no bin tokenizer is bound; fit one before encoding telemetry")
        selected = channels or self.bin_tokenizer.channels
        binned = self.bin_tokenizer.transform(frame)
        nan_id = self.special("<nan>")
        indices = [self.bin_tokenizer.channel_index(name) for name in selected]
        channel_ids = [self.layout.channel_id(CHANNEL_NAMES.index(name)) for name in selected]

        ids: list[int] = [self.special("<tel>")] if wrap else []
        for row in np.asarray(binned):
            for column, channel_id in zip(indices, channel_ids, strict=True):
                ids.append(channel_id)
                value = int(row[column])
                ids.append(nan_id if value == MISSING_BIN else self.layout.bin_id(value))
        if wrap:
            ids.append(self.special("</tel>"))
        return ids

    def encode_steps(self, frame: pd.DataFrame, masked: Sequence[str] = ()) -> np.ndarray:
        """Encode telemetry as the fixed-order stream: ``<sep>`` and one bin token a channel.

        Args:
            frame: Wide telemetry rows, in time order.
            masked: Channels emitted as ``<nan>`` whatever their value -- CARE's
                normalised power, for one (ADR-0011).

        Returns:
            A ``uint16`` array of shape ``(len(frame), 1 + channels)``: each row is one
            step, ``<sep>`` first, then the channels in the tokenizer's fitted order.

        Raises:
            RuntimeError: If no bin tokenizer is bound.
            KeyError: If a masked channel is not a fitted channel.
            ValueError: If an identifier would not fit ``uint16``.
        """
        if self.bin_tokenizer is None:
            raise RuntimeError("no bin tokenizer is bound; fit one before encoding telemetry")
        stray = [name for name in masked if name not in self.bin_tokenizer.channels]
        if stray:
            raise KeyError(f"masked channels {stray} are not fitted channels")
        if self.layout.total_size > np.iinfo(np.uint16).max + 1:
            raise ValueError(f"a vocabulary of {self.layout.total_size} does not fit uint16")
        binned = self.bin_tokenizer.transform(frame)
        ids = self.layout.bin_offset + binned
        ids[binned == MISSING_BIN] = self.special("<nan>")
        for name in masked:
            ids[:, self.bin_tokenizer.channel_index(name)] = self.special("<nan>")
        steps = np.empty((len(frame), 1 + ids.shape[1]), dtype=np.uint16)
        steps[:, 0] = self.special("<sep>")
        steps[:, 1:] = ids
        return steps

    def decode(self, global_id: int) -> Token:
        """Resolve one global identifier.

        Args:
            global_id: Identifier in the joint vocabulary.

        Returns:
            The decoded token.
        """
        return self.layout.decode(global_id)

    def describe(self) -> str:
        """Render the layout and bound tokenizers as Markdown.

        Returns:
            A Markdown fragment for reports and dataset cards.
        """
        lines = [self.layout.describe(), ""]
        text_state = "bound" if self.text_tokenizer is not None else "absent (M2)"
        bin_state = (
            f"bound, {len(self.bin_tokenizer.channels)} channels"
            if self.bin_tokenizer is not None
            else "absent"
        )
        lines.append(f"- text tokenizer: {text_state}")
        lines.append(f"- bin tokenizer: {bin_state}")
        lines.append(f"- total vocabulary: {self.size}")
        return "\n".join(lines) + "\n"
