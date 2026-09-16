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
| regression test | `tests/evaluation/test_text_ladder.py::test_calibration_is_timed_on_training_alone`, added 2026-09-16. The first version of this entry read: "**None.** `bc0fd3a` changed `text_ladder.py` only. This is an open gap." The test runs the ladder end to end and fails if validation loss is scored during the timed calibration call. It was checked against the pre-fix line (`measure=measure`), and it fails there. |
| commit | `bc0fd3a` |

## 4. The free-text detector's name branch bypasses the ratio guard

| field | |
| --- | --- |
| supposed to measure | Whether a column holds free-text narrative. The rule was pre-registered in ADR-0016 and quoted verbatim there: "a column qualifies if its name matches the narrative pattern, OR mean length > 80 chars AND distinct-value ratio > 0.5. (The ratio guard is the OE-417 lesson — mean length alone can be passed by a long coded field.)" (`docs/DECISIONS.md`, ADR-0016, pre-registered decision rule). |
| actually measured | Exactly the wording, which defeats the stated purpose. The name branch (`src/faultline/data/text/phmsa_manual.py:314`) admits any column whose name contains `detail`, `description` and so on, whatever its distinct-value ratio. That is the coded-field failure the guard was added to stop. **62 columns qualified, all by name**, and 61 of them are short `*_DETAILS` "other, specify" fields, some closed code sets (`CAUSE_DETAILS`: distinct ratio 0.007). |
| how found | Reading the measured per-column verdict table (`reports/data/phmsa_manual_20260915.md`) against the guard's stated reason while writing the Gate 6 report. This one was found by reading output against the rule, not code. |
| reported result if undetected | The free-text yield of the target file would stand as **1,030,940 tokens (all qualifying columns) rather than 894,467 (`NARRATIVE`)**, overstated by 136,473 (15.3%). The staging branch did not change here, because `NARRATIVE` alone is 3.6x the 250,000 bar. On a thinner file, closed code sets named `*_DETAILS` could have carried a source over the bar. |
| regression test | `tests/data/text/test_phmsa_manual.py::test_a_narrative_named_closed_code_set_is_not_narrative`, added 2026-09-16. The first version of this entry read: "**None. Not fixed.** The detector still evaluates the name branch first." The detector now requires `name matches AND distinct ratio > 0.5`. Re-read on the same file, 54 columns qualify instead of 62, and the file total is 1,001,924 tokens instead of 1,030,940. The PHMSA decision is unchanged (ADR-0016, amendment note of 2026-09-16). |
| commit | recorded in `4b3149a`; the amendment is applied in the commit that adds this entry's test |

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

## 9. H3's vocabulary split was drawn at the word level, and the model reads tokens

*Added 2026-09-16.* **This is the first entry where the instrument that did not measure what
it claimed was the scientific analysis, not the code.** Every line of code involved did what
its docstring says. What diverged was the choice of unit in the analysis that H3's test was
built on.

| field | |
| --- | --- |
| supposed to measure | Which status strings "share vocabulary with the narrative corpus", the split H3's test rests on: "the joint model's held-out-site advantage over the telemetry-only M1 model should be **larger** for event types whose status strings share vocabulary with the narrative corpus than for event types whose strings do not" (`docs/DECISIONS.md`, ADR-0007, H3). The mechanism H3 names is narrative pretraining, so the vocabulary that counts is what pretraining leaves the model: trained embeddings for the token ids a status string encodes to. |
| actually measured | **Word-level overlap.** A string was on the high side when every lowercase `[a-z]+` word in it occurs at least 100 times in the training split's text (`src/faultline/data/text/vocab_overlap.py`, partition under condition C). The word rule lowercases, ignores position, and treats a word as one unit. The tokenizer does none of those things. A status string starts a line and is capitalised, so its first word encodes as a string-initial piece that prose rarely produces (`Wind` is `W` + `ind`). **Word level: 80/264 on the high side, which looked workable. Token level, what the model receives: 18/264.** Of the 80 high-side strings, **66 reach the model with at least one token id seen fewer than 100 times.** |
| how found | Two instruments disagreed. Building the code-book card (step A1 of the M3 entry brief, `3c294c2`), token-level coverage was computed beside the word-level count, and both were printed, labelled by level, in one table: 18/264 against 80/264. The disagreement was recorded on the card as a property of string framing. It was recognised as a defect in H3's analysis only when H3 was withdrawn and its split was read against its own mechanism. H3' Stage A (`d56684a`) then measured the gap directly. |
| reported result if undetected | **H3 would have been run as an ablation that could not answer its own question.** The narrative-pretraining ablation would have compared held-out advantage across a "high-overlap" side where 66 of 80 strings carry a token pretraining barely trained. A flat result could not separate "narrative pretraining does not transfer status meaning" from "the high side was not high for the model", and a positive result could not be attributed to shared vocabulary. The run did not happen, but for other reasons: the testability gate fired on event counts (Hill of Towie 0/693, CARE 0/45, 2 types on the training sites' high side) before any training. Had those counts cleared, nothing in the pipeline would have stopped the ablation from running on the word-level split. |
| regression test | **No test can pin this, and that is the finding.** A test checks that code implements a rule. It cannot check that the rule is the right unit for the hypothesis. Two tests pin what can be pinned: `tests/data/text/test_code_book.py::test_card_labels_token_and_word_level_and_states_role` (both levels are always reported, and labelled), and `tests/data/text/test_status_convention.py::test_equal_counts_are_compared_as_sets` (Stage A's normalized 80 equals the word-level 80 by count but shares only 72 strings, so the two levels are compared as sets). Token-level coverage has a limit of its own: it is a floor on how often pieces were seen, not evidence that a word is known. `Yaw error` is token-covered as `Y` `aw` ` error`, and `yaw` never occurs in the corpus (ADR-0017). |
| commit | None fixes it in code. Found in `3c294c2`; H3 withdrawn in `343e302`; measured at the token level in `d56684a`. |

---

## 10. The gate chain that did not gate

*Added 2026-09-16.* **The verification harness failed its own check.** Every other entry
here is a check that measured the wrong thing. This one is the check that decides whether
any of those checks ran green before a commit.

| field | |
| --- | --- |
| supposed to measure | Whether every gate is green before a commit: "all gates green before each commit" (the M3 briefs of 2026-09-16). The gates are ruff, `mypy --strict src/`, `pytest -q` and `faultline check naming`, run as one chain whose failure stops the commit. |
| actually measured | **The exit status of `tail`.** The chain was typed as `pytest -q \| tail -n 3 && ... && git commit`. A pipeline's status is its last command's, and `tail` exits 0 whatever it reads. A failing pytest therefore let the chain continue to `git commit`. Ruff and mypy were piped the same way, so a lint or type failure would have passed as well. Only the final summary lines were printed, and the chain went on either way. |
| how found | The failure summary was read in the output of the same command that had made the commit. The commit `bbd8614` (C0, 18:58:05) carried a failing test, `tests/training/test_positive_aware_risk.py::test_the_ladder_opens_a_balanced_sampler_at_the_stage_fraction`. The synthetic shard was too short for `telemetry_v1`'s stride of 6 to keep a positive window, so the sampler raised. It was amended 65 seconds later as `904ff77`, which changes only that test (`git diff bbd8614 904ff77`). The failing tree is kept in the reflog. |
| reported result if undetected | **Every "gates green" in a commit message since the chain was piped is unverified.** C0's message says "implemented and fixture-tested" over a red test. Nothing would have stopped a real defect in C1 or C2 in the same way, and a later commit's message would have been built on it. The earlier commits were re-gated for this entry: see the note below the table. The failure that was caught happened to be a test defect, not a code defect. That was luck, not the chain. |
| regression test | `tests/test_gates.py::test_a_failing_stage_fails_the_chain_although_its_output_is_piped_to_tail`, with three siblings: every stage runs so one run shows every red gate, a failure inside a stage's own pipeline counts, and the shipped chain names all four gates under `pipefail`. It was checked against the defect. With `pipefail` removed from `scripts/gates.sh`, the same failing stage prints `ALL GATES PASSED` and exits 0. |
| commit | The commit that adds this entry: `scripts/gates.sh`, with `set -euo pipefail` over the whole chain and every stage run as `bash -o pipefail -c`. The script also refuses untracked, unignored files, because `faultline check naming` scans tracked files only, and a file not yet added passes it unread. |

**Re-gated for this entry, 2026-09-16.** Every commit of the M3 entry brief was checked out
into a clean worktree and run through the four gates, each exit code read directly with no
pipe: `3c294c2`, `e29c10c`, `314fcd0`, `b29e2a4`, `343e302`, `d56684a`, `8f9379f`,
`33c9591`, `904ff77`, `fc7104c` and `58c0096`. **All eleven pass ruff, `mypy --strict`,
pytest and naming.** As a control, the pre-amend tree `bbd8614` was run the same way, and
pytest exits 1 with the one failure named above. So the harness that re-gated the history
can see a failure, and none of the committed trees hides one. The claims in those commit
messages stand, but they now stand on this re-run, not on the chain that made them.

## 11. Token-level coverage cannot fail for an absent word

*Added 2026-09-16.* **This is the second analysis-level entry, after entry 9.** Entry 9 found
that a split drawn at the word level did not describe what the model reads, and moved the
measurement to the token level. This entry finds that the token-level measurement is not a
valid metric for the claim either. The code does what its docstring says. What is wrong is
what the number was taken to show.

| field | |
| --- | --- |
| supposed to measure | Whether a status string is within what narrative pretraining gave the model: "Of the 246 strings not covered at the token level, 62 are blocked by surface convention ... and 184 by genuine vocabulary absence" (`docs/DECISIONS.md`, ADR-0017, H3'). Stage A's decision rule reads the same instrument: "more than 50 of 264 covered after normalization: surface convention is confirmed as the dominant barrier" (ibid.). |
| actually measured | **How often the pieces of a string's segmentation were seen**, which is a property of the tokenizer's fallback, not of the words. Byte-level BPE has no out-of-vocabulary token by construction. A word the corpus never contains is still encoded, into shorter pieces, and shorter pieces are more frequent. `Yaw error` is covered raw as `Y` (1,089) `aw` (110) ` error` (1,242), and `yaw` occurs **0** times in the training text. So an absent word can make a string *more* likely to be covered, not less. Measured on the frozen tokenizer: **2 of the 18** raw-covered strings contain a word that never occurs in training (`Yaw error`, `Yaw speed high`), and 4 of 18 a word seen fewer than 100 times. Normalized, 1 of the 80 covered strings has a never-seen word and 8 have a rare one. As training text grows, every short piece clears any fixed floor, and coverage tends to 264/264 whether or not a single status word becomes known. **In the limit the metric measures nothing.** |
| how found | Reading Stage A's own diff against the claim it supported. Of the 5 strings normalization *loses*, `Yaw error` goes from covered to uncovered because ` y` (41) is rarer than `Y`. A string should not leave the covered set when its encoding comes closer to how prose writes words. The caveat was written into ADR-0017 and entry 9 ("a floor on how often pieces were seen ... not evidence that a word is known"), but the verdict and the "62 by convention" decomposition were still read off the same count. The instrument was retired when that caveat was read against the verdict. |
| reported result if undetected | **H3' would have been reported on a metric that cannot fail.** "Surface convention CONFIRMED as the dominant barrier (80 > 50)" is in ADR-0017 and the roadmap. Under a metric where more fallback means more coverage, no count could have come out at 50 or below for a reason connected to word knowledge. The "62 blocked by convention" decomposition would have gone into the M3 record as a mechanism. The two 80s share only 72 strings, and the measured change is 67 gained and 5 lost, not a block of 62. |
| regression test | Added with the replacement metric (step E1 of the M3 pre-run brief): single-token-word rate, which checks exactly whether the word's surface form exists as one vocabulary entry, and per-string NLL under the text checkpoints, which is behavioural. The test names are recorded in the note added with that commit. |
| commit | The commit that adds this entry records the defect. The metric is replaced in the next commit (E1). |

*Note added with E1, 2026-09-16.* The regression tests are
`tests/evaluation/test_status_nll.py::test_a_word_absent_from_the_corpus_is_covered_by_tokens_and_is_not_one_token`
(on a fitted tokenizer, ` yaw error` reads covered at the token level while its
single-token-word rate is 0.5) and
`tests/evaluation/test_status_nll.py::test_one_token_means_an_exact_vocabulary_entry_not_an_encoder_accident`.
Measured on the real code book (`reports/data/h3prime_behavioural_v1_20260916.md`), the 8
strings covered at the token level but not the word level cost **2.30 nats/byte** under S2.
That is as much as the 176-string vocabulary-absent residual (2.26), against 1.62 for strings
covered at both levels. The old metric put them on the covered side, and the model does not.

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
- **Two independent instruments disagreeing**: entries 8 and 9.

The same point applies to the tests. A regression test written after the fact pins the
corrected definition, but it cannot say whether a new instrument measures what its brief
says. That question is only answered by reading the instrument against the brief. Two
entries (3 and 4) still have no regression test at all. *(2026-09-16: both now have one;
see their rows.)*

### The same shape one level up: an analysis in the wrong unit (entry 9)

Entries 1 to 8 are code whose rule diverged from its brief. In entry 9 the code matched its
brief, and the analysis diverged from the hypothesis it served: the split was measured in
words, and the model reads tokens. This is the budget sub-pattern below, applied to the
unit of analysis. **Measure in the unit the mechanism acts on.** For a claim about what
pretraining gives the model, that unit is the token id, not the word.

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

### Entry 11 corrects the lesson of entry 9

Entry 9's rule, "measure in the unit the mechanism acts on", was right about the unit and
not sufficient. The token id is the unit, but a frequency floor on token ids cannot fail
for an absent word, because byte-level BPE falls back to shorter and more frequent pieces
exactly when a word is missing. **A metric has to be able to fail for the reason the claim
names.** Before a count is read as evidence, ask what input would make it come out low, and
check that the input is the thing the claim is about. For "the model knows this word", the
answer is behavioural: its NLL under the pretrained model (entry 11, and the E1 step that
replaces the metric).

### Entry 10: the check on the checks

The practices listed above find instrument defects by reading. They are only worth
anything if a red test stops a commit. Entry 10 is the one place where the harness itself
let a failure through, and it was caught by reading output, the same practice as entries
3 and 4. The gate chain is now a file (`scripts/gates.sh`) with a test that feeds it a
failure, not a line retyped before each commit.
