"""Perplexity arithmetic, target classes and generation statistics (Lesson 11, C4)."""

from __future__ import annotations

import importlib
import json
import math
from pathlib import Path

import numpy as np
import pytest
import torch

from faultline.tokenizers.layout import BIN_OFFSET, TEXT_OFFSET

# Imported by name: the root package ``evaluation`` shares its name with ``tests/evaluation``,
# which the pinned pre-commit ruff sorts as first-party and the venv's ruff as third-party.
ppl = importlib.import_module("evaluation.perplexity")
gen = importlib.import_module("evaluation.generate")

RESULTS = Path(__file__).resolve().parents[2] / "evaluation" / "results.json"
N_BINS, N_TEXT = 256, 32768
VOCAB = TEXT_OFFSET + N_TEXT


def test_the_slide_example() -> None:
    mean = ppl.mean_nll_of_probabilities([0.40, 0.30, 0.20, 0.10])
    assert mean == pytest.approx(1.508, abs=5e-4)
    assert ppl.perplexity(mean) == pytest.approx(4.52, abs=5e-3)
    # The slide's 4.53 is exp of the rounded 1.51.
    assert ppl.perplexity(round(mean, 2)) == pytest.approx(4.53, abs=5e-3)


def test_uniform_logits_give_the_size_of_the_valid_set() -> None:
    targets = torch.tensor([[BIN_OFFSET + 3, ppl.NAN_ID, TEXT_OFFSET + 7, 8]])
    classes = torch.from_numpy(ppl.target_classes(targets.numpy(), N_BINS, N_TEXT))
    valid = {k: torch.as_tensor(ppl.valid_ids(k, N_BINS, N_TEXT)) for k in ppl.CLASS_NAMES}
    full, restricted = ppl.token_nll(torch.zeros(1, 4, VOCAB), targets, classes, valid)
    assert math.exp(float(restricted[0, 0])) == pytest.approx(257)
    assert math.exp(float(restricted[0, 1])) == pytest.approx(257)
    assert math.exp(float(restricted[0, 2])) == pytest.approx(32768)
    assert float(restricted[0, 3]) == 0.0  # excluded
    assert math.exp(float(full[0, 0])) == pytest.approx(VOCAB)


def test_targets_are_classed_by_the_vocabulary() -> None:
    targets = np.array([8, 9, BIN_OFFSET, BIN_OFFSET + 255, BIN_OFFSET + 256, 4, 5, TEXT_OFFSET])
    assert ppl.target_classes(targets, N_BINS, N_TEXT).tolist() == [
        ppl.EXCLUDED,
        ppl.VALUE,
        ppl.VALUE,
        ppl.VALUE,
        ppl.EXCLUDED,
        ppl.EXCLUDED,
        ppl.EXCLUDED,
        ppl.TEXT,
    ]


def test_unigram_is_add_one_within_the_class() -> None:
    counts = np.zeros(VOCAB, dtype=np.int64)
    counts[BIN_OFFSET] = 256
    table = ppl.unigram_log_probs(counts, N_BINS, N_TEXT)
    assert math.exp(table[ppl.VALUE][BIN_OFFSET]) == pytest.approx(257 / (256 + 257))
    assert math.exp(table[ppl.VALUE][ppl.NAN_ID]) == pytest.approx(1 / (256 + 257))
    assert table[ppl.VALUE][TEXT_OFFSET] == -np.inf
    assert math.exp(table[ppl.TEXT][TEXT_OFFSET]) == pytest.approx(1 / N_TEXT)
    uniform = ppl.unigram_log_probs(np.zeros(VOCAB, dtype=np.int64), N_BINS, N_TEXT)
    facts = ppl.unigram_versus_uniform(uniform, N_BINS, N_TEXT)
    assert facts["kl_unigram_to_uniform_nats"] == pytest.approx(0.0, abs=1e-12)


def test_generation_statistics() -> None:
    assert gen.distinct([[1, 2, 3, 1]], 1) == 0.75
    assert gen.distinct([[1, 2, 1, 2]], 2) == pytest.approx(2 / 3)
    assert gen.repeated_4gram_rate([[1, 2, 3, 4, 1, 2, 3, 4]]) == pytest.approx(1 / 5)
    assert gen.repeated_4gram_rate([[1, 2, 3, 4], [1, 2, 3, 4]]) == 0.0  # within a sample only
    assert math.isnan(gen.distinct([[1]], 2))


def test_the_prompts_are_four_and_four() -> None:
    styles = [style for style, _ in gen.read_prompts()]
    assert styles.count("status") == 4 and styles.count("narrative") == 4
    assert len(gen.STRATEGIES) == 5


def test_results_carry_the_label_when_written() -> None:
    if not RESULTS.exists():
        pytest.skip("evaluation/results.json not written")
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert results["label"] == (
        "Course Lesson 11 output. Descriptive. Not a registered ADR finding."
    )
    assert results["course_lesson_output"]["note"] == "BLEU/ROUGE not computed: no reference texts."
    assert results["course_lesson_output"]["a4_logged_loss_check"]["reproduced"]
