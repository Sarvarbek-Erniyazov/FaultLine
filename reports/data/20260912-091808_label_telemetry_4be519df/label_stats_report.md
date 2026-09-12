# Telemetry pipeline - event labels, harmonised

| field | value |
| --- | --- |
| run_id | 20260912-091808_label_telemetry_4be519df |
| stage | label |
| config | configs/data/telemetry_v4.yaml |
| config_hash | 4be519df |
| git_sha | 1747d1230b5273eeecbac150c69113603b6d600a |
| created_at (UTC) | 2026-09-12T09:18:08+00:00 |

## Rules

| field | value |
| --- | --- |
| labels config | configs/data/events_v2.yaml |
| labels config sha256[:8] | 61f436b5 |
| decision | ADR-0009: narrow the held-out site to the training definition; do not widen the training sites |
| the rule | an event is a run of consecutive 10-minute steps holding downtime of the chosen causes, lasting at least the minimum duration; one function (harmonise.select_events), with no source argument |
| narrow (primary) | technical |
| broad (secondary) | any cause: technical, environmental, grid, planned, unknown |
| minimum duration (s) | 60 |
| horizons | event_within_1h, event_within_6h, event_within_24h |
| positive | an event of the set starts in (t, t + H] for the step at t |
| unknown label | no event seen, and the horizon runs past the record the events were read from: NA, never False (ADR-0006) |
| events per turbine-year | events starting in a step of the cleaned grid, over grid steps / 52,596 |

## Label table: events per turbine-year and base rate, both sets

Events with their rate per turbine-year of grid time in brackets. A base rate is positive steps over steps whose label is known. A source labelled one event per dataset is reported per dataset, in its own section below (ADR-0010).

| site | turbines | turbine-years | narrow events (/ty) | broad events (/ty) | narrow within_1h | narrow within_6h | narrow within_24h | broad within_1h | broad within_6h | broad within_24h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kelmarsh | 6 | 53.56 | 719 (13.4) | 5,604 (104.6) | 0.151% | 0.724% | 2.481% | 1.186% | 6.724% | 24.619% |
| penmanshiel | 14 | 91.26 | 1,503 (16.5) | 11,656 (127.7) | 0.182% | 0.879% | 3.040% | 1.432% | 7.712% | 27.492% |
| hill_of_towie | 21 | 41.97 | 693 (16.5) | 5,753 (137.1) | 0.187% | 1.013% | 3.542% | 1.552% | 8.881% | 32.176% |

## Base rate on steps with data, and how many labels are unknown

`with data`: at least one core channel has a value. `unknown`: share of all grid steps whose label is NA because its horizon runs past the event record.

| site | narrow within_1h with data | narrow within_6h with data | narrow within_24h with data | broad within_1h with data | broad within_6h with data | broad within_24h with data | narrow within_1h unknown | narrow within_6h unknown | narrow within_24h unknown | broad within_1h unknown | broad within_6h unknown | broad within_24h unknown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kelmarsh | 0.144% | 0.660% | 2.345% | 1.194% | 6.765% | 24.759% | 0.001% | 0.008% | 0.031% | 0.001% | 0.008% | 0.029% |
| penmanshiel | 0.174% | 0.789% | 2.807% | 1.465% | 7.878% | 27.990% | 0.002% | 0.011% | 0.039% | 0.002% | 0.011% | 0.036% |
| hill_of_towie | 0.160% | 0.933% | 3.426% | 1.557% | 8.903% | 32.245% | 0.430% | 0.691% | 1.597% | 0.000% | 0.000% | 0.000% |

## Duration threshold sensitivity

Events per set at each minimum duration, with the rate per turbine-year. The threshold applies to the seconds of downtime of the set's causes in the run.

| site | set | 60 s | 300 s | 600 s |
| --- | --- | --- | --- | --- |
| kelmarsh | narrow | 719 (13.4) | 517 (9.7) | 463 (8.6) |
| kelmarsh | broad | 5,604 (104.6) | 2,857 (53.3) | 2,764 (51.6) |
| penmanshiel | narrow | 1,503 (16.5) | 1,074 (11.8) | 992 (10.9) |
| penmanshiel | broad | 11,656 (127.7) | 7,001 (76.7) | 6,857 (75.1) |
| hill_of_towie | narrow | 693 (16.5) | 606 (14.4) | 544 (13.0) |
| hill_of_towie | broad | 5,753 (137.1) | 3,184 (75.9) | 1,905 (45.4) |

## Training sites: status rows against episodes

Gate 1 counted equipment-fault status rows (`rows, any duration`), and divided by turbine-year files (54, 98 and, at the held-out site, 42), which gave 19.5, 24.8 and 212.6; every rate here is over grid time instead. One fault episode is often several rows, and a Siemens downtime run is one event whatever it holds. The harmonised rule counts episodes at every site; this shows what that does to the training sites.

| site | technical rows, any duration (/ty) | rows >= 60 s | rows >= 300 s | rows >= 600 s | episodes >= 60 s | episodes >= 300 s | episodes >= 600 s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| kelmarsh | 1,054 (19.7) | 1,032 (19.3) | 628 (11.7) | 564 (10.5) | 719 (13.4) | 517 (9.7) | 463 (8.6) |
| penmanshiel | 2,433 (26.7) | 2,396 (26.3) | 1,318 (14.4) | 1,217 (13.3) | 1,503 (16.5) | 1,074 (11.8) | 992 (10.9) |

## Events per calendar year

Years with at least a day of grid. At the held-out site 2019 is before the AeroUp retrofit and 2023 after it, and 2019 publishes no wind direction.

| site | year | turbine-years | narrow (/ty) | broad (/ty) |
| --- | --- | --- | --- | --- |
| kelmarsh | 2016 | 5.56 | 58 (10.4) | 541 (97.2) |
| kelmarsh | 2017 | 6.00 | 54 (9.0) | 632 (105.4) |
| kelmarsh | 2018 | 6.00 | 50 (8.3) | 597 (99.6) |
| kelmarsh | 2019 | 6.00 | 39 (6.5) | 604 (100.7) |
| kelmarsh | 2020 | 6.01 | 64 (10.6) | 575 (95.6) |
| kelmarsh | 2021 | 6.00 | 39 (6.5) | 565 (94.2) |
| kelmarsh | 2022 | 6.00 | 110 (18.3) | 690 (115.1) |
| kelmarsh | 2023 | 6.00 | 204 (34.0) | 757 (126.3) |
| kelmarsh | 2024 | 6.01 | 101 (16.8) | 643 (106.9) |
| penmanshiel | 2016 | 7.28 | 212 (29.1) | 986 (135.5) |
| penmanshiel | 2017 | 13.99 | 115 (8.2) | 1,522 (108.8) |
| penmanshiel | 2018 | 13.99 | 138 (9.9) | 1,628 (116.4) |
| penmanshiel | 2019 | 13.99 | 128 (9.1) | 1,606 (114.8) |
| penmanshiel | 2020 | 14.03 | 282 (20.1) | 1,933 (137.8) |
| penmanshiel | 2021 | 13.99 | 295 (21.1) | 1,983 (141.7) |
| penmanshiel | 2022 | 13.99 | 333 (23.8) | 1,998 (142.8) |
| hill_of_towie | 2019 | 20.99 | 383 (18.3) | 2,960 (141.0) |
| hill_of_towie | 2023 | 20.99 | 309 (14.7) | 2,793 (133.1) |

## Broad events by dominant cause

| site | technical | environmental | grid | planned | unknown |
| --- | --- | --- | --- | --- | --- |
| kelmarsh | 639 | 95 | 471 | 4,298 | 101 |
| penmanshiel | 963 | 1,885 | 850 | 7,799 | 159 |
| hill_of_towie | 428 | 1,826 | 38 | 2,703 | 758 |

## Where the cause comes from: the published columns

Every column of every table the labels read, as published. At the held-out site neither `ShutdownDuration.csv` nor `tblAlarmLog` carries a cause or availability category. `tblSCTurFlag` does, as seconds per step in four stop classes: `wtc_ScTurSto_timeon` (the provider's description: 'Time turbine error active in period'), and `wtc_ScEnvSto_timeon`, `wtc_ScComSto_timeon` and `wtc_ScGrdSto_timeon` (not described). That is rung (a) of ADR-0009: exclusion by cause.

| site | table | columns | names |
| --- | --- | --- | --- |
| kelmarsh | status export | 9 | `Code`, `Comment`, `Duration`, `IEC category`, `Message`, `Service contract category`, `Status`, `Timestamp end`, `Timestamp start` |
| penmanshiel | status export | 9 | `Code`, `Comment`, `Duration`, `IEC category`, `Message`, `Service contract category`, `Status`, `Timestamp end`, `Timestamp start` |
| hill_of_towie | ShutdownDuration.csv | 3 | `TimeStamp_StartFormat`, `TurbineName`, `ShutdownDuration` |
| hill_of_towie | tblAlarmLog | 4 | `TimeOn`, `TimeOff`, `StationNr`, `Alarmcode` |
| hill_of_towie | Hill_of_Towie_alarms_description.csv | 3 | `Alarm Code`, `Description`, `Stopping` |
| hill_of_towie | tblSCTurFlag | 44 | `TimeStamp`, `StationId`, `wtc_ScYawOpe_counts`, `wtc_ScYawOpe_endvalue`, `wtc_ScYawUnw_counts`, `wtc_ScYawUnw_endvalue`, `wtc_PriAnAct_endvalue`, `wtc_ScAStart_counts`, `wtc_ScAStart_endvalue`, `wtc_ScBrakOp_counts`, `wtc_ScBrakOp_endvalue`, `wtc_ScBrakOp_timeon`, `wtc_ScFrsErr_endvalue`, `wtc_ScInOper_counts`, `wtc_ScInOper_endvalue`, `wtc_ScInOper_timeon`, `wtc_ScReToOp_counts`, `wtc_ScReToOp_endvalue`, `wtc_ScReToOp_timeon`, `wtc_ScStartC_counts`, `wtc_ScWindIR_counts`, `wtc_ScWindIR_endvalue`, `wtc_ScWindIR_timeon`, `wtc_OpCode_endvalue`, `wtc_ScEnvSto_counts`, `wtc_ScEnvSto_endvalue`, `wtc_ScEnvSto_timeon`, `wtc_ScComSto_counts`, `wtc_ScComSto_endvalue`, `wtc_ScComSto_timeon`, `wtc_ScTurSto_counts`, `wtc_ScTurSto_endvalue`, `wtc_ScTurSto_timeon`, `wtc_ScGrdSto_counts`, `wtc_ScGrdSto_endvalue`, `wtc_ScGrdSto_timeon`, `wtc_LocRemSt_endvalue`, `wtc_AlarmCde_endvalue`, `wtc_BrakStat_endvalue`, `wtc_GenStat_endvalue`, `wtc_Turbstat_endvalue`, `wtc_YawStat_endvalue`, `wtc_TlcStat_endvalue`, `wtc_TlcStat_timeon` |
| care | event_info | 8 | `asset`, `event_description`, `event_end`, `event_end_id`, `event_id`, `event_label`, `event_start`, `event_start_id` |

## hill_of_towie: how the downtime was attributed

| field | value |
| --- | --- |
| down steps in the labelled years | 61,830 |
| of which no stop-class row was published | 7,751 |
| of which no stop class covers a second (cause unknown) | 25,477 |
| stop-class rows read | 2,199,227 |

Described codes whose own description names a non-technical cause take the turbine-error seconds of the steps their alarm is active in:

| code | description | cause | steps moved | turbine-error seconds moved |
| --- | --- | --- | --- | --- |
| 1005 | Availability - low wind | environmental | 48 | 9,648 |
| 10105 | Stopped, untwisting cables | planned | 33 | 16,707 |
| 3130 | Pitch lubrication | planned | 3,750 | 556,654 |
| 8000 | Windspeed too high to operate | environmental | 58 | 33,440 |
| 8230 | Ice detection: Low torque | environmental | 203 | 121,247 |

## Wind state at the start of narrow events

Diagnostic, not a filter (`apply: false`). One envelope for every site: cut-in 3.0 m/s, cut-out 20.0 m/s. Provenance: cut_in_ms: the median wind at the start of each provider's own low-wind stop is 2.71 m/s (Kelmarsh, 'Wind < start wind', n=57,575), 3.39 (Penmanshiel, n=111,136) and 3.86 (Hill of Towie, code 1005, n=2,665); 1% of producing steps (power > 10 kW) are below 2.83, 3.67 and 3.21. cut_out_ms: the median at the start of a high-wind stop is 22.52 (Kelmarsh 'Max. wind speed', n=4), 22.68 (Penmanshiel, n=3,339) and 20.70 (Hill of Towie code 8000, n=232); the lowest, rounded down. The last column is the narrow rate a wind rule would leave.

| site | narrow events | below cut-in | above cut-out | inside | unknown | inside or unknown (/ty) |
| --- | --- | --- | --- | --- | --- | --- |
| kelmarsh | 719 | 105 | 52 | 551 | 11 | 562 (10.5) |
| penmanshiel | 1,503 | 209 | 346 | 933 | 15 | 948 (10.4) |
| hill_of_towie | 693 | 77 | 24 | 592 | 0 | 592 (14.1) |

## Sensitivity: emergency stops counted as faults

The configured emergency-stop strings move from their category (manual operation, or unmapped) to technical. Hill of Towie describes no emergency-stop code, so it has no counterpart.

| site | emergency stop rows | narrow (/ty) | with them (/ty) | change (/ty) |
| --- | --- | --- | --- | --- |
| kelmarsh | 10 | 719 (13.4) | 722 (13.5) | +0.06 |
| penmanshiel | 22 | 1,503 (16.5) | 1,523 (16.7) | +0.22 |

## hill_of_towie: downtime against the provider's Stopping flag

An occurrence of a described code agrees when downtime at or above the threshold appears from the step it opens in through the window after its end, exactly when the code is described as stopping.

**Threshold 60 s, window 1 step(s)**: 879,841 of 891,528 occurrences agree (98.69%); stopping codes 7,678 of 7,687 (99.88%)

| code | stopping | occurrences | showing downtime | agreeing | agreement |
| --- | --- | --- | --- | --- | --- |
| 20 | no | 441,896 | 5,219 | 436,677 | 98.8% |
| 25 | no | 441,895 | 6,459 | 435,436 | 98.5% |
| 3130 | yes | 2,977 | 2,976 | 2,976 | 100.0% |
| 1005 | yes | 2,744 | 2,736 | 2,736 | 99.7% |
| 10105 | yes | 1,508 | 1,508 | 1,508 | 100.0% |
| 8000 | yes | 232 | 232 | 232 | 100.0% |
| 8230 | yes | 226 | 226 | 226 | 100.0% |
| 102 | no | 50 | 0 | 50 | 100.0% |


**Threshold 300 s, window 1 step(s)**: 884,537 of 891,528 occurrences agree (99.22%); stopping codes 4,857 of 7,687 (63.18%)

| code | stopping | occurrences | showing downtime | agreeing | agreement |
| --- | --- | --- | --- | --- | --- |
| 20 | no | 441,896 | 1,410 | 440,486 | 99.7% |
| 25 | no | 441,895 | 2,751 | 439,144 | 99.4% |
| 3130 | yes | 2,977 | 291 | 291 | 9.8% |
| 1005 | yes | 2,744 | 2,688 | 2,688 | 98.0% |
| 10105 | yes | 1,508 | 1,420 | 1,420 | 94.2% |
| 8000 | yes | 232 | 232 | 232 | 100.0% |
| 8230 | yes | 226 | 226 | 226 | 100.0% |
| 102 | no | 50 | 0 | 50 | 100.0% |


**Threshold 600 s, window 1 step(s)**: 885,265 of 891,528 occurrences agree (99.30%); stopping codes 3,167 of 7,687 (41.20%)

| code | stopping | occurrences | showing downtime | agreeing | agreement |
| --- | --- | --- | --- | --- | --- |
| 20 | no | 441,896 | 239 | 441,657 | 99.9% |
| 25 | no | 441,895 | 1,504 | 440,391 | 99.7% |
| 3130 | yes | 2,977 | 114 | 114 | 3.8% |
| 1005 | yes | 2,744 | 2,582 | 2,582 | 94.1% |
| 10105 | yes | 1,508 | 101 | 101 | 6.7% |
| 8000 | yes | 232 | 145 | 145 | 62.5% |
| 8230 | yes | 226 | 225 | 225 | 99.6% |
| 102 | no | 50 | 0 | 50 | 100.0% |

## Status stream: inputs, never targets

Every status row and alarm is written to `labels/status_stream.parquet`, warnings and non-stopping codes included, for the text pathway to read as input. Targets are built from stops only -- a Senvion row whose provider status is Stop, the downtime series at Hill of Towie -- so a warning can inform a prediction and never be one.

| site | counts |
| --- | --- |
| kelmarsh | rows: 504,180, provider Warning rows: 6,566, provider Stop rows: 7,049 |
| penmanshiel | rows: 839,303, provider Warning rows: 10,949, provider Stop rows: 17,298 |
| hill_of_towie | rows: 1,004,336, non-stopping codes: 883,841, undescribed codes: 112,808, stopping codes: 7,687 |

## care: labelled events, per dataset

One labelled window per dataset. An `anomaly` row is both label sets, and there is no stop evidence to apply the rule to. CARE is scored per dataset, with its own CARE score, so no per-step base rate and no rate per turbine-year is printed for it; the table after the counts is the interval a dataset-level rate near 50% can carry at these counts, with and without farm A (ADR-0004, ADR-0010).

| field | value |
| --- | --- |
| event_info rows | 95 |
| farm_a anomaly | 12 |
| farm_a normal | 10 |
| farm_b anomaly | 6 |
| farm_b normal | 9 |
| farm_c anomaly | 27 |
| farm_c normal | 31 |
| anomaly starts inside their dataset's grid | 45 |

| label | farms | datasets | a rate near 50%, 95% interval |
| --- | --- | --- | --- |
| anomaly | all farms | 45 | 35-63% |
| anomaly | without farm A | 33 | 33-65% |
| normal | all farms | 50 | 37-63% |
| normal | without farm A | 40 | 35-65% |
