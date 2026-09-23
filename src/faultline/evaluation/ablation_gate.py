"""ADR-0027: F8, the two ablations read through read-out (d) with the instrument gate.

ADR-0026 §1 withdrew ``joint_status_raw`` and ``joint_no_txt`` because they would have been read
through a read-out that does not respond to text, and admitted them back on one condition: that
H1' be SUPPORTED, so that a read-out demonstrably reading the text exists. It is, and ADR-0026's
outcome adds the second condition — that revisiting them is a new registration against a named
write-up sentence. ADR-0027 is that registration. Each ablation decides exactly one sentence
(§1), each is pretrained at ``joint``'s budget with the narrative share re-weighted onto plain
telemetry so that paired ``tel+status`` exposure is unchanged to the token (§2), each is probed
with (d) ``last_plus_text`` on its own windows (§3), and each passes or fails its own
nine-of-nine random-init gate before its Δ against ``joint`` is read at all (§4, §5).

**This module holds the configuration only.** It is written in the registration commit, before
any code that builds, trains or scores an ablation arm exists (ADR-0027 §7). It reads
``configs/train/ablation_arms_v*.yaml`` (the F8-2 runner) and
``configs/eval/ablation_gate_v*.yaml`` (the gate and the rule, by value). The arms themselves are
``configs/train/joint_v2.yaml``, loaded through :class:`faultline.training.mixture
.JointMixtureConfig`, whose raw-twin rule is what keeps ``joint_status_raw`` an ablation of the
convention and nothing else. :class:`AblationArmsConfig.budget` is the gate run's rounding, as
``H1ArmsConfig.budget`` is, so an ablation pretrains on the same 763 steps as ``joint`` did.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from faultline.config import StrictModel
from faultline.evaluation.gate_check import BootstrapConfig
from faultline.evaluation.h1_gate import OptimiserConfig, SelectionSplit, WindowIndexCounts
from faultline.training.config import Budget
from faultline.training.mixture import StatusConvention

#: The verdicts ADR-0027 §5's four clauses name. Nothing else may be written as a verdict, and a
#: measurement the clauses do not name is reported as measured rather than given a new clause.
ABLATION_VERDICTS: frozenset[str] = frozenset(
    {"hurts", "helps", "equivalent", "inconclusive", "not_evaluable"}
)

#: The read-out every side of every F8 comparison is read through (ADR-0027 §3). ADR-0026 §1's
#: rationale admits this one and no other: an instrument that does not respond to text cannot
#: discriminate between backbones that differ in their text.
ABLATION_READOUT: Literal["last_plus_text"] = "last_plus_text"


class AblationOptimiser(OptimiserConfig):
    """The gate run's pretraining protocol, plus the guard every arm before this one ran under.

    Attributes:
        initial_loss_guard: Whether the pretraining path's initial-loss guard is imposed.
    """

    initial_loss_guard: bool = True


class TokenBudget(StrictModel):
    """ADR-0027 §2's realised counts: what the mixture sampler must hit, per arm.

    ``paired_tel_status_tokens`` is the equality the re-weighting exists to preserve. Giving the
    narrative share to plain telemetry rather than renormalising proportionally keeps every arm's
    ``tel+status`` exposure at ``joint``'s count to the token, so an ablation removes the
    narrative without also adding status.

    Attributes:
        windows: Pretraining windows every arm draws.
        steps: Optimiser steps those windows make.
        context_tokens: Tokens per window.
        total_tokens: Tokens every arm sees.
        paired_tel_status_tokens: ``tel+status`` tokens every arm must see, identical across arms.
        proportional_tel_status_tokens: What proportional renormalisation would have made it.
    """

    windows: int = Field(gt=0)
    steps: int = Field(gt=0)
    context_tokens: int = Field(gt=0)
    total_tokens: int = Field(gt=0)
    paired_tel_status_tokens: int = Field(gt=0)
    proportional_tel_status_tokens: int = Field(gt=0)

    @model_validator(mode="after")
    def _consistent(self) -> TokenBudget:
        """Refuse a budget whose parts do not multiply out, or a re-weighting with nothing to do.

        Raises:
            ValueError: If the windows do not make the total at this context, or if proportional
                renormalisation would not in fact have changed the paired exposure, in which case
                the rationale recorded beside it is false.
        """
        if self.windows * self.context_tokens != self.total_tokens:
            raise ValueError(
                f"{self.windows} windows x {self.context_tokens} tokens is not {self.total_tokens}"
            )
        if self.proportional_tel_status_tokens <= self.paired_tel_status_tokens:
            raise ValueError(
                "proportional renormalisation must raise the paired exposure, or the re-weighting "
                f"has no purpose: {self.proportional_tel_status_tokens} against "
                f"{self.paired_tel_status_tokens}"
            )
        return self


class AblationProbeConfig(StrictModel):
    """The (d) probe protocol every ablation shares (ADR-0027 §3).

    Attributes:
        readout: The read-out probed; ``last_plus_text`` and no other.
        cadence_config: G3's evaluation cadence.
        checkpoint: The probe checkpoint read; ``final_step``.
        label: The label the probe is trained and scored on.
        window_rule: ADR-0025 §2's registered rule, by name.
        context_tokens: The padded window length.
        status_rows: Which status rows the window holds; ``all`` is R0.
        sampling: The probe's sampler; ``balanced``.
        train_stride: Steps between the probe's training windows.
        selection: The probes' selection split.
    """

    readout: Literal["last_plus_text"]
    cadence_config: str
    checkpoint: Literal["final_step"]
    label: str
    window_rule: Literal["tail_anchored_2048"]
    context_tokens: int = Field(gt=0)
    status_rows: Literal["all"]
    sampling: Literal["balanced"]
    train_stride: int = Field(gt=0)
    selection: SelectionSplit


class ArmWindowRule(StrictModel):
    """Per arm, which ``tel+status`` stream its windows are framed over (ADR-0027 §3).

    The M1 index is the same for both arms — the same ``(turbine, year, end step)`` keys, the same
    labels and the same 137,025 / 5,312 counts — but raw strings are longer, so the tail-anchored
    rule drops more whole leading steps. The counts below are the F8 read-only check's.

    Attributes:
        arm: The arm.
        status_convention: The convention its stream is written in.
        reuses_normalized_index: Whether its windows are byte for byte the ones F7' scored.
        windows_differing_in_steps_retained: Test windows retaining a different number of steps.
        positives_differing_in_steps_retained: Positive test windows among them.
        head_cut_windows: Windows where step ``t`` alone exceeded the context.
        random_init_probes: New random-init (d) probes the instrument gate needs on these windows.
    """

    arm: str
    status_convention: StatusConvention
    reuses_normalized_index: bool
    windows_differing_in_steps_retained: int = Field(ge=0)
    positives_differing_in_steps_retained: int = Field(ge=0)
    head_cut_windows: int = Field(ge=0)
    random_init_probes: int = Field(ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> ArmWindowRule:
        """Refuse a rule that claims to reuse the index while also re-framing it.

        Raises:
            ValueError: If an arm reuses the normalized index yet differs from it, or needs its
                own random-init probes; or if it does not reuse it yet needs none, since a gate
                computed on different windows from the arm it gates is not a gate (§4).
        """
        differs = self.windows_differing_in_steps_retained > 0
        if self.reuses_normalized_index and (differs or self.random_init_probes):
            raise ValueError(
                f"{self.arm}: reuses the normalized index but differs from it in "
                f"{self.windows_differing_in_steps_retained} windows and asks for "
                f"{self.random_init_probes} random-init probes"
            )
        if not self.reuses_normalized_index and not self.random_init_probes:
            raise ValueError(
                f"{self.arm}: frames its own windows, so the instrument gate needs its own "
                "random-init probes on them"
            )
        return self


class AblationWindowIndex(WindowIndexCounts):
    """ADR-0025 §2's counts, plus the strata ADR-0027 §6 reports.

    Attributes:
        has_status_windows: Test windows holding at least one status token.
        has_status_positives: Positive windows among them.
        no_status_windows: Test windows holding none.
        no_status_positives: Positive windows among them.
    """

    has_status_windows: int = Field(gt=0)
    has_status_positives: int = Field(gt=0)
    no_status_windows: int = Field(gt=0)
    no_status_positives: int = Field(gt=0)

    @model_validator(mode="after")
    def _strata_partition_the_split(self) -> AblationWindowIndex:
        """Refuse strata that do not partition the scored split.

        Raises:
            ValueError: If the two strata do not sum to the test counts.
        """
        windows = self.has_status_windows + self.no_status_windows
        positives = self.has_status_positives + self.no_status_positives
        if (windows, positives) != (self.test_windows, self.test_positives):
            raise ValueError(
                f"the strata sum to {windows} / {positives}, not "
                f"{self.test_windows} / {self.test_positives}"
            )
        return self


class AblationCost(StrictModel):
    """ADR-0027 §7's itemised cost, and who launches the runs.

    Attributes:
        pretrainings: Ablation pretrainings; ``joint`` is not retrained.
        ablation_probes: (d) probes on the ablation backbones.
        random_init_probes: New random-init (d) probes, on the raw windows only.
        scorings: Scorings of all of the above.
        estimated_seconds: The estimate at ADR-0025 §7's measured per-item rates.
        launched_by: Who launches them; the author, as in F6-2 and F7'-2.
    """

    pretrainings: int = Field(gt=0)
    ablation_probes: int = Field(gt=0)
    random_init_probes: int = Field(ge=0)
    scorings: int = Field(gt=0)
    estimated_seconds: int = Field(gt=0)
    launched_by: Literal["author"]


class AblationArmsConfig(StrictModel):
    """Top level of ``configs/train/ablation_arms_v*.yaml``: the F8-2 runner.

    Attributes:
        version: Version of this configuration.
        mixture_config: The mixture naming the arms.
        ladder_config: The ladder: the rung's spec and the probe stage's recipe.
        gate_config: The gate run, whose protocol every arm shares.
        readout_config: The read-out definitions and the text-position rule.
        random_init_config: ADR-0023's random-init construction, re-used unchanged.
        arms: The arms pretrained and probed; the reference arm is not among them.
        reference_arm: The arm every difference is taken against, not retrained.
        reference_run: The registered run whose saved (d) reads are the reference side.
        rung: The model rung.
        seeds: Pretraining and probe seeds.
        tokens: The token budget before rounding up to whole optimiser steps.
        optimiser: The gate run's pretraining protocol and the initial-loss guard.
        token_budget: The realised counts the sampler must hit.
        probe: The (d) probe protocol.
        window_rule_per_arm: Per arm, which stream its windows are framed over.
        window_index: The counts every arm's index must reproduce, and the strata.
        cost: The itemised cost.
    """

    version: int = 0
    mixture_config: str
    ladder_config: str
    gate_config: str
    readout_config: str
    random_init_config: str
    arms: list[str] = Field(min_length=1)
    reference_arm: str
    reference_run: str
    rung: str
    seeds: list[int] = Field(min_length=1)
    tokens: int = Field(gt=0)
    optimiser: AblationOptimiser
    token_budget: TokenBudget
    probe: AblationProbeConfig
    window_rule_per_arm: list[ArmWindowRule] = Field(min_length=1)
    window_index: AblationWindowIndex
    cost: AblationCost

    @model_validator(mode="after")
    def _arms_and_rules_agree(self) -> AblationArmsConfig:
        """Refuse a runner whose arm list and window rules disagree, or that retrains the reference.

        Raises:
            ValueError: If the reference arm is in the arm list, if the window rules do not cover
                the arms exactly, or if the cost does not match the runs asked for.
        """
        if self.reference_arm in self.arms:
            raise ValueError(
                f"{self.reference_arm} is the reference and is not retrained: {self.arms}"
            )
        ruled = [rule.arm for rule in self.window_rule_per_arm]
        if sorted(ruled) != sorted(self.arms):
            raise ValueError(f"window rules cover {ruled}, the arms are {self.arms}")
        runs = len(self.arms) * len(self.seeds)
        new_probes = sum(rule.random_init_probes for rule in self.window_rule_per_arm)
        if (self.cost.pretrainings, self.cost.ablation_probes) != (runs, runs):
            raise ValueError(
                f"{runs} arm-seeds ask for {runs} pretrainings and probes, the cost records "
                f"{self.cost.pretrainings} and {self.cost.ablation_probes}"
            )
        if self.cost.random_init_probes != new_probes:
            raise ValueError(
                f"the window rules ask for {new_probes} random-init probes, the cost records "
                f"{self.cost.random_init_probes}"
            )
        if self.cost.scorings != runs + new_probes:
            raise ValueError(
                f"{runs} ablation probes and {new_probes} random-init probes are "
                f"{runs + new_probes} scorings, the cost records {self.cost.scorings}"
            )
        return self

    @property
    def batch_windows(self) -> int:
        """Windows per forward pass while pretraining."""
        return self.optimiser.batch_windows

    def budget(self, context_tokens: int) -> Budget:
        """The pretraining window budget: the token target, rounded up to a whole step.

        Args:
            context_tokens: Tokens per window.

        Returns:
            The budget, identical to the one ``joint`` pretrained under.
        """
        per_step = self.optimiser.batch_windows * self.optimiser.accumulate
        steps = -(-self.tokens // (per_step * context_tokens))
        return Budget(
            windows=steps * per_step,
            batch_windows=self.optimiser.batch_windows,
            accumulate=self.optimiser.accumulate,
            learning_rate=self.optimiser.learning_rate,
            evaluations=self.optimiser.evaluations,
        )

    def window_rule(self, arm: str) -> ArmWindowRule:
        """One arm's window rule.

        Args:
            arm: The arm.

        Returns:
            Which stream its windows are framed over.

        Raises:
            KeyError: If no rule names that arm.
        """
        for rule in self.window_rule_per_arm:
            if rule.arm == arm:
                return rule
        raise KeyError(f"no window rule for {arm!r}: {[r.arm for r in self.window_rule_per_arm]}")


class RandomInitSource(StrictModel):
    """Per ablation, where its random-init (d) scores come from (ADR-0027 §4).

    A gate computed on different windows from the arm it gates is not a gate, so an arm that
    frames its own windows gets its own probes — on the *same* saved backbones, re-used rather
    than re-drawn, so the comparison is the windows and not the initialisation.

    Attributes:
        arm: The ablation gated.
        source: Where the three scores come from.
        new_probes: Probes trained for it.
        backbones_reused_from: The configuration constructing the backbones, when new probes run.
    """

    arm: str
    source: Literal["adr_0026_r_rand_d", "new_on_raw_windows"]
    new_probes: int = Field(ge=0)
    backbones_reused_from: str | None = None

    @model_validator(mode="after")
    def _source_matches_the_probes(self) -> RandomInitSource:
        """Refuse a source that does not match the probes it asks for.

        Raises:
            ValueError: If saved scores are claimed while probes are trained, or the reverse; or
                if new probes name no backbone construction.
        """
        saved = self.source == "adr_0026_r_rand_d"
        if saved != (self.new_probes == 0):
            raise ValueError(f"{self.arm}: source {self.source!r} with {self.new_probes} probes")
        if not saved and self.backbones_reused_from is None:
            raise ValueError(f"{self.arm}: new probes must name the backbones they re-use")
        return self


class InstrumentGate(StrictModel):
    """ADR-0027 §4's gate: computed first, per ablation, and it decides whether §5 is read at all.

    Attributes:
        readout: The read-out gated.
        reference_backbone: The untrained backbone family compared against.
        pairing: Which pairs are formed; ``same_and_cross_seed``.
        comparisons: How many paired lower bounds must clear the bound.
        lower_bound_above: The bound every paired lower bound must exceed.
        on_failure: The verdict for that ablation on FAIL; ``not_evaluable``.
        random_init_scores: Per ablation, where its random-init scores come from.
    """

    readout: Literal["last_plus_text"]
    reference_backbone: Literal["random_init"]
    pairing: Literal["same_and_cross_seed"]
    comparisons: int = Field(gt=0)
    lower_bound_above: float
    on_failure: Literal["not_evaluable"]
    random_init_scores: list[RandomInitSource] = Field(min_length=1)


class AblationComparison(StrictModel):
    """What each F8 difference compares (ADR-0027 §5).

    Attributes:
        arms: The ablations under test, one verdict each.
        reference: The arm every difference is taken against; ``joint``.
        reference_readout: The read-out the reference is read through; (d), not (a).
        pairing: How the two sides are paired; ``same_seed``.
        seeds: The seeds compared.
        checkpoint: The probe checkpoint read on both sides.
        windows: The window variant the verdict is read on; ``R0``.
    """

    arms: list[str] = Field(min_length=1)
    reference: str
    reference_readout: Literal["last_plus_text"]
    pairing: Literal["same_seed"]
    seeds: list[int] = Field(min_length=1)
    checkpoint: Literal["final_step"]
    windows: Literal["R0"]


class AblationRule(StrictModel):
    """ADR-0027 §5's four clauses, by value.

    Attributes:
        smallest_effect: The smallest AUPRC difference of interest, read from ``readout_v0``.
        hurts_upper_bound_below: Every paired upper bound must fall below this for HURTS.
        hurts_median_below: The median point difference must fall below this for HURTS.
        helps_lower_bound_above: Every paired lower bound must exceed this for HELPS.
        helps_median_above: The median point difference must exceed this for HELPS.
        equivalent_interval_within: Every paired interval must lie inside this for EQUIVALENT.
        otherwise: The verdict when no clause holds.
    """

    smallest_effect: float = Field(gt=0.0)
    hurts_upper_bound_below: float
    hurts_median_below: float
    helps_lower_bound_above: float
    helps_median_above: float
    equivalent_interval_within: tuple[float, float]
    otherwise: Literal["inconclusive"]

    @model_validator(mode="after")
    def _clauses_are_the_smallest_effect(self) -> AblationRule:
        """Refuse clauses that drift from the registered smallest effect of interest.

        Raises:
            ValueError: If either median threshold or the equivalence band is not the smallest
                effect of interest, signed; the three clauses are one number read four ways.
        """
        effect = self.smallest_effect
        if (self.hurts_median_below, self.helps_median_above) != (-effect, effect):
            raise ValueError(
                f"the median thresholds must be -/+{effect}, got "
                f"{self.hurts_median_below} and {self.helps_median_above}"
            )
        if self.equivalent_interval_within != (-effect, effect):
            raise ValueError(
                f"the equivalence band must be (-{effect}, +{effect}), got "
                f"{self.equivalent_interval_within}"
            )
        return self


class AblationSentence(StrictModel):
    """One write-up sentence an ablation is registered to decide (ADR-0027 §1).

    Attributes:
        arm: The ablation that decides it.
        sentence: The sentence, with its alternatives in brackets.
    """

    arm: str
    sentence: str

    @model_validator(mode="after")
    def _carries_its_brackets(self) -> AblationSentence:
        """Refuse a sentence that does not carry both alternatives.

        Raises:
            ValueError: If the bracketed alternative is missing, in which case the sentence was
                not written before the run in the form F8-3 strikes.
        """
        if "[" not in self.sentence or "]" not in self.sentence:
            raise ValueError(f"{self.arm}: the sentence carries no bracketed alternative")
        return self


class VerdictToSentence(StrictModel):
    """How each verdict of ADR-0027 §5 is written into its sentence.

    Attributes:
        hurts: What HURTS writes.
        equivalent: What EQUIVALENT writes.
        helps: What HELPS writes; neither bracket is struck.
        inconclusive: What INCONCLUSIVE writes; the sentence stays undecided.
        not_evaluable: What a gate FAIL writes; the sentence stays undecided.
    """

    hurts: Literal["does_matter"]
    equivalent: Literal["does_not_measurably"]
    helps: Literal["reported_as_measured_with_direction"]
    inconclusive: Literal["undecided"]
    not_evaluable: Literal["undecided"]


class StatusOnlyBag(StrictModel):
    """Control (ii)'s order-blind status-only classifier, reported beside each verdict (§6).

    Attributes:
        auprc: Its read on the 137,025 stride-12 test windows.
        interval: Its interval.
        fit_on: The convention its strings were written in when it was fit.
        refit_for_raw: Whether it is refit for the raw arm; it is not.
    """

    auprc: float = Field(gt=0.0)
    interval: tuple[float, float]
    fit_on: StatusConvention
    refit_for_raw: bool

    @model_validator(mode="after")
    def _reported_as_fit(self) -> StatusOnlyBag:
        """Refuse a refit comparator, and an interval that does not bracket the read.

        Raises:
            ValueError: If the comparator is refit for the raw arm, which ADR-0027 §6 forbids so
                that the row stays the one F6-1b measured; or if the interval excludes the read.
        """
        if self.refit_for_raw:
            raise ValueError("ADR-0027 §6 reports the comparator as-is and does not refit it")
        low, high = self.interval
        if not low <= self.auprc <= high:
            raise ValueError(f"{self.auprc} is not inside {self.interval}")
        return self


class AblationGateConfig(StrictModel):
    """Top level of ``configs/eval/ablation_gate_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        registered_in: ADR-0027's registration commit, or ``pending`` inside that commit.
        axis_config: The axis-gate configuration naming the temporal split.
        readout_config: Read-out (d), its protocol and the smallest effect of interest.
        runner_config: The F8-2 runs.
        mixture_config: The arms, by value.
        h1_gate_config: H1's rule, for the reported ``tel_only`` reference.
        label: The label scored.
        axis: The axis scored; ``temporal``.
        stride: The scored thinning.
        windows: Windows scored.
        positives: Positive windows scored.
        bootstrap: ADR-0021's interval, as ADR-0024 pairs it.
        readout: The read-out every side of every comparison is read through.
        instrument_gate: The gate computed first, per ablation.
        comparison: What each difference compares.
        rule: The four clauses.
        sentences: The write-up sentence each ablation decides.
        verdict_to_sentence: How each verdict is written into its sentence.
        reported: Comparisons reported beside the verdicts, deciding nothing.
        status_only_bag: The order-blind comparator, reported as F6-1b fit it.
        caveats: Caveats carried on every row.
        raw_only_caveat: The caveat carried in addition on every raw row.
    """

    version: int = 0
    registered_in: str
    axis_config: str
    readout_config: str
    runner_config: str
    mixture_config: str
    h1_gate_config: str
    label: str
    axis: Literal["temporal"]
    stride: int = Field(gt=0)
    windows: int = Field(gt=0)
    positives: int = Field(gt=0)
    bootstrap: BootstrapConfig
    readout: Literal["last_plus_text"]
    instrument_gate: InstrumentGate
    comparison: AblationComparison
    rule: AblationRule
    sentences: list[AblationSentence] = Field(min_length=1)
    verdict_to_sentence: VerdictToSentence
    reported: list[str] = Field(min_length=1)
    status_only_bag: StatusOnlyBag
    caveats: list[str] = Field(min_length=1)
    raw_only_caveat: str

    @model_validator(mode="after")
    def _every_arm_is_registered_once(self) -> AblationGateConfig:
        """Refuse an arm without a sentence, or a gate that does not cover every arm.

        Raises:
            ValueError: If the sentences, the gate's random-init sources and the compared arms are
                not the same set, since an arm decides exactly one sentence and passes its own
                gate before that sentence is read (§1, §4).
        """
        arms = sorted(self.comparison.arms)
        if sorted(s.arm for s in self.sentences) != arms:
            raise ValueError(
                f"one sentence per arm: {[s.arm for s in self.sentences]} against {arms}"
            )
        gated = sorted(s.arm for s in self.instrument_gate.random_init_scores)
        if gated != arms:
            raise ValueError(f"the instrument gate covers {gated}, the arms are {arms}")
        if self.readout != self.comparison.reference_readout != self.instrument_gate.readout:
            raise ValueError("every side of every comparison is read through the same read-out")
        return self

    def sentence(self, arm: str) -> str:
        """The write-up sentence one ablation decides.

        Args:
            arm: The ablation.

        Returns:
            The sentence, with its alternatives in brackets.

        Raises:
            KeyError: If no sentence is registered to that arm.
        """
        for registered in self.sentences:
            if registered.arm == arm:
                return registered.sentence
        raise KeyError(f"no sentence registered to {arm!r}: {[s.arm for s in self.sentences]}")
