"""The shipped gate configuration is the one ADR-0021 registered."""

from __future__ import annotations

from pathlib import Path

from faultline.config import load_config
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.variance_probe import VarianceProbeConfig
from faultline.training.mixture import JointMixtureConfig

REPO = Path(__file__).resolve().parents[2]
SHIPPED = REPO / "configs/train/gate_check_v0.yaml"


def test_the_shipped_interval_is_the_one_registered_in_adr_0021() -> None:
    config = load_config(SHIPPED, GateCheckConfig)
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "## ADR-0021 The held-out-site gate" in decisions
    assert (
        "**10,000 replicates,\n  bootstrap seed 20260916, 95% percentile interval.**" in decisions
    )
    bootstrap = config.bootstrap
    assert bootstrap.block_steps == 288
    assert bootstrap.replicates == 10_000
    assert bootstrap.seed == 20260916
    assert bootstrap.confidence == 0.95
    assert bootstrap.max_discarded_share == 0.01
    assert config.held_out_source == "hill_of_towie"


def test_the_gate_runs_one_seed_at_the_full_arm_budget_rounded_up_to_a_step() -> None:
    config = load_config(SHIPPED, GateCheckConfig)
    mixture = load_config(REPO / config.mixture_config, JointMixtureConfig)
    assert config.tokens == mixture.tokens_per_arm == 50_000_000
    budget = config.budget(mixture.context_tokens)
    assert budget.steps == 763
    assert budget.windows * mixture.context_tokens == 50_003_968
    assert config.rung == "S2" and config.arm == "tel_only" and config.seed == 1


def test_only_the_budget_and_the_seeds_differ_from_adr_0020s_probe() -> None:
    config = load_config(SHIPPED, GateCheckConfig)
    probe = load_config(REPO / config.half_budget_probe_config, VarianceProbeConfig)
    held = (
        "mixture_config",
        "ladder_config",
        "arm",
        "rung",
        "batch_windows",
        "accumulate",
        "learning_rate",
        "evaluations",
        "selection_windows",
        "held_out_source",
    )
    for name in held:
        assert getattr(config, name) == getattr(probe, name), name
    assert config.tokens == 2 * probe.tokens
    assert config.seed in probe.seeds
