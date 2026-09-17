"""The seed-variance probe (ADR-0020): is a three-arm, one-seed M3 design informative?

Before the three M3 arms are run once each, the arm that is cheapest to reason about,
``tel_only``, is run **twice at half budget**, differing only in seed. Each run pretrains the
S2 decoder on the ``tel`` stream to 25,000,000 tokens, then trains the frozen probe of
M3 step 0 on it (``configs/train/telemetry_v1.yaml``, balanced, 16,000 positives, rate
2e-3) and scores it on the held-out site.

**The pre-registered rule (ADR-0020, committed before either run).** If the two seeds'
held-out-site (Hill of Towie test) AUPRC differ by at least the smallest difference worth
claiming between arms, a three-arm design at one seed cannot tell an arm effect from a
seed, and the plan changes to two arms (``joint`` against ``tel_only``) at three seeds.
Otherwise the three-arm design stands. The rule reads one number; this module computes it
and prints the verdict, and does not start any other run.

**What the probe holds fixed.** Everything but the seed: the shards, the windows drawn for
evaluation (seeded subsamples identical across seeds), the rung, the budget, the schedule and
the probe stage. The seed sets the pretraining initialisation and data order, the head's
initialisation and the balanced sampler's order, which is the variance a one-seed arm
carries.

**How the risk probe reads a joint-vocabulary backbone.** The probe's windows are the M1
risk windows (144 steps, 1,872 tokens, the ``narrow_within_24h`` label and its leakage-checked
index). Every one starts on a step boundary, as every pretraining window does, so position
``mod 13`` names the channel for both. The backbone's 2,048 learned positions cover them.
Telemetry ids are identical under the M1 and the joint vocabulary (ADR-0003, verified
2026-09-16), so no window is re-encoded.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import pyarrow.parquet as pq
import torch
from pydantic import Field, model_validator
from torch import Tensor, nn

from faultline.config import StrictModel, config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.data.telemetry.bins import QuantileBinsConfig
from faultline.data.telemetry.shards import shards_dir, tokenizer_path
from faultline.evaluation.calibration import (
    at_natural_rate,
    expected_calibration_error,
    mean_predicted_rate,
)
from faultline.evaluation.ladder import balanced_training_sampler, build_split
from faultline.evaluation.metrics import RiskScore, score_source
from faultline.logging_utils import get_logger
from faultline.model.checkpoints import read_checkpoint
from faultline.model.risk import RiskModel, RiskSpec, prior_correction
from faultline.model.transformer import ModelSpec, TelemetryDecoder
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.seed import seed_everything
from faultline.training.config import (
    Budget,
    LadderConfig,
    LadderModel,
    Optimiser,
    PositiveAwareRiskStage,
)
from faultline.training.loop import Measurement, risk_logits, train, write_step_log
from faultline.training.mixture import STREAM_DIRS, JointMixtureConfig
from faultline.training.windows import Batch, ShardSet

logger = get_logger(__name__)


class VarianceProbeConfig(StrictModel):
    """Top level of ``configs/train/variance_probe_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        mixture_config: The joint mixture (shards, arms, the full per-arm budget).
        ladder_config: The positive-aware risk stage, the evaluation windows and the optimiser.
        arm: The arm run twice. Only a telemetry-only arm is supported.
        rung: The rung, from the ladder's model configuration.
        seeds: The seeds; the runs differ in nothing else.
        tokens: Pretraining tokens per run: half the mixture's per-arm budget.
        batch_windows: Windows per forward pass while pretraining.
        accumulate: Forward passes per optimiser step while pretraining.
        learning_rate: Peak pretraining learning rate.
        evaluations: Validation measurements during pretraining.
        selection_windows: Validation windows per source for pretraining selection.
        held_out_source: The held-out site whose test AUPRC the rule reads.
        smallest_claimable_auprc_difference: ADR-0020's line, registered before any run.
    """

    version: int = 0
    mixture_config: str
    ladder_config: str
    arm: str
    rung: str
    seeds: list[int] = Field(min_length=2, max_length=2)
    tokens: int = Field(gt=0)
    batch_windows: int = Field(gt=0)
    accumulate: int = Field(gt=0)
    learning_rate: float = Field(gt=0.0)
    evaluations: int = Field(gt=0)
    selection_windows: int = Field(gt=0)
    held_out_source: str
    smallest_claimable_auprc_difference: float = Field(gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _two_distinct_seeds(self) -> VarianceProbeConfig:
        """Refuse a probe whose runs would not differ in seed.

        Raises:
            ValueError: If the two seeds are equal.
        """
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError(f"the probe's runs must differ in seed, got {self.seeds}")
        return self

    def budget(self, context_tokens: int) -> Budget:
        """The pretraining window budget: the token target, rounded up to a whole step."""
        per_step = self.batch_windows * self.accumulate
        steps = -(-self.tokens // (per_step * context_tokens))
        return Budget(
            windows=steps * per_step,
            batch_windows=self.batch_windows,
            accumulate=self.accumulate,
            learning_rate=self.learning_rate,
            evaluations=self.evaluations,
        )


# =====================================================================================
# the tel stream
# =====================================================================================


@dataclass
class TelWindows:
    """Pretraining windows over the ``tel`` stream: context-long slices of M1 shard runs.

    Attributes:
        streams: Per shard key, its memory-mapped M1 token stream.
        keys: Shard keys, in index order.
        index: ``(windows, 2)`` of key position and first token.
        context: Tokens per window.
    """

    streams: dict[str, np.memmap]
    keys: list[str]
    index: np.ndarray
    context: int

    def __len__(self) -> int:
        """Windows available."""
        return int(self.index.shape[0])

    def _gather(self, rows: np.ndarray) -> Batch:
        out = np.empty((rows.shape[0], self.context), dtype=np.int64)
        for position, (key, first) in enumerate(rows):
            out[position] = self.streams[self.keys[int(key)]][
                int(first) : int(first) + self.context
            ]
        return torch.from_numpy(out), torch.zeros(rows.shape[0]), rows[:, 0].copy()

    def forever(self, seed: int, batch: int) -> Iterator[Batch]:
        """Shuffled passes without end, without replacement inside a pass."""
        generator = np.random.default_rng(seed)
        while True:
            order = self.index[generator.permutation(len(self))]
            for start in range(0, order.shape[0] - batch + 1, batch):
                yield self._gather(order[start : start + batch])

    def epoch(self, batch: int) -> Iterator[Batch]:
        """One unshuffled pass, for measurement."""
        for start in range(0, len(self), batch):
            yield self._gather(self.index[start : start + batch])


def tel_windows(
    joint_root: Path,
    telemetry: ShardSet,
    split: str,
    sources: list[str],
    context: int,
    stride_steps: int,
    limit: int | None = None,
    seed: int = 0,
) -> TelWindows:
    """Open ``tel`` windows of one split: every ``stride_steps``-th step start inside a run.

    Args:
        joint_root: The joint shard directory, for the ``tel`` run index.
        telemetry: The M1 shard set the run index points into.
        split: The split.
        sources: Sources to read.
        context: Window length in tokens.
        stride_steps: Steps between window starts.
        limit: At most this many windows per source, sampled without replacement.
        seed: Seed of that subsample.

    Returns:
        The windows.

    Raises:
        ValueError: If no run holds a whole window.
    """
    width = telemetry.tokens_per_step
    streams: dict[str, np.memmap] = {}
    keys: list[str] = []
    rows: list[np.ndarray] = []
    for source in sources:
        key = f"{source}__{split}"
        runs = pq.read_table(joint_root / STREAM_DIRS["tel"] / f"{key}.runs.parquet").to_pandas()
        record = telemetry.files()[key]
        streams[key] = np.memmap(telemetry.root / str(record["tokens"]), dtype=np.uint16, mode="r")
        starts = [
            first + width * np.arange(0, steps, stride_steps, dtype=np.int64)
            for first, steps, tokens in zip(
                runs["first_token"], runs["steps"], runs["tokens"], strict=True
            )
        ]
        ends = [
            first + tokens
            for first, tokens in zip(runs["first_token"], runs["tokens"], strict=True)
        ]
        admissible = np.concatenate(
            [s[s + context <= end] for s, end in zip(starts, ends, strict=True)]
        )
        if limit is not None and admissible.size > limit:
            admissible = np.sort(
                np.random.default_rng(seed).choice(admissible, limit, replace=False)
            )
        keys.append(key)
        rows.append(np.stack([np.full(admissible.size, len(keys) - 1), admissible], axis=1))
    index = np.concatenate(rows).astype(np.int64)
    if not index.size:
        raise ValueError(f"no {context}-token tel window in {split} of {sources}")
    return TelWindows(streams=streams, keys=keys, index=index, context=context)


# =====================================================================================
# one seed
# =====================================================================================


@dataclass
class SeedRecord:
    """One seed's pretraining and probe, and what they scored.

    Attributes:
        seed: The seed.
        lm_tokens: Pretraining tokens seen.
        lm_steps: Pretraining optimiser steps.
        lm_seconds: Pretraining wall clock, measurement included.
        lm_selected: The selected validation next-token loss and its step.
        lm_history: Every pretraining validation measurement, as (step, loss).
        lm_final_train_loss: Mean training loss over the last tenth of pretraining.
        probe_positives_seen: Positive windows the probe drew.
        probe_seconds: Probe wall clock.
        probe_selected: The selected validation AUPRC and its step.
        prior_offset: The logit offset reading scores at the natural rate.
        natural_rate: The training windows' positive share.
        test: Per test source, its score.
        held_out_calibration: Mean corrected probability, base rate and ECE on the held-out site.
        checkpoint: The pretrained backbone's file.
        step_logs: Per stage, the per-step training log's file.
    """

    seed: int
    lm_tokens: int
    lm_steps: int
    lm_seconds: float
    lm_selected: tuple[int, float]
    lm_history: list[tuple[int, float]]
    lm_final_train_loss: float
    probe_positives_seen: int
    probe_seconds: float
    probe_selected: tuple[int, float]
    prior_offset: float
    natural_rate: float
    test: list[RiskScore]
    held_out_calibration: dict[str, float]
    checkpoint: str
    step_logs: dict[str, str] = field(default_factory=dict)

    def held_out(self, source: str) -> RiskScore:
        """This seed's score on one test source."""
        return next(score for score in self.test if score.source == source)


@torch.no_grad()
def tel_lm_loss(model: nn.Module, windows: TelWindows, device: torch.device, batch: int) -> float:
    """Mean next-token loss over one pass of ``tel`` windows."""
    total, counted = 0.0, 0
    autocast = torch.autocast(
        device_type=device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"
    )
    for tokens, _, _ in windows.epoch(batch):
        tokens = tokens.to(device, non_blocking=True)
        with autocast:
            loss = model.loss(tokens)  # type: ignore[operator]
        predicted = tokens.shape[0] * (tokens.shape[1] - 1)
        total += float(loss) * predicted
        counted += predicted
    return total / counted if counted else math.nan


class TelPretraining(Protocol):
    """What pretraining ``tel_only`` reads from a configuration: the probe's or the gate's."""

    @property
    def rung(self) -> str:
        """The rung."""

    @property
    def arm(self) -> str:
        """The arm, telemetry-only."""

    @property
    def batch_windows(self) -> int:
        """Windows per forward pass while pretraining."""

    def budget(self, context_tokens: int) -> Budget:
        """The pretraining window budget."""


@dataclass
class ProbeInputs:
    """Everything a ``tel_only`` pretraining and its frozen probe read, opened once.

    Attributes:
        spec: The rung at the joint vocabulary and the mixture context.
        ladder: The positive-aware risk stage's configuration.
        ladder_model: The ladder's model configuration, for the head.
        telemetry: The M1 shard set.
        joint_root: The joint shard directory.
        mixture: The mixture configuration.
        splits: The evaluation windows: ``lm_selection``, ``selection`` and ``test``.
        device: Where to train.
    """

    spec: ModelSpec
    ladder: LadderConfig
    ladder_model: LadderModel
    telemetry: ShardSet
    joint_root: Path
    mixture: JointMixtureConfig
    splits: dict[str, Any]
    device: torch.device


def open_probe_inputs(
    paths: ProjectPaths,
    mixture_config: str,
    ladder_config: str,
    arm_name: str,
    rung_name: str,
    selection_windows: int,
    held_out_source: str,
    device_name: str | None,
) -> ProbeInputs:
    """Open the shards, the rung and the evaluation windows a ``tel_only`` probe reads.

    Args:
        paths: Resolved project paths.
        mixture_config: The joint mixture configuration, relative to the repository.
        ladder_config: The ladder configuration, relative to the repository.
        arm_name: The arm; only a telemetry-only arm is supported.
        rung_name: The rung.
        selection_windows: Validation ``tel`` windows per source for pretraining selection.
        held_out_source: The held-out site, scored on test beside the training sites.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The opened inputs.

    Raises:
        ValueError: If the arm is not telemetry-only or the ladder's risk stage is not the
            positive-aware one.
    """
    mixture = load_config(paths.repo_root / mixture_config, JointMixtureConfig)
    ladder = load_config(paths.repo_root / ladder_config, LadderConfig)
    ladder_model = load_config(paths.repo_root / ladder.model_config_path, LadderModel)
    arm = next(a for a in mixture.arms if a.name == arm_name)
    if arm.mixture != {"tel": 1.0}:
        raise ValueError(f"{arm_name} is not a telemetry-only arm: {arm.mixture}")
    if not isinstance(ladder.risk, PositiveAwareRiskStage):
        raise ValueError(f"{ladder_config} is not the positive-aware risk stage")
    bins = load_config(paths.repo_root / mixture.telemetry_tokenizer_config, QuantileBinsConfig)
    telemetry = ShardSet.load(shards_dir(paths, tokenizer_path(paths, bins)))
    joint_root = (
        paths.data_root / "shards" / "joint" / f"joint_v{mixture.version}_{config_hash(mixture)}"
    )
    joint_manifest = json.loads((joint_root / "manifest.json").read_text(encoding="utf-8"))
    rung = next(r for r in ladder_model.rungs if r.name == rung_name)
    spec = rung.spec(
        mixture.context_tokens, int(joint_manifest["vocabulary_size"]), ladder_model.dropout
    )
    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    evaluation = ladder.evaluation
    splits: dict[str, Any] = {
        "lm_selection": tel_windows(
            joint_root,
            telemetry,
            "val",
            mixture.training_sources,
            spec.context,
            mixture.window_stride_steps,
            limit=selection_windows,
            seed=evaluation.seed,
        ),
        "selection": build_split(
            telemetry,
            "val",
            evaluation.selection_windows,
            evaluation.stride,
            evaluation.seed,
            evaluation.batch_windows,
            ladder.risk.label,
        ),
        "test": build_split(
            telemetry,
            "test",
            evaluation.test_windows,
            evaluation.stride,
            evaluation.seed,
            evaluation.batch_windows,
            ladder.risk.label,
            sources=[*mixture.training_sources, held_out_source],
        ),
    }
    return ProbeInputs(
        spec=spec,
        ladder=ladder,
        ladder_model=ladder_model,
        telemetry=telemetry,
        joint_root=joint_root,
        mixture=mixture,
        splits=splits,
        device=device,
    )


@dataclass
class PretrainRecord:
    """One seed's ``tel_only`` pretraining.

    Attributes:
        lm_tokens: Pretraining tokens seen.
        lm_steps: Pretraining optimiser steps.
        lm_seconds: Pretraining wall clock, measurement included.
        lm_selected: The selected validation next-token loss and its step.
        lm_history: Every pretraining validation measurement, as (step, loss).
        lm_final_train_loss: Mean training loss over the last tenth of pretraining.
        checkpoint: The pretrained backbone's file.
        step_log: The per-step training log's file.
    """

    lm_tokens: int
    lm_steps: int
    lm_seconds: float
    lm_selected: tuple[int, float]
    lm_history: list[tuple[int, float]]
    lm_final_train_loss: float
    checkpoint: Path
    step_log: Path


@dataclass
class ProbeResult:
    """One frozen probe on one backbone, and what it scored.

    Attributes:
        probe_positives_seen: Positive windows the probe drew.
        probe_seconds: Probe wall clock.
        probe_selected: The selected validation AUPRC and its step.
        prior_offset: The logit offset reading scores at the natural rate.
        natural_rate: The training windows' positive share.
        test: Per test source, its score.
        held_out_calibration: Mean corrected probability, base rate and ECE on the held-out site.
        step_log: The probe's per-step training log's file.
        logits: Every test window's logit, before the offset.
        labels: Every test window's label.
        which: Every test window's window-set index into the test split's sources.
        probe_history: Every validation measurement, as (step, AUPRC); step 0 is a reference.
    """

    probe_positives_seen: int
    probe_seconds: float
    probe_selected: tuple[int, float]
    prior_offset: float
    natural_rate: float
    test: list[RiskScore]
    held_out_calibration: dict[str, float]
    step_log: Path
    logits: np.ndarray
    labels: np.ndarray
    which: np.ndarray
    probe_history: list[tuple[int, float]] = field(default_factory=list)


def pretrain_tel(
    seed: int, config: TelPretraining, inputs: ProbeInputs, out_dir: Path, log_dir: Path
) -> PretrainRecord:
    """Pretrain ``tel_only`` to the configuration's budget and save the backbone.

    Args:
        seed: The seed.
        config: The rung, arm and budget.
        inputs: The opened shards, rung and evaluation windows.
        out_dir: Where the checkpoint is written.
        log_dir: Where the per-step training log is written.

    Returns:
        The pretraining record.
    """
    spec, device = inputs.spec, inputs.device
    seed_everything(seed)
    torch.manual_seed(seed)
    train_windows = tel_windows(
        inputs.joint_root,
        inputs.telemetry,
        "train",
        inputs.mixture.training_sources,
        spec.context,
        inputs.mixture.window_stride_steps,
    )
    budget = config.budget(spec.context)
    decoder = TelemetryDecoder(spec).to(device)

    def lm_loss(model: nn.Module, tokens: Tensor, labels: Tensor) -> Tensor:
        del labels
        return model.loss(tokens)  # type: ignore[operator,no-any-return]

    def lm_measure(model: nn.Module) -> Measurement:
        value = tel_lm_loss(model, inputs.splits["lm_selection"], device, config.batch_windows)
        return Measurement(step=0, windows=0, value=value)

    started = time.perf_counter()
    lm = train(
        module=decoder,
        batches=train_windows.forever(seed, budget.batch_windows),
        budget=budget,
        optimiser=inputs.ladder.optimiser,
        device=device,
        loss_fn=lm_loss,
        measure=lm_measure,
        higher_is_better=False,
        tokens_per_window=spec.context,
        label=f"{config.rung}/{config.arm}/seed{seed}/lm",
    )
    lm_seconds = time.perf_counter() - started
    checkpoint = out_dir / f"{config.rung}_{config.arm}_seed{seed}.pt"
    torch.save({"spec": spec.__dict__, "kind": "lm", "seed": seed, "state": lm.state}, checkpoint)
    lm_log = write_step_log(
        lm.step_log, log_dir / f"{config.rung}_{config.arm}_seed{seed}_lm.steps.csv"
    )
    del decoder
    return PretrainRecord(
        lm_tokens=lm.tokens,
        lm_steps=lm.steps,
        lm_seconds=lm_seconds,
        lm_selected=(lm.best.step, lm.best.value),
        lm_history=[(m.step, m.value) for m in lm.history],
        lm_final_train_loss=lm.final_train_loss,
        checkpoint=checkpoint,
        step_log=lm_log,
    )


def probe_and_score(
    seed: int,
    checkpoint: Path | None,
    inputs: ProbeInputs,
    held_out_source: str,
    step_log: Path,
    label: str,
    save_to: Path | None = None,
    pooling: Literal["last", "mean"] = "last",
    head_layers: Literal[1, 2] = 1,
    unfrozen_blocks: int = 0,
    measure_steps: Sequence[int] | None = None,
    measure_initial: bool = False,
    save_final_to: Path | None = None,
) -> ProbeResult:
    """Train the frozen probe on a backbone and score every test source.

    The probe stage is seeded here, from the seed alone, so a re-run on a saved backbone starts
    from the state the original run's probe started from.

    **Without a checkpoint the backbone is left as constructed** (ADR-0023's random-init
    control). The model is built right after ``torch.manual_seed(seed)``, and the backbone is
    constructed before the head, so its weights are the ones pretraining at ``seed`` starts from,
    and the head starts where a trained backbone's probe at ``seed`` starts.

    Args:
        seed: The seed.
        checkpoint: The pretrained backbone, or ``None`` for the untrained initialisation.
        inputs: The opened shards, rung and evaluation windows.
        held_out_source: The site whose calibration is measured.
        step_log: Where the probe's per-step training log is written.
        label: The run's label in the training log.
        save_to: Where to write the selected probe's whole state, when given.
        pooling: What the head reads (ADR-0023 §b): the final position or the window's mean.
        head_layers: Hidden layers in the head (ADR-0023 §c): one, or two.
        unfrozen_blocks: Final backbone blocks that train (ADR-0023 §d), at the ladder's
            fine-tune rate, while the head keeps the probe's rate.
        measure_steps: Steps to measure validation after, in place of the budget's even
            spacing (ADR-0024 G3).
        measure_initial: Also measure the untrained head, as a reference that is never selected.
        save_final_to: Where to write the last step's whole state as well, when given.

    Returns:
        The probe's result, with every test window's logit.
    """
    assert isinstance(inputs.ladder.risk, PositiveAwareRiskStage)
    stage = inputs.ladder.risk
    optimiser: Optimiser = inputs.ladder.optimiser
    telemetry, device, splits = inputs.telemetry, inputs.device, inputs.splits
    seed_everything(seed)
    torch.manual_seed(seed)
    probe_budget = stage.budget("probe")
    risk = RiskSpec(
        hidden=inputs.ladder_model.head_hidden,
        dropout=inputs.ladder_model.head_dropout,
        label=stage.label,
        pooling=pooling,
        layers=head_layers,
    )
    model = RiskModel(
        inputs.spec,
        risk,
        frozen=True,
        unfrozen_blocks=unfrozen_blocks,
        backbone_lr_scale=stage.budget("finetune").learning_rate / probe_budget.learning_rate,
    ).to(device)
    if checkpoint is not None:
        backbone = read_checkpoint(checkpoint)["state"]
        model.backbone.load_state_dict({k: v.to(device) for k, v in backbone.items()})
    sampler = balanced_training_sampler(telemetry, inputs.ladder, stage, probe_budget.batch_windows)
    train_rate = sampler.positives_per_batch / probe_budget.batch_windows
    offset = prior_correction(train_rate, sampler.natural_rate)
    autocast_on = optimiser.precision == "bf16"

    def probe_loss(module: nn.Module, tokens: Tensor, labels: Tensor) -> Tensor:
        return module.loss(tokens, labels, 1.0)  # type: ignore[operator,no-any-return]

    def probe_measure(module: nn.Module) -> Measurement:
        logits, labels, _ = risk_logits(module, splits["selection"].sampler, device, autocast_on)
        scored = score_source("validation", logits + offset, labels, math.nan)
        return Measurement(
            step=0, windows=0, value=scored.auprc, extra={"base_rate": scored.base_rate}
        )

    started = time.perf_counter()
    probe = train(
        module=model,
        batches=sampler.forever(seed),
        budget=probe_budget,
        optimiser=optimiser,
        device=device,
        loss_fn=probe_loss,
        measure=probe_measure,
        higher_is_better=True,
        tokens_per_window=telemetry.context_tokens,
        label=label,
        measure_steps=measure_steps,
        measure_initial=measure_initial,
        keep_final=save_final_to is not None,
    )
    probe_seconds = time.perf_counter() - started
    probe_log = write_step_log(probe.step_log, step_log)
    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "spec": inputs.spec.__dict__,
                "kind": "probe",
                "pooling": pooling,
                "head_layers": head_layers,
                "unfrozen_blocks": unfrozen_blocks,
                "seed": seed,
                "backbone": None if checkpoint is None else checkpoint.as_posix(),
                "selected": (probe.best.step, probe.best.value),
                "train_rate": train_rate,
                "natural_rate": sampler.natural_rate,
                "state": probe.state,
            },
            save_to,
        )

    if save_final_to is not None and probe.final_state is not None:
        last = probe.history[-1]
        save_final_to.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "spec": inputs.spec.__dict__,
                "kind": "probe",
                "pooling": pooling,
                "head_layers": head_layers,
                "unfrozen_blocks": unfrozen_blocks,
                "seed": seed,
                "backbone": None if checkpoint is None else checkpoint.as_posix(),
                "selected": (probe.best.step, probe.best.value),
                "final": (last.step, last.value),
                "history": [(m.step, m.value) for m in probe.history],
                "train_rate": train_rate,
                "natural_rate": sampler.natural_rate,
                "state": probe.final_state,
            },
            save_final_to,
        )

    # -- test, the held-out site included ----------------------------------------------
    model.load_state_dict({k: v.to(device) for k, v in probe.state.items()})
    model.eval()
    split = splits["test"]
    logits, labels, which = risk_logits(model, split.sampler, device, autocast_on)
    test: list[RiskScore] = []
    calibration: dict[str, float] = {}
    for index, source in enumerate(split.sources):
        chosen = which == index
        test.append(
            score_source(source, logits[chosen] + offset, labels[chosen], split.shares[source])
        )
        if source == held_out_source:
            scores = at_natural_rate(logits[chosen], train_rate, sampler.natural_rate)
            calibration = {
                "mean_predicted_rate": mean_predicted_rate(scores),
                "base_rate": float(labels[chosen].mean()),
                "expected_calibration_error": expected_calibration_error(scores, labels[chosen]),
                "uncorrected_mean_predicted_rate": mean_predicted_rate(
                    at_natural_rate(logits[chosen], train_rate, train_rate)
                ),
            }
    return ProbeResult(
        probe_positives_seen=sampler.positives_seen,
        probe_seconds=probe_seconds,
        probe_selected=(probe.best.step, probe.best.value),
        prior_offset=offset,
        natural_rate=sampler.natural_rate,
        test=test,
        held_out_calibration=calibration,
        step_log=probe_log,
        logits=logits,
        labels=labels,
        which=which,
        probe_history=[(m.step, m.value) for m in probe.history],
    )


def run_seed(
    seed: int,
    config: VarianceProbeConfig,
    inputs: ProbeInputs,
    out_dir: Path,
    log_dir: Path,
    paths: ProjectPaths,
) -> SeedRecord:
    """Pretrain ``tel_only`` at half budget, probe it, score it.

    Args:
        seed: The seed.
        config: The probe configuration.
        inputs: The opened shards, rung and evaluation windows.
        out_dir: Where checkpoints are written.
        log_dir: Where the per-step training logs are written (tracked, beside the report).
        paths: Resolved project paths, so the record names files relative to the repository.

    Returns:
        The seed's record.
    """
    lm = pretrain_tel(seed, config, inputs, out_dir, log_dir)
    probe = probe_and_score(
        seed,
        lm.checkpoint,
        inputs,
        config.held_out_source,
        log_dir / f"{config.rung}_{config.arm}_seed{seed}_probe.steps.csv",
        f"{config.rung}/{config.arm}/seed{seed}/probe",
    )
    return SeedRecord(
        seed=seed,
        lm_tokens=lm.lm_tokens,
        lm_steps=lm.lm_steps,
        lm_seconds=lm.lm_seconds,
        lm_selected=lm.lm_selected,
        lm_history=lm.lm_history,
        lm_final_train_loss=lm.lm_final_train_loss,
        probe_positives_seen=probe.probe_positives_seen,
        probe_seconds=probe.probe_seconds,
        probe_selected=probe.probe_selected,
        prior_offset=probe.prior_offset,
        natural_rate=probe.natural_rate,
        test=probe.test,
        held_out_calibration=probe.held_out_calibration,
        checkpoint=_relative(lm.checkpoint, paths),
        step_logs={"lm": _relative(lm.step_log, paths), "probe": _relative(probe.step_log, paths)},
    )


# =====================================================================================
# the verdict
# =====================================================================================


@dataclass(frozen=True)
class Verdict:
    """The pre-registered rule, applied.

    Attributes:
        gap: Absolute difference in held-out-site test AUPRC between the two seeds.
        line: The smallest claimable difference, registered before the runs.
        uninformative: Whether the gap reaches the line.
        design: The design the rule selects.
    """

    gap: float
    line: float
    uninformative: bool
    design: str


def decide(first: float, second: float, line: float) -> Verdict:
    """Apply ADR-0020's rule to the two seeds' held-out-site AUPRC.

    Args:
        first: One seed's held-out-site test AUPRC.
        second: The other's.
        line: The smallest difference worth claiming between arms.

    Returns:
        The verdict. A gap **at or above** the line makes a one-seed arm comparison
        uninformative.

    Raises:
        ValueError: If either AUPRC is not a number.
    """
    if math.isnan(first) or math.isnan(second):
        raise ValueError("a held-out-site AUPRC is nan; the rule cannot be read")
    gap = abs(first - second)
    uninformative = gap >= line
    design = (
        "two arms (joint vs tel_only) at three seeds: a three-arm n=1 design is uninformative"
        if uninformative
        else "three arms (joint, joint_status_raw, tel_only) at one seed stands"
    )
    return Verdict(gap=gap, line=line, uninformative=uninformative, design=design)


# =====================================================================================
# the run and the report
# =====================================================================================


def run_variance_probe(
    paths: ProjectPaths, config_path: Path, device_name: str | None = None
) -> tuple[Path, Path]:
    """Run both seeds, apply the pre-registered rule, and write the report.

    Args:
        paths: Resolved project paths.
        config_path: The probe configuration.
        device_name: Torch device; chosen automatically when omitted.

    Returns:
        The report and its JSON record.

    Raises:
        ValueError: If the arm is not telemetry-only, the ladder's risk stage is not the
            positive-aware one, or the budget is not half the mixture's.
    """
    config = load_config(config_path, VarianceProbeConfig)
    mixture = load_config(paths.repo_root / config.mixture_config, JointMixtureConfig)
    if config.tokens * 2 != mixture.tokens_per_arm:
        raise ValueError(
            f"the probe runs at half budget: {config.tokens:,} x 2 != {mixture.tokens_per_arm:,}"
        )
    inputs = open_probe_inputs(
        paths,
        config.mixture_config,
        config.ladder_config,
        config.arm,
        config.rung,
        config.selection_windows,
        config.held_out_source,
        device_name,
    )
    spec, device = inputs.spec, inputs.device
    digest = config_hash(config)
    out_dir = paths.checkpoints_dir / f"variance_probe_v{config.version}_{digest}"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = paths.data_reports_dir / f"variance_probe_v{config.version}_steps"
    log_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    records = []
    for seed in config.seeds:
        logger.info("=== variance probe %s seed %d ===", config.arm, seed)
        records.append(run_seed(seed, config, inputs, out_dir, log_dir, paths))
    seconds = time.perf_counter() - started
    first, second = (r.held_out(config.held_out_source).auprc for r in records)
    verdict = decide(first, second, config.smallest_claimable_auprc_difference)
    stem = f"variance_probe_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(
        render_report(config, config_path, spec, records, verdict, seconds, paths, digest, device),
        encoding="utf-8",
        newline="\n",
    )
    record = paths.data_reports_dir / f"{stem}.json"
    payload = {
        "config": config.model_dump(mode="json"),
        "config_hash": digest,
        "spec": spec.__dict__,
        "seconds": seconds,
        "device": str(device),
        "verdict": asdict(verdict),
        "seeds": [asdict(r) for r in records],
    }
    record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, record)
    return report, record


def _relative(path: Path, paths: ProjectPaths) -> str:
    """A path relative to the repository where it lies inside it, so a report names no machine."""
    try:
        return path.resolve().relative_to(paths.repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _f(value: float, digits: int = 4) -> str:
    return "n/a" if value != value else f"{value:.{digits}f}"


def render_report(
    config: VarianceProbeConfig,
    config_path: Path,
    spec: ModelSpec,
    records: list[SeedRecord],
    verdict: Verdict,
    seconds: float,
    paths: ProjectPaths,
    digest: str,
    device: torch.device,
) -> str:
    """Render the variance probe's report.

    Args:
        config: The probe configuration.
        config_path: Where it was read from.
        spec: The rung as built.
        records: Both seeds' records.
        verdict: The rule applied.
        seconds: Wall clock of both seeds.
        paths: Resolved project paths.
        digest: The configuration hash.
        device: The device run on.

    Returns:
        The report as Markdown.
    """
    first_record, second_record = records
    score_rows = []
    for score in first_record.test:
        other = second_record.held_out(score.source)
        score_rows.append(
            (
                score.source,
                _f(score.auprc),
                _f(score.lift, 2),
                _f(other.auprc),
                _f(other.lift, 2),
                f"{score.windows:,}",
                f"{score.positives:,}",
                _f(score.base_rate),
                _f(abs(score.auprc - other.auprc)),
            )
        )
    run_rows = [
        (
            r.seed,
            f"{r.lm_tokens:,}",
            r.lm_steps,
            f"{r.lm_selected[1]:.4f} at step {r.lm_selected[0]}",
            _f(r.lm_final_train_loss),
            f"{r.lm_seconds / 60:.1f}",
            f"{r.probe_positives_seen:,}",
            f"{r.probe_selected[1]:.4f} at step {r.probe_selected[0]}",
            f"{r.probe_seconds / 60:.1f}",
        )
        for r in records
    ]
    calibration_rows = [
        (
            r.seed,
            _f(r.prior_offset, 3),
            _f(r.natural_rate),
            _f(r.held_out_calibration.get("uncorrected_mean_predicted_rate", math.nan)),
            _f(r.held_out_calibration.get("mean_predicted_rate", math.nan)),
            _f(r.held_out_calibration.get("base_rate", math.nan)),
            _f(r.held_out_calibration.get("expected_calibration_error", math.nan)),
        )
        for r in records
    ]
    word = "REACHES" if verdict.uninformative else "is BELOW"
    verdict_body = (
        f"**Between-seed gap in {config.held_out_source} test AUPRC: {verdict.gap:.4f}. "
        f"Pre-registered smallest claimable difference: {verdict.line:.4f} (ADR-0020). "
        f"The gap {word} the line. Design: {verdict.design}.**\n\n"
        "No other run was started.\n"
    )
    return "".join(
        [
            "# Seed-variance probe: tel_only twice at half budget\n\n",
            kv_table(
                {
                    "configuration": f"{_relative(config_path, paths)} (hash {digest})",
                    "arm": config.arm,
                    "rung": f"{spec.name}: d_model {spec.d_model}, {spec.n_layer} layers, "
                    f"{spec.n_head} heads, context {spec.context}, "
                    f"vocabulary {spec.vocab_size:,}",
                    "seeds": f"{first_record.seed} and {second_record.seed}, "
                    "differing in nothing else",
                    "pretraining budget": f"{config.tokens:,} tokens per seed, half the "
                    "per-arm budget, rounded up to a whole optimiser step",
                    "probe": f"{config.ladder_config}: frozen backbone, balanced sampling",
                    "held-out site": config.held_out_source,
                    "device": str(device),
                    "wall clock, both seeds": f"{seconds / 3600:.2f} GPU-hours",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model variance-probe",
                }
            ),
            section("1. The verdict, under the rule registered before the runs", verdict_body),
            section(
                "2. Test AUPRC per source and seed",
                table(
                    [
                        "source",
                        f"seed {first_record.seed} AUPRC",
                        "lift",
                        f"seed {second_record.seed} AUPRC",
                        "lift",
                        "windows",
                        "positives",
                        "base rate",
                        "gap",
                    ],
                    score_rows,
                )
                + "\nBoth seeds are scored on the same seeded windows (stride 1, capped per "
                "source), with the prior correction applied. AUPRC does not change under it.\n",
            ),
            section(
                "3. What each run spent and selected",
                table(
                    [
                        "seed",
                        "pretraining tokens",
                        "steps",
                        "selected val loss",
                        "train loss, last tenth",
                        "pretraining min",
                        "probe positives seen",
                        "selected val AUPRC",
                        "probe min",
                    ],
                    run_rows,
                )
                + "\nThe per-step training loss of both stages of both seeds is in the step "
                "logs the JSON record names.\n",
            ),
            section(
                f"4. Calibration on {config.held_out_source}, prior-corrected (ADR-0019)",
                table(
                    [
                        "seed",
                        "logit offset",
                        "training natural rate",
                        "mean p, uncorrected",
                        "mean p, corrected",
                        "held-out base rate",
                        "ECE, corrected",
                    ],
                    calibration_rows,
                )
                + "\nThe correction reads scores at the training sites' prior. What remains "
                "between the corrected mean and the held-out base rate is site shift. It is "
                "measured here, not corrected.\n",
            ),
        ]
    )
