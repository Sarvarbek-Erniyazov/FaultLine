# Text pipeline - quality filtering

| field | value |
| --- | --- |
| run_id | 20260913-142340_all_text_2a6ec5b7 |
| stage | filter |
| config | configs/data/text_v1.yaml |
| config_hash | 2a6ec5b7 |
| git_sha | 5d12196868ff0f6fc13360cca4ce807da5934672 |
| created_at (UTC) | 2026-09-13T14:23:40+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| filter | 33,725 | 33,472 | 253 | 99.25% |

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
| repeated_lines | 171 | 0.507% |
| min_chars | 79 | 0.234% |
| max_chars | 3 | 0.009% |

## Document length, kept documents (characters)

| length statistic | value |
| --- | --- |
| count | 33,472 |
| mean | 1,692 |
| std | 2,358 |
| min | 200 |
| p1 | 267 |
| p5 | 415 |
| p25 | 818 |
| p50 | 1,206 |
| p75 | 1,821 |
| p95 | 4,165 |
| p99 | 9,704 |
| max | 9.492e+04 |

## Alphabetic ratio, kept documents

| alphabetic ratio statistic | value |
| --- | --- |
| count | 33,472 |
| mean | 0.7773 |
| std | 0.02487 |
| min | 0.5409 |
| p1 | 0.7073 |
| p5 | 0.7344 |
| p25 | 0.7634 |
| p50 | 0.7791 |
| p75 | 0.7934 |
| p95 | 0.8145 |
| p99 | 0.8317 |
| max | 0.8617 |

## Repeated-line ratio, kept documents

| repeated-line ratio statistic | value |
| --- | --- |
| count | 33,472 |
| mean | 0.009355 |
| std | 0.03815 |
| min | 0 |
| p1 | 0 |
| p5 | 0 |
| p25 | 0 |
| p50 | 0 |
| p75 | 0 |
| p95 | 0.07407 |
| p99 | 0.2222 |
| max | 0.3 |

## Sampled removed documents

Random sample of documents the filters dropped, truncated to 200 characters. Read these before trusting the thresholds.

1. `[repeated_lines] AGREEMENT STATE REPORT - LOST MATERIAL IN TRANSIT\n The following is summarized from an e-mail received from the Commonwealth of Massachusetts:\n The licensee reported on 4/6/20 that…`
2. `[repeated_lines] * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *\n THIS IS NOT A NEW REPORT.\n …`
3. `[repeated_lines] TECHNICAL SPECIFICATION REPORTABLE OCCURRENCE\nThe following information was provided by the licensee via phone and email:\n"In accordance with Technical Specification (TS) 6.7.2.1, …`
4. `[repeated_lines] AGREEMENT STATE REPORT - LOST MATERIAL IN TRANSIT\n The following is summarized from an e-mail received from the Commonwealth of Massachusetts:\n The licensee reported on 4/6/20 that…`
5. `[min_chars] UNACCOUNTED FOR ACCESS KEY. COMPENSATORY MEASURES WERE PUT INTO PLACE.\n\n SEE HOO LOG FOR DETAILS.\n\n THE RESIDENT INSPECTOR WAS NOTIFIED.`
