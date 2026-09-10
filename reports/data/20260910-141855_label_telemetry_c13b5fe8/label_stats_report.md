# Telemetry pipeline - event labels

| field | value |
| --- | --- |
| run_id | 20260910-141855_label_telemetry_c13b5fe8 |
| stage | label |
| config | configs/data/telemetry_v1.yaml |
| config_hash | c13b5fe8 |
| git_sha | 801a8ee24cd9745a37e264bce138b04baba69a2d |
| created_at (UTC) | 2026-09-10T14:18:55+00:00 |

## Rules

| field | value |
| --- | --- |
| labels config | configs/data/events_v1.yaml |
| labels config sha256[:8] | 400658bc |
| horizons | event_within_1h, event_within_6h, event_within_24h |
| positive | a fault event starts in (t, t + H] for the step at t |
| primary horizon | none chosen; all three are labelled side by side |

## Positive base rate per site and horizon

Share of grid steps whose horizon holds the start of a fault event. `all steps` counts every step of the cleaned grid, gaps included; `steps with data` counts the steps where at least one core channel has a value.

| site | turbines | grid steps | steps with data | fault events | event_within_1h (all steps) | event_within_6h (all steps) | event_within_24h (all steps) | event_within_1h (steps with data) | event_within_6h (steps with data) | event_within_24h (steps with data) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kelmarsh | 6 | 2,817,246 | 2,784,159 | 1,054 | 0.168% | 0.746% | 2.520% | 0.163% | 0.683% | 2.385% |
| penmanshiel | 14 | 4,799,792 | 4,678,960 | 2,433 | 0.208% | 0.918% | 3.097% | 0.203% | 0.829% | 2.857% |
| hill_of_towie | 21 | 2,207,562 | 2,199,102 | 8,928 | 0.845% | 4.734% | 17.187% | 0.847% | 4.743% | 17.226% |
| care | 95 | 5,273,872 | 5,242,948 | 45 | 0.005% | 0.031% | 0.123% | 0.005% | 0.031% | 0.124% |

## Events: kelmarsh

| field | value |
| --- | --- |
| events by category | normal_operation: 342,845, environmental: 117,011, routine_procedure: 30,847, equipment_warning: 5,874, manual_operation: 2,641, grid_and_curtailment: 2,314, communication: 1,292, equipment_fault: 1,054, unmapped: 302 |

| field | value |
| --- | --- |
| status rows | 504,180 |
| distinct strings | 217 |
| unmapped rows | 302 (0.060%) |
| distinct strings unmapped | 90 |
| provider Stop rows unmapped | 186 of 7,049 (2.64%) |
| IEC Forced outage rows unmapped | 147 of 1,746 (8.42%) |
| provider Stop rows by configured category | routine_procedure: 3,930, manual_operation: 1,168, equipment_fault: 1,054, grid_and_curtailment: 603, unmapped: 186, environmental: 108 |

**Most frequent unmapped strings**

| string (normalized) | count | share |
| --- | --- | --- |
| high rotor speed nacelle | 17 | 12.59% |
| oscillation encoder tower | 17 | 12.59% |
| low hydraulic pressure | 11 | 8.15% |
| wind < power | 11 | 8.15% |
| frequency converter load rejection | 10 | 7.41% |
| manual operation generator fan 3 | 9 | 6.67% |
| manual operation lubrication rotorbearing | 9 | 6.67% |
| parameterized p red. | 9 | 6.67% |
| high temp. gear bearing 1 | 6 | 4.44% |
| manual operation gear bypass filter | 6 | 4.44% |
| manual operation gearbox heating module | 6 | 4.44% |
| overload gear bypass filter | 6 | 4.44% |
| overload transf. fan inlet air | 6 | 4.44% |
| pitch angle deviation | 6 | 4.44% |
| test brake program 180 | 6 | 4.44% |

## Events: penmanshiel

| field | value |
| --- | --- |
| events by category | normal_operation: 569,505, environmental: 199,526, routine_procedure: 48,339, equipment_warning: 7,374, grid_and_curtailment: 4,948, manual_operation: 4,163, equipment_fault: 2,433, communication: 2,424, unmapped: 591 |

| field | value |
| --- | --- |
| status rows | 839,303 |
| distinct strings | 231 |
| unmapped rows | 591 (0.070%) |
| distinct strings unmapped | 103 |
| provider Stop rows unmapped | 298 of 17,298 (1.72%) |
| IEC Forced outage rows unmapped | 184 of 5,141 (3.58%) |
| provider Stop rows by configured category | routine_procedure: 6,932, environmental: 3,539, equipment_fault: 2,433, manual_operation: 2,237, grid_and_curtailment: 1,859, unmapped: 298 |

**Most frequent unmapped strings**

| string (normalized) | count | share |
| --- | --- | --- |
| comm.err. iec server <- cms drive tr. | 20 | 8.77% |
| nat. tower freq. implausible | 20 | 8.77% |
| 4-20ma yaw current sensor | 18 | 7.89% |
| rotor rotation direction nacelle | 18 | 7.89% |
| oil filter gear choked | 16 | 7.02% |
| feedback brake 1 | 15 | 6.58% |
| pt100 base box temp. defect | 15 | 6.58% |
| test brake program 180 | 15 | 6.58% |
| parameter outside limits | 14 | 6.14% |
| pitch current asymmetry | 14 | 6.14% |
| overload gear bypass filter | 13 | 5.70% |
| set point><actual value axis 2 | 13 | 5.70% |
| test brake program 50 | 13 | 5.70% |
| high temp. gen. bearing 1 | 12 | 5.26% |
| set point><actual value axis 1 | 12 | 5.26% |

## Events: hill_of_towie

| field | value |
| --- | --- |
| events by category | shutdown: 8,928 |

| field | value |
| --- | --- |
| threshold (s) | 300 |
| downtime rows read (staged years and the year after) | 6,259,701 |
| down steps at the threshold | 297,641 |
| events at each threshold | 1 s: 16,216, 300 s: 8,928, 600 s: 4,780 |

**Downtime against the Stopping flag, threshold 1 s, window 1 step(s)**: 878,839 of 891,528 occurrences agree (98.58%); stopping codes 7,685 of 7,687 (99.97%); mean over codes 99.6%

| code | stopping | occurrences | showing downtime | agreeing | agreement |
| --- | --- | --- | --- | --- | --- |
| 20 | no | 441,896 | 5,932 | 435,964 | 98.7% |
| 25 | no | 441,895 | 6,755 | 435,140 | 98.5% |
| 3130 | yes | 2,977 | 2,976 | 2,976 | 100.0% |
| 1005 | yes | 2,744 | 2,743 | 2,743 | 100.0% |
| 10105 | yes | 1,508 | 1,508 | 1,508 | 100.0% |
| 8000 | yes | 232 | 232 | 232 | 100.0% |
| 8230 | yes | 226 | 226 | 226 | 100.0% |
| 102 | no | 50 | 0 | 50 | 100.0% |

**Downtime against the Stopping flag, threshold 300 s, window 1 step(s)**: 884,537 of 891,528 occurrences agree (99.22%); stopping codes 4,857 of 7,687 (63.18%); mean over codes 87.6%

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

**Downtime against the Stopping flag, threshold 600 s, window 1 step(s)**: 885,265 of 891,528 occurrences agree (99.30%); stopping codes 3,167 of 7,687 (41.20%); mean over codes 70.8%

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

## Events: care

| field | value |
| --- | --- |
| events by category | normal: 50, anomaly: 45 |
