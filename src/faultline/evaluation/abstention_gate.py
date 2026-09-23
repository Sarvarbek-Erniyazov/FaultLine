"""ADR-0028: calibration, risk–coverage and H2 (graceful degradation under abstention).

ADR-0001 names calibrated abstention as the endpoint and no calibration or abstention result
exists. ADR-0028 registers one operating model per arm — the three-seed ensemble of prior-corrected
probabilities, with seed disagreement as its confidence — and fixes its operating point (τ, κ) on
the clean 2021 validation split before any test number is read (§1). Part A reads calibration and
risk–coverage on the saved clean test scores, with Gate A asking whether disagreement orders risk
better than chance (§2). Part B masks nested sets of core channels on ``joint`` (d)'s windows,
checks with Gate B that the ranking is damaged, and reads H2 at the strongest severity (§3).

**This module holds the configuration only.** It is written in the registration commit, before
any code that computes a risk–coverage curve or scores a masked or validation window exists
(ADR-0028 §5). It reads ``configs/eval/abstention_v*.yaml``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from faultline.config import StrictModel
from faultline.evaluation.gate_check import BootstrapConfig

#: The verdicts ADR-0028 §3's H2 rule names, with the two its prerequisites can force. Nothing
#: else may be written as a verdict.
H2_VERDICTS: frozenset[str] = frozenset(
    {"supported", "refuted", "inconclusive", "not_evaluable", "not_testable"}
)

#: The core channels in the telemetry step layout's order (quantile_bins_v2's manifest, ``step``
#: without ``<sep>``). The ladder's permutation is drawn over this order.
CORE_CHANNELS: tuple[str, ...] = (
    "wind_speed_ms",
    "power_pu",
    "rotor_speed_rpm",
    "generator_speed_rpm",
    "pitch_angle_deg",
    "nacelle_position_deg",
    "ambient_temp_c",
    "nacelle_temp_c",
    "gearbox_oil_temp_c",
    "generator_bearing_temp_c",
    "generator_winding_temp_c",
    "main_bearing_temp_c",
)


class SplitCounts(StrictModel):
    """One split's windows and positives (the F9 read-only check).

    Attributes:
        shard_keys: The shards the split is read from, where the record names them.
        windows: Windows at the scored stride.
        positives: Positive windows.
        base_rate: ``positives / windows``, to four places.
    """

    shard_keys: list[str] = Field(default_factory=list)
    windows: int = Field(gt=0)
    positives: int = Field(gt=0)
    base_rate: float = Field(gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _base_rate_is_the_counts(self) -> SplitCounts:
        """Refuse a base rate that is not the counts'.

        Raises:
            ValueError: If ``base_rate`` differs from ``positives / windows`` at four places.
        """
        if round(self.positives / self.windows, 4) != self.base_rate:
            raise ValueError(f"base rate {self.base_rate} is not {self.positives} / {self.windows}")
        return self


class Splits(StrictModel):
    """The test split scored and the validation split the operating point is fixed on.

    Attributes:
        test: The forward-in-time test split.
        validation: The 2021 validation split.
    """

    test: SplitCounts
    validation: SplitCounts


class AbstentionArm(StrictModel):
    """One arm whose three-seed ensemble is read (ADR-0028 §1).

    Attributes:
        name: The arm's name in this record.
        backbone: The pretrained backbone family.
        readout: The read-out its probes use.
        source: The registered run its saved test scores come from.
        test_scores: The saved clean test scores, with ``{seed}`` for the seed.
    """

    name: str
    backbone: Literal["tel_only", "joint"]
    readout: Literal["final_position", "last_plus_text"]
    source: str
    test_scores: str

    @model_validator(mode="after")
    def _one_file_per_seed(self) -> AbstentionArm:
        """Refuse a scores path that does not name the seed.

        Raises:
            ValueError: If ``test_scores`` has no ``{seed}`` placeholder.
        """
        if "{seed}" not in self.test_scores:
            raise ValueError(f"{self.name}: test_scores must carry a {{seed}} placeholder")
        return self


class OperatingModel(StrictModel):
    """The ensemble, its confidence and its operating point (ADR-0028 §1).

    Attributes:
        ensemble: How the seeds are combined.
        primary_signal: The confidence every gate and the rule read.
        secondary_signals: Confidences reported beside it, deciding nothing.
        disagreement_ddof: Degrees of freedom of the disagreement's standard deviation.
        operating_point_split: The split τ and κ are fixed on.
        tau_rule: How τ is chosen there.
        kappa_coverage: Clean validation coverage κ is set to give.
        abstain_when: The abstention rule.
        alarm_when: The alarm rule on covered windows.
        selective_risk: What selective risk counts.
        validation_scorings: Validation scorings F9-2 must run, since none exist in this form.
    """

    ensemble: Literal["mean_corrected_probability"]
    primary_signal: Literal["seed_disagreement"]
    secondary_signals: list[Literal["margin"]]
    disagreement_ddof: Literal[0]
    operating_point_split: Literal["validation"]
    tau_rule: Literal["max_f1"]
    kappa_coverage: float = Field(gt=0.0, lt=1.0)
    abstain_when: Literal["disagreement_above_kappa"]
    alarm_when: Literal["p_at_or_above_tau"]
    selective_risk: Literal["misclassification_rate_on_covered"]
    validation_scorings: int = Field(gt=0)


class CalibrationReport(StrictModel):
    """Part A's calibration rows: reported, no verdict (ADR-0028 §2).

    Attributes:
        ece_bins: Bins of the expected calibration error.
        binning: How the bins are cut.
        variants: The probabilities read.
        verdict: Whether any verdict is read from them; never.
        known_under_read: F3's ``tel_only`` corrected test means, stated before the run.
    """

    ece_bins: int = Field(gt=1)
    binning: Literal["equal_mass"]
    variants: list[Literal["prior_corrected", "platt_on_validation"]] = Field(min_length=1)
    verdict: Literal[False]
    known_under_read: list[float] = Field(min_length=1)


class RiskCoverage(StrictModel):
    """How the curve and its random reference are drawn (ADR-0028 §2).

    Attributes:
        ordering: The order windows are admitted in.
        random_orderings: Permutations the random-ordering AURC is averaged over.
        random_seed: Seed of those permutations.
    """

    ordering: Literal["disagreement_ascending"]
    random_orderings: int = Field(gt=0)
    random_seed: int


class GateA(StrictModel):
    """Gate A, the instrument, per arm (ADR-0028 §2).

    Attributes:
        statistic: The paired difference bootstrapped.
        upper_bound_below: PASS iff the 95% upper bound falls below this.
        on_failure: What abstention on that arm is on FAIL.
    """

    statistic: Literal["aurc_disagreement_minus_aurc_random"]
    upper_bound_below: float
    on_failure: Literal["not_evaluable"]


class SeverityLadder(StrictModel):
    """Part B's masking ladder on ``joint`` (d) (ADR-0028 §3).

    Attributes:
        arm: The arm masked.
        mechanism: How a channel is removed.
        text_kept: Whether the text stays in the window.
        split: The split scored under a mask.
        seed: Seed of the one permutation every set is read from.
        severities: Numbers of core channels masked.
        sets: The channels masked at each severity.
        test_scorings: Scorings the ladder costs.
        gpu_hours_estimate: The record's estimate, ladder and validation scorings together.
        launched_by: Who launches the GPU run.
    """

    arm: str
    mechanism: Literal["mask_to_nan_every_step"]
    text_kept: Literal[True]
    split: Literal["test"]
    seed: int
    severities: list[int] = Field(min_length=1)
    sets: dict[int, list[str]]
    test_scorings: int = Field(gt=0)
    gpu_hours_estimate: float = Field(gt=0.0)
    launched_by: Literal["author"]

    @model_validator(mode="after")
    def _sets_are_nested_core_channels(self) -> SeverityLadder:
        """Refuse sets that are not nested, sized by their severity, and drawn from the core.

        Raises:
            ValueError: If the severities are not increasing, a set's size is not its severity,
                a channel is not core or is listed twice, or a set does not contain the one below.
        """
        if self.severities != sorted(set(self.severities)) or sorted(self.sets) != self.severities:
            raise ValueError(f"severities {self.severities} and sets {sorted(self.sets)} differ")
        previous: set[str] = set()
        for k in self.severities:
            chosen = self.sets[k]
            if len(chosen) != k or len(set(chosen)) != k:
                raise ValueError(f"the set at k={k} holds {chosen}")
            stray = set(chosen) - set(CORE_CHANNELS)
            if stray:
                raise ValueError(f"{sorted(stray)} are not core channels")
            if not previous <= set(chosen):
                raise ValueError(f"the set at k={k} does not contain the set below it")
            previous = set(chosen)
        return self


class GateB(StrictModel):
    """Gate B, damage, computed before the H2 rule (ADR-0028 §3).

    Attributes:
        statistic: The paired difference bootstrapped.
        severity: The severity it is read at.
        upper_bound_below: Damage iff the 95% upper bound falls below this.
        on_failure: What H2 is without damage.
    """

    statistic: Literal["auprc_ensemble_k8_minus_clean"]
    severity: int = Field(gt=0)
    upper_bound_below: float
    on_failure: Literal["not_testable"]


class H2Rule(StrictModel):
    """ADR-0028 §3's H2 rule, by value.

    Attributes:
        arm: The arm H2 is read on.
        severity: The severity read against clean.
        operating_point: Which τ and κ are used; the clean validation ones, unchanged.
        smallest_effect_risk: The smallest selective-risk difference of interest, absolute.
        supported_cov_upper_below: SUPPORTED needs the Δcov upper bound below this.
        supported_risk_upper_below: SUPPORTED needs the Δrisk upper bound below this.
        refuted_cov_lower_at_or_above: REFUTED needs the Δcov lower bound at or above this.
        refuted_risk_lower_above: REFUTED needs the Δrisk lower bound above this.
        otherwise: The verdict when neither clause holds.
        requires: The gates that must pass before the rule is read.
    """

    arm: str
    severity: int = Field(gt=0)
    operating_point: Literal["clean_validation_unchanged"]
    smallest_effect_risk: float = Field(gt=0.0)
    supported_cov_upper_below: float
    supported_risk_upper_below: float
    refuted_cov_lower_at_or_above: float
    refuted_risk_lower_above: float
    otherwise: Literal["inconclusive"]
    requires: list[Literal["gate_a_pass_joint_d", "gate_b_damage"]] = Field(min_length=2)

    @model_validator(mode="after")
    def _supported_reads_the_smallest_effect(self) -> H2Rule:
        """Refuse a SUPPORTED bound that drifts from the registered smallest effect.

        Raises:
            ValueError: If ``supported_risk_upper_below`` is not ``smallest_effect_risk``.
        """
        if self.supported_risk_upper_below != self.smallest_effect_risk:
            raise ValueError(
                f"SUPPORTED reads Δrisk against {self.smallest_effect_risk}, "
                f"got {self.supported_risk_upper_below}"
            )
        return self


class AbstentionConfig(StrictModel):
    """Top level of ``configs/eval/abstention_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        registered_in: ADR-0028's registration commit, or ``pending`` inside that commit.
        axis_config: The axis-gate configuration naming the temporal split.
        readout_config: The read-outs and their runs.
        h1_gate_config: The (a) reads' runs.
        telemetry_manifest: The shard manifest whose step layout orders the core channels.
        label: The label scored.
        axis: The axis scored; ``temporal``.
        stride: The scored thinning.
        splits: Test and validation counts.
        bootstrap: ADR-0021's interval, as ADR-0024 pairs it.
        arms: The arms read.
        seeds: The seeds every ensemble averages.
        checkpoint: The probe checkpoint read.
        windows: The window variant read.
        prior_correction: The correction every logit carries.
        operating_model: The ensemble, its confidence and its operating point.
        calibration: Part A's calibration rows.
        risk_coverage: Part A's curve and its random reference.
        gate_a: Gate A.
        ladder: Part B's severity ladder.
        gate_b: Gate B.
        h2_rule: The H2 rule.
        reported: Rows reported beside the verdict, deciding nothing.
        caveats: Caveats carried on every row.
    """

    version: int = 0
    registered_in: str
    axis_config: str
    readout_config: str
    h1_gate_config: str
    telemetry_manifest: str
    label: str
    axis: Literal["temporal"]
    stride: int = Field(gt=0)
    splits: Splits
    bootstrap: BootstrapConfig
    arms: list[AbstentionArm] = Field(min_length=1)
    seeds: list[int] = Field(min_length=2)
    checkpoint: Literal["final_step"]
    windows: Literal["R0"]
    prior_correction: Literal["adr_0019"]
    operating_model: OperatingModel
    calibration: CalibrationReport
    risk_coverage: RiskCoverage
    gate_a: GateA
    ladder: SeverityLadder
    gate_b: GateB
    h2_rule: H2Rule
    reported: list[str] = Field(min_length=1)
    caveats: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _h2_is_read_where_the_ladder_is(self) -> AbstentionConfig:
        """Refuse a rule, a gate and a ladder that do not name the same arm and severity.

        Raises:
            ValueError: If the ladder's or the rule's arm is not an arm here, if Gate B and the
                rule read a severity other than the ladder's strongest, or if the scoring count
                is not severities × seeds.
        """
        names = {arm.name for arm in self.arms}
        if self.ladder.arm not in names or self.h2_rule.arm != self.ladder.arm:
            raise ValueError(f"ladder arm {self.ladder.arm}, rule arm {self.h2_rule.arm}")
        strongest = max(self.ladder.severities)
        if self.gate_b.severity != strongest or self.h2_rule.severity != strongest:
            raise ValueError(f"Gate B and the rule must read k={strongest}")
        if self.ladder.test_scorings != len(self.ladder.severities) * len(self.seeds):
            raise ValueError("the ladder scores every severity on every seed")
        return self

    def arm(self, name: str) -> AbstentionArm:
        """The arm called ``name``."""
        return next(a for a in self.arms if a.name == name)
