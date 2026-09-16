"""The ladder's run configuration (M1e).

One file drives the whole experiment, because the experiment is the ladder and not any
one of its runs: a size sweep reported one model at a time is a different, weaker claim.
The file fixes the rungs, the seeds, the two strides, the optimiser, the budgets, and
which of the four runs are made at each rung.

Three things in here are pre-registered rather than tuned, and each is a field so that the
record shows it was fixed before the runs rather than chosen after them:

* **Context is constant across the ladder.** ``context_steps`` is one number for every
  rung. Varying it with size would confound the two, and it is a separate ablation.
* **The training stride is not 1.** Windows at stride 1 overlap in 143 of 144 steps, so
  the effective sample size is far below the token count. Both strides are recorded.
* **Selection never reads the test split.** The selection metric is named per run type and
  is always measured on validation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from faultline.config import StrictModel
from faultline.model.transformer import ModelSpec

#: The four runs the ladder makes at each rung, in the order they must run: the language
#: model is the representation the next two read, and the ablation is the control for them.
RunKind = Literal["lm", "probe", "finetune", "random"]
RUN_KINDS: tuple[RunKind, ...] = ("lm", "probe", "finetune", "random")

#: What each run is selected on. Never a test-split quantity.
SELECTION: dict[RunKind, str] = {
    "lm": "validation next-token loss",
    "probe": "validation AUPRC",
    "finetune": "validation AUPRC",
    "random": "validation AUPRC",
}


class Rung(StrictModel):
    """One rung of the size ladder.

    Attributes:
        name: The rung's label.
        d_model: Residual width.
        n_layer: Blocks.
        n_head: Attention heads.
        seeds: The seeds run at this rung. Three at the small rungs establishes
            run-to-run variance; one at the large rungs is what the budget allows, and
            the report quotes the small rungs' spread as the error bar rather than
            implying three seeds throughout.
    """

    name: str
    d_model: int = Field(gt=0)
    n_layer: int = Field(gt=0)
    n_head: int = Field(gt=0)
    seeds: list[int] = Field(min_length=1)

    def spec(self, context_tokens: int, vocab_size: int, dropout: float) -> ModelSpec:
        """Build the model specification for this rung.

        Args:
            context_tokens: Context length in tokens, the same for every rung.
            vocab_size: Identifiers the embedding covers.
            dropout: Dropout the runs use.

        Returns:
            The specification.
        """
        return ModelSpec(
            name=self.name,
            d_model=self.d_model,
            n_layer=self.n_layer,
            n_head=self.n_head,
            context=context_tokens,
            vocab_size=vocab_size,
            dropout=dropout,
        )


class LadderModel(StrictModel):
    """Top level of ``configs/model/ladder_v*.yaml``: the architecture, and only that.

    Kept apart from the training configuration because the two answer different
    questions and change on different occasions: this file says what the models *are*,
    and a training file says what a run does to them. The ladder reads both and records
    the hash of each.

    Attributes:
        version: Version of this configuration.
        context_steps: Window length in grid steps, THE SAME AT EVERY RUNG. Varying it
            with size would confound size with context; context is a separate ablation.
        dropout: Dropout in the backbone, the same at every rung.
        head_hidden: The risk head's hidden width, as a multiple of ``d_model``.
        head_dropout: Dropout inside the risk head.
        rungs: The sizes, smallest first.
    """

    version: int = 0
    context_steps: int = Field(gt=0)
    dropout: float = Field(default=0.0, ge=0.0, lt=1.0)
    head_hidden: float = Field(default=1.0, gt=0.0)
    head_dropout: float = Field(default=0.0, ge=0.0, lt=1.0)
    rungs: list[Rung] = Field(min_length=1)

    @model_validator(mode="after")
    def _ordered(self) -> LadderModel:
        """Reject a ladder that could not be read as one.

        Raises:
            ValueError: If rung names repeat, the rungs are not listed smallest first, or
                a rung's width is not divisible by its head count.
        """
        names = [rung.name for rung in self.rungs]
        if len(set(names)) != len(names):
            raise ValueError(f"rung names repeat: {names}")
        sizes = [12 * rung.n_layer * rung.d_model**2 for rung in self.rungs]
        if sizes != sorted(sizes):
            raise ValueError(
                f"rungs must be listed smallest first so the report reads as a ladder: {names}"
            )
        for rung in self.rungs:
            if rung.d_model % rung.n_head:
                raise ValueError(
                    f"{rung.name}: d_model {rung.d_model} is not divisible by n_head {rung.n_head}"
                )
        return self


class Optimiser(StrictModel):
    """The optimiser and schedule, shared by every run.

    Attributes:
        weight_decay: AdamW decay, applied to matrices and not to norms or embeddings.
        beta1: First moment decay.
        beta2: Second moment decay.
        warmup_fraction: Share of the budget spent warming the learning rate up.
        grad_clip: Global gradient-norm clip.
        precision: Autocast dtype.
    """

    weight_decay: float = Field(default=0.1, ge=0.0)
    beta1: float = Field(default=0.9, gt=0.0, lt=1.0)
    beta2: float = Field(default=0.95, gt=0.0, lt=1.0)
    warmup_fraction: float = Field(default=0.02, ge=0.0, lt=0.5)
    grad_clip: float = Field(default=1.0, gt=0.0)
    precision: Literal["bf16", "fp32"] = "bf16"


class Budget(StrictModel):
    """What one run is allowed to spend, and how often it is looked at.

    A budget in windows rather than epochs, because the runs are compared to each other
    and an epoch is a different amount of work at each rung.

    Attributes:
        windows: Training windows the run consumes.
        batch_windows: Windows per forward pass.
        accumulate: Forward passes per optimiser step.
        learning_rate: Peak learning rate.
        evaluations: How many times the run stops to measure validation. The best of
            these is the run's selected checkpoint.
    """

    windows: int = Field(gt=0)
    batch_windows: int = Field(gt=0)
    accumulate: int = Field(default=1, gt=0)
    learning_rate: float = Field(gt=0.0)
    evaluations: int = Field(default=10, gt=0)

    @property
    def steps(self) -> int:
        """Optimiser steps in the budget."""
        return max(1, self.windows // (self.batch_windows * self.accumulate))


class RiskStage(StrictModel):
    """What the three risk runs share.

    Attributes:
        label: The window-index column the head is trained and selected on.
        positive_weight: Weight on the positive class in the loss.
        probe: The budget of the frozen-backbone run.
        finetune: The budget of the unfrozen run.
        random: The budget of the randomly-initialised control. It matches ``finetune``
            so that the comparison is initialisation and nothing else; the validator
            enforces that rather than trusting the file.
    """

    label: str = "narrow_within_24h"
    positive_weight: float = Field(default=1.0, gt=0.0)
    probe: Budget
    finetune: Budget
    random: Budget

    @model_validator(mode="after")
    def _control_matches(self) -> RiskStage:
        """Refuse a control the comparison could not be read from.

        Raises:
            ValueError: If the randomly-initialised control is not given the same budget
                as the fine-tuned run it is the control for.
        """
        same = ("windows", "batch_windows", "accumulate", "learning_rate")
        differing = [f for f in same if getattr(self.random, f) != getattr(self.finetune, f)]
        if differing:
            raise ValueError(
                f"the random-initialisation control differs from finetune in {differing}; "
                "it is the control for that run and must differ only in initialisation"
            )
        return self


class PositiveBudget(StrictModel):
    """A risk run's budget in positives seen, not in windows or steps (M3 step 0).

    M1e budgeted its risk runs in windows: 40,000 windows at the natural base rate bought
    882 positives, and 49% of optimiser steps carried none. A budget in windows hides that
    number and a budget in positives cannot, so the positive target is what the file
    states. The window count is derived from it and from the declared positive fraction,
    and both go in the run record.

    Attributes:
        positives: Positive windows the run is to see, counting repeats.
        batch_windows: Windows per forward pass.
        accumulate: Forward passes per optimiser step.
        learning_rate: Peak learning rate, fixed per arm before the runs.
        evaluations: How many times the run stops to measure validation.
    """

    positives: int = Field(gt=0)
    batch_windows: int = Field(gt=0)
    accumulate: int = Field(default=1, gt=0)
    learning_rate: float = Field(gt=0.0)
    evaluations: int = Field(default=10, gt=0)

    def positives_per_batch(self, positive_fraction: float) -> int:
        """Positive windows in every forward pass, exactly.

        Args:
            positive_fraction: The declared share of each batch that is positive.

        Returns:
            The whole number of positives per batch.
        """
        return round(positive_fraction * self.batch_windows)

    def to_budget(self, positive_fraction: float) -> Budget:
        """The window budget the training loop is handed.

        Every step carries exactly ``positives_per_batch * accumulate`` positives, so the
        step count is the positive target over that, rounded up: the run sees at least
        the target and less than one step more.

        Args:
            positive_fraction: The declared share of each batch that is positive.

        Returns:
            The equivalent window budget.
        """
        per_step = self.positives_per_batch(positive_fraction) * self.accumulate
        steps = -(-self.positives // per_step)
        return Budget(
            windows=steps * self.batch_windows * self.accumulate,
            batch_windows=self.batch_windows,
            accumulate=self.accumulate,
            learning_rate=self.learning_rate,
            evaluations=self.evaluations,
        )


class PositiveAwareRiskStage(StrictModel):
    """The three risk runs under M3 step 0's pre-registered remedy.

    Three changes against :class:`RiskStage`, each recorded in ``docs/ROADMAP.md`` (M3,
    step 0) before any run:

    * **Balanced sampling**, not a loss weight. Every training batch holds a declared share
      of positive windows, and the loss is unweighted because the positives are already in
      the batch. Scores are brought back to the natural base rate by
      :func:`faultline.model.risk.prior_correction` wherever a calibrated probability is
      read; a ranking metric (AUPRC) is unchanged by that constant logit shift.
    * **The budget is in positives seen** (:class:`PositiveBudget`).
    * **The frozen probe has its own learning rate.** M1e shared one rate across the three
      arms and reported the cost as limitation (a); this stage refuses a probe rate equal
      to the fine-tune rate. The random control still matches the fine-tune in everything
      but initialisation.

    Attributes:
        label: The window-index column the head is trained and selected on.
        sampling: How positives reach the head. Only ``balanced`` is implemented.
        positive_fraction: The share of each training batch that is positive.
        probe: The frozen-backbone run's budget.
        finetune: The unfrozen run's budget.
        random: The randomly initialised control's budget.
    """

    label: str = "narrow_within_24h"
    sampling: Literal["balanced"]
    positive_fraction: float = Field(gt=0.0, lt=1.0)
    probe: PositiveBudget
    finetune: PositiveBudget
    random: PositiveBudget

    @model_validator(mode="after")
    def _readable(self) -> PositiveAwareRiskStage:
        """Refuse a stage whose arms could not be compared as pre-registered.

        Raises:
            ValueError: If a batch cannot hold a whole, non-zero number of positives and
                negatives at the declared fraction; if the control differs from the
                fine-tune in anything but initialisation; or if the probe shares the
                fine-tune learning rate.
        """
        for name in ("probe", "finetune", "random"):
            arm: PositiveBudget = getattr(self, name)
            exact = self.positive_fraction * arm.batch_windows
            if abs(exact - round(exact)) > 1e-9 or not 0 < round(exact) < arm.batch_windows:
                raise ValueError(
                    f"{name}: positive_fraction {self.positive_fraction} of "
                    f"{arm.batch_windows} windows is not a whole number of positives with "
                    "at least one negative beside it"
                )
        same = ("positives", "batch_windows", "accumulate", "learning_rate")
        differing = [f for f in same if getattr(self.random, f) != getattr(self.finetune, f)]
        if differing:
            raise ValueError(
                f"the random-initialisation control differs from finetune in {differing}; "
                "it is the control for that run and must differ only in initialisation"
            )
        if self.probe.learning_rate == self.finetune.learning_rate:
            raise ValueError(
                "the frozen probe shares the fine-tune learning rate; M3 step 0 gives the "
                "probe its own, declared before the runs"
            )
        return self

    def budget(self, kind: RunKind) -> Budget:
        """The window budget one risk arm is handed.

        Args:
            kind: ``probe``, ``finetune`` or ``random``.

        Returns:
            Its window budget, derived from its positive target.
        """
        arm: PositiveBudget = getattr(self, kind)
        return arm.to_budget(self.positive_fraction)


class Evaluation(StrictModel):
    """How the trained models are scored, and on how much.

    A risk model is scored on every step it would have to make a call on, which is stride
    1 -- and at stride 1 the test split holds about nine million windows, roughly 17
    billion tokens of forward pass per checkpoint. That is not a budget this project has,
    so the windows are subsampled and the size is a field, printed in every table it
    produces. The subsample is seeded and identical for every checkpoint, so the ladder
    compares like with like even where it cannot see everything.

    Attributes:
        stride: The stride windows are taken at before subsampling. 1 is dense per-step
            prediction.
        selection_windows: Validation windows the periodic in-training measurement reads.
            Small, because it is read many times.
        validation_windows: Validation windows the final measurement reads, per source.
        test_windows: Test windows the final measurement reads, per source.
        seed: Seed of the subsample, fixed so every checkpoint sees the same windows.
        batch_windows: Windows per forward pass.
    """

    stride: int = Field(default=1, gt=0)
    selection_windows: int = Field(gt=0)
    validation_windows: int = Field(gt=0)
    test_windows: int = Field(gt=0)
    seed: int = 20260912
    batch_windows: int = Field(default=64, gt=0)


class LadderConfig(StrictModel):
    """Top level of ``configs/train/telemetry_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        tokenizer_config: The tokenizer configuration whose shards the runs read.
        model_config_path: The model configuration holding the rungs and the context.
        train_stride: Steps between the training windows the runs consume.
        runs: Which of the four runs the ladder makes.
        optimiser: The optimiser and schedule.
        lm: The language-modelling budget.
        risk: The three risk runs: M1e's window-budgeted stage, or M3 step 0's
            positive-aware one.
        evaluation: How the trained models are scored.
        notes: Free text printed at the end of the report.
    """

    version: int = 0
    tokenizer_config: str
    model_config_path: str
    train_stride: int = Field(gt=0)
    runs: list[RunKind] = Field(default_factory=lambda: list(RUN_KINDS))
    optimiser: Optimiser = Field(default_factory=Optimiser)
    lm: Budget
    risk: RiskStage | PositiveAwareRiskStage
    evaluation: Evaluation
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> LadderConfig:
        """Reject a ladder that could not be read as one.

        Raises:
            ValueError: If a run kind repeats, a risk run is asked for without the
                language model it reads, or the training stride is 1.
        """
        if len(set(self.runs)) != len(self.runs):
            raise ValueError(f"a run kind is listed twice: {self.runs}")
        needs_backbone = {"probe", "finetune"} & set(self.runs)
        if needs_backbone and "lm" not in self.runs:
            raise ValueError(
                f"{sorted(needs_backbone)} read the language model's backbone, so 'lm' "
                "must be in runs"
            )
        if self.train_stride == 1:
            raise ValueError(
                "train_stride 1 yields windows overlapping in every step but one, so the "
                "effective sample size is far below the token count; set it deliberately"
            )
        return self

    def budget_for(self, kind: RunKind) -> Budget:
        """The budget one run kind is given.

        Args:
            kind: The run kind.

        Returns:
            Its budget.
        """
        if kind == "lm":
            return self.lm
        if isinstance(self.risk, PositiveAwareRiskStage):
            return self.risk.budget(kind)
        return {
            "probe": self.risk.probe,
            "finetune": self.risk.finetune,
            "random": self.risk.random,
        }[kind]
