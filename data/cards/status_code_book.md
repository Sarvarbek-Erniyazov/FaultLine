# status_code_book


## Identity

| field | value |
| --- | --- |
| source id | status_code_book |
| provider | Cubico Sustainable Investments Ltd (Kelmarsh and Penmanshiel wind farm status logs) |
| licence | CC BY 4.0 (inherited: the same licence as the Kelmarsh and Penmanshiel telemetry records) |
| attribution | Cubico Sustainable Investments Ltd, Kelmarsh and Penmanshiel wind farm data, Zenodo, doi:10.5281/zenodo.5841833 and doi:10.5281/zenodo.5946807 (CC BY 4.0) |
| records and DOIs | inherited, not its own: Kelmarsh (concept DOI 10.5281/zenodo.5841833, version 10.5281/zenodo.16807551) and Penmanshiel (concept DOI 10.5281/zenodo.5946807, version 10.5281/zenodo.16807304), both CC BY 4.0, via Zenodo; see `data/cards/kelmarsh.md` and `data/cards/penmanshiel.md` |
| provenance | **derived, not downloaded**: the distinct status-message strings of the status tables already staged and md5-verified for M1, pooled by `build_status_code_book` (`faultline download text`); no network request is made for this source |
| access route | not fetched over the network |

_Identity fields are copied from `configs/data/sources_text.yaml` and the two telemetry cards._

## Contents

| field | value |
| --- | --- |
| strings (measured) | 264 |
| strings shared by both sites | 184 |
| characters | 5,990 |
| language | English (provider status labels) |
| note on the count | 264 is the measured count; the brief's ~230 was an estimate |

| site | turbine model | strings | strings at this site only | word types |
| --- | --- | --- | --- | --- |
| kelmarsh | Senvion MM92 | 217 | 33 | 264 |
| penmanshiel | Senvion MM82 | 231 | 47 | 271 |

Word types (lowercase `[a-z]+`): 297 in all, 238 at both sites. **Both sites are Senvion**: the site split is between two turbine models of one manufacturer, not between manufacturers, so it shows how far one OEM's vocabulary moves between models; it is not evidence about the cross-OEM case ADR-0007 argues from, and the held-out Siemens site publishes alarm codes, not strings (ADR-0001 evidence).

**Free-text verdict: VERIFIED no** - a code book, as the Kelmarsh and Penmanshiel cards already record from the raw inventory.

## Staging

| field | value |
| --- | --- |
| raw file | data/raw/text/status_code_book.jsonl (one string a line) |
| manifest | data/cards/manifests/status_code_book.json |
| site membership | each site's `labels/status_stream.parquet`, matched lowercased; every stream message is in the code book |

## Readiness for the joint vocabulary (ADR-0007, M3)

| field | value |
| --- | --- |
| tokenizer | data/tokenizers/text_bpe_v1_22c56e49.json |
| token frequency from | training shards `data/shards/text/text_bpe_v1_22c56e49` (10,012,124 text tokens, `<sep>` excluded) |
| word frequency from | the `operator_narratives` training split |
| frequent means | seen at least 100 times in training |
| quantiles | nearest rank, so every value is an observed token count |
| vocabulary ids seen fewer than 100 times | 25,387 / 32,768 (77.5%) |

### Tokens per string

| group | strings | min | p25 | median | p75 | p95 | max | mean | chars/token | bytes/token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pooled | 264 | 2 | 4 | 5 | 6 | 9 | 20 | 5.47 | 4.15 | 4.15 |
| kelmarsh | 217 | 2 | 4 | 5 | 6 | 9 | 20 | 5.36 | 4.22 | 4.23 |
| penmanshiel | 231 | 2 | 4 | 5 | 6 | 9 | 15 | 5.39 | 4.22 | 4.22 |
| kelmarsh only | 33 | 3 | 4 | 5 | 6 | 9 | 20 | 6.03 | 3.73 | 3.73 |
| penmanshiel only | 47 | 2 | 4 | 5 | 8 | 10 | 13 | 5.94 | 3.86 | 3.86 |
| shared | 184 | 2 | 4 | 5 | 6 | 8 | 15 | 5.24 | 4.32 | 4.33 |

For comparison, held-out bytes/token per narrative source (val and test together, same tokenizer): nrc_bulletins 4.63, nrc_event_notifications 4.78, nrc_gen_letters 4.81, nrc_info_notices 4.65, nrc_reg_issues 5.29, phmsa_incident_narratives 4.96. A lower figure means a string breaks into shorter pieces than the prose the tokenizer was fitted on.

Longest: `Max.temp.conv.inl.>perm.out.t.` -> `M` | `ax` | `.` | `tem` | `p` | `.` | `con` | `v` | `.` | `in` | `l` | `.` | `>` | `per` | `m` | `.` | `out` | `.` | `t` | `.`.

### Distribution (strings per token count)

| tokens | pooled | kelmarsh | penmanshiel |
| --- | --- | --- | --- |
| 2 | 9 | 8 | 9 |
| 3 | 24 | 20 | 22 |
| 4 | 66 | 54 | 59 |
| 5 | 57 | 49 | 49 |
| 6 | 44 | 36 | 36 |
| 7 | 25 | 24 | 23 |
| 8 | 18 | 13 | 16 |
| 9 | 12 | 8 | 9 |
| 10 | 3 | 1 | 3 |
| 11 | 2 | 2 | 2 |
| 12 | 0 | 0 | 0 |
| 13 | 2 | 0 | 2 |
| 14 | 0 | 0 | 0 |
| 15 | 1 | 1 | 1 |
| 16 | 0 | 0 | 0 |
| 17 | 0 | 0 | 0 |
| 18 | 0 | 0 | 0 |
| 19 | 0 | 0 | 0 |
| 20 | 1 | 1 | 0 |

### Coverage by the training data

| group | TOKEN-level: every BPE token seen >= 100 | WORD-level: every word seen >= 100 |
| --- | --- | --- |
| pooled | 18 / 264 (6.8%) | 80 / 264 (30.3%) |
| kelmarsh | 16 / 217 (7.4%) | 69 / 217 (31.8%) |
| penmanshiel | 15 / 231 (6.5%) | 74 / 231 (32.0%) |
| kelmarsh only | 3 / 33 (9.1%) | 6 / 33 (18.2%) |
| penmanshiel only | 2 / 47 (4.3%) | 11 / 47 (23.4%) |
| shared | 13 / 184 (7.1%) | 63 / 184 (34.2%) |

**Token-level coverage is the lower of the two.** The word rule lowercases and ignores position; the tokenizer does neither. A status string starts without a leading space and with a capital, so its first word encodes as a string-initial piece that prose rarely produces (`Wind` is `W` + `ind`, where prose writes ` wind`). 60 / 264 (22.7%) strings are held below the floor by their first token alone; encoded after a single space, 63 / 264 (23.9%) have every token frequent. Reported, not changed: how a status string is framed in the joint stream is an M3 decision. H3's vocabulary split is word-level (`reports/data/h3_vocab_overlap_v1_20260916.md`).

## Use in FaultLine

| field | value |
| --- | --- |
| intended role | ADR-0007 readiness and the M3 joint vocabulary -- **not training data** |
| PII policy (ADR-0005) | not applicable: machine status labels, no person named or described |
| excluded from this source | Hill of Towie (alarm codes, no strings) and CARE (written event descriptions, evaluation-only under CC BY-SA 4.0) |
| not applicable | turbines, channels, timezone, sampling resolution (carried on the two telemetry cards) |

## Caveats

**From the provider.** none beyond the telemetry records' own.

**Found during measurement.** The code book is two Senvion models, not two manufacturers. Membership is by string identity: two strings that differ only in wording are different strings here.

**Known limits of this card.** Readiness is measured against one tokenizer (`text_bpe_v1`); a refit makes every figure above stale.

## Generation

| field | value |
| --- | --- |
| generated (UTC) | 2026-09-16T09:02:23+00:00 |
| git_sha | b86e70e7838b9defb27ef52c6150a2648755438d |
| generated by | faultline cards code-book |
| template | docs/DATASET_CARD_TEMPLATE.md |
| generated from | the staged code book, the Kelmarsh and Penmanshiel status streams, the fitted tokenizer, its training shards and training split |
| hand-written | identity, copied from configs/data/sources_text.yaml and the telemetry cards |
