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

**Status:** Accepted · **Date:** 2026-09-09

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
redesigning it. **TODO(m2): replace the phone pattern with one anchored on telephone
formatting (country codes, separators, plausible lengths) and measure its false
positives against the real narrative corpus before enabling it.** Until then, any
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
