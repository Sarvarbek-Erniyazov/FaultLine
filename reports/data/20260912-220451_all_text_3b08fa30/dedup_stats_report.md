# Text pipeline - deduplication

| field | value |
| --- | --- |
| run_id | 20260912-220451_all_text_3b08fa30 |
| stage | dedup |
| config | configs/data/text_codebook_v1.yaml |
| config_hash | 3b08fa30 |
| git_sha | dca971c12db9d69a22a19742e790a4e252a2bb63 |
| created_at (UTC) | 2026-09-12T22:04:51+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| dedup | 264 | 264 | 0 | 100.00% |

## Settings

| field | value |
| --- | --- |
| strategy | exact |
| lowercase | yes |
| strip | yes |

## Duplicates

| field | value |
| --- | --- |
| exact duplicates removed | 0 |
| unique documents | 264 |
| duplicate rate | 0 |

## Sampled duplicate documents

_(no samples collected)_
