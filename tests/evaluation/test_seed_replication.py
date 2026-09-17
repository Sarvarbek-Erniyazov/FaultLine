"""F3: the shipped seed replication is the one ADR-0024's addendum registered."""

from __future__ import annotations

from pathlib import Path

from faultline.config import load_config
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.seed_replication import SeedReplicationConfig

REPO = Path(__file__).resolve().parents[2]


def test_the_shipped_replication_is_the_f3_addendum() -> None:
    config = load_config(REPO / "configs/train/seed_replication_v0.yaml", SeedReplicationConfig)
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "### Addendum (F3), registered 2026-09-17 before its code or run" in decisions
    assert config.new_seeds == [2, 3] and config.init_seeds == [1, 2, 3]
    assert config.design == "final_position"
    gate = load_config(REPO / config.gate_config, GateCheckConfig)
    # the gate run's pretraining protocol, only the seed differs
    assert gate.seed == 1 and gate.seed not in config.new_seeds
    assert gate.budget(2048).steps == 763


def test_a_probe_history_is_recovered_from_its_run_log(tmp_path: Path) -> None:
    from faultline.evaluation.seed_replication import history_from_log, same_step_logs

    log = tmp_path / "seed_replication_v0_1.log"
    log.write_text(
        "x INFO faultline.training.loop | f3/S2_trained_seed3 step 0/1000 validation 0.0192 "
        "(reference)\n"
        "x INFO faultline.training.loop | f3/S2_trained_seed2 step 25/1000 lr 1e-3 loss 0.6 "
        "validation 0.0300\n"
        "x INFO faultline.training.loop | f3/S2_trained_seed3 step 25/1000 lr 1e-3 loss 0.6 "
        "validation 0.0250 *\n",
        encoding="utf-8",
    )
    assert history_from_log([log], "f3/S2_trained_seed3") == [(0, 0.0192), (25, 0.025)]
    # a re-run's label is not confused with the original's
    assert history_from_log([log], "f3/S2_trained_seed3/rerun") == []
    other = tmp_path / "b.csv"
    other.write_text(log.read_text(encoding="utf-8"), encoding="utf-8")
    assert same_step_logs(log, other)
