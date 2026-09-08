# `faultline.evaluation`

**Empty at M0 by design.**

## Interface contract (M1)

```python
def risk_metrics(scores: NDArray, labels: NDArray) -> RiskReport: ...
def risk_coverage(scores: NDArray, labels: NDArray, confidence: NDArray) -> Curve: ...
def conformal_threshold(calibration: Calibration, target_risk: float) -> float: ...
def shift_report(per_site: dict[str, RiskReport]) -> ShiftReport: ...
```

The metrics, and why these rather than accuracy:

| metric | why |
| --- | --- |
| AUPRC | events are rare; ROC-AUC flatters a model on an imbalanced problem |
| event-level F1 | credit belongs to detecting an *event*, not to each timestep near it |
| false alarms per hour | the quantity that decides whether anyone would tolerate the system |
| detection delay | a correct warning that arrives too late is not a correct warning |
| risk–coverage, AURC | the model may abstain, and abstention has to be scored |
| coverage under shift | an honest model abstains **more** when its inputs are degraded |
| worst-site performance | a mean over sites hides the site that fails |

Every number carries a multi-seed confidence interval and the run id it came from. The
reporting function refuses to emit a headline number without both.
