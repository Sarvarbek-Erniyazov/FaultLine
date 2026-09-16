"""Text-only pretraining, end to end on a tiny model and a synthetic corpus."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultline.data.text.bpe_fit import fit_text_bpe
from faultline.data.text.shards import build_text_shards
from faultline.evaluation.text_ladder import (
    _bits_per_byte,
    load_text_pretrain_config,
    run_text_ladder,
)
from faultline.paths import ProjectPaths

CORPUS_NAME = "ladder_test_corpus"

# Repeated short "documents" so a tiny BPE fit has real structure and a training pass
# has more than a couple of windows to draw from.
TRAIN_DOCS = [
    {
        "text": f"the reactor tripped on high vibration at unit {i % 3}",
        "source": "a",
        "doc_id": str(i),
    }
    for i in range(20)
] + [
    {
        "text": f"the licensee notified the inspector about event {i}",
        "source": "b",
        "doc_id": str(i),
    }
    for i in range(20)
]
VAL_DOCS = [
    {"text": "the turbine was returned to service this morning", "source": "a", "doc_id": "v0"},
    {"text": "the inspector notified the licensee of the finding", "source": "b", "doc_id": "v1"},
]
TEST_DOCS = [
    {"text": "the pump fault cleared after a controller reset", "source": "a", "doc_id": "t0"},
    {"text": "the licensee traced the fault to a failed bearing", "source": "b", "doc_id": "t1"},
]


def _write_final_shard(paths: ProjectPaths, split: str, docs: list[dict[str, str]]) -> None:
    final_dir = paths.stage_dir("final", "text") / CORPUS_NAME
    final_dir.mkdir(parents=True, exist_ok=True)
    with (final_dir / f"{split}-00000.jsonl").open("w", encoding="utf-8") as handle:
        for doc in docs:
            handle.write(json.dumps(doc) + "\n")


@pytest.fixture
def shards_config_path(tmp_paths: ProjectPaths, tmp_path: Path) -> Path:
    _write_final_shard(tmp_paths, "train", TRAIN_DOCS)
    _write_final_shard(tmp_paths, "val", VAL_DOCS)
    _write_final_shard(tmp_paths, "test", TEST_DOCS)

    bpe_path = tmp_path / "text_bpe_v1.yaml"
    bpe_path.write_text(
        f"version: 1\ncorpus_name: {CORPUS_NAME}\nfit_split: train\nvocab_size: 280\n"
        'report_splits: ["val", "test"]\n',
        encoding="utf-8",
    )
    fit_text_bpe(tmp_paths, bpe_path)

    shards_path = tmp_path / "text_shards_v1.yaml"
    shards_path.write_text(
        f"version: 1\ntokenizer_config: {bpe_path.as_posix()}\ncontext_steps: 16\n",
        encoding="utf-8",
    )
    build_text_shards(tmp_paths, shards_path)
    return shards_path


@pytest.fixture
def model_config_path(tmp_path: Path) -> Path:
    path = tmp_path / "ladder_v0.yaml"
    path.write_text(
        "version: 0\n"
        "context_steps: 16\n"
        "dropout: 0.0\n"
        "head_hidden: 1.0\n"
        "head_dropout: 0.0\n"
        "rungs:\n"
        "  - {name: Stest, d_model: 16, n_layer: 1, n_head: 2, seeds: [1]}\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def pretrain_config_path(tmp_path: Path, shards_config_path: Path, model_config_path: Path) -> Path:
    path = tmp_path / "text_v1.yaml"
    path.write_text(
        f"version: 1\n"
        f"shards_config: {shards_config_path.as_posix()}\n"
        f"model_config_path: {model_config_path.as_posix()}\n"
        'rungs: ["Stest"]\n'
        "seed: 1\n"
        "batch_windows: 2\n"
        "accumulate: 1\n"
        "learning_rate: 0.003\n"
        "calibration_steps: 2\n"
        "gpu_hour_budget: 4.0\n"
        "evaluations: 2\n"
        "selection_windows: 10\n"
        "validation_windows: 10\n"
        "test_windows: 10\n"
        "optimiser: {precision: fp32}\n",
        encoding="utf-8",
    )
    return path


def test_config_loads(pretrain_config_path: Path) -> None:
    config = load_text_pretrain_config(pretrain_config_path)
    assert config.rungs == ["Stest"]
    assert config.batch_windows == 2


def test_bits_per_byte_arithmetic() -> None:
    import math

    # a model that reproduces the training distribution exactly (loss = 0) reads 0 bpb
    assert _bits_per_byte(0.0, 100, 400) == 0.0
    # nan when there is nothing to divide by, not a crash
    assert math.isnan(_bits_per_byte(1.0, 100, 0))
    assert math.isnan(_bits_per_byte(1.0, 0, 400))


def test_bits_per_byte_uses_one_streams_tokens_and_bytes() -> None:
    import math

    # 1 nat/token over a 1,000-token stream encoding 4,000 bytes: 0.25 nats/byte
    assert math.isclose(_bits_per_byte(1.0, 1000, 4000), 0.25 / math.log(2))


def test_one_pass_is_training_tokens_over_context_not_the_window_count(
    tmp_paths: ProjectPaths, pretrain_config_path: Path
) -> None:
    import math

    from faultline.evaluation.text_ladder import (
        _load_shards,
        one_pass_windows,
        stream_tokens,
    )

    shards, _corpus = _load_shards(tmp_paths, load_text_pretrain_config(pretrain_config_path))
    train_tokens = sum(stream_tokens(shards, "train").values())
    assert one_pass_windows(shards) == math.ceil(train_tokens / shards.context_tokens)
    admissible = sum(
        max(0, n - shards.context_tokens + 1) for n in stream_tokens(shards, "train").values()
    )
    assert one_pass_windows(shards) < admissible


def test_run_text_ladder_end_to_end(tmp_paths: ProjectPaths, pretrain_config_path: Path) -> None:
    json_path, report_path = run_text_ladder(tmp_paths, pretrain_config_path)
    assert json_path.is_file()
    assert report_path.is_file()

    records = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(records) == 1
    record = records[0]
    assert record["rung"] == "Stest"
    assert record["budget_bound"] in ("one_pass", "gpu_hours")
    assert record["windows"] > 0
    assert (tmp_paths.checkpoints_dir / record["checkpoint"]).is_file()
    assert set(record["validation_loss"]) <= {"a", "b"}
    assert set(record["test_loss"]) <= {"a", "b"}
    # every reported loss is a finite non-negative nats figure
    for value in record["validation_loss"].values():
        assert value >= 0.0

    report = report_path.read_text(encoding="utf-8")
    assert "bound hit" in report
    assert "bits/byte" in report
    assert "never selected on" in report


def test_calibration_is_timed_on_training_alone(
    tmp_paths: ProjectPaths, pretrain_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # bc0fd3a: the timed calibration call once scored the whole selection set, so its
    # windows/second counted evaluation as training and shrank the GPU-hour bound
    from faultline.evaluation import text_ladder

    active: list[str] = []
    scored_under: list[str] = []
    real_train = text_ladder.train
    real_loss = text_ladder.language_model_loss

    def recording_train(*args: object, **kwargs: object) -> object:
        active.append(str(kwargs["label"]))
        try:
            return real_train(*args, **kwargs)  # type: ignore[arg-type]
        finally:
            active.pop()

    def recording_loss(*args: object, **kwargs: object) -> float:
        scored_under.append(active[-1] if active else "")
        return real_loss(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(text_ladder, "train", recording_train)
    monkeypatch.setattr(text_ladder, "language_model_loss", recording_loss)
    run_text_ladder(tmp_paths, pretrain_config_path)

    assert not [label for label in scored_under if label.endswith("/calibrate")]
    # the budgeted run still measures, so the check above is not vacuous
    assert [label for label in scored_under if label.endswith("/lm")]
