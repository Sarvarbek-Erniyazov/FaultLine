# Evaluation configurations

Empty at M0 by design.

## Two reporting rules, fixed before there is anything to report

Written at M1c, before the first model is trained, because a reporting rule chosen after
the numbers are in is a choice about which number to show.

**1. A per-source metric is always printed next to that source's `<nan>` share.** The
sources do not carry the same amount of measured data, and the difference is large enough
to explain a result on its own: at the M1b shards roughly 12% of all value tokens were
`<nan>`, and the share ran from 0.01% at Hill of Towie to 29.7% at CARE, which maps a
different subset of the canonical channels at each of its three farms (ADR-0010). A score
computed over mostly-`<nan>` steps is a score about missingness. Any table of per-source
results therefore carries the `<nan>` share as a column, and any single per-source figure
in prose carries it in the same sentence.

**2. CARE is never pooled with Hill of Towie into a headline number.** They are different
kinds of evidence and averaging them would state neither. Hill of Towie is a whole record
at a held-out site, scored per step and per event, and reported per calendar year as well
as pooled (`per_year_sites`, ADR-0008). CARE is 95 chosen datasets scored per dataset,
whose interval cannot separate two models differing by less than roughly 15 points
(ADR-0010). A "generalisation score" averaging the two would hide which axis moved.
Site shift and dataset-level probe are reported separately, always.

Both rules apply to every table in `reports/`, to every figure, and to the project's own
prose about its results.

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

  It also carries the ablation pre-registered in ADR-0012: Hill of Towie scored with
  `pitch_angle_deg` masked to `<nan>` (core-11) beside the same checkpoints scored with
  it, to attribute how much of the site-shift penalty is pitch. Masking is the mechanism
  modality dropout already uses, so it needs no re-tokenisation.

A number that does not come out of one of these configs does not go in the README.
