"""Text token shards for M2d text-only pretraining.

Mirrors the telemetry shard convention (``faultline.data.telemetry.shards``) closely
enough that ``faultline.training.windows``' ``ShardSet``, ``WindowSampler`` and
``load_windows`` work on it unchanged: one flat token stream per source and split
under ``data/shards/text/<tokenizer>/``, a window index of every admissible window
start, and a manifest in the same schema. Text needs none of telemetry's per-step
label machinery -- there is no risk label here, only next-token prediction -- so the
window index carries just ``start_step``/``end_step``, plus a ``year`` column fixed at
``0`` because :func:`faultline.training.windows.load_windows` reads that column for
every shard set regardless of whether anything downstream uses it.

**Document boundaries are marked by ``<sep>``** (one identifier past the fitted BPE
vocabulary -- not a joint-layout special, since a text-only pretraining run has no
joint vocabulary to draw one from) between consecutive documents in one source and
split's stream. **Windows are drawn only within one source's own stream** ("no packing
across sources", per the M2 brief): a window may span several documents of the same
source, but a source and a split are always their own file, so a window can never
cross either boundary.

A "step" is one BPE token; ``tokens_per_step`` is always ``1``, so the manifest's
``context_steps`` is directly the context length in tokens (2048, per the M2 brief).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, table
from faultline.data.text.bpe_fit import (
    CorpusDocument,
    TextBPEConfig,
    load_text_bpe_config,
    read_split,
)
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.tokenizers.text_bpe import TextBPETokenizer

logger = get_logger(__name__)

#: Text shard token dtype. A vocabulary of 32,768 plus one `<sep>` id fits comfortably.
TOKEN_DTYPE = np.uint16

SPLITS: tuple[str, ...] = ("train", "val", "test")


class TextShardsConfig(StrictModel):
    """Top level of ``configs/tokenizer/text_shards_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        tokenizer_config: The fitted text BPE tokenizer's configuration, relative to
            the repository root -- names both the tokenizer and the corpus it reads.
        context_steps: Context length in tokens, held fixed across every rung that
            reads these shards (the M2 brief's 2048).
    """

    version: int = 1
    tokenizer_config: str
    context_steps: int = 2048


def load_text_shards_config(path: Path) -> TextShardsConfig:
    """Load and validate a text shards configuration.

    Args:
        path: Path to the YAML file.

    Returns:
        The validated configuration.
    """
    return load_config(path, TextShardsConfig)


def tokenizer_path(paths: ProjectPaths, tokenizer_config_path: Path) -> Path:
    """Where ``faultline text bpe`` wrote the tokenizer a shards configuration names.

    Args:
        paths: Resolved project paths.
        tokenizer_config_path: The ``text_bpe_v*.yaml`` file the shards config names.

    Returns:
        The tokenizer file path.
    """
    config = load_config(tokenizer_config_path, TextBPEConfig)
    return paths.tokenizers_dir / f"text_bpe_v{config.version}_{config_hash(config)}.json"


def shards_dir(paths: ProjectPaths, tokenizer: Path) -> Path:
    """The directory one tokenizer's text shards are written to, under the data root."""
    return paths.data_root / "shards" / "text" / tokenizer.stem


def _group_by_source(documents: list[CorpusDocument]) -> dict[str, list[CorpusDocument]]:
    """Bucket documents by source, preserving each source's internal order.

    Args:
        documents: Documents from one split, as :func:`read_split` returns them.

    Returns:
        Documents grouped by source.
    """
    by_source: dict[str, list[CorpusDocument]] = {}
    for document in documents:
        by_source.setdefault(document.source, []).append(document)
    return by_source


def build_text_shards(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """Write the text token shards, the window index and the manifest, and report them.

    Args:
        paths: Resolved project paths.
        config_path: The shards configuration.

    Returns:
        The manifest path and the report path.

    Raises:
        FileNotFoundError: If the tokenizer the configuration names was never fitted.
    """
    config = load_text_shards_config(config_path)
    bpe_config_path = paths.repo_root / config.tokenizer_config
    bpe_config = load_text_bpe_config(bpe_config_path)
    source_tokenizer = tokenizer_path(paths, bpe_config_path)
    if not source_tokenizer.is_file():
        raise FileNotFoundError(f"{source_tokenizer} not found: run `faultline text bpe` first")
    tokenizer = TextBPETokenizer.load(source_tokenizer)
    sep_id = tokenizer.vocab_size
    vocab_size = tokenizer.vocab_size + 1

    root = shards_dir(paths, source_tokenizer)
    root.mkdir(parents=True, exist_ok=True)

    entries: dict[str, dict[str, object]] = {}
    per_split_tokens: dict[str, int] = {}
    per_split_windows: dict[str, int] = {}
    for split in SPLITS:
        try:
            documents = read_split(paths, bpe_config.corpus_name, split)
        except FileNotFoundError:
            logger.warning(
                "%s: no %s split for corpus %r; skipping",
                config_path,
                split,
                bpe_config.corpus_name,
            )
            continue
        for source, source_docs in sorted(_group_by_source(documents).items()):
            stream: list[int] = []
            for document in source_docs:
                stream.extend(tokenizer.encode(document.text))
                stream.append(sep_id)
            array = np.asarray(stream, dtype=TOKEN_DTYPE)
            token_path = root / f"{source}__{split}.bin"
            array.tofile(token_path)

            n = int(array.shape[0])
            window_count = max(0, n - config.context_steps + 1)
            if window_count == 0:
                logger.warning(
                    "%s/%s: %d tokens does not reach the %d-token context; no admissible window",
                    source,
                    split,
                    n,
                    config.context_steps,
                )
            starts = np.arange(window_count, dtype=np.int64)
            index = pa.table(
                {
                    "year": np.zeros(window_count, dtype=np.int64),
                    "start_step": starts,
                    "end_step": starts + config.context_steps - 1,
                }
            )
            index_path = root / f"{source}__{split}.windows.parquet"
            pq.write_table(index, index_path)

            entries[f"{source}__{split}"] = {
                "tokens": token_path.name,
                "steps": n,
                "tokens_count": n,
                "bytes": int(array.nbytes),
                "windows": index_path.name,
            }
            per_split_tokens[split] = per_split_tokens.get(split, 0) + n
            per_split_windows[split] = per_split_windows.get(split, 0) + window_count

    manifest = {
        "tokenizer": source_tokenizer.relative_to(paths.repo_root).as_posix(),
        "tokenizer_config": config.tokenizer_config,
        "corpus_name": bpe_config.corpus_name,
        "dtype": "uint16",
        "tokens_per_step": 1,
        "specials": {"<sep>": int(sep_id)},
        "vocabulary_size": int(vocab_size),
        "context_steps": config.context_steps,
        "files": entries,
        "git_sha": git_sha(paths.repo_root),
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    header = kv_table(
        {
            "shards config": config_path.as_posix(),
            "tokenizer": source_tokenizer.relative_to(paths.repo_root).as_posix(),
            "corpus": bpe_config.corpus_name,
            "context (tokens)": config.context_steps,
            "vocabulary (incl. <sep>)": vocab_size,
            "shards": root.relative_to(paths.data_root).as_posix()
            + " (under the data root; never committed)",
            "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "git_sha": git_sha(paths.repo_root),
            "generated by": "faultline text shards",
        }
    )
    per_file_rows = [
        (key, entry["steps"], entry["tokens_count"], entry["bytes"])
        for key, entry in sorted(entries.items())
    ]
    body = table(["source__split", "tokens", "tokens_count", "bytes"], per_file_rows)
    totals = kv_table(
        {
            f"{split} tokens": per_split_tokens.get(split, 0)
            for split in SPLITS
            if split in per_split_tokens
        }
        | {
            f"{split} admissible windows (stride 1)": per_split_windows.get(split, 0)
            for split in SPLITS
            if split in per_split_windows
        }
    )
    report = (
        "# Text token shards\n\n"
        + header
        + "\n## Per source and split\n\n"
        + body
        + "\n## Totals\n\n"
        + totals
    )
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d")
    report_path = paths.data_reports_dir / f"text_shards_v{config.version}_{stamp}.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info("wrote %s and %s", manifest_path, report_path)
    return manifest_path, report_path
