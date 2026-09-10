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
| provider note | farm A is 5 onshore turbines in Portugal, farms B and C are offshore in Germany; 86/257/957 features per farm; 95 datasets, 45 with labelled anomaly events; event_info files carry event descriptions |

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
| channels mapped | 0 of 14 |
| mapping status | UNVERIFIED - every entry is still TODO(m1); the adapter skips this source rather than guessing at column names |

## Use in FaultLine

| field | value |
| --- | --- |
| intended use | labelled anomaly events for evaluation and label cross-check |
| PII policy | not applicable - telemetry and coded event logs; the text policy in ADR-0005 applies to narrative corpora only |
| exclusions | tier 2 files are specified but not staged at M0 (grid meter, phasor measurement, geographic overlays) |

## Caveats

**From the provider.** farm A is 5 onshore turbines in Portugal, farms B and C are offshore in Germany; 86/257/957 features per farm; 95 datasets, 45 with labelled anomaly events; event_info files carry event descriptions

**Found during inspection.** See `reports/data/raw_inventory_care_20260910.md`.

**Known limits of this card.** Every field marked `UNVERIFIED` is an open question, not an absence of a problem.

## Generation

| field | value |
| --- | --- |
| generated (UTC) | 2026-09-10T09:55:57+00:00 |
| git_sha | 3e78a10e0b622b766ef384205c8084cb667ea49a |
| generated by | faultline cards build |
| template | docs/DATASET_CARD_TEMPLATE.md |
| generated from | the manifest (staging), the raw inventory report (free-text verdict), the resolution report (measured questions) and the channel map file (channels) |
| hand-written | 'Contents as published', the provenance chain, the intended use and the provider caveat, copied from configs/data/sources_telemetry.yaml |
