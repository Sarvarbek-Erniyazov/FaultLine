"""F9-3: the second implementations behind the claim table, the arm labels, the committed record."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from faultline.config import file_hash, load_config
from faultline.evaluation.abstention_gate import AbstentionConfig
from faultline.evaluation.abstention_outcome import (
    OPERATING_POINT_COMMIT,
    ap_by_thresholds,
    aurc_by_curve,
    random_aurc_by_curve,
    second_reading,
)
from faultline.evaluation.abstention_verdict import (
    ARM_LABELS,
    fit_operating_point,
    load_ensemble,
    validation_file,
)
from faultline.evaluation.metrics import average_precision
from faultline.evaluation.risk_coverage import (
    VALIDATION,
    OperatingPoint,
    admission_order,
    aurc,
    coverage_and_risk,
    permutation_seeds,
    random_aurc,
)

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/eval/abstention_v0.yaml"
RECORD = REPO / "reports/data/abstention_operating_points_v0.json"


def test_average_precision_by_thresholds_matches_the_cumsum_one_with_ties() -> None:
    rng = np.random.default_rng(3)
    p = np.round(rng.random(2000), 2)  # heavy ties
    y = (rng.random(2000) < 0.1 + 0.3 * p).astype(np.float64)
    assert ap_by_thresholds(p, y) == pytest.approx(average_precision(p, y), abs=1e-12)


def test_aurc_as_a_curve_mean_matches_the_weighted_sum() -> None:
    rng = np.random.default_rng(4)
    errors = rng.random(500) < 0.2
    u = np.round(rng.random(500), 1)
    order = admission_order(u, False)
    assert aurc_by_curve(errors, order) == pytest.approx(aurc(errors, order), abs=1e-12)
    seeds = permutation_seeds(20260924, 7)
    assert random_aurc_by_curve(errors, seeds) == pytest.approx(
        random_aurc(errors, seeds), abs=1e-12
    )


def test_the_second_reading_of_coverage_and_risk() -> None:
    rng = np.random.default_rng(5)
    p, u = rng.random(300), rng.random(300)
    y = (rng.random(300) < 0.2).astype(np.float64)
    point = OperatingPoint(tau=0.5, kappa=0.7, margin_cut=0.1)
    second = second_reading(p, u, y, point, np.zeros(0, dtype=np.uint64))
    cov, risk = coverage_and_risk(u <= 0.7, (p >= 0.5) != (y > 0.5))
    assert (second["coverage"], second["risk"]) == pytest.approx((cov, risk), abs=1e-12)
    assert "aurc_random" not in second


def test_the_control_iii_arm_carries_the_authors_label() -> None:
    assert ARM_LABELS["tel_only_a"] == (
        "tel_only backbone, (a), on R0 windows (ADR-0025 control iii)"
    )
    config = load_config(CONFIG, AbstentionConfig)
    assert {arm.name for arm in config.arms} == set(ARM_LABELS)


def test_the_committed_record_is_validation_only_and_labelled() -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    assert record["split"] == "validation"
    assert record["test_files_opened"] is False
    assert set(record["arms"]) == set(ARM_LABELS.values())
    assert len(OPERATING_POINT_COMMIT) == 7


def test_the_committed_record_refits_exactly_from_the_validation_scores() -> None:
    config = load_config(CONFIG, AbstentionConfig)
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    directory = REPO / "checkpoints/abstention_v0_30c9c714"
    counts = config.splits.validation
    for row in record["arms"].values():
        name = row["config_arm"]
        files = [validation_file(directory, name, s, config.stride) for s in config.seeds]
        if not all(f.is_file() for f in files):
            pytest.skip("F9-2's validation scores are not on this machine")
        assert [file_hash(f, 64) for f in files] == row["sha256"]
        refit = fit_operating_point(
            load_ensemble(files, VALIDATION, counts.windows, counts.positives),
            config.operating_model.kappa_coverage,
        )
        for key, value in refit.items():
            assert row[key] == value, (name, key)
