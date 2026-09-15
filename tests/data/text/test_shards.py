"""Text token shards: written to be read by faultline.training.windows unchanged."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultline.data.text.bpe_fit import fit_text_bpe
from faultline.data.text.shards import build_text_shards, load_text_shards_config
from faultline.paths import ProjectPaths
from faultline.training.windows import ShardSet, WindowSampler, load_windows

CORPUS_NAME = "shard_test_corpus"

TRAIN_DOCS = [
    {
        "text": "the reactor coolant pump tripped on high vibration today",
        "source": "a",
        "doc_id": "0",
    },
    {
        "text": "the reactor coolant pump was returned to service afterwards",
        "source": "a",
        "doc_id": "1",
    },
    {
        "text": "the licensee notified the resident inspector of the event",
        "source": "b",
        "doc_id": "2",
    },
    {
        "text": "the licensee traced the fault to a failed bearing assembly",
        "source": "b",
        "doc_id": "3",
    },
] * 5
VAL_DOCS = [
    {"text": "the turbine was returned to service this morning", "source": "a", "doc_id": "4"},
    {"text": "the inspector notified the licensee of the finding", "source": "b", "doc_id": "5"},
]


def _write_shard(paths: ProjectPaths, split: str, docs: list[dict[str, str]]) -> None:
    final_dir = paths.stage_dir("final", "text") / CORPUS_NAME
    final_dir.mkdir(parents=True, exist_ok=True)
    with (final_dir / f"{split}-00000.jsonl").open("w", encoding="utf-8") as handle:
        for doc in docs:
            handle.write(json.dumps(doc) + "\n")


@pytest.fixture
def bpe_config_path(tmp_paths: ProjectPaths, tmp_path: Path) -> Path:
    _write_shard(tmp_paths, "train", TRAIN_DOCS)
    _write_shard(tmp_paths, "val", VAL_DOCS)
    path = tmp_path / "text_bpe_v1.yaml"
    path.write_text(
        f"version: 1\ncorpus_name: {CORPUS_NAME}\nfit_split: train\nvocab_size: 300\n"
        'report_splits: ["val"]\n',
        encoding="utf-8",
    )
    fit_text_bpe(tmp_paths, path)
    return path


@pytest.fixture
def shards_config_path(tmp_path: Path, bpe_config_path: Path) -> Path:
    path = tmp_path / "text_shards_v1.yaml"
    path.write_text(
        f"version: 1\ntokenizer_config: {bpe_config_path.as_posix()}\ncontext_steps: 20\n",
        encoding="utf-8",
    )
    return path


def test_load_config(shards_config_path: Path) -> None:
    config = load_text_shards_config(shards_config_path)
    assert config.context_steps == 20


def test_build_writes_a_manifest_shard_set_can_load(
    tmp_paths: ProjectPaths, shards_config_path: Path
) -> None:
    manifest_path, report_path = build_text_shards(tmp_paths, shards_config_path)
    assert manifest_path.is_file()
    assert report_path.is_file()

    shards = ShardSet.load(manifest_path.parent)
    assert shards.tokens_per_step == 1
    assert shards.context_steps == 20
    assert shards.context_tokens == 20
    # <sep> sits one past the fitted vocabulary
    assert shards.manifest["specials"]["<sep>"] == shards.vocab_size - 1
    keys = shards.keys("train")
    assert keys == ["a__train", "b__train"]


def test_windows_are_never_empty_and_a_sampler_can_draw_batches(
    tmp_paths: ProjectPaths, shards_config_path: Path
) -> None:
    manifest_path, _ = build_text_shards(tmp_paths, shards_config_path)
    shards = ShardSet.load(manifest_path.parent)
    sets = [load_windows(shards, key, stride=1) for key in shards.keys("train")]
    assert all(len(s) > 0 for s in sets)

    sampler = WindowSampler(
        sets,
        batch_size=4,
        tokens_per_step=shards.tokens_per_step,
        context_steps=shards.context_steps,
        labelled=False,
    )
    tokens, _labels, which = next(sampler.epoch())
    assert tokens.shape[1] == 20
    assert which.shape[0] <= 4


def test_a_source_shorter_than_context_raises(tmp_paths: ProjectPaths, tmp_path: Path) -> None:
    _write_shard(tmp_paths, "train", [{"text": "short", "source": "tiny", "doc_id": "0"}])
    bpe_path = tmp_path / "text_bpe_v1.yaml"
    bpe_path.write_text(
        f"version: 1\ncorpus_name: {CORPUS_NAME}\nfit_split: train\nvocab_size: 260\n"
        "report_splits: []\n",
        encoding="utf-8",
    )
    fit_text_bpe(tmp_paths, bpe_path)
    shards_path = tmp_path / "text_shards_v1.yaml"
    shards_path.write_text(
        f"version: 1\ntokenizer_config: {bpe_path.as_posix()}\ncontext_steps: 2048\n",
        encoding="utf-8",
    )
    # a split with no admissible window would evaluate silently empty; it must not build
    with pytest.raises(ValueError, match="tiny/train"):
        build_text_shards(tmp_paths, shards_path)
