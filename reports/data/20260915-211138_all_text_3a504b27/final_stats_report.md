# Text pipeline - final corpus

| field | value |
| --- | --- |
| run_id | 20260915-211138_all_text_3a504b27 |
| stage | final |
| config | configs/data/text_v2.yaml |
| config_hash | 3a504b27 |
| git_sha | dfbd7023363b79a871e5feea6746d476a3150cf8 |
| created_at (UTC) | 2026-09-15T21:11:38+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| final | 32,800 | 32,800 | 0 | 100.00% |

## Split assignment

| split | documents | share | shards |
| --- | --- | --- | --- |
| test | 548 | 1.67% | 1 |
| train | 31,750 | 96.80% | 7 |
| val | 502 | 1.53% | 1 |

## Split assignment per source (documents / whitespace words)

| source | test | train | val |
| --- | --- | --- | --- |
| nrc_bulletins | 31 / 36,173 | 182 / 214,799 | 15 / 19,318 |
| nrc_event_notifications | 238 / 57,134 | 21,424 / 4,833,287 | 220 / 48,730 |
| nrc_gen_letters | 21 / 21,780 | 504 / 635,118 | 31 / 29,605 |
| nrc_info_notices | 37 / 34,933 | 348 / 330,197 | 37 / 34,751 |
| nrc_reg_issues | 14 / 25,100 | 25 / 35,193 | 14 / 31,244 |
| phmsa_incident_narratives | 207 / 34,866 | 9,267 / 1,591,940 | 185 / 33,640 |

## Document length, final corpus (characters)

| length statistic | value |
| --- | --- |
| count | 32,800 |
| mean | 1,556 |
| std | 2,263 |
| min | 200 |
| p1 | 247 |
| p5 | 349 |
| p25 | 717 |
| p50 | 1,107 |
| p75 | 1,719 |
| p95 | 3,834 |
| p99 | 8,801 |
| max | 9.492e+04 |

## Outputs

| file | documents |
| --- | --- |
| test-00000.jsonl | 548 |
| train-00000.jsonl | 5,000 |
| train-00001.jsonl | 5,000 |
| train-00002.jsonl | 5,000 |
| train-00003.jsonl | 5,000 |
| train-00004.jsonl | 5,000 |
| train-00005.jsonl | 5,000 |
| train-00006.jsonl | 1,750 |
| val-00000.jsonl | 502 |
