# `faultline.deployment`

**Empty at M0 by design.**

## Interface contract (M3)

```python
def export_onnx(model: nn.Module, layout: VocabLayout, path: Path) -> Path: ...


class StreamingScorer:
    """Consumes 10-minute telemetry steps and emits a risk score or an abstention."""
```

The demonstration target is CPU streaming inference: one turbine, 10-minute steps,
scored as they arrive, on an ordinary laptop. Not because production would run that
way, but because it is the cheapest honest evidence that the model is small enough and
fast enough to be more than a training-time artefact.

Constraints:

- The exported graph includes the risk head and the abstention threshold. Shipping a
  backbone and reconstructing the decision rule by hand at inference is how a
  calibrated model quietly stops being calibrated.
- The export records the vocabulary layout and both tokenizer hashes. A model that
  cannot verify its own tokenizer will produce confident nonsense on a mismatch.
- Measured latency and memory go in the report. An unmeasured performance claim is not
  a claim.
