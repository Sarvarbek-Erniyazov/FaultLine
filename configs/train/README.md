# Training configurations

Empty at M0 by design. No training loop exists in this repository yet.

## Planned files

`telemetry_v0.yaml` (M1), `text_v0.yaml` (M2), `joint_v0.yaml` (M3)
: Optimiser, learning-rate schedule, batch and accumulation, precision, gradient
  clipping, checkpoint policy, and the seeds. Multi-seed runs are not optional here:
  the project reports confidence intervals across seeds, so the seed list is part of
  the config rather than a command-line afterthought.

Every training config names the data config and tokenizer config it depends on by
path and by hash, so a checkpoint can be traced back to the exact corpus that
produced it.
