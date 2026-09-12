# Tokenizer configurations

The code these drive lives in `src/faultline/tokenizers/`. The telemetry configuration is
written and fitted; the text and joint configurations are still to come.

## Files

`quantile_bins_v*.yaml` (telemetry)
: The telemetry configuration each reads, the channels (every core channel, in identifier
  order), the candidate bin counts and the one chosen with its reason, exact bins for
  point masses, the tail rule, and the channels emitted as `<nan>` at a source. **Fitting
  uses the training split only** -- fitting on the full record leaks the held-out period's
  distribution into the vocabulary and flatters every drift number the project reports.
  `faultline telemetry bins --config <file>` fits one into
  `data/tokenizers/quantile_bins_v<version>_<hash>.json` and reports it in
  `reports/data/quantile_bins_v<version>_<date>.md`. A version a run has read is never
  edited; a change is a new version file, and the older ones stay for the record.

  | version | milestone | what it is | state |
  | --- | --- | --- | --- |
  | `v0` | M1b step 11, ADR-0011 | 256 pure quantile bins, exact bins for point masses | superseded; no longer validates -- it names `power_kw`, which ADR-0013 renamed |
  | `v1` | M1c, ADR-0014 | hybrid tails, 16 fixed-width bins a side | superseded by `v2` |
  | `v2` | M1d, ADR-0015 | `n_tail` turned to 4 as pre-registered, and the clamp bin population-floored | **current** |

`text_bpe_v0.yaml` (M2)
: Byte-level BPE vocabulary size, minimum merge frequency, and the corpus manifest
  the tokenizer is trained on.

`joint_v0.yaml` (M3)
: How much of each block the fitted vocabulary uses (ADR-0003). The block *offsets*
  are not configurable: they derive from the fixed capacities in
  `faultline.tokenizers.layout`, so the M1 and M2 tokenizers are fitted independently
  against local ids and concatenated here by appending text to a telemetry prefix
  that never moves -- no retokenizing, and no M1 shard invalidated.
