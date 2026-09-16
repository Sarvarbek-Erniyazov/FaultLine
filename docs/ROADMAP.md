# Roadmap

Five milestones in two phases. Each has explicit "done when" criteria, because the
failure mode of a solo research project is a milestone that is 80% finished four times
over.

The ordering is deliberate: telemetry first (M1) because it carries the decision
endpoint and can be evaluated without any language modelling; text second (M2)
because it runs in lockstep with the author's coursework; joint last (M3) because it
is only interesting once both halves independently work.

## Sequencing (2026-09-12)

**Phase A — M1c ladder, then M2, then M3, then deployment.** The original scope,
unchanged, through the final-exam defense. Everything below under M1, M2 and M3 is
Phase A.

**Phase B — M4, after the defense only.** Paper readiness. None of it starts during
Phase A, and none of its items appear in an M1, M2 or M3 checklist.

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

      *2026-09-13: `nrc_event_notifications.json` (M2a) outgrew this limit twice as
      the source's real size became known (10,867, then 32,455 documents) -- the
      manifest's own shape was wrong for a source this size, not the limit. It is now
      sharded per report year as compact JSONL under
      `data/cards/manifests/nrc_event_notifications/`, each shard well under 5 MB;
      the limit itself stays at 5 MB rather than being raised
      (`faultline.data.common.manifest.write_manifest_sharded`/`load_manifest`).*

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
- *M1d, 2026-09-12: the last tokenizer change before the ladder (`quantile_bins_v2.yaml`,
  ADR-0015, `reports/data/quantile_bins_v2_20260912.md`). Two changes, both about the
  tails, on the same tables and the same splits as M1c.*
  - *`n_tail` turned from 16 to 4, as ADR-0014 pre-registered: the signal was 184 of 352
    tail bins under 500 training values and 42 empty, and it fired. The curve it was
    turned on is re-measured by the run rather than quoted: 16 -> 184/42, 12 -> 130/25,
    8 -> 76/12, 4 -> 30/1, 2 -> 10/0. After the fit, 0 of 41 tail bins are starved and
    none are empty.*
  - *The outermost bin of each tail is population-floored at 0.1% of the channel's own
    training values: it is the clamp target for every out-of-range value, so its effective
    width is unbounded, and at `n_tail` 16 `main_bearing_temp_c`'s top bin held 24
    training values while 2.68% of the held-out site's 2023 values clamp into it. It now
    holds 23,285. Both pre-registered acceptance checks pass and no channel is named.*
  - ***And the floor cancelled the tail rule on most channels while doing it.** Of 88
    fixed-width bins laid, 47 were merged back; 8 of 12 channels ended with a top bin
    wider than a pure-quantile fit's -- wider than doing nothing, on the measure ADR-0014
    was accepted for. A tail's values pack against its inner boundary, so the merge
    cascades and the clamp bin ends up spanning the whole 0.5% tail against a quantile end
    bin's 0.39%. Reported and not iterated on, as pre-registered; ADR-0015 carries it as
    the limitation and names the single design that would replace both rules.*
  - *Re-sharded under the v2 tokenizer (`reports/data/shards_v2_20260912.md`). **Every
    pre-registered invariant holds byte-identically**: the report differs from the v1
    shards' only in the three lines naming the tokenizer, its hash and the run. 61,601,722
    training tokens, every window count at every split, horizon and label set, the
    43,580,055-window leakage re-check, all 22,355,601 stored labels equal to those
    recomputed from the events, and `<nan>` at 8.90% -- all unchanged, as they must be:
    the bin edges moved and nothing else did.*
  - *The two reports gate 4 left historical are regenerated under `telemetry_v4.yaml`:
    ranges (`reports/data/ranges_20260912.md`, power percentiles now in per unit) and
    verification (`reports/data/verification_20260912.md`, splits_v3, and the producing
    threshold now printed as 0.005 pu -- the column heading still read "> 10 kW" while the
    code had used per unit since M1c).*
- *M1e, 2026-09-12: the model code. A decoder-only causal transformer written from
  scratch (`src/faultline/model/`), the window sampler over the shards, the training loop
  the four runs share, average precision written out and checked against hand-computed
  values, and the ladder that runs the experiment and writes one report
  (`faultline model ladder`; `configs/model/ladder_v0.yaml`,
  `configs/train/telemetry_v0.yaml`). Four sizes, four runs each, context held fixed as a
  separate ablation, and 57 tests.*
- *M1e results, 2026-09-13: the ladder run in full -- 32 runs, 4 sizes x 4 runs x the
  configured seeds, 3.0 billion training tokens, 4h57m wall clock on one 8 GB card
  (`reports/data/ladder_v0_20260912.md`, `.json`). **Two results, and they do not point
  the same way.***
  - ***Next-token loss scales cleanly.** Validation loss falls monotonically with size:
    2.791 +/- 0.047 (S0, 308k) -> 2.597 +/- 0.056 (S1, 1.18M) -> 2.371 (S2, 3.54M) ->
    2.242 (S3, 9.96M) nats. The seed half-range at the two rungs that have three seeds is
    about a fifth of the gap between adjacent rungs, so the curve is a curve and not
    noise. The course deliverable works.*
  - ***No risk arm learned beyond the prior at this budget with unweighted BCE; these runs
    cannot separate an unlearnable label from a starved head.** The AUPRC measurements
    stand and are unchanged: the frozen probe reads 0.031 / 0.044 / 0.043 / 0.048 and the
    fine-tune 0.052 / 0.055 / 0.042 / 0.043 across S0 to S3, against base rates of 1.15%
    and 2.45%, and on the test sites several arms score BELOW their own base rate. **The
    conclusion first drawn from them -- that event risk "does not scale" -- is withdrawn**
    (2026-09-13, docs-only, no retraining): it reads an absence of signal as a property of
    the label, and the training arithmetic below shows this budget could not have
    distinguished that from a head that never received enough positives to train.*
  - ***The arithmetic, from the run config and the committed records.** The risk arms ran
    at batch 16 with 2-step accumulation -- **32 windows an optimiser step** -- for 1,250
    steps, 40,000 windows. The 24-hour narrow label runs at **2.2050%** of the windows the
    sampler actually drew (16,524 positives in 749,387 stride-6 admissible training
    windows, both sites pooled; the committed shards report's per-site 1.58% and 2.51%
    agree to three figures). So a batch carried **0.71 positives on average**, **49% of
    optimiser steps carried none at all**, and a whole run saw **882 positives** -- 5.3% of
    the 16,524 distinct positive windows available to it. Mean training loss over each
    run's last tenth: **0.1004 (probe), 0.0971 (finetune), 0.1009 (random) nats**, against
    the binary entropy of the training base rate **H(p) = 0.1059 nats**. Every arm sits
    within 8% of the loss a constant predictor achieves, and 4 of the 24 risk runs sit
    above it.*
  - ***The evidence that the head is starved rather than merely unsuccessful.** Validation
    AUPRC was measured seven times a run on a pooled selection subsample holding 117
    positives in 6,000 windows, so **0.0195 is exactly the score of a constant scorer** --
    the average precision of an output carrying no ranking information at all. The
    randomly initialised control reads exactly 0.0195 in **27 of its 56 measurements,
    across 7 of its 8 runs** -- **S3/random 6 of 7, S2/random 3 of 7**. The fine-tune reads
    it 3 times, each at its own first measurement, before moving off it; the probe never
    does. A control pinned on the prior through most of training is not a measured
    baseline, so **the pretraining ablation is INCONCLUSIVE**: the 14-of-16 validation
    separation is a comparison against an arm that did not train, not evidence about a
    representation.*
  - ***Status, recorded rather than implied. H1 is UNTESTED** -- the ladder produces no
    evidence for or against it, in either direction. **The pretraining ablation is
    INCONCLUSIVE.** Neither is a negative result and neither may be cited as one. The
    remedy is pre-registered as M3 step 0 below, and is not started here.*
  - *Held out per year (`per_year_sites`): Hill of Towie 2019 runs at a 3.89% base rate and
    2023 at 2.76%, and every arm tracks the base rate at both -- the site-shift penalty is
    not visible because there is not enough signal above chance for it to be visible in.*
  - *Pre-registered and honoured: context held fixed at 144 steps across the ladder,
    training stride 6 with evaluation at stride 1, selection never on test, the control
    budget-matched to the fine-tune and enforced by the configuration, and three seeds at
    S0 and S1 quoted as the error bar for the single-seed S2 and S3 rather than implied
    throughout.*
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
  incident reports. *Superseded 2026-09-13: the trigger did not fire, and keyed dedup by
  event number is what this corpus needed (ADR-0016).*
- Train the byte-level BPE tokenizer; pretrain the text-only decoder.

*Done 2026-09-16. Full evidence: `reports/data/m2_gate6_20260916.md`; the source
decisions and their corrections are ADR-0016.*

**Done when**

- [x] Every enabled corpus has a dataset card stating its licence, its PII setting and
      its stats report. *Six cards under `data/cards/`, generated by `faultline cards
      text` from the manifests and the finished corpus; `docs/DATA_LICENSES.md` carries
      the text-source table.*
- [x] A trained tokenizer with documented vocabulary size and compression statistics
      on held-out text. *32,768 ids (32,512 merges), one fit, no sweep;
      `reports/data/text_bpe_v1_20260915.md` reports bytes/token per source on val and
      test, never pooled, and the share of the vocabulary seen under 100 times -- 77.47%,
      corrected 2026-09-16 from the 74.63% that report prints (never-seen ids were left
      out of the count).*
- [x] A text-only checkpoint with a validation loss curve and a documented compute
      budget. *S2 and S3, one seed each; `reports/data/text_pretrain_v1_*.md` carries
      the loss curve, the per-source loss and bits/byte, and which bound each rung hit;
      the selected parameters are in `checkpoints/text/` (not committed).*
- [x] Near-duplicate removal implemented and its effect measured, not assumed. *The
      pre-registered random-pair trigger measured 0.0005% of pairs above 0.8 Jaccard and
      did not fire, so MinHash/LSH stays unimplemented; the near-duplication this corpus
      actually has is keyed on event number, and `keyed_dedup.py` removes it: 4,521
      superseded revisions, measured. Exact dedup removed a further 5,816 documents.*

*Correction, 2026-09-16: why S3 is not better than S2.* Both rungs spent **10,027,008
training tokens** (4,896 windows of 2,048). Any reading of the ordering as "the larger rung
saw fewer tokens", or as a difference in how undertrained each was, is **withdrawn**. What
the record supports: at about 10M tokens both rungs are far to the left of any balance
point between model size and tokens. S2 saw 0.98 tokens per parameter and S3 0.50, against
the roughly 20 of the compute-optimal literature. In that regime a larger model is less
sample-efficient per token. **The S2-S3 ordering carries no scaling information, and a
ladder over a corpus of about 10M tokens cannot demonstrate scaling.**

*Curves, 2026-09-16 (`reports/data/text_pretrain_curves_v1_20260916.md`, read from the
pretraining record, nothing retrained).* Terminal slope over the last full interval (steps
125 to 150): S2 -0.0279, **S3 -0.0308** nats per million tokens, so S3's is 1.10 times
steeper. One seed each. The curves already crossed once: S3 was below S2 up to 3.3M tokens
and above it from 4.9M. **Whether S3 would cross back is open.** Both slopes were read at a
learning rate decayed to 0.1 of its peak, so no crossover is extrapolated.

**One limitation carried into M3, stated once.** The configured capacities are sized for a
corpus several times larger than the licence-clean route could produce. That one fact shows
up in three places, and they are not three separate limitations:

- the model ladder cannot show scaling at 10.0M training tokens (above);
- **77.47%** of the tokenizer's vocabulary (25,387 of 32,768 ids) is seen fewer than 100
  times;
- the **32,768-id text region** (ADR-0003 v2) is oversized for this corpus.

The corpus is 8.05M words, **26.8% of the 30M floor**, which is 3.7 times what was
produced. The capacities are frozen (ADR-0003), so this is carried, not fixed.

---

## M3 — joint model, modality shift, streaming demonstration

**Hypothesis under test**

> **H3.** Pretraining on the operator-narrative corpus improves cross-OEM transfer of
> status semantics under leave-site-out evaluation, relative to the same joint
> architecture with the narrative pretraining ablated. (ADR-0007.)

> **H3 — WITHDRAWN 2026-09-16, on evidence, not deferred.** Three measured counts: Hill of
> Towie **0/693** narrow events map to either side of the split, CARE **0/45**, and the
> training sites' high-overlap side holds **2** event types. The lenient Hill of Towie
> mapping (the last described alarm before the event) is rejected: it names a fault after
> whichever generator alarm fired last. **Negative result, recorded as a deliverable:** the
> premise that a nuclear/pipeline narrative corpus supplies wind-turbine status vocabulary
> is false at the lexical level. PHMSA's 1,969,035 training tokens moved zero wind-specific
> words (29 code-book word types stay absent). ADR-0007's decision is kept and its
> justification replaced; the full record is under "H3 withdrawn" in ADR-0007. The residual
> question, whether convention or vocabulary is the barrier, is H3' (ADR-0017), and it
> needs no training.
>
> **H3' Stage A, 2026-09-16:** lowercased after a space with the frozen tokenizer, **80/264**
> status strings have every token frequent (raw 18). That is above the pre-registered 50, so
> surface convention is confirmed as the dominant barrier. 45 of the 60 first-token failures
> are fixed, and chars/token goes from 4.15 to 4.82, inside the narrative 4.63-5.29. Equal to
> the word-level 80 by count but not by set (72 shared). The residual 184 is 176
> vocabulary-absent plus 8 below the word level (ADR-0017).
>
> **H3' restated, 2026-09-16 (ADR-0017 amendment).** Token-level coverage is withdrawn as
> the metric, because it cannot fail for an absent word (INSTRUMENT_AUDIT entry 11). The "62
> blocked by convention" decomposition is **withdrawn**: the measured change is 67 gained and
> 5 lost, and the mechanism is the word-initial leading space (18 to 63) more than casing (18
> to 32). H3' is now behavioural. Normalization is the treatment, and the per-string NLL
> difference under the text-only checkpoints is the effect size: **-5.33 nats/string at S2,
> -5.67 at S3** (`<sep>` context, 95% intervals exclude 0). The leading space alone gives
> -3.72 and lowercase alone -1.64. Strings with an absent word stay at 2.64 nats/byte
> normalized, against 1.26 for held-out narrative text
> (`reports/data/h3prime_behavioural_v1_20260916.md`).

*The record below is kept as it was written before the withdrawal.*

H3 exists because ADR-0007 routes SCADA status messages through the BPE text pathway
instead of a per-OEM code book. That choice only pays off if narrative pretraining
transfers meaning across manufacturers, so the choice and the hypothesis are tested
together: **larger** held-out-site advantage on event types whose status strings share
vocabulary with the narrative corpus than on those that do not. A flat difference
falsifies H3 and supersedes ADR-0007.

*Pre-M3 measurement, 2026-09-16 (full record under H3 in ADR-0007).* Against the NRC-only
training split, 31 code-book word types are absent from the narrative corpus
(`yaw, nacelle, anemometer, drivetrain, winddirection, bladeangle, …`), and only 76 of
the 264 status strings have every word seen at least 100 times. The gap is
wind-specific, not generic. The corpus is nuclear, and since 2026-09-16 nuclear plus
pipeline. A flat H3 result has to be read against this gap before it is attributed to
the text pathway. The split is re-measured against the M2c training corpus in the
Gate 6 report.

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

H1 and H2 are reserved for the two claims the project already carries — that the joint
model beats both single-modality baselines, and that calibrated abstention degrades
gracefully under modality shift. They are stated as milestone criteria below rather
than as numbered hypotheses, and will be written out as H1 and H2 when there are M1
results to phrase them against.

> **H1 — UNTESTED as of 2026-09-13.** The M1e ladder was the first run that could have
> borne on it and does not: no risk arm trained on enough positives to separate a
> representation from a starved head, so the ladder is evidence neither for H1 nor
> against it. The pretraining ablation is **INCONCLUSIVE** for the same reason — its
> control sat pinned at the prior for most of training. Neither may be cited as a
> negative result. M3 step 0 is the pre-registered remedy and runs before any joint
> model; H1 is written out as a numbered hypothesis when a risk run exists whose control
> arm demonstrably trained.

**Work**

- **Step 0 — positive-aware risk training, before any joint work.** *Implemented and
  fixture-tested 2026-09-16, NOT RUN (`configs/train/telemetry_v1.yaml`,
  `PositiveAwareRiskStage`, `BalancedWindowSampler`, `prior_correction`). Balanced sampling
  at a positive fraction of 0.5, not `pos_weight`: 16,524 of 749,387 stride-6 training
  windows are positive (2.21%), so `pos_weight` would need about 725,000 windows per arm to
  show a head 16,000 positives. Budgets are 16,000 positives seen per arm (32,000 windows).
  The probe learning rate is 2e-3, against 5e-4 for the fine-tune and the control. The
  provenance of every value is in the YAML. **The prior correction is part of the method
  (ADR-0019, 2026-09-16):** logits move by `logit(pi_true) - logit(pi_train)` before any
  calibration metric or abstention threshold, and `faultline.evaluation.calibration` refuses
  uncorrected scores. On a held-out set at the natural prior, a balanced head recovers the
  base rate: 3.07% predicted against 2.89% true, where uncorrected it reads 13.8%. Originally "not started";
  recorded 2026-09-13 from the M1e re-reading above, which left H1 UNTESTED and the
  pretraining ablation INCONCLUSIVE because no risk arm trained on enough positives to
  say otherwise.* Three changes, all pre-registered here rather than chosen once numbers
  exist:
  - **The loss becomes positive-aware** — `pos_weight` on the BCE, or balanced sampling
    of the training windows. The arm that is chosen and the value it takes are recorded
    before the runs; `positive_weight` is already a config knob and already defaults to
    1.0 by an explicit decision, so this supersedes that default rather than discovering
    it.
  - **The risk budget is sized in positives seen, not optimiser steps.** 1,250 steps at
    32 windows bought 882 positives; a budget stated in steps hides that, and a budget
    stated in positives cannot. The window budget is derived from the positive target
    and the measured base rate, and both go in the run config.
  - **The frozen probe gets its own learning rate**, separate from the fine-tune's. M1e
    pre-registered one shared rate and reported the cost as limitation (a); with the
    control now known to have sat on the prior, a shared rate is no longer the
    conservative choice it was argued to be. Each arm's rate is fixed before the runs so
    the ablation stays a comparison of initialisation and not of tuning effort.

  **Done when** the control arm moves off the prior — measured, not assumed: no run may
  report a validation AUPRC series pinned at the selection subsample's base rate. Until
  it does, H1 stays UNTESTED and no pretraining claim is made in either direction.
- Concatenate the M1 and M2 vocabularies per ADR-0003; no retokenization.
  *Verified 2026-09-16 (`faultline check joint-vocab`): all 14 assertions pass, ADR-0003
  stands.*
- **Mixture (ADR-0018), shards written 2026-09-16, nothing trained.** Three streams: `tel`,
  `txt` (nuclear/pipeline text, NOT paired with wind telemetry) and `tel+status` (the only
  paired signal; normalized strings by default, raw as the ablation). Arms `joint`,
  `joint_status_raw` and `tel_only`, each 50,000,000 tokens seen. Ratio 30/20/50, so no stream
  repeats (`txt` one pass). GPU-hours are an observation.
- **Before the full run, 2026-09-16 (M3 pre-run brief).** *Resource ruling:* all three arms
  at S2 only, a rung fixed for comparability, not performance; S3 on `joint` alone and only if
  budget remains. The 8.5 GPU-hours an arm projection is wrong by about 50 times. It came from
  M2 runs at micro-batch 16, which spill out of 8 GB. At 4 x 8 an S2 arm trains at 89,817
  tokens/s (ADR-0018 rulings). *Hypothesis, not a finding:* S3 better than S2 to 3.3M tokens
  and worse from 4.9M runs backwards for an undertrained pair. The ordinary cause is a peak rate
  tuned at S2 being too high for S3, so the text rungs may not be comparable for a reason
  separate from corpus size. *Held-out gap:* 275 Hill of Towie status messages are not written
  (step absent from the final rows), recorded on the card. *Seed-variance probe (ADR-0020):*
  `tel_only` twice at half budget. If the Hill of Towie test AUPRC gap between seeds is at or
  above **0.010**, the design becomes two arms (`joint`, `tel_only`) at three seeds.
  **Outcome:** the gap is **0.0080**, below the line, so the three-arm design stands (seeds:
  0.0353 and 0.0433; 0.38 GPU-hours for both). It is one draw at 80% of the line, and it
  implies one-seed arm differences carry about 0.010 of seed noise. On Kelmarsh the gap was
  0.0173 (ADR-0020 outcome).
- **The E0-E5 ruling, 2026-09-16.** The probe PASSED under `33c5ab4`'s line, and the pass is
  not load-bearing: both seeds are within 0.0100 AUPRC of chance, 0.010 is 30% of the base rate,
  and no within-seed interval exists (ADR-0020 ruling). *Held-out-site gate, pre-registered
  (ADR-0021):* `tel_only` at full budget, one seed. Hill of Towie is EVALUABLE only if the lower
  bound of a 48-hour block-bootstrap interval on its AUPRC is above its base rate, 0.03325.
  Otherwise leave-site-out becomes a reported negative result, and CARE or a temporal holdout
  at the training sites becomes primary.
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
- [x] ~~**H3 tested, with the narrative-pretraining ablation actually run** — reported
      whichever way it comes out, and ADR-0007 superseded if it comes out flat.~~
      *Withdrawn 2026-09-16, not met: H3 was withdrawn on evidence before M3 training
      (above). ADR-0007 keeps its decision with a replaced justification. The negative
      result stands as this criterion's deliverable.*

---

## M4 — paper readiness (**Phase B: after the final-exam defense**)

**This milestone does not start during Phase A.** No item below is begun, scoped or
prototyped while M1, M2 or M3 are open, and no M4 item is ever added to an M1, M2 or M3
checklist. Its commits are never mixed into Phase A history: M4 work begins after the
defense, on its own commits, and a Phase A commit that carries an M4 item is a mistake to
be split rather than a head start.

**Target and framing.** *Wind Energy Science* (Copernicus), with Wiley *Wind Energy* as
the fallback, and arXiv on the day of submission rather than before it.

The claim is **the harmonisation protocol and the convention-versus-physics findings**,
not the model. Datums are conventions and are harmonised across sites; physics is not
harmonised, and the difference between sites is what the held-out evaluation measures
(ADR-0012, ADR-0013, ADR-0014, ADR-0015). The pitch datum, the per-unit power scale, the
one event rule across four record formats, and what each of them did to the held-out
site's out-of-range shares are the contribution. **The ladder is one row among baselines**,
and on the M1e evidence it is not the best row; the paper says so.

**Work**

- Classical baselines, each on the same windows, splits and labels as the ladder: a
  gradient-boosted tree on window statistics, a 1D convolutional network, an LSTM, an
  autoencoder reconstruction-error detector, and a zero-shot Chronos row.
- Selective prediction: risk–coverage curves, selective AUPRC at fixed coverage, and
  coverage degradation from the training sites to Hill of Towie, under a **declared**
  abstention mechanism — conformal risk control preferred, with a calibration split
  disjoint from both training and test.
- The manuscript itself, in the Copernicus template.

**Done when**

- [ ] Every baseline above is run on the same windows, splits and labels as the ladder,
      and reported in one table with the ladder as a row rather than as the subject.
- [ ] A risk–coverage curve and a selective AUPRC at fixed coverage for every held-out
      site, and the coverage degradation from the training sites to Hill of Towie.
- [ ] The abstention mechanism is declared before the numbers are produced, and its
      calibration split is disjoint from both training and test.
- [ ] Every figure and table regenerates from a config hash and a run id in this
      repository.
- [ ] A manuscript in the Copernicus template, with the harmonisation protocol and the
      convention-versus-physics findings as the claim.
- [ ] arXiv posted on the day of submission, not before.

---

## Explicit non-goals, at every milestone

Not an operations product. Not instruction-tuned. Not tool-calling. No data, code or
time from the author's employer, advisor or funded projects. Public,
licence-documented data only.
