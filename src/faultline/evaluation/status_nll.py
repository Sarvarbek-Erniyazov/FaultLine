"""H3' measured behaviourally: single-token words and per-string NLL (ADR-0017, audit entry 11).

Token-level coverage, the instrument H3' Stage A read, cannot fail for an absent word:
byte-level BPE encodes a missing word into shorter, more frequent pieces, so absence can
*raise* coverage (`Yaw error` is covered raw as `Y` `aw` ` error`, and `yaw` never occurs).
This module replaces it with two measurements that can fail for the reason the claim names.

**Single-token-word rate.** Per status string under the normalized encoding, the share of
its words that are one vocabulary entry. A *word* is a pretokenizer chunk of letters, with
the leading space the chunk carries (` yaw`), because a chunk is the unit no BPE merge
crosses, so "one token" is well defined for it. Existence is checked **exactly**: a token
whose byte sequence equals the chunk's UTF-8 bytes is looked up in the vocabulary. Whether
the encoder emits that token for the chunk is checked beside it and any disagreement is
counted, not assumed away.

**Per-string NLL.** Each string is scored by the M2 text-only checkpoints, S2 and S3, as
the sum of next-token negative log-likelihoods of its tokens given one ``<sep>``. ``<sep>``
is the only boundary the text model was trained on (it precedes every document); the joint
stream's ``<txt>`` wrapper does not exist for it. That context is declared the primary one
here, before any NLL was computed. Its known bias is measured rather than argued: documents
start without a leading space, so a raw string sits where prose starts and a normalized one
does not. A mid-prose context is reported beside it as the other extreme.

The four Stage A conventions are all scored, so the leading space and the casing are
separated behaviourally as well as by count. Totals are compared per string, and per byte
of the string **as staged**, which is the same denominator under every convention, so a
convention cannot win by being written in more bytes.

The reference scale is held-out narrative text under the same checkpoints: the first
tokens of validation documents after their ``<sep>``, and the full-context validation loss
the pretraining record holds.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch import Tensor

from faultline.data.common.report import kv_table, section, table
from faultline.data.text.code_book import (
    CODE_BOOK_SOURCE,
    RARE_THRESHOLD,
    every_token_frequent,
    train_token_frequency,
    train_word_frequency,
)
from faultline.data.text.shards import shards_dir
from faultline.data.text.status_convention import CONVENTIONS, NORMALIZED, RAW
from faultline.logging_utils import get_logger
from faultline.model.checkpoints import migrate_text_checkpoint, text_support
from faultline.model.transformer import ModelSpec, TelemetryDecoder
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.tokenizers.layout import VocabLayout
from faultline.tokenizers.text_bpe import TextBPETokenizer, pretokenize

logger = get_logger(__name__)

#: The mid-prose context, reported beside ``<sep>``. A clause as NRC event text writes one.
PROSE_CONTEXT = "The licensee reported"

#: Narrative documents read per validation source for the document-start reference.
REFERENCE_DOCUMENTS = 400

#: Tokens of each document the document-start reference scores.
REFERENCE_TOKENS = 16

#: Seed of the reference document sample and of the bootstrap.
SEED = 20260916

#: Bootstrap resamples for the paired convention effect.
BOOTSTRAP = 10_000

#: Word-level vocabulary status of a string, from its rarest word.
ABSENT, RARE, FREQUENT = "a word absent", "a word rare, none absent", "every word frequent"
WORD_STATUSES: tuple[str, ...] = (FREQUENT, RARE, ABSENT)


@dataclass(frozen=True)
class WordForm:
    """One word of a status string under the normalized encoding.

    Attributes:
        surface: The chunk as the tokenizer sees it, leading space included.
        in_vocabulary: Whether a vocabulary entry has exactly these bytes.
        encoded_tokens: Tokens the encoder emits for the chunk.
        corpus_count: Occurrences of the word (lowercase letters) in the training text.
    """

    surface: str
    in_vocabulary: bool
    encoded_tokens: int
    corpus_count: int


def word_forms(
    text: str,
    lookup: Callable[[bytes], int | None],
    encode: Callable[[str], Sequence[int]],
    word_frequency: Counter[str],
) -> list[WordForm]:
    """The words of a string's normalized encoding, each checked for being one token.

    Args:
        text: A status string as staged.
        lookup: The vocabulary id whose byte sequence equals the given bytes, or ``None``.
        encode: The tokenizer's encoder.
        word_frequency: Training word counts, lowercase.

    Returns:
        One form per letter chunk, in order.
    """
    forms = []
    for chunk in pretokenize(CONVENTIONS[NORMALIZED](text)):
        letters = chunk.lstrip(" ")
        if not letters or not letters.isalpha():
            continue
        forms.append(
            WordForm(
                surface=chunk,
                in_vocabulary=lookup(chunk.encode("utf-8")) is not None,
                encoded_tokens=len(encode(chunk)),
                corpus_count=int(word_frequency[letters.lower()]),
            )
        )
    return forms


def single_token_word_rate(forms: Sequence[WordForm]) -> float:
    """Share of words that exist as one vocabulary entry, ``nan`` for a string with no word."""
    return sum(f.in_vocabulary for f in forms) / len(forms) if forms else math.nan


def word_status(forms: Sequence[WordForm], threshold: int = RARE_THRESHOLD) -> str:
    """A string's word-level vocabulary status, from its rarest word.

    Args:
        forms: The string's words.
        threshold: The frequency floor, inclusive.

    Returns:
        One of :data:`WORD_STATUSES`.
    """
    counts = [f.corpus_count for f in forms]
    if any(c == 0 for c in counts):
        return ABSENT
    if any(c < threshold for c in counts):
        return RARE
    return FREQUENT


@torch.no_grad()
def sequence_nll(
    model: TelemetryDecoder,
    prefix: Sequence[int],
    sequences: Sequence[Sequence[int]],
    device: torch.device,
    batch: int = 64,
    to_model: Tensor | None = None,
) -> list[np.ndarray]:
    """Per-token NLL of each sequence, given a shared prefix, under a causal decoder.

    Sequences are right-padded inside a batch. The decoder is causal, so padding after a
    position cannot change that position's prediction, and padded positions are dropped.

    Args:
        model: The decoder, in evaluation mode.
        prefix: Context tokens before every sequence, at least one.
        sequences: Token ids to score, in the scored vocabulary's own ids.
        device: Where the model lives.
        batch: Sequences per forward pass.
        to_model: Where the scored vocabulary sits in the model's: entry ``i`` is the model
            id of scored id ``i``. The softmax is taken over those ids only, so a text-only
            checkpoint migrated to the joint vocabulary scores exactly as it did natively
            (:func:`faultline.model.checkpoints.text_support`). ``None`` scores the model's
            own vocabulary.

    Returns:
        Per sequence, the NLL of each of its tokens in nats, float64.

    Raises:
        ValueError: If the prefix is empty, since the first token would have no context.
    """
    if not prefix:
        raise ValueError("a prefix of at least one token is required")
    support = to_model.to(device) if to_model is not None else None
    out: list[np.ndarray] = []
    for start in range(0, len(sequences), batch):
        group = sequences[start : start + batch]
        width = len(prefix) + max(len(s) for s in group)
        ids = torch.zeros((len(group), width), dtype=torch.long)
        for row, sequence in enumerate(group):
            full = [*prefix, *sequence]
            ids[row, : len(full)] = torch.tensor(full, dtype=torch.long)
        ids = ids.to(device)
        inputs = support[ids] if support is not None else ids
        logits = model.logits(model(inputs[:, :-1])).float()
        if support is not None:
            logits = logits[..., support]
        logp = F.log_softmax(logits, dim=-1)
        nll = -logp.gather(-1, ids[:, 1:].unsqueeze(-1)).squeeze(-1).double().cpu().numpy()
        for row, sequence in enumerate(group):
            first = len(prefix) - 1
            out.append(nll[row, first : first + len(sequence)].copy())
    return out


def load_text_decoder(
    path: Path, layout: VocabLayout, shard_dir: Path, tokenizer_size: int, device: torch.device
) -> tuple[TelemetryDecoder, Tensor]:
    """A text-only checkpoint, migrated to the joint vocabulary, and its text support.

    A 32,769-row checkpoint is read only through the migration (E2), so the model scored here
    is the joint-vocabulary decoder M3 initialises from. Scored over its text support, it
    gives the text-only model's own distribution.

    Args:
        path: A ``checkpoints/text/*_text_seed*.pt`` file.
        layout: The joint layout.
        shard_dir: The text shards it was trained on, to locate its separator row.
        tokenizer_size: Ids the fitted tokenizer defines.
        device: Where to put the model.

    Returns:
        The decoder in evaluation mode, and :func:`text_support` for ``to_model``.
    """
    payload, _location = migrate_text_checkpoint(path, layout, shard_dir, tokenizer_size)
    model = TelemetryDecoder(ModelSpec(**payload["spec"]))
    model.load_state_dict(payload["state"])
    return model.to(device).eval(), text_support(layout)


@dataclass
class StringRecord:
    """One status string's measurements.

    Attributes:
        text: As staged.
        utf8_bytes: Bytes of the string as staged, the per-byte denominator.
        words: Its words under the normalized encoding.
        single_token_rate: Share of words that are one vocabulary entry.
        word_status: One of :data:`WORD_STATUSES`.
        coverage_class: Stage A's class: covered by both levels, token level only, a
            vocabulary-absent residual, or blocked below the word level.
        tokens: Per convention, its token count.
        nll: Per checkpoint, context and convention, the string's total NLL in nats.
    """

    text: str
    utf8_bytes: int
    words: list[WordForm]
    single_token_rate: float
    word_status: str
    coverage_class: str
    tokens: dict[str, int]
    nll: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)


@dataclass
class Reference:
    """Held-out narrative text under one checkpoint.

    Attributes:
        documents: Documents scored at their start.
        position_nll: Mean NLL at each of the first tokens after ``<sep>``.
        nats_per_byte: Per token count ``n``, total NLL over bytes of the first ``n`` tokens.
        space_initial_share: Share of documents whose first token starts with a space.
        validation_loss: Full-context validation loss per token, from the pretraining record.
        validation_nats_per_byte: The same per byte, from the record's bits per byte.
    """

    documents: int
    position_nll: list[float]
    nats_per_byte: dict[int, float]
    space_initial_share: float
    validation_loss: float
    validation_nats_per_byte: float


def coverage_class(token_covered: bool, word_covered: bool) -> str:
    """Stage A's four-way class of a string, from normalized-token and word coverage."""
    if token_covered and word_covered:
        return "covered, both levels"
    if token_covered:
        return "covered, token level only"
    if word_covered:
        return "residual, below the word level"
    return "residual, vocabulary-absent"


def narrative_reference(
    model: TelemetryDecoder,
    tokenizer: TextBPETokenizer,
    shard_dir: Path,
    device: torch.device,
    record: dict[str, Any],
    to_model: Tensor | None = None,
) -> Reference:
    """Score the first tokens of held-out documents, and read the full-context loss.

    Args:
        model: The decoder.
        tokenizer: Its tokenizer, for the bytes of each token.
        shard_dir: The text shards; validation streams are read from them.
        device: Where the model lives.
        record: The checkpoint's pretraining record entry.
        to_model: The text support of a migrated model, as :func:`sequence_nll` takes it.

    Returns:
        The reference scale.
    """
    manifest = json.loads((shard_dir / "manifest.json").read_text(encoding="utf-8"))
    sep = int(manifest["specials"]["<sep>"])
    rng = np.random.default_rng(SEED)
    starts: list[list[int]] = []
    for key in sorted(k for k in manifest["files"] if k.endswith("__val")):
        stream = np.fromfile(shard_dir / manifest["files"][key]["tokens"], dtype=manifest["dtype"])
        # every document follows a <sep>, except the stream's first
        boundaries = np.r_[0, np.flatnonzero(stream == sep) + 1]
        docs = [
            stream[b : b + REFERENCE_TOKENS].astype(np.int64).tolist()
            for b in boundaries
            if b + REFERENCE_TOKENS <= stream.size and sep not in stream[b : b + REFERENCE_TOKENS]
        ]
        take = rng.choice(len(docs), size=min(REFERENCE_DOCUMENTS, len(docs)), replace=False)
        starts.extend(docs[int(i)] for i in sorted(take))
    nll = np.stack(sequence_nll(model, [sep], starts, device, to_model=to_model))
    byte_lengths = np.array(
        [[len(tokenizer.decode_bytes([t])) for t in doc] for doc in starts], dtype=np.float64
    )
    nats_per_byte = {
        n: float(nll[:, :n].sum() / byte_lengths[:, :n].sum()) for n in (2, 4, 8, REFERENCE_TOKENS)
    }
    space_initial = float(
        np.mean([tokenizer.decode_bytes([d[0]]).startswith(b" ") for d in starts])
    )
    validation = record["validation_loss"]
    bpb = record["validation_bpb"]
    return Reference(
        documents=len(starts),
        position_nll=[float(v) for v in nll.mean(axis=0)],
        nats_per_byte=nats_per_byte,
        space_initial_share=space_initial,
        validation_loss=float(np.mean(list(validation.values()))),
        validation_nats_per_byte=float(np.mean(list(bpb.values()))) * math.log(2),
    )


def paired_effect(a: np.ndarray, b: np.ndarray, seed: int = SEED) -> tuple[float, float, float]:
    """Mean of ``b - a`` over strings with a bootstrap 95% interval over strings.

    Args:
        a: Per string, the baseline value.
        b: Per string, the treated value.
        seed: Bootstrap seed.

    Returns:
        The mean difference and the 2.5th and 97.5th percentiles of its bootstrap.
    """
    delta = b - a
    rng = np.random.default_rng(seed)
    means = delta[rng.integers(0, delta.size, size=(BOOTSTRAP, delta.size))].mean(axis=1)
    return float(delta.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


@dataclass
class BehaviourResult:
    """Everything the behavioural H3' report holds.

    Attributes:
        strings: Per status string, its record.
        references: Per checkpoint, the narrative reference scale.
        checkpoints: Per checkpoint name, the file read.
        contexts: Per context name, its token ids.
        tokenizer_file: The frozen tokenizer.
        vocabulary_lookup_disagreements: Words whose exact vocabulary entry exists but the
            encoder does not emit it alone, or the other way round.
    """

    strings: list[StringRecord]
    references: dict[str, Reference]
    checkpoints: dict[str, str]
    contexts: dict[str, list[int]]
    tokenizer_file: str
    vocabulary_lookup_disagreements: list[str]

    def totals(self, checkpoint: str, context: str, convention: str) -> np.ndarray:
        """Per string, in order, its total NLL under one condition."""
        return np.array([s.nll[checkpoint][context][convention] for s in self.strings])

    def per_byte(self, checkpoint: str, context: str, convention: str) -> np.ndarray:
        """Per string, its total NLL over its staged bytes."""
        denominator = np.array([s.utf8_bytes for s in self.strings], dtype=np.float64)
        return self.totals(checkpoint, context, convention) / denominator


def measure_behaviour(
    paths: ProjectPaths,
    tokenizer_file: Path,
    corpus_name: str,
    checkpoints: dict[str, Path],
    record_path: Path,
    device: torch.device,
    layout: VocabLayout,
) -> BehaviourResult:
    """Measure single-token-word rates and per-string NLL for the staged code book.

    Args:
        paths: Resolved project paths.
        tokenizer_file: The frozen text tokenizer.
        corpus_name: The corpus it was fitted on, for word counts.
        checkpoints: Per rung name, its text-only checkpoint.
        record_path: The text pretraining record, for the full-context reference.
        device: Where to run the models.
        layout: The joint layout the checkpoints are migrated to.

    Returns:
        The measurement.

    Raises:
        FileNotFoundError: If the code book is not staged.
    """
    book = paths.stage_dir("raw", "text") / f"{CODE_BOOK_SOURCE}.jsonl"
    if not book.is_file():
        raise FileNotFoundError(f"{book}: stage the code book with `faultline download text`")
    texts = [
        str(json.loads(line)["text"])
        for line in book.read_text(encoding="utf-8").splitlines()
        if line
    ]
    tokenizer = TextBPETokenizer.load(tokenizer_file)
    shard_dir = shards_dir(paths, tokenizer_file)
    frequency = train_token_frequency(shard_dir, tokenizer.vocab_size)
    word_frequency, _ = train_word_frequency(paths, corpus_name)
    sep = tokenizer.vocab_size

    strings: list[StringRecord] = []
    disagreements: list[str] = []
    for text in texts:
        forms = word_forms(text, tokenizer.id_of_bytes, tokenizer.encode, word_frequency)
        disagreements += [f.surface for f in forms if f.in_vocabulary != (f.encoded_tokens == 1)]
        token_covered = every_token_frequent(
            tokenizer.encode(CONVENTIONS[NORMALIZED](text)), frequency, RARE_THRESHOLD
        )
        status = word_status(forms)
        strings.append(
            StringRecord(
                text=text,
                utf8_bytes=len(text.encode("utf-8")),
                words=forms,
                single_token_rate=single_token_word_rate(forms),
                word_status=status,
                coverage_class=coverage_class(token_covered, status == FREQUENT),
                tokens={name: len(tokenizer.encode(c(text))) for name, c in CONVENTIONS.items()},
            )
        )

    contexts = {"<sep>": [sep], "mid-prose": [sep, *tokenizer.encode(PROSE_CONTEXT)]}
    records = {r["rung"]: r for r in json.loads(record_path.read_text(encoding="utf-8"))}
    references: dict[str, Reference] = {}
    for name, path in checkpoints.items():
        model, support = load_text_decoder(path, layout, shard_dir, tokenizer.vocab_size, device)
        for context, prefix in contexts.items():
            for convention, convert in CONVENTIONS.items():
                encoded = [tokenizer.encode(convert(s.text)) for s in strings]
                for record, nll in zip(
                    strings,
                    sequence_nll(model, prefix, encoded, device, to_model=support),
                    strict=True,
                ):
                    record.nll.setdefault(name, {}).setdefault(context, {})[convention] = float(
                        nll.sum()
                    )
        references[name] = narrative_reference(
            model, tokenizer, shard_dir, device, records[name], support
        )
        logger.info("%s scored: %d strings, 4 conventions, 2 contexts", name, len(strings))
        del model
    return BehaviourResult(
        strings=strings,
        references=references,
        checkpoints={name: _relative(path, paths) for name, path in checkpoints.items()},
        contexts=contexts,
        tokenizer_file=_relative(tokenizer_file, paths),
        vocabulary_lookup_disagreements=sorted(set(disagreements)),
    )


def _relative(path: Path, paths: ProjectPaths) -> str:
    """A path relative to the repository where it lies inside it, so a report names no machine."""
    try:
        return path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _f(value: float, digits: int = 3) -> str:
    return "n/a" if value != value else f"{value:.{digits}f}"


def _rate_bin(rate: float) -> str:
    if rate != rate:
        return "no word"
    if rate == 1.0:
        return "1 (every word one token)"
    if rate == 0.0:
        return "0 (no word one token)"
    return "between 0 and 1"


def render_behaviour_report(result: BehaviourResult, paths: ProjectPaths) -> str:
    """Render the behavioural H3' report.

    Args:
        result: The measurement.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    strings = result.strings
    n = len(strings)
    ckpts = list(result.checkpoints)
    covered = [s for s in strings if s.coverage_class.startswith("covered")]

    # -- (a) single-token-word rates ------------------------------------------------
    bins = Counter(_rate_bin(s.single_token_rate) for s in strings)
    bin_rows = [
        (label, bins[label], sum(1 for s in covered if _rate_bin(s.single_token_rate) == label))
        for label in (
            "1 (every word one token)",
            "between 0 and 1",
            "0 (no word one token)",
            "no word",
        )
    ]
    words = [w for s in strings for w in s.words]
    distinct = {w.surface: w for w in words}
    absent_one_token = sorted(
        w.surface for w in distinct.values() if w.in_vocabulary and w.corpus_count == 0
    )
    frequent_not_one = sorted(
        w.surface
        for w in distinct.values()
        if not w.in_vocabulary and w.corpus_count >= RARE_THRESHOLD
    )
    rates = np.array(
        [s.single_token_rate for s in strings if s.single_token_rate == s.single_token_rate]
    )
    by_status_rate = [
        (
            status,
            sum(s.word_status == status for s in strings),
            _f(
                float(
                    np.mean(
                        [
                            s.single_token_rate
                            for s in strings
                            if s.word_status == status
                            and s.single_token_rate == s.single_token_rate
                        ]
                    )
                ),
                3,
            ),
            sum(s.word_status == status and s.single_token_rate == 1.0 for s in strings),
        )
        for status in WORD_STATUSES
    ]
    part_a = (
        "A word is a pretokenizer letter chunk with its leading space (` yaw`). It is one token "
        "when a vocabulary entry has **exactly** its UTF-8 bytes. The encoder was run on every "
        f"chunk as a cross-check: **{len(result.vocabulary_lookup_disagreements)}** distinct words "
        "disagree between the exact lookup and the encoder"
        + (
            f" ({', '.join(f'`{w}`' for w in result.vocabulary_lookup_disagreements)})"
            if result.vocabulary_lookup_disagreements
            else ""
        )
        + ".\n\n"
        + kv_table(
            {
                "status strings": n,
                "word occurrences / distinct words": f"{len(words):,} / {len(distinct):,}",
                "distinct words that are one token": (
                    f"{sum(w.in_vocabulary for w in distinct.values())} of {len(distinct)}"
                ),
                "mean single-token-word rate over strings": _f(float(rates.mean())),
                "median": _f(float(np.median(rates))),
            }
        )
        + "\n**Distribution over strings, against Stage A's 80/264 token coverage:**\n\n"
        + table(
            ["single-token-word rate", "strings", "of which token-covered (Stage A's 80)"], bin_rows
        )
        + "\n**By word-level vocabulary status** (the string's rarest word in "
        "`operator_narratives` training):\n\n"
        + table(["word status", "strings", "mean rate", "strings at rate 1"], by_status_rate)
        + "\n**Where the two instruments part.** Words that are one vocabulary entry although the "
        "training text never contains them: "
        f"{', '.join(f'`{w}`' for w in absent_one_token) or 'none'}. "
        "Words seen at least 100 times that are not one entry: "
        f"{', '.join(f'`{w}`' for w in frequent_not_one) or 'none'}.\n"
    )

    # -- (b) NLL -------------------------------------------------------------------------
    conv_rows = []
    effect_rows = []
    for ckpt in ckpts:
        for context in result.contexts:
            raw = result.totals(ckpt, context, RAW)
            for convention in CONVENTIONS:
                values = result.totals(ckpt, context, convention)
                conv_rows.append(
                    (
                        ckpt,
                        context,
                        convention,
                        _f(float(values.mean()), 2),
                        _f(float(np.median(values)), 2),
                        _f(float(result.per_byte(ckpt, context, convention).mean()), 3),
                        sum(result.totals(ckpt, context, convention) < raw)
                        if convention != RAW
                        else "-",
                    )
                )
            for convention in ("leading space only", "lowercase only", NORMALIZED):
                mean, low, high = paired_effect(raw, result.totals(ckpt, context, convention))
                effect_rows.append(
                    (
                        ckpt,
                        context,
                        f"{convention} - raw",
                        _f(mean, 2),
                        f"[{_f(low, 2)}, {_f(high, 2)}]",
                    )
                )
    status_rows = []
    class_rows = []
    for ckpt in ckpts:
        for convention in (RAW, NORMALIZED):
            per_byte = result.per_byte(ckpt, "<sep>", convention)
            for status in WORD_STATUSES:
                chosen = np.array([s.word_status == status for s in strings])
                status_rows.append(
                    (
                        ckpt,
                        convention,
                        status,
                        int(chosen.sum()),
                        _f(float(per_byte[chosen].mean()), 3),
                        _f(float(np.median(per_byte[chosen])), 3),
                    )
                )
        per_byte = result.per_byte(ckpt, "<sep>", NORMALIZED)
        for label in (
            "covered, both levels",
            "covered, token level only",
            "residual, below the word level",
            "residual, vocabulary-absent",
        ):
            chosen = np.array([s.coverage_class == label for s in strings])
            class_rows.append(
                (ckpt, label, int(chosen.sum()), _f(float(per_byte[chosen].mean()), 3))
            )
    reference_rows = []
    for ckpt, ref in result.references.items():
        reference_rows.append(
            (
                ckpt,
                ref.documents,
                " / ".join(_f(v, 2) for v in ref.position_nll[:4]),
                _f(float(np.mean(ref.position_nll)), 3),
                " / ".join(f"{k}: {_f(v, 3)}" for k, v in ref.nats_per_byte.items()),
                f"{ref.space_initial_share:.1%}",
                _f(ref.validation_loss, 3),
                _f(ref.validation_nats_per_byte, 3),
            )
        )
    part_b = (
        f"Every string, under all four Stage A conventions, scored by {', '.join(ckpts)} (the M2 "
        "text-only checkpoints, read through the E2 migration onto the joint vocabulary and "
        "scored over their own 32,769 ids), as its total next-token NLL given a "
        "context. `<sep>` is the primary context, declared before scoring: it is the only boundary "
        f"the text model saw. Mid-prose is `<sep>` + `{PROSE_CONTEXT}`. Per byte means over the "
        "string's bytes **as staged**, one denominator for every convention.\n\n"
        "**Reference scale: held-out narrative text under the same checkpoints.** Document starts "
        f"are the first {REFERENCE_TOKENS} tokens of up to {REFERENCE_DOCUMENTS} validation "
        "documents per source after their `<sep>`. Full context is the pretraining record's "
        "validation loss, averaged over sources.\n\n"
        + table(
            [
                "checkpoint",
                "documents",
                "NLL at tokens 1-4",
                f"mean NLL, tokens 1-{REFERENCE_TOKENS}",
                "nats/byte over the first n tokens",
                "documents starting with a space",
                "full-context val nats/token",
                "full-context val nats/byte",
            ],
            reference_rows,
        )
        + "\n**The convention claim.** Total NLL per string (nats) and per staged byte, per "
        "convention; the last column counts strings whose NLL is below their raw NLL.\n\n"
        + table(
            [
                "checkpoint",
                "context",
                "convention",
                "mean nats/string",
                "median",
                "mean nats/byte",
                "strings below raw",
            ],
            conv_rows,
        )
        + "\n**Effect sizes**, paired over the 264 strings, mean NLL difference in nats per string "
        "(negative: the convention lowers NLL), bootstrap 95% interval over strings "
        f"({BOOTSTRAP:,} resamples):\n\n"
        + table(
            ["checkpoint", "context", "difference", "mean nats/string", "95% interval"], effect_rows
        )
        + "\n**The absence claim.** Nats per staged byte, `<sep>` context, grouped by the string's "
        "rarest word:\n\n"
        + table(
            ["checkpoint", "convention", "word status", "strings", "mean nats/byte", "median"],
            status_rows,
        )
        + "\nAnd by Stage A's four classes, normalized, for continuity with the withdrawn "
        "decomposition:\n\n"
        + table(["checkpoint", "Stage A class", "strings", "mean nats/byte"], class_rows)
    )

    # -- per string ----------------------------------------------------------------------
    first = ckpts[0]
    string_rows = [
        (
            s.text.replace("|", "\\|"),
            " ".join(f"`{w.surface}`{'' if w.in_vocabulary else '*'}" for w in s.words) or "-",
            _f(s.single_token_rate, 2),
            s.word_status,
            s.coverage_class,
            *(
                f"{_f(s.nll[c]['<sep>'][RAW], 1)} / {_f(s.nll[c]['<sep>'][NORMALIZED], 1)}"
                for c in ckpts
            ),
        )
        for s in sorted(strings, key=lambda s: (s.single_token_rate, s.text))
    ]
    part_c = (
        "Words marked `*` are not one vocabulary entry. NLL is total nats given `<sep>`, raw / "
        "normalized. Ordered by rate, then text. The JSON record holds every condition.\n\n"
        + table(
            [
                "status string",
                "words",
                "rate",
                "word status",
                "Stage A class",
                *(f"{c} NLL raw / norm" for c in ckpts),
            ],
            string_rows,
        )
    )
    del first
    return "".join(
        [
            "# H3' measured behaviourally: single-token words and per-string NLL\n\n",
            kv_table(
                {
                    "replaces": "token-level coverage as H3' evidence "
                    "(docs/INSTRUMENT_AUDIT.md, entry 11)",
                    "tokenizer": result.tokenizer_file,
                    "checkpoints": ", ".join(f"{k}: `{v}`" for k, v in result.checkpoints.items()),
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model status-nll",
                    "training": "none; forward passes only",
                }
            ),
            section("a. Single-token-word rate, normalized encoding", part_a),
            section("b. Per-string NLL under the text-only checkpoints", part_b),
            section("c. Per string", part_c),
        ]
    )


def write_behaviour_report(
    paths: ProjectPaths,
    tokenizer_file: Path,
    corpus_name: str,
    checkpoints: dict[str, Path],
    record_path: Path,
    device: torch.device,
    layout: VocabLayout,
) -> tuple[Path, Path]:
    """Measure, then write the report and its JSON record.

    Args:
        paths: Resolved project paths.
        tokenizer_file: The frozen text tokenizer.
        corpus_name: The corpus it was fitted on.
        checkpoints: Per rung name, its text-only checkpoint.
        record_path: The text pretraining record.
        device: Where to run the models.
        layout: The joint layout the checkpoints are migrated to.

    Returns:
        The report and the JSON record.
    """
    result = measure_behaviour(
        paths, tokenizer_file, corpus_name, checkpoints, record_path, device, layout
    )
    stem = f"h3prime_behavioural_v1_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(render_behaviour_report(result, paths), encoding="utf-8", newline="\n")
    record = paths.data_reports_dir / f"{stem}.json"
    record.write_text(json.dumps(asdict(result), indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record)
    return report, record
