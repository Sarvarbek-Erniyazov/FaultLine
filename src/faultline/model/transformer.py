"""The telemetry decoder: a causal transformer written from scratch (M1e).

One decoder-only stack over the joint vocabulary's fixed telemetry prefix. It is the
course deliverable and the representation the risk head reads, so it is written out here
rather than imported: the attention is the arithmetic, not a library call.

Four choices are worth the reader's attention, because they are not the defaults.

* **Learned absolute position embeddings, not rotary.** In the fixed-order stream position
  *is* identity: a step is 13 tokens -- ``<sep>`` then one bin token per core channel in
  canonical order -- so ``position mod 13`` names the channel, and no channel token is
  emitted (ADR-0003, M1b step 12). A learned absolute table can represent that directly.
  Rotary encodes relative offset, which is the right prior for language and the wrong one
  for a rigid frame whose absolute phase carries the schema.
* **The output head is tied to the token embedding.** The vocabulary is 1,184 identifiers
  of which 258 occur, so an untied head would spend more parameters on the vocabulary than
  some rungs of the ladder spend on the whole backbone.
* **Parameters are counted excluding embeddings**, which is what the ladder's axis is and
  what ``12 * n_layer * d_model ** 2`` approximates: 4 d^2 of attention and 8 d^2 of MLP
  per block. The embeddings are excluded because they scale with the vocabulary and the
  context, and the ladder holds both fixed.
* **Attention has two implementations that must agree.** The fused kernel is what the
  ladder runs; the explicit one -- scores, mask, softmax, weighted sum -- is what the
  reader checks it against, and a test asserts they match. Writing only the fused call
  would hide the one piece of arithmetic this milestone exists to demonstrate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from faultline.tokenizers.layout import TELEMETRY_PREFIX_SIZE


@dataclass(frozen=True)
class ModelSpec:
    """One rung of the size ladder.

    Attributes:
        name: The rung's label, ``S0`` to ``S3``.
        d_model: Residual width.
        n_layer: Number of blocks.
        n_head: Attention heads; must divide ``d_model``.
        context: Sequence length in tokens, held fixed across the ladder so that size is
            not confounded with context (it is a separate ablation).
        vocab_size: Identifiers the embedding covers.
        dropout: Dropout on attention output and MLP output.
    """

    name: str
    d_model: int
    n_layer: int
    n_head: int
    context: int
    vocab_size: int = TELEMETRY_PREFIX_SIZE
    dropout: float = 0.0

    def __post_init__(self) -> None:
        """Reject a rung the attention could not be built from.

        Raises:
            ValueError: If the width is not divisible by the head count, or any size is
                not positive.
        """
        if self.d_model % self.n_head:
            raise ValueError(
                f"{self.name}: d_model {self.d_model} is not divisible by n_head {self.n_head}"
            )
        for field, value in (
            ("d_model", self.d_model),
            ("n_layer", self.n_layer),
            ("n_head", self.n_head),
            ("context", self.context),
        ):
            if value <= 0:
                raise ValueError(f"{self.name}: {field} must be positive, got {value}")

    @property
    def backbone_params(self) -> int:
        """Parameters excluding embeddings, exactly as the ladder's axis counts them."""
        per_block = 4 * self.d_model**2 + 8 * self.d_model**2 + 2 * self.d_model
        return self.n_layer * per_block + self.d_model

    @property
    def nominal_params(self) -> int:
        """The ``12 * L * d^2`` the rung was chosen by, for the report to print beside."""
        return 12 * self.n_layer * self.d_model**2


class RMSNorm(nn.Module):
    """Root-mean-square layer norm, without the mean subtraction or the bias.

    Attributes:
        weight: Per-channel scale.
        eps: Added inside the square root.
    """

    def __init__(self, d_model: int, eps: float = 1e-5) -> None:
        """Build the norm.

        Args:
            d_model: Width to normalise over.
            eps: Numerical floor.
        """
        super().__init__()
        self.weight = nn.Parameter(torch.ones(d_model))
        self.eps = eps

    def forward(self, x: Tensor) -> Tensor:
        """Normalise the last dimension and rescale.

        Args:
            x: Input of shape ``(..., d_model)``.

        Returns:
            The normalised tensor, in the input's dtype.
        """
        normed = x.float() * torch.rsqrt(x.float().pow(2).mean(-1, keepdim=True) + self.eps)
        return (normed * self.weight.float()).type_as(x)


class CausalSelfAttention(nn.Module):
    """Multi-head causal self-attention.

    Attributes:
        n_head: Number of heads.
        d_head: Width of each head.
        qkv: Fused projection to queries, keys and values.
        proj: Output projection.
        dropout: Dropout applied to the output.
        fused: Whether to use the fused kernel; the explicit path is the reference.
    """

    def __init__(self, spec: ModelSpec, fused: bool = True) -> None:
        """Build the attention.

        Args:
            spec: The rung being built.
            fused: Use the fused scaled-dot-product kernel. The explicit implementation
                is always available through :meth:`explicit` and the two are asserted
                equal in the tests.
        """
        super().__init__()
        self.n_head = spec.n_head
        self.d_head = spec.d_model // spec.n_head
        self.qkv = nn.Linear(spec.d_model, 3 * spec.d_model, bias=False)
        self.proj = nn.Linear(spec.d_model, spec.d_model, bias=False)
        self.dropout = nn.Dropout(spec.dropout)
        self.fused = fused

    def _split(self, x: Tensor) -> tuple[Tensor, Tensor, Tensor]:
        """Project and reshape to ``(batch, head, time, d_head)``."""
        batch, time, _ = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        shape = (batch, time, self.n_head, self.d_head)
        return (t.view(shape).transpose(1, 2) for t in (q, k, v))  # type: ignore[return-value]

    def explicit(self, x: Tensor) -> Tensor:
        """Attention written out: scores, causal mask, softmax, weighted sum.

        This is the reference the fused path is checked against, and the arithmetic the
        milestone is meant to demonstrate. It materialises the ``time x time`` score
        matrix, so it is the slow path and is not what the ladder runs.

        Args:
            x: Input of shape ``(batch, time, d_model)``.

        Returns:
            The attention output, same shape.
        """
        q, k, v = self._split(x)
        scores = (q @ k.transpose(-2, -1)) / math.sqrt(self.d_head)
        time = x.shape[1]
        causal = torch.ones(time, time, dtype=torch.bool, device=x.device).tril()
        scores = scores.masked_fill(~causal, float("-inf"))
        out = F.softmax(scores.float(), dim=-1).type_as(v) @ v
        return self._merge(out, x)

    def _merge(self, out: Tensor, x: Tensor) -> Tensor:
        """Concatenate the heads and project back to the residual width."""
        batch, time, _ = x.shape
        merged = out.transpose(1, 2).contiguous().view(batch, time, -1)
        return cast(Tensor, self.dropout(self.proj(merged)))

    def forward(self, x: Tensor) -> Tensor:
        """Apply causal self-attention.

        Args:
            x: Input of shape ``(batch, time, d_model)``.

        Returns:
            The attention output, same shape.
        """
        if not self.fused:
            return self.explicit(x)
        q, k, v = self._split(x)
        out = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        return self._merge(out, x)


class MLP(nn.Module):
    """The position-wise feed-forward network: four-fold expansion, GELU, back down.

    Attributes:
        up: Expansion projection.
        down: Contraction projection.
        dropout: Dropout applied to the output.
    """

    def __init__(self, spec: ModelSpec) -> None:
        """Build the network.

        Args:
            spec: The rung being built.
        """
        super().__init__()
        self.up = nn.Linear(spec.d_model, 4 * spec.d_model, bias=False)
        self.down = nn.Linear(4 * spec.d_model, spec.d_model, bias=False)
        self.dropout = nn.Dropout(spec.dropout)

    def forward(self, x: Tensor) -> Tensor:
        """Expand, activate and contract.

        Args:
            x: Input of shape ``(..., d_model)``.

        Returns:
            The transformed tensor, same shape.
        """
        return cast(Tensor, self.dropout(self.down(F.gelu(self.up(x)))))


class Block(nn.Module):
    """One pre-norm transformer block: attention, then feed-forward, both residual.

    Attributes:
        norm_attention: Norm before the attention.
        attention: Causal self-attention.
        norm_mlp: Norm before the feed-forward network.
        mlp: The feed-forward network.
    """

    def __init__(self, spec: ModelSpec, fused: bool = True) -> None:
        """Build the block.

        Args:
            spec: The rung being built.
            fused: Passed to the attention.
        """
        super().__init__()
        self.norm_attention = RMSNorm(spec.d_model)
        self.attention = CausalSelfAttention(spec, fused=fused)
        self.norm_mlp = RMSNorm(spec.d_model)
        self.mlp = MLP(spec)

    def forward(self, x: Tensor) -> Tensor:
        """Apply the block.

        Args:
            x: Input of shape ``(batch, time, d_model)``.

        Returns:
            The block's output, same shape.
        """
        x = x + self.attention(self.norm_attention(x))
        return cast(Tensor, x + self.mlp(self.norm_mlp(x)))


class TelemetryDecoder(nn.Module):
    """The decoder-only backbone over telemetry tokens.

    Attributes:
        spec: The rung this instance is.
        tokens: Token embedding, tied to the output head.
        positions: Learned absolute position embedding.
        blocks: The transformer stack.
        norm: Final norm before the head.
    """

    def __init__(self, spec: ModelSpec, fused: bool = True) -> None:
        """Build the backbone.

        Args:
            spec: The rung to build.
            fused: Use the fused attention kernel.
        """
        super().__init__()
        self.spec = spec
        self.tokens = nn.Embedding(spec.vocab_size, spec.d_model)
        self.positions = nn.Embedding(spec.context, spec.d_model)
        self.drop = nn.Dropout(spec.dropout)
        self.blocks = nn.ModuleList(Block(spec, fused=fused) for _ in range(spec.n_layer))
        self.norm = RMSNorm(spec.d_model)
        self.apply(self._init)
        # The residual stream is written to twice a block, so the projections that write
        # into it are scaled down by the depth they accumulate over (GPT-2's rule).
        for name, parameter in self.named_parameters():
            if name.endswith(("proj.weight", "down.weight")):
                nn.init.normal_(parameter, mean=0.0, std=0.02 / math.sqrt(2 * spec.n_layer))

    @staticmethod
    def _init(module: nn.Module) -> None:
        """Initialise linear and embedding weights to the usual small normal."""
        if isinstance(module, nn.Linear | nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                nn.init.zeros_(module.bias)

    def parameter_counts(self) -> dict[str, int]:
        """Count the parameters, split the way the ladder reports them.

        Returns:
            ``backbone`` (everything but the two embedding tables), ``embeddings``,
            ``total``, and ``nominal``, the ``12 * L * d^2`` the rung was chosen by.
        """
        embeddings = self.tokens.weight.numel() + self.positions.weight.numel()
        total = sum(p.numel() for p in self.parameters())
        return {
            "backbone": total - embeddings,
            "embeddings": embeddings,
            "total": total,
            "nominal": self.spec.nominal_params,
        }

    def forward(self, tokens: Tensor) -> Tensor:
        """Run the stack and return the final hidden states.

        Args:
            tokens: Token identifiers of shape ``(batch, time)``, ``time`` at most the
                rung's context.

        Returns:
            Hidden states of shape ``(batch, time, d_model)``, normed.

        Raises:
            ValueError: If the sequence is longer than the context the positions cover.
        """
        _, time = tokens.shape
        if time > self.spec.context:
            raise ValueError(f"sequence of {time} tokens exceeds context {self.spec.context}")
        positions = torch.arange(time, device=tokens.device)
        x = self.drop(self.tokens(tokens) + self.positions(positions))
        for block in self.blocks:
            x = block(x)
        return cast(Tensor, self.norm(x))

    def logits(self, hidden: Tensor) -> Tensor:
        """Project hidden states onto the vocabulary through the tied embedding.

        Args:
            hidden: Hidden states of shape ``(batch, time, d_model)``.

        Returns:
            Logits of shape ``(batch, time, vocab_size)``.
        """
        return F.linear(hidden, self.tokens.weight)

    def loss(self, tokens: Tensor) -> Tensor:
        """Next-token cross entropy over a batch of windows.

        Every position predicts the next one, so a window of ``T`` tokens contributes
        ``T - 1`` predictions. No position is excluded: ``<nan>`` is a token the model is
        meant to predict, because missingness is itself a shift signal (ADR-0006).

        Args:
            tokens: Token identifiers of shape ``(batch, time)``.

        Returns:
            The mean cross entropy, a scalar.
        """
        hidden = self(tokens[:, :-1])
        logits = self.logits(hidden)
        # No explicit upcast: cross entropy is on autocast's float32 list and promotes
        # internally, and materialising a float32 copy of a (batch, time, vocab) tensor
        # is the single largest allocation a step would make.
        return F.cross_entropy(logits.reshape(-1, logits.shape[-1]), tokens[:, 1:].reshape(-1))
