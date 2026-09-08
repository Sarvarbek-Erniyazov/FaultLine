# `faultline.model`

**Empty at M0 by design.** No model is defined in this repository yet, and the project
status line says so rather than implying otherwise.

## Interface contract (M1)

```python
class TelemetryDecoder(nn.Module):
    def forward(self, tokens: LongTensor, mask: BoolTensor | None) -> Logits: ...


class RiskHead(nn.Module):
    """Maps decoder states to P(event within horizon) and an abstention score."""
```

Three constraints that are decisions, not details:

1. **The vocabulary is fixed by `faultline.tokenizers.layout.VocabLayout`** (ADR-0003).
   The model reads block sizes from the layout; it never hardcodes an offset.
2. **The risk head is part of the model, not a post-hoc wrapper.** The endpoint is
   calibrated risk with abstention, so the component that produces it is specified and
   trained alongside the backbone.
3. **It must fit in 8 GB of VRAM with room for activations.** Width, depth and context
   length are budget decisions, and the config records what was tried and rejected.

## M3

The joint decoder is the same class over the concatenated vocabulary, plus the packing
rule for a text segment and a telemetry window in one sequence. If M3 turns out to need
a different architecture, that is an ADR, not a quiet edit.
