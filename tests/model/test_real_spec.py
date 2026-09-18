"""Causality, padding and the initial loss at the specification the F6 arms run (S2, 33,952, 2,048).

``test_transformer.py`` checks causality on a toy decoder at one position, batch 1, forward only,
and the initial loss on a 64-token vocabulary. Those tests stay as they are. This module binds the
same properties to the code F6 runs:

- The S2 rung of ``configs/model/ladder_v0.yaml`` at the joint vocabulary (33,952 ids) and the
  mixture's 2,048-token context.
- Both attention paths and the trainable-tail forward.
- ``RiskModel.pool``, the state the tail-anchored probe reads from a right-padded window.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import torch

from faultline.config import config_hash, load_config
from faultline.model.risk import RiskModel, RiskSpec
from faultline.model.transformer import ModelSpec, TelemetryDecoder
from faultline.tokenizers.layout import VocabLayout
from faultline.training.config import LadderModel
from faultline.training.joint_windows import PAD_ID, SEP_ID

REPO = Path(__file__).resolve().parents[2]
VOCAB = VocabLayout.from_sizes(32768, 14, 256).total_size
CONTEXT = 2048
#: ln(33,952), the loss of a uniform prediction over the joint vocabulary.
LN_VOCAB = math.log(VOCAB)


def s2() -> ModelSpec:
    """The S2 rung as the F6 arms build it: joint vocabulary, 2,048-token context."""
    ladder = load_config(REPO / "configs/model/ladder_v0.yaml", LadderModel)
    rung = next(r for r in ladder.rungs if r.name == "S2")
    return rung.spec(CONTEXT, VOCAB, ladder.dropout)


@pytest.fixture(scope="module")
def decoders() -> dict[str, TelemetryDecoder]:
    """The S2 decoder on the fused path, and the same weights on the explicit path."""
    torch.manual_seed(0)
    fused = TelemetryDecoder(s2(), fused=True).eval()
    explicit = TelemetryDecoder(s2(), fused=False).eval()
    explicit.load_state_dict(fused.state_dict())
    return {"fused": fused, "explicit": explicit}


def test_the_spec_is_the_one_f6_runs() -> None:
    spec = s2()
    assert (spec.d_model, spec.n_layer, spec.n_head) == (192, 8, 8)
    assert (spec.vocab_size, spec.context) == (33952, 2048)
    assert LN_VOCAB == pytest.approx(10.4327, abs=5e-5)


# =====================================================================================
# 1. causality at every depth of the context
# =====================================================================================


@pytest.mark.parametrize("path", ["fused", "explicit", "trainable_tail"])
@pytest.mark.parametrize("position", [0, 1, 517, 2046])
def test_changing_a_token_moves_nothing_before_it(
    decoders: dict[str, TelemetryDecoder], path: str, position: int
) -> None:
    model = decoders["explicit" if path == "explicit" else "fused"]

    def run(tokens: torch.Tensor) -> torch.Tensor:
        if path == "trainable_tail":
            return model.forward_with_trainable_tail(tokens, 2)
        return model(tokens)

    generator = torch.Generator().manual_seed(position)
    tokens = torch.randint(1, VOCAB, (3, CONTEXT), generator=generator)
    changed = tokens.clone()
    changed[:, position] = (changed[:, position] + 7919) % (VOCAB - 1) + 1
    assert torch.all(changed[:, position] != tokens[:, position])
    with torch.no_grad():
        before, after = run(tokens), run(changed)
    assert torch.allclose(before[:, :position], after[:, :position], atol=1e-6)
    assert not torch.allclose(before[:, position:], after[:, position:], atol=1e-6)


# =====================================================================================
# 2. padding cannot reach the pooled state
# =====================================================================================


def _window(length: int, seed: int) -> torch.Tensor:
    """``length`` real tokens: whole telemetry steps, then a message, never a padding id."""
    rng = np.random.default_rng(seed)
    steps = -(-length // 13)
    block = np.empty((steps, 13), dtype=np.int64)
    block[:, 0] = SEP_ID
    block[:, 1:] = rng.integers(96, 1120, (steps, 12))
    tokens = block.ravel()[:length]
    if length > 13:  # a status message after the first step, as the stream writes them
        tokens[13:40] = np.r_[4, rng.integers(1184, VOCAB, 25), 5][: max(0, min(27, length - 13))]
    return torch.from_numpy(tokens)


LENGTHS = (13, 1_872, 2_000)
OTHER_PAD = 10  # <mask>: an id that never occurs in a stream, and is not <pad>


@pytest.fixture(scope="module")
def probe() -> RiskModel:
    """The frozen §a probe as F6 builds it, with the right-padding id."""
    torch.manual_seed(1)
    return RiskModel(s2(), RiskSpec(), frozen=True, pad_id=PAD_ID).eval()


def _padded(windows: list[torch.Tensor], pad: int) -> torch.Tensor:
    out = torch.full((len(windows), CONTEXT), pad, dtype=torch.long)
    for row, window in enumerate(windows):
        out[row, : window.numel()] = window
    return out


def test_the_pooled_state_is_the_last_real_position_whatever_the_padding(probe: RiskModel) -> None:
    windows = [_window(length, seed) for seed, length in enumerate(LENGTHS)]
    with torch.no_grad():
        pooled = probe.pool(_padded(windows, PAD_ID))
        hidden = probe.backbone(_padded(windows, PAD_ID))
        probe.pad_id = OTHER_PAD
        try:
            other = probe.pool(_padded(windows, OTHER_PAD))
        finally:
            probe.pad_id = PAD_ID
        probe.pad_id = None
        try:
            alone = [probe.pool(window[None])[0] for window in windows]
        finally:
            probe.pad_id = PAD_ID
    for row, length in enumerate(LENGTHS):
        # The gather reads index L - 1 ...
        assert torch.equal(pooled[row], hidden[row, length - 1])
        # ... which no padding token can reach, whatever its id ...
        assert torch.allclose(pooled[row], other[row], atol=1e-6)
        # ... and which equals the window run alone, unpadded.
        assert torch.allclose(pooled[row], alone[row], atol=1e-6)


# =====================================================================================
# 3. the loss side: pretraining never sees padding
# =====================================================================================
# TelemetryDecoder.loss has no ignore-index path, and needs none: every pretraining window is a
# full 2,048-token slice. tests/training/test_pretraining_windows.py asserts that the samplers never
# yield a short or padded window.


def test_the_pretraining_loss_has_no_padding_path() -> None:
    import inspect

    source = inspect.getsource(TelemetryDecoder.loss)
    assert "ignore_index" not in source


# =====================================================================================
# 4. the initial loss at the real specification
# =====================================================================================


def _first_batch(seed: int, count: int) -> torch.Tensor:
    """The first ``count`` windows ``pretrain_tel`` draws at ``seed``, or synthetic ones.

    Real windows are drawn exactly as pretraining draws them (the ``tel`` stream, 2,048 tokens,
    stride 6, ``default_rng(seed)``), so the check reads what a run's first step reads. A fixed
    choice is not neutral: the first window of the Kelmarsh training shard starts in a stretch
    whose initial loss is 9.5 to 9.9, and eight windows at fixed offsets read 10.33 to 10.40.
    Without the shards, the windows are synthetic with the real token regions: ``<sep>`` and 12
    bin ids a step.
    """
    from faultline.data.telemetry.bins import QuantileBinsConfig
    from faultline.data.telemetry.shards import shards_dir, tokenizer_path
    from faultline.evaluation.variance_probe import tel_windows
    from faultline.paths import ProjectPaths
    from faultline.training.mixture import JointMixtureConfig
    from faultline.training.windows import ShardSet

    mixture = load_config(REPO / "configs/train/joint_v1.yaml", JointMixtureConfig)
    joint = REPO / "data/shards/joint" / f"joint_v1_{config_hash(mixture)}"
    if not (joint / "manifest.json").is_file():
        rng = np.random.default_rng(seed)
        block = np.empty((count * 158, 13), dtype=np.int64)
        block[:, 0] = SEP_ID
        block[:, 1:] = rng.integers(96, 1120, (count * 158, 12))
        return torch.from_numpy(block.ravel()[: count * CONTEXT].reshape(count, CONTEXT))
    paths = ProjectPaths.resolve()
    bins = load_config(REPO / mixture.telemetry_tokenizer_config, QuantileBinsConfig)
    telemetry = ShardSet.load(shards_dir(paths, tokenizer_path(paths, bins)))
    windows = tel_windows(joint, telemetry, "train", mixture.training_sources, CONTEXT, 6)
    tokens, _, _ = next(windows.forever(seed, count))
    return tokens


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_initial_loss_is_ln_vocabulary_at_the_real_spec(seed: int) -> None:
    """At initialisation the S2 decoder predicts almost uniformly over 33,952 ids.

    ln(33,952) = 10.4327. The recorded seed-2 step-1 pretraining loss is 10.4175
    (``reports/data/seed_replication_v0_steps/S2_tel_only_seed2_lm.steps.csv``). This batch is
    the first 8 of that step's 32 windows. Measured 2026-09-18 in fp32 on the CPU: seed 1 10.4562,
    seed 2 10.4509, seed 3 10.4703. The step's own 32 windows reproduce the recorded step-1
    losses (10.4605, 10.4174, 10.4639 against 10.4604, 10.4175, 10.4639 on the GPU in bf16).
    """
    torch.manual_seed(seed)
    model = TelemetryDecoder(s2()).eval()
    windows = _first_batch(seed, 8)
    with torch.no_grad():
        # One window at a time: 8 x 2,047 x 33,952 logits would be 2.2 GB at once. Every
        # window is full, so the mean of the per-window means is the batch loss.
        loss = float(np.mean([float(model.loss(window[None])) for window in windows]))
    assert abs(loss - LN_VOCAB) < 0.05, loss
