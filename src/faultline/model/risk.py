"""The risk head over the telemetry decoder (M1e).

The endpoint of M1 is a risk model, not a forecaster: given the last 144 steps, how likely
is a technical stop inside the next horizon. That is one scalar per window, and this is the
head that produces it.

**It reads the last position only.** The backbone is causal, so the final position is the
only one that has seen the whole window; it is also the only one that exists at inference
time in a streaming deployment, which M3 has to demonstrate. Mean-pooling over the window
would score better on a frozen probe and would not be deployable a step at a time, so the
cheaper number is declined here rather than reported and quietly walked back later.

**It is shallow on purpose.** Run (2) of the ladder freezes the backbone and trains only
this head, and that run is evidence about the *representation*: a head deep enough to solve
the task by itself would answer a different question. One hidden layer is the most that can
be called a probe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from faultline.model.transformer import ModelSpec, RMSNorm, TelemetryDecoder


@dataclass(frozen=True)
class RiskSpec:
    """How the head is built and what it is trained against.

    Attributes:
        hidden: Width of the head's single hidden layer, as a multiple of ``d_model``.
        dropout: Dropout before the output projection.
        label: The window-index column the head is trained on, for the record.
    """

    hidden: float = 1.0
    dropout: float = 0.0
    label: str = "narrow_within_24h"


class RiskHead(nn.Module):
    """A one-hidden-layer head mapping the last hidden state to a risk logit.

    Attributes:
        norm: Norm on the pooled state, so a frozen backbone's scale does not set the
            head's learning rate.
        up: Hidden projection.
        down: Output projection to a single logit.
        dropout: Dropout before the output projection.
    """

    def __init__(self, d_model: int, spec: RiskSpec) -> None:
        """Build the head.

        Args:
            d_model: Width of the backbone's residual stream.
            spec: The head's shape.
        """
        super().__init__()
        hidden = max(1, int(round(spec.hidden * d_model)))
        self.norm = RMSNorm(d_model)
        self.up = nn.Linear(d_model, hidden)
        self.dropout = nn.Dropout(spec.dropout)
        self.down = nn.Linear(hidden, 1)
        nn.init.normal_(self.up.weight, mean=0.0, std=0.02)
        nn.init.zeros_(self.up.bias)
        nn.init.normal_(self.down.weight, mean=0.0, std=0.02)
        nn.init.zeros_(self.down.bias)

    def forward(self, hidden: Tensor) -> Tensor:
        """Score one window.

        Args:
            hidden: The backbone's final hidden state at the last position, of shape
                ``(batch, d_model)``.

        Returns:
            One logit per window, of shape ``(batch,)``.
        """
        x = F.gelu(self.up(self.norm(hidden)))
        return cast(Tensor, self.down(self.dropout(x)).squeeze(-1))


class RiskModel(nn.Module):
    """The backbone and the risk head, as one module the training loop can own.

    Attributes:
        backbone: The telemetry decoder.
        head: The risk head.
        frozen: Whether the backbone's parameters are held fixed.
    """

    def __init__(self, spec: ModelSpec, risk: RiskSpec, frozen: bool, fused: bool = True) -> None:
        """Build the risk model.

        Args:
            spec: The rung to build.
            risk: The head's shape.
            frozen: Freeze the backbone, which is what makes run (2) a probe.
            fused: Use the fused attention kernel.
        """
        super().__init__()
        self.backbone = TelemetryDecoder(spec, fused=fused)
        self.head = RiskHead(spec.d_model, risk)
        self.frozen = frozen
        if frozen:
            for parameter in self.backbone.parameters():
                parameter.requires_grad_(False)

    def trainable_parameters(self) -> list[nn.Parameter]:
        """The parameters the optimiser is given, which is what ``frozen`` decides."""
        return [p for p in self.parameters() if p.requires_grad]

    def forward(self, tokens: Tensor) -> Tensor:
        """Score a batch of windows.

        Args:
            tokens: Token identifiers of shape ``(batch, time)``.

        Returns:
            One risk logit per window, of shape ``(batch,)``.
        """
        if self.frozen:
            with torch.no_grad():
                hidden = self.backbone(tokens)
            hidden = hidden.detach()
        else:
            hidden = self.backbone(tokens)
        return cast(Tensor, self.head(hidden[:, -1]))

    def loss(self, tokens: Tensor, labels: Tensor, positive_weight: float = 1.0) -> Tensor:
        """Binary cross entropy of the risk logits against the horizon labels.

        Args:
            tokens: Token identifiers of shape ``(batch, time)``.
            labels: Float labels of shape ``(batch,)``, 1 where the horizon holds an event.
            positive_weight: Weight on the positive class. The 24-hour narrow label runs
                at a base rate of a few per cent, so the default of 1.0 is stated rather
                than assumed: it is a config knob and the run config records it.

        Returns:
            The mean loss, a scalar.
        """
        logits = self(tokens).float()
        weight = torch.as_tensor(positive_weight, device=logits.device, dtype=logits.dtype)
        return F.binary_cross_entropy_with_logits(logits, labels.float(), pos_weight=weight)
