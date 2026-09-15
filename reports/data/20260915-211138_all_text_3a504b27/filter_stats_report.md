# Text pipeline - quality filtering

| field | value |
| --- | --- |
| run_id | 20260915-211138_all_text_3a504b27 |
| stage | filter |
| config | configs/data/text_v2.yaml |
| config_hash | 3a504b27 |
| git_sha | dfbd7023363b79a871e5feea6746d476a3150cf8 |
| created_at (UTC) | 2026-09-15T21:11:38+00:00 |

## Documents

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| filter | 43,758 | 43,137 | 621 | 98.58% |

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
| min_chars | 447 | 1.022% |
| repeated_lines | 171 | 0.391% |
| max_chars | 3 | 0.007% |

## Document length, kept documents (characters)

| length statistic | value |
| --- | --- |
| count | 43,137 |
| mean | 1,549 |
| std | 2,122 |
| min | 200 |
| p1 | 253 |
| p5 | 365 |
| p25 | 744 |
| p50 | 1,126 |
| p75 | 1,716 |
| p95 | 3,748 |
| p99 | 8,620 |
| max | 9.492e+04 |

## Alphabetic ratio, kept documents

| alphabetic ratio statistic | value |
| --- | --- |
| count | 43,137 |
| mean | 0.7792 |
| std | 0.02553 |
| min | 0.5409 |
| p1 | 0.7061 |
| p5 | 0.7349 |
| p25 | 0.7647 |
| p50 | 0.7811 |
| p75 | 0.7959 |
| p95 | 0.8172 |
| p99 | 0.8319 |
| max | 0.8617 |

## Repeated-line ratio, kept documents

| repeated-line ratio statistic | value |
| --- | --- |
| count | 43,137 |
| mean | 0.007259 |
| std | 0.03383 |
| min | 0 |
| p1 | 0 |
| p5 | 0 |
| p25 | 0 |
| p50 | 0 |
| p75 | 0 |
| p95 | 0.04795 |
| p99 | 0.2 |
| max | 0.3 |

## Sampled removed documents

Random sample of documents the filters dropped, truncated to 200 characters. Read these before trusting the thresholds.

1. `[repeated_lines] AGREEMENT STATE REPORT - LOST MATERIAL IN TRANSIT\n The following is summarized from an e-mail received from the Commonwealth of Massachusetts:\n The licensee reported on 4/6/20 that…`
2. `[min_chars] CIG 5A PIPELINE RELEASED 97,506 MCF. NTSB IS CURRENTLY INVESTIGATING. PIPELINE IS CURRENTLY OUT OF SERVICE. SUPPLEMENTAL REPORT WILL BE FILED UPON INVESTIGATION COMPLETION.`
3. `[repeated_lines] TECHNICAL SPECIFICATION REPORTABLE OCCURRENCE\nThe following information was provided by the licensee via phone and email:\n"In accordance with Technical Specification (TS) 6.7.2.1, …`
4. `[repeated_lines] AGREEMENT STATE REPORT - LOST MATERIAL IN TRANSIT\n The following is summarized from an e-mail received from the Commonwealth of Massachusetts:\n The licensee reported on 4/6/20 that…`
5. `[min_chars] MIXER ON TANK 23 EXPERIENCED A SEAL FAILURE. RESPONSE EQUIPMENT WAS BROUGHT ONSITE AND CONTAINED THE LEAK WHILE OIL WAS TRANSFERRED FROM THE TANK.`
