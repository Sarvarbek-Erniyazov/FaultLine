# Text pipeline - quality filtering

| field | value |
| --- | --- |
| run_id | 20260908-221358_all_text_34e5612d |
| stage | filter |
| config | configs/data/text_v0.yaml |
| config_hash | 34e5612d |
| git_sha | 5dc15b28c9a9dc00209244792e864398e9bb1fd8 |
| created_at (UTC) | 2026-09-08T22:13:58+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| filter | 54 | 43 | 11 | 79.63% |

## Thresholds applied

| field | value |
| --- | --- |
| min_chars | 200 |
| max_chars | 100,000 |
| min_alpha_ratio | 0.3 |
| max_repeated_line_ratio | 0.3 |

## Drop reasons (first failing rule)

| rule | dropped | share of input |
| --- | --- | --- |
| min_chars | 5 | 9.259% |
| alpha_ratio | 3 | 5.556% |
| repeated_lines | 3 | 5.556% |

## Document length, kept documents (characters)

| length statistic | value |
| --- | --- |
| count | 43 |
| mean | 648.3 |
| std | 150.3 |
| min | 397 |
| p1 | 409.6 |
| p5 | 432.4 |
| p25 | 512 |
| p50 | 625 |
| p75 | 756.5 |
| p95 | 892.5 |
| p99 | 956.1 |
| max | 991 |

## Alphabetic ratio, kept documents

| alphabetic ratio statistic | value |
| --- | --- |
| count | 43 |
| mean | 0.7752 |
| std | 0.005383 |
| min | 0.7567 |
| p1 | 0.7601 |
| p5 | 0.767 |
| p25 | 0.7724 |
| p50 | 0.7755 |
| p75 | 0.778 |
| p95 | 0.7848 |
| p99 | 0.7856 |
| max | 0.7856 |

## Repeated-line ratio, kept documents

| repeated-line ratio statistic | value |
| --- | --- |
| count | 43 |
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

Random sample of documents the filters dropped, truncated to 200 characters. Read these before trusting the thresholds.

1. `[min_chars] Short note 0: the unit restarted without incident.`
2. `[min_chars] Short note 3: the unit restarted without incident.`
3. `[min_chars] Short note 1: the unit restarted without incident.`
4. `[alpha_ratio] 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3…`
5. `[alpha_ratio] === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === === =…`
