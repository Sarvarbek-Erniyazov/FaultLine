# Raw inventory: kelmarsh

| field | value |
| --- | --- |
| source | kelmarsh |
| provider | Cubico Sustainable Investments Ltd |
| licence | CC-BY-4.0 |
| zenodo record | 16,807,551 |
| concept DOI | 10.5281/zenodo.5841833 |
| staged directory | C:\Users\sharg\Desktop\github\FaultLine\data\raw\telemetry\kelmarsh |
| files staged | 11 |
| members discovered | 110 |
| member classification | file-name substring patterns in the adapter |
| event members parsed | 54 of 54 (caps: 200 members, 209.7 MB and 500,000 rows per member) |
| generated (UTC) | 2026-09-10T09:22:22+00:00 |
| git_sha | aac5d7110773da2a7337e045b61237a5001db107 |

## Free-text verdict

**VERIFIED no** - a code book: 217 distinct strings over 504,180 rows with text, mean length 14.1 characters (2.3 words), 14.7% of the distinct strings occurring exactly once; at most 81 distinct strings in any one table. A closed set of recurring labels, not open-ended language (ADR-0001 holds)

This is the evidence behind ADR-0001: whether the paired text in this record is open-ended language or a controlled vocabulary.

Thresholds applied: more than 500 distinct strings is open-ended text; within that, a set in which at least 50% of the distinct strings occur exactly once was written per event, otherwise it is a code book; written descriptions averaging at most 200 characters are short. The measurements are pooled over every parsed event table and listed in the next section.

## Text measurements (all parsed tables pooled)

| field | value |
| --- | --- |
| event tables parsed | 54 |
| rows | 504,180 |
| rows with a non-empty message | 504,180 (100.0%) |
| distinct messages | 217 |
| mean length (characters) | 14.1 |
| mean length (words) | 2.3 |
| distinct messages occurring exactly once | 14.7% |
| most distinct messages in one table | 81 |
| longest mean length in one table (characters) | 15.5 |

**Top 20 messages** (share of rows with a message)

| message | count | share |
| --- | --- | --- |
| Automatic start-up | 60,842 | 12.07% |
| Run-up | 59,555 | 11.81% |
| System OK | 58,454 | 11.59% |
| Wind < start wind | 57,746 | 11.45% |
| Mains connection | 54,765 | 10.86% |
| Brake program 50 | 54,707 | 10.85% |
| Mains run-up | 54,614 | 10.83% |
| Mains operation | 54,583 | 10.83% |
| Bypass limit switches | 4,830 | 0.96% |
| Absence of wind during run-up | 4,363 | 0.87% |
| System test 1 | 3,244 | 0.64% |
| Brake program 52 | 3,035 | 0.60% |
| System test 2 | 3,024 | 0.60% |
| System test 3 | 3,003 | 0.60% |
| Battery test | 2,607 | 0.52% |
| Brake program 180 | 2,503 | 0.50% |
| Brake program 60 | 2,499 | 0.50% |
| Technical curtailment | 1,440 | 0.29% |
| High yaw motor current | 1,274 | 0.25% |
| Brake program 170 | 1,206 | 0.24% |

## Event codes (all parsed tables pooled)

| field | value |
| --- | --- |
| tables with a code column | 54 of 54 |
| rows carrying a code | 504,180 |
| distinct codes | 216 |

**Top 20 codes**

| code | rows | share |
| --- | --- | --- |
| 100130 | 60,842 | 12.07% |
| 100180 | 59,555 | 11.81% |
| 0 | 58,454 | 11.59% |
| 10 | 57,746 | 11.45% |
| 100190 | 54,765 | 10.86% |
| 100070 | 54,707 | 10.85% |
| 100200 | 54,614 | 10.83% |
| 100210 | 54,583 | 10.83% |
| 100110 | 4,830 | 0.96% |
| 65 | 4,363 | 0.87% |
| 100140 | 3,244 | 0.64% |
| 100060 | 3,035 | 0.60% |
| 100150 | 3,024 | 0.60% |
| 100160 | 3,003 | 0.60% |
| 710 | 2,607 | 0.52% |
| 100030 | 2,503 | 0.50% |
| 100050 | 2,499 | 0.50% |
| 108 | 1,440 | 0.29% |
| 6052 | 1,274 | 0.25% |
| 100035 | 1,206 | 0.24% |

## Staged files

| file | size (MB) | members |
| --- | --- | --- |
| Kelmarsh_SCADA_2016_3082.zip | 97.9 | 12 |
| Kelmarsh_SCADA_2017_3083.zip | 174.6 | 12 |
| Kelmarsh_SCADA_2018_3084.zip | 262.2 | 12 |
| Kelmarsh_SCADA_2019_3085.zip | 311.3 | 12 |
| Kelmarsh_SCADA_2020_3086.zip | 473.7 | 12 |
| Kelmarsh_SCADA_2021_4456.zip | 467.5 | 12 |
| Kelmarsh_SCADA_2022_4457.zip | 485.6 | 12 |
| Kelmarsh_SCADA_2023_5961.zip | 716.1 | 12 |
| Kelmarsh_SCADA_2024_5962.zip | 704.6 | 12 |
| Kelmarsh_WT_dataSignalMapping.csv | 0 | 1 |
| Kelmarsh_WT_static.csv | 0 | 1 |

## Members by kind

| kind | members | uncompressed (MB) |
| --- | --- | --- |
| metadata | 2 | 0 |
| scada_10min | 54 | 4.153e+04 |
| status_events | 54 | 47.9 |

## Event tables found

| member | rows | columns | code column | message column | unique codes | unique messages | free-text share | mean chars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_1_2016-01-03_… | 2,122 | 9 | Code | Message | 69 | 69 | 100.0% | 14.7 |
| Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_2_2016-01-03_… | 1,790 | 9 | Code | Message | 75 | 75 | 100.0% | 14.5 |
| Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_3_2016-01-03_… | 2,873 | 9 | Code | Message | 68 | 68 | 100.0% | 14 |
| Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_4_2016-01-03_… | 1,929 | 9 | Code | Message | 67 | 67 | 100.0% | 14 |
| Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_5_2016-01-03_… | 2,116 | 9 | Code | Message | 59 | 59 | 100.0% | 14.2 |
| Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_6_2016-01-03_… | 3,189 | 9 | Code | Message | 60 | 60 | 100.0% | 14.1 |
| Kelmarsh_SCADA_2017_3083.zip::Status_Kelmarsh_1_2017-01-01_… | 7,365 | 9 | Code | Message | 63 | 63 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2017_3083.zip::Status_Kelmarsh_2_2017-01-01_… | 6,382 | 9 | Code | Message | 64 | 64 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2017_3083.zip::Status_Kelmarsh_3_2017-01-01_… | 9,670 | 9 | Code | Message | 66 | 66 | 100.0% | 13.8 |
| Kelmarsh_SCADA_2017_3083.zip::Status_Kelmarsh_4_2017-01-01_… | 6,505 | 9 | Code | Message | 62 | 62 | 100.0% | 14 |
| Kelmarsh_SCADA_2017_3083.zip::Status_Kelmarsh_5_2017-01-01_… | 7,696 | 9 | Code | Message | 62 | 62 | 100.0% | 14 |
| Kelmarsh_SCADA_2017_3083.zip::Status_Kelmarsh_6_2017-01-01_… | 11,514 | 9 | Code | Message | 58 | 58 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2018_3084.zip::Status_Kelmarsh_1_2018-01-01_… | 10,674 | 9 | Code | Message | 67 | 67 | 100.0% | 14 |
| Kelmarsh_SCADA_2018_3084.zip::Status_Kelmarsh_2_2018-01-01_… | 9,443 | 9 | Code | Message | 78 | 78 | 100.0% | 14 |
| Kelmarsh_SCADA_2018_3084.zip::Status_Kelmarsh_3_2018-01-01_… | 12,515 | 9 | Code | Message | 71 | 71 | 100.0% | 14.5 |
| Kelmarsh_SCADA_2018_3084.zip::Status_Kelmarsh_4_2018-01-01_… | 9,933 | 9 | Code | Message | 68 | 68 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2018_3084.zip::Status_Kelmarsh_5_2018-01-01_… | 11,444 | 9 | Code | Message | 72 | 72 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2018_3084.zip::Status_Kelmarsh_6_2018-01-01_… | 15,954 | 9 | Code | Message | 77 | 77 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2019_3085.zip::Status_Kelmarsh_1_2019-01-01_… | 7,821 | 9 | Code | Message | 63 | 63 | 100.0% | 14.1 |
| Kelmarsh_SCADA_2019_3085.zip::Status_Kelmarsh_2_2019-01-01_… | 7,830 | 9 | Code | Message | 58 | 58 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2019_3085.zip::Status_Kelmarsh_3_2019-01-01_… | 11,902 | 9 | Code | Message | 54 | 54 | 100.0% | 13.8 |
| Kelmarsh_SCADA_2019_3085.zip::Status_Kelmarsh_4_2019-01-01_… | 8,838 | 9 | Code | Message | 66 | 66 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2019_3085.zip::Status_Kelmarsh_5_2019-01-01_… | 9,163 | 9 | Code | Message | 56 | 56 | 100.0% | 13.8 |
| Kelmarsh_SCADA_2019_3085.zip::Status_Kelmarsh_6_2019-01-01_… | 13,772 | 9 | Code | Message | 54 | 54 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2020_3086.zip::Status_Kelmarsh_1_2020-01-01_… | 8,737 | 9 | Code | Message | 65 | 65 | 100.0% | 14 |
| Kelmarsh_SCADA_2020_3086.zip::Status_Kelmarsh_2_2020-01-01_… | 7,532 | 9 | Code | Message | 66 | 66 | 100.0% | 14.1 |
| Kelmarsh_SCADA_2020_3086.zip::Status_Kelmarsh_3_2020-01-01_… | 11,192 | 9 | Code | Message | 62 | 62 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2020_3086.zip::Status_Kelmarsh_4_2020-01-01_… | 8,601 | 9 | Code | Message | 55 | 55 | 100.0% | 14 |
| Kelmarsh_SCADA_2020_3086.zip::Status_Kelmarsh_5_2020-01-01_… | 9,400 | 9 | Code | Message | 51 | 51 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2020_3086.zip::Status_Kelmarsh_6_2020-01-01_… | 12,053 | 9 | Code | Message | 58 | 58 | 100.0% | 14.2 |
| Kelmarsh_SCADA_2021_4456.zip::Status_Kelmarsh_1_2021-01-01_… | 9,997 | 11 | Code | Message | 72 | 72 | 100.0% | 14 |
| Kelmarsh_SCADA_2021_4456.zip::Status_Kelmarsh_2_2021-01-01_… | 7,717 | 11 | Code | Message | 60 | 60 | 100.0% | 14.4 |
| Kelmarsh_SCADA_2021_4456.zip::Status_Kelmarsh_3_2021-01-01_… | 12,262 | 11 | Code | Message | 62 | 62 | 100.0% | 14.3 |
| Kelmarsh_SCADA_2021_4456.zip::Status_Kelmarsh_4_2021-01-01_… | 10,311 | 11 | Code | Message | 60 | 60 | 100.0% | 14.1 |
| Kelmarsh_SCADA_2021_4456.zip::Status_Kelmarsh_5_2021-01-01_… | 11,008 | 11 | Code | Message | 73 | 73 | 100.0% | 14 |
| Kelmarsh_SCADA_2021_4456.zip::Status_Kelmarsh_6_2021-01-01_… | 14,033 | 11 | Code | Message | 62 | 62 | 100.0% | 14 |
| Kelmarsh_SCADA_2022_4457.zip::Status_Kelmarsh_1_2022-01-01_… | 11,385 | 11 | Code | Message | 79 | 79 | 100.0% | 14.1 |
| Kelmarsh_SCADA_2022_4457.zip::Status_Kelmarsh_2_2022-01-01_… | 10,739 | 11 | Code | Message | 81 | 81 | 100.0% | 14.1 |
| Kelmarsh_SCADA_2022_4457.zip::Status_Kelmarsh_3_2022-01-01_… | 13,714 | 11 | Code | Message | 60 | 60 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2022_4457.zip::Status_Kelmarsh_4_2022-01-01_… | 9,526 | 11 | Code | Message | 66 | 66 | 100.0% | 14 |
| Kelmarsh_SCADA_2022_4457.zip::Status_Kelmarsh_5_2022-01-01_… | 11,197 | 11 | Code | Message | 69 | 69 | 100.0% | 14.2 |
| Kelmarsh_SCADA_2022_4457.zip::Status_Kelmarsh_6_2022-01-01_… | 13,289 | 11 | Code | Message | 72 | 72 | 100.0% | 14.3 |
| Kelmarsh_SCADA_2023_5961.zip::Status_Kelmarsh_1_2023-01-01_… | 7,997 | 11 | Code | Message | 64 | 64 | 100.0% | 14 |
| Kelmarsh_SCADA_2023_5961.zip::Status_Kelmarsh_2_2023-01-01_… | 7,652 | 11 | Code | Message | 60 | 60 | 100.0% | 14.3 |
| Kelmarsh_SCADA_2023_5961.zip::Status_Kelmarsh_3_2023-01-01_… | 10,556 | 11 | Code | Message | 54 | 54 | 100.0% | 13.9 |
| Kelmarsh_SCADA_2023_5961.zip::Status_Kelmarsh_4_2023-01-01_… | 8,970 | 11 | Code | Message | 79 | 79 | 100.0% | 15.5 |
| Kelmarsh_SCADA_2023_5961.zip::Status_Kelmarsh_5_2023-01-01_… | 10,705 | 11 | Code | Message | 73 | 73 | 100.0% | 14.2 |
| Kelmarsh_SCADA_2023_5961.zip::Status_Kelmarsh_6_2023-01-01_… | 12,143 | 11 | Code | Message | 61 | 61 | 100.0% | 14.2 |
| Kelmarsh_SCADA_2024_5962.zip::Status_Kelmarsh_1_2024-01-01_… | 9,437 | 11 | Code | Message | 64 | 64 | 100.0% | 14.3 |
| Kelmarsh_SCADA_2024_5962.zip::Status_Kelmarsh_2_2024-01-01_… | 8,748 | 11 | Code | Message | 55 | 55 | 100.0% | 14.2 |
| Kelmarsh_SCADA_2024_5962.zip::Status_Kelmarsh_3_2024-01-01_… | 12,781 | 11 | Code | Message | 54 | 54 | 100.0% | 13.8 |
| Kelmarsh_SCADA_2024_5962.zip::Status_Kelmarsh_4_2024-01-01_… | 8,365 | 11 | Code | Message | 67 | 67 | 100.0% | 14.2 |
| Kelmarsh_SCADA_2024_5962.zip::Status_Kelmarsh_5_2024-01-01_… | 9,700 | 11 | Code | Message | 54 | 54 | 100.0% | 14.3 |
| Kelmarsh_SCADA_2024_5962.zip::Status_Kelmarsh_6_2024-01-01_… | 11,993 | 11 | Code | Message | 69 | 69 | 100.0% | 14.5 |

### Top messages: Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_1_2016-01-03_…

| message | count | share |
| --- | --- | --- |
| System OK | 911 | 42.93% |
| Wind < start wind | 753 | 35.49% |
| Brake accumulator defect | 68 | 3.20% |
| Absence of wind during run-up | 67 | 3.16% |
| Battery test | 40 | 1.89% |
| Manual yaw | 33 | 1.56% |
| Data communication unavailable | 28 | 1.32% |
| Manual stop - on site | 27 | 1.27% |
| Timeout brake closed | 22 | 1.04% |
| Comm. failure FPM | 18 | 0.85% |
| Cable autounwind | 10 | 0.47% |
| Gearbox warm-up stage | 10 | 0.47% |
| High rotor speed nacelle | 8 | 0.38% |
| Overload generator fan 1 | 8 | 0.38% |
| Overload generator fan 2 | 8 | 0.38% |
| Overload generator fan 3 | 8 | 0.38% |
| Battery charge cycle axis 1 error | 6 | 0.28% |
| Battery charge cycle axis 2 error | 6 | 0.28% |
| Battery charge cycle axis 3 error | 6 | 0.28% |
| Hydraulic oil flushing operation | 5 | 0.24% |

### Top messages: Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_2_2016-01-03_…

| message | count | share |
| --- | --- | --- |
| System OK | 763 | 42.63% |
| Wind < start wind | 679 | 37.93% |
| Absence of wind during run-up | 46 | 2.57% |
| Battery test | 42 | 2.35% |
| Data communication unavailable | 28 | 1.56% |
| Manual yaw | 21 | 1.17% |
| Manual stop - on site | 19 | 1.06% |
| Gear heating enabled | 11 | 0.61% |
| Cable autounwind | 10 | 0.56% |
| Gearbox warm-up stage | 10 | 0.56% |
| Timeout brake closed | 10 | 0.56% |
| Breakdown obstacle light | 8 | 0.45% |
| Frequency converter not ready | 8 | 0.45% |
| Oscillation encoder tower | 8 | 0.45% |
| Grid loss | 7 | 0.39% |
| Manual stop - remote | 7 | 0.39% |
| Brake accumulator defect | 6 | 0.34% |
| Comm. failure FPM | 6 | 0.34% |
| Safety chain open | 6 | 0.34% |
| Frequency converter error | 5 | 0.28% |

### Top messages: Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_3_2016-01-03_…

| message | count | share |
| --- | --- | --- |
| System OK | 1,354 | 47.13% |
| Wind < start wind | 1,122 | 39.05% |
| Absence of wind during run-up | 103 | 3.59% |
| Battery test | 41 | 1.43% |
| Data communication unavailable | 27 | 0.94% |
| Manual stop - on site | 24 | 0.84% |
| Gearbox warm-up stage | 22 | 0.77% |
| Manual yaw | 21 | 0.73% |
| Cable autounwind | 12 | 0.42% |
| Comm. failure FPM | 11 | 0.38% |
| Oscillation encoder tower | 9 | 0.31% |
| Timeout brake closed | 9 | 0.31% |
| Grid loss | 6 | 0.21% |
| Brake accumulator defect | 5 | 0.17% |
| Gear heating enabled | 5 | 0.17% |
| Overload generator fan 1 | 5 | 0.17% |
| Overload generator fan 2 | 5 | 0.17% |
| Overload generator fan 3 | 5 | 0.17% |
| 4-20 mA vane 2 | 4 | 0.14% |
| 4-20mA anemometer 2 | 4 | 0.14% |

### Top messages: Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_4_2016-01-03_…

| message | count | share |
| --- | --- | --- |
| System OK | 895 | 46.40% |
| Wind < start wind | 738 | 38.26% |
| Absence of wind during run-up | 59 | 3.06% |
| Battery test | 45 | 2.33% |
| Data communication unavailable | 28 | 1.45% |
| Manual yaw | 17 | 0.88% |
| Manual stop - on site | 15 | 0.78% |
| Cable autounwind | 10 | 0.52% |
| Timeout brake closed | 8 | 0.41% |
| Brake accumulator defect | 7 | 0.36% |
| Comm. failure FPM | 6 | 0.31% |
| Grid loss | 6 | 0.31% |
| Frequency converter not ready | 5 | 0.26% |
| Gearbox warm-up stage | 5 | 0.26% |
| Hydraulic oil flushing operation | 5 | 0.26% |
| Overload generator fan 1 | 5 | 0.26% |
| Overload generator fan 2 | 5 | 0.26% |
| Overload generator fan 3 | 5 | 0.26% |
| High frequency - P reduction | 4 | 0.21% |
| Manual stop - remote | 4 | 0.21% |

### Top messages: Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_5_2016-01-03_…

| message | count | share |
| --- | --- | --- |
| System OK | 936 | 44.23% |
| Wind < start wind | 812 | 38.37% |
| Absence of wind during run-up | 65 | 3.07% |
| Battery test | 47 | 2.22% |
| Data communication unavailable | 27 | 1.28% |
| Gear heating enabled | 24 | 1.13% |
| Manual yaw | 24 | 1.13% |
| Manual stop - on site | 19 | 0.90% |
| Comm. failure FPM | 18 | 0.85% |
| Cable autounwind | 16 | 0.76% |
| Timeout brake closed | 15 | 0.71% |
| Gearbox warm-up stage | 11 | 0.52% |
| Overload generator fan 1 | 7 | 0.33% |
| Overload generator fan 2 | 7 | 0.33% |
| Overload generator fan 3 | 7 | 0.33% |
| Breakdown obstacle light | 5 | 0.24% |
| Grid loss | 5 | 0.24% |
| Hydraulic oil flushing operation | 5 | 0.24% |
| High frequency - P reduction | 4 | 0.19% |
| Low gearbox oil pressure | 4 | 0.19% |

### Top messages: Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_6_2016-01-03_…

| message | count | share |
| --- | --- | --- |
| System OK | 1,493 | 46.82% |
| Wind < start wind | 1,282 | 40.20% |
| Absence of wind during run-up | 135 | 4.23% |
| Battery test | 43 | 1.35% |
| Data communication unavailable | 28 | 0.88% |
| Manual yaw | 18 | 0.56% |
| Manual stop - on site | 13 | 0.41% |
| Overload generator fan 1 | 12 | 0.38% |
| Cable autounwind | 10 | 0.31% |
| Overload generator fan 2 | 10 | 0.31% |
| Overload generator fan 3 | 10 | 0.31% |
| Timeout brake closed | 10 | 0.31% |
| Battery charge cycle axis 1 error | 8 | 0.25% |
| Battery charge cycle axis 2 error | 8 | 0.25% |
| Battery charge cycle axis 3 error | 8 | 0.25% |
| Brake accumulator defect | 8 | 0.25% |
| Comm. failure FPM | 7 | 0.22% |
| Frequency converter not ready | 7 | 0.22% |
| Gearbox warm-up stage | 6 | 0.19% |
| Grid loss | 5 | 0.16% |

### Top messages: Kelmarsh_SCADA_2017_3083.zip::Status_Kelmarsh_1_2017-01-01_…

| message | count | share |
| --- | --- | --- |
| System OK | 1,005 | 13.65% |
| Automatic start-up | 861 | 11.69% |
| Run-up | 852 | 11.57% |
| Wind < start wind | 801 | 10.88% |
| Mains connection | 796 | 10.81% |
| Mains operation | 796 | 10.81% |
| Mains run-up | 796 | 10.81% |
| Brake program 50 | 791 | 10.74% |
| Absence of wind during run-up | 65 | 0.88% |
| Bypass limit switches | 56 | 0.76% |
| Brake program 180 | 50 | 0.68% |
| System test 1 | 50 | 0.68% |
| System test 2 | 50 | 0.68% |
| System test 3 | 50 | 0.68% |
| Battery test | 48 | 0.65% |
| Manual stop - on site | 29 | 0.39% |
| Brake program 52 | 26 | 0.35% |
| Manual yaw | 25 | 0.34% |
| Data communication unavailable | 21 | 0.29% |
| Brake program 170 | 20 | 0.27% |

### Top messages: Kelmarsh_SCADA_2017_3083.zip::Status_Kelmarsh_2_2017-01-01_…

| message | count | share |
| --- | --- | --- |
| System OK | 826 | 12.94% |
| Automatic start-up | 750 | 11.75% |
| Run-up | 742 | 11.63% |
| Wind < start wind | 700 | 10.97% |
| Mains connection | 699 | 10.95% |
| Mains operation | 699 | 10.95% |
| Mains run-up | 699 | 10.95% |
| Brake program 50 | 676 | 10.59% |
| Bypass limit switches | 57 | 0.89% |
| Battery test | 50 | 0.78% |
| Absence of wind during run-up | 47 | 0.74% |
| System test 1 | 47 | 0.74% |
| System test 2 | 47 | 0.74% |
| System test 3 | 47 | 0.74% |
| Brake program 180 | 39 | 0.61% |
| Brake program 52 | 32 | 0.50% |
| Brake program 170 | 23 | 0.36% |
| Manual stop - on site | 19 | 0.30% |
| Cable autounwind | 18 | 0.28% |
| Data communication unavailable | 17 | 0.27% |

### Top messages: Kelmarsh_SCADA_2017_3083.zip::Status_Kelmarsh_3_2017-01-01_…

| message | count | share |
| --- | --- | --- |
| System OK | 1,334 | 13.80% |
| Automatic start-up | 1,154 | 11.93% |
| Run-up | 1,143 | 11.82% |
| Wind < start wind | 1,123 | 11.61% |
| Brake program 50 | 1,079 | 11.16% |
| Mains connection | 1,062 | 10.98% |
| Mains run-up | 1,061 | 10.97% |
| Mains operation | 1,060 | 10.96% |
| Absence of wind during run-up | 84 | 0.87% |
| Bypass limit switches | 61 | 0.63% |
| Battery test | 53 | 0.55% |
| System test 1 | 47 | 0.49% |
| System test 2 | 47 | 0.49% |
| System test 3 | 47 | 0.49% |
| Brake program 180 | 45 | 0.47% |
| Brake program 52 | 30 | 0.31% |
| Data communication unavailable | 21 | 0.22% |
| Cable autounwind | 18 | 0.19% |
| Manual yaw | 18 | 0.19% |
| Manual stop - on site | 17 | 0.18% |

### Top messages: Kelmarsh_SCADA_2017_3083.zip::Status_Kelmarsh_4_2017-01-01_…

| message | count | share |
| --- | --- | --- |
| System OK | 871 | 13.39% |
| Automatic start-up | 762 | 11.71% |
| Run-up | 754 | 11.59% |
| Wind < start wind | 701 | 10.78% |
| Brake program 50 | 695 | 10.68% |
| Mains connection | 694 | 10.67% |
| Mains operation | 693 | 10.65% |
| Mains run-up | 693 | 10.65% |
| Absence of wind during run-up | 68 | 1.05% |
| Bypass limit switches | 55 | 0.85% |
| Battery test | 51 | 0.78% |
| System test 1 | 47 | 0.72% |
| System test 2 | 47 | 0.72% |
| System test 3 | 47 | 0.72% |
| Brake program 180 | 38 | 0.58% |
| Breakdown obstacle light | 28 | 0.43% |
| Brake program 52 | 27 | 0.42% |
| Data communication unavailable | 26 | 0.40% |
| Brake program 170 | 22 | 0.34% |
| Manual stop - on site | 19 | 0.29% |

### Top messages: Kelmarsh_SCADA_2017_3083.zip::Status_Kelmarsh_5_2017-01-01_…

| message | count | share |
| --- | --- | --- |
| System OK | 1,031 | 13.40% |
| Automatic start-up | 904 | 11.75% |
| Run-up | 894 | 11.62% |
| Wind < start wind | 851 | 11.06% |
| Brake program 50 | 822 | 10.68% |
| Mains connection | 817 | 10.62% |
| Mains run-up | 816 | 10.60% |
| Mains operation | 815 | 10.59% |
| Bypass limit switches | 80 | 1.04% |
| Absence of wind during run-up | 73 | 0.95% |
| System test 1 | 57 | 0.74% |
| System test 2 | 56 | 0.73% |
| System test 3 | 56 | 0.73% |
| Battery test | 51 | 0.66% |
| Brake program 180 | 50 | 0.65% |
| Brake program 60 | 37 | 0.48% |
| Brake program 52 | 28 | 0.36% |
| Brake program 170 | 23 | 0.30% |
| Brake program 200 | 21 | 0.27% |
| Data communication unavailable | 20 | 0.26% |

### Top messages: Kelmarsh_SCADA_2017_3083.zip::Status_Kelmarsh_6_2017-01-01_…

| message | count | share |
| --- | --- | --- |
| System OK | 1,577 | 13.70% |
| Automatic start-up | 1,403 | 12.19% |
| Run-up | 1,361 | 11.82% |
| Wind < start wind | 1,290 | 11.20% |
| Brake program 50 | 1,268 | 11.01% |
| Mains connection | 1,233 | 10.71% |
| Mains run-up | 1,233 | 10.71% |
| Mains operation | 1,231 | 10.69% |
| Absence of wind during run-up | 114 | 0.99% |
| Bypass limit switches | 105 | 0.91% |
| Brake program 60 | 65 | 0.56% |
| System test 1 | 65 | 0.56% |
| Brake program 52 | 58 | 0.50% |
| System test 2 | 54 | 0.47% |
| System test 3 | 54 | 0.47% |
| Battery test | 47 | 0.41% |
| Brake program 180 | 38 | 0.33% |
| Brake program 170 | 34 | 0.30% |
| Data communication unavailable | 29 | 0.25% |
| Open disc brake | 28 | 0.24% |

_Per-table top messages are shown for the first 12 of 54 tables with messages; the pooled measurements above cover all of them._

## Header samples (first lines, one member per kind)

**Kelmarsh_SCADA_2016_3082.zip::Turbine_Data_Kelmarsh_1_2016-01-03_-_2017-01-01_228.csv**

```text
# This file was exported by Greenbyte at 2022-01-27 10:33:05. Please see https://www.greenbyte.com for more information about Greenbyte.
#
# Turbine: Kelmarsh 1
# Turbine type: Senvion MM92
# Time zone: UTC
# Time interval: 2016-01-01 00:00:00 - 2017-01-01 00:00:00 (366 days)
#
# Data that is missing or is erroneous has been marked with the value "NaN"
#
# Date and time,Wind speed (m/s),"Wind speed, Standard deviation (m/s)","Wind speed, Minimum (m/s)","Wind speed, Maximum (m/s)",Long Term Wind (m/s),Wind speed Sensor 1 (m/s),"Wind speed Sensor 1, Sta
2016-01-03 00:00:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 00:10:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 00:20:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 00:30:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 00:40:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 00:50:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 01:00:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 01:10:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 01:20:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 01:30:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 01:40:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 01:50:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 02:00:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 02:10:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 02:20:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 02:30:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 02:40:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 02:50:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 03:00:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
2016-01-03 03:10:00,NaN,NaN,NaN,NaN,7.1,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,171.25287356321837,NaN,NaN,N
```

**Kelmarsh_SCADA_2016_3082.zip::Status_Kelmarsh_1_2016-01-03_-_2017-01-01_228.csv**

```text
# This file was exported by Greenbyte at 2022-01-27 10:52:06. Please see https://www.greenbyte.com for more information about Greenbyte.
#
# Turbine: Kelmarsh 1
# Turbine type: Senvion MM92 (Senvion MM92 kW)
# Time zone: UTC
# Time interval: 2016-01-01 00:00:00 - 2017-01-01 00:00:00 (366 days)
#
# Kelmarsh 1 Sum production: 4239777 kWh
#
Timestamp start,Timestamp end,Duration,Status,Code,Message,Comment,Service contract category,IEC category
2016-01-14 19:28:03,2016-01-23 14:36:32,211:08:29,Stop,111,Emergency stop nacelle,,Emergency stop switch (Nacelle) (11),Forced outage
2016-01-14 19:28:03,2016-01-14 19:38:03,00:10:00,Warning,5720,Brake accumulator defect,,Warnings (27),
2016-01-14 19:28:05,2016-01-23 11:27:46,207:59:41,Informational,3835,Cable panel breaker open,,Warnings (27),
2016-01-14 19:28:05,2016-01-23 11:27:46,207:59:41,Informational,3830,Supply circuit breaker earthed,,Warnings (27),Full Performance
2016-01-14 19:28:05,2016-01-23 14:09:18,210:41:13,Warning,3870,Overload transformer fan outlet air,,Warnings (27),Full Performance
2016-01-14 19:28:05,2016-01-23 12:38:11,209:10:06,Warning,3875,Overload transf. fan inlet air,,Warnings (27),
2016-01-14 19:28:05,2016-01-23 11:27:42,207:59:37,Warning,2650,Overload generator fan 2,,Warnings (27),Forced outage
2016-01-14 19:28:05,2016-01-23 11:27:42,207:59:37,Warning,2655,Overload generator fan 3,,Warnings (27),Forced outage
2016-01-14 19:28:05,2016-01-23 11:27:42,207:59:37,Warning,2550,Overload generator fan 1,,Warnings (27),Forced outage
2016-01-14 19:28:05,2016-01-23 12:38:11,209:10:06,Warning,1825,Overload gear bypass filter,,Warnings (27),
2016-01-14 19:28:06,2016-01-23 13:27:50,209:59:44,Warning,785,Error brake resistor CHP,,Warnings (27),Full Performance
2016-01-14 19:28:15,2016-01-23 13:30:53,210:02:38,Warning,8402,No assignment to a PMU,,Warnings (27),
2016-01-23 11:45:28,2016-01-23 13:46:40,02:01:12,Warning,675,Pitch measuring system 1><2,,Warnings (27),
2016-01-23 12:22:52,2016-01-23 12:28:14,00:05:22,Informational,1555,Gear heating enabled,,Operating states  (28),Technical Standby
2016-01-23 12:26:59,2016-01-23 14:39:43,02:12:44,Informational,402,Semi-automatic operation,,Warnings (27),
2016-01-23 12:30:30,2016-01-23 12:30:41,00:00:11,Informational,2900,Manual operation generator heating,,Warnings (27),Full Performance
2016-01-23 12:30:32,2016-01-23 12:31:04,00:00:32,Informational,2910,Manual operation generator fan 1,,Warnings (27),Full Performance
2016-01-23 12:30:33,2016-01-23 12:31:05,00:00:32,Informational,2920,Manual operation generator fan 2,,Warnings (27),Full Performance
2016-01-23 12:30:34,2016-01-23 12:31:07,00:00:33,Informational,2930,Manual operation generator fan 3,,Warnings (27),Full Performance
2016-01-23 12:30:35,2016-01-23 12:31:08,00:00:33,Informational,1560,Manual operation fan gear,,Operating states  (28),Full Performance
```

**Kelmarsh_WT_dataSignalMapping.csv**

```text
Greenbyte Signal ID,Greenbyte Title,Manufacturer Title,Unit
359,Ambient temperature (converter),Temperature of converter inlet air,degC
323,Apparent power,Actual value of apparent power,kVA
80,Blade angle (pitch position) A,Pitch angle for blade 1,deg
81,Blade angle (pitch position) B,Pitch angle for blade 2,deg
82,Blade angle (pitch position) C,Pitch angle for blade 3,deg
450,Cable windings from calibration point,Cable winding: number of windings from calibration point,
1624,CPU temperature,CPU temperature 1s,degC
49,Current L1 / U,Phase A current,A
50,Current L2 / V,Phase B current,A
51,Current L3 / W,Phase C current,A
456,Drive train acceleration,Drive train osc. z 10min,mm/ss
4,Energy Export,Entire active energy generation,kWh
90,Energy Import,Active energy demand,kWh
9,Front bearing temperature,Axle bearing temperature 1,degC
317,Gear oil inlet pressure,Pressure gearb.inlet 1s,bar
117,Gear oil inlet temperature,Temp. gearb. inlet 1s,degC
455,Gear oil pump pressure,Pressure gear pump 1s,bar
178,Gear oil temperature,Gear oil temperature,degC
448,Gearbox speed,Gearbox speed,RPM
119,Generator bearing front temperature,Temperature of bearing 1,degC
118,Generator bearing rear temperature,Temperature of bearing 2,degC
86,Generator RPM,Generator speed,RPM
297,Grid current,Line current,A
85,Grid frequency,Frequency,Hz
298,Grid voltage,Line voltage,V
294,Hub temperature,Rotor hub temperature,degC
1618,Metal particle count,Metalscan particl. g.oil,
413,Motor current axis 1,Current axis 1 1s,A
414,Motor current axis 2,Current axis 2 1s,A
```

## Member listing (110 of 110)

| archive | member | kind | uncompressed (MB) | compressed (MB) |
| --- | --- | --- | --- | --- |
| Kelmarsh_SCADA_2016_3082.zip | Turbine_Data_Kelmarsh_1_2016-01-03_-_2017-01-01_228.csv | scada_10min | 90.96 | 16.5 |
| Kelmarsh_SCADA_2016_3082.zip | Status_Kelmarsh_1_2016-01-03_-_2017-01-01_228.csv | status_events | 0.257 | 0.024 |
| Kelmarsh_SCADA_2016_3082.zip | Turbine_Data_Kelmarsh_2_2016-01-03_-_2017-01-01_229.csv | scada_10min | 90.97 | 16.42 |
| Kelmarsh_SCADA_2016_3082.zip | Status_Kelmarsh_2_2016-01-03_-_2017-01-01_229.csv | status_events | 0.219 | 0.02 |
| Kelmarsh_SCADA_2016_3082.zip | Turbine_Data_Kelmarsh_3_2016-01-03_-_2017-01-01_230.csv | scada_10min | 90.77 | 16.36 |
| Kelmarsh_SCADA_2016_3082.zip | Status_Kelmarsh_3_2016-01-03_-_2017-01-01_230.csv | status_events | 0.35 | 0.029 |
| Kelmarsh_SCADA_2016_3082.zip | Turbine_Data_Kelmarsh_4_2016-01-03_-_2017-01-01_231.csv | scada_10min | 90.63 | 16.32 |
| Kelmarsh_SCADA_2016_3082.zip | Status_Kelmarsh_4_2016-01-03_-_2017-01-01_231.csv | status_events | 0.234 | 0.021 |
| Kelmarsh_SCADA_2016_3082.zip | Turbine_Data_Kelmarsh_5_2016-01-03_-_2017-01-01_232.csv | scada_10min | 90.85 | 16.31 |
| Kelmarsh_SCADA_2016_3082.zip | Status_Kelmarsh_5_2016-01-03_-_2017-01-01_232.csv | status_events | 0.258 | 0.023 |
| Kelmarsh_SCADA_2016_3082.zip | Turbine_Data_Kelmarsh_6_2016-01-03_-_2017-01-01_233.csv | scada_10min | 90.26 | 15.86 |
| Kelmarsh_SCADA_2016_3082.zip | Status_Kelmarsh_6_2016-01-03_-_2017-01-01_233.csv | status_events | 0.388 | 0.031 |
| Kelmarsh_SCADA_2017_3083.zip | Turbine_Data_Kelmarsh_1_2017-01-01_-_2018-01-01_228.csv | scada_10min | 112.1 | 29.17 |
| Kelmarsh_SCADA_2017_3083.zip | Status_Kelmarsh_1_2017-01-01_-_2018-01-01_228.csv | status_events | 0.686 | 0.053 |
| Kelmarsh_SCADA_2017_3083.zip | Turbine_Data_Kelmarsh_2_2017-01-01_-_2018-01-01_229.csv | scada_10min | 112.4 | 29.18 |
| Kelmarsh_SCADA_2017_3083.zip | Status_Kelmarsh_2_2017-01-01_-_2018-01-01_229.csv | status_events | 0.593 | 0.046 |
| Kelmarsh_SCADA_2017_3083.zip | Turbine_Data_Kelmarsh_3_2017-01-01_-_2018-01-01_230.csv | scada_10min | 112.4 | 29.23 |
| Kelmarsh_SCADA_2017_3083.zip | Status_Kelmarsh_3_2017-01-01_-_2018-01-01_230.csv | status_events | 0.902 | 0.066 |
| Kelmarsh_SCADA_2017_3083.zip | Turbine_Data_Kelmarsh_4_2017-01-01_-_2018-01-01_231.csv | scada_10min | 112.4 | 28.95 |
| Kelmarsh_SCADA_2017_3083.zip | Status_Kelmarsh_4_2017-01-01_-_2018-01-01_231.csv | status_events | 0.607 | 0.047 |
| Kelmarsh_SCADA_2017_3083.zip | Turbine_Data_Kelmarsh_5_2017-01-01_-_2018-01-01_232.csv | scada_10min | 112.4 | 29 |
| Kelmarsh_SCADA_2017_3083.zip | Status_Kelmarsh_5_2017-01-01_-_2018-01-01_232.csv | status_events | 0.717 | 0.054 |
| Kelmarsh_SCADA_2017_3083.zip | Turbine_Data_Kelmarsh_6_2017-01-01_-_2018-01-01_233.csv | scada_10min | 111.9 | 28.72 |
| Kelmarsh_SCADA_2017_3083.zip | Status_Kelmarsh_6_2017-01-01_-_2018-01-01_233.csv | status_events | 1.071 | 0.079 |
| Kelmarsh_SCADA_2018_3084.zip | Turbine_Data_Kelmarsh_1_2018-01-01_-_2019-01-01_228.csv | scada_10min | 141.1 | 43.69 |
| Kelmarsh_SCADA_2018_3084.zip | Status_Kelmarsh_1_2018-01-01_-_2019-01-01_228.csv | status_events | 0.983 | 0.074 |
| Kelmarsh_SCADA_2018_3084.zip | Turbine_Data_Kelmarsh_2_2018-01-01_-_2019-01-01_229.csv | scada_10min | 141.5 | 43.66 |
| Kelmarsh_SCADA_2018_3084.zip | Status_Kelmarsh_2_2018-01-01_-_2019-01-01_229.csv | status_events | 0.87 | 0.066 |
| Kelmarsh_SCADA_2018_3084.zip | Turbine_Data_Kelmarsh_3_2018-01-01_-_2019-01-01_230.csv | scada_10min | 141.4 | 43.63 |
| Kelmarsh_SCADA_2018_3084.zip | Status_Kelmarsh_3_2018-01-01_-_2019-01-01_230.csv | status_events | 1.164 | 0.088 |
| Kelmarsh_SCADA_2018_3084.zip | Turbine_Data_Kelmarsh_4_2018-01-01_-_2019-01-01_231.csv | scada_10min | 141.4 | 43.37 |
| Kelmarsh_SCADA_2018_3084.zip | Status_Kelmarsh_4_2018-01-01_-_2019-01-01_231.csv | status_events | 0.915 | 0.069 |
| Kelmarsh_SCADA_2018_3084.zip | Turbine_Data_Kelmarsh_5_2018-01-01_-_2019-01-01_232.csv | scada_10min | 141.7 | 43.67 |
| Kelmarsh_SCADA_2018_3084.zip | Status_Kelmarsh_5_2018-01-01_-_2019-01-01_232.csv | status_events | 1.055 | 0.078 |
| Kelmarsh_SCADA_2018_3084.zip | Turbine_Data_Kelmarsh_6_2018-01-01_-_2019-01-01_233.csv | scada_10min | 141.4 | 43.65 |
| Kelmarsh_SCADA_2018_3084.zip | Status_Kelmarsh_6_2018-01-01_-_2019-01-01_233.csv | status_events | 1.473 | 0.107 |
| Kelmarsh_SCADA_2019_3085.zip | Turbine_Data_Kelmarsh_1_2019-01-01_-_2020-01-01_228.csv | scada_10min | 147.3 | 50.55 |
| Kelmarsh_SCADA_2019_3085.zip | Status_Kelmarsh_1_2019-01-01_-_2020-01-01_228.csv | status_events | 0.73 | 0.056 |
| Kelmarsh_SCADA_2019_3085.zip | Turbine_Data_Kelmarsh_2_2019-01-01_-_2020-01-01_229.csv | scada_10min | 150.5 | 52.06 |
| Kelmarsh_SCADA_2019_3085.zip | Status_Kelmarsh_2_2019-01-01_-_2020-01-01_229.csv | status_events | 0.72 | 0.055 |
| Kelmarsh_SCADA_2019_3085.zip | Turbine_Data_Kelmarsh_3_2019-01-01_-_2020-01-01_230.csv | scada_10min | 150.2 | 52.26 |
| Kelmarsh_SCADA_2019_3085.zip | Status_Kelmarsh_3_2019-01-01_-_2020-01-01_230.csv | status_events | 1.097 | 0.08 |
| Kelmarsh_SCADA_2019_3085.zip | Turbine_Data_Kelmarsh_4_2019-01-01_-_2020-01-01_231.csv | scada_10min | 150.1 | 51.8 |
| Kelmarsh_SCADA_2019_3085.zip | Status_Kelmarsh_4_2019-01-01_-_2020-01-01_231.csv | status_events | 0.814 | 0.061 |
| Kelmarsh_SCADA_2019_3085.zip | Turbine_Data_Kelmarsh_5_2019-01-01_-_2020-01-01_232.csv | scada_10min | 150.6 | 51.98 |
| Kelmarsh_SCADA_2019_3085.zip | Status_Kelmarsh_5_2019-01-01_-_2020-01-01_232.csv | status_events | 0.844 | 0.062 |
| Kelmarsh_SCADA_2019_3085.zip | Turbine_Data_Kelmarsh_6_2019-01-01_-_2020-01-01_233.csv | scada_10min | 150.6 | 52.22 |
| Kelmarsh_SCADA_2019_3085.zip | Status_Kelmarsh_6_2019-01-01_-_2020-01-01_233.csv | status_events | 1.272 | 0.091 |
| Kelmarsh_SCADA_2020_3086.zip | Turbine_Data_Kelmarsh_1_2020-01-01_-_2021-01-01_228.csv | scada_10min | 204.1 | 79.08 |
| Kelmarsh_SCADA_2020_3086.zip | Status_Kelmarsh_1_2020-01-01_-_2021-01-01_228.csv | status_events | 0.805 | 0.061 |
| Kelmarsh_SCADA_2020_3086.zip | Turbine_Data_Kelmarsh_2_2020-01-01_-_2021-01-01_229.csv | scada_10min | 205.3 | 79.31 |
| Kelmarsh_SCADA_2020_3086.zip | Status_Kelmarsh_2_2020-01-01_-_2021-01-01_229.csv | status_events | 0.696 | 0.054 |
| Kelmarsh_SCADA_2020_3086.zip | Turbine_Data_Kelmarsh_3_2020-01-01_-_2021-01-01_230.csv | scada_10min | 204.9 | 78.85 |
| Kelmarsh_SCADA_2020_3086.zip | Status_Kelmarsh_3_2020-01-01_-_2021-01-01_230.csv | status_events | 1.032 | 0.077 |
| Kelmarsh_SCADA_2020_3086.zip | Turbine_Data_Kelmarsh_4_2020-01-01_-_2021-01-01_231.csv | scada_10min | 204.9 | 78.22 |
| Kelmarsh_SCADA_2020_3086.zip | Status_Kelmarsh_4_2020-01-01_-_2021-01-01_231.csv | status_events | 0.793 | 0.061 |
| Kelmarsh_SCADA_2020_3086.zip | Turbine_Data_Kelmarsh_5_2020-01-01_-_2021-01-01_232.csv | scada_10min | 205.2 | 78.7 |
| Kelmarsh_SCADA_2020_3086.zip | Status_Kelmarsh_5_2020-01-01_-_2021-01-01_232.csv | status_events | 0.866 | 0.065 |
| Kelmarsh_SCADA_2020_3086.zip | Turbine_Data_Kelmarsh_6_2020-01-01_-_2021-01-01_233.csv | scada_10min | 205.5 | 79.11 |
| Kelmarsh_SCADA_2020_3086.zip | Status_Kelmarsh_6_2020-01-01_-_2021-01-01_233.csv | status_events | 1.119 | 0.083 |
| Kelmarsh_SCADA_2021_4456.zip | Turbine_Data_Kelmarsh_1_2021-01-01_-_2022-01-01_228.csv | scada_10min | 206.8 | 78.5 |
| Kelmarsh_SCADA_2021_4456.zip | Status_Kelmarsh_1_2021-01-01_-_2022-01-01_228.csv | status_events | 0.956 | 0.071 |
| Kelmarsh_SCADA_2021_4456.zip | Turbine_Data_Kelmarsh_2_2021-01-01_-_2022-01-01_229.csv | scada_10min | 207.7 | 78.72 |
| Kelmarsh_SCADA_2021_4456.zip | Status_Kelmarsh_2_2021-01-01_-_2022-01-01_229.csv | status_events | 0.74 | 0.056 |
| Kelmarsh_SCADA_2021_4456.zip | Turbine_Data_Kelmarsh_3_2021-01-01_-_2022-01-01_230.csv | scada_10min | 206.7 | 78.18 |
| Kelmarsh_SCADA_2021_4456.zip | Status_Kelmarsh_3_2021-01-01_-_2022-01-01_230.csv | status_events | 1.176 | 0.086 |
| Kelmarsh_SCADA_2021_4456.zip | Turbine_Data_Kelmarsh_4_2021-01-01_-_2022-01-01_231.csv | scada_10min | 207.2 | 77.86 |
| Kelmarsh_SCADA_2021_4456.zip | Status_Kelmarsh_4_2021-01-01_-_2022-01-01_231.csv | status_events | 0.988 | 0.073 |
| Kelmarsh_SCADA_2021_4456.zip | Turbine_Data_Kelmarsh_5_2021-01-01_-_2022-01-01_232.csv | scada_10min | 205.8 | 76.38 |
| Kelmarsh_SCADA_2021_4456.zip | Status_Kelmarsh_5_2021-01-01_-_2022-01-01_232.csv | status_events | 1.052 | 0.079 |
| Kelmarsh_SCADA_2021_4456.zip | Turbine_Data_Kelmarsh_6_2021-01-01_-_2022-01-01_233.csv | scada_10min | 207.4 | 77.35 |
| Kelmarsh_SCADA_2021_4456.zip | Status_Kelmarsh_6_2021-01-01_-_2022-01-01_233.csv | status_events | 1.345 | 0.099 |
| Kelmarsh_SCADA_2022_4457.zip | Turbine_Data_Kelmarsh_1_2022-01-01_-_2023-01-01_228.csv | scada_10min | 210.2 | 81.02 |
| Kelmarsh_SCADA_2022_4457.zip | Status_Kelmarsh_1_2022-01-01_-_2023-01-01_228.csv | status_events | 1.079 | 0.082 |
| Kelmarsh_SCADA_2022_4457.zip | Turbine_Data_Kelmarsh_2_2022-01-01_-_2023-01-01_229.csv | scada_10min | 212.1 | 81.5 |
| Kelmarsh_SCADA_2022_4457.zip | Status_Kelmarsh_2_2022-01-01_-_2023-01-01_229.csv | status_events | 1.016 | 0.076 |
| Kelmarsh_SCADA_2022_4457.zip | Turbine_Data_Kelmarsh_3_2022-01-01_-_2023-01-01_230.csv | scada_10min | 211.7 | 81.73 |
| Kelmarsh_SCADA_2022_4457.zip | Status_Kelmarsh_3_2022-01-01_-_2023-01-01_230.csv | status_events | 1.3 | 0.093 |
| Kelmarsh_SCADA_2022_4457.zip | Turbine_Data_Kelmarsh_4_2022-01-01_-_2023-01-01_231.csv | scada_10min | 210.5 | 78.97 |
| Kelmarsh_SCADA_2022_4457.zip | Status_Kelmarsh_4_2022-01-01_-_2023-01-01_231.csv | status_events | 0.907 | 0.068 |
| Kelmarsh_SCADA_2022_4457.zip | Turbine_Data_Kelmarsh_5_2022-01-01_-_2023-01-01_232.csv | scada_10min | 212 | 81.11 |
| Kelmarsh_SCADA_2022_4457.zip | Status_Kelmarsh_5_2022-01-01_-_2023-01-01_232.csv | status_events | 1.065 | 0.079 |
| Kelmarsh_SCADA_2022_4457.zip | Turbine_Data_Kelmarsh_6_2022-01-01_-_2023-01-01_233.csv | scada_10min | 211.8 | 80.8 |
| Kelmarsh_SCADA_2022_4457.zip | Status_Kelmarsh_6_2022-01-01_-_2023-01-01_233.csv | status_events | 1.266 | 0.094 |
| Kelmarsh_SCADA_2023_5961.zip | Turbine_Data_Kelmarsh_1_2023-01-01_-_2024-01-01_228.csv | scada_10min | 2,895 | 117.5 |
| Kelmarsh_SCADA_2023_5961.zip | Status_Kelmarsh_1_2023-01-01_-_2024-01-01_228.csv | status_events | 0.758 | 0.058 |
| Kelmarsh_SCADA_2023_5961.zip | Turbine_Data_Kelmarsh_2_2023-01-01_-_2024-01-01_229.csv | scada_10min | 2,895 | 117.7 |
| Kelmarsh_SCADA_2023_5961.zip | Status_Kelmarsh_2_2023-01-01_-_2024-01-01_229.csv | status_events | 0.73 | 0.058 |
| Kelmarsh_SCADA_2023_5961.zip | Turbine_Data_Kelmarsh_3_2023-01-01_-_2024-01-01_230.csv | scada_10min | 2,895 | 117.6 |
| Kelmarsh_SCADA_2023_5961.zip | Status_Kelmarsh_3_2023-01-01_-_2024-01-01_230.csv | status_events | 0.998 | 0.073 |
| Kelmarsh_SCADA_2023_5961.zip | Turbine_Data_Kelmarsh_4_2023-01-01_-_2024-01-01_231.csv | scada_10min | 2,941 | 125.5 |
| Kelmarsh_SCADA_2023_5961.zip | Status_Kelmarsh_4_2023-01-01_-_2024-01-01_231.csv | status_events | 0.984 | 0.073 |
| Kelmarsh_SCADA_2023_5961.zip | Turbine_Data_Kelmarsh_5_2023-01-01_-_2024-01-01_232.csv | scada_10min | 2,913 | 119.7 |
| Kelmarsh_SCADA_2023_5961.zip | Status_Kelmarsh_5_2023-01-01_-_2024-01-01_232.csv | status_events | 1.013 | 0.079 |
| Kelmarsh_SCADA_2023_5961.zip | Turbine_Data_Kelmarsh_6_2023-01-01_-_2024-01-01_233.csv | scada_10min | 2,896 | 117.6 |
| Kelmarsh_SCADA_2023_5961.zip | Status_Kelmarsh_6_2023-01-01_-_2024-01-01_233.csv | status_events | 1.157 | 0.087 |
| Kelmarsh_SCADA_2024_5962.zip | Turbine_Data_Kelmarsh_1_2024-01-01_-_2025-01-01_228.csv | scada_10min | 2,899 | 118.4 |
| Kelmarsh_SCADA_2024_5962.zip | Status_Kelmarsh_1_2024-01-01_-_2025-01-01_228.csv | status_events | 0.898 | 0.068 |
| Kelmarsh_SCADA_2024_5962.zip | Turbine_Data_Kelmarsh_2_2024-01-01_-_2025-01-01_229.csv | scada_10min | 2,895 | 117.4 |
| Kelmarsh_SCADA_2024_5962.zip | Status_Kelmarsh_2_2024-01-01_-_2025-01-01_229.csv | status_events | 0.831 | 0.063 |
| Kelmarsh_SCADA_2024_5962.zip | Turbine_Data_Kelmarsh_3_2024-01-01_-_2025-01-01_230.csv | scada_10min | 2,896 | 117.4 |
| Kelmarsh_SCADA_2024_5962.zip | Status_Kelmarsh_3_2024-01-01_-_2025-01-01_230.csv | status_events | 1.209 | 0.087 |
| Kelmarsh_SCADA_2024_5962.zip | Turbine_Data_Kelmarsh_4_2024-01-01_-_2025-01-01_231.csv | scada_10min | 2,894 | 114.6 |
| Kelmarsh_SCADA_2024_5962.zip | Status_Kelmarsh_4_2024-01-01_-_2025-01-01_231.csv | status_events | 0.795 | 0.062 |
| Kelmarsh_SCADA_2024_5962.zip | Turbine_Data_Kelmarsh_5_2024-01-01_-_2025-01-01_232.csv | scada_10min | 2,904 | 119.7 |
| Kelmarsh_SCADA_2024_5962.zip | Status_Kelmarsh_5_2024-01-01_-_2025-01-01_232.csv | status_events | 0.92 | 0.069 |
| Kelmarsh_SCADA_2024_5962.zip | Turbine_Data_Kelmarsh_6_2024-01-01_-_2025-01-01_233.csv | scada_10min | 2,901 | 116.8 |
| Kelmarsh_SCADA_2024_5962.zip | Status_Kelmarsh_6_2024-01-01_-_2025-01-01_233.csv | status_events | 1.15 | 0.087 |
| Kelmarsh_WT_dataSignalMapping.csv | (loose file) | metadata | 0.003 | 0.003 |
| Kelmarsh_WT_static.csv | (loose file) | metadata | 0.001 | 0.001 |
