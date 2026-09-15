# Text pipeline - deduplication

| field | value |
| --- | --- |
| run_id | 20260915-211138_all_text_3a504b27 |
| stage | dedup |
| config | configs/data/text_v2.yaml |
| config_hash | 3a504b27 |
| git_sha | dfbd7023363b79a871e5feea6746d476a3150cf8 |
| created_at (UTC) | 2026-09-15T21:11:38+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| dedup | 43,137 | 32,800 | 10,337 | 76.04% |

## Settings

| field | value |
| --- | --- |
| strategy | exact |
| lowercase | yes |
| strip | yes |
| keyed | {'enabled': True, 'source': 'nrc_event_notifications'} |

## Duplicates

| field | value |
| --- | --- |
| exact duplicates removed | 5,816 |
| unique documents | 32,800 |
| duplicate rate | 0.1348 |

## Sampled duplicate documents

Random sample of documents removed as exact duplicates.

1. `AGREEMENT STATE REPORT - RADIOGRAPHY CAMERA SOURCE DISCONNECT \nThe following report was received from the State of Texas Radiation Branch via facsimile: \n"On October 17, 2012, the Agency [Texas Rad…`
2. `OHIO AGREEMENT STATE REPORT - DAMAGED MOISTURE DENSITY GAUGE \nThe following was received from the State of Ohio via e-mail: \n"Ohio Department of Health (ODH) was informed on 8/27/10 of an incident …`
3. `AGREEMENT STATE REPORT - SHUTTER MECHANISM MALFUNCTION\n The following was received from the Ohio Dept. of Health via e-mail:\n "During a routine inspection of a generally licensed device a broken sp…`
4. `AGREEMENT STATE REPORT- PHARMACEUTICAL DISTRIBUTION FAILED QUALITY CONTROL TESTING \nThe following information was received by email: \n"This First Notice constitutes EARLY notice of events of POSSIB…`
5. `AGREEMENT STATE REPORT - MISSING GAUGE WITH 100 MILLICURIE CO-60 SOURCE \nThe following report was received from the Tennessee Department of Environment and Conservation Division of Radiological Heal…`

## Source-aware (keyed) deduplication

| field | value |
| --- | --- |
| applies to source | nrc_event_notifications |
| distinct keys seen | 21,882 |
| keys with >1 surviving revision | 3,901 |
| documents superseded (kept latest only) | 4,521 |
