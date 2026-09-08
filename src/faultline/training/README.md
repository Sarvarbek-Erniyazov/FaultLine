# `faultline.training`

**Empty at M0 by design.** No training loop exists in this repository yet.

## Interface contract (M1)

```python
def train(config: TrainConfig, data: DataModule, model: nn.Module) -> Checkpoint: ...
```

What the loop must do, because the evaluation depends on it:

- **Multi-seed by construction.** The project reports confidence intervals across
  seeds, so the seed list belongs in the config and the loop runs them — rather than a
  single run being repeated by hand and stitched together later.
- **Fit the budget.** One RTX 4060, 8 GB. Gradient accumulation and mixed precision are
  expected; silently spilling into system memory is a bug, not a slowdown.
- **Checkpoint provenance.** Every checkpoint records the data config hash, the
  tokenizer config hash, the git SHA and the seed. A checkpoint that cannot name the
  corpus it was trained on cannot be reported.
- **Never touch the test split.** The calibration split for conformal risk control is
  disjoint from both training and test, and the loop enforces that rather than trusting
  the caller to remember.

Torch is deliberately not a dependency at M0; M1 pins the CUDA build matching the
driver recorded in the M0 report.
