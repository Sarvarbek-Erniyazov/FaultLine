# Dataset card: Hill of Towie


## Identity

| field | value |
| --- | --- |
| source id | hill_of_towie |
| provider | RES on behalf of TRIG |
| version-pinned record | https://zenodo.org/records/14870023 |
| concept DOI | 10.5281/zenodo.14870023 |
| version DOI | 10.5281/zenodo.14870023 |
| licence | CC-BY-4.0 |
| attribution | RES on behalf of The Renewables Infrastructure Group, Hill of Towie wind farm data, Zenodo, doi:10.5281/zenodo.14870023 (CC BY 4.0) |
| accompanying publication | none |
| provenance chain | none stated by the publisher |

## Contents as published

| field | value |
| --- | --- |
| site | Hill of Towie |
| country | UK |
| turbine model | Siemens SWT-2.3-VS-82 |
| turbines | 21 |
| rated power (kW) | 2,300 |
| period | 2016-01..2024-08 |
| resolution | 10 min (as published) |
| timezone | UTC |
| real calendar timestamps | yes |
| provider note | AeroUp retrofits 2021-2023 and TuneUp 2024 are a built-in regime change; install dates are in Hill_of_Towie_AeroUp_install_dates.csv |

_Hand-written: copied from the provider's record metadata into `configs/data/sources_telemetry.yaml`, not generated from the staged files._

## Staging

| field | value |
| --- | --- |
| files retrieved | 9 |
| total size (MB) | 2,962 |
| all checksums verified | yes |
| first retrieved (UTC) | 2026-09-09T13:36:54+00:00 |
| manifest | data/cards/manifests/hill_of_towie.json |
| raw inventory report | reports/data/raw_inventory_hill_of_towie_20260910.md |

| file | size (MB) | md5 recorded | verified |
| --- | --- | --- | --- |
| 2019.zip | 1,430 | yes | yes |
| 2023.zip | 1,512 | yes | yes |
| Hill_of_Towie_AeroUp_install_dates.csv | 0 | yes | yes |
| Hill_of_Towie_ShutdownDuration.zip | 19.8 | yes | yes |
| Hill_of_Towie_alarms_description.csv | 0 | yes | yes |
| Hill_of_Towie_grid_fields_description.csv | 0 | yes | yes |
| Hill_of_Towie_tables_description.csv | 0 | yes | yes |
| Hill_of_Towie_turbine_fields_description.csv | 0 | yes | yes |
| Hill_of_Towie_turbine_metadata.csv | 0 | yes | yes |

_Generated from the manifest; no figure in this section is typed by hand._

## Event, alarm and status logs

**Free-text verdict: VERIFIED no**

codes only: 24 event tables and 1,004,341 rows were parsed, and not one row carries a message

This is the field that decides whether the paired text in this record can carry a language model, or whether it only supplies labels and structure (ADR-0001). The verdict is one of `VERIFIED no` (codes only, or a code book of recurring labels), `VERIFIED short written descriptions` (a closed set of strings written per event; `VERIFIED written descriptions` when they run longer than a line), `VERIFIED yes` (open-ended text) or `UNVERIFIED`. It follows the measurements in the raw inventory report named above; do not edit this field by hand.

These thresholds were chosen after all four sources had been inspected, so they describe what was measured rather than predicting it. The classification does not hinge on them. The singleton shares measured are 14.7% (Kelmarsh), 11.3% (Penmanshiel) and 85.7% (CARE), and Hill of Towie carries no text at all, so any singleton-share threshold between 20% and 80% yields the same classification for all four sources; the full band runs from just above 14.7% to 85.7%. Likewise the 500-string ceiling sits above the largest closed set measured (231 strings, Penmanshiel).

## Questions resolved by measurement

| question | verdict | evidence |
| --- | --- | --- |
| Power column unit | **kW** | the median per-turbine-year p99.5 is 2,299.2, which sits on the rated power of 2,300 kW and is 6.0x the 383.3 kWh a 10-minute energy total would reach |
| Timestamp timezone | **UTC** | across 42 turbine-years, every spring-forward hour is fully populated and no autumn fall-back hour repeats a timestamp -- neither fingerprint that Europe/London would leave is present; both halves applied to every turbine-year |

These are questions the provider metadata could not settle, because it either contradicted itself or asserted without evidence. They were measured from the staged archives by `faultline inspect resolve`; the per-turbine-year tables behind each verdict are in `reports/data/resolved_hill_of_towie_20260910.md`. Do not edit this section by hand.

## Channels

| field | value |
| --- | --- |
| channel map | configs/data/channel_map/hill_of_towie.yaml |
| channels mapped | 14 of 14 resolved, 0 verified absent, 0 ambiguous |
| mapping status | resolved: 14 of 14 mapped from the provider's field lookup; wind direction is published in the 2023 export only |

## Use in FaultLine

| field | value |
| --- | --- |
| intended use | held-out site; also the temporal-drift axis |
| PII policy | not applicable - telemetry and coded event logs; the text policy in ADR-0005 applies to narrative corpora only |
| exclusions | tier 2 files are specified but not staged at M0 (grid meter, phasor measurement, geographic overlays) |

## Caveats

**From the provider.** AeroUp retrofits 2021-2023 and TuneUp 2024 are a built-in regime change; install dates are in Hill_of_Towie_AeroUp_install_dates.csv

**Found during inspection.** See `reports/data/raw_inventory_hill_of_towie_20260910.md`.

**Known limits of this card.** Every field marked `UNVERIFIED` is an open question, not an absence of a problem.

## Evaluation gaps (added by hand, 2026-09-16; not produced by `faultline cards build`)

This section is written by hand, because the generator has no field for it. A regeneration of
this card must carry it forward. The same record is kept in `docs/ROADMAP.md` (M3) and
ADR-0018.

- **275 Hill of Towie status messages are not written into the `tel+status` stream.** Their
  step is absent from the final telemetry rows (a filtered outage or a gap), so the attachment
  rule has no step to put them after (`reports/data/joint_mixture_v0_20260916.md`, messages not
  written). Hill of Towie is the held-out site, so every held-out-site result that reads status
  text is measured without these 275 messages. The number is small against the 891,253 written
  to its test split, and it is not zero. It is not known whether those messages cluster around
  events: a gap in the rows is where an outage, and therefore an event, is likely.
- The free-text verdict above (`VERIFIED no`) was generated at M0 from the event tables alone.
  The described status messages the M3 stream reads were added to this source later.
  `data/cards/status_code_book.md` is the record of those strings.

## Generation

| field | value |
| --- | --- |
| generated (UTC) | 2026-09-10T14:11:11+00:00 |
| git_sha | dded9436d9495c754c83ef750a1e20a95372ea46 |
| generated by | faultline cards build |
| template | docs/DATASET_CARD_TEMPLATE.md |
| generated from | the manifest (staging), the raw inventory report (free-text verdict), the resolution report (measured questions) and the channel map file (channels) |
| hand-written | 'Contents as published', the provenance chain, the intended use and the provider caveat, copied from configs/data/sources_telemetry.yaml |
