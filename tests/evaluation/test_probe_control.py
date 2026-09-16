"""The random-init probe control (ADR-0023): the criterion, the backbone, the scores on disk."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from faultline.config import load_config
from faultline.evaluation.bootstrap import AuprcInterval
from faultline.evaluation.gate_check import BootstrapConfig
from faultline.evaluation.probe_control import (
    HEAD_LAYERS,
    POOLING,
    UNFROZEN_BLOCKS,
    ProbeControlConfig,
    ScoredWindows,
    decide_sensitive,
)
from faultline.model.risk import RiskModel, RiskSpec
from faultline.model.transformer import ModelSpec, TelemetryDecoder

REPO = Path(__file__).resolve().parents[2]
SHIPPED = REPO / "configs/train/probe_control_v0.yaml"


def interval(low: float, high: float, discarded: int = 0) -> AuprcInterval:
    return AuprcInterval(
        unit="block",
        auprc=(low + high) / 2,
        low=low,
        high=high,
        lift_low=0.0,
        lift_high=0.0,
        base_rate=0.03,
        windows=100,
        positives=10,
        blocks=10,
        positive_blocks=5,
        replicates=1000,
        discarded=discarded,
        confidence=0.95,
        seed=1,
    )


# ------------------------------------------------------------------ the criterion


def test_the_trained_interval_must_clear_every_random_upper_bound() -> None:
    random = [interval(0.03, 0.040), interval(0.03, 0.045), interval(0.03, 0.041)]
    passing = decide_sensitive(interval(0.046, 0.06), random, 0.01)
    assert passing.sensitive and passing.random_high == 0.045
    # Above two of the three random seeds is not enough.
    failing = decide_sensitive(interval(0.044, 0.06), random, 0.01)
    assert not failing.sensitive


def test_touching_the_highest_random_upper_bound_is_not_above_it() -> None:
    verdict = decide_sensitive(interval(0.045, 0.06), [interval(0.03, 0.045)], 0.01)
    assert not verdict.sensitive


def test_an_untrusted_interval_fails_the_criterion() -> None:
    verdict = decide_sensitive(interval(0.08, 0.09), [interval(0.03, 0.04, discarded=11)], 0.01)
    assert not verdict.sensitive
    assert "untrusted" in verdict.reason


def test_the_criterion_needs_a_random_side() -> None:
    with pytest.raises(ValueError, match="at least one"):
        decide_sensitive(interval(0.05, 0.06), [], 0.01)


# ------------------------------------------------------------------ the backbone


def test_an_unloaded_probe_backbone_is_pretrainings_initialisation_at_that_seed() -> None:
    # ADR-0023: the random-init backbone is what pretraining at the seed starts from. The probe
    # builds its model right after seeding, backbone first, so no checkpoint means exactly that.
    spec = ModelSpec(name="T", d_model=32, n_layer=2, n_head=4, context=26, vocab_size=64)
    torch.manual_seed(3)
    pretraining_start = TelemetryDecoder(spec)
    torch.manual_seed(3)
    control = RiskModel(spec, RiskSpec(), frozen=True)
    for name, value in pretraining_start.state_dict().items():
        assert torch.equal(value, control.backbone.state_dict()[name]), name


# ------------------------------------------------------------------ scores on disk


def scored(tmp_path: Path, name: str, logits: np.ndarray) -> ScoredWindows:
    rng = np.random.default_rng(0)
    n = logits.size
    path = tmp_path / f"{name}.npz"
    np.savez(
        path,
        logits=logits,
        labels=(rng.random(n) < 0.2).astype(np.float32),
        which=np.repeat([0, 1, 2], n // 3),
        ends=np.tile(np.arange(n // 3) * 50, 3),
        sources=np.asarray(["hill_of_towie", "kelmarsh", "penmanshiel"]),
        prior_offset=np.asarray(-3.0),
    )
    return ScoredWindows.load(path)


def test_pooled_blocks_never_join_two_sources(tmp_path: Path) -> None:
    windows = scored(tmp_path, "a", np.random.default_rng(1).normal(size=300))
    bootstrap = BootstrapConfig(
        block_steps=288, replicates=200, seed=5, confidence=0.95, max_discarded_share=0.01
    )
    pooled = windows.interval(["kelmarsh", "penmanshiel"], bootstrap)
    assert pooled.windows == 200
    # 100 windows 50 steps apart span 18 blocks of 288 in each shard: 36 pooled, not 18.
    assert pooled.blocks == 36
    assert windows.auprc(["kelmarsh", "penmanshiel"]) == pytest.approx(pooled.auprc)


def test_two_score_files_must_cover_the_same_windows(tmp_path: Path) -> None:
    one = scored(tmp_path, "a", np.zeros(300))
    two = scored(tmp_path, "b", np.ones(300))
    assert one.same_windows(two)
    shifted = ScoredWindows(
        two.logits, two.labels, two.which, two.ends + 1, two.sources, two.prior_offset
    )
    assert not one.same_windows(shifted)


# ------------------------------------------------------------------ the configuration


def test_the_shipped_control_is_the_one_registered_in_adr_0023() -> None:
    config = load_config(SHIPPED, ProbeControlConfig)
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "## ADR-0023 The random-init probe control" in decisions
    assert "strictly above the upper bound of every one of the three" in decisions
    assert config.init_seeds == [1, 2, 3]
    assert config.pooled_sources == ["kelmarsh", "penmanshiel"]
    assert config.design == "final_position"
    assert config.gate_config == "configs/train/gate_check_v0.yaml"


def test_the_shipped_mean_pooled_control_is_adr_0023_section_b() -> None:
    v0 = load_config(SHIPPED, ProbeControlConfig)
    v1 = load_config(REPO / "configs/train/probe_control_v1.yaml", ProbeControlConfig)
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "### §b, registered 2026-09-16 before its code or run" in decisions
    assert v1.design == "mean_pooled" and POOLING[v1.design] == "mean"
    # Only the design (and the version) differ from §a.
    assert v1.model_dump(exclude={"design", "version"}) == v0.model_dump(
        exclude={"design", "version"}
    )


def test_the_shipped_mlp_control_is_adr_0023_section_c() -> None:
    v1 = load_config(REPO / "configs/train/probe_control_v1.yaml", ProbeControlConfig)
    v2 = load_config(REPO / "configs/train/probe_control_v2.yaml", ProbeControlConfig)
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "### §c, registered 2026-09-16 before its code or run" in decisions
    assert v2.design == "mlp_mean_pooled"
    assert POOLING[v2.design] == "mean" and HEAD_LAYERS[v2.design] == 2
    assert v2.model_dump(exclude={"design", "version"}) == v1.model_dump(
        exclude={"design", "version"}
    )


def test_the_shipped_unfrozen_control_is_adr_0023_section_d() -> None:
    v2 = load_config(REPO / "configs/train/probe_control_v2.yaml", ProbeControlConfig)
    v3 = load_config(REPO / "configs/train/probe_control_v3.yaml", ProbeControlConfig)
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "### §d, registered 2026-09-17 before its code or run" in decisions
    assert v3.design == "unfrozen_mlp_mean_pooled"
    assert POOLING[v3.design] == "mean" and HEAD_LAYERS[v3.design] == 2
    assert UNFROZEN_BLOCKS[v3.design] == 2
    assert all(
        UNFROZEN_BLOCKS[d] == 0 for d in ("final_position", "mean_pooled", "mlp_mean_pooled")
    )
    assert v3.model_dump(exclude={"design", "version"}) == v2.model_dump(
        exclude={"design", "version"}
    )
