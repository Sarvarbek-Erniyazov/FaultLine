# Course notebook port map

The text pipeline in `src/faultline/data/text/` is a port of the instructor's
reference notebook from the author's LLM-engineering course. This file maps every
notebook cell onto the module, function, config key and test that replaced it, and
lists every place where behaviour deliberately differs.

The notebook itself is kept out of git under `notebooks/_reference/` (git-ignored).
It carried the instructor's absolute paths and `!pip install` cells in its outputs,
and it is a source to port, not an artefact to keep.

## Correction to the port brief

The brief described the notebook as "config-driven (`data.yaml`)". It is not. The
notebook has **one inline dictionary**, `FILTER_CONFIG` (cell 21), holding four
quality thresholds; everything else — the regexes, the Unicode form, the hash
normalisation, the PII placeholders, the directory layout — is hard-coded in the cell
bodies. There is no `data.yaml` in the notebook and none was supplied.

This matters for the port: the four `FILTER_CONFIG` keys keep their exact names in
`configs/data/text_v0.yaml`, and everything else that became a config key is marked
`# course default (was hard-coded)` rather than pretending it was already
configurable.

## What the notebook actually contained

44 cells. Imports: `pathlib`, `re`, `hashlib`, `json`, `unicodedata`, `html`,
`collections.Counter`, plus `pandas` (imported, never used) and `datasets` (used only
to download TinyStories). No `beautifulsoup4`, `lxml`, `ftfy` or `regex` — which is
why none of them is a FaultLine dependency.

Pipeline order: clean → filter → deduplicate → scrub PII → write final. **That order
is preserved exactly.** No stage was reordered.

## Cell-by-cell map

| notebook cell | what it did | FaultLine module.function | config key(s) | test | semantic change |
| --- | --- | --- | --- | --- | --- |
| 00 | imports | — | — | — | `pandas` import dropped (unused); `datasets` not a dependency |
| 01 | build `data/{raw,cleaned,filtered,final}` from a relative `PROJECT_ROOT` | `paths.ProjectPaths.stage_dir` | `FAULTLINE_DATA_ROOT` env | `tests/test_paths.py` | **Changed.** Directories are resolved from the repo root or an env var, not from a notebook-relative path, and split by modality |
| 02–03 | `!pip install` / reinstall | — | — | — | **Dropped.** Dependencies are declared in `pyproject.toml` |
| 04–07 | download TinyStories, print columns and length | — | — | — | **Not ported.** TinyStories is the course corpus; FaultLine corpora are specified in `configs/data/sources_text.yaml` (M2). The pipeline reads JSON Lines and does not know where it came from |
| 08 | write raw JSONL | `data.text.pipeline.write_jsonl` | `text.io.corpus_name` | `tests/data/text/test_pipeline.py::test_jsonl_round_trip` | — |
| 10 | `load_jsonl` reading the whole corpus into a list | `data.text.pipeline.read_jsonl` | — | `tests/data/text/test_pipeline.py::test_jsonl_round_trip` | **Changed.** Streams a generator instead of materialising the corpus. The notebook held four full copies of TinyStories in memory at once; that does not survive a real corpus on 32 GB |
| 11 | raw document and character counts | `data.common.report.counts_table`, `percentile_summary` | — | `tests/data/common/test_report.py` | Extended: percentiles as well as totals |
| 16 | `remove_html`, `normalize_unicode`, `remove_control_characters`, `normalize_whitespace`, `clean_text` | `data.text.clean.*` | `text.clean.*` | `tests/data/text/test_clean.py` | **None.** Regexes, NFKC, the kept control characters (`\n`, `\t`) and the chain order are identical. Each step gained an on/off switch, defaulting to the notebook behaviour |
| 17 | cleaning loop, `cleaning_stats` counters, drop empty | `data.text.pipeline.CleanStage.run` | `text.clean.drop_empty` | `tests/data/text/test_pipeline.py::test_clean_stage_counts` | — |
| 18 | write cleaned JSONL | `CleanStage` output | — | same | — |
| 21 | `FILTER_CONFIG` dict | `configs/data/text_v0.yaml` → `text.filter` | `min_chars`, `max_chars`, `min_alpha_ratio`, `max_repeated_line_ratio` | `tests/data/text/test_filter.py` | **Key names preserved exactly.** Values preserved exactly (200 / 100000 / 0.30 / 0.30) |
| 22 | `alphabetic_ratio`, `repeated_line_ratio` | `data.text.filter.*` | — | `tests/data/text/test_filter.py` | **None.** Including the edge cases: empty text is 0.0, a single non-empty line is 0.0 |
| 23 | filter loop with per-rule counters | `data.text.filter.filter_reason`, `pipeline.FilterStage.run` | `text.filter.*` | `tests/data/text/test_filter.py::test_first_failing_rule_wins` | **None.** The notebook `continue`d on the first failing rule, so per-rule counts already summed to the drop count; `filter_reason` makes that explicit |
| 24 | write filtered JSONL | `FilterStage` output | — | — | — |
| 27 | `document_hash` (strip, lowercase, SHA-256) | `data.text.dedup.document_hash` | `text.dedup.lowercase`, `text.dedup.strip` | `tests/data/text/test_dedup.py` | **None.** Normalisation made configurable, defaulting to the notebook behaviour |
| 28 | dedup loop over a `seen_hashes` set | `data.text.dedup.ExactDeduplicator`, `pipeline.DedupStage.run` | `text.dedup.strategy` | `tests/data/text/test_dedup.py::test_exact_deduplicator` | Extended: `strategy` key with `exact` implemented and `minhash` rejected as `TODO(m2)`, rather than silently doing nothing |
| 32 | `EMAIL_PATTERN`, `PHONE_PATTERN`, `NUMBER_PATTERN` | `data.text.pii.*` | — | `tests/data/text/test_pii.py` | **None.** All three regexes are byte-identical to the notebook |
| 33 | `scrub_pii`, always masking all three classes | `data.text.pii.scrub_pii` | `text.pii.mask_emails`, `mask_phones`, `mask_digits` | `tests/data/text/test_pii.py::test_digit_masking_is_off_by_default` | **CHANGED — ADR-0005.** Each class is toggleable, and `mask_digits` defaults to **`false`**. See below |
| 34 | PII loop with totals | `pipeline.PIIStage.run` | `text.pii.*` | `tests/data/text/test_pipeline.py` | Extended: counts documents touched per class, not only replacement totals |
| 35 | write one flat final JSONL | `pipeline.FinalStage.run`, `ShardWriter` | `text.final.shard_size`, `split_fractions`, `split_seed` | `tests/data/text/test_pipeline.py::test_final_stage_splits_and_shards` | **CHANGED.** The notebook wrote a single file with no splits. FaultLine assigns train/val/test deterministically from a hash of the document and shards the output. See below |
| 37 | one `stats_report.md` at the end | `data.common.report.*` + `data.text.report.*` | `text.report.*` | `tests/data/common/test_report.py` | **CHANGED.** One report per stage, in `reports/data/<run_id>/`, each carrying the run id, config hash and git SHA; plus `run.json`. See below |
| 38 | retention percentages printed | `data.common.report.counts_table` | — | `tests/data/common/test_report.py` | Same numbers, rendered as a table |
| 40–41 | print the first 5 documents before/after | reservoir samples in every stage report | `text.report.sample_size` | `tests/data/text/test_pipeline.py` | **CHANGED.** Random samples rather than the first N, and the filter stage samples *removed* documents. The first five documents of a corpus tell you nothing about what a filter deleted |
| 43 | markdown diagram of the lesson plan | — | — | — | Not ported |
| 09, 12–15, 19–20, 25–26, 29–31, 36, 39, 42 | comment-only or empty cells | — | — | — | Not ported |

## Semantic changes, justified

Five, and no others.

**1. Digit masking is off by default (ADR-0005).** The notebook masks any run of six
or more digits. Correct for TinyStories; destructive for operator narratives, where
"reactor power held at 850000 kW" is the technical content. Emails and phone numbers
stay masked. Recorded per corpus on its dataset card.

**2. Streaming instead of materialising.** Every stage reads and writes JSON Lines
through generators. The notebook held `raw_docs`, `cleaned_docs`, `filtered_docs`,
`unique_docs` and `final_docs` simultaneously — five full copies. The deduplicator
keeps digests only; report samples are bounded reservoirs.

**3. Splits and sharding at the final stage.** The notebook wrote one file. Splits are
assigned deterministically from `sha256(seed:document)`, so the assignment survives
re-runs, reordering and shard-size changes — a document cannot migrate from
validation into training because the pipeline was edited.

**4. One report per stage, with run identity.** The notebook printed one report at
the end. Each stage now writes its own Markdown report carrying the run id, config
hash and git SHA, alongside `run.json`. A stage that cannot describe what it did is
rejected by the `Stage` base class.

**5. Random samples of removed documents.** The notebook printed the first five
documents. The filter report samples documents the filters *dropped*, which is the
only cheap way to notice a threshold quietly deleting good text.

## A wart found by running the port, and kept

Two behaviours inherited from the notebook are wrong for FaultLine's corpora but are
preserved anyway, because a port that quietly "improves" its source cannot be checked
against it. Both are recorded here and carry a TODO:

1. **The tag-stripping regex eats prose comparisons.** `<[^>]+>` is greedy about angle
   brackets, so `2 < 3 and 4 > 1` cleans to `2   1`. Harmless on TinyStories; not
   harmless in text describing thresholds. Covered by a test that asserts the lossy
   behaviour explicitly (`tests/data/text/test_clean.py`), so the day it is fixed, the
   fix is deliberate.
2. **The phone regex masks long digit runs that are not phone numbers.** The M0
   fixture run turned `Serial number 8812349900` into `Serial number <PHONE>`. This
   matters more than it looks: ADR-0005 turns *digit* masking off to protect technical
   content, and the phone pattern then does much of the same damage anyway. See
   ADR-0005 for the analysis and the M2 replacement plan.

## What was deliberately not changed

The regexes, the NFKC normalisation, the kept control characters, the four threshold
values and their key names, the hash normalisation, the placeholder strings, and the
stage order. Where the port could have "improved" the course logic, it did not:
matching behaviour is what makes the port checkable against the original.
