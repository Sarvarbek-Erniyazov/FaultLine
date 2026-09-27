"""A tiny random model in the served export format, and a two-window bundle, for the app tests.

Real tokenizers (tracked under ``data/tokenizers/``), so the layout and special ids are the
served model's; only the backbone is tiny and random.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from inference.bundle import write_bundle
from inference.engine import FORMAT, Engine, RankTable, sha256_file

from faultline.model.risk import RiskModel, RiskSpec, TextPositionRule
from faultline.model.transformer import ModelSpec
from faultline.tokenizers.layout import TEXT_OFFSET

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKENIZERS = REPO_ROOT / "data" / "tokenizers"
FILES = {"bins": "quantile_bins_v2_9cd52b65.json", "text": "text_bpe_v1_22c56e49.json"}
VOCAB_SIZE = 33952
END = pd.Timestamp("2023-06-01 12:00", tz="UTC")


def write_tiny_export(directory: Path) -> tuple[Path, Path]:
    """Write ``model.pt`` and the two tokenizers into ``directory``.

    Returns:
        The model file and the tokenizer directory.
    """
    tokenizer_dir = directory / "tokenizers"
    tokenizer_dir.mkdir(parents=True, exist_ok=True)
    for name in FILES.values():
        shutil.copy(TOKENIZERS / name, tokenizer_dir / name)
    torch.manual_seed(0)
    spec = ModelSpec(
        name="tiny", d_model=16, n_layer=1, n_head=2, context=2048, vocab_size=VOCAB_SIZE
    )
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
    payload: dict[str, Any] = {
        "format": FORMAT,
        "spec": dict(spec.__dict__),
        "head": {
            "hidden": 1.0,
            "dropout": 0.0,
            "label": "narrow_within_24h",
            "pooling": "last_plus_text",
            "layers": 1,
            "pad_id": 0,
            "text_positions": {"special_ids": [4, 5], "min_id": TEXT_OFFSET},
        },
        "window": {
            "rule": "tail_anchored_2048",
            "context_tokens": 2048,
            "context_steps": 144,
            "tokens_per_step": 13,
            "status_convention": "normalized",
        },
        "state": model.state_dict(),
        "prior_offset": -3.79,
        "score_table": {
            "values": torch.from_numpy(table.values.copy()),
            "cumulative": torch.from_numpy(table.cumulative.copy()),
        },
        "tokenizers": {
            role: {"file": name, "sha256": sha256_file(tokenizer_dir / name)}
            for role, name in FILES.items()
        },
    }
    path = directory / "model.pt"
    torch.save(payload, path)
    return path, tokenizer_dir


def write_tiny_bundle(path: Path, channels: list[str]) -> Path:
    """Two windows: a registered-only positive and a negative."""
    values = np.random.default_rng(1).uniform(0.0, 15.0, (2, 144, len(channels)))
    values[1, 10, 0] = np.nan
    end = int(END.timestamp())
    write_bundle(
        path,
        {
            "window_id": np.array(["K4-20230601T1200", "K5-20230601T1200"]),
            "row": np.array([11, 12], dtype=np.int64),
            "turbine": np.array(["Kelmarsh 4", "Kelmarsh 5"]),
            "end_utc_s": np.array([end, end], dtype=np.int64),
            "values": values,
            "label_registered": np.array([True, False]),
            "label_variant": np.array([False, False]),
            "label_variant_known": np.array([True, True]),
            "hours_since_last_fault": np.array([2.0, 720.0]),
            "hours_since_last_fault_percentile": np.array([97.5, 28.9]),
            "recorded_logit": np.array([-0.5, -1.0], dtype=np.float32),
            "recorded_score": np.array([-4.29, -4.79], dtype=np.float32),
            "recorded_percentile": np.array([61.0, 21.0]),
            "message_window": np.array([0], dtype=np.int64),
            "message_start_ns": np.array([(end - 3600) * 10**9], dtype=np.int64),
            "message_text": np.array(["Anemometer defect"]),
            "channels": np.asarray(channels),
        },
    )
    return path


def load_tiny(directory: Path) -> tuple[Engine, Path]:
    """The tiny engine and its bundle."""
    model, tokenizers = write_tiny_export(directory)
    engine = Engine.load(model, tokenizers)
    return engine, write_tiny_bundle(directory / "bundle.npz", engine.channels)
