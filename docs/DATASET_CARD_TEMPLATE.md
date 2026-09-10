# Dataset card template

The fields every card in `data/cards/` must answer. Cards are **generated** by
`faultline cards build` from the source specification, the checksum manifest, the
raw inventory report and the resolution report — this file documents the contract, it is not a form to fill in
by hand. Editing a generated card by hand is a bug: the next build overwrites it, and
the edit was not backed by evidence anyway.

## Rule for every field

A field is either **filled from evidence** — the record metadata, the manifest, or a
named inventory report — or marked `UNVERIFIED — TODO(m<N>): <exact question>`.
Nothing is guessed, and nothing is left blank. A blank field reads as "no problem
here"; `UNVERIFIED` reads as "nobody has checked", which is the truth.

## Fields

### Identity
- Name and source id
- Provider
- Version-pinned record (id and link) and **concept DOI**
- Version DOI actually retrieved
- Licence (SPDX-style) and the required attribution string
- Accompanying publication, if the provider names one

### Contents as published
- Site name, country
- Turbine manufacturer and model
- Number of turbines, rated power per turbine
- Period covered, publication date
- Sampling resolution
- Timezone of the timestamps
- Any note the provider attaches to the record

### Staging
- Download date (first retrieval)
- Tier retrieved, number of files, total size
- Whether every checksum verified
- Path of the checksum manifest
- Path of the raw inventory report

### Channels
- Channel count as published
- Path of the channel map config
- **Mapping status**: resolved, partially resolved, or unresolved, and against which
  provider file

### Event, alarm and status logs
- Present in the record? Which member?
- Row count, unique codes, unique messages
- **Free-text verdict**, with the evidence — rows, rows with a message, distinct
  strings, mean length, and the share of distinct strings that occur exactly once,
  pooled over every parsed event table, from the inventory report. One of:
  - `VERIFIED no` — codes only (no message text at all), or a code book: a closed set
    of labels that recur, most distinct strings occurring more than once
  - `VERIFIED short written descriptions` — a closed set (at most 500 distinct
    strings) of which most occur exactly once, i.e. written per event rather than
    drawn from a code book; `VERIFIED written descriptions` when they average more
    than 200 characters
  - `VERIFIED yes` — open-ended text, more than 500 distinct strings
  - `UNVERIFIED` — nothing staged, or no event table found

  This is the field that ADR-0001 rests on: whether the paired text in this record is
  open-ended language or a controlled vocabulary that supplies only labels and
  structure. It is the single most consequential line on the card. The labels are not
  forced into yes/no: a record whose text is richer than a code book but far too small
  to be a corpus says exactly that.

### Questions resolved by measurement
- One row per question the provider metadata could not settle, with the verdict and
  the measurement behind it, from `faultline inspect resolve`
- `UNVERIFIED` until something has actually been measured

  A provider that states a unit in one file and a different unit for the same signal
  in another has not told you the unit; a header line asserting a timezone is a claim
  by the exporter, not a property of the timestamps. Where metadata contradicts
  itself or asserts without evidence, the card carries the measurement instead.

### Use in FaultLine
- Intended role: training site, validation site, held-out site, label source,
  evaluation only
- PII policy applied (ADR-0005), and why
- What is excluded from this source and why

### Caveats
- Caveats the provider states
- Caveats discovered during inspection
- Known limits of the card itself

### Generation
- Timestamp, git SHA, the command that produced the card, this template
