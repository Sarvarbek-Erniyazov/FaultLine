"""The risk head, and what freezing the backbone does and does not do."""

from __future__ import annotations

import pytest
import torch

from faultline.model.risk import RiskModel, RiskSpec, TextPositionRule
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


def test_a_one_hidden_layer_head_is_unchanged_by_the_two_layer_option() -> None:
    # ADR-0023 §c adds a second hidden layer only when asked: the default head draws the same
    # random numbers and holds the same state as before, so earlier probes reproduce.
    torch.manual_seed(7)
    one = RiskModel(spec(), RiskSpec(), frozen=True)
    torch.manual_seed(7)
    two = RiskModel(spec(), RiskSpec(layers=2), frozen=True)
    assert set(one.head.state_dict()) == {
        "norm.weight",
        "up.weight",
        "up.bias",
        "down.weight",
        "down.bias",
    }
    assert {"mid.weight", "mid.bias"} <= set(two.head.state_dict())
    assert torch.equal(one.head.up.weight, two.head.up.weight)
    assert torch.equal(one.head.down.weight, two.head.down.weight)
    tokens = torch.randint(0, 64, (3, CONTEXT))
    assert two.eval()(tokens).shape == (3,)


def test_unfreezing_the_tail_trains_those_blocks_and_the_head_only() -> None:
    # ADR-0023 §d: the last two blocks train under a frozen backbone; nothing before them does.
    torch.manual_seed(0)
    model = RiskModel(spec(), RiskSpec(), frozen=True, unfrozen_blocks=1, backbone_lr_scale=0.25)
    loss = model.loss(torch.randint(0, 64, (4, CONTEXT)), torch.tensor([0.0, 1.0, 0.0, 1.0]))
    loss.backward()
    graded = {n for n, p in model.named_parameters() if p.grad is not None}
    assert any(n.startswith("backbone.blocks.1.") for n in graded)
    assert not any(
        n.startswith(("backbone.blocks.0.", "backbone.tokens", "backbone.norm")) for n in graded
    )
    assert model.parameter_lr_scale("backbone.blocks.1.mlp.up.weight") == 0.25
    assert model.parameter_lr_scale("head.up.weight") == 1.0


def test_the_trainable_tail_computes_what_the_whole_stack_computes() -> None:
    torch.manual_seed(0)
    model = RiskModel(spec(), RiskSpec(), frozen=True, unfrozen_blocks=1).eval()
    tokens = torch.randint(0, 64, (2, CONTEXT))
    with torch.no_grad():
        assert torch.allclose(
            model.backbone.forward_with_trainable_tail(tokens, 1), model.backbone(tokens), atol=1e-6
        )


def test_blocks_cannot_be_unfrozen_in_an_unfrozen_model() -> None:
    with pytest.raises(ValueError, match="frozen backbone only"):
        RiskModel(spec(), RiskSpec(), frozen=False, unfrozen_blocks=1)


# =====================================================================================
# ADR-0026 §2: the text-aware read-outs, on a synthetic padded window
# =====================================================================================

#: A synthetic joint layout: ``<pad>`` 0, ``<txt>`` 4 and ``</txt>`` 5 as in the real one, and a
#: text block starting well inside the tiny vocabulary so both kinds of text id can be placed.
PAD = 0
RULE = TextPositionRule(special_ids=(4, 5), min_id=48)


def padded_window() -> torch.Tensor:
    """Two windows of the same length: one holding text, one holding none, both right-padded.

    Row 0 is telemetry, then ``<txt>``, two text ids, ``</txt>``, then telemetry, then pads: six
    text-token positions in all. Row 1 is telemetry only, then pads.
    """
    telemetry = [6, 7, 8, 9, 10, 11]
    row0 = [*telemetry, 4, 50, 51, 5, 12, 13]
    row1 = [*telemetry, 14, 15, 16, 17, 18, 19]
    pads = [PAD] * (CONTEXT - len(row0))
    return torch.tensor([row0 + pads, row1 + pads])


def text_model(pooling: str = "last_plus_text") -> RiskModel:
    torch.manual_seed(3)
    risk = RiskSpec(pooling=pooling, text_positions=RULE if pooling == "last_plus_text" else None)
    return RiskModel(spec(), risk, frozen=True, pad_id=PAD).eval()


def test_mean_all_excludes_the_pads_from_the_sum_and_the_divisor() -> None:
    # ADR-0026 (b). The divisor is the real count, not the window length, so the mean is the
    # mean over the 12 real positions and not over 78 positions of which 66 are pads.
    model = text_model("mean")
    tokens = padded_window()
    real = int((tokens[0] != PAD).sum())
    assert 0 < real < CONTEXT
    with torch.no_grad():
        hidden = model.backbone(tokens)
        pooled = model.pool(tokens)
        assert torch.allclose(pooled, hidden[:, :real].mean(dim=1), atol=1e-6)
        # Dividing by the window length instead, or summing the pad states in, is a different
        # number: the test would pass vacuously if the pads contributed nothing.
        assert not torch.allclose(pooled, hidden.mean(dim=1), atol=1e-4)
        assert not torch.allclose(pooled, hidden[:, :real].sum(dim=1) / CONTEXT, atol=1e-4)


def test_last_plus_text_averages_exactly_the_text_positions() -> None:
    # ADR-0026 (d), second block: the mean over the window's text-token positions, which are
    # <txt>, </txt> and every id in the text block -- and nothing else.
    model = text_model()
    tokens = padded_window()
    d_model = spec().d_model
    positions = [6, 7, 8, 9]
    assert [int(t) for t in tokens[0, positions]] == [4, 50, 51, 5]
    with torch.no_grad():
        hidden = model.backbone(tokens)
        pooled = model.pool(tokens)
        assert pooled.shape == (2, 2 * d_model + 1)
        assert torch.allclose(
            pooled[0, d_model : 2 * d_model], hidden[0, positions].mean(0), 0, 1e-6
        )
        # Not the mean over every real position, and not over the telemetry ones.
        assert not torch.allclose(pooled[0, d_model : 2 * d_model], hidden[0, :12].mean(0), 0, 1e-4)


def test_last_plus_text_is_the_zero_vector_and_a_zero_flag_without_text() -> None:
    # ADR-0026 (d): "when the window holds no such position this block is the zero vector",
    # and the third block is the has-text indicator. Row 1 of the synthetic window holds none.
    model = text_model()
    tokens = padded_window()
    d_model = spec().d_model
    with torch.no_grad():
        pooled = model.pool(tokens)
    assert torch.equal(pooled[1, d_model : 2 * d_model], torch.zeros(d_model))
    assert float(pooled[1, -1]) == 0.0
    assert float(pooled[0, -1]) == 1.0
    assert not torch.equal(pooled[0, d_model : 2 * d_model], torch.zeros(d_model))


def test_last_plus_texts_first_block_is_the_read_out_in_force() -> None:
    # ADR-0026 (d), first block: h[L], which is exactly what RiskModel.pool returns under the
    # `last` pooling with pad_id set. On a window with no text, (d) is (a) plus a constant.
    model = text_model()
    last = text_model("last")
    last.backbone.load_state_dict(model.backbone.state_dict())
    tokens = padded_window()
    d_model = spec().d_model
    with torch.no_grad():
        assert torch.equal(model.pool(tokens)[:, :d_model], last.pool(tokens))


def test_last_plus_text_refuses_to_build_without_its_text_positions() -> None:
    with pytest.raises(ValueError, match="text positions"):
        RiskModel(spec(), RiskSpec(pooling="last_plus_text"), frozen=True, pad_id=PAD)


def test_the_head_input_width_follows_the_read_out() -> None:
    assert RiskSpec().input_width(192) == 192
    assert RiskSpec(pooling="mean").input_width(192) == 192
    assert RiskSpec(pooling="last_plus_text", text_positions=RULE).input_width(192) == 385
    wide = text_model()
    assert wide.head.up.in_features == 2 * spec().d_model + 1
    assert wide.head.norm.weight.shape == (2 * spec().d_model + 1,)
    # The hidden layer is the one in force: head_hidden x d_model, whatever the input width.
    assert wide.head.up.out_features == text_model("last").head.up.out_features == spec().d_model
    assert wide(padded_window()).shape == (2,)
