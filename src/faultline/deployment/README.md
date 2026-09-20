# `faultline.deployment`

**Empty at M0 by design.** `stream.py` is the first thing in it: a CPU streaming trace
over one held-out turbine-year, written at the end of the programme as a demonstration.

## What is here now

`stream.py` runs the path end to end -- backbone, frozen probe, prior-corrected
probability, one window after another in time order -- over real forward-in-time data, and
writes a CSV, an SVG and a report under `reports/data/`. It is a demonstration, not an
evaluation: it registers no rule, decides nothing, and adds no number to the record. It
calls the evaluation package's own correction and bootstrap rather than re-deriving
either.

## Which turbine-year, and why two of them

A demonstration chooses its example, and choosing it badly is how a demonstration quietly
becomes a claim. `selection.py` holds the two rules that choose it, both written down
before any score was looked at, and both read labels only:

| rule | criterion | what it selects for |
| --- | --- | --- |
| most events | the turbine with the most labelled narrow event starts in the year | the densest turbine-year the site has, which is an atypical one by construction |
| typical event rate | the turbine whose positive-window rate in the year is closest to the pooled test base rate | the turbine-year least unlike the pooled test split the gates were read on |

Ties go to the lowest turbine id. `faultline model stream-trace` runs both by default and
writes both reports from the same pass, so the two agree with each other; each report and
`reports/data/figures_index.md` state both rules side by side. Two examples chosen under
two rules are not a sample, and neither trace is an evaluation result.

The figure draws two labelled reference lines, the pooled test base rate and the
turbine-year's own positive rate, because an AUPRC only means anything against the base
rate it was measured on, and the two differ here by a large factor. Each report says
plainly whether the turbine-year's interval clears or contains its own positive rate.

It meets the second and third constraints below and deliberately does not meet the first:
**it draws and computes no abstention threshold.** The contract sketched at M0 assumed the
programme would earn an operating point. It did not -- ADR-0025 closed INCONCLUSIVE -- so
shipping a decision rule now would be a claim the record does not support. The trace shows
the score and the labelled events and stops there. Latency and throughput are measured and
in the report, as the third constraint asks.

## Interface contract (M3, as written at M0)

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
