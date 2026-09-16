"""Reading decoder checkpoints, and the one way a text-only checkpoint enters the joint vocabulary.

The M2 text checkpoints (``checkpoints/text/S*_text_seed1.pt``) embed **32,769** rows: the
32,768 ids of the fitted BPE and one local ``<sep>`` that the text shards write after every
document (``faultline check joint-vocab``, 2026-09-16). The joint vocabulary (ADR-0003 v2)
has 33,952 ids: a 1,184-id structure-and-telemetry prefix, then the text block at
``TEXT_OFFSET + i``. Its ``<sep>`` is the structural id 8. Loading a 32,769-row table into a
33,952-row model by slicing would be silent and wrong in one of several ways, and the
off-by-one that puts ``<sep>`` inside the text block would pass every shape check.

So this module is the **only** place ``torch.load`` is called on a checkpoint (a test scans
``src/`` for any other), and :func:`read_checkpoint` refuses a 32,769-row checkpoint.
The one way through is :func:`migrate_text_checkpoint`, which

1. **locates** the separator row rather than assuming it (:func:`locate_separator_row`): the
   text shard manifest's ``<sep>`` id, the tokenizer's size, the checkpoint's row count and
   the training streams themselves (every stream ends in the id, the id is the stream
   maximum, and no two occur together) must all name the same row, and that row must be the
   last, leaving ``0 .. 32,767`` as the BPE ids;
2. **copies** every BPE row ``i`` to ``TEXT_OFFSET + i`` unchanged and the separator row to
   joint id 8;
3. **initialises** the 1,183 other prefix rows as the decoder initialises any embedding,
   from a seeded generator, since a text-only model never trained them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import Tensor

from faultline.tokenizers.layout import TEXT_CAPACITY, TEXT_OFFSET, VocabLayout

#: Rows of an M2 text-only checkpoint's token embedding: the BPE ids and one local ``<sep>``.
TEXT_CHECKPOINT_ROWS = TEXT_CAPACITY + 1

#: The embedding the decoder ties its output head to.
EMBEDDING_KEY = "tokens.weight"

#: Where that embedding sits in a decoder state and in a risk model's state.
EMBEDDING_KEYS: tuple[str, ...] = (EMBEDDING_KEY, "backbone." + EMBEDDING_KEY)

#: Standard deviation of a freshly initialised embedding row, as ``TelemetryDecoder._init``.
INIT_STD = 0.02


class TextCheckpointRefusedError(ValueError):
    """A 32,769-row text-only checkpoint was read other than through the migration."""


def _read(path: Path) -> dict[str, Any]:
    """Read a checkpoint file with no guard. Private: callers use the two functions below."""
    payload: dict[str, Any] = torch.load(path, map_location="cpu", weights_only=False)
    return payload


def embedding_rows(path: Path) -> int:
    """The token-embedding row count of a checkpoint, observed without loading it into a model.

    Args:
        path: A checkpoint file.

    Returns:
        The row count, or -1 where the state has no token embedding.
    """
    state = _read(path)["state"]
    key = next((k for k in EMBEDDING_KEYS if k in state), None)
    return int(state[key].shape[0]) if key is not None else -1


def read_checkpoint(path: Path) -> dict[str, Any]:
    """Read a decoder checkpoint, refusing a text-only one.

    Args:
        path: A checkpoint file.

    Returns:
        The payload: ``spec``, ``kind``, ``seed`` and ``state``.

    Raises:
        TextCheckpointRefusedError: If the token embedding has 32,769 rows. Use
            :func:`migrate_text_checkpoint`.
    """
    payload = _read(path)
    state = payload["state"]
    rows = {int(state[k].shape[0]) for k in EMBEDDING_KEYS if k in state}
    if TEXT_CHECKPOINT_ROWS in rows:
        raise TextCheckpointRefusedError(
            f"{path}: a {TEXT_CHECKPOINT_ROWS:,}-row text-only checkpoint is read only through "
            "faultline.model.checkpoints.migrate_text_checkpoint, which maps its local <sep> "
            "to joint id 8"
        )
    return payload


@dataclass(frozen=True)
class SeparatorLocation:
    """Where a text checkpoint's separator row sits, and every piece of evidence for it.

    Attributes:
        row: The row, asserted equal across every source below.
        manifest_sep: ``specials["<sep>"]`` in the text shard manifest.
        manifest_vocabulary: ``vocabulary_size`` in the same manifest.
        tokenizer_size: Ids the fitted BPE tokenizer defines.
        checkpoint_rows: Token-embedding rows of the checkpoint.
        stream_maximum: The largest id in any training stream.
        streams_ending_in_sep: Training streams whose last id is the row, of all streams.
        adjacent_separators: Places two separators occur together (an empty document).
        separators: Separator ids counted over the training streams.
    """

    row: int
    manifest_sep: int
    manifest_vocabulary: int
    tokenizer_size: int
    checkpoint_rows: int
    stream_maximum: int
    streams_ending_in_sep: tuple[int, int]
    adjacent_separators: int
    separators: int


def locate_separator_row(
    shard_dir: Path, tokenizer_size: int, checkpoint_rows: int
) -> SeparatorLocation:
    """Find the separator row from the shards and the checkpoint, and assert it is the last.

    Args:
        shard_dir: The text shard directory the checkpoint was trained on.
        tokenizer_size: Ids the fitted tokenizer defines.
        checkpoint_rows: The checkpoint's token-embedding rows.

    Returns:
        The location and its evidence.

    Raises:
        ValueError: If any source disagrees, or the row is not ``TEXT_CAPACITY``, the end of
            the text region.
    """
    manifest = json.loads((shard_dir / "manifest.json").read_text(encoding="utf-8"))
    sep = int(manifest["specials"]["<sep>"])
    maximum = -1
    ending = total = adjacent = count = 0
    for key, record in sorted(manifest["files"].items()):
        if not key.endswith("__train"):
            continue
        stream = np.fromfile(shard_dir / str(record["tokens"]), dtype=np.dtype(manifest["dtype"]))
        total += 1
        maximum = max(maximum, int(stream.max()))
        ending += int(stream[-1]) == sep
        marks = stream == sep
        count += int(marks.sum())
        adjacent += int((marks[1:] & marks[:-1]).sum())
    location = SeparatorLocation(
        row=sep,
        manifest_sep=sep,
        manifest_vocabulary=int(manifest["vocabulary_size"]),
        tokenizer_size=tokenizer_size,
        checkpoint_rows=checkpoint_rows,
        stream_maximum=maximum,
        streams_ending_in_sep=(ending, total),
        adjacent_separators=adjacent,
        separators=count,
    )
    failures = [
        f"{name} is {value:,}, expected {expected:,}"
        for name, value, expected in (
            ("the manifest <sep>", sep, TEXT_CAPACITY),
            ("the tokenizer size", tokenizer_size, sep),
            ("the manifest vocabulary", location.manifest_vocabulary, sep + 1),
            ("the checkpoint's rows", checkpoint_rows, sep + 1),
            ("the largest training id", maximum, sep),
            ("training streams ending in <sep>", ending, total),
            ("adjacent separators", adjacent, 0),
        )
        if value != expected
    ]
    if not total:
        failures.append("no training stream was read")
    if failures:
        raise ValueError(
            f"{shard_dir}: the separator row is not where it must be: " + "; ".join(failures)
        )
    return location


def migrate_text_state(
    state: dict[str, Tensor], layout: VocabLayout, separator_row: int, seed: int = 0
) -> dict[str, Tensor]:
    """Map a text-only state dictionary onto the joint vocabulary.

    Args:
        state: The text-only decoder's parameters, 32,769 embedding rows.
        layout: The joint layout.
        separator_row: The located separator row (:func:`locate_separator_row`).
        seed: Seed of the generator initialising the prefix rows a text model never trained.

    Returns:
        A new state dictionary: every other tensor shared, the embedding rebuilt at
        ``layout.total_size`` rows.

    Raises:
        ValueError: If the embedding is not 32,769 rows, the separator row is not the one past
            the text region, or the layout's text block does not hold every BPE row.
    """
    table = state[EMBEDDING_KEY]
    rows, width = table.shape
    if rows != TEXT_CHECKPOINT_ROWS:
        raise ValueError(f"a text-only state has {TEXT_CHECKPOINT_ROWS:,} rows, got {rows:,}")
    if separator_row != TEXT_CAPACITY:
        raise ValueError(f"the separator row must be {TEXT_CAPACITY:,}, got {separator_row:,}")
    if layout.n_text != TEXT_CAPACITY:
        raise ValueError(f"the joint text block holds {layout.n_text:,} ids, not {TEXT_CAPACITY:,}")
    generator = torch.Generator().manual_seed(seed)
    joint = (
        torch.randn((layout.total_size, width), generator=generator, dtype=table.dtype) * INIT_STD
    )
    joint[TEXT_OFFSET : TEXT_OFFSET + TEXT_CAPACITY] = table[:TEXT_CAPACITY]
    joint[layout.special_id("<sep>")] = table[separator_row]
    return {**state, EMBEDDING_KEY: joint}


def migrate_text_checkpoint(
    path: Path, layout: VocabLayout, shard_dir: Path, tokenizer_size: int, seed: int = 0
) -> tuple[dict[str, Any], SeparatorLocation]:
    """Read a text-only checkpoint onto the joint vocabulary, the one permitted way.

    Args:
        path: The text-only checkpoint.
        layout: The joint layout.
        shard_dir: The text shards it was trained on, to locate the separator.
        tokenizer_size: Ids the fitted tokenizer defines.
        seed: Seed for the untrained prefix rows.

    Returns:
        The payload with its state migrated and its spec's ``vocab_size`` set to the joint
        size, and the separator's location.
    """
    payload = _read(path)
    rows = int(payload["state"][EMBEDDING_KEY].shape[0])
    location = locate_separator_row(shard_dir, tokenizer_size, rows)
    state = migrate_text_state(payload["state"], layout, location.row, seed)
    spec = {**payload["spec"], "vocab_size": layout.total_size}
    return {**payload, "spec": spec, "state": state, "migrated_from": path.as_posix()}, location


def text_support(layout: VocabLayout) -> Tensor:
    """The joint ids a text-only model could emit, in its own id order.

    Position ``i < 32,768`` holds ``TEXT_OFFSET + i``; the last position holds joint ``<sep>``.
    Restricting a migrated model's softmax to these ids reproduces the text-only model's
    distribution exactly, which is how the migration is checked behaviourally.

    Args:
        layout: The joint layout.

    Returns:
        A ``long`` tensor of 32,769 joint ids.
    """
    ids = torch.arange(TEXT_OFFSET, TEXT_OFFSET + TEXT_CAPACITY, dtype=torch.long)
    return torch.cat([ids, torch.tensor([layout.special_id("<sep>")], dtype=torch.long)])
