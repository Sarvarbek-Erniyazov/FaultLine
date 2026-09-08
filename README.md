# FaultLine

FaultLine is a from-scratch joint telemetry–text sequence model for risk-calibrated event
modeling in cyber-physical (wind-energy) systems. One decoder-only transformer is pretrained
over a **joint vocabulary**: byte-level BPE tokens from an English operator-narrative corpus
(public-domain incident and event reports about power and process plants), per-channel
**quantile-bin tokens** for wind-turbine SCADA telemetry, and structural tokens (modality
delimiters, channel identifiers, a missing-value token). The endpoint is decision-theoretic
rather than a forecast error: **the risk of a fault or shutdown event within a horizon, with
calibrated abstention, evaluated under shift.**

## Status

**M0 — skeleton, pipelines and data staging. No model has been trained. Nothing here is a
result yet.** This line is updated at each milestone.

What exists today: the repository skeleton and tooling, the text pipeline ported from a
course reference notebook into a tested package, the telemetry pipeline (canonical schemas,
per-source archive readers, cleaning/filtering/imputation/event stages) exercised on
synthetic fixtures, the joint vocabulary layout and the quantile-bin tokenizer, a
checksum-verifying downloader, and four public SCADA datasets staged with dataset cards and
manifests. What does not exist: any model, any training loop, any evaluation number.

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

**Text (planned, M2).** Public-domain operator-narrative sources — incident and event reports
from public safety and regulatory bodies. They are specified with `enabled: false` in
[configs/data/sources_text.yaml](configs/data/sources_text.yaml) and nothing is downloaded
until their terms are verified in writing (ADR-0004).

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
# environment (uv recommended; python -m venv works identically)
uv venv
uv pip install -e ".[dev]"
pre-commit install

faultline --help

# tests: no network, no real data, under a minute
pytest -q

# stage the tier-1 telemetry archives (~19.5 GB; --dry-run prints the plan first)
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
made against that budget rather than against a cluster. Torch is deliberately not a dependency
at M0; M1 pins the CUDA build matching the recorded driver.

## Roadmap

M0 skeleton and data staging → M1 telemetry-only model with risk evaluation under
leave-farm-out → M2 text tokenizer and text-only pretraining → M3 joint model, modality-shift
evaluation, ONNX/CPU streaming demonstration. Criteria for each are in
[docs/ROADMAP.md](docs/ROADMAP.md).

## Limitations

- **The paired text in public SCADA data is not language.** Status and alarm logs are
  template-like codes and short fixed strings, not open-ended prose. The operator-narrative
  corpus is what makes the text side a language model; the SCADA event logs are a label and
  structure source. This is recorded as ADR-0001 and it is the central risk of the design.
- Site coverage is small (four sources, three of them UK onshore), so "under site shift"
  means a handful of held-out farms, not a population.
- CARE is anonymised: channel names are opaque, so its channel map is unresolved at M0.
- Nothing here is validated against operational practice; it is a research prototype and is
  explicitly not an operations product.

## Licence and citation

Code is MIT ([LICENSE](LICENSE)); it covers the source only. Datasets keep their own licences
([docs/DATA_LICENSES.md](docs/DATA_LICENSES.md)) and are not redistributed here. Citation
metadata is in [CITATION.cff](CITATION.cff).
