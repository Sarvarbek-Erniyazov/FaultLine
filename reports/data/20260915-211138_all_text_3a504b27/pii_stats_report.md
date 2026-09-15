# Text pipeline - PII scrubbing

| field | value |
| --- | --- |
| run_id | 20260915-211138_all_text_3a504b27 |
| stage | pii |
| config | configs/data/text_v2.yaml |
| config_hash | 3a504b27 |
| git_sha | dfbd7023363b79a871e5feea6746d476a3150cf8 |
| created_at (UTC) | 2026-09-15T21:11:38+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| pii | 32,800 | 32,800 | 0 | 100.00% |

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
| email | 344 | 231 |
| phone | 1,554 | 993 |
| digits | 0 | 0 |

## Sampled scrubbed documents

Random sample of documents in which at least one replacement was made.

1. `PART 21 - MATERIAL DEGRADATION INTERIM REPORT\nThe following summary was provided by the licensee via email:\nEmerson/Fisher Controls International LLC identified a potential deviation on February 17…`
2. `The NRC is modernizing nrc.gov with an updated design and improved navigation to enhance usability. We are committed to a smooth transition and will work to minimize any disruption. The site may be b…`
3. `The NRC is modernizing nrc.gov with an updated design and improved navigation to enhance usability. We are committed to a smooth transition and will work to minimize any disruption. The site may be b…`
4. `The NRC is modernizing nrc.gov with an updated design and improved navigation to enhance usability. We are committed to a smooth transition and will work to minimize any disruption. The site may be b…`
5. `The NRC is modernizing nrc.gov with an updated design and improved navigation to enhance usability. We are committed to a smooth transition and will work to minimize any disruption. The site may be b…`
