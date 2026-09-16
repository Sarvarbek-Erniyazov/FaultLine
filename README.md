# FaultLine

FaultLine is a from-scratch joint telemetry–text sequence model for risk-calibrated event
modeling in cyber-physical (wind-energy) systems. One decoder-only transformer is pretrained
over a **joint vocabulary**: byte-level BPE tokens from an English incident-narrative corpus
(public-domain reports published by two U.S. federal regulators: the Nuclear Regulatory
Commission's event notifications and generic communications, which cover nuclear power
plants and radioactive-materials licensees, and PHMSA's pipeline incident narratives),
per-channel
**quantile-bin tokens** for wind-turbine SCADA telemetry, and structural tokens (modality
delimiters, channel identifiers, a missing-value token). The endpoint is decision-theoretic
rather than a forecast error: **the risk of a fault or shutdown event within a horizon, with
calibrated abstention, evaluated under shift.**

## Status

**M2 — text tokenizer and text-only pretraining, done 2026-09-16
([Gate 6 report](reports/data/m2_gate6_20260916.md)). M3, the joint model, is not
started.** M0 is done (tagged `m0`). M1 trained a telemetry-only model ladder, but its risk
result is **not** a positive finding: H1 is UNTESTED and the pretraining ablation
INCONCLUSIVE, with the reasons recorded in [docs/ROADMAP.md](docs/ROADMAP.md). M2's two
text rungs are undertrained at their pre-registered one-pass budget and the larger is not
better, so they are a working pipeline and a baseline, not a scaling result. No number here
yet supports the joint model. This line is updated at each milestone.

What exists today: the repository tooling; the telemetry pipeline over four staged SCADA
sources, its quantile-bin tokenizer, shards and the M1 model ladder with its risk
evaluation; the text pipeline, ported from a course reference notebook into a tested
package and run on the real text corpus; a robots.txt-gated text downloader; the fitted
byte-level BPE tokenizer (32,768 ids), its text shards and two text-only pretrained rungs;
and dataset cards plus checksum manifests for every staged source. What does not exist yet:
anything joint - no telemetry-and-text model, and no evaluation under modality shift.

**Tier 1 is staged for all four sources**: 37 files, 17.44 GB, every one md5-verified
against its record and re-hashed on 2026-09-10 — Kelmarsh 11 files (3.69 GB), Penmanshiel
16 (5.28 GB), Hill of Towie 9 (2.96 GB), CARE 1 (5.50 GB). Those figures are a hand-written
snapshot; the generated record is `data/cards/manifests/*.json` and the dataset cards built
from it, and `faultline inspect telemetry && faultline cards build` regenerates the evidence.

## Scientific framing

**Endpoint.** Given a window of telemetry and any accompanying text, estimate the probability
of a fault or shutdown event within a horizon *H*, and either commit to a decision or abstain.
Abstention is a first-class output, calibrated with selective prediction and conformal risk
control, not a post-hoc threshold.

**Shift axes.** The model is judged on data it was not trained on, along three axes:

| axis | held out | why it is the hard case |
| --- | --- | --- |
| site | leave-wind-farm-out (a whole farm, its turbine model and its control system) | the deployment case: a new farm has no labelled history |
| modality | text or telemetry channels dropped or corrupted at inference | sensors fail and narratives are missing exactly when things go wrong |
| temporal | later periods, and a site with a mid-record retrofit | control systems and turbines are modified in service |

**Metrics.** AUPRC, event-level F1, false alarms per hour, detection delay, risk–coverage
curves and AURC, coverage under shift, worst-site performance, all with multi-seed confidence
intervals. Accuracy on a random split is not a metric this project reports.

## Provenance and independence

FaultLine is a personal research project: personal hardware, personal time, public and
licence-documented data only. It uses no data, code, or deliverables from the author's
employer, advisor, or funded projects, and it is not a component of any of them. The full
statement, including the table contrasting this work with the author's other research, is in
[docs/PROVENANCE.md](docs/PROVENANCE.md). The naming rule that keeps the two identities
separate is recorded as ADR-0002 in [docs/DECISIONS.md](docs/DECISIONS.md) and enforced by
`tests/test_naming.py`.

## Data

Raw data is never committed; dataset cards and checksum manifests are. Every card records the
version-pinned DOI, the licence, the download date, the files retrieved and the caveats found
during inspection.

**Telemetry (staged at M0).**

| source | provider | turbines | period | licence | role |
| --- | --- | --- | --- | --- | --- |
| [Kelmarsh](https://doi.org/10.5281/zenodo.5841833) | Cubico Sustainable Investments | 6 × Senvion MM92 | 2016–2024 | CC BY 4.0 | training / validation site |
| [Penmanshiel](https://doi.org/10.5281/zenodo.5946807) | Cubico Sustainable Investments | 14 × Senvion MM82 | 2016–2024 | CC BY 4.0 | training / validation site |
| [Hill of Towie](https://doi.org/10.5281/zenodo.14870023) | RES on behalf of TRIG | 21 × Siemens SWT-2.3-VS-82 | 2016–2024 | CC BY 4.0 | held-out site, with a mid-record retrofit |
| [CARE to Compare](https://doi.org/10.5281/zenodo.10958774) | Fraunhofer IEE | 36, anonymised | multi-year | CC BY-SA 4.0 | labelled anomaly events, label cross-check |

Attribution strings, share-alike propagation and the sources deliberately excluded are in
[docs/DATA_LICENSES.md](docs/DATA_LICENSES.md). Per-source cards are in
[data/cards/](data/cards/), checksums in [data/cards/manifests/](data/cards/manifests/).

**Text (M2, staged).** Public-domain (17 U.S.C. 105) reports from two U.S. federal
regulators, staged by a robots.txt-gated downloader and specified in
[configs/data/sources_text.yaml](configs/data/sources_text.yaml):

- U.S. Nuclear Regulatory Commission (nrc.gov): Event Notification Reports, and four
  generic-communications collections (Information Notices, Bulletins, Generic Letters,
  Regulatory Issue Summaries). The event notifications are licensee-reported, and 27.5% of
  them are Agreement State reports from radioactive-materials licensees (medical, gauges,
  radiography) rather than plant events. The generic communications are regulator-authored
  guidance, 22.7% of the NRC corpus's tokens.
- Pipeline and Hazardous Materials Safety Administration (via data.transportation.gov):
  operator-written incident narratives from the 2010-onward hazardous-liquid, gas
  distribution, gas transmission and gathering, and LNG report files, 10,033 reports.

What was considered and excluded, and why, is recorded in ADR-0016.

## Repository layout

```
configs/         one YAML per run; never edited after a run (configs/README.md)
data/cards/      tracked dataset cards + manifests/ with checksums
data/{raw,cleaned,filtered,final}/{telemetry,text,paired}/   git-ignored stages
src/faultline/   the package: core, data/{common,text,telemetry}, tokenizers, download
scripts/         thin wrappers around the CLI; all logic lives in src/
tests/           mirrors src/; fixtures carry provenance READMEs
reports/         tracked Markdown + small JSON evidence, one directory per run
docs/            roadmap, decision records, provenance, licences, course port map
```

Both modalities run the same **four-stage contract** — `raw → cleaned → filtered → final` —
with the same rules: one YAML drives a run, each stage reads only the previous stage's output,
and each stage must emit a Markdown stats report. The text pipeline cleans, filters,
deduplicates and scrubs; the telemetry pipeline resamples to a regular grid, bounds-checks,
segments gaps and imputes short ones — always emitting a companion mask column, because
missingness is itself a shift signal (ADR-0006).

## Quickstart

```bash
# environment: uv installing exactly what uv.lock pins (docs/ENVIRONMENT.md)
uv sync --extra dev
pre-commit install

faultline --help

# tests: no network, no real data, under a minute
pytest -q

# stage the tier-1 telemetry archives (17.44 GB; --dry-run prints the plan first)
faultline download telemetry --config configs/data/sources_telemetry.yaml --tier 1 --dry-run
faultline download telemetry --config configs/data/sources_telemetry.yaml --tier 1

# inspect archives in place and write raw inventory reports
faultline inspect telemetry --source kelmarsh

# render dataset cards from record metadata + manifest + inventory
faultline cards build

# run the text pipeline end to end on the committed fixture corpus
python scripts/run_text_stage.py --config configs/data/text_v0.yaml --stage all \
    --input tests/fixtures/text/sample.jsonl
```

Set `FAULTLINE_DATA_ROOT` (see `.env.example`) to keep the archives off the repository drive.

## Hardware and budget

One RTX 4060 (8 GB VRAM), 32 GB RAM with roughly 10 GB typically free, a single researcher.
Every design choice — vocabulary size, context length, model size, the tiered download — is
made against that budget rather than against a cluster. torch is pinned in `uv.lock` to the
CUDA 13.2 build that matches the recorded driver (616.56, CUDA 13.4); see
[docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).

## Roadmap

M0 skeleton and data staging → M1 telemetry-only model with risk evaluation under
leave-farm-out → M2 text tokenizer and text-only pretraining → M3 joint model, modality-shift
evaluation, ONNX/CPU streaming demonstration. Criteria for each are in
[docs/ROADMAP.md](docs/ROADMAP.md).

## Limitations

- **The paired text in public SCADA data is almost never language.** Measured over all four
  records: Kelmarsh and Penmanshiel publish a code book of short recurring status strings,
  Hill of Towie publishes alarm codes with no text at all, and CARE's only text is 35 short
  root-cause descriptions written per event — richer than a code book, far too small to
  train on, and evaluation-only under its share-alike licence. The operator-narrative corpus
  is what makes the text side a language model; the SCADA event logs are a label and
  structure source. This is ADR-0001, qualified by its 2026-09-10 evidence, and it is the
  central risk of the design.
- Site coverage is small (four sources, three of them UK onshore), so "under site shift"
  means a handful of held-out farms, not a population.
- CARE is anonymised: its channel names are opaque, and its map is resolved per farm from
  the provider's feature descriptions rather than from names. Its active power is
  normalised against a rated power the record does not publish, so CARE power cannot be
  put on the kW scale the other three sources share.
- Nothing here is validated against operational practice; it is a research prototype and is
  explicitly not an operations product.

## Licence and citation

Code is MIT ([LICENSE](LICENSE)); it covers the source only. Datasets keep their own licences
([docs/DATA_LICENSES.md](docs/DATA_LICENSES.md)) and are not redistributed here. Citation
metadata is in [CITATION.cff](CITATION.cff).
