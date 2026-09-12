r"""Byte-level BPE, trained by this project's own code (M2c).

Two pieces, both written from scratch and neither importing the ``tokenizers``
library, per the M2 brief: a GPT-2-style pre-tokenizer that splits text into chunks a
merge is never allowed to cross, and the merge-learning loop itself. ``tokenizers`` is
a *test-only* dependency (``tests/tokenizers/test_text_bpe.py``): the reference this
module's output is checked against, never a component of it.

**Pre-tokenization is not a detail; it is most of what makes byte-level BPE reproduce
a reference implementation exactly.** Two texts joined by a space split into two
chunks, not one, so a merge never spans a word boundary; a run of digits never merges
with a run of letters; contractions (``'s``, ``'t``, ``'re``, ``'ve``, ``'m``, ``'ll``,
``'d``) are cut off their word. The rule that took the most work to get right, because
it is the one place a naive reading of "split on whitespace" disagrees with the
reference: **only a literal space character (U+0020) can attach to the token that
follows it.** A run of whitespace ending in a space hands that one space to the next
word (``"a  b"`` -> ``"a"``, ``" "``, ``" b"``); a run ending in a tab or newline does
not -- ``"a\\n\\nb"`` -> ``"a"``, ``"\\n"``, ``"\\n"``, ``"b"``, three chunks, the
newlines each alone and the following word unattached. This was found by fetching the
reference pre-tokenizer's output on deliberately varied fixtures rather than by
reading the GPT-2 paper's regex and assuming Python's ``re`` would agree with it.

**Vocabulary.** 256 base tokens, one per byte value, identifiers ``0``-``255``, plus
one merge per identifier ``256`` upward. Fitting to ``vocab_size`` therefore learns
``vocab_size - 256`` merges. These are *local* identifiers: a fitted tokenizer's ids
run ``[0, vocab_size)`` and mean nothing about where they sit in the joint vocabulary.
Placing them at ``layout.text_offset`` (ADR-0003) is ``JointVocab.encode_text``'s job,
not this module's -- exactly as ``QuantileBinTokenizer`` stays local and
``VocabLayout``/``JointVocab`` do the shifting for telemetry.

**Tie-breaking.** Fitting on real text essentially never needs it -- English prose
does not produce two byte pairs occurring the exact same number of times at the same
step outside adversarial or degenerate input -- and this project does not assert that
its tie-break matches any particular reference implementation's undocumented internal
behaviour (reverse-engineering that behaviour from a black box was tried during
development and abandoned: two probes that should have settled it gave answers that
contradicted a single consistent rule, which is what "undocumented" means in practice).
What this module needs is a tie-break that is deterministic and stated, so a refit is
reproducible; it is not required to be the same tie-break another implementation makes.
Ascending ``(left_id, right_id)`` is what is used, and the reference-comparison test
asserts the fixture it runs on never reaches one, so the fixture's result does not
depend on this choice.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from faultline.logging_utils import get_logger

logger = get_logger(__name__)

#: Base alphabet: one token per byte value. Merges start at this id.
BASE_VOCAB_SIZE = 256

#: GPT-2's contraction suffixes, checked at every chunk boundary before the general
#: character-class rules. Order does not matter for correctness here: none is a
#: prefix of another.
_CONTRACTIONS: tuple[str, ...] = ("'s", "'t", "'re", "'ve", "'m", "'ll", "'d")

Pair = tuple[int, int]


def _char_class(ch: str) -> str:
    r"""Classify one character for pre-tokenization.

    Args:
        ch: A single character.

    Returns:
        ``"space"`` for anything ``str.isspace``, ``"letter"`` for anything
        ``str.isalpha`` (the practical stand-in for ``\\p{L}`` without the ``regex``
        package), ``"digit"`` for anything ``str.isdigit``, ``"other"`` otherwise.
    """
    if ch.isspace():
        return "space"
    if ch.isalpha():
        return "letter"
    if ch.isdigit():
        return "digit"
    return "other"


def _raw_runs(text: str) -> list[tuple[str, str]]:
    """Split text into maximal same-class runs, contractions cut off first.

    Args:
        text: Input string.

    Returns:
        ``(class, substring)`` pairs covering ``text`` end to end, in order. Class is
        one of ``"contraction"``, ``"space"``, ``"letter"``, ``"digit"``, ``"other"``.
    """
    runs: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        matched = next((suf for suf in _CONTRACTIONS if text.startswith(suf, i)), None)
        if matched:
            runs.append(("contraction", matched))
            i += len(matched)
            continue
        cls = _char_class(text[i])
        j = i + 1
        while j < n and _char_class(text[j]) == cls:
            j += 1
        runs.append((cls, text[i:j]))
        i = j
    return runs


def pretokenize(text: str) -> list[str]:
    """Split text into chunks a BPE merge may never cross.

    A whitespace run followed by something else hands at most one character to that
    following chunk, and only when that character is a literal space (see the module
    docstring). Everything else -- letters, digits, punctuation runs, contractions,
    and a whitespace run with nothing after it -- is its own chunk untouched.

    Args:
        text: Input string.

    Returns:
        Chunks that concatenate back to ``text`` exactly.
    """
    runs = _raw_runs(text)
    chunks: list[str] = []
    i = 0
    while i < len(runs):
        cls, s = runs[i]
        if cls == "space" and i + 1 < len(runs):
            if len(s) > 1:
                chunks.append(s[:-1])
            last = s[-1]
            if last == " ":
                _next_cls, next_s = runs[i + 1]
                chunks.append(last + next_s)
                i += 2
                continue
            chunks.append(last)
            i += 1
            continue
        chunks.append(s)
        i += 1
    return chunks


def _pair_counts(symbol_chunks: list[tuple[list[int], int]]) -> Counter[Pair]:
    """Count adjacent-symbol pairs across every chunk, weighted by chunk frequency.

    Args:
        symbol_chunks: Each chunk's current symbol sequence and how many times that
            chunk occurs in the corpus.

    Returns:
        Pair frequencies.
    """
    counts: Counter[Pair] = Counter()
    for symbols, freq in symbol_chunks:
        for left, right in zip(symbols, symbols[1:], strict=False):
            counts[(left, right)] += freq
    return counts


def _apply_merge(symbols: list[int], pair: Pair, new_id: int) -> list[int]:
    """Replace every non-overlapping occurrence of ``pair`` in ``symbols`` with ``new_id``.

    Args:
        symbols: A chunk's current symbol sequence.
        pair: The pair being merged.
        new_id: Identifier the merged pair becomes.

    Returns:
        The updated sequence.
    """
    out: list[int] = []
    i, n = 0, len(symbols)
    while i < n:
        if i + 1 < n and (symbols[i], symbols[i + 1]) == pair:
            out.append(new_id)
            i += 2
        else:
            out.append(symbols[i])
            i += 1
    return out


class TextBPETokenizer:
    """Byte-level BPE: fit, encode and decode over local identifiers ``[0, vocab_size)``.

    Attributes:
        vocab_size: Total identifiers, base alphabet plus merges.
        merges: Learned merges in the order they were learned; the identifier a merge
            produces is ``BASE_VOCAB_SIZE + its index in this list``.
        meta: Provenance recorded at fit time.
    """

    def __init__(
        self,
        vocab_size: int = BASE_VOCAB_SIZE,
        merges: list[Pair] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Construct a tokenizer, normally via :meth:`fit` or :meth:`load`.

        Args:
            vocab_size: Target vocabulary size; unfitted below :data:`BASE_VOCAB_SIZE`.
            merges: Pre-learned merges, in learned order.
            meta: Provenance metadata.

        Raises:
            ValueError: If ``vocab_size`` is smaller than the base alphabet.
        """
        if vocab_size < BASE_VOCAB_SIZE:
            raise ValueError(f"vocab_size must be at least {BASE_VOCAB_SIZE}, got {vocab_size}")
        self.vocab_size = vocab_size
        self.merges: list[Pair] = list(merges or [])
        self.meta: dict[str, Any] = dict(meta or {})
        self._rank: dict[Pair, int] = {pair: index for index, pair in enumerate(self.merges)}
        self._merge_id: dict[Pair, int] = {
            pair: BASE_VOCAB_SIZE + index for index, pair in enumerate(self.merges)
        }
        self._bytes_of: dict[int, bytes] = self._resolve_byte_sequences()

    @property
    def is_fitted(self) -> bool:
        """Whether this tokenizer has learned any merges."""
        return len(self.merges) > 0

    def _resolve_byte_sequences(self) -> dict[int, bytes]:
        """Build the id -> raw-byte-sequence table every merge id decodes to.

        Returns:
            A mapping covering the base alphabet and every learned merge.
        """
        table: dict[int, bytes] = {i: bytes([i]) for i in range(BASE_VOCAB_SIZE)}
        for index, (left, right) in enumerate(self.merges):
            table[BASE_VOCAB_SIZE + index] = table[left] + table[right]
        return table

    # -- fitting --------------------------------------------------------------------

    @classmethod
    def fit(cls, texts: Iterable[str], vocab_size: int) -> TextBPETokenizer:
        """Learn merges from a corpus of documents.

        Args:
            texts: Training documents. Fitted on the train split only, the same
                discipline :class:`~faultline.tokenizers.quantile_bins.QuantileBinTokenizer`
                follows: fitting on held-out text would leak its distribution into the
                vocabulary.
            vocab_size: Target vocabulary size.

        Returns:
            The fitted tokenizer.
        """
        chunk_freq: Counter[str] = Counter()
        for text in texts:
            chunk_freq.update(pretokenize(text))

        symbol_chunks: list[tuple[list[int], int]] = [
            (list(chunk.encode("utf-8")), freq) for chunk, freq in chunk_freq.items()
        ]

        merges: list[Pair] = []
        target_merges = vocab_size - BASE_VOCAB_SIZE
        while len(merges) < target_merges:
            counts = _pair_counts(symbol_chunks)
            if not counts:
                break
            # Highest frequency wins; among ties, the smallest (left, right) pair --
            # stated in the module docstring, not asserted to match any reference.
            pair, _count = min(counts.items(), key=lambda item: (-item[1], item[0]))
            new_id = BASE_VOCAB_SIZE + len(merges)
            merges.append(pair)
            symbol_chunks = [
                (_apply_merge(symbols, pair, new_id), freq) for symbols, freq in symbol_chunks
            ]

        actual_size = BASE_VOCAB_SIZE + len(merges)
        if actual_size < vocab_size:
            logger.warning(
                "fit stopped at %d merges (%d identifiers): the training text ran out "
                "of repeating pairs before reaching the requested vocab_size=%d",
                len(merges),
                actual_size,
                vocab_size,
            )
        return cls(vocab_size=actual_size, merges=merges, meta={"requested_vocab_size": vocab_size})

    # -- encode / decode --------------------------------------------------------------

    def encode(self, text: str) -> list[int]:
        """Encode text into local BPE identifiers.

        Args:
            text: Document to encode.

        Returns:
            Local identifiers in ``[0, vocab_size)``.
        """
        ids: list[int] = []
        for chunk in pretokenize(text):
            ids.extend(self._encode_chunk(list(chunk.encode("utf-8"))))
        return ids

    def _encode_chunk(self, symbols: list[int]) -> list[int]:
        """Apply learned merges to one chunk's byte sequence, in learned priority order.

        Args:
            symbols: The chunk's raw byte values.

        Returns:
            The merged symbol sequence.
        """
        while len(symbols) > 1:
            candidates = (
                (self._rank[pair], pair)
                for pair in zip(symbols, symbols[1:], strict=False)
                if pair in self._rank
            )
            best = min(candidates, default=None, key=lambda item: item[0])
            if best is None:
                break
            _rank, pair = best
            symbols = _apply_merge(symbols, pair, self._merge_id[pair])
        return symbols

    def decode(self, ids: list[int]) -> str:
        """Decode local identifiers back into text.

        Args:
            ids: Local identifiers, as :meth:`encode` produced.

        Returns:
            The decoded string.

        Raises:
            KeyError: If an identifier is not in this tokenizer's vocabulary.
        """
        raw = b"".join(self._bytes_of[i] for i in ids)
        return raw.decode("utf-8", errors="replace")

    # -- persistence ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain, JSON-safe mapping.

        Returns:
            The tokenizer's state.
        """
        return {
            "vocab_size": self.vocab_size,
            "merges": [list(pair) for pair in self.merges],
            "meta": self.meta,
        }

    def save(self, path: Path) -> Path:
        """Write the tokenizer to a JSON file.

        Args:
            path: Destination file; parent directories are created.

        Returns:
            The path written.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> TextBPETokenizer:
        """Read a tokenizer back from JSON.

        Args:
            path: File written by :meth:`save`.

        Returns:
            The restored tokenizer.
        """
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        merges = [(int(left), int(right)) for left, right in payload["merges"]]
        return cls(
            vocab_size=int(payload["vocab_size"]), merges=merges, meta=dict(payload.get("meta", {}))
        )
