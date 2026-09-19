"""F7''s runner (ADR-0026 §3): the plan, the names, and the random-init backbones it reads."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from faultline.config import load_config
from faultline.evaluation.axis_gate import ProbeCheckpoints
from faultline.evaluation.h1_arms import ArmsLayout
from faultline.evaluation.h1_gate import H1ArmsConfig, H1GateConfig
from faultline.evaluation.h1_scoring import ScoringLayout
from faultline.evaluation.readout import ReadoutConfig
from faultline.evaluation.readout_runs import (
    ReadoutLayout,
    materialise_random_init,
    preflight,
    probe_plan,
    random_init_state,
    readout_layout,
)
from faultline.model.risk import RiskModel, RiskSpec
from faultline.model.transformer import ModelSpec, TelemetryDecoder
from faultline.paths import ProjectPaths
from faultline.seed import seed_everything

REPO = Path(__file__).resolve().parents[2]
READOUT = REPO / "configs/eval/readout_v0.yaml"
#: F3's probe record, which the layout reads to name ``tel_only``'s final-step scores.
F3 = REPO / "checkpoints/seed_replication_v0_424c4f33/S2_trained_seed1_probe.json"
TINY = ModelSpec(name="S2", d_model=16, n_layer=2, n_head=4, context=48, vocab_size=64)
SEEDS = (1, 2, 3)


def _config() -> ReadoutConfig:
    return load_config(READOUT, ReadoutConfig)


def _layout(paths: ProjectPaths) -> ReadoutLayout:
    """A layout of the runner's shape whose every directory is the isolated root's.

    The real :func:`readout_layout` resolves ``tel_only``'s scores through F6-3's layout, which
    reads F3's probe records off disk. Those are checkpoints, not tracked files, so the runner's
    naming and its pre-flight are tested against a stand-in of the same shape, and the real
    resolution is tested below wherever the checkpoints are present.
    """
    root = paths.repo_root
    config = _config()
    runner = load_config(root / config.arms_config, H1ArmsConfig)
    arms = ArmsLayout(
        runner=runner,
        out_dir=root / "arms",
        log_dir=root / "arms_steps",
        joint_root=root / "joint",
        tel_only={s: root / "f3" / f"S2_tel_only_seed{s}.pt" for s in SEEDS},
    )
    h1 = ScoringLayout(
        gate=load_config(root / config.h1_gate_config, H1GateConfig),
        arms=arms,
        out_dir=root / "h1",
        patterns={},
        reference={
            s: ProbeCheckpoints(
                seed=s,
                name=f"S2_trained_seed{s}",
                selected_step=900,
                last_step=1000,
                selected=root / "f3" / f"S2_trained_seed{s}_probe.pt",
                final=root / "f3" / f"S2_trained_seed{s}_final_probe.pt",
                prior_offset=0.0,
            )
            for s in SEEDS
        },
        f3_dir=root / "f3",
        sources=["kelmarsh", "penmanshiel"],
        plan=[],
    )
    return ReadoutLayout(
        config=config,
        h1=h1,
        out_dir=paths.checkpoints_dir / "readout_v0_test",
        log_dir=paths.data_reports_dir / "readout_v0_steps",
        random_dir=paths.checkpoints_dir / "probe_control_v0_00d2d3c0",
        rung=runner.rung,
        plan=probe_plan(config, runner.rung),
    )


def test_the_plan_is_adr_0026s_twelve_probes_run_major_seed_minor() -> None:
    plan = probe_plan(_config(), "S2")
    assert len(plan) == 12
    assert [(item.run, item.seed) for item in plan] == [
        (run, seed) for run in ("R-joint-b", "R-joint-d", "R-ctrl-d", "R-rand-d") for seed in SEEDS
    ]
    assert [item.readout for item in plan[:3]] == ["mean_all"] * 3
    assert {item.readout for item in plan[3:]} == {"last_plus_text"}
    assert [item.family for item in plan] == ["joint"] * 6 + ["tel_only"] * 3 + ["random_init"] * 3
    assert plan[0].name == "S2_R-joint-b_seed1"
    assert plan[-1].name == "S2_R-rand-d_seed3"
    # Every artefact of a probe is named from the same stem, so a run's files sort together.
    assert len({item.name for item in plan}) == 12


def test_the_layout_names_one_file_per_artefact(repo_paths: ProjectPaths) -> None:
    layout = _layout(repo_paths)
    item = layout.plan[3]
    assert item.run == "R-joint-d" and item.seed == 1
    # The final state is the one the rule reads; the selected one is saved beside it (§4).
    assert layout.probe(item).name == "S2_R-joint-d_seed1_final_probe.pt"
    assert layout.probe(item, "selected").name == "S2_R-joint-d_seed1_probe.pt"
    assert layout.probe_record(item).name == "S2_R-joint-d_seed1_probe.json"
    assert layout.scores(item).name == "S2_R-joint-d_seed1_final_R0_stride12_scores.npz"
    assert layout.random_record.name == "random_init.json"
    assert layout.lock.name == "RUNNING.lock"
    assert layout.status.name == "readout_status.json"


def test_the_layout_reads_the_backbones_f6_2_and_f3_already_wrote(
    repo_paths: ProjectPaths,
) -> None:
    layout = _layout(repo_paths)
    joint, control, random = layout.plan[3], layout.plan[6], layout.plan[9]
    # Nothing is pretrained: the joint and tel_only sides name F6-2's and F3's own files, through
    # F6-3's layout, so this record cannot point at a different backbone than H1 was read on.
    assert layout.backbone(joint) == layout.h1.arms.backbone(1)
    assert layout.backbone(joint).name == "S2_joint_seed1.pt"
    assert layout.backbone(control) == layout.h1.arms.tel_only[1]
    assert layout.backbone(control).name == "S2_tel_only_seed1.pt"
    assert layout.backbone(random) == layout.out_dir / "S2_random_init_seed1.pt"
    assert layout.random_source(1).name == "S2_random_seed1_probe.pt"


def test_a_random_init_backbone_is_the_one_pretraining_would_start_from() -> None:
    # ADR-0023's construction: the run is seeded, the risk model is built, and the backbone is
    # built before the head -- so the backbone does not depend on which read-out is probed.
    state = random_init_state(TINY, 2)
    seed_everything(2)
    torch.manual_seed(2)
    decoder = TelemetryDecoder(TINY)
    assert sorted(state) == sorted(decoder.state_dict())
    assert all(torch.equal(state[k], decoder.state_dict()[k]) for k in state)
    seed_everything(2)
    torch.manual_seed(2)
    wide = RiskModel(TINY, RiskSpec(pooling="mean"), frozen=True)
    assert all(torch.equal(state[k], v) for k, v in wide.backbone.state_dict().items())
    assert not all(torch.equal(v, random_init_state(TINY, 3)[k]) for k, v in state.items())


def _plant(path: Path, spec: ModelSpec, seed: int) -> dict[str, torch.Tensor]:
    """A saved ADR-0023 random-init probe: the whole risk model, backbone included."""
    seed_everything(seed)
    torch.manual_seed(seed)
    model = RiskModel(spec, RiskSpec(), frozen=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"spec": spec.__dict__, "kind": "probe", "seed": seed, "state": model.state_dict()}, path
    )
    return {k: v.clone() for k, v in model.backbone.state_dict().items()}


def test_the_gate_reuses_adr_0023s_saved_backbone_when_it_is_on_disk(
    repo_paths: ProjectPaths,
) -> None:
    layout = _layout(repo_paths)
    layout.out_dir.mkdir(parents=True, exist_ok=True)
    planted = _plant(layout.random_source(1), TINY, 1)
    lines = materialise_random_init(layout, TINY, [1, 2])
    assert "ADR-0023 saved backbone" in lines[0] and "S2_random_seed1_probe.pt" in lines[0]
    assert lines[1] == "seed 2: constructed fresh at this init seed with the joint spec"
    written = torch.load(layout.random_backbone(1), map_location="cpu", weights_only=False)
    assert written["kind"] == "random_init" and written["seed"] == 1
    # The backbone is read out of ADR-0023's probe, not re-drawn: no head parameter comes with it.
    assert sorted(written["state"]) == sorted(planted)
    assert all(torch.equal(written["state"][k], planted[k]) for k in planted)
    # Seed 2 has no saved probe, so it is constructed -- to the weights either route gives.
    fresh = torch.load(layout.random_backbone(2), map_location="cpu", weights_only=False)["state"]
    expected = random_init_state(TINY, 2)
    assert all(torch.equal(fresh[k], expected[k]) for k in expected)
    record = json.loads(layout.random_record.read_text(encoding="utf-8"))
    assert [row["seed"] for row in record["rows"]] == [1, 2]
    assert record["vocab_size"] == TINY.vocab_size and record["context"] == TINY.context
    assert record["rows"][0]["source"] is not None and record["rows"][1]["source"] is None


def test_a_saved_random_init_backbone_of_another_rung_is_refused(
    repo_paths: ProjectPaths,
) -> None:
    layout = _layout(repo_paths)
    layout.out_dir.mkdir(parents=True, exist_ok=True)
    other = ModelSpec(name="S2", d_model=16, n_layer=2, n_head=4, context=48, vocab_size=65)
    _plant(layout.random_source(1), other, 1)
    with pytest.raises(ValueError, match="the saved random-init backbone is"):
        materialise_random_init(layout, TINY, [1])


def test_the_preflight_reports_every_missing_backbone_and_every_item(
    repo_paths: ProjectPaths,
) -> None:
    layout = _layout(repo_paths)
    problems, lines = preflight(repo_paths, layout)
    assert len(lines) == 24  # twelve probes, then twelve scorings
    assert lines[0] == "[ 1/12] probe R-joint-b seed 1 (mean_all on joint): to run"
    assert lines[12] == "[ 1/12] score S2_R-joint-b_seed1: to run"
    # Nothing exists under the isolated root, so every backbone and F3 score is reported missing.
    missing = [p for p in problems if p.startswith("missing: ")]
    assert any("S2_joint_seed1.pt" in p for p in missing)
    assert any("S2_tel_only_seed1.pt" in p for p in missing)
    assert any("stride12_scores.npz" in p for p in missing)
    assert any("kelmarsh__train.bin" in p for p in missing)
    # A random-init seed with no saved backbone is not a problem: it is constructed.
    assert not any("random" in p for p in problems)


def test_the_preflight_refuses_a_lock_left_by_another_process(repo_paths: ProjectPaths) -> None:
    layout = _layout(repo_paths)
    layout.out_dir.mkdir(parents=True, exist_ok=True)
    layout.lock.write_text("4242\n", encoding="utf-8")
    problems, _ = preflight(repo_paths, layout)
    assert any("RUNNING.lock" in p and "4242" in p for p in problems)


@pytest.mark.skipif(not F3.is_file(), reason="F3's probe records are not on this machine")
def test_the_real_layout_resolves_this_records_directories() -> None:
    layout = readout_layout(ProjectPaths.resolve(), READOUT)
    assert layout.out_dir.name.startswith("readout_v0_")
    assert layout.random_dir.name == "probe_control_v0_00d2d3c0"
    assert layout.h1.arms.out_dir.name == "h1_arms_v0_03629ab1"
    assert layout.backbone(layout.plan[0]).name == "S2_joint_seed1.pt"
    assert layout.backbone(layout.plan[6]).name == "S2_tel_only_seed1.pt"


@pytest.mark.skipif(not F3.is_file(), reason="F3's probe records are not on this machine")
def test_the_real_random_init_backbones_carry_the_joint_vocabulary_and_context() -> None:
    # ADR-0026 §3 re-applies ADR-0023's random-init control. Those backbones were built at the
    # joint vocabulary and the mixture context, which is what this record's probes read.
    layout = readout_layout(ProjectPaths.resolve(), READOUT)
    for seed in SEEDS:
        source = layout.random_source(seed)
        assert source.is_file(), source
        spec = ModelSpec(**torch.load(source, map_location="cpu", weights_only=False)["spec"])
        assert (spec.vocab_size, spec.context) == (33952, 2048)
        assert spec.name == "S2"
