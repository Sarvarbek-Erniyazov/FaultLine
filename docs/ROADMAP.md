# Roadmap

Four milestones. Each has explicit "done when" criteria, because the failure mode of
a solo research project is a milestone that is 80% finished four times over.

The ordering is deliberate: telemetry first (M1) because it carries the decision
endpoint and can be evaluated without any language modelling; text second (M2)
because it runs in lockstep with the author's coursework; joint last (M3) because it
is only interesting once both halves independently work.

---

## M0 — skeleton, pipelines, data staging · **current**

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
      60 seconds and touch no real data and no network. *(322 tests, 2.6 s.)*
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
- [ ] **Remote exists, the `m0` tag is pushed, and no data, secret or file over 5 MB is
      in the history.** *Remote and history are done and verified. The tag is
      deliberately withheld until the staging criterion above is met — tagging a
      milestone that fails one of its own stated criteria is exactly the kind of
      quiet overstatement this project is built to avoid. Tag with:*
      `git tag -a m0 -m "M0: skeleton, pipelines, data staging" && git push --tags`.

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
  exports, and prove the choice loses no values.
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
