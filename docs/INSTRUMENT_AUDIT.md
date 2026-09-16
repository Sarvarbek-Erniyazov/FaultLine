# Instrument audit

A record of the checks, budgets and measurements in this project that **did not measure
what they were stated to measure**. It covers the M1 and M2 milestones and the download
and training code, and it grows: a new entry is added when a divergence is found,
and an entry is never edited away.

## The distinction this document is organised around

- **INSTRUMENT defect.** The code ran without error and produced a number, a flag or a
  bound that *looked* like the stated quantity, but the rule it implemented was not the
  rule it was stated to implement. Nothing fails. The output is plausible, gets
  reported, and a result is built on it.
- **IMPLEMENTATION defect.** The code was wrong in the ordinary way: it crashed, warned,
  or left out an output someone went looking for. It surfaced through normal use.

The first kind is the one that matters for the evidence. An implementation defect costs
time. An instrument defect changes a reported result without anyone noticing. So every
entry below says what the reported result would have been if the divergence had not
been found. That column is what makes this document evidence rather than a changelog.

## Entry format

Each instrument has six fields:

1. **Supposed to measure**, quoting the brief, ADR or config with a reference. The M2
   brief is not a file in this repository (`reports/data/phmsa_gate_brief_20260915.md`,
   section on "One fit; no iteration"), so it is quoted where the repository quotes it.
2. **Actually measured.**
3. **How the divergence was found**: the practice that found it, not the symptom.
4. **Reported result had it gone undetected.**
5. **Regression test**, as `file::test_name`. "None" is written where none exists.
6. **Commit** that fixed it.

---

## 1. The near-duplicate trigger

| field | |
| --- | --- |
| supposed to measure | Whether republished incident reports survive exact dedup: "add MinHash near-duplicate removal (`dedup.strategy: minhash`), which exact hashing cannot cover for republished incident reports" (`docs/ROADMAP.md`, M2 Work). The pre-registered trigger: "on a 2,000-document sample (post-exact-dedup), 5-shingle Jaccard overlap between every pair; if more than 5% of pairs above 0.8 survive exact dedup, MinHash-LSH becomes a second strategy" (commit `27b12c3`). |
| actually measured | The share of **random document pairs** above 0.8 Jaccard: 9 of 1,999,000 (0.0005%). The corpus held 21,882 distinct event numbers, so two revisions of one event almost never land in the same random pair. The sample could not see the republication pattern the trigger existed to detect, and it would have read near zero whatever that pattern's size. |
| how found | At the review of the M2 checkpoint (`5d12196` to `825b896`). The one surviving pair inspected by hand, `20041126en_en41208` and `20041124en_en41208`, was the same event number on two report days. That pair was read against the sampling design, with one question: can a random-pair sample see this at all? |
| reported result if undetected | The checkpoint's own sentence: "exact dedup is the whole story for this corpus" (`reports/data/m2_checkpoint_20260913.md`, section c). **4,521 superseded event revisions** would have stayed in the corpus: 37,321 documents instead of 32,800, so 12.1% of them would have been older copies of an event also present. Splits are assigned by content hash, so revisions of one event could also have fallen on both sides of the train/held-out line. That leakage is possible, not measured. |
| regression test | `tests/data/text/test_keyed_dedup.py::test_keeps_only_the_latest_revision_per_event_number`. The random-pair trigger itself is unchanged; a keyed rule was added beside it rather than the trigger being repaired. |
| commit | `825b896` |

## 2. `one_pass_windows`: one pass counted as stride-1 windows

| field | |
| --- | --- |
| supposed to measure | The size of one pass over the training data: "BUDGET: one pass over the training corpus, or gpu_hour_budget GPU-hours, whichever is smaller" (`configs/train/text_v1.yaml:9-10`). |
| actually measured | The sampler's count of admissible windows at stride 1: **10,031,592 windows** for 10,043,874 training tokens. Those windows overlap in all but one token, so the count is about the context length times the corpus, roughly 2,000 passes. |
| how found | Reading `text_ladder` before the first real run, against the config's definition of the budget (commit message `a9ce65e`). |
| reported result if undetected | The 4 GPU-hour cap would have bound on both rungs. From each rung's recorded calibrated throughput (`reports/data/text_pretrain_v1_20260916.json`, `gpu_hour_windows`), S2 would have trained on **81,706 windows (about 167M tokens, 16.7 passes)** and S3 on **47,842 (about 98M, 9.8 passes)**. Both would have been reported as "gpu_hours bound" under a budget line that says "one pass". The S2-versus-S3 comparison would have given the smaller rung 1.7x the tokens. |
| regression test | `tests/evaluation/test_text_ladder.py::test_one_pass_is_training_tokens_over_context_not_the_window_count` |
| commit | `a9ce65e` |

## 3. Throughput calibration timed evaluation as training

| field | |
| --- | --- |
| supposed to measure | Training throughput, so that the GPU-hour cap can be turned into a window count: "measured per rung by a short calibration pass rather than assumed" (`configs/train/text_v1.yaml:10`). |
| actually measured | 20 optimiser steps **plus one full validation measurement** (up to 3,000 windows per source) inside the timed call. S2 read **0.7 windows/s** against a true training rate of 5.7. |
| how found | Reading S2's logged calibration line during the real run: the rate was implausible for the card. The code was then read against the config's definition. The run was stopped and restarted rather than reported. This is the one entry found from a running job's output rather than before the run. |
| reported result if undetected | S2's cap would still have exceeded one pass (0.7 x 14,400 s = 10,080 windows, more than 4,905), so S2 would have run as reported. **S3 would have calibrated at about 0.24 windows/s and been cut to about 3,400 windows (about 7M tokens) by the GPU-hour bound**, against S2's 10.0M. Gate 6 would then have compared rungs at unequal token budgets, and "S3 is worse" would have been confounded with "S3 saw 30% fewer tokens" (`reports/data/m2_gate6_20260916.md`, section 9.5). |
| regression test | **None.** `bc0fd3a` changed `text_ladder.py` only. This is an open gap. |
| commit | `bc0fd3a` |

## 4. The free-text detector's name branch bypasses the ratio guard

| field | |
| --- | --- |
| supposed to measure | Whether a column holds free-text narrative. The rule was pre-registered in ADR-0016 and quoted verbatim there: "a column qualifies if its name matches the narrative pattern, OR mean length > 80 chars AND distinct-value ratio > 0.5. (The ratio guard is the OE-417 lesson — mean length alone can be passed by a long coded field.)" (`docs/DECISIONS.md`, ADR-0016, pre-registered decision rule). |
| actually measured | Exactly the wording, which defeats the stated purpose. The name branch (`src/faultline/data/text/phmsa_manual.py:314`) admits any column whose name contains `detail`, `description` and so on, whatever its distinct-value ratio. That is the coded-field failure the guard was added to stop. **62 columns qualified, all by name**, and 61 of them are short `*_DETAILS` "other, specify" fields, some closed code sets (`CAUSE_DETAILS`: distinct ratio 0.007). |
| how found | Reading the measured per-column verdict table (`reports/data/phmsa_manual_20260915.md`) against the guard's stated reason while writing the Gate 6 report. This one was found by reading output against the rule, not code. |
| reported result if undetected | The free-text yield of the target file would stand as **1,030,940 tokens (all qualifying columns) rather than 894,467 (`NARRATIVE`)**, overstated by 136,473 (15.3%). The staging branch did not change here, because `NARRATIVE` alone is 3.6x the 250,000 bar. On a thinner file, closed code sets named `*_DETAILS` could have carried a source over the bar. |
| regression test | **None. Not fixed.** The detector still evaluates the name branch first. The Gate 6 report records it as a limitation for "a future rule of this shape" (section 2). This is an open gap. |
| commit | none (recorded in `4b3149a`) |

## 5. The robots.txt gate (`urllib.robotparser`)

| field | |
| --- | --- |
| supposed to measure | Whether a URL is permitted by the host's robots.txt before the first request: "`NrcTextClient` now checks robots.txt before, not after, the first request to a host" (`docs/DECISIONS.md`, ADR-0016 status line). Every text card also carries a "robots.txt basis" row. |
| actually measured | The standard-library parser's reading, which differs from RFC 9309 in two ways that affect both files this project reads. **(a) Blank lines:** a blank line ends a group, so `Disallow` lines written below one are dropped. On `data.transportation.gov`, `/api/odata/x` and `/login` read as allowed. **(b) Full-URL values:** a value such as `Disallow: https://www.nrc.gov/site-help/search` is stored percent-encoded and never matches a path, so all four `User-agent: *` rules on `www.nrc.gov` read as allow-all. `*` and `$` were also treated literally. |
| how found | While preparing the PHMSA gate brief, `data.transportation.gov/robots.txt` was fetched and read, then the parser's answers were queried against the lines in the file (`reports/data/phmsa_gate_brief_20260915.md`, section 2a). The reading was then repeated on `www.nrc.gov`'s file, where the other failure (b) turned up. |
| reported result if undetected | The staged corpus would be the same: every staged nrc.gov URL is under `/reading-rm/` or `/documents-reports/`, and none came from a path the parser wrongly allowed (checked against the manifests). What would have been false is the claim itself: every card's "robots.txt basis" and ADR-0016's "checks robots.txt before the first request" would have asserted enforcement of rules that were never enforced on either host, and any later crawl of a disallowed path would have gone through. |
| regression test | `tests/download/test_robots.py::TestDataTransportationGov::test_disallowed_paths_are_refused`, `tests/download/test_robots.py::TestWwwNrcGov::test_full_url_disallows_are_refused` |
| commit | `ebfa946` (wording follow-up `ad24062`) |

## 6. `verified=True` written before the archive was parsed

| field | |
| --- | --- |
| supposed to measure | Whether a staged file is verified: the dataset-card template's "Whether every checksum verified" (`docs/DATASET_CARD_TEMPLATE.md`, Staging), printed on text cards as "every document hashed and verified". The fix states the intent: "a file that does not parse is not verified data" (`phmsa_manual.ArchiveParseError`). |
| actually measured | Only that the file hashed. `inspect phmsa` wrote the manifest record with `verified=True` first and then opened the zip. A member that failed to parse was logged as a warning and skipped. |
| how found | Reading the `inspect phmsa` code path before the first real inspection (Gate 6 report, section 9.1). |
| reported result if undetected | The real target member is tab-delimited Windows-1252, which the comma/UTF-8 reader could not parse. The first inspection would have skipped it, found **zero qualifying columns**, and returned the pre-registered rule's first branch: "no column passes -> EXCLUDE for thinness ... gate closes permanently", under a manifest record saying the file was verified. PHMSA, now 20.8% of training words, would have been excluded for good on a file that had never been read. What actually happened: the fixed code exited 2 and recorded nothing. |
| regression test | `tests/data/text/test_phmsa_manual.py::test_cli_writes_nothing_and_exits_non_zero_for_a_malformed_archive` |
| commit | `ebfa946` |

## 7. Bits per byte mixed one window's tokens with a whole split's bytes

| field | |
| --- | --- |
| supposed to measure | Bits per byte per source: "Convert a mean next-token loss in nats to bits per byte" (`src/faultline/evaluation/text_ladder.py`, `_bits_per_byte`), reported "per source, never pooled" (Gate 6, section 6). |
| actually measured | Mean loss multiplied by one window's 2,047 predicted tokens, divided by the UTF-8 bytes of the **whole** source split. The figure was understated by the ratio of the split's token stream to one window. |
| how found | Reading `text_ladder` before the first real run, together with defect 2 (commit message `a9ce65e`). |
| reported result if undetected | Each source's figure would have been scaled by 2,047 over its own stream length. For S2 on validation that gives event notifications **0.056** instead of 1.777 (65,086-token stream), PHMSA **0.087** instead of 1.778 (41,747), and regulatory issue summaries **0.093** instead of 1.789 (39,369). The per-source ranking would have followed split size, not the model, and event notifications would have looked about 1.6x easier than PHMSA because their validation split is longer. |
| regression test | `tests/evaluation/test_text_ladder.py::test_bits_per_byte_uses_one_streams_tokens_and_bytes` |
| commit | `a9ce65e` |

## 8. The rare-vocabulary share left out ids never seen

| field | |
| --- | --- |
| supposed to measure | The share of the tokenizer's vocabulary seen fewer than 100 times in training: "share of vocabulary under the rare threshold" (`reports/data/text_bpe_v1_20260915.md`), carried into the Gate 6 limitations. |
| actually measured | Ids seen **at least once** and fewer than 100 times. The count ran over a `Counter` of the ids that occurred, and a never-seen id is not in the `Counter`, so the 931 ids never seen were left out of a quantity they belong to. The printed figure was 24,456 (74.63%). |
| how found | Two instruments disagreed. While building the code-book card (step A1 of the M3 entry brief), token frequency was recounted independently from the training shards. The count gave 25,387, and the difference was exactly the 931 never-seen ids the same report printed one line above. |
| reported result if undetected | **74.63%** rare in Gate 6 and the roadmap, against the true **77.47% (25,387 of 32,768)**: a limitation understated by 2.84 points. |
| regression test | `tests/data/text/test_bpe_fit.py::test_rare_id_count_includes_ids_never_seen` |
| commit | `3c294c2` |

---

## The seven defects reported for the Gate 6 run, classified

Gate 6's section 9 lists five defects and two further fixes. The seventh "fix", the
incremental BPE fit (`3cbcb2d`), is a performance change asserted to give identical
merges, not a defect. The seven defects are these:

| # | defect | class | why | entry |
| --- | --- | --- | --- | --- |
| 1 | `inspect phmsa` recorded `verified=True` before parsing | **INSTRUMENT** | A verification flag asserted a check that had not happened; the output was a plausible manifest record | 6 |
| 2 | Robots gate on `urllib.robotparser` | **INSTRUMENT** | A permission check answered "allowed" for rules it never read, silently and plausibly | 5 |
| 3 | A split shorter than one context wrote an empty window index | IMPLEMENTATION | Nothing claimed a check; the code logged a warning, so the defect surfaced through normal output | -- |
| 4 | `one_pass_windows` counted stride-1 windows | **INSTRUMENT** | A budget bound labelled "one pass" was about 2,000 passes | 2 |
| 5 | Bits per byte mixed one window's tokens with a split's bytes | **INSTRUMENT** | A reported metric had the right name, a plausible magnitude per source, and the wrong units | 7 |
| 6 | Calibration timed evaluation as training | **INSTRUMENT** | A throughput measurement fed a bound; nothing failed, and the rate was wrong by 8x | 3 |
| 7 | `text_ladder` never saved the selected parameters | IMPLEMENTATION | An output was missing, and someone went looking for the file five minutes into the first run | -- |

**Five instruments, two implementations.** Neither implementation defect could have
changed a reported number: one warned, and the other left out a file that was needed.
Each of the five instrument defects changes, or would have changed, a number, a
bound or a decision without any error being raised.

The five entries named in the M3 entry brief were 1, 2, 3, 4 and 5 above. Entries 6 and 7
are the two remaining instruments among the seven, and entry 8 was found while writing
this document's first version.

## The recurring shape

**The stated rule and the implemented rule diverged silently, and no divergence was
found by a failing test.** In every entry the test suite passed, both before and after,
because each test checked what the code did, and the code did what it was written to do.
The finds came from practices, not from checks:

- **Reading code or design against the stated rule before trusting the output**: entries
  1, 2, 5, 6 and 7.
- **Reading an output against what the rule implied**: entry 3 (a calibration rate
  implausible for the card) and entry 4 (a per-column table whose qualifiers were code
  sets).
- **Two independent instruments disagreeing**: entry 8.

The same point applies to the tests. A regression test written after the fact pins the
corrected definition, but it cannot say whether a new instrument measures what its brief
says. That question is only answered by reading the instrument against the brief. Two
entries (3 and 4) still have no regression test at all.

### A sub-pattern seen twice: a budget stated in the wrong unit

A budget stated in a unit that is not the quantity the comparison depends on hides the
quantity that matters:

1. **Optimiser steps instead of positives seen** (M1e, `docs/ROADMAP.md`, M1 results).
   1,250 steps at 32 windows looked like a fixed budget and bought **882 positives**. 49%
   of steps carried none, and the control arm sat pinned at the prior. H1 went UNTESTED,
   and the pretraining ablation INCONCLUSIVE, for that reason. M3 step 0 states the
   remedy: size the risk budget in positives seen.
2. **GPU-hours instead of tokens seen** (M2d, entries 2 and 3). A wall-clock cap turned
   into windows by a measured rate lets that rate choose the budget. A defect in the
   pass count (entry 2) or in the rate (entry 3) would have given two rungs different
   token counts under one budget line. The rungs as run spent identical tokens
   (10,027,008 each) only because both defects were fixed first.

The rule this pattern leads to: **budget in the unit the comparison is about, and report
the other units as observations.** Tokens seen for pretraining arms. Positives seen for
risk heads.
