# Raw inventory: care

| field | value |
| --- | --- |
| source | care |
| provider | Fraunhofer IEE |
| licence | CC-BY-SA-4.0 |
| zenodo record | 15,846,963 |
| concept DOI | 10.5281/zenodo.10958774 |
| staged directory | C:\Users\sharg\Desktop\github\FaultLine\data\raw\telemetry\care |
| files staged | 1 |
| members discovered | 103 |
| member classification | the file structure documented in the record README: Wind Farm <x>/event_info.csv, feature_description.csv and datasets/<event_id>.csv |
| event members parsed | 3 of 3 (caps: 200 members, 209.7 MB and 500,000 rows per member) |
| generated (UTC) | 2026-09-10T09:22:27+00:00 |
| git_sha | aac5d7110773da2a7337e045b61237a5001db107 |

## Free-text verdict

**VERIFIED short written descriptions** - a closed set of 35 strings written per event rather than drawn from a code book: 35 distinct strings over 45 rows with text, mean length 55.9 characters (8.4 words), 85.7% of the distinct strings occurring exactly once. Richer than a code book and far too little to be a corpus, so ADR-0001 is qualified rather than overturned

This is the evidence behind ADR-0001: whether the paired text in this record is open-ended language or a controlled vocabulary.

Thresholds applied: more than 500 distinct strings is open-ended text; within that, a set in which at least 50% of the distinct strings occur exactly once was written per event, otherwise it is a code book; written descriptions averaging at most 200 characters are short. The measurements are pooled over every parsed event table and listed in the next section.

## Text measurements (all parsed tables pooled)

| field | value |
| --- | --- |
| event tables parsed | 3 |
| rows | 95 |
| rows with a non-empty message | 45 (47.4%) |
| distinct messages | 35 |
| mean length (characters) | 55.9 |
| mean length (words) | 8.4 |
| distinct messages occurring exactly once | 85.7% |
| most distinct messages in one table | 26 |
| longest mean length in one table (characters) | 76.3 |

_Quoted messages are the provider's text under CC-BY-SA-4.0 (Gueck, Bruns, Dupont, CARE to Compare, Fraunhofer IEE, Zenodo, doi:10.5281/zenodo.10958774 (CC BY-SA 4.0)). They are quoted because the measurement needs them; this report otherwise reproduces none of the record: header samples are cut to their first line and per-table message listings are omitted._

**Top 20 messages** (share of rows with a message)

| message | count | share |
| --- | --- | --- |
| Hydraulic group | 6 | 13.33% |
| high temperature in transformer cell | 3 | 6.67% |
| 23020 : Axis 3 not ready-to-operate | 2 | 4.44% |
| Gearbox failure | 2 | 4.44% |
| Generator bearing failure | 2 | 4.44% |
| 10115 : Oil level error, two-pump mode + Oil Leakage Gear Oil Supply + 12019: Rotor brake B cannot be closed + P20_yaw … | 1 | 2.22% |
| 15004 : Safety chain relay open + 93005 : Gear oil cooler bypass valve | 1 | 2.22% |
| 21002 : Axis 1 DC-link voltage low, batt | 1 | 2.22% |
| COMMUNICATION FAULT BK1120 IN NC300 A2 | 1 | 2.22% |
| Communication and Pitchfailure - slip ring and Beckhoff card | 1 | 2.22% |
| Communication fault BK1120 in NC300 | 1 | 2.22% |
| Converter Failure from 17.11 12:30 - 18.11. 13:57, Fuse Filter Supply | 1 | 2.22% |
| Failure 2023-04-05 03:30 - defective coupling between gear oil pump and motor | 1 | 2.22% |
| Failure due to Rotorbrake and Hydraulic problemes - Hydraulic pump A disabeld, 2h later turbine back in production - An… | 1 | 2.22% |
| Gearbox bearings damaged | 1 | 2.22% |
| Harting plug Nacelle/HUB damaged + NCR20_HUB: Wiring blade control system | 1 | 2.22% |
| P20_Blade3_Grease Collector missing | 1 | 2.22% |
| P20_DGUV-v3 RCD 28F1 NC310 defective + 0 : P20_Blades_Cabinet Caps missing | 1 | 2.22% |
| P20_Grounding role brake disc + P20_cover-lightning-main-cabinet-hub | 1 | 2.22% |
| P20_spinner_carbonbrush defekt + P20_Accumulators_hydraulic system | 1 | 2.22% |

## Staged files

| file | size (MB) | members |
| --- | --- | --- |
| CARE_To_Compare.zip | 5,503 | 103 |

## Members by kind

| kind | members | uncompressed (MB) |
| --- | --- | --- |
| metadata | 5 | 0 |
| scada_10min | 95 | 1.999e+04 |
| status_events | 3 | 0 |

## Event tables found

| member | rows | columns | code column | message column | unique codes | unique messages | free-text share | mean chars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/event_info… | 22 | 8 | - | event_description | 0 | 5 | 54.5% | 17.8 |
| CARE_To_Compare.zip::CARE_To_Compare/Wind Farm B/event_info… | 15 | 8 | - | event_description | 0 | 4 | 40.0% | 40.5 |
| CARE_To_Compare.zip::CARE_To_Compare/Wind Farm C/event_info… | 58 | 8 | - | event_description | 0 | 26 | 46.6% | 76.3 |

_Per-table message listings are omitted for this share-alike record; the pooled top 20 above is the only text quoted._

## Header samples (first lines, one member per kind)

_Share-alike record: each sample is cut to its first line._

**CARE_To_Compare.zip::CARE_To_Compare/README.md**

```text
## Table of Contents
```

**CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/datasets/0.csv**

```text
time_stamp;asset_id;id;train_test;status_type_id;sensor_0_avg;sensor_1_avg;sensor_2_avg;wind_speed_3_avg;wind_speed_4_avg;wind_speed_3_max;wind_speed_3_min;wind_speed_3_std;sensor_5_avg;sensor_5_max;s
```

**CARE_To_Compare.zip::CARE_To_Compare/Wind Farm A/event_info.csv**

```text
asset;event_id;event_label;event_start;event_start_id;event_end;event_end_id;event_description
```

## Member listing (103 of 103)

| archive | member | kind | uncompressed (MB) | compressed (MB) |
| --- | --- | --- | --- | --- |
| CARE_To_Compare.zip | CARE_To_Compare/README.md | metadata | 0.005 | 0.002 |
| CARE_To_Compare.zip | CARE_To_Compare/README.txt | metadata | 0.005 | 0.002 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/0.csv | scada_10min | 36.89 | 7.227 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/10.csv | scada_10min | 35.83 | 7.044 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/13.csv | scada_10min | 36.22 | 7.033 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/14.csv | scada_10min | 36.61 | 7.303 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/17.csv | scada_10min | 36.85 | 7.25 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/22.csv | scada_10min | 35.47 | 6.878 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/24.csv | scada_10min | 36.98 | 7.278 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/25.csv | scada_10min | 36.62 | 7.211 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/26.csv | scada_10min | 36.07 | 7.047 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/3.csv | scada_10min | 37.09 | 7.289 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/38.csv | scada_10min | 37.28 | 7.472 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/40.csv | scada_10min | 37.31 | 7.298 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/42.csv | scada_10min | 35.94 | 7.059 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/45.csv | scada_10min | 36.48 | 7.301 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/51.csv | scada_10min | 36.5 | 7.096 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/68.csv | scada_10min | 36.38 | 7.168 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/69.csv | scada_10min | 36.69 | 7.223 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/71.csv | scada_10min | 36.55 | 7.188 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/72.csv | scada_10min | 36.25 | 7.046 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/73.csv | scada_10min | 36.31 | 7.14 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/84.csv | scada_10min | 36.48 | 7.306 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/datasets/92.csv | scada_10min | 36.07 | 7.098 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/event_info.csv | status_events | 0.002 | 0.001 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm A/feature_description.csv | metadata | 0.004 | 0.001 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/19.csv | scada_10min | 89.68 | 26.45 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/2.csv | scada_10min | 87.15 | 25.63 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/21.csv | scada_10min | 85.18 | 25.04 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/23.csv | scada_10min | 86.39 | 24.97 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/27.csv | scada_10min | 98.96 | 28.83 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/34.csv | scada_10min | 89.44 | 25.71 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/52.csv | scada_10min | 87.4 | 25.14 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/53.csv | scada_10min | 93.27 | 27.25 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/7.csv | scada_10min | 92.09 | 27.08 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/74.csv | scada_10min | 88.65 | 26.16 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/77.csv | scada_10min | 98.68 | 29.37 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/82.csv | scada_10min | 87.4 | 25.61 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/83.csv | scada_10min | 105 | 30.59 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/86.csv | scada_10min | 88.57 | 26.37 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/datasets/87.csv | scada_10min | 87.96 | 25.71 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/event_info.csv | status_events | 0.001 | 0 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm B/feature_description.csv | metadata | 0.005 | 0.001 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/1.csv | scada_10min | 299.8 | 83.8 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/11.csv | scada_10min | 314.7 | 85.64 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/12.csv | scada_10min | 314.8 | 88.5 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/15.csv | scada_10min | 301 | 81.33 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/16.csv | scada_10min | 298.8 | 82.81 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/18.csv | scada_10min | 294.7 | 81.44 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/20.csv | scada_10min | 302.7 | 84.67 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/28.csv | scada_10min | 310.6 | 87 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/29.csv | scada_10min | 303.1 | 80.62 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/30.csv | scada_10min | 311.7 | 84.22 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/31.csv | scada_10min | 305.9 | 84.6 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/32.csv | scada_10min | 309.5 | 87.51 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/33.csv | scada_10min | 313.2 | 86.26 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/35.csv | scada_10min | 294.3 | 82.16 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/36.csv | scada_10min | 310.2 | 87.01 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/37.csv | scada_10min | 300.4 | 81.02 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/39.csv | scada_10min | 298.5 | 82.88 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/4.csv | scada_10min | 315.2 | 87.22 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/41.csv | scada_10min | 309.2 | 83.88 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/43.csv | scada_10min | 306.5 | 85.35 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/44.csv | scada_10min | 354.1 | 99.23 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/46.csv | scada_10min | 311.1 | 88.94 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/47.csv | scada_10min | 301.9 | 84.33 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/48.csv | scada_10min | 310.1 | 85.45 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/49.csv | scada_10min | 294 | 79.31 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/5.csv | scada_10min | 295.1 | 80.63 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/50.csv | scada_10min | 306 | 83.71 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/54.csv | scada_10min | 308.7 | 86.5 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/55.csv | scada_10min | 312.7 | 87.84 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/56.csv | scada_10min | 298.4 | 82.8 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/57.csv | scada_10min | 309 | 86.59 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/58.csv | scada_10min | 306.3 | 87.19 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/59.csv | scada_10min | 306.8 | 83.59 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/6.csv | scada_10min | 305 | 84.04 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/60.csv | scada_10min | 301.8 | 81.1 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/61.csv | scada_10min | 312.6 | 87.71 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/62.csv | scada_10min | 298.9 | 83.5 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/63.csv | scada_10min | 307.2 | 85.22 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/64.csv | scada_10min | 307.4 | 87.27 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/65.csv | scada_10min | 311.9 | 85.31 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/66.csv | scada_10min | 295.8 | 79.99 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/67.csv | scada_10min | 344.8 | 95.42 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/70.csv | scada_10min | 316 | 88.23 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/75.csv | scada_10min | 316.5 | 89.47 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/76.csv | scada_10min | 290.3 | 80.32 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/78.csv | scada_10min | 297.3 | 82.74 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/79.csv | scada_10min | 299.9 | 85.02 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/8.csv | scada_10min | 307.8 | 87.05 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/80.csv | scada_10min | 309.6 | 86.54 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/81.csv | scada_10min | 299.8 | 82.52 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/85.csv | scada_10min | 291.9 | 81.81 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/88.csv | scada_10min | 310.9 | 88.42 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/89.csv | scada_10min | 305.6 | 84.77 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/9.csv | scada_10min | 314.3 | 89.38 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/90.csv | scada_10min | 307.3 | 84.98 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/91.csv | scada_10min | 318.3 | 89.83 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/93.csv | scada_10min | 313.3 | 86.44 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/datasets/94.csv | scada_10min | 305.7 | 84.46 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/event_info.csv | status_events | 0.006 | 0.002 |
| CARE_To_Compare.zip | CARE_To_Compare/Wind Farm C/feature_description.csv | metadata | 0.021 | 0.003 |
