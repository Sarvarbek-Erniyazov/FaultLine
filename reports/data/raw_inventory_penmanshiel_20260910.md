# Raw inventory: penmanshiel

| field | value |
| --- | --- |
| source | penmanshiel |
| provider | Cubico Sustainable Investments Ltd |
| licence | CC-BY-4.0 |
| zenodo record | 16,807,304 |
| concept DOI | 10.5281/zenodo.5946807 |
| staged directory | C:\Users\sharg\Desktop\github\FaultLine\data\raw\telemetry\penmanshiel |
| files staged | 16 |
| members discovered | 198 |
| member classification | file-name substring patterns in the adapter |
| event members parsed | 98 of 98 (caps: 200 members, 209.7 MB and 500,000 rows per member) |
| generated (UTC) | 2026-09-10T09:22:25+00:00 |
| git_sha | aac5d7110773da2a7337e045b61237a5001db107 |

## Free-text verdict

**VERIFIED no** - a code book: 231 distinct strings over 839,303 rows with text, mean length 13.9 characters (2.4 words), 11.3% of the distinct strings occurring exactly once; at most 78 distinct strings in any one table. A closed set of recurring labels, not open-ended language (ADR-0001 holds)

This is the evidence behind ADR-0001: whether the paired text in this record is open-ended language or a controlled vocabulary.

Thresholds applied: more than 500 distinct strings is open-ended text; within that, a set in which at least 50% of the distinct strings occur exactly once was written per event, otherwise it is a code book; written descriptions averaging at most 200 characters are short. The measurements are pooled over every parsed event table and listed in the next section.

## Text measurements (all parsed tables pooled)

| field | value |
| --- | --- |
| event tables parsed | 98 |
| rows | 839,303 |
| rows with a non-empty message | 839,303 (100.0%) |
| distinct messages | 231 |
| mean length (characters) | 13.9 |
| mean length (words) | 2.4 |
| distinct messages occurring exactly once | 11.3% |
| most distinct messages in one table | 78 |
| longest mean length in one table (characters) | 16.3 |

**Top 20 messages** (share of rows with a message)

| message | count | share |
| --- | --- | --- |
| System OK | 119,819 | 14.28% |
| Wind < start wind | 111,208 | 13.25% |
| Automatic start-up | 95,165 | 11.34% |
| Run-up | 92,186 | 10.98% |
| Mains connection | 87,612 | 10.44% |
| Mains run-up | 87,417 | 10.42% |
| Mains operation | 87,193 | 10.39% |
| Brake program 50 | 81,986 | 9.77% |
| Brake program 52 | 8,545 | 1.02% |
| Bypass limit switches | 6,556 | 0.78% |
| System test 1 | 4,930 | 0.59% |
| System test 2 | 4,409 | 0.53% |
| System test 3 | 4,351 | 0.52% |
| Battery test | 4,293 | 0.51% |
| Brake program 60 | 3,868 | 0.46% |
| Brake program 180 | 3,424 | 0.41% |
| Max. wind speed | 3,348 | 0.40% |
| Absence of wind during run-up | 2,668 | 0.32% |
| P output externally reduced | 1,852 | 0.22% |
| Cable autounwind | 1,845 | 0.22% |

## Event codes (all parsed tables pooled)

| field | value |
| --- | --- |
| tables with a code column | 98 of 98 |
| rows carrying a code | 839,303 |
| distinct codes | 231 |

**Top 20 codes**

| code | rows | share |
| --- | --- | --- |
| 0 | 119,819 | 14.28% |
| 10 | 111,208 | 13.25% |
| 100130 | 95,165 | 11.34% |
| 100180 | 92,186 | 10.98% |
| 100190 | 87,612 | 10.44% |
| 100200 | 87,417 | 10.42% |
| 100210 | 87,193 | 10.39% |
| 100070 | 81,986 | 9.77% |
| 100060 | 8,545 | 1.02% |
| 100110 | 6,556 | 0.78% |
| 100140 | 4,930 | 0.59% |
| 100150 | 4,409 | 0.53% |
| 100160 | 4,351 | 0.52% |
| 710 | 4,293 | 0.51% |
| 100050 | 3,868 | 0.46% |
| 100030 | 3,424 | 0.41% |
| 64 | 3,348 | 0.40% |
| 65 | 2,668 | 0.32% |
| 9000 | 1,852 | 0.22% |
| 6200 | 1,845 | 0.22% |

## Staged files

| file | size (MB) | members |
| --- | --- | --- |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | 128.9 | 18 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | 55.9 | 10 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | 273.5 | 18 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | 152.9 | 10 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | 365 | 18 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | 204.8 | 10 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | 473.5 | 18 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | 265.4 | 10 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | 694.5 | 18 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip | 389.3 | 10 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | 749.7 | 18 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip | 418.6 | 10 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | 710.8 | 18 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip | 396.7 | 10 |
| Penmanshiel_WT_dataSignalMapping.xlsx | 0 | 1 |
| Penmanshiel_WT_static.csv | 0 | 1 |

## Members by kind

| kind | members | uncompressed (MB) |
| --- | --- | --- |
| metadata | 2 | 0 |
| scada_10min | 98 | 1.621e+04 |
| status_events | 98 | 81 |

## Event tables found

| member | rows | columns | code column | message column | unique codes | unique messages | free-text share | mean chars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 2,698 | 9 | Code | Message | 65 | 65 | 100.0% | 15.6 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,657 | 9 | Code | Message | 59 | 59 | 100.0% | 15.2 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,427 | 9 | Code | Message | 71 | 71 | 100.0% | 15.6 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,500 | 9 | Code | Message | 58 | 58 | 100.0% | 15.5 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,684 | 9 | Code | Message | 63 | 63 | 100.0% | 15 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,843 | 9 | Code | Message | 55 | 55 | 100.0% | 15.9 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,174 | 9 | Code | Message | 62 | 62 | 100.0% | 15.6 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,321 | 9 | Code | Message | 64 | 64 | 100.0% | 15.3 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,294 | 9 | Code | Message | 54 | 54 | 100.0% | 15 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel… | 1,025 | 9 | Code | Message | 67 | 67 | 100.0% | 15.7 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel… | 1,086 | 9 | Code | Message | 73 | 73 | 100.0% | 15.5 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel… | 907 | 9 | Code | Message | 41 | 41 | 100.0% | 15 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel… | 1,053 | 9 | Code | Message | 77 | 77 | 100.0% | 15.3 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel… | 1,093 | 9 | Code | Message | 65 | 65 | 100.0% | 16.3 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip::Status_Penmanshiel… | 3,998 | 9 | Code | Message | 40 | 40 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip::Status_Penmanshiel… | 2,820 | 9 | Code | Message | 45 | 45 | 100.0% | 13.4 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip::Status_Penmanshiel… | 2,083 | 9 | Code | Message | 35 | 35 | 100.0% | 14 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip::Status_Penmanshiel… | 2,910 | 9 | Code | Message | 36 | 36 | 100.0% | 13.4 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip::Status_Penmanshiel… | 2,644 | 9 | Code | Message | 37 | 37 | 100.0% | 13.6 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip::Status_Penmanshiel… | 3,099 | 9 | Code | Message | 48 | 48 | 100.0% | 13.7 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip::Status_Penmanshiel… | 2,481 | 9 | Code | Message | 39 | 39 | 100.0% | 13.3 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip::Status_Penmanshiel… | 3,206 | 9 | Code | Message | 39 | 39 | 100.0% | 13.3 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip::Status_Penmanshiel… | 3,213 | 9 | Code | Message | 28 | 28 | 100.0% | 13.2 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip::Status_Penmanshiel… | 2,300 | 9 | Code | Message | 43 | 43 | 100.0% | 13.4 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip::Status_Penmanshiel… | 1,983 | 9 | Code | Message | 33 | 33 | 100.0% | 13.3 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip::Status_Penmanshiel… | 1,562 | 9 | Code | Message | 44 | 44 | 100.0% | 14.7 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip::Status_Penmanshiel… | 2,309 | 9 | Code | Message | 33 | 33 | 100.0% | 13.2 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip::Status_Penmanshiel… | 2,172 | 9 | Code | Message | 39 | 39 | 100.0% | 13.3 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip::Status_Penmanshiel… | 8,508 | 9 | Code | Message | 58 | 58 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip::Status_Penmanshiel… | 10,059 | 9 | Code | Message | 72 | 72 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip::Status_Penmanshiel… | 8,476 | 9 | Code | Message | 62 | 62 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip::Status_Penmanshiel… | 12,004 | 9 | Code | Message | 58 | 58 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip::Status_Penmanshiel… | 9,339 | 9 | Code | Message | 61 | 61 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip::Status_Penmanshiel… | 10,998 | 9 | Code | Message | 59 | 59 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip::Status_Penmanshiel… | 8,551 | 9 | Code | Message | 63 | 63 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip::Status_Penmanshiel… | 10,046 | 9 | Code | Message | 58 | 58 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip::Status_Penmanshiel… | 10,617 | 9 | Code | Message | 66 | 66 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip::Status_Penmanshiel… | 8,440 | 9 | Code | Message | 60 | 60 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip::Status_Penmanshiel… | 7,304 | 9 | Code | Message | 64 | 64 | 100.0% | 14 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip::Status_Penmanshiel… | 8,099 | 9 | Code | Message | 56 | 56 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip::Status_Penmanshiel… | 8,522 | 9 | Code | Message | 64 | 64 | 100.0% | 14 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip::Status_Penmanshiel… | 7,876 | 9 | Code | Message | 58 | 58 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip::Status_Penmanshiel… | 9,839 | 9 | Code | Message | 63 | 63 | 100.0% | 14 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip::Status_Penmanshiel… | 11,846 | 9 | Code | Message | 71 | 71 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip::Status_Penmanshiel… | 10,607 | 9 | Code | Message | 64 | 64 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip::Status_Penmanshiel… | 12,857 | 9 | Code | Message | 73 | 73 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip::Status_Penmanshiel… | 12,044 | 9 | Code | Message | 73 | 73 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip::Status_Penmanshiel… | 12,606 | 9 | Code | Message | 71 | 71 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip::Status_Penmanshiel… | 9,245 | 9 | Code | Message | 63 | 63 | 100.0% | 14.1 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip::Status_Penmanshiel… | 11,883 | 9 | Code | Message | 60 | 60 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip::Status_Penmanshiel… | 12,372 | 9 | Code | Message | 64 | 64 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip::Status_Penmanshiel… | 9,321 | 9 | Code | Message | 65 | 65 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip::Status_Penmanshiel… | 8,039 | 9 | Code | Message | 68 | 68 | 100.0% | 14.1 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip::Status_Penmanshiel… | 9,956 | 9 | Code | Message | 61 | 61 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip::Status_Penmanshiel… | 10,526 | 9 | Code | Message | 68 | 68 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip::Status_Penmanshiel… | 8,666 | 9 | Code | Message | 72 | 72 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip::Status_Penmanshiel… | 10,274 | 9 | Code | Message | 63 | 63 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip::Status_Penmanshiel… | 11,914 | 9 | Code | Message | 76 | 76 | 100.0% | 14 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip::Status_Penmanshiel… | 11,177 | 9 | Code | Message | 59 | 59 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip::Status_Penmanshiel… | 13,386 | 9 | Code | Message | 56 | 56 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip::Status_Penmanshiel… | 12,246 | 9 | Code | Message | 55 | 55 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip::Status_Penmanshiel… | 13,426 | 9 | Code | Message | 67 | 67 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip::Status_Penmanshiel… | 10,474 | 9 | Code | Message | 57 | 57 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip::Status_Penmanshiel… | 13,015 | 9 | Code | Message | 67 | 67 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip::Status_Penmanshiel… | 13,459 | 9 | Code | Message | 64 | 64 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip::Status_Penmanshiel… | 10,097 | 9 | Code | Message | 58 | 58 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip::Status_Penmanshiel… | 8,592 | 9 | Code | Message | 63 | 63 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip::Status_Penmanshiel… | 9,897 | 9 | Code | Message | 59 | 59 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip::Status_Penmanshiel… | 11,039 | 9 | Code | Message | 65 | 65 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip::Status_Penmanshiel… | 9,634 | 9 | Code | Message | 78 | 78 | 100.0% | 14.1 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip::Status_Penmanshiel… | 12,787 | 11 | Code | Message | 59 | 59 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip::Status_Penmanshiel… | 17,142 | 11 | Code | Message | 60 | 60 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip::Status_Penmanshiel… | 13,366 | 11 | Code | Message | 77 | 77 | 100.0% | 14.1 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip::Status_Penmanshiel… | 15,774 | 11 | Code | Message | 57 | 57 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip::Status_Penmanshiel… | 13,335 | 11 | Code | Message | 69 | 69 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip::Status_Penmanshiel… | 16,059 | 11 | Code | Message | 64 | 64 | 100.0% | 14 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip::Status_Penmanshiel… | 14,272 | 11 | Code | Message | 63 | 63 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip::Status_Penmanshiel… | 14,242 | 11 | Code | Message | 77 | 77 | 100.0% | 14.1 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip::Status_Penmanshiel… | 15,373 | 11 | Code | Message | 64 | 64 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip::Status_Penmanshiel… | 11,808 | 11 | Code | Message | 67 | 67 | 100.0% | 14 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip::Status_Penmanshiel… | 10,719 | 11 | Code | Message | 68 | 68 | 100.0% | 14.2 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip::Status_Penmanshiel… | 11,875 | 11 | Code | Message | 67 | 67 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip::Status_Penmanshiel… | 12,452 | 11 | Code | Message | 59 | 59 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip::Status_Penmanshiel… | 10,307 | 11 | Code | Message | 73 | 73 | 100.0% | 14.2 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip::Status_Penmanshiel… | 9,983 | 11 | Code | Message | 57 | 57 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip::Status_Penmanshiel… | 11,537 | 11 | Code | Message | 58 | 58 | 100.0% | 14 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip::Status_Penmanshiel… | 9,591 | 11 | Code | Message | 61 | 61 | 100.0% | 14.5 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip::Status_Penmanshiel… | 13,219 | 11 | Code | Message | 59 | 59 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip::Status_Penmanshiel… | 11,027 | 11 | Code | Message | 67 | 67 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip::Status_Penmanshiel… | 13,676 | 11 | Code | Message | 64 | 64 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip::Status_Penmanshiel… | 14,809 | 11 | Code | Message | 62 | 62 | 100.0% | 14 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip::Status_Penmanshiel… | 12,149 | 11 | Code | Message | 66 | 66 | 100.0% | 14.1 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip::Status_Penmanshiel… | 12,743 | 11 | Code | Message | 54 | 54 | 100.0% | 13.8 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip::Status_Penmanshiel… | 9,620 | 11 | Code | Message | 75 | 75 | 100.0% | 14.1 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip::Status_Penmanshiel… | 8,812 | 11 | Code | Message | 70 | 70 | 100.0% | 14.2 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip::Status_Penmanshiel… | 10,080 | 11 | Code | Message | 59 | 59 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip::Status_Penmanshiel… | 10,060 | 11 | Code | Message | 68 | 68 | 100.0% | 13.9 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip::Status_Penmanshiel… | 8,668 | 11 | Code | Message | 65 | 65 | 100.0% | 14.2 |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 1,126 | 41.73% |
| System OK | 936 | 34.69% |
| P output externally reduced | 144 | 5.34% |
| Manual yaw | 50 | 1.85% |
| Brake accumulator defect | 48 | 1.78% |
| Externally stopped | 48 | 1.78% |
| Manual stop - on site | 32 | 1.19% |
| Comm. failure FPM | 30 | 1.11% |
| Absence of wind during run-up | 20 | 0.74% |
| Battery charge cycle axis 1 error | 20 | 0.74% |
| Battery charge cycle axis 2 error | 20 | 0.74% |
| Battery charge cycle axis 3 error | 20 | 0.74% |
| Battery test | 20 | 0.74% |
| High frequency - P reduction | 14 | 0.52% |
| Timeout brake closed | 14 | 0.52% |
| Cable autounwind | 12 | 0.44% |
| Frequency converter not ready | 10 | 0.37% |
| Gearbox warm-up stage | 10 | 0.37% |
| Gear heating enabled | 6 | 0.22% |
| Grid loss | 6 | 0.22% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 696 | 42.00% |
| System OK | 550 | 33.19% |
| P output externally reduced | 70 | 4.22% |
| Externally stopped | 46 | 2.78% |
| Vane 2 defect | 41 | 2.47% |
| Manual stop - on site | 27 | 1.63% |
| Manual yaw | 23 | 1.39% |
| Battery test | 22 | 1.33% |
| Comm. failure FPM | 18 | 1.09% |
| Gear heating enabled | 12 | 0.72% |
| Cable autounwind | 11 | 0.66% |
| Absence of wind during run-up | 10 | 0.60% |
| Timeout brake closed | 9 | 0.54% |
| Frequency converter not ready | 8 | 0.48% |
| Grid loss | 7 | 0.42% |
| Overload generator fan 1 | 7 | 0.42% |
| Repeating error BP52 | 7 | 0.42% |
| Brake accumulator defect | 6 | 0.36% |
| Overload generator fan 2 | 6 | 0.36% |
| Overload generator fan 3 | 6 | 0.36% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 566 | 39.66% |
| System OK | 479 | 33.57% |
| P output externally reduced | 51 | 3.57% |
| Manual stop - on site | 33 | 2.31% |
| Manual yaw | 26 | 1.82% |
| Externally stopped | 24 | 1.68% |
| Battery test | 22 | 1.54% |
| Comm. failure FPM | 21 | 1.47% |
| Low gearbox oil pressure | 18 | 1.26% |
| Absence of wind during run-up | 12 | 0.84% |
| High temp. gen. bearing 1 | 12 | 0.84% |
| Battery charge cycle axis 1 error | 9 | 0.63% |
| Battery charge cycle axis 2 error | 9 | 0.63% |
| Battery charge cycle axis 3 error | 9 | 0.63% |
| Cable autounwind | 8 | 0.56% |
| Frequency converter not ready | 8 | 0.56% |
| Gearbox warm-up stage | 8 | 0.56% |
| Repeating error BP52 | 8 | 0.56% |
| Grid loss | 7 | 0.49% |
| Brake accumulator defect | 6 | 0.42% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 716 | 47.73% |
| System OK | 476 | 31.73% |
| P output externally reduced | 31 | 2.07% |
| Manual stop - on site | 26 | 1.73% |
| Battery test | 19 | 1.27% |
| Externally stopped | 17 | 1.13% |
| Manual yaw | 16 | 1.07% |
| Absence of wind during run-up | 15 | 1.00% |
| Comm. failure FPM | 15 | 1.00% |
| Repeating error BP52 | 12 | 0.80% |
| Cable autounwind | 11 | 0.73% |
| Missing gear oil (high rpm) | 11 | 0.73% |
| Battery charge cycle axis 1 error | 10 | 0.67% |
| Battery charge cycle axis 2 error | 10 | 0.67% |
| Battery charge cycle axis 3 error | 10 | 0.67% |
| Frequency converter not ready | 8 | 0.53% |
| Gearbox warm-up stage | 8 | 0.53% |
| Max. wind speed | 7 | 0.47% |
| Timeout brake closed | 7 | 0.47% |
| Grid loss | 6 | 0.40% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 537 | 31.89% |
| System OK | 478 | 28.38% |
| Vane 2 defect | 326 | 19.36% |
| P output externally reduced | 50 | 2.97% |
| Externally stopped | 32 | 1.90% |
| Comm. failure FPM | 22 | 1.31% |
| Battery test | 19 | 1.13% |
| Manual yaw | 17 | 1.01% |
| Manual stop - on site | 16 | 0.95% |
| Timeout brake closed | 12 | 0.71% |
| Brake accumulator defect | 11 | 0.65% |
| Absence of wind during run-up | 10 | 0.59% |
| Pitch measuring system 1><2 | 10 | 0.59% |
| Battery charge cycle axis 1 error | 9 | 0.53% |
| Battery charge cycle axis 2 error | 9 | 0.53% |
| Battery charge cycle axis 3 error | 9 | 0.53% |
| Cable autounwind | 9 | 0.53% |
| Gearbox warm-up stage | 9 | 0.53% |
| Repeating error BP52 | 7 | 0.42% |
| Frequency converter not ready | 6 | 0.36% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 821 | 44.55% |
| System OK | 597 | 32.39% |
| P output externally reduced | 68 | 3.69% |
| Battery charge cycle axis 1 error | 54 | 2.93% |
| Externally stopped | 52 | 2.82% |
| Manual stop - on site | 30 | 1.63% |
| Comm. failure FPM | 26 | 1.41% |
| Absence of wind during run-up | 24 | 1.30% |
| Battery test | 24 | 1.30% |
| Battery charge cycle axis 2 error | 12 | 0.65% |
| Battery charge cycle axis 3 error | 12 | 0.65% |
| Manual yaw | 12 | 0.65% |
| Frequency converter not ready | 9 | 0.49% |
| Cable autounwind | 8 | 0.43% |
| Repeating error BP52 | 7 | 0.38% |
| Grid loss | 6 | 0.33% |
| Brake accumulator defect | 5 | 0.27% |
| Gearbox warm-up stage | 5 | 0.27% |
| High frequency - P reduction | 5 | 0.27% |
| Park master stop | 5 | 0.27% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 383 | 32.62% |
| System OK | 376 | 32.03% |
| Overfrequency | 96 | 8.18% |
| P output externally reduced | 51 | 4.34% |
| Externally stopped | 47 | 4.00% |
| Manual stop - on site | 24 | 2.04% |
| Battery test | 19 | 1.62% |
| Absence of wind during run-up | 15 | 1.28% |
| Manual yaw | 15 | 1.28% |
| Battery charge cycle axis 1 error | 10 | 0.85% |
| Battery charge cycle axis 2 error | 10 | 0.85% |
| Battery charge cycle axis 3 error | 10 | 0.85% |
| Comm. failure FPM | 10 | 0.85% |
| Frequency converter not ready | 8 | 0.68% |
| Brake accumulator defect | 6 | 0.51% |
| High frequency - P reduction | 6 | 0.51% |
| Park master stop | 6 | 0.51% |
| Timeout brake closed | 6 | 0.51% |
| Cable panel breaker open | 5 | 0.43% |
| Repeating error BP52 | 5 | 0.43% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 486 | 36.79% |
| System OK | 459 | 34.75% |
| Overfrequency | 63 | 4.77% |
| P output externally reduced | 54 | 4.09% |
| Externally stopped | 47 | 3.56% |
| Battery test | 19 | 1.44% |
| Manual yaw | 16 | 1.21% |
| Frequency converter not ready | 15 | 1.14% |
| Manual stop - on site | 15 | 1.14% |
| Absence of wind during run-up | 10 | 0.76% |
| Brake accumulator defect | 10 | 0.76% |
| Comm. failure FPM | 10 | 0.76% |
| Repeating error BP52 | 9 | 0.68% |
| Battery charge cycle axis 1 error | 7 | 0.53% |
| Battery charge cycle axis 2 error | 7 | 0.53% |
| Battery charge cycle axis 3 error | 7 | 0.53% |
| Gearbox warm-up stage | 6 | 0.45% |
| Cable autounwind | 5 | 0.38% |
| Park master stop | 5 | 0.38% |
| Timeout brake closed | 5 | 0.38% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| System OK | 513 | 39.64% |
| Wind < start wind | 468 | 36.17% |
| P output externally reduced | 63 | 4.87% |
| Externally stopped | 47 | 3.63% |
| Manual stop - on site | 23 | 1.78% |
| Manual yaw | 18 | 1.39% |
| Battery test | 17 | 1.31% |
| Comm. failure FPM | 15 | 1.16% |
| Repeating error BP52 | 12 | 0.93% |
| Absence of wind during run-up | 11 | 0.85% |
| Frequency converter not ready | 11 | 0.85% |
| Missing gear oil (high rpm) | 9 | 0.70% |
| Brake accumulator defect | 8 | 0.62% |
| Overfrequency | 8 | 0.62% |
| Gearbox warm-up stage | 7 | 0.54% |
| Battery charge cycle axis 1 error | 4 | 0.31% |
| Battery charge cycle axis 2 error | 4 | 0.31% |
| Battery charge cycle axis 3 error | 4 | 0.31% |
| Cable autounwind | 4 | 0.31% |
| Grid loss | 4 | 0.31% |

### Top messages: Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 418 | 40.78% |
| System OK | 302 | 29.46% |
| P output externally reduced | 53 | 5.17% |
| Externally stopped | 45 | 4.39% |
| Overfrequency | 24 | 2.34% |
| Battery test | 17 | 1.66% |
| Manual yaw | 16 | 1.56% |
| Comm. failure FPM | 13 | 1.27% |
| Manual stop - on site | 12 | 1.17% |
| Brake accumulator defect | 8 | 0.78% |
| Repeating error BP52 | 7 | 0.68% |
| Lightning protection defect | 6 | 0.59% |
| Timeout brake closed | 6 | 0.59% |
| Cable autounwind | 5 | 0.49% |
| Max. wind speed | 5 | 0.49% |
| Park master stop | 5 | 0.49% |
| Absence of wind during run-up | 4 | 0.39% |
| Frequency converter not ready | 4 | 0.39% |
| Overload generator fan 3 | 4 | 0.39% |
| Battery charge cycle axis 1 error | 3 | 0.29% |

### Top messages: Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| System OK | 314 | 28.91% |
| Wind < start wind | 297 | 27.35% |
| Overfrequency | 165 | 15.19% |
| P output externally reduced | 56 | 5.16% |
| Externally stopped | 45 | 4.14% |
| Manual stop - on site | 23 | 2.12% |
| Max. wind speed | 17 | 1.57% |
| Battery test | 14 | 1.29% |
| Manual yaw | 13 | 1.20% |
| Comm. failure FPM | 10 | 0.92% |
| Battery charge cycle axis 1 error | 6 | 0.55% |
| Battery charge cycle axis 2 error | 6 | 0.55% |
| Battery charge cycle axis 3 error | 6 | 0.55% |
| Repeating error BP52 | 6 | 0.55% |
| Timeout brake closed | 6 | 0.55% |
| Error brake resistor CHP | 5 | 0.46% |
| Brake accumulator defect | 4 | 0.37% |
| Cable autounwind | 4 | 0.37% |
| Manual stop - remote | 4 | 0.37% |
| Pitch batteries charging cycle | 4 | 0.37% |

### Top messages: Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| System OK | 337 | 37.16% |
| Wind < start wind | 326 | 35.94% |
| P output externally reduced | 50 | 5.51% |
| Externally stopped | 42 | 4.63% |
| Battery test | 16 | 1.76% |
| Max. wind speed | 15 | 1.65% |
| Overfrequency | 13 | 1.43% |
| Comm. failure FPM | 12 | 1.32% |
| Manual stop - on site | 11 | 1.21% |
| Manual yaw | 9 | 0.99% |
| Frequency converter not ready | 7 | 0.77% |
| Brake accumulator defect | 6 | 0.66% |
| Cable autounwind | 6 | 0.66% |
| Timeout brake closed | 6 | 0.66% |
| Repeating error BP52 | 5 | 0.55% |
| Grid loss | 4 | 0.44% |
| Park master stop | 4 | 0.44% |
| Absence of wind during run-up | 3 | 0.33% |
| High frequency - P reduction | 3 | 0.33% |
| Tower oscillation Y level 1 | 3 | 0.33% |

_Per-table top messages are shown for the first 12 of 98 tables with messages; the pooled measurements above cover all of them._

## Header samples (first lines, one member per kind)

**Penmanshiel_SCADA_2016_WT01-10_3107.zip::Turbine_Data_Penmanshiel_01_2016-06-06_-_2017-01-01_1042.csv**

```text
# This file was exported by Greenbyte at 2022-02-01 13:06:11. Please see https://www.greenbyte.com for more information about Greenbyte.
#
# Turbine: Penmanshiel 01
# Turbine type: Senvion MM82
# Time zone: UTC
# Time interval: 2016-01-01 00:00:00 - 2017-01-01 00:00:00 (366 days)
#
# Data that is missing or is erroneous has been marked with the value "NaN"
#
# Date and time,Wind speed (m/s),"Wind speed, Standard deviation (m/s)","Wind speed, Minimum (m/s)","Wind speed, Maximum (m/s)",Long Term Wind (m/s),Wind speed Sensor 1 (m/s),"Wind speed Sensor 1, Sta
2016-06-06 18:10:00,0,0,0,0,5.8,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,NaN,0,NaN,0,3.9521666924158727,3.9521666924158727,NaN,0,3.9521666924158727,NaN,0,78.34908813138546,3.9521666924158727,3.9521
2016-06-06 18:20:00,3.55999994277954,0.839999973773956,1.27999997138977,5.40999984741211,5.8,3.64000010490417,0.819999992847443,1.21000003814697,5.57000017166138,3.48000001907349,0.939999997615814,0.3
2016-06-06 18:30:00,3,0.540000021457672,1.41999995708466,4.78000020980835,5.8,3.04999995231628,0.550000011920929,1.46000003814697,4.8899998664856,2.94000005722046,0.569999992847443,0.660000026226044,4
2016-06-06 18:40:00,2.54999995231628,0.430000007152557,1.11000001430511,3.52999997138977,5.8,2.5699999332428,0.419999986886978,1.27999997138977,3.61999988555908,2.51999998092651,0.479999989271164,0.56
2016-06-06 18:50:00,2.78999996185303,0.490000009536743,1.55999994277954,3.69000005722046,5.8,2.76999998092651,0.479999989271164,1.60000002384186,3.72000002861023,2.80999994277954,0.519999980926514,1.3
2016-06-06 19:00:00,3.22000002861023,0.610000014305115,1.25,4.3899998664856,5.8,3.20000004768372,0.610000014305115,1.25,4.32999992370605,3.25,0.639999985694885,1.14999997615814,4.53000020980835,3.1815
2016-06-06 19:10:00,3.40000009536743,0.589999973773956,1.10000002384186,4.59000015258789,5.8,3.38000011444092,0.569999992847443,1.33000004291534,4.51999998092651,3.42000007629395,0.649999976158142,0.6
2016-06-06 19:20:00,2.66000008583069,0.540000021457672,0.759999990463257,3.85999989509583,5.8,2.64000010490417,0.519999980926514,0.759999990463257,3.76999998092651,2.67000007629395,0.579999983310699,0
2016-06-06 19:30:00,2.72000002861023,0.550000011920929,0.930000007152557,3.75999999046326,5.8,2.69000005722046,0.569999992847443,0.819999992847443,3.73000001907349,2.75,0.560000002384186,0.58999997377
2016-06-06 19:40:00,2.83999991416931,0.469999998807907,0.860000014305115,3.98000001907349,5.8,2.79999995231628,0.479999989271164,0.870000004768372,3.95000004768372,2.89000010490417,0.479999989271164,0
2016-06-06 19:50:00,3.30999994277954,0.28999999165535,2.17000007629395,4.07999992370605,5.8,3.25999999046326,0.280000001192093,2.46000003814697,3.99000000953674,3.35999989509583,0.300000011920929,1.87
2016-06-06 20:00:00,2.85999989509583,0.349999994039536,1.79999995231628,3.65000009536743,5.8,2.78999996185303,0.340000003576279,1.85000002384186,3.57999992370605,2.92000007629395,0.379999995231628,1.5
2016-06-06 20:10:00,3.34999990463257,0.300000011920929,2.28999996185303,4.01000022888184,5.8,3.30999994277954,0.310000002384186,2.30999994277954,4.01000022888184,3.39000010490417,0.319999992847443,2.0
2016-06-06 20:20:00,3.20000004768372,0.449999988079071,1.99000000953674,4.15000009536743,5.8,3.1800000667572,0.419999986886978,2.13000011444092,4.19000005722046,3.23000001907349,0.490000009536743,1.69
2016-06-06 20:30:00,3.51999998092651,0.349999994039536,2.73000001907349,4.05999994277954,5.8,3.48000001907349,0.379999995231628,2.74000000953674,4.09999990463257,3.55999994277954,0.319999992847443,2.6
2016-06-06 20:40:00,2.90000009536743,0.409999996423721,2.08999991416931,3.82999992370605,5.8,2.86999988555908,0.400000005960464,2.1800000667572,3.82999992370605,2.9300000667572,0.439999997615814,1.809
2016-06-06 20:50:00,3.04999995231628,0.319999992847443,1.45000004768372,3.41000008583069,5.8,3.02999997138977,0.310000002384186,1.75,3.44000005722046,3.0699999332428,0.340000003576279,1.00999999046326
2016-06-06 21:00:00,2.92000007629395,0.259999990463257,2.27999997138977,3.50999999046326,5.8,2.85999989509583,0.270000010728836,2.3199999332428,3.53999996185303,2.97000002861023,0.270000010728836,2.14
2016-06-06 21:10:00,2.75999999046326,0.180000007152557,1.95000004768372,3.21000003814697,5.8,2.74000000953674,0.170000001788139,2.11999988555908,3.23000001907349,2.77999997138977,0.219999998807907,1.5
2016-06-06 21:20:00,2.75,0.140000000596046,2.40000009536743,3.05999994277954,5.8,2.75,0.170000001788139,2.42000007629395,3.10999989509583,2.75999999046326,0.129999995231628,2.25999999046326,3.03999996
```

**Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel_01_2016-06-06_-_2017-01-01_1042.csv**

```text
# This file was exported by Greenbyte at 2022-02-01 13:16:19. Please see https://www.greenbyte.com for more information about Greenbyte.
#
# Turbine: Penmanshiel 01
# Turbine type: Senvion MM82 (Senvion MM82 kW)
# Time zone: UTC
# Time interval: 2016-01-01 00:00:00 - 2017-01-01 00:00:00 (366 days)
#
# Penmanshiel 01 Sum production: 2614804 kWh
#
Timestamp start,Timestamp end,Duration,Status,Code,Message,Comment,Service contract category,IEC category
2016-06-06 17:08:40,2016-06-10 11:28:00,90:19:20,Stop,3500,Grid loss,,External stop (grid) (4),Out of Electrical Specification
2016-06-06 17:08:41,2016-06-06 18:14:07,01:05:26,Warning,3875,Overload transf. fan inlet air,,Warnings (27),
2016-06-06 17:08:41,2016-06-06 18:14:39,01:05:58,Warning,1825,Overload gear bypass filter,,Warnings (27),
2016-06-06 17:08:41,2016-06-06 18:14:07,01:05:26,Warning,3875,Overload transf. fan inlet air,,Warnings (27),
2016-06-06 17:08:41,2016-06-06 18:14:39,01:05:58,Warning,1825,Overload gear bypass filter,,Warnings (27),
2016-06-06 17:08:52,2016-06-06 18:15:02,01:06:10,Warning,8402,No assignment to a PMU,,Warnings (27),
2016-06-06 17:08:52,2016-06-06 18:15:02,01:06:10,Warning,8402,No assignment to a PMU,,Warnings (27),
2016-06-08 01:34:01,2016-06-11 00:56:54,71:22:53,Warning,7324,Check time synchronization,,Warnings (27),
2016-06-08 01:34:01,2016-06-11 00:56:54,71:22:53,Warning,7324,Check time synchronization,,Warnings (27),
2016-06-10 11:28:00,2016-06-10 11:30:53,00:02:53,Informational,0,System OK,,System OK (32),Full Performance
2016-06-10 11:28:00,2016-06-10 11:30:53,00:02:53,Informational,0,System OK,,System OK (32),Full Performance
2016-06-10 11:30:53,2016-06-10 11:33:05,00:02:12,Warning,5720,Brake accumulator defect,,Warnings (27),
2016-06-10 11:30:53,2016-06-10 11:57:04,00:26:11,Stop,2100,Feedback brake 1,,Mechanical error (23),Forced outage
2016-06-10 11:30:53,2016-06-10 11:33:05,00:02:12,Warning,5720,Brake accumulator defect,,Warnings (27),
2016-06-10 11:33:05,2016-06-10 11:33:07,00:00:02,Informational,0,System OK,,System OK (32),Full Performance
2016-06-10 11:33:05,2016-06-10 11:33:07,00:00:02,Informational,0,System OK,,System OK (32),Full Performance
2016-06-10 11:33:13,2016-06-10 12:46:40,01:13:27,Informational,6410,Manual yaw,,Manual stop (service)  (9),Full Performance
2016-06-10 11:33:13,2016-06-10 12:46:40,01:13:27,Informational,6410,Manual yaw,,Manual stop (service)  (9),Full Performance
2016-06-10 11:34:58,2016-06-10 11:37:56,00:02:58,Warning,5100,Service obstacle light,,Warnings (27),
2016-06-10 11:34:58,2016-06-10 11:37:56,00:02:58,Warning,5100,Service obstacle light,,Warnings (27),
```

**Penmanshiel_WT_static.csv**

```text
﻿Wind Farm,Title,Alternative Title,Identity,Manufacturer,Model,Rated power (kW),Hub Height (m),Rotor Diameter (m),Latitude,Longitude,Elevation (m),Country,Commercial Operations Date,
Penmanshiel,Penmanshiel 01,T01,MM82/59 82765-01,Senvion,MM82,2050,59,82,55.902502,-2.306389,212.26,UK,01/09/2016,
Penmanshiel,Penmanshiel 02,T02,MM82/59 82766-02,Senvion,MM82,2050,59,82,55.900008,-2.301268,200.46,UK,01/09/2016,
Penmanshiel,Penmanshiel 04,T04,MM82/59 82768-04,Senvion,MM82,2050,59,82,55.905943,-2.30269,208.91,UK,01/09/2016,
Penmanshiel,Penmanshiel 05,T05,MM82/59 82769-05,Senvion,MM82,2050,59,82,55.903294,-2.298367,201.38,UK,01/09/2016,
Penmanshiel,Penmanshiel 06,T06,MM82/59 82770-06,Senvion,MM82,2050,59,82,55.900951,-2.293967,199.03,UK,01/09/2016,
Penmanshiel,Penmanshiel 07,T07,MM82/59 82771-07,Senvion,MM82,2050,59,82,55.898741,-2.289856,180.24,UK,01/09/2016,
Penmanshiel,Penmanshiel 08,T08,MM82/59 82772-08,Senvion,MM82,2050,59,82,55.907915,-2.297314,200.13,UK,01/09/2016,
Penmanshiel,Penmanshiel 09,T09,MM82/59 82773-09,Senvion,MM82,2050,59,82,55.90499,-2.291806,187.04,UK,01/09/2016,
Penmanshiel,Penmanshiel 10,T10,MM82/59 82774-10,Senvion,MM82,2050,59,82,55.903032,-2.287585,186.88,UK,01/09/2016,
Penmanshiel,Penmanshiel 11,T11,MM82/59 82775-11,Senvion,MM82,2050,59,82,55.900852,-2.282371,204.84,UK,01/09/2016,
Penmanshiel,Penmanshiel 12,T12,MM82/59 82776-12,Senvion,MM82,2050,59,82,55.908703,-2.290986,219.31,UK,01/09/2016,
Penmanshiel,Penmanshiel 13,T13,MM82/59 82777-13,Senvion,MM82,2050,59,82,55.907026,-2.285887,220,UK,01/09/2016,
Penmanshiel,Penmanshiel 14,T14,MM82/59 82778-14,Senvion,MM82,2050,59,82,55.90505,-2.28165,219.46,UK,01/09/2016,
Penmanshiel,Penmanshiel 15,T15,MM82/59 82767-15,Senvion,MM82,2050,59,82,55.902463,-2.277329,228.15,UK,01/09/2016,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
,,,,,,,,,,,,,,
```

## Member listing (198 of 198)

| archive | member | kind | uncompressed (MB) | compressed (MB) |
| --- | --- | --- | --- | --- |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_01_2016-06-06_-_2017-01-01_1042.csv | scada_10min | 82.36 | 16.1 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_01_2016-06-06_-_2017-01-01_1042.csv | status_events | 0.356 | 0.024 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_02_2016-06-03_-_2017-01-01_1043.csv | scada_10min | 83.8 | 16.19 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_02_2016-06-03_-_2017-01-01_1043.csv | status_events | 0.219 | 0.023 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_04_2016-06-13_-_2017-01-01_1044.csv | scada_10min | 80.6 | 15.84 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_04_2016-06-13_-_2017-01-01_1044.csv | status_events | 0.188 | 0.02 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_05_2016-06-15_-_2017-01-01_1045.csv | scada_10min | 81.39 | 16.08 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_05_2016-06-15_-_2017-01-01_1045.csv | status_events | 0.202 | 0.021 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_06_2016-06-02_-_2017-01-01_1046.csv | scada_10min | 79.86 | 14.77 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_06_2016-06-02_-_2017-01-01_1046.csv | status_events | 0.213 | 0.024 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_07_2016-06-02_-_2017-01-01_1047.csv | scada_10min | 84.59 | 16.48 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_07_2016-06-02_-_2017-01-01_1047.csv | status_events | 0.246 | 0.025 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_08_2016-07-27_-_2017-01-01_1048.csv | scada_10min | 58.59 | 11.2 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_08_2016-07-27_-_2017-01-01_1048.csv | status_events | 0.15 | 0.017 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_09_2016-06-24_-_2017-01-01_1049.csv | scada_10min | 63.93 | 11.23 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_09_2016-06-24_-_2017-01-01_1049.csv | status_events | 0.171 | 0.018 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_10_2016-06-27_-_2017-01-01_1050.csv | scada_10min | 62.63 | 10.85 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_10_2016-06-27_-_2017-01-01_1050.csv | status_events | 0.168 | 0.018 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Turbine_Data_Penmanshiel_11_2016-07-19_-_2017-01-01_1051.csv | scada_10min | 60.01 | 11.24 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Status_Penmanshiel_11_2016-07-19_-_2017-01-01_1051.csv | status_events | 0.135 | 0.015 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Turbine_Data_Penmanshiel_12_2016-07-02_-_2017-01-01_1052.csv | scada_10min | 63.82 | 11.45 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Status_Penmanshiel_12_2016-07-02_-_2017-01-01_1052.csv | status_events | 0.135 | 0.016 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Turbine_Data_Penmanshiel_13_2016-06-30_-_2017-01-01_1053.csv | scada_10min | 63.24 | 11.36 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Status_Penmanshiel_13_2016-06-30_-_2017-01-01_1053.csv | status_events | 0.118 | 0.013 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Turbine_Data_Penmanshiel_14_2016-07-09_-_2017-01-01_1054.csv | scada_10min | 60.44 | 10.76 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Status_Penmanshiel_14_2016-07-09_-_2017-01-01_1054.csv | status_events | 0.134 | 0.015 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Turbine_Data_Penmanshiel_15_2016-07-14_-_2017-01-01_1056.csv | scada_10min | 60.49 | 11.04 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Status_Penmanshiel_15_2016-07-14_-_2017-01-01_1056.csv | status_events | 0.139 | 0.016 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_01_2017-01-01_-_2018-01-01_1042.csv | scada_10min | 149.9 | 30.51 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_01_2017-01-01_-_2018-01-01_1042.csv | status_events | 0.532 | 0.033 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_02_2017-01-01_-_2018-01-01_1043.csv | scada_10min | 150 | 30.53 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_02_2017-01-01_-_2018-01-01_1043.csv | status_events | 0.368 | 0.034 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_04_2017-01-01_-_2018-01-01_1044.csv | scada_10min | 149.1 | 30.5 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_04_2017-01-01_-_2018-01-01_1044.csv | status_events | 0.278 | 0.026 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_05_2017-01-01_-_2018-01-01_1045.csv | scada_10min | 150.5 | 30.63 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_05_2017-01-01_-_2018-01-01_1045.csv | status_events | 0.381 | 0.035 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_06_2017-01-01_-_2018-01-01_1046.csv | scada_10min | 147.9 | 30.34 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_06_2017-01-01_-_2018-01-01_1046.csv | status_events | 0.345 | 0.033 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_07_2017-01-01_-_2018-01-01_1047.csv | scada_10min | 148.1 | 30.14 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_07_2017-01-01_-_2018-01-01_1047.csv | status_events | 0.407 | 0.037 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_08_2017-01-01_-_2018-01-01_1048.csv | scada_10min | 147.8 | 30.37 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_08_2017-01-01_-_2018-01-01_1048.csv | status_events | 0.324 | 0.03 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_09_2017-01-01_-_2018-01-01_1049.csv | scada_10min | 147.3 | 30.09 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_09_2017-01-01_-_2018-01-01_1049.csv | status_events | 0.42 | 0.038 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_10_2017-01-01_-_2018-01-01_1050.csv | scada_10min | 147.4 | 30.12 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_10_2017-01-01_-_2018-01-01_1050.csv | status_events | 0.422 | 0.038 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Turbine_Data_Penmanshiel_11_2017-01-01_-_2018-01-01_1051.csv | scada_10min | 149.1 | 30.44 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Status_Penmanshiel_11_2017-01-01_-_2018-01-01_1051.csv | status_events | 0.3 | 0.028 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Turbine_Data_Penmanshiel_12_2017-01-01_-_2018-01-01_1052.csv | scada_10min | 149.8 | 30.64 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Status_Penmanshiel_12_2017-01-01_-_2018-01-01_1052.csv | status_events | 0.258 | 0.024 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Turbine_Data_Penmanshiel_13_2017-01-01_-_2018-01-01_1053.csv | scada_10min | 149 | 30.71 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Status_Penmanshiel_13_2017-01-01_-_2018-01-01_1053.csv | status_events | 0.213 | 0.021 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Turbine_Data_Penmanshiel_14_2017-01-01_-_2018-01-01_1054.csv | scada_10min | 148.2 | 30.48 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Status_Penmanshiel_14_2017-01-01_-_2018-01-01_1054.csv | status_events | 0.302 | 0.028 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Turbine_Data_Penmanshiel_15_2017-01-01_-_2018-01-01_1056.csv | scada_10min | 148.2 | 30.5 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Status_Penmanshiel_15_2017-01-01_-_2018-01-01_1056.csv | status_events | 0.283 | 0.027 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_01_2018-01-01_-_2019-01-01_1042.csv | scada_10min | 146.2 | 39.52 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_01_2018-01-01_-_2019-01-01_1042.csv | status_events | 0.847 | 0.061 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_02_2018-01-01_-_2019-01-01_1043.csv | scada_10min | 146.6 | 40.68 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_02_2018-01-01_-_2019-01-01_1043.csv | status_events | 0.961 | 0.074 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_04_2018-01-01_-_2019-01-01_1044.csv | scada_10min | 147.1 | 40.69 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_04_2018-01-01_-_2019-01-01_1044.csv | status_events | 0.813 | 0.063 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_05_2018-01-01_-_2019-01-01_1045.csv | scada_10min | 148 | 41.28 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_05_2018-01-01_-_2019-01-01_1045.csv | status_events | 1.165 | 0.087 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_06_2018-01-01_-_2019-01-01_1046.csv | scada_10min | 146.6 | 40.42 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_06_2018-01-01_-_2019-01-01_1046.csv | status_events | 0.895 | 0.069 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_07_2018-01-01_-_2019-01-01_1047.csv | scada_10min | 146.6 | 40.67 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_07_2018-01-01_-_2019-01-01_1047.csv | status_events | 1.059 | 0.08 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_08_2018-01-01_-_2019-01-01_1048.csv | scada_10min | 146.9 | 40.83 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_08_2018-01-01_-_2019-01-01_1048.csv | status_events | 0.82 | 0.063 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_09_2018-01-01_-_2019-01-01_1049.csv | scada_10min | 146.1 | 40.33 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_09_2018-01-01_-_2019-01-01_1049.csv | status_events | 0.967 | 0.074 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_10_2018-01-01_-_2019-01-01_1050.csv | scada_10min | 145.4 | 39.95 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_10_2018-01-01_-_2019-01-01_1050.csv | status_events | 1.02 | 0.078 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Turbine_Data_Penmanshiel_11_2018-01-01_-_2019-01-01_1051.csv | scada_10min | 147.2 | 40.7 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Status_Penmanshiel_11_2018-01-01_-_2019-01-01_1051.csv | status_events | 0.808 | 0.063 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Turbine_Data_Penmanshiel_12_2018-01-01_-_2019-01-01_1052.csv | scada_10min | 147.6 | 40.71 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Status_Penmanshiel_12_2018-01-01_-_2019-01-01_1052.csv | status_events | 0.697 | 0.055 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Turbine_Data_Penmanshiel_13_2018-01-01_-_2019-01-01_1053.csv | scada_10min | 147.9 | 41.19 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Status_Penmanshiel_13_2018-01-01_-_2019-01-01_1053.csv | status_events | 0.774 | 0.06 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Turbine_Data_Penmanshiel_14_2018-01-01_-_2019-01-01_1054.csv | scada_10min | 147 | 40.86 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Status_Penmanshiel_14_2018-01-01_-_2019-01-01_1054.csv | status_events | 0.815 | 0.064 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Turbine_Data_Penmanshiel_15_2018-01-01_-_2019-01-01_1056.csv | scada_10min | 147.4 | 41.05 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Status_Penmanshiel_15_2018-01-01_-_2019-01-01_1056.csv | status_events | 0.754 | 0.059 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_01_2019-01-01_-_2020-01-01_1042.csv | scada_10min | 151.9 | 52.59 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_01_2019-01-01_-_2020-01-01_1042.csv | status_events | 0.907 | 0.069 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_02_2019-01-01_-_2020-01-01_1043.csv | scada_10min | 150.8 | 52.9 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_02_2019-01-01_-_2020-01-01_1043.csv | status_events | 1.093 | 0.082 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_04_2019-01-01_-_2020-01-01_1044.csv | scada_10min | 151.6 | 53.05 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_04_2019-01-01_-_2020-01-01_1044.csv | status_events | 0.977 | 0.073 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_05_2019-01-01_-_2020-01-01_1045.csv | scada_10min | 150.6 | 52.79 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_05_2019-01-01_-_2020-01-01_1045.csv | status_events | 1.187 | 0.088 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_06_2019-01-01_-_2020-01-01_1046.csv | scada_10min | 151.8 | 52.62 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_06_2019-01-01_-_2020-01-01_1046.csv | status_events | 1.11 | 0.083 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_07_2019-01-01_-_2020-01-01_1047.csv | scada_10min | 147.8 | 50.84 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_07_2019-01-01_-_2020-01-01_1047.csv | status_events | 1.165 | 0.087 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_08_2019-01-01_-_2020-01-01_1048.csv | scada_10min | 151.6 | 52.85 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_08_2019-01-01_-_2020-01-01_1048.csv | status_events | 0.853 | 0.065 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_09_2019-01-01_-_2020-01-01_1049.csv | scada_10min | 150.5 | 52.57 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_09_2019-01-01_-_2020-01-01_1049.csv | status_events | 1.096 | 0.081 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_10_2019-01-01_-_2020-01-01_1050.csv | scada_10min | 150.9 | 52.58 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_10_2019-01-01_-_2020-01-01_1050.csv | status_events | 1.141 | 0.084 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Turbine_Data_Penmanshiel_11_2019-01-01_-_2020-01-01_1051.csv | scada_10min | 151.2 | 52.79 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Status_Penmanshiel_11_2019-01-01_-_2020-01-01_1051.csv | status_events | 0.859 | 0.065 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Turbine_Data_Penmanshiel_12_2019-01-01_-_2020-01-01_1052.csv | scada_10min | 151.2 | 53.08 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Status_Penmanshiel_12_2019-01-01_-_2020-01-01_1052.csv | status_events | 0.738 | 0.058 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Turbine_Data_Penmanshiel_13_2019-01-01_-_2020-01-01_1053.csv | scada_10min | 152.4 | 53.2 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Status_Penmanshiel_13_2019-01-01_-_2020-01-01_1053.csv | status_events | 0.916 | 0.069 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Turbine_Data_Penmanshiel_14_2019-01-01_-_2020-01-01_1054.csv | scada_10min | 151.7 | 52.96 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Status_Penmanshiel_14_2019-01-01_-_2020-01-01_1054.csv | status_events | 0.968 | 0.073 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Turbine_Data_Penmanshiel_15_2019-01-01_-_2020-01-01_1056.csv | scada_10min | 151.8 | 53.01 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Status_Penmanshiel_15_2019-01-01_-_2020-01-01_1056.csv | status_events | 0.799 | 0.061 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Turbine_Data_Penmanshiel_01_2020-01-01_-_2021-01-01_1042.csv | scada_10min | 201.7 | 77.05 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Status_Penmanshiel_01_2020-01-01_-_2021-01-01_1042.csv | status_events | 0.943 | 0.072 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Turbine_Data_Penmanshiel_02_2020-01-01_-_2021-01-01_1043.csv | scada_10min | 199.9 | 76.72 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Status_Penmanshiel_02_2020-01-01_-_2021-01-01_1043.csv | status_events | 1.092 | 0.083 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Turbine_Data_Penmanshiel_04_2020-01-01_-_2021-01-01_1044.csv | scada_10min | 201.3 | 77.16 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Status_Penmanshiel_04_2020-01-01_-_2021-01-01_1044.csv | status_events | 1.027 | 0.077 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Turbine_Data_Penmanshiel_05_2020-01-01_-_2021-01-01_1045.csv | scada_10min | 200.4 | 77.49 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Status_Penmanshiel_05_2020-01-01_-_2021-01-01_1045.csv | status_events | 1.231 | 0.091 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Turbine_Data_Penmanshiel_06_2020-01-01_-_2021-01-01_1046.csv | scada_10min | 202.7 | 77.33 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Status_Penmanshiel_06_2020-01-01_-_2021-01-01_1046.csv | status_events | 1.125 | 0.084 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Turbine_Data_Penmanshiel_07_2020-01-01_-_2021-01-01_1047.csv | scada_10min | 200.3 | 76.72 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Status_Penmanshiel_07_2020-01-01_-_2021-01-01_1047.csv | status_events | 1.237 | 0.092 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Turbine_Data_Penmanshiel_08_2020-01-01_-_2021-01-01_1048.csv | scada_10min | 202.1 | 77.57 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Status_Penmanshiel_08_2020-01-01_-_2021-01-01_1048.csv | status_events | 0.962 | 0.073 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Turbine_Data_Penmanshiel_09_2020-01-01_-_2021-01-01_1049.csv | scada_10min | 201.1 | 77.11 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Status_Penmanshiel_09_2020-01-01_-_2021-01-01_1049.csv | status_events | 1.198 | 0.089 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Turbine_Data_Penmanshiel_10_2020-01-01_-_2021-01-01_1050.csv | scada_10min | 201.3 | 76.57 |
| Penmanshiel_SCADA_2020_WT01-10_3109.zip | Status_Penmanshiel_10_2020-01-01_-_2021-01-01_1050.csv | status_events | 1.24 | 0.092 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip | Turbine_Data_Penmanshiel_11_2020-01-01_-_2021-01-01_1051.csv | scada_10min | 201.5 | 77.48 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip | Status_Penmanshiel_11_2020-01-01_-_2021-01-01_1051.csv | status_events | 0.925 | 0.07 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip | Turbine_Data_Penmanshiel_12_2020-01-01_-_2021-01-01_1052.csv | scada_10min | 201.9 | 78.13 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip | Status_Penmanshiel_12_2020-01-01_-_2021-01-01_1052.csv | status_events | 0.787 | 0.061 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip | Turbine_Data_Penmanshiel_13_2020-01-01_-_2021-01-01_1053.csv | scada_10min | 202.4 | 77.74 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip | Status_Penmanshiel_13_2020-01-01_-_2021-01-01_1053.csv | status_events | 0.907 | 0.069 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip | Turbine_Data_Penmanshiel_14_2020-01-01_-_2021-01-01_1054.csv | scada_10min | 202.4 | 77.68 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip | Status_Penmanshiel_14_2020-01-01_-_2021-01-01_1054.csv | status_events | 1.013 | 0.076 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip | Turbine_Data_Penmanshiel_15_2020-01-01_-_2021-01-01_1056.csv | scada_10min | 202.9 | 77.93 |
| Penmanshiel_SCADA_2020_WT11-15_3118.zip | Status_Penmanshiel_15_2020-01-01_-_2021-01-01_1056.csv | status_events | 0.886 | 0.069 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Turbine_Data_Penmanshiel_01_2021-01-01_-_2022-01-01_1042.csv | scada_10min | 225.9 | 83.33 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Status_Penmanshiel_01_2021-01-01_-_2022-01-01_1042.csv | status_events | 1.214 | 0.088 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Turbine_Data_Penmanshiel_02_2021-01-01_-_2022-01-01_1043.csv | scada_10min | 224 | 83.98 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Status_Penmanshiel_02_2021-01-01_-_2022-01-01_1043.csv | status_events | 1.634 | 0.117 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Turbine_Data_Penmanshiel_04_2021-01-01_-_2022-01-01_1044.csv | scada_10min | 225.3 | 83.22 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Status_Penmanshiel_04_2021-01-01_-_2022-01-01_1044.csv | status_events | 1.27 | 0.094 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Turbine_Data_Penmanshiel_05_2021-01-01_-_2022-01-01_1045.csv | scada_10min | 224 | 83.69 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Status_Penmanshiel_05_2021-01-01_-_2022-01-01_1045.csv | status_events | 1.498 | 0.108 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Turbine_Data_Penmanshiel_06_2021-01-01_-_2022-01-01_1046.csv | scada_10min | 226.2 | 82.94 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Status_Penmanshiel_06_2021-01-01_-_2022-01-01_1046.csv | status_events | 1.264 | 0.093 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Turbine_Data_Penmanshiel_07_2021-01-01_-_2022-01-01_1047.csv | scada_10min | 223.2 | 82.39 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Status_Penmanshiel_07_2021-01-01_-_2022-01-01_1047.csv | status_events | 1.524 | 0.111 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Turbine_Data_Penmanshiel_08_2021-01-01_-_2022-01-01_1048.csv | scada_10min | 225.8 | 83.1 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Status_Penmanshiel_08_2021-01-01_-_2022-01-01_1048.csv | status_events | 1.357 | 0.1 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Turbine_Data_Penmanshiel_09_2021-01-01_-_2022-01-01_1049.csv | scada_10min | 225.4 | 83.3 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Status_Penmanshiel_09_2021-01-01_-_2022-01-01_1049.csv | status_events | 1.357 | 0.101 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Turbine_Data_Penmanshiel_10_2021-01-01_-_2022-01-01_1050.csv | scada_10min | 224.9 | 82.79 |
| Penmanshiel_SCADA_2021_WT01-10_4460.zip | Status_Penmanshiel_10_2021-01-01_-_2022-01-01_1050.csv | status_events | 1.457 | 0.105 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip | Turbine_Data_Penmanshiel_11_2021-01-01_-_2022-01-01_1051.csv | scada_10min | 224.5 | 82.74 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip | Status_Penmanshiel_11_2021-01-01_-_2022-01-01_1051.csv | status_events | 1.117 | 0.084 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip | Turbine_Data_Penmanshiel_12_2021-01-01_-_2022-01-01_1052.csv | scada_10min | 225.4 | 84.31 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip | Status_Penmanshiel_12_2021-01-01_-_2022-01-01_1052.csv | status_events | 1.017 | 0.078 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip | Turbine_Data_Penmanshiel_13_2021-01-01_-_2022-01-01_1053.csv | scada_10min | 226.5 | 83.8 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip | Status_Penmanshiel_13_2021-01-01_-_2022-01-01_1053.csv | status_events | 1.126 | 0.084 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip | Turbine_Data_Penmanshiel_14_2021-01-01_-_2022-01-01_1054.csv | scada_10min | 226.2 | 83.64 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip | Status_Penmanshiel_14_2021-01-01_-_2022-01-01_1054.csv | status_events | 1.18 | 0.086 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip | Turbine_Data_Penmanshiel_15_2021-01-01_-_2022-01-01_1056.csv | scada_10min | 226.5 | 83.71 |
| Penmanshiel_SCADA_2021_WT11-15_4461.zip | Status_Penmanshiel_15_2021-01-01_-_2022-01-01_1056.csv | status_events | 0.978 | 0.075 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Turbine_Data_Penmanshiel_01_2022-01-01_-_2023-01-01_1042.csv | scada_10min | 215.2 | 79.47 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Status_Penmanshiel_01_2022-01-01_-_2023-01-01_1042.csv | status_events | 0.944 | 0.07 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Turbine_Data_Penmanshiel_02_2022-01-01_-_2023-01-01_1043.csv | scada_10min | 212.5 | 79.03 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Status_Penmanshiel_02_2022-01-01_-_2023-01-01_1043.csv | status_events | 1.095 | 0.081 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Turbine_Data_Penmanshiel_04_2022-01-01_-_2023-01-01_1044.csv | scada_10min | 213.7 | 78.95 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Status_Penmanshiel_04_2022-01-01_-_2023-01-01_1044.csv | status_events | 0.921 | 0.07 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Turbine_Data_Penmanshiel_05_2022-01-01_-_2023-01-01_1045.csv | scada_10min | 212.5 | 78.03 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Status_Penmanshiel_05_2022-01-01_-_2023-01-01_1045.csv | status_events | 1.255 | 0.092 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Turbine_Data_Penmanshiel_06_2022-01-01_-_2023-01-01_1046.csv | scada_10min | 214.8 | 78.03 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Status_Penmanshiel_06_2022-01-01_-_2023-01-01_1046.csv | status_events | 1.044 | 0.078 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Turbine_Data_Penmanshiel_07_2022-01-01_-_2023-01-01_1047.csv | scada_10min | 211.5 | 78.72 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Status_Penmanshiel_07_2022-01-01_-_2023-01-01_1047.csv | status_events | 1.292 | 0.094 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Turbine_Data_Penmanshiel_08_2022-01-01_-_2023-01-01_1048.csv | scada_10min | 215.3 | 79.89 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Status_Penmanshiel_08_2022-01-01_-_2023-01-01_1048.csv | status_events | 1.41 | 0.104 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Turbine_Data_Penmanshiel_09_2022-01-01_-_2023-01-01_1049.csv | scada_10min | 213.7 | 79.08 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Status_Penmanshiel_09_2022-01-01_-_2023-01-01_1049.csv | status_events | 1.154 | 0.085 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Turbine_Data_Penmanshiel_10_2022-01-01_-_2023-01-01_1050.csv | scada_10min | 213.5 | 78.82 |
| Penmanshiel_SCADA_2022_WT01-10_4462.zip | Status_Penmanshiel_10_2022-01-01_-_2023-01-01_1050.csv | status_events | 1.204 | 0.087 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip | Turbine_Data_Penmanshiel_11_2022-01-01_-_2023-01-01_1051.csv | scada_10min | 203.6 | 73.41 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip | Status_Penmanshiel_11_2022-01-01_-_2023-01-01_1051.csv | status_events | 0.909 | 0.07 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip | Turbine_Data_Penmanshiel_12_2022-01-01_-_2023-01-01_1052.csv | scada_10min | 214.6 | 79.84 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip | Status_Penmanshiel_12_2022-01-01_-_2023-01-01_1052.csv | status_events | 0.836 | 0.065 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip | Turbine_Data_Penmanshiel_13_2022-01-01_-_2023-01-01_1053.csv | scada_10min | 227.4 | 84.77 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip | Status_Penmanshiel_13_2022-01-01_-_2023-01-01_1053.csv | status_events | 0.952 | 0.07 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip | Turbine_Data_Penmanshiel_14_2022-01-01_-_2023-01-01_1054.csv | scada_10min | 214.3 | 79.13 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip | Status_Penmanshiel_14_2022-01-01_-_2023-01-01_1054.csv | status_events | 0.951 | 0.071 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip | Turbine_Data_Penmanshiel_15_2022-01-01_-_2023-01-01_1056.csv | scada_10min | 214.7 | 79.23 |
| Penmanshiel_SCADA_2022_WT11-15_4463.zip | Status_Penmanshiel_15_2022-01-01_-_2023-01-01_1056.csv | status_events | 0.823 | 0.063 |
| Penmanshiel_WT_dataSignalMapping.xlsx | (loose file) | metadata | 0.019 | 0.019 |
| Penmanshiel_WT_static.csv | (loose file) | metadata | 0.002 | 0.002 |
