"""Slow serving-parity test on the real checkpoint: skipped when the export or the record is absent.

Tier 1 (identical token ids) and tier 2 (the revised criteria: max |Δ| <= 0.02, Spearman >= 0.999,
max percentile shift <= 1.0 pp) on the 20 fixed test windows. Tier 3 needs CUDA and is left to
the measurement itself (:func:`evaluation.parity.measure`).
"""

from __future__ import annotations

import importlib

import pytest
from inference.engine import Engine
from inference.export import MODEL_FILE, served_paths, tokenizer_files

from faultline.paths import ProjectPaths

# Imported by name: the root package ``evaluation`` shares its name with ``tests/evaluation``,
# which ruff's ``src`` setting makes the pinned pre-commit ruff sort as first-party and the
# venv's ruff as third-party, so an import statement would never satisfy both.
parity = importlib.import_module("evaluation.parity")


def test_the_criteria_are_the_revised_ones() -> None:
    assert parity.MAX_ABS_DELTA == 0.02
    assert parity.MIN_SPEARMAN == 0.999
    assert parity.MAX_PERCENTILE_SHIFT == 1.0
    assert parity.ORIGINAL_MAX_PERCENTILE_SHIFT == 0.5
    assert "0.543" in parity.PERCENTILE_REVISION


def test_serving_parity_on_the_fixed_windows() -> None:
    paths = ProjectPaths.resolve()
    model_path = paths.checkpoints_dir / MODEL_FILE
    if not model_path.exists():
        pytest.skip(f"{model_path} absent: run `python -m inference.export`")
    try:
        record = served_paths(paths)
    except (FileNotFoundError, OSError) as missing:
        pytest.skip(f"the record is absent: {missing}")
    if not record["scores"].exists():
        pytest.skip(f"{record['scores']} absent")
    engine = Engine.load(model_path, tokenizer_files(paths)["bins"].parent)
    ctx = parity.open_context(paths)
    rows, raws, labels = parity.parity_windows(engine, ctx)
    result = parity.measure(engine, ctx, rows, raws, labels, run_tier3=False)
    tier1, tier2 = result["tier1_token_ids"], result["tier2_logits"]
    assert tier1 == {"windows": 20, "identical": 20, "passed": True}
    assert tier2["max_abs_delta"] <= 0.02
    assert tier2["spearman"] >= 0.999
    assert tier2["max_percentile_shift"] <= 1.0
    assert tier2["passed"] and result["passed"]
