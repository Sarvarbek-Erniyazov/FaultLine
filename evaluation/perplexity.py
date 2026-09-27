"""Per-stream perplexity of the served backbone on held-out data (Course Lesson 11 output).

**What is scored.** The joint seed-1 backbone read as a language model, on the three streams it
was pretrained on, each on held-out splits the pretraining never drew from:

- ``txt``: every whole 2,048-token tile of the NRC/PHMSA validation and test shards;
- ``tel``: 2,048-token telemetry windows of Kelmarsh and Penmanshiel, validation (2021) and test
  (2022 on) separately, every 6th step start, drawn as the pretraining's own validation read was
  (:func:`faultline.evaluation.variance_probe.tel_windows`);
- ``tel+status``: the same sites' telemetry with the normalized status messages interleaved,
  windows starting at a step as the pretraining pool's (:func:`run_step_starts`).

A deterministic cap keeps each stream-split near 1M predicted tokens: at most
:data:`WINDOWS_PER_SOURCE` windows a source, a seeded draw without replacement. N is recorded.

**Which positions count.** Every target is classed by what the vocabulary says it is: a
telemetry value (one of the 256 shared bin ids, or ``<nan>``), a text token, or a structural
token (``<sep>``, ``<txt>``, ``</txt>``, ...). Structural targets are excluded and counted.

**Metrics.** Mean NLL in nats and PPL = exp(mean NLL), two ways: over the full 33,952-id
softmax (the model's own probability, as it was trained), and renormalised over the ids valid
at that position (257 for a value, 32,768 for text), which is what the reference points are
measured over. Bits per byte for text targets only: NLL / ln 2 over the UTF-8 bytes of those
tokens.

**Reference points, on the same targets.** Uniform over the valid ids; a unigram over the
stream's own train split (add-one smoothing within the class); and a randomly initialised
backbone of the same spec (seed :data:`RANDOM_INIT_SEED`).
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
import torch
from torch import Tensor, nn

from faultline.evaluation.variance_probe import tel_windows
from faultline.model.transformer import TelemetryDecoder
from faultline.tokenizers.layout import BIN_OFFSET, SPECIAL_TOKENS, TEXT_OFFSET
from faultline.training.joint_windows import run_step_starts, step_offsets, tile_starts
from faultline.training.windows import ShardSet

#: ``<nan>``, the value token for a missing reading.
NAN_ID = SPECIAL_TOKENS.index("<nan>")

#: Windows per source and stream-split: 245 x 2 sources x 2,047 targets ~ 1.0M.
WINDOWS_PER_SOURCE = 245

#: Seeds: the window draw, and the random-init reference backbone.
WINDOW_SEED = 20260927
RANDOM_INIT_SEED = 20260927

#: Target classes.
EXCLUDED, VALUE, TEXT = 0, 1, 2
CLASS_NAMES = {VALUE: "value", TEXT: "text"}

#: What every text and tel+status number is (A4).
NEW_MEASUREMENT = "new course-lesson measurement; no logged comparison exists"


def mean_nll_of_probabilities(probabilities: Sequence[float]) -> float:
    """Mean negative log-likelihood of the probabilities given to the observed tokens.

    Args:
        probabilities: Per token, the probability the model gave it.

    Returns:
        The mean NLL in nats.
    """
    return float(np.mean([-math.log(p) for p in probabilities]))


def perplexity(mean_nll: float) -> float:
    """PPL = exp(mean NLL)."""
    return math.exp(mean_nll)


def target_classes(targets: np.ndarray, n_bins: int, n_text: int) -> np.ndarray:
    """Class every target: a telemetry value, a text token, or structural (excluded).

    Args:
        targets: Global ids.
        n_bins: Bins in use (256).
        n_text: Text ids in use (32,768).

    Returns:
        Per target, :data:`VALUE`, :data:`TEXT` or :data:`EXCLUDED`.
    """
    out = np.full(targets.shape, EXCLUDED, dtype=np.int64)
    out[((targets >= BIN_OFFSET) & (targets < BIN_OFFSET + n_bins)) | (targets == NAN_ID)] = VALUE
    out[(targets >= TEXT_OFFSET) & (targets < TEXT_OFFSET + n_text)] = TEXT
    return out


def valid_ids(kind: int, n_bins: int, n_text: int) -> np.ndarray:
    """The ids valid at a position of a class: 256 bins and ``<nan>``, or the text block."""
    if kind == VALUE:
        return np.concatenate([[NAN_ID], np.arange(BIN_OFFSET, BIN_OFFSET + n_bins)])
    return np.arange(TEXT_OFFSET, TEXT_OFFSET + n_text)


def token_nll(
    logits: Tensor, targets: Tensor, classes: Tensor, valid: dict[int, Tensor]
) -> tuple[Tensor, Tensor]:
    """Per-target NLL over the full softmax and renormalised over the class's valid ids.

    Args:
        logits: ``(..., vocab)``.
        targets: ``(...)`` global ids.
        classes: ``(...)`` target classes.
        valid: Per class, its valid ids.

    Returns:
        ``(full, restricted)``, each ``(...)`` in float64; restricted is 0 where excluded. The
        log-sum-exps are float32 (a float64 copy of 2,047 x 33,952 logits a window is too large);
        the differences are summed in float64.
    """
    logits = logits.float()
    chosen = logits.gather(-1, targets.unsqueeze(-1)).squeeze(-1)
    full = (torch.logsumexp(logits, dim=-1) - chosen).double()
    restricted = torch.zeros_like(full)
    for kind, ids in valid.items():
        mask = classes == kind
        if bool(mask.any()):
            normaliser = torch.logsumexp(logits.index_select(-1, ids), dim=-1)
            restricted[mask] = (normaliser - chosen)[mask].double()
    return full, restricted


@dataclass
class Tally:
    """Sums of one class's NLLs under every scorer."""

    tokens: int = 0
    bytes: int = 0
    sums: dict[str, float] = field(default_factory=dict)

    def add(self, name: str, value: float) -> None:
        """Add to one scorer's sum."""
        self.sums[name] = self.sums.get(name, 0.0) + value

    def report(self, text: bool) -> dict[str, Any]:
        """Mean NLL, PPL and (text only) bits per byte of every scorer."""
        out: dict[str, Any] = {"tokens": self.tokens}
        if text:
            out["bytes"] = self.bytes
        for name, total in sorted(self.sums.items()):
            mean = total / self.tokens if self.tokens else math.nan
            entry = {"mean_nll": mean, "ppl": perplexity(mean) if self.tokens else math.nan}
            if text and self.bytes:
                entry["bits_per_byte"] = total / math.log(2) / self.bytes
            out[name] = entry
        return out


@dataclass(frozen=True)
class Windows:
    """Fixed-length windows over memory-mapped streams.

    Attributes:
        streams: Per key, the tokens.
        keys: Keys in order.
        index: ``(n, 2)`` rows of (key position, start).
        context: Window length.
    """

    streams: dict[str, np.ndarray]
    keys: list[str]
    index: np.ndarray
    context: int

    def batches(self, size: int) -> Iterator[np.ndarray]:
        """``(b, context)`` int64 token batches, in index order."""
        for first in range(0, len(self.index), size):
            rows = self.index[first : first + size]
            yield np.stack(
                [
                    np.asarray(self.streams[self.keys[k]][s : s + self.context], dtype=np.int64)
                    for k, s in rows
                ]
            )


def _capped(starts: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    if starts.size > WINDOWS_PER_SOURCE:
        starts = np.sort(rng.choice(starts, WINDOWS_PER_SOURCE, replace=False))
    return starts


def txt_windows(joint_root: Path, split: str, context: int) -> Windows:
    """Every whole tile of each text source's split, capped per source."""
    files = sorted((joint_root / "txt").glob(f"*__{split}.bin"))
    streams = {f.name[: -len(".bin")]: np.memmap(f, dtype=np.uint16, mode="r") for f in files}
    keys = list(streams)
    rng = np.random.default_rng(WINDOW_SEED)
    starts = [_capped(tile_starts(int(streams[k].size), context), rng) for k in keys]
    rows = [np.stack([np.full(s.size, i), s], axis=1) for i, s in enumerate(starts)]
    return Windows(dict(streams), keys, np.concatenate(rows).astype(np.int64), context)


def telemetry_windows(
    joint_root: Path,
    telemetry: ShardSet,
    split: str,
    sources: list[str],
    context: int,
    stride: int,
) -> Windows:
    """``tel`` windows through the pretraining's own reader, capped per source."""
    read = tel_windows(
        joint_root,
        telemetry,
        split,
        sources,
        context,
        stride,
        limit=WINDOWS_PER_SOURCE,
        seed=WINDOW_SEED,
    )
    return Windows(dict(read.streams), list(read.keys), np.asarray(read.index), context)


def tel_status_windows(
    joint_root: Path, convention: str, split: str, sources: list[str], context: int, stride: int
) -> Windows:
    """``tel+status`` windows starting at a step, as the pretraining pool's, capped per source."""
    directory = joint_root / f"tel_status_{convention}"
    keys = [f"{source}__{split}" for source in sources]
    streams = {k: np.memmap(directory / f"{k}.bin", dtype=np.uint16, mode="r") for k in keys}
    rng = np.random.default_rng(WINDOW_SEED)
    rows = []
    for i, key in enumerate(keys):
        offsets = step_offsets(streams[key])
        runs = pq.read_table(directory / f"{key}.runs.parquet").to_pandas()
        starts = np.concatenate(
            [
                run_step_starts(offsets, int(first), int(tokens), stride, context)
                for first, tokens in zip(runs["first_token"], runs["tokens"], strict=True)
            ]
        )
        chosen = _capped(starts, rng)
        rows.append(np.stack([np.full(chosen.size, i), chosen], axis=1))
    return Windows(dict(streams), keys, np.concatenate(rows).astype(np.int64), context)


def unigram_log_probs(counts: np.ndarray, n_bins: int, n_text: int) -> dict[int, np.ndarray]:
    """Per class, log-probabilities over the whole vocabulary (valid ids only are finite).

    Add-one smoothing within the class: ``p(i) = (c_i + 1) / (sum_class c + |class|)``.

    Args:
        counts: Per global id, its train-split count.
        n_bins: Bins in use.
        n_text: Text ids in use.

    Returns:
        Per class, a vocabulary-length array.
    """
    out = {}
    for kind in (VALUE, TEXT):
        ids = valid_ids(kind, n_bins, n_text)
        table = np.full(counts.size, -np.inf)
        table[ids] = np.log((counts[ids] + 1.0) / (counts[ids].sum() + ids.size))
        out[kind] = table
    return out


def train_counts(paths: Sequence[Path], vocab: int) -> np.ndarray:
    """Per global id, its count over the given uint16 streams."""
    total = np.zeros(vocab, dtype=np.int64)
    for path in paths:
        total += np.bincount(np.memmap(path, dtype=np.uint16, mode="r"), minlength=vocab)[:vocab]
    return total


def random_init_backbone(template: TelemetryDecoder) -> TelemetryDecoder:
    """A backbone of the template's spec, as constructed after ``manual_seed``."""
    torch.manual_seed(RANDOM_INIT_SEED)
    return TelemetryDecoder(template.spec).float().eval()


@torch.inference_mode()
def score_windows(
    models: dict[str, nn.Module],
    windows: Windows,
    unigram: dict[int, np.ndarray],
    byte_lengths: np.ndarray,
    n_bins: int,
    n_text: int,
    device: torch.device,
    batch: int = 2,
) -> dict[str, Any]:
    """Score one stream-split under every model and reference.

    Args:
        models: Name to backbone (``model``, ``random_init``), on ``device``, float32.
        windows: The windows.
        unigram: :func:`unigram_log_probs` of the stream's train split.
        byte_lengths: Per local text id, its UTF-8 byte length.
        n_bins: Bins in use.
        n_text: Text ids in use.
        device: Where the models are.
        batch: Windows per forward pass.

    Returns:
        Windows, target counts (scored and excluded by name) and per class every scorer's
        metrics.
    """
    valid = {k: torch.as_tensor(valid_ids(k, n_bins, n_text), device=device) for k in CLASS_NAMES}
    tallies = {k: Tally() for k in CLASS_NAMES}
    excluded = np.zeros(len(SPECIAL_TOKENS) + 1, dtype=np.int64)
    for tokens_np in windows.batches(batch):
        targets_np = tokens_np[:, 1:]
        classes_np = target_classes(targets_np, n_bins, n_text)
        other = targets_np[classes_np == EXCLUDED]
        excluded += np.bincount(
            np.where(other < len(SPECIAL_TOKENS), other, len(SPECIAL_TOKENS)),
            minlength=excluded.size,
        )
        tokens = torch.from_numpy(tokens_np).to(device)
        targets = tokens[:, 1:]
        classes = torch.from_numpy(classes_np).to(device)
        for kind, tally in tallies.items():
            mask = classes_np == kind
            tally.tokens += int(mask.sum())
            chosen = targets_np[mask]
            tally.add("uniform", float(mask.sum()) * math.log(valid[kind].numel()))
            tally.add("unigram", float(-unigram[kind][chosen].sum()))
            if kind == TEXT:
                tally.bytes += int(byte_lengths[chosen - TEXT_OFFSET].sum())
        for name, model in models.items():
            decoder: Any = model
            hidden = decoder(tokens)[:, :-1]
            full, restricted = token_nll(decoder.logits(hidden), targets, classes, valid)
            for kind, tally in tallies.items():
                mask = classes == kind
                tally.add(name, float(full[mask].sum()))
                tally.add(f"{name}_valid_only", float(restricted[mask].sum()))
    names = [*SPECIAL_TOKENS, "other"]
    return {
        "windows": len(windows.index),
        "targets_scored": {CLASS_NAMES[k]: t.tokens for k, t in tallies.items()},
        "targets_excluded": {names[i]: int(n) for i, n in enumerate(excluded) if n},
        "classes": {
            CLASS_NAMES[k]: t.report(text=k == TEXT) for k, t in tallies.items() if t.tokens
        },
    }


def unigram_versus_uniform(
    unigram: dict[int, np.ndarray], n_bins: int, n_text: int
) -> dict[str, float]:
    """How far the telemetry value unigram is from uniform: KL and the probability range."""
    ids = valid_ids(VALUE, n_bins, n_text)
    log_p = unigram[VALUE][ids]
    p = np.exp(log_p)
    uniform = 1.0 / ids.size
    return {
        "valid_ids": int(ids.size),
        "kl_unigram_to_uniform_nats": float(np.sum(p * (log_p - math.log(uniform)))),
        "entropy_nats": float(-np.sum(p * log_p)),
        "uniform_entropy_nats": math.log(ids.size),
        "max_probability_over_uniform": float(p.max() / uniform),
        "min_probability_over_uniform": float(p.min() / uniform),
        "nan_probability": float(math.exp(unigram[VALUE][NAN_ID])),
    }
