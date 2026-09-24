"""F9-2's runner and F9's CPU half: the plan, the three assertions, the gates and the rule."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from faultline.config import load_config
from faultline.evaluation.abstention_gate import CORE_CHANNELS, AbstentionConfig, SplitCounts
from faultline.evaluation.abstention_runs import (
    ArmProbe,
    assert_masked_count,
    assert_validation_scoring,
    ladder_channel_offsets,
    scoring_plan,
)
from faultline.evaluation.abstention_verdict import (
    PROVISIONAL_FREE,
    arm_label,
    decide_gate_a,
    decide_gate_b,
    decide_h2,
    load_ensemble,
    operating_points,
    render_part_a,
    validation_file,
)
from faultline.evaluation.risk_coverage import TEST, Interval

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/eval/abstention_v0.yaml"
STEP = ["<sep>", *CORE_CHANNELS]


def _config() -> AbstentionConfig:
    return load_config(CONFIG, AbstentionConfig)


# -- the plan ----------------------------------------------------------------------------


def test_the_plan_is_nine_validation_scorings_then_twelve_ladder_scorings() -> None:
    plan = scoring_plan(_config())
    assert [s.kind for s in plan] == ["validation"] * 9 + ["ladder"] * 12
    assert [(s.arm, s.seed) for s in plan[:9]] == [
        (arm, seed) for arm in ("tel_only_a", "joint_a", "joint_d") for seed in (1, 2, 3)
    ]
    assert [(s.severity, s.seed) for s in plan[9:]] == [
        (k, seed) for k in (2, 4, 6, 8) for seed in (1, 2, 3)
    ]
    assert {s.arm for s in plan[9:]} == {"joint_d"}
    assert len({s.name for s in plan}) == 21


# -- assertion 1: the ladder's masks -----------------------------------------------------


def test_the_ladder_masks_are_the_registered_nested_telemetry_slots() -> None:
    masks = ladder_channel_offsets(_config(), STEP)
    assert sorted(masks) == [2, 4, 6, 8]
    assert masks[8][0] == [
        "nacelle_position_deg",
        "ambient_temp_c",
        "generator_speed_rpm",
        "rotor_speed_rpm",
        "generator_bearing_temp_c",
        "power_pu",
        "pitch_angle_deg",
        "generator_winding_temp_c",
    ]
    assert masks[2][1].tolist() == [6, 7]
    assert masks[8][1].tolist() == [2, 3, 4, 5, 6, 7, 10, 11]
    for small, large in [(2, 4), (4, 6), (6, 8)]:
        assert set(masks[small][1].tolist()) < set(masks[large][1].tolist())
    for k, (channels, offsets) in masks.items():
        assert offsets.size == k and offsets.min() >= 1
        assert sorted(STEP[o] for o in offsets) == sorted(channels)


def test_the_ladder_refuses_a_set_the_permutation_does_not_give() -> None:
    config = _config()
    tampered = config.model_copy(deep=True)
    tampered.ladder.sets[2] = ["ambient_temp_c", "nacelle_position_deg"]  # right set, wrong order
    with pytest.raises(ValueError, match="the permutation gives"):
        ladder_channel_offsets(tampered, STEP)
    swapped = tampered.model_copy(deep=True)
    swapped.ladder.sets[2] = ["nacelle_position_deg", "wind_speed_ms"]
    with pytest.raises(ValueError, match="the permutation gives"):
        ladder_channel_offsets(swapped, STEP)


def test_the_ladder_refuses_a_step_layout_that_is_not_the_records() -> None:
    reordered = ["<sep>", *reversed(CORE_CHANNELS)]
    with pytest.raises(ValueError, match="core channels"):
        ladder_channel_offsets(_config(), reordered)
    with pytest.raises(ValueError, match="core channels"):
        ladder_channel_offsets(_config(), [*CORE_CHANNELS, "<sep>"])


def test_the_masked_count_must_be_retained_steps_times_k() -> None:
    assert_masked_count("ok", 38_140_924, 19_070_462, 2)
    with pytest.raises(ValueError, match="channel slots"):
        assert_masked_count("short", 38_140_923, 19_070_462, 2)


# -- assertion 2: validation reads the test probe, final step, same framing -----------------


def _probe(tmp_path: Path, sidecar: dict[str, object]) -> ArmProbe:
    probe = tmp_path / "checkpoints" / "S2_joint_seed1_final_probe.pt"
    test = tmp_path / "checkpoints" / "S2_joint_seed1_final_R0_stride12_scores.npz"
    test.parent.mkdir(parents=True, exist_ok=True)
    test.with_suffix(".timing.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return ArmProbe("joint_a", 1, "final_position", probe, test, 0.07, -3.79)


def test_validation_scoring_requires_the_test_probe_at_its_final_step_in_its_framing(
    tmp_path: Path,
) -> None:
    good = {
        "probe": "checkpoints/S2_joint_seed1_final_probe.pt",
        "role": "final_step",
        "windows": "R0",
    }
    assert assert_validation_scoring(_probe(tmp_path, good), "R0", tmp_path)["windows"] == "R0"
    with pytest.raises(ValueError, match="framed as R0"):
        assert_validation_scoring(_probe(tmp_path, {**good, "windows": "m1"}), "R0", tmp_path)
    with pytest.raises(ValueError, match="not final"):
        assert_validation_scoring(_probe(tmp_path, {**good, "role": "selected"}), "R0", tmp_path)
    other = {**good, "probe": "checkpoints/S2_joint_seed1_probe.pt"}
    with pytest.raises(ValueError, match="was scored by"):
        assert_validation_scoring(_probe(tmp_path, other), "R0", tmp_path)


# -- assertion 3 and the operating-point record ------------------------------------------


def _write_scores(path: Path, logits: np.ndarray, labels: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        logits=logits.astype(np.float32),
        labels=labels.astype(np.float32),
        which=np.zeros(labels.size, dtype=np.int64),
        ends=np.arange(labels.size, dtype=np.int64),
        sources=np.array(["kelmarsh"]),
        prior_offset=np.float64(-1.0),
    )


def _small_config(windows: int, positives: int) -> AbstentionConfig:
    config = _config()
    validation = SplitCounts(
        shard_keys=config.splits.validation.shard_keys,
        windows=windows,
        positives=positives,
        base_rate=round(positives / windows, 4),
    )
    splits = config.splits.model_copy(update={"validation": validation})
    return config.model_copy(update={"splits": splits})


def test_load_ensemble_refuses_other_counts_and_misaligned_seeds(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    labels = (rng.random(200) < 0.1).astype(np.float32)
    files = [tmp_path / f"s{s}.npz" for s in (1, 2, 3)]
    for f in files:
        _write_scores(f, rng.normal(size=200), labels)
    positives = int(labels.sum())
    assert load_ensemble(files, TEST, 200, positives).windows == 200
    with pytest.raises(ValueError, match="registered"):
        load_ensemble(files, TEST, 199, positives)
    _write_scores(files[2], rng.normal(size=200), np.roll(labels, 1))  # same count, other rows
    with pytest.raises(ValueError, match="does not align"):
        load_ensemble(files, TEST, 200, positives)


def test_the_operating_point_is_fitted_once_from_validation_and_then_only_read(
    tmp_path: Path,
) -> None:
    rng = np.random.default_rng(1)
    labels = (rng.random(300) < 0.1).astype(np.float32)
    config = _small_config(300, int(labels.sum()))
    for arm in config.arms:
        for seed in config.seeds:
            logits = 2 * labels - 1 + rng.normal(0, 1, 300)
            _write_scores(validation_file(tmp_path, arm.name, seed, config.stride), logits, labels)
    record = tmp_path / "operating_point.json"
    first = operating_points(record, config, tmp_path)
    assert set(first) == {"tel_only_a", "joint_a", "joint_d"}
    written = json.loads(record.read_text(encoding="utf-8"))
    assert written["split"] == "validation"
    assert {"tau", "kappa", "margin_cut", "platt_a", "platt_b"} <= set(
        written["arms"][arm_label("joint_d")]
    )
    assert written["test_files_opened"] is False
    # Overwrite the validation scores: the record is read back, never refitted.
    for arm in config.arms:
        for seed in config.seeds:
            _write_scores(
                validation_file(tmp_path, arm.name, seed, config.stride),
                rng.normal(0, 5, 300),
                labels,
            )
    assert operating_points(record, config, tmp_path) == first


# -- the gates and the rule --------------------------------------------------------------


def _iv(low: float, high: float, trusted: bool = True) -> Interval:
    return Interval((low + high) / 2, low, high, 10000, 0 if trusted else 500, trusted)


def test_gate_a_and_gate_b_read_the_upper_bound_below_zero() -> None:
    config = _config()
    assert decide_gate_a(_iv(-0.02, -0.001), config.gate_a) == "pass"
    assert decide_gate_a(_iv(-0.02, 0.0), config.gate_a) == "not_evaluable"
    assert decide_gate_a(_iv(-0.02, -0.001, trusted=False), config.gate_a) == "untrusted"
    assert decide_gate_b(_iv(-0.05, -0.01), config.gate_b) == "damage"
    assert decide_gate_b(_iv(-0.05, 0.001), config.gate_b) == "not_testable"


def test_the_h2_rule_as_registered() -> None:
    rule = _config().h2_rule
    down, flat, up = _iv(-0.10, -0.02), _iv(-0.003, 0.004), _iv(0.001, 0.02)
    assert decide_h2("pass", "damage", down, flat, rule) == "supported"
    assert decide_h2("pass", "damage", down, _iv(0.0, 0.005), rule) == "inconclusive"
    assert decide_h2("pass", "damage", _iv(0.0, 0.01), up, rule) == "refuted"
    assert decide_h2("pass", "damage", _iv(0.0, 0.01), _iv(0.0, 0.01), rule) == "inconclusive"
    assert decide_h2("pass", "damage", down, _iv(-0.1, 0.0, trusted=False), rule) == "inconclusive"
    assert decide_h2("not_evaluable", "damage", down, flat, rule) == "not_evaluable"
    assert decide_h2("pass", "not_testable", down, flat, rule) == "not_testable"


# -- the report --------------------------------------------------------------------------


def test_the_part_a_report_carries_its_label_and_every_caveat() -> None:
    iv = {"value": 0.02, "low": 0.018, "high": 0.022, "discarded": 0}
    payload = {
        "adr": "ADR-0028 §2, Part A (i)",
        "label": PROVISIONAL_FREE,
        "config": "configs/eval/abstention_v0.yaml",
        "config_hash": "x",
        "windows": 137025,
        "positives": 5312,
        "blocks": 999,
        "bins": 15,
        "binning": "equal_mass",
        "bootstrap": {"replicates": 10000, "seed": 20260916, "confidence": 0.95},
        "known_under_read": [0.0176, 0.0173, 0.0189],
        "caveats": ["one", "two"],
        "git_sha": "abc",
        "rows": [
            {
                "arm": "joint_d",
                "ece": iv,
                "mean_p": iv,
                "base_rate": 0.0388,
                "seed_means": [0.02, 0.02, 0.02],
                "reliability": [
                    {"windows": 10, "mean_p": 0.01, "positive_share": 0.02, "low": 0, "high": 0.1}
                ],
            }
        ],
    }
    text = render_part_a(payload)
    assert PROVISIONAL_FREE in text and "- one" in text and "- two" in text
    assert "joint_d" in text and "0.0200" in text
