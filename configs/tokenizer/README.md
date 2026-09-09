# Tokenizer configurations

Empty at M0. The code these will drive already exists and is tested
(`src/faultline/tokenizers/`); only the fitted artefacts and their configs are
missing, because fitting on real data is an M1 activity.

## Planned files

`quantile_bins_v0.yaml` (M1)
: Channels to fit, bin count, row sample cap, seed, and the split the edges are
  fitted on. **Fitting uses the training split only** -- fitting on the full record
  leaks the held-out period's distribution into the vocabulary and flatters every
  drift number the project reports.

`text_bpe_v0.yaml` (M2)
: Byte-level BPE vocabulary size, minimum merge frequency, and the corpus manifest
  the tokenizer is trained on.

`joint_v0.yaml` (M3)
: How much of each block the fitted vocabulary uses (ADR-0003). The block *offsets*
  are not configurable: they derive from the fixed capacities in
  `faultline.tokenizers.layout`, so the M1 and M2 tokenizers are fitted independently
  against local ids and concatenated here by appending text to a telemetry prefix
  that never moves -- no retokenizing, and no M1 shard invalidated.
