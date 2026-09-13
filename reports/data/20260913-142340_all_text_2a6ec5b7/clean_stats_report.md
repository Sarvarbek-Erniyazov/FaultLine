# Text pipeline - cleaning

| field | value |
| --- | --- |
| run_id | 20260913-142340_all_text_2a6ec5b7 |
| stage | clean |
| config | configs/data/text_v1.yaml |
| config_hash | 2a6ec5b7 |
| git_sha | 5d12196868ff0f6fc13360cca4ce807da5934672 |
| created_at (UTC) | 2026-09-13T14:23:40+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| clean | 33,725 | 33,725 | 0 | 100.00% |

## Drop reasons

| rule | dropped | share of input |
| --- | --- | --- |
| empty_after_cleaning | 0 | 0.000% |

## Characters

| field | value |
| --- | --- |
| characters in | 60,297,874 |
| characters out | 57,605,616 |
| characters removed | 2,692,258 |

## Document length after cleaning (characters)

| length statistic | value |
| --- | --- |
| count | 33,725 |
| mean | 1,708 |
| std | 2,604 |
| min | 1 |
| p1 | 257 |
| p5 | 408 |
| p25 | 818 |
| p50 | 1,207 |
| p75 | 1,828 |
| p95 | 4,192 |
| p99 | 9,835 |
| max | 1.268e+05 |

## Declared fixed-boilerplate rules (Gate-6 correction)

| rule | matches removed |
| --- | --- |
| en_revision_header | 1,316 |
| iaea_less_than_cat3 | 3,482 |

## Sampled documents (before -> after)

Random sample of cleaned documents, truncated to 200 characters.

1. `SUPPLEMENTAL COOLING INOPERABLE DURING MOVEMENT OF DRY CASK STORAGE HI-TRACK TRANSFER CASK \nThis 24  -> SUPPLEMENTAL COOLING INOPERABLE DURING MOVEMENT OF DRY CASK STORAGE HI-TRACK TRANSFER CASK \nT…`
2. `OFFSITE NOTIFICATION TO LOCAL LAW ENFORCEMENT DUE TO FIRE BRIGADE ACTIVATION \n"At 2018 hrs, the Cont -> OFFSITE NOTIFICATION TO LOCAL LAW ENFORCEMENT DUE TO FIRE BRIGADE ACTIVATION \n"At 2018 hrs, t…`
3. `UNUSUAL EVENT DECLARED DUE TO FIRE IN THE MAIN TRANSFORMER >15 MIN.\n\n Unusual event declared at 2025 -> UNUSUAL EVENT DECLARED DUE TO FIRE IN THE MAIN TRANSFORMER >15 MIN.\n\n Unusual event declare…`
4. `AGREEMENT STATE REPORT - PERSONNEL OVEREXPOSURE DURING RADIOGRAPHY \nThe following report was receive -> AGREEMENT STATE REPORT - PERSONNEL OVEREXPOSURE DURING RADIOGRAPHY \nThe following report was …`
5. `PART 21 INTERIM EVALUATION OF A DEVIATION - CONTACTOR FAILURE \nThe following was received via FAX: \n -> PART 21 INTERIM EVALUATION OF A DEVIATION - CONTACTOR FAILURE \nThe following was received vi…`
