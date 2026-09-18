"""The model ladder: four sizes, four runs each, one report (M1e).

``faultline model ladder`` reads one configuration and runs the whole experiment, because
the experiment *is* the ladder. At each rung, in this order:

1. **lm** -- next-token prediction on the train split. The course deliverable and the
   representation the next two read. Selected on validation next-token loss.
2. **probe** -- the language model's backbone frozen, a shallow risk head trained on the
   24-hour narrow label. Selected on validation AUPRC.
3. **finetune** -- the same, unfrozen. Selected on validation AUPRC.
4. **random** -- the same head and the same budget on a *randomly initialised* backbone of
   the same size. This is the run that makes the ladder an experiment rather than a size
   sweep: (2) and (3) against (4) is what answers whether next-token pretraining on
   quantised telemetry buys anything for event risk, and the answer is publishable either
   way, including no.

The curve is the result. One rung picked out and presented as "the model" would be a
different and weaker claim, so this module reports every rung and never names a winner.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import torch
from torch import Tensor, nn

from faultline.config import config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.data.telemetry.bins import QuantileBinsConfig
from faultline.data.telemetry.shards import shards_dir, tokenizer_path
from faultline.evaluation.metrics import RiskScore, score_source
from faultline.logging_utils import get_logger
from faultline.model.risk import RiskModel, RiskSpec, prior_correction
from faultline.model.transformer import TelemetryDecoder
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.seed import seed_everything
from faultline.training.config import (
    SELECTION,
    LadderConfig,
    LadderModel,
    PositiveAwareRiskStage,
    Rung,
    RunKind,
)
from faultline.training.loop import (
    Measurement,
    language_model_loss,
    risk_logits,
    train,
    write_step_log,
)
from faultline.training.windows import (
    BalancedWindowSampler,
    ShardSet,
    WindowSampler,
    WindowSet,
    load_windows,
)

logger = get_logger(__name__)

#: The fused attention kernels need a head dimension divisible by this. A rung that misses
#: it falls back, silently, to the kernel that materialises the whole score matrix: on this
#: project's hardware that was measured at 8 times the memory and an eighth of the
#: throughput, for exactly the same parameter count.
HEAD_DIM_MULTIPLE = 8

#: CARE is a dataset-level probe and its per-step base rates are not the project's endpoint
#: (ADR-0010). Its per-step figures are printed with this caveat rather than omitted, so
#: that the source appears and is not quietly pooled into anyone else's number.
CARE_CAVEAT = "dataset-level probe (ADR-0010): per-step figures are diagnostic, not the endpoint"


def nan_share(
    window_set: WindowSet, tokens_per_step: int, width: int, nan_id: int, sep_id: int
) -> float:
    """Share of ``<nan>`` among the value tokens of the windows actually scored.

    Measured on the scored windows rather than on the whole split, because that is the
    data the metric beside it was computed from.

    Args:
        window_set: The windows.
        tokens_per_step: Tokens a grid step contributes.
        width: Tokens in a window.
        nan_id: The ``<nan>`` identifier.
        sep_id: The ``<sep>`` identifier, excluded because it is not a value.

    Returns:
        The share, or ``nan`` without windows.
    """
    missing = counted = 0
    for start in window_set.starts:
        begin = int(start) * tokens_per_step
        piece = np.asarray(window_set.tokens[begin : begin + width])
        values = piece[piece != sep_id]
        missing += int((values == nan_id).sum())
        counted += int(values.size)
    return missing / counted if counted else math.nan


@dataclass
class SplitEval:
    """One split's evaluation windows, one window set per source.

    Attributes:
        sampler: The windows, iterated in a fixed unshuffled order.
        sources: Per window set, the source it belongs to.
        shares: Per source, the ``<nan>`` share of the windows scored.
        years: Per window, the calendar year, in the sampler's order.
        sets: Per window, the index of the set it came from, in the sampler's order.
    """

    sampler: WindowSampler
    sources: list[str]
    shares: dict[str, float]
    years: np.ndarray
    sets: np.ndarray


@dataclass
class RunRecord:
    """One trained model and what it scored.

    Attributes:
        kind: Which of the four runs this is.
        rung: The rung's name.
        seed: The seed.
        params: Parameter counts, split the way the ladder reports them.
        selection: What the run was selected on, in words.
        best: The selected validation measurement.
        history: Every validation measurement taken.
        seconds: Wall-clock seconds the run took.
        windows: Training windows consumed.
        tokens: Training tokens consumed.
        train_loss: Mean training loss over the last tenth of the run.
        validation: Per source, the final validation score; empty for a language model.
        test: Per source, the final test score; empty where the run was not scored there.
        test_years: Per source and calendar year, the same, for a held-out site.
        lm_loss: Per split and source, next-token loss; empty for a risk run.
        checkpoint: Where the selected parameters were written.
        positives_seen: Positive training windows drawn, counting repeats, where the
            sampler counts them exactly (balanced sampling); ``None`` otherwise.
        prior_offset: The logit offset added to every score so it reads at the natural
            base rate; 0.0 for a run trained at that rate.
    """

    kind: RunKind
    rung: str
    seed: int
    params: dict[str, int]
    selection: str
    best: Measurement
    history: list[Measurement]
    seconds: float
    windows: int
    tokens: int
    train_loss: float
    validation: list[RiskScore] = field(default_factory=list)
    test: list[RiskScore] = field(default_factory=list)
    test_years: list[tuple[str, int, RiskScore]] = field(default_factory=list)
    lm_loss: dict[str, float] = field(default_factory=dict)
    checkpoint: str = ""
    positives_seen: int | None = None
    prior_offset: float = 0.0

    @property
    def key(self) -> str:
        """A short identifier, ``<rung>/<kind>/seed<seed>``."""
        return f"{self.rung}/{self.kind}/seed{self.seed}"


# =====================================================================================
# building the splits
# =====================================================================================


def build_split(
    shards: ShardSet,
    split: str,
    per_source: int | None,
    stride: int,
    seed: int,
    batch_windows: int,
    label: str | None,
    sources: Sequence[str] | None = None,
) -> SplitEval:
    """Open one split's evaluation windows, capped per source.

    A risk model is scored on every step it would have to make a call on, which is stride
    1; at stride 1 this project's test split holds about nine million windows and roughly
    seventeen billion tokens of forward pass per checkpoint, which is not a budget it has.
    So the windows are capped, the cap is seeded and identical for every checkpoint, and
    the cap is printed in every table it produces.

    Args:
        shards: The shard set.
        split: The split to open.
        per_source: The most windows to keep per source; every window at the stride when ``None``.
        stride: The stride windows are taken at before the cap.
        seed: Seed of the subsample.
        batch_windows: Windows per forward pass.
        label: The label column, or ``None`` for language modelling.
        sources: Sources to keep; every source of the split when omitted.

    Returns:
        The split's evaluation windows.
    """
    sets: list[WindowSet] = []
    for key in shards.keys(split, sources):
        window_set = load_windows(
            shards, key, stride=stride, label=label, limit=per_source, seed=seed
        )
        if len(window_set):
            sets.append(window_set)
        else:
            logger.warning("%s holds no admissible labelled window; it is not scored", key)
    sampler = WindowSampler(
        sets,
        batch_size=batch_windows,
        tokens_per_step=shards.tokens_per_step,
        context_steps=shards.context_steps,
        labelled=label is not None,
    )
    specials = dict(shards.manifest["specials"])
    shares = {
        s.source: nan_share(
            s,
            shards.tokens_per_step,
            shards.context_tokens,
            int(specials["<nan>"]),
            int(specials["<sep>"]),
        )
        for s in sets
    }
    # An unshuffled pass yields windows in exactly this order, so each scored window can
    # be attributed back to its source and its calendar year.
    order = sampler.index
    years = np.array([sets[int(i)].years[int(row)] for i, row in order], dtype=np.int64)
    return SplitEval(
        sampler=sampler,
        sources=[s.source for s in sets],
        shares=shares,
        years=years,
        sets=order[:, 0].copy(),
    )


def score_split(
    module: nn.Module,
    split: SplitEval,
    device: torch.device,
    autocast_on: bool,
    logit_offset: float = 0.0,
) -> tuple[list[RiskScore], list[tuple[str, int, RiskScore]]]:
    """Score every window of a split, per source and per source-year.

    Args:
        module: The risk model, in evaluation mode.
        split: The windows.
        device: Where the model lives.
        autocast_on: Whether to run the pass in bfloat16.
        logit_offset: Added to every logit, the prior correction of a balanced run.

    Returns:
        One score per source, and one per source and calendar year.
    """
    logits, labels, which = risk_logits(module, split.sampler, device, autocast_on)
    logits = logits + logit_offset
    per_source: list[RiskScore] = []
    per_year: list[tuple[str, int, RiskScore]] = []
    for index, source in enumerate(split.sources):
        chosen = which == index
        if not chosen.any():
            continue
        per_source.append(
            score_source(source, logits[chosen], labels[chosen], split.shares[source])
        )
        years = split.years[chosen]
        if np.unique(years).size > 1:
            for year in np.unique(years):
                here = years == year
                per_year.append(
                    (
                        source,
                        int(year),
                        score_source(
                            source, logits[chosen][here], labels[chosen][here], split.shares[source]
                        ),
                    )
                )
    return per_source, per_year


def language_model_losses(
    module: nn.Module, split: SplitEval, device: torch.device, autocast_on: bool
) -> dict[str, float]:
    """Next-token loss per source on one split.

    Args:
        module: The decoder, in evaluation mode.
        split: The windows.
        device: Where the model lives.
        autocast_on: Whether to run the pass in bfloat16.

    Returns:
        Per source, the mean loss per predicted token.
    """
    out: dict[str, float] = {}
    for index, source in enumerate(split.sources):
        one = WindowSampler(
            [split.sampler.sets[index]],
            batch_size=split.sampler.batch_size,
            tokens_per_step=split.sampler.tokens_per_step,
            context_steps=split.sampler.context_steps,
            labelled=False,
        )
        out[source] = language_model_loss(module, one, device, autocast_on)
    return out


# =====================================================================================
# the runs
# =====================================================================================


def training_sampler(
    shards: ShardSet, config: LadderConfig, label: str | None, batch_windows: int
) -> WindowSampler:
    """Open the training windows at the configured stride.

    Args:
        shards: The shard set.
        config: The ladder configuration.
        label: The label column, or ``None`` for language modelling.
        batch_windows: Windows per forward pass.

    Returns:
        A sampler over every training source's admissible windows.
    """
    sets = [
        load_windows(shards, key, stride=config.train_stride, label=label)
        for key in shards.keys("train")
    ]
    return WindowSampler(
        [s for s in sets if len(s)],
        batch_size=batch_windows,
        tokens_per_step=shards.tokens_per_step,
        context_steps=shards.context_steps,
        labelled=label is not None,
    )


def balanced_training_sampler(
    shards: ShardSet, config: LadderConfig, stage: PositiveAwareRiskStage, batch_windows: int
) -> BalancedWindowSampler:
    """Open the labelled training windows for balanced sampling.

    Args:
        shards: The shard set.
        config: The ladder configuration, for the training stride.
        stage: The positive-aware stage, for the label and the positive fraction.
        batch_windows: Windows per forward pass.

    Returns:
        A sampler putting a fixed number of positives in every batch.
    """
    sets = [
        load_windows(shards, key, stride=config.train_stride, label=stage.label)
        for key in shards.keys("train")
    ]
    return BalancedWindowSampler(
        [s for s in sets if len(s)],
        batch_size=batch_windows,
        positives_per_batch=round(stage.positive_fraction * batch_windows),
        tokens_per_step=shards.tokens_per_step,
        context_steps=shards.context_steps,
    )


def run_one(
    kind: RunKind,
    rung: Rung,
    seed: int,
    config: LadderConfig,
    model_config: LadderModel,
    shards: ShardSet,
    device: torch.device,
    selection: SplitEval,
    backbone_state: dict[str, Tensor] | None,
    checkpoints: Path,
) -> tuple[RunRecord, dict[str, Tensor]]:
    """Make one run of the ladder.

    Args:
        kind: Which of the four runs.
        rung: The rung.
        seed: The seed, applied to every generator before the model is built.
        config: The ladder's training configuration.
        model_config: The ladder's model configuration.
        shards: The shard set.
        device: Where the model lives.
        selection: The validation windows the periodic measurement reads.
        backbone_state: The language model's parameters, for ``probe`` and ``finetune``;
            ``None`` for ``lm`` and for the randomly initialised control.
        checkpoints: Directory the selected parameters are written to.

    Returns:
        The run's record and its selected state dictionary.

    Raises:
        ValueError: If a run that reads a backbone is given none.
    """
    seed_everything(seed)
    torch.manual_seed(seed)
    spec = rung.spec(shards.context_tokens, shards.vocab_size, model_config.dropout)
    budget = config.budget_for(kind)
    autocast_on = config.optimiser.precision == "bf16"
    label = f"{rung.name}/{kind}/seed{seed}"

    module: nn.Module
    offset = 0.0
    if kind == "lm":
        module = TelemetryDecoder(spec).to(device)
        counts = module.parameter_counts()
        sampler = training_sampler(shards, config, None, budget.batch_windows)

        def loss_fn(model: nn.Module, tokens: Tensor, labels: Tensor) -> Tensor:
            return cast(Tensor, model.loss(tokens))  # type: ignore[operator]

        def measure(model: nn.Module) -> Measurement:
            value = language_model_loss(model, selection.sampler, device, autocast_on)
            return Measurement(step=0, windows=0, value=value)

        higher_is_better = False
    else:
        if kind in {"probe", "finetune"} and backbone_state is None:
            raise ValueError(f"{kind} reads the language model's backbone and was given none")
        risk = RiskSpec(
            hidden=model_config.head_hidden,
            dropout=model_config.head_dropout,
            label=config.risk.label,
        )
        model = RiskModel(spec, risk, frozen=kind == "probe").to(device)
        if backbone_state is not None and kind != "random":
            model.backbone.load_state_dict({k: v.to(device) for k, v in backbone_state.items()})
        module = model
        counts = model.backbone.parameter_counts()
        if isinstance(config.risk, PositiveAwareRiskStage):
            # the positives are in the batch, so the loss is not reweighted as well
            sampler = balanced_training_sampler(shards, config, config.risk, budget.batch_windows)
            weight = 1.0
            offset = prior_correction(
                sampler.positives_per_batch / budget.batch_windows, sampler.natural_rate
            )
        else:
            sampler = training_sampler(shards, config, config.risk.label, budget.batch_windows)
            weight = config.risk.positive_weight

        def loss_fn(model: nn.Module, tokens: Tensor, labels: Tensor) -> Tensor:
            return cast(Tensor, model.loss(tokens, labels, weight))  # type: ignore[operator]

        def measure(model: nn.Module) -> Measurement:
            logits, labels, _ = risk_logits(model, selection.sampler, device, autocast_on)
            scored = score_source("validation", logits + offset, labels, math.nan)
            return Measurement(
                step=0,
                windows=0,
                value=scored.auprc,
                extra={"base_rate": scored.base_rate, "loss": scored.loss},
            )

        higher_is_better = True

    result = train(
        module=module,
        batches=sampler.forever(seed),
        budget=budget,
        optimiser=config.optimiser,
        device=device,
        loss_fn=loss_fn,
        measure=measure,
        higher_is_better=higher_is_better,
        tokens_per_window=shards.context_tokens,
        label=label,
        initial_loss_vocab=spec.vocab_size if kind == "lm" else None,
    )
    destination = checkpoints / f"{rung.name}_{kind}_seed{seed}.pt"
    torch.save(
        {"spec": spec.__dict__, "kind": kind, "seed": seed, "state": result.state}, destination
    )
    # every optimiser step's training loss, beside the checkpoint: it cannot be recovered later
    write_step_log(result.step_log, destination.with_suffix(".steps.csv"))
    record = RunRecord(
        kind=kind,
        rung=rung.name,
        seed=seed,
        params=counts,
        selection=SELECTION[kind],
        best=result.best,
        history=result.history,
        seconds=result.seconds,
        windows=result.windows,
        tokens=result.tokens,
        train_loss=result.final_train_loss,
        checkpoint=destination.name,
        positives_seen=(
            sampler.positives_seen if isinstance(sampler, BalancedWindowSampler) else None
        ),
        prior_offset=offset,
    )
    return record, result.state


def score_record(
    record: RunRecord,
    state: dict[str, Tensor],
    rung: Rung,
    config: LadderConfig,
    model_config: LadderModel,
    shards: ShardSet,
    device: torch.device,
    validation: SplitEval,
    test: SplitEval | None,
) -> None:
    """Score one run's selected checkpoint on validation, and on test where asked.

    Args:
        record: The run's record, filled in place.
        state: The selected parameters.
        rung: The rung.
        config: The ladder's training configuration.
        model_config: The ladder's model configuration.
        shards: The shard set.
        device: Where the model lives.
        validation: The final validation windows.
        test: The final test windows, or ``None`` to score validation only.
    """
    spec = rung.spec(shards.context_tokens, shards.vocab_size, 0.0)
    autocast_on = config.optimiser.precision == "bf16"
    if record.kind == "lm":
        model = TelemetryDecoder(spec).to(device)
        model.load_state_dict({k: v.to(device) for k, v in state.items()})
        model.eval()
        record.lm_loss = language_model_losses(model, validation, device, autocast_on)
        return
    risk = RiskSpec(hidden=model_config.head_hidden, dropout=0.0, label=config.risk.label)
    scorer = RiskModel(spec, risk, frozen=False).to(device)
    scorer.load_state_dict({k: v.to(device) for k, v in state.items()})
    scorer.eval()
    record.validation, _ = score_split(scorer, validation, device, autocast_on, record.prior_offset)
    if test is not None:
        record.test, record.test_years = score_split(
            scorer, test, device, autocast_on, record.prior_offset
        )


# =====================================================================================
# the report
# =====================================================================================


def _num(value: float, digits: int = 4) -> str:
    return "n/a" if value != value else f"{value:.{digits}f}"


def _pct(value: float, digits: int = 2) -> str:
    return "n/a" if value != value else f"{value * 100:.{digits}f}%"


def _spread(values: Sequence[float]) -> str:
    """Mean and half-range of a few seeds, or the single value where there is one."""
    kept = [v for v in values if v == v]
    if not kept:
        return "n/a"
    if len(kept) == 1:
        return _num(kept[0])
    return f"{statistics.mean(kept):.4f} +/- {(max(kept) - min(kept)) / 2:.4f}"


def _by(records: Sequence[RunRecord], kind: RunKind, rung: str) -> list[RunRecord]:
    return [r for r in records if r.kind == kind and r.rung == rung]


def _setup_section(
    config: LadderConfig, model_config: LadderModel, shards: ShardSet, records: Sequence[RunRecord]
) -> str:
    rows = []
    for rung in model_config.rungs:
        head = rung.d_model // rung.n_head
        made = [r for r in records if r.rung == rung.name and r.kind == "lm"]
        backbone = made[0].params["backbone"] if made else 0
        rows.append(
            (
                rung.name,
                rung.d_model,
                rung.n_layer,
                rung.n_head,
                head,
                f"{backbone:,}" if backbone else "-",
                f"{12 * rung.n_layer * rung.d_model**2:,}",
                ", ".join(str(s) for s in rung.seeds),
                "yes" if head % HEAD_DIM_MULTIPLE == 0 else "NO",
            )
        )
    body = (
        "Four sizes, and **context is held fixed across all of them** -- it is a separate "
        "ablation, not a confound with size. Parameters are counted excluding embeddings, "
        "which is the axis of every plot below and what `12 * L * d^2` approximates.\n\n"
        + table(
            [
                "rung",
                "d_model",
                "layers",
                "heads",
                "d_head",
                "parameters (measured, excl. embeddings)",
                "12 L d^2",
                "seeds",
                f"d_head divisible by {HEAD_DIM_MULTIPLE}",
            ],
            rows,
        )
        + f"\nThe last column is not decoration. The fused attention kernels require a head "
        f"dimension divisible by {HEAD_DIM_MULTIPLE}; a rung that misses it falls back "
        "without warning to the kernel that materialises the whole score matrix, measured "
        "on this project's hardware at 8 times the memory and an eighth of the throughput "
        "for exactly the same parameter count. The head counts below were chosen to clear "
        "it at the same widths.\n\n"
        + kv_table(
            {
                "tokenizer": config.tokenizer_config,
                "shards": shards.root.name,
                "context": f"{shards.context_steps} steps x {shards.tokens_per_step} tokens = "
                f"{shards.context_tokens} tokens, the same at every rung",
                "training stride": f"{config.train_stride} steps (hourly). At stride 1 the "
                "windows overlap in every step but one and the effective sample size is far "
                "below the token count",
                "evaluation stride": f"{config.evaluation.stride} step, dense per-step "
                "prediction, then capped per source",
                "optimiser": f"AdamW, betas ({config.optimiser.beta1}, {config.optimiser.beta2}), "
                f"weight decay {config.optimiser.weight_decay} on matrices only, cosine schedule "
                f"with {config.optimiser.warmup_fraction:.0%} warmup, gradient clip "
                f"{config.optimiser.grad_clip}, {config.optimiser.precision}",
                "risk label": config.risk.label,
                "selection": "; ".join(f"{k}: {v}" for k, v in SELECTION.items()),
                "test": "never selected on",
            }
        )
    )
    return section("The ladder, and what is held fixed", body)


def _budget_section(
    config: LadderConfig, model_config: LadderModel, shards: ShardSet, records: Sequence[RunRecord]
) -> str:
    rows = [
        (
            kind,
            f"{config.budget_for(kind).windows:,}",
            f"{config.budget_for(kind).windows * shards.context_tokens:,}",
            config.budget_for(kind).batch_windows,
            config.budget_for(kind).accumulate,
            f"{config.budget_for(kind).learning_rate:.1e}",
            config.budget_for(kind).steps,
            config.budget_for(kind).evaluations,
        )
        for kind in config.runs
    ]
    spent = {}
    for rung in model_config.rungs:
        for kind in config.runs:
            made = _by(records, kind, rung.name)
            if made:
                spent[f"{rung.name} {kind}"] = f"{sum(r.seconds for r in made) / 60:.1f} min"
    body = (
        "Budgets are in **windows**, not epochs: an epoch is a different amount of work at "
        "every rung and the comparison is between rungs. The randomly initialised control "
        "is given the fine-tuned run's budget exactly, so the comparison between them is "
        "initialisation and nothing else; the configuration refuses to load if they "
        "differ.\n\n"
        + table(
            [
                "run",
                "windows",
                "tokens",
                "batch",
                "accumulate",
                "peak lr",
                "optimiser steps",
                "validation measurements",
            ],
            rows,
        )
        + "\n**Wall clock, training only** (measurement included, final scoring not)\n\n"
        + kv_table(spent)
    )
    return section("What each run was allowed to spend", body)


def _lm_section(model_config: LadderModel, records: Sequence[RunRecord]) -> str:
    sources = sorted({s for r in records if r.kind == "lm" for s in r.lm_loss})
    headers = ["rung", "parameters", "validation loss (selected)", *(f"{s}: loss" for s in sources)]
    rows = []
    for rung in model_config.rungs:
        made = _by(records, "lm", rung.name)
        if not made:
            continue
        cells: list[str | int] = [
            rung.name,
            f"{made[0].params['backbone']:,}",
            _spread([r.best.value for r in made]),
        ]
        cells += [_spread([r.lm_loss.get(s, math.nan) for r in made]) for s in sources]
        rows.append(tuple(cells))
    shares = {}
    for record in records:
        if record.kind == "lm":
            continue
        for score in record.validation:
            shares[score.source] = _pct(score.nan_share)
    body = (
        "Run (1): next-token prediction on the train split, selected on validation "
        "next-token loss. This is the course deliverable and the representation runs (2) "
        "and (3) read. Loss is mean cross entropy per predicted token, in nats; `<nan>` is "
        "a token the model is meant to predict, because missingness is itself a shift "
        "signal (ADR-0006), so no position is excluded from it.\n\n"
        "Where a rung has three seeds the cell is mean +/- half the range; where it has "
        "one it is that run.\n\n" + table(headers, rows)
    )
    if shares:
        body += (
            "\nEach source's `<nan>` share over the windows scored, carried beside every "
            "per-source figure by the project's first reporting rule:\n\n"
            + kv_table(shares, key_header="source", value_header="`<nan>` share")
        )
    return section("The ladder: language modelling", body)


def _risk_section(
    config: LadderConfig, model_config: LadderModel, records: Sequence[RunRecord], split: str
) -> str:
    """Render one split's AUPRC per rung and per source.

    Every source keeps its row even where the metric is undefined, because a source that
    disappears from a table reads as a source that was never scored. The window and
    positive counts are in the table the figures were computed from, since every figure
    here is a seeded subsample.

    Args:
        config: The ladder's training configuration.
        model_config: The ladder's model configuration.
        records: Every run made.
        split: ``validation`` or ``test``.

    Returns:
        A Markdown section, or an empty string where nothing was scored on this split.
    """
    kinds: list[RunKind] = [k for k in ("probe", "finetune", "random") if k in config.runs]

    def scores(record: RunRecord) -> list[RiskScore]:
        return record.validation if split == "validation" else record.test

    sources = sorted({score.source for r in records for score in scores(r)})
    if not sources:
        return ""
    rows = []
    for rung in model_config.rungs:
        for source in sources:
            cells: list[str] = [rung.name, f"`{source}`"]
            seen: RiskScore | None = None
            for kind in kinds:
                values = []
                for record in _by(records, kind, rung.name):
                    for score in scores(record):
                        if score.source == source:
                            values.append(score.auprc)
                            seen = score
                cells.append(_spread(values))
            if seen is None:
                continue
            rows.append(
                (
                    *cells,
                    _pct(seen.base_rate),
                    f"{seen.windows:,}",
                    f"{seen.positives:,}",
                    _pct(seen.nan_share),
                )
            )
    if not rows:
        return ""
    lead = (
        f"AUPRC on the **{split}** split, per source, never pooled. The base rate is the "
        "floor a random scorer reaches and is printed beside every AUPRC, because at a base "
        "rate of two per cent an AUPRC of 0.10 is five times a coin toss and reads like "
        "failure without it. The `<nan>` share is the project's first reporting rule, and "
        "the window count is there because every figure is a seeded subsample of the "
        "split.\n\n"
    )
    if split == "test":
        lead += (
            "**Scored for the first seed of each rung only.** The seeds measure run-to-run "
            "variance, which is a validation quantity; the test pass is the expensive one "
            "and is made once per rung and run. A cell here is therefore one run, not a "
            "mean.\n\n"
        )
    body = lead + table(
        [
            "rung",
            "source",
            *kinds,
            "base rate",
            "windows",
            "positives",
            "`<nan>` share",
        ],
        rows,
    )
    if any("`care`" == r[1] for r in rows):
        body += (
            f"\n`care` is a {CARE_CAVEAT}. Its per-step positives are thin enough at this "
            "subsample that an AUPRC over them carries no weight; the row is present so the "
            "source is visibly scored rather than quietly dropped, and `n/a` means the "
            "subsample held no positive window at all.\n"
        )
    return section(f"The ladder: event risk on {split}", body)


def _ablation_section(
    config: LadderConfig, model_config: LadderModel, records: Sequence[RunRecord]
) -> str:
    if "random" not in config.runs:
        return ""
    rows = []
    for rung in model_config.rungs:
        for kind in ("probe", "finetune"):
            if kind not in config.runs:
                continue
            pretrained = [r.best.value for r in _by(records, kind, rung.name)]
            control = [r.best.value for r in _by(records, "random", rung.name)]
            kept_a = [v for v in pretrained if v == v]
            kept_b = [v for v in control if v == v]
            if not kept_a or not kept_b:
                continue
            difference = statistics.mean(kept_a) - statistics.mean(kept_b)
            spread = max(
                (max(kept_a) - min(kept_a)) / 2 if len(kept_a) > 1 else 0.0,
                (max(kept_b) - min(kept_b)) / 2 if len(kept_b) > 1 else 0.0,
            )
            verdict = (
                "within seed spread"
                if spread and abs(difference) <= spread
                else ("pretraining ahead" if difference > 0 else "control ahead")
            )
            rows.append(
                (
                    rung.name,
                    kind,
                    _spread(pretrained),
                    _spread(control),
                    f"{difference:+.4f}",
                    verdict,
                )
            )
    body = (
        "The comparison the ladder exists for. Run (4) is the same head, the same budget "
        "and the same size on a **randomly initialised** backbone, so the only difference "
        "from run (3) is whether the backbone was pretrained on next-token prediction over "
        "quantised telemetry. A flat or negative column is a result and is reported as "
        "one.\n\n"
        + table(
            [
                "rung",
                "pretrained run",
                "pretrained validation AUPRC",
                "random-init control",
                "difference",
                "against seed spread",
            ],
            rows,
        )
        + "\n`within seed spread` means the gap is no larger than the half-range across the "
        "seeds that were run at that rung, so it is not evidence of a difference. Where a "
        "rung has one seed there is no spread to compare against, and the small rungs' "
        "spread is the error bar to read it with.\n"
    )
    return section("The pretraining ablation: does next-token pretraining buy anything", body)


def _seed_section(
    config: LadderConfig, model_config: LadderModel, records: Sequence[RunRecord]
) -> str:
    rows = []
    for rung in model_config.rungs:
        for kind in config.runs:
            made = _by(records, kind, rung.name)
            values = [r.best.value for r in made if r.best.value == r.best.value]
            if len(values) < 2:
                continue
            rows.append(
                (
                    rung.name,
                    kind,
                    len(values),
                    _num(statistics.mean(values)),
                    _num(statistics.pstdev(values)),
                    f"{min(values):.4f} to {max(values):.4f}",
                )
            )
    counts = {r.name: len(r.seeds) for r in model_config.rungs}
    body = (
        "**Three seeds at the small rungs, one at the large ones.** That is what the budget "
        "allowed, and it is stated rather than implied: the spread measured at the rungs "
        "that have it is the error bar the single-seed rungs are read with, and no "
        "single-seed number carries an interval of its own.\n\n"
        + kv_table({k: f"{v} seed(s)" for k, v in counts.items()}, key_header="rung")
        + "\n"
        + (
            table(
                ["rung", "run", "seeds", "mean", "population sd", "range"],
                rows,
            )
            if rows
            else "No rung has more than one seed in this run.\n"
        )
    )
    return section("Run-to-run variance", body)


def _year_section(records: Sequence[RunRecord]) -> str:
    """Render every multi-year test source's AUPRC per calendar year.

    Args:
        records: Every run made.

    Returns:
        A Markdown section, or an empty string where nothing was scored per year.
    """
    rows = [
        (
            r.rung,
            r.kind,
            f"`{source}`",
            str(year),
            _num(score.auprc),
            _pct(score.base_rate),
            f"{score.windows:,}",
            f"{score.positives:,}",
        )
        for r in records
        for source, year, score in r.test_years
    ]
    if not rows:
        return ""
    body = (
        "A held-out site is reported per calendar year as well as pooled "
        "(`per_year_sites`, ADR-0008): the two years of the held-out record are different "
        "grids and a pooled number would hide which one moved. Every other multi-year test "
        "source is broken out the same way, for the same reason.\n\n"
        + table(
            [
                "rung",
                "run",
                "source",
                "year",
                "AUPRC",
                "base rate",
                "windows",
                "positives",
            ],
            rows,
        )
    )
    return section("Test sources, per calendar year", body)


def render_ladder(
    header: str,
    config: LadderConfig,
    model_config: LadderModel,
    shards: ShardSet,
    records: Sequence[RunRecord],
) -> str:
    """Render the ladder report.

    Args:
        header: The report header.
        config: The ladder's training configuration.
        model_config: The ladder's model configuration.
        shards: The shard set the runs read.
        records: Every run made.

    Returns:
        A Markdown document.
    """
    parts = [
        header,
        _setup_section(config, model_config, shards, records),
        _budget_section(config, model_config, shards, records),
        _lm_section(model_config, records),
        _risk_section(config, model_config, records, "validation"),
        _ablation_section(config, model_config, records),
        _seed_section(config, model_config, records),
        _risk_section(config, model_config, records, "test"),
        _year_section(records),
    ]
    if config.notes:
        parts.append(section("Notes", config.notes + "\n"))
    return "".join(p for p in parts if p)


def run_ladder(paths: ProjectPaths, config_path: Path, device_name: str | None = None) -> Path:
    """Run the whole ladder and write its report.

    Args:
        paths: Resolved project paths.
        config_path: The ladder configuration.
        device_name: Torch device to run on; chosen automatically when omitted.

    Returns:
        The report written.

    Raises:
        ValueError: If the shards were built at a different context length than the
            configuration asks for.
    """
    config = load_config(config_path, LadderConfig)
    model_config = load_config(paths.repo_root / config.model_config_path, LadderModel)
    tokenizer_config = load_config(paths.repo_root / config.tokenizer_config, QuantileBinsConfig)
    shards = ShardSet.load(shards_dir(paths, tokenizer_path(paths, tokenizer_config)))
    if shards.context_steps != model_config.context_steps:
        raise ValueError(
            f"the shards hold {shards.context_steps}-step windows and the model configuration "
            f"asks for {model_config.context_steps}; re-shard or fix the configuration"
        )
    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    digest = config_hash(
        {"train": config.model_dump(mode="json"), "model": model_config.model_dump(mode="json")}
    )
    checkpoints = paths.checkpoints_dir / f"ladder_v{config.version}_{digest}"
    checkpoints.mkdir(parents=True, exist_ok=True)
    logger.info("ladder %s on %s, shards %s", digest, device, shards.root.name)

    evaluation = config.evaluation
    selection = build_split(
        shards,
        "val",
        evaluation.selection_windows,
        evaluation.stride,
        evaluation.seed,
        evaluation.batch_windows,
        config.risk.label,
    )
    selection_lm = build_split(
        shards,
        "val",
        evaluation.selection_windows,
        evaluation.stride,
        evaluation.seed,
        evaluation.batch_windows,
        None,
    )
    validation = build_split(
        shards,
        "val",
        evaluation.validation_windows,
        evaluation.stride,
        evaluation.seed,
        evaluation.batch_windows,
        config.risk.label,
    )
    validation_lm = build_split(
        shards,
        "val",
        evaluation.validation_windows,
        evaluation.stride,
        evaluation.seed,
        evaluation.batch_windows,
        None,
    )
    test = build_split(
        shards,
        "test",
        evaluation.test_windows,
        evaluation.stride,
        evaluation.seed,
        evaluation.batch_windows,
        config.risk.label,
    )

    records: list[RunRecord] = []
    for rung in model_config.rungs:
        for seed in rung.seeds:
            backbone: dict[str, Tensor] | None = None
            for kind in config.runs:
                logger.info("=== %s / %s / seed %d ===", rung.name, kind, seed)
                record, state = run_one(
                    kind,
                    rung,
                    seed,
                    config,
                    model_config,
                    shards,
                    device,
                    selection_lm if kind == "lm" else selection,
                    backbone,
                    checkpoints,
                )
                if kind == "lm":
                    backbone = state
                # Test is scored for the first seed of each rung only: the seeds are there
                # to measure run-to-run variance, which is a validation quantity, and the
                # test pass is the expensive one.
                score_record(
                    record,
                    state,
                    rung,
                    config,
                    model_config,
                    shards,
                    device,
                    validation_lm if kind == "lm" else validation,
                    test if (kind != "lm" and seed == rung.seeds[0]) else None,
                )
                records.append(record)
                logger.info(
                    "%s selected %s = %.4f in %.1f min",
                    record.key,
                    record.selection,
                    record.best.value,
                    record.seconds / 60,
                )

    header = "# The telemetry model ladder\n\n" + kv_table(
        {
            "training config": config_path.as_posix(),
            "model config": config.model_config_path,
            "config hash (both files)": digest,
            "tokenizer config": config.tokenizer_config,
            "shards": shards.root.name,
            "device": str(device),
            "checkpoints": f"checkpoints/{checkpoints.name} (never committed)",
            "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "git_sha": git_sha(paths.repo_root),
            "generated by": "faultline model ladder",
        }
    )
    report = render_ladder(header, config, model_config, shards, records)
    stem = f"ladder_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    destination = paths.data_reports_dir / f"{stem}.md"
    destination.write_text(report, encoding="utf-8")
    # The machine-readable results go beside the report and NOT beside the checkpoints.
    # `checkpoints/` is git-ignored and a pre-commit hook refuses anything under it, so a
    # record written there is a result of the headline experiment that no commit carries.
    records_path = paths.data_reports_dir / f"{stem}.json"
    records_path.write_text(
        json.dumps([_serialise(r) for r in records], indent=2) + "\n", encoding="utf-8"
    )
    logger.info("wrote %s and %s", destination, records_path)
    return destination


def _serialise(record: RunRecord) -> dict[str, Any]:
    """The machine-readable form of one run, written beside the report it summarises."""
    return {
        "kind": record.kind,
        "rung": record.rung,
        "seed": record.seed,
        "params": record.params,
        "selection": record.selection,
        "best": {"step": record.best.step, "value": record.best.value, **record.best.extra},
        "history": [
            {"step": m.step, "windows": m.windows, "value": m.value} for m in record.history
        ],
        "seconds": record.seconds,
        "windows": record.windows,
        "tokens": record.tokens,
        "train_loss": record.train_loss,
        "lm_loss": record.lm_loss,
        "validation": [s.__dict__ for s in record.validation],
        "test": [s.__dict__ for s in record.test],
        "test_years": [
            {"source": source, "year": year, **score.__dict__}
            for source, year, score in record.test_years
        ],
        "checkpoint": record.checkpoint,
    }
