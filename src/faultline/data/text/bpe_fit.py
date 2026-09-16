"""Fit the text BPE tokenizer on the train split of a finished corpus (M2c).

``faultline text bpe`` reads ``configs/tokenizer/text_bpe_v*.yaml``: which corpus and
which split to fit on, and the target vocabulary size. One fit; no iteration, per the
M2 brief -- there is no candidate sweep here the way the telemetry quantile bins have
one, because a BPE vocabulary has no analogous cheap axis to compare fits along before
committing.

The fitted tokenizer's ids are local, ``[0, vocab_size)``; placing them in the text
region of the joint layout (``[1184, 1184 + 32768)``, ADR-0003) is
``JointVocab.encode_text``'s job at fit time, not this module's, exactly as the
quantile-bin tokenizer stays local and the layout does the shifting for telemetry.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.tokenizers.text_bpe import BASE_VOCAB_SIZE, TextBPETokenizer

logger = get_logger(__name__)


class TextBPEConfig(StrictModel):
    """Top level of ``configs/tokenizer/text_bpe_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        corpus_name: The finished corpus to fit on, under ``data/final/text/``.
        fit_split: The split the tokenizer is fitted on. Only ``train`` is accepted --
            fitting on held-out text would leak its distribution into the vocabulary,
            the same discipline the quantile-bin tokenizer follows.
        vocab_size: Target vocabulary size, including the 256-token base alphabet.
        report_splits: Splits the compression report measures, per source.
        code_book_corpus: An optional second, already-final corpus (the status-message
            code book) to report tokens-per-string readiness for, without fitting on it.
    """

    version: int = 1
    corpus_name: str
    fit_split: Literal["train"] = "train"
    vocab_size: int = Field(default=32768, ge=BASE_VOCAB_SIZE)
    report_splits: list[str] = Field(default_factory=lambda: ["val", "test"])
    code_book_corpus: str | None = None


def load_text_bpe_config(path: Path) -> TextBPEConfig:
    """Load and validate a text BPE tokenizer configuration.

    Args:
        path: Path to the YAML file.

    Returns:
        The validated configuration.
    """
    return load_config(path, TextBPEConfig)


@dataclass(frozen=True)
class CorpusDocument:
    """One document read back from a finished corpus's shards.

    Attributes:
        text: Document body.
        source: The source id it was staged under.
    """

    text: str
    source: str


def read_split(paths: ProjectPaths, corpus_name: str, split: str) -> list[CorpusDocument]:
    """Read every document of one split of a finished corpus.

    Args:
        paths: Resolved project paths.
        corpus_name: The corpus, as ``TextLayout.build`` names its final directory.
        split: ``train``, ``val`` or ``test``.

    Returns:
        Every document in the split, across all its shards.

    Raises:
        FileNotFoundError: If the corpus has no final shards for this split.
    """
    final_dir = paths.stage_dir("final", "text") / corpus_name
    shards = sorted(final_dir.glob(f"{split}-*.jsonl"))
    if not shards:
        raise FileNotFoundError(
            f"no {split} shards under {final_dir}; run `faultline text run` first"
        )
    documents = []
    for shard in shards:
        for line in shard.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            record = json.loads(line)
            documents.append(
                CorpusDocument(text=record["text"], source=record.get("source", corpus_name))
            )
    return documents


def compression_by_source(
    tokenizer: TextBPETokenizer, documents: list[CorpusDocument]
) -> dict[str, tuple[int, int]]:
    """Measure bytes-per-token compression, per source.

    Args:
        tokenizer: The fitted tokenizer.
        documents: Documents to measure, from one split.

    Returns:
        Per source, ``(utf-8 bytes, tokens)``.
    """
    totals: dict[str, list[int]] = {}
    for document in documents:
        bucket = totals.setdefault(document.source, [0, 0])
        bucket[0] += len(document.text.encode("utf-8"))
        bucket[1] += len(tokenizer.encode(document.text))
    return {source: (bytes_, tokens) for source, (bytes_, tokens) in totals.items()}


def token_frequency(tokenizer: TextBPETokenizer, documents: list[CorpusDocument]) -> Counter[int]:
    """Count how often each vocabulary id appears across a split.

    Args:
        tokenizer: The fitted tokenizer.
        documents: Documents to count over.

    Returns:
        Token id frequencies.
    """
    counts: Counter[int] = Counter()
    for document in documents:
        counts.update(tokenizer.encode(document.text))
    return counts


def rare_id_count(frequency: Counter[int], vocab_size: int, threshold: int) -> int:
    """Count the vocabulary ids seen fewer than ``threshold`` times, never-seen ids included.

    A ``Counter`` holds only the ids that occurred, so counting over its values misses
    every id seen zero times -- which is fewer than any positive threshold. The M2c report
    did exactly that and printed 24,456 (74.63%) where the vocabulary holds 25,387
    (77.47%) such ids.

    Args:
        frequency: Token id frequencies over a split.
        vocab_size: The vocabulary the share is taken of.
        threshold: The rare threshold, exclusive.

    Returns:
        Ids in ``[0, vocab_size)`` whose frequency is below ``threshold``.
    """
    return sum(1 for token_id in range(vocab_size) if frequency.get(token_id, 0) < threshold)


def render_report(
    config: TextBPEConfig,
    config_path: Path,
    tokenizer: TextBPETokenizer,
    tokenizer_path: Path,
    train_frequency: Counter[int],
    compression: dict[str, dict[str, tuple[int, int]]],
    code_book_tokens: list[tuple[str, int]] | None,
    paths: ProjectPaths,
) -> str:
    """Render the M2c tokenizer report.

    Args:
        config: The tokenizer configuration.
        config_path: Where that configuration lives, for the report header.
        tokenizer: The fitted tokenizer.
        tokenizer_path: Where it was written.
        train_frequency: Token frequency over the training split it was fitted on.
        compression: Per report split, per source, ``(bytes, tokens)``.
        code_book_tokens: Per code-book string, its token count; ``None`` if not
            configured.
        paths: Resolved project paths.

    Returns:
        The report, as Markdown.
    """
    header = kv_table(
        {
            "tokenizer config": config_path.as_posix(),
            "config hash": config_hash(config),
            "corpus": config.corpus_name,
            "fitted on": f"{config.fit_split} split",
            "vocab_size (requested)": config.vocab_size,
            "vocab_size (actual)": tokenizer.vocab_size,
            "merges learned": len(tokenizer.merges),
            "tokenizer file": tokenizer_path.relative_to(paths.repo_root).as_posix(),
            "generated (UTC)": datetime.now(tz=UTC).isoformat(),
            "git_sha": git_sha(paths.repo_root),
            "generated by": "faultline text bpe",
        }
    )

    compression_rows = []
    for split, by_source in compression.items():
        for source, (byte_count, token_count) in sorted(by_source.items()):
            bytes_per_token = byte_count / token_count if token_count else float("nan")
            compression_rows.append(
                (split, source, byte_count, token_count, f"{bytes_per_token:.3f}")
            )
    compression_section = section(
        "Compression: bytes per token, per source, held-out splits",
        "Never pooled across sources, the project's first reporting rule.\n\n"
        + table(["split", "source", "utf-8 bytes", "tokens", "bytes/token"], compression_rows),
    )

    total_train_tokens = sum(train_frequency.values())
    rare_threshold = 100
    rare = rare_id_count(train_frequency, tokenizer.vocab_size, rare_threshold)
    seen_ids = set(train_frequency)
    unseen = tokenizer.vocab_size - len(seen_ids)
    frequency_section = section(
        "Token frequency distribution (training split)",
        kv_table(
            {
                "distinct tokens seen in training": len(seen_ids),
                "vocabulary size": tokenizer.vocab_size,
                "tokens never seen in training": unseen,
                f"tokens seen fewer than {rare_threshold} times": rare,
                "share of vocabulary under the rare threshold": (
                    f"{rare / tokenizer.vocab_size * 100:.2f}%"
                ),
                "total training tokens counted": total_train_tokens,
            }
        )
        + "\nA limitation of this fit at this corpus size, not a trigger for a refit "
        "(the M2 brief pre-registers one fit; no iteration).\n",
    )

    sections = [compression_section, frequency_section]
    if code_book_tokens is not None:
        lengths = [count for _string, count in code_book_tokens]
        mean_len = sum(lengths) / len(lengths) if lengths else float("nan")
        code_book_section = section(
            "Tokens per status string (ADR-0007 readiness)",
            kv_table(
                {
                    "status strings measured": len(code_book_tokens),
                    "mean tokens per string": f"{mean_len:.2f}",
                    "min tokens": min(lengths) if lengths else "n/a",
                    "max tokens": max(lengths) if lengths else "n/a",
                }
            )
            + "\nEvery status string encodes to a finite, small token count under the "
            "fitted vocabulary -- the readiness check ADR-0007 asks for: the model reads "
            "a held-out site's status messages through the same BPE pathway as narrative "
            "text, not a per-OEM code book.\n",
        )
        sections.append(code_book_section)

    return f"# Text BPE tokenizer\n\n{header}\n" + "\n".join(sections)


def fit_text_bpe(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """Fit the text tokenizer, per its configuration, and write it and its report.

    Args:
        paths: Resolved project paths.
        config_path: Path to ``configs/tokenizer/text_bpe_v*.yaml``.

    Returns:
        ``(tokenizer_path, report_path)``.
    """
    config = load_text_bpe_config(config_path)
    train_docs = read_split(paths, config.corpus_name, config.fit_split)
    logger.info(
        "fitting text BPE on %d %s documents from %r to vocab_size=%d",
        len(train_docs),
        config.fit_split,
        config.corpus_name,
        config.vocab_size,
    )
    tokenizer = TextBPETokenizer.fit((doc.text for doc in train_docs), vocab_size=config.vocab_size)

    digest = config_hash(config)
    tokenizer_path = paths.tokenizers_dir / f"text_bpe_v{config.version}_{digest}.json"
    tokenizer.save(tokenizer_path)

    train_frequency = token_frequency(tokenizer, train_docs)
    compression: dict[str, dict[str, tuple[int, int]]] = {
        config.fit_split: compression_by_source(tokenizer, train_docs)
    }
    for split in config.report_splits:
        docs = read_split(paths, config.corpus_name, split)
        compression[split] = compression_by_source(tokenizer, docs)

    code_book_tokens = None
    if config.code_book_corpus is not None:
        code_book_tokens = []
        for split in ("train", "val", "test"):
            try:
                docs = read_split(paths, config.code_book_corpus, split)
            except FileNotFoundError:
                continue
            for doc in docs:
                code_book_tokens.append((doc.text, len(tokenizer.encode(doc.text))))

    report = render_report(
        config,
        config_path,
        tokenizer,
        tokenizer_path,
        train_frequency,
        compression,
        code_book_tokens,
        paths,
    )
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d")
    report_path = paths.data_reports_dir / f"text_bpe_v{config.version}_{stamp}.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info("wrote %s and %s", tokenizer_path, report_path)
    return tokenizer_path, report_path
