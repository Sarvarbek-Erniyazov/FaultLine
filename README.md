# FaultLine

**A from-scratch joint telemetry–text sequence model for wind-turbine event risk, built and evaluated as a pre-registered study on one 8 GB GPU.**

FaultLine asks a narrow question and answers it with a full pipeline: does pretraining a small decoder-only transformer over quantised SCADA telemetry — alone, or jointly with operator text — produce a representation from which a frozen linear probe can read the risk of a fault event in the next 24 hours, and does that reading survive a change of site, of manufacturer, or of time? Every component was written for this repository: the data pipeline, the telemetry tokenizer, the byte-level BPE, the transformer, the training loop, the evaluation harness. Every evaluation rule was registered in `docs/DECISIONS.md` and committed *before* the run it governs, with the registering commit's hash recorded beside the outcome.

The result is a set of measured answers, several of them negative, each with its rule, its interval and its control. That is the deliverable.

---

## Status

**Experimental programme closed (2026-09-20).** Six pre-registered gates were run (ADR-0021 → ADR-0026). The final test (F7′, ADR-0026) **passed its instrument control nine of nine and returned H1′ SUPPORTED**: read with a text-aware linear head, the joint model beats the telemetry-only model by +0.017 to +0.023 AUPRC on every seed. ADR-0026 §1 withdrew two backbone ablations (`joint_status_raw`, `joint_no_txt`); H1′'s outcome makes them revisitable under a new registration against a named write-up sentence, and nothing in the record schedules a run. Nothing in this repository is a deployed system.

Total GPU cost of the runs that wrote a timing sidecar beside their checkpoints: **12.6 GPU-hours** on a single NVIDIA RTX 4060 (8 GB), over 98 records in eleven run directories. That is a floor for the programme, not its total: the telemetry ladder, the text pretraining and the order-blind comparators wrote no sidecar and are timed only in their own reports under `reports/data/`.

---

## What was built

| stage | what it is | where |
|---|---|---|
| Data pipeline | Four public SCADA sources → canonical long-format schema → cleaning, plausibility bounds, gap handling, imputation with missingness masks → site/time splits with a leakage check. Text: cleaning, filtering, exact and near-duplicate detection, PII policy per corpus. Every stage writes a stats report. | `src/faultline/data/`, `reports/data/` |
| Telemetry tokenizer | 12 core channels at 10-minute resolution, each quantised to 256 bins: point masses carved out, 16 fixed-width bins per tail at the training p0.5/p99.5, quantile bins over the centre. Fitted on the training split only. One step = `<sep>` + 12 bin tokens = 13 tokens; a 24 h window = 144 steps = 1,872 tokens. | `src/faultline/tokenizers/` |
| Text tokenizer | Byte-level BPE, 32,768 merges, trained by this repository's own implementation on a public-domain corpus of US federal incident narratives (NRC event reports and licensee event reports, PHMSA pipeline incident narratives; ~10.0M training tokens). | `src/faultline/tokenizers/text_bpe.py` |
| Joint vocabulary | Fixed-capacity blocks so telemetry ids never move: specials [0, 32) · channel [32, 96) · bin [96, 1120) · time [1120, 1184) · text [1184, 33952). 33,952 ids. | ADR-0003 |
| Model | Decoder-only causal transformer: RMSNorm, GELU MLP at 4×, tied output head, learned positions, no dropout. A four-rung ladder (S0–S3: 0.31M / 1.18M / 3.54M / 9.96M backbone parameters). **S2 — 8 layers, d_model 192, 8 heads — is the rung every result below uses**, fixed for comparability across arms rather than selected for performance; the rung's geometry is `ladder_v0.yaml`'s. Two context lengths, and the difference is load-bearing. The ladder's own context is `ladder_v0.yaml`'s `context_steps: 144`, 144 × 13 = **1,872 tokens**, one 24 h telemetry window and nothing else. Every M3 run trains and probes at the **2,048 tokens** of `configs/train/joint_v1.yaml` (`context_tokens`), and the 176-token difference is the room the status text has in the `tail_anchored_2048` probe window: past it, whole leading telemetry steps are dropped. | `src/faultline/model/`, `configs/model/ladder_v0.yaml` (geometry, 1,872), `configs/train/joint_v1.yaml` (2,048) |
| Pretraining | Next-token prediction, AdamW, cosine schedule, bf16. Each arm sees exactly 50,003,968 tokens; GPU-hours are observed, never the budget. Fail-fast guard on the first batch's loss against ln(V). | `src/faultline/training/` |
| Risk probe | A linear head on the frozen backbone's last-position state, trained with balanced sampling and an explicit prior correction so that probabilities are recoverable at the natural base rate. Fixed final-step checkpoint (the validation split was shown unable to rank checkpoints). | `src/faultline/model/risk.py` |
| Evaluation | AUPRC with a two-day block bootstrap (10,000 replicates); **paired** bootstrap for every model-vs-model comparison; a random-initialisation control for every probe design; an order-blind bag-of-tokens comparator; pre-registered pass/fail rules with hashes. | `src/faultline/evaluation/`, `docs/DECISIONS.md` |
| Instrument audit | Thirteen recorded cases where an evaluation instrument, not the model, was the defect — each with its counterfactual. | `docs/INSTRUMENT_AUDIT.md` |

---

## Data

All data is public and licence-documented; raw files are never committed, but download manifests with checksums, dataset cards and every stats report are.

| source | provider · licence | role | turbines · OEM |
|---|---|---|---|
| Kelmarsh | Cubico · CC BY 4.0 | training / validation / forward-in-time test | 6 · Senvion MM92 |
| Penmanshiel | Cubico · CC BY 4.0 | training / validation / forward-in-time test | 14 · Senvion MM82 |
| Hill of Towie | RES/TRIG · CC BY 4.0 | held-out site (same country, different OEM) | 21 · Siemens SWT-2.3-82 |
| CARE | Fraunhofer IEE · CC BY-SA 4.0 | held-out cross-OEM evaluation (anonymised, 3 farms) | 36 · undisclosed |

Splits are by time: training 2016–2020, validation 2021, test 2022–2024 at Kelmarsh and 2022 at Penmanshiel, whose test shard holds no later year. The training stream is 61.6M telemetry tokens ≈ 4.74M ten-minute steps ≈ 90 turbine-years. Labels are "a fault event starts within the next 24 hours", derived from provider stop records; the test base rate is 0.0388, 1.8× the training rate — a recorded temporal shift. The status-message code books (217 distinct strings at Kelmarsh, 231 at Penmanshiel) are the only paired text; the narrative corpus is unpaired. Two facts about the data shaped the design and are stated in ADR-0001: public SCADA event logs are template strings, not language, and no public wind source pairs telemetry with free text.

---

## How the study was run

Every gate below follows the same discipline: the rule is written into `docs/DECISIONS.md` and committed in its own commit; the run happens; the outcome is written under the rule with the registering hash; nothing is re-worded after the numbers exist. Where a registered rule turned out to be mis-specified (it happened twice), the original verdict stands on record and a replacement is registered under a new number with the reason stated.

Three controls carry the weight. The **random-initialisation control** trains the identical probe on an untrained backbone at the same size; a probe that cannot separate trained from random cannot measure anything about pretraining. The **paired block bootstrap** compares two models on the same resampled blocks, because independent intervals on a shared test set are a known-bad test of a difference. The **order-blind comparator** — logistic regression on the token histogram of a window — asks whether the sequence model beats a classifier that ignores order.

---

## Findings

### 1. Site shift: two pre-registered negatives, with attribution

**Hill of Towie** (Siemens, held out). Rule ADR-0021: the block-bootstrap 95% lower bound must exceed the site's base rate (0.03325). Seed 1: AUPRC 0.0393 [0.0306, 0.0553] — not evaluable. Three seeds: 0.0390, 0.0510, 0.0359; one clears. The site is marginal, not null, and the verdict is the same under the one-seed and the two-of-three rule.

**CARE** (three anonymised farms, other OEMs). Rule ADR-0022, same criterion at CARE's own base rate 0.00125, scored on 430,506 windows holding all 45 labelled events. Pooled AUPRC 0.0012–0.0015 on every seed and checkpoint, 0.0008–0.0018 on the per-farm rows; every interval contains its own base rate; discarded-replicate share 0.00% on the pooled rows the rule reads, 0.11% at worst per farm. At chance.

**Attribution** (ADR-0022 F6-0). Imposing each CARE farm's missing-channel pattern on the *training-site* test split leaves the probe above base rate on 3 of 3 seeds for all three patterns — the channel gaps do not explain the null. The order-blind comparator is also at chance on CARE. The null is a property of the token stream across manufacturers: quantile bins fitted on one OEM's distribution do not carry to another's. Neither the backbone nor the channel gaps are the cause.

**Consequence.** The only evaluable axis is the forward-in-time split at the training sites (all three seeds clear 0.0388). Every result below is forward-in-time, same sites, and none is a site-shift result.

### 2. The probe sees the backbone — and pretraining buys about a quarter of the base rate

Paired Δ(trained − random-init), pooled forward-in-time test split, three pretraining seeds × three init seeds: nine of nine lower bounds above zero; Δ = +0.009 to +0.019 AUPRC against a base rate of 0.0388 (ADR-0024). Untrained backbones already read 0.039–0.042; trained backbones 0.051–0.058. Fifty million tokens of telemetry pretraining moves a frozen linear probe by a quarter to a half of the base rate.

### 3. Telemetry-only: the sequence model is at parity with a bag of tokens

Paired Δ(probe − order-blind comparator) on three seeds: +0.0016 [−0.0059, +0.0084], +0.0053 [−0.0017, +0.0128], −0.0015 [−0.0094, +0.0053]. On this stream, at this size and budget, the pretrained sequence model does not measurably beat a classifier that ignores token order.

### 4. The status text carries risk signal — and the read-out, not the model, was the limit

An order-blind classifier on the window's **status strings alone** scores **0.0725 [0.0537, 0.0979]** on the forward-in-time test windows — above every telemetry probe of either arm — with the whole gain inside windows that have text; removing provider "Stop" rows halves it (the recurrence channel).

**H1** (ADR-0025): the joint arm (telemetry 0.30 · narrative 0.20 · telemetry-with-status 0.50, same S2, same 50M-token budget, three seeds) against telemetry-only, same-seed paired Δ, smallest effect of interest 0.005: **+0.0022 [−0.0034, +0.0068], −0.0022 [−0.0084, +0.0021], −0.0018 [−0.0060, +0.0021] — INCONCLUSIVE.** No effect detectable; any effect below about 0.007 AUPRC. The decomposition explained why: the joint window *costs* the telemetry-only backbone −0.008 to −0.012 (less telemetry fits, and text it cannot read), joint pretraining recovers +0.006 to +0.014 at identical input, and the two cancel. The registered read-out was a linear head on the **last position** — a telemetry bin token — with status messages attached to earlier steps.

**H1′** (ADR-0026): the same frozen joint backbones, no further pretraining, read with a text-aware linear head — the last-position state concatenated with the mean over text-token positions and a has-text indicator. Registered with a random-initialisation gate on the new instrument, because a bag of text embeddings through an *untrained* backbone might already read the strings.

- **Gate: PASS, nine of nine** paired lower bounds above zero (weakest +0.0058), so what the read-out harvests is **not only the tokens' embeddings**. The level, though, is largely theirs: an *untrained* backbone read with the same head scores 0.0581 / 0.0575 / 0.0547 — at or above the trained telemetry-only probe — and pretraining adds +0.0103 to +0.0263 on top of that.
- **H1′: SUPPORTED.** Paired Δ against telemetry-only: **+0.0200 [+0.0112, +0.0294], +0.0234 [+0.0128, +0.0342], +0.0170 [+0.0111, +0.0232]**; median +0.0200, four times the smallest effect of interest.
- Joint pretraining still matters once the text has a direct path: Δ against the telemetry-only backbone under the same read-out is +0.0271 / +0.0285 / +0.0267, every interval above zero. A telemetry-only backbone reads the text no better than an untrained one, and on two of three seeds measurably worse (−0.0072, −0.0050 [−0.0110, +0.0007], −0.0129). F6-R's measurement that its 32,768 text embedding rows had collapsed onto one shared vector is the plausible explanation; this test does not establish it.
- The gain is where the text is: has-status strata +0.0252 / +0.0260 / +0.0145, no-status strata inconsistent in sign. Mean-pooling alone does not do it (−0.0026 / +0.0100 / +0.0094): the text block is what moves the read-out.
- **Against the cheap baseline, it is parity, not victory.** Paired Δ against the order-blind status-only classifier: +0.0055 [−0.0173, +0.0241], +0.0085 [−0.0141, +0.0265], −0.0040 [−0.0264, +0.0125] — all three span zero.

So: the text carries the signal, the joint model's representation encodes it beyond what the tokens alone supply, a text-aware linear read-out reaches it — and the end-to-end result lands level with a classifier that counts the strings. H1's INCONCLUSIVE stands as a verdict about the arm *read through the last-position instrument*; H1′ is the same hypothesis re-tested with an instrument that can see, registered as such after H1's result was known.

### 5. Graceful degradation, first rows (H2, forward-in-time)

Dropping one to three core channels at inference costs the joint probe at most 0.0085 AUPRC — about half its lift over base rate on the seed where that worst case falls, and an eighth or less on the other two. Coverage and selective-risk curves are not yet implemented and are not claimed.

### 6. Text-side findings

Normalising status strings to prose surface form (lowercase, leading space) lowers their negative log-likelihood under the narrative-pretrained model by 5.33 nats; the two mechanisms are additive (ADR-0017). Of 246 strings not fully covered by the BPE vocabulary, 62 are blocked by surface convention and 184 by genuine domain absence — narrative pretraining supplies no wind vocabulary, and the cross-OEM transfer hypothesis H3 was withdrawn on that measured evidence. A scaling ladder over a ~10M-token text corpus cannot demonstrate scaling (S3 < S2 at equal tokens, both undertrained); recorded, not re-run.

### 7. What the instrument audit found

Thirteen entries. Among them: the first probe-control criterion required non-overlap of two independent intervals, which cannot pass for a paired comparison — replaced by the paired test, original FAILs retained; the validation split (117 positives) cannot rank probe checkpoints, so the untrained head sits inside every selection interval — fixed-final-step selection adopted under a registered criterion; the "20 tokens per parameter" heuristic was carried as a planning assumption that never entered the record; a pre-registered attribution clause named one farm where the measurement was made on three.

---

## What is open

- The only evaluable evaluation axis is forward-in-time at the training sites. Site shift returned two pre-registered negatives, and no result here is a site-shift result.
- The joint model at parity with an order-blind classifier on the status strings (B4) is the honest ceiling of the current design. Beating it is the next research question, not a claim this record supports.
- Coverage and selective risk — the "calibrated abstention" endpoint — have a prior correction and a threshold function but no risk–coverage harness. H2 has its first rows (channel dropout, ≤0.009 AUPRC) and nothing more.
- The cross-OEM null is a tokenizer-level finding: quantile bins fitted on one manufacturer's distribution do not carry to another's. Per-site or rank-based bin fitting is the indicated next design, untried here.
- Seed variance on the forward-in-time split equals one seed's interval half-width; ~0.005 AUPRC is the smallest difference this evaluation can resolve, and every claim above is sized to that.
- Two withdrawn ablations (`joint_status_raw`, `joint_no_txt`) are revisitable: they would test whether raw status casing and the unpaired narrative corpus contribute anything. ADR-0026 §1 withdrew them and admits them back on one condition only, that H1′ be SUPPORTED — which it is; the outcome section adds the second, that revisiting them is a new registration against a named write-up sentence under §5, and records that nothing schedules a run. §1's rationale — that an instrument which cannot read the text cannot discriminate between backbones that differ in their text — implies such a registration would read them through the H1′ read-out; that inference is not itself registered.

## Reproducing the record

```
pip install -e ".[dev]"
faultline --help
scripts/gates.sh            # ruff, ruff format, mypy --strict, pytest, naming, untracked-files
```

Raw data is downloaded from the pinned Zenodo records in `configs/data/sources_telemetry.yaml` (≈20 GB, md5-verified). Every run reads one YAML, copies it with its hash into its report directory, and is resumable by output markers. Every number in this README is in a tracked file under `reports/data/` or `docs/DECISIONS.md` — with one exception, the GPU-hours floor above, which sums timing sidecars under `checkpoints/`, a directory that is not committed — and the commit that registered each rule is named beside its outcome.

Repository layout: `configs/` (one file per run, never edited after), `src/faultline/` (package), `tests/` (mirrors `src/`), `reports/data/` (stats reports, gate reports, per-step training logs), `docs/` (`DECISIONS.md`, `INSTRUMENT_AUDIT.md`, `ROADMAP.md`, `PROVENANCE.md`, `DATA_LICENSES.md`, `COURSE_PORT.md`), `data/cards/` (dataset cards and checksum manifests).

---

## Provenance and independence

Built by one person on personal hardware and personal time, from public, licence-documented data only, with no data, code or deliverables from any employer, advisor or grant project. `docs/PROVENANCE.md` states this in full, with a table contrasting FaultLine with the author's other work. A naming gate enforces the separation mechanically.

The text-pipeline discipline (clean → filter → dedup → PII → report) was ported from an LLM-engineering course reference and applied to an original domain; `docs/COURSE_PORT.md` maps every ported cell to its module and test.

## Licence and citation

Code: MIT. Data: per-source licences in `docs/DATA_LICENSES.md` (CARE is share-alike; only cards, manifests and statistics are redistributed). Cite via `CITATION.cff`.
