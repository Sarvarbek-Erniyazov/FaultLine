"""The decoder backbone: the arithmetic, not the plumbing.

Every test here is about a property the ladder's claims rest on -- the parameter count
that is the report's axis, the causality that makes next-token prediction meaningful, and
the agreement between the fused kernel the ladder runs and the explicit implementation a
reader can check it against.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import torch

from faultline.config import load_config
from faultline.model.transformer import (
    CausalSelfAttention,
    ModelSpec,
    RMSNorm,
    TelemetryDecoder,
)
from faultline.training.config import LadderModel

CONTEXT = 78  # six steps of thirteen tokens


def tiny(**overrides: int) -> ModelSpec:
    fields: dict[str, int] = {
        "d_model": 32,
        "n_layer": 2,
        "n_head": 4,
        "context": CONTEXT,
        "vocab_size": 64,
    }
    fields.update(overrides)
    return ModelSpec(name="T", **fields)  # type: ignore[arg-type]


def test_the_backbone_parameter_count_is_the_axis_the_ladder_reports() -> None:
    # 12 L d^2 is what the rungs were chosen by: 4 d^2 of attention and 8 d^2 of MLP a
    # block. The measured count may exceed it only by the norms, which are 2d a block
    # plus a final d, and never by a matrix.
    for d_model, n_layer in ((32, 2), (80, 4), (128, 6)):
        spec = tiny(d_model=d_model, n_layer=n_layer, n_head=4)
        counts = TelemetryDecoder(spec).parameter_counts()
        norms = n_layer * 2 * d_model + d_model
        assert counts["nominal"] == 12 * n_layer * d_model**2
        assert counts["backbone"] == counts["nominal"] + norms
        assert counts["backbone"] == spec.backbone_params


def test_embeddings_are_excluded_from_the_axis_and_the_head_is_tied() -> None:
    spec = tiny()
    model = TelemetryDecoder(spec)
    counts = model.parameter_counts()
    assert counts["embeddings"] == spec.vocab_size * spec.d_model + spec.context * spec.d_model
    assert counts["total"] == counts["backbone"] + counts["embeddings"]
    # tied: the output projection is the token embedding, so there is no separate matrix
    names = {name for name, _ in model.named_parameters()}
    assert not any("lm_head" in name or "output" in name for name in names)
    hidden = torch.zeros(1, 3, spec.d_model)
    assert model.logits(hidden).shape == (1, 3, spec.vocab_size)


def test_the_fused_kernel_and_the_explicit_arithmetic_agree() -> None:
    # The ladder runs the fused kernel; this is the implementation a reader can check,
    # and the milestone would be hollow if only the call existed.
    torch.manual_seed(0)
    spec = tiny()
    attention = CausalSelfAttention(spec, fused=True).eval()
    x = torch.randn(3, CONTEXT, spec.d_model)
    with torch.no_grad():
        assert torch.allclose(attention(x), attention.explicit(x), atol=1e-5)


def test_attention_is_causal() -> None:
    # Changing a token cannot move any output before it. This is the property that makes
    # next-token prediction a prediction rather than a lookup.
    torch.manual_seed(0)
    model = TelemetryDecoder(tiny()).eval()
    tokens = torch.randint(0, 64, (1, CONTEXT))
    changed = tokens.clone()
    changed[0, 40] = (changed[0, 40] + 7) % 64
    with torch.no_grad():
        before, after = model(tokens), model(changed)
    assert torch.allclose(before[:, :40], after[:, :40], atol=1e-6)
    assert not torch.allclose(before[:, 40:], after[:, 40:], atol=1e-6)


def test_a_sequence_longer_than_the_context_is_refused() -> None:
    model = TelemetryDecoder(tiny())
    with pytest.raises(ValueError, match="exceeds context"):
        model(torch.zeros(1, CONTEXT + 1, dtype=torch.long))


def test_the_loss_predicts_every_position_but_the_first() -> None:
    torch.manual_seed(0)
    model = TelemetryDecoder(tiny())
    tokens = torch.randint(0, 64, (2, CONTEXT))
    with torch.no_grad():
        loss = model.loss(tokens)
    assert loss.ndim == 0 and torch.isfinite(loss)
    # An untrained model over a 64-token vocabulary sits near log(64).
    assert abs(float(loss) - torch.log(torch.tensor(64.0))) < 0.5


def test_rms_norm_normalises_without_centring() -> None:
    norm = RMSNorm(8)
    x = torch.randn(4, 8) * 5 + 3
    out = norm(x)
    assert torch.allclose(out.pow(2).mean(-1).sqrt(), torch.ones(4), atol=1e-4)


def test_a_width_not_divisible_by_the_head_count_is_refused() -> None:
    with pytest.raises(ValueError, match="not divisible"):
        tiny(d_model=30, n_head=4)


def test_every_shipped_rung_keeps_its_head_dimension_on_the_fused_path(repo_root: Path) -> None:
    # A head dimension not divisible by 8 drops the attention onto the kernel that
    # materialises the whole score matrix: measured at 8 times the memory and an eighth
    # of the throughput for the same parameter count. It fails silently, so it is a test.
    shipped = load_config(repo_root / "configs" / "model" / "ladder_v0.yaml", LadderModel)
    for rung in shipped.rungs:
        assert (rung.d_model // rung.n_head) % 8 == 0, rung.name


def test_the_shipped_rungs_are_the_sizes_the_ladder_claims(repo_root: Path) -> None:
    shipped = load_config(repo_root / "configs" / "model" / "ladder_v0.yaml", LadderModel)
    expected = {"S0": 0.3e6, "S1": 1.2e6, "S2": 3.5e6, "S3": 10e6}
    assert [r.name for r in shipped.rungs] == list(expected)
    for rung in shipped.rungs:
        spec = rung.spec(shipped.context_steps * 13, 1184, shipped.dropout)
        assert spec.backbone_params == pytest.approx(expected[rung.name], rel=0.05)
