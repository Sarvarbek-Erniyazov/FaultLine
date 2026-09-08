"""Byte-level BPE tokenizer for the operator-narrative corpus (M2).

This is a typed stub. The interface is fixed now so that ``JointVocab`` and the
M1 telemetry work can be written against it, and so that the M2 implementation
cannot quietly change the joint vocabulary contract (ADR-0003): the trained
tokenizer emits *local* identifiers in ``[0, vocab_size)`` and knows nothing about
offsets.

Implementation is deliberately deferred to M2, in lockstep with the text
pretraining milestone.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from faultline.config import StrictModel


class TextBPEConfig(StrictModel):
    """Training settings for the byte-level BPE tokenizer.

    Attributes:
        vocab_size: Target vocabulary size, excluding structural tokens.
        min_frequency: Minimum pair frequency for a merge to be learned.
        byte_level: Operate over UTF-8 bytes, so no input is ever out of vocabulary.
        lowercase: Whether to lowercase before training; off by default because
            operator narratives use capitalisation to mark equipment tags.
    """

    vocab_size: int = 16_384
    min_frequency: int = 2
    byte_level: bool = True
    lowercase: bool = False


class TextBPETokenizer:
    """Byte-level BPE over the operator-narrative corpus.

    Attributes:
        config: Training settings.
        vocab_size: Size of the trained vocabulary, or 0 before training.
    """

    def __init__(self, config: TextBPEConfig | None = None) -> None:
        """Create an untrained tokenizer.

        Args:
            config: Training settings; defaults when omitted.
        """
        self.config = config or TextBPEConfig()
        self.vocab_size = 0

    def train(self, corpus: Iterable[str], vocab_size: int | None = None) -> TextBPETokenizer:
        """Learn merges from a corpus.

        Args:
            corpus: Iterable of documents, streamed rather than materialized.
            vocab_size: Override for the configured vocabulary size.

        Returns:
            The trained tokenizer.

        Raises:
            NotImplementedError: Always; scheduled for M2.
        """
        raise NotImplementedError("TODO(m2): byte-level BPE training")

    def encode(self, text: str) -> list[int]:
        """Encode a document into local identifiers.

        Args:
            text: Document to encode.

        Returns:
            Local identifiers in ``[0, vocab_size)``.

        Raises:
            NotImplementedError: Always; scheduled for M2.
        """
        raise NotImplementedError("TODO(m2): byte-level BPE encoding")

    def decode(self, ids: list[int]) -> str:
        """Decode local identifiers back into a document.

        Args:
            ids: Local identifiers in ``[0, vocab_size)``.

        Returns:
            The decoded document.

        Raises:
            NotImplementedError: Always; scheduled for M2.
        """
        raise NotImplementedError("TODO(m2): byte-level BPE decoding")

    def save(self, path: Path) -> Path:
        """Persist the trained tokenizer.

        Args:
            path: Destination file.

        Returns:
            The path written.

        Raises:
            NotImplementedError: Always; scheduled for M2.
        """
        raise NotImplementedError("TODO(m2): tokenizer serialization")

    @classmethod
    def load(cls, path: Path) -> TextBPETokenizer:
        """Restore a trained tokenizer from disk.

        Args:
            path: File written by :meth:`save`.

        Returns:
            The restored tokenizer.

        Raises:
            NotImplementedError: Always; scheduled for M2.
        """
        raise NotImplementedError("TODO(m2): tokenizer deserialization")

    def to_dict(self) -> dict[str, Any]:
        """Return the tokenizer state as a dictionary.

        Returns:
            A JSON-ready mapping.

        Raises:
            NotImplementedError: Always; scheduled for M2.
        """
        raise NotImplementedError("TODO(m2): tokenizer serialization")
