"""Write ``evaluation/results.json``: Course Lesson 11 output, descriptive, not an ADR finding.

Run from the repository root: ``python -m evaluation.evaluate`` (``--device cpu`` to keep the
language-model passes off the GPU). In order:

1. **A4, first.** Re-measure the logged joint seed-1 ``tel`` validation loss (3.4047 nats at
   step 763) by the pretraining's own code: the same 1,000 validation windows of 2,048 tokens
   (``lm_selection``, 500 a source, the evaluation seed), ``<sep>`` included, bfloat16 autocast
   on CUDA, the pretraining's batch. Within 0.01 nats, or the report says it was not.
2. Per-stream perplexity with its reference points (:mod:`evaluation.perplexity`).
3. Seeded generation under five strategies (:mod:`evaluation.generate`).
4. The serving-parity record (``lesson11/demo/parity.json``) and the demo bundle's composition.
5. The served model's research numbers, **copied** from the record with their JSON paths.

Nothing here is referenced from the README or the research summary (G3). Two runs give files
identical except for ``provenance.generated_utc``.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import platform
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from inference.bundle import read_bundle
from inference.engine import Engine, sha256_file
from inference.export import MODEL_FILE, READOUT_CONFIG, served_paths, tokenizer_files

from faultline.config import load_config
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.readout_runs import readout_layout
from faultline.evaluation.variance_probe import ProbeInputs, open_probe_inputs, tel_lm_loss
from faultline.model.transformer import TelemetryDecoder
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.tokenizers.text_bpe import TextBPETokenizer

from . import perplexity as ppl
from .generate import read_prompts, run_generation

LABEL = "Course Lesson 11 output. Descriptive. Not a registered ADR finding."
RESULTS_FILE = Path(__file__).resolve().parent / "results.json"
DEMO_DIR = Path(__file__).resolve().parents[1] / "lesson11" / "demo"
EXPLORATORY_REPORT = "reports/data/exploratory_v0_20260926.json"
SPLITS_CONFIG = "configs/data/splits_v3.yaml"

#: A4's tolerance.
A4_TOLERANCE = 0.01

#: The served seed's name in the ADR-0029 report.
SERVED_KEY = "joint (d) seed 1"


def copied(path: str, report: dict[str, Any], pointer: list[str]) -> dict[str, Any]:
    """A value from a committed report, with where it was read."""
    value: Any = report
    for part in pointer:
        value = value[part]
    return {"source": f"{path}#/{'/'.join(pointer)}", "value": value}


def open_inputs(paths: ProjectPaths, device: torch.device) -> tuple[Any, ProbeInputs]:
    """The joint arm's inputs, opened with the arguments its pretraining was run with."""
    runner = readout_layout(paths, paths.repo_root / READOUT_CONFIG).h1.arms.runner
    gate = load_config(paths.repo_root / runner.gate_config, GateCheckConfig)
    inputs = open_probe_inputs(
        paths,
        runner.mixture_config,
        runner.ladder_config,
        runner.arm,
        runner.rung,
        runner.optimiser.selection_windows,
        gate.held_out_source,
        device.type,
        window_rule=runner.probe.window_rule,
        status_rows=runner.probe.status_rows,
    )
    return runner, inputs


def reproduce_logged_loss(
    paths: ProjectPaths,
    runner: Any,
    inputs: ProbeInputs,
    backbone: TelemetryDecoder,
    device: torch.device,
) -> dict[str, Any]:
    """A4: the logged joint seed-1 ``tel`` validation loss, re-measured by the same code."""
    record_path = readout_layout(paths, paths.repo_root / READOUT_CONFIG).h1.arms.lm_record(1)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    step, logged = int(record["selected"][0]), float(record["selected"][1])
    windows = inputs.splits["lm_selection"]
    measured = tel_lm_loss(backbone, windows, device, runner.batch_windows)
    return {
        "logged": {
            "source": record_path.relative_to(paths.repo_root).as_posix() + "#/selected",
            "step": step,
            "tel_validation_loss_nats": logged,
        },
        "measured_nats": measured,
        "abs_difference": abs(measured - logged),
        "tolerance": A4_TOLERANCE,
        "reproduced": bool(abs(measured - logged) <= A4_TOLERANCE),
        "windows": int(len(windows.index)),
        "tokens_per_window": int(windows.context),
        "includes_sep": True,
        "precision": "bf16 autocast" if device.type == "cuda" else "float32 (no CUDA)",
        "batch_windows": int(runner.batch_windows),
        "code": "faultline.evaluation.variance_probe.open_probe_inputs + tel_lm_loss",
    }


def perplexities(
    runner: Any,
    inputs: ProbeInputs,
    engine: Engine,
    text_file: Path,
    backbone: TelemetryDecoder,
    device: torch.device,
) -> dict[str, Any]:
    """Every stream-split with its reference points, and the unigram-vs-uniform fact."""
    mixture, telemetry, root = inputs.mixture, inputs.telemetry, inputs.joint_root
    arm = next(a for a in mixture.arms if a.name == runner.arm)
    sources = list(mixture.training_sources)
    context, stride = int(mixture.context_tokens), int(mixture.window_stride_steps)
    assert engine.vocab.bin_tokenizer is not None
    n_bins = int(engine.vocab.bin_tokenizer.n_bins)
    text_tokenizer = TextBPETokenizer.load(text_file)
    n_text = int(text_tokenizer.vocab_size)
    vocab = int(backbone.spec.vocab_size)
    byte_lengths = np.array([len(text_tokenizer.decode_bytes([i])) for i in range(n_text)])
    tel_status_dir = root / f"tel_status_{arm.status_convention}"
    train = {
        "tel": [telemetry.root / str(telemetry.files()[f"{s}__train"]["tokens"]) for s in sources],
        "txt": sorted((root / "txt").glob("*__train.bin")),
        "tel+status": [tel_status_dir / f"{s}__train.bin" for s in sources],
    }
    unigrams = {
        stream: ppl.unigram_log_probs(ppl.train_counts(files, vocab), n_bins, n_text)
        for stream, files in train.items()
    }
    models: dict[str, torch.nn.Module] = {
        "model": backbone,
        "random_init": ppl.random_init_backbone(backbone).to(device),
    }
    plan: list[tuple[str, str, Callable[[], ppl.Windows]]] = [
        ("txt", "val", lambda: ppl.txt_windows(root, "val", context)),
        ("txt", "test", lambda: ppl.txt_windows(root, "test", context)),
        (
            "tel",
            "val",
            lambda: ppl.telemetry_windows(root, telemetry, "val", sources, context, stride),
        ),
        (
            "tel",
            "test",
            lambda: ppl.telemetry_windows(root, telemetry, "test", sources, context, stride),
        ),
        (
            "tel+status",
            "val",
            lambda: ppl.tel_status_windows(
                root, arm.status_convention, "val", sources, context, stride
            ),
        ),
        (
            "tel+status",
            "test",
            lambda: ppl.tel_status_windows(
                root, arm.status_convention, "test", sources, context, stride
            ),
        ),
    ]
    streams: dict[str, Any] = {}
    for stream, split, build in plan:
        windows = build()
        result = ppl.score_windows(
            models, windows, unigrams[stream], byte_lengths, n_bins, n_text, device
        )
        result["sources"] = sorted({k.split("__")[0] for k in windows.keys})
        result["note"] = (
            ppl.NEW_MEASUREMENT
            if stream != "tel"
            else "the logged tel validation loss (A4) includes <sep> and is over other windows; "
            "this excludes <sep>, so the two are not the same number"
        )
        streams[f"{stream}/{split}"] = result
    return {
        "splits": {
            "config": SPLITS_CONFIG,
            "val": "2021 for telemetry; the text shards' validation split",
            "test": "2022 on for telemetry; the text shards' test split",
        },
        "window_rule": {
            "context_tokens": context,
            "txt": "every whole 2,048-token tile",
            "tel": "every 6th step start inside a run (tel_windows)",
            "tel+status": "every 6th step's <sep> inside a run (run_step_starts)",
            "cap": f"at most {ppl.WINDOWS_PER_SOURCE} windows a source, "
            f"default_rng({ppl.WINDOW_SEED}) without replacement",
        },
        "targets": "value = 256 shared bin ids + <nan> (257 valid); text = 32,768 ids; "
        "structural targets excluded and counted",
        "scorers": {
            "model": "served backbone, full 33,952-id softmax",
            "model_valid_only": "served backbone, renormalised over the valid ids",
            "uniform": "uniform over the valid ids",
            "unigram": "train-split frequencies of the same stream, add-one within the class",
            "random_init": f"same spec, torch.manual_seed({ppl.RANDOM_INIT_SEED}), full softmax",
            "random_init_valid_only": "the same, renormalised over the valid ids",
        },
        "device": device.type,
        "precision": "float32 (TF32 off)",
        "streams": streams,
        "telemetry_unigram_versus_uniform": {
            "stream": "tel, train split, Kelmarsh + Penmanshiel",
            **ppl.unigram_versus_uniform(unigrams["tel"], n_bins, n_text),
        },
    }


def parity_section() -> dict[str, Any]:
    """The C3 parity measurement with the A9/A10 statements."""
    result = json.loads((DEMO_DIR / "parity.json").read_text(encoding="utf-8"))
    windows = result.pop("windows")
    bundle = [w for w in windows if w["set"] == "bundle"]
    over = [w for w in bundle if w["percentile_shift"] > 0.5]
    over_scores = [w["recorded"] for w in over]
    return {
        "source": "lesson11/demo/parity.json",
        "summary": result,
        "original_criterion": "max percentile shift <= 0.5 pp (A1, fixed before measurement)",
        "original_failure": "0.543 pp on the 20 fixed windows: row 33694, Kelmarsh 3, "
        "2023-10-31 01:10",
        "decomposition": "about 0.18 pp is half of a bf16 tie group of 495 recorded windows; "
        "about 0.36 pp is real rank movement in the densest region of the scores",
        "revision": "max percentile shift <= 1.0 pp, set after the 20-window result (0.543 pp) "
        "and before the bundle measurement: the display resolution, and more than twice the "
        "largest bf16 tie group (614 windows, 0.448 pp). |delta| <= 0.02 and rho >= 0.999 "
        "unchanged. No further revision.",
        "bundle_result": f"bundle maximum {max(w['percentile_shift'] for w in bundle):.3f} pp; "
        f"{len(over)} of {len(bundle)} bundle windows exceed the original 0.5 pp limit, all in "
        "the dense region around -4.2 to -4.5 (recorded scores "
        f"{min(over_scores):.3f} to {max(over_scores):.3f})",
        "bundle_windows_over_original_limit": len(over),
    }


def bundle_section(exploratory: dict[str, Any]) -> dict[str, Any]:
    """The demo bundle's composition, stated (A10)."""
    manifest = json.loads((DEMO_DIR / "manifest.json").read_text(encoding="utf-8"))
    windows = read_bundle(DEMO_DIR / manifest["bundle"])
    registered = np.array([w.label_registered for w in windows])
    variant = np.array([w.label_variant for w in windows])
    if (variant & ~registered).any():
        raise ValueError("a variant positive is not a registered positive")
    counts = manifest["counts"]
    full = exploratory["row_sets"]["full__pooled"]
    return {
        "source": "lesson11/demo/manifest.json",
        "content_sha256": manifest["content_sha256"],
        "rule": manifest["rule"],
        "windows": len(windows),
        "registered_positives": int(registered.sum()),
        "variant_positives": int(variant.sum()),
        "anemometer_only_positives": int((registered & ~variant).sum()),
        "candidates": counts["candidates"],
        "candidate_positives": counts["positives_available"],
        "candidate_positive_rate": counts["positives_available"] / counts["candidates"],
        "test_set_positive_rate": {
            "source": f"{EXPLORATORY_REPORT}#/row_sets/full__pooled/base_rate",
            "value": full["base_rate"],
        },
        "statements": [
            f"Positives are over-represented by design: {int(registered.sum())} of "
            f"{len(windows)} windows, against {counts['positives_available']:,} of "
            f"{counts['candidates']:,} candidates "
            f"({100 * counts['positives_available'] / counts['candidates']:.1f}%) and "
            f"{100 * full['base_rate']:.1f}% in the full test set.",
            f"{int((registered & ~variant).sum())} of the {int(registered.sum())} positives are "
            "positive only because of anemometer-defect events; "
            f"{int(variant.sum())} are positive under the ADR-0009 variant label.",
            "The selection rule was fixed before this composition was seen, and was not changed.",
        ],
    }


def record_section(exploratory: dict[str, Any]) -> dict[str, Any]:
    """The served model's research numbers, copied, not recomputed."""
    path = EXPLORATORY_REPORT
    out: dict[str, Any] = {"note": "copied from the committed record, not recomputed"}
    for label in ("full", "variant"):
        name = "registered" if label == "full" else "variant"
        out[f"seed1_d_auprc_{name}"] = copied(
            path, exploratory, ["part_b", "comparators", label, SERVED_KEY]
        )
        for score in ("P1", "P2"):
            out[f"{score}_auprc_{name}"] = copied(
                path, exploratory, ["part_b", "scores", label, score]
            )
            out[f"{score}_minus_seed1_d_{name}"] = copied(
                path, exploratory, ["part_b", "deltas", label, score, SERVED_KEY]
            )
    return out


def provenance(
    paths: ProjectPaths, engine: Engine, device: torch.device, a4: dict[str, Any]
) -> dict[str, Any]:
    """Hashes, versions and settings."""
    root = paths.repo_root
    served = served_paths(paths)
    return {
        "git_sha": git_sha(root),
        "model": {
            "path": f"checkpoints/{MODEL_FILE}",
            "sha256": engine.meta["model_sha256"],
            "served": engine.meta["served"],
            "sources": {
                role: {"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p)}
                for role, p in served.items()
            },
        },
        "tokenizers": {
            role: {"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p)}
            for role, p in tokenizer_files(paths).items()
        },
        "demo_parity_sha256": sha256_file(DEMO_DIR / "parity.json"),
        "splits_config": SPLITS_CONFIG,
        "seeds": {
            "perplexity_windows": ppl.WINDOW_SEED,
            "random_init": ppl.RANDOM_INIT_SEED,
            "generation": "20260927 + prompt index",
        },
        "a4_windows": a4["windows"],
        "torch": torch.__version__,
        "numpy": np.__version__,
        "python": platform.python_version(),
        "device": device.type,
        "device_name": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu",
        "generated_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
    }


def evaluate(paths: ProjectPaths, device: torch.device) -> dict[str, Any]:
    """Build the whole results document."""
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    engine = Engine.load(paths.checkpoints_dir / MODEL_FILE, tokenizer_files(paths)["bins"].parent)
    backbone: TelemetryDecoder = copy.deepcopy(engine.model.backbone).to(device).float().eval()
    exploratory = json.loads((paths.repo_root / EXPLORATORY_REPORT).read_text(encoding="utf-8"))
    runner, inputs = open_inputs(paths, device)
    a4 = reproduce_logged_loss(paths, runner, inputs, backbone, device)
    text_file = tokenizer_files(paths)["text"]
    lm = perplexities(runner, inputs, engine, text_file, backbone, device)
    del backbone
    generation = run_generation(engine, read_prompts())
    return {
        "label": LABEL,
        "provenance": provenance(paths, engine, device, a4),
        "course_lesson_output": {
            "a4_logged_loss_check": a4,
            "perplexity": lm,
            "generation": generation,
            "note": "BLEU/ROUGE not computed: no reference texts.",
        },
        "parity": parity_section(),
        "demo_bundle": bundle_section(exploratory),
        "copied_from_record": record_section(exploratory),
    }


def main() -> None:
    """Command-line entry: write ``evaluation/results.json``."""
    parser = argparse.ArgumentParser(description="Course Lesson 11: write evaluation/results.json")
    parser.add_argument("--device", default=None, help="cuda or cpu; cuda when available")
    parser.add_argument("--out", type=Path, default=RESULTS_FILE)
    args = parser.parse_args()
    device = torch.device(args.device or ("cuda" if torch.cuda.is_available() else "cpu"))
    results = evaluate(ProjectPaths.resolve(), device)
    text = json.dumps(results, indent=1, allow_nan=False) + "\n"
    args.out.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()
    a4 = results["course_lesson_output"]["a4_logged_loss_check"]
    print(f"wrote {args.out} ({len(text):,} bytes, sha256 {digest[:12]})")
    print(
        f"A4: measured {a4['measured_nats']:.4f} vs logged "
        f"{a4['logged']['tel_validation_loss_nats']:.4f}: reproduced={a4['reproduced']}"
    )
    if not math.isfinite(a4["measured_nats"]):
        raise SystemExit("A4 measurement is not finite")


if __name__ == "__main__":
    main()
