# Architecture decision records

Each record states what was decided, what was rejected, and what would change the
decision. Records are append-only: a superseded decision keeps its entry and gains a
"superseded by" line, because the reasoning behind an abandoned path is part of the
research record.

> **Note on this file.** This is the only file in the repository permitted to spell
> the strings banned by ADR-0002, because the rule cannot be stated otherwise.
> `tests/test_naming.py` excludes exactly this path and no other.

---

## ADR-0001 Domain and design choice

**Status:** Accepted, qualified on 2026-09-10 by the inventory evidence below ·
**Date:** 2026-09-09

**Decision.** Build a joint telemetry–text sequence model with risk-calibrated
abstention for wind-turbine event risk: one decoder-only transformer pretrained from
scratch over a joint vocabulary of byte-level BPE text tokens, per-channel
quantile-bin telemetry tokens and structural tokens. The endpoint is the probability
of a fault or shutdown event within a horizon, with calibrated abstention, evaluated
under site shift, modality shift and temporal drift.

**Context.** The author needs a research portfolio project that is unmistakably a
language-model project, is scientifically defensible, runs on one RTX 4060 with
8 GB of VRAM, and is visibly independent of their funded and doctoral work.

**Alternatives considered and rejected.**

| alternative | why rejected |
| --- | --- |
| Uzbek-language small language model | Strong evidence of LM engineering, but it establishes a research identity in low-resource NLP that does not connect to the author's fellowship narrative. |
| English energy-domain text-only small LM | No decision endpoint and no telemetry. It would demonstrate pretraining and nothing about risk. |
| Telemetry-only sequence model | Not a language model, and closest of all the options to the author's doctoral work. It also loses the modality-shift axis, which is the most novel part of the evaluation. |
| System-log small LM | Weakest licensing position of the four, and the narrowest literature to situate results in. |

**The data fact that drives the design.** Public SCADA event logs carry
template-like alarm and status messages — a controlled vocabulary of a few hundred
fixed strings — not open-ended language. A model trained on those alone would learn
a categorical code book, not language. The text side is therefore anchored by a
separate public-domain operator-narrative corpus (M2), and the SCADA event logs
serve as a label and structure source.

*Note, 2026-09-16: what the narrative corpus turned out to be.* Measured on the corrected
M2 corpus (run `20260913-142340_all_text_2a6ec5b7`, ADR-0016), it was **single-agency**:
every document came from the U.S. Nuclear Regulatory Commission. **About 23% of it is not
operator narrative:** the four generic-communications collections, which are
regulator-authored guidance, hold 1,448,211 of 6,387,362 whitespace tokens (22.7%). Among
the event notifications, 6,024 of 21,882 (27.5%) are Agreement State reports from
radioactive-materials licensees, not plant events. The framing above still holds, since
it asks for a public-domain narrative corpus and not a multi-agency one, and the change
trigger below has not fired. On the same date PHMSA's 2010-onward pipeline incident
narratives, which are operator-written, were added under ADR-0016's pre-registered rule.
From then on the corpus is two-agency, and this note records the state before that.

**This is the central risk of the project and it is checked, not assumed.**
`faultline inspect telemetry` profiles every status, alarm and event table found in
the staged archives — unique messages, mean message length, share of rows with
non-empty text — and each dataset card records the verdict as `VERIFIED yes`,
`VERIFIED no` or `UNVERIFIED`. If the evidence contradicts the assumption above,
this record is superseded rather than quietly ignored.

**What would change this decision.** Inventory evidence that a public record carries
genuinely open-ended operator prose in volume; or an M2 finding that no adequately
licensed narrative corpus is reachable, in which case the text side is re-scoped and
the change is recorded here.

### Evidence, 2026-09-10 — all four sources inspected

Every tier-1 file is staged and md5-verified (37 files, 17.44 GB), and
`faultline inspect telemetry` has profiled every status, alarm and event table in all
four records, pooling the text across tables. The verdicts, and the measurements they
follow from (`reports/data/raw_inventory_<source>_20260910.md`):

| source | event tables | rows | rows with text | distinct strings | mean length | distinct strings occurring once | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Kelmarsh | 54 status tables | 504,180 | 504,180 | 217 | 14.1 chars, 2.3 words | 14.7% | `VERIFIED no` — a code book |
| Penmanshiel | 98 status tables | 839,303 | 839,303 | 231 | 13.9 chars, 2.4 words | 11.3% | `VERIFIED no` — a code book |
| Hill of Towie | 24 monthly alarm logs | 1,004,341 | 0 | none (429 distinct codes) | — | — | `VERIFIED no` — codes only |
| CARE | 3 `event_info` files, one per farm | 95 | 45 | 35 | 55.9 chars, 8.4 words | 85.7% | `VERIFIED short written descriptions` |

The verdict vocabulary gained a label so that the last row could be said at all. A
code book and a set of short written descriptions are both small and both short; what
separates them is recurrence — a code book's labels recur by construction, while a
description written for one event mostly occurs once — and that is what the verdict
now follows. The thresholds live in `src/faultline/data/telemetry/inspect.py` and every
report prints them beside its verdict.

**The thresholds were chosen after all four sources had been inspected**, so they
describe the data rather than predict it. What makes them defensible anyway is the
margin. The measured singleton shares are 14.7% (Kelmarsh), 11.3% (Penmanshiel) and 85.7%
(CARE), and Hill of Towie has no text to classify, so any singleton-share threshold
between 20% and 80% yields the same classification for all four; the full band runs
from just above 14.7% to 85.7%. `tests/data/telemetry/test_inspect.py` checks that claim
against the tracked reports, so a re-inspection that moves a share out of the band fails
a test rather than quietly changing a verdict.

Three things the table compresses:

- **Kelmarsh.** The "at most 75 distinct strings per turbine-year" quoted in ADR-0007
  came from the first 12 of 54 turbine-years. Over all 54 the most in any one
  turbine-year is 81, and the record-wide code book is 217 strings. The conclusion does
  not move.
- **Hill of Towie.** The alarm log is `TimeOn, TimeOff, StationNr, Alarmcode` and nothing
  else. The only text for its codes is `Hill_of_Towie_alarms_description.csv`, which
  describes 12 codes in 23.8 characters on average. Those 12 cover 88.8% of alarm rows
  but only 8 of the 429 codes that occur, because generator cut-in and cut-out (codes 20
  and 25) are 88% of the log on their own. The held-out site has *less* status text
  than the training sites, not different text.
- **CARE.** Its event descriptions are the only operator-written text in the four
  records: root-cause notes such as "Turbine is stopped due to a main bearing damage",
  some carrying alarm codes or work-order tags, some partly in German (CARE, CC BY-SA
  4.0). Farm A's twelve are short category labels, five distinct; farms B and C carry
  the notes. In all it is 45 strings and about 2,500 characters.

**What this does to the decision.**

(a) **CARE's text cannot be training text, whatever it contains.** CARE is
evaluation-only — `eval_only_sources: [care]` in `configs/data/splits_v0.yaml`, enforced
in `assign_splits` — and it is CC BY-SA 4.0, so anything trained on it would inherit the
share-alike question that `docs/DATA_LICENSES.md` deliberately leaves open. Its
descriptions can serve as labels and as a check on what an event label means; they
cannot pretrain the language-model side. **The M2 operator-narrative corpus is required
regardless of what CARE turned out to hold.**

(b) **The original conclusion is qualified, not restated.** "Public SCADA event logs
carry template-like alarm and status messages — a controlled vocabulary of a few hundred
fixed strings" holds for Kelmarsh and Penmanshiel. For Hill of Towie it overstates
what is there: there is no string vocabulary, only codes. For CARE it is false: the text
is richer than a code book, short root-cause descriptions written per event. That
richness is real, and it is also tiny — 35 distinct strings is not a corpus — and (a)
bars it from training in any case. So the design stands, for a narrower reason than it
was first given: not "public SCADA text is never language", but "the only public SCADA
text that is language is too small to train on and licensed out of training".

**Consequence for ADR-0007, recorded here so it is not rediscovered later.** ADR-0007
routes status *strings* through the text pathway and argues from the held-out site
receiving Siemens messages. The held-out site receives codes. Unless its alarm codes
are rendered as text through a code description — and the provider describes 12 of the
429 that occur — the text pathway has nothing to carry there, and H3 cannot be tested
at that site as stated. TODO(m1): decide how Hill of Towie alarm codes enter the text
pathway, if at all, before ADR-0007 is relied on.

*Closed 2026-09-16.* Measured: 0 of Hill of Towie's 693 narrow events map under the rule,
and H3 is withdrawn on that and two other counts (ADR-0007, "H3 withdrawn"). No alarm-code
rendering is adopted to rescue it.

---

## ADR-0002 Naming discipline

**Status:** Accepted · **Date:** 2026-09-09

**Decision.** The following strings must not appear anywhere in this repository —
source, documentation, configuration, commit messages, branch names — matched
case-insensitively:

- `copilot`
- `VPP`
- `virtual power plant`
- `agent`

One exception: the HTTP header name `User-Agent`, and the Python constant that
carries it in `src/faultline/download/zenodo.py`. The scanner masks
`user[-_ ]?agent` before matching, so the header is permitted and any other use of
the word is not.

Discouraged, and to be avoided in new text without being mechanically enforced:
`assistant`, `chatbot`, `tool-calling`, `operations assistant`.

**Why.** FaultLine must be, and must read as, independent of the author's funded
project work and doctoral research. Those strings carry that other identity. A
reader who encounters them here will reasonably infer that this repository is a
spin-off of work that belongs to someone else, which is exactly the inference the
project exists to avoid — and it is not an inference that a disclaimer in a README
reliably prevents.

The rule also disciplines the design. This project is not an assistant, does not
call tools, and is not instruction-tuned; a vocabulary that keeps reaching for those
words is a sign the scope has drifted.

**Enforcement.** `tests/test_naming.py` scans every git-tracked text file and fails
on any match, exempting only `docs/DECISIONS.md`. The same scan runs as
`faultline check naming`. The scanner itself stores the banned strings reversed
(`src/faultline/naming.py`) so that it does not need to exempt itself — an exemption
list with two entries is one entry away from being a loophole.

**What would change this decision.** Nothing before the project is public and the
independence statement in `docs/PROVENANCE.md` is signed. After that, the rule can be
relaxed only by superseding this record and stating why.

---

## ADR-0003 Joint vocabulary layout

**Status:** Accepted, amended to v2 on 2026-09-09 · **Date:** 2026-09-09

> The v1 decision is kept below verbatim; the v2 amendment follows it. The
> amendment changes the block *order* and replaces count-derived offsets with
> fixed capacities. It does not change what a block contains.

### v1 (superseded by the v2 amendment below)

**Decision.** One identifier space, partitioned into contiguous, disjoint blocks in
this order:

| block | range | contents |
| --- | --- | --- |
| specials | `[0, 32)` | `<pad> <bos> <eos> <unk> <txt> </txt> <tel> </tel> <sep> <nan> <mask>` plus reserved slots |
| text | `[32, 32 + V_text)` | byte-level BPE tokens |
| channel | `[C0, C0 + N_channels)` | one identifier per canonical SCADA channel |
| bin | `[B0, B0 + N_bins)` | quantile bins, **shared across all channels** |
| time | `[T0, T0 + N_time)` | reserved time markers |

Telemetry is emitted as `<tel> (channel, bin) (channel, bin) … </tel>` per timestep.
The channel identity of a bin token is carried by the channel token immediately
preceding it.

**Rationale.** Sharing one bin range across channels keeps the vocabulary compact:
13 channels × 64 bins costs 64 bin identifiers plus 13 channel identifiers instead of
832. On an 8 GB card, embedding and output-projection width is a real constraint, not
an aesthetic one.

Because the blocks are laid out by size and never interleaved, the M1 telemetry
tokenizer and the M2 text tokenizer can be fitted independently against *local*
identifiers and concatenated at M3 without retokenizing anything. The specials block
is oversized on purpose: adding a structural token later must not shift the text or
telemetry ranges, which would invalidate every checkpoint.

**Alternative recorded.** Channel-specific bin identifiers (`N_channels × N_bins`).
Larger vocabulary, no cross-channel bin sharing, but no reliance on the model
learning to condition a shared bin on the preceding channel token. Revisit at M3 if
channel-token conditioning proves weak — for example if probing shows the same bin
identifier is represented identically across physically unrelated channels.

**Consequence to respect.** The canonical channel order in
`src/faultline/data/telemetry/schemas.py` fixes the channel identifiers. Reordering
that list after M1 invalidates every trained checkpoint.

### v2 amendment — fixed-capacity blocks, telemetry first

**Date:** 2026-09-09

**What changes.** The blocks keep their contents and gain two properties: a fixed
capacity, and an order that puts text last.

| block | range | capacity | contents |
| --- | --- | --- | --- |
| specials | `[0, 32)` | 32 | structural tokens plus reserved slots |
| channel | `[32, 96)` | 64 | one identifier per canonical SCADA channel |
| bin | `[96, 1120)` | 1024 | quantile bins, **shared across all channels** |
| time | `[1120, 1184)` | 64 | reserved time markers |
| text | `[1184, 1184 + 32768)` | 32768 | byte-level BPE tokens |

**Every offset above derives from the capacities, never from the counts in use.**
A vocabulary fitted with 13 channels and 64 bins and one fitted with 40 channels and
256 bins put the bin block at 96 and the text block at 1184 alike. Slots between the
count in use and the capacity are reserved: they decode to their block with no name,
and they are not encodable.

**Why v1 was not good enough.** In v1 the text block sat second, at `[32, 32 + V_text)`,
and every telemetry offset was `32 + V_text + …`. That makes every telemetry
identifier a function of a number that is not known until M2. The v1 text says the
two tokenizers can be "fitted independently and concatenated at M3", and they can —
but only by *renumbering* the telemetry side when the text vocabulary size arrives.
Anything already written down in telemetry identifiers is then stale.

That is not hypothetical. M1 tokenizes the SCADA corpus into shards on disk, and
those shards are the expensive artefact: re-emitting them is a full pass over ~20 GB
of archives. Under v1, training the M2 tokenizer invalidates all of them.

**The rule this buys.** *Telemetry identifiers are a stable prefix.* Identifiers
below 1184 are fixed for the life of the project. An M1 telemetry-only vocabulary is
exactly that prefix; M2 fits a text tokenizer of any size up to 32768 against local
identifiers; M3 concatenates by appending, and every M1 shard is still valid, byte
for byte. The bin block is oversized for the same reason the specials block always
was — headroom that is never used costs one integer, and a block that has to move
costs every checkpoint and every shard.

**Cost, stated.** The reserved slots are real: a telemetry-only M1 vocabulary is
1184 identifiers of which around 110 carry meaning, so roughly 91% of the embedding
rows are unused at M1. At M1 widths that is a few hundred thousand parameters — a
rounding error against the activation memory that actually constrains an 8 GB card,
and it shrinks to noise once the text block is populated at M3. Compactness was the
v1 rationale for sharing one bin range across channels, and that part stands: what is
traded away here is a slice of the *embedding table*, not the quadratic part of the
budget.

**What would change this decision.** A measured M1 result where the unused embedding
rows are a material share of the memory budget, which would mean shrinking the bin or
text capacity before any checkpoint exists — not after. After M1 the capacities are
frozen: raising one moves every later block, so it supersedes this record rather than
editing a constant. `VocabLayout.__post_init__` raises on capacity overflow so that
the choice cannot be made by accident.

### Note, 2026-09-12 (M1b step 12) -- the M1 stream carries no channel tokens

The shards M1 trains on use a **fixed-order stream** (`JointVocab.encode_steps`): each step
is `<sep>` followed by one bin token for each core channel in identifier order, so twelve
core channels cost thirteen tokens a step rather than the twenty-five a channel token before
every bin would. Position identifies the channel because every step carries the same
channels in the same order; a missing value is `<nan>` in its channel's position, and a
channel excluded at a source (CARE power, ADR-0011) is `<nan>` throughout. Shards are
`uint16`: every identifier of the telemetry prefix is below 1,184, and the joint vocabulary
with a full text block stays below 65,536.

**The channel block is kept, and reserved.** Its 64 identifiers are not emitted at M1. They
are for the variable-set ablation over extended channels, where a step carries a varying set
of channels and position can no longer say which is which; `encode_telemetry`, a channel
token before each bin, is kept for it. The shared bin range this record chose still needs
conditioning on the channel; in the fixed-order stream that conditioning comes from position
instead of a preceding channel token, and whether it is strong enough stays the M3 probe
recorded above.

**A defect this note fixes.** This record says the canonical channel order fixes the channel
identifiers. The M0 encoder took a channel token's identifier from the channel's position in
the tokenizer's fitted list, which agrees with the canonical position only while a tokenizer
fits a prefix of the canonical list. With the twelve core channels it would have renumbered
every channel after wind direction. The identifier is now the canonical position, checked
against the layout when a vocabulary is built, and tested with a tokenizer fitted in reverse
order. No shard or checkpoint carried the old numbering: no channel token has been written.

### Verified on disk, 2026-09-16 (M3 entry, C1) -- the v2 promise holds

`faultline check joint-vocab` (`reports/data/joint_vocab_check_v1_20260916.md`) checked the
concatenation against the artefacts, not the constants. **All 14 assertions pass.** No id
collides across `[0,1184)` and `[1184,33952)`: 33,952 ids were decoded, and the 274 encodable
telemetry ids and 32,768 text ids share none. All 32 M1 ladder checkpoints embed exactly 1,184
rows. For each of the 8 shard files, the first turbine-year written to it was re-encoded with
the M1 vocabulary and with the joint vocabulary, and both equal the bytes on disk. The highest
id in 193,590,020 shard tokens is 351. The text region is exactly full at 32,768, contiguous,
and the id after it is refused. A telemetry+text fixture round-trips to the single-modality
encodings. Each check is tested to fail on a broken input
(`tests/tokenizers/test_joint_check.py`). **This record is not superseded.**

Observed, not asserted: the M2 text checkpoints embed 32,769 rows, because the text shards
append a local `<sep>` at 32,768. That row has no joint id in the text region. A joint model
initialised from them maps it to the structural `<sep>` (id 8) rather than appending it.

### Migration, 2026-09-16 (M3 pre-run brief, E2) -- asserted, a named function, and the only way in

The observation above is now an assertion, and the mapping is code, not a note.
`faultline.model.checkpoints.migrate_text_checkpoint` locates the separator row from five
independent sources before it maps anything: the text shard manifest's `<sep>`, its vocabulary
size, the tokenizer's size, the checkpoint's row count, and the training streams themselves. All
six streams end in the id, it is the stream maximum, and there are no adjacent separators. All
agree on **row 32,768, the last**, so rows 0 to 32,767 are the BPE ids untouched. BPE row `i`
goes to joint `1,184 + i` bit for bit, and row 32,768 goes to joint id 8. `read_checkpoint`
refuses a 32,769-row checkpoint, and a test fails if any module but `checkpoints.py` calls
`torch.load`. On the real S2 and S3 checkpoints (`faultline check text-migration`,
`reports/data/text_checkpoint_migration_v1_20260916.md`), the row moved to id 8 is +3.2 (S2) and
+4.1 (S3) nats more probable where a held-out document ends than elsewhere, with median rank 3
there. All 4,224 per-string NLLs of the E1 record are reproduced through the migration within
2.9e-6 nats.

**Ruling, 2026-09-16 (E0-E5 ruling, E2): the five sources are not equal evidence.** They answer
two different questions, and only one check answers the one that matters.

- **Where the extra row is: the five sources.** Four of them (the manifest's `<sep>`, the
  manifest's vocabulary size, the tokenizer's size and the checkpoint's row count) establish
  **only that the extra row is the last one, 32,768**. They are sizes and labels written by the
  same pipeline, and an appended row of any kind would give the same four numbers. The fifth, the
  training streams (six of six ending in the id, 31,750 occurrences, no two adjacent), shows that
  the data the model was fed used id 32,768 as a boundary. It is about the data. It does not show
  what the embedding row at that index learned.
- **What the row is: the behavioural check.** The row mapped to id 8 is **+3.2 nats (S2) and +4.1
  nats (S3) more probable where a held-out document ends than elsewhere**, at median rank 3. The
  last BPE row, the row an off-by-one would have taken, shows +0.2 and -0.5
  (`reports/data/text_checkpoint_migration_v1_20260916.md`, section 2). **This is the check that
  establishes the row is a separator.** Mapping a separator onto the structural `<sep>` is only
  correct if the row is one.

The four agreeing sources are a consistency check on the layout, and the migration still
refuses to run if any of them disagrees. They are not four confirmations of the separator's
identity. That rests on the behavioural contrast, one measurement per checkpoint.

---

## ADR-0004 Data licence policy

**Status:** Accepted, amended on 2026-09-10 (republished sources, below) · **Date:** 2026-09-09

**Decision.** Admit only sources that are public domain, CC0, CC BY, CC BY-SA, MIT
or Apache-2.0. Record the licence per file in the download manifest, not merely per
source. Propagate share-alike obligations as described in `docs/DATA_LICENSES.md`.
Exclude any source whose terms are unspecified or unverified — including EDP Open
Data — until the terms are confirmed in writing and recorded in that file.

**Why "per file".** A record can mix licences across its files, and a manifest that
records only a source-level licence cannot answer the question that matters when a
derived artefact is redistributed: which licence attaches to *this* file.

**Why exclude the unverified.** A source with unclear terms is not a small risk taken
for a large gain; it is an unbounded risk taken for one more site. The project is
built to be publishable and reusable, and a single unlicensed corpus makes the whole
thing unpublishable.

**Consequence.** CARE is CC BY-SA 4.0, so any *derived dataset* redistributed from
this repository would carry CC BY-SA 4.0. This repository therefore redistributes no
derived data at all: only cards, manifests and aggregate statistics. Code stays MIT
because code is not a derivative of the data.

### Amendment, 2026-09-10 — a republished source is judged by its republication

**What was wrong with the record as written.** The decision named EDP Open Data as
excluded, and CARE as admitted, without noticing that the two overlap. The CARE README
states that "the data for Wind farm A is based on data from the EDP-open data platform".
Read literally, the record excluded a source and then admitted a republication of it.

**The rule, made explicit.** Two cases are different, and the record now says so:

| case | example | decision |
| --- | --- | --- |
| **Direct use** of a source whose terms are unspecified or unverified | EDP Open Data downloaded from EDP's own platform | **Excluded**, unchanged. A widely used dataset is not a licensed one. |
| **Republished use**: a third party republishes the data under a clear licence, and the chain from the original source to that licence is documented | CARE farm A: EDP Open Data → Fraunhofer IEE, CARE to Compare → CC BY-SA 4.0 | **Permitted**, under the conditions below. |

A republished source is admitted only when all four of these hold:

1. The republisher states a licence explicitly, on a version-pinned record.
2. The republisher states where the data came from. The chain is documented, not
   inferred from similar-looking data.
3. The data is used as republished. It is never joined back to the upstream original,
   because that would be direct use again by another route.
4. The republished part is separable, so a result can be recomputed without it.

**Applied to CARE.** All four hold. (1) CC BY-SA 4.0 on Zenodo record 15846963. (2) The
record README names the EDP Open Data platform as the basis of farm A. (3) Only the CARE
archive is staged, and nothing from EDP's platform is. (4) Farm A is its own directory,
22 of 95 datasets and 5 of 36 turbines. The chain is recorded in
`docs/DATA_LICENSES.md`, in `configs/data/sources_telemetry.yaml`, and on the CARE
dataset card.

**The residual risk, stated.** A republisher can grant only the rights it holds. If the
upstream terms did not allow republication under CC BY-SA, the defect sits upstream of
this project, and a documented chain does not cure it. Condition 4 is what bounds that
risk. Every CARE result is reported with farm A and without it, so a later finding about
the EDP terms costs one column of a table, not the result. CARE also stays
evaluation-only (`eval_only_sources`), so no trained weight depends on farm A.

**What would change this amendment.** Either publisher stating that the republication was
not permitted. That removes farm A, and the sensitivity check means nothing else has to
be rerun.

---

## ADR-0005 PII policy per corpus

**Status:** Accepted · **Date:** 2026-09-09

**Decision.** For FaultLine text corpora, `text.pii.mask_digits` defaults to
`false`; `mask_emails` and `mask_phones` default to `true`. Every corpus records its
own PII setting on its dataset card.

**Context.** The ported course pipeline masks any run of six or more digits with
`<NUMBER>`. On TinyStories that is correct and nearly free: long digit runs there are
noise.

**Why it changes here.** In an operator narrative, quantities *are* the technical
content. "Reactor power held at 850000 kW for six minutes" becomes "reactor power
held at `<NUMBER>` kW for six minutes" — the sentence survives, the physics does not.
A model whose purpose is reasoning about equipment state must be able to read
magnitudes.

Email addresses and phone numbers are different: they identify people, they carry no
technical signal, and masking them costs nothing.

**Residual risk, acknowledged.** Digits can be identifying — a badge number, a phone
number in an unusual format the phone pattern misses. This is why the decision is
per corpus and recorded on each card rather than set globally, and why a narrative
corpus admitted at M2 must be spot-checked for identifiers before it is enabled.

**Observed defect, deferred rather than hidden.** The M0 fixture run
(`reports/data/20260908-221358_all_text_34e5612d/pii_stats_report.md`) shows the
inherited phone pattern masking the sentence "Serial number 8812349900 was recorded
on the replacement bearing" as `Serial number <PHONE>`. The course regex,
`(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)`, matches any run of nine or more digits, so
in a maintenance corpus it eats serial numbers, work-order references and asset tags
— exactly the identifiers that tie a narrative to a machine.

Turning `mask_digits` off therefore does **not** fully protect technical content; the
phone pattern still does damage that digit masking was blamed for. The regex is left
unchanged at M0 because the port is meant to be checkable against the original
(`docs/COURSE_PORT.md`), and because the fixture corpus is the wrong evidence base for
redesigning it.

**Resolved in part, 2026-09-09.** `configs/data/text_v1.yaml` selects a replacement
pattern anchored on telephone formatting — an explicit country code, or separated
groups of at least two digits in one of three conventional shapes — instead of on
digit count. It still masks `+44 1234 567890` and `020 7946 0958`; it no longer masks
`Serial number 8812349900`. `text_v0.yaml` is untouched and still selects the course
regex, so the port stays checkable, and the defaults in code are v0. The golden diff
test enumerates every string the two versions disagree on.

That does **not** settle the second half of the request above.
**TODO(m2): measure v1's false-positive rate against the real narrative corpus before
trusting it there.** A pattern validated on nine hand-written cases and a synthetic
fixture is a pattern that has not met real text. Until that measurement exists, any
corpus enabled at M2 records this limitation on its card.

---

## ADR-0006 Telemetry canonical schema and missingness as a feature

**Status:** Accepted · **Date:** 2026-09-09

**Decision.** Two canonical shapes:

- **SCADA**, long form `(source, site, turbine_id, timestamp_utc, channel, value)`,
  stored wide — one column per channel — in one Parquet file per
  `(source, turbine, year)`.
- **Events**, `(source, site, turbine_id, start_utc, end_utc, code, message,
  category, is_fault, raw)`, with the provider's original row preserved verbatim in
  `raw`.

**Every imputed value travels with a boolean `<channel>__imputed` companion column,
and that column is a model input, not bookkeeping.**

**Why wide-per-turbine-year.** It is the layout a windowed sequence model reads, and
it caps peak memory at one turbine-year (~52,000 rows at 10-minute resolution) — a
real constraint on a workstation with 32 GB shared with everything else. The long
form is kept for inspection and per-channel statistics, where it is far more
convenient.

**Why `raw` is preserved.** Normalisation is lossy and the fault-code mapping is
unresolved at M0. Keeping the original row means a later mapping revision does not
require re-ingesting 17 GB of archives.

**Why missingness is a feature.** Sensors and communication links fail, and they
fail disproportionately around the events this project predicts. A model that cannot
distinguish "measured 0" from "invented by interpolation" will be scored partly on
its own guesses, and modality shift — the axis where channels are deliberately
dropped at inference — becomes impossible to interpret. Short gaps are filled up to
`impute.max_impute_steps`; longer gaps are never filled, they end a segment.

**Related rule.** Unmapped event codes yield `is_fault = None`, never `False`.
Silence about a code is not evidence that it is benign, and defaulting to `False`
would silently inflate precision.

### Resolution, 2026-09-11 (M1b step 10) -- a feature where it recurs, an artifact where it cannot

"Missingness is a feature" and condition (c) of ADR-0008 ("a gap must not be a label
shortcut") read as if they pulled against each other: the first keeps gaps visible to the
model, the second asks whether the model could learn from them. They answer different
questions, and the test that separates them is **whether the pattern occurs at
deployment**, which for this project means at the held-out site.

- **A feature** is missingness whose pattern recurs where the model is used: a link that
  drops out around a stop, a sensor that fails as a component degrades, a turbine that
  goes silent in a grid event. The model should see it, through `<nan>` and the
  `__imputed` companions, and may learn from it.
- **An artifact** is missingness whose pattern cannot recur there: an instrumentation
  outage specific to one training site and one period. A model that learns from it learns
  a fact about the training data's history, and is scored on nothing like it.

Penmanshiel's spring-2018 gap is an artifact by that test. Ambient and nacelle temperature
are non-null on 99.6% of the held-out grid, in both of its years, so the held-out site
never presents the pattern the model would have learnt at Penmanshiel. **The remedy for an
artifact is to remove the artifact, not the channel**: the outage's spans are withheld from
training windows (`training_exclusions`, `splits_v2.yaml`), and both channels stay core.
Which gaps may be treated so, and which may not, is bounded in ADR-0008.

---

## ADR-0007 Status messages go through the text pathway, not a code book

**Status:** Accepted, justification replaced 2026-09-16 (**H3 WITHDRAWN on evidence**; the
decision is kept, the transfer argument is not, see "H3 withdrawn" below) · **Date:** 2026-09-09

**Decision.** Status and alarm messages from the SCADA event logs are encoded
through the **text pathway** — the byte-level BPE tokenizer, emitted inside
`<txt> … </txt>` — and **not** as categorical tokens in a block of their own. The
event `code` and `category` fields stay structured and keep their role as label and
structure sources (ADR-0006); this record is about the message *string*.

**Context, and why the obvious answer is the wrong one.** ADR-0001 rests on the
finding that these messages are a controlled vocabulary rather than prose, and the
inventory confirmed it: `VERIFIED no` for Kelmarsh, at most 75 distinct strings per
turbine-year with a mean length of 14.7 characters. The natural reading of that
finding is "so encode them categorically" — one identifier per distinct message,
like the channel tokens. That reading is wrong, and it is wrong for the same reason
the finding was worth checking.

**Why not a code book.**

1. **A code book is per-OEM, and the headline result is leave-site-out.** Kelmarsh
   and Penmanshiel are Senvion; Hill of Towie is Siemens and is the held-out site.
   A code book fitted on the training sites has no identifier for a Siemens message,
   so every status message at the held-out site becomes `<unk>` — on precisely the
   axis the project reports. The text side would contribute nothing exactly where it
   is supposed to contribute most.
2. **The strings are compositional English, and subwords cross the OEM boundary.**
   "Overload generator fan 1", "Battery charge cycle axis 2 error", "Gearbox warm-up
   stage", "Absence of wind during run-up". A code book treats
   `Overload generator fan 1` and `Overload generator fan 2` as unrelated symbols.
   BPE does not, and the same subwords appear in the narrative corpus and in the
   canonical channel names. A different manufacturer describing the same failure in
   different words still shares most of the vocabulary.
3. **Choosing a code book now would be choosing it permanently.** Under ADR-0003 v2
   the blocks have fixed capacities and text sits last. A categorical message block
   would have to be carved out of the prefix, which moves the text offset and
   invalidates every shard and checkpoint after it. Routing messages through the
   text block costs no new block at all. A decision that cannot be revisited should
   not be made on convenience.

**What this gives up, stated.** A code book is cheaper: one token per message
against roughly four or five BPE tokens, and exact message identity available to the
model for free. The text route spends sequence length on strings that carry little
entropy *within* a site — "System OK" and "Wind < start wind" together are over 80%
of the status rows in every Kelmarsh turbine-year inventoried. The cost is bounded,
because status rows are sparse next to 10-minute telemetry, but it is a real cost and
not a free lunch.

**Consequence for the text pipeline.** Routing these strings through the text
pathway puts them through the text cleaning stage, and the second most common
Kelmarsh status message is `Wind < start wind`. The inherited tag-stripping regex
`<[^>]+>` consumes everything between a `<` and the next `>`, so a message with a
`<` followed anywhere later by a `>` is silently gutted. That defect was recorded in
`docs/COURSE_PORT.md` as harmless on TinyStories; this decision is what makes it not
harmless, and `configs/data/text_v1.yaml` is where it is fixed.

**H3, the hypothesis this creates — tested at M3.**

> **H3.** Pretraining on the operator-narrative corpus improves cross-OEM transfer of
> status semantics under leave-site-out evaluation, relative to the same joint
> architecture with the narrative pretraining ablated.

Made falsifiable: the joint model's held-out-site advantage over the telemetry-only
M1 model should be **larger** for event types whose status strings share vocabulary
with the narrative corpus than for event types whose strings do not. If the
advantage is flat across that split, the text pathway is carrying site identity
rather than meaning, H3 is false, and this record is superseded rather than the
result being reported as support for it.

*Pre-M3 measurement, 2026-09-16: the wind vocabulary gap H3 will be tested against.*
Recorded before M3, so that a flat H3 result is not blamed on the text pathway alone.
The status code book (`data/raw/text/status_code_book.jsonl`: 264 strings, 297 word
types, 883 word tokens) was compared with the **NRC-only** training split of run
`20260913-142340_all_text_2a6ec5b7`. **191 of 297 word types (64.3%) occur at least 100
times, covering 70.2% of code-book word tokens; 266 (89.6%) occur at least once. Only
76 of the 264 status strings have every word seen at least 100 times.** 31 word types
are absent entirely: `adaption, anemometer, asymmetry, autounwind, bladeangle, conv, dev,
drivetrain, earthed, electr, err, freq, implausible, login, mains, mconfig, nacelle, nat,
obstacle, overfrequency, parameterized, parkmaster, pmu, rotorbearing, sntp,
synchronisation, thermistor, transf, twistangle, winddirection, yaw`. Seen only 1-99
times, among others: `pitch, rotor, gearbox, converter, icing, gust, stator, vane, rpm,
brake, lubrication, curtailment`. The corpus supplies the generic electrical and
mechanical vocabulary (generator, turbine, breaker, transformer, pump, battery). What it
lacks is the wind-specific vocabulary. The "shares vocabulary with the narrative corpus"
split above is therefore drawn against a nuclear, and since 2026-09-16 nuclear plus
pipeline, corpus. PHMSA is not expected to close the wind-specific gap; that
expectation is not yet measured, and the split is re-measured against the corpus the
M2c fit actually uses (Gate 6 report).

*Testability gate, 2026-09-16 (`reports/data/h3_vocab_overlap_v1_20260916.md`,
`faultline inspect vocab-overlap`).* The split was re-measured under three conditions so the
held-out share change (`4b8caa3`) is not read as PHMSA's contribution: NRC only at the old
shares 191/297 types, 76/264 strings (re-derived, matching the record); NRC only at the new
shares 190/297, 76/264 (`resistor` fell from 117 to 78); NRC + PHMSA 199/297, 80/264. PHMSA
moves eleven code-book words (`mains` and `login` from absent; nine past 100) and **no wind
term**; `compressor`, `valve` and `corrosion` rose in the corpus but are not code-book words,
and `pressure` was already frequent, so none of them moves the split. **The pre-registered
gate fired.** Under the rule (an event's type is the status string that opens it), **0 of Hill
of Towie's 693 narrow events and 0 of CARE's 45 anomalies map to either side**: the held-out
site's only described messages are generator switching, lubrication, wind and icing, none of
them technical, and CARE has no status strings. Even at the training sites, where every event
maps, the high-overlap side holds 2 event types. **H3 as worded is not testable at this data
scale**; Part C of the M3 entry brief was not started. What replaces the test is not decided
here.

The ablation is the test, not the joint-versus-telemetry comparison on its own: a
joint model can beat a telemetry-only model by having more parameters.

**H3 WITHDRAWN, 2026-09-16: on evidence, not deferred.** H3 is not postponed to a
larger corpus or a later milestone. It is withdrawn, because the three measured counts
that decide whether it can be tested all say it cannot:

1. **Hill of Towie, the held-out site: 0 of 693 narrow events map to either side of the
   split.** Its only described messages are generator cut-in and cut-out (non-stopping),
   pitch lubrication and cable untwisting (planned), and low wind, high wind and icing
   (environmental). None of them is technical, so none can be the type of a fault event.
2. **CARE: 0 of 45 anomalies map.** CARE publishes no status strings.
3. **At the training sites, where every event does map, the high-overlap side holds 2
   event types** (Kelmarsh: drive train monitor level 2, safety chain open; Penmanshiel:
   the same two). A per-type advantage cannot be compared across a side of two types.

**The lenient Hill of Towie mapping is rejected, not adopted.** Labelling each event with
the last described alarm before it clears the gate's count (639 high, 54 low). It clears
it by naming a fault after whichever generator alarm fired last, almost always `Fast
cut-out of generator` or `Large generator Cut-in`, which fire about 442,000 times each.
That measures which text sits next to a fault, not what the fault was. A split built on
it would test nothing about status semantics.

**The negative result is a deliverable, and is recorded as one.** *The premise that a
nuclear and pipeline regulatory narrative corpus supplies wind-turbine status vocabulary
is false at the lexical level.* Measured (`reports/data/h3_vocab_overlap_v1_20260916.md`):
29 code-book word types are absent from the NRC + PHMSA training split, among them `yaw`,
`nacelle`, `anemometer`, `drivetrain`, `bladeangle` and `rotorbearing`. Adding PHMSA,
9,267 training documents and 1,969,035 BPE training tokens, **moved zero wind-specific
words**. The eleven code-book words it did move (`mains`, `login`, `plc`, `pads`, ...) are
generic electrical or plant vocabulary, and they moved the string split from 76 to 80 of
264. At the token level, which is what the model sees, 18 of 264 strings have every token
frequent (`data/cards/status_code_book.md`).

**ADR-0007's decision is KEPT; its justification is REPLACED.** Status strings still go
through the text pathway. **H3's transfer justification did not survive measurement.** The
decision above argued that subwords shared with the narrative corpus would carry status
meaning across manufacturers. That argument is withdrawn with H3. The replacement
justification is pragmatic, and it makes no claim about transfer:

- **A per-OEM code book would not transfer either.** Hill of Towie's eight described strings are
  distinct from Kelmarsh's and Penmanshiel's, and they are not in the training code book, so
  a code book fitted on the training sites gives them no identifier. The text pathway at
  least encodes them.
- **The joint vocabulary is frozen.** ADR-0003 v2 fixes the text block at `[1184, 33952)`.
  A categorical message block would have to be carved out of the telemetry prefix, which
  moves every later identifier. Routing strings through the text block needs no new block.
- **The cost is small and measured.** A status string costs a median of 5 BPE tokens (mean
  5.47, p95 9, max 20; `data/cards/status_code_book.md`), and status rows are sparse next
  to 10-minute telemetry.

Nothing in the replaced justification predicts that narrative pretraining helps the status
strings. Any M3 result that bears on that question is reported as a new measurement. It is
not a test of H3. The cheap residual question H3 leaves, whether the barrier is surface
convention or vocabulary, is registered as H3' in ADR-0017.

**What would change this decision.** An M2 finding that no adequately licensed
narrative corpus is reachable, which removes the mechanism H3 depends on and
re-opens the code book; or an M3 probe showing message representations cluster by
site rather than by meaning.

*2026-09-16: the first condition is superseded along with H3.* The decision no longer
depends on the narrative corpus supplying anything. What would change it now: a measured
sequence-length cost from status strings that is material against the M3 context budget,
or a held-out source whose status text a code book covers and BPE does not.

**Evidence note, 2026-09-10.** Two facts above were measured on part of the data and
have since been measured on all of it; see the evidence section of ADR-0001. Pooled over
all 54 Kelmarsh turbine-years, the most distinct strings in one turbine-year is 81, not
75. And the held-out site, Hill of Towie, publishes alarm codes with no message strings
at all, so point 1's "every status message at the held-out site becomes `<unk>`" has no
messages to apply to until its codes are given text. The decision is not changed by
this note; its TODO(m1) is recorded in ADR-0001.

---

## ADR-0008 The core channel set is derived from the channel maps and frozen

**Status:** Accepted, amended on 2026-09-11 (M1b step 10: core is the maps and three
measured conditions; below) · **Date:** 2026-09-10

**Decision.** A canonical channel is **core** when it is present at both training
sites (Kelmarsh, Penmanshiel) *and* mappable at the held-out site (Hill of Towie).
Everything else is **extended**. The set is derived from the resolved channel maps by
`channels.derive_core`, and not declared. It is frozen, with a one-line evidence note
per channel, in `configs/data/telemetry_v1.yaml`:

- **core, 13:** wind speed, power, rotor speed, generator speed, pitch, nacelle
  position, wind direction, ambient temperature, nacelle temperature, gearbox oil
  temperature, generator bearing temperature, generator winding temperature, main
  bearing temperature;
- **extended, 1:** gearbox bearing temperature. Both Senvion signal mappings verify it
  absent, while the held-out site publishes four.

**What changed from M0.** M0 declared eight core channels on Kelmarsh evidence alone.
The five drivetrain and enclosure temperatures joined core once Penmanshiel's and Hill of
Towie's maps showed them on both sides of the split. The canonical *order* does not
change, so no channel token identifier moves (ADR-0003).

**The leave-site-out rule now runs on the maps, not on declarations.**
`splits.check_eval_channels_against_maps` derives the core set from the maps and rejects
any evaluation channel outside it. The final stage calls it, and a test calls it on the
shipped split specs. The tiers in `schemas.py` repeat the frozen set, because config
validation must not read files, and `tests/data/telemetry/test_core_channels.py` fails
if the declaration, the frozen config and the maps ever disagree.

**Three things this does not settle, recorded so they are not rediscovered.**

1. *Mappable is not present.* Hill of Towie's wind direction is described in the
   provider's lookup and present in the 2023 export, but absent from every month of
   2019. It is core by the rule, and half the staged held-out period reads it as
   missing.
2. *The generator bearing is matched by inference.* The Senvion maps take the "front"
   bearing and Hill of Towie's is taken at the drive end, on the reasoning that a
   generator's front faces the gearbox that drives it. Neither provider states this.
3. *Coverage is measured later.* M1a step 8 measures per-site missingness on the core
   channels. A core channel that turns out mostly missing at a site is demoted in
   `telemetry_v2.yaml`, and this record gains a "superseded by" line; nothing is edited
   in place.

**What would change this decision.** The step-8 coverage table, or a new training or
held-out site whose map lacks a core channel.

**Evidence note, 2026-09-11 -- the step-8 coverage table exists.**
`reports/data/missingness_20260910.md` (`faultline inspect missingness`, telemetry_v2)
measures every core channel per site on the cleaned grid. Point 1 above is now a number:
Hill of Towie's wind direction is non-null on 49.8% of the held-out grid -- 0% in 2019
and 99.5% in 2023, and each year is half the grid -- while every other core channel there
is at 99.6%. Penmanshiel's pitch angle (70.0%) and gear-oil temperature (70.2%) are the
only training-site core channels below 94%, and almost all of their missing steps sit in
gaps of a week or more, whole turbine-years among them. At CARE, which is evaluation-only
and mapped per farm, nacelle temperature and generator bearing are at 22.7% and nacelle
position and wind direction at 39.0%. This record said a core channel "mostly missing at a
site is demoted in telemetry_v2.yaml"; telemetry_v2 was written before this table, by the
order of the work, and demotes nothing. Whether any of these is demoted is gate 2's
decision and would be a telemetry_v3.yaml; this note supersedes nothing.

### Amendment, 2026-09-11 (M1b step 10) -- core is the maps and three measured conditions

**Status of the rule above:** the definition "present at both training sites and mappable
at the held-out site" is superseded by this amendment. It stays necessary; it is no longer
sufficient. `telemetry_v3.yaml` freezes the result, `faultline inspect core` measures it
(`reports/data/core_rule_20260911.md`), and v0-v2 are untouched.

**The result: core = 12.** Wind direction is extended. Ambient and nacelle temperature,
pitch and gear oil stay core, with no exception recorded for any of them.

| channel | K | P (outside exclusions) | H (2019, 2023) | outcome |
| --- | --- | --- | --- | --- |
| `wind_direction_deg` | 96.0% | 97.5% (97.4%) | 49.8% (0.0%, 99.5%) | **extended**: fails (a) |
| `ambient_temp_c`, `nacelle_temp_c` | 95.2% | 94.5% (96.9%) | 99.6% (99.7%, 99.5%) | core: the spring-2018 outage is withheld from training; outside it (c) does not arise |
| `pitch_angle_deg` | 95.2% | 70.0% (71.9%) | 99.6% (99.7%, 99.5%) | core: (c) clears, matched ratio 0.95 (0.83-1.09) |
| `gearbox_oil_temp_c` | 95.3% | 70.2% (72.1%) | 99.6% (99.7%, 99.5%) | core: (c) clears, 0.95 (0.83-1.08) |
| `gearbox_bearing_temp_c` | 0.0% | 0.0% | 99.6% | extended, as before: fails the maps and (b) |

Every other core channel is at 95.9% or more at both training sites and 99.6% at the
held-out site. The leave-site-out validation now rejects any split specification that
evaluates wind direction with a site held out, `splits_v0.yaml` and `splits_v1.yaml`
included: they are left as written and no longer load, and every report that read them
stays regenerable from the commit it landed in. The channel keeps its position, so no
token identifier moves (ADR-0003).

#### The rule, and the two corrections that led to it

The record keeps both corrections, not only the rule that survived them.

**First correction: the single threshold.** The rule first proposed at gate 2 was "present
at >= 95% on the clean grid at every site used for training or held-out evaluation". It
failed on first contact. It demanded exceptions at once: Penmanshiel's pitch (70.0%) and
gear oil (70.2%), and ambient and nacelle temperature (94.5%), all of which gate 2 had
kept core. And it turned on differences that measure nothing: ambient temperature at
94.5% at Penmanshiel failed, at 95.2% at Kelmarsh passed. A threshold that has to be
excused the day it is written describes a preference, not a rule. It was replaced, not
excepted.

**The three conditions that replaced it**, all of which must hold for a mappable channel:

- **(a) Held-out integrity.** >= 95% non-null on the cleaned grid at every held-out site,
  and availability not confounded with an evaluation axis: >= 95% in every calendar year
  there as well as pooled.
- **(b) Training sufficiency.** >= 95% at one training site at least, and genuinely
  measured (> 0%, not structurally absent) at every one.
- **(c) No label shortcut.** Where a training site measures the channel below 95%, its
  missingness is shown not to be label-informative.

**Second correction: condition (c) was under-specified.** As first written, (c) compared
the event rate of affected against unaffected turbine-years, with no regard to the
calendar. Block missingness and event rates are both time-structured, and a raw
missing-against-present comparison cannot separate the two. The evidence that it could not:
on the same two channels it gave opposite answers depending on which comparison was taken.
Pitch and gear oil **passed** at train level (rate ratio 0.90, 0.79-1.03, affected against
unaffected turbine-years) and **failed** within 2018 (0.23, missing against present steps).
The second comparison sets January-May against June-December; the first sets 2016-2017
against 2019-2020. Neither holds the season fixed.

**The fix: a seasonally matched control.** (c) now compares the affected calendar window
with the same window in other years at the same site. In general form: a turbine-day is
affected when the channel is missing on more than 5% of its reporting steps; within each
calendar month, affected turbine-days are set against unaffected turbine-days of that month,
which for a site-wide gap lie in other years; the rate ratio is pooled over months
(Mantel-Haenszel, Greenland-Robins interval). It **clears** when the 95% interval contains 1
and lies within [0.5, 2] -- a halving or a doubling is the size of difference this project
already treats as material -- **does not clear** when the interval excludes 1, and is
**inconclusive** otherwise. That reading was fixed in code before any number was
computed. Its intervals are Poisson and take no account of year-to-year variation beyond
the count's own, which is real (below); they are the narrowest defensible intervals, not
the widest.

#### The control for Penmanshiel's spring-2018 gap, as asked, and what it says

February to May at Penmanshiel, narrow events per turbine-year with Poisson intervals and
the 24-hour narrow base rate, every turbine pooled:

| year | turbine-years | narrow events | per turbine-year (95%) | 24 h base rate |
| --- | --- | --- | --- | --- |
| 2016 | no grid: the record starts in June 2016 | - | - | - |
| 2017 | 4.60 | 33 | 7.2 (4.9-10.1) | 1.57% |
| **2018** | 4.60 | 13 | 2.8 (1.5-4.8) | 0.77% |
| 2019 | 4.60 | 26 | 5.7 (3.7-8.3) | 1.42% |
| 2020 | 4.64 | 102 | 22.0 (17.9-26.7) | 4.34% |
| 2017, 2019, 2020 pooled | 13.84 | 161 | 11.6 (9.9-13.6) | 2.45% |

Rate ratio, 2018 to the other years: **0.24 (0.14-0.43): does not clear.** Spring 2018 is
below every other year's spring, not merely below the pool that 2020 inflates. On the
outage's own calendar days (1 March to 16 May) the ratio is 0.49 (0.22-1.09):
inconclusive. The general month-matched form gives 0.44 (0.22-0.88) on the whole grid,
against a crude 0.23: matching halves the apparent effect, and does not remove it. The
control does not clear the correlation. It is reported as it came out.

#### The exclusion, and why it rests on the instrumentation

The spring-2018 block is withheld from **training windows only**. The rows stay in every
table; no evaluation window is touched, because none lies in 2018; a training window whose
144-step context touches a span is not admitted, and the leakage re-check fails if one is
(`windows.window_ends`, `assert_windows_within_splits`).

The ground is the instrumentation, not the event rate. What the cleaned grid shows is a
bounded, site-wide, simultaneous outage: at every one of Penmanshiel's 14 turbines, ambient
and nacelle temperature are missing on 100% of the reporting steps of each span, and
present on 93-100% of the site's reporting steps in the week before and after. That is
unrepresentative operating data, and it would be excluded on that ground **whatever the
event rate showed**. The control above decides nothing about the exclusion; it is recorded
because it was asked for, and because a reader should see that the low spring rate was
looked at and not explained away.

The block is not what the gate described, in three ways, measured
(`reports/data/core_rule_20260911.md`):

1. **Four channels, not two.** Pitch and gear oil are missing on the same steps: 100% of
   the reporting steps in both spans. For them the outage continues an absence that began
   with the record, so they are not listed as the outage's channels -- the "bounded" test
   fails for them at the first span's start by construction -- and the report names them
   beside it.
2. **Two spans, not one Feb-May block.** 2018-03-01 00:00 to 04-05 13:40 UTC, and 04-21
   05:40 to 05-16 10:10. All four channels return for the 16 days between, and those days
   are kept.
3. **Turbine-specific edges are not excluded.** Penmanshiel 01 misses ambient and nacelle
   temperature from 8 February to 31 May, and Penmanshiel 02 from 27 February (the turbine
   itself silent to 5 March). Those extra turbine-days (127) are not site-wide, so by the
   bound below they stay, and they count against the channel: outside the spans, ambient and
   nacelle temperature are at 96.9% at Penmanshiel, so (c) does not arise for them.

| excluded span (UTC) | grid steps | turbine-years | share of Penmanshiel's training steps | share of all training steps |
| --- | --- | --- | --- | --- |
| 2018-03-01 00:00 to 04-05 13:40 | 71,722 | 1.36 | 2.16% | 1.47% |
| 2018-04-21 05:40 to 05-16 10:10 | 50,792 | 0.97 | 1.53% | 1.04% |
| **both** | **122,514** | **2.33** | **3.69%** | **2.51%** |

On the final tables, which windows are drawn from
(`reports/data/20260911-125811_final_telemetry_54a0a17d`), the spans hold 121,849 training
rows: 3.79% of Penmanshiel's and 2.57% of every training site's. **125,567 training windows
are withheld at each horizon**, the spans' rows plus the windows whose day of context
reaches into them: 4.00% of Penmanshiel's known 24-hour training windows (3,137,111 to
3,011,544) and 2.72% of all training windows. They carry 1,008 of Penmanshiel's 76,717
positive 24-hour windows (1.3%), so its training base rate moves from 2.45% to 2.51%: the
low spring rate, withheld with the outage rather than chosen for. Validation and the late
test are unchanged, window for window.

#### The bound, so that (c) keeps its teeth

An exclusion is permitted **only** for a bounded, site-wide, simultaneous outage: every
turbine of the source, two channels or more, one contiguous span. `TrainingExclusion`
enforces the shape (two distinct channels at least, a span that ends after it starts, a
stated reason, a training source, nothing past `train_until`), and `faultline inspect core`
measures the substance on the cleaned grid: every turbine reports in the span, each misses
every listed channel on >= 95% of its reporting steps there, and the site publishes the
channels on more than half its reporting steps in the week either side. **Dispersed or
turbine-specific missingness demotes the channel instead**, or passes (c); it is never
excluded. Without the bound, "exclude the gap" would be an answer to every failed (c), and
the condition would test nothing.

**Pitch and gear oil are an era, not an outage.** They are absent from the start of the
record (June 2016) at every turbine to spring 2018: 42 of 70 training turbine-years, none in
validation or the late test. That is a documented train/evaluation mismatch, not a defect,
and it is not excluded: an era is not bounded, and excluding it would remove 2016-2017 from
training. They pass (c) at train level (0.90, 0.79-1.03, unmatched) and under the matched
control (0.93, 0.82-1.06 on the whole grid; 0.95, 0.83-1.09 outside the exclusions), and
stay core with no exclusion.

#### Core-10 costs nothing to revisit

A core-10 evaluation -- ambient and nacelle temperature demoted as well -- is derivable from
core-12 shards by masking those two channels to `<nan>`, the mechanism modality dropout
already uses (M3). Core-12 shards therefore yield core-10 for free, while the reverse would
mean re-tokenising the corpus. The demotion that was not made here can be revisited
empirically at M1c, by scoring the same checkpoints both ways, at no cost.

**Also from step 10.** Hill of Towie results are always reported per calendar year as well as
pooled, never pooled only (`per_year_sites`): its two years sit either side of a retrofit,
and only 2023 publishes wind direction.

**What would change this amendment.** A held-out site where ambient or nacelle temperature
shows an outage of the same shape, which would make the pattern one that recurs at
deployment; a training-site gap that is site-wide but unbounded, which the bound would send
to (c) or demotion; or an M1c result where core-10 beats core-12 at the held-out site.

### Amendment, 2026-09-12 (M1c gate 3) -- the Feb-May control was uninformative

**What this amendment does and does not change.** The Penmanshiel spring-2018 training
exclusion **stands**, unchanged, on the instrumentation gap alone. The amendment above
already rests it there -- "the ground is the instrumentation, not the event rate", and the
block "would be excluded on that ground whatever the event rate showed". What is recorded
here is that the control reported beside it could not have discriminated an artifact from
ordinary variation, so it should not be read as evidence either way.

**The tolerance band was narrower than the site's own inter-year spread.** Condition (c)
clears a channel when the 95% interval contains 1 and lies within [0.5, 2]: "a halving or a
doubling is the size of difference this project already treats as material". Penmanshiel's
February-to-May event rate varies by more than that between ordinary years. Taking each year
of the control table above against the pool of the other three -- the same comparison the
control makes for 2018, point estimates only, no interval:

| year against the other three | narrow events per turbine-year | the other three pooled | rate ratio | against [0.5, 2] |
| --- | --- | --- | --- | --- |
| 2017 | 7.2 | 10.2 | **0.70** | inside |
| 2018 | 2.8 | 11.6 | **0.24** | fails |
| 2019 | 5.7 | 10.7 | **0.53** | at the band edge |
| 2020 | 22.0 | 5.2 | **4.21** | fails |

Three of the four years fail the band or sit on its edge. A band that two ordinary years
(2019, 2020) cannot stay inside does not separate an instrumentation artifact from a
year like any other: 2018's 0.24 is the lowest of the four, but 2020's 4.21 is further from
1 than 2018's is, and nothing was wrong with 2020's instrumentation. The control did not
discriminate, and this record does not claim it did.

**What follows.** The exclusion keeps its stated ground and its bound: a bounded, site-wide,
simultaneous outage, measured on the cleaned grid. Condition (c) keeps its band, because
nothing better is available from four years of one site; what changes is that a (c) verdict
is now read beside the site's own inter-year spread, and a "does not clear" is not read as
evidence of a label shortcut where that spread is wider than the band.

**Reports generated with `splits_v0.yaml` or `splits_v1.yaml` are historical and are no
longer reproducible with the current code**, because both specifications now fail validation:
they name `wind_direction_deg` in `eval_channels` with a site held out, which the
leave-site-out rule rejects since the amendment above. The amendment's own sentence -- "every
report that read them stays regenerable from the commit it landed in" -- is true only of the
commit each report landed in, with the code as it stood there. It is not true of this tree
and was not meant to claim otherwise. The files stay as written; they are not edited to load.

---

## ADR-0009 Label harmonisation: one event rule for every site

**Status:** Accepted · **Date:** 2026-09-11

**Decision.** Every source is reduced to one table -- seconds of downtime per turbine and
10-minute step, split into five causes: `technical`, `environmental`, `grid`, `planned`,
`unknown` (IEC 61400-26 style) -- and one function turns that table into events. An
event is a run of consecutive steps holding downtime of the chosen causes, lasting at
least 60 s (`harmonise.select_events`, which takes no source argument). The **narrow**
label, primary, keeps technical downtime only; the **broad** label, secondary, keeps any
cause. Both are labelled at 1 h, 6 h and 24 h, and a label whose horizon runs past the
record the events were read from is unknown (NA), never False (ADR-0006). The
translation of each provider's vocabulary into the five causes lives in
`configs/data/events_v2.yaml` beside its evidence; `events_v1.yaml` is untouched.

**Context: gate 1.** Under events_v1 the sites counted 19.5 (Kelmarsh), 24.8
(Penmanshiel) and 212.6 (Hill of Towie) events per turbine-year, because they counted
different things: equipment-fault status rows at the Senvion sites, downtime runs of any
cause -- low wind included -- at the Siemens site. Gate 1 decided to narrow the held-out
site's events and not to widen the training sites. Widening would admit wind-lull stops,
which the wind-speed channel predicts trivially and which mean nothing operationally: it
would inflate AUPRC and empty the false-alarm rate and the detection delay of meaning.

**Rung (a) of the ladder held: the held-out site publishes a cause.**
`ShutdownDuration.csv` is `TimeStamp_StartFormat, TurbineName, ShutdownDuration` and
`tblAlarmLog` is `TimeOn, TimeOff, StationNr, Alarmcode`; neither carries a cause or
availability category. `tblSCTurFlag` ("Turbine status information [10min]") does: per
turbine and step, the seconds spent in four stop classes. `wtc_ScTurSto_timeon` is the
provider's "Time turbine error active in period". `wtc_ScEnvSto_timeon`,
`wtc_ScComSto_timeon` and `wtc_ScGrdSto_timeon` are not described; they are read as
environmental, commanded (planned) and grid stops from their names and from
`tblDailySummary`, which counts the same four classes as `StopsEnvironmental`,
`StopsCommanded`, `StopsTurbineFault` and `StopsGridFault`. The described codes agree
with that reading: high wind (8000) runs under Env on 99.1% of occurrences, icing (8230)
on 100%, cable untwisting (10105) on 99.7%. Low wind (1005) runs under none of the four;
low wind is not a stop class, so that downtime is `unknown` and enters the broad label
only. Rung (b), exclusion by wind state, was therefore not needed as the rule; the wind
state of every narrow event is measured as a diagnostic instead.

**Pitch lubrication is excluded by cause, not by duration.** It runs under turbine error
on 99.9% of its 2,977 occurrences, and it is short: the 300 s threshold of v1 silently
dropped it (stopping codes agreed with the downtime series 99.97% at 1 s but 63.18% at
300 s), and the 60 s threshold here would let it back in as a fault. In a step where a
described code's alarm is active and the code's own description names a non-technical
cause, the step's turbine-error seconds move to that cause; for 3130 that is 3,750 steps
and 556,654 s. The threshold is lowered to 60 s because documented stops are short, not
to reach a rate.

**The same rule changes the training sites, and that is the point of one rule.** One
Senvion fault episode is often several status rows -- a converter writes "not ready" and
then "error" within a minute -- while a Siemens downtime run is one event whatever it
holds. Counted as episodes, technical stops of at least 60 s go from 19.3 to 13.4 per
turbine-year at Kelmarsh and from 26.3 to 16.5 at Penmanshiel (grid-time denominators;
gate 1 divided by turbine-year files). The row counts are printed beside the episodes in
the label report so the change is visible.

**Result.** Per turbine-year of grid time, and base rate of known labels
(`reports/data/20260910-212256_label_telemetry_20fa4ac5/label_stats_report.md`):

| site | narrow /ty | broad /ty | narrow 1 h / 6 h / 24 h | broad 1 h / 6 h / 24 h |
| --- | --- | --- | --- | --- |
| Kelmarsh | 13.4 | 104.6 | 0.151 / 0.724 / 2.481% | 1.186 / 6.724 / 24.619% |
| Penmanshiel | 16.5 | 127.7 | 0.182 / 0.879 / 3.040% | 1.432 / 7.712 / 27.492% |
| Hill of Towie | 16.5 | 137.1 | 0.187 / 1.013 / 3.542% | 1.552 / 8.881 / 32.176% |

The 20-40 target was set while the training sites still read 19.5 and 24.8. Under an
identical rule they read 13.4 and 16.5, and the held-out site sits with them at 16.5.
The rule was not tuned toward the band, and the band is not a criterion any more: the
criterion is that the three sites are counted by the same function. The rate moves more
between years than between sites: 6.5 to 34.0 per turbine-year at Kelmarsh (2023 the
highest), 8.2 to 29.1 at Penmanshiel, and 18.3 (2019) against 14.7 (2023) at the held-out
site. The temporal split (M1a step 7) has to be read with that in mind.

Sensitivity, from the label report: at 60 / 300 / 600 s the narrow rate is 13.4 / 9.7 /
8.6 (Kelmarsh), 16.5 / 11.8 / 10.9 (Penmanshiel) and 16.5 / 14.4 / 13.0 (Hill of
Towie). Counting emergency stops as faults moves it by +0.06 and +0.22 per turbine-year
at the training sites, which is not material, and the held-out site describes no
emergency-stop code. Of the narrow events, 22% (Kelmarsh), 37% (Penmanshiel) and 15%
(Hill of Towie) start outside a 3-20 m/s envelope measured from each provider's own
low- and high-wind stops; a wind rule would leave 10.5, 10.4 and 14.1. That cut depends
on the site -- Penmanshiel's technical stops at high wind -- which is one more reason the
cause does the excluding and the wind does not.

**Warnings are inputs, never targets.** Every status row and alarm, warnings and
non-stopping codes included, is written to `labels/status_stream.parquet` for the text
pathway. Targets are built only from stops: a Senvion row whose provider status is Stop,
the downtime series at Hill of Towie.

**Rejected.**

| alternative | why rejected |
| --- | --- |
| Widen the training sites to any stop | Gate 1: admits wind-lull stops (above). Kept as the broad, secondary label. |
| A threshold or rule per site | A site-specific rule is a leak: it can be tuned to the held-out site's answer. |
| Exclude by wind state (rung b) as the rule | Not needed where a cause is published, and it removes real faults: 13-14% of training-site equipment-fault stops start below 3 m/s. |
| The Senvion IEC availability category as the fault flag | As in events_v1: it describes accounting, not events ("Manual stop - remote" is filed Forced outage). |
| Count status rows, as gate 1 did | Counts one episode several times at one OEM and once at the other. |

**Unsettled, recorded so it is not rediscovered.**

1. Three of the four stop-class timers are undescribed by the provider, and reading
   commanded stops as planned is a judgement.
2. Downtime no stop class covers (low wind) is `unknown`, so it can never be narrow.
3. Stop classes are staged for 2019 and 2023 only, so the held-out site's narrow labels
   are unknown where a horizon crosses into 2020 or 2024: 1.6% of steps at 24 h.
4. CARE is one dataset per labelled anomaly; its anomalies are both label sets, and its
   rate per turbine-year does not compare with the other three sites.

**What would change this decision.** A provider description of the three undescribed
timers that contradicts the reading above; a training site whose status export stops
publishing start and end times; or a new held-out site with no published cause, where
rung (b) would apply and be recorded here as an amendment.

### Evidence note, 2026-09-11 (M1b step 9) -- the stop classes by behaviour, the late period

`reports/data/verification_20260911.md` (`faultline inspect verification`, telemetry_v2)
is the evidence for every figure below.

**Gate 2 accepted these labels and voided the 20-40 target.** The target was set against
counts of status rows; this rule counts episodes, so the change of rule re-based the unit.
The target is recorded as void, never as met, and no rate is compared with it.

**The four stop-class timers, read by what they do.** Unsettled point 1 above called the
commanded-as-planned reading a judgement. It is now measured. Every timer's runs at the
held-out site (2019 and 2023, 21 turbines) were profiled: when in the week and the day
they begin, how long they last, whether telemetry is missing while they run, how many
turbines share them, and how their hours per turbine-day compare with each `Out...Hours`
column of the provider's `tblDailySummary`. No pairing with those columns was assumed
from the names; every timer met every column.

| timer | provider description | read as | behaviour | best daily-summary match | confidence |
| --- | --- | --- | --- | --- | --- |
| `wtc_ScTurSto_timeon` | "Time turbine error active in period" | technical | starts spread evenly over the week (29.9% of runs Mon-Fri 07-17 UTC, 29.8% for an even spread; 29.1% at weekends, 28.6% even); one turbine at a time (median) | `OutTurHours`, 97.1% of turbine-days | high: described, and behaves like faults |
| `wtc_ScEnvSto_timeon` | not described | environmental | an afternoon peak (14:00 UTC) and an even week (28.3% at weekends); 7 turbines at once (median), 11 or more on 23.3% of its steps; high wind (8000) and icing (8230) run under it on 99.1% and 100% of occurrences | `OutEnvHours`, 99.5% | high |
| `wtc_ScComSto_timeon` | not described | planned (commanded) | working hours; see below | `OutCmdHours`, 83.9%; no other column above 37.4% | high |
| `wtc_ScGrdSto_timeon` | not described | grid | farm-wide: 19 of 21 turbines at once (median), 11 or more on 88.6% of its steps; 299 runs | `OutGrdHours`, 62.0% | moderate: a grid event's signature, but the weakest daily agreement of the four and few runs |

**Com, both readings, with the evidence for each.**

- *Commanded, so planned (as configured).* 86.4% of its 755 runs start Monday to Friday
  between 07:00 and 17:00 UTC, against 29.8% for starts spread evenly over the week; 6.0%
  start at a weekend, against 28.6%; 26.8% start in the 07:00 hour, the start of a working
  day. Telemetry is present on every one of its steps (0.00% missing). The rotor turns on
  10.9% of them, the fewest of the four timers, and a median of one turbine is in it at a
  time. Its hours agree with `OutCmdHours` on 83.9% of turbine-days.
- *Communication, so possibly technical.* For it: the abbreviation, and 11.8% of its steps
  with 11 or more turbines in it at once, which a park-level outage would produce -- and
  so would a park-level command such as curtailment. Against it: a communication outage
  leaves the telemetry missing while it lasts, and this one never does; and an outage has
  no reason to keep office hours.
- *The counterfactual.* Read as technical, the held-out site's narrow label goes from 693
  to 1,206 events (16.5 to 28.7 per turbine-year): 625 unchanged, 68 extended or merged,
  516 added. **84.3% of the Hill of Towie narrow label moves.** No other reading in this
  record matters as much, which is why it rests on four behavioural measures that agree
  rather than on the name. For comparison, reading Env as technical moves 0.7% and Grd
  16.9%.

**The late split is a temporal hold-out with a change in what is labelled, not a drift
test.** This supersedes "the temporal test is a drift test" (M1a step 7, `splits_v1.yaml`).
The narrow rate rises from 2022 at Kelmarsh (18.3 per turbine-year, 95% interval
15.1-22.1, against 8.96 in training) and from 2021 at Penmanshiel. That is before the 2023
SCADA export change, which therefore does not explain it. The message whose narrow events
rose most between training and the late test -- found by the report, not chosen -- is
`anemometer defect`. It opens more than one narrow event per turbine-year from 2021 at
**both** training sites at once (two events before then at Kelmarsh, one at Penmanshiel),
the year the status export gained two columns. Two farms starting to log the same stop in
the same year points to a reporting or firmware change, not to both farms degrading at
once. The stops are also concentrated: one turbine holds 162 of Kelmarsh's 204 narrow
events in 2023. Without the events the message opens, Kelmarsh reads 8.2 per turbine-year
in both 2022 and 2023, flat against training. The late test then reads 11.05 (Kelmarsh)
and 12.44 (Penmanshiel) per turbine-year, against 23.05 and 23.80 with them. Kelmarsh 2024
(16.8, none from that message) stays above training and is not explained here.

**Standing requirement: every late-test result is reported both with and without the
anemometer-defect events.** The events stay in the label: there is one rule, and the
configured categories file the message as an equipment fault. But no late-test number
stands alone. From M1b steps 10 and 12 the split specification names the message, and the
window index carries what the second number needs.

---

## ADR-0010 CARE is a secondary, dataset-level generalisation probe

**Status:** Accepted · **Date:** 2026-09-11

**Decision.** CARE is evaluated per dataset and reported as a secondary generalisation
probe, with a Wilson 95% interval on every rate, both with and without farm A (ADR-0004). No
per-step base rate or rate per turbine-year is reported for CARE beside the other sites.
The label report and the final-stage report print its datasets in a section of their own,
driven by `HarmonisedSite.dataset_level` and the final stage's `dataset_level_sources`: the
sources the labelling file reads through its `event_info` rule.

**Context.** CARE is a benchmark of 95 datasets. Each is one turbine's history built around
one provider label: 45 anomalous (12, 6 and 27 in farms A, B and C) and 50 normal (10, 9 and
31). The provider scores a detector per dataset with its own CARE score (Gueck, Bruns and
Dupont 2024). Until this record the label report printed a per-step base rate for it
(0.005%, 0.031% and 0.123% at 1 h, 6 h and 24 h). That counts steps of chosen datasets, and
it does not compare with the three sites whose steps are a whole record.

**Why its steps do not compare** (`reports/data/verification_20260911.md`, section d):

1. **Normalised power.** Active power is per unit of a rated power the record does not
   publish (bound -0.1 to 1.1), so it is not on the kW scale the other sites share.
2. **Anonymised timestamps.** Their spacing is real and their dates are not
   (`absolute_time: false`), so CARE has no calendar feature and no calendar split.
3. **Missingness by farm.** On the clean grid farm A has no main bearing temperature;
   farm B has no nacelle temperature, generator bearing or winding temperature; farm C
   has no nacelle position, wind direction, nacelle temperature or generator bearing. Each
   farm maps a different subset of the canonical list.

**Its statistical power, stated.** At a 50% detection rate, 45 anomalous datasets give a
95% interval of 35-63%, about ±14 points. Without farm A (33 datasets) it is ±16 points,
and a single farm gives ±18 (C), ±25 (A) or ±31 (B). **CARE therefore cannot separate two
models whose dataset-level rates differ by less than roughly 15 points**, and no smaller
CARE difference is reported as a difference. A paired comparison on the same datasets
could resolve less. It would be stated with its own test, and it does not change CARE's
role here.

**Rejected.**

| alternative | why rejected |
| --- | --- |
| CARE per-step base rates beside the other sites | Steps of chosen datasets are not a record; the rate says how the datasets were cut. |
| CARE as a fourth site in worst-site performance | Its interval is wider than most differences a worst-site figure would show, and its power channel and calendar are not comparable. |

**What this does not change.** CARE stays evaluation-only under its licence (ADR-0004), and
its `anomaly` rows stay both label sets (ADR-0009). How its normalised power enters the
token stream is decided with the tokenizer (M1b step 11).

**What would change this decision.** A published rated power per farm, a CARE release with
real timestamps, or more datasets. Each of these would narrow the interval or make the
steps comparable.

**Note, 2026-09-11 (M1b step 11).** How CARE's normalised power enters the token stream is
decided: as `<nan>`, at every farm (`configs/tokenizer/quantile_bins_v0.yaml`, ADR-0011).
There is no published rating to rescale it by, and binned against the training edges in kW,
all 5,240,487 of its values (-0.04 to 1.07) would decode to 10 kW or less: every CARE
turbine would read as not producing.

**Superseded, 2026-09-12 (M1c), by ADR-0013.** CARE's power is included, and the first of
the three reasons above -- "its power channel is not on the kW scale the other sites share"
-- no longer holds, because no site is on a kW scale. The canonical channel is per unit of
rated power at every source, and the provider states that CARE's power is already scaled by
rated power (*Data* 9(12):138, section 3.1.4), so it is in the canonical unit by
documentation rather than by inference. Nothing else in this record changes: CARE stays a
secondary, dataset-level probe with the interval its 45 anomalous datasets allow, its
timestamps stay anonymised, and its per-farm missingness stays what it was. A rated power
per farm is still unpublished and still inferred from nothing.

---

## ADR-0011 The telemetry tokenizer: 256 quantile bins, exact bins for point masses, fitted on the training split

**Status:** Accepted · **Date:** 2026-09-11

**Decision.** Every core channel is binned by one tokenizer,
`data/tokenizers/quantile_bins_v0_7b91fd02.json`, fitted by `faultline telemetry bins` from
`configs/tokenizer/quantile_bins_v0.yaml`. The evidence for every figure below is
`reports/data/quantile_bins_20260911.md`.

- **Fitted on the training split only**: the `train` rows of Kelmarsh (1,527,681) and
  Penmanshiel (3,210,913), never validation, the late test, the held-out site or CARE.
  11,498 imputed values are not fitted on: they are interpolations, not measurements
  (ADR-0006). The training exclusions' rows are fitted on, because an exclusion withholds
  training windows, not values (ADR-0008); inside it, the channels the outage took out have
  no values to fit.
- **256 bins a channel**, every channel's local identifiers 256 wide, sharing ADR-0003's bin
  block: 256 of its 1,024 fixed identifiers.
- **An exact bin for every point mass**: a value holding at least 1/256 of a channel's
  training values gets a bin of its own, reaching halfway to its nearest observed neighbours,
  and decodes to itself. Ten qualify, on three channels: pitch at 0, 1.49, 44.99 and 45
  degrees (0 alone holds 31.46% of pitch values), rotor speed at 0, 10.81, 17.09, 17.1 and
  17.11 rpm, and generator speed at 0 rpm.
- **CARE power is emitted as `<nan>`** (ADR-0010, note of this date).

**Why 256.** Reconstruction error -- the mean absolute difference between a value and the
value its bin decodes to, as a share of the channel's interquartile range -- across the twelve
channels:

| n_bins | median, train | largest, train | median, validation | largest, validation |
| --- | --- | --- | --- | --- |
| 64 | 3.66% | 10.31% | 4.27% | 18.97% |
| 128 | 1.72% | 4.08% | 2.29% | 7.20% |
| 256 | 0.81% | 2.10% | 1.19% | 4.19% |

The error falls with every doubling on every channel, on the validation year (2021) the edges
never saw as on the training values, so the grid has no interior optimum and the finest
candidate is chosen. It costs 256 identifiers in a block whose size is fixed whatever is
chosen, and nothing in sequence length: every step is one token per channel at any bin count.

*A correction to the configuration's reason.* `n_bins_reason` says 256 bins leave every bin
"about 13,000 training values or more". That is a plain division of each channel's values by
256. With exact bins it is not true of pitch: its four exact bins hold 41.6% of its values,
and its 251 other bins hold about 7,800 each. The claim is corrected here and not in the file,
which a run has read; 7,800 values a bin is still ample.

**Why exact bins.** Plain quantiles give pitch 41, 79 and 154 distinct edges at 64, 128 and 256
bins (the probe recorded in the configuration's header): the duplicate edges on a point mass
are empty bins, and the rest of the channel is squeezed into what is left. With exact bins
pitch uses 255 bins at 256, and its reconstruction error is 2.10% of its interquartile range
on the training values and 2.58% on validation.

**What the tokenizer does not fix, reported for gate 3.** Values outside the training range
land in the first or the last bin, and that bin's training occupancy says how rare a state
they are read as. Per held-out year:

| channel | Hill of Towie 2019 | Hill of Towie 2023 | the bin they land in holds |
| --- | --- | --- | --- |
| `pitch_angle_deg` | 71.40% below | 61.83% below | 0.07% of training values |
| `power_kw` | 6.81% above | 5.62% above | 0.39% |
| `main_bearing_temp_c` | 0.88% above | 2.68% above | 0.39% |

1. **Pitch.** Most of the held-out site's pitch values lie below the lowest training value
   (-0.087 degrees): its fine pitch sits below the training sites' 0. The held-out site's
   commonest operating state is read as a state the training split almost never shows.
2. **Power.** The highest training value is 2,087.6 kW and the held-out turbines are rated
   2,300 kW, so their top output collapses into one bin.

Both could be addressed -- a per-site pitch reference, power as a share of rated power -- and
both would change what a token means at every site. They are not done here; they are
decisions for gate 3, and either would be a new tokenizer configuration and new shards. A
third limit applies everywhere: the tails are coarse at every candidate. At 256 bins the last
bin of generator bearing temperature spans 42.7 degrees C and that of nacelle temperature
31.4, where overheating is.

**Rejected.**

| alternative | why rejected |
| --- | --- |
| 64 or 128 bins | Two to four times the reconstruction error, for no saving that matters: the bin block is fixed, and sequence length does not depend on it. |
| Plain quantiles | Spend bins on duplicate edges wherever a value repeats in bulk: pitch keeps 154 of 256. |
| Fitting on every split, or on the held-out site | Leaks the evaluation periods' distributions into the vocabulary (the rule since M0). |
| Rescaling CARE power by an assumed rating | Puts it on a scale nobody can check; `<nan>` says what is known. |

**What would change this decision.** A gate-3 decision on the pitch or power hazards, which
would be `quantile_bins_v1.yaml`, a new tokenizer and new shards; or an M1c result showing the
model starved in the tail bins, which would argue for fixed-width tail bins beside the
quantiles.

**Superseded in three parts, 2026-09-12 (M1c gate 3), by ADR-0012, ADR-0013 and ADR-0014.**
Gate 3 decided all three of the things this record left open, and all three are
`quantile_bins_v1.yaml`, a new tokenizer and new shards, as this record said they would be.
The pitch hazard is answered by a uniform datum floor at 0.0 degrees (ADR-0012); the power
hazard by putting every source's power in per unit of rated power, which also brings CARE's
power back into the stream (ADR-0013); and **the coarse tails -- the third limit above, "a
third limit applies everywhere" -- by hybrid tail bins (ADR-0014)**, which is the
fixed-width-tails-beside-the-quantiles change this paragraph anticipated. The figures
above stand as what the v0 tokenizer measured, and `quantile_bins_v0.yaml` no longer
validates, because it names the old channel spelling. ADR-0014 was itself amended at M1d
by **ADR-0015**, which turns the tail knob as ADR-0014 pre-registered and floors the clamp
bin; `quantile_bins_v2.yaml` is the current fit.

---

## ADR-0012 The pitch datum is harmonised: a uniform floor at 0.0 degrees, every site

**Status:** Accepted · **Date:** 2026-09-12

> **The principle, which ADR-0012, ADR-0013 and ADR-0014 all rest on.** Datums are
> conventions and are harmonised across sites. Physics is not harmonised; differences in
> physics between sites are what the held-out evaluation measures.

**Decision.** `pitch_angle_deg` is floored at **0.0 degrees at every source**, as a
declared, config-driven transform: `harmonise.pitch_angle_deg.floor` in
`configs/data/telemetry_v4.yaml`, applied by
`faultline.data.telemetry.datums.apply_datums` in the cleaning stage **after** the
plausibility bounds. A pitch below the -5 degree bound is `NaN` and is not rescued to 0.
The rule names no site.

**The diagnostic it rests on.** Measured on the final tables of 2026-09-12, before the
change (every measured, non-imputed value of the channel):

| | Kelmarsh | Penmanshiel | Hill of Towie 2019 | Hill of Towie 2023 |
| --- | --- | --- | --- | --- |
| manufacturer | Senvion MM92 | Senvion MM82 | Siemens SWT-2.3-82 | the same |
| exactly `0.0` | **41.30%** | **21.12%** | 0.010% | 0.001% |
| within 0.05 deg of -1.0 | 0.00% | 0.00% | **45.29%** | **32.84%** |
| lowest value | -0.1175 | -0.0870 | -1.2732 | -1.2236 |
| below 0.0 | 0.81% | 0.17% | 72.05% | 62.30% |

Senvion reports fine pitch as a hard exact zero; Siemens reports a continuous band centred
on -1.0 and reaches zero essentially never. The two machines are in the same operating
state. **That difference, and nothing else, is the 71.40% / 61.83% of Hill of Towie pitch
values that ADR-0011 reported below the training range** (the training range starts at
-0.087, so the two figures differ from the below-zero shares above by the values in
between).

It is not a two-site quirk. CARE farms A and C report a negative fine pitch as well
(p25 -1.700 and -1.503, 50.90% and 52.89% of their values below zero) and farm B does not
(p25 0.030, 6.94% of its values exactly zero). Three of the six machine populations in this
project -- Hill of Towie, CARE farm A and CARE farm C -- report fine pitch against a
non-zero datum, and the floor is what the other three already publish.

**Why a site-agnostic rule and not a per-site one.** The floor is large at one site and
negligible at the training sites -- 0.81% of Kelmarsh's values and 0.17% of Penmanshiel's,
every one of them within 0.12 degrees of zero -- but it is stated once, for every source,
and the configuration has no place to write a per-source datum. A rule that named
Hill of Towie would be a parameter chosen by looking at the held-out site.

**Declined: a +1.0 degree offset for Hill of Towie.** It is the better transform on its
face. It preserves the within-band variation the floor destroys -- Hill of Towie's pitch
runs p5 -0.9998 to p75 1.978, and while producing it sits in a band roughly -1.00 to -0.90
that carries real control activity. It is declined because **no document states a Siemens
pitch datum**: not the record README, not the field descriptions, not the turbine metadata.
The offset could only be fitted from the held-out site's own distribution, and fitting
anything to held-out data is what the pre-registered protocol forbids. Recorded as
declined for that reason, not as wrong. A published Siemens pitch reference would reopen it.

**The cost, stated.** About **72% (2019) and 62% (2023) of Hill of Towie's pitch values
collapse into the 0.0 point-mass token**, together with 50.9% and 52.9% of CARE farms A
and C. Everything the held-out site's fine-pitch band contained is gone. That is not a
loss the training sites can feel the absence of: at 0.0 exactly, Senvion reports *no
within-band variation at all*, so the model has never seen any, and no representation of
it exists to map onto. Aligning the held-out site to the vocabulary the training sites
actually produced is the honest zero-shot treatment; keeping the band would put 72% of the
held-out site's values in a bin holding 0.07% of training values, which is what ADR-0011
measured and what this decision answers.

**Not corrected, and named as a source of shift instead.** Hill of Towie feathers at
**78.0 degrees** exactly -- its maximum, at both staged years, with 2.39% of its values at
or above 70 and a median of 77.0 among them. Senvion runs higher: Kelmarsh and Penmanshiel
put 2.54% and 2.51% of their values at or above 70, with a mass at 89.99/90.00, a 95th
percentile of 92.49 among them, and maxima of 98.83 and 98.64. That is the machine's own
blade and control design, not a reporting convention, so **it stays**. It has a measured
consequence: 78.0 falls inside the training range and lands in pitch bin 247, which spans
[45.06, 80.52] degrees, decodes to 62.8 degrees, and holds **0.235%** of training pitch
values (7,883 of 3,350,222) -- at the training sites, the transit between the 45-degree
mass and feather, a mid-pitch transient. Hill of Towie's parked state will read as a
training site's transient. Hill of Towie also has **no 45-degree mass** (0.00% within 0.01
degrees of 45, against Kelmarsh's 6.60% and Penmanshiel's 12.89%). Both differences are
physics and are left for the evaluation to measure.

**Pre-planned analysis, registered here so it is not post-hoc.** An M1 ablation evaluates
Hill of Towie with pitch masked to `<nan>` (core-11), scoring the same checkpoints both
ways, to attribute how much of the site-shift penalty is pitch. The mechanism is the one
modality dropout already uses, so it costs no re-tokenisation (ADR-0008, "core-10 costs
nothing to revisit").

**Rejected.**

| alternative | why rejected |
| --- | --- |
| A +1.0 deg offset at Hill of Towie | No published Siemens datum; the offset could only be fitted from held-out data. Recorded above in full. |
| The floor in `clean.py`, with the bounds | Cleaning decides whether a value is a reading at all. A datum decides what a reading is measured from. Ordering them the other way would rescue an out-of-bounds pitch to 0 and present an instrument failure as fine pitch; `tests/data/telemetry/test_datums.py` fails if it does. |
| The floor in the Hill of Towie adapter | It would make a site-agnostic convention look like a per-site correction, and would hide from every other source a rule that in fact moves values at four of six machine populations. |
| Leaving pitch as published | Measured: 71.40% / 61.83% of the held-out site's values outside the training range, landing in a bin holding 0.07% of training values (ADR-0011). |

**What would change this decision.** A published Siemens pitch datum, which would make the
offset a documented conversion rather than a fitted one; or an M1c core-11 ablation showing
the floored channel is worse than no pitch at all at the held-out site.

---

## ADR-0013 Power is per unit of rated power at every source, and CARE's power comes back

**Status:** Accepted · **Date:** 2026-09-12

> **The principle, which ADR-0012, ADR-0013 and ADR-0014 all rest on.** Datums are
> conventions and are harmonised across sites. Physics is not harmonised; differences in
> physics between sites are what the held-out evaluation measures.

**Decision.** The canonical power channel holds **P / P_rated** at every source, and is
renamed `power_kw` -> `power_pu` across the schema, the channel maps, the configurations
and the tests. The division is done in the adapters, as any other unit conversion is,
driven by `rated_power_kw` in `configs/data/sources_telemetry.yaml`:

| source | machine | rated power | citation |
| --- | --- | --- | --- |
| Kelmarsh | Senvion MM92 | 2,050 kW | `Kelmarsh_WT_static.csv`, column "Rated power (kW)", Zenodo record 16807551: one distinct value at all 6 turbines |
| Penmanshiel | Senvion MM82 | 2,050 kW | `Penmanshiel_WT_static.csv`, same column, record 16807304: one distinct value at all 29 listed turbines |
| Hill of Towie | Siemens SWT-2.3-VS-82 | 2,300 kW | `Hill_of_Towie_turbine_metadata.csv`, same column, record 14870023: one distinct value at all 21 turbines |
| CARE | anonymised | none declared | it publishes power already scaled by rated power; see below |

Each number is read from the provider's own staged metadata file, not from a datasheet and
not from the data. **A nameplate is a published fact about a machine, not a quantity fitted
from the record, so dividing by it leaks nothing from an evaluation period.** The
configuration model refuses a rating with no citation.

**Why rename the channel.** A channel named `power_kw` holding values between 0 and 1 is
precisely the error in CARE's own `feature_description.csv`, which gives every active-power
feature a `unit` of kW while the values read -0.02 to 1.04 -- the error this project's
diagnostic caught and spent a decision on. Repeating it in our own schema would be
indefensible. The channel keeps its position and therefore its token identifier
(ADR-0003); `schemas.RENAMED_CHANNELS` records the rename so that the frozen
configurations can still be compared with the current schema instead of exempted from it.

**CARE's power is included, on the provider's documentation.** Gueck, Bruns and Dupont
(2024), *Data* 9(12):138, section 3.1.4 states that "power and reactive power features have
been scaled with the rated power of the turbine", and the staged values read -0.043 to
1.071. That is per unit **by documentation, not by inference from the range**. Since the
canonical channel is now per unit, CARE's power is already in the target unit: no rating is
needed, none is inferred from its percentiles for any purpose, and the tokenizer
configuration's exclusion is removed (`quantile_bins_v1.yaml`, `excluded: {}`). This
supersedes the note of 2026-09-11 on ADR-0010 and the `<nan>` rule in ADR-0011: both rested
on there being no factor to convert kW edges by, and there are no kW edges now.

**The bounds, converted.** `telemetry_v4.yaml` divides v3's power bounds by each site's
rating:

| source | v3, kW | v4, per unit | arithmetic |
| --- | --- | --- | --- |
| Kelmarsh, Penmanshiel (default) | [-100, 2255] | **[-0.0487805, 1.1]** | -100/2050, 2255/2050 |
| Hill of Towie | [-100, 2530] | **[-0.0434783, 1.1]** | -100/2300, 2530/2300 |
| CARE | [-0.1, 1.1] | **[-0.1, 1.1]** | unchanged: already per unit |

The plausible **maximum is now the same number, 1.1 pu, at every source**, which is what
the conversion buys: the three bounds were the same rule -- 110% of rated -- written three
ways. The minima are not identical, and are not forced to be: -100 kW was an absolute
allowance for a machine drawing from the grid while idle, and an absolute quantity does not
scale with a rating. Recorded rather than tidied away. Both minima are rounded away
from zero, so the converted bound admits everything the kW bound did; no source comes
near it, the lowest power on the cleaned grid being -21.17 kW.

**Consequences beyond the channel.**

* `splits_v3.yaml`. `splits_v2.yaml` names `power_kw` in `eval_channels` and therefore no
  longer validates, exactly as `splits_v0` and `splits_v1` stopped validating when wind
  direction was demoted. A specification a run has read is never edited, so v3 is written
  as v2 with that one name changed and **nothing else whatever**; a test asserts the two
  parse to the same object under the rename. `events_v2.yaml` is genuinely untouched: it
  names no channel. Reports generated under `splits_v2` join `splits_v0` and `splits_v1`
  as historical (ADR-0008, amendment of this date).
* `quantile_bins_v0.yaml` no longer validates either, for the same reason. Its fitted
  tokenizer stays in `data/tokenizers/` as the artifact of the run that produced the gate-3
  tables.
* The "producing" threshold in `verify.py` becomes **0.005 pu** instead of a flat 10 kW
  (10.25 kW at a 2.05 MW machine, 11.5 kW at a 2.3 MW one). A threshold in per unit is the
  same rule at every machine, which a threshold in kW is not.
  `events_v2.yaml`'s provenance text records the 10 kW threshold its own measurement used,
  and is not edited.

**What this fixes, measured.** ADR-0011 reported 6.81% (2019) and 5.62% (2023) of Hill of
Towie's power values above the highest training value, collapsing its top output into one
bin, because the highest training value was 2,087.6 kW at a 2.05 MW machine and the
held-out turbines are rated 2.3 MW. In per unit that ceiling is 1.018 pu of a Senvion
against a Siemens reading up to about 1.0 pu of its own rating. **The share above range is
expected to shrink and not to vanish** -- a turbine can exceed its nameplate -- and the
re-fit reports the number it actually is.

**Rejected.**

| alternative | why rejected |
| --- | --- |
| Leaving power in kW | Two machine sizes on one scale: the held-out site's rated output sits above every training value, and its whole upper power range reads as one bin (ADR-0011). |
| Keeping the name `power_kw` for per-unit values | The exact mistake in CARE's own feature lookup, which this project spent a diagnostic catching. |
| Dividing in `clean.py` or a later stage | A unit is part of what a provider publishes, and an adapter is where provider-specific facts live. Everything downstream of an adapter is meant to read one schema in one set of units, and the bounds are applied downstream. |
| Inferring a rating for CARE from its percentiles | Rejected at ADR-0011 and still rejected. Nothing needs one: section 3.1.4 says what the unit is. |
| Recovering farm A's rating from EDP Open Data | Deferred, not refused. Farm A is 5 of 36 turbines and 22 of 95 datasets, and the EDP terms are still unverified (ADR-0004). Recorded as a possible **M3** refinement; it would narrow nothing at M1, because CARE's power needs no rating. |

**What would change this decision.** A published rated power per CARE farm, which would
make its power comparable in kW as well; a provider correcting the rating in its own
metadata; or a site whose record publishes no rating at all, which would need its own rule
rather than an inferred divisor.

---

## ADR-0014 Hybrid tail bins: fixed-width in the tails, quantiles in the middle

**Status:** Accepted · **Date:** 2026-09-12

**Amended, 2026-09-12 (M1d), by ADR-0015.** The signal this record pre-registered fired
at the v1 fit -- 184 of 352 tail bins under 500 training values, 42 empty -- and `n_tail`
is turned to 4 as written. ADR-0015 also adds a rule this record has no clause for: the
outermost bin of each tail is population-floored, because it is the clamp target for every
value beyond the training range and rule 6 therefore gives it unbounded effective width.
Rules 1, 2, 5 and 6 below are unchanged; rule 3 reads 4 instead of 16, and rule 4 is
recomputed after the floor. Read the two records together, and ADR-0015 for what the floor
cost.

> **The principle, which ADR-0012, ADR-0013 and ADR-0014 all rest on.** Datums are
> conventions and are harmonised across sites. Physics is not harmonised; differences in
> physics between sites are what the held-out evaluation measures.

**Decision.** Every channel still gets **256 bins**, and how they are spent changes. One
rule, the same for every channel, **fixed in `configs/tokenizer/quantile_bins_v1.yaml`
before the fit was run**:

1. **Point-mass bins are carved out first**, exactly as at v0: a value holding at least
   1/256 of the channel's training values gets an exact bin reaching halfway to its
   nearest observed neighbours.
2. **The tail boundaries are the training p0.5 and p99.5** of the channel.
3. **Each tail gets `n_tail = 16` bins of equal width** over `[train_min, p0.5)` and
   `(p99.5, train_max]`.
4. **The remaining `256 - n_pointmass - 32` bins are quantile bins** over `[p0.5, p99.5]`.
5. **A tail with zero width gives its 16 bins back to the central quantile pool** -- when
   its boundary is already the range edge, or falls inside a point mass's exact bin. This
   is stated in advance because it will fire: pitch sits at exactly 0.0 on more than a
   fifth of its training values at both training sites, and after the datum floor of
   ADR-0012 more still, so its p0.5 *is* its minimum. The report names every channel that
   triggers it.
6. **A value outside the training range clamps to the extreme bin**, as at v0.

The fit is still on the **train split of Kelmarsh and Penmanshiel only** -- never
validation, the late test, the held-out site or CARE. Nothing about what the edges are
fitted on changes.

**Why.** Quantile bins put resolution where the data is dense. Faults are not where the
data is dense. ADR-0011 recorded the cost and left it: "at 256 bins the last bin of
generator bearing temperature spans 42.7 degrees C and that of nacelle temperature 31.4,
where overheating is". A 42.7-degree top bin cannot distinguish a bearing running warm
from one about to fail, and a model cannot learn a distinction its vocabulary does not
carry. Fixed-width tails spend identifiers where the events are.

**Pre-registered expectations, written before the fit and reported against afterwards.**

| | expectation | why |
| --- | --- | --- |
| median reconstruction error | **rises slightly** | the middle loses 32 quantile bins |
| worst reconstruction error | **falls** | the worst channel is worst because of its tail |
| generator-bearing top bin | **42.7 degC to roughly 3 degC** | one sixteenth of a slightly wider span |
| pitch's lower tail | **collapses (rule 5)** | its p0.5 is its minimum |

**The knob, and the signal to turn it.** The knob is `n_tail`. **The signal is degenerate
tail-bin training counts -- many bins holding under about 500 training values -- and not
the median reconstruction error**, which is expected to rise and whose rising is not
evidence of anything. The report prints the training count of every tail bin and counts
those under 500, so the signal is visible rather than inferred. A tail bin with almost no
training values is an identifier the model cannot learn; a slightly coarser middle is a
known, bounded cost.

**What is compared with what.** The report fits the same bin count on the same values with
pure quantiles and prints the two side by side, so the before and after differ by the tail
rule and nothing else. This matters because the underlying tables changed in the same
revision (ADR-0012, ADR-0013): a comparison against the M1b tables alone would confound
three decisions.

**Rejected.**

| alternative | why rejected |
| --- | --- |
| More bins instead of better-spent bins | The bin block is 1,024 identifiers and 256 is already the chosen size (ADR-0011); doubling to 512 halves every tail bin but also halves every central bin, when the central bins were never the problem. |
| Fixed-width bins everywhere | Would spend most of the vocabulary on values that occur a few times a year -- the reason quantiles were chosen at M0. |
| A log transform before binning | Changes what a bin means per channel and cannot be applied to channels that cross zero (power, ambient temperature, pitch). |
| Tails at p1 / p99 | A wider tail region makes each fixed-width bin wider, which is the thing being fixed. p0.5 keeps 1% of the training values in 32 bins, which is where the starvation check bites. |
| Turning `n_tail` on the median error | The median error is the cost of the rule, not evidence about it. Stated here so that a later "the error went up, turn the tails down" is recognisable as the mistake it would be. |

**What would change this decision.** Tail bins starved of training values in the report
below, which turns `n_tail` down; a model result showing the tail tokens are not learned
at all, which would argue for fewer and wider tail bins; or a new channel whose tail
behaviour differs enough that one `n_tail` for every channel stops being defensible.

---

## ADR-0015 The tail knob is turned as pre-registered, and the clamp bin is population-floored

**Status:** Accepted; **frozen for Phase A** 2026-09-13 · **Date:** 2026-09-12 · **Amends:** ADR-0014

> **The principle, which ADR-0012, ADR-0013 and ADR-0014 all rest on.** Datums are
> conventions and are harmonised across sites. Physics is not harmonised; differences in
> physics between sites are what the held-out evaluation measures.

**Decision.** `configs/tokenizer/quantile_bins_v2.yaml` changes exactly two things from
v1, both about the tails. Nothing about the telemetry configuration, the split
specification, the channels, the bin count or what the edges are fitted on changes.

1. **`n_tail: 4`, down from 16.** ADR-0014 named the knob and the signal before the v1 fit
   was run: the knob is `n_tail`, and the signal to turn it down is degenerate tail bins
   -- many holding under about 500 training values -- and explicitly *not* the median
   reconstruction error. **The signal fired.** At `n_tail = 16`, 184 of 352 tail bins held
   under 500 training values and 42 held none. The knob is turned as written.
2. **The outermost bin on each side is population-floored (`clamp_floor: 0.001`).** After
   the four fixed-width bins are laid, the outermost is merged with its inward neighbour,
   repeatedly, until it holds at least **0.1% of that channel's measured training values**.

The merge has two stops, and both are rules rather than tuning. The boundary with the
quantile middle is never merged away, so a tail always keeps at least one bin and never
eats into the middle. A point mass's exact bin is never merged away either -- rule 1 of
ADR-0014 outranks this rule -- so where one bounds the outermost bin the merge stops short
of the floor and the report names the channel. Whatever the merge gives up returns to the
central quantile pool, exactly as rule 5 returns the bins of a zero-width tail.

**Why the clamp bin needs a floor at all, which ADR-0014 could not have known.** A
fixed-width tail gives its outermost bin a *nominal* width. The outermost bin is also
where **every value beyond the training range clamps** (rule 6), so its *effective* width
is unbounded in the direction that matters. ADR-0014 gave the catch-all the narrowest
nominal width available and therefore made it the rarest token in the channel. The
concrete case: at `n_tail = 16`, `main_bearing_temp_c`'s top bin held **24** training
values, while **2.68%** of Hill of Towie's 2023 values clamp into it. A token the model
sees 24 times in training is not a token it learns, and the held-out site would read a
fortieth of that channel through it. Turning `n_tail` down alone does not fix this: the
defect is that the bin at the boundary of the known range is sized by geometry when it is
the one bin that must be sized by population.

0.1% is chosen as an order of magnitude of headroom below the worst measured clamp share
(2.68%), and still leaves roughly 4,700 training values behind the token at the channels
with the most values. It is a share of each channel's own values, not a fixed count,
because the channels do not have the same number of measured values -- pitch and gear oil
have about 3.35 million, the rest about 4.66 million.

**Pre-registered acceptance check, fixed before the fit, REPORTED AND NOT ITERATED ON.**
A channel that fails one is recorded as a limitation here; it is **not** a reason to fit a
third time. Stated in advance because the failure mode of a knob with a good rationale is
fitting until the table is clean.

**What came out** (`reports/data/quantile_bins_v2_20260912.md`, config hash `9cd52b65`):

| check | result |
| --- | --- |
| no tail bin empty at any channel | **PASS** — 0 of 41 |
| every tail bin at or above 500 training values | 0 of 41 starved (was 184 of 352) |
| every clamp bin at or above the 0.1% floor | **PASS** — all 24, no channel named |
| `generator_bearing_temp_c` top bin | 42.68 degC quantile only → 2.783 at `n_tail` 16 → **33.4** chosen |
| median reconstruction error, train | 0.815% quantile only → 0.475% at `n_tail` 16 → **0.740%** chosen |
| median reconstruction error, validation | 1.190% → 0.500% → **1.055%** |
| `main_bearing_temp_c` top bin, training values | 24 at `n_tail` 16 → **23,285** (0.500%) |

The curve the knob was turned on, re-measured by this run rather than quoted from gate 4,
each point a whole refit at 256 bins on the same training values:

| `n_tail` | tail bins | under 500 | empty | `generator_bearing_temp_c` top bin |
| --- | --- | --- | --- | --- |
| 16 | 352 | 184 (52%) | 42 | 2.783 |
| 12 | 264 | 130 (49%) | 25 | 3.711 |
| 8 | 176 | 76 (43%) | 12 | 5.566 |
| **4** | 88 | 30 (34%) | 1 | 11.13 |
| 2 | 44 | 10 (23%) | 0 | 22.27 |

4 is where the empty bins all but vanish while the witness channel's top bin is still a
quarter of the 42.68 degrees C pure quantiles give it. 2 clears the signal outright and
gives half of that back; 8 leaves a double-figure count of bins the model would see fewer
than 500 times.

**The limitation this record has to carry, and it is the important part.** The floor met
its own objective and **cancelled the tail rule on most channels while doing it**. Of the
88 fixed-width bins laid, the merge took 47 back; 8 of 12 channels ended with a **top bin
wider than the pure-quantile control's**, and 2 of 12 with a wider bottom bin. Wider than
doing nothing at all, on the measure ADR-0014 was accepted for.

The mechanism is arithmetic and was foreseeable, and was not foreseen. A tail's values are
packed against its inner boundary, so the outer fixed-width bins are nearly empty and the
merge cascades. Where it runs all the way to the boundary the clamp bin spans the entire
tail and holds `tail_quantile` = 0.5% of the channel's values by construction -- against
the 0.39% (1/256) a pure quantile end bin holds. A population floor and a fixed-width tail
pull in opposite directions, and with only merging available the floor always wins.

So this fit buys a clamp token the model can actually learn and pays for it in clamp
*resolution* on two thirds of the channels. Both halves of that sentence are the measured
result; neither is the outcome the decision was written expecting. It stands as fitted for
the model ladder, because the ladder needs one frozen vocabulary and because a token seen
24 times is the worse of the two defects, and the next tokenizer revision -- if the model
results call for one -- should design the tail rule and the floor together rather than
bolt the second onto the first. The obvious candidate, not run here: make the tail
boundary itself a function of the floor, so that the outer tail bins are laid at equal
*population* and only the inner ones at equal width.

**What is compared with what.** Three fits of the same bin count on the same training
values, differing by the tail rule alone: pure quantiles (the M1b rule), `n_tail = 16`
without a floor (v1, which this supersedes), and the chosen fit. The controls are measured
and never written to `data/tokenizers/`, so no run can read one by mistake. Comparing
against v1's *report* instead would have been cheaper and wrong: v1's numbers are sound,
but a refit is the only way to be sure the difference is the rule and not the run.

**Rejected.**

| alternative | why rejected |
| --- | --- |
| Keep `n_tail = 16` and floor the clamp bins only | The floor repairs the outermost bin; it does nothing for the 180-odd bins *behind* it that the signal was raised about. The two changes answer two defects and both were needed. |
| Drop the fixed-width tails and return to pure quantiles | Throws away what ADR-0014 was accepted for. The witness channel's top bin returns to 42.68 degrees C, which is the defect that started this. |
| A fixed count -- "at least 500 values" -- instead of a share | 500 is the *starvation* threshold, a floor on a bin the model must learn. The clamp bin carries a different burden, and the channels do not have the same number of measured values, so a share is the comparable quantity. |
| Floor every tail bin, not just the outermost | That is quantile binning of the tail, which spends the resolution back where the data is dense -- the thing fixed-width tails exist to avoid. Only the outermost bin has unbounded effective width, so only it is floored. |
| Merge the boundary with the middle away when the floor is still unmet | The tail would eat into the quantile middle, and one bin spanning the tail *and* part of the middle is neither rule. The merge stops and the channel is named instead. |
| Size the floor from the held-out site's clamp share | Fits the tokenizer to the held-out site. The floor is fixed from the training values alone; the 2.68% is what made the defect visible, not an input to the rule. |
| Turn `n_tail` on the median reconstruction error | Already rejected in ADR-0014, repeated because the error table moves again here (0.475% to 0.740% on the training values). The median error is the rule's cost, not evidence about it. |
| Fit a third time now that the cost is measured | Pre-registered against, above, and refused here. The record carries the limitation instead. |

**FROZEN for Phase A, 2026-09-13.** `quantile_bins_v2` is the telemetry tokenizer for the
rest of Phase A -- M2, M3 and the deployment work -- and is not refitted again inside it.
Two reasons, and the second is the one that decides it:

1. The joint model needs one frozen telemetry vocabulary. ADR-0003 makes the telemetry
   region a stable prefix so that M1 shards survive the M2 text tokenizer; refitting the
   bins inside Phase A would re-shard everything M1 produced and invalidate the ladder it
   is the baseline for.
2. **The trigger named below has not fired, because nothing has been able to test it.**
   "A model result showing the tail tokens are still not learned" requires a risk run that
   trained; the M1e ladder's risk arms did not (see the 2026-09-13 addendum to
   `reports/data/ladder_v0_20260912.md`: H1 UNTESTED, the pretraining ablation
   INCONCLUSIVE). A tokenizer must not be refitted on the strength of a model result that
   the model runs cannot support, in either direction. Refitting now would be fitting the
   vocabulary to noise.

**The replacement design is Phase B / M4**, not Phase A: outer tail bins laid at equal
*population* and inner ones at equal width, designed as one rule rather than a floor
bolted onto a fixed-width tail. It is the tail rule the harmonisation-protocol claim will
be written against, and under the Phase A / Phase B split it is not begun, scoped or
prototyped while M1, M2 or M3 are open.

**What would change this decision** -- and none of it inside Phase A. A model result
showing the tail tokens are still not learned, or that the widened clamp bins cost
held-out performance, either would reopen the rule, and the replacement should be the
single design named above rather than another bolt-on; but such a result only counts if it
comes from a risk run whose control arm demonstrably trained, which M3 step 0 is the
pre-registered attempt at. Also: a channel that fails the floor for a reason other than a
point mass bounding its clamp bin, or a new source whose clamp share exceeds 0.1% by
enough that the headroom stops being an order of magnitude.

---

## ADR-0016 The M2 text corpus is NRC operator-narrative documents, not the four-source Tier-1/Tier-2 list as scoped

**Status:** Accepted, corrected 2026-09-13 (Tier-1 table restructured; PHMSA and
DOE OE-417 re-tested; `NrcTextClient` now checks robots.txt before, not after,
the first request to a host; the generic-communications yield table corrected
after a second PDF-hosting path was found undercounting Regulatory Issue
Summaries; Gate-6 corrections below -- source-aware dedup by event number, two
declared fixed-boilerplate rules; **corrected 2026-09-16: PHMSA route and target
re-read, decision rule pre-registered, see the last section**) · **Date:** 2026-09-13

**Decision.** The M2 text corpus is drawn from `www.nrc.gov`: Event Notification
Reports (native HTML, the whole collection) and four "generic communications"
collections -- Information Notices, Bulletins, Generic Letters, Regulatory Issue
Summaries -- restricted to the documents that stay on `nrc.gov` outside `/docs/`
(below). A fifth generic-communications collection, Preliminary Notification
Reports, is configured and disabled: measured to hold zero documents through the
permitted route. A tiny sixth source, the Kelmarsh/Penmanshiel status-message code
book, is drawn from telemetry already staged for M1, not fetched over the
network. Every Tier-2 candidate (NERC Lessons Learned, four sampled ISO/RTO
notice pages, NREL/OSTI technical reports) is excluded, each for a reason
measured on 2026-09-13 and recorded in `configs/data/sources_text.yaml`'s
`excluded_candidates` block, not merely asserted here. Of the three other
Tier-1 sources, one (NRC Licensee Event Reports) is excluded on the same terms;
one (DOE OE-417) is excluded for thinness, corrected below from an earlier,
overstated "unreachable"; and one (PHMSA) is **not excluded** -- it is pending a
manual download this ADR names the exact file for.

**The table below distinguishes two different claims a "blocked" line can
mean, and the original version of this ADR conflated them.** "This project's
automated crawler cannot fetch this under the access policies it honours" and
"this project cannot obtain this data by any permitted route" are different
statements. A person downloading a stated-public-domain file in their own
browser and recording its URL, retrieval date and hash in the manifest is
ordinary provenance -- the same kind every Zenodo-staged telemetry source
already uses -- not a workaround; it is distinct from an automated client
presenting itself as something it is not (a browser, a different crawler),
which stays refused regardless of what it would unlock. The table reports
both routes for each source, separately.

| source | automated route | manual route | estimated narrative yield | decision |
| --- | --- | --- | --- | --- |
| NRC Licensee Event Reports | **Blocked.** `lersearch.inl.gov/robots.txt`: `User-agent: *` / `Disallow: /`, commented "Don't index this site" -- a direct instruction, honoured rather than tested around. ADAMS' own public interface moved from `adams.nrc.gov/wba` (now NXDOMAIN) to `adams-search.nrc.gov`, a single-page app with no documented public API. data.gov's catalogue entry for this dataset names the LERSearch UI as its sole resource -- no bulk export. | **Not open, and nothing to name.** LERSearch is a case-by-case search form, not a bulk listing, so there is no "exact file" a human could fetch the way PHMSA's can be named below. | Likely substantial -- LERs are the NRC's longest-form technical narrative filings, longer than an Event Notification -- but unmeasured: no route, automated or manual-bulk, is open to measure it from. | **Excluded.** Route forward: a written bulk-export request to NRC, recorded as such if it is ever made; not something this session can action. |
| PHMSA pipeline incidents | **Blocked, tested from a second, independent angle this time.** `data.transportation.gov` (DOT's Socrata portal) is a different host from `phmsa.dot.gov`'s Akamai front, with its own `robots.txt` (permits `/resource/*` and `/api/views/*` for a generic agent). Queried directly: the named dataset ("Pipeline Incident Flagged Files", `qdme-9bbm`) is a metadata-only record (`"assetType": "href"`) -- Socrata never hosted the rows, only a pointer. Its `additionalAccessPoints.zip` field, and a sibling dataset's (`27nc-rsge`) access point, both resolve to files still served from `phmsa.dot.gov` -- the same host already found to 403 every non-browser client. Confirmed independently: Claude's own `WebFetch` tool (a different client, different network path) also received `403 Forbidden` fetching the PHMSA landing page. Two different automated tools, two networks, the same result: there is no independently-hosted export for this data, only a catalogue pointer back to the blocked host. **[Corrected 2026-09-16: false. `27nc-rsge` hosts 15 incident-data zips on `data.transportation.gov` itself; this check read `accessPoints` and never `metadata.attachments`. See the last section of this ADR.]** | **Open.** An edge rule built against non-browser traffic does not block a human browser session, and downloading a stated-public-domain file and recording its URL, date and hash is ordinary provenance. **Exact file, named via `data.transportation.gov`'s own structured metadata:** `https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/PHMSA_Pipeline_Safety_Flagged_Incidents.zip` ("Flagged Files (zip file)", the `qdme-9bbm` record's access point). The broader per-year accident/incident files live under `https://www.phmsa.dot.gov/data-and-statistics/pipeline/distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data`, which this project cannot enumerate (both `requests` and `WebFetch` are blocked there) but a browser reaches normally. | Unmeasured pending the file. PHMSA's own dataset description names "significant incidents," "reported incidents" and cause information among the underlying fields -- exactly what a downloaded file needs to be profiled against (`faultline inspect telemetry`'s free-text-verdict method, `docs/DATASET_CARD_TEMPLATE.md`) before any yield number is reported. | **Not staged, not excluded.** Awaiting a manual download at the file named above; this project will profile it and report the free-text verdict once it exists. Licence already confirmed clean: `27nc-rsge`'s Socrata metadata states `License: http://www.usa.gov/publicdomain/label/1.0/`, consistent with 17 U.S.C. 105. |
| DOE OE-417 disturbance reports | The publishing host, `www.oe.netl.doe.gov`, resolves IPv6-only from this network and is genuinely unreachable -- that part stands. **The original exclusion reason is corrected here**: it said "unreachable," true of that one host and false of the source as a whole, conflating the two. The ORNL OpenEnergyHub mirror (`openenergyhub.ornl.gov`) *is* reachable and was queried, in the original reconnaissance and again for this correction, via its `/api/explore/...` REST endpoint -- **which its own `robots.txt` disallows for a generic `User-agent: *`** (`Disallow: /api/`, with `Allow: /api/` carved out for `Googlebot` only). That is a compliance error in this project's own prior action, caught rereading the same file rather than by anyone else, and it is corrected here: the mirror's API is not an open automated route, on the same standard this ADR applies to every other source. | Not tested, given the measured thinness below. If this source is wanted later, the mirror's human-facing dataset page (`/explore/dataset/oe-417-annual-summaries/`, not disallowed) or a written request to DOE/ORNL are the routes to check first. | **Measured** (the data already retrieved is kept as evidence of thinness, not relied on as an ongoing route -- see the correction above): 341 rows total, covering 2023 only -- the mirror's own description states it captures "annual summary... for 2023 only for data discovery purposes," not a multi-year archive. Its one text-bearing field (`alert_criteria`) holds **27 distinct values across all 341 rows**: a closed set of regulatory reporting categories, not free narrative -- the same code-book-versus-narrative distinction ADR-0001 draws for the telemetry sources. Every text field combined (`area_affected`, `alert_criteria`, `event_type`) totals **9,614 whitespace-delimited tokens** for the entire dataset. | **Excluded -- for thinness, not unreachability.** A public-domain source (confirmed) with a 2023-only sample of a few hundred rows and a 27-entry code book where a narrative field would be; profiled the way the telemetry sources are, it would not clear `docs/DATASET_CARD_TEMPLATE.md`'s `VERIFIED no` threshold. |

None of the three is a licence problem -- all three would be admissible on terms
alone, and two of the three have an explicit public-domain statement on record.
Two are genuinely blocked by every route checked; the third (PHMSA) has an open
manual route this ADR names a file for, which the original version did not
distinguish from the other two.

**The ORNL `/api/` error is why `NrcTextClient` now checks robots.txt before the
first request to a host, not after the fact.** Both queries against
`openenergyhub.ornl.gov`'s `/api/explore/...` endpoint -- the original
reconnaissance and the 2026-09-13 recheck above -- went out before its
`robots.txt` had been read as carefully as `nrc.gov`'s was; a `Disallow: /api/`
for the general user agent sat there both times, unnoticed until this
correction. `src/faultline/download/nrc_text.py`'s `NrcTextClient` now fetches
and parses a host's `robots.txt` once, before its first request to that host,
and refuses any path it disallows for this project's user agent, with a
logged reason; `tests/download/test_nrc_text.py::TestRobotsGating` asserts
against a fake transport that a disallowed URL is never passed to it. This
does not change anything already reported above -- the ORNL data was already
flagged as improperly fetched and not relied on further -- it changes whether
the same mistake can happen again undetected.

**The user's decision, 2026-09-13, on being shown the original evidence.**
Expand within the one source family that is actually reachable by an automated,
robots.txt-compliant route (`nrc.gov`) for the corpus proper, rather than search
for substitutes or work around the barriers above with automation. Explicitly
refused, and still refused after this correction: fetching a blocked route with
a spoofed browser `User-Agent`, or any other automated presentation of this
project's client as something it is not -- that would technically succeed
against PHMSA's WAF and would violate `lersearch.inl.gov`'s explicit
`Disallow: /`, and the project's defensibility rests on a provenance chain that
can be written plainly in a dataset card. A **human** downloading a
public-domain file in their own browser and recording it in the manifest is a
different act from that, not a smaller version of it, which is what this
correction's table now says explicitly. If the NRC LERs are wanted later, the
stated route is a written request to the agency for a bulk export.

**The `/docs/` finding, measured rather than inferred from robots.txt.**
`nrc.gov/robots.txt`'s general `User-agent: *` rule does not disallow `/docs/`
(only two named crawlers, `Akamai-SiteSnapshot` and `Amazonbot`, are disallowed
there). In practice, every request to a `/docs/*.pdf` URL --  the ADAMS accession
path every generic-communications document has linked to since roughly the early
2000s -- returned `HTTP 403 Access Denied` from the Akamai edge, repeatably, on
requests that were not part of any burst (a plain `nrc.gov` HTML page fetched
immediately before and after each 403 returned 200 both times). This is a
structural block at the edge, separate from the robots.txt statement and from the
rate-limit-shaped 403s seen on `nrc.gov` HTML pages during reconnaissance (which
cleared after a pause -- the reason `NrcTextClient` paces every request at
`MIN_REQUEST_INTERVAL` regardless of server response time). Per the decision
above, this module does not attempt to work around either kind of block: it
follows only links that stay on `nrc.gov` outside `/docs/`, measured per
collection before anything was staged.

**What the PDF exclusion costs, corrected 2026-09-13** (`html` = native pages kept,
`pdf (/docs/)` = ADAMS accessions, blocked at the edge, `pdf (other path)` = a
second PDF-hosting path, `/sites/default/files/doc_library/...`, discovered only
because it under-collected Regulatory Issue Summaries -- see the correction below):

| collection | years checked | html docs | pdf docs, /docs/ | pdf docs, other path |
| --- | --- | --- | --- | --- |
| Information Notices | 1979-2026 | 424 | 1,818 | 15 |
| Bulletins | 1971-2026 | 230 | 28 | 0 |
| Generic Letters | 1977-2026 | 563 | 14 | 11 |
| Regulatory Issue Summaries | 1999-2026 | **53** | 269 | **127** |
| Preliminary Notification Reports | 2003-2025 | **0** | 118 | 0 |

**This table's first version, published a few hours earlier the same day, was
itself wrong for Regulatory Issue Summaries: it reported 180 "html docs" where the
true figure is 53.** The original `filter_native_document_links` excluded a link
only by checking for `/docs/` in its path, which is where every *other* collection's
PDFs turned out to live, but not where Regulatory Issue Summaries' 2003-onward
documents do -- those are served from `/sites/default/files/doc_library/...`, answer
`200 OK` (not blocked, just a different PDF), and were counted as native HTML by a
check that only knew about one PDF path. Every one of those 127 misclassified links
was then fetched, found to carry no `field--name-field-body` (because it is not
an HTML page at all), and silently dropped by `extract_generic_comm_document` --
with no warning logged, because the *request* succeeded; only the *extraction*
failed, silently, the way a content-shaped failure does. The crawl's actual staged
count for this collection, 53, was correct throughout; the reconnaissance number
this ADR published for it was not. `filter_native_document_links` now excludes any
link ending in `.pdf`, regardless of which path serves it, and a fixture built from
the real `/sites/default/files/...` URL that exposed this is a permanent regression
test (`tests/download/test_nrc_text.py`). Information Notices' and Generic
Letters' small differences from their own first-published figures (439 to 424,
574 to 563) are the same correction, measured smaller because fewer of their
documents happen to route through the second PDF path.

Preliminary Notification Reports is disabled in `sources_text.yaml` rather than
staged empty: every one of its 118 measured document links across all 20
published years routes through `/docs/`. It is named in the brief and kept in the
config, disabled, so the measurement that excludes it is traceable to the
collection it was made against.

**Tier 2, checked and excluded, each for a different reason:**

| candidate | reason | evidence |
| --- | --- | --- |
| NERC Lessons Learned | the publisher names Claude specifically for exclusion | `nerc.com/robots.txt`: `Content-Signal: search=yes,ai-train=no,use=reference` (an express rights reservation under EU Directive 2019/790 Art. 4, by the file's own preamble) and, separately, `User-agent: ClaudeBot` / `Disallow: /`. |
| ISO/RTO operator notices (CAISO, PJM, ERCOT, MISO sampled) | no permissive licence stated anywhere checked; access posture is restrictive where it says anything | CAISO disallows `/resources/*`; ERCOT's `robots.txt` itself returns 403; MISO carries the same `ClaudeBot: Disallow: /` as NERC; PJM has no blanket block but also no licence statement. |
| NREL/OSTI technical reports | the licence question is per-document, which does not scale to a corpus-acquisition step | OSTI's own copyright policy: public access is not public domain, and "for technical reports created in the performance of the contract, permission from DOE is required to establish and claim copyright" -- the marking must be checked per document. `www.nrel.gov` also does not resolve from this network. |

**Floor and target, re-read against the evidence.** The M2 brief set a 30M-token
floor and a 100M-token target against an assumption of four reachable Tier-1
sources. With one reachable, the floor is evidence to report against, not a gate
to iterate toward: per the brief's own words, "the pipeline and its reports are
the gate, not the token count." The measured corpus size and which bound it hit
are reported in the M2a acquisition report and carried into the Gate 6 summary as
a stated limitation, not chased by loosening the source list further.

**What would change this decision.** For NRC LERs and DOE OE-417: either
publishing a bulk route this project can use without impersonating a browser or
crossing a stated `Disallow`; NRC granting a written bulk-export request for
the LERs; or IPv6 connectivity becoming available on the machines this project
runs on, which would reopen the DOE OE-417 host directly (the ORNL mirror
would still be measured thin on the evidence above, corrected access route or
not). For PHMSA: the manual download named above actually happening, and the
retrieved file's free-text verdict clearing the same bar every other source in
this project was profiled against.

**Gate-6 correction, 2026-09-13: source-aware dedup by event number.** The M2b
pre-registered near-duplicate trigger (`near_duplicates.py`) is a random-pair
sample; it measured this corpus's near-duplication at 0.0005% and did not fire.
That measurement is correct on its own terms and was the wrong instrument for
what this corpus actually does: `nrc_event_notifications` republishes the same
event, under a stable event number, across later report days as a story
develops, each later copy holding the earlier text verbatim plus one or more
appended `"* * * UPDATE FROM ... * * *"` blocks. With 21,882 distinct event
numbers spread across tens of thousands of documents, a random pair of two
revisions of the *same* event is a near-impossible draw, so the trigger was
never structurally able to see this pattern -- not a measurement error, a
mismatch between the instrument and the question. This is the author's
correction to the original M2b brief, not a mistake in how the trigger was
built or run.

The keyed measurement this actually needs (`keyed_dedup.py`, run in real
pipeline order -- cleaned, filtered, then exact-deduped, 27,662 documents of
`nrc_event_notifications` reaching this point): 21,882 distinct event numbers,
3,901 with more than one surviving revision. Sampled evidence that "keep the
latest" is the right rule, not merely a plausible one: across 40 sampled
multi-revision groups, the latest revision is never shorter than the earliest
(40/40), and normalized, the earlier document's post-title body appears as a
substring of the later one in 30/40 -- the rest differ only in a reworded
opening line (a title corrected from "STOLEN MOISTURE DENSITY GAUGE" to
"AGREEMENT STATE REPORT - STOLEN MOISTURE DENSITY GAUGE" is typical), not a
content rewrite. **Declared rule, `configs/data/text_v1.yaml`
(`dedup.keyed`):** for `nrc_event_notifications`, keep one document per event
number -- the latest report day. Applied after exact dedup, implemented in
`src/faultline/data/text/keyed_dedup.py`, reported by `DedupStage`
(`reports/data/20260913-142340_all_text_2a6ec5b7/dedup_stats_report.md`):
4,521 documents removed, 1,214,427 whitespace tokens (7,602,753 before this
rule, at the point in the pipeline it runs -> 6,388,326 after; see the
checkpoint report addendum for the token counts in context of every other
stage).

**Gate-6 correction, 2026-09-13: two declared fixed-boilerplate rules.** Direct
inspection of modern-era (post-2020) event notifications found the extractor's
own metadata line pair prepended to 1,316 documents
(`EN Revision Imported Date: .../EN Revision Text:`) and a fixed IAEA
source-category explanation NRC appends whenever an event involves a
"Less than Cat 3" source, in two textually-identical forms distinguished only
by whether the trailing "Pub1227_web.pdf" URL sentence is present (2,616
occurrences) or absent (866 occurrences, used since at least 2005 -- found
while building this rule, not named in the original brief, included because it
is unambiguously the same fixed paragraph). **Declared rules,
`configs/data/text_v1.yaml` (`clean.boilerplate`):** strip both, implemented in
`src/faultline/data/text/boilerplate.py`, reported by `CleanStage`
(`reports/data/20260913-142340_all_text_2a6ec5b7/clean_stats_report.md`):
1,316 and 3,482 matches respectively removed, 419,746 whitespace tokens (4.4%
of the raw corpus) removed by these two rules alone. Three further occurrences
carry a source-side URL typo (`www.pub.iaea.org` for `www-pub.iaea.org`, or a
line-wrapped URL) and are not matched -- a documented, measured gap, not chased
with a broader regex.

A general check followed, as the brief asked: every document was split into
blank-line-delimited paragraphs, normalized, and hashed, counting how many
*documents* (not raw occurrences) each distinct paragraph appears in. Run
against the raw corpus, this finds exactly 7 paragraphs recurring in more than
100 documents, and every one is a short, genuine, formulaic sentence
("The licensee notified the NRC Resident Inspector.", "The NRC Resident
Inspector was notified.", and five near-variants) that recurs because many
independent incident reports end the same way -- not page furniture. **None
are stripped;** the full list is in the checkpoint report addendum. Neither of
the two boilerplate blocks above is found by this sweep: both are joined to
document-specific text by a single newline rather than a blank line, so
neither is ever its own paragraph -- a stated limitation of paragraph-level
hashing as a *discovery* method (it did not need to find them; they were
already found and matched by direct pattern before this check ran).

**Correction, 2026-09-16: PHMSA has a permitted automated route, and the flagged file
was the wrong target.** Source: `reports/data/phmsa_gate_brief_20260915.md`, a
read-only investigation, and the author's ruling on it.

*The false claim.* The PHMSA row above, and `configs/data/sources_text.yaml`'s
`phmsa_pipeline_incidents` evidence, said "there is no independently-hosted export for
this data". That is wrong. The 2026-09-13 check read `27nc-rsge`'s `accessPoints`,
which do point back to `phmsa.dot.gov`, and never read its `metadata.attachments`.
That field lists 15 zip files hosted on `data.transportation.gov` itself, each served
from `https://data.transportation.gov/api/views/27nc-rsge/files/<assetId>?download=true&filename=<filename>`.
`data.transportation.gov/robots.txt` disallows no rule matching `/api/views/`, and it
states `Crawl-delay: 1`. Each file answered `200 OK`, `application/octet-stream` to one
headers-only request on 2026-09-15 (brief, section 2b). Licence: `27nc-rsge`'s Socrata
metadata, `Common Core` `License: http://www.usa.gov/publicdomain/label/1.0/`,
consistent with 17 U.S.C. 105.

| attachment | assetId | bytes |
| --- | --- | --- |
| Gas Distribution Incident Data - January 2010 to present.zip | `fba42a19-f78d-44c9-9a76-4bacfc15fba0` | 1,566,027 |
| Gas Distribution Incident Data - March 2004 to December 2009.zip | `ef2727e4-bb70-4544-b292-9429027a9b14` | 1,076,055 |
| Gas Distribution Incident Data - mid 1984 to February 2004.zip | `7ccf83c5-a778-4c51-ba2d-a9a84e221c7b` | 676,906 |
| Gas Distribution Incident Data - 1970 to mid 1984.zip | `3087a9da-c2f1-4bcd-9951-fa524e08aca7` | 1,079,036 |
| Hazardous Liquid Accident Data - January 2010 to present.zip | `1d547e17-2be1-4a32-9958-a1d5a946ade9` | 4,597,548 |
| Hazardous Liquid Accident Data - January 2002 to December 2009.zip | `928038f8-523b-4003-aeff-79675b193086` | 1,892,458 |
| Hazardous Liquid Accident Data 1986 to January 2002.zip | `2cb38c7d-9a3e-4074-b175-05a5cd0c44a6` | 958,446 |
| Hazardous Liquid Accident Data - Pre 1986.zip | `94be9da7-e996-4ac4-8154-079995bc0326` | 275,191 |
| Gas Transmission & Gathering Incident Data - January 2010 to present.zip | `2b05c2d8-d14a-4c56-ac1c-7d23a4bc31c8` | 2,241,740 |
| Gas Transmission & Gathering Incident Data - 2002 to December 2009.zip | `3f48859a-5658-4f64-acf0-e33e632af625` | 1,240,023 |
| Gas Transmission & Gathering Incident Data - mid 1984 to 2001.zip | `bea0164f-672a-475e-986b-8e45e9634dbf` | 329,445 |
| Gas Transmission & Gathering Incident Data - 1970 to mid 1984.zip | `9f62744f-3372-46f6-aa5b-15cf60261a93` | 548,513 |
| Liquefied Natural Gas (LNG) Incident Data - January 2011 to present.zip | `875819a6-d388-4fa9-9962-2f0b53ffac21` | 459,113 |
| Hazardous Liquid Gravity & Reporting-Regulated-Only Jul 2020_present.zip | `28f0a80f-a155-4294-8d1e-1d46f1237896` | 560,015 |
| Type R Reporting-Regulated Gas Gathering May 2022 to Present.zip | `021f4773-ebc0-4abc-8628-9321af069f69` | 490,509 |

Asset ids were read from `GET /api/views/27nc-rsge.json` through `NrcTextClient` on
2026-09-15 20:41 UTC (server `Date`). The files carry no `Last-Modified`, so how current
they are is unmeasured.

*The flagged file, reclassified.* `PHMSA_Pipeline_Safety_Flagged_Incidents.zip` is
**blocked from a third independent client and network** (curl/8.15.0, the author's
home network, 2026-09-15 20:16-20:18 UTC). The response was `403 Forbidden`,
`Server: AkamaiGHost`, a 519-byte `text/html` "Access Denied" page, with no redirect,
Akamai error reference `#18.ce354317.1789503390.8406901` (`errors.edgesuite.net`).
**No copy exists on the author's machine.** `~/Downloads`, `~/Desktop`, `~/Documents`
and `~/OneDrive` were searched and nothing matched, not even an error page saved under
the name. **It is also the wrong target.** `qdme-9bbm` describes it as an analytical
derivative: PHMSA "add data that are routinely used during data analysis and when
presenting certain 20-year trends", covering serious and significant incidents.
`27nc-rsge` holds the raw per-type incident reports, which is where an incident
narrative would live. `manual_pending` on the flagged file is withdrawn.

*Considered and not taken: automating the author's real Chrome.* Driving the author's
own browser session against the Akamai edge was considered. That means automation over
CDP, or Playwright attached to the real profile. It reads against this ADR's own line.
"The user's decision" above separates a **human** downloading a file from "any other
automated presentation of this project's client as something it is not". Automation
borrowing a real browser session is the automated case, and it would work for the same
reason UA spoofing would. It is also moot, since a permitted automated route now
exists.

*Pre-registered decision rule.* Recorded and committed before the file below is
fetched or read, verbatim:

> Target: 27nc-rsge attachment "Hazardous Liquid - Jan 2010 to present"
> (4,597,548 bytes), fetched through the robots-gated client.
> Free-text test: a column qualifies if its name matches the narrative pattern,
> OR mean length > 80 chars AND distinct-value ratio > 0.5. (The ratio guard is
> the OE-417 lesson — mean length alone can be passed by a long coded field.
> Add this guard to phmsa_manual.py's detector as part of this step.)
> Rule:
>   - no column passes -> EXCLUDE for thinness, same disposition and wording
>     pattern as OE-417; gate closes permanently.
>   - passes but < 250,000 whitespace tokens in this file -> EXCLUDE for
>     thinness (<4% of corpus; not worth a card, licence row, split, eval row).
>   - passes and >= 250,000 tokens -> stage all 2010-onward files, fold into
>     the corpus, fit once with them included.
> Either outcome: M2c starts in this same session.

How it is implemented: the "narrative pattern" is `phmsa_manual.NARRATIVE_HINTS`, a
case-insensitive substring match on the column name (`narrative`, `description`,
`summary`, `comment`, `remark`, `additional_info`, `detail`). "Distinct-value ratio" is
distinct non-null values over non-null values (`DISTINCT_RATIO_THRESHOLD = 0.5`). "In
this file" means the sum over every narrative column of every tabular member. The
target attachment's full name is "Hazardous Liquid Accident Data - January 2010 to
present.zip", assetId `1d547e17-2be1-4a32-9958-a1d5a946ade9`. The robots gate that
fetches it is `download/robots.py`, not `urllib.robotparser`. The stdlib parser reads
`data.transportation.gov`'s file as allow-all, because blank lines separate its
`Disallow` rules from `User-agent: *` (commit `ebfa946`).

**Outcome, 2026-09-16: the pre-registered rule, applied as written.** Measured in
`reports/data/phmsa_manual_20260915.md` (commit `4257351`, after the rule's commit
`7542165`). The target file's one tabular member,
`accident_hazardous_liquid_jan2010_present.txt`, is tab-delimited Windows-1252 with 648
columns. All 5,850 data lines were read as 5,850 rows. 62 columns qualify, all of them
by name. `NARRATIVE` holds 5,820 non-null values, mean 953 characters, distinct-value
ratio 1.000, and 894,467 whitespace tokens. All qualifying columns together hold
**1,030,940 tokens, which is >= 250,000**. The rule's third branch applies: **stage all
2010-onward files, fold them into the corpus, fit once with them included.**

Staged as `phmsa_incident_narratives` in `configs/data/sources_text.yaml`. It covers
the six 2010-onward attachments: hazardous liquid, gas distribution, gas transmission
and gathering, LNG from 2011, hazardous-liquid gravity/reporting-regulated from July
2020, and Type R gas gathering from May 2022. Each zip was fetched through the
robots-gated client, parsed, and only then recorded in the `phmsa` manifest, with
`retrieval_method` unset (this project's automated client). Each non-empty `NARRATIVE`
is one document, `{pipeline_type}_{REPORT_NUMBER}`: 10,033 documents. Every file holds
one row per report number, so no revision dedup is needed. Report numbers do repeat
*across* files, because each form has its own sequence, which is why the pipeline type
prefixes the id. CSV-style quoting left on the field by the tab export is undone.

*A note on the threshold, separate from the rule and not changing its outcome.* Read
literally, the name pattern is broad. 61 of the 62 qualifying columns are
`*_DETAILS`/`*_DETAIL` fields, most of them short "other, specify" answers, and some
are closed code sets: `CAUSE_DETAILS` has 5,850 values at distinct ratio 0.007. The
file's token total therefore includes non-narrative text. Here that changed nothing,
since `NARRATIVE` alone is 3.6 times the 250,000 bar. A future rule of this kind
should apply the distinct-ratio guard to name matches as well. Separately, and as a
staging choice rather than a reading of the rule, only `NARRATIVE` is staged.

*Amendment applied, 2026-09-16.* The detector now reads `name matches AND distinct ratio
> 0.5` (`phmsa_manual.profile_member`; test
`tests/data/text/test_phmsa_manual.py::test_a_narrative_named_closed_code_set_is_not_narrative`),
as ruled on 2026-09-16 and not applied until now. Re-read on the same target file, read-only:
**54 columns qualify instead of 62, and all qualifying columns hold 1,001,924 tokens instead of
1,030,940.** The eight columns that no longer qualify are `CAUSE_DETAILS` (ratio 0.007, 25,456
tokens), `MATERIAL_DETAILS` (0.432, 2,633), `COMMODITY_DETAILS` (0.251, 776),
`PIPE_SEAM_DETAILS` (0.256, 151) and four columns with no values. **The amendment did not
change the PHMSA decision:** `NARRATIVE` alone is 894,467 tokens, 3.6 times the 250,000 bar,
and it is the only column staged. The measured report
`reports/data/phmsa_manual_20260915.md` is not regenerated. It stays the record of the rule
as it was applied. The guard removes closed code sets. It does not remove short "other,
specify" fields with high distinct ratios: 52 of the 54 qualifying columns are still
`*_DETAILS` fields.

**Correction, 2026-09-16: every source keeps a held-out split.** The v1 run
(`20260913-142340_all_text_2a6ec5b7`) used 98/1/1 for every source. It gave
`nrc_reg_issues` zero held-out documents, `nrc_bulletins` a test split of 2 documents
and 1,324 words, and `nrc_gen_letters` a val split of 3 documents and 1,557 words. M2b
requires a held-out split per source, so per-source perplexity can be reported. Splits
that small can fall short of one 2,048-token context and would evaluate as silently
empty. Commit `ebfa946` makes a zero-window split raise at shard time rather than warn.

**Chosen: larger held-out shares for small collections, not a train-only disposition.**
`configs/data/text_v2.yaml` adds `final.source_split_fractions`. Val and test each get
the smallest share in {1%, 2%, 5%, 10%, 20%} whose expected size is at least 25,000
whitespace words, capped at 20%. The share was fixed before any v2 run, from word
totals already measured:

| source | words | share | expected words per held-out split |
| --- | --- | --- | --- |
| nrc_event_notifications | 4,939,151 | 1% | 49,392 |
| phmsa_incident_narratives | 1,669,618 | 2% | 33,392 |
| nrc_gen_letters | 686,503 | 5% | 34,325 |
| nrc_info_notices | 399,881 | 10% | 39,988 |
| nrc_bulletins | 270,290 | 10% | 27,029 |
| nrc_reg_issues | 91,537 | 20% (cap) | 18,307, below the floor |

Event notifications keep the default fraction, so their documents keep exactly their
v1 assignment. The alternative was to mark small collections train-only and report
perplexity for the large sources only. That would keep about 0.3M words (under 4% of
the corpus) in training, but it gives up the register comparison: licensee event
reports against regulator-authored guidance, which is the one contrast per-source
reporting on this corpus can show. `nrc_reg_issues` is reported with the stated caveat
that its held-out splits sit below the floor. The 25,000-word floor guards against
degenerate splits and is not a precision target. At an assumed, not yet measured,
~1.3 BPE tokens per word it is about 16 non-overlapping context windows.

---

## ADR-0017 H3': the status strings' token-level gap is split into convention and vocabulary

**Status:** Accepted; Stage A pre-registered 2026-09-16, before its measurement ·
**Date:** 2026-09-16

**Context.** H3 is withdrawn (ADR-0007). One question it leaves costs nothing to answer.
At the token level, the unit the model sees, **18 of 264** status strings have every BPE
token seen at least 100 times in training. At the word level (lowercase `[a-z]+`), **80
of 264** have every word seen that often (`data/cards/status_code_book.md`). The gap
between the two is a property of how a string is written, not of what words it uses. A
status string starts a line and is capitalised, so its first word encodes as a
string-initial piece that prose rarely produces (`Wind` is `W` + `ind`; prose writes
` wind`). The card counts 60 strings held below the floor by their first token alone.

**H3'.** *Of the 246 strings not covered at the token level, 62 are blocked by surface
convention (the step from 18 to 80) and 184 by genuine vocabulary absence (the step from
80 to 264).* The 184 are not recoverable by narrative pretraining on this corpus: their
words are rare or absent in it (ADR-0007, "H3 withdrawn"). The 62 might be recoverable
at no cost, by writing a status string the way prose writes words.

This decomposition uses the word-level count, 80, as the ceiling on what convention can
recover. Stage A measures the convention share directly, and the two need not agree. A
word can be frequent while the pieces it encodes into after normalization are not.

**Stage A: normalization at encode time, no training, no refit.** All 264 strings are
re-encoded **lowercased with a single leading space** (`" " + s.lower()`) with the frozen
tokenizer `text_bpe_v1_22c56e49`. Token-level coverage is then re-measured with the same
instrument and threshold as the card: every token id seen at least 100 times in that
tokenizer's training shards. The tokenizer is not refitted, and no shard is rewritten.

**Decision rule, pre-registered here and in the M3 entry brief of 2026-09-16, before the
normalized count was computed:**

- **more than 50 of 264** covered after normalization: surface convention is confirmed as
  the dominant barrier among the recoverable strings;
- **50 of 264 or fewer**: convention is only a partial explanation, and the rest of the
  gap is at the segmentation level. The words are frequent, but the tokenizer does not
  split these strings into frequent pieces. That is reported as the finding, and the claim
  is not re-worded to fit the number.

Reported with it: the per-string diff (which strings change side, in either direction);
how many of the 60 first-token failures normalization fixes; and characters and bytes
per token before and after, against the held-out narrative baseline of 4.63-5.29 bytes
per token.

Normalization is an encoding convention for status strings in the joint stream (M3). It
is not a change to the tokenizer, the vocabulary or ADR-0003's layout.

**Stage A outcome, 2026-09-16 (`reports/data/h3prime_stage_a_v1_20260916.md`, `faultline
inspect status-convention`).** The raw row reproduces the card first: 18/264 covered, 60
first-token failures, and 63/264 with a leading space alone.

| convention | every token frequent | chars/token |
| --- | --- | --- |
| raw | 18 / 264 | 4.15 |
| leading space only | 63 / 264 | 4.67 |
| lowercase only | 32 / 264 | 4.33 |
| **normalized, lowercased after a space (pre-registered)** | **80 / 264** | **4.82** |

**80 > 50: surface convention is CONFIRMED as the dominant barrier among the recoverable
strings.** Normalization covers 67 strings and loses 5, net +62. It fixes 45 of the 60
first-token failures. Characters per token rise from 4.15 to 4.82, inside the held-out
narrative range of 4.63-5.29 bytes per token. Normalized strings compress like the prose
the tokenizer was fitted on. The leading space does most of the work (18 to 63); lowercase
adds the rest (to 80).

**The decomposition holds by count, not by set.** The normalized count equals the word-level
count, 80, but only 72 strings are in both sets:

- 8 strings are token-covered after normalization although a word is rare (`Mains
  connection`, `Tower resonance`, `WEC shut down`, ...);
- 8 have every word frequent and still encode a rare piece (`PLC hardware error`, `Park
  master stop`, `Particle sensor defect`, ...). This residual is below the word level: the
  frozen tokenizer splits a word into rare pieces, or the word rule ignores a digit or a
  symbol.

So of the 184 strings still uncovered after normalization, 176 carry a rare or absent word,
which is the vocabulary absence narrative pretraining cannot supply, and 8 are blocked below
the word level. The 5 strings normalization loses include `Yaw error`: raw it is `Y` `aw`
` error`, all frequent, and `yaw` never occurs in the corpus. **Token-level coverage is
therefore a floor on how often pieces were seen. It does not show that a word is known.**
That caveat applies to every token-level count in this record.

**Consequence.** Status strings enter the M3 joint stream **normalized by default** (recorded with the M3 mixture,
the `tel+status` stream), and unnormalized strings are a declared ablation arm. Nothing in
Stage A tests whether the model uses the covered strings. Stage A is about encoding only.

### Amendment, 2026-09-16 (M3 pre-run brief, E1) -- H3' restated as a behavioural claim; the metric replaced

**The instrument is withdrawn.** Token-level coverage cannot fail for an absent word
(`docs/INSTRUMENT_AUDIT.md`, entry 11). Byte-level BPE has no out-of-vocabulary token, so a
missing word falls back to shorter, more frequent pieces and can *raise* coverage. `Yaw error`
is covered raw, and `yaw` occurs 0 times in training. The Stage A verdict above ("80 > 50,
CONFIRMED") is kept as the record of what was measured. It is no longer read as evidence
about word knowledge, and every count built on it below is superseded.

**Withdrawn: "62 blocked by convention, 184 by vocabulary absence".** That decomposition
subtracted two counts of 80 that are not the same set: the word-level and normalized-token
80s share 72 strings. The measured change from raw to normalized is **67 strings gained and
5 lost**, not a block of 62. The residual 184 is **176 with a rare or absent word plus 8
blocked below the word level**. **The mechanism is the word-initial leading space more than
the casing.** A leading space alone takes coverage from 18 to 63, and lowercase alone to 32.

**H3', restated.** *Writing a status string the way prose writes words is a treatment on
what the pretrained text model assigns to it. Normalization (`" " + s.lower()`) is the
treatment, and the per-string NLL difference under the frozen text-only checkpoints
(normalized minus raw, in nats per string, paired over the 264 strings) is the effect size.*
Two companion claims are read on the same instrument: that the effect comes more from the
leading space than from casing, and that strings with an absent word stay costly after
normalization (the absence claim).

**Measured, 2026-09-16** (`faultline model status-nll`,
`reports/data/h3prime_behavioural_v1_20260916.md`; S2 and S3 text checkpoints, forward
passes only). The primary context is `<sep>`, declared before scoring. It is biased against
normalization: 0 of 502 held-out documents start with a space. A mid-prose context is
reported beside it.

| checkpoint | context | normalized - raw | leading space only - raw | lowercase only - raw | strings lower than raw |
| --- | --- | --- | --- | --- | --- |
| S2 | `<sep>` | **-5.33** [-6.12, -4.56] | -3.72 [-4.29, -3.18] | -1.64 [-2.14, -1.14] | 216 / 264 |
| S3 | `<sep>` | **-5.67** [-6.51, -4.84] | -3.27 [-3.84, -2.72] | -1.44 [-1.99, -0.89] | 217 / 264 |
| S2 | mid-prose | -7.75 [-8.53, -6.97] | -5.18 [-5.76, -4.63] | -2.24 [-2.79, -1.70] | 240 / 264 |
| S3 | mid-prose | -8.66 [-9.54, -7.79] | -5.37 [-6.00, -4.76] | -2.37 [-2.96, -1.78] | 229 / 264 |

Nats per string; the brackets are bootstrap 95% intervals over strings. **The convention effect
is real and not an artefact of the metric.** Normalization lowers NLL by about 5.5 nats a
string at the context biased against it, and every interval excludes zero. The leading space
carries about twice the casing's share (-3.72 against -1.64 at S2), as the counts said. Raw
strings average 51.2 nats (S2), so this is about a tenth of a string's cost.

**The absence claim** (normalized, `<sep>`, nats per staged byte; S2 then S3). Every word
frequent (80 strings): 1.63 / 1.65. A word rare, none absent (131): 2.11 / 2.17. A word
absent (53): 2.64 / 2.71. The **reference scale** is held-out narrative text under the same
checkpoints: 1.20-1.32 nats/byte over the first 2-16 tokens of a document (S2), and 1.26 at full
context. Even strings whose every word is frequent cost 1.3 times narrative text per byte, and
strings with an absent word cost 2.1 times. Normalization narrows the gap for the absent group
least (2.77 to 2.64, against 1.91 to 1.63 for the frequent group). The 8 strings Stage A counted
as covered at the token level only cost 2.30 nats/byte, as much as the vocabulary-absent residual
(2.26). That is entry 11's defect, seen in behaviour.

**Single-token-word rate** (normalized; a word is a pretokenizer letter chunk, and one token
means an exact vocabulary entry for its bytes, with 0 disagreements from the encoder).
Mean over strings 0.818, median 1.0. **144 strings have every word one token, 116 some, and 4
none.** Of Stage A's 80 covered strings, 65 have rate 1 and 15 do not. By word status the mean
rate is 0.966 for every word frequent (72 of 80 at rate 1), 0.826 for a rare word, and 0.576 for
an absent word (2 of 53 at rate 1). The rate can be fooled only where an absent abbreviation is
spelled like a frequent prefix piece (` conv`, ` electr`, ` transf`, `err`). The rate agrees
with the NLL ordering; token coverage did not.

**Consequence.** The M3 default stays **normalized** status strings. The decision now rests on
the NLL effect, not on the coverage count. The raw arm remains the declared ablation. Nothing
here shows that the joint model *uses* a string. It shows that the text-only model finds
normalized strings less surprising, and that strings with absent words stay surprising.

### Ruling, 2026-09-16 (E0-E5 ruling, E1) -- the context argument is load-bearing, the effect is additive at S2, and the single-token-word rate is retired

**The `<sep>` argument is load-bearing, and it stands verbatim.** From the amendment above:
"The primary context is `<sep>`, declared before scoring. It is biased against normalization: 0
of 502 held-out documents start with a space." The headline effect (-5.33 at S2, -5.67 at S3) is
read at the one context in which the model never saw a leading space after a boundary. A
convention effect that survives there is not produced by the choice of context. The mid-prose
figures (-7.75 and -8.66) are larger, and they are not the headline for that reason. Any later
restatement of H3' that moves the primary context to mid-prose would remove the ground the
effect stands on.

**The two parts add up at S2, and not at S3.** At S2, `<sep>`, the leading space alone gives
-3.72 and lowercase alone -1.64: **-3.72 + -1.64 = -5.36, against -5.33 measured** for both
together, 0.03 nats apart and well inside either interval. At S2 the two parts of the convention
act as separate, additive terms. Read from the same table, the sum is not the measured effect
elsewhere: S3 at `<sep>` sums to -4.71 against -5.67 measured, S2 mid-prose to -7.42 against
-7.75, and S3 mid-prose to -7.74 against -8.66. At the larger rung and in prose, the combined
effect exceeds its parts. "Additive" is a statement about S2 at `<sep>` only.

**The single-token-word rate is retired as a primary metric.** It was introduced with this
amendment as the instrument that "checks exactly whether the word's surface form exists as one
vocabulary entry". Read against its own distribution
(`reports/data/h3prime_behavioural_v1_20260916.md`, section a), it cannot carry the claim:

- **It saturates.** The median over strings is 1.0. **144 of 264 strings (55%) score exactly 1,**
  so it cannot order more than half the code book.
- **It disagrees with the coverage metric it replaced, in both directions.** 144 strings score 1,
  of which 65 are among Stage A's 80 token-covered strings, so **79 strings score 1 that coverage
  called uncovered**. And **15 of the 80 strings coverage called covered score below 1**. Neither
  instrument is a refinement of the other.
- **What separates strings is word frequency, not tokenization.** By the string's rarest word, 72
  of 80 all-frequent strings score 1, against 2 of 53 strings with an absent word. The rate tracks
  how often the words occur in training, which the word-status partition already states directly.
  It adds no information about segmentation that the NLL does not measure better. The report keeps
  printing it, as the record of what was measured. No H3' claim reads it.

The behavioural NLL is the only primary instrument for H3'. The retirement is audit entry 12
(`docs/INSTRUMENT_AUDIT.md`).

**The absence figures, 2.64 and 2.26, come from two different partitions.** Both are S2,
normalized, `<sep>`, mean nats per staged byte. They do not contradict each other:

- **2.64** is the **"a word absent"** class of the **word-status partition**. Every string is
  placed by its rarest word's count in `operator_narratives` training text, in three classes:
  every word seen at least 100 times (80 strings), a word seen 1-99 times and none absent (131),
  and **at least one word seen 0 times (53)**. The class holds absent words only.
- **2.26** is the **"residual, vocabulary-absent"** class of **Stage A's four-class partition**
  (word-level coverage crossed with normalized token-level coverage): **not token-covered after
  normalization, and with at least one word seen fewer than 100 times (176 strings)**. That is
  the 131 rare and 53 absent strings minus the 8 that are token-covered. It mixes rare words
  (2.11 by the first partition) with absent ones (2.64), which is why its mean sits between them.

"Vocabulary-absent" in the Stage A class name means below the 100-occurrence floor, not
zero occurrences. Where this record says "absent" without the Stage A class name, it means zero.

---

## ADR-0018 The M3 joint mixture: three named streams, a declared ratio, and budgets in tokens seen

**Status:** Accepted; shards written, nothing trained · **Date:** 2026-09-16

**Decision.** The joint model is pretrained on a mixture of exactly three stream types. Code
(`faultline.training.mixture.STREAMS`), configuration (`configs/train/joint_v0.yaml`) and
this record use these names and no others:

| stream | what it is | paired? |
| --- | --- | --- |
| `tel` | telemetry windows: the M1 fixed-order stream, `<sep>` then one bin token per core channel | unpaired |
| `txt` | narrative documents: the M2 NRC and PHMSA text at joint ids | unpaired |
| `tel+status` | telemetry windows with their own status strings, each wrapped as `<txt> ... </txt>` after its step | **paired** |

**The narrative corpus is not paired with wind telemetry.** `txt` is nuclear and pipeline
regulatory text: NRC event notifications and generic communications, and PHMSA incident
narratives. No document in it describes a wind turbine, and none is aligned in time or
place with any telemetry row. It enters the model as unpaired text, and nothing in M3 may
be reported as if it were paired. H3, the claim that it would transfer status meaning, is
withdrawn (ADR-0007). **`tel+status` is the only genuinely paired cross-modal signal in the
project.** It pairs each training site's telemetry with the status messages that same
turbine logged.

**How `tel+status` is written.**

- *Attachment.* A message follows the telemetry of the first step at or after its start,
  its start rounded **up** to the 10-minute grid. An event label at step `t` counts starts in
  `(t, t + H]`, so rounding down would show a window a message that its own step's label
  still treats as the future. A message whose step is not in the final rows is not written,
  and the build counts it.
- *Convention.* Strings are **normalized by default**, lowercased after one space
  (`normalize_status`, ADR-0017: 80 of 264 strings have every token frequent, against 18
  raw). The provider's own casing, recovered from the code book since the status stream is
  stored lowercased, is the **declared ablation**. Both variants are written as shards, and
  the configuration refuses a raw arm without a normalized arm of the same mixture.

**How `tel` and `txt` are written.** `tel` is the M1 shards, unchanged. The build re-encodes
every run with the joint vocabulary and checks it against the M1 bytes before recording a
run index; it writes no token file. `txt` is the M2 text shards shifted into the text region
(`1184 + i`). The M2 shards' local `<sep>` (32,768) becomes the structural `<sep>` (8), so
token counts are unchanged. That gives `<sep>` two roles, a step boundary in telemetry and a
document boundary in text. The alternative, `</txt> <txt>` at every document boundary,
costs one token a document and was not taken.

**Windows.** 2,048 tokens for every stream (the M2 context), starting on every sixth step
for the telemetry streams (M1's stride), and never crossing a split or a segment.

**Arms, the ratio, and the budget.**

| arm | role | `tel` | `txt` | `tel+status` | status strings |
| --- | --- | --- | --- | --- | --- |
| `joint` | default | 30% | 20% | 50% | normalized |
| `joint_status_raw` | ablation | 30% | 20% | 50% | raw |
| `tel_only` | control | 100% | -- | -- | -- |

**Every arm is budgeted in tokens seen, 50,000,000, one number for all arms.** GPU-hours
are an observation, and the schema has no field in which a wall-clock cap could be set.
Every run report states which bound bound, and by construction it is tokens. The ratio and
the budget are set together by one rule: **no stream repeats.** `txt` holds 10,043,874
training tokens, so its 20% share (10,000,000) is one pass, as in M2. `tel+status` takes the
largest share because it is the only paired signal. `tel` takes the rest. `tel_only` is the
equal-token control: a joint arm that beats M1 by seeing more tokens is not evidence for the
joint design. `tel` and `tel+status` draw on the same telemetry, so one step can appear in
both streams of an arm.

**What this record does not decide.** The evaluation harness, the rung and the run order.
No arm has been trained.

**Measured, 2026-09-16 (`faultline model mixture-shards`,
`reports/data/joint_mixture_v0_20260916.md`; shards in `data/shards/joint/joint_v0_9876bd4e`,
not committed).** Every `tel` run re-encoded equal to the M1 bytes. Training tokens available
to the arms:

| stream | train tokens | arm share | planned tokens | passes |
| --- | --- | --- | --- | --- |
| `tel` | 61,601,722 | 30% | 15,000,000 | 0.24 |
| `txt` | 10,043,874 | 20% | 10,000,000 | 1.00 |
| `tel+status`, normalized | 65,664,814 | 50% | 25,000,000 | 0.38 |
| `tel+status`, raw | 65,854,388 | 50% (ablation) | 25,000,000 | 0.38 |

Status messages make up 6.4% (Kelmarsh) and 6.1% (Penmanshiel) of normalized `tel+status`
training tokens: 248,062 and 490,073 messages. Raw casing costs 189,574 more training tokens
than normalized, which is H3' Stage A's compression gain measured on the stream. Messages not
written, because their step is not in the final rows: Kelmarsh 2,887 of 504,180, Penmanshiel
4,923 of 839,303, Hill of Towie 275. Hill of Towie's test split carries 891,253 messages,
18.9% of its tokens, almost all generator cut-in and cut-out. No stream repeats in any arm;
`tel_only` sees 0.81 passes. Projected GPU-hours per arm, an observation: S2 8.5, S3 10.0.

**What would change this decision.** A measured sequence cost of `tel+status` that crowds
telemetry out of a window; evidence that the shared `<sep>` confuses step and document
boundaries (then `</txt> <txt>` framing); or a larger licence-clean narrative corpus, which
would let the budget grow without repeating `txt`.

### Rulings and records, 2026-09-16 (M3 pre-run brief), before any M3 run

**Resource ruling: all three arms at S2 only.** The rung is fixed for **comparability, not
performance**. Every arm runs at one rung, so an arm difference cannot be a rung difference.
S3 runs on the `joint` arm alone, and only if budget remains after the S2 arms. The ruling was
made against the projection above (3 x 8.5 = 25.5 GPU-hours). Its basis is comparability, so it
does not change if the projection does.

**The projection above is wrong by about 50 times, measured.** It was taken from the M2 text
runs' rate at micro-batch 16, and at a 2,048-token context over a 33,952-id output softmax,
micro-batch 16 does not fit the card's 8 GB. It spills into shared memory. Measured on
2026-09-16 at S2 on the joint vocabulary with random telemetry ids and 32 windows per step
(throughput only, no run): micro-batch 8 x 4 gives **24,046 tokens/s** (6.91 GB peak, at
the limit); **4 x 8 gives 89,817 tokens/s (3.56 GB)**; 2 x 16 gives 86,765 tokens/s (1.89 GB). At
4 x 8 a 50,000,000-token arm trains in about **0.15 GPU-hours**, validation excluded, not 8.5.
The M2 runs' reported token counts and losses are unaffected, because their budgets were in
tokens. Only their wall clock, and projections built on it, carried the spill. The M3 runs use
4 x 8, the same 32 windows per optimiser step as M2's 16 x 2. The consequence for the S3
condition above ("only if budget remains") is left to the user.

**Hypothesis for M3, not a finding: the text rungs may not be comparable for a reason other than
corpus size.** D4 (`reports/data/text_pretrain_curves_v1_20260916.md`) found S3 better than S2
up to about 3.3M tokens and worse from about 4.9M. For an undertrained pair that runs
backwards: more capacity should help more as tokens accumulate, not less. The ordinary cause
is a peak learning rate tuned at S2 (6e-4, shared) being too high for S3's width. If that is
the cause, the S2/S3 comparison is confounded by the learning rate as well as limited by the
corpus. Recorded so that no M3 claim treats the text rungs as comparable before it is tested.

**Evaluation gap at the held-out site.** 275 Hill of Towie status messages are not written into
`tel+status`, because their step is absent from the final telemetry rows (measured above). Hill
of Towie is the held-out site, so the gap is recorded on its card
(`data/cards/hill_of_towie.md`, "Evaluation gaps") and in the roadmap.

---

## ADR-0019 Positive-aware risk training: balanced sampling, and the prior correction as part of the method

**Status:** Accepted; implemented and tested, no risk run of it yet · **Date:** 2026-09-16

**Context.** M1e's risk arms trained at the natural base rate and saw 882 positives in 40,000
windows; the control sat at the prior, H1 went UNTESTED (ROADMAP, M1 results). M3 step 0
pre-registered the remedy, and `configs/train/telemetry_v1.yaml` fixed its values
(`904ff77`). This record states the method in one place, because one part of it is not a
detail: the base rate the model is trained at is not the base rate it is scored at.

**Decision 1: balanced sampling, not `pos_weight`.** 16,524 of 749,387 stride-6 training
windows are positive (2.21%). `pos_weight` keeps that rate, so showing a head 16,000 positives
would cost about 725,000 windows an arm, and about half the steps would still carry no
positive. Balanced sampling at a positive fraction of 0.5 shows 16,000 positives in 32,000
windows, and every step carries 16. Budgets are stated in positives seen.

**Decision 2: the prior correction is applied before any calibration metric or abstention
threshold.** A head trained on half-positive batches learns a 50% prior. Its probabilities
are miscalibrated against the true prior **by construction**, and this project's claim is
*risk-calibrated* abstention, so an uncorrected probability would make that claim false
before any model is trained.

The correction is **logit adjustment** under label shift (the windows given a label are the
same in training and in deployment; only the class mix changes). Per class `c`, subtract
`log(pi_train_c / pi_true_c)` from its logit. The head has one binary logit `z = z_1 - z_0`,
so both classes' terms enter, and the correction is one constant:

    z_true = z_train - log(pi_train / pi_true) + log((1 - pi_train) / (1 - pi_true))
           = z_train + logit(pi_true) - logit(pi_train)

`pi_train` is the declared positive fraction (0.5). `pi_true` is the positive share of the
training windows at the training stride, measured by the sampler (`natural_rate`, 2.21%), and
not the evaluation split's rate, which a deployed model does not know. The offset is
-3.79 nats. Applying the positive class's term alone, `-log(0.5 / 0.0221)`, would under-correct
by `log(0.9779 / 0.5)` = 0.67 nats and leave scores at about twice the prior.

**The ordering is enforced in code, not by convention.** `faultline.evaluation.calibration`
computes calibration (mean predicted rate, expected calibration error) and abstention
thresholds only from `NaturalRateScores`. The only constructor is `at_natural_rate`, which
applies the offset, and a raw logit array is refused at run time as well as by the type
checker. AUPRC, a ranking metric, is unchanged by a constant shift and is read either way.

**Tested behaviourally, not only algebraically.**
`tests/evaluation/test_calibration.py::test_a_balanced_head_corrected_to_the_prior_recovers_the_true_base_rate`
trains a logistic head through `BalancedWindowSampler` on windows at a 3% natural rate and
scores 40,000 held-out windows at that rate. The windows' training natural rate is 2.97%, and the held-out rate is 2.89%. **Uncorrected, the mean predicted probability is 13.8% (ECE 0.110). Corrected, it is 3.07% (ECE 0.0019),** inside 15% of the true rate, which the test asserts. The one-term rule gives 4.08%, above the prior as the algebra says. The test trains with a decaying learning rate, as every run here does. A first version at a constant rate read 3.73%: the last iterate of an undecayed run is a noisy draw around the fit, and calibration reads the last iterate.

**What the correction assumes, and what would break it.** Label shift: `p(window | label)` is
the same in training and at the site scored. That fails under covariate shift, which is what a
held-out site is. At Hill of Towie the correction brings the prior to the training sites'
2.21%, not to Hill of Towie's own rate. The gap between the corrected mean prediction and a
held-out site's base rate is therefore reported as a measured shift, never absorbed into the
correction. A site-specific prior would need that site's labels, and using them is not
held-out evaluation.

**What would change this decision.** A calibration method fitted on validation data
(temperature or Platt scaling) that beats the analytic offset on the training sites' held-out
split. It would be fitted after the correction, not instead of it, and on validation only.

### Correction, 2026-09-16 (E0-E5 ruling, E3) -- the one-term form was wrong; this record supersedes the evaluation design's section 4

**Supersedes section 4 of `FaultLine_M3_evaluation_design_2026-09-16.md`** (the M3 evaluation
design document; it is not a file in this repository). That section wrote the prior correction in
the one-term, per-class form, subtracting `log(pi_train / pi_true)` from the positive logit alone.
**That form is wrong for this head.** The head emits one binary logit, `z = z_1 - z_0`, so the
negative class's term enters with the opposite sign. The correct form is the two-term offset
recorded above, `z_true = z_train + logit(pi_true) - logit(pi_train)`, and the code and tests
already implement it. Where the design document and this record disagree, this record holds.

**Verified independently.** The ruling recomputed the one-term form's shortfall,
`log((1 - pi_true) / (1 - pi_train))`, and got **0.664 nats**, against **0.67** reported above.
Both are right, at different priors. 0.664 is the shortfall at the calibration fixture's
held-out rate of 2.89% (0.6638; 0.6630 at the fixture's training rate of 2.97%). 0.67 is the
shortfall at the project's training natural rate of 2.21% (0.6708). The algebra agrees in both
cases. `tests/evaluation/test_calibration.py::test_the_one_term_multiclass_rule_would_still_read_above_the_prior`
checks the shortfall against the same expression to 1e-5.

**The interval on 3.07% against 2.89%.** The corrected mean prediction over-reads the held-out
rate by **+0.18 percentage points, a ratio of 1.063: about 6% relative.** A paired bootstrap over
the fixture's 40,000 held-out windows (2,000 resamples, seed 20260916, mean prediction and
observed rate drawn together from one resample) gives:

| quantity | point | 95% interval |
| --- | --- | --- |
| corrected mean prediction | 3.070% | [2.947%, 3.196%] |
| held-out positive rate | 2.888% | [2.722%, 3.053%] |
| over-read, predicted minus observed | +0.182 pp | **[+0.072, +0.290] pp** |
| over-read, predicted over observed | 1.063 | **[1.024, 1.105]** |

`tests/evaluation/test_calibration.py::test_the_corrected_over_read_is_small_and_its_interval_is_on_record`
recomputes the interval and pins it (above zero, below a ratio of 1.15).

**Whether ECE 0.0019 is enough to call this small residual miscalibration.** ECE is not enough
by itself. It bins by confidence, and at a 3% rate nearly every window sits in the lowest bins,
so a 6% relative shift in the mean moves ECE by about 0.002 whether the shift is real or noise.
**The held-out-set interval is what decides it,** and it confirms the over-read: the paired
interval excludes zero, and it bounds the over-read at no more than 10.5% relative. Most of it has
a known source. The correction reads scores at the **training** sample's rate, which is 2.97% here,
and the held-out sample drew 2.89%. Against the rate the correction targets, the corrected mean
over-reads by **3.4%**. The other 2.8% is the difference between the two samples. The correction
reads the training prior by design, and a model cannot know the held-out rate. So: a small
residual miscalibration of about 3% relative, confirmed on a held-out interval, plus a sampling
difference between the two synthetic sets. That interval does not include the uncertainty of the
training rate itself (40,000 windows, standard error about 0.085 pp).

### Addendum (F2), registered 2026-09-17 before its code or run -- the balanced mean rate, and π_train

**Why.** The correction's `pi_train` is the **declared** positive fraction, 0.5. That is right
only if the head has actually learned a 50% prior on the balanced batches it was trained on. Every
trained probe here selected an early checkpoint: step 166 under ADR-0021 and ADR-0023, and step
200 under ADR-0024's G3 cadence, a fifth of the way into a 1,000-step run. On Hill of Towie, the
step-166 head's corrected mean prediction was 0.0138. The step-200 head's is 0.0178. Both are below
the training natural rate of 0.0221 that the correction targets. An early head whose mean
prediction on balanced batches sits below 0.5 would produce exactly that under-read, and the
declared correction would not remove it. This addendum measures it.

**Where the band comes from.** The F-brief's text for F2 is not in this repository. The band and
the rule below are fixed **by this registration**, before any number from the measurement exists.
The user can supersede them.

**The checkpoint.** The in-force probe as G3 selected it: §a, step 200
(`checkpoints/probe_cadence_v0_c9646288/S2_trained_seed1_probe.pt`). The step-166 head that G1
re-ran (`checkpoints/paired_control_v0_b446304a/final_position/S2_trained_seed1_probe.pt`) is
measured beside it the same way. That row is reported, and it decides nothing.

**The measurement.**

- **The balanced set:** `balanced_training_sampler` over the training split (stride 6, Kelmarsh +
  Penmanshiel, positive fraction 0.5, 16 windows a batch), drawn with its own seed **20260917**,
  **1,000 batches: 16,000 windows, 8,000 of them positive.** This is the distribution the head was
  trained on. It is not a held-out set, and it does not need to be: the question is what prior the
  head learned on the data it saw.
- **The balanced mean rate `m`:** the mean of `sigmoid(z)` over those windows, where `z` is the
  head's logit with **no** offset. Reported with a window-bootstrap 95% interval (2,000
  resamples, seed 20260916), and separately over the positive and the negative windows.

**The rule.**

- **If `m` lies in [0.45, 0.55]**, the declared `pi_train` = 0.5 stands, and the offset stays
  -3.7921 (`logit(natural_rate) - logit(0.5)`). A head mean of 0.45 is a logit shift of about 0.2
  nats. At a 2% prior that moves the corrected mean prediction by about a fifth. A shift inside the
  band is not corrected.
- **If `m` lies outside it**, the correction uses the **measured** balanced prior. `c` is the
  constant solving `mean(sigmoid(z + c)) = 0.5` over the balanced set (bisection to 1e-6), and the
  offset becomes `c + logit(natural_rate) - logit(0.5)`. From F2 on, every calibration read of
  this checkpoint (F5 included) uses that offset, with the declared offset reported beside it.
- **Either way, nothing ranked changes.** The offset is one constant, so AUPRC, every interval
  on it and ADR-0024's verdicts are untouched.

**Reported under both offsets, deciding nothing:** the corrected mean predicted rate and ECE on the
pooled Kelmarsh + Penmanshiel test split at stride 12 (and per source), and on Hill of Towie's
12,000-window subsample. Beside each: that set's base rate and the training natural rate 0.0221.
Under ADR-0019, the gap to a held-out set's base rate is a measured shift, not a correction
target. The training sites' test split is 2022-2024, and it carries ADR-0009's caveat on what is
labelled.

**Carried from G3.** The in-force checkpoint is step 200, not step 166. ADR-0024's G1 verdict was
read on the step-166 head, and it is not re-run.

### F2 outcome, 2026-09-17 -- inside the band: the declared π_train = 0.5 stands for the in-force probe

`faultline model prior-band` (`configs/train/prior_band_v0.yaml`; `reports/data/prior_band_v0_20260917.md`,
git_sha `38fef95`, 1.6 minutes) drew 16,000 balanced training windows (8,000 positive, sampler
seed 20260917) through each head.

| head | balanced mean rate | 95% interval | on positives / negatives | shift to 0.5 | band [0.45, 0.55] |
| --- | --- | --- | --- | --- | --- |
| **step 200, G3, in force (decides)** | **0.4876** | [0.4857, 0.4894] | 0.5198 / 0.4553 | +0.0528 nats | **inside** |
| step 166, G1 re-run (reported) | 0.4375 | [0.4355, 0.4396] | 0.4725 / 0.4025 | +0.2702 nats | outside |

**Verdict: inside. The declared `pi_train` = 0.5 and the offset -3.7921 stand for the step-200
probe.** No shift is applied, and F5 reads this checkpoint's calibration under the declared
offset. As G3 recorded, ADR-0024's G1 verdict was read on the step-166 head, and it is not re-run.

Corrected calibration under both offsets (reported, deciding nothing; training natural rate 0.0221):

| head | windows | base rate | declared: mean rate / ECE | measured shift: mean rate / ECE |
| --- | --- | --- | --- | --- |
| step 200 | pooled training-site test, stride 12 | 0.0388 | 0.0176 / 0.0212 | 0.0186 / 0.0203 |
| step 200 | Kelmarsh test, stride 12 | 0.0368 | 0.0171 / 0.0198 | 0.0180 / 0.0189 |
| step 200 | Penmanshiel test, stride 12 | 0.0413 | 0.0183 / 0.0230 | 0.0193 / 0.0221 |
| step 200 | Hill of Towie, 12,000-window subsample | 0.0333 | 0.0178 / 0.0155 | 0.0188 / 0.0145 |
| step 166 | pooled training-site test, stride 12 | 0.0388 | 0.0139 / 0.0248 | 0.0181 / 0.0209 |
| step 166 | Hill of Towie, 12,000-window subsample | 0.0333 | 0.0138 / 0.0195 | 0.0180 / 0.0153 |

Recorded beside the verdict, deciding nothing:

- **The step-166 head had not learned the balanced prior.** Its mean of 0.4375 is a 0.27-nat
  under-read, and re-centring it moves its Hill of Towie corrected mean from 0.0138 to 0.0180.
  That accounts for most of the gap ADR-0021 recorded between 0.0138 and the natural rate of
  0.0221.
- **A residual under-read remains that the prior does not explain.** Even re-centred, both heads
  put a corrected mean of 0.018 to 0.019 on every test set, below the training natural rate of
  0.0221 that the correction targets. On test windows, the head's scores sit lower than on
  training windows. That is a shift between the 2016-2020 training windows and the 2022-2024 test
  windows, in the covariates or in what is labelled (ADR-0009). It is not a prior-correction
  error, and under ADR-0019 it is reported as measured, not absorbed.
- **The training sites' test base rate (0.0388) is 1.8 times the training natural rate
  (0.0221).** A correction that reads scores at the training prior under-reads it by construction.
  The temporal split's positive share moved, which is ADR-0009's caveat, measured.

---

## ADR-0020 The seed-variance probe, and the smallest held-out-site AUPRC difference worth claiming

**Status:** Accepted; the line is registered **before** either probe run · **Date:** 2026-09-16

**Context.** ADR-0018 plans three arms (`joint`, `joint_status_raw`, `tel_only`), each run
once. If two runs of one arm that differ only in seed land further apart on the held-out site
than any arm difference we would claim, then a one-seed arm comparison cannot tell an arm
effect from a seed. That is measured before the full run by running `tel_only` twice at half
budget (25,000,000 tokens), differing only in seed, and reading one number.

**The line: 0.010 absolute AUPRC on Hill of Towie test.** Decided blind, with no probe run
made. The only information used was already in the record:

- Hill of Towie is the held-out site. On the evaluation subsample every risk read-out uses
  (`telemetry_v1.yaml`: stride 1, 12,000 windows, seed 20260912) it holds 399 positive
  windows, a **base rate of 0.033** (M1e ladder record).
- M1e's S2 and S3 risk arms scored **0.032 to 0.046** there, lift 0.95 to 1.39, from models
  that differed in rung, arm and initialisation, not only seed.

A difference of 0.010 is 0.3 of the base rate in lift. Below that, two arms whose held-out
scores both sit within about 1.4 base rates of chance do not rank differently in any way an
abstention threshold would act on, and a claim resting on a smaller difference would rest on
the third decimal of a metric computed from 399 time-clustered positives. The line is not
set larger, because M1e's whole spread across rungs and arms was 0.015. A line above that
would declare every difference the project has ever measured unclaimable before looking.

**The pre-registered rule** (the M3 pre-run brief, verbatim in substance): if the between-seed
gap in held-out-site AUPRC is **at or above 0.010**, a three-arm n=1 design is uninformative,
and the plan changes to **two arms (`joint` vs `tel_only`) at three seeds**. Below 0.010 the
three-arm design stands. Either way the full run is not started by the probe.

**The read-out the line refers to.** Hill of Towie test AUPRC of the **frozen probe** of M3
step 0 (`telemetry_v1.yaml`: balanced, 16,000 positives, probe rate 2e-3, prior-corrected
per ADR-0019) on the pretrained S2 backbone, read on M1's 1,872-token risk windows.
The frozen probe is chosen over the fine-tune because the arms differ only in pretraining. A
fine-tune spends 16,000 positives rewriting the backbone, and at M1e the fine-tune and the
random control were not separable, so it would wash out the property under comparison. The
same read-out applies to the arm comparison the verdict governs.

**Held fixed between the two seeds:** the shards, the evaluation windows, the rung (S2), the
budget, the micro-batch and accumulation, the schedule, and the probe stage. The seed sets
the backbone initialisation, the pretraining data order, the head initialisation and the
balanced sampler's order. That is the variance a one-seed arm carries.

**What this record does not decide.** Whether a gap below the line licenses a claim between
arms. It licenses only the three-arm design at one seed. Any claim is still read against the
line and against the measured seed gap.

### Outcome, 2026-09-16 -- the gap is below the line; the three-arm design stands

`faultline model variance-probe` (`configs/train/variance_probe_v0.yaml`,
`reports/data/variance_probe_v0_20260916.md`). Both seeds ran 25,034,752 pretraining tokens
(382 steps at 4 x 8) and a 16,000-positive frozen probe. Both seeds took **0.38 GPU-hours
together**, against the brief's estimate of about 8.5 (ADR-0018 rulings). Per-step logs are in
`reports/data/variance_probe_v0_steps/`.

| test source | seed 1 AUPRC | seed 2 AUPRC | base rate | gap |
| --- | --- | --- | --- | --- |
| **hill_of_towie (held out)** | 0.0353 (lift 1.06) | 0.0433 (lift 1.30) | 0.0333 | **0.0080** |
| kelmarsh | 0.0679 | 0.0506 | 0.0365 | 0.0173 |
| penmanshiel | 0.0535 | 0.0624 | 0.0401 | 0.0088 |

**Verdict under the registered rule: 0.0080 < 0.010. A three-arm design at one seed stands.**
The rule reads the held-out site only, and it is applied as written.

Recorded beside the verdict, not as a re-decision:

- **The gap is 80% of the line, and it is one draw.** Two seeds give one absolute difference.
  If run-to-run AUPRC has standard deviation `s`, the expected gap is `1.13 s`, so this gap
  implies `s` near 0.007. A one-seed difference between two arms then has a standard deviation
  near `s x sqrt(2)`, about 0.010, the line itself. Under the three-arm design, an arm
  difference at the line would sit within one standard deviation of seed noise.
- On Kelmarsh, a training site, the gap between seeds is 0.0173, above the line.
- Both backbones are undertrained at half budget. Validation loss was still falling at the last
  step (seed 1: 4.2837 at step 315, 4.2128 at step 382). Both probes selected mid-run (steps 830
  and 664 of 1,000). Held-out lift is 1.06 and 1.30, the range M1e reached.
- The prior correction brings the uncorrected mean probability on Hill of Towie (0.47 and 0.53)
  to 0.022 and 0.027, near the training sites' 2.21%. Hill of Towie's own base rate is 3.33%.
  That gap is site shift, measured and not corrected (ADR-0019). ECE is 0.012 and 0.008.

No other run was started.

### Ruling, 2026-09-16 (E0-E5 ruling, E5) -- PASSED, and the pass is not load-bearing

**Verdict: PASSED. 0.0080 < 0.010.** The line was fixed in commit **`33c5ab4`** ("pre-register
the seed-variance line, 0.010 held-out AUPRC, before any probe run"). The probe code, the
configuration and both runs came after it (`f35ce4b`; the report's `git_sha` is `33c5ab4`). The
rule was applied as written, and the three-arm design at one seed stands under it. This entry
does not reopen that verdict.

**Why the pass carries no weight beyond that.** Three reasons, each enough by itself:

1. **A floor effect.** Both seeds sit at the floor of the metric. Their lift over chance, AUPRC
   minus Hill of Towie's base rate, is **0.0020 and 0.0100** (0.035297 and 0.043281 against
   399/12,000 = 0.03325; the ruling's 0.0023 and 0.0103 are the same subtraction against 0.033
   rounded). Seed 2 is **about 4.5 to 5 times** as far above chance as seed 1 (4.9 exact, 4.5
   against the rounded rate). When both scores are that close to chance, a small absolute gap
   says only that neither seed has much signal to differ in. It does not say that seeds agree.
   **The control is Kelmarsh,** a training site with signal (lift 1.39 to 1.86). There the same
   two seeds differ by **0.0173**, above the line. Where there is signal, the model has room to
   vary, and it does.
2. **The wrong scale.** 0.010 is **30% of the 0.033 base rate** (0.0100 / 0.03325 = 0.30). At the
   held-out site, a gap below the line can still be a large fraction of everything above chance:
   seed 1's whole lift is 0.0020. A line in absolute AUPRC, fixed without a lift or base-rate
   scale, cannot tell "seeds agree" from "both near zero".
3. **Conflated noise.** The gap mixes two noise sources and reports neither alone. It is seed
   variance (initialisation, data order, head, sampler) plus the sampling noise of the evaluation
   itself: 12,000 windows and 399 positive windows, clustered in time. **No within-seed interval
   was reported,** so it is not known how much of 0.0080, or of either AUPRC, a resample of the
   same windows would move. The within-seed bootstrap is pre-registered next, as ADR-0021, and applied to
   these two seeds there.

The E5 result licenses the three-arm design under its own rule and nothing more. It is not
evidence that one-seed arm differences at Hill of Towie are interpretable. Whether Hill of Towie
can be evaluated at all is ADR-0021's gate.

**The budget, reconciled.** Two throughput figures are on record for the same configuration, and
they measure different things:

| scope | tokens | seconds | tokens/s |
| --- | --- | --- | --- |
| **steady state**: throughput measurement, 4 x 8, random ids, optimiser steps only (ADR-0018 rulings) | -- | -- | **89,817** |
| pretraining stage, seed 1, with its 6 validation passes | 25,034,752 | 344.2 | 72,737 |
| pretraining stage, seed 2, with its 6 validation passes | 25,034,752 | 341.5 | 73,311 |
| **effective**: both seeds end to end, pretraining tokens over all wall clock | 50,069,504 | 1,356.0 | **36,925** |
| effective, as the ruling stated it: 50,000,000 nominal over 0.38 h | 50,000,000 | 1,368 | 36,550 |

Where the 1,356 seconds went (`reports/data/variance_probe_v0_20260916.json`):

| part | seconds | share |
| --- | --- | --- |
| optimiser steps at the steady-state rate (50,069,504 / 89,817) | 557.5 | 41% |
| pretraining validation passes and stage overhead (685.7 - 557.5) | 128.2 | 9% |
| probe stages, 16,000 positives each, validation included | 452.0 | 33% |
| test scoring (36,000 risk windows a seed), checkpoint I/O and set-up | 218.3 | 16% |

The steady-state rate is correct for what it measures. Less than half the wall clock is
pretraining steps, and a GPU-hour projection built on 89,817 alone under-reads a run by a
factor of about 2.4. A projection for a run that includes a probe and a test pass uses the
effective rate, or this breakdown. The full-budget `tel_only` gate check (ADR-0021) is projected
from the breakdown: 557.5 s of steps, 128 s of validation and overhead, 226 s of probe and about
109 s of test and I/O, so about **1,020 seconds, 0.28 GPU-hours**, before start-up.

---

## ADR-0021 The held-out-site gate: `tel_only` at full budget must put Hill of Towie's AUPRC interval above chance

**Status:** Accepted; **pre-registered 2026-09-16, before the run it governs, before its code and
before any number from it exists** · **Date:** 2026-09-16

**Context.** Hill of Towie is the leave-site-out evaluation that every M3 arm comparison reads
(ADR-0020). The seed-variance probe passed its line, and the pass is not load-bearing (ADR-0020,
E5 ruling). Both half-budget seeds sit within 0.0020 and 0.0100 AUPRC of chance, and no
within-seed interval exists. So it is not yet known whether Hill of Towie can distinguish **any**
model from chance at these budgets. If it cannot, a three-arm comparison on it cannot come out
informative whatever the arms do. That is checked first, on the cheapest arm, at the budget the
arms will actually run.

**The run.** `tel_only`, rung S2, **one seed (1)**, the full per-arm budget of **50,000,000
tokens** rounded up to a whole optimiser step (764 steps x 32 windows x 2,048 tokens =
50,069,504). Everything else is ADR-0020's probe held fixed: the `joint_v0` shards, 4 x 8, peak
rate 6e-4, 6 pretraining validation passes over 500 windows a source, and the frozen probe of
`configs/train/telemetry_v1.yaml` (balanced, 16,000 positives, prior-corrected per ADR-0019). The
configuration is `configs/train/gate_check_v0.yaml`, written after this record.

**The read-out.** Hill of Towie test AUPRC of the frozen probe on the same seeded evaluation
windows as ADR-0020: stride 1, 12,000 windows, seed 20260912, **399 positive windows, base rate
399 / 12,000 = 0.03325**.

**The within-seed interval, fixed here.**

- **Unit: 48-hour blocks, not windows.** Positive windows are clustered in time: an event makes
  every window whose 24-hour horizon reaches it positive. On these 12,000 windows the 399
  positives fall into **274 blocks** of 288 steps (48 hours, twice the label horizon) out of
  **5,983 occupied blocks**, measured from the labels alone, before any score. A block is the
  window's end step integer-divided by 288, within its shard. A window bootstrap would treat
  399 positives as 399 independent draws and understate the interval.
- **Procedure:** resample the occupied blocks with replacement, as many as there are; take
  every window of each drawn block, each time it is drawn; compute AUPRC. **10,000 replicates,
  bootstrap seed 20260916, 95% percentile interval.** A replicate with no positive window is
  discarded and counted.
- **The number the rule reads is the interval's lower bound, the 2.5th percentile.**

**The rule.** **EVALUABLE** if and only if the lower bound is **strictly above 0.03325**,
Hill of Towie's base rate on these windows. The ruling wrote 0.033. The measured rate is
0.03325, and the stricter reading is registered so that a lower bound between the two cannot
be argued either way. Otherwise the site is **NOT EVALUABLE**. If more than 1% of replicates are
discarded, the interval is not trusted, and the verdict is NOT EVALUABLE.

**The fallback, committed with the rule.**

- **EVALUABLE:** leave-site-out on Hill of Towie stays the primary evaluation. The three-arm
  design of ADR-0020 proceeds, and every arm's Hill of Towie AUPRC is reported with its
  within-seed interval beside the 0.010 line.
- **NOT EVALUABLE:** **leave-site-out is demoted to a reported negative result.** Every arm's
  Hill of Towie AUPRC and interval are still reported, labelled not evaluable under ADR-0021, and
  no arm claim rests on them. **The primary evaluation is promoted to either CARE (ADR-0010), or
  a temporal holdout at the training sites (the late test split at Kelmarsh and Penmanshiel).**
  The choice between those two is the user's. It is recorded and committed before either is
  scored for any arm, and it is not made by looking at either one's scores. If the temporal
  holdout is chosen, it carries ADR-0009's caveat: the late split includes a change in what is
  labelled, so it is not a pure drift test. The demotion is not reversed by a later, better
  result on Hill of Towie.

**Reported with the verdict, deciding nothing.** Hill of Towie's positive windows (399),
positive blocks (274) and occupied blocks; the AUPRC point estimate; a window-level bootstrap
interval, to show what the block unit changes; and an interval on lift over chance (AUPRC minus
each replicate's own base rate). The test logits are written to disk with the run, so no later
interval needs the GPU again.

**The half-budget result gets the same interval (§4.2's noise objection).** The same block
bootstrap, positive count included, is applied to **both ADR-0020 seeds at half budget**. Their
probe heads and test scores were not saved, only their backbones
(`checkpoints/variance_probe_v0_5d9ff5c0/`). The probe stage is therefore re-run on each saved
backbone, seeded exactly as before, and the bootstrap reads the re-run's scores. The re-run's
AUPRC is reported beside the recorded 0.0353 and 0.0433, and any difference is reported as the
probe stage's run-to-run nondeterminism, not hidden. These intervals are reported. They do not
decide this gate, and they do not reopen ADR-0020's verdict.

**What the interval does not cover.** One seed. It measures the evaluation's sampling noise at a
fixed model, not seed variance. An EVALUABLE verdict says that Hill of Towie can separate this
model from chance. It does not say that it can separate two arms.

**Erratum, 2026-09-16, with the code that reads this record (no run made).** "764 steps x 32
windows x 2,048 tokens = 50,069,504" above is an arithmetic slip: it doubled the half-budget
probe's 382 steps instead of rounding the full budget up. 50,000,000 tokens round up to **763
steps, 50,003,968 tokens**, and that is what `configs/train/gate_check_v0.yaml` runs
(`tests/evaluation/test_gate_check.py` pins it). The rule, the interval and the fallback are
unchanged. ADR-0020's projection of 557.5 seconds of steps becomes 556.7.

### Outcome, 2026-09-16 -- NOT EVALUABLE; leave-site-out is a reported negative, and the fallback is chosen under ADR-0022

**Verdict: NOT EVALUABLE.** The rule was registered in commit **`ce9c8ad`**, before the
configuration, the code (`e7ab586`) and the run existed. `faultline model gate-check`
(`configs/train/gate_check_v0.yaml`, hash 9697a266; `reports/data/gate_check_v0_20260916.md`,
git_sha `e7ab586`) put the block-bootstrap lower bound on Hill of Towie test AUPRC at **0.0306**,
not above the base rate **0.03325**. No replicate was discarded (0 of 10,000). As registered,
**leave-site-out on Hill of Towie is demoted to a reported negative result**: every arm's Hill of
Towie AUPRC and interval are still reported, labelled not evaluable under ADR-0021, and no arm
claim rests on them. The demotion is not reversed by a later, better Hill of Towie result.

**All three runs, one table.** Every row reads the same 12,000 seeded Hill of Towie test windows
(stride 1, seed 20260912): **399 positive windows, base rate 0.03325, 274 of 5,983 occupied
48-hour blocks holding a positive**. Intervals are 10,000 block-bootstrap replicates, seed
20260916, 95% percentile. The two half-budget rows come from `faultline model probe-intervals`
(`reports/data/variance_probe_v0_intervals_20260916.md`): the frozen probe was re-run on each
saved ADR-0020 backbone, and both re-runs reproduced the recorded AUPRC to four decimals.

| run | pretraining tokens | AUPRC | block 95% interval | width | lower bound above 0.03325 |
| --- | --- | --- | --- | --- | --- |
| half budget, seed 1 (ADR-0020) | 25,034,752 | 0.0353 | [0.0299, 0.0422] | 0.0123 | no |
| half budget, seed 2 (ADR-0020) | 25,034,752 | 0.0433 | [0.0356, 0.0554] | 0.0198 | yes |
| **full budget, seed 1 (this gate)** | **50,003,968** | **0.0393** | **[0.0306, 0.0553]** | 0.0247 | **no** |

Only the last row is the registered run. The half-budget rows are reported under the rule, and
the rule does not apply to them.

**Robust to the resampling unit.** Resampling windows instead of blocks treats the 399 clustered
positives as independent and narrows the interval to [0.0328, 0.0509]. Its lower bound, **0.0328**,
is still below the base rate. The verdict does not depend on the choice of unit.

**The site is marginal, not null.** Seed 2 at half budget would have cleared the rule (lower
bound 0.0356), and the registered full-budget run did not. Two of three runs sit below the line,
one sits above it, and all three point estimates are above chance (lift 1.06 to 1.30). Hill of
Towie carries a small signal that this evaluation cannot resolve from chance at one seed. It does
not show that the site carries no signal.

**The noise finding.** Each half-budget seed's own interval, **0.0123 and 0.0198 wide**, is wider
than the **0.0080** gap between the two seeds that ADR-0020 read. That gap is inside the
evaluation's own sampling noise at a fixed model. E5's comparison could not have told a seed
effect from a resample of the same 12,000 windows, which confirms the third reason in ADR-0020's
ruling (conflated noise) with a measurement.

**Recorded beside the verdict, deciding nothing.** Doubling pretraining lowered selected
validation loss from 4.21 (half budget, seed 1, step 382) to **3.3172** (step 763). Hill of Towie
AUPRC did not move outside either interval, and neither did Kelmarsh (0.0518) or Penmanshiel
(0.0504). The probe selected its **first** validation measurement, step 166 of 1,000. Its
prior-corrected mean prediction on Hill of Towie is **0.0138**, below the training natural rate
of 0.0221 that the correction targets. Both facts are carried into the next brief (F1, F2).

**The fallback is not chosen here.** The choice between CARE (ADR-0010) and a temporal holdout at
the training sites is deferred to **ADR-0022**, under a selection rule registered there before
either candidate is scored for any seed.[^0021-lift]

[^0021-lift]: The window-resampling interval on lift over chance is [+0.0004, +0.0172]. Its lower
bound is above zero. That row is not the registered unit and decides nothing. The block
interval on lift, the registered unit, is [-0.0012, +0.0211].

---

## ADR-0022 The primary evaluation axis after ADR-0021: the selection rule, the CARE facts and scoring protocol, and the temporal split named in-distribution

**Status:** Accepted; **registered 2026-09-17, before either candidate axis is scored for any seed**
· **Date:** 2026-09-17 · Number reserved 2026-09-16. Amends ADR-0010 in one respect (§3).
**Commit:** this record, `configs/eval/axis_gate_v0.yaml`, its test and the CARE card's channel
mapping were committed in **`801ab71`**, before either axis was scored for any seed. The hash is
recorded here by the commit after it. F5 may start only on the user's authorisation.

**Sources of every number.** Counts, rates and `<nan>` shares come from the F4 measurement of
2026-09-17: the window index and token stream of `data/shards/telemetry/quantile_bins_v2_9cd52b65/`
(`splits_v3.yaml`, label `narrow_within_24h`), read with no model loaded. Model results come from
`reports/data/seed_replication_v0_20260917.md` **as it existed when this record was written: the
first F3 run's report** (configuration hash 424c4f33, generated 2026-09-17T12:57:37Z, git_sha
`7497aaa`). The `b2ad4a7` resume run's report will supersede it **for the three F3 additions only**
(validation-split calibration, the selection-split interval, final-step checkpoints). It does not
supersede any number used here.

### 0. What is known before the axis is chosen

1. **Pretraining moves the frozen §a probe by +0.009 to +0.019 AUPRC over random init on three
   seeds.** All nine paired lower bounds are above zero, and the lowest is +0.0045 (ADR-0024 F3; the
   report, §1).
2. **The probe is at parity with a bag-of-tokens classifier on all three seeds.** Δ probe − bag is
   +0.0016, +0.0053 and −0.0015, and every interval spans zero (the report, §2; ADR-0024 G2).
3. **Therefore H1's claim is that the text pathway carries signal the telemetry tokens do not, not
   that the sequence model's representation helps.** H2 is unaffected (H1 and H2 as in
   `docs/ROADMAP.md`).

The seed spread on the pooled split, 0.0508 to 0.0576 (0.0068), is the size of one seed's interval
half-width: seed 1 reads [0.0474, 0.0618], half-width 0.0072. Every arm comparison is therefore
paired and three-seeded. At best it can resolve differences of order 0.005.

### 1. The two CARE facts, measured

**Fact 1: the positives and the rate.** At the project horizon H (144 steps, `narrow_within_24h`),
compared with the figures recorded before this measurement:

| quantity | previously recorded | measured 2026-09-17 |
| --- | --- | --- |
| labelled events | 45 | **45**: 12 / 6 / 27 at farms A / B / C, each a run of exactly 144 consecutive positive windows |
| known windows | — | **5,166,066** (of 5,179,569 index rows) |
| positive windows | 6,480, 144 per event | **6,480**, 144 per event |
| positive rate | 0.125% | **0.1254%** (0.001254) |
| two-day blocks (end step // 288, within the shard) | — | **18,196** |
| blocks holding a positive | — | **72** |

Every recorded figure agrees with the measurement. ADR-0010's "0.123% at 24 h" was a per-step rate
from the M1a label report, a different denominator, and it is not this rate. The 45 events are
also the 45 anomalous datasets of ADR-0010.

**Fact 2: the channel set.** There are 14 canonical channels, 12 of them core. Every stream carries
the 12 core channels as 13 tokens a step. **An unmapped core channel is emitted as `<nan>` on every
step, never masked** (`data/cards/care.md`, "Channel mapping in the token stream"):

| farm | canonical channels mapped (of 14) | core channels in the stream (of 12) | absent from the stream, as `<nan>` | `<nan>` share |
| --- | --- | --- | --- | --- |
| A | 13 | 11 | `main_bearing_temp_c` | 8.35% |
| B | 10 | 9 | `nacelle_temp_c`, `generator_bearing_temp_c`, `generator_winding_temp_c` | 25.01% |
| C | 9 | 9 | `nacelle_position_deg`, `nacelle_temp_c`, `generator_bearing_temp_c` | 25.22% |

All of CARE reads 21.34%. The training sites read 0.15% (Kelmarsh) and 0.36% (Penmanshiel) on their
test splits, and 4.45% and 6.41% on their pretraining windows.

**CARE is scored on a reduced channel set, and the cross-OEM claim is made on that set.** The absent
channels are emitted as `<nan>`. The brief anticipated that the backbone saw few or no `<nan>`
tokens in pretraining. The measurement corrects that. `<nan>` is common in pretraining, but **not
one of 749,847 pretraining windows** (both training sites, index at stride 6) has any CARE farm's
set of fully-`<nan>` channels. The 12,816 windows (1.71%) in which those channels are all `<nan>`
lose other channels with them, in whole-turbine gaps. A channel permanently absent while its
neighbours report is outside everything the backbone was pretrained on, at every CARE farm. **The
evaluation cannot remove this confound.** It is stated beside every CARE result, with the farm's
`<nan>` share.

### 2. The training-site temporal test split, named

**The pooled Kelmarsh + Penmanshiel test split, 2022–2024, cut at 2021-12-31T23:59:59Z; the same
windows as the F3 stride-12 set. It is the in-distribution temporal test set, not a shift axis. It
can carry H2 (degradation under modality dropout, in-distribution); it cannot support a shift
claim.**

The cut is `time.val_until` in `configs/data/splits_v3.yaml`, the split specification the shards in
force were built with. Train is 2016–2020 (`train_until` 2020-12-31T23:59:59Z) at both sites, and
validation is 2021. Test is 2022–2024 at Kelmarsh and 2022 only at Penmanshiel, whose test shard holds
no later year.

ADR-0009's caveat, verbatim (evidence note of 2026-09-11):

> **The late split is a temporal hold-out with a change in what is labelled, not a drift
> test.**

> **Standing requirement: every late-test result is reported both with and without the
> anemometer-defect events.**

**Every result reported on this split carries that caveat**, and every result is given both with
and without those events.

**Base rate at stride 12:** 5,312 of 137,025 windows, **0.0388**, confirmed from the shards
(0.03877). That matches the F2 record. Without the anemometer-defect events, it is 3,331 of 137,015
windows, 0.0243. There are 5,799 blocks, and 497 of them hold a positive.

### 3. The CARE scoring protocol

- **Uniform stride-12 thinning over the whole CARE evaluation set.** Every 12th known window of the
  `care__test` index at offset 0, as `load_windows(..., stride=12)` takes it. It is deterministic
  and identical for every model scored: the F3 protocol (ADR-0024 §4).
- **The scored set:** **430,506 windows, 540 positive** (12 per event; all 45 events represented),
  **for 45 events**. By farm: A 96,694 (144), B 70,803 (72), C 263,009 (324).
- **Block coverage, measured, and it is not complete.** The brief described the protocol as covering
  every block. F3's thinning does not. It covers **18,193 of 18,196 blocks** and **67 of 72
  positive blocks**. The three missed blocks hold 1 to 3 known windows each. The
  five missed positive blocks hold 1 to 8 positive windows at the edge of an event whose other
  windows are scored. The same thinning at the training sites covers 5,799 of 5,800 blocks and 497
  of 506 positive blocks (ADR-0024 §4). The protocol stays F3's as written, because changing it
  would make the two axes' scored sets differ in construction. One CARE block spans two datasets,
  because datasets are concatenated in the shard.
- **The base rate the rule reads is the scored set's own positive rate.** Under uniform thinning it
  equals the true rate. **Scored set: 540 / 430,506 = 0.0013. Full set: 6,480 / 5,166,066 = 0.0013.
  They agree to the fourth decimal (0.001254 both).**
- **The independent unit is the event.** The 45-event count is stated beside every CARE window
  count. Event-level metrics, if ever reported, have n = 45.
- **Interval:** ADR-0021's block bootstrap over two-day blocks (288 steps within the shard), 10,000
  replicates, seed 20260916, 95% percentile, max discarded share 0.01, as in
  `configs/train/gate_check_v0.yaml`.
- **Positive enrichment is rejected.** An evaluation set with all positives and sampled negatives
  changes the chance level, and its AUPRC cannot be compared with the true base rate.

**The amendment to ADR-0010.** ADR-0010 reports no per-step base rate for CARE beside the other
sites. That stands for reporting. Here, CARE's own scored-set rate is used only as the chance level
of its own rule, and it is never printed as a rate comparable with another site's. CARE is still
never pooled with another source (`configs/eval/README.md`, rule 2).

The values are in `configs/eval/axis_gate_v0.yaml`, written with this record.
`tests/evaluation/test_axis_gate.py` pins them to ADR-0021's interval and F3's stride, and it
re-counts them from the window index when the shards are present.

### 4. The selection rule

> A candidate axis is evaluable if the ADR-0021 rule — block-
> bootstrap 95% lower bound on tel_only test AUPRC strictly above
> that axis's OWN test-split base rate, never the training rate —
> holds on at least two of the three full-budget tel_only seeds,
> each scored at the checkpoint ADR-0024 selected for it. Both
> candidates are scored and both are reported in full regardless of
> outcome. If both are evaluable: H1 is evaluated on CARE, H2 on the
> training-site temporal test split, because CARE carries no status
> strings and cannot exercise the text pathway. If only the temporal
> split is evaluable, it carries both hypotheses and CARE is
> reported as a second negative beside Hill of Towie. If only CARE
> is evaluable, H1 is evaluated there and H2 is reported as
> untestable on an evaluable shift axis. If neither, stop and
> report.

The base rates the rule reads: **temporal split 0.0388** (137,025 windows); **CARE 0.0013**
(430,506 windows, 45 events).

### 5. Checkpoint and selection

F5 scores the **ADR-0024-selected checkpoint** of each seed, which is the rule in force. The
**final-step checkpoint** of each seed is scored beside it on both axes and reported. It does not
gate.

Whether the arm runs use selected-step or fixed-final-step selection is decided in a **dated
addendum to this record**, after the `b2ad4a7` F3 report exists, on a criterion registered now:
**if the final-step read agrees with the selected read within the paired interval on all three
seeds on the pooled split, arm runs use fixed-final-step selection. Otherwise the ADR-0024 rule
stays.** The addendum is written before any arm is pretrained.

### 6. Hill of Towie, retro-application

From the F3 report, on Hill of Towie's 12,000-window subsample with base rate 0.03325:

| seed | AUPRC | 95% block interval | lower bound above 0.03325 |
| --- | --- | --- | --- |
| 1 | 0.0390 | [0.0304, 0.0548] | no |
| 2 | 0.0510 | [0.0371, 0.0741] | yes |
| 3 | 0.0359 | [0.0276, 0.0508] | no |

The site clears on one seed of three. **Under rule §4 it is NOT EVALUABLE**, the same verdict
ADR-0021 reached on one seed. The demotion stands and is not reopened. The site is marginal, not
null. This paragraph exists so that ADR-0021 and ADR-0022 agree on what "evaluable" means.

### 7. What F5 is

F5 scores `tel_only` seeds 1–3, at the selected and final-step checkpoints, on both axes at stride
12, and reports:

- one table of axis × seed: AUPRC, interval, base rate, and whether the interval clears it;
- the verdict for each axis;
- the hypothesis assignment;
- the outcome section of this record.

Nothing is pretrained. F5 is not authorised by this record.

**Rejected.**

| alternative | why rejected |
| --- | --- |
| Positive-enriched CARE set (all 6,480 positives, sampled negatives) | Changes the chance level; its AUPRC cannot be compared with the true base rate (§3). |
| The training natural rate as the chance level on either axis | ADR-0021's rule reads the scored windows' own rate; a training rate is not what a no-signal scorer reaches on another set. |
| A per-block offset thinning that covers every block | Not the F3 protocol; the two axes' scored sets would differ in construction. The coverage it would add is 3 blocks and 5 positive blocks (§3). |
| The temporal split as a shift axis | Same sites, same instruments, a change in what is labelled (ADR-0009): in-distribution, not shift. |
| One seed deciding an axis | Seed spread equals one seed's interval half-width (§0); ADR-0021's one-seed verdict on Hill of Towie flips on seed 2. |

**What would change this decision.** A CARE release publishing the absent channels, or a
re-tokenization that masks absent channels instead of emitting `<nan>`. Either would remove the §1
confound and need a new version of the axis-gate configuration. A measurement showing that the F3
thinning misses an event would also change it: today every one of the 45 events is scored.

### Addendum, registered 2026-09-18 before any bootstrap of it is run -- arm-run checkpoint selection

**What §5 says, verbatim.**

> Whether the arm runs use selected-step or fixed-final-step selection is decided in a **dated
> addendum to this record**, after the `b2ad4a7` F3 report exists, on a criterion registered now:
> **if the final-step read agrees with the selected read within the paired interval on all three
> seeds on the pooled split, arm runs use fixed-final-step selection. Otherwise the ADR-0024 rule
> stays.** The addendum is written before any arm is pretrained.

**Why it is clarified.** Read literally, "agreement within the paired interval" is a two-sided
test, and it fails in the direction that argues *for* the change. A final step significantly
**better** than the selected one would not agree, so the criterion would retain the worse rule.
That is not the question §5 was written to ask. The question is whether fixed-final-step selection
**costs** anything: whether selecting on a 6,000-window validation split buys any test AUPRC over
simply taking the last step. Only a final step significantly **worse** than the selected one is
evidence against the change. The criterion below is the one-sided reading, and it adds the
condition that the pretraining effect itself must survive the switch.

**What was seen before this registration, stated plainly.** The point estimates in the F3 report
§5 were read before this text was written: the final step is at or above the selected step on
**every one of the six probes**, and on the trained seeds the gaps are **+0.0040** (seed 1,
0.0540 to 0.0580) and **+0.0007** (seed 3, 0.0508 to 0.0515), with seed 2 identical because it
selected the last step. Those are unpaired point differences read off two independent intervals.
**The paired intervals on Δ registered below did not exist when this was written, and neither did
the nine-cell final-versus-final table.** Nothing here is computed from them.

**The criterion, registered.**

> Fixed-final-step selection is adopted for the arm runs unless, on any trained seed, the paired
> 95% block-bootstrap interval of Δ = AUPRC(final) − AUPRC(selected) on the pooled stride-12 split
> lies entirely below zero; and only if the ADR-0024 F3 criterion, recomputed with final-step
> checkpoints on BOTH sides (trained final vs each random-init final), passes nine of nine.
> Otherwise the ADR-0024 selected-checkpoint rule stays for the arm runs. Whichever rule is
> adopted is the rule F5 scores under, and every probe in every arm from then on.

**How it is read, fixed here.** Δ is the paired block bootstrap of ADR-0024 §2 with the final-step
scores as the reference and the selected-step scores as the other: two-day blocks (288 steps within
each shard) drawn once per replicate, both reads taken on the identical resampled rows, **10,000
replicates, bootstrap seed 20260916, 95% percentile**, the discard rule at 1%. The windows are the
pooled Kelmarsh + Penmanshiel stride-12 split of ADR-0024 §4 (137,025 windows, 5,312 positive).
**Trained seed 2 selected step 1,000**, so its final checkpoint *is* its selected checkpoint and
Δ ≡ 0 identically; it is stated, not bootstrapped, and it cannot fail the condition. The nine-cell
recomputation is ADR-0024's criterion unchanged in every other respect, with each trained seed's
final-step scores against each random-init seed's final-step scores. Every score read is already
on disk under `checkpoints/seed_replication_v0_424c4f33/`. **Nothing is retrained and nothing is
re-scored on a GPU.**

**The evidence that motivates the change** (report §4 and §7 of the F3 outcome, all seen before
this registration, none of it the criterion):

| seed | selected step | selection AUPRC | 95% block interval | the untrained head's 0.0447 inside it |
| --- | --- | --- | --- | --- |
| 1 | 200 | 0.0471 | [0.0289, 0.0902] | yes |
| 2 | 1,000 | 0.0382 | [0.0255, 0.0607] | yes |
| 3 | 700 | 0.0382 | [0.0243, 0.0708] | yes |

The selection split holds 6,000 windows, 117 positive, in 2,789 occupied 48-hour blocks of which
78 hold a positive. Every interval is about as wide as the quantity being ranked, and **the step-0
untrained head's 0.0447 lies inside all three**. Validation-AUPRC selection on this split cannot
distinguish the checkpoints it is choosing between; it is selection on noise, and it costs a saved
checkpoint per measurement and a re-run whenever a final state is wanted. Fixed-final-step
selection removes a free parameter from every arm run. That is the case for the change. Whether it
is paid for in test AUPRC is what the criterion above measures.

**What this addendum does not change.** ADR-0022 §4's axis rule, the CARE scoring protocol, the
base rates, the interval and the stride all stand. §5's first paragraph stands for F5's reporting:
whichever checkpoint gates, the other is scored beside it on both axes and reported. F5 is not
authorised by this addendum.

### Outcome of the addendum, 2026-09-18 -- fixed-final-step selection is adopted; the final step is better, not merely equal

`faultline model checkpoint-selection` (`configs/train/seed_replication_v0.yaml`, hash `424c4f33`;
`reports/data/checkpoint_selection_v0_20260917.md` and `.json`, git_sha `4622564`, the registration
commit) read F3's saved stride-12 scores under
`checkpoints/seed_replication_v0_424c4f33/` and ran the five paired block bootstraps on the CPU in
**24.6 minutes**. **No model was loaded, nothing was pretrained, nothing was re-scored, and no GPU
was used.** Each bootstrap writes its intervals to a JSON beside the scores as it completes, so a
crash costs the one in flight; the report names how many of the five an invocation computed and how
many it resumed.

**1. Δ = AUPRC(final) − AUPRC(selected), paired, on the pooled stride-12 split** (137,025 windows,
5,312 positive, 497 of 5,799 blocks holding a positive; 10,000 replicates, seed 20260916, none
discarded):

| trained seed | selected | final | Δ final − selected, 95% paired interval | entirely below zero |
| --- | --- | --- | --- | --- |
| 1 | step 200 | step 1,000 | **+0.0041 [+0.0022, +0.0066]** | no |
| 2 | step 1,000 | step 1,000 | **0 exactly** -- one checkpoint, not bootstrapped | no |
| 3 | step 700 | step 1,000 | **+0.0007 [+0.0002, +0.0011]** | no |

**Both intervals lie entirely ABOVE zero.** The final step is not merely as good as the selected
step; on both seeds where the two differ it is **significantly better**, paired. This is the case
the clarification above was registered for: read as a two-sided test of "agreement", §5 would have
failed on both seeds and retained the rule that selects the **worse** checkpoint. Seed 1's paired
point estimate is +0.0041 against the +0.0040 the report §5 point estimates give; the difference is
rounding in the two 4-decimal figures, and the paired computation takes the exact difference.

**2. ADR-0024's criterion, recomputed with final-step checkpoints on BOTH sides** (trained final
against each random-init final; every other term of the criterion unchanged). Random-init final
steps are all step 1,000; seeds 2 and 3 had selected steps 300 and 225, so for them this is a
different checkpoint from the F3 row:

| trained seed (final) | Δ vs random 1 (final) | Δ vs random 2 (final) | Δ vs random 3 (final) | verdict |
| --- | --- | --- | --- | --- |
| 1 | +0.0164 [+0.0114, +0.0230] | +0.0161 [+0.0111, +0.0226] | +0.0163 [+0.0113, +0.0226] | **PASS** |
| 2 | +0.0160 [+0.0115, +0.0225] | +0.0157 [+0.0109, +0.0224] | +0.0159 [+0.0113, +0.0220] | **PASS** |
| 3 | +0.0099 [+0.0050, +0.0155] | +0.0096 [+0.0049, +0.0150] | +0.0098 [+0.0047, +0.0152] | **PASS** |

**Nine of nine.** Every paired lower bound is above zero and the lowest is **+0.0047** (seed 3
against random 3), against **+0.0045** for the selected-checkpoint reading in the F3 outcome. The
pretraining effect measured final-against-final is **+0.0096 to +0.0164**, against +0.0092 to
+0.0186 selected-against-selected. **The effect survives the switch and is, if anything, slightly
better resolved: no cell is weaker, and the three cells within a seed now agree closely with one
another** (seed 1 spans 0.0003 across its three random-init seeds, where the selected reading spans
0.0025). Removing a noisy per-probe selection removes a per-probe nuisance term from the
comparison, which is what the arm runs need.

**3. Verdict under the registered criterion: FIXED-FINAL-STEP SELECTION IS ADOPTED.** Neither
condition to retain the ADR-0024 rule is met: no trained seed's Δ interval lies entirely below
zero, and the nine-cell recomputation passes nine of nine.

**The rule in force for the arm runs and for F5: `final_step`.** Every probe in every arm, from
this record onward, is read at its last probe step. No validation-split checkpoint selection is
performed, and none of the machinery for it -- the G3 cadence measurements, the saved selected
head, the seeded re-run that recovers a final state -- is needed to decide which checkpoint scores.
The G3 cadence stays in force as **reporting**: the validation curve is still measured and still
reported, and it no longer chooses anything. The **selected-step** checkpoint is now the one scored
beside the gating checkpoint on both axes and reported, not gating; §5's two roles are exchanged
and nothing else in §5 changes.

`configs/eval/axis_gate_v0.yaml` states the rule by value (`checkpoints.gating: "final_step"`,
`reported: ["selected"]`) with this addendum's registration hash in its comment.
`tests/evaluation/test_axis_gate.py` parses the rule out of the sentence above and fails if the
shipped configuration disagrees with it, so the record and the file F5 reads cannot drift apart.

**What this does not decide.** ADR-0022 §4's axis rule, the two axes' base rates, the interval, the
stride and the CARE protocol are untouched. ADR-0024's F3 verdicts stand as recorded on the
selected checkpoints; they are not restated on final checkpoints, and §2 above is a recomputation
registered for this decision, not a re-judging of F3. **F5 is not authorised by this addendum.**


### Outcome, 2026-09-18 -- CARE is NOT EVALUABLE at chance on all three seeds; the in-distribution temporal split is EVALUABLE on all three and carries both hypotheses

`faultline model axis-gate` (`configs/eval/axis_gate_v0.yaml`, hash `4dce1a1c`;
`reports/data/axis_gate_v0_20260918.md` and `.json`) scored **the whole CARE evaluation set for the
first time in this project**: the five distinct probe checkpoints of `tel_only` seeds 1-3, at the
registered stride-12 thinning, **1.72 hours of GPU over five scorings** at 20.7 minutes each.
Nothing was pretrained and no probe was trained. The training-site temporal split and Hill of Towie
were **read, not re-scored**: F3's saved logits are the same checkpoints on the same windows.

**Five scorings, not six.** Trained seed 2 selected step 1,000, its last, so its final-step
checkpoint **is** its selected checkpoint. It is scored once and reported under both role names;
its two rows are bit-identical because they are one set of weights, not two.

**The counts were re-asserted from the window index before a single window was scored**, and every
ADR-0022 Part B number holds exactly: **430,506 windows, 540 positive, rate 0.001254, 18,193 of
18,196 blocks and 67 of 72 positive blocks**, over **45 events** (12 / 6 / 27 at farms A / B / C,
all 45 represented at this stride). Per farm: A 96,694 windows (144 positive), B 70,803 (72),
C 263,009 (324).

**1. The axis x seed x checkpoint table.** The gating checkpoint is `final_step`; the selected
checkpoint is scored beside it and reported. Every base rate is the scored set's own, never the
training rate. 10,000 replicates, two-day blocks, seed 20260916, **no replicate discarded on either
axis's deciding rows** (the highest share anywhere is 0.11%, on farm B's reported rows).

| axis | seed | checkpoint | AUPRC, 95% block interval | own base rate | lower bound strictly above |
| --- | --- | --- | --- | --- | --- |
| CARE | 1 | final_step (step 1,000, **gates**) | 0.0013 [0.0009, 0.0019] | 0.001254 | **no** |
| CARE | 1 | selected (step 200, reported) | 0.0015 [0.0010, 0.0021] | 0.001254 | no |
| CARE | 2 | final_step (step 1,000, **gates**) | 0.0012 [0.0009, 0.0016] | 0.001254 | **no** |
| CARE | 2 | selected (step 1,000, reported) | 0.0012 [0.0009, 0.0016] | 0.001254 | no |
| CARE | 3 | final_step (step 1,000, **gates**) | 0.0012 [0.0008, 0.0017] | 0.001254 | **no** |
| CARE | 3 | selected (step 700, reported) | 0.0012 [0.0009, 0.0018] | 0.001254 | no |
| temporal | 1 | final_step (step 1,000, **gates**) | 0.0580 [0.0505, 0.0672] | 0.0388 | **yes** |
| temporal | 1 | selected (step 200, reported) | 0.0540 [0.0474, 0.0618] | 0.0388 | yes |
| temporal | 2 | final_step (step 1,000, **gates**) | 0.0576 [0.0503, 0.0670] | 0.0388 | **yes** |
| temporal | 2 | selected (step 1,000, reported) | 0.0576 [0.0503, 0.0670] | 0.0388 | yes |
| temporal | 3 | final_step (step 1,000, **gates**) | 0.0515 [0.0453, 0.0586] | 0.0388 | **yes** |
| temporal | 3 | selected (step 700, reported) | 0.0508 [0.0447, 0.0580] | 0.0388 | yes |

**Every temporal row carries ADR-0009's caveat verbatim and the sentence naming the split
in-distribution**, in the report and in the JSON, per row and not once per table.

**CARE is at chance, not merely wide.** The point estimate is 0.0012 to 0.0015 against a base rate
of 0.001254, and every interval **contains** the base rate rather than sitting above or below it.
This is not a case of an interval too wide to resolve a real effect: the probe orders 430,506 CARE
windows no better than a scorer with no signal. The same holds farm by farm (§2 of the report):
A 0.0013-0.0018 against 0.001489, B 0.0008-0.0009 against 0.001017, C 0.0011-0.0016 against
0.001232, every interval spanning its farm's own rate.

**The confound stands beside every CARE row, and it is stated, not resolved: 0 of 749,847
pretraining windows carry any CARE farm's missing-channel pattern.** Farm A is missing
`main_bearing_temp_c` (8.35% `<nan>`), farm B `nacelle_temp_c`, `generator_bearing_temp_c` and
`generator_winding_temp_c` (25.01%), farm C `nacelle_position_deg`, `nacelle_temp_c` and
`generator_bearing_temp_c` (25.22%); all of CARE reads 21.34% against 0.15% (Kelmarsh) and 0.36%
(Penmanshiel) on the temporal split. F5 re-measured these from the token stream and reproduces the
F4 figures exactly on their basis, which counts each covered step once. **This null therefore
cannot be attributed**: a channel permanently absent while its neighbours report is outside
everything the backbone was pretrained on, so "the representation does not transfer across OEMs"
and "the stream is outside the pretraining distribution" predict the same measurement here, and
this evaluation cannot separate them. ADR-0022 §1 anticipated exactly this and it is why the
confound is reported on every row.

**2. The verdicts under §4, on the final-step checkpoint.**

| axis | seeds clearing | verdict |
| --- | --- | --- |
| CARE | **0 of 3** | **NOT EVALUABLE** |
| temporal test split at the training sites (in-distribution) | **3 of 3** | **EVALUABLE** |

**The selected checkpoint's rows produce the same verdict on both axes**, so which checkpoint gates
does not change the outcome of this gate. Hill of Towie, read from F3 and reported for comparison,
reproduces ADR-0022 §6 exactly (0.0390, 0.0510, 0.0359; clears on seed 2 alone): **NOT EVALUABLE**,
and the demotion is not reopened.

**3. The assignment §4 produces.** Only the temporal split is evaluable, so **it carries both
hypotheses, and CARE is reported as a second negative beside Hill of Towie.**

**What that costs, stated plainly.** Both of the project's shift axes are now measured and neither
is evaluable: leave-site-out (ADR-0021, Hill of Towie) and cross-OEM dataset transfer (CARE, here).
**The project has no evaluable shift axis.** H2 is written as graceful degradation under modality
shift; on the axis that carries it, modality dropout is applied **in-distribution**, at the same two
sites and the same instruments the backbone was pretrained on. Every H2 result from here is a
statement about in-distribution modality dropout and may not be reported as a shift result. §4
foresaw the branch where CARE alone is evaluable and H2 is "untestable on an evaluable shift axis";
the branch that actually obtained leaves H2 testable, but not on shift.

**The anemometer-defect variant, and where it comes from.** `Anemometer defect` is a **Senvion
status string** in the `equipment_fault` category of `configs/data/events_v2.yaml`, for sources
`kelmarsh` and `penmanshiel` only, named by `configs/data/splits_v3.yaml`'s
`report_without_messages` under ADR-0009's standing requirement. **It is not a CARE label
category.** CARE's labels come from `event_info` with the single fault label `anomaly`, and on
`care__test` the two label columns are identical: the variant removes **0 of the 45 CARE events, 0
of its 430,506 windows and 0 of its 540 positives, and touches no farm**. It is a temporal-axis
variant only, which is where the configuration puts it. Reported beside the full-set rows, on the
same scored windows relabelled (3,330 of 137,016 windows, base rate 0.0243), the temporal split
reads **0.0492 / 0.0483 / 0.0383** at the gating checkpoint on seeds 1 / 2 / 3, against 0.0580 /
0.0576 / 0.0515 with the events. **The verdict above is computed on the full label set**, as §4
requires; the variant is reported and decides nothing. The variant's counts differ from §2's 3,331
of 137,015 by one window and one positive, because §2 strides the variant label's own admissible
set while F5 must relabel the windows its logits were already computed on.

**4. What F6 is now authorised to test, and on which axis.** The remaining arms are gated on the
**training-site temporal test split at stride 12** (137,025 windows, 5,312 positive, base rate
0.0388), at the **final-step checkpoint**, on **three pretraining seeds**, paired against `tel_only`
on the identical windows and reported with and without the anemometer-defect events. **CARE is not
an axis F6 may read a positive result on**; it is reported as a negative. On that axis F6 may test:

- **H1** -- that the joint model beats both single-modality baselines. ADR-0022 §0 already narrowed
  this: the §a probe is at parity with a bag-of-tokens classifier on all three seeds, so H1's
  claim is that the **text pathway carries signal the telemetry tokens do not**, not that the
  sequence model's representation helps. The temporal split can carry that comparison because it is
  the only axis that separates `tel_only` from chance.
- **H2** -- graceful degradation under modality dropout, **in-distribution**, with the limitation
  above attached to every result.

**Two things F6 must settle before it runs, and this record does not settle them.** First,
`configs/train/joint_v0.yaml` carries three arms -- `joint`, `joint_status_raw` (ablation) and
`tel_only` (control) -- and **no `txt_only` arm**. A text-only baseline is required by H1 as stated
and does not exist in the mixture in force, so F6 needs a new mixture-configuration version rather
than an edit (`configs/README.md` rule 3). Second, the resolvable difference on this axis is about
0.005 AUPRC (ADR-0022 §0), and each seed's interval is about 0.008 wide, so F6's comparisons must
be paired and three-seeded to say anything at all. **F6 is not authorised by this record.**

### Addendum (F6-0), registered 2026-09-18 before its code or run -- attribution of the CARE null

**Commit:** this addendum, `configs/eval/care_attribution_v0.yaml` and its test were committed
together in **`ad1b7a3`**, before any code that scores either diagnostic existed and before either was
run. The hash is recorded here by the commit after it. F6-0a and F6-0b may run only on the user's
authorisation.

**1. The two readings, and what the per-farm rows already say.** The F5 outcome above found CARE at
chance on every seed, every farm and both checkpoints. Two readings predict that measurement
equally:

- **(i) failure to transfer**: the probe on the pretrained backbone does not transfer across OEMs;
- **(ii) out-of-distribution stream**: the CARE missing-channel pattern lies outside the
  pretraining distribution, and **0 of 749,847 pretraining windows carry any CARE farm's
  pattern** (`data/cards/care.md`, F4 of 2026-09-17).

The per-farm table of the F5 report (`reports/data/axis_gate_v0_20260918.md` §2) narrows the
question but does not decide it. The AUPRC range is taken over its six rows per farm (three seeds x
the final-step and selected checkpoints):

| farm | `<nan>` share | core channels absent, emitted as `<nan>` | windows | positives (events) | own base rate | AUPRC, six rows |
| --- | --- | --- | --- | --- | --- | --- |
| farm A | 8.35% | `main_bearing_temp_c` | 96,694 | 144 (12) | 0.001489 | 0.0013-0.0018 |
| farm B | 25.01% | `nacelle_temp_c`, `generator_bearing_temp_c`, `generator_winding_temp_c` | 70,803 | 72 (6) | 0.001017 | 0.0008-0.0009 |
| farm C | 25.22% | `nacelle_position_deg`, `nacelle_temp_c`, `generator_bearing_temp_c` | 263,009 | 324 (27) | 0.001232 | 0.0011-0.0016 |

Farm A lacks a single core channel, carries the least `<nan>` of the three, holds 144 positive
windows from 12 events, and is still at chance. That leans toward (i), but a single absent channel
is still a pattern the backbone never saw, so (ii) is not excluded. The two diagnostics below
separate the readings. **Nothing here re-opens the CARE verdict**: CARE stays NOT EVALUABLE, the
temporal split carries both hypotheses, and neither diagnostic is a gate.

**2. F6-0a -- masking transfer test.** Registered protocol:

> The three tel_only final-step probes (the ADR-0022 addendum rule in force) are scored on the
> training-site forward-in-time stride-12 test split (137,025 windows, 5,312 positive) with each
> CARE farm's missing-channel pattern imposed at inference: the farm's absent core channels are
> replaced by <nan> tokens on every step, exactly as the CARE adapter emits them, and nothing else
> changes. Three patterns (A: main_bearing_temp_c; B: nacelle_temp_c, generator_bearing_temp_c,
> generator_winding_temp_c; C: nacelle_position_deg, nacelle_temp_c, generator_bearing_temp_c)
> × three seeds = nine scorings. Block bootstrap as ADR-0021 (two-day blocks, 10,000 replicates,
> seed 20260916, discard rule 1%); each masked read also carries its paired Δ against the seed's
> unmasked F3 read on the identical windows.

Pre-registered reading:

> If under farm A's pattern the pooled 95% lower bound stays above the split's base rate (0.0388)
> on at least two of three seeds, a one-channel gap does not null the probe, and the CARE farm-A
> null is read as failure to transfer. If under a farm's pattern the pooled interval contains
> 0.0388 on at least two of three seeds, that pattern alone is sufficient to null the probe and
> that farm's CARE null remains unattributed. The two readings may differ by farm and are reported
> per farm.

**This reading has a gap.** A masked read whose lower bound clears 0.0388 on exactly one seed, or
whose interval lies wholly below 0.0388 on two or more, meets neither clause. It is reported as
measured, and the farm's null stays unattributed. No third clause is added after the numbers
exist.

The unmasked reference is F3's saved final-step score for each seed on the same 137,025 windows
(`checkpoints/seed_replication_v0_424c4f33/`), not re-scored. The paired Δ = AUPRC(masked) −
AUPRC(unmasked) is ADR-0024 §2's paired block bootstrap: the blocks are drawn once per replicate
and both reads are taken on the identical resampled rows. It is reported beside each masked
interval and decides nothing.

**These nine rows are also the project's first H2 measurement**: targeted channel dropout at
inference, forward in time, at the same sites. They will be reused as such. **No H2 result is a
site-shift result.** The masking here is in-distribution modality dropout at the two training
sites, and the F5 outcome's limitation applies to every one of these rows.

**3. F6-0b -- bag-of-tokens on CARE.** Registered protocol:

> The G2 bag-of-tokens classifier (ADR-0024 (6), trained on the training sites, unchanged, no
> refit) is scored on the CARE stride-12 set of ADR-0022 (430,506 windows, 540 positive), pooled
> and per farm, same bootstrap, base rate the scored set's own.

Pre-registered reading:

> If its pooled interval contains 0.001254, no order-blind classifier transfers either and the
> null is a property of the token stream across OEMs; if its pooled lower bound exceeds 0.001254,
> the backbone specifically fails to transfer where an order-blind classifier does not. Reported
> beside the F5 CARE rows; not a gate.

**This reading has a gap too.** An interval wholly below 0.001254 meets neither clause and is
reported as measured. Every per-farm row carries its farm's `<nan>` share
(`configs/eval/README.md`, rule 1).

**4. Cost and resume.** F6-0a is about **1 h of GPU**. That estimate scales F5's measured 20.7
minutes per CARE scoring of 430,506 windows to this split's 137,025, about 7 minutes a scoring,
nine scorings. F6-0b is under 30 minutes of CPU. Each scoring checks for its own output before it
scores and skips it if present. Each row's bootstrap result is written to JSON as it completes.
The report states how many rows were computed and how many resumed from disk, as the F5 report
does.

**5. What this addendum does not do.** No arm is pretrained. ADR-0022's verdict, its assignment
and the checkpoint rule (`final_step` gates) stand. Neither diagnostic can make CARE evaluable, and
neither reading changes which axis carries H1 or H2. **F6 is not authorised by this addendum**, and
neither is the execution of F6-0a or F6-0b.

### Outcome of the F6-0 addendum, 2026-09-18 -- farm A's CARE null reads as failure to transfer; farms B and C stay unattributed

**Run.** `faultline model care-attribution` with `configs/eval/care_attribution_v0.yaml` (hash
`424956da`), on the user's authorisation of 2026-09-18. Report:
`reports/data/care_attribution_v0_20260918.md` and its `.json`. The three final-step probes were
read under the rule in force. Seed 2 selected its last step, so its selected probe
(`S2_trained_seed2_probe.pt`) **is** its final probe, and that one file was read. The index held
the registered counts: 137,025 temporal windows with 5,312 positive, and 430,506 CARE windows
with 540 positive. The nine masked scorings cost **1.02 GPU-hours**. The comparator's CARE
scoring cost 7 s of CPU. The scoring invocation computed all 10 scorings and all 13 bootstrap
rows, and the committed report was re-rendered from those saved artefacts (0 computed, 10 and 13
resumed).

**The masking is the adapter's.** A CARE farm's absent core channel is a column its frame does
not carry. `QuantileBinTokenizer.transform` emits `MISSING_BIN` for it, and
`JointVocab.encode_steps` maps that to `<nan>` (id 9) at position `1 + channel_index` of every
step. There are no channel tokens. F6-0a writes id 9 at exactly those positions and changes
nothing else. This was checked three ways:

- a unit test on a synthetic window: the masked stream differs from the unmasked one only at the
  masked channels' bin positions, the replacement is the tokenizer's `<nan>` id, and the result
  equals the adapter path's own encoding;
- 256 real CARE windows per farm, which masking with their own farm's pattern leaves unchanged;
- each seed's unmasked first batch, re-scored through this path, reproduces F3's saved logits
  exactly (difference 0).

**Table 1 -- F6-0a.** Pooled over the temporal split, against the registered 0.0388. Δ is
AUPRC(masked) − AUPRC(unmasked), paired, and decides nothing. The unmasked read is F5's.

| pattern | seed | masked AUPRC [95% block] | position | paired Δ [95%] | unmasked AUPRC [95% block] |
| --- | --- | --- | --- | --- | --- |
| farm A | 1 | 0.0625 [0.0536, 0.0729] | clears | +0.0045 [-0.0020, +0.0107] | 0.0580 [0.0505, 0.0672] |
| farm A | 2 | 0.0539 [0.0466, 0.0625] | clears | -0.0037 [-0.0096, +0.0013] | 0.0576 [0.0503, 0.0670] |
| farm A | 3 | 0.0523 [0.0459, 0.0594] | clears | +0.0008 [-0.0010, +0.0026] | 0.0515 [0.0453, 0.0586] |
| farm B | 1 | 0.0604 [0.0524, 0.0695] | clears | +0.0024 [-0.0013, +0.0056] | 0.0580 [0.0505, 0.0672] |
| farm B | 2 | 0.0585 [0.0506, 0.0682] | clears | +0.0008 [-0.0015, +0.0033] | 0.0576 [0.0503, 0.0670] |
| farm B | 3 | 0.0550 [0.0475, 0.0637] | clears | +0.0035 [-0.0004, +0.0085] | 0.0515 [0.0453, 0.0586] |
| farm C | 1 | 0.0525 [0.0457, 0.0606] | clears | -0.0056 [-0.0089, -0.0029] | 0.0580 [0.0505, 0.0672] |
| farm C | 2 | 0.0488 [0.0421, 0.0574] | clears | -0.0088 [-0.0123, -0.0057] | 0.0576 [0.0503, 0.0670] |
| farm C | 3 | 0.0517 [0.0451, 0.0590] | clears | +0.0002 [-0.0030, +0.0037] | 0.0515 [0.0453, 0.0586] |

No interval discarded a replicate. The lowest masked lower bound is 0.0421, so the choice between
the registered 0.0388 and the unrounded 0.03877 decides nothing.

**The F6-0a reading, applied per farm.**

- **Farm A: the first clause holds.** The lower bound clears 0.0388 on 3 of 3 seeds. A one-channel
  gap does not null the probe, and **the CARE farm-A null is read as failure to transfer.**
- **Farms B and C: neither clause holds.** Each clears 0.0388 on 3 of 3 seeds and contains it on
  none. The first clause is registered for farm A's pattern only, and the second needs two seeds
  containing the line. The addendum's gap sentence names two such outcomes (one seed clearing,
  or two or more wholly below). This is a third, and it too meets neither clause. **Under the
  addendum's "neither reading" sentence, each is reported as measured, and farm B's and farm C's
  nulls stay unattributed.** No third clause is added.

Reported only: farm C's pattern lowers AUPRC on seeds 1 and 2, with paired intervals wholly below
zero (−0.0056 and −0.0088). Seed 3's interval straddles zero. Every other paired interval
straddles zero.

**Table 2 -- F6-0b.** The G2 comparator as saved (`bag_of_tokens.pt`, not refit; it reproduces
G2's saved temporal logits exactly), on CARE at stride 12. F5's final-step probe rows are beside
it.

| group | `<nan>` share | own base rate | bag of tokens [95% block] | position | discarded | probe seeds 1 / 2 / 3 (F5, final step) |
| --- | --- | --- | --- | --- | --- | --- |
| CARE, pooled | 21.34% | 0.001254 | 0.001940 [0.001233, 0.003830] | contains 0.001254 | 0.00% | 0.001331 / 0.001183 / 0.001211 |
| farm A | 8.35% | 0.001489 | 0.003602 [0.001111, 0.017206] | contains own rate | 0.00% | 0.001375 / 0.001283 / 0.001337 |
| farm B | 25.01% | 0.001017 | 0.001562 [0.000262, 0.008887] | contains own rate | 0.11% | 0.000785 / 0.000757 / 0.000818 |
| farm C | 25.22% | 0.001232 | 0.001995 [0.001204, 0.003162] | contains own rate | 0.00% | 0.001527 / 0.001148 / 0.001327 |

**The F6-0b reading, applied to the pooled row.** The pooled lower bound is 0.001233, which is
0.000021 below 0.001254, so the interval contains the line and **the first clause holds**. No
order-blind classifier transfers either, and the null is a property of the token stream across
OEMs. The margin is narrow and is reported as measured. The per-farm rows decide nothing.

**What the CARE null is attributed to, by the registered readings only.**

- **Farm A:** failure to transfer (F6-0a, first clause).
- **Farm B:** unattributed (F6-0a meets neither clause).
- **Farm C:** unattributed (F6-0a meets neither clause).

No registered clause attributes any farm's null to the missing-channel pattern. F6-0b's reading is
pooled and attributes no single farm.

The nine F6-0a rows are the project's first H2 targeted-dropout measurement: forward in time, at
the same sites. They are not a site-shift result.

**ADR-0022's verdict and assignment are unchanged.** CARE stays NOT EVALUABLE, the temporal split
carries both H1 and H2, and `final_step` stays the checkpoint rule.

---

## ADR-0023 The random-init probe control: can the frozen probe see backbone quality?

**Status:** Accepted; **pre-registered 2026-09-16, before any code, configuration or run of the
control exists** · **Date:** 2026-09-16 · **Criterion superseded by ADR-0024 (2026-09-17). The
§a-§d FAIL verdicts below stand as recorded.**

**Context.** H1 is read entirely through the frozen probe (ADR-0020). Doubling pretraining lowered
selected validation loss from 4.21 to 3.317, about 0.9 nats, and no site's probe AUPRC moved
outside its interval (ADR-0021 outcome). There are two readings. Either next-token loss does not
track a risk-relevant representation, or the probe cannot see backbone quality at all. Only a
control separates them. If the probe cannot see backbone quality, no arm comparison read through
it is informative, and the choice of evaluation axis (ADR-0022) does not matter.

**The criterion, verbatim as registered.**

> The probe is judged sensitive to backbone quality if and only if, on the pooled Kelmarsh +
> Penmanshiel test split with the same 12,000-window block bootstrap and 95% interval used in
> ADR-0021, the full-budget `tel_only` seed-1 backbone's AUPRC interval lies entirely above the
> random-init backbone's AUPRC interval. Hill of Towie is reported alongside but does not
> decide. If the criterion fails, the probe is the defect; the arm runs do not proceed until a
> redesigned probe passes this same criterion.

**How the criterion is read, fixed here before any number exists.**

- **The pooled split.** Kelmarsh's and Penmanshiel's test windows, as every probe here scores
  them (`configs/train/telemetry_v1.yaml`, evaluation: stride 1, 12,000 windows per source, seed
  20260912). That is **24,000 windows, 919 positive (438 + 481), and 373 of 5,705 occupied 48-hour
  blocks holding a positive**, counted from the labels in the gate run's saved test file. "The
  same 12,000-window block bootstrap" means the same procedure over these pooled windows: blocks
  of 288 steps within each source's shard, resampled with replacement, **10,000 replicates,
  seed 20260916, 95% percentile interval**, one AUPRC per replicate over the pooled windows.
  If more than 1% of either side's replicates are discarded, that interval is untrusted and the
  criterion is not met.
- **Three random-init backbones, one criterion.** The random-init side has three seeds (1, 2,
  3), so it has three intervals. **The criterion is met if and only if the trained backbone's
  lower bound is strictly above the upper bound of every one of the three.** A pass against the
  most favourable random seed alone does not count.
- **The trained side** is the registered gate run as scored: the full-budget `tel_only` seed-1
  backbone's probe, from its saved test scores
  (`checkpoints/gate_check_v0_9697a266/S2_tel_only_seed1_test_scores.npz`). It is not re-run for
  this criterion.
- **The random-init side.** The S2 backbone at the joint vocabulary and context 2,048, built by
  the same constructor pretraining uses (`TelemetryDecoder`), with the global seed set to the init
  seed before construction, as pretraining sets it, and **no optimiser step taken**. Its probe
  is the frozen probe of `probe_and_score`, run exactly as the full-budget probe was: seeded with
  the same seed, the balanced sampler, 16,000 positives, rate 2e-3, six validation measurements
  on the selection windows, the best of them selected, and the same test pass. Only the backbone's
  weights differ. **Every selected probe head is saved**, so that ADR-0019's check (the F2
  addendum) can be measured on it.
- **Reported, deciding nothing:** Hill of Towie's AUPRC and block interval for all four backbones,
  and each source's AUPRC separately.
- **This control selects no axis.** The pooled split is the same set of windows as the
  temporal-holdout candidate of ADR-0022. It asks whether the probe responds to the backbone, not
  whether that axis is evaluable, and ADR-0022's rule is registered separately.

**If the criterion fails: one redesign iteration, in this order.** Each step is registered as its
own sub-section here (**§b**, **§c**, **§d**), committed before its code or run, and judged by the
same criterion against three random-init backbones read through the same design:

- **§b** the probe reads the mean of the final hidden states over the window, instead of the
  final position;
- **§c** a two-layer MLP probe on the same pooled states;
- **§d** the last two backbone blocks unfrozen, at a separate, lower learning rate.

The first design that passes becomes the probe for every arm. It is stated here, and the change
goes into a new version of the C0 configuration (`configs/train/telemetry_v1.yaml` is frozen). **If
§d also fails, the work stops and is reported; nothing further proceeds.**

**What a pass does not show.** A pass says that the probe can tell a pretrained backbone from an
untrained one on the training sites' test windows. It does not say that it can tell two
pretrained arms apart, or that any held-out axis is evaluable.

### Result, 2026-09-16 (F1b) -- FAIL: the final-position frozen probe cannot tell the trained backbone from an untrained one

The criterion was registered in commit **`c9489a2`**, before `faultline model probe-control`,
`configs/train/probe_control_v0.yaml` or any run of them existed
(`reports/data/probe_control_v0_20260916.md`). Three random-init S2 backbones (seeds 1-3) were
probed exactly as the gate run's backbone was. Each probe took 3.6 minutes.

| backbone | pooled Kelmarsh + Penmanshiel AUPRC | 95% block interval (decides) | Hill of Towie AUPRC | 95% block interval (reported) |
| --- | --- | --- | --- | --- |
| **full-budget `tel_only`, seed 1** | **0.0502** | **[0.0434, 0.0587]** | 0.0393 | [0.0306, 0.0553] |
| random init, seed 1 | 0.0405 | [0.0353, 0.0470] | 0.0427 | [0.0328, 0.0591] |
| random init, seed 2 | 0.0401 | [0.0351, 0.0461] | 0.0406 | [0.0328, 0.0514] |
| random init, seed 3 | 0.0428 | [0.0372, 0.0500] | 0.0423 | [0.0326, 0.0609] |

Pooled split: 24,000 windows, 919 positive, base rate 0.0383. No replicate was discarded on
either side.

**Verdict: FAIL. The trained lower bound, 0.0434, is not above the highest random-init upper
bound, 0.0500 (seed 3).** The trained lower bound is above seeds 1 and 2's upper bounds, and that
does not count, as registered. **As registered, the probe is the defect.** The arm runs do not
proceed, and §b is registered next.

Recorded beside the verdict, deciding nothing:

- The trained backbone's point estimate is above every random-init interval on the pooled split.
  The failure is at the interval, not the point. The probe does see something of the backbone,
  and not enough to clear the registered bar.
- Per source, the gap is at Kelmarsh (trained 0.0518; random 0.0351 to 0.0368, around its base
  rate of 0.0365). At Penmanshiel the random backbones score 0.0454 to 0.0508 against the trained
  0.0504. At Hill of Towie **every random-init backbone scores above the trained one** (0.0406 to
  0.0427, against 0.0393).
- The random-init probes' training loss ends at 0.685 to 0.687, near ln 2 = 0.693. Their selected
  validation AUPRC (0.0224 to 0.0291, at steps 332 to 996) is below the trained probe's 0.0441 at
  step 166.

### §b, registered 2026-09-16 before its code or run -- the probe reads the window's mean hidden state

**Status:** pre-registered after the §a FAIL (commit `81a8fab`), before any §b code, configuration
or run exists.

**The design.** The frozen probe reads **the mean of the backbone's final hidden states over every
position of the window** (all 1,872 tokens: 144 steps of `<sep>` and 12 channel tokens, after
the final norm), instead of the final position's state. Nothing else changes. The head is the same
one-hidden-layer `RiskHead`, including its input norm, and it receives the pooled vector. The
probe stage is also unchanged: balanced sampling, 16,000 positives, rate 2e-3, six validation
measurements, the best one selected, and the prior correction. The M1e objection in
`faultline.model.risk` ("mean-pooling would score better and would not be deployable a step at a
time") is set aside for this sub-step, as the brief authorises. A mean over a fixed 144-step
window needs the same window a final-position read does, and whether it streams is a deployment
question, not a question about the representation.

**The criterion, unchanged.** It is ADR-0023's criterion, read as registered in `c9489a2`, with
both sides probed through the §b design:

- **Trained side:** the full-budget `tel_only` seed-1 backbone
  (`checkpoints/gate_check_v0_9697a266/S2_tel_only_seed1.pt`), probed through §b with seed 1. The
  §a scores are not reused.
- **Random-init side:** the same three untrained backbones as §a (seeds 1, 2, 3; pretraining's
  initialisation, no optimiser step), each probed through §b with its own seed.
- **Pooled** Kelmarsh + Penmanshiel test split, same windows, same block bootstrap. **Met if and
  only if the trained lower bound is strictly above the upper bound of every one of the three.**
  Hill of Towie is reported and does not decide. Every selected head is saved.

**On FAIL, §c is registered next** (a two-layer MLP probe on the same pooled states). **On PASS,
§b is the probe for every arm.** A new version of the C0 configuration then records it, because
`telemetry_v1.yaml` is frozen.

### §b result, 2026-09-16 -- FAIL: mean pooling does not separate the trained backbone either

§b was registered in **`04af42f`**, before `configs/train/probe_control_v1.yaml` (hash 1a56b74f), the
pooling option in `RiskSpec` or any run of them (`reports/data/probe_control_v1_20260916.md`,
git_sha `04af42f`). All four backbones were probed through the mean-pooled design, which took 0.36
GPU-hours.

| backbone | pooled Kelmarsh + Penmanshiel AUPRC | 95% block interval (decides) | Hill of Towie AUPRC | 95% block interval (reported) | selected validation AUPRC |
| --- | --- | --- | --- | --- | --- |
| **full-budget `tel_only`, seed 1** | **0.0542** | **[0.0463, 0.0641]** | 0.0360 | [0.0299, 0.0451] | 0.0352 at step 166 |
| random init, seed 1 | 0.0515 | [0.0424, 0.0661] | 0.0347 | [0.0295, 0.0414] | 0.0223 at step 996 |
| random init, seed 2 | 0.0510 | [0.0429, 0.0619] | 0.0358 | [0.0302, 0.0448] | 0.0257 at step 996 |
| random init, seed 3 | 0.0472 | [0.0402, 0.0562] | 0.0379 | [0.0305, 0.0517] | 0.0255 at step 498 |

**Verdict: FAIL. The trained lower bound, 0.0463, is not above the highest random-init upper bound,
0.0661 (seed 1).** It is not above any of the three random-init upper bounds. §c is registered
next.

Recorded, deciding nothing. Mean pooling raised the pooled AUPRC of **both** sides: trained from
0.0502 to 0.0542, random init from 0.0401-0.0428 to 0.0472-0.0515. It narrowed the gap between
them. At the point estimate, the trained backbone is now 0.0027 above the best random-init
backbone, against 0.0074 under §a. Across all four backbones, Hill of Towie scores sit between
0.0347 and 0.0379, against a base rate of 0.03325.

### §c, registered 2026-09-16 before its code or run -- a two-layer MLP probe on the mean-pooled states

**Status:** pre-registered after the §b FAIL (commit `a4cfc49`), before any §c code, configuration
or run exists.

**The design.** The probe reads the same mean-pooled final hidden states as §b. The head becomes a
two-layer MLP. **"Two-layer" is read here as two hidden layers**, because the head every probe has
used so far (`RiskHead`) already has one: input norm (RMSNorm), Linear(192 → 192), GELU,
Linear(192 → 192), GELU, Linear(192 → 1). The width is the ladder's head width (`head_hidden` 1.0
× `d_model`), and the dropout is the ladder's head dropout. The initialisation is `RiskHead`'s:
normal(0, 0.02) weights and zero biases. **Nothing else changes:** frozen backbone, balanced
sampling, 16,000 positives, rate 2e-3, six validation measurements with the best one selected, and
the prior correction.

**The criterion, unchanged.** It is ADR-0023's criterion as registered in `c9489a2`, read as in §b.
Both sides are probed through §c: the full-budget `tel_only` seed-1 backbone with seed 1, and the
three untrained backbones (seeds 1-3, pretraining's initialisation) with their own seeds. The
split is the pooled Kelmarsh + Penmanshiel test split, with the same block bootstrap. **Met if and
only if the trained lower bound is strictly above the upper bound of every one of the three.**
Hill of Towie is reported and does not decide. Every selected head is saved.

**On FAIL, §d is registered next** (the last two backbone blocks unfrozen, at a separate, lower
rate). **On PASS, §c is the probe for every arm.**

### §c result, 2026-09-16 -- FAIL: a two-hidden-layer head does not separate the trained backbone either

§c was registered in **`7e230be`**, before `configs/train/probe_control_v2.yaml`, the `layers` option
in `RiskSpec` or any run of them (`reports/data/probe_control_v2_20260916.md`, git_sha `7e230be`;
the run crossed midnight UTC+9, and the report's date is its UTC date). It took 0.35 GPU-hours.

| backbone | pooled Kelmarsh + Penmanshiel AUPRC | 95% block interval (decides) | Hill of Towie AUPRC | 95% block interval (reported) | selected validation AUPRC |
| --- | --- | --- | --- | --- | --- |
| **full-budget `tel_only`, seed 1** | **0.0521** | **[0.0449, 0.0608]** | 0.0369 | [0.0305, 0.0470] | 0.0441 at step 166 |
| random init, seed 1 | 0.0462 | [0.0388, 0.0570] | 0.0339 | [0.0289, 0.0405] | 0.0230 at step 166 |
| random init, seed 2 | 0.0514 | [0.0432, 0.0624] | 0.0347 | [0.0295, 0.0423] | 0.0267 at step 1000 |
| random init, seed 3 | 0.0471 | [0.0401, 0.0561] | 0.0384 | [0.0309, 0.0529] | 0.0260 at step 498 |

**Verdict: FAIL. The trained lower bound, 0.0449, is not above the highest random-init upper bound,
0.0624 (seed 2),** or above any of the three. §d is registered next, and it is the last sub-step
authorised.

Recorded, deciding nothing. Across §a to §c, **the trained backbone's pooled point estimate is
above every random-init point estimate in all three designs** (margins 0.0074, 0.0027, 0.0007).
No design brings its interval clear. The random-init backbones' pooled AUPRC ranges from 0.0401
to 0.0515, above the pooled base rate of 0.0383. An untrained S2 decoder's features carry most of
what these probes read.

### §d, registered 2026-09-17 before its code or run -- the last two backbone blocks unfrozen, at a lower rate

**Status:** pre-registered after the §c FAIL (commit `c743a8b`), before any §d code, configuration
or run exists. **§d is the last sub-step authorised. If it fails, the work stops and is reported.**

**The design.** §c's probe, which is mean-pooled final hidden states into the two-hidden-layer
head, with **the last two of the backbone's eight blocks unfrozen** (`blocks.6` and `blocks.7`,
every parameter in them). It builds on §c, not on §a, so each sub-step only adds capacity to the
one before it. Everything else in the backbone stays frozen: the token and position embeddings,
blocks 0-5, and the final norm.

- **Two learning rates, both fixed here and not tuned.** The head keeps the probe's peak rate of
  **2e-3**. The two unfrozen blocks take **5e-4**, the fine-tune rate that
  `configs/train/telemetry_v1.yaml` fixed before any run (4x lower). Both follow the same warmup
  and cosine schedule, as fixed ratios of it. Weight decay (0.1 on matrices, none on norms and
  biases), betas, clipping (global norm 1.0 over every trainable parameter) and precision are the
  optimiser's.
- **Unchanged:** balanced sampling, 16,000 positives, six validation measurements with the best
  one selected, the prior correction, and the test pass.

**The criterion, unchanged.** It is ADR-0023's criterion as registered in `c9489a2`, read as in §b
and §c. Both sides are probed through §d: the full-budget `tel_only` seed-1 backbone with seed 1,
and the three untrained backbones (seeds 1-3, pretraining's initialisation) with their own seeds.
On the untrained backbones, the same two blocks train from their initialisation. The split is the
pooled Kelmarsh + Penmanshiel test split, with the same block bootstrap. **Met if and only if the
trained lower bound is strictly above the upper bound of every one of the three.** Hill of Towie
is reported and does not decide. Every selected model is saved whole, since its backbone changed.

**What a §d pass would and would not license.** A pass makes §d the probe for every arm. Because
two blocks train, the read-out is then partly a fine-tune. What it measures is the pretrained
representation plus 16,000 positives' worth of adaptation, which ADR-0020 chose the frozen probe
to avoid. That cost is accepted by the brief. It is stated here so that no arm claim reads §d as a
frozen probe.

### §d result, 2026-09-17 -- FAIL; no registered probe design passes, and the work stops here

§d was registered in **`d0351e5`**, before `configs/train/probe_control_v3.yaml`, the unfrozen-tail
code (`forward_with_trainable_tail`, `RiskModel.unfrozen_blocks`, per-group learning-rate scales in
the training loop) or any run of them (`reports/data/probe_control_v3_20260916.md`, git_sha
`d0351e5`, dated in UTC). It took 0.44 GPU-hours, 4.8 minutes a probe.

| backbone | pooled Kelmarsh + Penmanshiel AUPRC | 95% block interval (decides) | Hill of Towie AUPRC | 95% block interval (reported) | selected validation AUPRC |
| --- | --- | --- | --- | --- | --- |
| **full-budget `tel_only`, seed 1** | **0.0541** | **[0.0463, 0.0645]** | 0.0456 | [0.0369, 0.0577] | 0.0487 at step 166 |
| random init, seed 1 | 0.0497 | [0.0419, 0.0595] | 0.0347 | [0.0295, 0.0411] | 0.0207 at step 332 |
| random init, seed 2 | 0.0461 | [0.0399, 0.0542] | 0.0348 | [0.0290, 0.0446] | 0.0307 at step 996 |
| random init, seed 3 | 0.0463 | [0.0397, 0.0547] | 0.0399 | [0.0322, 0.0509] | 0.0210 at step 1000 |

**Verdict: FAIL. The trained lower bound, 0.0463, is not above the highest random-init upper bound,
0.0595 (seed 1).** It is above the upper bounds of seeds 2 and 3, and that does not count, as
registered.

**All four registered designs fail ADR-0023's criterion.** As registered, **the work stops here and
is reported.** F2 (the prior-band check), F3 (seeds 2 and 3), F4 (ADR-0022) and F5 (the axis gate)
are not started. No probe design is in force for any arm, the C0 configuration is not versioned,
and ADR-0022 stays reserved with nothing decided under it. The report's generic line, "the next
registered sub-step", has no referent: none is authorised.

**The four designs, the pooled criterion side by side** (trained lower bound against the highest
random-init upper bound; the trained point estimate against the best random-init point estimate):

| sub-step | design | trained interval | highest random upper bound | trained point − best random point |
| --- | --- | --- | --- | --- |
| §a | final position, one hidden layer, frozen | [0.0434, 0.0587] | 0.0500 | +0.0074 |
| §b | mean-pooled, one hidden layer, frozen | [0.0463, 0.0641] | 0.0661 | +0.0027 |
| §c | mean-pooled, two hidden layers, frozen | [0.0449, 0.0608] | 0.0624 | +0.0007 |
| §d | §c with blocks 6-7 unfrozen at 5e-4 | [0.0463, 0.0645] | 0.0595 | +0.0044 |

Recorded beside the stop, deciding nothing:

- **In every design, the trained backbone's pooled point estimate is above every random-init
  point estimate, and in no design does its interval clear.** The probes see something of the
  pretraining. On the training sites' test windows, a 12,000-window-per-source evaluation cannot
  resolve that from an untrained S2 decoder. The two readings in this record's context are not
  separated, because the control cannot resolve its own contrast. "The probe is the defect" is the
  verdict the registered rule assigns. The data alone do not show whether the defect is the probe,
  the evaluation's resolution, or a pretraining signal too small to see.
- **Under §d, Hill of Towie's trained interval, [0.0369, 0.0577], lies above its base rate of
  0.03325.** This is a different read-out from ADR-0021's frozen probe, and one design of four. As
  ADR-0021 registered, the demotion is not reversed by a later, better Hill of Towie result.
- **All four trained-backbone probes selected their first validation measurement, step 166 of
  1,000.** Of the twelve random-init probes, eleven selected later steps. The prior-band question
  that F2 would have asked of such an early checkpoint is still open.
- Probe compute for the whole control, §a to §d: 0.27 + 0.36 + 0.35 + 0.44 = 1.42 GPU-hours.

---

## ADR-0024 The probe-sensitivity criterion is a paired test, and a bag-of-tokens comparator is reported beside it

**Status:** Accepted; **pre-registered 2026-09-17, after ADR-0023's four results were seen,
before any paired interval, any re-scoring or any comparator code or run exists** · **Date:**
2026-09-17 · Supersedes ADR-0023's criterion, not its verdicts.

### 1. Why ADR-0023's criterion is superseded

ADR-0023 required the trained backbone's block-bootstrap interval to lie entirely above each
random-init backbone's interval, **each interval bootstrapped on its own**. Both models are scored
on the same test windows, so their bootstrap estimates are strongly positively correlated. The
variance of their difference is Var(A) + Var(B) - 2 Cov(A, B), not Var(A) + Var(B). Requiring two
independent 95% intervals not to overlap is a far stricter test than a 5% one (the
overlapping-confidence-intervals fallacy). Each interval is about 0.015 wide, and the point gap is
about +0.009 at best (§a). The registered rule could not have passed at any of the four designs.
The rule was specified in the F-brief's Hill of Towie ruling (§3) and reproduced faithfully in
`c9489a2`, so the error is in the specification. **The four FAIL verdicts are retained as
recorded.** This record registers the test the question needed, a paired block bootstrap of the
difference. It is registered **after** ADR-0023's results were seen. No paired interval had been
computed when it was written.

### 2. The criterion

> The probe is judged sensitive to backbone quality if and only if, on the pooled Kelmarsh +
> Penmanshiel test split, the paired block-bootstrap 95% percentile interval of ΔAUPRC =
> AUPRC(trained, full-budget `tel_only` seed 1) − AUPRC(random-init seed k), computed by
> resampling two-day blocks once per replicate and scoring both models on the identical resampled
> set, has a lower bound strictly greater than zero for **each** of k = 1, 2, 3. Same number of
> replicates as ADR-0021. Hill of Towie is reported alongside and does not decide.

**How it is read, fixed here.**

- **Blocks and replicates are ADR-0021's.** A block is a window's end step integer-divided by 288
  (48 hours), within its source's shard. Each replicate draws as many blocks as are occupied, with
  replacement, and takes every window of each drawn block each time it is drawn. **10,000
  replicates, bootstrap seed 20260916, 95% percentile interval.** The trained and the random-init
  scores are read on the same drawn rows, and Δ is computed per replicate. The same seed serves
  every k, so all three comparisons draw identical blocks.
- **Discards.** A replicate with no positive window is discarded and counted. If more than 1% of
  a comparison's replicates are discarded, that comparison's interval is untrusted, and the
  comparison fails.
- **Scores** are each probe's test logits plus its prior offset. AUPRC reads only the order, so
  the offset does not change Δ.
- **Each design is compared within itself.** Its trained probe is compared with the three
  random-init probes read through the same design.

### 3. The order of application, fixed before any paired interval exists

1. **§a** (final position, one hidden layer, frozen) first. It is the original design, the one
   every prior result used, and the one with the largest point gap. **If §a passes, §a is the probe
   for every arm**, and §b-§d are reported for the record only.
2. If §a fails, **§d**, the only other design with a point gap materially above zero.
3. Then **§b**, then **§c**.

The first design to pass is the probe. If none passes on the deciding split (§4), the work stops
and is reported: the pretraining effect cannot be resolved on this project's test set.

### 4. The test set: the full split thinned to stride 12, by the user's choice

**Measured 2026-09-17 from the window index, labels only, before any score.** The 24,000-window
set ADR-0023 read is a **seeded subsample** (12,000 per source, `configs/train/telemetry_v1.yaml`)
of the pooled test split:

| set | windows | positive windows | base rate | occupied 48-hour blocks | blocks holding a positive |
| --- | --- | --- | --- | --- | --- |
| full pooled split, stride 1 | 1,644,286 | 63,760 | 0.03878 | 5,800 | 506 |
| **stride 12 (deciding)** | **137,025** | **5,312** | 0.03877 | **5,799** | **497** |
| ADR-0023 subsample | 24,000 | 919 | 0.03829 | 5,705 | 373 |

By source, the full split is Kelmarsh 926,430 windows (34,065 positive, 3,268 blocks, 251 of them
positive) and Penmanshiel 717,856 (29,695; 2,532; 255). At stride 12 it is Kelmarsh 77,203
(2,841; 3,268; 248) and Penmanshiel 59,822 (2,471; 2,531; 249).

**Why not stride 1.** The F-brief directed the full split. Its reasoning was that interval width
falls with the square root of the positive count. Under a block bootstrap, the resampled unit is
the block, and the full split adds few blocks: positive blocks go from 373 to 506 while positive
windows go up about 69x. Scoring throughput, measured on the S2 backbone on this machine, is **343
windows a second**, the same for the final-position and the mean-pooled read-outs. One model on the
full split would take **1.33 GPU-hours**: 5.3 for §a's four models, and about 21 if every design
were scored. The brief estimated under 0.3 for G0-G3. **On 2026-09-17 the user chose the full split
thinned to stride 12**: every 12th admissible window of each shard's index, taken as
`load_windows(..., stride=12)` takes it, with no cap and no random subsample. It keeps 5,799 of
5,800 blocks and 497 of 506 positive blocks, at about 24 windows a block, and it costs about **6.7
minutes a model**.

**What decides and what is reported.**

- **Deciding:** the stride-12 pooled Kelmarsh + Penmanshiel test split, for each design tested in
  §3's order, and only for those designs.
- **Reported beside it:** the paired Δ on ADR-0023's 24,000-window subsample for **all four
  designs**, from the scores already saved. Hill of Towie's paired Δ is reported on its saved
  12,000-window subsample. It is not re-scored at stride 12.
- **A design not tested** in §3's order is not re-scored at stride 12. Its record is the
  subsample row.

**Re-scoring, not retraining.** Every selected random-init probe of §a-§d, and the trained probes
of §b-§d, were saved whole under `checkpoints/probe_control_v*_*/`. They are loaded and scored on
the stride-12 windows, with no optimiser step. **The §a trained probe is the one exception: the
ADR-0021 gate run did not save its head** (`faultline.evaluation.gate_check` passed no `save_to`).
Its probe stage is re-run on the saved gate backbone, seeded exactly as before, and this time the
head is saved. The re-run is accepted as the gate run's probe **only if it reproduces the record
to four decimals**: selected at step 166 with validation AUPRC 0.0441, and pooled 24,000-window
test AUPRC 0.0502. The same check passed for both ADR-0020 probes (ADR-0021 outcome). If the re-run
does not reproduce the record, nothing is scored, and the discrepancy is reported.

### 5. The selection split, confirmed disjoint from test

Every probe in ADR-0021 and ADR-0023 selects its checkpoint on `splits["selection"]` from
`open_probe_inputs` (`src/faultline/evaluation/variance_probe.py`), which `probe_measure` in
`probe_and_score` reads. That split is `build_split(telemetry, "val", 3000, stride 1, seed
20260912)`. The only `val` shards are `kelmarsh__val` and `penmanshiel__val`, and every window in
them has year 2021. The test shards `kelmarsh__test` (2022-2024) and `penmanshiel__test` (2022)
are separate files, so no window spans the two splits (`configs/data/splits_v1.yaml`, `val_until`
2021-12-31). Hill of Towie and CARE have no `val` shard. **No probe was selected on test windows.**
Only a `val` window's label reaches past the cut: its 24-hour horizon may read an event on
2022-01-01. That is a label, not a test window, and nothing from it enters a test score. G1
proceeds.

### 6. The bag-of-tokens comparator (reported, not gating)

A classifier that ignores token order, to measure whether the sequence model beats one.

- **Features.** For each window, the count of each telemetry token id over its 1,872 tokens,
  across the tokenizer's full vocabulary (**1,184 ids**, `quantile_bins_v2_9cd52b65`, `<sep>` and
  `<nan>` included), divided by the window's 144 steps. Each channel's bins then sum to 1. Nothing
  else is fitted to the data: no standardisation and no feature selection.
- **Model.** Logistic regression: one linear layer, 1,184 → 1, with a bias, initialised to zero.
- **Training: the probe stage's, on CPU.** The same balanced sampler seeded with **1**, 16,000
  positives, 16 windows x 2 accumulation, peak rate 2e-3 with the optimiser's warmup, cosine
  schedule, weight decay and clipping, **six validation measurements on the same selection split
  (§5), and the best one selected.** The prior correction is applied as it is for the probe. None
  of these values is tuned. The comparator's training loss and selected step are reported, so a
  fit still improving at the end is visible.
- **Scored** on the deciding stride-12 split and on the 24,000-window subsample, each with the
  ADR-0021 block bootstrap. The G1 table reports its AUPRC and interval, and the paired Δ (the
  trained probe of the design in force minus bag-of-tokens) with its paired interval under §2's
  procedure.
- **It decides nothing.** If the comparator is within noise of the trained probe, the outcome says
  so in one sentence, and the arm comparison stays the registered study.

### 7. What this record does not change

The three-arm x three-seed design and S2-only stand. ADR-0021's NOT EVALUABLE verdict stands.
ADR-0022 stays reserved. F2-F5 of the F-brief wait on G1, and F6 is not authorised.

### Outcome, 2026-09-17 (G1) -- PASS: the final-position frozen probe sees the pretrained backbone; §a is the probe in force

The criterion was registered in **`79d4e97`**, before `faultline model paired-control`,
`configs/train/paired_control_v0.yaml` (hash b446304a) or any paired interval existed
(`reports/data/paired_control_v0_20260917.md`, git_sha `79d4e97`). The run took 0.84 hours:
0.06 for the §a re-run probe, about 0.53 for re-scoring its four probes, and the rest on CPU
bootstraps.

**The §a re-run reproduced the gate run exactly.** It selected step 166 at validation AUPRC
0.0441, and its pooled subsample AUPRC is 0.0502. Its test logits on all 36,000 subsample windows
equal the gate run's saved logits: the largest absolute difference is 0.0. Each of the four
re-scored probes gave its recorded pooled subsample AUPRC to four decimals, so the stride-12
scores come from the same heads.

**Deciding: §a, pooled Kelmarsh + Penmanshiel test at stride 12** (137,025 windows, 5,312
positive, 497 of 5,799 blocks holding a positive; 10,000 paired replicates, seed 20260916, none
discarded):

| random-init seed | trained AUPRC | random-init AUPRC | Δ | paired 95% interval | lower bound above 0 |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.0532 | 0.0416 | +0.0116 | [+0.0078, +0.0163] | yes |
| 2 | 0.0532 | 0.0406 | +0.0126 | [+0.0083, +0.0180] | yes |
| 3 | 0.0532 | 0.0409 | +0.0123 | [+0.0085, +0.0170] | yes |

**Verdict: PASS. Every paired lower bound is above zero; the lowest is +0.0078. As registered, §a
(final position, one hidden layer, frozen) is the probe for every arm.** §b, §d and §c were not
tested and were not re-scored at stride 12. Their record is the subsample rows below. The step-166
early-selection question (F2, and G3's cadence change) applies to §a and is not waived.

**Reported beside it: paired Δ on ADR-0023's 24,000-window subsample** (373 of 5,705 blocks
holding a positive):

| design | Δ vs seed 1 | Δ vs seed 2 | Δ vs seed 3 |
| --- | --- | --- | --- |
| §a final position | +0.0097 [+0.0049, +0.0154] | +0.0100 [+0.0049, +0.0165] | +0.0074 [+0.0025, +0.0128] |
| §d blocks 6-7 unfrozen | +0.0045 [-0.0028, +0.0119] | +0.0080 [+0.0017, +0.0151] | +0.0078 [+0.0020, +0.0147] |
| §b mean-pooled | +0.0027 [-0.0080, +0.0100] | +0.0032 [-0.0037, +0.0092] | +0.0070 [+0.0018, +0.0125] |
| §c two hidden layers | +0.0059 [-0.0018, +0.0117] | +0.0007 [-0.0071, +0.0067] | +0.0050 [-0.0004, +0.0099] |

**Hill of Towie (12,000 windows, reported, deciding nothing):**

| design | Δ vs seed 1 | Δ vs seed 2 | Δ vs seed 3 |
| --- | --- | --- | --- |
| §a final position | -0.0034 [-0.0158, +0.0092] | -0.0013 [-0.0111, +0.0136] | -0.0030 [-0.0174, +0.0094] |
| §d blocks 6-7 unfrozen | +0.0109 [+0.0022, +0.0218] | +0.0108 [+0.0012, +0.0207] | +0.0056 [-0.0066, +0.0182] |
| §b mean-pooled | +0.0012 [-0.0037, +0.0082] | +0.0002 [-0.0070, +0.0066] | -0.0019 [-0.0141, +0.0067] |
| §c two hidden layers | +0.0030 [-0.0023, +0.0110] | +0.0022 [-0.0031, +0.0093] | -0.0015 [-0.0140, +0.0076] |

Recorded beside the verdict, deciding nothing:

- **The effect is about +0.012 AUPRC at stride 12, about 0.3 times the pooled base rate of 0.0388.**
  On the subsample it is +0.0074 to +0.0100. Pretraining `tel_only` at S2 for 50M tokens moves
  the frozen final-position probe by this much over an untrained backbone on the training sites'
  test windows. Every arm comparison is a comparison of effects of this size or smaller.
- **The subsample alone would also have passed §a** (lowest lower bound +0.0025), so the verdict
  does not depend on the stride-12 choice. The stride-12 intervals are 0.0085 to 0.0097 wide,
  against 0.0103 to 0.0116 on the subsample.
- **Pooling weakened the contrast, as the ruling read it.** On the subsample, no pooled design
  clears zero against all three seeds. §b and §c each fail against two seeds, and §d fails against
  one.
- **On Hill of Towie, the §a trained probe scores below every random-init probe** (Δ -0.0013 to
  -0.0034, every interval spanning zero). The pretraining effect §a sees at the training sites does
  not appear at the held-out site. Only §d shows a Hill of Towie gap, and ADR-0021's demotion is not
  reversed by it.
- **The §a re-run's validation curve** peaked at its first measurement (0.0441 at step 166). It
  then held between 0.0393 and 0.0422 through step 1,000. On this run, early selection took a
  measurement no later one beat.

### Outcome, 2026-09-17 (G2) -- the bag-of-tokens comparator is within noise of the probe in force

`faultline model bag-of-tokens` (`configs/train/bag_of_tokens_v0.yaml`, hash 2b2827a9;
`reports/data/bag_of_tokens_v0_20260917.md`, git_sha `f6c2df0`) trained the §6 comparator as
registered, on the CPU in 8.7 minutes.

| test set | windows / positive | §a probe, 95% block interval | bag of tokens, 95% block interval | Δ probe − bag, paired 95% interval |
| --- | --- | --- | --- | --- |
| stride 12 (deciding split) | 137,025 / 5,312 | 0.0532 [0.0468, 0.0607] | 0.0523 [0.0445, 0.0619] | +0.0008 [-0.0067, +0.0075] |
| 24,000-window subsample | 24,000 / 919 | 0.0502 [0.0434, 0.0587] | 0.0520 [0.0419, 0.0660] | -0.0018 [-0.0137, +0.0074] |

**A logistic regression on the token histogram, which ignores order, scores within noise of the
frozen final-position probe on the pretrained backbone: on the training sites' test windows, the
sequence model does not measurably beat a classifier that ignores order.** The arm comparison
remains the registered study, and the F-brief write-up carries this framing.

Recorded, deciding nothing. The comparator selected its last full validation measurement (0.0261
at step 996). Its validation AUPRC rose from 0.0249 to 0.0261 over the run, and its training loss
ended at 0.664. The fit was still slowly improving, so the registered budget, if anything,
understates it. Its validation AUPRC is well below the §a probe's 0.0441 at step 166, while their
test AUPRCs match. The selection split (2021) and the test split (2022-2024) do not rank these two
classifiers the same way.

### Addendum, registered 2026-09-17 (G3) before its code or run -- the in-force probe's evaluation cadence

**Why.** All four trained probes of ADR-0023, and the §a re-run under G1, selected their first
validation measurement, step 166 of 1,000. A rule that first looks at step 166 cannot tell "best at
166" from "best at 40", and it never sees whether the probe was still improving before 166. F2
measures the prior band on the in-force probe, so the cadence is fixed first.

**The change.** Only when the §a probe is measured, nothing else:

- **Measured at step 0** (the head as initialised, before any optimiser step), **every 25 steps
  through step 300** (25, 50, ..., 300), **then every 100 steps** (400, 500, ..., 1,000): 23
  measurements, step 0 included.
- **Step 0 is a reference point and cannot be selected.** It is reported beside the others. The
  selected checkpoint is the best of the 22 measurements from step 25 onward, the earliest on a
  tie, as before.
- **The selection split is unchanged and named:** `splits["selection"]` of `open_probe_inputs`,
  that is `build_split(telemetry, "val", 3000, stride 1, seed 20260912)` over `kelmarsh__val` and
  `penmanshiel__val` (2021, 6,000 windows). It is disjoint from test (§5).
- **Everything else is the §a probe as G1 reproduced it:** the gate run's saved backbone, seed 1,
  frozen, final position, one hidden layer, balanced sampling, 16,000 positives, 16 x 2, rate
  2e-3, the optimiser's schedule and the prior correction. A measurement is an evaluation-mode pass
  under `no_grad` that consumes no training randomness. The optimiser trajectory is therefore the
  one G1 reproduced, and only where it is looked at changes.

**Reported:** every measurement (step, validation AUPRC); the selected step and its validation
AUPRC; that checkpoint's pooled Kelmarsh + Penmanshiel test AUPRC with ADR-0021's block interval
(10,000 replicates, seed 20260916) on the stride-12 split of §4, and on the 24,000-window
subsample beside it; and Hill of Towie on its 12,000-window subsample, deciding nothing.

**What it decides.** Nothing is re-judged. The step-166 checkpoint remains the ADR-0021 and G1
record, and the checkpoint selected here is the one F2 measures. If it is not step 166, ADR-0024's
paired verdict was read on the step-166 head, and that is stated beside F2's result. The
verdict is not re-run.

**Erratum to the G3 addendum, 2026-09-17, with the code that reads it (no run made).** "23
measurements, step 0 included" and "the best of the 22 measurements from step 25 onward" are
arithmetic slips. Every 25 steps through 300 is 12 measurements, and every 100 from 400 to 1,000
is 7. With step 0 that makes **20 measurements, and the selected checkpoint is the best of 19**.
The steps themselves are as registered, and nothing else changes
(`tests/evaluation/test_probe_cadence.py` pins them).

### Outcome of the G3 addendum, 2026-09-17 -- the in-force probe selects step 200; F2 measures that checkpoint

`faultline model probe-cadence` (`configs/train/probe_cadence_v0.yaml`, hash c9646288;
`reports/data/probe_cadence_v0_20260917.md`, git_sha `577592f`) re-trained the §a probe on the gate
backbone with seed 1 in 17.9 minutes. **Its 1,000-step training log is identical to G1's re-run**:
loss and gradient norm differ by 0.0 at every step. Measuring more often did not change the
trajectory.

**Selected: step 200, validation AUPRC 0.0471.** It is the best of the 19 selectable measurements.
That step was not measured under the old cadence, so it is not the step-166 checkpoint. As the
addendum registered, **ADR-0024's G1 verdict was read on the step-166 head, and it is not re-run.**
The step-200 checkpoint is the one F2 measures.

| step | 0 (reference) | 25 | 50 | 75 | 100 | 125 | 150 | 175 | **200** | 225 | 250 | 275 | 300 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| validation AUPRC | 0.0447 | 0.0465 | 0.0332 | 0.0287 | 0.0400 | 0.0404 | 0.0459 | 0.0465 | **0.0471** | 0.0434 | 0.0406 | 0.0307 | 0.0395 |

| step | 400 | 500 | 600 | 700 | 800 | 900 | 1,000 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| validation AUPRC | 0.0436 | 0.0420 | 0.0413 | 0.0377 | 0.0401 | 0.0426 | 0.0399 |

The step-200 checkpoint's test AUPRC, with ADR-0021's block interval (10,000 replicates, seed
20260916):

| test set | windows / positive | base rate | AUPRC | 95% block interval |
| --- | --- | --- | --- | --- |
| pooled Kelmarsh + Penmanshiel, stride 12 | 137,025 / 5,312 | 0.0388 | 0.0540 | [0.0474, 0.0618] |
| pooled, 24,000-window subsample | 24,000 / 919 | 0.0383 | 0.0510 | [0.0439, 0.0599] |
| Hill of Towie, 12,000-window subsample (reported) | 12,000 / 399 | 0.0333 | 0.0390 | [0.0304, 0.0548] |

Recorded, deciding nothing:

- **The untrained head at step 0 already scores 0.0447 on validation.** That is above 15 of the 19
  trained measurements. Validation AUPRC swings between 0.0287 and 0.0471 across neighbouring
  checkpoints, with no trend. On 6,000 selection windows, selection among these checkpoints is
  mostly selection on noise. "Best at 166" and "best at 200" are not distinguishable from each
  other on this evidence.
- Test AUPRC at step 200 (0.0540 at stride 12) is within noise of step 166 (0.0532), and so is its
  Hill of Towie score.
- Hill of Towie calibration at step 200: prior-corrected mean predicted rate **0.0178**, against a
  base rate of 0.0333 and a training natural rate of 0.0221 (ECE 0.0155). The uncorrected mean is
  0.439. F2 reads these, and nothing is judged here.

### Addendum (F3), registered 2026-09-17 before its code or run -- `tel_only` seeds 2 and 3, each paired against random init under the in-force protocol

**Why.** G1's pass is on one pretraining seed. The effect it measured, about +0.012 AUPRC, is the
size of every arm comparison to come. Before any arm runs, it has to hold on the two further seeds
that the three-arm x three-seed design already requires.

**The pretraining.** `tel_only` at S2, **seeds 2 and 3**, each exactly as the ADR-0021 gate run
pretrained seed 1 (`configs/train/gate_check_v0.yaml`): 763 steps, 50,003,968 tokens, 4 x 8, peak
rate 6e-4, six validation passes over 500 windows a source, and the lowest validation loss
selected. Only the seed differs.

**The in-force protocol, identical on both sides of every comparison.** §a (final position, one
hidden layer, frozen), with the probe seeded by the backbone's seed. Every probe is measured under
**G3's cadence** (step 0 as a reference, every 25 steps through 300, every 100 after) and selected
on the same `val` split. Every probe is scored on the stride-12 pooled Kelmarsh + Penmanshiel test
split of §4.

- **Trained side:** seed 1 is G3's step-200 probe, already scored, not re-run. Seeds 2 and 3 are
  probed after their pretraining.
- **Random-init side: the three §a random-init probes are re-trained under G3's cadence** (seeds
  1-3, pretraining's initialisation, no optimiser step on the backbone) and scored at stride 12. The
  G1 random-init probes were selected under the old cadence, and pairing a G3-selected trained
  probe against them would mix two protocols. The G1 probes are kept as the G1 record.
- **ADR-0019 F2 per trained seed:** each new trained head is measured on the same balanced draw
  (seed 20260917, 16,000 windows) against the same [0.45, 0.55] band, and the rule is applied as
  registered. This touches only calibration, never AUPRC.

**The criterion, per trained seed.** ADR-0024's criterion, unchanged: for trained seed s in
{1, 2, 3}, the paired block-bootstrap 95% interval of AUPRC(trained s) - AUPRC(random-init k),
10,000 replicates, seed 20260916, blocks of 288 steps within each shard, has a lower bound strictly
above zero for **each** k in {1, 2, 3}. Each trained seed gets its own verdict: 3 verdicts from 9
comparisons.

**What the verdicts do.** F3 reports them and stops, as the user directed. **No automatic
consequence is registered.** §a stays the probe in force whatever F3 shows. A seed that fails is
recorded as the evidence it is, for the user's ruling before F4.

**Reported, deciding nothing:**

- per seed, the selected pretraining validation loss and step, the probe's selected step and
  validation AUPRC, and the pooled stride-12 test AUPRC with its block interval;
- Hill of Towie AUPRC with its block interval on the 12,000-window subsample (ADR-0021's demotion
  stands);
- the spread of pooled stride-12 AUPRC across the three trained seeds;
- per seed, the paired Δ against the bag-of-tokens comparator at stride 12, from its saved scores
  (§6);
- the corrected mean predicted rate under the F2 rule.

**F3 additions and resume, registered 2026-09-17 after the first F3 invocation stopped and before any paired interval exists.**
The first invocation stopped without an error line during seed 3's stride-12 scoring. By then it
had completed and saved both pretrainings (seeds 2 and 3), both trained probes, seed 2's
stride-12 scores and both 24,000-window subsample score files. No random-init probe had been
re-trained, and no F3 paired interval or AUPRC interval had been computed. **Saved backbones and
selected probes are read, never re-trained.** Seed 3's probe record was never written. Its
selected step and rates are read from the saved probe, and its validation history from the run
log. Three reported additions, deciding nothing:

1. **Corrected mean on the 2021 validation split.** Each trained seed's selected probe is scored
   on `kelmarsh__val` + `penmanshiel__val` at stride 12, uncapped. Its corrected mean predicted rate
   (the offset F2's rule puts in force) is reported beside that split's base rate and the training
   natural rate. The val split is later than training and earlier than test. A corrected mean near
   the rate the correction targets there, with the under-read appearing only on 2022-2024 test,
   points to shift. An under-read there too points to the probe itself.
2. **The selection split's size, and an interval on selection AUPRC.** The 6,000 selection windows
   (3,000 a source), their positives and their occupied 48-hour blocks. Each trained seed's selected
   checkpoint gets a block-bootstrap interval on its selection AUPRC (ADR-0021's procedure: 10,000
   replicates, seed 20260916), seed 1's step-200 first.
3. **The final-step checkpoint beside the selected one, for every F3 probe.** Pooled stride-12 test
   AUPRC with its block interval, and the final step's validation AUPRC. The three random-init
   probes save both states when they are trained. The trained probes saved only the selected
   state. Seed 2 selected step 1,000, so its final state is its selected state. **For seeds 1
   (step 200) and 3 (step 700), the probe stage is re-run seeded to recover the step-1,000 state.**
   The re-run is accepted only if it reproduces the saved selection exactly (step and validation
   AUPRC) and its per-step training log matches the saved one row for row. It writes a separate
   final-state file and never replaces the selected probe. No pretraining is re-run. If a re-run
   does not reproduce, that seed's final-step row is reported as unavailable, with the mismatch.

The criterion, the random-init re-training under G3's cadence, and "report and stop" are unchanged.

### Outcome of the F3 addendum, 2026-09-18 -- PASS on all three seeds; the effect is a quarter to a half of the base rate

`faultline model seed-replication` (`configs/train/seed_replication_v0.yaml`, hash `424c4f33`;
`reports/data/seed_replication_v0_20260917.md` and `.json`, git_sha `92ee875`) pretrained
`tel_only` at S2 on seeds 2 and 3, probed both under §a at G3's cadence, re-trained the three §a
random-init probes under that same cadence, and computed the nine paired intervals.

**1. Verdict: PASS on all three trained seeds.** Every one of the nine paired block-bootstrap 95%
intervals of ΔAUPRC -- 10,000 replicates, seed 20260916, blocks of 288 steps within each shard,
both models scored on the identical resampled rows of the pooled Kelmarsh + Penmanshiel stride-12
split -- has a lower bound strictly above zero.

| trained seed | Δ vs random 1 | Δ vs random 2 | Δ vs random 3 | verdict |
| --- | --- | --- | --- | --- |
| 1 | +0.0124 [+0.0084, +0.0175] | +0.0130 [+0.0084, +0.0187] | +0.0149 [+0.0104, +0.0208] | PASS |
| 2 | +0.0160 [+0.0115, +0.0225] | +0.0166 [+0.0114, +0.0238] | +0.0186 [+0.0134, +0.0259] | PASS |
| 3 | +0.0092 [+0.0045, +0.0148] | +0.0098 [+0.0051, +0.0153] | +0.0118 [+0.0072, +0.0174] | PASS |

The lowest lower bound across the nine cells is **+0.0045** (seed 3 against random 1). The
pretraining effect is **+0.009 to +0.019 AUPRC**, against a pooled test base rate of 0.0388:
**a quarter to a half of the base rate**. ADR-0024's criterion is met for each trained seed, and
G1's single-seed pass is not a seed artefact.

**2. The bag-of-tokens parity replicates on three seeds.** Paired Δ at stride 12 against the §6
comparator, read from its saved scores:

| trained seed | Δ vs bag of tokens |
| --- | --- |
| 1 | +0.0016 [-0.0059, +0.0084] |
| 2 | +0.0053 [-0.0017, +0.0128] |
| 3 | -0.0015 [-0.0094, +0.0053] |

Every interval spans zero and the point estimate changes sign across seeds. **The pretrained
sequence model does not measurably beat a classifier that ignores token order.**

**3. The seed spread, read beside one seed's own interval.** Pooled stride-12 AUPRC across the
three trained seeds runs **0.0508 to 0.0576, a spread of 0.0068**, against a half-width of about
**0.007** on a single seed's block interval (seed 1: 0.0540 [0.0474, 0.0618]). Seed-to-seed
variation is the size of the sampling interval it sits inside, which is why arm comparisons are
paired and three-seeded. **Differences resolvable at this budget are of order 0.005.**

**4. Hill of Towie (reported, deciding nothing).** On the 12,000-window subsample, base rate
0.03325:

| seed | AUPRC | 95% block interval | lower bound above 0.03325 |
| --- | --- | --- | --- |
| 1 | 0.0390 | [0.0304, 0.0548] | no |
| 2 | 0.0510 | [0.0371, 0.0741] | yes |
| 3 | 0.0359 | [0.0276, 0.0508] | no |

The site clears on **one seed of three**. Under ADR-0022's two-of-three rule it is **NOT
EVALUABLE** -- the same verdict ADR-0021 reached on one seed. **The demotion stands and is not
reopened.** The site is marginal, not null.

**5. ADR-0019 F2 per trained seed.** On the same balanced draw (seed 20260917, 16,000 windows),
the mean predicted rates are **0.4876, 0.4900 and 0.5101**, all inside the [0.45, 0.55] band. The
declared π_train stands for every seed; no correction changes.

**6. Calibration on the 2021 validation split (report §3).** Each seed's selected probe, scored on
`kelmarsh__val` + `penmanshiel__val` at stride 12 (85,529 windows):

| seed | val corrected mean | val base rate | training natural rate | test corrected mean | test base rate |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.0185 | 0.0211 | 0.0221 | 0.0176 | 0.0388 |
| 2 | 0.0183 | 0.0211 | 0.0221 | 0.0173 | 0.0388 |
| 3 | 0.0217 | 0.0211 | 0.0221 | 0.0189 | 0.0388 |

**Two of the three seeds under-read in-time**, on a split the correction targets. The residual
under-read is therefore **a property of the probe, and is not attributable to the 2022-2024 shift
alone** -- which is the reading this measurement was registered to separate. Separately, the test
base rate is **1.8x the training natural rate** (0.0388 against 0.0221). That is the ADR-0009
shift, **recorded as such, not a correction error**.

**7. The selection split and an interval on selection AUPRC (report §4).** The split holds
**6,000 windows, 117 positive, 78 of 2,789 occupied 48-hour blocks holding a positive**.

| seed | selected step | selection AUPRC | 95% block interval |
| --- | --- | --- | --- |
| 1 | 200 | 0.0471 | [0.0289, 0.0902] |
| 2 | 1,000 | 0.0382 | [0.0255, 0.0607] |
| 3 | 700 | 0.0382 | [0.0243, 0.0708] |

**The untrained head's 0.0447 lies inside all three intervals.** Validation-AUPRC selection cannot
rank checkpoints on this split.

**8. Selected against final-step checkpoints (report §5).** Pooled stride-12 test AUPRC:

| probe | selected (val AUPRC) | selected test AUPRC | final (val AUPRC) | final test AUPRC | note |
| --- | --- | --- | --- | --- | --- |
| trained seed 1 | step 200 (0.0471) | 0.0540 [0.0474, 0.0618] | step 1,000 (0.0399) | 0.0580 [0.0505, 0.0672] | recovered by a seeded re-run that reproduced |
| trained seed 2 | step 1,000 (0.0382) | 0.0576 [0.0503, 0.0670] | step 1,000 (0.0382) | 0.0576 [0.0503, 0.0670] | selected the last step |
| trained seed 3 | step 700 (0.0382) | 0.0508 [0.0447, 0.0580] | step 1,000 (0.0373) | 0.0515 [0.0453, 0.0586] | recovered by a seeded re-run that reproduced |
| random seed 1 | step 1,000 (0.0290) | 0.0416 [0.0370, 0.0467] | step 1,000 (0.0290) | 0.0416 [0.0370, 0.0467] | selected the last step |
| random seed 2 | step 300 (0.0220) | 0.0410 [0.0368, 0.0458] | step 1,000 (0.0210) | 0.0419 [0.0374, 0.0468] | recovered by a seeded re-run that reproduced |
| random seed 3 | step 225 (0.0282) | 0.0390 [0.0351, 0.0433] | step 1,000 (0.0275) | 0.0418 [0.0371, 0.0470] | recovered by a seeded re-run that reproduced |

**The final step is never worse than the selected one, on either side of the comparison.** Whether
the arm runs use selected-step or fixed-final-step selection **is decided in the ADR-0022
addendum**, written next, under the criterion registered there. Nothing is decided here.

**9. Provenance.** Two complete F3 invocations exist, and the second superseded the first in place.

- **First run, 19:17:49-21:57:37 KST on 2026-09-17 (2.66 h),
  `checkpoints/logs/seed_replication_v0_20260917.log`.** It ran on pre-`b2ad4a7` code -- the F3
  addendum as first registered in `0d6d6b4` (19:15:09) -- and carried out both pretrainings, all
  six probes and the nine paired intervals, reaching the same three PASS verdicts and the same
  lowest lower bound of +0.0045. **Its report had no §3, §4 or §5**, because the three additions
  that produce them were registered at 20:09:09 in `b2ad4a7`, while it was still running.
- **An aborted resume, PID 19056, 20:15:17-20:16:07 KST.** Launched on the `b2ad4a7` code while
  the first run still held the checkpoints directory. It logged two lines, began re-running
  trained seed 1's probe stage, wrote no result and stopped. It is recorded because it rewrote
  `S2_trained_seed1_probe.json` at 20:15:19; the second run read that record and reproduced the
  selection it holds exactly (step 200, validation AUPRC 0.0471).
- **Second run, PID 22980, 21:58:03 KST on 2026-09-17 to 00:10:21 KST on 2026-09-18 (2.20 h),
  `checkpoints/logs/seed_replication_v0_20260917_215803.log`.** It ran on `b2ad4a7` code, read
  every saved backbone and selected probe rather than re-training any, and rewrote both report
  files in place with §3, §4 and §5. **It is the report this outcome reads.**
- **The four final states were recovered by seeded re-runs** (trained seeds 1 and 3, random seeds
  2 and 3). Each reproduced the saved selection -- step and validation AUPRC -- and matched the
  saved per-step training log row for row, which is the only condition under which the addendum
  admits them. No `_final_mismatch.txt` was written. Trained seed 2 and random seed 1 selected the
  last step, so their final state is their selected state.
- **Total F3 GPU wall clock: 2.66 h + 2.20 h.** No pretraining was run twice.

**10. Pretraining, seeds 2 and 3 (recorded, no claim).** Selected validation loss **3.2764 at step
763** (seed 2) and **3.3158 at step 762** (seed 3), against seed 1's **3.317** from the ADR-0021
gate run. The three sit within 0.04 of each other. Nothing is claimed from this: LM validation
loss is not a quantity any criterion in this record reads.

---

## ADR-0025 H1: the joint arm against `tel_only`, forward-in-time on the training sites

**Status:** Accepted; **registered 2026-09-18, before any F6 arm code, shard, pretraining or probe
exists** · **Date:** 2026-09-18.
**Commit:** this record, `configs/train/joint_v1.yaml`, `configs/train/h1_arms_v0.yaml`,
`configs/eval/h1_gate_v0.yaml`, their configuration classes and their test were committed together
in **`3e29202`**, before any code that builds, trains or scores the joint arm existed. The hash is
recorded here by the commit after it. **Nothing in this record authorises a run** (§8).

**Sources of every count.** Unless a line says otherwise, every count comes from the F6-R
reconnaissance of 2026-09-18 at `0bcbd01`, `checkpoints/scratch/f6_recon_20260918.md`
(git-ignored), cited below as *recon* with its section. The recon re-derived the builder's
attachment rule and checked it element-wise against every `tel_status_normalized/*.bin` file: step
counts, message counts, per-step message counts and total tokens all matched (recon, preamble).

### 0. What H1 now claims

From ADR-0022 §0: pretraining moves the frozen §a probe above random init on three seeds, but **the
probe is at parity with a bag-of-tokens classifier on all three** (ADR-0024 G2: Δ probe − bag
+0.0016, +0.0053, −0.0015, every interval spanning zero). **H1 therefore claims that the text
pathway carries signal the telemetry tokens do not. It does not claim that the sequence model's
representation helps.** This record tests that claim and nothing more. A supported H1 says the
joint arm's input and pretraining add risk signal over `tel_only` on the same windows. It does not
say why.

### 1. Arms

| arm | status | mixture (joint_v1.yaml) | seeds | tokens | rung, optimiser |
| --- | --- | --- | --- | --- | --- |
| `tel_only` | **exists**: three seeds, final-step probes, read in ADR-0024 F3 | tel 1.0 | 1, 2, 3 | 50,003,968 | S2, gate run |
| `joint` | **to be built** | tel 0.30 · txt 0.20 · tel+status 0.50, `status_convention: normalized` | 1, 2, 3 | 50,003,968 | S2, gate run |

- **Budget.** Both arms see 50,003,968 tokens: `tokens: 50000000` rounded up to whole optimiser
  steps, 763 × (4 × 8) windows × 2,048 (recon Q3a; ADR-0021 erratum). At joint_v1's ratio the txt
  share is 0.996 passes over its 10,043,874 train tokens (joint_v0.yaml header), so the joint arm
  sees narrative once.
- **Optimiser and schedule** are the gate run's (`configs/train/gate_check_v0.yaml`): 4 windows ×
  8 accumulation, peak learning rate 6e-4, 6 evaluations, 500 selection windows per source. The
  runner configuration restates them and the test asserts that they are equal.
- **`tel_only` is not re-run.** Its final-step pooled stride-12 AUPRCs are 0.0580 (seed 1), 0.0576
  (seed 2) and 0.0515 (seed 3) (ADR-0022 addendum outcome table). Its saved final-step scores are
  the reference side of every Δ.
- **`txt_only` is neither pretrained nor probed.** Three recon facts decide it:
  1. The only text stream a `txt_only` arm could pretrain on is `txt`. It holds NRC and PHMSA
     narrative with **no wind status strings**. At 50,000,000 tokens that is **4.98 passes** over
     its train tokens (recon Q3b, Q1d (i)). The probe would read strings the backbone never saw.
  2. A status-only probe input is **empty for 39,215 of 137,025 H1-split windows and 1,088 of 5,312
     positives** (recon Q1d). A decoder cannot read an empty sequence.
  3. **Presence alone is a label-correlated feature:** the base rate is 4.32% on non-empty windows
     and 2.77% on empty ones (recon Q1d). Any stand-in token for "empty" would carry that split.

  The text-only baseline is control (ii) of §4, which handles an empty window as a zero histogram.
- **Deferred to F7, conditional on H1 not being refuted here:** `joint_status_raw` (ADR-0017's
  convention ablation) and a `joint_no_txt` ablation (no narrative stream, to separate narrative
  from status strings). Neither is in joint_v1.

### 2. The joint arm's probe window

**No probe window exists for the tel+status stream today.** The stream has no 144-step framing, no
window index and no labels. Every probe reads M1's 1,872-token telemetry-only windows, and
`open_probe_inputs` refuses any arm other than `{tel: 1.0}` (recon Q1a, Q3a). With 144 steps and
their messages, **44,864 of 137,025 H1-split windows (32.7%) exceed 2,048 tokens, and so do 2,081
of 5,312 positives (39.2%)** (recon Q1c). `TelemetryDecoder.forward` raises above 2,048 tokens
(recon Q3c). The rule:

> A joint probe window ends at step t's last token (the M1 window's end step, same label
> narrow_within_24h) and holds the tel+status stream (every status row — no exclusion) back from t.
> Whole leading steps, with their attached messages, are dropped until the window holds at most
> 2,048 tokens; the window therefore always begins at a <sep>. If step t's own messages plus the
> step exceed 2,048, the window is the last 2,048 tokens and is counted as head-cut. The number of
> telemetry steps retained is recorded per window. Windows are right-padded to 2,048 with <pad>;
> attention is causal; the probe reads the hidden state at the last real index.

**Name:** `tail_anchored_2048`. The rule is read as follows, fixed here:

- **"Back from t" starts at the M1 window's first step, t − 143.** A joint window holds at most the
  M1 window's 144 steps, and fewer when messages displace leading steps. There are two reasons.
  The M1 index guarantees only that `[t − 143, t]` lies inside one contiguous run. The 32.7% above
  was also measured on exactly that framing (recon Q1c). A joint window never reaches further back
  than `tel_only`'s window does.
- **Step t's messages are in the window.** Every message attached to step t started at or before t,
  because attachment ceils a message's start to the grid (recon Q2a). Nothing after t enters.
- **"Last real index"** is the window's last non-`<pad>` position. The current `RiskModel` `last`
  pooling reads `hidden[:, -1]`, which is a pad under right-padding (recon Q3c). F6-1b changes how
  the index is read. The rule does not change.
- **Recorded per window:** telemetry steps retained, status tokens and the head-cut flag. The
  head-cut count is reported. F6-R did not measure it.

**The window index must reproduce M1's exactly.** The index for the tel+status stream is keyed by
the same (turbine, year, end step) as M1's, with the same labels and the same counts:

| split | stride | windows | positives | source |
| --- | ---: | ---: | ---: | --- |
| test (Kelmarsh + Penmanshiel) | 12 | 137,025 | 5,312 | recon preamble, Q1c; `axis_gate_v0.yaml` |
| train (Kelmarsh + Penmanshiel) | 6 | 749,387 | 16,524 | recon preamble, Q1c (247,463 + 501,924; 3,907 + 12,617) |
| selection (`kelmarsh__val` + `penmanshiel__val`) | 1 | 6,000 | as drawn | drawn as F3 drew them: `build_split(telemetry, "val", 3000, stride 1, seed 20260912)` (ADR-0024 §5) |

**A test asserts these before any probe is trained.** Only the framing of each window changes.
`tel_only` keeps its 1,872-token window and its existing final-step scores.

### 3. Leakage, decided

The recon measured leakage on the Kelmarsh and Penmanshiel test splits (strides 12 and 1) and train
splits (strides 6 and 1) (recon Q2b, Q2c):

> **Zero** messages starting at or after the labelled event's onset are in any window, in every row
> of both tables. "Carries event's own code", "… as a Stop row" and own message text are equal in
> every cell: **every own-code occurrence is an earlier Stop row**, i.e. recurrence. At stride 12 on
> test that is 1,060 of 2,841 Kelmarsh positives and 418 of 2,471 Penmanshiel positives, tracking
> "another narrow event started inside the window" (1,097 and 565).

Read-through is structurally impossible. The label counts only events starting strictly after t.
Event starts are floored to the grid, and messages are ceiled onto it (recon Q2a).

**Ruling.** Recurrence is information available at t, and the telemetry shows every earlier stop to
every arm, `tel_only` included. **The primary read uses every status row (R0).**

**Registered decompositions.** Both are reported only and decide nothing (§5).

- **R2.** Every provider `Stop` row is removed from the probe windows, and pretraining is
  unchanged. Each seed's R0 joint probe, not retrained, is scored on the R2 test windows. These are
  framed by the §2 rule applied to the stream with those rows deleted. R2 removes every own-code
  occurrence that was measured (recon Q2d). Under R2 the H1 split still has 1,088 status-empty
  positives, the same as R0 (recon Q2d).
- **Strata.** AUPRC of both arms, and the paired Δ, within the **has-status** and **no-status**
  strata of the R0 windows as framed by §2. The recon's 97,810 / 39,215 split (recon Q1d) uses the
  144-step framing. The §2 framing can empty a window whose only messages sat in dropped steps, so
  F6-1b counts the strata again and reports them.

**A caveat carried on every H1 row.** Message volume differs between train and test. Kelmarsh
positives average **67.2 status tokens in train (stride 6) and 190.1 in test (stride 12)** (recon
Q1c). The share of Kelmarsh positives carrying a technical Stop row is 9.2% in train (stride 6) and
38.5% in test (stride 12) (recon Q2c). The joint probe learns on the train mix and is scored on the
test mix.

### 4. Controls: reported, not gating

All run on §2's exact windows unless a line says otherwise.

- **(i) Bag-of-tokens on tel+status.** ADR-0024 §6's comparator is refit over the full 33,952-id
  vocabulary on the §2 windows. Its features are the counts of every real (non-`<pad>`) id,
  divided by the window's retained telemetry steps. It is trained by the same recipe: balanced
  sampler, the telemetry_v1 probe stage, seed 1, CPU. Compared with the existing bag-of-tokens on
  `tel` (ADR-0024 §6), it asks **whether status carries order-blind signal**. The runner hard-wires
  the 1,184-id M1 vocabulary today (recon Q3d); F6-1b changes that.
- **(ii) Bag-of-tokens over the status region only.** Ids ≥ 1,184 plus `<txt>` (4) and `</txt>`
  (5), with the same divisor and recipe. **An empty window is a zero histogram**, so for an empty
  window the classifier reads only its bias. **This is the text-only baseline** that replaces
  `txt_only` (§1).
- **(iii) `tel_only` backbones probed on the joint windows.** For each seed, a new §a probe is
  trained on the frozen `tel_only` final-step backbone under the G3 cadence (1,000 steps, 20
  measurements), read at its final step and scored on the §2 windows. **What this control can
  see:** in `tel_only` the 32,768 text embedding rows were trained only through the tied output
  head, and they have **collapsed onto one shared vector**. On seed 2 the text-row norm is 1.695 ±
  0.011, and the norm of their mean vector is 1.675 (recon Q3c). This control therefore sees
  **text presence and amount**, not string identity, plus the same truncated telemetry the joint
  arm sees.
  - **Δ(joint − iii)** isolates joint pretraining at identical input.
  - **Δ(iii − tel_only)** isolates the input change: truncation plus text presence, on a backbone
    that never read text.

**There is no random-init joint control.** H1 compares two pretrained arms. It does not compare a
backbone with the absence of one. Whether the tokens alone carry the signal is (i)'s question,
answered order-blind at no GPU cost. ADR-0024 already established that the probe moves off random
init at this rung.

### 5. The H1 rule

> Same-seed paired Δ = AUPRC(joint) − AUPRC(tel_only), pooled Kelmarsh + Penmanshiel stride-12
> forward-in-time test split, paired block bootstrap as ADR-0024 (two-day blocks, 10,000
> replicates, seed 20260916, discard rule 1%), final-step probes, R0 windows. Smallest effect of
> interest: 0.005 AUPRC. H1 is SUPPORTED if all three paired lower bounds exceed zero and the
> median Δ exceeds 0.005; REFUTED if all three paired upper bounds are below 0.005; otherwise
> INCONCLUSIVE at this budget, reported as such. The verdict is read on R0 only; R2, strata and
> controls are reported beside it and decide nothing.

The rule is read as follows, fixed here:

- **Pairing.** Seed k of `joint` is paired with seed k of `tel_only`. A joint window and a
  `tel_only` window with the same (turbine, year, end step) are one row, so both scores sit on the
  same drawn rows in every replicate (§2 guarantees that the keys match). A block is a window's end
  step // 288 within its shard, as in ADR-0024 §2.
- **The median Δ** is the median of the three seeds' full-sample point estimates.
- **A comparison whose discard share exceeds 1% is untrusted.** Its bounds count as neither above
  zero nor below 0.005, so it cannot contribute to SUPPORTED or REFUTED.
- **Why 0.005.** On this split the seed spread is 0.0068 and one seed's interval half-width is
  0.0072. Paired three-seed comparisons can therefore resolve differences of order 0.005 at best
  (ADR-0022 §0).

**Any outcome the three clauses do not name is reported as measured, and no clause is added
afterwards.** One such case is SUPPORTED and REFUTED holding together. That can happen only if a
point Δ lies outside its own percentile interval.

### 6. H2 in F6: reported only

This section measures the joint arm under modality loss, **forward in time at the same sites. It
is never a site-shift result** (ADR-0022 F6-0 outcome: the project has no evaluable shift axis).

- **Text withheld.** Each seed's R0 joint probe, not retrained, is scored through the joint
  backbone on `tel_only`'s **1,872-token M1 windows**, with the same keys and labels. **This is a
  different window from §2** (144 full steps, no messages, no truncation), and it is reported as
  such.
- **Channel loss.** The three F6-0a CARE-farm masks (`configs/eval/care_attribution_v0.yaml`,
  `masking.patterns`) are imposed as `<nan>` on the telemetry steps of §2's windows, with text
  present. They are reported beside the F6-0a `tel_only` masked rows, whose windows are the
  1,872-token ones.
- **Metric.** AUPRC with ADR-0024 intervals, paired against the unmasked joint read. **Coverage and
  selective risk are deferred until an abstention path exists. None exists today.** The only
  abstention code is `abstention_threshold` in `src/faultline/evaluation/calibration.py`, a
  confidence quantile that only its unit test calls. There is no risk-coverage curve, AURC or
  conformal procedure, and `configs/eval/selective_v0.yaml` is still listed as planned in
  `configs/eval/README.md`.

### 7. Cost

The table uses recon Q4's per-item rates, adjusted to three pretrainings. The factor
1.094 = 2,048 / 1,872 accounts for padding to 2,048.

| item | count | seconds each | seconds |
| --- | ---: | ---: | ---: |
| joint pretraining, 50,003,968 tokens (S2, 763 steps) | 3 | 609.9 | 1,829.7 |
| joint §a probes, G3 cadence | 3 | 447.2 × 1.094 | 1,467.7 |
| control (iii) probes | 3 | 447.2 × 1.094 | 1,467.7 |
| scorings, 137,025 windows (3 joint + 3 control (iii)) | 6 | 407.9 × 1.094 | 2,677.5 |
| **H1 verdict and control (iii)** | | | **7,442.6 s ≈ 2.1 GPU-h** |

Controls (i) and (ii) and the joint_v1 shard build (`faultline model mixture-shards`) run on CPU.
`tel_only` is not re-run or re-scored.

**Three items are not in the 2.1 h.** They are itemised here so that they are not discovered
later:

- **R2 scorings:** 3 × 407.9 × 1.094 = 1,338.7 s.
- **H2, text withheld:** 3 × 407.9 = 1,223.7 s.
- **H2, channel masks:** 9 × 407.9 × 1.094 = 4,016.2 s.

Together they add 6,578.6 s ≈ 1.8 GPU-h, for **≈ 3.9 GPU-h in all**. The pretraining rate is
`tel_only`'s. The joint data path does not exist yet, so that rate is assumed, not measured (recon
Q4). **The author launches the pretraining and probe runs. Claude Code prepares the commands and
reads the results.**

### 8. What this record does not authorise

**It does not authorise pretraining.** The order is below. Each step needs the user's
authorisation.

1. **F6-1b.** Code: the joint mixture sampler and pretraining path, the joint_v1 shards, the §2
   window index with its reproduction test, the padded probe with its last-real-index read, and
   the bag-of-tokens runner over 33,952 ids. The CPU controls (i) and (ii) are run in this step.
2. **F6-2.** Joint pretraining on three seeds, the joint probes and the control (iii) probes.
3. **F6-3.** Scoring, R2, strata, H2 rows and the H1 verdict under §5.

**Configurations.**

- `configs/train/joint_v1.yaml`: the mixture.
- `configs/train/h1_arms_v0.yaml`: the F6-2 runner.
- `configs/eval/h1_gate_v0.yaml`: this rule, by value.

joint_v1's shard directory `joint_v1_<hash>` does not exist until `mixture-shards` is re-run.

### Outcome of F6-3, 2026-09-19 -- H1 is INCONCLUSIVE at this budget

**Runs.**
- **Scoring.** `faultline model h1-score` ran on the GPU at `4cf68b9` from a clean tree, launched
  by the author. It made all 27 scorings in 3.33 GPU-hours, plus 4.0 min of selection re-checks
  and 0.7 min of validation loss. Every scoring was computed and none was resumed.
  `h1_scoring.py` sha256 is `5340406c…549d`.
- **Bootstrap and report.** `faultline model h1-gate` ran on the CPU in 15.1 min.
- **Report.** `reports/data/h1_gate_v0_20260919.md` and its `.json`, committed in `4e3008c`.
  Configuration `h1_gate_v0.yaml` has hash `a3f6606a`.

**Checks.** Every scoring covers F3's windows exactly: 137,025 windows, 5,312 positive, with the
same rows in the same order. All 12 probes' re-scored selection AUPRCs equal F6-2's records
exactly. Every mask overwrote exactly retained steps × channels telemetry slots, and no text
token. No interval discarded a replicate.

**B1 and the verdict.** Δ = AUPRC(joint) − AUPRC(`tel_only`), same seed, R0, final-step probes:

| seed | joint | `tel_only` | paired Δ [95%] |
| --- | --- | --- | --- |
| 1 | 0.0602 | 0.0580 | +0.0022 [-0.0034, +0.0068] |
| 2 | 0.0554 | 0.0576 | -0.0022 [-0.0084, +0.0021] |
| 3 | 0.0497 | 0.0515 | -0.0018 [-0.0060, +0.0021] |

The median Δ is **-0.0018**. No lower bound exceeds 0, so SUPPORTED fails. Seeds 2 and 3 have
upper bounds below 0.005, but seed 1's upper bound is 0.0068, so REFUTED fails too. **Under §5,
H1 is INCONCLUSIVE at this budget.** No comparison was untrusted. INCONCLUSIVE is a named
clause, so the "reported as measured" sentence does not apply. Nothing below changes the verdict.

**B2, decomposition through control (iii).**
- **What the input change costs.** Moving from the M1 window to the tail-anchored window with
  text, on a backbone that never read text, lowers AUPRC on every seed. Δ(iii − `tel_only`) is
  -0.0122, -0.0096 and -0.0076, and every interval lies below zero.
- **What joint pretraining adds at identical input.** Δ(joint − iii) is +0.0144, +0.0075 and
  +0.0059, and every interval lies above zero. Joint pretraining recovers roughly what the input
  change costs, and no more.

**B3, R2.** Removing every provider Stop row moves the joint read by -0.0028 [-0.0058, -0.0000]
on seed 1, and by -0.0001 and +0.0000 on seeds 2 and 3. The recurrence channel carries at most
about 0.003 AUPRC of the joint read, on one seed.

**B4, strata.** Δ(joint − `tel_only`) has no consistent sign in either stratum:
- **Has status (97,810 / 4,224):** +0.0020, -0.0034 and -0.0082. Only seed 3's interval excludes
  zero, and it is negative.
- **No status (39,215 / 1,088):** -0.0107, -0.0050 and +0.0085. Seeds 1 and 3 exclude zero, with
  opposite signs.

**B5, the first H2 rows. Reported only, forward in time at the same sites; never a site-shift
result.**
- **Text withheld.** The joint probe scored through the joint backbone on the 1,872-token M1
  windows reads 0.0558, 0.0543 and 0.0543. **This is a different window from the R0 and masked
  reads, and is not comparable with them. No paired Δ is given.**
- **Channel masks.** Each is imposed on the R0 windows with text present, and paired against the
  seed's R0 joint read:

  | farm | seed 1 | seed 2 | seed 3 |
  | --- | --- | --- | --- |
  | A | -0.0009 | **-0.0085** | -0.0001 |
  | B | -0.0026 | -0.0011 | +0.0014 |
  | C | +0.0011 | +0.0017 | **+0.0042** |

  Only the bold values have an interval that excludes zero.
- **Beside F6-0a.** F6-0a's `tel_only` masked rows, on their own 1,872-token windows, put farm C
  below its unmasked read on seeds 1 and 2. The joint arm does not repeat that.
- **Deferred.** Coverage and selective risk remain deferred (§6).

**B6, selected against final. Reported only.** Δ(final − selected), paired:

| probe | seed 1 | seed 2 | seed 3 |
| --- | --- | --- | --- |
| joint | +0.0009 [-0.0008, +0.0028] | **+0.0035** [+0.0014, +0.0052] | **+0.0033** [+0.0012, +0.0052] |
| control (iii) | -0.0010 | +0.0022 | +0.0024 [+0.0000, +0.0049] |

Joint seed 3's selection preferred step 200 over the final step by 0.022 validation AUPRC. On
test, its final read is nonetheless **above** its selected read, and the interval excludes zero.
The pre-written sentence applies only if seed 3's final read on test were below its selected read
by more than its paired interval, and it was not. **This is not evidence against the fixed-final
rule of ADR-0022's addendum.** Where the test favours either checkpoint, it favours the final one.

**Validation next-token loss, for the record.** Each backbone is read at its final pretraining
step. The tel+status windows are 500 per training site from `tel_status_normalized` val.

| seed | joint, tel+status val | joint, tel val | `tel_only`, tel val |
| --- | --- | --- | --- |
| 1 | 3.606 | 3.405 | 3.317 |
| 2 | 3.596 | 3.418 | 3.276 |
| 3 | 3.675 | 3.473 | 3.316 |

The joint arm's `tel` loss is 0.09 to 0.16 nats above `tel_only`'s on every seed. It spent 70%
of the same token budget on text-bearing streams.

**The two caveats, carried on every row.**
1. **Forward in time, same sites.** ADR-0009: a temporal hold-out with a change in what is
   labelled, not a drift test.
2. **Message volume.** Kelmarsh positives average 67.2 status tokens in train (stride 6) and
   190.1 in test (stride 12). The joint probe learns on the train mix and is scored on the test
   mix.

**What F7 is conditional on.** §1 defers `joint_status_raw` and `joint_no_txt` to F7,
"conditional on H1 not being refuted here". H1 was not refuted, so that condition is met, but
narrowly: two of the three seeds' upper bounds sit below 0.005. **F7 is not authorised by this
outcome.** It needs the user's authorisation. Whether it is worth its cost is a separate question:
- At this budget, B1 cannot resolve Δ from zero on any seed.
- B2 says the joint arm's pretraining gain is spent recovering the input change's cost.

---

## ADR-0026 F7': is the read-out the limit? Text-aware linear probes on the existing joint backbones

**Status:** Accepted; **registered 2026-09-20, before any read-out code, probe or scoring of it
exists** · **Date:** 2026-09-20.
**Commit:** this record, `configs/eval/readout_v0.yaml`, its configuration classes and their test
were committed together in **`319ae3b`**, before any code that builds, trains or scores a
text-aware read-out existed. The hash is recorded here by the commit after it. **Nothing in this
record authorises a run** (§6).

**This is a second pre-registered test of H1 with a changed instrument.** It is registered *after*
H1's INCONCLUSIVE result and after the three rows of §0 were seen. It is not a re-reading of the
H1 numbers and it adds no clause to ADR-0025 §5. H1's verdict stands as written; H1' below is a
separate hypothesis with its own rule, fixed here before any read-out is trained.

### 0. Why: three measured rows locate the reason H1 was inconclusive

H1 is INCONCLUSIVE. Same-seed paired Δ = AUPRC(joint) − AUPRC(`tel_only`) is **+0.0022
[−0.0034, +0.0068]**, **−0.0022 [−0.0084, +0.0021]** and **−0.0018 [−0.0060, +0.0021]** on seeds
1, 2 and 3; the median is **−0.0018** and the three upper bounds are **0.0068 / 0.0021 / 0.0021**
(`reports/data/h1_gate_v0_20260919.md`, B1). At this budget nothing separates the arms.

Three rows measured beside it say where the failure sits.

**(a) The status text carries risk signal.** Control (ii), the order-blind bag-of-tokens over the
status region only (ids ≥ 1,184 plus `<txt>`/`</txt>`, an empty window a zero histogram), scores
**0.0725 [0.0537, 0.0979]** on the same 137,025 stride-12 test windows
(`reports/data/h1_controls_v0_20260918.md`, §2, R0). Every probe of either arm sits between
**0.050 and 0.060**: joint 0.0602 / 0.0554 / 0.0497 and `tel_only` 0.0580 / 0.0576 / 0.0515
(h1_gate B1). A histogram of the strings, with no order and no model, is **above every probe**.
Within the has-status stratum the gap is wider still: control (ii) reads **0.0943
[0.0697, 0.1268]** against the tel bag's 0.0595 (h1_controls §3).

**(b) Adding the text to the window barely moves the last-position probe.** The joint backbone's
final-step probe reads **0.0558 / 0.0543 / 0.0543** with text withheld, on `tel_only`'s 1,872-token
M1 windows, and **0.0602 / 0.0554 / 0.0497** with the text present on the R0 tail-anchored windows
(h1_gate B5 and B1). Those are different windows and ADR-0025 §6 forbids pairing them, so no Δ is
claimed — but the two columns overlap seed for seed. Putting the text in front of the model changes
this read-out by roughly nothing, in either direction.

**(c) What joint pretraining buys is spent on the window, not on the text.** Control (iii) is
`tel_only`'s frozen backbone with a new §a probe on the joint windows. Δ(iii − `tel_only`), the
input change alone — truncation plus text presence on a backbone that never read text — is
**−0.0122 / −0.0096 / −0.0076**, every interval below zero. Δ(joint − iii), joint pretraining at
identical input, is **+0.0144 / +0.0075 / +0.0059**, every interval above zero (h1_gate B2). Joint
pretraining recovers about what the window change costs, and no more.

**The inference.** The registered read-out is a linear head on the hidden state at the **last real
position** of the window. Under ADR-0025 §2's `tail_anchored_2048` rule that position is the last
token of telemetry step *t* — a telemetry bin token, never a text token. Rows (a), (b) and (c)
together say that this read-out **does not harvest the text signal that row (a) proves is present
in the window**. What they do not say is whether the signal is absent from the backbone's
representation or merely absent from that one position. **That is the open question this record
tests, and the only one it tests.** A null here does not become a claim about the text pathway; it
becomes a claim about the pathway *and* every read-out named in §2.

### 1. Why not F7 as registered: `joint_status_raw` and `joint_no_txt` are withdrawn

ADR-0025 §1 defers two arms to F7 "conditional on H1 not being refuted here": `joint_status_raw`
(ADR-0017's convention ablation) and `joint_no_txt` (no narrative stream). That condition is met,
but only because seed 1's upper bound is **0.0068**; seeds 2 and 3 are both below 0.005.

Both arms vary **what the backbone is pretrained on** and read the result through the §a probe.
Section 0 says that probe does not read the text. Two arms that differ only in their text diet,
compared through an instrument that does not respond to text, return nulls that **cannot
discriminate between the arms and the instrument**. Their cost would buy a measurement whose
negative result is already explained.

**They are withdrawn from F7, not deferred.** Withdrawn is the honest word: deferring implies the
question is still queued, and it is not. **They may be revisited only if H1' below is SUPPORTED** —
that is, only once a read-out exists that demonstrably reads the text. If H1' is REFUTED, NOT
EVALUABLE or INCONCLUSIVE, they stay withdrawn and the record says so.

### 2. The read-outs, registered by name and definition

Three read-outs. Each is a **linear head** — the head in force, one hidden layer at the existing
head hidden width (`configs/model/ladder_v0.yaml`, `head_hidden: 1.0`, a hidden layer of
`d_model`), `RiskSpec` unchanged otherwise. Every probe is trained with **balanced sampling**, the
**G3 cadence** (`configs/train/probe_cadence_v0.yaml`: step 0, every 25 to 300, then every 100;
20 measurements in a 1,000-step probe), read at its **final step** under the fixed-final rule of
ADR-0022's addendum, on the **R0 tail-anchored windows of ADR-0025 §2**, with the **same optimiser
and learning rate as the §a probe** (`configs/train/telemetry_v1.yaml`, `risk.probe`: 2e-3,
16 windows × 2 accumulation, balanced at `positive_fraction` 0.5, under that file's optimiser
block).

Let `h` be the backbone's final hidden states over the window, of shape `(time, d_model)`; let a
position be **real** when its input id is not `<pad>`; let `L` be the index of the last real
position.

- **(a) `final_position`** — the probe in force. Head input `h[L]`, width `d_model`. **Reference
  only: no new run.** Its numbers are h1_gate B1's joint column and F3's `tel_only` column.
- **(b) `mean_all`** — head input the **mean of `h` over all real positions** of the window; pads
  are excluded from both the sum and the divisor. Width `d_model`. This is `RiskModel.pool`'s
  `mean` branch under `pad_id`, and it is ADR-0023 §b's pooling re-applied to a window that now
  holds text.
- **(d) `last_plus_text`** — head input the concatenation of three blocks, in this order:
  1. `h[L]`, the hidden state at the last real index — `d_model` values;
  2. the **mean of `h` over the window's text-token positions** — `d_model` values. A position is
     a text-token position when its input id is `<txt>` (4), `</txt>` (5), or **≥ 1,184** (the
     text block of the joint layout, ADR-0003). When the window holds no such position this block
     is the **zero vector**;
  3. a scalar **has-text indicator**: 1.0 when the window holds at least one text-token position,
     0.0 otherwise.

  Head input width is **2·`d_model` + 1**. On a window with no text the second block is zero and
  the third is a constant, so **(d) degrades to (a) plus a constant** — the read-out cannot be
  worse-posed than the one in force on the 39,215 status-empty windows.

There is no read-out (c). The letters name designs, not positions in a list, and (c) is ADR-0023's
two-hidden-layer head, which is not re-used here: **these are linear read-outs over a frozen
representation, and a deeper head would answer a different question** (ADR-0023 §c's reasoning,
unchanged).

**A unit test on a synthetic padded window asserts, before any GPU run:** that (b) excludes pad
positions from both numerator and denominator; that (d)'s text-mean block averages **exactly** the
text-token positions as defined above and is the zero vector for a window holding none; and that
(d)'s first block equals `RiskModel.pool`'s output under the `last` pooling with `pad_id` set.

### 3. Runs: twelve probes on saved backbones, nothing pretrained

Every backbone in this record **already exists on disk**. No arm is pretrained, no shard is built,
and `tel_only`'s and joint's saved backbones are read frozen.

| run | read-out | backbones | seeds | probes |
| --- | --- | --- | --- | ---: |
| `R-joint-b` | (b) `mean_all` | `joint` (F6-2) | 1, 2, 3 | 3 |
| `R-joint-d` | (d) `last_plus_text` | `joint` (F6-2) | 1, 2, 3 | 3 |
| `R-ctrl-d` | (d) `last_plus_text` | `tel_only` (F3), i.e. control (iii)'s backbones | 1, 2, 3 | 3 |
| `R-rand-d` | (d) `last_plus_text` | random-init S2, no optimiser step | init 1, 2, 3 | 3 |

All four run on the **same** ADR-0025 §2 R0 windows, at the same strides: probe training at stride
6 on the pooled Kelmarsh + Penmanshiel train index, selection on the probes' selection split
(`kelmarsh__val` + `penmanshiel__val`, 3,000 windows each, stride 1, seed 20260912), scoring on
the **137,025-window stride-12 pooled test split (5,312 positive)**.

`R-rand-d` is ADR-0023's random-init control re-applied to the new read-out: each backbone is the
S2 decoder as pretraining at that init seed constructs it, with **no optimiser step**, exactly as
`configs/train/probe_control_v0.yaml` constructs it. Only the read-out differs from §a.
**Which backbones, recorded by F7'-1:** the three saved under that configuration,
`checkpoints/probe_control_v0_00d2d3c0/S2_random_seed{1,2,3}_probe.pt`, whose spec is S2 at
`vocab_size` 33,952 and context 2,048 — reused rather than re-drawn, so the gate is read against
the backbones ADR-0023 probed; where such a file is absent the backbone is constructed fresh at
that init seed with the joint spec, which is the same construction, and the run record says which.

**Cost.** ADR-0025 §7's measured per-item rates, with the same 1.094 = 2,048 / 1,872 padding
factor:

| item | count | seconds each | seconds |
| --- | ---: | ---: | ---: |
| probes, G3 cadence | 12 | 447.2 × 1.094 | 5,870.9 |
| scorings, 137,025 windows | 12 | 407.9 × 1.094 | 5,354.9 |
| **F7' in all** | | | **11,225.8 s ≈ 3.1 GPU-h** |

**The author launches the runs, as in F6-2 and F6-3. Claude Code prepares the commands and reads
the results.** Each probe carries the two checks F6-3 ran: its **selection-split re-check** (the
re-scored selection AUPRC must equal the training run's record) and the **window-alignment check**
(the scored rows must be F3's windows exactly — 137,025 rows, 5,312 positive, the same rows in the
same order), both as `src/faultline/evaluation/h1_scoring.py` performs them.

### 4. The rules

**H1' — this decides.**

> Same-seed paired Δ = AUPRC((d) `last_plus_text` on the `joint` backbone) − AUPRC(`tel_only` under
> (a) `final_position`, its F3 final read), pooled Kelmarsh + Penmanshiel stride-12 forward-in-time
> test split, paired block bootstrap as ADR-0024 (two-day blocks of 288 steps, 10,000 replicates,
> seed 20260916, discard rule 1%), R0 windows of ADR-0025 §2, final-step probes. Smallest effect of
> interest: 0.005 AUPRC. H1' is SUPPORTED if all three paired lower bounds exceed zero and the
> median Δ exceeds 0.005; REFUTED if all three paired upper bounds are below 0.005; otherwise
> INCONCLUSIVE at this budget. A comparison discarding more than 1% of its replicates counts toward
> neither clause. Anything the clauses do not name is reported as measured, and no clause is added
> afterwards.

Read as follows, fixed here: pairing is seed *k* of the joint side with seed *k* of `tel_only`, on
identical (turbine, year, end step) rows in every replicate; a block is a window's end step // 288
within its shard; the median Δ is the median of the three full-sample point estimates. The
reference side is **unchanged from ADR-0025 §5** — the same saved `tel_only` final-step scores,
0.0580 / 0.0576 / 0.0515 — so H1 and H1' differ in the instrument on the joint side and in nothing
else.

**The random-init gate on the instrument — this must pass for H1' to be read at all.**

> (d) `last_plus_text` on the trained `joint` backbone must exceed (d) on every random-init
> backbone, **same-seed and cross-seed**: all **nine of nine** paired lower bounds strictly above
> zero, under ADR-0024's paired block bootstrap on the same windows.

If it fails, **H1' is NOT EVALUABLE**, and the sentence is written now so that it cannot be written
later: *whatever (d) harvests is the tokens' embeddings, not the pretraining — a bag of text
embeddings pushed through an untrained backbone already reads the status text.* In that case no Δ
from the H1' rule is reported as a verdict; the measured values are reported as measured.

**Reported beside the verdict, deciding nothing. Each carries its paired interval.**

> - **(d)-joint vs (d)-control**: `R-joint-d` against `R-ctrl-d`, same seed. Does joint pretraining
>   matter once the text has a direct path to the head?
> - **(b)-joint vs (a)-joint**: `R-joint-b` against h1_gate B1's joint column, same seed. What mean
>   pooling alone buys, with no text-specific block.
> - **(d)-joint vs the order-blind status-only classifier**: against control (ii)'s **0.0725
>   [0.0537, 0.0979]**, whose per-row scores already exist from F6-1b, paired on the identical
>   137,025 rows. **If a linear read of the SLM's text-position states cannot match a histogram of
>   the strings, the sequence model adds nothing over counting them.**
> - **(d)-joint strata**: AUPRC and paired Δ within the **has-status** and **no-status** strata of
>   the R0 windows, blocks re-formed within each stratum.
> - **Selected against final**, for every new probe, as h1_gate B6 reports it. The fixed-final rule
>   stays in force; nothing here changes which probe is read.

**Caveats carried on every row of every table**, in full, as h1_gate carries them: (1) **ADR-0009**
— the late split is a temporal hold-out with a change in what is labelled, not a drift test, and
every late-test result is reported both with and without the anemometer-defect events;
(2) **forward in time, same sites** — this is the in-distribution temporal test set; no row here is
a site-shift result; (3) **message-volume shift** — Kelmarsh positives average **67.2** status
tokens in train (stride 6) and **190.1** in test (stride 12), so every probe learns on the train
mix and is scored on the test mix.

### 5. Closure: the experimental programme ends with F7', whatever it returns

**Whatever F7' returns, this is the last experiment.** No further arm, read-out or axis is
registered after it. The record the dissertation is written against then holds:

1. **Two pre-registered site-shift negatives, with attribution.** Hill of Towie is NOT EVALUABLE
   under ADR-0021's gate, and CARE is not evaluable at chance under ADR-0022 (F5). The project has
   no evaluable shift axis, and F6-0 attributed farm A's null to transfer failure, with farms B and
   C unattributed.
2. **Telemetry bag-of-tokens parity on three seeds.** ADR-0024 G2: the frozen probe is at parity
   with an order-blind histogram of the telemetry tokens on every seed, every interval spanning
   zero.
3. **A measured text signal, and a measured answer to whether the SLM converts it.** Control (ii)
   reads 0.0725 on the status strings alone; H1 is INCONCLUSIVE through the last-position read-out;
   H1' says whether a text-aware linear read-out of the same backbones does better, and the
   random-init gate says whether any such gain is the pretraining or the embeddings.
4. **H2's first rows.** Text withheld and the three CARE-farm channel masks on the joint arm,
   forward in time at the same sites, reported and never a shift result. Coverage and selective
   risk remain deferred; no abstention path exists.

**The next step after F7' is the dissertation write-up against the committed record.** S3, the ONNX
export, the CPU demo and any further arm or ablation are **out of scope** unless the write-up needs
one for a specific sentence — in which case that sentence is named first and the run is registered
against it.

### 6. What this record does not authorise

**It does not authorise a run.** This commit holds the decision, the configuration and its
schema — no probe code, no read-out code, no scoring code. The order is:

1. **F7'-1.** Code: the three read-outs as pooling designs over the existing frozen backbones, the
   §2 unit test on a synthetic padded window, the runner over the four runs of §3, and the scoring
   path re-using `h1_scoring.py`'s checks.
2. **F7'-2.** The twelve probes and twelve scorings, author-launched.
3. **F7'-3.** The bootstrap, the random-init gate, the H1' verdict under §4, and the reported rows.

Each step needs the user's authorisation. **Configuration:** `configs/eval/readout_v0.yaml`, this
record's read-outs, runs, rule and gate by value.

### Outcome of F7'-3, 2026-09-20 -- the gate PASSES and H1' is SUPPORTED

**Runs.**
- **Probes and scorings.** `faultline model readout` ran on the GPU at `f945a11` from a clean
  tree, launched by the author. It made all 12 probes and all 12 scorings in **3.15 GPU-hours**
  (1.68 h of probes, 1.48 h of scorings), plus 3.9 min of selection re-checks. Every item was
  computed and none was resumed.
- **Bootstrap and report.** `faultline model readout-gate` ran on the CPU in 9.6 min. It trained
  nothing and scored nothing: every score file was read from disk. Its worker pool is capped for
  memory (each spawned worker re-imports the package); the per-job computation is F6-3's
  unchanged, and the cached replicate vectors are the ones an uncapped pool would write.
- **Report.** `reports/data/readout_v0_20260920.md` and its `.json`. Configuration
  `readout_v0.yaml` has hash `7c2765e7`; ADR-0026 was registered in `319ae3b` and its hash
  recorded by `ce0eb5a`.

**Checks.** All 19 scorers -- the twelve read-out scorings, `tel_only`'s three F3 final reads,
the joint arm's three F6-3 R0 reads and F6-1b's status-only classifier -- cover the same 137,025
windows, 5,312 positive, in the same order; the run was refused until they did. All 12 probes'
re-scored selection AUPRCs equal F7'-2's records exactly. No interval discarded a replicate. The
three random-init backbones are ADR-0023's saved ones, re-used rather than re-drawn.

**G, the random-init gate on the instrument. Computed before B1, and it decides whether H1' is
read at all.** Δ((d) on the trained `joint` backbone − (d) on a random-init backbone), all nine
(trained seed, init seed) pairs:

| (d) trained | vs init 1 | vs init 2 | vs init 3 |
| --- | --- | --- | --- |
| seed 1 (0.0780) | +0.0199 [+0.0128, +0.0290] | +0.0205 [+0.0128, +0.0301] | +0.0233 [+0.0156, +0.0329] |
| seed 2 (0.0810) | +0.0229 [+0.0160, +0.0313] | +0.0235 [+0.0166, +0.0318] | +0.0263 [+0.0187, +0.0354] |
| seed 3 (0.0685) | +0.0103 [+0.0058, +0.0152] | +0.0109 [+0.0064, +0.0158] | +0.0138 [+0.0090, +0.0187] |

The random-init backbones read 0.0581, 0.0575 and 0.0547 through the same read-out. **Nine of
nine paired lower bounds are strictly above zero; the weakest is +0.0058. The gate PASSES**, so
H1' is read. What (d) harvests is not only the tokens' embeddings: an untrained backbone pushed
through the same text-aware head reads the status text, but measurably less well than a
pretrained one, on every one of the nine pairs.

**B1 and the verdict.** Δ = AUPRC((d) `last_plus_text` on `joint`) − AUPRC(`tel_only` under (a)
`final_position`, its F3 final read), same seed, R0, final-step probes. The reference side is
ADR-0025 §5's, unchanged:

| seed | (d)-joint | `tel_only` (a) | paired Δ [95%] |
| --- | --- | --- | --- |
| 1 | 0.0780 | 0.0580 | +0.0200 [+0.0112, +0.0294] |
| 2 | 0.0810 | 0.0576 | +0.0234 [+0.0128, +0.0342] |
| 3 | 0.0685 | 0.0515 | +0.0170 [+0.0111, +0.0232] |

The median Δ is **+0.0200**. Every paired lower bound exceeds zero and the median exceeds the
smallest effect of interest, 0.005. **Under §4, H1' is SUPPORTED.** No comparison was untrusted.
ADR-0026 §0's open question is answered in the direction it left open: the text signal **is** in
the joint backbone's representation, and the last-position read-out registered under ADR-0025 --
not the pathway -- is what failed to reach it. H1's INCONCLUSIVE verdict stands as written; it
was a verdict about the arm read through that instrument, and this is a different instrument.

**B2, (d)-joint against (d)-control.** Joint pretraining still matters once the text has a direct
path to the head: Δ is **+0.0271 [+0.0196, +0.0366]**, **+0.0285 [+0.0199, +0.0386]** and
**+0.0267 [+0.0209, +0.0331]**, every interval above zero, against a `tel_only` backbone read
through the identical read-out (0.0509, 0.0526, 0.0418).

**B4, against the order-blind status-only classifier.** Δ((d)-joint − control (ii)'s 0.0725
[0.0537, 0.0979]) is **+0.0055 [-0.0173, +0.0241]**, **+0.0085 [-0.0141, +0.0265]** and
**-0.0040 [-0.0264, +0.0125]**: every interval spans zero. **A linear read of the SLM's
text-position states matches a histogram of the strings; it does not beat it.** Two seeds sit
above the comparator and one below, and at this budget the sequence model adds nothing
measurable over counting the strings -- ADR-0026 §4's sentence, read in the direction it names.

**B3, (b)-joint against (a)-joint.** Mean pooling alone, with no text-specific block, buys
-0.0026 [-0.0068, +0.0017], +0.0100 [+0.0051, +0.0164] and +0.0094 [+0.0054, +0.0142]: no
consistent sign, and well under (d)'s gain, so the text block and not the pooling change is what
moves the read-out.

**B5, strata.** The whole of H1's gain sits where the text is: Δ((d)-joint − `tel_only`) is
+0.0252 [+0.0158, +0.0357], +0.0260 [+0.0142, +0.0375] and +0.0145 [+0.0070, +0.0220] in the
has-status stratum (97,810 / 4,224, base rate 0.0432), and -0.0111, -0.0046 and +0.0083 in the
no-status stratum (39,215 / 1,088, base rate 0.0277), where the read-out degrades to (a) plus a
constant and no consistent sign survives.

**B7, for the record.** Δ((d)-control − (d)-random) is -0.0072 [-0.0125, -0.0022], -0.0050
[-0.0110, +0.0007] and -0.0129 [-0.0190, -0.0077]: a telemetry-only backbone's text rows --
collapsed, as F6-R found them -- read the status text **no better than an untrained backbone**,
and on two seeds measurably worse. Only the joint diet puts usable text structure in the
representation.

**B6, selected against final.** **No selected checkpoint was scored: this step scores nothing,
and ADR-0026 §2 registered the final step.** The validation-split values are reported for all
twelve probes from their records. The widest gaps are **R-joint-b seed 3, -0.0184** (selected
step 900, 0.0533; final step 1,000, 0.0350) and **R-ctrl-d seed 2, -0.0143** (selected 250,
0.0398; final 1,000, 0.0255). The fixed-final rule of ADR-0022's addendum stays in force and
reads the final step in both cases; the selected checkpoints are saved beside the final ones, so
any later re-run can score them, and test-split selected reads were not produced for F7'.

**Closure, now in force (§5).** **The experimental programme is closed.** F7' was the last
experiment, and no further arm, read-out or axis is registered after it. **The next step is the
dissertation write-up against the committed record.** S3, the ONNX export, the CPU demo and any
further arm or ablation stay out of scope unless the write-up needs one for a specific sentence,
in which case that sentence is named first and the run is registered against it.

**The §1 condition is met.** `joint_status_raw` and `joint_no_txt` were withdrawn from F7 because
they would have been read through an instrument that does not respond to text; §1 allows them to
be revisited **only if H1' is SUPPORTED**, and it is. A read-out that demonstrably reads the text
now exists. They are therefore revisitable -- but revisiting them is a **new registration**
against a named write-up sentence under §5, not an authorisation this record grants, and nothing
here schedules a run.

---

## ADR-0027 The two ablations: does the narrative corpus matter, and does status-string surface form matter, to the text signal read-out (d) harvests?

**Status:** Accepted; **registered 2026-09-23, before any F8 code, shard, pretraining, probe or
scoring exists** · **Date:** 2026-09-23.
**Commit:** this record, `configs/train/joint_v2.yaml`, `configs/train/ablation_arms_v0.yaml`,
`configs/eval/ablation_gate_v0.yaml`, their configuration classes and their tests were committed
together in **`179d769`**, before any code that builds, trains or scores an ablation arm existed.
The hash is recorded here by the commit after it. **Nothing in this record authorises a run** (§7).

**Sources of every count.** The two ablation arms' realised token counts come from
`mixture_schedule` read on this record's configuration, at the budget of ADR-0025 §1. The window
counts come from a read-only pass over the joint_v1 shard directory made on 2026-09-23 before this
record was written, cited below as *the F8 read-only check*. Everything else is cited to the record
it comes from.

### 0. Why now: ADR-0026 withdrew these arms, and its outcome admits them back

ADR-0026 §1 withdrew both arms, in these words:

> **They are withdrawn from F7, not deferred.** Withdrawn is the honest word: deferring implies the
> question is still queued, and it is not. **They may be revisited only if H1' below is
> SUPPORTED** — that is, only once a read-out exists that demonstrably reads the text. If H1' is
> REFUTED, NOT EVALUABLE or INCONCLUSIVE, they stay withdrawn and the record says so.

ADR-0026's outcome of 2026-09-20, in which the instrument gate passed nine of nine and H1' was
SUPPORTED, admits them back under a condition:

> **The §1 condition is met.** `joint_status_raw` and `joint_no_txt` were withdrawn from F7 because
> they would have been read through an instrument that does not respond to text; §1 allows them to
> be revisited **only if H1' is SUPPORTED**, and it is. A read-out that demonstrably reads the text
> now exists. They are therefore revisitable -- but revisiting them is a **new registration**
> against a named write-up sentence under §5, not an authorisation this record grants, and nothing
> here schedules a run.

**This record is that new registration.** ADR-0026 §5 closed the experimental programme and allows
a further run only where "the write-up needs one for a specific sentence — in which case that
sentence is named first and the run is registered against it". §1 below names the two sentences
before any arm exists. The read-out is (d) `last_plus_text`, the one ADR-0026's gate showed reads
the text, and it is fixed here; §1's rationale — that an instrument which cannot read the text
cannot discriminate between backbones that differ in their text — is what makes (d) and no other
read-out admissible for these two arms.

### 1. The two write-up sentences each ablation is registered to decide

Each sentence is written now, with its alternative in brackets, and F8-3 strikes one bracket. No
other sentence is decided by this record, and no sentence is added to it afterwards.

- **`joint_no_txt`** decides: *"The unpaired narrative corpus [does / does not measurably]
  contribute to the text signal the joint model's read-out harvests."*
- **`joint_status_raw`** decides: *"Normalising status strings to prose surface form (H3')
  [does / does not measurably] matter to the joint model's risk read-out."*

Both sentences are about **the text signal read-out (d) harvests**, not about the text pathway in
general. That is the only claim the instrument supports, and §5's mapping keeps the verdict inside
it.

### 2. Arms, by value, in a new `configs/train/joint_v2.yaml`

**Why a new version.** joint_v1.yaml is frozen: F6-2 pretrained against it, F6-3 and F7' scored
against it, and `open_probe_inputs` derives the shard directory from its `config_hash`. A
configuration read by a run is never edited, so a changed arm set is a new version. joint_v2 adds
two arms and changes nothing else — the same tokenizer configurations, the same sources, the same
2,048-token context, the same 6-step stride and the same 50,000,000-token budget.

| arm | role | mixture | convention | seeds | tokens |
| --- | --- | --- | --- | --- | ---: |
| `joint` | reference | tel 0.30 · txt 0.20 · tel+status 0.50 | normalized | 1, 2, 3 | 50,003,968 |
| `joint_status_raw` | ablation | tel 0.30 · txt 0.20 · tel+status 0.50 | **raw** | 1, 2, 3 | 50,003,968 |
| `joint_no_txt` | ablation | tel 0.50 · tel+status 0.50 | normalized | 1, 2, 3 | 50,003,968 |

**`joint` is not retrained.** It is the existing F6-2 backbones, carried into joint_v2 with the
mixture it was pretrained under, unchanged value for value. It is the reference side of every Δ in
§5, and it is listed here so that the arm set is complete and the raw arm has the normalized twin
the mixture schema requires.

**The re-weighting rationale, recorded verbatim.** The 0.20 narrative share **goes to plain
telemetry, not proportionally**, so that paired tel+status exposure stays exactly **25,001,984
tokens** as in `joint` — proportional renormalisation would raise it to **~31.25M** and confound
removing the narrative with adding status, the stream H1''s effect comes from. Telemetry is the
filler because its marginal value was measured small (ADR-0024 bag-of-tokens parity).

The arithmetic: proportional renormalisation is tel 0.30/0.80 = 0.375 and tel+status 0.50/0.80 =
0.625, which at 24,416 windows is 15,260 tel+status windows and **31,252,480** tel+status tokens,
6,250,496 more than `joint` sees. The registered re-weighting holds tel+status at 0.50 exactly.

**The realised token counts the sampler must hit per stream**, from `mixture_schedule` at 24,416
windows of 2,048 tokens (763 optimiser steps × 4 windows × 8 accumulation; ADR-0021 erratum):

| arm | tel | txt | tel+status | total |
| --- | ---: | ---: | ---: | ---: |
| `joint` and `joint_status_raw` | 7,325 windows, 15,001,600 | 4,883 windows, 10,000,384 | **12,208 windows, 25,001,984** | 24,416 windows, 50,003,968 |
| `joint_no_txt` | 12,208 windows, 25,001,984 | — | **12,208 windows, 25,001,984** | 24,416 windows, 50,003,968 |

The tel+status column is identical across all three arms, by construction and to the token. A test
asserts it before any arm is pretrained.

**Everything else is `joint`'s**: rung **S2**, **50,003,968 tokens**, **seeds 1, 2, 3**, and the
gate run's optimiser and schedule value for value (`configs/train/gate_check_v0.yaml`: 4 windows ×
8 accumulation, peak learning rate 6e-4, 6 evaluations, 500 selection windows per source), with the
**initial-loss guard** the pretraining path already imposes. The runner configuration restates them
and its test refuses any difference.

### 3. Probe and windows

**The read-out is (d) `last_plus_text`, exactly as ADR-0026 §2 defines it**: head input the
concatenation of the hidden state at the last real index, the mean of the hidden states over the
window's text-token positions (ids `<txt>` 4, `</txt>` 5, or ≥ 1,184; the zero vector when the
window holds none), and a scalar has-text indicator, of width 2·`d_model` + 1. Probes are trained
with **balanced sampling**, the **G3 cadence** (`configs/train/probe_cadence_v0.yaml`), read at the
**final step** under ADR-0022's addendum, at the §a probe's own learning rate, on the R0
tail-anchored windows at the strides of ADR-0026 §3: training at stride 6 on the pooled train
index, selection on the 6,000-window selection split, scoring on the **137,025-window stride-12
pooled test split (5,312 positive)**.

**`joint_no_txt` probes the normalized R0 `tail_anchored_2048` windows — identical to `joint`'s.**
Its status convention is normalized, so its windows are the same bytes, the same framing and the
same rows as the ones F6-3 and F7' scored. Nothing is rebuilt for it.

**`joint_status_raw` probes the raw-cased windows built by the same rule.** The `tel_status_raw`
shards already exist in the joint_v1 shard directory alongside the normalized ones (they were built
in the same pass, `manifest.json`, `tel_status_variants: ["normalized", "raw"]`), and
`open_probe_inputs` already takes the convention from the arm, so the raw windows are the **same
index framed over a different stream**, not a new index.

The F8 read-only check measured both, and its findings are fixed here:

- **The streams' step and message structure is identical.** On every one of the seven shard keys
  the raw and normalized streams hold the **same step count, the same message count and
  element-wise equal per-step message counts**, and their runs tables carry identical
  turbine/year/segment/steps. Raw is longer only in the BPE ids of the strings: +59,842 tokens on
  `kelmarsh__test` and +46,312 on `penmanshiel__test`, for example.
- **The index keys, labels and counts are identical.** Framed over either stream, the stride-12
  test index carries the same (turbine, year, end step) keys, the same labels and the same years,
  and the counts are **137,025 windows / 5,312 positives** on both. The has-status and no-status
  strata are also identical at **97,810 / 4,224** and **39,215 / 1,088**.
- **The truncation differs, and this is the one thing the raw arm does not inherit.** Longer raw
  strings push more whole leading steps out of the 2,048-token budget: **41,371 of the 137,025
  windows (30.19%) retain a different number of telemetry steps**, of which **1,838 are positives
  (34.60% of all positives)**. The mean difference among those windows is 1.54 steps at Kelmarsh
  and 1.34 at Penmanshiel, with a maximum of 12 and 9. Real length differs on 92,443 windows and
  status-token count on 94,803. **No window is head-cut under either convention.**

So the raw arm is probed and scored on **its own windows**, framed by the same rule from the same
index, and the paired Δ of §5 pairs row for row on identical keys while the two sides see slightly
different amounts of telemetry. §8 carries that as a caveat on every raw row.

### 4. The instrument gate, per ablation, computed first

Computed before any Δ of §5, separately for each ablation, and it decides whether that ablation's
sentence is read at all:

> (d) on each ablation backbone must exceed (d) on every random-init backbone, same-seed and
> cross-seed, nine of nine paired lower bounds strictly above zero, ADR-0024's paired block
> bootstrap on the ablation's own windows. On FAIL that ablation is NOT EVALUABLE and its sentence
> is reported as undecided.

- **`joint_no_txt` reuses ADR-0026's three random-init (d) scores**, because it probes the same
  windows: the `R-rand-d` reads of 0.0581, 0.0575 and 0.0547. No random-init probe is trained for
  it.
- **`joint_status_raw` requires three new random-init (d) probes on the raw windows.** The
  backbones are the **same random-init backbones ADR-0026 used** —
  `checkpoints/probe_control_v0_00d2d3c0/S2_random_seed{1,2,3}_probe.pt`, reused rather than
  re-drawn — but the probe is trained and scored on the raw-cased windows, because a gate computed
  on different windows from the arm it gates is not a gate.

A gate FAIL is not a null result about the ablation. It says the instrument does not read the text
on that arm's windows, and the sentence stays undecided.

### 5. The primary rule, per ablation

> Same-seed paired Δ = AUPRC(ablation, (d)) − AUPRC(joint, (d)), pooled stride-12 forward-in-time
> split, paired block bootstrap as ADR-0024, final-step probes. Smallest effect of interest 0.005.
> HURTS if all three paired upper bounds are below zero and the median Δ is below −0.005. HELPS if
> all three lower bounds are above zero and the median exceeds +0.005. EQUIVALENT if all three
> paired intervals lie inside (−0.005, +0.005). Otherwise INCONCLUSIVE at this budget. A comparison
> discarding >1% counts toward none; anything the clauses do not name is reported as measured and
> no clause is added afterwards.

Read as follows, fixed here: pairing is seed *k* of the ablation with seed *k* of `joint`, on
identical (turbine, year, end step) rows in every replicate; the bootstrap is ADR-0024's, two-day
blocks of 288 steps, 10,000 replicates, seed 20260916, a block being a window's end step // 288
within its shard; the median Δ is the median of the three full-sample point estimates; the
reference side is `joint` read through **(d)**, that is ADR-0026's `R-joint-d` reads of 0.0780,
0.0810 and 0.0685, not `joint` under (a).

**Mapping to the sentences of §1.** HURTS → "does matter / does contribute". EQUIVALENT → "does not
measurably". HELPS → reported as measured, with the direction stated; neither bracket is struck,
because neither sentence was written to be read in that direction. INCONCLUSIVE → the sentence
stays undecided.

**Stated plainly, before the run: EQUIVALENT is very unlikely to be reachable at this budget.**
Paired Δ intervals in ADR-0026 were about **0.018 to 0.022 wide** — H1''s were [+0.0112, +0.0294],
[+0.0128, +0.0342] and [+0.0111, +0.0232] — and EQUIVALENT requires all three to fit inside a
0.010-wide band. **The most likely non-HURTS outcome of this record is INCONCLUSIVE**, and an
INCONCLUSIVE result is not evidence that a component does not matter. This paragraph is written
before any arm is pretrained so that it cannot be read as an excuse afterwards.

### 6. Reported, not gating

Each row carries its paired interval and the caveats of §8. None decides a sentence.

- **Each ablation (d) against `tel_only` (a)**, under ADR-0026's H1' rule applied unchanged, as a
  **replication of H1' with the component removed**. The reference side is ADR-0025 §5's saved
  `tel_only` final-step scores, 0.0580 / 0.0576 / 0.0515.
- **Each ablation (d) against the status-only order-blind classifier**, control (ii)'s **0.0725
  [0.0537, 0.0979]**, whose per-row scores exist from F6-1b, paired on the identical 137,025 rows.
  **For `joint_status_raw`: the order-blind classifier was fit on normalized strings. It is
  reported as-is and is not refit on raw.** The comparison is therefore between a raw-diet backbone
  and a normalized-string histogram, and the row says so wherever it appears.
- **The has-status and no-status strata** of each ablation's own windows, blocks re-formed within
  each stratum.
- **Selected against final validation values** for every new probe, as ADR-0026's outcome reports
  them. The fixed-final rule of ADR-0022's addendum stays in force and nothing here changes which
  checkpoint is read.

### 7. Cost, and the order of steps

Using ADR-0025 §7's measured per-item rates with the same 1.094 = 2,048 / 1,872 padding factor:

| item | count | seconds each | seconds |
| --- | ---: | ---: | ---: |
| ablation pretrainings, 50,003,968 tokens (S2, 763 steps) | 6 | 609.9 | 3,659.4 |
| ablation (d) probes, G3 cadence | 6 | 447.2 × 1.094 | 2,935.5 |
| new random-init (d) probes, on the raw windows | 3 | 447.2 × 1.094 | 1,467.7 |
| scorings, 137,025 windows | 9 | 407.9 × 1.094 | 4,015.8 |
| **F8 in all** | | | **12,078.4 s ≈ 3.4 GPU-h** |

Budgeted at **≈ 3.5 GPU-h**. `joint` is not retrained, not re-probed and not re-scored: its three
(d) reads are ADR-0026's.

**One CPU item is not in that table and is named here so it is not discovered later.** joint_v2 has
its own `config_hash`, so `open_probe_inputs` will look for a shard directory `joint_v2_<hash>`
that does not exist until `faultline model mixture-shards` is re-run for it (CPU). Nothing that
determines shard content changes between joint_v1 and joint_v2 — the same tokenizer configurations,
the same sources, the same segmentation — so the streams are expected to be byte-identical to
joint_v1's. **F8-1 checks that rather than assuming it**, against the byte counts recorded in the
F8 read-only check.

**The author launches the pretraining, probe and scoring runs, as in F6-2 and F7'-2**, via `nohup`
with timestamped logs. Claude Code prepares the commands and reads the results.

**The order. Each step needs the user's authorisation.**

1. **F8-1.** Code: the mixture sampler over the joint_v2 arms, the raw window index if the
   framing pass needs one, and the runner. CPU only.
2. **F8-2.** The six pretrainings, the nine probes and the nine scorings, author-launched.
3. **F8-3.** The two instrument gates, the two verdicts under §5, the reported rows of §6, and the
   two sentences of §1 with one bracket struck each.

**Configurations.** `configs/train/joint_v2.yaml` (the arms), `configs/train/ablation_arms_v0.yaml`
(the runner), `configs/eval/ablation_gate_v0.yaml` (the rule and the gate, by value).

### 8. Caveats carried on every row

In full, on every row of every table this record produces:

1. **ADR-0009** — the late split is a temporal hold-out with a change in what is labelled, not a
   drift test, and every late-test result is reported both with and without the anemometer-defect
   events.
2. **Forward in time, same sites** — this is the in-distribution temporal test set. No row here is
   a site-shift result.
3. **Message-volume shift** — Kelmarsh positives average **67.2** status tokens in train (stride 6)
   and **190.1** in test (stride 12), so every probe learns on the train mix and is scored on the
   test mix.
4. **For `joint_status_raw` only** — raw casing changes token counts and therefore truncation in
   the tail-anchored window: **41,371 of 137,025 windows (30.19%), and 1,838 of 5,312 positives,
   retain a different number of telemetry steps** than the normalized windows `joint` is scored on.
   The two sides pair row for row on identical keys, but they do not see identical telemetry.

### Outcome of F8-3, 2026-09-24 -- `joint_no_txt`: gate PASSES, INCONCLUSIVE; `joint_status_raw`: gate FAILS, NOT EVALUABLE

**Runs.**
- **Pretrainings, probes and scorings.** `faultline model ablation-arms` ran on the GPU at
  `ba6cade` from a clean tree, launched by the author. It made all 6 pretrainings, 9 probes and 9
  scorings in **3.37 GPU-hours** (1.02 h of pretraining, 1.24 h of probes, 1.11 h of scorings;
  §7 estimated 3.36 h). Every item was computed and none was resumed.
- **Bootstrap and report.** `faultline model ablation-gate` ran on the CPU in 10.4 min (37
  replicate vectors on F7'-3's memory-capped pool). It trained nothing and scored nothing: every
  score file was read from disk.
- **Report.** `reports/data/ablation_gate_v0_20260923.md` and its `.json`. Configuration hashes:
  `ablation_gate_v0.yaml` `da81bbef`, `ablation_arms_v0.yaml` `ecb0b16e`, `joint_v2.yaml`
  `d432c6d7`, `readout_v0.yaml` `7c2765e7`. ADR-0027 was registered in `179d769` and its hash
  recorded by `37fbf74`.

**Checks.** All 19 scorers -- the nine F8-2 scorings, `joint`'s three (d) reads and the three
normalized random-init (d) reads from F7'-2, `tel_only`'s three F3 final reads and F6-1b's
status-only classifier -- cover the same 137,025 windows, 5,312 positive, in the same order; the
run was refused until they did. No interval discarded a replicate. The raw windows' has-status
mask, measured on the raw-framed windows, is identical row for row to the normalized one (97,810
has-status windows under both), so both arms read the same strata.

**G, the two instrument gates. Computed before B1; each decides whether its arm is read.**

- **`joint_no_txt`, against ADR-0026's normalized random-init (d) reads (0.0581, 0.0575,
  0.0547): PASS.** Nine of nine paired lower bounds are strictly above zero; the weakest is
  **+0.0041** (seed 2 vs init 1). The arm reads 0.0750, 0.0663 and 0.0672.
- **`joint_status_raw`, against the three new random-init (d) probes on the raw windows: FAIL.**
  Four of nine lower bounds clear zero; seed 1 against all three inits, and seeds 2 and 3
  against init 1, do not. The weakest is **-0.0058** (seed 1 vs init 1). On the raw windows the
  untrained backbones read **0.0665, 0.0653 and 0.0651**, higher than the 0.0581, 0.0575 and
  0.0547 they read on the normalized windows, while the raw arm reads 0.0719, 0.0773 and 0.0777.
  **`joint_status_raw` is NOT EVALUABLE**, and under §4 that is not a null result about surface
  form: the instrument does not separate a pretrained backbone from an untrained one on these
  windows, nine of nine.

**B1 and the verdicts under §5.** Δ = AUPRC(ablation (d)) − AUPRC(`joint` (d), ADR-0026's
`R-joint-d`), same seed, R0, final-step probes, smallest effect of interest 0.005:

| arm | seed 1 | seed 2 | seed 3 | median | verdict |
| --- | --- | --- | --- | ---: | --- |
| `joint_no_txt` | -0.0030 [-0.0102, +0.0026] | -0.0147 [-0.0207, -0.0101] | -0.0013 [-0.0040, +0.0015] | **-0.0030** | **INCONCLUSIVE** |
| `joint_status_raw` | -0.0061 [-0.0122, -0.0014] | -0.0037 [-0.0086, +0.0009] | +0.0092 [+0.0050, +0.0142] | -0.0037 | **NOT EVALUABLE** (gate FAIL; as measured) |

- **`joint_no_txt` is INCONCLUSIVE at this budget.** HURTS fails because seeds 1 and 3 have
  upper bounds above zero and the median, -0.0030, is not below -0.005; HELPS fails on every
  seed; EQUIVALENT fails because seeds 1 and 2 have intervals outside (-0.005, +0.005). Seed 2
  alone is measurably worse without the narrative corpus. No comparison was untrusted. **The §1
  sentence stays undecided:** *"The unpaired narrative corpus [does / does not measurably]
  contribute to the text signal the joint model's read-out harvests."* **This was the outcome
  §5 named as most likely before the run**, and it is not evidence that the narrative corpus
  does not matter.
- **`joint_status_raw` is NOT EVALUABLE.** Its gate failed, so its B1 row carries no verdict:
  one seed below zero, one spanning zero and one above zero, reported as measured only. The
  pairing is row for row on identical keys and labels while the input tokens differ, by design,
  and every raw row carries the truncation caveat of §8 (41,371 windows, 30.19%, and 1,838
  positives, 34.60%, retain a different number of telemetry steps, ~1.5 fewer on average).
  **The §1 sentence stays undecided:** *"Normalising status strings to prose surface form (H3')
  [does / does not measurably] matter to the joint model's risk read-out."*

**B2, H1' replicated with the component changed.** Both ablations still clear `tel_only` (a)
under ADR-0026's H1' rule unchanged -- `joint_no_txt` +0.0170, +0.0087, +0.0156 (median
+0.0156) and `joint_status_raw` +0.0139, +0.0197, +0.0262 (median +0.0197), every lower bound
above zero -- so H1''s direction survives removing the narrative corpus, and survives raw
strings (on a failed gate). This row decides nothing.

**B3, against the order-blind status-only classifier (0.0725 [0.0537, 0.0979]).** Every one of
the six paired intervals spans zero (Δ from -0.0062 to +0.0052); for `joint_status_raw` the
classifier was fit on normalized strings and is reported as-is.

**B4, strata.** The has-status stratum (97,810 / 4,224, base rate 0.0432) carries the B1
differences: `joint_no_txt` -0.0055, -0.0165, +0.0007 and `joint_status_raw` -0.0093, -0.0033,
+0.0107, against no-status (39,215 / 1,088, base rate 0.0277) differences within ±0.0047.

**B5, selected against final (validation only, nothing scored).** The widest gap is
`joint_no_txt` seed 3, -0.0138 (step 700, 0.0744; final step 1,000, 0.0606); the fixed-final
rule stays in force and every verdict above reads the final step.

**What this record now licenses.** Neither §1 sentence has a bracket struck. §5's closure is
unchanged: no further arm, read-out or axis follows from this record, and the write-up reports
both sentences as undecided, one at this budget and one because the instrument does not read
the raw windows.

---

## ADR-0028 Calibration, risk–coverage and graceful degradation (H2)

**Status:** Accepted; **registered 2026-09-24, before any risk–coverage code, masked scoring or
validation scoring exists, and before any number below is read on test** · **Date:** 2026-09-24.
**Commit:** this record, `configs/eval/abstention_v0.yaml`, its configuration classes
(`src/faultline/evaluation/abstention_gate.py`) and their tests were committed together in
**`8f7f10e`**, before any code that computes a risk–coverage curve or scores a masked window
existed. The hash is recorded here by the commit after it. **Nothing in this record authorises a
GPU run** (§5).

**Sources of every count.** The window and positive counts, the saved score files and the scoring
times come from a read-only pass over `checkpoints/` and the shard manifests made on 2026-09-24
before this record was written, cited below as *the F9 read-only check*. Everything else is cited
to the record it comes from.

### 0. Why: the endpoint has no result, and the degradations so far are too mild to test H2

ADR-0001 names the endpoint as "the probability of a fault or shutdown event within a horizon,
with calibrated abstention". The project calls itself risk-calibrated, yet **no calibration or
abstention result exists**. ADR-0025 §6 deferred coverage and selective risk "until an abstention
path exists. None exists today", and none has been built since. The only abstention code is
`abstention_threshold` in `src/faultline/evaluation/calibration.py`, a quantile of `max(p, 1 − p)`
that nothing but its unit test calls. There is no risk–coverage curve, no AURC and no conformal
procedure. `expected_calibration_error` in the same file uses equal-width bins, not the
equal-mass bins registered below (the F9 read-only check).

H2 and its falsifier, as first written in the author's M3 evaluation design. That planning
document is not in this repository. The repository's own statements of H2 are ROADMAP's
"calibrated abstention degrades gracefully under modality shift" and ADR-0022's "graceful
degradation under modality dropout, in-distribution".

> As degradation severity rises, coverage falls and selective risk stays approximately flat … if
> coverage stays flat while selective risk rises, H2 is refuted.

**The existing degradations cannot test this.** H2's first rows are ADR-0025's text-withheld read
and the three CARE-farm channel masks. Each of them costs **at most 0.009 AUPRC** against the
clean read. That is inside the three-seed spread, so it is too mild to decide whether coverage or
selective risk moves first. Part B (§3) therefore registers a severity ladder strong enough to
damage the ranking, and it checks that damage (Gate B) before the H2 rule is read.

H2 is read **in-distribution, forward in time at the same sites** (ADR-0022). It is not a
site-shift result, and no sentence written from it may call it one.

### 1. Operating model and signals

**Arms.** Three arms, all on the R0 `tail_anchored_2048` windows through final-step probes, each
with ADR-0019's prior-corrected probabilities:

- `tel_only` (a): the `final_position` read, ADR-0025 control (iii)
  (`checkpoints/h1_gate_v0_a3f6606a/S2_tel_only_seed{1,2,3}_on_joint_final_R0_stride12_scores.npz`);
- `joint` (a): the `final_position` read, ADR-0025 S1
  (`checkpoints/h1_gate_v0_a3f6606a/S2_joint_seed{1,2,3}_final_R0_stride12_scores.npz`);
- `joint` (d): the `last_plus_text` read, ADR-0026 `R-joint-d`
  (`checkpoints/readout_v0_7c2765e7/S2_R-joint-d_seed{1,2,3}_final_R0_stride12_scores.npz`).

**The operating model per arm is the three-seed ensemble.** Its probability is the mean of the
three seeds' prior-corrected probabilities, `p = mean_s sigmoid(z_s)`, where `z_s` is seed s's
logit plus its saved `prior_offset`. The three seeds are paired row for row on identical
(turbine, year, end step) keys, and F9-1 refuses to run if they are not.

**Confidence signals.**

- **PRIMARY: seed disagreement.** `u = std_s(z_s)` is the population standard deviation (ddof 0)
  of the three seeds' corrected logits. A lower `u` means more confidence.
- **SECONDARY, reported only: margin.** `|p − τ|`. A larger margin means more confidence. No
  gate or verdict reads it.

**The operating point, fixed on the 2021 VALIDATION split before any test number is read.** The
split is `kelmarsh__val` + `penmanshiel__val`, R0 windows at stride 12, clean:

- **τ** is the ensemble probability threshold that maximises F1 on validation. The candidates are
  the distinct validation values of `p`. On a tie, the smallest such threshold is taken.
- **κ** is the disagreement cut-off that gives **90% coverage** on clean validation: the 0.90
  quantile of validation `u` (`method="lower"`).
- **Decision.** Abstain when `u > κ`. On covered windows, alarm when `p ≥ τ`.
- **Selective risk** is the misclassification rate on the covered set:
  (false alarms + missed positives among covered windows) / covered windows.

τ and κ are computed once per arm from the clean validation scores. They are written to the F9
report before any test file is opened, and they are never recomputed on test or under a mask.

**Caveat, carried with the operating point.** The validation base rate is **0.0211** (1,805 of
85,529). The test base rate is **0.0388** (5,312 of 137,025), 1.8 times higher. A threshold that
maximises F1 at one prior is not the one that maximises it at the other. ADR-0024's F3 addendum
recorded the 1.8x gap between the training natural rate and the test base rate as the ADR-0009
shift, not a correction error. Test coverage at κ is also not expected to be 90%. Both are
reported as measured.

**No validation scores in the right form exist (the F9 read-only check).** The only per-window
validation scores on disk are F3's (`checkpoints/seed_replication_v0_424c4f33/
S2_trained_seed{1,2,3}_val_stride12_scores.npz`, 85,529 windows, 1,805 positive). They are
`tel_only`'s **selected-step** probes on the **telemetry-only** windows, which is not this record's
operating model on two counts. First, the fixed-final-step rule is in force (F4, ADR-0022
addendum). Second, on test the same end steps read through the two framings correlate at only r = 0.30
(`tel_only` seed 1). No validation scores exist for `joint` (a) or `joint` (d) at all. Every arm's
τ and κ therefore wait for **nine new validation scorings** (3 arms × 3 seeds, final-step probes,
R0 windows) in F9-2. They are forward passes of saved probes, and nothing is trained. F9-1
asserts that the validation R0 index holds 85,529 windows and 1,805 positives before any of them
runs.

**Clean test scores exist for all nine (arm × seed) reads** (the F9 read-only check). Each file
holds 137,025 windows and 5,312 positives, with keys `logits`, `labels`, `which`, `ends`,
`sources` and `prior_offset`.

### 2. Part A: CPU, on saved scores, clean test split

**Calibration per arm. Reported, no verdict.**

- **ECE** over **15 equal-mass bins** (bins cut at quantiles of `p`, not at equal widths of
  [0, 1]), with a reliability table (per bin: mean `p`, positive share, windows). Each has a block
  bootstrap interval under `gate_check_v0`'s bootstrap.
- It is computed for (i) the **prior-corrected ensemble** as it stands, and (ii) the ensemble
  after **Platt recalibration** (a, b on the ensemble's logit, `logit(p)`) **fitted on validation
  only** and applied unchanged to test.
- **The known under-read, stated before it is measured.** F3 (ADR-0024 addendum, report §3)
  read `tel_only`'s corrected mean test probability at **0.0176, 0.0173 and 0.0189**
  (0.017–0.019), against a test base rate of 0.0388. The prior-corrected ensemble is therefore
  expected to under-read on test. The Platt fit is on a split whose base rate is 0.0211 and does
  not remove that shift.

**Risk–coverage per arm.**

- **The full curve.** Windows are sorted by `u` ascending (ties broken by row order). At every
  coverage `c = i / n`, the selective risk is that of the `i` most confident windows at the
  arm's τ.
- **AURC** is the mean selective risk over the `n` coverage points.
- **The random-ordering reference.** AURC under a uniformly random confidence ordering, averaged
  over **100** permutations drawn from `numpy.random.default_rng(20260924)`. The same 100
  permutation seeds are reused in every bootstrap replicate.

**GATE A (the instrument), per arm:**

> Paired block-bootstrap Δ = AURC(seed disagreement) − AURC(random ordering). PASS iff the 95%
> upper bound is below zero. On FAIL, abstention on that arm is NOT EVALUABLE.

The bootstrap is `gate_check_v0`'s, unchanged: two-day blocks of 288 steps, 10,000 replicates,
seed 20260916, 95%, and more than 1% of replicates discarded makes the comparison untrusted. Both
sides are recomputed on the same resampled rows. A replicate is discarded only if it holds no
positive window. **Gate A needs τ**, which fixes what counts as a misclassification, and τ comes
from validation (§1). Gate A is therefore computed after F9-2's validation scorings. No
provisional τ is used for any number that is reported.

**Reported:** coverage and selective risk at (τ, κ) on clean test, per arm, each with its block
bootstrap interval. The same rows are reported under the margin signal, beside the primary.

### 3. Part B: the severity ladder on `joint` (d), GPU scoring only

**Degradation.** At inference, **k of the 12 core channels are masked to `<nan>` on every step of
the R0 `tail_anchored_2048` windows, and the text is kept**, for **k ∈ {2, 4, 6, 8}**. The
mechanism is ADR-0025 S5's masked joint sampler (`MaskedJointSampler` over
`care_attribution.mask_positions`). Every overwritten token is checked to be a telemetry value,
as S5 checked. Only the backbone's input changes: the probes, τ and κ stay the clean ones.

**The channel sets.** One draw decides all four sets. It is
`numpy.random.default_rng(20260924).permutation(12)` over the 12 core channels in the step
layout's order (`data/shards/telemetry/quantile_bins_v2_9cd52b65/manifest.json`, `step` without
`<sep>`: wind_speed_ms, power_pu, rotor_speed_rpm, generator_speed_rpm, pitch_angle_deg,
nacelle_position_deg, ambient_temp_c, nacelle_temp_c, gearbox_oil_temp_c,
generator_bearing_temp_c, generator_winding_temp_c, main_bearing_temp_c). The set at k is the
first k channels of that permutation. The sets are therefore nested, and they are identical
across seeds and windows:

| k | channels masked |
| ---: | --- |
| 2 | nacelle_position_deg, ambient_temp_c |
| 4 | + generator_speed_rpm, rotor_speed_rpm |
| 6 | + generator_bearing_temp_c, power_pu |
| 8 | + pitch_angle_deg, generator_winding_temp_c |

The four channels never masked are main_bearing_temp_c, wind_speed_ms, nacelle_temp_c and
gearbox_oil_temp_c. The draw is not tuned. It was made once, the seed is this record's date, and
the order is recorded above before anything is scored.

**Scorings.** 4 severities × 3 seeds = **12 on test**. There are also the **nine clean validation
scorings** of §1 (all three arms, because (a) found none of them in the right form, not only
`joint` (d)'s three). The validation split is not scored under a mask. **Cost, from the F9
read-only check's timing sidecars:** a clean R0 test scoring took 442.4 s (`joint` (d)), 456.7 s
(`joint` (a)) and 467.0 s (`tel_only` (a)), and a masked R0 test scoring 445.2 s. The 12 ladder
scorings come to about 12 × 445 s ≈ 1.48 h. The nine validation scorings are about 0.624 of a
test pass each (85,529 / 137,025), so about 0.71 h. The total is **about 2.2 GPU-h**,
author-launched, on the RTX 4060.

**GATE B (damage), computed first:**

> Paired Δ AUPRC(ensemble, k=8) − AUPRC(ensemble, clean). If its upper bound is not below zero,
> H2 is NOT TESTABLE at this severity and is reported as such.

**H2 RULE**, on the ensemble at k = 8 against clean, (τ, κ) unchanged:

> Δcov = coverage(k=8) − coverage(clean); Δrisk = selective risk(k=8) − selective risk(clean);
> paired block bootstrap. Smallest effect of interest for selective risk: 0.005 absolute (about 13%
> of the test base rate; chosen before the run). SUPPORTED (graceful) if the upper bound of Δcov is
> below zero AND the upper bound of Δrisk is below +0.005. REFUTED if the lower bound of Δcov is at
> or above zero AND the lower bound of Δrisk is above zero. Otherwise INCONCLUSIVE. Requires Gate A
> PASS on joint (d) and Gate B damage; anything the clauses do not name is reported as measured and
> no clause is added afterwards.

If Gate A fails on `joint` (d), H2 is **NOT EVALUABLE**. If Gate B shows no damage, H2 is **NOT
TESTABLE at this severity**. In either case the ladder is still reported as measured. The pairing
is row for row on the 137,025 test windows, and each side's ensemble, `u` and misclassifications
are recomputed on the same resampled rows. The bootstrap is `gate_check_v0`'s. A comparison that
discards more than 1% of replicates counts toward no clause.

**Reported beside the verdict, deciding nothing:** the whole ladder (k = 0, 2, 4, 6, 8) as curves
of coverage, selective risk, AUPRC and ECE (equal-mass, 15 bins), each with its interval. The
margin-signal results are reported beside the primary at every k.

### 4. Caveats, carried on every row

- **ADR-0009**: one harmonised event rule across sites; the label is that rule's, not a site's
  own.
- **Forward in time, same sites** (ADR-0022): in-distribution, never site shift.
- **Message-volume shift** (ADR-0025): Kelmarsh positives average 67.2 status tokens in train
  (stride 6) and 190.1 in test (stride 12).
- **A three-seed ensemble is a small ensemble.** Seed disagreement over three members is a coarse
  confidence signal, and Gate A exists because it may be no better than random.
- **The operating point is fixed on a split with a different base rate** (0.0211 validation
  against 0.0388 test; §1).

### 5. Steps. Each needs the user's authorisation

1. **F9-1, code.** The risk–coverage module (ensemble, disagreement, equal-mass ECE, Platt, AURC,
   the random-ordering reference, Gate A, the H2 rule), the validation-scoring runner and the
   masking-ladder runner. Everything is fixture-tested, and the §3 channel sets are asserted
   against this record. Part A is CPU and decides only a gate, never the H2 verdict. It runs and
   reports in F9-1 **only as far as it needs no validation scores**: the ECE and reliability table
   of (i). Every number that depends on τ, κ or a validation fit — the risk–coverage curves, AURC,
   Gate A, the Platt rows and the (τ, κ) rows — waits for F9-2's validation scorings, because none
   exist in the right form (§1).
2. **F9-2, scoring (author, GPU).** The nine clean validation scorings and the twelve ladder
   scorings, about 2.2 GPU-h.
3. **F9-3, verdict.** τ and κ from validation first. Then Part A's remaining rows and Gate A, then
   Gate B, then the H2 rule, then the reported ladder.

### Outcome of F9-3, 2026-09-24 -- Gate A PASSES on all three arms, Gate B shows damage, H2 is INCONCLUSIVE

**Runs.**
- **Scorings.** F9-2 ran on the GPU at `8281227` from a clean tree, launched by the author. It
  made the 21 scorings (9 clean validation, 12 masked test) in 2.24 GPU-hours. Every selection
  re-score matched, and on every masked scoring the masked slots equal retained steps × k.
- **Operating point.** `faultline model abstention-operating-point` fitted τ, κ, the margin
  cut-off and Platt's (a, b) on the clean validation scores only (85,529 windows, 1,805
  positive). The record, `reports/data/abstention_operating_points_v0.json`, was committed alone
  in **`1ad1890`** before any test file was opened, and a test refits it exactly from the
  validation files.
- **Verdict run.** `faultline model abstention-outcome` ran on the CPU in about 63 minutes: 10
  replicate vectors on the memory-capped pool, most of it the 100-permutation random reference.
  It trained nothing and scored nothing.
- **Report.** `reports/data/abstention_v0_20260924.md` and its `.json`, with configuration
  `abstention_v0.yaml` `30c9c714`. The report's claim table reads each of the 114 numbers this
  outcome draws on a second way, by a separate implementation on the scores or by re-reading the
  replicate vectors. All 114 agree.

**Checks.** Every ensemble read here covers the same 137,025 test windows, 5,312 of them
positive, in the same order: the three arms' clean reads and `joint` (d) at k = 2, 4, 6 and 8.
The run was refused until they did. No interval discarded a replicate.

**Step 0 and the arm's name.** The F9-3 brief first stopped at step 0. It assumed that
`tel_only` (a)'s test scores were on the M1 1,872-token windows. They are on R0 (§1, ADR-0025
control iii), and so are its validation scorings. The author ruled to proceed as registered and
to name the arm **"`tel_only` backbone, (a), on R0 windows (ADR-0025 control iii)"**. **It is
not F3's `tel_only` (a) on the 1,872-token M1 windows, the H1/H1′ comparator, and its
calibration should not be read as that baseline's.**

**Operating points (validation only):**

| arm | τ | κ |
| --- | ---: | ---: |
| `tel_only` backbone, (a), on R0 windows (ADR-0025 control iii) | 0.0353 | 0.3257 |
| `joint` (a), on R0 windows (ADR-0025 S1) | 0.0410 | 0.3322 |
| `joint` (d), on R0 windows (ADR-0026 R-joint-d) | 0.0637 | 0.3388 |

**Part A, reported, no verdict.** On clean test, the equal-mass ECE is **0.0181 [0.0143,
0.0219]**, **0.0194 [0.0157, 0.0232]** and **0.0172 [0.0135, 0.0209]** for the prior-corrected
ensembles in the order above. After the validation-fitted Platt map it is **0.0181 [0.0144,
0.0219]**, **0.0184 [0.0147, 0.0222]** and **0.0164 [0.0127, 0.0201]**, so every interval
overlaps its unmapped one. The corrected probabilities under-read by about half: their means are
0.0207, 0.0193 and 0.0216 (0.0206, 0.0204 and 0.0224 after Platt) against the test base rate of
0.0388. §2 predicted this before the run, because Platt is fitted at the validation base rate of
0.0211 and cannot remove that shift.

At (τ, κ) on clean test, coverage is 0.8911, 0.8854 and 0.8816 against the 0.90 fixed on
validation. Selective risk is 0.0577, 0.0729 and 0.0496.

**Gate A, per arm: PASS on all three.** Δ = AURC(seed disagreement) − AURC(random):

| arm | Δ AURC | outcome |
| --- | --- | --- |
| `tel_only` backbone, (a), on R0 windows (ADR-0025 control iii) | −0.0158 [−0.0177, −0.0140] | **PASS** |
| `joint` (a), on R0 windows (ADR-0025 S1) | −0.0184 [−0.0206, −0.0163] | **PASS** |
| `joint` (d), on R0 windows (ADR-0026 R-joint-d) | −0.0275 [−0.0302, −0.0250] | **PASS** |

Each random-ordering AURC matches its arm's full-coverage selective risk to within 0.0001 (0.0635,
0.0830 and 0.0689), which is the expected value of a random ordering. Seed disagreement
therefore orders risk better than chance on every arm, and abstention is evaluable on all three.

**Gate B, `joint` (d) at k = 8: DAMAGE, narrowly.** Δ AUPRC(ensemble, k = 8) − AUPRC(ensemble,
clean) = **−0.0039 [−0.0082, −0.0001]**. The upper bound is below zero by 0.0001.

**H2, `joint` (d), k = 8 against clean, (τ, κ) unchanged: INCONCLUSIVE.**

| Δcov | Δrisk | verdict |
| --- | --- | --- |
| **−0.0797 [−0.0841, −0.0753]** | **+0.0053 [+0.0033, +0.0074]** | **INCONCLUSIVE** |

- **SUPPORTED fails on its risk clause.** Coverage falls (the upper bound is below zero), but the
  Δrisk upper bound, +0.0074, is not below the registered +0.005.
- **REFUTED fails on its coverage clause.** Selective risk does rise measurably (the lower bound
  is +0.0033 > 0), but coverage does not stay flat (the lower bound is below zero).
- **Neither reading holds.** Abstention neither held selective risk within the smallest effect
  while it gave up coverage, nor held coverage while selective risk rose. It gave up 8
  percentage points of coverage (from 0.8816 to 0.8019), and selective risk still rose (from 0.0496
  to 0.0549). The point Δrisk, +0.0053, sits at the smallest effect of interest, and its
  interval straddles it.

**What this licenses about "risk-calibrated abstention under degradation".** Nothing beyond
"undecided". With eight of twelve core telemetry channels masked on forward-in-time data at the
training sites, disagreement-based abstention on `joint` (d) withdraws coverage, but at this
budget it cannot be shown to keep selective risk within 0.005 of clean. The ensemble's
probabilities under-read the test base rate by about half before and after Platt, so the project
has no calibrated-probability result either. This is not, and cannot be read as, a result under
site shift.

**The ladder, reported as measured, deciding nothing** (`joint` (d); intervals in the report):

| k | coverage | selective risk | AUPRC | ECE |
| ---: | --- | --- | --- | --- |
| 0 | 0.8816 [0.8779, 0.8853] | 0.0496 [0.0458, 0.0534] | (Gate B's paired Δ) | 0.0172 [0.0135, 0.0209] |
| 2 | 0.8960 [0.8927, 0.8993] | 0.0565 [0.0525, 0.0605] | 0.0867 [0.0748, 0.1005] | 0.0101 [0.0070, 0.0140] |
| 4 | 0.8866 [0.8833, 0.8898] | 0.0557 [0.0517, 0.0596] | 0.0868 [0.0749, 0.1006] | 0.0080 [0.0061, 0.0116] |
| 6 | 0.8467 [0.8429, 0.8503] | 0.0558 [0.0518, 0.0597] | 0.0823 [0.0714, 0.0950] | 0.0072 [0.0055, 0.0108] |
| 8 | 0.8019 [0.7976, 0.8060] | 0.0549 [0.0509, 0.0589] | 0.0754 [0.0657, 0.0865] | 0.0068 [0.0050, 0.0100] |

- **Selective risk moves first.** It steps up by k = 2 and then stays near 0.055. Coverage does
  not fall until k = 6.
- **AUPRC is not monotone in k.** The point AUPRC at k = 2 and 4 is above k = 8's, and above the
  clean read in the report.
- **ECE falls with k for a known reason.** Masking raises the mean probability (0.0216 clean,
  0.0335 at k = 8) toward the base rate, which offsets the under-read. It is not evidence that
  masking calibrates.
- **The margin signal is in the report beside every row** and decides nothing.

**What this record closes.** ADR-0028's three steps are done. H2 is INCONCLUSIVE at this budget
and severity, and no clause, severity or signal is added afterwards (§3). All three arms keep the
§4 caveats: ADR-0009's harmonised label, forward in time at the same sites, the message-volume
shift, a three-seed ensemble, and an operating point fixed at the validation base rate of 0.0211
against the test rate of 0.0388.
