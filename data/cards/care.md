# Dataset card: CARE farms A/B/C (anonymised)


## Identity

| field | value |
| --- | --- |
| source id | care |
| provider | Fraunhofer IEE |
| version-pinned record | https://zenodo.org/records/15846963 |
| concept DOI | 10.5281/zenodo.10958774 |
| version DOI | 10.5281/zenodo.15846963 |
| licence | CC-BY-SA-4.0 |
| attribution | Gueck, Bruns, Dupont, CARE to Compare, Fraunhofer IEE, Zenodo, doi:10.5281/zenodo.10958774 (CC BY-SA 4.0) |
| accompanying publication | Gueck, Bruns, Dupont (2024), CARE to Compare, Data 9(12):138, doi:10.3390/data9120138 |
| provenance chain | Farm A is EDP Open Data republished by Fraunhofer IEE: the record README states that "the data for Wind farm A is based on data from the EDP-open data platform". The chain is EDP Open Data -> Fraunhofer IEE, CARE to Compare (Zenodo record 15846963) -> CC BY-SA 4.0, and the CC BY-SA 4.0 licence on the Fraunhofer record is the one that governs. Farms B and C are offshore farms in Germany that the README gives no upstream for. Farm A can be separated out for a sensitivity check: it is its own directory, 22 of 95 datasets and 5 of 36 turbines. |

## Contents as published

| field | value |
| --- | --- |
| site | CARE farms A/B/C (anonymised) |
| country | PT / DE |
| turbine model | TODO(m1): not published; turbines are anonymised |
| turbines | 36 |
| rated power (kW) | UNVERIFIED - not published per farm |
| period | 89 turbine-years |
| resolution | 10 min (as published) |
| timezone | not applicable - timestamps anonymised by the provider (record README) |
| real calendar timestamps | no - anonymised by the provider, so this source is excluded from every absolute-time and seasonal feature |
| provider note | farm A is 5 onshore turbines in Portugal, farms B and C are offshore in Germany; 86/257/957 features per farm; 95 datasets, 45 with labelled anomaly events by event_info (12/6/27 in farms A/B/C; the README says 44); event_info files carry event descriptions |

_Hand-written: copied from the provider's record metadata into `configs/data/sources_telemetry.yaml`, not generated from the staged files._

## Staging

| field | value |
| --- | --- |
| files retrieved | 1 |
| total size (MB) | 5,503 |
| all checksums verified | yes |
| first retrieved (UTC) | 2026-09-09T16:37:49+00:00 |
| manifest | data/cards/manifests/care.json |
| raw inventory report | reports/data/raw_inventory_care_20260910.md |

| file | size (MB) | md5 recorded | verified |
| --- | --- | --- | --- |
| CARE_To_Compare.zip | 5,503 | yes | yes |

_Generated from the manifest; no figure in this section is typed by hand._

## Event, alarm and status logs

**Free-text verdict: VERIFIED short written descriptions**

a closed set of 35 strings written per event rather than drawn from a code book: 35 distinct strings over 45 rows with text, mean length 55.9 characters (8.4 words), 85.7% of the distinct strings occurring exactly once. Richer than a code book and far too little to be a corpus, so ADR-0001 is qualified rather than overturned

This is the field that decides whether the paired text in this record can carry a language model, or whether it only supplies labels and structure (ADR-0001). The verdict is one of `VERIFIED no` (codes only, or a code book of recurring labels), `VERIFIED short written descriptions` (a closed set of strings written per event; `VERIFIED written descriptions` when they run longer than a line), `VERIFIED yes` (open-ended text) or `UNVERIFIED`. It follows the measurements in the raw inventory report named above; do not edit this field by hand.

These thresholds were chosen after all four sources had been inspected, so they describe what was measured rather than predicting it. The classification does not hinge on them. The singleton shares measured are 14.7% (Kelmarsh), 11.3% (Penmanshiel) and 85.7% (CARE), and Hill of Towie carries no text at all, so any singleton-share threshold between 20% and 80% yields the same classification for all four sources; the full band runs from just above 14.7% to 85.7%. Likewise the 500-string ceiling sits above the largest closed set measured (231 strings, Penmanshiel).

## Questions resolved by measurement

UNVERIFIED - nothing has been measured for this source yet. Run `faultline inspect resolve --source care` once its archives are staged.

## Channels

| field | value |
| --- | --- |
| channel map | configs/data/channel_map/care.yaml |
| channels mapped | farm_a: 13 of 14 resolved, 1 verified absent, 0 ambiguous; farm_b: 10 of 14 resolved, 2 verified absent, 2 ambiguous; farm_c: 9 of 14 resolved, 3 verified absent, 2 ambiguous |
| mapping status | resolved per farm from feature_description.csv: farm A 13, farm B 10, farm C 9 of 14 mapped; the rest verified absent or ambiguous; power is normalised, not kW |

## Use in FaultLine

| field | value |
| --- | --- |
| intended use | labelled anomaly events for evaluation and label cross-check |
| PII policy | not applicable - telemetry and coded event logs; the text policy in ADR-0005 applies to narrative corpora only |
| exclusions | tier 2 files are specified but not staged at M0 (grid meter, phasor measurement, geographic overlays) |

## Caveats

**From the provider.** farm A is 5 onshore turbines in Portugal, farms B and C are offshore in Germany; 86/257/957 features per farm; 95 datasets, 45 with labelled anomaly events by event_info (12/6/27 in farms A/B/C; the README says 44); event_info files carry event descriptions

**Found during inspection.** See `reports/data/raw_inventory_care_20260910.md`.

**Known limits of this card.** Every field marked `UNVERIFIED` is an open question, not an absence of a problem.

## Channel mapping in the token stream (added by hand, 2026-09-17; not produced by `faultline cards build`)

This section is written by hand, because the generator has no field for it. A regeneration of
this card must carry it forward. It is the record ADR-0022 reads (F4). Every figure below was
measured on 2026-09-17 from `configs/data/channel_map/care.yaml`, the shard manifest and the
token stream of `data/shards/telemetry/quantile_bins_v2_9cd52b65/` (the shards in force:
`quantile_bins_v2.yaml`, `telemetry_v4.yaml`, `splits_v3.yaml`). No model was loaded.

**The counts.** `schemas.CANONICAL_CHANNELS` holds **14 canonical channels**. **12 are core**
and **2 are extended** (`wind_direction_deg` and `gearbox_bearing_temp_c`). The tokenizer is
fitted on the 12 core channels only, so every source's stream carries those 12, as 13 tokens a
step (`<sep>` and one bin token per core channel, manifest `tokens_per_step: 13`). Both training
sites (Kelmarsh, Penmanshiel) populate all 12 core channels. The two extended channels are never
tokenized at any source, whether mapped or not.

**How an absent channel enters the stream: as `<nan>` tokens, never masked.** The manifest's
`masked` and the tokenizer's `excluded` are both empty. An unmapped core channel keeps its
position in every step and reads `<nan>` on every step: its measured `<nan>` share is 1.0000 at
its farm. No window drops an absent channel.

| farm | canonical channels mapped (of 14) | canonical channels absent | core channels in the stream (of 12) | core channels absent from the stream, emitted as `<nan>` | `<nan>` share of value tokens |
| --- | --- | --- | --- | --- | --- |
| farm A | 13 | `main_bearing_temp_c` (verified absent) | 11 | `main_bearing_temp_c` | 8.35% |
| farm B | 10 | `nacelle_temp_c`, `generator_winding_temp_c` (verified absent); `gearbox_bearing_temp_c`, `generator_bearing_temp_c` (ambiguous, left unmapped) | 9 | `nacelle_temp_c`, `generator_bearing_temp_c`, `generator_winding_temp_c` | 25.01% |
| farm C | 9 | `nacelle_position_deg`, `wind_direction_deg`, `nacelle_temp_c` (verified absent); `gearbox_bearing_temp_c`, `generator_bearing_temp_c` (ambiguous, left unmapped) | 9 | `nacelle_position_deg`, `nacelle_temp_c`, `generator_bearing_temp_c` | 25.22% |

The `<nan>` shares are over the steps the known CARE evaluation windows cover (label
`narrow_within_24h`). All of CARE reads **21.34%**. Beside them, per the M1c reporting rule
(`configs/eval/README.md`, rule 1): the training sites' test splits read **0.15%** (Kelmarsh) and
**0.36%** (Penmanshiel), and their pretraining windows (the training index at stride 6) read
**4.45%** and **6.41%**.

### Caveats discovered during inspection

- **Correction: the core set is 12 channels, not 13.** "13" comes from `configs/data/splits_v1.yaml`
  ("thirteen channels", frozen before wind direction was demoted at M1b step 10) and from the 13
  tokens a step. The F0–F6 brief's "13 canonical channels" is wrong: there are 14 canonical channels
  and 12 core channels. The G-series CARE report's "1 of the 12" counts core channels in the stream,
  and it is right.
- **The pretraining stream never shows a CARE farm's absence pattern.** `<nan>` is not rare in
  pretraining. But of 749,847 pretraining windows (both training sites, index at stride 6), **0**
  have exactly farm A's, farm B's or farm C's set of fully-`<nan>` channels. The 12,816 windows
  (1.71%) in which those channels are all `<nan>` lose other channels with them (whole-turbine gaps
  at Kelmarsh). A channel that is permanently absent while its neighbours report is new to the
  backbone at every CARE farm.
- **The 29.7% CARE `<nan>` share in `configs/eval/README.md` is historical.** It was measured on
  the M1b shards, where CARE power was also `<nan>` (ADR-0011). Power returned at M1c (ADR-0013),
  and the share on the shards in force is 21.34%.

## Generation

| field | value |
| --- | --- |
| generated (UTC) | 2026-09-10T21:28:06+00:00 |
| git_sha | 4aff202e3ef865531e6b712c056cbf7d962da613 |
| generated by | faultline cards build |
| template | docs/DATASET_CARD_TEMPLATE.md |
| generated from | the manifest (staging), the raw inventory report (free-text verdict), the resolution report (measured questions) and the channel map file (channels) |
| hand-written | 'Contents as published', the provenance chain, the intended use and the provider caveat, copied from configs/data/sources_telemetry.yaml |
