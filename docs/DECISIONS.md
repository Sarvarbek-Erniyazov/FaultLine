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

**Status:** Accepted · **Date:** 2026-09-09

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

The ablation is the test, not the joint-versus-telemetry comparison on its own: a
joint model can beat a telemetry-only model by having more parameters.

**What would change this decision.** An M2 finding that no adequately licensed
narrative corpus is reachable, which removes the mechanism H3 depends on and
re-opens the code book; or an M3 probe showing message representations cluster by
site rather than by meaning.

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
