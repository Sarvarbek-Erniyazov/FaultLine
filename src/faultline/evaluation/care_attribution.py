"""ADR-0022's F6-0 addendum: two reported-only diagnostics that attribute the CARE null.

F5 found CARE at chance on every seed, farm and checkpoint. Two readings predict that equally: the
probe does not transfer across OEMs, or the CARE missing-channel pattern lies outside everything
the backbone was pretrained on. The addendum registers two diagnostics that separate them:

- **F6-0a, masking transfer.** The three ``tel_only`` final-step probes scored on the training-site
  temporal split with each CARE farm's absent core channels imposed as ``<nan>``.
- **F6-0b, bag of tokens on CARE.** The G2 comparator, unchanged, scored on the CARE stride-12 set.

**This module holds the configuration only.** It was written in the registration commit, before
any code that scores either diagnostic existed; that code is added only once the user has
authorised the run. ``configs/eval/care_attribution_v*.yaml`` is what it reads.
"""

from __future__ import annotations

from pydantic import Field

from faultline.config import StrictModel
from faultline.evaluation.gate_check import BootstrapConfig


class MaskingConfig(StrictModel):
    """F6-0a: each CARE farm's absent core channels, imposed on the temporal split.

    Attributes:
        axis: The split scored, ``temporal`` in the axis configuration.
        seed_replication_config: The F3 configuration naming the probes and their unmasked reads.
        windows: Windows at the registered stride.
        positives: Positive windows at that stride.
        base_rate: The scored set's own positive rate, to four decimals.
        seeds_required: Seeds of three on which either registered reading must hold.
        patterns: Per farm, the core channels emitted as ``<nan>`` on every step.
    """

    axis: str
    seed_replication_config: str
    windows: int = Field(gt=0)
    positives: int = Field(gt=0)
    base_rate: float = Field(gt=0.0, lt=1.0)
    seeds_required: int = Field(gt=0)
    patterns: dict[str, list[str]] = Field(min_length=1)


class BagOfTokensTransferConfig(StrictModel):
    """F6-0b: the G2 comparator, not refit, scored on the CARE evaluation set.

    Attributes:
        axis: The set scored, ``care`` in the axis configuration.
        config: The comparator's training configuration (ADR-0024 §6).
        refit: Whether the comparator is refit; registered false.
        windows: Windows at the registered stride.
        positives: Positive windows at that stride.
        base_rate: The scored set's own positive rate, to six decimals.
        per_farm: Whether per-farm rows are reported beside the pooled one.
    """

    axis: str
    config: str
    refit: bool
    windows: int = Field(gt=0)
    positives: int = Field(gt=0)
    base_rate: float = Field(gt=0.0, lt=1.0)
    per_farm: bool


class CareAttributionConfig(StrictModel):
    """Top level of ``configs/eval/care_attribution_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        registered_in: The addendum's registration commit, or ``pending`` inside that commit.
        axis_config: The axis-gate configuration in force.
        label: The label every probe is scored on.
        stride: The registered thinning.
        bootstrap: ADR-0021's interval, unchanged.
        checkpoint: The probe checkpoint read, under the ADR-0022 addendum rule.
        base_rate_source: Where every chance level comes from; ``scored_set``.
        seeds: The full-budget ``tel_only`` seeds.
        masking: F6-0a.
        bag_of_tokens: F6-0b.
    """

    version: int = 0
    registered_in: str
    axis_config: str
    label: str
    stride: int = Field(gt=0)
    bootstrap: BootstrapConfig
    checkpoint: str
    base_rate_source: str
    seeds: list[int] = Field(min_length=1)
    masking: MaskingConfig
    bag_of_tokens: BagOfTokensTransferConfig
