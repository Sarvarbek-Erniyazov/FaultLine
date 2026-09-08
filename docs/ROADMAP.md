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

**Done when**

- [ ] `uv pip install -e ".[dev]"` succeeds and `faultline --help` lists every command.
- [ ] `ruff check`, `mypy --strict src/` and `pytest -q` all pass; tests run in under
      60 seconds and touch no real data and no network.
- [ ] `docs/COURSE_PORT.md` maps every notebook cell to a module, function, config key
      and test, and lists every semantic change with its justification.
- [ ] `faultline text run` on the committed fixture corpus produces
      `reports/data/<run_id>/` with a stats report per stage and a `run.json`.
- [ ] Telemetry stages, adapter discovery, event horizon labelling, split assignment,
      `VocabLayout`, `QuantileBinTokenizer` and `JointVocab` are implemented and unit
      tested on synthetic data.
- [ ] Tier-1 files for all four sources are downloaded and md5-verified, with
      manifests committed under `data/cards/manifests/`.
- [ ] One raw inventory report per source in `reports/data/`, and one dataset card per
      source in `data/cards/`, each answering the free-text question with evidence or
      an explicit `UNVERIFIED`.
- [ ] `tests/test_naming.py` passes; the banned strings appear only in ADR-0002.
- [ ] Remote exists, the `m0` tag is pushed, and no data, secret or file over 5 MB is
      in the history.

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

---

## Explicit non-goals, at every milestone

Not an operations product. Not instruction-tuned. Not tool-calling. No data, code or
time from the author's employer, advisor or funded projects. Public,
licence-documented data only.
