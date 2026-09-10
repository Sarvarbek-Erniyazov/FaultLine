# Resolved questions: penmanshiel

| field | value |
| --- | --- |
| source | penmanshiel |
| provider | Cubico Sustainable Investments Ltd |
| staged directory | C:\Users\sharg\Desktop\github\FaultLine\data\raw\telemetry\penmanshiel |
| turbine-years measured | 98 |
| timestamp column | Date and time |
| rows tested | rows carrying a value in at least one of 13 ingested columns |
| station column | none: one turbine per member |
| value-identical copies of a label dropped across files | not applicable |
| members read | 98 |
| label offset applied | 0 min |
| generated (UTC) | 2026-09-10T13:54:16+00:00 |
| git_sha | dded9436d9495c754c83ef750a1e20a95372ea46 |

## Power column unit

**VERDICT kW** - the median per-turbine-year p99.5 is 2,056.0, which sits on the rated power of 2,050 kW and is 6.0x the 341.7 kWh a 10-minute energy total would reach

| field | value |
| --- | --- |
| column measured | Power (kW) |
| separate energy column | Energy Export (kWh) |
| rated power (kW) | 2,050 |
| if the column is kW, the tail should be near | 2,050 |
| if it is kWh per step, near | 341.7 |
| measured median p99.5 | 2,056.0 |

| member | turbine | rows | with a value | p99.5 | max | min | energy p99.5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Turbine_Data_Penmanshiel_01_2016-06-06_-_2017-01-01_1042.csv | Penmanshiel 01 | 29,987 | 28,943 | 2,057 | 2,061 | -15.85 | 409 |
| Turbine_Data_Penmanshiel_02_2016-06-03_-_2017-01-01_1043.csv | Penmanshiel 02 | 30,475 | 28,843 | 2,057 | 2,061 | -15.37 | 409 |
| Turbine_Data_Penmanshiel_04_2016-06-13_-_2017-01-01_1044.csv | Penmanshiel 04 | 28,999 | 28,524 | 2,057 | 2,062 | -15.43 | 410 |
| Turbine_Data_Penmanshiel_05_2016-06-15_-_2017-01-01_1045.csv | Penmanshiel 05 | 28,687 | 28,274 | 2,058 | 2,062 | -13.32 | 408 |
| Turbine_Data_Penmanshiel_06_2016-06-02_-_2017-01-01_1046.csv | Penmanshiel 06 | 30,564 | 27,500 | 2,059 | 2,062 | -15.12 | 410 |
| Turbine_Data_Penmanshiel_07_2016-06-02_-_2017-01-01_1047.csv | Penmanshiel 07 | 30,566 | 30,025 | 2,055 | 2,061 | -14.77 | 408 |
| Turbine_Data_Penmanshiel_08_2016-07-27_-_2017-01-01_1048.csv | Penmanshiel 08 | 22,658 | 19,418 | 2,059 | 2,061 | -14.33 | 410 |
| Turbine_Data_Penmanshiel_09_2016-06-24_-_2017-01-01_1049.csv | Penmanshiel 09 | 27,434 | 18,991 | 2,058 | 2,062 | -15.3 | 409 |
| Turbine_Data_Penmanshiel_10_2016-06-27_-_2017-01-01_1050.csv | Penmanshiel 10 | 26,964 | 18,929 | 2,057 | 2,061 | -15.23 | 409 |
| Turbine_Data_Penmanshiel_11_2016-07-19_-_2017-01-01_1051.csv | Penmanshiel 11 | 23,846 | 19,286 | 2,059 | 2,062 | -12.56 | 410 |
| Turbine_Data_Penmanshiel_12_2016-07-02_-_2017-01-01_1052.csv | Penmanshiel 12 | 26,254 | 19,354 | 2,060 | 2,061 | -13.29 | 411 |
| Turbine_Data_Penmanshiel_13_2016-06-30_-_2017-01-01_1053.csv | Penmanshiel 13 | 26,552 | 19,038 | 2,060 | 2,062 | -13.59 | 411 |
| Turbine_Data_Penmanshiel_14_2016-07-09_-_2017-01-01_1054.csv | Penmanshiel 14 | 25,246 | 18,554 | 2,060 | 2,062 | -19.17 | 410 |
| Turbine_Data_Penmanshiel_15_2016-07-14_-_2017-01-01_1056.csv | Penmanshiel 15 | 24,504 | 19,175 | 2,058 | 2,061 | -15.55 | 410 |
| Turbine_Data_Penmanshiel_01_2017-01-01_-_2018-01-01_1042.csv | Penmanshiel 01 | 52,560 | 52,394 | 2,056 | 2,061 | -17.65 | 410 |
| Turbine_Data_Penmanshiel_02_2017-01-01_-_2018-01-01_1043.csv | Penmanshiel 02 | 52,560 | 52,342 | 2,052 | 2,061 | -15.04 | 410 |
| Turbine_Data_Penmanshiel_04_2017-01-01_-_2018-01-01_1044.csv | Penmanshiel 04 | 52,560 | 52,427 | 2,056 | 2,061 | -16.53 | 410 |
| Turbine_Data_Penmanshiel_05_2017-01-01_-_2018-01-01_1045.csv | Penmanshiel 05 | 52,560 | 52,429 | 2,056 | 2,061 | -15.98 | 410 |
| Turbine_Data_Penmanshiel_06_2017-01-01_-_2018-01-01_1046.csv | Penmanshiel 06 | 52,560 | 52,241 | 2,052 | 2,062 | -15.54 | 410 |
| Turbine_Data_Penmanshiel_07_2017-01-01_-_2018-01-01_1047.csv | Penmanshiel 07 | 52,560 | 52,425 | 2,051 | 2,061 | -13.9 | 409 |
| Turbine_Data_Penmanshiel_08_2017-01-01_-_2018-01-01_1048.csv | Penmanshiel 08 | 52,560 | 52,449 | 2,056 | 2,061 | -16.74 | 410 |
| Turbine_Data_Penmanshiel_09_2017-01-01_-_2018-01-01_1049.csv | Penmanshiel 09 | 52,560 | 52,254 | 2,051 | 2,062 | -16.43 | 409 |
| Turbine_Data_Penmanshiel_10_2017-01-01_-_2018-01-01_1050.csv | Penmanshiel 10 | 52,560 | 52,428 | 2,050 | 2,061 | -15.72 | 409 |
| Turbine_Data_Penmanshiel_11_2017-01-01_-_2018-01-01_1051.csv | Penmanshiel 11 | 52,560 | 52,427 | 2,054 | 2,061 | -15.31 | 410 |
| Turbine_Data_Penmanshiel_12_2017-01-01_-_2018-01-01_1052.csv | Penmanshiel 12 | 52,560 | 52,413 | 2,058 | 2,062 | -13.79 | 410 |
| Turbine_Data_Penmanshiel_13_2017-01-01_-_2018-01-01_1053.csv | Penmanshiel 13 | 52,560 | 52,419 | 2,057 | 2,062 | -14.08 | 410 |
| Turbine_Data_Penmanshiel_14_2017-01-01_-_2018-01-01_1054.csv | Penmanshiel 14 | 52,560 | 52,427 | 2,058 | 2,061 | -16.4 | 410 |
| Turbine_Data_Penmanshiel_15_2017-01-01_-_2018-01-01_1056.csv | Penmanshiel 15 | 52,560 | 52,426 | 2,058 | 2,061 | -14.02 | 410 |
| Turbine_Data_Penmanshiel_01_2018-01-01_-_2019-01-01_1042.csv | Penmanshiel 01 | 52,560 | 52,456 | 2,053 | 2,071 | -16.9 | 409 |
| Turbine_Data_Penmanshiel_02_2018-01-01_-_2019-01-01_1043.csv | Penmanshiel 02 | 52,560 | 51,664 | 2,053 | 2,075 | -19.31 | 409 |
| Turbine_Data_Penmanshiel_04_2018-01-01_-_2019-01-01_1044.csv | Penmanshiel 04 | 52,560 | 52,461 | 2,053 | 2,074 | -15.13 | 410 |
| Turbine_Data_Penmanshiel_05_2018-01-01_-_2019-01-01_1045.csv | Penmanshiel 05 | 52,560 | 52,455 | 2,053 | 2,072 | -14.6 | 410 |
| Turbine_Data_Penmanshiel_06_2018-01-01_-_2019-01-01_1046.csv | Penmanshiel 06 | 52,560 | 52,139 | 2,054 | 2,076 | -15.55 | 410 |
| Turbine_Data_Penmanshiel_07_2018-01-01_-_2019-01-01_1047.csv | Penmanshiel 07 | 52,560 | 52,464 | 2,052 | 2,072 | -16.37 | 409 |
| Turbine_Data_Penmanshiel_08_2018-01-01_-_2019-01-01_1048.csv | Penmanshiel 08 | 52,560 | 52,431 | 2,053 | 2,077 | -15.79 | 409 |
| Turbine_Data_Penmanshiel_09_2018-01-01_-_2019-01-01_1049.csv | Penmanshiel 09 | 52,560 | 52,290 | 2,051 | 2,070 | -16.14 | 409 |
| Turbine_Data_Penmanshiel_10_2018-01-01_-_2019-01-01_1050.csv | Penmanshiel 10 | 52,560 | 51,757 | 2,050 | 2,074 | -14.6 | 408 |
| Turbine_Data_Penmanshiel_11_2018-01-01_-_2019-01-01_1051.csv | Penmanshiel 11 | 52,560 | 52,390 | 2,054 | 2,078 | -13.75 | 410 |
| Turbine_Data_Penmanshiel_12_2018-01-01_-_2019-01-01_1052.csv | Penmanshiel 12 | 52,560 | 52,411 | 2,055 | 2,078 | -15.53 | 410 |
| Turbine_Data_Penmanshiel_13_2018-01-01_-_2019-01-01_1053.csv | Penmanshiel 13 | 52,560 | 52,410 | 2,056 | 2,071 | -15.96 | 410 |
| Turbine_Data_Penmanshiel_14_2018-01-01_-_2019-01-01_1054.csv | Penmanshiel 14 | 52,560 | 52,407 | 2,055 | 2,072 | -16.06 | 410 |
| Turbine_Data_Penmanshiel_15_2018-01-01_-_2019-01-01_1056.csv | Penmanshiel 15 | 52,560 | 52,405 | 2,056 | 2,075 | -16.54 | 410 |
| Turbine_Data_Penmanshiel_01_2019-01-01_-_2020-01-01_1042.csv | Penmanshiel 01 | 52,560 | 52,174 | 2,055 | 2,070 | -16.14 | 409 |
| Turbine_Data_Penmanshiel_02_2019-01-01_-_2020-01-01_1043.csv | Penmanshiel 02 | 52,560 | 52,276 | 2,054 | 2,072 | -15.01 | 409 |
| Turbine_Data_Penmanshiel_04_2019-01-01_-_2020-01-01_1044.csv | Penmanshiel 04 | 52,560 | 52,146 | 2,057 | 2,072 | -16.86 | 409 |
| Turbine_Data_Penmanshiel_05_2019-01-01_-_2020-01-01_1045.csv | Penmanshiel 05 | 52,560 | 52,099 | 2,057 | 2,072 | -15.91 | 409 |
| Turbine_Data_Penmanshiel_06_2019-01-01_-_2020-01-01_1046.csv | Penmanshiel 06 | 52,560 | 52,070 | 2,057 | 2,088 | -14.85 | 410 |
| Turbine_Data_Penmanshiel_07_2019-01-01_-_2020-01-01_1047.csv | Penmanshiel 07 | 52,560 | 50,569 | 2,050 | 2,073 | -19.06 | 408 |
| Turbine_Data_Penmanshiel_08_2019-01-01_-_2020-01-01_1048.csv | Penmanshiel 08 | 52,560 | 52,326 | 2,056 | 2,075 | -17.83 | 409 |
| Turbine_Data_Penmanshiel_09_2019-01-01_-_2020-01-01_1049.csv | Penmanshiel 09 | 52,560 | 52,278 | 2,053 | 2,073 | -15.44 | 408 |
| Turbine_Data_Penmanshiel_10_2019-01-01_-_2020-01-01_1050.csv | Penmanshiel 10 | 52,560 | 52,175 | 2,052 | 2,071 | -13.89 | 408 |
| Turbine_Data_Penmanshiel_11_2019-01-01_-_2020-01-01_1051.csv | Penmanshiel 11 | 52,560 | 52,127 | 2,053 | 2,070 | -15.14 | 409 |
| Turbine_Data_Penmanshiel_12_2019-01-01_-_2020-01-01_1052.csv | Penmanshiel 12 | 52,560 | 52,135 | 2,059 | 2,071 | -15.76 | 410 |
| Turbine_Data_Penmanshiel_13_2019-01-01_-_2020-01-01_1053.csv | Penmanshiel 13 | 52,560 | 52,268 | 2,059 | 2,069 | -16.94 | 410 |
| Turbine_Data_Penmanshiel_14_2019-01-01_-_2020-01-01_1054.csv | Penmanshiel 14 | 52,560 | 52,131 | 2,058 | 2,070 | -17.34 | 410 |
| Turbine_Data_Penmanshiel_15_2019-01-01_-_2020-01-01_1056.csv | Penmanshiel 15 | 52,560 | 52,124 | 2,058 | 2,080 | -16.3 | 410 |
| Turbine_Data_Penmanshiel_01_2020-01-01_-_2021-01-01_1042.csv | Penmanshiel 01 | 52,704 | 49,603 | 2,056 | 2,077 | -14.92 | 409 |
| Turbine_Data_Penmanshiel_02_2020-01-01_-_2021-01-01_1043.csv | Penmanshiel 02 | 52,704 | 49,621 | 2,054 | 2,085 | -15.67 | 409 |
| Turbine_Data_Penmanshiel_04_2020-01-01_-_2021-01-01_1044.csv | Penmanshiel 04 | 52,704 | 49,675 | 2,056 | 2,083 | -15.69 | 410 |
| Turbine_Data_Penmanshiel_05_2020-01-01_-_2021-01-01_1045.csv | Penmanshiel 05 | 52,704 | 49,681 | 2,056 | 2,073 | -14.74 | 409 |
| Turbine_Data_Penmanshiel_06_2020-01-01_-_2021-01-01_1046.csv | Penmanshiel 06 | 52,704 | 49,836 | 2,057 | 2,075 | -15.79 | 410 |
| Turbine_Data_Penmanshiel_07_2020-01-01_-_2021-01-01_1047.csv | Penmanshiel 07 | 52,704 | 49,729 | 2,053 | 2,070 | -15.81 | 409 |
| Turbine_Data_Penmanshiel_08_2020-01-01_-_2021-01-01_1048.csv | Penmanshiel 08 | 52,704 | 49,891 | 2,055 | 2,073 | -16.52 | 409 |
| Turbine_Data_Penmanshiel_09_2020-01-01_-_2021-01-01_1049.csv | Penmanshiel 09 | 52,704 | 49,979 | 2,052 | 2,071 | -15.58 | 408 |
| Turbine_Data_Penmanshiel_10_2020-01-01_-_2021-01-01_1050.csv | Penmanshiel 10 | 52,704 | 49,867 | 2,051 | 2,073 | -14.79 | 408 |
| Turbine_Data_Penmanshiel_11_2020-01-01_-_2021-01-01_1051.csv | Penmanshiel 11 | 52,704 | 49,731 | 2,054 | 2,076 | -15.87 | 409 |
| Turbine_Data_Penmanshiel_12_2020-01-01_-_2021-01-01_1052.csv | Penmanshiel 12 | 52,704 | 49,881 | 2,057 | 2,071 | -14.36 | 410 |
| Turbine_Data_Penmanshiel_13_2020-01-01_-_2021-01-01_1053.csv | Penmanshiel 13 | 52,704 | 49,632 | 2,058 | 2,079 | -15.63 | 410 |
| Turbine_Data_Penmanshiel_14_2020-01-01_-_2021-01-01_1054.csv | Penmanshiel 14 | 52,704 | 49,881 | 2,057 | 2,075 | -16.76 | 410 |
| Turbine_Data_Penmanshiel_15_2020-01-01_-_2021-01-01_1056.csv | Penmanshiel 15 | 52,704 | 49,738 | 2,057 | 2,075 | -14.93 | 410 |
| Turbine_Data_Penmanshiel_01_2021-01-01_-_2022-01-01_1042.csv | Penmanshiel 01 | 52,560 | 52,497 | 2,055 | 2,071 | -15.42 | 409 |
| Turbine_Data_Penmanshiel_02_2021-01-01_-_2022-01-01_1043.csv | Penmanshiel 02 | 52,560 | 52,486 | 2,053 | 2,072 | -15.94 | 409 |
| Turbine_Data_Penmanshiel_04_2021-01-01_-_2022-01-01_1044.csv | Penmanshiel 04 | 52,560 | 52,398 | 2,055 | 2,074 | -17.24 | 409 |
| Turbine_Data_Penmanshiel_05_2021-01-01_-_2022-01-01_1045.csv | Penmanshiel 05 | 52,560 | 52,474 | 2,055 | 2,071 | -15.45 | 409 |
| Turbine_Data_Penmanshiel_06_2021-01-01_-_2022-01-01_1046.csv | Penmanshiel 06 | 52,560 | 52,420 | 2,056 | 2,069 | -14.21 | 410 |
| Turbine_Data_Penmanshiel_07_2021-01-01_-_2022-01-01_1047.csv | Penmanshiel 07 | 52,560 | 52,330 | 2,053 | 2,070 | -18.22 | 409 |
| Turbine_Data_Penmanshiel_08_2021-01-01_-_2022-01-01_1048.csv | Penmanshiel 08 | 52,560 | 52,460 | 2,052 | 2,072 | -16.78 | 409 |
| Turbine_Data_Penmanshiel_09_2021-01-01_-_2022-01-01_1049.csv | Penmanshiel 09 | 52,560 | 52,459 | 2,055 | 2,071 | -15.54 | 409 |
| Turbine_Data_Penmanshiel_10_2021-01-01_-_2022-01-01_1050.csv | Penmanshiel 10 | 52,560 | 52,411 | 2,054 | 2,073 | -15.25 | 408 |
| Turbine_Data_Penmanshiel_11_2021-01-01_-_2022-01-01_1051.csv | Penmanshiel 11 | 52,560 | 52,030 | 2,054 | 2,073 | -15.34 | 409 |
| Turbine_Data_Penmanshiel_12_2021-01-01_-_2022-01-01_1052.csv | Penmanshiel 12 | 52,560 | 52,463 | 2,058 | 2,071 | -16.82 | 410 |
| Turbine_Data_Penmanshiel_13_2021-01-01_-_2022-01-01_1053.csv | Penmanshiel 13 | 52,560 | 52,430 | 2,057 | 2,072 | -15.06 | 410 |
| Turbine_Data_Penmanshiel_14_2021-01-01_-_2022-01-01_1054.csv | Penmanshiel 14 | 52,560 | 52,429 | 2,056 | 2,070 | -15.7 | 410 |
| Turbine_Data_Penmanshiel_15_2021-01-01_-_2022-01-01_1056.csv | Penmanshiel 15 | 52,560 | 52,380 | 2,057 | 2,071 | -17.87 | 410 |
| Turbine_Data_Penmanshiel_01_2022-01-01_-_2023-01-01_1042.csv | Penmanshiel 01 | 52,560 | 52,467 | 2,057 | 2,073 | -14.98 | 410 |
| Turbine_Data_Penmanshiel_02_2022-01-01_-_2023-01-01_1043.csv | Penmanshiel 02 | 52,560 | 52,474 | 2,057 | 2,072 | -15.62 | 409 |
| Turbine_Data_Penmanshiel_04_2022-01-01_-_2023-01-01_1044.csv | Penmanshiel 04 | 52,560 | 52,306 | 2,059 | 2,076 | -15.75 | 410 |
| Turbine_Data_Penmanshiel_05_2022-01-01_-_2023-01-01_1045.csv | Penmanshiel 05 | 52,560 | 52,362 | 2,057 | 2,079 | -15.98 | 410 |
| Turbine_Data_Penmanshiel_06_2022-01-01_-_2023-01-01_1046.csv | Penmanshiel 06 | 52,560 | 52,465 | 2,058 | 2,088 | -14.36 | 410 |
| Turbine_Data_Penmanshiel_07_2022-01-01_-_2023-01-01_1047.csv | Penmanshiel 07 | 52,560 | 51,750 | 2,055 | 2,076 | -15.02 | 409 |
| Turbine_Data_Penmanshiel_08_2022-01-01_-_2023-01-01_1048.csv | Penmanshiel 08 | 52,560 | 52,472 | 2,055 | 2,073 | -15.64 | 409 |
| Turbine_Data_Penmanshiel_09_2022-01-01_-_2023-01-01_1049.csv | Penmanshiel 09 | 52,560 | 52,469 | 2,054 | 2,072 | -16.5 | 409 |
| Turbine_Data_Penmanshiel_10_2022-01-01_-_2023-01-01_1050.csv | Penmanshiel 10 | 52,560 | 52,438 | 2,054 | 2,075 | -16.34 | 408 |
| Turbine_Data_Penmanshiel_11_2022-01-01_-_2023-01-01_1051.csv | Penmanshiel 11 | 52,560 | 48,320 | 2,055 | 2,075 | -16.28 | 409 |
| Turbine_Data_Penmanshiel_12_2022-01-01_-_2023-01-01_1052.csv | Penmanshiel 12 | 52,560 | 52,436 | 2,059 | 2,073 | -15.56 | 410 |
| Turbine_Data_Penmanshiel_13_2022-01-01_-_2023-01-01_1053.csv | Penmanshiel 13 | 52,560 | 52,444 | 2,060 | 2,075 | -15.59 | 410 |
| Turbine_Data_Penmanshiel_14_2022-01-01_-_2023-01-01_1054.csv | Penmanshiel 14 | 52,560 | 52,303 | 2,059 | 2,074 | -14.83 | 410 |
| Turbine_Data_Penmanshiel_15_2022-01-01_-_2023-01-01_1056.csv | Penmanshiel 15 | 52,560 | 52,430 | 2,059 | 2,077 | -16.1 | 410 |

## Timestamp timezone

**VERDICT UTC** - across 98 turbine-years, every spring-forward hour is fully populated and no autumn fall-back hour repeats a timestamp -- neither fingerprint that Europe/London would leave is present; the spring half was not applicable on 14 of 98 turbine-years, whose series does not run through the hour (no data in the hour before or after it)

| field | value |
| --- | --- |
| column measured | Date and time |
| candidate local zone | Europe/London |
| declared in the source specification | UTC |

A local-time series is missing every observation in the spring-forward hour and repeats every label in the autumn fall-back hour. A UTC series does neither. The test runs on the rows that carry a value in at least one ingested column, which is what the ingest keeps. `steps in spring hour` counts distinct labels out of the six a 10-minute grid holds. `repeated steps` reads `n/a` where labels still repeat outside the fall-back hour after that drop, because the test cannot then tell a fall-back from that.

| member | turbine | year | rows | distinct | rows with a value | duplicate labels among them | spring hour (local) | steps in spring hour | autumn hour (local) | repeated steps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Turbine_Data_Penmanshiel_01_2016-06-06_-_2017-01-01_1042.csv | Penmanshiel 01 | 2,016 | 29,987 | 29,987 | 28,943 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_02_2016-06-03_-_2017-01-01_1043.csv | Penmanshiel 02 | 2,016 | 30,475 | 30,475 | 28,843 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_04_2016-06-13_-_2017-01-01_1044.csv | Penmanshiel 04 | 2,016 | 28,999 | 28,999 | 28,524 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_05_2016-06-15_-_2017-01-01_1045.csv | Penmanshiel 05 | 2,016 | 28,687 | 28,687 | 28,274 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_06_2016-06-02_-_2017-01-01_1046.csv | Penmanshiel 06 | 2,016 | 30,564 | 30,564 | 27,500 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_07_2016-06-02_-_2017-01-01_1047.csv | Penmanshiel 07 | 2,016 | 30,566 | 30,566 | 30,025 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_08_2016-07-27_-_2017-01-01_1048.csv | Penmanshiel 08 | 2,016 | 22,658 | 22,658 | 19,418 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_09_2016-06-24_-_2017-01-01_1049.csv | Penmanshiel 09 | 2,016 | 27,434 | 27,434 | 18,991 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_10_2016-06-27_-_2017-01-01_1050.csv | Penmanshiel 10 | 2,016 | 26,964 | 26,964 | 18,929 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_11_2016-07-19_-_2017-01-01_1051.csv | Penmanshiel 11 | 2,016 | 23,846 | 23,846 | 19,286 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_12_2016-07-02_-_2017-01-01_1052.csv | Penmanshiel 12 | 2,016 | 26,254 | 26,254 | 19,354 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_13_2016-06-30_-_2017-01-01_1053.csv | Penmanshiel 13 | 2,016 | 26,552 | 26,552 | 19,038 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_14_2016-07-09_-_2017-01-01_1054.csv | Penmanshiel 14 | 2,016 | 25,246 | 25,246 | 18,554 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_15_2016-07-14_-_2017-01-01_1056.csv | Penmanshiel 15 | 2,016 | 24,504 | 24,504 | 19,175 | 0 | 2016-03-27 01 | n/a | 2016-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_01_2017-01-01_-_2018-01-01_1042.csv | Penmanshiel 01 | 2,017 | 52,560 | 52,560 | 52,394 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_02_2017-01-01_-_2018-01-01_1043.csv | Penmanshiel 02 | 2,017 | 52,560 | 52,560 | 52,342 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_04_2017-01-01_-_2018-01-01_1044.csv | Penmanshiel 04 | 2,017 | 52,560 | 52,560 | 52,427 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_05_2017-01-01_-_2018-01-01_1045.csv | Penmanshiel 05 | 2,017 | 52,560 | 52,560 | 52,429 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_06_2017-01-01_-_2018-01-01_1046.csv | Penmanshiel 06 | 2,017 | 52,560 | 52,560 | 52,241 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_07_2017-01-01_-_2018-01-01_1047.csv | Penmanshiel 07 | 2,017 | 52,560 | 52,560 | 52,425 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_08_2017-01-01_-_2018-01-01_1048.csv | Penmanshiel 08 | 2,017 | 52,560 | 52,560 | 52,449 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_09_2017-01-01_-_2018-01-01_1049.csv | Penmanshiel 09 | 2,017 | 52,560 | 52,560 | 52,254 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_10_2017-01-01_-_2018-01-01_1050.csv | Penmanshiel 10 | 2,017 | 52,560 | 52,560 | 52,428 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_11_2017-01-01_-_2018-01-01_1051.csv | Penmanshiel 11 | 2,017 | 52,560 | 52,560 | 52,427 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_12_2017-01-01_-_2018-01-01_1052.csv | Penmanshiel 12 | 2,017 | 52,560 | 52,560 | 52,413 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_13_2017-01-01_-_2018-01-01_1053.csv | Penmanshiel 13 | 2,017 | 52,560 | 52,560 | 52,419 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_14_2017-01-01_-_2018-01-01_1054.csv | Penmanshiel 14 | 2,017 | 52,560 | 52,560 | 52,427 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_15_2017-01-01_-_2018-01-01_1056.csv | Penmanshiel 15 | 2,017 | 52,560 | 52,560 | 52,426 | 0 | 2017-03-26 01 | 6 | 2017-10-29 01 | 0 |
| Turbine_Data_Penmanshiel_01_2018-01-01_-_2019-01-01_1042.csv | Penmanshiel 01 | 2,018 | 52,560 | 52,560 | 52,456 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_02_2018-01-01_-_2019-01-01_1043.csv | Penmanshiel 02 | 2,018 | 52,560 | 52,560 | 51,664 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_04_2018-01-01_-_2019-01-01_1044.csv | Penmanshiel 04 | 2,018 | 52,560 | 52,560 | 52,461 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_05_2018-01-01_-_2019-01-01_1045.csv | Penmanshiel 05 | 2,018 | 52,560 | 52,560 | 52,456 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_06_2018-01-01_-_2019-01-01_1046.csv | Penmanshiel 06 | 2,018 | 52,560 | 52,560 | 52,139 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_07_2018-01-01_-_2019-01-01_1047.csv | Penmanshiel 07 | 2,018 | 52,560 | 52,560 | 52,464 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_08_2018-01-01_-_2019-01-01_1048.csv | Penmanshiel 08 | 2,018 | 52,560 | 52,560 | 52,431 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_09_2018-01-01_-_2019-01-01_1049.csv | Penmanshiel 09 | 2,018 | 52,560 | 52,560 | 52,290 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_10_2018-01-01_-_2019-01-01_1050.csv | Penmanshiel 10 | 2,018 | 52,560 | 52,560 | 51,757 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_11_2018-01-01_-_2019-01-01_1051.csv | Penmanshiel 11 | 2,018 | 52,560 | 52,560 | 52,390 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_12_2018-01-01_-_2019-01-01_1052.csv | Penmanshiel 12 | 2,018 | 52,560 | 52,560 | 52,411 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_13_2018-01-01_-_2019-01-01_1053.csv | Penmanshiel 13 | 2,018 | 52,560 | 52,560 | 52,410 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_14_2018-01-01_-_2019-01-01_1054.csv | Penmanshiel 14 | 2,018 | 52,560 | 52,560 | 52,407 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_15_2018-01-01_-_2019-01-01_1056.csv | Penmanshiel 15 | 2,018 | 52,560 | 52,560 | 52,405 | 0 | 2018-03-25 01 | 6 | 2018-10-28 01 | 0 |
| Turbine_Data_Penmanshiel_01_2019-01-01_-_2020-01-01_1042.csv | Penmanshiel 01 | 2,019 | 52,560 | 52,560 | 52,174 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_02_2019-01-01_-_2020-01-01_1043.csv | Penmanshiel 02 | 2,019 | 52,560 | 52,560 | 52,276 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_04_2019-01-01_-_2020-01-01_1044.csv | Penmanshiel 04 | 2,019 | 52,560 | 52,560 | 52,146 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_05_2019-01-01_-_2020-01-01_1045.csv | Penmanshiel 05 | 2,019 | 52,560 | 52,560 | 52,099 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_06_2019-01-01_-_2020-01-01_1046.csv | Penmanshiel 06 | 2,019 | 52,560 | 52,560 | 52,070 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_07_2019-01-01_-_2020-01-01_1047.csv | Penmanshiel 07 | 2,019 | 52,560 | 52,560 | 50,569 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_08_2019-01-01_-_2020-01-01_1048.csv | Penmanshiel 08 | 2,019 | 52,560 | 52,560 | 52,326 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_09_2019-01-01_-_2020-01-01_1049.csv | Penmanshiel 09 | 2,019 | 52,560 | 52,560 | 52,278 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_10_2019-01-01_-_2020-01-01_1050.csv | Penmanshiel 10 | 2,019 | 52,560 | 52,560 | 52,175 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_11_2019-01-01_-_2020-01-01_1051.csv | Penmanshiel 11 | 2,019 | 52,560 | 52,560 | 52,128 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_12_2019-01-01_-_2020-01-01_1052.csv | Penmanshiel 12 | 2,019 | 52,560 | 52,560 | 52,136 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_13_2019-01-01_-_2020-01-01_1053.csv | Penmanshiel 13 | 2,019 | 52,560 | 52,560 | 52,268 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_14_2019-01-01_-_2020-01-01_1054.csv | Penmanshiel 14 | 2,019 | 52,560 | 52,560 | 52,131 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_15_2019-01-01_-_2020-01-01_1056.csv | Penmanshiel 15 | 2,019 | 52,560 | 52,560 | 52,124 | 0 | 2019-03-31 01 | 6 | 2019-10-27 01 | 0 |
| Turbine_Data_Penmanshiel_01_2020-01-01_-_2021-01-01_1042.csv | Penmanshiel 01 | 2,020 | 52,704 | 52,704 | 49,604 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_02_2020-01-01_-_2021-01-01_1043.csv | Penmanshiel 02 | 2,020 | 52,704 | 52,704 | 49,622 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_04_2020-01-01_-_2021-01-01_1044.csv | Penmanshiel 04 | 2,020 | 52,704 | 52,704 | 49,675 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_05_2020-01-01_-_2021-01-01_1045.csv | Penmanshiel 05 | 2,020 | 52,704 | 52,704 | 49,682 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_06_2020-01-01_-_2021-01-01_1046.csv | Penmanshiel 06 | 2,020 | 52,704 | 52,704 | 49,837 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_07_2020-01-01_-_2021-01-01_1047.csv | Penmanshiel 07 | 2,020 | 52,704 | 52,704 | 49,729 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_08_2020-01-01_-_2021-01-01_1048.csv | Penmanshiel 08 | 2,020 | 52,704 | 52,704 | 49,892 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_09_2020-01-01_-_2021-01-01_1049.csv | Penmanshiel 09 | 2,020 | 52,704 | 52,704 | 49,981 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_10_2020-01-01_-_2021-01-01_1050.csv | Penmanshiel 10 | 2,020 | 52,704 | 52,704 | 49,867 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_11_2020-01-01_-_2021-01-01_1051.csv | Penmanshiel 11 | 2,020 | 52,704 | 52,704 | 49,731 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_12_2020-01-01_-_2021-01-01_1052.csv | Penmanshiel 12 | 2,020 | 52,704 | 52,704 | 49,881 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_13_2020-01-01_-_2021-01-01_1053.csv | Penmanshiel 13 | 2,020 | 52,704 | 52,704 | 49,633 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_14_2020-01-01_-_2021-01-01_1054.csv | Penmanshiel 14 | 2,020 | 52,704 | 52,704 | 49,881 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_15_2020-01-01_-_2021-01-01_1056.csv | Penmanshiel 15 | 2,020 | 52,704 | 52,704 | 49,738 | 0 | 2020-03-29 01 | 6 | 2020-10-25 01 | 0 |
| Turbine_Data_Penmanshiel_01_2021-01-01_-_2022-01-01_1042.csv | Penmanshiel 01 | 2,021 | 52,560 | 52,560 | 52,497 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_02_2021-01-01_-_2022-01-01_1043.csv | Penmanshiel 02 | 2,021 | 52,560 | 52,560 | 52,486 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_04_2021-01-01_-_2022-01-01_1044.csv | Penmanshiel 04 | 2,021 | 52,560 | 52,560 | 52,398 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_05_2021-01-01_-_2022-01-01_1045.csv | Penmanshiel 05 | 2,021 | 52,560 | 52,560 | 52,474 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_06_2021-01-01_-_2022-01-01_1046.csv | Penmanshiel 06 | 2,021 | 52,560 | 52,560 | 52,420 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_07_2021-01-01_-_2022-01-01_1047.csv | Penmanshiel 07 | 2,021 | 52,560 | 52,560 | 52,330 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_08_2021-01-01_-_2022-01-01_1048.csv | Penmanshiel 08 | 2,021 | 52,560 | 52,560 | 52,460 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_09_2021-01-01_-_2022-01-01_1049.csv | Penmanshiel 09 | 2,021 | 52,560 | 52,560 | 52,459 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_10_2021-01-01_-_2022-01-01_1050.csv | Penmanshiel 10 | 2,021 | 52,560 | 52,560 | 52,411 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_11_2021-01-01_-_2022-01-01_1051.csv | Penmanshiel 11 | 2,021 | 52,560 | 52,560 | 52,030 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_12_2021-01-01_-_2022-01-01_1052.csv | Penmanshiel 12 | 2,021 | 52,560 | 52,560 | 52,464 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_13_2021-01-01_-_2022-01-01_1053.csv | Penmanshiel 13 | 2,021 | 52,560 | 52,560 | 52,431 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_14_2021-01-01_-_2022-01-01_1054.csv | Penmanshiel 14 | 2,021 | 52,560 | 52,560 | 52,430 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_15_2021-01-01_-_2022-01-01_1056.csv | Penmanshiel 15 | 2,021 | 52,560 | 52,560 | 52,381 | 0 | 2021-03-28 01 | 6 | 2021-10-31 01 | 0 |
| Turbine_Data_Penmanshiel_01_2022-01-01_-_2023-01-01_1042.csv | Penmanshiel 01 | 2,022 | 52,560 | 52,560 | 52,467 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_02_2022-01-01_-_2023-01-01_1043.csv | Penmanshiel 02 | 2,022 | 52,560 | 52,560 | 52,475 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_04_2022-01-01_-_2023-01-01_1044.csv | Penmanshiel 04 | 2,022 | 52,560 | 52,560 | 52,307 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_05_2022-01-01_-_2023-01-01_1045.csv | Penmanshiel 05 | 2,022 | 52,560 | 52,560 | 52,363 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_06_2022-01-01_-_2023-01-01_1046.csv | Penmanshiel 06 | 2,022 | 52,560 | 52,560 | 52,465 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_07_2022-01-01_-_2023-01-01_1047.csv | Penmanshiel 07 | 2,022 | 52,560 | 52,560 | 51,750 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_08_2022-01-01_-_2023-01-01_1048.csv | Penmanshiel 08 | 2,022 | 52,560 | 52,560 | 52,472 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_09_2022-01-01_-_2023-01-01_1049.csv | Penmanshiel 09 | 2,022 | 52,560 | 52,560 | 52,469 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_10_2022-01-01_-_2023-01-01_1050.csv | Penmanshiel 10 | 2,022 | 52,560 | 52,560 | 52,438 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_11_2022-01-01_-_2023-01-01_1051.csv | Penmanshiel 11 | 2,022 | 52,560 | 52,560 | 48,320 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_12_2022-01-01_-_2023-01-01_1052.csv | Penmanshiel 12 | 2,022 | 52,560 | 52,560 | 52,437 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_13_2022-01-01_-_2023-01-01_1053.csv | Penmanshiel 13 | 2,022 | 52,560 | 52,560 | 52,444 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_14_2022-01-01_-_2023-01-01_1054.csv | Penmanshiel 14 | 2,022 | 52,560 | 52,560 | 52,303 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
| Turbine_Data_Penmanshiel_15_2022-01-01_-_2023-01-01_1056.csv | Penmanshiel 15 | 2,022 | 52,560 | 52,560 | 52,430 | 0 | 2022-03-27 01 | 6 | 2022-10-30 01 | 0 |
