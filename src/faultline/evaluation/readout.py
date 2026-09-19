"""ADR-0026: F7', text-aware linear read-outs on the existing joint backbones.

H1 was read through a linear head on the hidden state at the window's last real position. Under
ADR-0025 §2's ``tail_anchored_2048`` rule that position is a telemetry bin token, never a text
token, and three measured rows say the read-out does not harvest the text signal the status
strings carry: the order-blind status-only classifier scores 0.0725 where every probe of either
arm sits between 0.050 and 0.060; the joint probe barely moves when the text enters the window;
and joint pretraining's gain is spent recovering the window change's cost. H1' asks whether the
backbone's representation holds that signal **elsewhere in the window**, read by ``mean_all`` and
``last_plus_text`` instead.

**The configuration is ADR-0026's registration commit; the selector below is F7'-1's.** The
registration commit held no code that builds, trains or scores a text-aware read-out (ADR-0026
§6). This module reads ``configs/eval/readout_v*.yaml`` — the read-out definitions, the four
runs, the H1' rule and the random-init gate on the instrument, all by value — and F7'-1 adds
:func:`risk_spec`, which turns one registered read-out **name** into the head specification the
risk model is built from. Nothing chooses a pooling by literal anywhere else: the name comes from
the configuration, the text positions come from the configuration, and the width the head reads
follows from both. The bootstrap is the gate run's, and the reference side of every H1' difference
is ADR-0025 §5's unchanged ``tel_only`` final-step read.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from faultline.config import StrictModel
from faultline.evaluation.gate_check import BootstrapConfig
from faultline.evaluation.h1_gate import SelectionSplit
from faultline.model.risk import RiskSpec, TextPositionRule

#: The read-outs ADR-0026 §2 registers, by name. Nothing else may be probed under this record.
READOUT_NAMES: frozenset[str] = frozenset({"final_position", "mean_all", "last_plus_text"})

#: What the risk head reads under each registered read-out (ADR-0026 §2). ``final_position`` is
#: the pooling in force, unchanged: a probe built through this map is the probe built before it.
READOUT_POOLING: dict[str, Literal["last", "mean", "last_plus_text"]] = {
    "final_position": "last",
    "mean_all": "mean",
    "last_plus_text": "last_plus_text",
}

#: Hidden layers in the head under every read-out. ADR-0026 §2: these are linear read-outs over a
#: frozen representation, and ADR-0023 §c's deeper head "would answer a different question".
READOUT_HEAD_LAYERS: Literal[1, 2] = 1

#: Backbone blocks that train under every read-out: none. The backbones are read frozen (§3).
READOUT_UNFROZEN_BLOCKS = 0


class ProbeProtocol(StrictModel):
    """What every read-out's probe shares (ADR-0026 §2); only the pooling differs.

    Attributes:
        cadence_config: G3's evaluation cadence.
        checkpoint: The probe checkpoint read; ``final_step`` under ADR-0022's addendum.
        window_rule: ADR-0025 §2's registered window rule, by name.
        context_tokens: The padded window length.
        status_rows: Which status rows the window holds; ``all`` is R0.
        sampling: The probe's sampler; ``balanced``.
        head_hidden: The head's hidden width as a multiple of ``d_model``, the width in force.
        learning_rate: The §a probe's own rate, from the ladder's probe stage.
        train_stride: Steps between the probe's training windows, the ladder's.
        selection: The probes' selection split, drawn as F3 drew it.
    """

    cadence_config: str
    checkpoint: Literal["final_step"]
    window_rule: Literal["tail_anchored_2048"]
    context_tokens: int = Field(gt=0)
    status_rows: Literal["all"]
    sampling: Literal["balanced"]
    head_hidden: float = Field(gt=0.0)
    learning_rate: float = Field(gt=0.0)
    train_stride: int = Field(gt=0)
    selection: SelectionSplit


class TextPositions(StrictModel):
    """What counts as a text-token position for ``last_plus_text`` (ADR-0026 §2).

    Attributes:
        special_ids: The structural markers ``<txt>`` and ``</txt>``.
        min_id: The first identifier of the joint layout's text block (ADR-0003).
        empty_window: What a window holding no text position contributes; ``zero_vector``.
    """

    special_ids: list[int] = Field(min_length=1)
    min_id: int = Field(gt=0)
    empty_window: Literal["zero_vector"]


class Readout(StrictModel):
    """One read-out, by name and definition (ADR-0026 §2).

    Attributes:
        name: The registered name.
        pooling: What the head reads, by name.
        d_model_blocks: Blocks of ``d_model`` values in the head's input.
        scalars: Scalar features appended to those blocks, such as the has-text indicator.
        text_block: Whether the input holds a mean over the text-token positions.
        in_force: Whether this is the probe already in force, which is not re-run.
    """

    name: Literal["final_position", "mean_all", "last_plus_text"]
    pooling: Literal["last_real", "mean_real", "last_real_plus_text_mean"]
    d_model_blocks: int = Field(gt=0)
    scalars: int = Field(ge=0)
    text_block: bool
    in_force: bool = False

    def head_input_width(self, d_model: int) -> int:
        """The head's input width at a given residual width."""
        return self.d_model_blocks * d_model + self.scalars


class ReadoutRun(StrictModel):
    """One of ADR-0026 §3's four runs: a read-out on a family of saved backbones.

    Attributes:
        name: The run's registered name.
        readout: The read-out probed, by name.
        backbone: The backbone family read frozen; nothing here is pretrained.
        seeds: The pretraining or initialisation seeds probed.
    """

    name: str
    readout: Literal["final_position", "mean_all", "last_plus_text"]
    backbone: Literal["joint", "tel_only", "random_init"]
    seeds: list[int] = Field(min_length=1)


class ReadoutRule(StrictModel):
    """ADR-0026 §4's H1' rule, by value.

    Attributes:
        arm_readout: The read-out on the arm under test.
        arm_backbone: The backbone under test.
        reference_readout: The read-out on the reference side, ADR-0025 §5's unchanged.
        reference_backbone: The reference arm.
        pairing: How the two sides are paired; ``same_seed``.
        seeds: The seeds compared.
        checkpoint: The probe checkpoint read on both sides.
        windows: The window variant the verdict is read on; ``R0``.
        smallest_effect: The smallest AUPRC difference of interest.
        supported_lower_bound_above: Every paired lower bound must exceed this for SUPPORTED.
        supported_median_above: The median point difference must exceed this for SUPPORTED.
        refuted_upper_bound_below: Every paired upper bound must fall below this for REFUTED.
        otherwise: The verdict when neither holds.
    """

    arm_readout: Literal["last_plus_text"]
    arm_backbone: Literal["joint"]
    reference_readout: Literal["final_position"]
    reference_backbone: Literal["tel_only"]
    pairing: Literal["same_seed"]
    seeds: list[int] = Field(min_length=1)
    checkpoint: Literal["final_step"]
    windows: Literal["R0"]
    smallest_effect: float = Field(gt=0.0)
    supported_lower_bound_above: float
    supported_median_above: float
    refuted_upper_bound_below: float
    otherwise: Literal["inconclusive"]


class RandomInitGate(StrictModel):
    """ADR-0026 §4's gate on the instrument: must pass for H1' to be read at all.

    Attributes:
        readout: The read-out gated.
        arm_backbone: The trained backbone that must come out above.
        reference_backbone: The untrained backbone family compared against.
        pairing: Which pairs are formed; ``same_and_cross_seed``.
        comparisons: How many paired lower bounds must clear the bound.
        lower_bound_above: The bound every paired lower bound must exceed.
        on_failure: The verdict on FAIL; ``not_evaluable``.
    """

    readout: Literal["last_plus_text"]
    arm_backbone: Literal["joint"]
    reference_backbone: Literal["random_init"]
    pairing: Literal["same_and_cross_seed"]
    comparisons: int = Field(gt=0)
    lower_bound_above: float
    on_failure: Literal["not_evaluable"]


class ReadoutConfig(StrictModel):
    """Top level of ``configs/eval/readout_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        registered_in: ADR-0026's registration commit, or ``pending`` inside that commit.
        axis_config: The axis-gate configuration naming the temporal split.
        h1_gate_config: H1's rule, whose reference side H1' keeps unchanged.
        arms_config: The joint backbones, their probe and its windows.
        random_init_config: ADR-0023's random-init construction, re-used unchanged.
        ladder_config: The probe stage's recipe.
        model_config_path: The model ladder, holding the head's hidden width.
        label: The label scored.
        axis: The axis scored; ``temporal``.
        stride: The scored thinning.
        windows: Windows scored.
        positives: Positive windows scored.
        bootstrap: ADR-0021's interval, as ADR-0024 pairs it.
        probe: The protocol every read-out's probe shares.
        text_positions: What counts as a text-token position.
        readouts: The read-outs registered by name and definition.
        runs: The runs of ADR-0026 §3.
        rule: The H1' rule.
        random_init_gate: The gate on the instrument.
        reported: Comparisons reported beside the verdict, deciding nothing.
        caveats: Caveats carried on every row.
    """

    version: int = 0
    registered_in: str
    axis_config: str
    h1_gate_config: str
    arms_config: str
    random_init_config: str
    ladder_config: str
    model_config_path: str
    label: str
    axis: Literal["temporal"]
    stride: int = Field(gt=0)
    windows: int = Field(gt=0)
    positives: int = Field(gt=0)
    bootstrap: BootstrapConfig
    probe: ProbeProtocol
    text_positions: TextPositions
    readouts: list[Readout] = Field(min_length=1)
    runs: list[ReadoutRun] = Field(min_length=1)
    rule: ReadoutRule
    random_init_gate: RandomInitGate
    reported: list[str] = Field(min_length=1)
    caveats: list[str] = Field(min_length=1)

    @property
    def readout_names(self) -> set[str]:
        """The registered read-out names."""
        return {readout.name for readout in self.readouts}

    def readout(self, name: str) -> Readout:
        """One read-out by name.

        Args:
            name: The registered name.

        Returns:
            The read-out's definition.

        Raises:
            KeyError: If no read-out carries that name.
        """
        for readout in self.readouts:
            if readout.name == name:
                return readout
        raise KeyError(f"no read-out named {name!r}: {sorted(self.readout_names)}")

    @property
    def probes(self) -> int:
        """Probes the runs ask for: one per seed of each run, and one scoring each."""
        return sum(len(run.seeds) for run in self.runs)


def risk_spec(
    config: ReadoutConfig, name: str, head_hidden: float, head_dropout: float, label: str
) -> RiskSpec:
    """The head specification one registered read-out is probed through.

    This is the only place a read-out name becomes a pooling. The text positions are attached
    for ``last_plus_text`` alone, from the configuration's ``text_positions``, and the width the
    head will read is checked against the width the configuration declares for that read-out
    (``d_model_blocks`` and ``scalars``), so the record and the module cannot drift apart.

    Args:
        config: The loaded read-out configuration.
        name: A registered read-out name.
        head_hidden: The head's hidden width as a multiple of ``d_model`` (the ladder's).
        head_dropout: The head's dropout (the ladder's).
        label: The label the head is trained on.

    Returns:
        The head specification.

    Raises:
        KeyError: If no read-out carries that name.
    """
    readout = config.readout(name)
    pooling = READOUT_POOLING[readout.name]
    positions = None
    if readout.text_block:
        positions = TextPositionRule(
            special_ids=tuple(config.text_positions.special_ids),
            min_id=config.text_positions.min_id,
        )
    spec = RiskSpec(
        hidden=head_hidden,
        dropout=head_dropout,
        label=label,
        pooling=pooling,
        layers=READOUT_HEAD_LAYERS,
        text_positions=positions,
    )
    _check_width(readout, spec)
    return spec


def _check_width(readout: Readout, spec: RiskSpec) -> None:
    """Refuse a read-out whose head width is not the one the configuration registers.

    Args:
        readout: The registered read-out.
        spec: The head specification built from it.

    Raises:
        ValueError: If the two widths disagree at any residual width.
    """
    for d_model in (1, 192):
        declared, built = readout.head_input_width(d_model), spec.input_width(d_model)
        if declared != built:
            raise ValueError(
                f"{readout.name}: the configuration registers a head input of {declared} at "
                f"d_model {d_model} ({readout.d_model_blocks} blocks + {readout.scalars} "
                f"scalars), the read-out builds {built}"
            )
