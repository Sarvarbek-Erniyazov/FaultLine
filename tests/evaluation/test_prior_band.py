"""ADR-0019 F2: the balanced mean rate, its band, and the re-centring shift."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from faultline.config import load_config
from faultline.evaluation.calibration import at_natural_rate, balanced_shift, mean_predicted_rate
from faultline.evaluation.prior_band import PriorBandConfig, decide_band

REPO = Path(__file__).resolve().parents[2]


def test_the_shift_recentres_a_head_on_its_balanced_rate() -> None:
    logits = np.random.default_rng(0).normal(-0.8, 1.5, size=10_000)
    shift = balanced_shift(logits, 0.5)
    assert shift > 0.0
    recentred = 1.0 / (1.0 + np.exp(-(logits + shift)))
    assert recentred.mean() == pytest.approx(0.5, abs=1e-5)


def test_a_zero_shift_is_the_declared_correction() -> None:
    logits = np.linspace(-3, 3, 11)
    declared = at_natural_rate(logits, 0.5, 0.0221)
    same = at_natural_rate(logits, 0.5, 0.0221, balanced_shift=0.0)
    assert mean_predicted_rate(declared) == mean_predicted_rate(same)
    moved = at_natural_rate(logits, 0.5, 0.0221, balanced_shift=0.4)
    assert moved.offset == pytest.approx(declared.offset + 0.4)


def test_the_band_is_closed_and_only_outside_it_is_the_shift_applied() -> None:
    assert decide_band(0.45, 0.2, 0.45, 0.55).inside
    assert decide_band(0.55, -0.2, 0.45, 0.55).shift == 0.0
    outside = decide_band(0.4499, 0.2, 0.45, 0.55)
    assert not outside.inside and outside.shift == 0.2


def test_bad_targets_are_refused() -> None:
    with pytest.raises(ValueError, match="target"):
        balanced_shift(np.zeros(3), 1.0)
    with pytest.raises(ValueError, match="no logits"):
        balanced_shift(np.zeros(0), 0.5)


def test_the_shipped_f2_configuration_is_the_one_registered() -> None:
    config = load_config(REPO / "configs/train/prior_band_v0.yaml", PriorBandConfig)
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "### Addendum (F2), registered 2026-09-17 before its code or run" in decisions
    assert (config.band_low, config.band_high) == (0.45, 0.55)
    assert config.sampler_seed == 20260917 and config.batches == 1000
    deciding = [p for p in config.probes if p.decides]
    assert len(deciding) == 1 and "probe_cadence_v0_c9646288" in deciding[0].probe
