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
convention or vocabulary, is taken up as H3', registered on its own before it is measured.

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
