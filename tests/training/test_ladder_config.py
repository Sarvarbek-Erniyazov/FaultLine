"""The ladder configuration: the rules that make it an experiment rather than a sweep."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from faultline.config import load_config
from faultline.training.config import RUN_KINDS, LadderConfig, LadderModel


def model_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "context_steps": 144,
        "rungs": [
            {"name": "S0", "d_model": 80, "n_layer": 4, "n_head": 5, "seeds": [1, 2, 3]},
            {"name": "S1", "d_model": 128, "n_layer": 6, "n_head": 8, "seeds": [1]},
        ],
    }
    payload.update(overrides)
    return payload


def budget(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "windows": 400,
        "batch_windows": 8,
        "accumulate": 1,
        "learning_rate": 5e-4,
        "evaluations": 2,
    }
    payload.update(overrides)
    return payload


def train_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tokenizer_config": "configs/tokenizer/quantile_bins_v2.yaml",
        "model_config_path": "configs/model/ladder_v0.yaml",
        "train_stride": 6,
        "lm": budget(windows=800),
        "risk": {"probe": budget(), "finetune": budget(), "random": budget()},
        "evaluation": {
            "selection_windows": 100,
            "validation_windows": 200,
            "test_windows": 200,
        },
    }
    payload.update(overrides)
    return payload


def test_the_control_must_match_the_run_it_controls() -> None:
    # The ablation's whole claim is that the arms differ in initialisation and nothing
    # else. A control with its own budget would make the comparison unreadable, so the
    # configuration refuses it rather than the report explaining it away afterwards.
    for field, value in (("windows", 800), ("learning_rate", 1e-3), ("batch_windows", 16)):
        payload = train_payload()
        payload["risk"]["random"] = budget(**{field: value})
        with pytest.raises(ValidationError, match="differs from finetune"):
            LadderConfig.model_validate(payload)


def test_a_risk_run_without_the_language_model_it_reads_is_refused() -> None:
    with pytest.raises(ValidationError, match="must be in runs"):
        LadderConfig.model_validate(train_payload(runs=["probe", "finetune", "random"]))


def test_the_control_alone_needs_no_language_model() -> None:
    # The randomly initialised arm reads nothing, so it is the one run that can stand on
    # its own; refusing it would be the validator overreaching.
    assert LadderConfig.model_validate(train_payload(runs=["random"])).runs == ["random"]


def test_a_training_stride_of_one_is_refused() -> None:
    with pytest.raises(ValidationError, match="effective sample size"):
        LadderConfig.model_validate(train_payload(train_stride=1))


def test_a_repeated_run_kind_is_refused() -> None:
    with pytest.raises(ValidationError, match="listed twice"):
        LadderConfig.model_validate(train_payload(runs=["lm", "lm", "probe"]))


def test_rungs_must_be_listed_smallest_first() -> None:
    payload = model_payload()
    payload["rungs"] = list(reversed(payload["rungs"]))
    with pytest.raises(ValidationError, match="smallest first"):
        LadderModel.model_validate(payload)


def test_rung_names_must_be_distinct() -> None:
    payload = model_payload()
    payload["rungs"][1]["name"] = "S0"
    with pytest.raises(ValidationError, match="names repeat"):
        LadderModel.model_validate(payload)


def test_a_width_not_divisible_by_the_head_count_is_refused() -> None:
    payload = model_payload()
    payload["rungs"][0]["n_head"] = 7
    with pytest.raises(ValidationError, match="not divisible"):
        LadderModel.model_validate(payload)


def test_the_budget_converts_windows_to_optimiser_steps() -> None:
    config = LadderConfig.model_validate(train_payload())
    assert config.lm.steps == 800 // 8
    assert config.budget_for("probe").steps == 400 // 8
    assert [config.budget_for(k) for k in RUN_KINDS]


def test_the_shipped_configuration_is_the_experiment_it_claims(repo_root: Path) -> None:
    train = load_config(repo_root / "configs" / "train" / "telemetry_v0.yaml", LadderConfig)
    model = load_config(repo_root / train.model_config_path, LadderModel)
    assert train.runs == list(RUN_KINDS)
    assert train.train_stride == 6
    assert train.evaluation.stride == 1
    assert train.tokenizer_config == "configs/tokenizer/quantile_bins_v2.yaml"
    # context is one number for the whole ladder: it is a separate ablation, not a
    # confound with size
    assert model.context_steps == 144
    assert [len(r.seeds) for r in model.rungs] == [3, 3, 1, 1]
    # every risk arm gets the same budget, so no arm is tuned more than another
    arms = [train.risk.probe, train.risk.finetune, train.risk.random]
    assert len({(a.windows, a.batch_windows, a.accumulate, a.learning_rate) for a in arms}) == 1


def test_the_shipped_configuration_survives_a_round_trip(repo_root: Path) -> None:
    original = load_config(repo_root / "configs" / "train" / "telemetry_v0.yaml", LadderConfig)
    again = LadderConfig.model_validate(copy.deepcopy(original.model_dump(mode="json")))
    assert again == original
