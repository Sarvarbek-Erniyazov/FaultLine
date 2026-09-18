"""ADR-0025: H1, the joint arm against ``tel_only``, forward in time on the training sites.

H1 claims that the text pathway carries risk signal the telemetry tokens do not. It is read as a
same-seed paired AUPRC difference between the ``joint`` arm of ``configs/train/joint_v1.yaml`` and
the three existing ``tel_only`` seeds, on the pooled Kelmarsh + Penmanshiel stride-12 test split.
The joint probe reads ADR-0025 §2's ``tail_anchored_2048`` window over every status row (R0).

**This module holds the configuration only.** It was written in the registration commit
(``3e29202``), before any code that builds, trains or scores the joint arm existed. That code
arrived in F6-1b: the windows and the mixture sampler in :mod:`faultline.training.joint_windows`,
the controls in :mod:`faultline.evaluation.h1_controls` and the F6-2 runner in
:mod:`faultline.evaluation.h1_arms`. It reads ``configs/train/h1_arms_v*.yaml`` (the F6-2 runner)
and ``configs/eval/h1_gate_v*.yaml`` (the rule by value). ``H1ArmsConfig.budget`` is the gate
run's rounding (``GateCheckConfig.budget``), so the joint arm pretrains on the same 763 steps.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from faultline.config import StrictModel
from faultline.evaluation.gate_check import BootstrapConfig
from faultline.training.config import Budget


class OptimiserConfig(StrictModel):
    """The gate run's pretraining protocol, restated value for value.

    Attributes:
        batch_windows: Windows per micro-batch.
        accumulate: Micro-batches per optimiser step.
        learning_rate: Peak learning rate.
        evaluations: Validation measurements over pretraining.
        selection_windows: Validation windows per source for the pretraining read.
    """

    batch_windows: int = Field(gt=0)
    accumulate: int = Field(gt=0)
    learning_rate: float = Field(gt=0.0)
    evaluations: int = Field(gt=0)
    selection_windows: int = Field(gt=0)


class SelectionSplit(StrictModel):
    """The probes' selection split, drawn as F3 drew it (ADR-0024 §5).

    Attributes:
        shard_keys: The validation shards drawn from.
        windows_per_source: Windows drawn from each shard.
        stride: Index thinning before the draw.
        seed: The draw's seed.
    """

    shard_keys: list[str] = Field(min_length=1)
    windows_per_source: int = Field(gt=0)
    stride: int = Field(gt=0)
    seed: int


class JointProbeConfig(StrictModel):
    """The probe protocol in force, over ADR-0025 §2's window.

    Attributes:
        design: The probe design, §a ``final_position``.
        cadence_config: G3's evaluation cadence.
        checkpoint: The probe checkpoint read; ``final_step``.
        label: The label the probe is trained and scored on.
        window_rule: ADR-0025 §2's registered rule, by name.
        context_tokens: The padded window length.
        status_rows: Which status rows the window holds; ``all`` is R0.
        selection: The probes' selection split.
    """

    design: Literal["final_position"]
    cadence_config: str
    checkpoint: Literal["final_step"]
    label: str
    window_rule: Literal["tail_anchored_2048"]
    context_tokens: int = Field(gt=0)
    status_rows: Literal["all"]
    selection: SelectionSplit


class WindowIndexCounts(StrictModel):
    """The M1 window index the tel+status index must reproduce (ADR-0025 §2).

    Attributes:
        test_shard_keys: The scored test shards.
        test_stride: The scored thinning.
        test_windows: Windows at that stride.
        test_positives: Positive windows at that stride.
        train_shard_keys: The probe training shards.
        train_stride: The probe training thinning.
        train_windows: Windows at that stride.
        train_positives: Positive windows at that stride.
    """

    test_shard_keys: list[str] = Field(min_length=1)
    test_stride: int = Field(gt=0)
    test_windows: int = Field(gt=0)
    test_positives: int = Field(gt=0)
    train_shard_keys: list[str] = Field(min_length=1)
    train_stride: int = Field(gt=0)
    train_windows: int = Field(gt=0)
    train_positives: int = Field(gt=0)


class H1ArmsConfig(StrictModel):
    """Top level of ``configs/train/h1_arms_v*.yaml``: the F6-2 runner.

    Attributes:
        version: Version of this configuration.
        mixture_config: The mixture naming the arm.
        ladder_config: The ladder: the rung's spec and the probe stage's recipe.
        gate_config: The gate run, whose protocol every arm shares.
        arm: The arm pretrained and probed.
        rung: The model rung.
        seeds: Pretraining and probe seeds.
        tokens: The token budget before rounding up to whole optimiser steps.
        optimiser: The gate run's pretraining protocol.
        probe: The probe protocol.
        window_index: The counts the tel+status index must reproduce.
    """

    version: int = 0
    mixture_config: str
    ladder_config: str
    gate_config: str
    arm: str
    rung: str
    seeds: list[int] = Field(min_length=1)
    tokens: int = Field(gt=0)
    optimiser: OptimiserConfig
    probe: JointProbeConfig
    window_index: WindowIndexCounts

    @property
    def batch_windows(self) -> int:
        """Windows per forward pass while pretraining."""
        return self.optimiser.batch_windows

    def budget(self, context_tokens: int) -> Budget:
        """The pretraining window budget: the token target, rounded up to a whole step."""
        per_step = self.optimiser.batch_windows * self.optimiser.accumulate
        steps = -(-self.tokens // (per_step * context_tokens))
        return Budget(
            windows=steps * per_step,
            batch_windows=self.optimiser.batch_windows,
            accumulate=self.optimiser.accumulate,
            learning_rate=self.optimiser.learning_rate,
            evaluations=self.optimiser.evaluations,
        )


class Comparison(StrictModel):
    """What the H1 difference compares.

    Attributes:
        arm: The arm under test.
        reference: The arm it is compared with.
        pairing: How the two are paired; ``same_seed``.
        seeds: The seeds compared.
        checkpoint: The probe checkpoint read on both sides.
        windows: The window variant the verdict is read on; ``R0``.
    """

    arm: str
    reference: str
    pairing: Literal["same_seed"]
    seeds: list[int] = Field(min_length=1)
    checkpoint: Literal["final_step"]
    windows: Literal["R0"]


class H1Rule(StrictModel):
    """ADR-0025 §5, by value.

    Attributes:
        smallest_effect: The smallest AUPRC difference of interest.
        supported_lower_bound_above: Every paired lower bound must exceed this for SUPPORTED.
        supported_median_above: The median point difference must exceed this for SUPPORTED.
        refuted_upper_bound_below: Every paired upper bound must fall below this for REFUTED.
        otherwise: The verdict when neither holds.
    """

    smallest_effect: float = Field(gt=0.0)
    supported_lower_bound_above: float
    supported_median_above: float
    refuted_upper_bound_below: float
    otherwise: Literal["inconclusive"]


class H1GateConfig(StrictModel):
    """Top level of ``configs/eval/h1_gate_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        registered_in: ADR-0025's registration commit, or ``pending`` inside that commit.
        axis_config: The axis-gate configuration naming the temporal split.
        runner_config: The joint arm's runs.
        reference_config: The run holding ``tel_only``'s saved final-step scores.
        label: The label scored.
        axis: The axis scored; ``temporal``.
        stride: The scored thinning.
        windows: Windows scored.
        positives: Positive windows scored.
        bootstrap: ADR-0021's interval, as ADR-0024 pairs it.
        comparison: What is compared.
        rule: The verdict rule.
        reported_variants: Decompositions reported beside the verdict.
        controls: Controls reported beside the verdict.
        caveats: Caveats carried on every H1 row.
    """

    version: int = 0
    registered_in: str
    axis_config: str
    runner_config: str
    reference_config: str
    label: str
    axis: Literal["temporal"]
    stride: int = Field(gt=0)
    windows: int = Field(gt=0)
    positives: int = Field(gt=0)
    bootstrap: BootstrapConfig
    comparison: Comparison
    rule: H1Rule
    reported_variants: list[str] = Field(min_length=1)
    controls: list[str] = Field(min_length=1)
    caveats: list[str]
