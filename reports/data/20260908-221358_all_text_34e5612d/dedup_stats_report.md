# Text pipeline - deduplication

| field | value |
| --- | --- |
| run_id | 20260908-221358_all_text_34e5612d |
| stage | dedup |
| config | configs/data/text_v0.yaml |
| config_hash | 34e5612d |
| git_sha | 5dc15b28c9a9dc00209244792e864398e9bb1fd8 |
| created_at (UTC) | 2026-09-08T22:13:58+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| dedup | 43 | 38 | 5 | 88.37% |

## Settings

| field | value |
| --- | --- |
| strategy | exact |
| lowercase | yes |
| strip | yes |

## Duplicates

| field | value |
| --- | --- |
| exact duplicates removed | 5 |
| unique documents | 38 |
| duplicate rate | 0.1163 |

## Sampled duplicate documents

Random sample of documents removed as exact duplicates.

1. `At 02:10 the transformer temperature rose steadily on unit 16. The unit was stopped for inspection. The cause remains under investigation. At 21:45 the gearbox vibration exceeded the alarm level on u…`
2. `AT 00:31 THE COOLING CIRCUIT THE UNIT TRIPPED AND RESET AUTOMATICALLY ON UNIT 8. A TECHNICIAN ATTENDED THE SITE THE FOLLOWING MORNING. THE ROOT CAUSE WAS TRACED TO A LOOSE CONNECTION. AT 15:56 THE TR…`
3. `At 00:02 the pitch system temperature rose steadily on unit 2. Operations continued at reduced power. The root cause was traced to a loose connection. At 16:30 the generator an intermittent fault was…`
4. `At 19:46 the main bearing vibration exceeded the alarm level on unit 7. Operations continued at reduced power. No secondary damage was found. At 12:31 the pitch system oil particle count increased on…`
5. `At 02:10 the transformer temperature rose steadily on unit 16. The unit was stopped for inspection. The cause remains under investigation. At 21:45 the gearbox vibration exceeded the alarm level on u…`
