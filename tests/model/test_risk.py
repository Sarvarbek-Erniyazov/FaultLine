"""The risk head, and what freezing the backbone does and does not do."""

from __future__ import annotations

import pytest
import torch

from faultline.model.risk import RiskModel, RiskSpec
from faultline.model.transformer import ModelSpec

CONTEXT = 78


def spec() -> ModelSpec:
    return ModelSpec(name="T", d_model=32, n_layer=2, n_head=4, context=CONTEXT, vocab_size=64)


def test_the_head_scores_one_logit_a_window() -> None:
    model = RiskModel(spec(), RiskSpec(), frozen=False)
    logits = model(torch.randint(0, 64, (5, CONTEXT)))
    assert logits.shape == (5,)


def test_the_head_reads_the_last_position_only() -> None:
    # Changing any earlier token moves the score, because the last position attends to
    # all of them; changing the LAST token must move it too, and pooling would blur that.
    # The property under test is that the score is a function of the last hidden state.
    torch.manual_seed(0)
    model = RiskModel(spec(), RiskSpec(), frozen=False).eval()
    tokens = torch.randint(0, 64, (1, CONTEXT))
    with torch.no_grad():
        hidden = model.backbone(tokens)
        assert torch.allclose(model(tokens), model.head(hidden[:, -1]), atol=1e-6)


def test_freezing_trains_the_head_and_nothing_else() -> None:
    frozen = RiskModel(spec(), RiskSpec(), frozen=True)
    trainable = {name for name, p in frozen.named_parameters() if p.requires_grad}
    assert trainable and all(name.startswith("head.") for name in trainable)
    assert len(frozen.trainable_parameters()) == len(list(frozen.head.parameters()))

    loss = frozen.loss(torch.randint(0, 64, (4, CONTEXT)), torch.tensor([0.0, 1.0, 0.0, 1.0]))
    loss.backward()
    assert all(p.grad is None for p in frozen.backbone.parameters())
    assert any(p.grad is not None for p in frozen.head.parameters())


def test_unfreezing_trains_the_backbone_too() -> None:
    model = RiskModel(spec(), RiskSpec(), frozen=False)
    loss = model.loss(torch.randint(0, 64, (4, CONTEXT)), torch.tensor([0.0, 1.0, 0.0, 1.0]))
    loss.backward()
    assert any(p.grad is not None and p.grad.abs().sum() > 0 for p in model.backbone.parameters())


def test_the_two_initialisations_share_a_state_dictionary_shape() -> None:
    # The ablation loads a pretrained backbone into the same module the control leaves
    # random, so the two must be interchangeable by construction.
    pretrained = RiskModel(spec(), RiskSpec(), frozen=False)
    control = RiskModel(spec(), RiskSpec(), frozen=False)
    control.load_state_dict(pretrained.state_dict())
    for (a, x), (b, y) in zip(
        pretrained.state_dict().items(), control.state_dict().items(), strict=True
    ):
        assert a == b and torch.equal(x, y)


def test_the_positive_weight_raises_the_cost_of_missing_a_positive() -> None:
    torch.manual_seed(0)
    model = RiskModel(spec(), RiskSpec(), frozen=False).eval()
    tokens = torch.randint(0, 64, (4, CONTEXT))
    positives = torch.ones(4)
    with torch.no_grad():
        plain = float(model.loss(tokens, positives, 1.0))
        weighted = float(model.loss(tokens, positives, 4.0))
    assert weighted == pytest.approx(4 * plain, rel=1e-5)


def test_mean_pooling_reads_the_mean_hidden_state_of_the_window() -> None:
    # ADR-0023 §b: the head reads the mean over every position, not the last one.
    torch.manual_seed(0)
    model = RiskModel(spec(), RiskSpec(pooling="mean"), frozen=True).eval()
    tokens = torch.randint(0, 64, (2, CONTEXT))
    with torch.no_grad():
        hidden = model.backbone(tokens)
        assert torch.allclose(model(tokens), model.head(hidden.mean(dim=1)), atol=1e-6)
        assert not torch.allclose(model(tokens), model.head(hidden[:, -1]), atol=1e-4)
