# Telemetry pipeline - ingest

| field | value |
| --- | --- |
| run_id | 20260910-212844_ingest_telemetry_c13b5fe8 |
| stage | ingest |
| config | configs/data/telemetry_v1.yaml |
| config_hash | c13b5fe8 |
| git_sha | 4aff202e3ef865531e6b712c056cbf7d962da613 |
| created_at (UTC) | 2026-09-10T21:28:44+00:00 |

## Rows

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| ingest | 44,947,300 | 14,905,169 | 30,042,131 | 33.16% |

## Sources

| source | members discovered | rows loaded | turbines | events | identical cross-file copies dropped | differing cross-file repeats left for the clean stage |
| --- | --- | --- | --- | --- | --- | --- |
| care | 103 | 5,242,948 | 95 | 95 | 0 | 0 |
| hill_of_towie | 319 | 2,199,102 | 21 | 1,004,336 | 460 | 0 |
| kelmarsh | 110 | 2,784,159 | 6 | 504,180 | 0 | 0 |
| penmanshiel | 198 | 4,678,960 | 14 | 839,303 | 0 | 0 |

## Members by kind

| kind | members |
| --- | --- |
| alarm_log | 24 |
| downtime_series | 1 |
| metadata | 15 |
| other | 72 |
| scada_10min | 463 |
| status_events | 155 |

## Row accounting per file

Every SCADA file goes through the repeated-label rule: drop the rows null in every ingested channel, assert that no (label, column) then holds two distinct values, and collapse to one row per label. `rows_raw` is rows read, `rows_after_null_drop` is rows carrying any ingested value, `labels_distinct` is distinct labels read (label and station, where one file holds every turbine), `rows_out` is rows kept from that file. A file that does not repeat shows `rows_raw == labels_distinct`; a file whose three counts agree also had no row without an ingested value. The assertion held for every file below, or the run would have stopped.

Where a loader joins several files into one unit -- a Hill of Towie month is three tables joined on (label, station) -- the files' `rows_out` describe the same rows three times and do not add up; the unit's joined rows do. The total below is over units.

| field | value |
| --- | --- |
| files | 319 |
| files that repeat labels (rows_raw > labels_distinct) | 12 |
| files where the three counts agree | 133 |
| rows_raw | 44,947,300 |
| rows_after_null_drop | 19,304,713 |
| units read | 271 |
| units joining several files | 24 |
| rows_out, over units (after each unit's join) | 14,905,629 |
| identical cross-file copies dropped | 460 |
| rows loaded (rows_out over units, less the copies) | 14,905,169 |
| rows_out over units less the copies equals rows loaded | yes |

**Units that join several files**

| source | unit | files | rows after the join |
| --- | --- | --- | --- |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_01.csv + tblSCTurTemp_2019_01.csv + tblSCTurbine_2019_01.csv | 3 | 93,723 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_02.csv + tblSCTurTemp_2019_02.csv + tblSCTurbine_2019_02.csv | 3 | 84,611 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_03.csv + tblSCTurTemp_2019_03.csv + tblSCTurbine_2019_03.csv | 3 | 93,735 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_04.csv + tblSCTurTemp_2019_04.csv + tblSCTurbine_2019_04.csv | 3 | 90,690 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_05.csv + tblSCTurTemp_2019_05.csv + tblSCTurbine_2019_05.csv | 3 | 93,750 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_06.csv + tblSCTurTemp_2019_06.csv + tblSCTurbine_2019_06.csv | 3 | 90,689 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_07.csv + tblSCTurTemp_2019_07.csv + tblSCTurbine_2019_07.csv | 3 | 92,942 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_08.csv + tblSCTurTemp_2019_08.csv + tblSCTurbine_2019_08.csv | 3 | 93,415 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_09.csv + tblSCTurTemp_2019_09.csv + tblSCTurbine_2019_09.csv | 3 | 89,531 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_10.csv + tblSCTurTemp_2019_10.csv + tblSCTurbine_2019_10.csv | 3 | 93,383 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_11.csv + tblSCTurTemp_2019_11.csv + tblSCTurbine_2019_11.csv | 3 | 90,660 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_12.csv + tblSCTurTemp_2019_12.csv + tblSCTurbine_2019_12.csv | 3 | 93,765 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_01.csv + tblSCTurTemp_2023_01.csv + tblSCTurbine_2023_01.csv | 3 | 93,118 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_02.csv + tblSCTurTemp_2023_02.csv + tblSCTurbine_2023_02.csv | 3 | 84,596 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_03.csv + tblSCTurTemp_2023_03.csv + tblSCTurbine_2023_03.csv | 3 | 93,721 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_04.csv + tblSCTurTemp_2023_04.csv + tblSCTurbine_2023_04.csv | 3 | 90,694 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_05.csv + tblSCTurTemp_2023_05.csv + tblSCTurbine_2023_05.csv | 3 | 93,725 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_06.csv + tblSCTurTemp_2023_06.csv + tblSCTurbine_2023_06.csv | 3 | 89,463 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_07.csv + tblSCTurTemp_2023_07.csv + tblSCTurbine_2023_07.csv | 3 | 93,580 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_08.csv + tblSCTurTemp_2023_08.csv + tblSCTurbine_2023_08.csv | 3 | 93,417 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_09.csv + tblSCTurTemp_2023_09.csv + tblSCTurbine_2023_09.csv | 3 | 90,583 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_10.csv + tblSCTurTemp_2023_10.csv + tblSCTurbine_2023_10.csv | 3 | 93,756 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_11.csv + tblSCTurTemp_2023_11.csv + tblSCTurbine_2023_11.csv | 3 | 89,623 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_12.csv + tblSCTurTemp_2023_12.csv + tblSCTurbine_2023_12.csv | 3 | 92,392 |

| source | file | turbine | rows_raw | rows_after_null_drop | labels_distinct | rows_out |
| --- | --- | --- | --- | --- | --- | --- |
| kelmarsh | Kelmarsh_SCADA_2016_3082.zip::Turbine_Data_Kelmarsh_1_2016-01-03_-_2017-01-01_228.csv | Kelmarsh 1 | 52,416 | 48,485 | 52,416 | 48,485 |
| kelmarsh | Kelmarsh_SCADA_2016_3082.zip::Turbine_Data_Kelmarsh_2_2016-01-03_-_2017-01-01_229.csv | Kelmarsh 2 | 52,416 | 48,483 | 52,416 | 48,483 |
| kelmarsh | Kelmarsh_SCADA_2016_3082.zip::Turbine_Data_Kelmarsh_3_2016-01-03_-_2017-01-01_230.csv | Kelmarsh 3 | 52,416 | 47,492 | 52,416 | 47,492 |
| kelmarsh | Kelmarsh_SCADA_2016_3082.zip::Turbine_Data_Kelmarsh_4_2016-01-03_-_2017-01-01_231.csv | Kelmarsh 4 | 52,416 | 46,882 | 52,416 | 46,882 |
| kelmarsh | Kelmarsh_SCADA_2016_3082.zip::Turbine_Data_Kelmarsh_5_2016-01-03_-_2017-01-01_232.csv | Kelmarsh 5 | 52,416 | 47,755 | 52,416 | 47,755 |
| kelmarsh | Kelmarsh_SCADA_2016_3082.zip::Turbine_Data_Kelmarsh_6_2016-01-03_-_2017-01-01_233.csv | Kelmarsh 6 | 52,416 | 46,596 | 52,416 | 46,596 |
| kelmarsh | Kelmarsh_SCADA_2017_3083.zip::Turbine_Data_Kelmarsh_1_2017-01-01_-_2018-01-01_228.csv | Kelmarsh 1 | 52,560 | 51,932 | 52,560 | 51,932 |
| kelmarsh | Kelmarsh_SCADA_2017_3083.zip::Turbine_Data_Kelmarsh_2_2017-01-01_-_2018-01-01_229.csv | Kelmarsh 2 | 52,560 | 52,205 | 52,560 | 52,205 |
| kelmarsh | Kelmarsh_SCADA_2017_3083.zip::Turbine_Data_Kelmarsh_3_2017-01-01_-_2018-01-01_230.csv | Kelmarsh 3 | 52,560 | 52,008 | 52,560 | 52,008 |
| kelmarsh | Kelmarsh_SCADA_2017_3083.zip::Turbine_Data_Kelmarsh_4_2017-01-01_-_2018-01-01_231.csv | Kelmarsh 4 | 52,560 | 52,015 | 52,560 | 52,015 |
| kelmarsh | Kelmarsh_SCADA_2017_3083.zip::Turbine_Data_Kelmarsh_5_2017-01-01_-_2018-01-01_232.csv | Kelmarsh 5 | 52,560 | 52,071 | 52,560 | 52,071 |
| kelmarsh | Kelmarsh_SCADA_2017_3083.zip::Turbine_Data_Kelmarsh_6_2017-01-01_-_2018-01-01_233.csv | Kelmarsh 6 | 52,560 | 51,542 | 52,560 | 51,542 |
| kelmarsh | Kelmarsh_SCADA_2018_3084.zip::Turbine_Data_Kelmarsh_1_2018-01-01_-_2019-01-01_228.csv | Kelmarsh 1 | 52,560 | 50,755 | 52,560 | 50,755 |
| kelmarsh | Kelmarsh_SCADA_2018_3084.zip::Turbine_Data_Kelmarsh_2_2018-01-01_-_2019-01-01_229.csv | Kelmarsh 2 | 52,560 | 50,745 | 52,560 | 50,745 |
| kelmarsh | Kelmarsh_SCADA_2018_3084.zip::Turbine_Data_Kelmarsh_3_2018-01-01_-_2019-01-01_230.csv | Kelmarsh 3 | 52,560 | 50,611 | 52,560 | 50,611 |
| kelmarsh | Kelmarsh_SCADA_2018_3084.zip::Turbine_Data_Kelmarsh_4_2018-01-01_-_2019-01-01_231.csv | Kelmarsh 4 | 52,560 | 50,743 | 52,560 | 50,743 |
| kelmarsh | Kelmarsh_SCADA_2018_3084.zip::Turbine_Data_Kelmarsh_5_2018-01-01_-_2019-01-01_232.csv | Kelmarsh 5 | 52,560 | 50,754 | 52,560 | 50,754 |
| kelmarsh | Kelmarsh_SCADA_2018_3084.zip::Turbine_Data_Kelmarsh_6_2018-01-01_-_2019-01-01_233.csv | Kelmarsh 6 | 52,560 | 50,750 | 52,560 | 50,750 |
| kelmarsh | Kelmarsh_SCADA_2019_3085.zip::Turbine_Data_Kelmarsh_1_2019-01-01_-_2020-01-01_228.csv | Kelmarsh 1 | 52,560 | 52,476 | 52,560 | 52,476 |
| kelmarsh | Kelmarsh_SCADA_2019_3085.zip::Turbine_Data_Kelmarsh_2_2019-01-01_-_2020-01-01_229.csv | Kelmarsh 2 | 52,560 | 52,489 | 52,560 | 52,489 |
| kelmarsh | Kelmarsh_SCADA_2019_3085.zip::Turbine_Data_Kelmarsh_3_2019-01-01_-_2020-01-01_230.csv | Kelmarsh 3 | 52,560 | 52,488 | 52,560 | 52,488 |
| kelmarsh | Kelmarsh_SCADA_2019_3085.zip::Turbine_Data_Kelmarsh_4_2019-01-01_-_2020-01-01_231.csv | Kelmarsh 4 | 52,560 | 52,506 | 52,560 | 52,506 |
| kelmarsh | Kelmarsh_SCADA_2019_3085.zip::Turbine_Data_Kelmarsh_5_2019-01-01_-_2020-01-01_232.csv | Kelmarsh 5 | 52,560 | 52,479 | 52,560 | 52,479 |
| kelmarsh | Kelmarsh_SCADA_2019_3085.zip::Turbine_Data_Kelmarsh_6_2019-01-01_-_2020-01-01_233.csv | Kelmarsh 6 | 52,560 | 52,506 | 52,560 | 52,506 |
| kelmarsh | Kelmarsh_SCADA_2020_3086.zip::Turbine_Data_Kelmarsh_1_2020-01-01_-_2021-01-01_228.csv | Kelmarsh 1 | 52,704 | 52,236 | 52,704 | 52,236 |
| kelmarsh | Kelmarsh_SCADA_2020_3086.zip::Turbine_Data_Kelmarsh_2_2020-01-01_-_2021-01-01_229.csv | Kelmarsh 2 | 52,704 | 52,253 | 52,704 | 52,253 |
| kelmarsh | Kelmarsh_SCADA_2020_3086.zip::Turbine_Data_Kelmarsh_3_2020-01-01_-_2021-01-01_230.csv | Kelmarsh 3 | 52,704 | 52,210 | 52,704 | 52,210 |
| kelmarsh | Kelmarsh_SCADA_2020_3086.zip::Turbine_Data_Kelmarsh_4_2020-01-01_-_2021-01-01_231.csv | Kelmarsh 4 | 52,704 | 52,244 | 52,704 | 52,244 |
| kelmarsh | Kelmarsh_SCADA_2020_3086.zip::Turbine_Data_Kelmarsh_5_2020-01-01_-_2021-01-01_232.csv | Kelmarsh 5 | 52,704 | 52,249 | 52,704 | 52,249 |
| kelmarsh | Kelmarsh_SCADA_2020_3086.zip::Turbine_Data_Kelmarsh_6_2020-01-01_-_2021-01-01_233.csv | Kelmarsh 6 | 52,704 | 52,251 | 52,704 | 52,251 |
| kelmarsh | Kelmarsh_SCADA_2021_4456.zip::Turbine_Data_Kelmarsh_1_2021-01-01_-_2022-01-01_228.csv | Kelmarsh 1 | 52,560 | 52,050 | 52,560 | 52,050 |
| kelmarsh | Kelmarsh_SCADA_2021_4456.zip::Turbine_Data_Kelmarsh_2_2021-01-01_-_2022-01-01_229.csv | Kelmarsh 2 | 52,560 | 52,042 | 52,560 | 52,042 |
| kelmarsh | Kelmarsh_SCADA_2021_4456.zip::Turbine_Data_Kelmarsh_3_2021-01-01_-_2022-01-01_230.csv | Kelmarsh 3 | 52,560 | 51,573 | 52,560 | 51,573 |
| kelmarsh | Kelmarsh_SCADA_2021_4456.zip::Turbine_Data_Kelmarsh_4_2021-01-01_-_2022-01-01_231.csv | Kelmarsh 4 | 52,560 | 52,038 | 52,560 | 52,038 |
| kelmarsh | Kelmarsh_SCADA_2021_4456.zip::Turbine_Data_Kelmarsh_5_2021-01-01_-_2022-01-01_232.csv | Kelmarsh 5 | 52,560 | 51,467 | 52,560 | 51,467 |
| kelmarsh | Kelmarsh_SCADA_2021_4456.zip::Turbine_Data_Kelmarsh_6_2021-01-01_-_2022-01-01_233.csv | Kelmarsh 6 | 52,560 | 52,017 | 52,560 | 52,017 |
| kelmarsh | Kelmarsh_SCADA_2022_4457.zip::Turbine_Data_Kelmarsh_1_2022-01-01_-_2023-01-01_228.csv | Kelmarsh 1 | 52,560 | 52,010 | 52,560 | 52,010 |
| kelmarsh | Kelmarsh_SCADA_2022_4457.zip::Turbine_Data_Kelmarsh_2_2022-01-01_-_2023-01-01_229.csv | Kelmarsh 2 | 52,560 | 52,488 | 52,560 | 52,488 |
| kelmarsh | Kelmarsh_SCADA_2022_4457.zip::Turbine_Data_Kelmarsh_3_2022-01-01_-_2023-01-01_230.csv | Kelmarsh 3 | 52,560 | 52,448 | 52,560 | 52,448 |
| kelmarsh | Kelmarsh_SCADA_2022_4457.zip::Turbine_Data_Kelmarsh_4_2022-01-01_-_2023-01-01_231.csv | Kelmarsh 4 | 52,560 | 52,327 | 52,560 | 52,327 |
| kelmarsh | Kelmarsh_SCADA_2022_4457.zip::Turbine_Data_Kelmarsh_5_2022-01-01_-_2023-01-01_232.csv | Kelmarsh 5 | 52,560 | 52,449 | 52,560 | 52,449 |
| kelmarsh | Kelmarsh_SCADA_2022_4457.zip::Turbine_Data_Kelmarsh_6_2022-01-01_-_2023-01-01_233.csv | Kelmarsh 6 | 52,560 | 52,324 | 52,560 | 52,324 |
| kelmarsh | Kelmarsh_SCADA_2023_5961.zip::Turbine_Data_Kelmarsh_1_2023-01-01_-_2024-01-01_228.csv | Kelmarsh 1 | 2,174,760 | 52,477 | 52,560 | 52,477 |
| kelmarsh | Kelmarsh_SCADA_2023_5961.zip::Turbine_Data_Kelmarsh_2_2023-01-01_-_2024-01-01_229.csv | Kelmarsh 2 | 2,174,760 | 52,479 | 52,560 | 52,479 |
| kelmarsh | Kelmarsh_SCADA_2023_5961.zip::Turbine_Data_Kelmarsh_3_2023-01-01_-_2024-01-01_230.csv | Kelmarsh 3 | 2,174,760 | 52,306 | 52,560 | 52,306 |
| kelmarsh | Kelmarsh_SCADA_2023_5961.zip::Turbine_Data_Kelmarsh_4_2023-01-01_-_2024-01-01_231.csv | Kelmarsh 4 | 2,174,760 | 52,331 | 52,560 | 52,331 |
| kelmarsh | Kelmarsh_SCADA_2023_5961.zip::Turbine_Data_Kelmarsh_5_2023-01-01_-_2024-01-01_232.csv | Kelmarsh 5 | 2,174,760 | 52,454 | 52,560 | 52,454 |
| kelmarsh | Kelmarsh_SCADA_2023_5961.zip::Turbine_Data_Kelmarsh_6_2023-01-01_-_2024-01-01_233.csv | Kelmarsh 6 | 2,174,760 | 52,261 | 52,560 | 52,261 |
| kelmarsh | Kelmarsh_SCADA_2024_5962.zip::Turbine_Data_Kelmarsh_1_2024-01-01_-_2025-01-01_228.csv | Kelmarsh 1 | 2,174,904 | 52,574 | 52,704 | 52,574 |
| kelmarsh | Kelmarsh_SCADA_2024_5962.zip::Turbine_Data_Kelmarsh_2_2024-01-01_-_2025-01-01_229.csv | Kelmarsh 2 | 2,174,904 | 52,604 | 52,704 | 52,604 |
| kelmarsh | Kelmarsh_SCADA_2024_5962.zip::Turbine_Data_Kelmarsh_3_2024-01-01_-_2025-01-01_230.csv | Kelmarsh 3 | 2,174,904 | 52,575 | 52,704 | 52,575 |
| kelmarsh | Kelmarsh_SCADA_2024_5962.zip::Turbine_Data_Kelmarsh_4_2024-01-01_-_2025-01-01_231.csv | Kelmarsh 4 | 2,174,904 | 52,293 | 52,704 | 52,293 |
| kelmarsh | Kelmarsh_SCADA_2024_5962.zip::Turbine_Data_Kelmarsh_5_2024-01-01_-_2025-01-01_232.csv | Kelmarsh 5 | 2,174,904 | 52,493 | 52,704 | 52,493 |
| kelmarsh | Kelmarsh_SCADA_2024_5962.zip::Turbine_Data_Kelmarsh_6_2024-01-01_-_2025-01-01_233.csv | Kelmarsh 6 | 2,174,904 | 51,868 | 52,704 | 51,868 |
| penmanshiel | Penmanshiel_SCADA_2016_WT01-10_3107.zip::Turbine_Data_Penmanshiel_01_2016-06-06_-_2017-01-01_1042.csv | Penmanshiel 01 | 29,987 | 28,943 | 29,987 | 28,943 |
| penmanshiel | Penmanshiel_SCADA_2016_WT01-10_3107.zip::Turbine_Data_Penmanshiel_02_2016-06-03_-_2017-01-01_1043.csv | Penmanshiel 02 | 30,475 | 28,843 | 30,475 | 28,843 |
| penmanshiel | Penmanshiel_SCADA_2016_WT01-10_3107.zip::Turbine_Data_Penmanshiel_04_2016-06-13_-_2017-01-01_1044.csv | Penmanshiel 04 | 28,999 | 28,524 | 28,999 | 28,524 |
| penmanshiel | Penmanshiel_SCADA_2016_WT01-10_3107.zip::Turbine_Data_Penmanshiel_05_2016-06-15_-_2017-01-01_1045.csv | Penmanshiel 05 | 28,687 | 28,274 | 28,687 | 28,274 |
| penmanshiel | Penmanshiel_SCADA_2016_WT01-10_3107.zip::Turbine_Data_Penmanshiel_06_2016-06-02_-_2017-01-01_1046.csv | Penmanshiel 06 | 30,564 | 27,500 | 30,564 | 27,500 |
| penmanshiel | Penmanshiel_SCADA_2016_WT01-10_3107.zip::Turbine_Data_Penmanshiel_07_2016-06-02_-_2017-01-01_1047.csv | Penmanshiel 07 | 30,566 | 30,025 | 30,566 | 30,025 |
| penmanshiel | Penmanshiel_SCADA_2016_WT01-10_3107.zip::Turbine_Data_Penmanshiel_08_2016-07-27_-_2017-01-01_1048.csv | Penmanshiel 08 | 22,658 | 19,418 | 22,658 | 19,418 |
| penmanshiel | Penmanshiel_SCADA_2016_WT01-10_3107.zip::Turbine_Data_Penmanshiel_09_2016-06-24_-_2017-01-01_1049.csv | Penmanshiel 09 | 27,434 | 18,991 | 27,434 | 18,991 |
| penmanshiel | Penmanshiel_SCADA_2016_WT01-10_3107.zip::Turbine_Data_Penmanshiel_10_2016-06-27_-_2017-01-01_1050.csv | Penmanshiel 10 | 26,964 | 18,929 | 26,964 | 18,929 |
| penmanshiel | Penmanshiel_SCADA_2016_WT11-15_3107.zip::Turbine_Data_Penmanshiel_11_2016-07-19_-_2017-01-01_1051.csv | Penmanshiel 11 | 23,846 | 19,286 | 23,846 | 19,286 |
| penmanshiel | Penmanshiel_SCADA_2016_WT11-15_3107.zip::Turbine_Data_Penmanshiel_12_2016-07-02_-_2017-01-01_1052.csv | Penmanshiel 12 | 26,254 | 19,354 | 26,254 | 19,354 |
| penmanshiel | Penmanshiel_SCADA_2016_WT11-15_3107.zip::Turbine_Data_Penmanshiel_13_2016-06-30_-_2017-01-01_1053.csv | Penmanshiel 13 | 26,552 | 19,038 | 26,552 | 19,038 |
| penmanshiel | Penmanshiel_SCADA_2016_WT11-15_3107.zip::Turbine_Data_Penmanshiel_14_2016-07-09_-_2017-01-01_1054.csv | Penmanshiel 14 | 25,246 | 18,554 | 25,246 | 18,554 |
| penmanshiel | Penmanshiel_SCADA_2016_WT11-15_3107.zip::Turbine_Data_Penmanshiel_15_2016-07-14_-_2017-01-01_1056.csv | Penmanshiel 15 | 24,504 | 19,175 | 24,504 | 19,175 |
| penmanshiel | Penmanshiel_SCADA_2017_WT01-10_3114.zip::Turbine_Data_Penmanshiel_01_2017-01-01_-_2018-01-01_1042.csv | Penmanshiel 01 | 52,560 | 52,394 | 52,560 | 52,394 |
| penmanshiel | Penmanshiel_SCADA_2017_WT01-10_3114.zip::Turbine_Data_Penmanshiel_02_2017-01-01_-_2018-01-01_1043.csv | Penmanshiel 02 | 52,560 | 52,342 | 52,560 | 52,342 |
| penmanshiel | Penmanshiel_SCADA_2017_WT01-10_3114.zip::Turbine_Data_Penmanshiel_04_2017-01-01_-_2018-01-01_1044.csv | Penmanshiel 04 | 52,560 | 52,427 | 52,560 | 52,427 |
| penmanshiel | Penmanshiel_SCADA_2017_WT01-10_3114.zip::Turbine_Data_Penmanshiel_05_2017-01-01_-_2018-01-01_1045.csv | Penmanshiel 05 | 52,560 | 52,429 | 52,560 | 52,429 |
| penmanshiel | Penmanshiel_SCADA_2017_WT01-10_3114.zip::Turbine_Data_Penmanshiel_06_2017-01-01_-_2018-01-01_1046.csv | Penmanshiel 06 | 52,560 | 52,241 | 52,560 | 52,241 |
| penmanshiel | Penmanshiel_SCADA_2017_WT01-10_3114.zip::Turbine_Data_Penmanshiel_07_2017-01-01_-_2018-01-01_1047.csv | Penmanshiel 07 | 52,560 | 52,425 | 52,560 | 52,425 |
| penmanshiel | Penmanshiel_SCADA_2017_WT01-10_3114.zip::Turbine_Data_Penmanshiel_08_2017-01-01_-_2018-01-01_1048.csv | Penmanshiel 08 | 52,560 | 52,449 | 52,560 | 52,449 |
| penmanshiel | Penmanshiel_SCADA_2017_WT01-10_3114.zip::Turbine_Data_Penmanshiel_09_2017-01-01_-_2018-01-01_1049.csv | Penmanshiel 09 | 52,560 | 52,254 | 52,560 | 52,254 |
| penmanshiel | Penmanshiel_SCADA_2017_WT01-10_3114.zip::Turbine_Data_Penmanshiel_10_2017-01-01_-_2018-01-01_1050.csv | Penmanshiel 10 | 52,560 | 52,428 | 52,560 | 52,428 |
| penmanshiel | Penmanshiel_SCADA_2017_WT11-15_3115.zip::Turbine_Data_Penmanshiel_11_2017-01-01_-_2018-01-01_1051.csv | Penmanshiel 11 | 52,560 | 52,427 | 52,560 | 52,427 |
| penmanshiel | Penmanshiel_SCADA_2017_WT11-15_3115.zip::Turbine_Data_Penmanshiel_12_2017-01-01_-_2018-01-01_1052.csv | Penmanshiel 12 | 52,560 | 52,413 | 52,560 | 52,413 |
| penmanshiel | Penmanshiel_SCADA_2017_WT11-15_3115.zip::Turbine_Data_Penmanshiel_13_2017-01-01_-_2018-01-01_1053.csv | Penmanshiel 13 | 52,560 | 52,419 | 52,560 | 52,419 |
| penmanshiel | Penmanshiel_SCADA_2017_WT11-15_3115.zip::Turbine_Data_Penmanshiel_14_2017-01-01_-_2018-01-01_1054.csv | Penmanshiel 14 | 52,560 | 52,427 | 52,560 | 52,427 |
| penmanshiel | Penmanshiel_SCADA_2017_WT11-15_3115.zip::Turbine_Data_Penmanshiel_15_2017-01-01_-_2018-01-01_1056.csv | Penmanshiel 15 | 52,560 | 52,426 | 52,560 | 52,426 |
| penmanshiel | Penmanshiel_SCADA_2018_WT01-10_3113.zip::Turbine_Data_Penmanshiel_01_2018-01-01_-_2019-01-01_1042.csv | Penmanshiel 01 | 52,560 | 52,456 | 52,560 | 52,456 |
| penmanshiel | Penmanshiel_SCADA_2018_WT01-10_3113.zip::Turbine_Data_Penmanshiel_02_2018-01-01_-_2019-01-01_1043.csv | Penmanshiel 02 | 52,560 | 51,664 | 52,560 | 51,664 |
| penmanshiel | Penmanshiel_SCADA_2018_WT01-10_3113.zip::Turbine_Data_Penmanshiel_04_2018-01-01_-_2019-01-01_1044.csv | Penmanshiel 04 | 52,560 | 52,461 | 52,560 | 52,461 |
| penmanshiel | Penmanshiel_SCADA_2018_WT01-10_3113.zip::Turbine_Data_Penmanshiel_05_2018-01-01_-_2019-01-01_1045.csv | Penmanshiel 05 | 52,560 | 52,456 | 52,560 | 52,456 |
| penmanshiel | Penmanshiel_SCADA_2018_WT01-10_3113.zip::Turbine_Data_Penmanshiel_06_2018-01-01_-_2019-01-01_1046.csv | Penmanshiel 06 | 52,560 | 52,139 | 52,560 | 52,139 |
| penmanshiel | Penmanshiel_SCADA_2018_WT01-10_3113.zip::Turbine_Data_Penmanshiel_07_2018-01-01_-_2019-01-01_1047.csv | Penmanshiel 07 | 52,560 | 52,464 | 52,560 | 52,464 |
| penmanshiel | Penmanshiel_SCADA_2018_WT01-10_3113.zip::Turbine_Data_Penmanshiel_08_2018-01-01_-_2019-01-01_1048.csv | Penmanshiel 08 | 52,560 | 52,431 | 52,560 | 52,431 |
| penmanshiel | Penmanshiel_SCADA_2018_WT01-10_3113.zip::Turbine_Data_Penmanshiel_09_2018-01-01_-_2019-01-01_1049.csv | Penmanshiel 09 | 52,560 | 52,290 | 52,560 | 52,290 |
| penmanshiel | Penmanshiel_SCADA_2018_WT01-10_3113.zip::Turbine_Data_Penmanshiel_10_2018-01-01_-_2019-01-01_1050.csv | Penmanshiel 10 | 52,560 | 51,757 | 52,560 | 51,757 |
| penmanshiel | Penmanshiel_SCADA_2018_WT11-15_3116.zip::Turbine_Data_Penmanshiel_11_2018-01-01_-_2019-01-01_1051.csv | Penmanshiel 11 | 52,560 | 52,390 | 52,560 | 52,390 |
| penmanshiel | Penmanshiel_SCADA_2018_WT11-15_3116.zip::Turbine_Data_Penmanshiel_12_2018-01-01_-_2019-01-01_1052.csv | Penmanshiel 12 | 52,560 | 52,411 | 52,560 | 52,411 |
| penmanshiel | Penmanshiel_SCADA_2018_WT11-15_3116.zip::Turbine_Data_Penmanshiel_13_2018-01-01_-_2019-01-01_1053.csv | Penmanshiel 13 | 52,560 | 52,410 | 52,560 | 52,410 |
| penmanshiel | Penmanshiel_SCADA_2018_WT11-15_3116.zip::Turbine_Data_Penmanshiel_14_2018-01-01_-_2019-01-01_1054.csv | Penmanshiel 14 | 52,560 | 52,407 | 52,560 | 52,407 |
| penmanshiel | Penmanshiel_SCADA_2018_WT11-15_3116.zip::Turbine_Data_Penmanshiel_15_2018-01-01_-_2019-01-01_1056.csv | Penmanshiel 15 | 52,560 | 52,405 | 52,560 | 52,405 |
| penmanshiel | Penmanshiel_SCADA_2019_WT01-10_3112.zip::Turbine_Data_Penmanshiel_01_2019-01-01_-_2020-01-01_1042.csv | Penmanshiel 01 | 52,560 | 52,174 | 52,560 | 52,174 |
| penmanshiel | Penmanshiel_SCADA_2019_WT01-10_3112.zip::Turbine_Data_Penmanshiel_02_2019-01-01_-_2020-01-01_1043.csv | Penmanshiel 02 | 52,560 | 52,276 | 52,560 | 52,276 |
| penmanshiel | Penmanshiel_SCADA_2019_WT01-10_3112.zip::Turbine_Data_Penmanshiel_04_2019-01-01_-_2020-01-01_1044.csv | Penmanshiel 04 | 52,560 | 52,146 | 52,560 | 52,146 |
| penmanshiel | Penmanshiel_SCADA_2019_WT01-10_3112.zip::Turbine_Data_Penmanshiel_05_2019-01-01_-_2020-01-01_1045.csv | Penmanshiel 05 | 52,560 | 52,099 | 52,560 | 52,099 |
| penmanshiel | Penmanshiel_SCADA_2019_WT01-10_3112.zip::Turbine_Data_Penmanshiel_06_2019-01-01_-_2020-01-01_1046.csv | Penmanshiel 06 | 52,560 | 52,070 | 52,560 | 52,070 |
| penmanshiel | Penmanshiel_SCADA_2019_WT01-10_3112.zip::Turbine_Data_Penmanshiel_07_2019-01-01_-_2020-01-01_1047.csv | Penmanshiel 07 | 52,560 | 50,569 | 52,560 | 50,569 |
| penmanshiel | Penmanshiel_SCADA_2019_WT01-10_3112.zip::Turbine_Data_Penmanshiel_08_2019-01-01_-_2020-01-01_1048.csv | Penmanshiel 08 | 52,560 | 52,326 | 52,560 | 52,326 |
| penmanshiel | Penmanshiel_SCADA_2019_WT01-10_3112.zip::Turbine_Data_Penmanshiel_09_2019-01-01_-_2020-01-01_1049.csv | Penmanshiel 09 | 52,560 | 52,278 | 52,560 | 52,278 |
| penmanshiel | Penmanshiel_SCADA_2019_WT01-10_3112.zip::Turbine_Data_Penmanshiel_10_2019-01-01_-_2020-01-01_1050.csv | Penmanshiel 10 | 52,560 | 52,175 | 52,560 | 52,175 |
| penmanshiel | Penmanshiel_SCADA_2019_WT11-15_3117.zip::Turbine_Data_Penmanshiel_11_2019-01-01_-_2020-01-01_1051.csv | Penmanshiel 11 | 52,560 | 52,128 | 52,560 | 52,128 |
| penmanshiel | Penmanshiel_SCADA_2019_WT11-15_3117.zip::Turbine_Data_Penmanshiel_12_2019-01-01_-_2020-01-01_1052.csv | Penmanshiel 12 | 52,560 | 52,136 | 52,560 | 52,136 |
| penmanshiel | Penmanshiel_SCADA_2019_WT11-15_3117.zip::Turbine_Data_Penmanshiel_13_2019-01-01_-_2020-01-01_1053.csv | Penmanshiel 13 | 52,560 | 52,268 | 52,560 | 52,268 |
| penmanshiel | Penmanshiel_SCADA_2019_WT11-15_3117.zip::Turbine_Data_Penmanshiel_14_2019-01-01_-_2020-01-01_1054.csv | Penmanshiel 14 | 52,560 | 52,131 | 52,560 | 52,131 |
| penmanshiel | Penmanshiel_SCADA_2019_WT11-15_3117.zip::Turbine_Data_Penmanshiel_15_2019-01-01_-_2020-01-01_1056.csv | Penmanshiel 15 | 52,560 | 52,124 | 52,560 | 52,124 |
| penmanshiel | Penmanshiel_SCADA_2020_WT01-10_3109.zip::Turbine_Data_Penmanshiel_01_2020-01-01_-_2021-01-01_1042.csv | Penmanshiel 01 | 52,704 | 49,604 | 52,704 | 49,604 |
| penmanshiel | Penmanshiel_SCADA_2020_WT01-10_3109.zip::Turbine_Data_Penmanshiel_02_2020-01-01_-_2021-01-01_1043.csv | Penmanshiel 02 | 52,704 | 49,622 | 52,704 | 49,622 |
| penmanshiel | Penmanshiel_SCADA_2020_WT01-10_3109.zip::Turbine_Data_Penmanshiel_04_2020-01-01_-_2021-01-01_1044.csv | Penmanshiel 04 | 52,704 | 49,675 | 52,704 | 49,675 |
| penmanshiel | Penmanshiel_SCADA_2020_WT01-10_3109.zip::Turbine_Data_Penmanshiel_05_2020-01-01_-_2021-01-01_1045.csv | Penmanshiel 05 | 52,704 | 49,682 | 52,704 | 49,682 |
| penmanshiel | Penmanshiel_SCADA_2020_WT01-10_3109.zip::Turbine_Data_Penmanshiel_06_2020-01-01_-_2021-01-01_1046.csv | Penmanshiel 06 | 52,704 | 49,837 | 52,704 | 49,837 |
| penmanshiel | Penmanshiel_SCADA_2020_WT01-10_3109.zip::Turbine_Data_Penmanshiel_07_2020-01-01_-_2021-01-01_1047.csv | Penmanshiel 07 | 52,704 | 49,729 | 52,704 | 49,729 |
| penmanshiel | Penmanshiel_SCADA_2020_WT01-10_3109.zip::Turbine_Data_Penmanshiel_08_2020-01-01_-_2021-01-01_1048.csv | Penmanshiel 08 | 52,704 | 49,892 | 52,704 | 49,892 |
| penmanshiel | Penmanshiel_SCADA_2020_WT01-10_3109.zip::Turbine_Data_Penmanshiel_09_2020-01-01_-_2021-01-01_1049.csv | Penmanshiel 09 | 52,704 | 49,981 | 52,704 | 49,981 |
| penmanshiel | Penmanshiel_SCADA_2020_WT01-10_3109.zip::Turbine_Data_Penmanshiel_10_2020-01-01_-_2021-01-01_1050.csv | Penmanshiel 10 | 52,704 | 49,867 | 52,704 | 49,867 |
| penmanshiel | Penmanshiel_SCADA_2020_WT11-15_3118.zip::Turbine_Data_Penmanshiel_11_2020-01-01_-_2021-01-01_1051.csv | Penmanshiel 11 | 52,704 | 49,731 | 52,704 | 49,731 |
| penmanshiel | Penmanshiel_SCADA_2020_WT11-15_3118.zip::Turbine_Data_Penmanshiel_12_2020-01-01_-_2021-01-01_1052.csv | Penmanshiel 12 | 52,704 | 49,881 | 52,704 | 49,881 |
| penmanshiel | Penmanshiel_SCADA_2020_WT11-15_3118.zip::Turbine_Data_Penmanshiel_13_2020-01-01_-_2021-01-01_1053.csv | Penmanshiel 13 | 52,704 | 49,633 | 52,704 | 49,633 |
| penmanshiel | Penmanshiel_SCADA_2020_WT11-15_3118.zip::Turbine_Data_Penmanshiel_14_2020-01-01_-_2021-01-01_1054.csv | Penmanshiel 14 | 52,704 | 49,881 | 52,704 | 49,881 |
| penmanshiel | Penmanshiel_SCADA_2020_WT11-15_3118.zip::Turbine_Data_Penmanshiel_15_2020-01-01_-_2021-01-01_1056.csv | Penmanshiel 15 | 52,704 | 49,738 | 52,704 | 49,738 |
| penmanshiel | Penmanshiel_SCADA_2021_WT01-10_4460.zip::Turbine_Data_Penmanshiel_01_2021-01-01_-_2022-01-01_1042.csv | Penmanshiel 01 | 52,560 | 52,497 | 52,560 | 52,497 |
| penmanshiel | Penmanshiel_SCADA_2021_WT01-10_4460.zip::Turbine_Data_Penmanshiel_02_2021-01-01_-_2022-01-01_1043.csv | Penmanshiel 02 | 52,560 | 52,486 | 52,560 | 52,486 |
| penmanshiel | Penmanshiel_SCADA_2021_WT01-10_4460.zip::Turbine_Data_Penmanshiel_04_2021-01-01_-_2022-01-01_1044.csv | Penmanshiel 04 | 52,560 | 52,398 | 52,560 | 52,398 |
| penmanshiel | Penmanshiel_SCADA_2021_WT01-10_4460.zip::Turbine_Data_Penmanshiel_05_2021-01-01_-_2022-01-01_1045.csv | Penmanshiel 05 | 52,560 | 52,474 | 52,560 | 52,474 |
| penmanshiel | Penmanshiel_SCADA_2021_WT01-10_4460.zip::Turbine_Data_Penmanshiel_06_2021-01-01_-_2022-01-01_1046.csv | Penmanshiel 06 | 52,560 | 52,420 | 52,560 | 52,420 |
| penmanshiel | Penmanshiel_SCADA_2021_WT01-10_4460.zip::Turbine_Data_Penmanshiel_07_2021-01-01_-_2022-01-01_1047.csv | Penmanshiel 07 | 52,560 | 52,330 | 52,560 | 52,330 |
| penmanshiel | Penmanshiel_SCADA_2021_WT01-10_4460.zip::Turbine_Data_Penmanshiel_08_2021-01-01_-_2022-01-01_1048.csv | Penmanshiel 08 | 52,560 | 52,460 | 52,560 | 52,460 |
| penmanshiel | Penmanshiel_SCADA_2021_WT01-10_4460.zip::Turbine_Data_Penmanshiel_09_2021-01-01_-_2022-01-01_1049.csv | Penmanshiel 09 | 52,560 | 52,459 | 52,560 | 52,459 |
| penmanshiel | Penmanshiel_SCADA_2021_WT01-10_4460.zip::Turbine_Data_Penmanshiel_10_2021-01-01_-_2022-01-01_1050.csv | Penmanshiel 10 | 52,560 | 52,411 | 52,560 | 52,411 |
| penmanshiel | Penmanshiel_SCADA_2021_WT11-15_4461.zip::Turbine_Data_Penmanshiel_11_2021-01-01_-_2022-01-01_1051.csv | Penmanshiel 11 | 52,560 | 52,030 | 52,560 | 52,030 |
| penmanshiel | Penmanshiel_SCADA_2021_WT11-15_4461.zip::Turbine_Data_Penmanshiel_12_2021-01-01_-_2022-01-01_1052.csv | Penmanshiel 12 | 52,560 | 52,464 | 52,560 | 52,464 |
| penmanshiel | Penmanshiel_SCADA_2021_WT11-15_4461.zip::Turbine_Data_Penmanshiel_13_2021-01-01_-_2022-01-01_1053.csv | Penmanshiel 13 | 52,560 | 52,431 | 52,560 | 52,431 |
| penmanshiel | Penmanshiel_SCADA_2021_WT11-15_4461.zip::Turbine_Data_Penmanshiel_14_2021-01-01_-_2022-01-01_1054.csv | Penmanshiel 14 | 52,560 | 52,430 | 52,560 | 52,430 |
| penmanshiel | Penmanshiel_SCADA_2021_WT11-15_4461.zip::Turbine_Data_Penmanshiel_15_2021-01-01_-_2022-01-01_1056.csv | Penmanshiel 15 | 52,560 | 52,381 | 52,560 | 52,381 |
| penmanshiel | Penmanshiel_SCADA_2022_WT01-10_4462.zip::Turbine_Data_Penmanshiel_01_2022-01-01_-_2023-01-01_1042.csv | Penmanshiel 01 | 52,560 | 52,467 | 52,560 | 52,467 |
| penmanshiel | Penmanshiel_SCADA_2022_WT01-10_4462.zip::Turbine_Data_Penmanshiel_02_2022-01-01_-_2023-01-01_1043.csv | Penmanshiel 02 | 52,560 | 52,475 | 52,560 | 52,475 |
| penmanshiel | Penmanshiel_SCADA_2022_WT01-10_4462.zip::Turbine_Data_Penmanshiel_04_2022-01-01_-_2023-01-01_1044.csv | Penmanshiel 04 | 52,560 | 52,307 | 52,560 | 52,307 |
| penmanshiel | Penmanshiel_SCADA_2022_WT01-10_4462.zip::Turbine_Data_Penmanshiel_05_2022-01-01_-_2023-01-01_1045.csv | Penmanshiel 05 | 52,560 | 52,363 | 52,560 | 52,363 |
| penmanshiel | Penmanshiel_SCADA_2022_WT01-10_4462.zip::Turbine_Data_Penmanshiel_06_2022-01-01_-_2023-01-01_1046.csv | Penmanshiel 06 | 52,560 | 52,465 | 52,560 | 52,465 |
| penmanshiel | Penmanshiel_SCADA_2022_WT01-10_4462.zip::Turbine_Data_Penmanshiel_07_2022-01-01_-_2023-01-01_1047.csv | Penmanshiel 07 | 52,560 | 51,750 | 52,560 | 51,750 |
| penmanshiel | Penmanshiel_SCADA_2022_WT01-10_4462.zip::Turbine_Data_Penmanshiel_08_2022-01-01_-_2023-01-01_1048.csv | Penmanshiel 08 | 52,560 | 52,472 | 52,560 | 52,472 |
| penmanshiel | Penmanshiel_SCADA_2022_WT01-10_4462.zip::Turbine_Data_Penmanshiel_09_2022-01-01_-_2023-01-01_1049.csv | Penmanshiel 09 | 52,560 | 52,469 | 52,560 | 52,469 |
| penmanshiel | Penmanshiel_SCADA_2022_WT01-10_4462.zip::Turbine_Data_Penmanshiel_10_2022-01-01_-_2023-01-01_1050.csv | Penmanshiel 10 | 52,560 | 52,438 | 52,560 | 52,438 |
| penmanshiel | Penmanshiel_SCADA_2022_WT11-15_4463.zip::Turbine_Data_Penmanshiel_11_2022-01-01_-_2023-01-01_1051.csv | Penmanshiel 11 | 52,560 | 48,320 | 52,560 | 48,320 |
| penmanshiel | Penmanshiel_SCADA_2022_WT11-15_4463.zip::Turbine_Data_Penmanshiel_12_2022-01-01_-_2023-01-01_1052.csv | Penmanshiel 12 | 52,560 | 52,437 | 52,560 | 52,437 |
| penmanshiel | Penmanshiel_SCADA_2022_WT11-15_4463.zip::Turbine_Data_Penmanshiel_13_2022-01-01_-_2023-01-01_1053.csv | Penmanshiel 13 | 52,560 | 52,444 | 52,560 | 52,444 |
| penmanshiel | Penmanshiel_SCADA_2022_WT11-15_4463.zip::Turbine_Data_Penmanshiel_14_2022-01-01_-_2023-01-01_1054.csv | Penmanshiel 14 | 52,560 | 52,303 | 52,560 | 52,303 |
| penmanshiel | Penmanshiel_SCADA_2022_WT11-15_4463.zip::Turbine_Data_Penmanshiel_15_2022-01-01_-_2023-01-01_1056.csv | Penmanshiel 15 | 52,560 | 52,430 | 52,560 | 52,430 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_01.csv | 21 stations | 93,723 | 93,720 | 93,723 | 93,720 |
| hill_of_towie | 2019.zip::tblSCTurTemp_2019_01.csv | 21 stations | 93,720 | 93,720 | 93,720 | 93,720 |
| hill_of_towie | 2019.zip::tblSCTurbine_2019_01.csv | 21 stations | 93,723 | 93,723 | 93,723 | 93,723 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_02.csv | 21 stations | 84,611 | 84,606 | 84,611 | 84,606 |
| hill_of_towie | 2019.zip::tblSCTurTemp_2019_02.csv | 21 stations | 84,606 | 84,606 | 84,606 | 84,606 |
| hill_of_towie | 2019.zip::tblSCTurbine_2019_02.csv | 21 stations | 84,611 | 84,611 | 84,611 | 84,611 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_03.csv | 21 stations | 93,735 | 93,735 | 93,735 | 93,735 |
| hill_of_towie | 2019.zip::tblSCTurTemp_2019_03.csv | 21 stations | 93,735 | 93,735 | 93,735 | 93,735 |
| hill_of_towie | 2019.zip::tblSCTurbine_2019_03.csv | 21 stations | 93,735 | 93,735 | 93,735 | 93,735 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_04.csv | 21 stations | 90,690 | 90,690 | 90,690 | 90,690 |
| hill_of_towie | 2019.zip::tblSCTurTemp_2019_04.csv | 21 stations | 90,690 | 90,690 | 90,690 | 90,690 |
| hill_of_towie | 2019.zip::tblSCTurbine_2019_04.csv | 21 stations | 90,690 | 90,690 | 90,690 | 90,690 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_05.csv | 21 stations | 93,750 | 93,750 | 93,750 | 93,750 |
| hill_of_towie | 2019.zip::tblSCTurTemp_2019_05.csv | 21 stations | 93,750 | 93,750 | 93,750 | 93,750 |
| hill_of_towie | 2019.zip::tblSCTurbine_2019_05.csv | 21 stations | 93,750 | 93,750 | 93,750 | 93,750 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_06.csv | 21 stations | 90,689 | 90,689 | 90,689 | 90,689 |
| hill_of_towie | 2019.zip::tblSCTurTemp_2019_06.csv | 21 stations | 90,689 | 90,689 | 90,689 | 90,689 |
| hill_of_towie | 2019.zip::tblSCTurbine_2019_06.csv | 21 stations | 90,689 | 90,689 | 90,689 | 90,689 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_07.csv | 21 stations | 92,943 | 92,942 | 92,943 | 92,942 |
| hill_of_towie | 2019.zip::tblSCTurTemp_2019_07.csv | 21 stations | 92,942 | 92,942 | 92,942 | 92,942 |
| hill_of_towie | 2019.zip::tblSCTurbine_2019_07.csv | 21 stations | 92,942 | 92,942 | 92,942 | 92,942 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_08.csv | 21 stations | 93,415 | 93,415 | 93,415 | 93,415 |
| hill_of_towie | 2019.zip::tblSCTurTemp_2019_08.csv | 21 stations | 93,415 | 93,414 | 93,415 | 93,414 |
| hill_of_towie | 2019.zip::tblSCTurbine_2019_08.csv | 21 stations | 93,415 | 93,415 | 93,415 | 93,415 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_09.csv | 21 stations | 89,531 | 89,531 | 89,531 | 89,531 |
| hill_of_towie | 2019.zip::tblSCTurTemp_2019_09.csv | 21 stations | 89,531 | 89,531 | 89,531 | 89,531 |
| hill_of_towie | 2019.zip::tblSCTurbine_2019_09.csv | 21 stations | 89,531 | 89,531 | 89,531 | 89,531 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_10.csv | 21 stations | 93,383 | 93,382 | 93,383 | 93,382 |
| hill_of_towie | 2019.zip::tblSCTurTemp_2019_10.csv | 21 stations | 93,382 | 93,382 | 93,382 | 93,382 |
| hill_of_towie | 2019.zip::tblSCTurbine_2019_10.csv | 21 stations | 93,383 | 93,383 | 93,383 | 93,383 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_11.csv | 21 stations | 90,660 | 90,660 | 90,660 | 90,660 |
| hill_of_towie | 2019.zip::tblSCTurTemp_2019_11.csv | 21 stations | 90,660 | 90,660 | 90,660 | 90,660 |
| hill_of_towie | 2019.zip::tblSCTurbine_2019_11.csv | 21 stations | 90,660 | 90,660 | 90,660 | 90,660 |
| hill_of_towie | 2019.zip::tblSCTurGrid_2019_12.csv | 21 stations | 93,765 | 93,765 | 93,765 | 93,765 |
| hill_of_towie | 2019.zip::tblSCTurTemp_2019_12.csv | 21 stations | 93,765 | 93,765 | 93,765 | 93,765 |
| hill_of_towie | 2019.zip::tblSCTurbine_2019_12.csv | 21 stations | 93,765 | 93,765 | 93,765 | 93,765 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_01.csv | 21 stations | 93,123 | 93,118 | 93,123 | 93,118 |
| hill_of_towie | 2023.zip::tblSCTurTemp_2023_01.csv | 21 stations | 93,123 | 93,118 | 93,123 | 93,118 |
| hill_of_towie | 2023.zip::tblSCTurbine_2023_01.csv | 21 stations | 93,123 | 93,118 | 93,123 | 93,118 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_02.csv | 21 stations | 84,600 | 84,596 | 84,600 | 84,596 |
| hill_of_towie | 2023.zip::tblSCTurTemp_2023_02.csv | 21 stations | 84,600 | 84,596 | 84,600 | 84,596 |
| hill_of_towie | 2023.zip::tblSCTurbine_2023_02.csv | 21 stations | 84,600 | 84,596 | 84,600 | 84,596 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_03.csv | 21 stations | 93,723 | 93,721 | 93,723 | 93,721 |
| hill_of_towie | 2023.zip::tblSCTurTemp_2023_03.csv | 21 stations | 93,723 | 93,721 | 93,723 | 93,721 |
| hill_of_towie | 2023.zip::tblSCTurbine_2023_03.csv | 21 stations | 93,723 | 93,721 | 93,723 | 93,721 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_04.csv | 21 stations | 90,701 | 90,689 | 90,701 | 90,689 |
| hill_of_towie | 2023.zip::tblSCTurTemp_2023_04.csv | 21 stations | 90,701 | 90,689 | 90,701 | 90,689 |
| hill_of_towie | 2023.zip::tblSCTurbine_2023_04.csv | 21 stations | 90,701 | 90,694 | 90,701 | 90,694 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_05.csv | 21 stations | 93,731 | 93,725 | 93,731 | 93,725 |
| hill_of_towie | 2023.zip::tblSCTurTemp_2023_05.csv | 21 stations | 93,731 | 93,725 | 93,731 | 93,725 |
| hill_of_towie | 2023.zip::tblSCTurbine_2023_05.csv | 21 stations | 93,731 | 93,725 | 93,731 | 93,725 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_06.csv | 21 stations | 89,552 | 89,462 | 89,552 | 89,462 |
| hill_of_towie | 2023.zip::tblSCTurTemp_2023_06.csv | 21 stations | 89,552 | 89,461 | 89,552 | 89,461 |
| hill_of_towie | 2023.zip::tblSCTurbine_2023_06.csv | 21 stations | 89,552 | 89,463 | 89,552 | 89,463 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_07.csv | 21 stations | 93,580 | 93,576 | 93,580 | 93,576 |
| hill_of_towie | 2023.zip::tblSCTurTemp_2023_07.csv | 21 stations | 93,580 | 93,576 | 93,580 | 93,576 |
| hill_of_towie | 2023.zip::tblSCTurbine_2023_07.csv | 21 stations | 93,580 | 93,580 | 93,580 | 93,580 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_08.csv | 21 stations | 93,423 | 93,417 | 93,423 | 93,417 |
| hill_of_towie | 2023.zip::tblSCTurTemp_2023_08.csv | 21 stations | 93,423 | 93,417 | 93,423 | 93,417 |
| hill_of_towie | 2023.zip::tblSCTurbine_2023_08.csv | 21 stations | 93,423 | 93,417 | 93,423 | 93,417 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_09.csv | 21 stations | 90,589 | 90,583 | 90,589 | 90,583 |
| hill_of_towie | 2023.zip::tblSCTurTemp_2023_09.csv | 21 stations | 90,589 | 90,583 | 90,589 | 90,583 |
| hill_of_towie | 2023.zip::tblSCTurbine_2023_09.csv | 21 stations | 90,589 | 90,583 | 90,589 | 90,583 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_10.csv | 21 stations | 93,757 | 93,756 | 93,757 | 93,756 |
| hill_of_towie | 2023.zip::tblSCTurTemp_2023_10.csv | 21 stations | 93,757 | 93,756 | 93,757 | 93,756 |
| hill_of_towie | 2023.zip::tblSCTurbine_2023_10.csv | 21 stations | 93,757 | 93,756 | 93,757 | 93,756 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_11.csv | 21 stations | 89,623 | 89,623 | 89,623 | 89,623 |
| hill_of_towie | 2023.zip::tblSCTurTemp_2023_11.csv | 21 stations | 89,623 | 89,623 | 89,623 | 89,623 |
| hill_of_towie | 2023.zip::tblSCTurbine_2023_11.csv | 21 stations | 89,623 | 89,623 | 89,623 | 89,623 |
| hill_of_towie | 2023.zip::tblSCTurGrid_2023_12.csv | 21 stations | 92,392 | 92,392 | 92,392 | 92,392 |
| hill_of_towie | 2023.zip::tblSCTurTemp_2023_12.csv | 21 stations | 92,392 | 92,392 | 92,392 | 92,392 |
| hill_of_towie | 2023.zip::tblSCTurbine_2023_12.csv | 21 stations | 92,392 | 92,392 | 92,392 | 92,392 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/0.csv | farm_a:asset0:dataset0 | 54,986 | 54,986 | 54,986 | 54,986 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/10.csv | farm_a:asset10:dataset10 | 53,592 | 53,592 | 53,592 | 53,592 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/13.csv | farm_a:asset21:dataset13 | 54,010 | 54,010 | 54,010 | 54,010 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/14.csv | farm_a:asset13:dataset14 | 54,197 | 54,197 | 54,197 | 54,197 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/17.csv | farm_a:asset10:dataset17 | 55,090 | 55,090 | 55,090 | 55,090 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/22.csv | farm_a:asset21:dataset22 | 53,036 | 53,036 | 53,036 | 53,036 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/24.csv | farm_a:asset0:dataset24 | 55,003 | 55,003 | 55,003 | 55,003 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/25.csv | farm_a:asset11:dataset25 | 54,712 | 54,712 | 54,712 | 54,712 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/26.csv | farm_a:asset0:dataset26 | 53,702 | 53,702 | 53,702 | 53,702 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/3.csv | farm_a:asset10:dataset3 | 55,487 | 55,487 | 55,487 | 55,487 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/38.csv | farm_a:asset13:dataset38 | 54,835 | 54,835 | 54,835 | 54,835 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/40.csv | farm_a:asset10:dataset40 | 56,158 | 56,158 | 56,158 | 56,158 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/42.csv | farm_a:asset10:dataset42 | 53,886 | 53,886 | 53,886 | 53,886 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/45.csv | farm_a:asset13:dataset45 | 53,739 | 53,739 | 53,739 | 53,739 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/51.csv | farm_a:asset21:dataset51 | 54,436 | 54,436 | 54,436 | 54,436 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/68.csv | farm_a:asset11:dataset68 | 54,358 | 54,358 | 54,358 | 54,358 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/69.csv | farm_a:asset11:dataset69 | 54,813 | 54,813 | 54,813 | 54,813 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/71.csv | farm_a:asset0:dataset71 | 54,744 | 54,744 | 54,744 | 54,744 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/72.csv | farm_a:asset21:dataset72 | 54,082 | 54,082 | 54,082 | 54,082 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/73.csv | farm_a:asset0:dataset73 | 54,042 | 54,042 | 54,042 | 54,042 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/84.csv | farm_a:asset13:dataset84 | 53,772 | 53,772 | 53,772 | 53,772 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/92.csv | farm_a:asset11:dataset92 | 54,067 | 54,067 | 54,067 | 54,067 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/19.csv | farm_b:asset11:dataset19 | 56,274 | 56,274 | 56,274 | 56,274 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/2.csv | farm_b:asset13:dataset2 | 54,774 | 54,774 | 54,774 | 54,774 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/21.csv | farm_b:asset0:dataset21 | 53,514 | 53,514 | 53,514 | 53,514 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/23.csv | farm_b:asset6:dataset23 | 54,542 | 54,542 | 54,542 | 54,542 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/27.csv | farm_b:asset7:dataset27 | 62,268 | 62,268 | 62,268 | 62,268 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/34.csv | farm_b:asset14:dataset34 | 56,564 | 56,564 | 56,564 | 56,564 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/52.csv | farm_b:asset14:dataset52 | 55,268 | 55,268 | 55,268 | 55,268 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/53.csv | farm_b:asset6:dataset53 | 58,607 | 58,607 | 58,607 | 58,607 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/7.csv | farm_b:asset13:dataset7 | 57,888 | 57,888 | 57,888 | 57,888 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/74.csv | farm_b:asset11:dataset74 | 55,602 | 55,602 | 55,602 | 55,602 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/77.csv | farm_b:asset12:dataset77 | 61,776 | 61,776 | 61,776 | 61,776 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/82.csv | farm_b:asset5:dataset82 | 54,992 | 54,992 | 54,992 | 54,992 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/83.csv | farm_b:asset2:dataset83 | 66,154 | 66,154 | 66,154 | 66,154 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/86.csv | farm_b:asset12:dataset86 | 55,486 | 55,486 | 55,486 | 55,486 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/datasets/87.csv | farm_b:asset7:dataset87 | 55,356 | 55,356 | 55,356 | 55,356 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/1.csv | farm_c:asset53:dataset1 | 53,569 | 53,569 | 53,569 | 53,569 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/11.csv | farm_c:asset43:dataset11 | 56,437 | 56,437 | 56,437 | 56,437 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/12.csv | farm_c:asset2:dataset12 | 56,107 | 56,107 | 56,107 | 56,107 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/15.csv | farm_c:asset12:dataset15 | 54,433 | 54,433 | 54,433 | 54,433 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/16.csv | farm_c:asset53:dataset16 | 53,568 | 53,568 | 53,568 | 53,568 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/18.csv | farm_c:asset34:dataset18 | 52,848 | 52,848 | 52,848 | 52,848 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/20.csv | farm_c:asset53:dataset20 | 54,001 | 54,001 | 54,001 | 54,001 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/28.csv | farm_c:asset52:dataset28 | 55,918 | 55,918 | 55,918 | 55,918 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/29.csv | farm_c:asset13:dataset29 | 54,865 | 54,865 | 54,865 | 54,865 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/30.csv | farm_c:asset16:dataset30 | 56,111 | 56,111 | 56,111 | 56,111 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/31.csv | farm_c:asset35:dataset31 | 54,589 | 54,589 | 54,589 | 54,589 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/32.csv | farm_c:asset42:dataset32 | 55,009 | 55,009 | 55,009 | 55,009 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/33.csv | farm_c:asset43:dataset33 | 55,873 | 55,873 | 55,873 | 55,873 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/35.csv | farm_c:asset53:dataset35 | 52,615 | 52,615 | 52,615 | 52,615 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/36.csv | farm_c:asset2:dataset36 | 55,448 | 55,448 | 55,448 | 55,448 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/37.csv | farm_c:asset23:dataset37 | 53,713 | 53,713 | 53,713 | 53,713 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/39.csv | farm_c:asset52:dataset39 | 53,727 | 53,727 | 53,727 | 53,727 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/4.csv | farm_c:asset34:dataset4 | 56,449 | 56,449 | 56,449 | 56,449 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/41.csv | farm_c:asset33:dataset41 | 55,666 | 55,666 | 55,666 | 55,666 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/43.csv | farm_c:asset52:dataset43 | 55,153 | 55,153 | 55,153 | 55,153 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/44.csv | farm_c:asset44:dataset44 | 63,003 | 63,003 | 63,003 | 63,003 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/46.csv | farm_c:asset16:dataset46 | 55,133 | 55,133 | 55,133 | 55,133 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/47.csv | farm_c:asset21:dataset47 | 53,993 | 53,993 | 53,993 | 53,993 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/48.csv | farm_c:asset35:dataset48 | 55,297 | 55,297 | 55,297 | 55,297 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/49.csv | farm_c:asset33:dataset49 | 53,014 | 53,014 | 53,014 | 53,014 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/5.csv | farm_c:asset32:dataset5 | 52,795 | 52,795 | 52,795 | 52,795 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/50.csv | farm_c:asset12:dataset50 | 55,153 | 55,153 | 55,153 | 55,153 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/54.csv | farm_c:asset52:dataset54 | 55,585 | 55,585 | 55,585 | 55,585 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/55.csv | farm_c:asset50:dataset55 | 55,753 | 55,753 | 55,753 | 55,753 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/56.csv | farm_c:asset34:dataset56 | 53,416 | 53,416 | 53,416 | 53,416 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/57.csv | farm_c:asset55:dataset57 | 55,009 | 55,009 | 55,009 | 55,009 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/58.csv | farm_c:asset35:dataset58 | 54,433 | 54,433 | 54,433 | 54,433 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/59.csv | farm_c:asset32:dataset59 | 54,865 | 54,865 | 54,865 | 54,865 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/6.csv | farm_c:asset38:dataset6 | 54,865 | 54,865 | 54,865 | 54,865 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/60.csv | farm_c:asset53:dataset60 | 54,433 | 54,433 | 54,433 | 54,433 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/61.csv | farm_c:asset43:dataset61 | 55,585 | 55,585 | 55,585 | 55,585 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/62.csv | farm_c:asset21:dataset62 | 53,448 | 53,448 | 53,448 | 53,448 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/63.csv | farm_c:asset56:dataset63 | 54,865 | 54,865 | 54,865 | 54,865 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/64.csv | farm_c:asset15:dataset64 | 54,433 | 54,433 | 54,433 | 54,433 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/65.csv | farm_c:asset16:dataset65 | 55,918 | 55,918 | 55,918 | 55,918 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/66.csv | farm_c:asset12:dataset66 | 53,503 | 53,503 | 53,503 | 53,503 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/67.csv | farm_c:asset35:dataset67 | 61,489 | 61,489 | 61,489 | 61,489 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/70.csv | farm_c:asset23:dataset70 | 56,038 | 56,038 | 56,038 | 56,038 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/75.csv | farm_c:asset44:dataset75 | 56,161 | 56,161 | 56,161 | 56,161 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/76.csv | farm_c:asset53:dataset76 | 52,086 | 52,086 | 52,086 | 52,086 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/78.csv | farm_c:asset15:dataset78 | 53,146 | 53,146 | 53,146 | 53,146 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/79.csv | farm_c:asset16:dataset79 | 53,281 | 53,281 | 53,281 | 53,281 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/8.csv | farm_c:asset50:dataset8 | 54,802 | 54,802 | 54,802 | 54,802 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/80.csv | farm_c:asset23:dataset80 | 54,913 | 54,913 | 54,913 | 54,913 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/81.csv | farm_c:asset38:dataset81 | 53,932 | 53,932 | 53,932 | 53,932 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/85.csv | farm_c:asset14:dataset85 | 52,417 | 52,417 | 52,417 | 52,417 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/88.csv | farm_c:asset55:dataset88 | 55,441 | 55,441 | 55,441 | 55,441 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/89.csv | farm_c:asset5:dataset89 | 54,577 | 54,577 | 54,577 | 54,577 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/9.csv | farm_c:asset55:dataset9 | 56,029 | 56,029 | 56,029 | 56,029 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/90.csv | farm_c:asset56:dataset90 | 54,880 | 54,880 | 54,880 | 54,880 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/91.csv | farm_c:asset42:dataset91 | 56,608 | 56,608 | 56,608 | 56,608 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/93.csv | farm_c:asset43:dataset93 | 55,873 | 55,873 | 55,873 | 55,873 |
| care | CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/datasets/94.csv | farm_c:asset34:dataset94 | 54,865 | 54,865 | 54,865 | 54,865 |
