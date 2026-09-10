# Resolved questions: hill_of_towie

| field | value |
| --- | --- |
| source | hill_of_towie |
| provider | RES on behalf of TRIG |
| staged directory | C:\Users\sharg\Desktop\github\FaultLine\data\raw\telemetry\hill_of_towie |
| turbine-years measured | 42 |
| timestamp column | TimeStamp |
| rows tested | rows carrying a value in at least one of 1 ingested columns |
| station column | StationId |
| value-identical copies of a label dropped across files | 460 (the shared boundary label of consecutive monthly files) |
| members read | 24 (tblSCTurGrid_*) |
| label offset applied | -10 min (interval-end labels moved to interval start) |
| generated (UTC) | 2026-09-10T13:49:09+00:00 |
| git_sha | dded9436d9495c754c83ef750a1e20a95372ea46 |

## Power column unit

**VERDICT kW** - the median per-turbine-year p99.5 is 2,299.2, which sits on the rated power of 2,300 kW and is 6.0x the 383.3 kWh a 10-minute energy total would reach

| field | value |
| --- | --- |
| column measured | wtc_ActPower_mean |
| separate energy column | none found in this export |
| rated power (kW) | 2,300 |
| if the column is kW, the tail should be near | 2,300 |
| if it is kWh per step, near | 383.3 |
| measured median p99.5 | 2,299.2 |

| member | turbine | rows | with a value | p99.5 | max | min | energy p99.5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tblSCTurGrid_2019_* station 2304510 | T01 | 52,189 | 52,189 | 2,299 | 2,302 | -23.09 | n/a |
| tblSCTurGrid_2019_* station 2304511 | T02 | 52,499 | 52,499 | 2,297 | 2,303 | -21.41 | n/a |
| tblSCTurGrid_2019_* station 2304512 | T03 | 52,499 | 52,499 | 2,300 | 2,303 | -21.78 | n/a |
| tblSCTurGrid_2019_* station 2304513 | T04 | 52,050 | 52,050 | 2,300 | 2,302 | -19.52 | n/a |
| tblSCTurGrid_2019_* station 2304514 | T05 | 52,498 | 52,498 | 2,299 | 2,302 | -22.62 | n/a |
| tblSCTurGrid_2019_* station 2304515 | T06 | 52,355 | 52,346 | 2,296 | 2,302 | -21.27 | n/a |
| tblSCTurGrid_2019_* station 2304516 | T07 | 52,432 | 52,432 | 2,300 | 2,303 | -21.8 | n/a |
| tblSCTurGrid_2019_* station 2304517 | T08 | 52,484 | 52,484 | 2,300 | 2,302 | -20.96 | n/a |
| tblSCTurGrid_2019_* station 2304518 | T09 | 52,498 | 52,498 | 2,300 | 2,302 | -20.5 | n/a |
| tblSCTurGrid_2019_* station 2304519 | T10 | 52,500 | 52,500 | 2,296 | 2,302 | -18.95 | n/a |
| tblSCTurGrid_2019_* station 2304520 | T11 | 52,479 | 52,479 | 2,300 | 2,303 | -19.79 | n/a |
| tblSCTurGrid_2019_* station 2304521 | T12 | 52,503 | 52,503 | 2,300 | 2,302 | -21.97 | n/a |
| tblSCTurGrid_2019_* station 2304522 | T13 | 52,497 | 52,497 | 2,301 | 2,303 | -19.81 | n/a |
| tblSCTurGrid_2019_* station 2304523 | T14 | 52,469 | 52,469 | 2,300 | 2,303 | -19.42 | n/a |
| tblSCTurGrid_2019_* station 2304524 | T15 | 52,494 | 52,494 | 2,291 | 2,302 | -21.36 | n/a |
| tblSCTurGrid_2019_* station 2304525 | T16 | 52,499 | 52,499 | 2,145 | 2,299 | -21.06 | n/a |
| tblSCTurGrid_2019_* station 2304526 | T17 | 52,493 | 52,492 | 2,292 | 2,302 | -22.09 | n/a |
| tblSCTurGrid_2019_* station 2304527 | T18 | 52,484 | 52,484 | 2,294 | 2,302 | -21.86 | n/a |
| tblSCTurGrid_2019_* station 2304528 | T19 | 52,491 | 52,491 | 2,299 | 2,302 | -20.05 | n/a |
| tblSCTurGrid_2019_* station 2304529 | T20 | 52,491 | 52,491 | 2,299 | 2,302 | -19.94 | n/a |
| tblSCTurGrid_2019_* station 2304530 | T21 | 51,761 | 51,761 | 2,300 | 2,304 | -20.37 | n/a |
| tblSCTurGrid_2023_* station 2304510 | T01 | 52,508 | 52,507 | 2,299 | 2,303 | -21.35 | n/a |
| tblSCTurGrid_2023_* station 2304511 | T02 | 52,517 | 52,517 | 2,296 | 2,302 | -22.63 | n/a |
| tblSCTurGrid_2023_* station 2304512 | T03 | 52,524 | 52,524 | 2,300 | 2,303 | -21.56 | n/a |
| tblSCTurGrid_2023_* station 2304513 | T04 | 52,525 | 52,513 | 2,299 | 2,303 | -21.57 | n/a |
| tblSCTurGrid_2023_* station 2304514 | T05 | 51,934 | 51,924 | 2,297 | 2,302 | -23.66 | n/a |
| tblSCTurGrid_2023_* station 2304515 | T06 | 52,510 | 52,510 | 2,293 | 2,302 | -22 | n/a |
| tblSCTurGrid_2023_* station 2304516 | T07 | 52,086 | 52,080 | 2,300 | 2,304 | -23.24 | n/a |
| tblSCTurGrid_2023_* station 2304517 | T08 | 52,268 | 52,261 | 2,299 | 2,302 | -19.82 | n/a |
| tblSCTurGrid_2023_* station 2304518 | T09 | 52,508 | 52,508 | 2,300 | 2,302 | -22.75 | n/a |
| tblSCTurGrid_2023_* station 2304519 | T10 | 52,511 | 52,511 | 2,298 | 2,301 | -20.63 | n/a |
| tblSCTurGrid_2023_* station 2304520 | T11 | 52,378 | 52,362 | 2,300 | 2,304 | -20.82 | n/a |
| tblSCTurGrid_2023_* station 2304521 | T12 | 52,491 | 52,487 | 2,300 | 2,303 | -21.68 | n/a |
| tblSCTurGrid_2023_* station 2304522 | T13 | 52,235 | 52,233 | 2,300 | 2,311 | -21.6 | n/a |
| tblSCTurGrid_2023_* station 2304523 | T14 | 52,533 | 52,533 | 2,300 | 2,302 | -21.37 | n/a |
| tblSCTurGrid_2023_* station 2304524 | T15 | 52,465 | 52,459 | 2,292 | 2,302 | -20.98 | n/a |
| tblSCTurGrid_2023_* station 2304525 | T16 | 50,347 | 50,347 | 2,292 | 2,301 | -36.54 | n/a |
| tblSCTurGrid_2023_* station 2304526 | T17 | 52,361 | 52,361 | 2,297 | 2,302 | -21.26 | n/a |
| tblSCTurGrid_2023_* station 2304527 | T18 | 52,524 | 52,523 | 2,298 | 2,302 | -22.35 | n/a |
| tblSCTurGrid_2023_* station 2304528 | T19 | 52,273 | 52,202 | 2,299 | 2,302 | -19.98 | n/a |
| tblSCTurGrid_2023_* station 2304529 | T20 | 52,517 | 52,517 | 2,299 | 2,302 | -20.9 | n/a |
| tblSCTurGrid_2023_* station 2304530 | T21 | 52,549 | 52,549 | 2,300 | 2,303 | -23.92 | n/a |

## Timestamp timezone

**VERDICT UTC** - across 42 turbine-years, every spring-forward hour is fully populated and no autumn fall-back hour repeats a timestamp -- neither fingerprint that Europe/London would leave is present; both halves applied to every turbine-year

| field | value |
| --- | --- |
| column measured | TimeStamp |
| candidate local zone | Europe/London |
| declared in the source specification | TODO(m1): confirm from Hill_of_Towie_tables_description.csv |

A local-time series is missing every observation in the spring-forward hour and repeats every label in the autumn fall-back hour. A UTC series does neither. The test runs on the rows that carry a value in at least one ingested column, which is what the ingest keeps. `steps in spring hour` counts distinct labels out of the six a 10-minute grid holds. `repeated steps` reads `n/a` where labels still repeat outside the fall-back hour after that drop, because the test cannot then tell a fall-back from that.

| member | turbine | year | rows | distinct | rows with a value | duplicate labels among them | spring hour (local) | steps in spring hour | autumn hour (local) | repeated steps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tblSCTurGrid_2019_* station 2304510 | T01 | 2,019 | 52,189 | 52,189 | 52,189 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304511 | T02 | 2,019 | 52,499 | 52,499 | 52,499 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304512 | T03 | 2,019 | 52,499 | 52,499 | 52,499 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304513 | T04 | 2,019 | 52,050 | 52,050 | 52,050 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304514 | T05 | 2,019 | 52,498 | 52,498 | 52,498 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304515 | T06 | 2,019 | 52,355 | 52,355 | 52,346 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304516 | T07 | 2,019 | 52,432 | 52,432 | 52,432 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304517 | T08 | 2,019 | 52,484 | 52,484 | 52,484 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304518 | T09 | 2,019 | 52,498 | 52,498 | 52,498 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304519 | T10 | 2,019 | 52,500 | 52,500 | 52,500 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304520 | T11 | 2,019 | 52,479 | 52,479 | 52,479 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304521 | T12 | 2,019 | 52,503 | 52,503 | 52,503 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304522 | T13 | 2,019 | 52,497 | 52,497 | 52,497 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304523 | T14 | 2,019 | 52,469 | 52,469 | 52,469 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304524 | T15 | 2,019 | 52,494 | 52,494 | 52,494 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304525 | T16 | 2,019 | 52,499 | 52,499 | 52,499 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304526 | T17 | 2,019 | 52,493 | 52,493 | 52,492 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304527 | T18 | 2,019 | 52,484 | 52,484 | 52,484 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304528 | T19 | 2,019 | 52,491 | 52,491 | 52,491 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304529 | T20 | 2,019 | 52,491 | 52,491 | 52,491 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2019_* station 2304530 | T21 | 2,019 | 51,761 | 51,761 | 51,761 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| tblSCTurGrid_2023_* station 2304510 | T01 | 2,023 | 52,508 | 52,508 | 52,507 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304511 | T02 | 2,023 | 52,517 | 52,517 | 52,517 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304512 | T03 | 2,023 | 52,524 | 52,524 | 52,524 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304513 | T04 | 2,023 | 52,525 | 52,525 | 52,513 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304514 | T05 | 2,023 | 51,934 | 51,934 | 51,924 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304515 | T06 | 2,023 | 52,510 | 52,510 | 52,510 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304516 | T07 | 2,023 | 52,086 | 52,086 | 52,080 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304517 | T08 | 2,023 | 52,268 | 52,268 | 52,261 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304518 | T09 | 2,023 | 52,508 | 52,508 | 52,508 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304519 | T10 | 2,023 | 52,511 | 52,511 | 52,511 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304520 | T11 | 2,023 | 52,378 | 52,378 | 52,362 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304521 | T12 | 2,023 | 52,491 | 52,491 | 52,487 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304522 | T13 | 2,023 | 52,235 | 52,235 | 52,233 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304523 | T14 | 2,023 | 52,533 | 52,533 | 52,533 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304524 | T15 | 2,023 | 52,465 | 52,465 | 52,459 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304525 | T16 | 2,023 | 50,347 | 50,347 | 50,347 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304526 | T17 | 2,023 | 52,361 | 52,361 | 52,361 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304527 | T18 | 2,023 | 52,524 | 52,524 | 52,523 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304528 | T19 | 2,023 | 52,273 | 52,273 | 52,202 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304529 | T20 | 2,023 | 52,517 | 52,517 | 52,517 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| tblSCTurGrid_2023_* station 2304530 | T21 | 2,023 | 52,549 | 52,549 | 52,549 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
