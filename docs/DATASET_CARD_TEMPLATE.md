# Dataset card template

The fields every card in `data/cards/` must answer. Cards are **generated** by
`faultline cards build` from the source specification, the checksum manifest and the
raw inventory report — this file documents the contract, it is not a form to fill in
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
- **Free text present: `VERIFIED yes` / `VERIFIED no` / `UNVERIFIED`**, with the
  evidence — the share of rows carrying a non-empty message and the mean message
  length, from the inventory report

  This is the field that ADR-0001 rests on: whether the paired text in this record is
  open-ended language or a controlled vocabulary that supplies only labels and
  structure. It is the single most consequential line on the card.

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
