"""The in-force probe's evaluation cadence (ADR-0024, G3 addendum)."""

from __future__ import annotations

from pathlib import Path

from faultline.config import load_config
from faultline.evaluation.probe_cadence import ProbeCadenceConfig

REPO = Path(__file__).resolve().parents[2]


def test_the_shipped_cadence_is_the_one_registered() -> None:
    config = load_config(REPO / "configs/train/probe_cadence_v0.yaml", ProbeCadenceConfig)
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "### Addendum, registered 2026-09-17 (G3) before its code or run" in decisions
    steps = config.steps(1000)
    assert config.measure_initial
    assert steps[:12] == list(range(25, 301, 25))
    assert steps[12:] == list(range(400, 1001, 100))
    assert len(steps) + 1 == 20  # step 0 included; the registration said 23 (erratum)
