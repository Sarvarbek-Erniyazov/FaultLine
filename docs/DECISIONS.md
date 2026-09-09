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

**Status:** Accepted · **Date:** 2026-09-09

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

**Status:** Accepted · **Date:** 2026-09-09

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
