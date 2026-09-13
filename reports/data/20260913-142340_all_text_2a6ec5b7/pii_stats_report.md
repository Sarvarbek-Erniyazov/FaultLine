# Text pipeline - PII scrubbing

| field | value |
| --- | --- |
| run_id | 20260913-142340_all_text_2a6ec5b7 |
| stage | pii |
| config | configs/data/text_v1.yaml |
| config_hash | 2a6ec5b7 |
| git_sha | 5d12196868ff0f6fc13360cca4ce807da5934672 |
| created_at (UTC) | 2026-09-13T14:23:40+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| pii | 23,141 | 23,141 | 0 | 100.00% |

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
| email | 332 | 224 |
| phone | 1,490 | 944 |
| digits | 0 | 0 |

## Sampled scrubbed documents

Random sample of documents in which at least one replacement was made.

1. `The NRC is modernizing nrc.gov with an updated design and improved navigation to enhance usability. We are committed to a smooth transition and will work to minimize any disruption. The site may be b…`
2. `The NRC is modernizing nrc.gov with an updated design and improved navigation to enhance usability. We are committed to a smooth transition and will work to minimize any disruption. The site may be b…`
3. `The NRC is modernizing nrc.gov with an updated design and improved navigation to enhance usability. We are committed to a smooth transition and will work to minimize any disruption. The site may be b…`
4. `The NRC is modernizing nrc.gov with an updated design and improved navigation to enhance usability. We are committed to a smooth transition and will work to minimize any disruption. The site may be b…`
5. `The NRC is modernizing nrc.gov with an updated design and improved navigation to enhance usability. We are committed to a smooth transition and will work to minimize any disruption. The site may be b…`
