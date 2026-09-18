"""The joint arm's windows (ADR-0025): mixture pretraining draws and tail-anchored probe windows.

**Pretraining.** A joint arm reads three streams in a declared ratio (``joint_v1.yaml``). Every
pretraining window is 2,048 tokens:

- ``tel``: the M1 shards, a window starting on a step every ``window_stride_steps`` steps and ending
  inside its run (:func:`faultline.evaluation.variance_probe.tel_windows`, unchanged).
- ``txt``: the narrative shards at joint ids, **tiled**: windows start every 2,048 tokens of a
  shard and end inside it. A pass reads every token at most once, so "txt is seen once" is
  literal. The few hundred tokens after the last whole tile of each shard are not read.
- ``tel+status``: the ``tel_status_<convention>`` shards, a window starting at a step's ``<sep>``
  every ``window_stride_steps`` steps and ending inside its run, as the builder counts them
  (``mixture_shards.windows_in_run``).

:class:`MixtureSampler` fixes which stream each window comes from with a seed-independent
largest-deficit schedule, so after ``n`` windows each stream is within one window of its share.
Each stream then draws from its own seeded, shuffled passes. The ``tel`` stream is shuffled by
``default_rng(seed)``, the generator ``pretrain_tel`` uses. A ``tel``-only arm therefore draws
exactly ``pretrain_tel``'s windows, in its order, until the end of the first pass over the
``tel`` windows. After that ``pretrain_tel`` skips the pass's last ``windows mod batch`` windows
and this sampler does not. At the registered budget no pass ends: 24,416 windows are drawn from
about 770,000.

**Probe windows, ADR-0025 §2 (``tail_anchored_2048``).** A probe window ends at the last token of
step ``t``, the M1 window's end step, messages included. It holds the ``tel+status`` stream back
to the M1 window's first step ``t - 143`` at most. Whole leading steps, with their messages, are
dropped until at most 2,048 tokens remain, so the window starts at a ``<sep>``. If step ``t``
alone exceeds 2,048 tokens, the window is its last 2,048 tokens and is **head-cut**. Every
window is built from an M1 window-index row, so its key, label, year and end step are M1's.
Windows are right-padded with ``<pad>``, and the risk head reads the last real position.

**R2 (ADR-0025 §3).** The same rule over the stream with every provider ``Stop`` message
removed. :func:`drop_messages` removes the messages, and the window rule is applied afterwards.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import torch

from faultline.paths import ProjectPaths
from faultline.tokenizers.layout import SPECIAL_TOKENS
from faultline.training.mixture import STREAMS, StreamName
from faultline.training.windows import BalancedWindowSampler, Batch, WindowSampler, WindowSet

#: Structural ids the rule reads (ADR-0003 layout).
PAD_ID = SPECIAL_TOKENS.index("<pad>")
SEP_ID = SPECIAL_TOKENS.index("<sep>")
TXT_OPEN_ID = SPECIAL_TOKENS.index("<txt>")
TXT_CLOSE_ID = SPECIAL_TOKENS.index("</txt>")

#: The registered probe window rule's name (``h1_arms_v0.yaml``, ``probe.window_rule``).
TAIL_ANCHORED = "tail_anchored_2048"


# =====================================================================================
# the tel+status stream: steps and messages
# =====================================================================================


def step_offsets(stream: np.ndarray) -> np.ndarray:
    """The token offset of every step of a ``tel+status`` stream.

    ``<sep>`` opens every step and occurs nowhere else: text ids are at least 1,184 and the
    message wrappers are ``<txt>`` and ``</txt>`` (F6-R recon, Q1a).

    Args:
        stream: The stream's tokens.

    Returns:
        Per step, the offset of its ``<sep>``, ascending.
    """
    return np.flatnonzero(np.asarray(stream) == SEP_ID).astype(np.int64)


def message_spans(stream: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Every message's token span, in stream order.

    Args:
        stream: The stream's tokens.

    Returns:
        Per message, the offset of its ``<txt>`` and one past its ``</txt>``.

    Raises:
        ValueError: If the wrappers do not pair up.
    """
    tokens = np.asarray(stream)
    opens = np.flatnonzero(tokens == TXT_OPEN_ID).astype(np.int64)
    closes = np.flatnonzero(tokens == TXT_CLOSE_ID).astype(np.int64) + 1
    if opens.size != closes.size or np.any(closes <= opens):
        raise ValueError(f"{opens.size} <txt> against {closes.size} </txt>: wrappers do not pair")
    if opens.size > 1 and np.any(opens[1:] < closes[:-1]):
        raise ValueError("a message opens before the previous one closes")
    return opens, closes


def drop_messages(stream: np.ndarray, dropped: np.ndarray) -> np.ndarray:
    """The stream with the flagged messages removed, every other token kept in order.

    Args:
        stream: The stream's tokens.
        dropped: Per message in stream order, whether it is removed.

    Returns:
        The filtered tokens, as a new array.

    Raises:
        ValueError: If there is not one flag per message.
    """
    tokens = np.asarray(stream)
    opens, closes = message_spans(tokens)
    if dropped.shape != opens.shape:
        raise ValueError(f"{dropped.size} flags for {opens.size} messages")
    keep = np.ones(tokens.size, dtype=bool)
    removed = np.zeros(tokens.size + 1, dtype=np.int64)
    np.add.at(removed, opens[dropped], 1)
    np.add.at(removed, closes[dropped], -1)
    keep &= np.cumsum(removed[:-1]) == 0
    return tokens[keep]


def step_message_counts(stream: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    """Per step, how many messages follow it in the stream."""
    opens, _ = message_spans(stream)
    return np.bincount(
        np.searchsorted(offsets, opens, side="right") - 1, minlength=offsets.size
    ).astype(np.int64)


# =====================================================================================
# ADR-0025 §2: the tail-anchored rule
# =====================================================================================


@dataclass(frozen=True)
class TailAnchored:
    """Per window, where the tail-anchored rule puts it in the stream.

    Attributes:
        first: The window's first token.
        length: Real (unpadded) tokens in the window, at most the context.
        steps_retained: Whole telemetry steps in the window; 0 when head-cut.
        head_cut: Whether step ``t`` alone exceeded the context.
        status_tokens: Message tokens in the window, wrappers included.
    """

    first: np.ndarray
    length: np.ndarray
    steps_retained: np.ndarray
    head_cut: np.ndarray
    status_tokens: np.ndarray


def tail_anchored(
    offsets: np.ndarray,
    stream_tokens: int,
    ends: np.ndarray,
    context_steps: int,
    context: int,
    tokens_per_step: int,
) -> TailAnchored:
    """Apply ADR-0025 §2's rule to every window end.

    Args:
        offsets: Per step, its ``<sep>`` offset in the stream (:func:`step_offsets`).
        stream_tokens: Tokens in the stream.
        ends: Per window, its end step ``t``: an index into ``offsets``.
        context_steps: Steps an M1 window holds, 144: the window reaches back to
            ``t - context_steps + 1`` at most.
        context: The window's token budget, 2,048.
        tokens_per_step: Telemetry tokens a step contributes, 13.

    Returns:
        Each window's span, retained steps, head cut and message tokens.

    Raises:
        ValueError: If an end step is not a step of the stream, or its window would reach
            before the stream's first step.
    """
    ends = np.asarray(ends, dtype=np.int64)
    if ends.size and (ends.min() < context_steps - 1 or ends.max() >= offsets.size):
        raise ValueError(f"window ends outside {context_steps - 1}..{offsets.size - 1}")
    after = np.append(offsets, stream_tokens)
    stop = after[ends + 1]
    earliest = ends - context_steps + 1
    fits = np.searchsorted(offsets, stop - context, side="left")
    start_step = np.maximum(fits, earliest)
    head_cut = start_step > ends
    first = np.where(head_cut, stop - context, offsets[np.minimum(start_step, ends)])
    length = stop - first
    steps = np.where(head_cut, 0, ends - start_step + 1)
    # A head-cut window keeps step t's telemetry only where it reaches past the cut.
    telemetry = np.where(
        head_cut,
        np.clip(offsets[ends] + tokens_per_step - first, 0, tokens_per_step),
        steps * tokens_per_step,
    )
    return TailAnchored(
        first=first.astype(np.int64),
        length=length.astype(np.int64),
        steps_retained=steps.astype(np.int64),
        head_cut=head_cut,
        status_tokens=(length - telemetry).astype(np.int64),
    )


@dataclass
class JointWindowSet(WindowSet):
    """An M1 window set, re-framed over the ``tel+status`` stream by the tail-anchored rule.

    The inherited fields are the M1 set's own (key, end steps, labels, years), so scores on
    these windows pair row for row with scores on the M1 windows. ``tokens`` is the
    ``tel+status`` stream, not the M1 shard.

    Attributes:
        context: Tokens a window is padded to.
        first: Per window, its first token in ``tokens``.
        length: Per window, its real tokens.
        steps_retained: Per window, whole telemetry steps kept.
        head_cut: Per window, whether step ``t`` alone exceeded the context.
        status_tokens: Per window, message tokens kept.
    """

    context: int = 2048
    first: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    length: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    steps_retained: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    head_cut: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    status_tokens: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))

    @classmethod
    def frame(
        cls,
        m1: WindowSet,
        stream: np.ndarray,
        context_steps: int,
        context: int,
        tokens_per_step: int,
        m1_steps: int,
    ) -> JointWindowSet:
        """Re-frame an M1 window set over a ``tel+status`` stream.

        Args:
            m1: The M1 windows: their end steps, labels and years are kept.
            stream: The ``tel+status`` stream of the same shard key.
            context_steps: Steps an M1 window holds.
            context: The window's token budget.
            tokens_per_step: Telemetry tokens a step contributes.
            m1_steps: Steps in the M1 shard, which the stream must hold too.

        Returns:
            The re-framed windows.

        Raises:
            ValueError: If the stream does not hold the M1 shard's steps.
        """
        offsets = step_offsets(stream)
        if offsets.size != m1_steps:
            raise ValueError(f"{m1.key}: {offsets.size} steps in the stream, {m1_steps} in M1")
        span = tail_anchored(
            offsets, int(np.asarray(stream).size), m1.ends, context_steps, context, tokens_per_step
        )
        return cls(
            key=m1.key,
            tokens=stream,  # type: ignore[arg-type]
            starts=m1.starts,
            ends=m1.ends,
            labels=m1.labels,
            years=m1.years,
            context=context,
            first=span.first,
            length=span.length,
            steps_retained=span.steps_retained,
            head_cut=span.head_cut,
            status_tokens=span.status_tokens,
        )


def gather_padded(sets: Sequence[WindowSet], rows: np.ndarray, labelled: bool) -> Batch:
    """Copy tail-anchored windows out of their streams, right-padded with ``<pad>``.

    Args:
        sets: The window sets, each a :class:`JointWindowSet`.
        rows: ``(batch, 2)`` of set index and window index.
        labelled: Whether to read the labels.

    Returns:
        The padded tokens, the labels and the set index of each window.
    """
    context = max(int(s.context) for s in sets if isinstance(s, JointWindowSet))
    out = np.full((rows.shape[0], context), PAD_ID, dtype=np.int64)
    labels = np.zeros(rows.shape[0], dtype=np.float32)
    for position, (which, row) in enumerate(rows):
        window = sets[int(which)]
        assert isinstance(window, JointWindowSet)
        first, length = int(window.first[row]), int(window.length[row])
        out[position, :length] = window.tokens[first : first + length]
        if labelled:
            labels[position] = window.labels[row]
    return torch.from_numpy(out), torch.from_numpy(labels), rows[:, 0]


class JointWindowSampler(WindowSampler):
    """:class:`WindowSampler` over tail-anchored windows: same order, padded windows."""

    def _gather(self, rows: np.ndarray) -> Batch:
        return gather_padded(self.sets, rows, self.labelled)


class JointBalancedSampler(BalancedWindowSampler):
    """:class:`BalancedWindowSampler` over tail-anchored windows.

    Built from the same sets in the same order as the M1 balanced sampler, it draws the same
    (set, row) sequence at the same seed: only the windows' framing differs.
    """

    def _gather(self, rows: np.ndarray) -> Batch:
        return gather_padded(self.sets, rows, True)


#: ADR-0025 §3's window variants: every status row (R0), or every ``Stop`` row removed (R2).
StatusRows = Literal["all", "no_stop"]


@dataclass
class TelStatusStreams:
    """The ``tel+status`` shards a tail-anchored window is read from, opened once per key.

    Attributes:
        root: The ``tel_status_<convention>`` directory of the joint shards.
        m1_steps: Per shard key, the M1 shard's step count, which the stream must match.
        context_steps: Steps an M1 window holds (144).
        tokens_per_step: Telemetry tokens a step contributes (13).
        context: The window's token budget (2,048).
        status_rows: ``all`` (R0) or ``no_stop`` (R2).
        dropped: Per shard key, per message in stream order, whether R2 removes it. Required
            for ``no_stop``.
    """

    root: Path
    m1_steps: dict[str, int]
    context_steps: int
    tokens_per_step: int
    context: int
    status_rows: StatusRows = "all"
    dropped: dict[str, np.ndarray] = field(default_factory=dict)
    _streams: dict[str, np.ndarray] = field(default_factory=dict)

    def stream(self, key: str) -> np.ndarray:
        """One shard's stream: memory-mapped under R0, filtered in memory under R2.

        Raises:
            KeyError: Under R2, if the key has no message flags.
        """
        if key not in self._streams:
            tokens = np.memmap(self.root / f"{key}.bin", dtype=np.uint16, mode="r")
            if self.status_rows == "no_stop":
                tokens = drop_messages(tokens, self.dropped[key])  # type: ignore[assignment]
            self._streams[key] = tokens
        return self._streams[key]

    def frame(self, m1: WindowSet) -> JointWindowSet:
        """Re-frame one M1 window set over its key's stream."""
        return JointWindowSet.frame(
            m1,
            self.stream(m1.key),
            self.context_steps,
            self.context,
            self.tokens_per_step,
            self.m1_steps[m1.key],
        )


def stop_flags(
    paths: ProjectPaths, root: Path, sources: Sequence[str], stop_status: str = "Stop"
) -> dict[str, np.ndarray]:
    """Per shard key, whether each message in stream order is a provider ``Stop`` row (R2).

    The messages are re-derived by the builder's walk and checked against the stream: the
    same count, each following the same step. A mismatch is refused, never guessed around.

    Args:
        paths: Resolved project paths.
        root: The ``tel_status_<convention>`` directory.
        sources: Status sources to read.
        stop_status: The ``provider_status`` value removed.

    Returns:
        Per key, one flag per message.

    Raises:
        ValueError: If the re-derived messages do not follow the stream's steps exactly.
    """
    from faultline.data.joint.mixture_shards import messages_in_stream_order

    flags: dict[str, np.ndarray] = {}
    for source in sources:
        for key, messages in messages_in_stream_order(paths, source, ["provider_status"]).items():
            path = root / f"{key}.bin"
            if not path.is_file():
                continue
            stream = np.memmap(path, dtype=np.uint16, mode="r")
            offsets = step_offsets(stream)
            opens, _ = message_spans(stream)
            found = np.searchsorted(offsets, opens, side="right") - 1
            if not np.array_equal(found, messages.steps):
                raise ValueError(f"{key}: re-derived messages do not follow the stream's steps")
            flags[key] = messages.columns["provider_status"].astype(str) == stop_status
    return flags


def last_real_index(tokens: torch.Tensor, pad_id: int = PAD_ID) -> torch.Tensor:
    """Per right-padded window, the index of its last non-``<pad>`` token.

    Args:
        tokens: ``(batch, time)`` token ids, right-padded.
        pad_id: The padding id.

    Returns:
        ``(batch,)`` indices.
    """
    return (tokens != pad_id).sum(dim=1).clamp(min=1) - 1


# =====================================================================================
# mixture pretraining
# =====================================================================================


def tile_starts(tokens: int, context: int) -> np.ndarray:
    """Starts of the whole ``context``-token tiles of a stream of ``tokens`` tokens."""
    return np.arange(0, tokens - context + 1, context, dtype=np.int64)


def run_step_starts(
    offsets: np.ndarray, run_first: int, run_tokens: int, stride: int, context: int
) -> np.ndarray:
    """Window starts of one run: every ``stride``-th step's ``<sep>``, ending inside the run.

    Args:
        offsets: The stream's step offsets.
        run_first: The run's first token.
        run_tokens: Tokens in the run.
        stride: Steps between window starts.
        context: Window length.

    Returns:
        The admissible starts, as stream offsets.
    """
    lo, hi = np.searchsorted(offsets, [run_first, run_first + run_tokens], side="left")
    starts = offsets[lo:hi:stride]
    return starts[starts + context <= run_first + run_tokens]


def mixture_schedule(shares: dict[StreamName, float], windows: int) -> np.ndarray:
    """Which stream each window is drawn from: the largest deficit first, ties in stream order.

    Seed-independent, so the ratio is a property of the configuration: after ``n`` windows,
    each stream is within one window of ``share * n``.

    Args:
        shares: Per stream, its share; the shares sum to 1.
        windows: Windows to schedule.

    Returns:
        Per window, the stream's position in ``STREAMS``.
    """
    names = [s for s in STREAMS if shares.get(s, 0.0) > 0.0]
    share = np.array([shares[s] for s in names])
    counts = np.zeros(len(names), dtype=np.int64)
    out = np.empty(windows, dtype=np.int64)
    for i in range(windows):
        pick = int(np.argmax(share * (i + 1) - counts))
        counts[pick] += 1
        out[i] = STREAMS.index(names[pick])
    return out


@dataclass
class StreamWindows:
    """Fixed-length windows of one stream: memory-mapped shards and ``(shard, first token)``.

    Attributes:
        streams: Per shard key, its tokens.
        keys: Shard keys, in index order.
        index: ``(windows, 2)`` of key position and first token.
        context: Tokens per window.
        train_tokens: Tokens the stream's shards hold, for the passes figure.
    """

    streams: dict[str, np.ndarray]
    keys: list[str]
    index: np.ndarray
    context: int
    train_tokens: int

    def __len__(self) -> int:
        """Windows in one pass."""
        return int(self.index.shape[0])

    def rows(self, generator: np.random.Generator) -> Iterator[np.ndarray]:
        """Index rows in shuffled passes without end, without replacement inside a pass."""
        while True:
            yield from self.index[generator.permutation(len(self))]

    def window(self, row: np.ndarray) -> np.ndarray:
        """One window's tokens."""
        first = int(row[1])
        return np.asarray(self.streams[self.keys[int(row[0])]][first : first + self.context])


@dataclass
class MixtureSampler:
    """Pretraining batches over a mixture's streams, in its declared ratio.

    Attributes:
        pools: Per stream, its windows.
        shares: Per stream, its share of the windows.
        seed: The run's seed.
        batch: Windows per batch.
        drawn: Per stream, windows drawn so far.
        drawn_rows: Per stream, every row drawn, when ``keep_rows`` is set.
        keep_rows: Record every drawn row, for tests.
    """

    pools: dict[StreamName, StreamWindows]
    shares: dict[StreamName, float]
    seed: int
    batch: int
    drawn: dict[StreamName, int] = field(default_factory=dict)
    drawn_rows: dict[StreamName, list[tuple[int, int]]] = field(default_factory=dict)
    keep_rows: bool = False

    def generator(self, stream: StreamName) -> np.random.Generator:
        """A stream's shuffling generator; ``tel`` gets ``pretrain_tel``'s ``default_rng(seed)``."""
        if stream == "tel":
            return np.random.default_rng(self.seed)
        return np.random.default_rng([self.seed, STREAMS.index(stream)])

    def plan(self, windows: int) -> dict[StreamName, int]:
        """Windows each stream contributes to a run of ``windows`` windows."""
        schedule = mixture_schedule(self.shares, windows)
        return {s: int((schedule == STREAMS.index(s)).sum()) for s in STREAMS if s in self.pools}

    def refuse_repeats(self, windows: int) -> None:
        """Refuse a budget under which any stream would start a second pass.

        Raises:
            ValueError: If a stream's planned windows exceed one pass.
        """
        for stream, planned in self.plan(windows).items():
            if planned > len(self.pools[stream]):
                raise ValueError(
                    f"{stream}: {planned:,} windows planned against {len(self.pools[stream]):,} "
                    "in one pass; the stream would repeat"
                )

    def forever(self) -> Iterator[Batch]:
        """Batches without end, each window from the scheduled stream.

        Yields:
            The tokens, zero labels (pretraining reads none) and each window's stream position.
        """
        sources = {s: self.pools[s].rows(self.generator(s)) for s in self.pools}
        names = [s for s in STREAMS if s in self.pools]
        share = np.array([self.shares[s] for s in names])
        counts = np.zeros(len(names), dtype=np.int64)
        self.drawn = {s: 0 for s in names}
        self.drawn_rows = {s: [] for s in names}
        context = next(iter(self.pools.values())).context
        while True:
            out = np.empty((self.batch, context), dtype=np.int64)
            which = np.empty(self.batch, dtype=np.int64)
            for position in range(self.batch):
                total = int(counts.sum())
                pick = int(np.argmax(share * (total + 1) - counts))
                counts[pick] += 1
                stream = names[pick]
                row = next(sources[stream])
                out[position] = self.pools[stream].window(row)
                which[position] = STREAMS.index(stream)
                self.drawn[stream] += 1
                if self.keep_rows:
                    self.drawn_rows[stream].append((int(row[0]), int(row[1])))
            yield torch.from_numpy(out), torch.zeros(self.batch), which
