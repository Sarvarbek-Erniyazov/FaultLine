# Text pipeline - cleaning

| field | value |
| --- | --- |
| run_id | 20260908-221358_all_text_34e5612d |
| stage | clean |
| config | configs/data/text_v0.yaml |
| config_hash | 34e5612d |
| git_sha | 5dc15b28c9a9dc00209244792e864398e9bb1fd8 |
| created_at (UTC) | 2026-09-08T22:13:58+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| clean | 55 | 54 | 1 | 98.18% |

## Drop reasons

| rule | dropped | share of input |
| --- | --- | --- |
| empty_after_cleaning | 1 | 1.818% |

## Characters

| field | value |
| --- | --- |
| characters in | 32,941 |
| characters out | 32,844 |
| characters removed | 97 |

## Document length after cleaning (characters)

| length statistic | value |
| --- | --- |
| count | 54 |
| mean | 608.2 |
| std | 244.5 |
| min | 50 |
| p1 | 50 |
| p5 | 50 |
| p25 | 454 |
| p50 | 617.5 |
| p75 | 758.8 |
| p95 | 979.3 |
| p99 | 1,052 |
| max | 1,090 |

## Sampled documents (before -> after)

Random sample of cleaned documents, truncated to 200 characters.

1. `At 19:46 the main bearing vibration exceeded the alarm level on unit 7. Operations continued at redu -> At 19:46 the main bearing vibration exceeded the alarm level on unit 7. Operations continued at…`
2. `At 05:25 the main bearing the unit tripped and reset automatically on unit 2. The unit was stopped f -> At 05:25 the main bearing the unit tripped and reset automatically on unit 2. The unit was stop…`
3. `At 02:10 the transformer temperature rose steadily on unit 16. The unit was stopped for inspection.  -> At 02:10 the transformer temperature rose steadily on unit 16. The unit was stopped for inspect…`
4. `[732, 372, 159, 434, 891, 851, 185, 564, 247, 451, 508, 309, 740, 282, 89, 830, 488, 542, 975, 808,  -> [732, 372, 159, 434, 891, 851, 185, 564, 247, 451, 508, 309, 740, 282, 89, 830, 488, 542, 975, …`
5. `At 06:37 the converter temperature rose steadily on unit 13. A replacement part was ordered. The cau -> At 06:37 the converter temperature rose steadily on unit 13. A replacement part was ordered. Th…`
