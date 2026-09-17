"""The bag-of-tokens comparator (ADR-0024 §6): order-blind features, and the configuration."""

from __future__ import annotations

from pathlib import Path

import torch

from faultline.config import load_config
from faultline.evaluation.bag_of_tokens import BagOfTokens, BagOfTokensConfig
from faultline.evaluation.paired_control import PairedControlConfig

REPO = Path(__file__).resolve().parents[2]
SHIPPED = REPO / "configs/train/bag_of_tokens_v0.yaml"


def test_features_are_counts_per_step_and_blind_to_order() -> None:
    model = BagOfTokens(vocab_size=10, steps=2)
    tokens = torch.tensor([[8, 1, 2, 8, 1, 3], [8, 1, 3, 8, 1, 2]])
    features = model.features(tokens)
    assert features.shape == (2, 10)
    assert torch.equal(features[0], features[1])
    assert features[0, 8].item() == 1.0  # one <sep> a step
    assert features[0, 1].item() == 1.0
    assert features[0, 2].item() == 0.5


def test_the_comparator_starts_at_even_odds_and_learns_a_count() -> None:
    torch.manual_seed(0)
    model = BagOfTokens(vocab_size=6, steps=4)
    positive = torch.tensor([[5, 5, 5, 1]] * 8)
    negative = torch.tensor([[1, 1, 1, 5]] * 8)
    tokens, labels = torch.cat([positive, negative]), torch.cat([torch.ones(8), torch.zeros(8)])
    assert torch.all(model(tokens) == 0.0)
    optimiser = torch.optim.SGD(model.parameters(), lr=1.0)
    for _ in range(50):
        optimiser.zero_grad()
        model.loss(tokens, labels).backward()  # type: ignore[no-untyped-call]
        optimiser.step()
    scores = model(tokens)
    assert scores[:8].min() > scores[8:].max()


def test_the_shipped_comparator_is_adr_0024_section_6() -> None:
    config = load_config(SHIPPED, BagOfTokensConfig)
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "### 6. The bag-of-tokens comparator (reported, not gating)" in decisions
    assert config.device == "cpu" and config.seed == 1
    paired = load_config(REPO / config.paired_config, PairedControlConfig)
    assert paired.stride == 12
