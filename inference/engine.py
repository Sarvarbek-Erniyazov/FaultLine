"""The serving engine: the research model loaded once, on CPU, for ranking and text (Lesson 11).

**What it serves.** One exported file, ``checkpoints/model.pt`` (:mod:`inference.export`): the
joint seed-1 backbone at its final step and its ADR-0026 (d) ``last_plus_text`` head, the prior
constant the record adds to every logit, and a small rank table of the seed-1 test scores. It is
loaded once, put in evaluation mode, and every call runs under ``torch.inference_mode`` in float32
on CPU.

**Nothing is re-implemented.** A raw 24 h window becomes model input through faultline's own
functions, in the shard builder's order: :meth:`JointVocab.encode_steps` for the 144 x 12 values,
:func:`attach_steps` and the stream's status convention for the messages,
:func:`interleave` for the step stream, and :func:`tail_anchored` (ADR-0025 §2) for the 2,048-token
window. ``tests/lesson11/test_parity.py`` checks the ids against the evaluation's own windows.

**What the score is.** The corrected logit: the head's logit plus the recorded prior offset,
added in float32 as the record adds it. It is a **ranking score, not a calibrated probability**,
and the percentile says where it falls among the seed-1 test scores.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from faultline.data.joint.mixture_shards import CONVENTIONS, attach_steps, interleave, nanoseconds
from faultline.data.telemetry.schemas import CHANNEL_NAMES
from faultline.model.risk import RiskModel, RiskSpec, TextPositionRule
from faultline.model.transformer import ModelSpec
from faultline.tokenizers.joint import JointVocab
from faultline.tokenizers.layout import TEXT_OFFSET, VocabLayout
from faultline.tokenizers.quantile_bins import QuantileBinTokenizer
from faultline.tokenizers.text_bpe import TextBPETokenizer
from faultline.training.joint_windows import PAD_ID, SEP_ID, tail_anchored
from inference.sampling import SamplingParams, sample_next, seeded_generator

#: What every score is, said wherever a score is shown.
RANKING_NOTE = "ranking score, not a calibrated probability"

#: The export format this engine reads.
FORMAT = "faultline-lesson11-model-v0"

#: One grid step of the telemetry.
STEP = pd.Timedelta(minutes=10)


def sha256_file(path: Path) -> str:
    """The SHA-256 of a file, streamed.

    Args:
        path: The file.

    Returns:
        The hex digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class RankTable:
    """An exact empirical distribution: sorted unique values and cumulative counts.

    The percentile of ``x`` is the mid-rank ``100 * (below + equal / 2) / total``. It was fixed
    as the definition before any parity number was measured.

    Attributes:
        values: Sorted unique values.
        cumulative: Per value, how many observations are at or below it.
    """

    values: np.ndarray
    cumulative: np.ndarray

    @classmethod
    def from_scores(cls, scores: np.ndarray) -> RankTable:
        """Build the table from every observation.

        Args:
            scores: The observations.

        Returns:
            The table.
        """
        values, counts = np.unique(np.asarray(scores, dtype=np.float64), return_counts=True)
        return cls(values=values, cumulative=np.cumsum(counts).astype(np.int64))

    @property
    def total(self) -> int:
        """Observations in the table."""
        return int(self.cumulative[-1]) if self.cumulative.size else 0

    def percentile(self, x: float) -> float:
        """Mid-rank percentile of ``x`` in ``[0, 100]``.

        Args:
            x: The value.

        Returns:
            The percentile.
        """
        left = int(np.searchsorted(self.values, x, side="left"))
        right = int(np.searchsorted(self.values, x, side="right"))
        below = int(self.cumulative[left - 1]) if left > 0 else 0
        upto = int(self.cumulative[right - 1]) if right > 0 else 0
        return 100.0 * (below + (upto - below) / 2.0) / self.total


@dataclass(frozen=True)
class StatusMessage:
    """One timestamped status message, as the provider's status log writes it.

    Attributes:
        start_utc: When it started.
        text: The message.
    """

    start_utc: pd.Timestamp
    text: str


@dataclass(frozen=True)
class RawWindow:
    """A raw 24 h window: 144 ten-minute steps of the 12 channels, and the status messages.

    Attributes:
        values: ``(144, 12)`` floats in :attr:`Engine.channels` order; ``nan`` is missing.
        end_utc: The last step's timestamp, on the 10-minute grid.
        messages: Status messages; those that start after ``end_utc`` are never attached.
    """

    values: np.ndarray
    end_utc: pd.Timestamp
    messages: tuple[StatusMessage, ...] = ()


@dataclass(frozen=True)
class TokenizedWindow:
    """A raw window as the model reads it.

    Attributes:
        ids: ``(context,)`` token ids, right-padded with ``<pad>``.
        length: Real tokens.
        n_status_messages: Messages the window holds after the tail-anchored rule.
        has_text: Whether any text position survives in the window.
        head_cut: Whether step ``t`` alone exceeded the context.
    """

    ids: np.ndarray
    length: int
    n_status_messages: int
    has_text: bool
    head_cut: bool


@dataclass(frozen=True)
class Prediction:
    """One scored window.

    Attributes:
        score: The corrected logit, a ranking score.
        logit: The head's logit before the prior offset.
        percentile: Where the score falls among the seed-1 test scores.
        has_text: Whether the window held any text.
        n_status_messages: Messages in the window.
        time_ms: Wall clock of tokenisation plus forward pass.
        note: :data:`RANKING_NOTE`.
    """

    score: float
    logit: float
    percentile: float
    has_text: bool
    n_status_messages: int
    time_ms: float
    note: str = RANKING_NOTE


@dataclass(frozen=True)
class Generation:
    """One text continuation.

    Attributes:
        text: The decoded continuation.
        token_ids: The emitted ids, global (joint layout); ``<sep>`` is never among them.
        stop_reason: ``sep`` (the model ended the document) or ``max_new_tokens``.
        prompt_tokens: Tokens the prompt encoded to, ``<sep>`` included.
        time_ms: Wall clock.
    """

    text: str
    token_ids: list[int]
    stop_reason: str
    prompt_tokens: int
    time_ms: float


@dataclass
class Engine:
    """The model, its tokenizers and its constants, loaded once.

    Attributes:
        model: The risk model (backbone + (d) head), in evaluation mode, float32.
        vocab: The joint vocabulary.
        prior_offset: The constant added to every logit, as the record adds it.
        scores: The seed-1 test scores' rank table.
        window: The window rule's constants: ``context_steps``, ``context_tokens``,
            ``tokens_per_step``, ``status_convention``.
        meta: Provenance: hashes, sources, the export's own record.
    """

    model: RiskModel
    vocab: JointVocab
    prior_offset: float
    scores: RankTable
    window: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze the model for inference and fix the constants the calls read.

        Raises:
            ValueError: If the window's status convention is not one the shards were built with,
                or the model's vocabulary is not the vocabulary's.
        """
        self.model.eval()
        for parameter in self.model.parameters():
            parameter.requires_grad_(False)
        if self.window["status_convention"] != "normalized":
            # "raw" re-cases through the staged code book, which is not shipped with a model.
            raise ValueError("only the normalized status convention is served")
        if self.model.backbone.spec.vocab_size != self.vocab.size:
            raise ValueError(
                f"model vocabulary {self.model.backbone.spec.vocab_size} is not the joint "
                f"vocabulary {self.vocab.size}"
            )
        text_size = self.vocab.layout.total_size - TEXT_OFFSET
        allowed = torch.zeros(self.vocab.size, dtype=torch.bool)
        allowed[TEXT_OFFSET : TEXT_OFFSET + text_size] = True
        allowed[SEP_ID] = True
        self._allowed = allowed

    # -- loading --------------------------------------------------------------------

    @classmethod
    def load(cls, model_path: Path, tokenizer_dir: Path) -> Engine:
        """Load the exported model and its tokenizers, verifying the tokenizers' hashes.

        Args:
            model_path: ``checkpoints/model.pt``.
            tokenizer_dir: The directory holding the two tokenizer files the export names.

        Returns:
            The engine.

        Raises:
            ValueError: If the file is not this format, or a tokenizer's hash is not the one the
                export recorded.
        """
        payload: dict[str, Any] = torch.load(model_path, map_location="cpu", weights_only=True)
        if payload.get("format") != FORMAT:
            raise ValueError(f"{model_path} is not a {FORMAT} file")
        files = {}
        for role in ("bins", "text"):
            record = payload["tokenizers"][role]
            path = tokenizer_dir / str(record["file"])
            found = sha256_file(path)
            if found != record["sha256"]:
                raise ValueError(f"{path}: sha256 {found} is not the exported {record['sha256']}")
            files[role] = path
        bins = QuantileBinTokenizer.load(files["bins"])
        text = TextBPETokenizer.load(files["text"])
        layout = VocabLayout.from_sizes(text.vocab_size, len(CHANNEL_NAMES), bins.n_bins)
        model = build_model(payload)
        meta = {
            "model_file": model_path.name,
            "model_sha256": sha256_file(model_path),
            "tokenizers": payload["tokenizers"],
            "sources": payload.get("sources", {}),
            "served": payload.get("served", {}),
        }
        return cls(
            model=model,
            vocab=JointVocab(layout, text, bins),
            prior_offset=float(payload["prior_offset"]),
            scores=RankTable(
                values=payload["score_table"]["values"].numpy(),
                cumulative=payload["score_table"]["cumulative"].numpy(),
            ),
            window=dict(payload["window"]),
            meta=meta,
        )

    # -- the window -----------------------------------------------------------------

    @property
    def channels(self) -> list[str]:
        """The 12 channels in the order a raw window's columns are read."""
        assert self.vocab.bin_tokenizer is not None
        return list(self.vocab.bin_tokenizer.channels)

    @property
    def context_steps(self) -> int:
        """Steps in a raw window (144)."""
        return int(self.window["context_steps"])

    def tokenize_window(self, raw: RawWindow) -> TokenizedWindow:
        """A raw window as the model reads it, through faultline's own functions.

        Args:
            raw: The window.

        Returns:
            The tokenized window.

        Raises:
            ValueError: If the values are not ``(144, 12)`` or the end is off the grid.
        """
        steps, channels = self.context_steps, self.channels
        values = np.asarray(raw.values, dtype=np.float64)
        if values.shape != (steps, len(channels)):
            raise ValueError(f"values must be {steps} x {len(channels)}, got {values.shape}")
        end = pd.Timestamp(raw.end_utc)
        end = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
        if end != end.floor("10min"):
            raise ValueError(f"end_utc {end} is not on the 10-minute grid")
        stamps = pd.date_range(end=end, periods=steps, freq=STEP)
        encoded_steps = self.vocab.encode_steps(pd.DataFrame(values, columns=channels))

        # The builder's order: messages by start, stable; attached to the first step at or after
        # the start; kept only where that step is one of the window's.
        messages = sorted(raw.messages, key=lambda m: _utc(m.start_utc))
        convention = CONVENTIONS[str(self.window["status_convention"])]
        if messages:
            attached = attach_steps(
                pd.DatetimeIndex([_utc(m.start_utc) for m in messages]), nanoseconds(stamps)
            )
        else:
            attached = np.zeros(0, dtype=np.int64)
        chosen = np.flatnonzero(attached >= 0)
        order = chosen[np.argsort(attached[chosen], kind="stable")]
        tokens = [
            np.asarray(self.vocab.encode_text(convention(messages[i].text)), dtype=np.int64)
            for i in order
        ]
        stream, offsets = interleave(encoded_steps, attached[order], tokens)

        context = int(self.window["context_tokens"])
        span = tail_anchored(
            offsets,
            int(stream.size),
            np.array([steps - 1]),
            steps,
            context,
            int(self.window["tokens_per_step"]),
        )
        first, length = int(span.first[0]), int(span.length[0])
        ids = np.full(context, PAD_ID, dtype=np.int64)
        ids[:length] = stream[first : first + length]
        opens = int((ids[:length] == self.vocab.special("<txt>")).sum())
        return TokenizedWindow(
            ids=ids,
            length=length,
            n_status_messages=opens,
            has_text=bool(int(span.status_tokens[0]) > 0),
            head_cut=bool(span.head_cut[0]),
        )

    def logit(self, ids: np.ndarray) -> float:
        """The head's logit for one tokenized window, float32 on CPU.

        Args:
            ids: ``(context,)`` token ids.

        Returns:
            The logit.
        """
        with torch.inference_mode():
            out = self.model(torch.from_numpy(np.asarray(ids, dtype=np.int64))[None])
        return float(out.float()[0])

    def corrected(self, logit: float) -> float:
        """The corrected logit, the offset added in float32 as the record adds it.

        Args:
            logit: The head's logit.

        Returns:
            The score.
        """
        return float(np.float32(logit) + np.float32(self.prior_offset))

    def predict(self, raw: RawWindow) -> Prediction:
        """Score one raw window.

        Args:
            raw: The window.

        Returns:
            The score, its percentile and what the window held.
        """
        started = time.perf_counter()
        window = self.tokenize_window(raw)
        logit = self.logit(window.ids)
        score = self.corrected(logit)
        return Prediction(
            score=score,
            logit=logit,
            percentile=self.scores.percentile(score),
            has_text=window.has_text,
            n_status_messages=window.n_status_messages,
            time_ms=(time.perf_counter() - started) * 1000.0,
        )

    # -- text -----------------------------------------------------------------------

    @property
    def allowed_ids(self) -> torch.Tensor:
        """The ids text generation may emit: the text block, and ``<sep>`` to stop."""
        return self._allowed.clone()

    def generate_text(
        self, prompt: str, params: SamplingParams, max_new_tokens: int = 64
    ) -> Generation:
        """Continue a text document, constrained to text ids; ``<sep>`` ends it.

        The prompt is read as the start of a new document of the ``txt`` stream, which is what
        ``<sep>`` before it says.

        Args:
            prompt: The document's opening.
            params: The decoding strategy; its seed seeds the draw.
            max_new_tokens: At most this many tokens are emitted.

        Returns:
            The continuation.

        Raises:
            ValueError: If ``max_new_tokens`` is not positive.
        """
        if max_new_tokens <= 0:
            raise ValueError(f"max_new_tokens must be positive, got {max_new_tokens}")
        started = time.perf_counter()
        prompt_ids = [SEP_ID, *self.vocab.encode_text(prompt, wrap=False)] if prompt else [SEP_ID]
        context = self.model.backbone.spec.context
        history: list[int] = list(prompt_ids)
        emitted: list[int] = []
        generator = seeded_generator(params.seed)
        stop = "max_new_tokens"
        with torch.inference_mode():
            for _ in range(max_new_tokens):
                window = torch.tensor(history[-context:], dtype=torch.long)[None]
                hidden = self.model.backbone(window)
                logits = self.model.backbone.logits(hidden[:, -1])[0]
                chosen = sample_next(
                    logits, params, previous=history[1:], allowed=self._allowed, generator=generator
                )
                if chosen == SEP_ID:
                    stop = "sep"
                    break
                history.append(chosen)
                emitted.append(chosen)
        return Generation(
            text=self.decode_text(emitted),
            token_ids=emitted,
            stop_reason=stop,
            prompt_tokens=len(prompt_ids),
            time_ms=(time.perf_counter() - started) * 1000.0,
        )

    def decode_text(self, ids: Sequence[int]) -> str:
        """Decode global text ids.

        Args:
            ids: Global ids in the text block.

        Returns:
            The text.

        Raises:
            ValueError: If an id is outside the text block.
        """
        assert self.vocab.text_tokenizer is not None
        local = [int(i) - TEXT_OFFSET for i in ids]
        if any(i < 0 for i in local):
            raise ValueError("only text ids decode to text")
        return self.vocab.text_tokenizer.decode(local)


def _utc(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def build_model(payload: dict[str, Any]) -> RiskModel:
    """Rebuild the risk model an export describes, and load its weights.

    Args:
        payload: The export's payload.

    Returns:
        The model, in evaluation mode, float32, on CPU.
    """
    head = payload["head"]
    rule = head.get("text_positions")
    risk = RiskSpec(
        hidden=float(head["hidden"]),
        dropout=float(head["dropout"]),
        label=str(head["label"]),
        pooling=head["pooling"],
        layers=int(head["layers"]),  # type: ignore[arg-type]
        text_positions=None
        if rule is None
        else TextPositionRule(
            special_ids=tuple(int(i) for i in rule["special_ids"]), min_id=int(rule["min_id"])
        ),
    )
    model = RiskModel(
        ModelSpec(**payload["spec"]), risk, frozen=True, unfrozen_blocks=0, pad_id=head["pad_id"]
    )
    model.load_state_dict(payload["state"], strict=True)
    model.float().eval()
    return model
