# Tokenizer configurations

The code these drive lives in `src/faultline/tokenizers/`. The telemetry configuration is
written and fitted; the text and joint configurations are still to come.

## Files

`quantile_bins_v0.yaml` (M1b step 11, ADR-0011)
: The telemetry configuration it reads, the channels (every core channel, in identifier
  order), the candidate bin counts and the one chosen with its reason, exact bins for
  point masses, and the channels emitted as `<nan>` at a source. **Fitting uses the
  training split only** -- fitting on the full record leaks the held-out period's
  distribution into the vocabulary and flatters every drift number the project reports.
  `faultline telemetry bins` fits it into `data/tokenizers/quantile_bins_v0_<hash>.json`.

`text_bpe_v0.yaml` (M2)
: Byte-level BPE vocabulary size, minimum merge frequency, and the corpus manifest
  the tokenizer is trained on.

`joint_v0.yaml` (M3)
: How much of each block the fitted vocabulary uses (ADR-0003). The block *offsets*
  are not configurable: they derive from the fixed capacities in
  `faultline.tokenizers.layout`, so the M1 and M2 tokenizers are fitted independently
  against local ids and concatenated here by appending text to a telemetry prefix
  that never moves -- no retokenizing, and no M1 shard invalidated.
