"""Windows over the token shards, for language modelling and for risk (M1e).

The shards are memory-mappable ``uint16`` streams of 13 tokens a step, one file per site
and split, beside a window index whose rows are the *admissible* window ends: context
inside one segment, horizon inside the split, no training window reading an excluded
outage, and a label that is known rather than assumed negative (M1b step 12). That index
is already leakage-checked, so training reads it rather than re-deriving windows and
re-deriving the mistake.

**Two strides, and they are not the same number.** Training reads the index at
``train_stride`` steps: at stride 1 the 4.7 million training steps yield windows that
overlap in 143 of their 144 steps, so the token count flatters the effective sample size
by more than an order of magnitude, and an epoch is mostly the same window. Evaluation
reads at stride 1, because a risk model is scored on every step it would have to make a
call on in deployment. Both numbers go in the run config and in the report.

Nothing is held in memory but the index columns the run needs: the token streams stay on
disk under ``numpy.memmap`` and the operating system's page cache does the rest.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
import torch
from torch import Tensor

from faultline.logging_utils import get_logger

logger = get_logger(__name__)

#: One batch: the tokens, the labels and the index of the set each window came from.
Batch = tuple[Tensor, Tensor, np.ndarray]

#: Tokens on disk are ``uint16``; torch has no unsigned 16-bit integer, so a window is
#: widened to ``int64`` at the moment it becomes a tensor and never before.
TOKEN_DTYPE = np.uint16


@dataclass(frozen=True)
class ShardSet:
    """One tokenizer's shards, as the manifest describes them.

    Attributes:
        root: The directory holding the shard files.
        manifest: The manifest written beside them.
    """

    root: Path
    manifest: dict[str, Any]

    @classmethod
    def load(cls, root: Path) -> ShardSet:
        """Read a shard directory's manifest.

        Args:
            root: The directory ``faultline telemetry shards`` wrote.

        Returns:
            The shard set.

        Raises:
            FileNotFoundError: If the manifest is not there.
        """
        path = root / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(
                f"no shard manifest at {path}; run `faultline telemetry shards`"
            )
        return cls(root=root, manifest=json.loads(path.read_text(encoding="utf-8")))

    @property
    def tokens_per_step(self) -> int:
        """Tokens written per grid step, 13 at M1."""
        return int(self.manifest["tokens_per_step"])

    @property
    def context_steps(self) -> int:
        """Steps in a window, as the shards were built with."""
        return int(self.manifest["context_steps"])

    @property
    def context_tokens(self) -> int:
        """Tokens in a window: the model's context length."""
        return self.context_steps * self.tokens_per_step

    @property
    def vocab_size(self) -> int:
        """Identifiers the shards were written against."""
        return int(self.manifest["vocabulary_size"])

    def files(self) -> dict[str, dict[str, Any]]:
        """Per ``<source>__<split>`` key, the manifest's file record."""
        return dict(self.manifest["files"])

    def keys(self, split: str, sources: Sequence[str] | None = None) -> list[str]:
        """The shard keys of one split, optionally restricted to some sources.

        Args:
            split: ``train``, ``val`` or ``test``.
            sources: Sources to keep; every source of the split when omitted.

        Returns:
            The matching keys, sorted.
        """
        wanted = set(sources) if sources is not None else None
        found = []
        for key in self.files():
            source, _, key_split = key.partition("__")
            if key_split == split and (wanted is None or source in wanted):
                found.append(key)
        return sorted(found)


def source_of(key: str) -> str:
    """The source a shard key belongs to."""
    return key.partition("__")[0]


@dataclass
class WindowSet:
    """Admissible windows of one shard, and the tokens they index into.

    Attributes:
        key: The shard key, ``<source>__<split>``.
        tokens: The memory-mapped token stream.
        starts: First step of each window.
        ends: Last step of each window, inclusive.
        labels: Per window, the label the risk head is trained or scored against; empty
            for a language-modelling set.
        years: Per window, the calendar year, so a held-out site can be reported per year
            (``per_year_sites``, ADR-0008) rather than pooled only.
    """

    key: str
    tokens: np.memmap
    starts: np.ndarray
    ends: np.ndarray
    labels: np.ndarray
    years: np.ndarray

    def __len__(self) -> int:
        """How many windows this set holds."""
        return int(self.starts.size)

    @property
    def source(self) -> str:
        """The source the windows come from."""
        return source_of(self.key)


def load_windows(
    shards: ShardSet,
    key: str,
    stride: int,
    label: str | None = None,
    limit: int | None = None,
    seed: int = 0,
) -> WindowSet:
    """Read one shard's window index and open its token stream.

    Args:
        shards: The shard set.
        key: The shard key, ``<source>__<split>``.
        stride: Keep every ``stride``-th admissible window. ``1`` keeps them all, which
            is what evaluation uses; training uses the run config's ``train_stride``.
        label: The window-index column to read as the target, and whose ``_known``
            companion decides admissibility at that horizon. ``None`` reads no label,
            which is the language-modelling case and keeps every window in the index.
        limit: Keep at most this many windows, sampled without replacement after the
            stride. For bounding an evaluation pass, never for training selection.
        seed: Seed for that subsample.

    Returns:
        The window set.

    Raises:
        KeyError: If the shard key is not in the manifest.
        ValueError: If the stride is not positive.
    """
    if stride < 1:
        raise ValueError(f"stride must be at least 1, got {stride}")
    record = shards.files().get(key)
    if record is None:
        raise KeyError(f"{key} is not in the shard manifest")
    columns = ["year", "start_step", "end_step"]
    if label is not None:
        columns += [label, f"{label}_known"]
    frame = pq.read_table(shards.root / str(record["windows"]), columns=columns).to_pandas()
    if label is not None:
        frame = frame[frame[f"{label}_known"].to_numpy()]
    keep = np.arange(0, len(frame), stride)
    if limit is not None and keep.size > limit:
        keep = np.sort(np.random.default_rng(seed).choice(keep, size=limit, replace=False))
    frame = frame.iloc[keep]
    steps = int(record["steps"])
    tokens = np.memmap(
        shards.root / str(record["tokens"]),
        dtype=TOKEN_DTYPE,
        mode="r",
        shape=(steps * shards.tokens_per_step,),
    )
    return WindowSet(
        key=key,
        tokens=tokens,
        starts=frame["start_step"].to_numpy(dtype=np.int64),
        ends=frame["end_step"].to_numpy(dtype=np.int64),
        labels=(
            frame[label].to_numpy(dtype=np.float32)
            if label is not None
            else np.zeros(0, np.float32)
        ),
        years=frame["year"].to_numpy(dtype=np.int64),
    )


class WindowSampler:
    """Draws batches of windows from several shards at once.

    One epoch is every window of every shard in the set, shuffled together so that a
    batch mixes the training sites rather than marching through one and then the other.
    The sampler is an iterator over batches, not a ``DataLoader``: the windows are
    memory-mapped slices and the work is a copy, so a worker process would cost more in
    serialisation than it saves.

    Attributes:
        sets: The window sets drawn from.
        batch_size: Windows per batch.
        tokens_per_step: Tokens a grid step contributes.
        context_steps: Steps in a window.
        labelled: Whether batches carry labels.
    """

    def __init__(
        self,
        sets: Sequence[WindowSet],
        batch_size: int,
        tokens_per_step: int,
        context_steps: int,
        labelled: bool,
    ) -> None:
        """Build the sampler.

        Args:
            sets: The shards to draw from.
            batch_size: Windows per batch.
            tokens_per_step: Tokens a grid step contributes, from the manifest.
            context_steps: Steps in a window, from the manifest.
            labelled: Whether the sets carry labels.

        Raises:
            ValueError: If no set holds a window.
        """
        self.sets = list(sets)
        self.batch_size = batch_size
        self.tokens_per_step = tokens_per_step
        self.context_steps = context_steps
        self.labelled = labelled
        sizes = [len(s) for s in self.sets]
        if not sum(sizes):
            raise ValueError("no admissible windows in any shard of this split")
        self._index = np.concatenate(
            [
                np.stack([np.full(n, i, np.int64), np.arange(n, dtype=np.int64)], axis=1)
                for i, n in enumerate(sizes)
                if n
            ]
        )

    def __len__(self) -> int:
        """Batches in one pass over every window."""
        return int(self._index.shape[0] + self.batch_size - 1) // self.batch_size

    @property
    def windows(self) -> int:
        """Windows in one pass."""
        return int(self._index.shape[0])

    @property
    def index(self) -> np.ndarray:
        """``(windows, 2)`` of set index and row, in the order an unshuffled pass yields.

        Scoring reads this to attribute each scored window back to its source and its
        calendar year, which is what lets a held-out site be reported per year and two
        sources be kept out of one number.
        """
        return self._index

    def _gather(self, rows: np.ndarray) -> Batch:
        """Copy one batch out of the memory maps.

        Args:
            rows: ``(batch, 2)`` of set index and window index.

        Returns:
            The tokens, the labels and the set index of each window.
        """
        width = self.context_steps * self.tokens_per_step
        out = np.empty((rows.shape[0], width), dtype=np.int64)
        labels = np.zeros(rows.shape[0], dtype=np.float32)
        for position, (which, row) in enumerate(rows):
            window = self.sets[which]
            start = int(window.starts[row]) * self.tokens_per_step
            out[position] = window.tokens[start : start + width]
            if self.labelled:
                labels[position] = window.labels[row]
        return torch.from_numpy(out), torch.from_numpy(labels), rows[:, 0]

    def epoch(self, generator: np.random.Generator | None = None) -> Iterator[Batch]:
        """Iterate one pass over every window.

        Args:
            generator: Shuffles the order when given; the order is left as indexed when
                omitted, which is what evaluation wants.

        Yields:
            The tokens, the labels and the set index of each window in the batch.
        """
        order = self._index
        if generator is not None:
            order = order[generator.permutation(order.shape[0])]
        for start in range(0, order.shape[0], self.batch_size):
            yield self._gather(order[start : start + self.batch_size])

    def forever(self, seed: int) -> Iterator[Batch]:
        """Iterate batches without end, reshuffling at every pass.

        Training runs to a token budget rather than to a number of epochs, so the loop
        needs a stream and not a length.

        Args:
            seed: Seed of the reshuffling generator.

        Yields:
            Batches, for ever.
        """
        generator = np.random.default_rng(seed)
        passes = 0
        while True:
            yield from self.epoch(generator)
            passes += 1
            logger.debug("sampler completed pass %d", passes)


class BalancedWindowSampler(WindowSampler):
    """Training batches holding a fixed number of positive windows (M3 step 0).

    At the natural base rate (2.2% of training windows at stride 6) a 32-window step
    carries no positive about half the time, which is how M1e's risk arms trained on 882
    positives. This sampler puts exactly ``positives_per_batch`` positives in every batch
    and fills the rest with negatives. Positives and negatives are each drawn by shuffled
    passes over their own rows, without replacement inside a pass, so every positive is
    seen once before any is seen twice. Within a batch the order is shuffled, so position
    says nothing about the label.

    It is a training sampler only. Evaluation reads the natural rate, so :meth:`epoch` is
    refused rather than quietly yielding a different distribution.

    Attributes:
        positives_per_batch: Positive windows in every batch.
        positives_seen: Positive windows drawn so far, counting repeats.
        positive_rows: Positive windows available.
        natural_rate: The share of positive windows in the sets, the rate a prior
            correction maps scores back to.
    """

    def __init__(
        self,
        sets: Sequence[WindowSet],
        batch_size: int,
        positives_per_batch: int,
        tokens_per_step: int,
        context_steps: int,
    ) -> None:
        """Build the sampler.

        Args:
            sets: The labelled shards to draw from.
            batch_size: Windows per batch.
            positives_per_batch: Positive windows in every batch.
            tokens_per_step: Tokens a grid step contributes, from the manifest.
            context_steps: Steps in a window, from the manifest.

        Raises:
            ValueError: If a batch could not hold at least one positive and one negative,
                or the sets hold no positive or no negative window.
        """
        super().__init__(sets, batch_size, tokens_per_step, context_steps, labelled=True)
        if not 0 < positives_per_batch < batch_size:
            raise ValueError(
                f"positives_per_batch {positives_per_batch} must leave a positive and a "
                f"negative in a batch of {batch_size}"
            )
        self.positives_per_batch = positives_per_batch
        labels = np.array(
            [self.sets[int(which)].labels[int(row)] for which, row in self._index],
            dtype=np.float32,
        )
        positive = labels > 0.5
        self._positives = self._index[positive]
        self._negatives = self._index[~positive]
        if not self._positives.shape[0] or not self._negatives.shape[0]:
            raise ValueError(
                f"balanced sampling needs both classes: {self._positives.shape[0]} positive "
                f"and {self._negatives.shape[0]} negative windows"
            )
        self.positives_seen = 0

    @property
    def positive_rows(self) -> int:
        """Positive windows available."""
        return int(self._positives.shape[0])

    @property
    def natural_rate(self) -> float:
        """The share of positive windows in the sets."""
        return self.positive_rows / self.windows

    def epoch(self, generator: np.random.Generator | None = None) -> Iterator[Batch]:
        """Refused: a balanced sampler has no natural pass, and evaluation must not use one.

        Raises:
            TypeError: Always.
        """
        raise TypeError("a balanced sampler is for training; evaluate at the natural rate")

    @staticmethod
    def _stream(rows: np.ndarray, generator: np.random.Generator) -> Iterator[np.ndarray]:
        """Rows one at a time, in shuffled passes without replacement inside a pass."""
        while True:
            yield from rows[generator.permutation(rows.shape[0])]

    def forever(self, seed: int) -> Iterator[Batch]:
        """Iterate balanced batches without end.

        Args:
            seed: Seed of the sampling generator.

        Yields:
            Batches with exactly ``positives_per_batch`` positive windows each.
        """
        generator = np.random.default_rng(seed)
        positives = self._stream(self._positives, generator)
        negatives = self._stream(self._negatives, generator)
        negatives_per_batch = self.batch_size - self.positives_per_batch
        while True:
            rows = np.stack(
                [next(positives) for _ in range(self.positives_per_batch)]
                + [next(negatives) for _ in range(negatives_per_batch)]
            )
            self.positives_seen += self.positives_per_batch
            yield self._gather(rows[generator.permutation(rows.shape[0])])
