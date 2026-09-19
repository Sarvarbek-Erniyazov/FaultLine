"""The risk head over the telemetry decoder (M1e).

The endpoint of M1 is a risk model, not a forecaster: given the last 144 steps, how likely
is a technical stop inside the next horizon. That is one scalar per window, and this is the
head that produces it.

**It reads the last position only.** The backbone is causal, so the final position is the
only one that has seen the whole window; it is also the only one that exists at inference
time in a streaming deployment, which M3 has to demonstrate. Mean-pooling over the window
would score better on a frozen probe and would not be deployable a step at a time, so the
cheaper number is declined here rather than reported and quietly walked back later.

**ADR-0026 adds two read-outs beside it, for a frozen probe only.** H1 was read through the
last real position, which under ADR-0025 §2's window is always a telemetry bin token, and three
measured rows say that read-out does not harvest the status text's signal. ``mean_all`` and
``last_plus_text`` ask whether the representation holds it elsewhere in the window. They are
read-outs over a frozen backbone under a pre-registered rule, not a change of deployment
target: the streaming argument above still governs what M3 ships, and ``final_position``
remains the probe in force.

**It is shallow on purpose.** Run (2) of the ladder freezes the backbone and trains only
this head, and that run is evidence about the *representation*: a head deep enough to solve
the task by itself would answer a different question. One hidden layer is the most that can
be called a probe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, cast

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from faultline.model.transformer import ModelSpec, RMSNorm, TelemetryDecoder


@dataclass(frozen=True)
class TextPositionRule:
    """Which positions of a window carry text, for the ``last_plus_text`` read-out (ADR-0026 §2).

    A position is a text-token position when its input id is one of the structural markers or
    sits in the joint layout's text block. The values come from ``configs/eval/readout_v0.yaml``
    (``text_positions``), never from a literal here: this is the shape the model reads them in.

    Attributes:
        special_ids: The structural markers, ``<txt>`` and ``</txt>``.
        min_id: The first id of the text block; every id at or above it is text.
    """

    special_ids: tuple[int, ...]
    min_id: int

    def mask(self, tokens: Tensor) -> Tensor:
        """Which positions of ``tokens`` are text-token positions.

        Args:
            tokens: Token identifiers of shape ``(batch, time)``.

        Returns:
            A boolean tensor of the same shape.
        """
        is_text = tokens >= self.min_id
        for special in self.special_ids:
            is_text = is_text | (tokens == special)
        return is_text


@dataclass(frozen=True)
class RiskSpec:
    """How the head is built and what it is trained against.

    Attributes:
        hidden: Width of the head's single hidden layer, as a multiple of ``d_model``.
        dropout: Dropout before the output projection.
        label: The window-index column the head is trained on, for the record.
        pooling: What the head reads: the final position's hidden state (``last``, every probe
            before ADR-0023 §b, ADR-0026's ``final_position``), the mean over every real position
            of the window (``mean``, §b, ADR-0026's ``mean_all``), or ADR-0026 (d)'s three blocks
            (``last_plus_text``).
        layers: Hidden layers in the head: one for every probe before ADR-0023 §c, two for §c.
        text_positions: What counts as a text-token position; required by ``last_plus_text`` and
            unused by the other read-outs.
    """

    hidden: float = 1.0
    dropout: float = 0.0
    label: str = "narrow_within_24h"
    pooling: Literal["last", "mean", "last_plus_text"] = "last"
    layers: Literal[1, 2] = 1
    text_positions: TextPositionRule | None = None

    def input_width(self, d_model: int) -> int:
        """The head's input width at a given residual width.

        ``last_plus_text`` concatenates the last real state, the mean over the text-token
        positions and the has-text indicator, so its head reads ``2 * d_model + 1`` values
        (ADR-0026 §2). Every other read-out reads ``d_model``.

        Args:
            d_model: Width of the backbone's residual stream.

        Returns:
            The width the head's first projection takes.
        """
        return 2 * d_model + 1 if self.pooling == "last_plus_text" else d_model


class RiskHead(nn.Module):
    """A one-hidden-layer head mapping the pooled state to a risk logit.

    The head is the one in force under every read-out: the same norm, the same single hidden
    layer at ``hidden * d_model``, the same output projection. Only its *input width* follows
    the read-out (``RiskSpec.input_width``), and the norm is taken over that whole input, so
    ``final_position`` builds exactly the module it built before ADR-0026, parameter for
    parameter and random number for random number.

    Attributes:
        norm: Norm on the pooled state, so a frozen backbone's scale does not set the
            head's learning rate.
        up: Hidden projection.
        mid: A second hidden projection, present only for a two-hidden-layer head (§c).
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
        width = spec.input_width(d_model)
        self.norm = RMSNorm(width)
        self.up = nn.Linear(width, hidden)
        self.dropout = nn.Dropout(spec.dropout)
        self.down = nn.Linear(hidden, 1)
        nn.init.normal_(self.up.weight, mean=0.0, std=0.02)
        nn.init.zeros_(self.up.bias)
        nn.init.normal_(self.down.weight, mean=0.0, std=0.02)
        nn.init.zeros_(self.down.bias)
        # Built last and only when asked for, so a one-hidden-layer head draws exactly the random
        # numbers, and holds exactly the state, that it did before ADR-0023 §c.
        self.mid: nn.Linear | None = None
        if spec.layers == 2:
            self.mid = nn.Linear(hidden, hidden)
            nn.init.normal_(self.mid.weight, mean=0.0, std=0.02)
            nn.init.zeros_(self.mid.bias)

    def forward(self, hidden: Tensor) -> Tensor:
        """Score one window.

        Args:
            hidden: The pooled state the read-out produces, of shape
                ``(batch, spec.input_width(d_model))``.

        Returns:
            One logit per window, of shape ``(batch,)``.
        """
        x = F.gelu(self.up(self.norm(hidden)))
        if self.mid is not None:
            x = F.gelu(self.mid(x))
        return cast(Tensor, self.down(self.dropout(x)).squeeze(-1))


class RiskModel(nn.Module):
    """The backbone and the risk head, as one module the training loop can own.

    Attributes:
        backbone: The telemetry decoder.
        head: The risk head.
        frozen: Whether the backbone's parameters are held fixed.
        pooling: What the head reads, from the head's specification.
        text_positions: What counts as a text-token position, for ``last_plus_text``.
        unfrozen_blocks: Blocks at the end of a frozen backbone that train anyway (ADR-0023 §d).
        backbone_lr_scale: The unfrozen blocks' learning rate as a fraction of the head's.
        pad_id: The padding id of right-padded windows (ADR-0025 §2), or ``None`` for windows
            that are never padded, whose last position is read as before.
    """

    def __init__(
        self,
        spec: ModelSpec,
        risk: RiskSpec,
        frozen: bool,
        fused: bool = True,
        unfrozen_blocks: int = 0,
        backbone_lr_scale: float = 1.0,
        pad_id: int | None = None,
    ) -> None:
        """Build the risk model.

        Args:
            spec: The rung to build.
            risk: The head's shape.
            frozen: Freeze the backbone, which is what makes run (2) a probe.
            fused: Use the fused attention kernel.
            unfrozen_blocks: With ``frozen``, this many final blocks train anyway (ADR-0023 §d).
            backbone_lr_scale: Those blocks' learning rate as a fraction of the run's.
            pad_id: The padding id of right-padded windows; ``None`` when windows are never
                padded.

        Raises:
            ValueError: If blocks are unfrozen in an unfrozen model, or more than exist, or
                the ``last_plus_text`` read-out is asked for without its text positions.
        """
        super().__init__()
        self.backbone = TelemetryDecoder(spec, fused=fused)
        self.head = RiskHead(spec.d_model, risk)
        self.frozen = frozen
        self.pooling = risk.pooling
        self.text_positions = risk.text_positions
        if self.pooling == "last_plus_text" and self.text_positions is None:
            raise ValueError("the last_plus_text read-out needs its text positions (ADR-0026 §2)")
        if unfrozen_blocks and not frozen:
            raise ValueError("unfrozen_blocks applies to a frozen backbone only")
        if not 0 <= unfrozen_blocks <= spec.n_layer:
            raise ValueError(f"unfrozen_blocks must be in 0..{spec.n_layer}, got {unfrozen_blocks}")
        self.unfrozen_blocks = unfrozen_blocks
        self.backbone_lr_scale = backbone_lr_scale
        self.pad_id = pad_id
        if frozen:
            for parameter in self.backbone.parameters():
                parameter.requires_grad_(False)
            for block in self.backbone.blocks[spec.n_layer - unfrozen_blocks :]:
                for parameter in block.parameters():
                    parameter.requires_grad_(True)

    def parameter_lr_scale(self, name: str) -> float:
        """The learning-rate multiple of one named parameter: the unfrozen blocks' scale, or 1."""
        first = self.backbone.spec.n_layer - self.unfrozen_blocks
        if self.unfrozen_blocks and name.startswith("backbone.blocks."):
            if int(name.split(".")[2]) >= first:
                return self.backbone_lr_scale
        return 1.0

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
        return cast(Tensor, self.head(self.pool(tokens)))

    def pool(self, tokens: Tensor) -> Tensor:
        """The state the head reads: the backbone run over the windows, then pooled.

        Args:
            tokens: Token identifiers of shape ``(batch, time)``, right-padded with ``pad_id``
                when it is set.

        Returns:
            One pooled state per window, of shape ``(batch, width)``, where ``width`` is the
            read-out's input width: ``d_model``, or ``2 * d_model + 1`` for ``last_plus_text``.
        """
        if self.frozen and self.unfrozen_blocks:
            hidden = self.backbone.forward_with_trainable_tail(tokens, self.unfrozen_blocks)
        elif self.frozen:
            with torch.no_grad():
                hidden = self.backbone(tokens)
            hidden = hidden.detach()
        else:
            hidden = self.backbone(tokens)
        if self.pooling == "last_plus_text":
            return self._last_plus_text(hidden, tokens)
        if self.pad_id is None:
            pooled = hidden.mean(dim=1) if self.pooling == "mean" else hidden[:, -1]
        else:
            # Right-padded windows (ADR-0025 §2): attention is causal, so no real position sees a
            # pad, and the head reads the last real position (or the mean over real ones).
            real = tokens != self.pad_id
            if self.pooling == "mean":
                weights = real.to(hidden.dtype).unsqueeze(-1)
                pooled = (hidden * weights).sum(dim=1) / weights.sum(dim=1).clamp(min=1.0)
            else:
                last = real.sum(dim=1).clamp(min=1) - 1
                pooled = hidden[torch.arange(hidden.shape[0], device=hidden.device), last]
        return pooled

    def _real(self, tokens: Tensor) -> Tensor:
        """Which positions of a window are real: everything, when the windows carry no pad."""
        if self.pad_id is None:
            return torch.ones_like(tokens, dtype=torch.bool)
        return tokens != self.pad_id

    def _last_plus_text(self, hidden: Tensor, tokens: Tensor) -> Tensor:
        """ADR-0026 (d): the last real state, the text-position mean, and the has-text scalar.

        The three blocks are concatenated in that order. The second is the mean of ``hidden``
        over exactly the window's text-token positions, and the **zero vector** where the window
        holds none; the third is 1.0 where it holds at least one and 0.0 otherwise. On a window
        with no text the read-out is therefore the ``last`` read-out plus a constant, so it is
        never worse-posed than the probe in force on the status-empty windows.

        Args:
            hidden: The backbone's final hidden states, of shape ``(batch, time, d_model)``.
            tokens: The windows' token identifiers, of shape ``(batch, time)``.

        Returns:
            The head's input, of shape ``(batch, 2 * d_model + 1)``.

        Raises:
            ValueError: If the text positions are not set.
        """
        if self.text_positions is None:  # pragma: no cover - refused in __init__
            raise ValueError("the last_plus_text read-out needs its text positions")
        real = self._real(tokens)
        last = real.sum(dim=1).clamp(min=1) - 1
        final = hidden[torch.arange(hidden.shape[0], device=hidden.device), last]
        # A pad is never a text id, but the mask is intersected with the real positions anyway,
        # so the block is defined by the window's real content alone.
        text = self.text_positions.mask(tokens) & real
        weights = text.to(hidden.dtype).unsqueeze(-1)
        count = weights.sum(dim=1)
        mean = (hidden * weights).sum(dim=1) / count.clamp(min=1.0)
        return torch.cat([final, mean, (count > 0).to(hidden.dtype)], dim=-1)

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


def prior_correction(train_rate: float, natural_rate: float) -> float:
    """The logit offset that maps a score trained at one base rate back to another.

    A head trained on batches that are ``train_rate`` positive learns that prior. Under
    the usual label-shift assumption (the windows given a label are the same, only the mix
    changes), adding ``logit(natural_rate) - logit(train_rate)`` to its logits gives the
    score a head trained at ``natural_rate`` would give. The offset is one constant, so
    any ranking metric, AUPRC included, is unchanged by it. Loss and calibration are not.

    Args:
        train_rate: The positive share of the training batches.
        natural_rate: The positive share the scores are to be read at.

    Returns:
        The offset to add to every logit.

    Raises:
        ValueError: If either rate is not strictly between 0 and 1.
    """
    for name, rate in (("train_rate", train_rate), ("natural_rate", natural_rate)):
        if not 0.0 < rate < 1.0:
            raise ValueError(f"{name} must be strictly between 0 and 1, got {rate}")

    def logit(rate: float) -> float:
        return math.log(rate / (1.0 - rate))

    return logit(natural_rate) - logit(train_rate)
