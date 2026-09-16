"""The M3 joint mixture: three stream types, declared arms, budgets in tokens seen (ADR-0018).

Three stream types, named here, in ``configs/train/joint_v*.yaml`` and in ADR-0018, and
nowhere given another name:

* ``tel`` -- telemetry windows, unpaired. The M1 fixed-order stream (``<sep>`` and one bin
  token a channel), byte for byte the M1 shards (verified, ADR-0003 note of 2026-09-16).
* ``txt`` -- narrative documents, unpaired. The M2 NRC and PHMSA text, at joint ids. It is
  nuclear and pipeline regulatory text and is **not paired with wind telemetry**.
* ``tel+status`` -- telemetry windows with their own status strings, the only genuinely
  paired cross-modal signal the project has. Each message is emitted as
  ``<txt> ... </txt>`` after the first step at or after its start. Strings are encoded
  **normalized** (H3', ADR-0017) by default; **raw** provider casing is a declared ablation.

**Budgets are in tokens seen, equal across arms.** GPU-hours are recorded as an observation
and never bound a run; this schema has no field for a wall-clock cap, so none can be set.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from faultline.config import StrictModel

#: The three stream types, in report order.
StreamName = Literal["tel", "txt", "tel+status"]
STREAMS: tuple[StreamName, ...] = ("tel", "txt", "tel+status")

#: How status strings are written in ``tel+status``.
StatusConvention = Literal["normalized", "raw"]

#: File-system spelling of a stream, since ``+`` is avoided in paths.
STREAM_DIRS: dict[StreamName, str] = {"tel": "tel", "txt": "txt", "tel+status": "tel_status"}


class Arm(StrictModel):
    """One pretraining arm: a mixture over the streams and a status convention.

    Attributes:
        name: The arm's label.
        role: What the arm is for: the default, an ablation, or a control.
        mixture: Share of the arm's tokens drawn from each stream; the shares sum to 1.
        status_convention: How ``tel+status`` strings are written in this arm.
    """

    name: str
    role: Literal["default", "ablation", "control"]
    mixture: dict[StreamName, float]
    status_convention: StatusConvention = "normalized"

    @model_validator(mode="after")
    def _shares(self) -> Arm:
        """Refuse a mixture that is not a distribution.

        Raises:
            ValueError: If a share is negative or the shares do not sum to 1.
        """
        if any(share < 0 for share in self.mixture.values()):
            raise ValueError(f"{self.name}: a mixture share is negative: {self.mixture}")
        if abs(sum(self.mixture.values()) - 1.0) > 1e-9:
            raise ValueError(f"{self.name}: mixture shares sum to {sum(self.mixture.values())}")
        return self

    def share(self, stream: StreamName) -> float:
        """The arm's share of one stream, zero where the stream is not listed."""
        return self.mixture.get(stream, 0.0)


class JointMixtureConfig(StrictModel):
    """Top level of ``configs/train/joint_v*.yaml``.

    Attributes:
        version: Version of this configuration.
        telemetry_tokenizer_config: The M1 quantile bin configuration (tokenizer, shards).
        text_shards_config: The M2 text shards configuration (tokenizer, shards).
        status_sources: Sources whose status streams are paired with their telemetry.
        training_sources: Sources whose train split the arms draw ``tel`` and
            ``tel+status`` from.
        context_tokens: Window length in tokens, the same for every stream.
        window_stride_steps: Telemetry windows start every this many steps.
        tokens_per_arm: Training tokens every arm sees. One number, so arms are equal.
        arms: The arms.
    """

    version: int = 0
    telemetry_tokenizer_config: str
    text_shards_config: str
    status_sources: list[str] = Field(min_length=1)
    training_sources: list[str] = Field(min_length=1)
    context_tokens: int = Field(gt=0)
    window_stride_steps: int = Field(gt=0)
    tokens_per_arm: int = Field(gt=0)
    arms: list[Arm] = Field(min_length=1)

    @model_validator(mode="after")
    def _readable(self) -> JointMixtureConfig:
        """Refuse arms that could not be compared.

        Raises:
            ValueError: If arm names repeat; there is not exactly one default arm; or a
                raw-convention ablation has no normalized twin with the same mixture, so
                the ablation would differ in more than the convention.
        """
        names = [arm.name for arm in self.arms]
        if len(set(names)) != len(names):
            raise ValueError(f"arm names repeat: {names}")
        defaults = [arm for arm in self.arms if arm.role == "default"]
        if len(defaults) != 1:
            raise ValueError(f"exactly one default arm is required, found {len(defaults)}")
        for arm in self.arms:
            if arm.status_convention != "raw":
                continue
            twins = [
                other
                for other in self.arms
                if other.status_convention == "normalized"
                and {s: other.share(s) for s in STREAMS} == {s: arm.share(s) for s in STREAMS}
            ]
            if not twins:
                raise ValueError(
                    f"{arm.name}: a raw-convention arm needs a normalized arm with the same "
                    "mixture, or it ablates more than the convention"
                )
        return self

    def stream_tokens(self, arm: Arm) -> dict[StreamName, int]:
        """Tokens an arm draws from each stream.

        Args:
            arm: The arm.

        Returns:
            Tokens per stream, summing to ``tokens_per_arm`` up to rounding.
        """
        return {stream: round(arm.share(stream) * self.tokens_per_arm) for stream in STREAMS}
