"""Export the served model to ``checkpoints/model.pt`` (Course Lesson 11). Read-only on the record.

**Which model, by rule.** ADR-0026's ``R-joint-d`` run, its **first** seed (seed 1), the
**final-step** probe (ADR-0022's fixed-final rule): the joint seed-1 backbone and its
``last_plus_text`` head, as one file. The rule is applied whatever the seeds score. Seed 1 is
second of three on the registered label and first under the ADR-0009 variant (ADR-0029), and
neither fact chose it.

**What is read, and how.** The probe with ``torch.load(..., map_location="cpu",
weights_only=True)``; the backbone file only to check that the probe carries it bit for bit;
the scores ``.npz`` with ``numpy.load`` (no pickle). Nothing under ``checkpoints/`` is written
except ``model.pt``, and only when nothing exists at that path: the file is opened in exclusive
mode, so an existing file is never overwritten.

**What the file holds.** The float32 state (backbone + head), the model and head shapes, the
window rule's constants, the prior offset, the rank table of the 137,025 recorded seed-1 test
scores (corrected logits, float32 add), the two tokenizers' file names and SHA-256, and the
SHA-256 of every file it was built from. It loads with ``weights_only=True``.

Run from the repository root: ``python -m inference.export``.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from faultline.config import load_config
from faultline.data.telemetry.bins import QuantileBinsConfig
from faultline.data.telemetry.shards import shards_dir
from faultline.data.telemetry.shards import tokenizer_path as telemetry_tokenizer_path
from faultline.data.text.shards import load_text_shards_config
from faultline.data.text.shards import tokenizer_path as text_tokenizer_path
from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.readout_runs import readout_layout
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.training.config import LadderConfig, LadderModel
from faultline.training.mixture import JointMixtureConfig
from faultline.training.windows import ShardSet
from inference.engine import FORMAT, RankTable, sha256_file

#: ADR-0026's registration, which names the runs and resolves every path.
READOUT_CONFIG = "configs/eval/readout_v0.yaml"

#: The served run, and the rule that picks its seed: the first one.
SERVED_RUN = "R-joint-d"

#: Where the export goes.
MODEL_FILE = "model.pt"


def served_paths(paths: ProjectPaths) -> dict[str, Path]:
    """The backbone, the final-step probe and the scores of the served model, by rule.

    Args:
        paths: Resolved project paths.

    Returns:
        ``backbone``, ``probe``, ``scores`` and ``probe_record``.
    """
    layout = readout_layout(paths, paths.repo_root / READOUT_CONFIG)
    run = next(r for r in layout.config.runs if r.name == SERVED_RUN)
    seed = run.seeds[0]
    item = next(i for i in layout.plan if i.run == SERVED_RUN and i.seed == seed)
    return {
        "backbone": layout.backbone(item),
        "probe": layout.probe(item),
        "scores": layout.scores(item),
        "probe_record": layout.probe_record(item),
    }


def tokenizer_files(paths: ProjectPaths) -> dict[str, Path]:
    """The two tokenizer files the joint mixture reads.

    Args:
        paths: Resolved project paths.

    Returns:
        ``bins`` and ``text``.
    """
    layout = readout_layout(paths, paths.repo_root / READOUT_CONFIG)
    mixture = load_config(
        paths.repo_root / layout.h1.arms.runner.mixture_config, JointMixtureConfig
    )
    bins = load_config(paths.repo_root / mixture.telemetry_tokenizer_config, QuantileBinsConfig)
    text = load_text_shards_config(paths.repo_root / mixture.text_shards_config)
    return {
        "bins": telemetry_tokenizer_path(paths, bins),
        "text": text_tokenizer_path(paths, paths.repo_root / text.tokenizer_config),
    }


def recorded_scores(scores_path: Path) -> tuple[np.ndarray, float]:
    """The recorded corrected scores: logits plus the offset, added in float32.

    Args:
        scores_path: The scores ``.npz``.

    Returns:
        The corrected scores and the offset.
    """
    saved = ScoredWindows.load(scores_path)
    corrected = saved.logits.astype(np.float32) + np.float32(saved.prior_offset)
    return corrected, float(saved.prior_offset)


def build_payload(paths: ProjectPaths) -> dict[str, Any]:
    """Assemble the export from the record, reading everything read-only.

    Args:
        paths: Resolved project paths.

    Returns:
        The payload ``torch.save`` writes.

    Raises:
        ValueError: If the probe is not the (d) read-out, or does not carry the backbone.
    """
    root = paths.repo_root
    served = served_paths(paths)
    probe: dict[str, Any] = torch.load(served["probe"], map_location="cpu", weights_only=True)
    if probe.get("pooling") != "last_plus_text" or probe.get("window_rule") != "tail_anchored_2048":
        raise ValueError(f"{served['probe']} is not the (d) tail-anchored probe")
    backbone: dict[str, Any] = torch.load(served["backbone"], map_location="cpu", weights_only=True)
    for key, tensor in backbone["state"].items():
        if not torch.equal(tensor, probe["state"]["backbone." + key]):
            raise ValueError(f"the probe's backbone differs from {served['backbone']} at {key}")

    layout = readout_layout(paths, root / READOUT_CONFIG)
    runner = layout.h1.arms.runner
    ladder = load_config(root / layout.config.ladder_config, LadderConfig)
    ladder_model = load_config(root / ladder.model_config_path, LadderModel)
    mixture = load_config(root / runner.mixture_config, JointMixtureConfig)
    arm = next(a for a in mixture.arms if a.name == runner.arm)
    corrected, offset = recorded_scores(served["scores"])
    table = RankTable.from_scores(corrected)
    tokenizers = tokenizer_files(paths)
    telemetry = ShardSet.load(shards_dir(paths, tokenizers["bins"]))

    def rel(path: Path) -> str:
        return path.resolve().relative_to(root.resolve()).as_posix()

    state = {
        key: (value.float() if value.is_floating_point() else value).contiguous().clone()
        for key, value in probe["state"].items()
    }
    return {
        "format": FORMAT,
        "spec": dict(probe["spec"]),
        "head": {
            "hidden": float(ladder_model.head_hidden),
            "dropout": float(ladder_model.head_dropout),
            "label": str(ladder.risk.label),
            "pooling": str(probe["pooling"]),
            "layers": int(probe["head_layers"]),
            "pad_id": int(probe["pad_id"]),
            "text_positions": {
                "special_ids": [int(i) for i in probe["text_positions"]["special_ids"]],
                "min_id": int(probe["text_positions"]["min_id"]),
            },
        },
        "window": {
            "rule": str(probe["window_rule"]),
            "context_tokens": int(mixture.context_tokens),
            "context_steps": int(telemetry.context_steps),
            "tokens_per_step": int(telemetry.tokens_per_step),
            "status_convention": str(arm.status_convention),
        },
        "state": state,
        "prior_offset": offset,
        "score_table": {
            "values": torch.from_numpy(table.values.copy()),
            "cumulative": torch.from_numpy(table.cumulative.copy()),
            "definition": "mid-rank percentile over the 137,025 recorded seed-1 test scores "
            "(pooled Kelmarsh + Penmanshiel, stride 12), each the recorded logit plus the prior "
            "offset added in float32",
        },
        "tokenizers": {
            role: {"file": path.name, "path": rel(path), "sha256": sha256_file(path)}
            for role, path in tokenizers.items()
        },
        "sources": {
            role: {"path": rel(path), "sha256": sha256_file(path)} for role, path in served.items()
        },
        "served": {
            "run": SERVED_RUN,
            "seed": int(probe["seed"]),
            "checkpoint": "final_step",
            "readout": "last_plus_text",
            "rule": "the first seed of R-joint-d, final-step probe; applied whatever it scores",
            "backbone_origin": "joint",
        },
        "git_sha": git_sha(root),
    }


def export(paths: ProjectPaths, out: Path) -> dict[str, Any]:
    """Write the export, refusing if anything exists at the path.

    Args:
        paths: Resolved project paths.
        out: The target, ``checkpoints/model.pt``.

    Returns:
        A summary: the path, its SHA-256, the source hashes.

    Raises:
        FileExistsError: If anything exists at ``out``.
    """
    if out.exists():
        raise FileExistsError(f"{out} exists; the export never overwrites")
    payload = build_payload(paths)
    buffer = io.BytesIO()
    torch.save(payload, buffer)
    # "xb": exclusive creation, so a file that appeared since the check is not overwritten either.
    with out.open("xb") as handle:
        handle.write(buffer.getvalue())
    # The written file must load under the loader the engine uses.
    torch.load(out, map_location="cpu", weights_only=True)
    return {
        "model": out.as_posix(),
        "sha256": sha256_file(out),
        "bytes": out.stat().st_size,
        "sources": payload["sources"],
        "tokenizers": payload["tokenizers"],
        "prior_offset": payload["prior_offset"],
        "score_table_entries": int(payload["score_table"]["values"].numel()),
    }


def main() -> None:
    """Command-line entry: export once, print the summary."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="default: checkpoints/model.pt")
    args = parser.parse_args()
    paths = ProjectPaths.resolve()
    out = args.out or paths.checkpoints_dir / MODEL_FILE
    print(json.dumps(export(paths, out), indent=2))


if __name__ == "__main__":
    main()
