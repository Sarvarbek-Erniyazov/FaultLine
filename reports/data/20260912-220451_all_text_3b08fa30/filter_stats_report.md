# Text pipeline - quality filtering

| field | value |
| --- | --- |
| run_id | 20260912-220451_all_text_3b08fa30 |
| stage | filter |
| config | configs/data/text_codebook_v1.yaml |
| config_hash | 3b08fa30 |
| git_sha | dca971c12db9d69a22a19742e790a4e252a2bb63 |
| created_at (UTC) | 2026-09-12T22:04:51+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| filter | 264 | 264 | 0 | 100.00% |

## Thresholds applied

| field | value |
| --- | --- |
| min_chars | 5 |
| max_chars | 100,000 |
| min_alpha_ratio | 0.3 |
| max_repeated_line_ratio | 0.3 |

## Drop reasons (first failing rule)

_(no rows)_

## Document length, kept documents (characters)

| length statistic | value |
| --- | --- |
| count | 264 |
| mean | 22.69 |
| std | 6.609 |
| min | 6 |
| p1 | 9 |
| p5 | 12 |
| p25 | 18 |
| p50 | 23 |
| p75 | 27 |
| p95 | 32.85 |
| p99 | 38.37 |
| max | 41 |

## Alphabetic ratio, kept documents

| alphabetic ratio statistic | value |
| --- | --- |
| count | 264 |
| mean | 0.843 |
| std | 0.08155 |
| min | 0.4286 |
| p1 | 0.6316 |
| p5 | 0.704 |
| p25 | 0.8 |
| p50 | 0.8636 |
| p75 | 0.9062 |
| p95 | 0.9333 |
| p99 | 0.9553 |
| max | 1 |

## Repeated-line ratio, kept documents

| repeated-line ratio statistic | value |
| --- | --- |
| count | 264 |
| mean | 0 |
| std | 0 |
| min | 0 |
| p1 | 0 |
| p5 | 0 |
| p25 | 0 |
| p50 | 0 |
| p75 | 0 |
| p95 | 0 |
| p99 | 0 |
| max | 0 |

## Sampled removed documents

_(no samples collected)_
