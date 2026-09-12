# Roadmap

Four milestones. Each has explicit "done when" criteria, because the failure mode of
a solo research project is a milestone that is 80% finished four times over.

The ordering is deliberate: telemetry first (M1) because it carries the decision
endpoint and can be evaluated without any language modelling; text second (M2)
because it runs in lockstep with the author's coursework; joint last (M3) because it
is only interesting once both halves independently work.

---

## M0 — skeleton, pipelines, data staging · **done** (tagged `m0`, 2026-09-10)

Repository, tooling and hygiene; the course text pipeline ported into a tested
package; the telemetry pipeline designed and implemented against synthetic fixtures;
the joint vocabulary layout and quantile-bin tokenizer implemented and tested; four
public SCADA sources staged, checksum-verified and documented.

No model code beyond typed stubs. No training. No tokenizer fitted on real data.

**Done when** (status as of 2026-09-10)

Figures in this list are hand-written snapshots. The generated record is the checksum
manifests (`data/cards/manifests/*.json`), the dataset cards built from them, and the
reports under `reports/data/`; where the two disagree, the generated record is right.

- [x] `uv pip install -e ".[dev]"` succeeds and `faultline --help` lists every command.
- [x] `ruff check`, `mypy --strict src/` and `pytest -q` all pass; tests run in under
      60 seconds and touch no real data and no network. *(358 tests, 3.7 s, 2026-09-10.)*
- [x] `docs/COURSE_PORT.md` maps every notebook cell to a module, function, config key
      and test, and lists every semantic change with its justification.
- [x] `faultline text run` on the committed fixture corpus produces
      `reports/data/<run_id>/` with a stats report per stage and a `run.json`.
- [x] Telemetry stages, adapter discovery, event horizon labelling, split assignment,
      `VocabLayout`, `QuantileBinTokenizer` and `JointVocab` are implemented and unit
      tested on synthetic data.
- [x] **Tier-1 files for all four sources downloaded and md5-verified.** *37 files,
      17.44 GB: Kelmarsh 11 (3.69 GB), Penmanshiel 16 (5.28 GB), Hill of Towie 9
      (2.96 GB), CARE 1 (5.50 GB). Every file was re-hashed against its manifest on
      2026-09-10 and all 37 match. Staging took two Zenodo outages (HTTP 504, then
      connection timeouts); the resumable downloader is what got through them.*
- [x] One raw inventory report per source in `reports/data/`, and one dataset card per
      source in `data/cards/`. *All four answer the free-text question with
      measurements pooled over every parsed event table: Kelmarsh and Penmanshiel
      `VERIFIED no`, a code book (217 and 231 recurring labels); Hill of Towie
      `VERIFIED no`, codes only (1,004,341 alarm rows, no message column); CARE
      `VERIFIED short written descriptions` (35 strings over 45 described events).
      ADR-0001 records what that does to its conclusion.*
- [x] `tests/test_naming.py` passes; the banned strings appear only in ADR-0002.
- [x] **Remote exists, the `m0` tag is pushed, and no data, secret or file over 5 MB is
      in the history.** *Verified 2026-09-10 across every commit: no path under
      `data/{raw,cleaned,filtered,final}/` and no `.env` has ever been tracked, and the
      largest blob in the history is 70.9 KB. The tag was withheld until every line
      above passed, and is applied to the commit that closes this list; the tag itself
      is the evidence for this line.*

**Beyond the original M0 scope, because the evidence allowed it.** All of the
following was scheduled for M1 and was brought forward once the staged Kelmarsh
archives made it answerable:

- The Kelmarsh adapter's loaders are implemented and tested against a committed
  excerpt of the real archive, and its channel map is resolved — 13 of 14 channels,
  cross-checked against the provider signal mapping, with the fourteenth
  (`gearbox_bearing_temp_c`) verified *absent* from the record rather than left
  unmapped.
- `main_bearing_temp_c` was added to the canonical channel list, and every canonical
  channel now declares a `core` or `extended` tier. A leave-site-out evaluation may
  read core channels only, enforced in split-config validation.
- Two `TODO(m1)` questions were closed by measurement rather than by re-reading
  metadata that contradicted itself: the Kelmarsh power column is **kW** (median
  per-turbine-year p99.5 of 2,057 against a rated 2,050, six times what a 10-minute
  energy total would reach), and its timestamps are **UTC** (no daylight-saving
  fingerprint in any of 54 turbine-years). `faultline inspect resolve` and
  `reports/data/resolved_kelmarsh_20260909.md` are the evidence.
- Found while measuring, and now a documented M1 obligation: the Kelmarsh 2023 and
  2024 exports repeat every timestamp about 41 times.
- ADR-0003 was amended to v2 — fixed-capacity blocks with telemetry as a stable
  prefix — so that M1 shards survive the M2 tokenizer. ADR-0007 was added, routing
  status messages through the text pathway and stating hypothesis H3.
- `configs/data/text_v1.yaml` fixes the two regex defects the M0 fixture run
  exposed, leaving `text_v0.yaml` untouched as the faithful port.
- CARE's evaluation-only restriction is enforced in `assign_splits`, closing the
  `TODO(m1)` in `docs/DATA_LICENSES.md`.

---

## M1 — telemetry-only model and risk evaluation

The first real result. A decoder-only transformer over telemetry tokens alone,
trained from scratch, evaluated as a risk model rather than a forecaster.

**Work**

- Implement the source adapters' loaders against the M0 inventory evidence; fill the
  channel maps from the provider signal-mapping files.
- Resolve every remaining `TODO(m1)` in the configs — plausibility bounds, the three
  unmeasured timezones, fault code mappings, split dates — against the stats reports,
  and freeze the result as `telemetry_v1.yaml`. Kelmarsh's timezone and its power
  bound are already measured; the rest are not.
- Decide how ingest collapses the repeated timestamps in the Kelmarsh 2023 and 2024
  exports, and prove the choice loses no values. *Done 2026-09-10 (M1a step 4): drop
  rows null in every mapped channel, assert at most one value per (label, channel),
  collapse. The assertion held in all 12 repeated files; read across all 311 columns,
  the repeats carry values in 9 derived availability columns only, with 0 conflicts.*
- *M1a, 2026-09-10: all four loaders implemented; Hill of Towie and CARE mapped from
  their own lookups; the core channel set derived from the maps and frozen in
  `telemetry_v1.yaml` (13 core, 1 extended, ADR-0008); timezones measured UTC at
  Kelmarsh, Penmanshiel and Hill of Towie, CARE's anonymised by design.*
- *M1a step 6b, 2026-09-11: labels harmonised under one rule at every site (ADR-0009,
  `events_v2.yaml`): seconds down per step by cause, then runs of at least 60 s. The
  held-out site publishes a cause (`tblSCTurFlag`), and pitch lubrication is excluded by
  it. Narrow (technical) per turbine-year: Kelmarsh 13.4, Penmanshiel 16.5, Hill of
  Towie 16.5; broad (any stop): 104.6, 127.7, 137.1.*
- *M1a step 6c, 2026-09-11: the collapse assertion counts distinct values and holds on
  all 311 columns of the 12 repeated Kelmarsh files; ingest counts rows per joined unit
  (14,905,629 less 460 copies = 14,905,169 loaded; the per-file sum had read
  19,304,713); CARE carries 45 labelled anomalies, not the README's 44; a split rule
  that misses the held-out source now fails loudly.*
- *M1a step 7, 2026-09-11: splits settled and checked (`splits_v1.yaml`, `windows.py`):
  train 2016-2020, val 2021, late test 2022-2024 at both training sites; Hill of Towie
  held out, CARE evaluation-only. 1,656 segments and 43,956,756 windows checked, none
  crossing a split. Narrow events: train 265 / 875, val 39 / 295, late test 415 / 333
  (Kelmarsh / Penmanshiel), Hill of Towie 693. The late period runs at about twice the
  training rate: the temporal test is a drift test. Short all-channel gaps now reach
  imputation instead of being dropped with the long ones.*
- *M1a step 8, 2026-09-11: `telemetry_v2.yaml` lists each source's missing-value codes
  and revises every bound from the observed percentiles (`faultline inspect ranges`);
  v0 and v1 untouched. Coverage measured (`faultline inspect missingness`): core
  channels 95-100% at Kelmarsh and Hill of Towie, except Hill of Towie wind direction
  at 49.8% (absent in 2019, half the held-out grid); Penmanshiel pitch and gear oil at
  70% (whole turbine-years missing). Imputation fills under 0.03% of steps. No channel
  is demoted: that is gate 2's decision, recorded under ADR-0008.*
- *Gate 2, 2026-09-11: wind direction demoted to extended (core 12); Penmanshiel pitch and
  gear oil stay core; the harmonised labels accepted; the 20-40 events/turbine-year target
  void -- it was set against row counts, and the rule re-based the unit -- and never met.*
- *M1b step 9, 2026-09-11: four checks in `reports/data/verification_20260911.md`
  (`faultline inspect verification`).*
  - *Hill of Towie's Com timer reads as a commanded stop by behaviour: 86.4% of its runs
    start Mon-Fri 07-17 UTC, and telemetry never drops out while it runs. Reading it as
    technical would move 84.3% of the held-out narrow label (693 to 1,206 events;
    ADR-0009).*
  - *The late split is a temporal hold-out with a change in what is labelled, not a drift
    test; this supersedes step 7's wording. The rise starts in 2022 at Kelmarsh and 2021
    at Penmanshiel, before the 2023 export change, and `anemometer defect` stops lead it,
    logged from 2021 at both sites at once. Without them Kelmarsh 2022-23 is flat against
    training. Standing requirement: every late-test result is reported with and without
    the anemometer-defect events.*
  - *Penmanshiel's pitch and gear-oil gaps fill 42 of 70 train turbine-years and none in
    val or late test. Within train they are not label-informative: rate ratio 0.90
    (0.79-1.03).*
  - *CARE becomes a secondary, dataset-level probe with Wilson intervals: ±14 points at 50%
    (ADR-0010). The label and final reports stop printing its per-step base rates.*
- *M1b step 10, 2026-09-11: core = 12 in `telemetry_v3.yaml`, by the maps and three
  measured conditions (ADR-0008 amendment; `faultline inspect core`,
  `reports/data/core_rule_20260911.md`). Wind direction is extended: 0% of the held-out
  2019 grid. Condition (c) now uses a seasonally matched control; Penmanshiel's spring
  2018 rate did not clear it (0.24, 0.14-0.43), and the site-wide instrumentation outage
  behind it -- two spans, four channels, 3.69% of Penmanshiel's training steps -- is
  withheld from training windows only (`splits_v2.yaml`): 125,567 windows at each horizon,
  2.72% of all training windows. Pitch and gear oil clear the
  matched control (0.95) and stay core. Hill of Towie is reported per year, and the late
  test with and without `anemometer defect`.*
- *M1b step 11, 2026-09-11: the quantile-bin tokenizer, fitted on the train split of the
  training sites only (`faultline telemetry bins`, `configs/tokenizer/quantile_bins_v0.yaml`,
  `reports/data/quantile_bins_20260911.md`; ADR-0011). 256 bins: median reconstruction error
  0.81% of the interquartile range, 1.19% on validation. Ten point masses get exact bins (pitch
  at 0 degrees holds 31.5% of its values). CARE power is emitted as `<nan>`. 71% (2019) and
  62% (2023) of Hill of Towie pitch values lie below the training range, and 7% and 6% of its
  power above it: reported for gate 3, not corrected.*
- *M1b step 12, 2026-09-12: the fixed-order token stream and the window index
  (`faultline telemetry shards`, `reports/data/shards_20260911.md`; ADR-0003 note). Thirteen
  `uint16` tokens a step -- `<sep>` and the twelve core channels -- in one memory-mappable file
  per site and split under `data/shards/`, never committed. 61,601,722 training tokens,
  13,558,350 validation, 118,429,948 test; `<nan>` is 11.61% of all tokens. The window index
  reproduces the final stage's counts exactly at every split, horizon and label set, and carries
  the narrow label without `anemometer defect`: the late test's 24-hour base rate reads 3.68% and
  4.14% with it (Kelmarsh, Penmanshiel), 2.37% and 2.52% without. Channel tokens are reserved
  for the extended-channel ablation, and a channel token's identifier is now its canonical
  position.*
- *Gate 3, reached 2026-09-12: report and stop. The model is not chosen here.*
- *M1c, 2026-09-12: the gate-3 decisions applied together -- one config version, one
  re-tokenise, one re-shard, one leakage re-check (`telemetry_v4.yaml`,
  `quantile_bins_v1.yaml`, `splits_v3.yaml`; ADR-0012, ADR-0013, ADR-0014).*
  - *Pitch is floored at 0.0 degrees at every site as a declared datum transform applied
    after the bounds (`harmonise`, `datums.py`): Senvion reports fine pitch as an exact 0.0
    (41.30% / 21.12% of values), Siemens as a band centred on -1.0 (45.29% / 32.84% within
    0.05 deg of it). 3,819,549 values moved, 25.6% of all rows. Hill of Towie pitch below
    the training range: 71.40% / 61.83% -> 0.00% / 0.00%.*
  - *Power is per unit of rated power everywhere (`power_kw` -> `power_pu`), divided in the
    adapters by each record's own published nameplate (2,050 / 2,050 / 2,300 kW). CARE's
    power comes back into the stream on the provider's documentation, so `<nan>` falls from
    11.61% to 8.90% of all tokens and from 29.68% to 21.34% at CARE. Hill of Towie power
    above the training range: 6.81% / 5.62% -> 0.00% / 0.00%.*
  - *The tails get 16 fixed-width bins a side out of the same 256. Against a pure-quantile
    fit of the same bin count on the same values, the median reconstruction error falls from
    0.82% to 0.48% of the interquartile range (validation 1.19% to 0.50%) and the generator
    bearing's top bin from 42.7 degC to 2.78. **184 of 352 tail bins hold fewer than 500
    training values and 42 hold none**, which is the pre-registered signal to turn `n_tail`
    down; it is reported at gate 4, not acted on.*
  - *Every pre-registered invariant holds: the ingest, filter and final reports are
    byte-identical to M1b's apart from the channel rename, all 441 label tables regenerate
    unchanged, and the token counts, window counts at every split, horizon and label set,
    the 43,580,055-window leakage re-check and the label recomputation checks are unchanged.*
- *Gate 4, reached 2026-09-12: report and stop. The model ladder does not start here.*
- Fit `QuantileBinTokenizer` on the training split only.
- Model, training loop, checkpointing; multi-seed runs.
- Risk evaluation: AUPRC, event-level F1, false alarms per hour, detection delay.
- Selective prediction: risk–coverage curves, AURC, conformal risk control with a
  calibration split disjoint from both training and test.

**Done when**

- [ ] Leave-wind-farm-out results with multi-seed confidence intervals, reporting
      **worst-site** as well as mean performance.
- [ ] A risk–coverage curve and an AURC for every held-out site.
- [ ] A documented baseline the model must beat (at minimum: a power-curve residual
      detector and a gradient-boosted tree on window features).
- [ ] Every number in the report traceable to a config hash and a run id.
- [ ] No `TODO(m1)` left in the telemetry configs.

---

## M2 — text tokenizer and text-only pretraining

Runs alongside the author's LLM-engineering coursework, so the milestone is shaped by
what that course covers: tokenizer training, dataset building, a from-scratch
pretraining loop.

**Work**

- Verify the licence of each candidate operator-narrative source in writing and
  record it in `docs/DATA_LICENSES.md`; enable sources one at a time in
  `configs/data/sources_text.yaml`.
- Run the ported text pipeline on the real corpus; add MinHash near-duplicate removal
  (`dedup.strategy: minhash`), which exact hashing cannot cover for republished
  incident reports.
- Train the byte-level BPE tokenizer; pretrain the text-only decoder.

**Done when**

- [ ] Every enabled corpus has a dataset card stating its licence, its PII setting and
      its stats report.
- [ ] A trained tokenizer with documented vocabulary size and compression statistics
      on held-out text.
- [ ] A text-only checkpoint with a validation loss curve and a documented compute
      budget.
- [ ] Near-duplicate removal implemented and its effect measured, not assumed.

---

## M3 — joint model, modality shift, streaming demonstration

**Hypothesis under test**

> **H3.** Pretraining on the operator-narrative corpus improves cross-OEM transfer of
> status semantics under leave-site-out evaluation, relative to the same joint
> architecture with the narrative pretraining ablated. (ADR-0007.)

H3 exists because ADR-0007 routes SCADA status messages through the BPE text pathway
instead of a per-OEM code book. That choice only pays off if narrative pretraining
transfers meaning across manufacturers, so the choice and the hypothesis are tested
together: **larger** held-out-site advantage on event types whose status strings share
vocabulary with the narrative corpus than on those that do not. A flat difference
falsifies H3 and supersedes ADR-0007.

H1 and H2 are reserved for the two claims the project already carries — that the joint
model beats both single-modality baselines, and that calibrated abstention degrades
gracefully under modality shift. They are stated as milestone criteria below rather
than as numbered hypotheses, and will be written out as H1 and H2 when there are M1
results to phrase them against.

**Work**

- Concatenate the M1 and M2 vocabularies per ADR-0003; no retokenization.
- Train the joint decoder; compare against both single-modality baselines.
- Modality-shift evaluation: channels dropped or corrupted, text withheld, at
  inference time — the axis that justifies the joint design.
- Export to ONNX and demonstrate CPU streaming inference.

**Done when**

- [ ] Joint model compared against the M1 and M2 models on the same held-out sites
      and the same seeds.
- [ ] A modality-shift table: performance and *coverage* under each degradation, since
      an abstaining model should abstain more when its inputs are damaged.
- [ ] A reproducible ONNX export plus a CPU streaming demonstration with measured
      latency.
- [ ] An honest limitations section: where the model fails and what would fix it.
- [ ] **H3 tested, with the narrative-pretraining ablation actually run** — reported
      whichever way it comes out, and ADR-0007 superseded if it comes out flat.

---

## Explicit non-goals, at every milestone

Not an operations product. Not instruction-tuned. Not tool-calling. No data, code or
time from the author's employer, advisor or funded projects. Public,
licence-documented data only.
