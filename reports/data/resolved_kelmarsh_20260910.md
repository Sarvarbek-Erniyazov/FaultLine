# Resolved questions: kelmarsh

| field | value |
| --- | --- |
| source | kelmarsh |
| provider | Cubico Sustainable Investments Ltd |
| staged directory | C:\Users\sharg\Desktop\github\FaultLine\data\raw\telemetry\kelmarsh |
| turbine-years measured | 54 |
| timestamp column | Date and time |
| rows tested | rows carrying a value in at least one of 13 ingested columns |
| station column | none: one turbine per member |
| value-identical copies of a label dropped across files | not applicable |
| members read | 54 |
| label offset applied | 0 min |
| generated (UTC) | 2026-09-10T14:17:24+00:00 |
| git_sha | dded9436d9495c754c83ef750a1e20a95372ea46 |

## Power column unit

**VERDICT kW** - the median per-turbine-year p99.5 is 2,057.3, which sits on the rated power of 2,050 kW and is 6.0x the 341.7 kWh a 10-minute energy total would reach

| field | value |
| --- | --- |
| column measured | Power (kW) |
| separate energy column | Energy Export (kWh) |
| rated power (kW) | 2,050 |
| if the column is kW, the tail should be near | 2,050 |
| if it is kWh per step, near | 341.7 |
| measured median p99.5 | 2,057.3 |

| member | turbine | rows | with a value | p99.5 | max | min | energy p99.5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Turbine_Data_Kelmarsh_1_2016-01-03_-_2017-01-01_228.csv | Kelmarsh 1 | 52,416 | 48,485 | 2,046 | 2,072 | -16.65 | 395 |
| Turbine_Data_Kelmarsh_2_2016-01-03_-_2017-01-01_229.csv | Kelmarsh 2 | 52,416 | 48,483 | 2,054 | 2,068 | -17.71 | 408 |
| Turbine_Data_Kelmarsh_3_2016-01-03_-_2017-01-01_230.csv | Kelmarsh 3 | 52,416 | 47,492 | 2,042 | 2,069 | -15.41 | 376 |
| Turbine_Data_Kelmarsh_4_2016-01-03_-_2017-01-01_231.csv | Kelmarsh 4 | 52,416 | 46,882 | 2,039 | 2,069 | -15.5 | 380 |
| Turbine_Data_Kelmarsh_5_2016-01-03_-_2017-01-01_232.csv | Kelmarsh 5 | 52,416 | 47,755 | 2,031 | 2,072 | -16.9 | 364 |
| Turbine_Data_Kelmarsh_6_2016-01-03_-_2017-01-01_233.csv | Kelmarsh 6 | 52,416 | 46,596 | 1,967 | 2,064 | -17.21 | 345 |
| Turbine_Data_Kelmarsh_1_2017-01-01_-_2018-01-01_228.csv | Kelmarsh 1 | 52,560 | 51,932 | 2,057 | 2,076 | -15.62 | 409 |
| Turbine_Data_Kelmarsh_2_2017-01-01_-_2018-01-01_229.csv | Kelmarsh 2 | 52,560 | 52,205 | 2,059 | 2,080 | -16.06 | 410 |
| Turbine_Data_Kelmarsh_3_2017-01-01_-_2018-01-01_230.csv | Kelmarsh 3 | 52,560 | 52,008 | 2,056 | 2,078 | -15.99 | 408 |
| Turbine_Data_Kelmarsh_4_2017-01-01_-_2018-01-01_231.csv | Kelmarsh 4 | 52,560 | 52,015 | 2,058 | 2,081 | -16.77 | 409 |
| Turbine_Data_Kelmarsh_5_2017-01-01_-_2018-01-01_232.csv | Kelmarsh 5 | 52,560 | 52,071 | 2,056 | 2,073 | -16.22 | 408 |
| Turbine_Data_Kelmarsh_6_2017-01-01_-_2018-01-01_233.csv | Kelmarsh 6 | 52,560 | 51,542 | 2,051 | 2,073 | -16.76 | 404 |
| Turbine_Data_Kelmarsh_1_2018-01-01_-_2019-01-01_228.csv | Kelmarsh 1 | 52,560 | 50,755 | 2,058 | 2,080 | -16.34 | 409 |
| Turbine_Data_Kelmarsh_2_2018-01-01_-_2019-01-01_229.csv | Kelmarsh 2 | 52,560 | 50,745 | 2,059 | 2,078 | -17.41 | 409 |
| Turbine_Data_Kelmarsh_3_2018-01-01_-_2019-01-01_230.csv | Kelmarsh 3 | 52,560 | 50,611 | 2,058 | 2,075 | -16.57 | 409 |
| Turbine_Data_Kelmarsh_4_2018-01-01_-_2019-01-01_231.csv | Kelmarsh 4 | 52,560 | 50,743 | 2,059 | 2,079 | -18.45 | 409 |
| Turbine_Data_Kelmarsh_5_2018-01-01_-_2019-01-01_232.csv | Kelmarsh 5 | 52,560 | 50,754 | 2,054 | 2,084 | -20.69 | 408 |
| Turbine_Data_Kelmarsh_6_2018-01-01_-_2019-01-01_233.csv | Kelmarsh 6 | 52,560 | 50,750 | 2,052 | 2,079 | -16.87 | 406 |
| Turbine_Data_Kelmarsh_1_2019-01-01_-_2020-01-01_228.csv | Kelmarsh 1 | 52,560 | 52,476 | 2,058 | 2,081 | -17.85 | 409 |
| Turbine_Data_Kelmarsh_2_2019-01-01_-_2020-01-01_229.csv | Kelmarsh 2 | 52,560 | 52,489 | 2,059 | 2,076 | -15.82 | 409 |
| Turbine_Data_Kelmarsh_3_2019-01-01_-_2020-01-01_230.csv | Kelmarsh 3 | 52,560 | 52,488 | 2,058 | 2,079 | -16.15 | 409 |
| Turbine_Data_Kelmarsh_4_2019-01-01_-_2020-01-01_231.csv | Kelmarsh 4 | 52,560 | 52,506 | 2,057 | 2,083 | -18.1 | 409 |
| Turbine_Data_Kelmarsh_5_2019-01-01_-_2020-01-01_232.csv | Kelmarsh 5 | 52,560 | 52,479 | 2,055 | 2,077 | -21.17 | 408 |
| Turbine_Data_Kelmarsh_6_2019-01-01_-_2020-01-01_233.csv | Kelmarsh 6 | 52,560 | 52,506 | 2,052 | 2,087 | -16.12 | 407 |
| Turbine_Data_Kelmarsh_1_2020-01-01_-_2021-01-01_228.csv | Kelmarsh 1 | 52,704 | 52,236 | 2,061 | 2,079 | -16.49 | 410 |
| Turbine_Data_Kelmarsh_2_2020-01-01_-_2021-01-01_229.csv | Kelmarsh 2 | 52,704 | 52,253 | 2,062 | 2,081 | -14.49 | 410 |
| Turbine_Data_Kelmarsh_3_2020-01-01_-_2021-01-01_230.csv | Kelmarsh 3 | 52,704 | 52,209 | 2,061 | 2,080 | -14.17 | 409 |
| Turbine_Data_Kelmarsh_4_2020-01-01_-_2021-01-01_231.csv | Kelmarsh 4 | 52,704 | 52,244 | 2,061 | 2,083 | -16.49 | 410 |
| Turbine_Data_Kelmarsh_5_2020-01-01_-_2021-01-01_232.csv | Kelmarsh 5 | 52,704 | 52,248 | 2,059 | 2,082 | -16.78 | 409 |
| Turbine_Data_Kelmarsh_6_2020-01-01_-_2021-01-01_233.csv | Kelmarsh 6 | 52,704 | 52,250 | 2,056 | 2,075 | -16.71 | 408 |
| Turbine_Data_Kelmarsh_1_2021-01-01_-_2022-01-01_228.csv | Kelmarsh 1 | 52,560 | 52,050 | 2,057 | 2,076 | -17.01 | 409 |
| Turbine_Data_Kelmarsh_2_2021-01-01_-_2022-01-01_229.csv | Kelmarsh 2 | 52,560 | 52,042 | 2,060 | 2,075 | -16.8 | 410 |
| Turbine_Data_Kelmarsh_3_2021-01-01_-_2022-01-01_230.csv | Kelmarsh 3 | 52,560 | 51,573 | 2,058 | 2,075 | -15.72 | 409 |
| Turbine_Data_Kelmarsh_4_2021-01-01_-_2022-01-01_231.csv | Kelmarsh 4 | 52,560 | 52,038 | 2,058 | 2,078 | -16.14 | 409 |
| Turbine_Data_Kelmarsh_5_2021-01-01_-_2022-01-01_232.csv | Kelmarsh 5 | 52,560 | 51,467 | 2,056 | 2,077 | -16.39 | 408 |
| Turbine_Data_Kelmarsh_6_2021-01-01_-_2022-01-01_233.csv | Kelmarsh 6 | 52,560 | 52,017 | 2,049 | 2,071 | -17.79 | 405 |
| Turbine_Data_Kelmarsh_1_2022-01-01_-_2023-01-01_228.csv | Kelmarsh 1 | 52,560 | 52,010 | 2,058 | 2,083 | -17.22 | 409 |
| Turbine_Data_Kelmarsh_2_2022-01-01_-_2023-01-01_229.csv | Kelmarsh 2 | 52,560 | 52,488 | 2,059 | 2,080 | -17.64 | 409 |
| Turbine_Data_Kelmarsh_3_2022-01-01_-_2023-01-01_230.csv | Kelmarsh 3 | 52,560 | 52,448 | 2,057 | 2,081 | -16.35 | 408 |
| Turbine_Data_Kelmarsh_4_2022-01-01_-_2023-01-01_231.csv | Kelmarsh 4 | 52,560 | 52,327 | 2,052 | 2,076 | -15.92 | 406 |
| Turbine_Data_Kelmarsh_5_2022-01-01_-_2023-01-01_232.csv | Kelmarsh 5 | 52,560 | 52,449 | 2,056 | 2,078 | -15.19 | 408 |
| Turbine_Data_Kelmarsh_6_2022-01-01_-_2023-01-01_233.csv | Kelmarsh 6 | 52,560 | 52,324 | 2,050 | 2,076 | -17.78 | 405 |
| Turbine_Data_Kelmarsh_1_2023-01-01_-_2024-01-01_228.csv | Kelmarsh 1 | 2,174,760 | 52,477 | 2,058 | 2,077 | -15.46 | 409 |
| Turbine_Data_Kelmarsh_2_2023-01-01_-_2024-01-01_229.csv | Kelmarsh 2 | 2,174,760 | 52,479 | 2,059 | 2,082 | -17.25 | 409 |
| Turbine_Data_Kelmarsh_3_2023-01-01_-_2024-01-01_230.csv | Kelmarsh 3 | 2,174,760 | 52,306 | 2,058 | 2,079 | -16.06 | 409 |
| Turbine_Data_Kelmarsh_4_2023-01-01_-_2024-01-01_231.csv | Kelmarsh 4 | 2,174,760 | 52,331 | 2,058 | 2,081 | -16.67 | 409 |
| Turbine_Data_Kelmarsh_5_2023-01-01_-_2024-01-01_232.csv | Kelmarsh 5 | 2,174,760 | 52,454 | 2,057 | 2,080 | -14.91 | 409 |
| Turbine_Data_Kelmarsh_6_2023-01-01_-_2024-01-01_233.csv | Kelmarsh 6 | 2,174,760 | 52,261 | 2,052 | 2,073 | -16.85 | 406 |
| Turbine_Data_Kelmarsh_1_2024-01-01_-_2025-01-01_228.csv | Kelmarsh 1 | 2,174,904 | 52,574 | 2,058 | 2,075 | -16.42 | 409 |
| Turbine_Data_Kelmarsh_2_2024-01-01_-_2025-01-01_229.csv | Kelmarsh 2 | 2,174,904 | 52,604 | 2,060 | 2,079 | -17.42 | 410 |
| Turbine_Data_Kelmarsh_3_2024-01-01_-_2025-01-01_230.csv | Kelmarsh 3 | 2,174,904 | 52,575 | 2,058 | 2,079 | -19.28 | 409 |
| Turbine_Data_Kelmarsh_4_2024-01-01_-_2025-01-01_231.csv | Kelmarsh 4 | 2,174,904 | 52,293 | 2,057 | 2,077 | -16.02 | 409 |
| Turbine_Data_Kelmarsh_5_2024-01-01_-_2025-01-01_232.csv | Kelmarsh 5 | 2,174,904 | 52,493 | 2,056 | 2,083 | -19.33 | 408 |
| Turbine_Data_Kelmarsh_6_2024-01-01_-_2025-01-01_233.csv | Kelmarsh 6 | 2,174,904 | 51,868 | 2,054 | 2,089 | -14.24 | 407 |

## Timestamp timezone

**VERDICT UTC** - across 54 turbine-years, every spring-forward hour is fully populated and no autumn fall-back hour repeats a timestamp -- neither fingerprint that Europe/London would leave is present; both halves applied to every turbine-year

| field | value |
| --- | --- |
| column measured | Date and time |
| candidate local zone | Europe/London |
| declared in the source specification | UTC |

A local-time series is missing every observation in the spring-forward hour and repeats every label in the autumn fall-back hour. A UTC series does neither. The test runs on the rows that carry a value in at least one ingested column, which is what the ingest keeps. `steps in spring hour` counts distinct labels out of the six a 10-minute grid holds. `repeated steps` reads `n/a` where labels still repeat outside the fall-back hour after that drop, because the test cannot then tell a fall-back from that.

| member | turbine | year | rows | distinct | rows with a value | duplicate labels among them | spring hour (local) | steps in spring hour | autumn hour (local) | repeated steps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Turbine_Data_Kelmarsh_1_2016-01-03_-_2017-01-01_228.csv | Kelmarsh 1 | 2,016 | 52,416 | 52,416 | 48,485 | 0 | 2016-03-27 01 | 6 | 2016-10-30 01 | 0 |
| Turbine_Data_Kelmarsh_2_2016-01-03_-_2017-01-01_229.csv | Kelmarsh 2 | 2,016 | 52,416 | 52,416 | 48,483 | 0 | 2016-03-27 01 | 6 | 2016-10-30 01 | 0 |
| Turbine_Data_Kelmarsh_3_2016-01-03_-_2017-01-01_230.csv | Kelmarsh 3 | 2,016 | 52,416 | 52,416 | 47,492 | 0 | 2016-03-27 01 | 6 | 2016-10-30 01 | 0 |
| Turbine_Data_Kelmarsh_4_2016-01-03_-_2017-01-01_231.csv | Kelmarsh 4 | 2,016 | 52,416 | 52,416 | 46,882 | 0 | 2016-03-27 01 | 6 | 2016-10-30 01 | 0 |
| Turbine_Data_Kelmarsh_5_2016-01-03_-_2017-01-01_232.csv | Kelmarsh 5 | 2,016 | 52,416 | 52,416 | 47,755 | 0 | 2016-03-27 01 | 6 | 2016-10-30 01 | 0 |
| Turbine_Data_Kelmarsh_6_2016-01-03_-_2017-01-01_233.csv | Kelmarsh 6 | 2,016 | 52,416 | 52,416 | 46,596 | 0 | 2016-03-27 01 | 6 | 2016-10-30 01 | 0 |
| Turbine_Data_Kelmarsh_1_2017-01-01_-_2018-01-01_228.csv | Kelmarsh 1 | 2,017 | 52,560 | 52,560 | 51,932 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Kelmarsh_2_2017-01-01_-_2018-01-01_229.csv | Kelmarsh 2 | 2,017 | 52,560 | 52,560 | 52,205 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Kelmarsh_3_2017-01-01_-_2018-01-01_230.csv | Kelmarsh 3 | 2,017 | 52,560 | 52,560 | 52,008 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Kelmarsh_4_2017-01-01_-_2018-01-01_231.csv | Kelmarsh 4 | 2,017 | 52,560 | 52,560 | 52,015 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Kelmarsh_5_2017-01-01_-_2018-01-01_232.csv | Kelmarsh 5 | 2,017 | 52,560 | 52,560 | 52,071 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Kelmarsh_6_2017-01-01_-_2018-01-01_233.csv | Kelmarsh 6 | 2,017 | 52,560 | 52,560 | 51,542 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Kelmarsh_1_2018-01-01_-_2019-01-01_228.csv | Kelmarsh 1 | 2,018 | 52,560 | 52,560 | 50,755 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Kelmarsh_2_2018-01-01_-_2019-01-01_229.csv | Kelmarsh 2 | 2,018 | 52,560 | 52,560 | 50,745 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Kelmarsh_3_2018-01-01_-_2019-01-01_230.csv | Kelmarsh 3 | 2,018 | 52,560 | 52,560 | 50,611 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Kelmarsh_4_2018-01-01_-_2019-01-01_231.csv | Kelmarsh 4 | 2,018 | 52,560 | 52,560 | 50,743 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Kelmarsh_5_2018-01-01_-_2019-01-01_232.csv | Kelmarsh 5 | 2,018 | 52,560 | 52,560 | 50,754 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Kelmarsh_6_2018-01-01_-_2019-01-01_233.csv | Kelmarsh 6 | 2,018 | 52,560 | 52,560 | 50,750 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Kelmarsh_1_2019-01-01_-_2020-01-01_228.csv | Kelmarsh 1 | 2,019 | 52,560 | 52,560 | 52,476 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Kelmarsh_2_2019-01-01_-_2020-01-01_229.csv | Kelmarsh 2 | 2,019 | 52,560 | 52,560 | 52,489 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Kelmarsh_3_2019-01-01_-_2020-01-01_230.csv | Kelmarsh 3 | 2,019 | 52,560 | 52,560 | 52,488 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Kelmarsh_4_2019-01-01_-_2020-01-01_231.csv | Kelmarsh 4 | 2,019 | 52,560 | 52,560 | 52,506 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Kelmarsh_5_2019-01-01_-_2020-01-01_232.csv | Kelmarsh 5 | 2,019 | 52,560 | 52,560 | 52,479 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Kelmarsh_6_2019-01-01_-_2020-01-01_233.csv | Kelmarsh 6 | 2,019 | 52,560 | 52,560 | 52,506 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Kelmarsh_1_2020-01-01_-_2021-01-01_228.csv | Kelmarsh 1 | 2,020 | 52,704 | 52,704 | 52,236 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Kelmarsh_2_2020-01-01_-_2021-01-01_229.csv | Kelmarsh 2 | 2,020 | 52,704 | 52,704 | 52,253 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Kelmarsh_3_2020-01-01_-_2021-01-01_230.csv | Kelmarsh 3 | 2,020 | 52,704 | 52,704 | 52,210 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Kelmarsh_4_2020-01-01_-_2021-01-01_231.csv | Kelmarsh 4 | 2,020 | 52,704 | 52,704 | 52,244 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Kelmarsh_5_2020-01-01_-_2021-01-01_232.csv | Kelmarsh 5 | 2,020 | 52,704 | 52,704 | 52,249 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Kelmarsh_6_2020-01-01_-_2021-01-01_233.csv | Kelmarsh 6 | 2,020 | 52,704 | 52,704 | 52,251 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Kelmarsh_1_2021-01-01_-_2022-01-01_228.csv | Kelmarsh 1 | 2,021 | 52,560 | 52,560 | 52,050 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Kelmarsh_2_2021-01-01_-_2022-01-01_229.csv | Kelmarsh 2 | 2,021 | 52,560 | 52,560 | 52,042 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Kelmarsh_3_2021-01-01_-_2022-01-01_230.csv | Kelmarsh 3 | 2,021 | 52,560 | 52,560 | 51,573 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Kelmarsh_4_2021-01-01_-_2022-01-01_231.csv | Kelmarsh 4 | 2,021 | 52,560 | 52,560 | 52,038 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Kelmarsh_5_2021-01-01_-_2022-01-01_232.csv | Kelmarsh 5 | 2,021 | 52,560 | 52,560 | 51,467 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Kelmarsh_6_2021-01-01_-_2022-01-01_233.csv | Kelmarsh 6 | 2,021 | 52,560 | 52,560 | 52,017 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Kelmarsh_1_2022-01-01_-_2023-01-01_228.csv | Kelmarsh 1 | 2,022 | 52,560 | 52,560 | 52,010 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Kelmarsh_2_2022-01-01_-_2023-01-01_229.csv | Kelmarsh 2 | 2,022 | 52,560 | 52,560 | 52,488 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Kelmarsh_3_2022-01-01_-_2023-01-01_230.csv | Kelmarsh 3 | 2,022 | 52,560 | 52,560 | 52,448 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Kelmarsh_4_2022-01-01_-_2023-01-01_231.csv | Kelmarsh 4 | 2,022 | 52,560 | 52,560 | 52,327 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Kelmarsh_5_2022-01-01_-_2023-01-01_232.csv | Kelmarsh 5 | 2,022 | 52,560 | 52,560 | 52,449 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Kelmarsh_6_2022-01-01_-_2023-01-01_233.csv | Kelmarsh 6 | 2,022 | 52,560 | 52,560 | 52,324 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Kelmarsh_1_2023-01-01_-_2024-01-01_228.csv | Kelmarsh 1 | 2,023 | 2,174,760 | 52,560 | 52,477 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| Turbine_Data_Kelmarsh_2_2023-01-01_-_2024-01-01_229.csv | Kelmarsh 2 | 2,023 | 2,174,760 | 52,560 | 52,479 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| Turbine_Data_Kelmarsh_3_2023-01-01_-_2024-01-01_230.csv | Kelmarsh 3 | 2,023 | 2,174,760 | 52,560 | 52,306 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| Turbine_Data_Kelmarsh_4_2023-01-01_-_2024-01-01_231.csv | Kelmarsh 4 | 2,023 | 2,174,760 | 52,560 | 52,331 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| Turbine_Data_Kelmarsh_5_2023-01-01_-_2024-01-01_232.csv | Kelmarsh 5 | 2,023 | 2,174,760 | 52,560 | 52,454 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| Turbine_Data_Kelmarsh_6_2023-01-01_-_2024-01-01_233.csv | Kelmarsh 6 | 2,023 | 2,174,760 | 52,560 | 52,261 | 0 | 2023-03-26 01 | 6 | 2023-10-29 01 | 0 |
| Turbine_Data_Kelmarsh_1_2024-01-01_-_2025-01-01_228.csv | Kelmarsh 1 | 2,024 | 2,174,904 | 52,704 | 52,574 | 0 | 2024-03-31 01 | 6 | 2024-10-27 01 | 0 |
| Turbine_Data_Kelmarsh_2_2024-01-01_-_2025-01-01_229.csv | Kelmarsh 2 | 2,024 | 2,174,904 | 52,704 | 52,604 | 0 | 2024-03-31 01 | 6 | 2024-10-27 01 | 0 |
| Turbine_Data_Kelmarsh_3_2024-01-01_-_2025-01-01_230.csv | Kelmarsh 3 | 2,024 | 2,174,904 | 52,704 | 52,575 | 0 | 2024-03-31 01 | 6 | 2024-10-27 01 | 0 |
| Turbine_Data_Kelmarsh_4_2024-01-01_-_2025-01-01_231.csv | Kelmarsh 4 | 2,024 | 2,174,904 | 52,704 | 52,293 | 0 | 2024-03-31 01 | 6 | 2024-10-27 01 | 0 |
| Turbine_Data_Kelmarsh_5_2024-01-01_-_2025-01-01_232.csv | Kelmarsh 5 | 2,024 | 2,174,904 | 52,704 | 52,493 | 0 | 2024-03-31 01 | 6 | 2024-10-27 01 | 0 |
| Turbine_Data_Kelmarsh_6_2024-01-01_-_2025-01-01_233.csv | Kelmarsh 6 | 2,024 | 2,174,904 | 52,704 | 51,868 | 0 | 2024-03-31 01 | 6 | 2024-10-27 01 | 0 |

## Repeated timestamp labels

12 of 54 members repeat their timestamp labels. The worst is `Turbine_Data_Kelmarsh_1_2023-01-01_-_2024-01-01_228.csv`: 2,174,760 rows over 52,560 distinct labels, a factor of 41.4.

This is an export-format change and not duplicated data. Once the rows that carry no ingested value are dropped, every label occurs once (`rows with a value` equals `distinct`, and there are no duplicate labels among them), so the autumn half of the test above applies to these members as well. Read across every column of the file, the repeated rows carry values in 9 column(s) -- `Equivalent Full Load Hours (s)`, `Production-based Contractual Avail.`, `Production-based Contractual Avail. (Custom)`, `Production-based Contractual Avail. (Global)`, `Production-based IEC B.2.2 (Users View)`, `Production-based IEC B.2.3 (Users View)`, `Production-based IEC B.3.2 (Manufacturers View)`, `Production-based System Avail.`, `Production-based System Avail. (virtual)` -- and not one of those values differs from the value on the label's other rows. None of them is an ingested channel.

The ingest collapses these files only after asserting the same thing for the channels it reads (`src/faultline/data/telemetry/collapse.py`), and stops if a label carries two values.

| member | rows | distinct labels | factor | rows with a value |
| --- | --- | --- | --- | --- |
| Turbine_Data_Kelmarsh_1_2023-01-01_-_2024-01-01_228.csv | 2,174,760 | 52,560 | 41.4 | 52,477 |
| Turbine_Data_Kelmarsh_2_2023-01-01_-_2024-01-01_229.csv | 2,174,760 | 52,560 | 41.4 | 52,479 |
| Turbine_Data_Kelmarsh_3_2023-01-01_-_2024-01-01_230.csv | 2,174,760 | 52,560 | 41.4 | 52,306 |
| Turbine_Data_Kelmarsh_4_2023-01-01_-_2024-01-01_231.csv | 2,174,760 | 52,560 | 41.4 | 52,331 |
| Turbine_Data_Kelmarsh_5_2023-01-01_-_2024-01-01_232.csv | 2,174,760 | 52,560 | 41.4 | 52,454 |
| Turbine_Data_Kelmarsh_6_2023-01-01_-_2024-01-01_233.csv | 2,174,760 | 52,560 | 41.4 | 52,261 |
| Turbine_Data_Kelmarsh_1_2024-01-01_-_2025-01-01_228.csv | 2,174,904 | 52,704 | 41.3 | 52,574 |
| Turbine_Data_Kelmarsh_2_2024-01-01_-_2025-01-01_229.csv | 2,174,904 | 52,704 | 41.3 | 52,604 |
| Turbine_Data_Kelmarsh_3_2024-01-01_-_2025-01-01_230.csv | 2,174,904 | 52,704 | 41.3 | 52,575 |
| Turbine_Data_Kelmarsh_4_2024-01-01_-_2025-01-01_231.csv | 2,174,904 | 52,704 | 41.3 | 52,293 |
| Turbine_Data_Kelmarsh_5_2024-01-01_-_2025-01-01_232.csv | 2,174,904 | 52,704 | 41.3 | 52,493 |
| Turbine_Data_Kelmarsh_6_2024-01-01_-_2025-01-01_233.csv | 2,174,904 | 52,704 | 41.3 | 51,868 |

| member | columns read | columns with values on repeated rows | columns whose repeated values differ |
| --- | --- | --- | --- |
| Turbine_Data_Kelmarsh_1_2023-01-01_-_2024-01-01_228.csv | 311 | 9 | 0 |
| Turbine_Data_Kelmarsh_2_2023-01-01_-_2024-01-01_229.csv | 311 | 9 | 0 |
| Turbine_Data_Kelmarsh_3_2023-01-01_-_2024-01-01_230.csv | 311 | 9 | 0 |
| Turbine_Data_Kelmarsh_4_2023-01-01_-_2024-01-01_231.csv | 311 | 9 | 0 |
| Turbine_Data_Kelmarsh_5_2023-01-01_-_2024-01-01_232.csv | 311 | 9 | 0 |
| Turbine_Data_Kelmarsh_6_2023-01-01_-_2024-01-01_233.csv | 311 | 9 | 0 |
| Turbine_Data_Kelmarsh_1_2024-01-01_-_2025-01-01_228.csv | 311 | 9 | 0 |
| Turbine_Data_Kelmarsh_2_2024-01-01_-_2025-01-01_229.csv | 311 | 9 | 0 |
| Turbine_Data_Kelmarsh_3_2024-01-01_-_2025-01-01_230.csv | 311 | 9 | 0 |
| Turbine_Data_Kelmarsh_4_2024-01-01_-_2025-01-01_231.csv | 311 | 9 | 0 |
| Turbine_Data_Kelmarsh_5_2024-01-01_-_2025-01-01_232.csv | 311 | 9 | 0 |
| Turbine_Data_Kelmarsh_6_2024-01-01_-_2025-01-01_233.csv | 311 | 9 | 0 |
