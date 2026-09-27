"""The serving engine on a tiny random model with the real layout: load once, determinism, text ids.

The tokenizers are the real ones (tracked under ``data/tokenizers/``), so the vocabulary, the
block offsets and the special ids are the served model's; only the backbone is tiny and random.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import torch
from inference import engine as engine_module
from inference.engine import (
    FORMAT,
    RANKING_NOTE,
    Engine,
    RankTable,
    RawWindow,
    StatusMessage,
    sha256_file,
)
from inference.export import export
from inference.sampling import SamplingParams

from faultline.model.risk import RiskModel, RiskSpec, TextPositionRule
from faultline.model.transformer import ModelSpec
from faultline.tokenizers.layout import TEXT_OFFSET
from faultline.training.joint_windows import SEP_ID

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKENIZERS = REPO_ROOT / "data" / "tokenizers"
BINS_FILE = "quantile_bins_v2_9cd52b65.json"
TEXT_FILE = "text_bpe_v1_22c56e49.json"
VOCAB_SIZE = 33952
END = pd.Timestamp("2023-06-01 12:00", tz="UTC")


def tiny_payload(tokenizer_dir: Path) -> dict[str, Any]:
    """An export in the served format: real tokenizers and head rule, a tiny random backbone."""
    torch.manual_seed(0)
    spec = ModelSpec(
        name="tiny", d_model=16, n_layer=1, n_head=2, context=2048, vocab_size=VOCAB_SIZE
    )
    rule = {"special_ids": [4, 5], "min_id": TEXT_OFFSET}
    risk = RiskSpec(
        hidden=1.0,
        dropout=0.0,
        label="narrow_within_24h",
        pooling="last_plus_text",
        layers=1,
        text_positions=TextPositionRule(special_ids=(4, 5), min_id=TEXT_OFFSET),
    )
    model = RiskModel(spec, risk, frozen=True, unfrozen_blocks=0, pad_id=0)
    table = RankTable.from_scores(np.random.default_rng(0).normal(-4.0, 1.0, 1000))
    return {
        "format": FORMAT,
        "spec": {
            "name": spec.name,
            "d_model": spec.d_model,
            "n_layer": spec.n_layer,
            "n_head": spec.n_head,
            "context": spec.context,
            "vocab_size": spec.vocab_size,
            "dropout": spec.dropout,
        },
        "head": {
            "hidden": 1.0,
            "dropout": 0.0,
            "label": "narrow_within_24h",
            "pooling": "last_plus_text",
            "layers": 1,
            "pad_id": 0,
            "text_positions": rule,
        },
        "window": {
            "rule": "tail_anchored_2048",
            "context_tokens": 2048,
            "context_steps": 144,
            "tokens_per_step": 13,
            "status_convention": "normalized",
        },
        "state": model.state_dict(),
        "prior_offset": -3.7921449117457753,
        "score_table": {
            "values": torch.from_numpy(table.values.copy()),
            "cumulative": torch.from_numpy(table.cumulative.copy()),
        },
        "tokenizers": {
            role: {"file": name, "sha256": sha256_file(tokenizer_dir / name)}
            for role, name in (("bins", BINS_FILE), ("text", TEXT_FILE))
        },
    }


@pytest.fixture
def model_file(tmp_path: Path) -> tuple[Path, Path]:
    tokenizer_dir = tmp_path / "tokenizers"
    tokenizer_dir.mkdir()
    for name in (BINS_FILE, TEXT_FILE):
        shutil.copy(TOKENIZERS / name, tokenizer_dir / name)
    path = tmp_path / "model.pt"
    torch.save(tiny_payload(tokenizer_dir), path)
    return path, tokenizer_dir


@pytest.fixture
def engine(model_file: tuple[Path, Path]) -> Engine:
    return Engine.load(*model_file)


def raw_window(engine: Engine, messages: tuple[StatusMessage, ...] = ()) -> RawWindow:
    rng = np.random.default_rng(3)
    values = rng.uniform(0.0, 20.0, (engine.context_steps, len(engine.channels)))
    values[5, 2] = np.nan  # a missing value is allowed
    return RawWindow(values=values, end_utc=END, messages=messages)


def test_load_reads_the_file_once_and_calls_never_touch_disk(
    model_file: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    real_load = torch.load

    def counting_load(*args: Any, **kwargs: Any) -> Any:
        calls.append(args[0])
        return real_load(*args, **kwargs)

    monkeypatch.setattr(engine_module.torch, "load", counting_load)
    engine = Engine.load(*model_file)
    assert len(calls) == 1
    # Everything a call needs is in memory: remove the files and serve anyway.
    model_path, tokenizer_dir = model_file
    model_path.unlink()
    shutil.rmtree(tokenizer_dir)
    engine.predict(raw_window(engine))
    engine.generate_text("gearbox", SamplingParams(temperature=1.0, seed=1), max_new_tokens=3)
    assert len(calls) == 1
    assert not engine.model.training
    assert all(not p.requires_grad for p in engine.model.parameters())
    assert all(p.dtype == torch.float32 for p in engine.model.parameters())


def test_a_tokenizer_whose_hash_changed_is_refused(model_file: tuple[Path, Path]) -> None:
    model_path, tokenizer_dir = model_file
    with (tokenizer_dir / TEXT_FILE).open("a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="sha256"):
        Engine.load(model_path, tokenizer_dir)


def test_a_file_of_another_format_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "other.pt"
    torch.save({"format": "something-else"}, path)
    with pytest.raises(ValueError, match="format|faultline-lesson11"):
        Engine.load(path, TOKENIZERS)


def test_predict_is_deterministic_and_labelled_a_ranking(engine: Engine) -> None:
    window = raw_window(
        engine, (StatusMessage(END - pd.Timedelta(hours=2), "Gearbox oil pressure low"),)
    )
    first, second = engine.predict(window), engine.predict(window)
    assert first.score == second.score
    assert first.note == RANKING_NOTE == "ranking score, not a calibrated probability"
    assert first.score == float(np.float32(first.logit) + np.float32(engine.prior_offset))
    assert 0.0 <= first.percentile <= 100.0
    assert first.has_text and first.n_status_messages == 1
    assert first.time_ms >= 0.0


def test_messages_outside_the_window_are_not_attached(engine: Engine) -> None:
    inside = StatusMessage(END - pd.Timedelta(hours=1), "Yaw error")
    after = StatusMessage(END + pd.Timedelta(minutes=10), "Later message")
    before = StatusMessage(END - pd.Timedelta(hours=30), "Earlier message")
    tokenized = engine.tokenize_window(raw_window(engine, (after, inside, before)))
    assert tokenized.n_status_messages == 1
    plain = engine.tokenize_window(raw_window(engine))
    assert plain.n_status_messages == 0 and not plain.has_text
    assert tokenized.ids.shape == plain.ids.shape == (2048,)


def test_a_window_of_the_wrong_shape_or_off_the_grid_is_refused(engine: Engine) -> None:
    good = raw_window(engine)
    with pytest.raises(ValueError, match="144 x 12"):
        engine.tokenize_window(RawWindow(values=good.values[:-1], end_utc=END))
    with pytest.raises(ValueError, match="grid"):
        engine.tokenize_window(RawWindow(values=good.values, end_utc=END + pd.Timedelta(minutes=3)))


def test_generation_is_seeded(engine: Engine) -> None:
    params = SamplingParams(temperature=1.0, top_p=0.9, seed=7)
    one = engine.generate_text("turbine stopped", params, max_new_tokens=8)
    two = engine.generate_text("turbine stopped", params, max_new_tokens=8)
    assert one.token_ids == two.token_ids and one.text == two.text
    other = engine.generate_text(
        "turbine stopped", SamplingParams(temperature=1.0, top_p=0.9, seed=8), 8
    )
    assert other.token_ids != one.token_ids


def test_no_non_text_id_is_ever_emitted_even_when_favoured(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng = torch.Generator().manual_seed(0)

    def rigged(hidden: torch.Tensor) -> torch.Tensor:
        logits = torch.randn(hidden.shape[0], VOCAB_SIZE, generator=rng)
        logits[:, :TEXT_OFFSET] += 50.0  # every structural and telemetry id is the favourite
        logits[:, SEP_ID] = -50.0  # and the stop token is not, so the run is long
        return logits

    monkeypatch.setattr(engine.model.backbone, "logits", rigged)
    for seed in range(5):
        out = engine.generate_text(
            "pitch", SamplingParams(temperature=2.0, seed=seed), max_new_tokens=20
        )
        assert out.stop_reason == "max_new_tokens" and len(out.token_ids) == 20
        assert all(TEXT_OFFSET <= i < VOCAB_SIZE for i in out.token_ids)


def test_sep_ends_the_document(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    def stop_now(hidden: torch.Tensor) -> torch.Tensor:
        logits = torch.zeros(hidden.shape[0], VOCAB_SIZE)
        logits[:, SEP_ID] = 50.0
        return logits

    monkeypatch.setattr(engine.model.backbone, "logits", stop_now)
    out = engine.generate_text("", SamplingParams(temperature=0.0), max_new_tokens=10)
    assert out.stop_reason == "sep" and out.token_ids == [] and out.prompt_tokens == 1
    with pytest.raises(ValueError):
        engine.generate_text("x", SamplingParams(), max_new_tokens=0)


def test_mid_rank_percentile() -> None:
    table = RankTable.from_scores(np.array([1.0, 2.0, 2.0, 3.0]))
    assert table.total == 4
    assert table.percentile(0.5) == 0.0
    assert table.percentile(2.0) == 50.0
    assert table.percentile(1.0) == 12.5
    assert table.percentile(9.0) == 100.0
    assert table.percentile(2.5) == 75.0


def test_the_export_never_overwrites(tmp_path: Path) -> None:
    out = tmp_path / "model.pt"
    out.write_bytes(b"already here")
    with pytest.raises(FileExistsError):
        export(None, out)  # type: ignore[arg-type]
    assert out.read_bytes() == b"already here"
