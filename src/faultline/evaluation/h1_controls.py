"""ADR-0025 §4 controls (i) and (ii), the tail-anchored index, and the mixture's draw (F6-1b).

Three things the H1 runs rest on, measured on the CPU before any GPU is spent:

1. **The window index (ADR-0025 §2).** Every M1 window of the training sites, re-framed over the
   ``tel+status`` stream by ``tail_anchored_2048``. Reported per split at the stride it is used
   at, for positives and negatives separately: steps retained, truncated and head-cut shares,
   and the share holding at least one status token.
2. **Controls (i) and (ii).** The bag-of-tokens comparator refit on those windows: over every id
   (i), and over the status region only (ii). Each is fitted once on R0 windows. Each is scored on
   the stride-12 test windows under R0 and R2, and paired against v0's ``tel`` bag-of-tokens on
   the identical rows. Rows are also given within the has-status and no-status strata of the R0
   windows.
3. **The mixture's draw at the registered budget.** The joint arm's sampler, run to 24,416 windows
   without a model, per seed: the realised ratio, the passes per stream, and whether any stream
   repeated a window.

**Reported controls. No verdict is read here.** Resume is per artefact: an index table, a fitted
control, a score file or a row already on disk is read, not recomputed.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from faultline.config import config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.evaluation.bag_of_tokens import BagOfTokens, BagOfTokensConfig, BagOfTokensV1Config
from faultline.evaluation.bootstrap import (
    bootstrap_auprc,
    paired_bootstrap_deltas,
    window_blocks,
)
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.evaluation.h1_gate import H1ArmsConfig, H1GateConfig
from faultline.evaluation.ladder import SplitEval, build_split
from faultline.evaluation.metrics import score_source
from faultline.evaluation.paired_control import save_split_scores
from faultline.evaluation.probe_control import ScoredWindows
from faultline.evaluation.variance_probe import (
    ProbeInputs,
    frame_split,
    joint_sampler,
    open_probe_inputs,
    probe_training_sampler,
    tel_status_streams,
)
from faultline.logging_utils import get_logger
from faultline.model.checkpoints import read_checkpoint
from faultline.model.risk import prior_correction
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.seed import seed_everything
from faultline.training.config import PositiveAwareRiskStage
from faultline.training.joint_windows import PAD_ID, JointWindowSet, TelStatusStreams
from faultline.training.loop import Measurement, risk_logits, train, write_step_log
from faultline.training.windows import load_windows

logger = get_logger(__name__)

#: ADR-0025's names for the two window variants.
VARIANT = {"all": "R0", "no_stop": "R2"}


# =====================================================================================
# the window index
# =====================================================================================


def split_windows(
    inputs: ProbeInputs, streams: TelStatusStreams, split: str, stride: int
) -> list[JointWindowSet]:
    """Every labelled window of one split of the training sites, re-framed, at one stride."""
    telemetry, label = inputs.telemetry, inputs.ladder.risk.label
    return [
        streams.frame(load_windows(telemetry, key, stride=stride, label=label))
        for key in telemetry.keys(split, inputs.mixture.training_sources)
    ]


def index_statistics(sets: list[JointWindowSet], context_steps: int) -> dict[str, dict[str, Any]]:
    """Per class (positives, negatives, all), what the tail-anchored rule kept.

    Args:
        sets: The re-framed windows of one split.
        context_steps: Steps an M1 window holds.

    Returns:
        Per class: windows, steps retained (mean, p5, min), and the truncated, head-cut and
        has-status shares.
    """
    labels = np.concatenate([s.labels for s in sets]) > 0.5
    steps = np.concatenate([s.steps_retained for s in sets])
    cut = np.concatenate([s.head_cut for s in sets])
    status = np.concatenate([s.status_tokens for s in sets])
    out: dict[str, dict[str, Any]] = {}
    for name, mask in (("positive", labels), ("negative", ~labels), ("all", np.ones_like(labels))):
        n = int(mask.sum())
        chosen = steps[mask]
        out[name] = {
            "windows": n,
            "steps_mean": float(chosen.mean()) if n else math.nan,
            "steps_p5": float(np.percentile(chosen, 5)) if n else math.nan,
            "steps_min": int(chosen.min()) if n else 0,
            "truncated_share": float((chosen < context_steps).mean()) if n else math.nan,
            "truncated": int((chosen < context_steps).sum()),
            "head_cut_share": float(cut[mask].mean()) if n else math.nan,
            "head_cut": int(cut[mask].sum()),
            "has_status_share": float((status[mask] > 0).mean()) if n else math.nan,
            "status_tokens_mean": float(status[mask].mean()) if n else math.nan,
        }
    return out


def per_window(split: SplitEval, attribute: str) -> np.ndarray:
    """One re-framed attribute per scored window, in the order a pass scores them."""
    index = split.sampler.index
    out = np.empty(index.shape[0], dtype=np.int64)
    for position, window_set in enumerate(split.sampler.sets):
        chosen = index[:, 0] == position
        out[chosen] = np.asarray(getattr(window_set, attribute))[index[chosen, 1]]
    return out


# =====================================================================================
# the controls
# =====================================================================================


def fit_control(
    inputs: ProbeInputs,
    mode: str,
    vocab_size: int,
    seed: int,
    step_log: Path,
    label: str,
) -> tuple[BagOfTokens, dict[str, Any]]:
    """Fit one bag-of-tokens control by v0's recipe, on the inputs' windows.

    Args:
        inputs: The opened inputs, tail-anchored R0.
        mode: ``all`` or ``status_only``.
        vocab_size: Ids counted.
        seed: The sampler's and the run's seed.
        step_log: Where the per-step training log is written.
        label: The run's label in the training log.

    Returns:
        The fitted classifier at its selected measurement, and its record.
    """
    stage = inputs.ladder.risk
    assert isinstance(stage, PositiveAwareRiskStage)
    seed_everything(seed)
    torch.manual_seed(seed)
    budget = stage.budget("probe")
    model = BagOfTokens(vocab_size, None, mode, PAD_ID).to(inputs.device)  # type: ignore[arg-type]
    sampler = probe_training_sampler(inputs, stage, budget.batch_windows)
    train_rate = sampler.positives_per_batch / budget.batch_windows
    offset = prior_correction(train_rate, sampler.natural_rate)

    def measure(module: nn.Module) -> Measurement:
        logits, labels, _ = risk_logits(
            module, inputs.splits["selection"].sampler, inputs.device, False
        )
        scored = score_source("validation", logits + offset, labels, math.nan)
        return Measurement(
            step=0, windows=0, value=scored.auprc, extra={"base_rate": scored.base_rate}
        )

    run = train(
        module=model,
        batches=sampler.forever(seed),
        budget=budget,
        optimiser=inputs.ladder.optimiser,
        device=inputs.device,
        loss_fn=lambda m, t, y: m.loss(t, y, 1.0),  # type: ignore[operator]
        measure=measure,
        higher_is_better=True,
        tokens_per_window=inputs.window_tokens,
        label=label,
    )
    write_step_log(run.step_log, step_log)
    model.load_state_dict(run.state)
    model.eval()
    record = {
        "mode": mode,
        "selected": [run.best.step, run.best.value],
        "history": [(m.step, m.value) for m in run.history],
        "final_train_loss": run.final_train_loss,
        "train_rate": train_rate,
        "natural_rate": sampler.natural_rate,
        "prior_offset": offset,
        "positives_seen": sampler.positives_seen,
        "seconds": run.seconds,
        "state": run.state,
    }
    return model, record


def interval_row(
    control: ScoredWindows,
    reference: ScoredWindows,
    strata: dict[str, np.ndarray],
    bootstrap: Any,
) -> dict[str, Any]:
    """A control's interval and its paired Δ against the reference, pooled and per stratum.

    Args:
        control: The control's scores.
        reference: The ``tel`` bag-of-tokens scores on the identical rows.
        strata: Per stratum name, its window mask; ``pooled`` is every window.
        bootstrap: ADR-0021's interval settings.

    Returns:
        Per stratum, the control's interval and Δ control − reference.
    """
    out: dict[str, Any] = {}
    for name, mask in strata.items():
        blocks = window_blocks(control.ends[mask], control.which[mask], bootstrap.block_steps)
        args = (bootstrap.replicates, bootstrap.seed, bootstrap.confidence)
        first = control.logits[mask] + control.prior_offset
        second = reference.logits[mask] + reference.prior_offset
        labels = control.labels[mask]
        out[name] = {
            "control": asdict(bootstrap_auprc(first, labels, blocks, *args)),
            "delta": asdict(paired_bootstrap_deltas(first, [second], labels, blocks, *args)[0]),
        }
    return out


def reference_row(
    reference: ScoredWindows, strata: dict[str, np.ndarray], bootstrap: Any
) -> dict[str, Any]:
    """The ``tel`` bag-of-tokens interval, pooled and per stratum."""
    out: dict[str, Any] = {}
    for name, mask in strata.items():
        blocks = window_blocks(reference.ends[mask], reference.which[mask], bootstrap.block_steps)
        out[name] = asdict(
            bootstrap_auprc(
                reference.logits[mask] + reference.prior_offset,
                reference.labels[mask],
                blocks,
                bootstrap.replicates,
                bootstrap.seed,
                bootstrap.confidence,
            )
        )
    return out


# =====================================================================================
# the run
# =====================================================================================


def run_h1_controls(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """Build the index statistics, fit and score both controls, draw the mixture, and report.

    Args:
        paths: Resolved project paths.
        config_path: ``configs/train/bag_of_tokens_v1.yaml``.

    Returns:
        The report and its JSON record.

    Raises:
        ValueError: If the joint vocabulary, the window counts or the reference windows differ
            from what the configurations register.
    """
    started = time.perf_counter()
    config = load_config(config_path, BagOfTokensV1Config)
    runner = load_config(paths.repo_root / config.runner_config, H1ArmsConfig)
    h1 = load_config(paths.repo_root / config.h1_gate_config, H1GateConfig)
    gate = load_config(paths.repo_root / runner.gate_config, GateCheckConfig)
    reference_config = load_config(paths.repo_root / config.reference_config, BagOfTokensConfig)
    digest = config_hash(config)
    out_dir = paths.checkpoints_dir / f"bag_of_tokens_v{config.version}_{digest}"
    log_dir = paths.data_reports_dir / f"bag_of_tokens_v{config.version}_steps"
    out_dir.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}

    inputs = open_probe_inputs(
        paths,
        runner.mixture_config,
        runner.ladder_config,
        runner.arm,
        runner.rung,
        runner.optimiser.selection_windows,
        gate.held_out_source,
        config.device,
        window_rule=runner.probe.window_rule,
        status_rows=runner.probe.status_rows,
    )
    assert inputs.tel_status is not None
    if inputs.spec.vocab_size != config.vocab_size:
        raise ValueError(f"vocabulary {inputs.spec.vocab_size:,}, config {config.vocab_size:,}")
    evaluation = inputs.ladder.evaluation
    selection = runner.probe.selection
    drawn_as = (evaluation.selection_windows, evaluation.stride, evaluation.seed)
    if (selection.windows_per_source, selection.stride, selection.seed) != drawn_as:
        raise ValueError(f"selection split {drawn_as} is not the runner's {selection}")
    label = inputs.ladder.risk.label

    # -- 1. the index ---------------------------------------------------------------------
    index_file = out_dir / "index_statistics.json"
    if not index_file.exists():
        tick = time.perf_counter()
        index = runner.window_index
        streams_r2 = tel_status_streams(
            paths,
            inputs.joint_root,
            inputs.telemetry,
            "normalized",
            inputs.spec.context,
            "no_stop",
            inputs.mixture.training_sources,
        )
        stats: dict[str, Any] = {}
        for name, split, stride, streams in (
            ("train", "train", index.train_stride, inputs.tel_status),
            ("val", "val", 1, inputs.tel_status),
            ("test", "test", index.test_stride, inputs.tel_status),
            ("test_r2", "test", index.test_stride, streams_r2),
        ):
            sets = split_windows(inputs, streams, split, stride)
            stats[name] = {
                "split": split,
                "stride": stride,
                "status_rows": streams.status_rows,
                "per_key": {
                    s.key: index_statistics([s], inputs.telemetry.context_steps) for s in sets
                },
                **index_statistics(sets, inputs.telemetry.context_steps),
            }
        for name, windows, positives in (
            ("train", index.train_windows, index.train_positives),
            ("test", index.test_windows, index.test_positives),
        ):
            got = (stats[name]["all"]["windows"], stats[name]["positive"]["windows"])
            if got != (windows, positives):
                raise ValueError(f"{name}: {got} windows/positives against {windows, positives}")
        index_file.write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8")
        timings["index"] = time.perf_counter() - tick
    stats = json.loads(index_file.read_text(encoding="utf-8"))

    # -- 2. the test windows and the reference ----------------------------------------------
    m1_test = build_split(
        inputs.telemetry,
        "test",
        None,
        h1.stride,
        evaluation.seed,
        evaluation.batch_windows,
        label,
        sources=inputs.mixture.training_sources,
    )
    tests = {"all": frame_split(m1_test, inputs.tel_status)}
    if "no_stop" in config.status_rows:
        tests["no_stop"] = frame_split(
            m1_test,
            tel_status_streams(
                paths,
                inputs.joint_root,
                inputs.telemetry,
                "normalized",
                inputs.spec.context,
                "no_stop",
                inputs.mixture.training_sources,
            ),
        )
    reference = ScoredWindows.load(
        paths.checkpoints_dir
        / f"bag_of_tokens_v{reference_config.version}_{config_hash(reference_config)}"
        / f"bag_of_tokens_stride{h1.stride}_scores.npz"
    )
    has_status = per_window(tests["all"], "status_tokens") > 0
    strata = {
        "pooled": np.ones_like(has_status),
        "has_status": has_status,
        "no_status": ~has_status,
    }
    reference_file = out_dir / "tel_reference_row.json"
    if not reference_file.exists():
        tick = time.perf_counter()
        reference_file.write_text(
            json.dumps(reference_row(reference, strata, h1.bootstrap), indent=1) + "\n",
            encoding="utf-8",
        )
        timings["reference_intervals"] = time.perf_counter() - tick

    # -- 3. the controls --------------------------------------------------------------------
    fits: dict[str, dict[str, Any]] = {}
    rows: dict[str, dict[str, Any]] = {}
    for control in config.controls:
        fit_file = out_dir / f"{control.name}.pt"
        record_file = out_dir / f"{control.name}_fit.json"
        model = BagOfTokens(config.vocab_size, None, control.mode, PAD_ID)
        if not record_file.exists():
            tick = time.perf_counter()
            logger.info("=== fitting control %s (%s) ===", control.name, control.mode)
            model, record = fit_control(
                inputs,
                control.mode,
                config.vocab_size,
                config.seed,
                log_dir / f"{control.name}.steps.csv",
                f"bag_of_tokens_v1/{control.name}",
            )
            torch.save(
                {
                    "kind": "bag_of_tokens",
                    "mode": control.mode,
                    "seed": config.seed,
                    "vocab_size": config.vocab_size,
                    "pad_id": PAD_ID,
                    "state": record.pop("state"),
                },
                fit_file,
            )
            record["fit_seconds"] = time.perf_counter() - tick
            record_file.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
        fits[control.name] = json.loads(record_file.read_text(encoding="utf-8"))
        model.load_state_dict(read_checkpoint(fit_file)["state"])
        model.eval()
        offset = float(fits[control.name]["prior_offset"])
        for variant in config.status_rows:
            name = f"{control.name}_{VARIANT[variant]}"
            scores_file = out_dir / f"{name}_stride{h1.stride}_scores.npz"
            if not scores_file.exists():
                tick = time.perf_counter()
                logger.info("scoring %s", name)
                logits, labels, _ = risk_logits(model, tests[variant].sampler, inputs.device, False)
                save_split_scores(scores_file, (logits, labels), tests[variant], offset)
                timings[f"score_{name}"] = time.perf_counter() - tick
            scores = ScoredWindows.load(scores_file)
            if not scores.same_windows(reference):
                raise ValueError(f"{name}: not the reference's windows")
            row_file = out_dir / f"{name}_row.json"
            if not row_file.exists():
                tick = time.perf_counter()
                logger.info("bootstrapping %s", name)
                row = interval_row(scores, reference, strata, h1.bootstrap)
                row_file.write_text(json.dumps(row, indent=1) + "\n", encoding="utf-8")
                timings[f"bootstrap_{name}"] = time.perf_counter() - tick
            rows[name] = json.loads(row_file.read_text(encoding="utf-8"))

    # -- 4. the mixture's draw ----------------------------------------------------------------
    mixture_file = out_dir / "mixture_draw.json"
    if not mixture_file.exists():
        tick = time.perf_counter()
        mixture_file.write_text(
            json.dumps(mixture_draw(paths, runner, inputs), indent=1) + "\n", encoding="utf-8"
        )
        timings["mixture_draw"] = time.perf_counter() - tick
    mixture = json.loads(mixture_file.read_text(encoding="utf-8"))

    timing_file = out_dir / "timings.json"
    saved = json.loads(timing_file.read_text(encoding="utf-8")) if timing_file.exists() else {}
    saved.update(timings)
    saved["last_invocation_seconds"] = time.perf_counter() - started
    timing_file.write_text(json.dumps(saved, indent=1) + "\n", encoding="utf-8")

    reference_rows = json.loads(reference_file.read_text(encoding="utf-8"))
    stem = f"h1_controls_v0_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    payload = {
        "config": config.model_dump(mode="json"),
        "config_hash": digest,
        "runner_config_hash": config_hash(runner),
        "index": stats,
        "reference": reference_rows,
        "fits": fits,
        "rows": rows,
        "mixture": mixture,
        "cpu_seconds": saved,
        "git_sha": git_sha(paths.repo_root),
    }
    report.write_text(
        render_report(config, config_path, runner, payload, paths), encoding="utf-8", newline="\n"
    )
    record_path = paths.data_reports_dir / f"{stem}.json"
    record_path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record_path)
    return report, record_path


def mixture_draw(paths: ProjectPaths, runner: H1ArmsConfig, inputs: ProbeInputs) -> dict[str, Any]:
    """The joint arm's sampler run to the registered budget without a model, per seed.

    Args:
        paths: Resolved project paths.
        runner: The F6-2 runner, for the arm, the seeds and the budget.
        inputs: The opened inputs.

    Returns:
        Per seed, per stream: windows, tokens, share, passes, and repeated windows; and the pools'
        sizes beside the builder's window counts.
    """
    budget = runner.budget(inputs.spec.context)
    built = json.loads(
        sorted(paths.data_reports_dir.glob(f"joint_mixture_v{inputs.mixture.version}_*.json"))[
            -1
        ].read_text(encoding="utf-8")
    )
    arm = next(a for a in inputs.mixture.arms if a.name == runner.arm)

    def builder_windows(stream: str) -> int:
        variant = arm.status_convention if stream == "tel+status" else "-"
        return sum(
            int(f["windows"])
            for f in built["files"]
            if f["stream"] == stream
            and f["variant"] == variant
            and f["split"] == "train"
            and f["source"] in inputs.mixture.training_sources
        )

    out: dict[str, Any] = {"budget_windows": budget.windows, "steps": budget.steps, "seeds": {}}
    for seed in runner.seeds:
        sampler = joint_sampler(seed, runner, inputs, runner.arm)
        sampler.keep_rows = True
        batches = sampler.forever()
        for _ in range(budget.windows // budget.batch_windows):
            next(batches)
        context = inputs.spec.context
        total = sum(sampler.drawn.values())
        out["seeds"][str(seed)] = {
            stream: {
                "windows": count,
                "tokens": count * context,
                "share": count / total,
                "windows_per_pass": len(sampler.pools[stream]),
                "passes_by_windows": count / len(sampler.pools[stream]),
                "train_tokens": sampler.pools[stream].train_tokens,
                "passes_by_tokens": count * context / sampler.pools[stream].train_tokens,
                "repeated_windows": count - len(set(sampler.drawn_rows[stream])),
            }
            for stream, count in sampler.drawn.items()
        }
        if seed == runner.seeds[0]:
            out["pools"] = {
                stream: {
                    "windows": len(pool),
                    "builder_windows": builder_windows(stream) if stream != "txt" else None,
                }
                for stream, pool in sampler.pools.items()
            }
    return out


# =====================================================================================
# the report
# =====================================================================================


def _iv(value: dict[str, Any]) -> str:
    return f"{value['auprc']:.4f} [{value['low']:.4f}, {value['high']:.4f}]"


def _dv(value: dict[str, Any]) -> str:
    return f"{value['delta']:+.4f} [{value['low']:+.4f}, {value['high']:+.4f}]"


def render_report(
    config: BagOfTokensV1Config,
    config_path: Path,
    runner: H1ArmsConfig,
    payload: dict[str, Any],
    paths: ProjectPaths,
) -> str:
    """Render the controls' report.

    Args:
        config: The controls' configuration.
        config_path: Where it was read from.
        runner: The F6-2 runner configuration.
        payload: Everything measured.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    relative = config_path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    index_rows = []
    for name in ("train", "val", "test", "test_r2"):
        entry = payload["index"][name]
        for cls in ("positive", "negative"):
            s = entry[cls]
            index_rows.append(
                (
                    f"{entry['split']} ({VARIANT[entry['status_rows']]})",
                    entry["stride"],
                    cls,
                    f"{s['windows']:,}",
                    f"{s['steps_mean']:.1f} / {s['steps_p5']:.0f} / {s['steps_min']}",
                    f"{s['truncated_share']:.1%} ({s['truncated']:,})",
                    f"{s['head_cut_share']:.3%} ({s['head_cut']:,})",
                    f"{s['has_status_share']:.1%}",
                    f"{s['status_tokens_mean']:.1f}",
                )
            )
    reference = payload["reference"]
    control_rows = [
        ("tel bag-of-tokens (v0, reference)", "R0", _iv(reference["pooled"]), "-", "-", "-")
    ]
    strata_rows = [
        (
            "tel bag-of-tokens (v0, reference)",
            "R0",
            _iv(reference["has_status"]),
            "-",
            _iv(reference["no_status"]),
            "-",
        )
    ]
    for name, row in payload["rows"].items():
        control, variant = name.rsplit("_", 1)
        fit = payload["fits"][control]
        control_rows.append(
            (
                f"({'i' if fit['mode'] == 'all' else 'ii'}) {control}",
                variant,
                _iv(row["pooled"]["control"]),
                _dv(row["pooled"]["delta"]),
                f"{row['pooled']['delta']['discarded']}",
                f"step {fit['selected'][0]} ({fit['selected'][1]:.4f})",
            )
        )
        strata_rows.append(
            (
                f"({'i' if fit['mode'] == 'all' else 'ii'}) {control}",
                variant,
                _iv(row["has_status"]["control"]),
                _dv(row["has_status"]["delta"]),
                _iv(row["no_status"]["control"]),
                _dv(row["no_status"]["delta"]),
            )
        )
    has = reference["has_status"]
    none = reference["no_status"]
    mixture = payload["mixture"]
    mixture_rows = []
    for seed, streams in mixture["seeds"].items():
        for stream, s in streams.items():
            mixture_rows.append(
                (
                    seed,
                    stream,
                    f"{s['windows']:,}",
                    f"{s['tokens']:,}",
                    f"{s['share']:.4f}",
                    f"{s['windows_per_pass']:,}",
                    f"{s['passes_by_windows']:.4f}",
                    f"{s['passes_by_tokens']:.4f}",
                    s["repeated_windows"],
                )
            )
    pool_rows = [
        (
            stream,
            f"{p['windows']:,}",
            "-" if p["builder_windows"] is None else f"{p['builder_windows']:,}",
        )
        for stream, p in mixture["pools"].items()
    ]
    cpu = payload["cpu_seconds"]
    cpu_rows = [(k, f"{v / 60:.1f}") for k, v in cpu.items()]
    return "".join(
        [
            "# H1 controls (i) and (ii), the tail-anchored window index and the mixture\n\n",
            "**Reported controls (ADR-0025 §4). They decide nothing, and no H1 verdict is read "
            "here.** Every figure is from the CPU. No GPU, pretraining or probe was run.\n\n",
            kv_table(
                {
                    "configuration": f"{relative} (hash {payload['config_hash']})",
                    "decision record": "docs/DECISIONS.md, ADR-0025 (registered in 3e29202)",
                    "windows": f"{runner.probe.window_rule}, joint_v1 tel_status_normalized "
                    f"(runner {config.runner_config}, hash {payload['runner_config_hash']})",
                    "controls fitted on": "R0 training windows, stride 6, balanced; "
                    "selected on the probes' selection split (3,000 val windows per source)",
                    "test": "stride-12 pooled Kelmarsh + Penmanshiel, 137,025 windows, 5,312 "
                    "positive; R2 is the R0 fit scored on windows with every Stop row removed",
                    "bootstrap": "ADR-0024 paired block bootstrap: 288-step blocks, 10,000 "
                    "replicates, seed 20260916, 95% percentile",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": payload["git_sha"],
                    "generated by": "faultline model h1-controls",
                }
            ),
            section(
                "1. The tail-anchored window index (ADR-0025 §2)",
                table(
                    [
                        "split (variant)",
                        "stride",
                        "class",
                        "windows",
                        "steps retained mean / p5 / min",
                        "truncated (< 144 steps)",
                        "head-cut",
                        "≥ 1 status token",
                        "status tokens, mean",
                    ],
                    index_rows,
                )
                + "\nEvery window is an M1 window-index row (same key, end step, label and year), "
                "re-framed over the `tel+status` stream. Train is read at the probe's stride 6, "
                "val at stride 1 (the probes' selection split draws 3,000 of it per source), and "
                "test at the H1 stride 12. Train and test counts equal the registered ones "
                "(749,387 / 16,524 and 137,025 / 5,312); the run refuses otherwise.\n",
            ),
            section(
                "2. Controls (i) and (ii) on the stride-12 test windows",
                table(
                    [
                        "control",
                        "variant",
                        "AUPRC [95%]",
                        "Δ control − tel bag [95%, paired]",
                        "discarded",
                        "selected (val AUPRC)",
                    ],
                    control_rows,
                )
                + "\nΔ is paired on the identical 137,025 rows: the tel bag-of-tokens is v0's "
                "saved stride-12 scores (ADR-0024 §6). Reported; decides nothing.\n",
            ),
            section(
                "3. Within the has-status and no-status strata of the R0 windows",
                table(
                    [
                        "control",
                        "variant",
                        "has-status AUPRC",
                        "has-status Δ vs tel bag",
                        "no-status AUPRC",
                        "no-status Δ vs tel bag",
                    ],
                    strata_rows,
                )
                + f"\nStrata are fixed on the R0 windows for every row: has-status "
                f"{has['windows']:,} windows ({has['positives']:,} positive, base rate "
                f"{has['base_rate']:.4f}); no-status {none['windows']:,} ({none['positives']:,}, "
                f"{none['base_rate']:.4f}). Blocks are re-derived within each stratum.\n",
            ),
            section(
                "4. The joint arm's mixture sampler at the registered budget (no model)",
                table(
                    [
                        "seed",
                        "stream",
                        "windows",
                        "tokens",
                        "share",
                        "windows / pass",
                        "passes (windows)",
                        "passes (tokens)",
                        "repeated windows",
                    ],
                    mixture_rows,
                )
                + f"\n{mixture['budget_windows']:,} windows = {mixture['steps']} optimiser steps "
                "x 32 windows x 2,048 tokens. The stream of each window is fixed by a "
                "seed-independent schedule, so every seed draws the same count from each stream. "
                "`passes (tokens)` is tokens drawn over the stream's train tokens, the builder "
                "report's measure; `txt` windows are whole 2,048-token tiles, so `passes "
                "(windows)` is the fraction of the narrative read.\n\n"
                + table(["stream", "sampler windows / pass", "builder's count"], pool_rows)
                + "\n`tel` and `tel+status` windows are counted as the builder counts them "
                "(`windows_in_run`, stride 6 steps); `txt` tiles are not a builder count.\n",
            ),
            section(
                "5. CPU time",
                table(["stage", "minutes"], cpu_rows)
                + "\nStages found on disk from an earlier invocation keep their recorded time.\n",
            ),
        ]
    )
