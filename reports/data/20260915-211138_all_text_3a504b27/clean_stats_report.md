# Text pipeline - cleaning

| field | value |
| --- | --- |
| run_id | 20260915-211138_all_text_3a504b27 |
| stage | clean |
| config | configs/data/text_v2.yaml |
| config_hash | 3a504b27 |
| git_sha | dfbd7023363b79a871e5feea6746d476a3150cf8 |
| created_at (UTC) | 2026-09-15T21:11:38+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| clean | 43,758 | 43,758 | 0 | 100.00% |

## Drop reasons

| rule | dropped | share of input |
| --- | --- | --- |
| empty_after_cleaning | 0 | 0.000% |

## Characters

| field | value |
| --- | --- |
| characters in | 70,592,316 |
| characters out | 67,804,795 |
| characters removed | 2,787,521 |

## Document length after cleaning (characters)

| length statistic | value |
| --- | --- |
| count | 43,758 |
| mean | 1,550 |
| std | 2,330 |
| min | 1 |
| p1 | 197 |
| p5 | 340 |
| p25 | 735 |
| p50 | 1,121 |
| p75 | 1,715 |
| p95 | 3,755 |
| p99 | 8,708 |
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
3. `ON 2/4/2019, AT APPROXIMATELY 1500 HOURS, A LOCAL OPERATIONS EMPLOYEE WAS PERFORMING ROUTINE MAINTEN -> ON 2/4/2019, AT APPROXIMATELY 1500 HOURS, A LOCAL OPERATIONS EMPLOYEE WAS PERFORMING ROUTINE MA…`
4. `AGREEMENT STATE REPORT - PERSONNEL OVEREXPOSURE DURING RADIOGRAPHY \nThe following report was receive -> AGREEMENT STATE REPORT - PERSONNEL OVEREXPOSURE DURING RADIOGRAPHY \nThe following report was …`
5. `PART 21 INTERIM EVALUATION OF A DEVIATION - CONTACTOR FAILURE \nThe following was received via FAX: \n -> PART 21 INTERIM EVALUATION OF A DEVIATION - CONTACTOR FAILURE \nThe following was received vi…`
