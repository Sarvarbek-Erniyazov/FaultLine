# Text pipeline - PII scrubbing

| field | value |
| --- | --- |
| run_id | 20260908-221358_all_text_34e5612d |
| stage | pii |
| config | configs/data/text_v0.yaml |
| config_hash | 34e5612d |
| git_sha | 5dc15b28c9a9dc00209244792e864398e9bb1fd8 |
| created_at (UTC) | 2026-09-08T22:13:58+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| pii | 38 | 38 | 0 | 100.00% |

## Policy (ADR-0005)

| field | value |
| --- | --- |
| mask_emails | yes |
| mask_phones | yes |
| mask_digits | no |
| email_placeholder | <EMAIL> |
| phone_placeholder | <PHONE> |
| number_placeholder | <NUMBER> |

## Replacements

| class | replacements | documents touched |
| --- | --- | --- |
| email | 3 | 3 |
| phone | 3 | 3 |
| digits | 0 | 0 |

## Sampled scrubbed documents

Random sample of documents in which at least one replacement was made.

1. `The site engineer logged the event and forwarded the record to <EMAIL> for review. A follow-up call was placed to <PHONE> the same evening. Recorded output at the moment of the trip was 1850 kW again…`
2. `Contact the control room at <PHONE> or <EMAIL> before isolating the circuit. The measured winding temperature was 148 degrees Celsius against a trip threshold of 155. Cumulative energy since commissi…`
3. `Queries to <EMAIL>. Serial number <PHONE> was recorded on the replacement bearing. At 10:14 the anemometer oil particle count increased on unit 1. A technician attended the site the following morning…`
