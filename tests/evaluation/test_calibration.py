"""The prior correction is part of the method: a balanced head recovers the true base rate."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import torch

from faultline.evaluation.calibration import (
    NaturalRateScores,
    abstention_threshold,
    at_natural_rate,
    expected_calibration_error,
    mean_predicted_rate,
)
from faultline.model.risk import prior_correction
from faultline.training.windows import BalancedWindowSampler, WindowSampler, WindowSet

#: Tokens a window holds; one step of eight, so a window is one row of the stream.
WIDTH = 8

#: The natural base rate of the synthetic windows, near the project's 2.2%.
NATURAL = 0.03


def _windows(path: Path, n: int, seed: int) -> WindowSet:
    """Windows whose tokens are class-conditional Gaussian draws around 50 +/- 3."""
    rng = np.random.default_rng(seed)
    labels = (rng.random(n) < NATURAL).astype(np.float32)
    centre = np.where(labels > 0.5, 53.0, 47.0)[:, None]
    tokens = np.clip(np.rint(rng.normal(centre, 6.0, size=(n, WIDTH))), 0, 100).astype(np.uint16)
    tokens.tofile(path)
    stream = np.memmap(path, dtype=np.uint16, mode="r", shape=(n * WIDTH,))
    return WindowSet(
        key="synthetic__train",
        tokens=stream,
        starts=np.arange(n, dtype=np.int64),
        ends=np.arange(n, dtype=np.int64),
        labels=labels,
        years=np.full(n, 2020, dtype=np.int64),
    )


def _logits(model: torch.nn.Module, tokens: torch.Tensor) -> torch.Tensor:
    return model(tokens.float().mean(dim=1, keepdim=True)).squeeze(-1)


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory) -> tuple[np.ndarray, np.ndarray, float]:
    """A logistic head trained on balanced batches, scored on held-out natural-rate windows."""
    root = tmp_path_factory.mktemp("calibration")
    train = _windows(root / "train.bin", 40_000, seed=1)
    held_out = _windows(root / "test.bin", 40_000, seed=2)
    sampler = BalancedWindowSampler([train], 64, 32, WIDTH, 1)
    torch.manual_seed(0)
    model = torch.nn.Sequential(torch.nn.Linear(1, 1))
    optimiser = torch.optim.Adam(model.parameters(), lr=0.05)
    steps = 1500
    # decayed to zero, as every run in this project decays its rate: the last iterate of a
    # constant-rate run is a noisy draw around the fit, and calibration reads that iterate
    schedule = torch.optim.lr_scheduler.LambdaLR(optimiser, lambda k: 1 - k / steps)
    stream = sampler.forever(seed=3)
    for _ in range(steps):
        tokens, labels, _ = next(stream)
        loss = torch.nn.functional.binary_cross_entropy_with_logits(
            _logits(model, tokens - 50), labels
        )
        optimiser.zero_grad()
        loss.backward()  # type: ignore[no-untyped-call]
        optimiser.step()
        schedule.step()
    scorer = WindowSampler([held_out], 4096, WIDTH, 1, labelled=True)
    logits, labels = [], []
    with torch.no_grad():
        for tokens, target, _ in scorer.epoch():
            logits.append(_logits(model, tokens - 50).numpy())
            labels.append(target.numpy())
    return np.concatenate(logits), np.concatenate(labels), sampler.natural_rate


def test_a_balanced_head_corrected_to_the_prior_recovers_the_true_base_rate(
    trained: tuple[np.ndarray, np.ndarray, float],
) -> None:
    logits, labels, natural = trained
    true_rate = float(labels.mean())
    uncorrected = at_natural_rate(logits, train_rate=0.5, natural_rate=0.5)
    corrected = at_natural_rate(logits, train_rate=0.5, natural_rate=natural)
    # without the correction the head reads its training prior, several times the truth
    assert mean_predicted_rate(uncorrected) > 4 * true_rate
    # with it, the mean prediction on held-out natural-rate windows is the base rate
    assert mean_predicted_rate(corrected) == pytest.approx(true_rate, rel=0.15)
    assert expected_calibration_error(corrected, labels) < 0.01
    assert expected_calibration_error(uncorrected, labels) > 0.1


def test_the_one_term_multiclass_rule_would_still_read_above_the_prior(
    trained: tuple[np.ndarray, np.ndarray, float],
) -> None:
    logits, labels, natural = trained
    one_term = logits - math.log(0.5 / natural)
    corrected = at_natural_rate(logits, 0.5, natural)
    assert one_term.mean() - corrected.logits.mean() == pytest.approx(
        math.log((1 - natural) / 0.5), abs=1e-5
    )
    probability = 1 / (1 + np.exp(-one_term))
    assert probability.mean() > 1.3 * float(labels.mean())
    assert probability.mean() > mean_predicted_rate(corrected)


def test_calibration_and_abstention_refuse_uncorrected_logits() -> None:
    raw = np.zeros(10)
    labels = np.zeros(10)
    with pytest.raises(TypeError, match="at_natural_rate"):
        expected_calibration_error(raw, labels)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="at_natural_rate"):
        abstention_threshold(raw, 0.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="at_natural_rate"):
        mean_predicted_rate(raw)  # type: ignore[arg-type]


def test_the_offset_is_the_risk_modules_prior_correction() -> None:
    scores = at_natural_rate(np.array([0.0, 1.0]), 0.5, 0.022)
    assert isinstance(scores, NaturalRateScores)
    assert scores.offset == prior_correction(0.5, 0.022)
    assert scores.probabilities[0] == pytest.approx(0.022)


def test_abstention_answers_the_requested_share_of_windows() -> None:
    rng = np.random.default_rng(0)
    scores = at_natural_rate(rng.normal(size=1000), 0.022, 0.022)
    threshold = abstention_threshold(scores, 0.8)
    confidence = np.maximum(scores.probabilities, 1 - scores.probabilities)
    assert (confidence >= threshold).mean() == pytest.approx(0.8, abs=0.002)
    with pytest.raises(ValueError, match="coverage"):
        abstention_threshold(scores, 0.0)


def test_the_corrected_over_read_is_small_and_its_interval_is_on_record(
    trained: tuple[np.ndarray, np.ndarray, float],
) -> None:
    # ADR-0019, E3 ruling: corrected 3.07% against a held-out 2.89%. A paired bootstrap over
    # the held-out windows puts an interval on the over-read. It excludes zero on this set, and
    # it bounds the relative over-read well inside the 15% the calibration test allows.
    logits, labels, natural = trained
    probabilities = at_natural_rate(logits, 0.5, natural).probabilities
    rng = np.random.default_rng(20260916)
    ratios, gaps = [], []
    for _ in range(2_000):
        rows = rng.integers(0, labels.size, labels.size)
        predicted, observed = probabilities[rows].mean(), labels[rows].mean()
        ratios.append(predicted / observed)
        gaps.append(predicted - observed)
    low, high = np.quantile(gaps, [0.025, 0.975])
    ratio_low, ratio_high = np.quantile(ratios, [0.025, 0.975])
    assert 0.0 < low < high < 0.004
    assert 1.0 < ratio_low < ratio_high < 1.15
    # half the over-read is the training sample's rate, which the correction reads by design
    assert natural > float(labels.mean())
