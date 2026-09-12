# Text pipeline - PII scrubbing

| field | value |
| --- | --- |
| run_id | 20260912-220451_all_text_3b08fa30 |
| stage | pii |
| config | configs/data/text_codebook_v1.yaml |
| config_hash | 3b08fa30 |
| git_sha | dca971c12db9d69a22a19742e790a4e252a2bb63 |
| created_at (UTC) | 2026-09-12T22:04:51+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| pii | 264 | 264 | 0 | 100.00% |

## Policy (ADR-0005)

| field | value |
| --- | --- |
| mask_emails | yes |
| mask_phones | yes |
| mask_digits | no |
| phone_pattern | v1 |
| email_placeholder | <EMAIL> |
| phone_placeholder | <PHONE> |
| number_placeholder | <NUMBER> |

## Replacements

| class | replacements | documents touched |
| --- | --- | --- |
| email | 0 | 0 |
| phone | 0 | 0 |
| digits | 0 | 0 |

## Sampled scrubbed documents

_(no samples collected)_
