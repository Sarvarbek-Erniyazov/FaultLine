# Evaluation configurations

Empty at M0 by design.

## Planned files

`risk_v0.yaml` (M1)
: The horizon, the decision threshold sweep, and the primary metrics: AUPRC,
  event-level F1, false alarms per hour, detection delay.

`selective_v0.yaml` (M1)
: Abstention: risk-coverage curves, AURC, the conformal risk control procedure and
  its target risk level, and the calibration split -- which must be disjoint from
  both training and test.

`shift_v0.yaml` (M1/M3)
: The three shift axes. Site: leave-wind-farm-out, reporting worst-site rather than
  mean-site performance. Modality: which channels or which text are dropped or
  corrupted at inference, and how. Temporal: the later periods and the retrofit
  boundary at the held-out site.

A number that does not come out of one of these configs does not go in the README.
