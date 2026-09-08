# Provenance and independence

> **Draft for the author to review, edit and sign.** The placeholders marked
> `<author fills in>` describe the author's other work and must be completed by the
> author, not by anyone else. Nothing in this file should be taken as accurate until
> it is signed.

## Statement

FaultLine is a personal research project by Sarvarbek Erniyazov.

1. **Hardware and time.** It is developed on personally owned hardware — a single
   workstation with one NVIDIA RTX 4060 (8 GB VRAM) and 32 GB of system memory — and
   in personal time. No institutional compute, cluster allocation or cloud credit is
   used.

2. **Data.** It uses public, licence-documented data only. Every source is recorded
   in `docs/DATA_LICENSES.md` with its licence and attribution, and staged with a
   checksum manifest under `data/cards/manifests/`. Sources whose terms are
   unspecified or unverified are excluded until the terms are confirmed in writing
   (ADR-0004). No proprietary, confidential or partner-supplied data is used, at any
   stage, in any form — including as a sanity check.

3. **Independence from other work.** FaultLine uses no data, code, models,
   deliverables or unpublished results from the author's employer, doctoral advisor,
   or any funded project the author participates in. It is not a component,
   spin-off, prototype or preliminary study of any of them, and no result produced
   here is reported as an output of any of them.

4. **Naming.** A set of terms associated with the author's funded and doctoral work
   is banned from this repository outright and the ban is checked mechanically
   (ADR-0002, `tests/test_naming.py`). This is a safeguard against inadvertent
   association, not a claim that association would otherwise be intended.

5. **Scope.** FaultLine is a research prototype. It is not an operations product, is
   not validated against operational practice, and must not be used to make
   decisions about real equipment.

## How this project differs from the author's other work

The author fills in the right-hand column. The point of the table is that the two
bodies of work should differ on *every* row; if a row ends up matching, that row
needs an explanation in this file rather than a shrug.

| dimension | FaultLine | the author's other work |
| --- | --- | --- |
| **Endpoint** | Calibrated probability of a fault or shutdown event within a horizon, with abstention as a first-class output; scored by AUPRC, event-level F1, false alarms per hour, detection delay, and risk–coverage behaviour under shift. | `<author fills in>` |
| **Model class** | A single decoder-only transformer pretrained from scratch over a joint discrete vocabulary of text tokens and per-channel quantile-bin telemetry tokens. | `<author fills in>` |
| **Data** | Four public wind-farm SCADA records (CC BY 4.0 and CC BY-SA 4.0) plus a public-domain operator-narrative text corpus. Nothing proprietary; nothing under embargo. | `<author fills in>` |
| **Ownership** | Personal hardware, personal time, sole authorship; code MIT-licensed by the author. | `<author fills in>` |

## Third-party material used

| what | where it came from | how it is used | licence |
| --- | --- | --- | --- |
| Text pipeline design (cleaning, quality filtering, exact deduplication, PII scrubbing, stats reporting) | The instructor's reference notebook from the author's LLM-engineering course | Ported into `src/faultline/data/text/`, with every change documented in `docs/COURSE_PORT.md`. The notebook itself is kept out of git under `notebooks/_reference/`. | Course material; the ported implementation is the author's own writing |
| Wind-farm SCADA records | Zenodo; see `docs/DATA_LICENSES.md` | Staged locally, never redistributed | CC BY 4.0, CC BY-SA 4.0 |
| Open-source libraries | PyPI | Runtime and development dependencies, declared in `pyproject.toml` | Their own licences |

The course notebook is acknowledged deliberately. It supplied the *shape* of the text
pipeline — the stage sequence and the quality heuristics — and pretending otherwise
would misrepresent the work. What is original here is the modular, typed,
config-driven implementation, the telemetry pipeline, the joint vocabulary, and the
evaluation design.

## Signature

Signed: `<author fills in>` · Date: `<author fills in>`
