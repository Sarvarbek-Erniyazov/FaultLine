"""M3 step 0: balanced sampling, budgets in positives seen, the probe's own learning rate."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from faultline.config import config_hash, load_config
from faultline.evaluation.metrics import average_precision
from faultline.model.risk import prior_correction
from faultline.training.config import (
    LadderConfig,
    LadderModel,
    PositiveAwareRiskStage,
    RiskStage,
)
from faultline.training.windows import BalancedWindowSampler, ShardSet, load_windows

from .test_windows import CONTEXT_STEPS, TOKENS_PER_STEP, make_shards

REPO = Path(__file__).resolve().parents[2]


def positive_budget(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "positives": 100,
        "batch_windows": 8,
        "accumulate": 2,
        "learning_rate": 5e-4,
        "evaluations": 2,
    }
    payload.update(overrides)
    return payload


def stage_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sampling": "balanced",
        "positive_fraction": 0.5,
        "probe": positive_budget(learning_rate=2e-3),
        "finetune": positive_budget(),
        "random": positive_budget(),
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------------ the configuration


def test_the_v1_file_loads_as_the_positive_aware_stage() -> None:
    config = load_config(REPO / "configs/train/telemetry_v1.yaml", LadderConfig)
    assert isinstance(config.risk, PositiveAwareRiskStage)
    assert config.risk.sampling == "balanced"
    for kind in ("probe", "finetune", "random"):
        budget = config.budget_for(kind)
        # 16,000 positives at 16 a step: 1,000 steps, 32,000 windows
        assert budget.windows == 32_000
        assert budget.steps == 1_000
    assert config.risk.probe.learning_rate != config.risk.finetune.learning_rate


def test_the_frozen_v0_file_still_loads_unchanged() -> None:
    # M1e's report names this hash; widening the risk field must not move it
    config = load_config(REPO / "configs/train/telemetry_v0.yaml", LadderConfig)
    model = load_config(REPO / "configs/model/ladder_v0.yaml", LadderModel)
    assert isinstance(config.risk, RiskStage)
    combined = {"train": config.model_dump(mode="json"), "model": model.model_dump(mode="json")}
    assert config_hash(combined) == "70860821"


def test_the_budget_is_derived_from_positives_and_rounds_up_to_a_whole_step() -> None:
    stage = PositiveAwareRiskStage.model_validate(stage_payload())
    budget = stage.budget("finetune")
    # 4 positives a batch, 2 batches a step: 8 a step; 100 positives need 13 steps
    assert budget.steps == 13
    assert budget.windows == 13 * 8 * 2
    assert budget.learning_rate == 5e-4


def test_the_probe_sharing_the_finetune_rate_is_refused() -> None:
    with pytest.raises(ValidationError, match="own"):
        PositiveAwareRiskStage.model_validate(stage_payload(probe=positive_budget()))


def test_the_control_must_match_the_finetune_it_controls() -> None:
    for field, value in (("positives", 200), ("learning_rate", 1e-3), ("batch_windows", 16)):
        with pytest.raises(ValidationError, match="differs from finetune"):
            PositiveAwareRiskStage.model_validate(
                stage_payload(random=positive_budget(**{field: value}))
            )


def test_a_fraction_that_is_not_a_whole_number_of_positives_is_refused() -> None:
    with pytest.raises(ValidationError, match="whole number"):
        PositiveAwareRiskStage.model_validate(stage_payload(positive_fraction=0.3))


def test_a_stage_without_a_declared_sampling_is_not_positive_aware() -> None:
    payload = stage_payload()
    del payload["sampling"]
    with pytest.raises(ValidationError):
        PositiveAwareRiskStage.model_validate(payload)


def test_the_stage_carries_no_loss_weight_to_double_count_with() -> None:
    payload = copy.deepcopy(stage_payload())
    payload["positive_weight"] = 10.0
    with pytest.raises(ValidationError):
        PositiveAwareRiskStage.model_validate(payload)


# ------------------------------------------------------------------ the sampler


@pytest.fixture
def labelled(tmp_path: Path) -> list[Any]:
    shards = ShardSet.load(make_shards(tmp_path / "shards"))
    return [
        load_windows(shards, key, stride=1, label="narrow_within_24h")
        for key in shards.keys("train")
    ]


def test_every_batch_holds_exactly_the_declared_positives(labelled: list[Any]) -> None:
    sampler = BalancedWindowSampler(labelled, 6, 3, TOKENS_PER_STEP, CONTEXT_STEPS)
    stream = sampler.forever(seed=1)
    for _ in range(20):
        tokens, labels, _which = next(stream)
        assert tokens.shape == (6, TOKENS_PER_STEP * CONTEXT_STEPS)
        assert int(labels.sum()) == 3
    assert sampler.positives_seen == 60


def test_every_positive_is_seen_once_before_any_is_seen_twice(labelled: list[Any]) -> None:
    sampler = BalancedWindowSampler(labelled, 4, 2, TOKENS_PER_STEP, CONTEXT_STEPS)
    batches = -(-sampler.positive_rows // 2)
    stream = sampler.forever(seed=7)
    seen: list[bytes] = []
    for _ in range(batches):
        tokens, labels, _which = next(stream)
        seen += [tokens[i].numpy().tobytes() for i in range(4) if labels[i] > 0.5]
    first_pass = seen[: sampler.positive_rows]
    assert len(set(first_pass)) == sampler.positive_rows


def test_the_natural_rate_is_the_share_of_positive_windows(labelled: list[Any]) -> None:
    sampler = BalancedWindowSampler(labelled, 6, 3, TOKENS_PER_STEP, CONTEXT_STEPS)
    total = sum(len(s) for s in labelled)
    positives = int(sum(s.labels.sum() for s in labelled))
    assert sampler.positive_rows == positives
    assert math.isclose(sampler.natural_rate, positives / total)


def test_a_balanced_sampler_refuses_to_serve_an_evaluation_pass(labelled: list[Any]) -> None:
    sampler = BalancedWindowSampler(labelled, 6, 3, TOKENS_PER_STEP, CONTEXT_STEPS)
    with pytest.raises(TypeError, match="natural rate"):
        next(sampler.epoch())


def test_a_batch_without_room_for_both_classes_is_refused(labelled: list[Any]) -> None:
    with pytest.raises(ValueError, match="positive and a"):
        BalancedWindowSampler(labelled, 4, 4, TOKENS_PER_STEP, CONTEXT_STEPS)


# ------------------------------------------------------------------ the prior correction


def test_the_prior_correction_maps_a_balanced_score_back_to_the_natural_rate() -> None:
    offset = prior_correction(0.5, 0.022)
    # a head that learned only the prior outputs logit 0 at 50%; corrected, 2.2%
    assert math.isclose(1 / (1 + math.exp(-(0.0 + offset))), 0.022)
    assert prior_correction(0.1, 0.1) == 0.0
    with pytest.raises(ValueError, match="strictly between"):
        prior_correction(0.5, 0.0)


def test_the_prior_correction_leaves_auprc_unchanged() -> None:
    generator = np.random.default_rng(3)
    logits = generator.normal(size=500)
    labels = (generator.random(500) < 0.1).astype(np.float64)
    shifted = logits + prior_correction(0.5, 0.022)
    assert average_precision(shifted, labels) == average_precision(logits, labels)


def test_the_ladder_opens_a_balanced_sampler_at_the_stage_fraction(tmp_path: Path) -> None:
    from faultline.evaluation.ladder import balanced_training_sampler

    shards = ShardSet.load(make_shards(tmp_path / "shards"))
    # the synthetic shard is too short for v1's stride of 6 to keep a positive window
    config = load_config(REPO / "configs/train/telemetry_v1.yaml", LadderConfig).model_copy(
        update={"train_stride": 2}
    )
    stage = PositiveAwareRiskStage.model_validate(stage_payload())
    sampler = balanced_training_sampler(shards, config, stage, batch_windows=8)
    assert sampler.positives_per_batch == 4
    _tokens, labels, _which = next(sampler.forever(seed=2))
    assert int(labels.sum()) == 4
