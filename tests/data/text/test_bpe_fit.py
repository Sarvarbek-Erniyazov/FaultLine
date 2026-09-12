"""Fitting the text BPE tokenizer over a finished corpus's shards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultline.data.text.bpe_fit import (
    fit_text_bpe,
    load_text_bpe_config,
    read_split,
)
from faultline.paths import ProjectPaths

CORPUS_NAME = "test_corpus"
CODE_BOOK_NAME = "test_code_book"

TRAIN_DOCS = [
    {"text": "the reactor coolant pump tripped on high vibration", "source": "a", "doc_id": "0"},
    {"text": "the reactor coolant pump was returned to service", "source": "a", "doc_id": "1"},
    {"text": "the licensee notified the resident inspector", "source": "b", "doc_id": "2"},
    {"text": "the licensee traced the fault to a failed bearing", "source": "b", "doc_id": "3"},
] * 5  # repeated so a small vocab_size has real merges to learn
VAL_DOCS = [
    {"text": "the turbine was returned to service", "source": "a", "doc_id": "4"},
    {"text": "the inspector notified the licensee", "source": "b", "doc_id": "5"},
]


def _write_shard(paths: ProjectPaths, corpus: str, split: str, docs: list[dict[str, str]]) -> None:
    final_dir = paths.stage_dir("final", "text") / corpus
    final_dir.mkdir(parents=True, exist_ok=True)
    with (final_dir / f"{split}-00000.jsonl").open("w", encoding="utf-8") as handle:
        for doc in docs:
            handle.write(json.dumps(doc) + "\n")


@pytest.fixture
def corpus_paths(tmp_paths: ProjectPaths) -> ProjectPaths:
    _write_shard(tmp_paths, CORPUS_NAME, "train", TRAIN_DOCS)
    _write_shard(tmp_paths, CORPUS_NAME, "val", VAL_DOCS)
    _write_shard(
        tmp_paths,
        CODE_BOOK_NAME,
        "train",
        [{"text": "Fault code 12", "source": CODE_BOOK_NAME, "doc_id": "m0"}],
    )
    return tmp_paths


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "text_bpe_v1.yaml"
    path.write_text(
        "version: 1\n"
        f"corpus_name: {CORPUS_NAME}\n"
        "fit_split: train\n"
        "vocab_size: 300\n"
        'report_splits: ["val"]\n'
        f"code_book_corpus: {CODE_BOOK_NAME}\n",
        encoding="utf-8",
    )
    return path


def test_read_split_reads_every_shard(corpus_paths: ProjectPaths) -> None:
    docs = read_split(corpus_paths, CORPUS_NAME, "train")
    assert len(docs) == len(TRAIN_DOCS)
    assert {doc.source for doc in docs} == {"a", "b"}


def test_read_split_missing_raises(corpus_paths: ProjectPaths) -> None:
    with pytest.raises(FileNotFoundError, match="run `faultline text run`"):
        read_split(corpus_paths, CORPUS_NAME, "test")


def test_config_loads(config_path: Path) -> None:
    config = load_text_bpe_config(config_path)
    assert config.corpus_name == CORPUS_NAME
    assert config.vocab_size == 300
    assert config.code_book_corpus == CODE_BOOK_NAME


def test_fit_writes_a_tokenizer_and_a_report(corpus_paths: ProjectPaths, config_path: Path) -> None:
    tokenizer_path, report_path = fit_text_bpe(corpus_paths, config_path)
    assert tokenizer_path.is_file()
    assert report_path.is_file()

    from faultline.tokenizers.text_bpe import TextBPETokenizer

    tokenizer = TextBPETokenizer.load(tokenizer_path)
    assert tokenizer.is_fitted
    assert tokenizer.vocab_size <= 300

    report = report_path.read_text(encoding="utf-8")
    assert "bytes/token" in report
    assert "| val | a |" in report or "| val | b |" in report
    assert "Tokens per status string" in report
    assert "rare threshold" in report or "fewer than" in report
