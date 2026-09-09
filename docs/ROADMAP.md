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

**Done when** (status as of 2026-09-09)

- [x] `uv pip install -e ".[dev]"` succeeds and `faultline --help` lists every command.
- [x] `ruff check`, `mypy --strict src/` and `pytest -q` all pass; tests run in under
      60 seconds and touch no real data and no network. *(242 tests, 2.1 s.)*
- [x] `docs/COURSE_PORT.md` maps every notebook cell to a module, function, config key
      and test, and lists every semantic change with its justification.
- [x] `faultline text run` on the committed fixture corpus produces
      `reports/data/<run_id>/` with a stats report per stage and a `run.json`.
- [x] Telemetry stages, adapter discovery, event horizon labelling, split assignment,
      `VocabLayout`, `QuantileBinTokenizer` and `JointVocab` are implemented and unit
      tested on synthetic data.
- [ ] **Tier-1 files for all four sources downloaded and md5-verified.** *Partial:
      Kelmarsh (11/11, 3.69 GB) and Penmanshiel (8/16, 1.65 GB) are staged and
      verified; Hill of Towie and CARE have not started. Zenodo was unavailable for
      long stretches of the staging window — two separate outages returning HTTP 504
      and then connection timeouts, including on its own front page. The downloader is
      resumable and skips verified files, so finishing is one command:*
      `faultline download telemetry --tier 1 --attempts 60`.
- [x] One raw inventory report per source in `reports/data/`, and one dataset card per
      source in `data/cards/`. *Kelmarsh and Penmanshiel answer the free-text question
      with evidence (`VERIFIED no`, a controlled vocabulary); Hill of Towie and CARE
      are explicitly `UNVERIFIED` because nothing is staged to inspect.*
- [x] `tests/test_naming.py` passes; the banned strings appear only in ADR-0002.
- [ ] **Remote exists, the `m0` tag is pushed, and no data, secret or file over 5 MB is
      in the history.** *Remote and history are done and verified. The tag is
      deliberately withheld until the staging criterion above is met — tagging a
      milestone that fails one of its own stated criteria is exactly the kind of
      quiet overstatement this project is built to avoid. Tag with:*
      `git tag -a m0 -m "M0: skeleton, pipelines, data staging" && git push --tags`.

**Beyond the original M0 scope, because the evidence allowed it:** the Kelmarsh
adapter's loaders are implemented and tested against a committed excerpt of the real
archive, and its channel map is resolved (12 of 13 channels, cross-checked against
the provider signal mapping). Both were scheduled for M1.

---

## M1 — telemetry-only model and risk evaluation

The first real result. A decoder-only transformer over telemetry tokens alone,
trained from scratch, evaluated as a risk model rather than a forecaster.

**Work**

- Implement the source adapters' loaders against the M0 inventory evidence; fill the
  channel maps from the provider signal-mapping files.
- Resolve every `TODO(m1)` in the configs — plausibility bounds, timezones, fault
  code mappings, split dates — against the stats reports, and freeze the result as
  `telemetry_v1.yaml`.
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
