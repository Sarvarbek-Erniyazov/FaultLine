# A from-scratch telemetry–text language model for wind-turbine fault prediction does not beat time since the last fault: a pre-registered, controlled study

**Sarvarbek Erniyazov**

Research summary for expert review — the canonical record is [docs/DECISIONS.md](DECISIONS.md)

Written against commit `0468f1f` · 2026-09-27 · Repository: <https://github.com/Sarvarbek-Erniyazov/FaultLine>

*Conventions.* AUPRC is step-wise average precision. Brackets hold a 95% two-day block-bootstrap percentile interval (10,000 replicates, seed 20260916). π is the scored split's positive rate, which is the AUPRC of a no-signal scorer. "Seed" is the pretraining seed unless stated otherwise. Every model-versus-model comparison is a same-row paired Δ. Verdict words are those of `docs/DECISIONS.md`.

---

## 1. Summary

FaultLine is a controlled study of what a small decoder-only transformer, pretrained from scratch on one 8 GB GPU, encodes about the risk of a technical stop in the next 24 hours. It is pretrained on quantised 10-minute SCADA telemetry, wind-turbine status strings and an unpaired corpus of US federal incident narratives, every component written in-repo, and read by a one-hidden-layer probe on the frozen backbone on a forward-in-time split. Eight gates were committed before their runs. Every comparison is paired, three-seeded and set beside random-init and order-blind controls. After the programme closed, an exploratory record (ADR-0029) supplied two things the registrations lacked: a persistence baseline, and the anemometer-excluded label variant that ADR-0009 had required.

Four results matter. (i) **The model does not beat time since the last fault.** Like for like, a check for an event start in the model's own 24 h window (P1) beats the text-aware joint read-out on the registered label and is level with it under the variant. The hours since the last event start, looking back up to 720 h (P2), beats it on both labels. (ii) The status text is invisible through a last-position read-out (H1 INCONCLUSIVE). Through a text-aware one, H1′ is SUPPORTED on the registered label; INCONCLUSIVE under the ADR-0009 anemometer-excluded variant (ADR-0029, exploratory). What it recovers matches an order-blind count of the strings on the registered label and falls below it under the variant. (iii) One defect-message cluster, `anemometer defect`, carries much of the test period's excess event rate and much of the probabilities' apparent under-read. (iv) Neither site-shift axis is evaluable. Pretraining is visible to the probe (9/9 paired intervals above zero), yet the telemetry model is at parity with an order-blind bag of tokens.

### Findings at a glance

*Exploratory* rows come from ADR-0029, which re-decides no verdict. The variant (π = 0.0243, 3,330 of 137,016 windows) drops the events `anemometer defect` opens.

| finding | key number (95% interval) | verdict | ADR |
|---|---|---|---|
| P1, event start in (t − 24 h, t]: 24 h look-back, the model's own (like-for-like) | registered label: 0.1262 [0.1024, 0.1528]; Δ(P1 − joint (d)) +0.0451 to +0.0577, all above 0. Variant: 0.0625 [0.0463, 0.0821]; every Δ spans 0 | beats joint (d); level under the variant (*exploratory*) | 0029 |
| P2, −hours since the last event start: look-back up to 720 h (strongest) | registered label: 0.2211 [0.1862, 0.2582]; Δ +0.1400 to +0.1526. Variant: 0.0944 [0.0735, 0.1189]; Δ +0.0312 to +0.0430, all above 0 | beats joint (d) on both labels (*exploratory*) | 0029 |
| H1′: joint through text-aware read-out (d) against `tel_only` (a) (registered after H1's result) | Δ +0.0200 [+0.0112, +0.0294], +0.0234 [+0.0128, +0.0342], +0.0170 [+0.0111, +0.0232]; instrument gate 9/9. Variant: seed 2 +0.0031 [−0.0076, +0.0116] | **SUPPORTED** on the registered label; **INCONCLUSIVE** under the ADR-0009 anemometer-excluded variant (ADR-0029, exploratory) | 0026, 0029 |
| H1: joint against `tel_only`, last-position read-out (a) | Δ +0.0022 [−0.0034, +0.0068], −0.0022 [−0.0084, +0.0021], −0.0018 [−0.0060, +0.0021] | **INCONCLUSIVE** (variant: same) | 0025 |
| Joint (d) against an order-blind status-string count | Δ +0.0055 [−0.0173, +0.0241], +0.0085 [−0.0141, +0.0265], −0.0040 [−0.0264, +0.0125]. Variant: −0.0187, −0.0305 [−0.0635, −0.0058], −0.0299 [−0.0641, −0.0050] | parity on the registered label; below the count under the variant, excluding 0 on seeds 2 and 3 (*exploratory*) | 0026, 0029 |
| Calibration and the defect cluster | mean p 0.019–0.022; ECE 0.016–0.019 against π = 0.0388. Variant: π = 0.0243, ECE 0.004–0.005 | under-read about half on the registered label; about a tenth to a fifth under the variant (*exploratory*) | 0028, 0029 |
| Graceful degradation under channel loss (H2) | at k = 8: Δcoverage −0.0797 [−0.0841, −0.0753], Δselective risk +0.0053 [+0.0033, +0.0074] | **INCONCLUSIVE** (Gate A **PASS**; variant: same) | 0028 |
| Site shift: Hill of Towie (held-out site) and CARE (other OEMs) | lower bound clears π on 1 of 3 seeds (π = 0.03325) and on 0 of 3 (π = 0.001254) | **NOT EVALUABLE**, both | 0021, 0022 |
| The frozen probe sees pretraining (telemetry-only) | Δ(trained − random-init), 3 × 3 seed pairs: +0.0092 to +0.0186; lowest lower bound +0.0045 | PASS | 0024 |
| The telemetry model against an order-blind bag of tokens | Δ +0.0016 [−0.0059, +0.0084], +0.0053 [−0.0017, +0.0128], −0.0015 [−0.0094, +0.0053] | parity (reported, not gated) | 0024 |

---

## 2. Problem and motivation

SCADA data are heterogeneous across manufacturers (OEMs) in channels and value distributions. The operator text that public records pair with telemetry is sparse, short and vendor-specific. Kelmarsh publishes 217 distinct status strings and Penmanshiel 231, all Senvion templates with a median length of 5 BPE tokens. Hill of Towie publishes alarm codes, CARE no strings, and no public wind source pairs telemetry with free text (ADR-0001).

Foundation models are proposed for time series [cite] and SCADA [cite], increasingly with text [cite]. These questions come before scale. Does pretraining put anything a frozen probe can read into the representation? Is it more than a token histogram? Does text help, and through which path? Does it beat the event history an operator already holds? Does any of it survive a later period, another site or another OEM?

Everything ran on one NVIDIA GeForce RTX 4060 (8 GB): one small rung (S2, about 10.5M parameters), 50,003,968 tokens per arm and three seeds. Evaluation is forward in time (train 2016–2020, test 2022 onward), because adjacent 10-minute windows are near-copies and a random split measures interpolation.

---

## 3. Method

### 3.1 Task, labels and leakage

**One label rule at every site (ADR-0009).** Every source is reduced to seconds of downtime per turbine and step, split into five causes: technical, environmental, grid, planned and unknown. One function with no source argument (`harmonise.select_events`) turns that into events: consecutive steps holding downtime of the chosen causes, lasting at least 60 s. The primary **narrow** label keeps technical downtime only. Targets come only from stops, and warnings are inputs only. The sites read 13.4, 16.5 and 16.5 narrow events per turbine-year (Kelmarsh, Penmanshiel, Hill of Towie).

**Task.** At window end t, predict `narrow_within_24h`: does a narrow event start in (t, t + 144] steps? A horizon running past the record is unknown, never negative. The input is the 144 steps ending at t (1,872 telemetry tokens).

| split (windows as scored) | windows | positive | π |
|---|---:|---:|---:|
| train, Kelmarsh + Penmanshiel, stride 6 | 749,387 | 16,524 | 0.0221 |
| validation 2021, stride 12 | 85,529 | 1,805 | 0.0211 |
| test 2022+, pooled, stride 12 | 137,025 | 5,312 | 0.0388 |
| · of which Kelmarsh / Penmanshiel | 77,203 / 59,822 | 2,841 / 2,471 | 0.0368 / 0.0413 |
| Hill of Towie, seeded 12,000-window subsample | 12,000 | 399 | 0.03325 |
| CARE, stride 12 (45 events) | 430,506 | 540 | 0.001254 |

The test π is 1.8× the training π. ADR-0009 traces the rise to the message `anemometer defect`, which opens more than one narrow event per turbine-year at both sites from 2021, the year the status export gained two columns. The record reads this as pointing to a reporting or firmware change. Without those events the test π is still 0.0243, and Kelmarsh 2024 stays above training unexplained. The record registers the late split as "a temporal hold-out with a change in what is labelled, not a drift test", and requires results with and without those events. That was done only post hoc, in ADR-0029 (§5.1).

**Leakage rule for status strings (ADR-0025 §3).** A message is attached to the first step at or after its start, rounded *up* to the grid, and labels count only events starting strictly after t. A window ends at step t's last token, so read-through is structurally impossible; the F6-R reconnaissance found no message starting at or after the labelled onset in any window. Earlier `Stop` rows with the labelled event's own code are recurrence, information available at t: 1,060 of 2,841 Kelmarsh and 418 of 2,471 Penmanshiel test positives carry one. The primary read (R0) keeps every row; a reported decomposition (R2) deletes every `Stop` row. 1,088 of 5,312 test positives carry no status token, and 2,081 (39.2%) lose leading steps to the 2,048-token context (§3.4).

### 3.2 Tokenization

**Telemetry.** 12 of 14 canonical channels are *core*: present at both training sites and mappable at Hill of Towie (ADR-0008). Each gets 256 bins fitted on the training split only (`configs/tokenizer/quantile_bins_v2.yaml`): point masses first (≥ 1/256 of values, up to 16), then **4** fixed-width tail bins per side beyond p0.5/p99.5 (v1's 16 were cut under a pre-registered signal), the outermost merged inward to a 0.1% floor, then quantile bins over the centre. Missing values become `<nan>` (id 9). A step is `<sep>` (id 8) plus the 12 core bins in fixed order: 13 tokens.

**The (channel, bin) → id map has no channel term.** The id is **96 + b for every channel**, where b is the bin from that channel's own edges ([joint.py:203](../src/faultline/tokenizers/joint.py#L203); [layout.py:85-86](../src/faultline/tokenizers/layout.py#L85-L86)). The 12 × 256 pairs share ids [96, 352), and position carries the channel, so the decoder uses learned absolute positions. One consequence matters in §5.4: an id means "the b-th interval of this channel's *training-site* distribution", so it carries a different physical value at another OEM.

**Text.** An in-repo byte-level BPE has a vocabulary of 32,768 (256 bytes + 32,512 merges), fitted on the NRC + PHMSA training split (10,043,874 training tokens). Status strings are normalised on the frozen tokenizer (ADR-0017: `" " + s.lower()`). The surviving evidence for that is per-string NLL; a token-coverage count was retired as a metric that cannot fail (audit entry 11).

**Joint vocabulary (ADR-0003 v2): 33,952 ids.** Offsets derive from fixed capacities, never counts in use.

| block | ids | capacity | in use |
|---|---|---:|---|
| specials | [0, 32) | 32 | 11 (`<pad>` 0 … `<txt>` 4, `</txt>` 5, `<sep>` 8, `<nan>` 9, `<mask>` 10) |
| channel | [32, 96) | 64 | 14 defined, none emitted |
| bin | [96, 1120) | 1,024 | 256 (ids 96–351) |
| time | [1120, 1184) | 64 | reserved |
| text | [1184, 33952) | 32,768 | all |

### 3.3 Model and pretraining

**S2** is a decoder-only causal transformer: 8 layers, d_model 192, 8 heads, a 4× GELU MLP, no biases, pre-norm RMSNorm, a tied head, 2,048 learned positions and dropout 0. It has 3,542,208 backbone and 10,454,208 total parameters. A test asserts causality at this specification (atol 1e-6). Each arm trains on next-token loss for exactly **50,003,968 tokens**: 763 steps × 32 windows × 2,048. AdamW, peak 6e-4, 2% warmup, cosine to 0.1×, weight decay 0.1, bf16. An initial-loss guard refuses a first batch outside [ln V − 0.50, ln V + 0.10] of ln 33,952 = 10.4327. The arms are `tel_only` (tel 1.0) and `joint` (tel 0.30 · txt 0.20 · tel+status 0.50), with three seeds each. 50M is the largest round budget under which no stream repeats: txt gets 0.996 passes.

**Why S2.** ADR-0018 fixed all arms at one rung "for comparability, not performance"; one S2 arm's pretraining measured 609.9 s. The text-only ladder gives no reason to go larger: at 10,027,008 tokens each, S3's validation loss was not lower than S2's (6.1977 against 6.1474 nats), and "a ladder over a corpus of about 10M tokens cannot demonstrate scaling". Every model here is undertrained.

### 3.4 Read-outs

The text result changes sign between two read-outs of the same frozen backbones, so this subsection carries the methodological weight.

**The probe.** Every probe read in this summary (not the order-blind classifiers) is a one-hidden-layer probe (RMSNorm → Linear(w→192) → GELU → Linear(192→1)) on the frozen backbone, where w is the read-out's width ([risk.py:111-168](../src/faultline/model/risk.py#L111-L168)); the ADRs call it a "linear head". Probes see 16,000 positives over 1,000 steps under **balanced sampling** at 0.5. The **ADR-0019 prior correction**, z − 3.79, restores the training natural rate. It moves calibration, not AUPRC.

**Fixed final step (ADR-0022 addendum).** The selection split (117 positives) cannot rank checkpoints: the untrained head's step-0 read, 0.0447, lies inside all three selected checkpoints' intervals. The criterion was written **after the F3 point estimates were read**, before any paired interval existed. Every probe since is read at its last step.

**The read-outs** (ADR-0026 §2). h is the final-layer states, and L is the last real (non-`<pad>`) position.

- **(a) `final_position`**: h_L, width 192. This is H1's registered probe.
- **(b) `mean_all`**: the mean of h over the real positions, width 192. It is a pooling-only control.
- **(d) `last_plus_text`**: [h_L ; mean of h over text-token positions (`<txt>`, `</txt>`, id ≥ 1,184) ; has-text flag], width 385. Without text the middle block is zero and the flag is 0, so **(d) reduces to (a) plus a constant** on the 28.6% of test windows that carry no text.

**Why (a) may miss the text.** The joint window (`tail_anchored_2048`) ends at step t's last token, a telemetry bin; messages sit earlier. Read-out (a) sees text only if the backbone routes it forward into that one vector.

**Why (d) needed a control.** Through an *untrained* backbone, the text mean is nearly a bag of text-token embeddings. ADR-0026 registered a **random-init gate on the instrument**. (d) on each trained joint backbone must beat (d) on each of three random-init backbones: 9/9 paired lower bounds above zero. Otherwise H1′ is NOT EVALUABLE, with the pre-written conclusion "whatever (d) harvests is the tokens' embeddings, not the pretraining". (d) on `tel_only` backbones and (b) are further controls.

### 3.5 Evaluation protocol

**Split** (`configs/data/splits_v3.yaml`): train to 2020, validation 2021, test 2022 onward (Penmanshiel 2022 only; its 2023–2024 files were never staged). The pooled test split is thinned to stride 12, which keeps 5,799 of 5,800 two-day blocks and 497 of 506 positive blocks.

**Statistics.** Blocks are 288 steps (48 h, twice the horizon) within each shard, resampled with replacement. A replicate without a positive is discarded, and more than 1% discarded untrusts the interval; no deciding row here discarded any. **Every comparison is paired**: both models are scored on identical resampled rows, and the interval is on Δ.

**Why paired.** ADR-0023 required the trained model's interval to clear each random-init interval, each bootstrapped alone. For correlated estimates that is far stricter than a 5% test, and ADR-0024 §1 shows it "could not have passed at any of the four designs". The four FAILs stand. **ADR-0024's paired criterion was registered after them**, before any paired interval existed.

**Controls.** (1) Random-init backbones: init seeds 1–3, no optimiser step, the same probe. (2) An order-blind bag of tokens: logistic regression on per-window token counts, with the probe's sampler (seed 1). (3) An order-blind status-only classifier: the same model over text ids and `<txt>`/`</txt>` only. It replaces a `txt_only` arm, which could not read the 1,088 empty positives.

**Decision rule.** The smallest effect of interest is 0.005 AUPRC, which is the resolution limit: seed spread 0.0068, single-seed half-width 0.0072. **SUPPORTED** if all three same-seed paired lower bounds exceed 0 and the median Δ exceeds 0.005. **REFUTED** if all three upper bounds are below 0.005. **INCONCLUSIVE** otherwise. Unnamed outcomes are reported as measured, and no clause is added afterwards.

### 3.6 Pre-registration mechanics

Each rule is committed before any scoring code exists (from ADR-0022, with its configuration and a test that parses the rule); the next commit records the hash, the outcome follows later, and a configuration a run has read is never edited.

| gate | registered | hash recorded | code or run | outcome |
|---|---|---|---|---|
| ADR-0025 (H1) | `3e29202` | `7a03201` | scoring at `4cf68b9` | `23699ee` |
| ADR-0026 (H1′) | `319ae3b` | `ce0eb5a` | read-outs `f945a11` | `9beebaa` |
| ADR-0028 (H2) | `8f7f10e` | `b62c145` | operating point `1ad1890`, committed alone before any test file was opened | `b659897` |
| ADR-0029 (exploratory, no verdict) | `db5fb96` | `382ba64` | CPU recomputation from saved scores, `382ba64` | `0468f1f` |

[INSTRUMENT_AUDIT.md](INSTRUMENT_AUDIT.md) records every case where an instrument or premise was the defect, each with its counterfactual result (§6).

![FaultLine architecture: data to token ids to the S2 decoder to two heads](figures/fig0_architecture.svg)

---

## 4. Data

| source | OEM / model, or content | role | years / split | scale | licence | provenance notes |
|---|---|---|---|---|---|---|
| Kelmarsh | Senvion MM92 × 6, 2,050 kW | train / val / test | train 2016–2020 · val 2021 · test 2022–2024 | 1,527,681 train steps; 941,165 test steps; 217 status strings | CC BY 4.0 | Cubico; Zenodo 16807551; 11 files, md5 verified |
| Penmanshiel | Senvion MM82 × 14 (WT03 absent), 2,050 kW | train / val / test | train 2016–2020 · val 2021 · test **2022 only** | 3,210,913 train steps; 729,158 test steps; 231 status strings | CC BY 4.0 | Cubico; Zenodo 16807304; 2023–2024 files are tier 2, never staged |
| Hill of Towie | Siemens SWT-2.3-VS-82 × 21, 2,300 kW | held-out site, test only | 2019 and 2023 staged | 2,199,043 steps; scored on 12,000 windows (399 positive) | CC BY 4.0 | RES for TRIG; Zenodo 14870023; alarm codes, not status strings; AeroUp retrofit 2021–2023 |
| CARE to Compare | 36 turbines, 3 anonymised farms (A: 5 onshore, Portugal; B, C: offshore, Germany) | cross-OEM evaluation only | every row is test; timestamps anonymised | 5,240,630 steps; 430,506 scored windows; 45 events (12 / 6 / 27) | CC BY-SA 4.0 | Fraunhofer IEE; farm A: EDP Open Data → Fraunhofer IEE → CC BY-SA 4.0; evaluation-only (`eval_only_sources`, share-alike; ADR-0001 evidence, ADR-0004 policy); no status strings |
| NRC | 5 collections: event notifications, information notices, bulletins, generic letters, regulatory issue summaries | unpaired text pretraining | own train / val / test by content hash | with PHMSA: 10,043,874 train tokens | public domain (17 U.S.C. 105) | pinned by sha256 per document; keyed dedup removed 4,521 superseded revisions |
| PHMSA | US pipeline incident narratives, 2010 onward | unpaired text pretraining | as NRC | 10,033 staged, 9,659 after the pipeline; 1,969,035 train tokens | public domain (17 U.S.C. 105) | data.transportation.gov 27nc-rsge; PII policy: emails and phone numbers masked |

**Cleaning and checksums.** Values outside plausibility bounds (for example wind speed 0–40 m/s) become missing, as do provider sentinels. Pitch is floored at 0.0° (ADR-0012), and power is per unit of rated power (ADR-0013). Telemetry is md5-verified, and text is pinned by sha256. **CARE's channels:** an unmapped core channel is `<nan>` on every step. Farm A lacks one channel (8.35% `<nan>`), farms B and C three each (25.01% and 25.22%), against 0.15% and 0.36% on the training-site test splits, and no pretraining window carries any CARE pattern.

---

## 5. Results

§5.1–5.3 and §5.5–5.6 are on the pooled Kelmarsh + Penmanshiel stride-12 test split (π = 0.0388 on the registered label), forward in time at the training sites. **None is a site-shift result.**

### 5.1 Persistence and the ADR-0009 variant (ADR-0029, exploratory)

ADR-0029 was registered after the programme closed and is **exploratory**: reported, not gating, and no verdict is re-decided. It discloses what was seen first: the fault-opening `Stop`-row prevalence (2.63% of negatives, 30.7% of positives), the has-text flag's 0.0423, and one variant spot check (0.0780 → 0.0632); no P-score AUPRC had been computed. All is recomputed from saved scores.

**The variant.** `narrow_within_24h_without` drops the events `anemometer defect` opens. It knows 137,016 of the 137,025 evaluated windows, 3,330 of them positive (π = 0.0243). The 9 it does not know, at Penmanshiel on 2022-12-31, are positive only through such events and have horizons that run past the end of the record.

**Table A. What each registered rule would return under the variant.**

| registered gate or rule | record | under the variant |
|---|---|---|
| ADR-0025 §5, H1 | INCONCLUSIVE | INCONCLUSIVE; seed 1's upper bound 0.0050057 misses REFUTED by one bound |
| ADR-0026 §4, random-init gate on (d) | PASS | PASS; weakest +0.0012 |
| ADR-0026 §4, H1′ | SUPPORTED | **INCONCLUSIVE**: +0.0140 [+0.0026, +0.0264], +0.0031 [−0.0076, +0.0116], +0.0137 [+0.0077, +0.0201] |
| ADR-0027 §4, gate, `joint_no_txt` | PASS | **FAIL**, 5 of 9 lower bounds above 0 |
| ADR-0027 §5, `joint_no_txt` | INCONCLUSIVE | **NOT EVALUABLE** (the rule as measured: INCONCLUSIVE) |
| ADR-0027 §4-5, `joint_status_raw` | gate FAIL; NOT EVALUABLE | the same |
| ADR-0027 B2, H1′'s rule replicated, both arms (reported) | SUPPORTED | **INCONCLUSIVE** |
| ADR-0028 Gate A (three arms), Gate B, H2 | pass, damage, INCONCLUSIVE | the same; Δselective risk +0.0044 [+0.0024, +0.0064] |

H1′ fails on one seed: seed 2's joint (d) loses 0.0296 AUPRC to the variant, and `tel_only` (a) seed 2 loses 0.0093. The status-only classifier is the only read whose AUPRC rises (0.0725 → 0.0819 [0.0538, 0.1200]; lift 1.87 → 3.37). The parity Δ becomes −0.0187 [−0.0534, +0.0093], −0.0305 [−0.0635, −0.0058] and −0.0299 [−0.0641, −0.0050]. ECE falls from 0.016–0.019 to 0.004–0.005 on every arm, and the mean prior-corrected probability (0.0193–0.0216) does not move.

**Persistence scores**, on the same rows and estimator: **P1**, a narrow event of the turbine started in (t − 24 h, t], a 24 h look-back equal to the model's window; **P2**, −(hours since the last narrow event start), a look-back capped at 720 h; **P3**, a `Stop` row in (t − 24 h, t] of the raw status log whose code opened a training-split event (18 codes, frozen before scoring); **P4**, P3 read only from the messages in the model's R0 window. P1 and P2 read every narrow event, anemometer-defect events included.

**Table B. Persistence against the model** (AUPRC [95%]; paired Δ(P − joint (d)) per seed).

| score | registered label (π = 0.0388) | Δ against joint (d), seeds 1 / 2 / 3 | variant (π = 0.0243) | Δ against joint (d), seeds 1 / 2 / 3 |
|---|---|---|---|---|
| P1 (24 h) | 0.1262 [0.1024, 0.1528] | +0.0481 / +0.0451 / +0.0577, all above 0 | 0.0625 [0.0463, 0.0821] | −0.0007 / +0.0111 / +0.0105, all span 0 |
| P2 (≤ 720 h) | 0.2211 [0.1862, 0.2582] | +0.1430 / +0.1400 / +0.1526, all above 0 | 0.0944 [0.0735, 0.1189] | +0.0312 [+0.0093, +0.0536] / +0.0430 [+0.0250, +0.0632] / +0.0424 [+0.0241, +0.0633] |
| P3 (24 h, raw log) | 0.1256 [0.1019, 0.1521] | all above 0 | 0.0628 [0.0466, 0.0825] | all span 0 |
| P4 (24 h, model's window) | 0.1252 [0.1015, 0.1518] | all above 0 | 0.0635 [0.0471, 0.0834] | all span 0 |
| joint (d) | 0.0780 / 0.0810 / 0.0685 | — | 0.0632 / 0.0514 / 0.0520 | — |
| (d) three-seed ensemble | 0.0793 [0.0687, 0.0916] | P2: +0.1418 [+0.1103, +0.1746] | 0.0573 [0.0475, 0.0696] | P2: +0.0371 [+0.0178, +0.0580] |
| status-only classifier | 0.0725 [0.0537, 0.0979] | — | 0.0819 [0.0538, 0.1200] | P2 − it: +0.0125 [−0.0173, +0.0353] |

**Task composition**: share of positives against negatives with a narrow event start in the preceding window.

| label | site | 6 h | 24 h |
|---|---|---|---|
| registered | Kelmarsh | 15.31% vs 0.61% | 38.61% vs 2.33% |
| registered | Penmanshiel | 9.39% vs 0.86% | 22.87% vs 3.19% |
| registered | pooled | 12.56% vs 0.72% | 31.29% vs 2.71% |
| variant | pooled | 9.04% vs 0.98% | 26.46% vs 3.25% |

**What the input pipeline loses.** P3 − P4 is +0.0004 [−0.0009, +0.0019] on the registered label and −0.0007 [−0.0013, −0.0000] under the variant. 173 windows carry the flag in the raw log but not in the model's window, all cut by the 2,048-token cap; none carries it only in the window.

**One measured caveat.** An event is dated by its first step, so one starting exactly at t may rest on later steps for its 60-second qualification. P1 is set only through such an event on 25 windows (12 positive); without them P1 reads 0.1253.

*Reading.* On the registered label, a text-free event-log look-back of the model's own length beats the model. Under the variant it ties, and a 30-day look-back beats it on both. The task as labelled is substantially recurrence, the model's window holds almost all of the recurrence signal the raw log does, and the model does not extract more of it than a lookup.

### 5.2 The read-out decides whether the text is visible (ADR-0025, ADR-0026)

![The H1/H1′ mechanism: design (a), design (d) and their controls](../reports/data/fig4_readout_mechanism.svg)

| read (all final-step probes; π = 0.0388) | seed 1 | seed 2 | seed 3 |
|---|---|---|---|
| `tel_only`, (a), M1 1,872-token windows | 0.0580 [0.0505, 0.0672] | 0.0576 [0.0503, 0.0670] | 0.0515 [0.0453, 0.0586] |
| joint, (a), R0 windows | 0.0602 [0.0527, 0.0688] | 0.0554 [0.0490, 0.0626] | 0.0497 [0.0441, 0.0559] |
| joint, (a), text withheld (M1 windows; different windows, not paired) | 0.0558 [0.0491, 0.0631] | 0.0543 [0.0480, 0.0612] | 0.0543 [0.0477, 0.0616] |
| joint, (b) `mean_all` | 0.0576 [0.0502, 0.0660] | 0.0654 [0.0565, 0.0758] | 0.0591 [0.0515, 0.0677] |
| **joint, (d) `last_plus_text`** | **0.0780 [0.0668, 0.0916]** | **0.0810 [0.0697, 0.0939]** | **0.0685 [0.0599, 0.0780]** |
| `tel_only` backbone, (d) | 0.0509 [0.0449, 0.0579] | 0.0526 [0.0465, 0.0594] | 0.0418 [0.0371, 0.0468] |
| random-init backbone, (d) (init seed) | 0.0581 [0.0505, 0.0666] | 0.0575 [0.0500, 0.0661] | 0.0547 [0.0478, 0.0627] |
| order-blind status-only classifier (sampler seed 1; one fit) | 0.0725 [0.0537, 0.0979] | — | — |

| paired comparison | seed 1 | seed 2 | seed 3 | reading |
|---|---|---|---|---|
| **H1**: joint (a) − `tel_only` (a) | +0.0022 [−0.0034, +0.0068] | −0.0022 [−0.0084, +0.0021] | −0.0018 [−0.0060, +0.0021] | **INCONCLUSIVE** (median −0.0018) |
| **H1′**: joint (d) − `tel_only` (a) | +0.0200 [+0.0112, +0.0294] | +0.0234 [+0.0128, +0.0342] | +0.0170 [+0.0111, +0.0232] | **SUPPORTED** on the registered label (median +0.0200); **INCONCLUSIVE** under the ADR-0009 anemometer-excluded variant (ADR-0029, exploratory; §5.1) |
| gate: joint (d) − random-init (d), same-seed cell | +0.0199 [+0.0128, +0.0290] | +0.0235 [+0.0166, +0.0318] | +0.0138 [+0.0090, +0.0187] | **PASS** 9/9; weakest cell +0.0058 (seed 3 vs init 1) |
| joint (d) − `tel_only` backbone (d) | +0.0271 [+0.0196, +0.0366] | +0.0285 [+0.0199, +0.0386] | +0.0267 [+0.0209, +0.0331] | reported |
| joint (b) − joint (a) | −0.0026 [−0.0068, +0.0017] | +0.0100 [+0.0051, +0.0164] | +0.0094 [+0.0054, +0.0142] | reported; no consistent sign |
| joint (d) − status-only classifier | +0.0055 [−0.0173, +0.0241] | +0.0085 [−0.0141, +0.0265] | −0.0040 [−0.0264, +0.0125] | reported; parity on the registered label; below the count under the variant (ADR-0029, exploratory; §5.1) |
| `tel_only` backbone (d) − random-init (d) | −0.0072 [−0.0125, −0.0022] | −0.0050 [−0.0110, +0.0007] | −0.0129 [−0.0190, −0.0077] | reported |

**H1 through (a).** Seed 1's upper bound (0.0068) blocks REFUTED; no lower bound clears zero. Control (iii), an (a) probe on the frozen `tel_only` backbone over the joint windows, explains why. The input change alone costs −0.0122, −0.0096 and −0.0076, with every interval below zero, through truncation plus text the backbone cannot read. Joint pretraining at identical input recovers +0.0144, +0.0075 and +0.0059, with every interval above zero. The two cancel.

**H1′ through (d)** was registered after H1's INCONCLUSIVE result was seen, and is evaluated on the same test windows. It is SUPPORTED on the registered label; INCONCLUSIVE under the ADR-0009 anemometer-excluded variant (ADR-0029, exploratory). The gate passes 9/9, so (d) reads more than token embeddings. The gain sits where the text is. The has-status stratum holds **97,810 of 137,025 test windows (71.4%)** and 4,224 of 5,312 positives (π = 0.0432). In it, Δ(joint (d) − `tel_only` (a)) is +0.0252 [+0.0158, +0.0357], +0.0260 [+0.0142, +0.0375] and +0.0145 [+0.0070, +0.0220]. In the no-status stratum (π = 0.0277) the sign is inconsistent. A `tel_only` backbone reads text no better than an untrained one; its text-embedding rows collapsed onto one shared vector (seed 2), a plausible but unestablished reason.

**Parity with counting strings.** The status-only classifier is above every (a) probe, and joint (d) is level with it on the registered label. Under the variant the classifier reads above joint (d) on all three seeds, excluding zero on seeds 2 and 3 (ADR-0029, exploratory). Its signal is partly recurrence. With every `Stop` row removed (R2) it reads 0.0597 [0.0468, 0.0785] (π = 0.0388, sampler seed 1), and its paired lift over the telemetry bag falls from +0.0202 [+0.0007, +0.0453] to +0.0074 [−0.0070, +0.0259]. R2 was not measured for (d).

*Derived check, not a registered result.* A score equal to (d)'s has-text flag alone (1 on the 97,810 windows holding any text token, 4,224 of them positive; 0 elsewhere) reads AUPRC 0.0423 [0.0378, 0.0469] on the 137,025 test windows (π = 0.0388, same estimator). The flag alone cannot account for (d)'s 0.0685–0.0810.

*Reading.* The text signal sits at the joint backbone's text positions and is recoverable there by the one-hidden-layer probe, not at the last position. What is recovered matches an order-blind count of the strings on the registered label and falls below it under the variant, and it stays below P1 (24 h; level under the variant) and P2 (up to 720 h) (§5.1; ADR-0029, exploratory). Part of it is available from an untrained backbone's embeddings: random-init (d) reads above trained `tel_only` (a) on seeds 1 and 3 and within 0.0001 of it on seed 2 (first table).

### 5.3 Pretraining against random initialisation and a bag of tokens (ADR-0024)

| read (π = 0.0388) | seed 1 | seed 2 | seed 3 |
|---|---|---|---|
| random-init backbone, (a), final step (init seed) | 0.0416 [0.0370, 0.0467] | 0.0419 [0.0374, 0.0468] | 0.0418 [0.0371, 0.0470] |
| order-blind telemetry bag of tokens (sampler seed 1; one fit) | 0.0523 [0.0445, 0.0619] | — | — |

Against three random-init seeds each, **all nine paired lower bounds are above zero** (PASS). On the checkpoints the F3 rule selected, Δ runs from +0.0092 to +0.0186, with the lowest lower bound at +0.0045. Final-against-final (the table above), the range is +0.0096 to +0.0164 and the lowest lower bound is +0.0047. Against the bag of tokens (selected checkpoints), Δ is +0.0016 [−0.0059, +0.0084], +0.0053 [−0.0017, +0.0128] and −0.0015 [−0.0094, +0.0053]. *Reading:* pretraining moves a frozen probe by a quarter to a half of π, and buys nothing measurable over a token histogram.

### 5.4 Site shift (ADR-0021, ADR-0022)

![Site-shift gate: Hill of Towie, CARE and the forward-in-time split, each against its own base rate](../reports/data/fig1_site_shift.svg)

| axis | π | seed 1 | seed 2 | seed 3 | seeds clearing π | verdict |
|---|---:|---|---|---|---|---|
| Hill of Towie (12,000 windows) | 0.03325 | 0.0390 [0.0304, 0.0548] | 0.0510 [0.0371, 0.0741] | 0.0359 [0.0276, 0.0508] | 1 of 3 | **NOT EVALUABLE** |
| CARE (430,506 windows, 45 events) | 0.001254 | 0.0013 [0.0009, 0.0019] | 0.0012 [0.0009, 0.0016] | 0.0012 [0.0008, 0.0017] | 0 of 3 | **NOT EVALUABLE** |
| training-site forward-in-time test | 0.0388 | 0.0580 [0.0505, 0.0672] | 0.0576 [0.0503, 0.0670] | 0.0515 [0.0453, 0.0586] | 3 of 3 | EVALUABLE |

The ADR-0021 gate itself read 0.0393 [0.0306, 0.0553] (seed 1) and was NOT EVALUABLE. Hill of Towie is marginal, not null. CARE is at chance, per farm as well as pooled. **The project has no evaluable shift axis.**

**Attribution (ADR-0022 F6-0, registered before it ran).** Imposing each CARE farm's missing-channel pattern on the training-site test split leaves all nine masked reads above 0.0388 (lowest lower bound 0.0421). Farm A's null is therefore read as failure to transfer; farms B and C stay unattributed. The telemetry bag of tokens, not refit, scores 0.001940 [0.001233, 0.003830] on CARE, so the registered clause holds: "the null is a property of the token stream across OEMs". That bins fitted on one OEM family do not carry across OEMs is the author's interpretation, made plausible by §3.2's shared-id design; no per-site or rank-normalised tokenizer was tried.

### 5.5 Pretraining-content ablations (ADR-0027)

| arm | (d) AUPRC, seeds 1 / 2 / 3 (π = 0.0388) | gate | Δ against joint (d), seeds 1 / 2 / 3 | verdict |
|---|---|---|---|---|
| `joint_no_txt` (no narrative corpus; tel+status exposure held at 25,001,984 tokens) | 0.0750 [0.0657, 0.0853] / 0.0663 [0.0578, 0.0757] / 0.0672 [0.0589, 0.0764] | **PASS** 9/9, weakest +0.0041, on the registered label; **FAIL** 5/9 under the ADR-0009 anemometer-excluded variant (ADR-0029, exploratory) | −0.0030 [−0.0102, +0.0026] / −0.0147 [−0.0207, −0.0101] / −0.0013 [−0.0040, +0.0015] | **INCONCLUSIVE** |
| `joint_status_raw` (status strings in provider casing) | 0.0719 [0.0625, 0.0828] / 0.0773 [0.0668, 0.0894] / 0.0777 [0.0672, 0.0895] | **FAIL** 4/9, weakest −0.0058 | −0.0061 [−0.0122, −0.0014] / −0.0037 [−0.0086, +0.0009] / +0.0092 [+0.0050, +0.0142] (as measured) | **NOT EVALUABLE** |

On raw-cased windows the untrained backbones read 0.0665 [0.0547, 0.0824], 0.0653 [0.0551, 0.0780] and 0.0651 [0.0537, 0.0805] through (d) (init seeds 1–3; π = 0.0388), above their normalised reads (§5.1). *Reading:* the narrative corpus's contribution is undecided, as registered in advance as the likeliest outcome. On raw strings the instrument cannot separate pretraining from the tokens.

### 5.6 Calibration and abstention (ADR-0028)

Each arm is a three-seed ensemble, p = mean of sigmoid(z_s), with seed disagreement u = std(z_s) as its confidence signal. τ (the F1 maximiser) and κ (90% coverage) are fixed on 2021 validation before any test file is opened.

| arm (R0 windows, three-seed ensemble; test π = 0.0388) | clean AUPRC | ECE, 15 equal-mass bins | ECE after validation-fitted Platt | mean p (after Platt) | Gate A: Δ AURC(disagreement − random) |
|---|---|---|---|---|---|
| `tel_only` backbone, (a) (ADR-0025 control iii) | 0.0479 [0.0426, 0.0536] | 0.0181 [0.0143, 0.0219] | 0.0181 [0.0144, 0.0219] | 0.0207 (0.0206) | −0.0158 [−0.0177, −0.0140] **PASS** |
| joint, (a) | 0.0567 [0.0499, 0.0643] | 0.0194 [0.0157, 0.0232] | 0.0184 [0.0147, 0.0222] | 0.0193 (0.0204) | −0.0184 [−0.0206, −0.0163] **PASS** |
| joint, (d) | 0.0793 [0.0687, 0.0916] | 0.0172 [0.0135, 0.0209] | 0.0164 [0.0127, 0.0201] | 0.0216 (0.0224) | −0.0275 [−0.0302, −0.0250] **PASS** |

On test, the mean p (0.019–0.022) is about half of π on the registered label, and Platt fitted at the validation π of 0.0211 does not fix it. Under the ADR-0009 anemometer-excluded variant (ADR-0029, exploratory) the under-read is about a tenth to a fifth, and ECE is 0.004–0.005 on every arm (§5.1). The rest is partly an in-time property of the probe: two of three `tel_only` seeds under-read on 2021 validation (0.0185 and 0.0183 against π = 0.0211). Scores are rankings, not risks, without recent recalibration.

**Gate B and H2.** On `joint` (d), k of 12 core channels are masked to `<nan>`, with the text kept and nested sets drawn once with seed 20260924. Gate B, Δ AUPRC(k = 8 − clean), is −0.0039 [−0.0082, −0.0001]: damage, by 0.0001. For H2 at fixed (τ, κ), Δcoverage is −0.0797 [−0.0841, −0.0753] and Δselective risk is +0.0053 [+0.0033, +0.0074]. The upper bound misses +0.005 and coverage is not flat, so H2 is **INCONCLUSIVE** (under the variant, Δselective risk +0.0044 [+0.0024, +0.0064]: the same). Calibrated abstention implemented and evaluated; graceful degradation not established.

![Abstention under channel masking (H2)](../reports/data/fig7_abstention.svg)

### 5.7 Instrument findings

**Checkpoint selection is noise at 117 positives** (§3.4). The most consequential [INSTRUMENT_AUDIT.md](INSTRUMENT_AUDIT.md) entries: H3's split was drawn in words while the model reads tokens, and two replacement metrics could not fail (entries 9, 11, 12); the gate chain returned `tail`'s exit status (entry 10); and causality and the initial loss were asserted only at toy scale until the joint arm (entry 13).

### Gate ledger

| gate | hypothesis / question | registered | outcome commit | verdict | key numbers |
|---|---|---|---|---|---|
| ADR-0021 | Hill of Towie separates `tel_only` from chance | `ce9c8ad` | `ed60e8d` | **NOT EVALUABLE** | seed 1: 0.0393 [0.0306, 0.0553], π 0.03325 |
| ADR-0022 | choose the primary axis; CARE | `801ab71` | `d87a524` | CARE **NOT EVALUABLE**; temporal EVALUABLE | CARE 0/3 seeds; temporal 3/3 |
| ADR-0022 addendum | fixed-final-step selection | `4622564` | `267147d` | adopted | Δ(final − selected) +0.0041, +0.0007 |
| ADR-0022 F6-0 | attribute the CARE null | `ad1b7a3` | `0bcbd01` | farm A: transfer failure; B, C unattributed; token stream | lowest masked lower bound 0.0421; bag on CARE 0.001940 [0.001233, 0.003830] |
| ADR-0023 | probe sees pretraining (non-overlap) | `c9489a2` | `81a8fab` (§a) … `95a2cef` (§d) | **FAIL** (§a–§d) | §a: lower bound 0.0434 against random-init upper bound 0.0500 |
| ADR-0024 | probe sees pretraining (paired) | `79d4e97` | `f6c2df0`; F3 `d16e93f` | **PASS** | 9/9; +0.009 to +0.019 |
| ADR-0025 | H1 | `3e29202` | `23699ee` | **INCONCLUSIVE** | median −0.0018 |
| ADR-0026 | H1′ + instrument gate | `319ae3b` | `9beebaa` | **SUPPORTED** on the registered label; INCONCLUSIVE under the ADR-0009 anemometer-excluded variant (ADR-0029, exploratory); gate **PASS** | median +0.0200; gate 9/9 |
| ADR-0027 | narrative corpus; surface form | `179d769` | `183b1a0` | **INCONCLUSIVE** (gate PASS; FAIL under the variant, ADR-0029, exploratory); **NOT EVALUABLE** | median −0.0030; gate 4/9 |
| ADR-0029 | ADR-0009 variant; persistence | `db5fb96` | `0468f1f` | exploratory; no verdict | Table A; P1 (24 h) 0.1262, P2 (≤ 720 h) 0.2211 |
| ADR-0028 | H2 + Gates A, B | `8f7f10e` | `b659897` | Gate A **PASS** ×3; Gate B damage; H2 **INCONCLUSIVE** | Δcov −0.0797; Δrisk +0.0053 [+0.0033, +0.0074] |

---

## 6. Why the evidence can be trusted

**Rules precede numbers.** Each of the eight gates was committed before its code existed. From ADR-0022 onward, the registration commit also carries the configuration by value and a test that parses the rule from the ADR text ([ledger](../reports/data/ledger_gates.md)). ADR-0028's operating point was committed alone (`1ad1890`) before any test file was opened.

**Negative outcomes stand under the same rules.** Both shift axes are NOT EVALUABLE. ADR-0023's four FAILs remain beside the corrected criterion, and H1's INCONCLUSIVE stands beside H1′'s paired outcome. ADR-0027 named INCONCLUSIVE as its likeliest outcome before running.

**The record's own obligation, once executed, turned around its only positive result.** ADR-0009 registered a robustness obligation at M1: report every late-test result with and without the `anemometer defect` events. It went unexecuted for H1, H1′, ADR-0027 and ADR-0028 until this summary's verification pass found the gap. ADR-0029 executed it with a persistence check, registered before any P-score AUPRC or variant metric bar one disclosed spot check. H1′, the parity result and the `joint_no_txt` gate do not hold under the variant, and the model does not beat P1, a 24 h event-log look-back of its own length, or P2, which looks back up to 720 h. The verdicts stand as registered; this summary leads with the reversal. An obligation left unexecuted is a degree of freedom.

**Every positive claim met a falsifying control, and three framings fell.** The bag of tokens falsified sequence-structure learning in the telemetry model. The status-only classifier falsified the claim that the joint model extracts more from text than a string count (parity on the registered label; below it under the variant). Persistence (ADR-0029, exploratory) falsified the claim that it adds to the event log. The random-init gate on (d) passed, and it also exposed how much of (d)'s level an untrained backbone reaches.

**Scale is stated.** A ~0.005 resolution, three seeds per arm and control, one RTX 4060, **18.2 GPU-hours** (Appendix B). The audit has 17 entries, each with its counterfactual; entries 16 and 17 record the two gaps above.

---

## 7. Limitations and threats to validity

**Low absolute performance, below persistence.** The best clean single-probe read, joint (d) seed 2 at 0.0810 [0.0697, 0.0939], is 2.1× π = 0.0388. P1, with the same 24 h look-back, reads 0.1262, and P2, looking back up to 720 h, reads 0.2211 (ADR-0029, exploratory). It is a ranking signal, weaker than a lookup.

**Parity, not superiority.** On the registered label, joint (d) matches an order-blind string count, and the telemetry model matches a token histogram. Under the variant the string count reads above joint (d) (ADR-0029, exploratory).

**The only positive result depends on the label.** H1′ is SUPPORTED on the registered label; INCONCLUSIVE under the ADR-0009 anemometer-excluded variant (ADR-0029, exploratory). One seed carries the difference.

**No evaluable shift axis.** Every positive result is forward in time at the two training sites, a split the record calls in-distribution.

**Calibration.** Probabilities under-read π by about half on the registered label, and Platt does not fix it. Under the variant the under-read is about a tenth to a fifth (ADR-0029, exploratory). Scores are rankings, not risks, without recent recalibration.

**Post-hoc elements and test reuse.** H1′ was registered after H1's result and evaluated on the same windows. The ADR-0022 addendum's criterion followed point estimates, and ADR-0024's followed ADR-0023's FAILs. H3 was withdrawn at its testability gate: 0 of 693 Hill of Towie events and 0 of 45 CARE anomalies mapped to a string type. ADR-0029 followed a reconnaissance and is exploratory by design. No confirmatory split untouched by any registration has been used.

**Recurrence and continuation are not separated.** A narrow event started in the preceding 24 h for 31.29% of test positives and 2.71% of negatives (ADR-0029, exploratory). The record does not separate a new fault from a continuing episode, and R2 was never measured for (d).

**Narrow domain, small scale, few external baselines.** Both training farms are Senvion, from one publisher; 3.5M backbone parameters and 50M tokens per arm leave the models undertrained. Persistence exists only as an exploratory comparator, and there is no GBDT, normal-behaviour model or time-series foundation model.

---

## 8. Request for expert feedback

What follows is a request for expert feedback — specifically, how would you strengthen the methodology, results, or framing to make this a strong top-tier submission (e.g., NeurIPS/ICML workshop, applied ML venue, or an energy-AI journal)? What's the strongest angle for a paper here — the read-out finding, the pre-registration framework, the negative-result methodology, or something else?

1. **Framing.** The leading candidate angle is now **evaluation practice in SCADA fault prediction (persistence, continuation, defect clusters)**. A pre-registered from-scratch model does not beat time since the last fault (P1, 24 h, like-for-like; P2, up to 720 h, strongest), its only positive result depends on one defect-message cluster, and an unexecuted robustness obligation and a missing persistence baseline hid them. Is that the strongest framing, or should the read-out finding lead?
2. **Experiments.** Please rank, cut or add to these candidates, marking any you consider mandatory:
   - the incremental value of (d) over P2 (up to 720 h), with the combination fitted on 2021 validation (CPU);
   - continuation-excluded windows: drop windows in which a fault episode is already under way at t, and re-score the model, P1 (24 h) and P2 (up to 720 h) (CPU);
   - the Penmanshiel 2023–2024 confirmatory set, which no run has read, staged under rules registered before staging (CPU scoring of the frozen checkpoints);
   - decomposing read-out (d) (last-position only / text mean only / has-text flag only);
   - standard baselines: GBDT on engineered SCADA features plus status counts and P2 (up to 720 h); a normal-behaviour model; a frozen pretrained time-series foundation model under the same probe;
   - a per-turbine or per-OEM normalisation tokenizer variant on CARE; CARE under its published benchmark protocol;
   - one additional scale point.
3. **Test reuse.** Is test-set reuse across sequential, disclosed registrations acceptable, or does the paper need the fresh confirmatory set?
4. **Labels.** Should defect clusters such as `anemometer defect` be excluded from the primary label, reported as a variant, or treated as a separate task?
5. **Venue.** Which venue fits the evidence as it stands, and which would fit after the experiments you consider mandatory?

---

## Appendix A — Evidence map

| claim (§) | ADR | report | registered → outcome |
|---|---|---|---|
| Label rule; events per turbine-year (3.1) | 0009 | [label report](../reports/data/20260910-212256_label_telemetry_20fa4ac5/label_stats_report.md) | accepted 2026-09-11 |
| Leakage measurement and R0 ruling (3.1) | 0025 §3 | [h1_controls_v0](../reports/data/h1_controls_v0_20260918.md) | `3e29202` → `23699ee` |
| Tokenizer v2, n_tail 4 (3.2) | 0014, 0015 | [quantile_bins_v2](../reports/data/quantile_bins_v2_20260912.md), [shards_v2](../reports/data/shards_v2_20260912.md) | config `quantile_bins_v2.yaml` |
| BPE 32,768 / 32,512 merges (3.2) | 0016 | [text_bpe_v1](../reports/data/text_bpe_v1_20260915.md), [text_shards_v1](../reports/data/text_shards_v1_20260915.md) | — |
| Status normalisation 18 → 80 of 264 (3.2) | 0017 | [h3prime_stage_a_v1](../reports/data/h3prime_stage_a_v1_20260916.md) | `d56684a` |
| S2 / S3 text ladder (3.3) | 0018 | [m2_gate6](../reports/data/m2_gate6_20260916.md) | — |
| Fixed final step (3.4) | 0022 addendum | [checkpoint_selection_v0](../reports/data/checkpoint_selection_v0_20260917.md) | `4622564` → `267147d` |
| ADR-0023 FAIL §a–§d (3.5, 6) | 0023 | [probe_control_v0](../reports/data/probe_control_v0_20260916.md) … [v3](../reports/data/probe_control_v3_20260916.md) | `c9489a2` → `81a8fab` … `95a2cef` |
| H1 INCONCLUSIVE; decomposition (5.2) | 0025 | [h1_gate_v0](../reports/data/h1_gate_v0_20260919.md) | `3e29202` → `23699ee` |
| Status-only 0.0725; R2 (5.2) | 0025 §4 | [h1_controls_v0](../reports/data/h1_controls_v0_20260918.md) | `3e29202` → `5c00dd6` |
| H1′ SUPPORTED on the registered label (INCONCLUSIVE under the ADR-0009 anemometer-excluded variant, ADR-0029, exploratory); gate; (b), (d) controls; strata (5.2) | 0026 | [readout_v0](../reports/data/readout_v0_20260920.md) | `319ae3b` → `9beebaa` |
| Pretraining vs random init, 9/9 (5.3) | 0024 F3 | [seed_replication_v0](../reports/data/seed_replication_v0_20260917.md), [paired_control_v0](../reports/data/paired_control_v0_20260917.md) | `79d4e97` → `f6c2df0`; `0d6d6b4` → `d16e93f` |
| Bag-of-tokens parity (5.3) | 0024 §6 | [bag_of_tokens_v0](../reports/data/bag_of_tokens_v0_20260917.md) | `79d4e97` → `77390ba` |
| Hill of Towie NOT EVALUABLE (5.4) | 0021, 0022 §6 | [gate_check_v0](../reports/data/gate_check_v0_20260916.md), [seed_replication_v0](../reports/data/seed_replication_v0_20260917.md) | `ce9c8ad` → `ed60e8d` |
| CARE NOT EVALUABLE (5.4) | 0022 | [axis_gate_v0](../reports/data/axis_gate_v0_20260918.md) | `801ab71` → `d87a524` |
| CARE attribution (5.4) | 0022 F6-0 | [care_attribution_v0](../reports/data/care_attribution_v0_20260918.md), [fig5](../reports/data/fig5_care_attribution.svg) | `ad1b7a3` → `0bcbd01` |
| Ablations (5.5) | 0027 | [ablation_gate_v0](../reports/data/ablation_gate_v0_20260923.md) | `179d769` → `183b1a0` |
| Calibration, Gate A, Gate B, H2 (5.6) | 0028 | [abstention_v0](../reports/data/abstention_v0_20260924.md), [abstention_part_a_ece_v0](../reports/data/abstention_part_a_ece_v0_20260924.md), [operating points](../reports/data/abstention_operating_points_v0.json) | `8f7f10e` → `1ad1890` → `b659897` |
| In-time validation under-read (5.6) | 0024 F3 §6 | [seed_replication_v0](../reports/data/seed_replication_v0_20260917.md) | `b2ad4a7` → `d16e93f` |
| Anemometer-defect variant (5.1, 7) | 0009, 0022, 0029 | [axis_gate_v0](../reports/data/axis_gate_v0_20260918.md), [exploratory_v0](../reports/data/exploratory_v0_20260926.md) | `801ab71` → `d87a524`; `db5fb96` → `0468f1f` |
| Persistence P1-P4, composition, P3 − P4 (5.1) | 0029 | [exploratory_v0](../reports/data/exploratory_v0_20260926.md) ([JSON](../reports/data/exploratory_v0_20260926.json)) | `db5fb96` → `382ba64` → `0468f1f` |
| Instrument audit entries (5.7, 6) | — | [INSTRUMENT_AUDIT.md](INSTRUMENT_AUDIT.md) | per entry |
| All paired comparisons in one view | — | [fig3_paired_deltas](../reports/data/fig3_paired_deltas.svg), [figures index](../reports/data/figures_index.md) | — |

## Appendix B — Reproduction

**Environment.** One supported environment: `uv sync --extra dev` from the committed [uv.lock](../uv.lock); torch 2.14.0 (`+cu132`); NVIDIA GeForce RTX 4060, 8 GB, driver 616.56 ([ENVIRONMENT.md](ENVIRONMENT.md)). Gates: `scripts/gates.sh`. Raw telemetry comes from the version-pinned Zenodo records in `configs/data/sources_telemetry.yaml`, md5-verified; text is fetched by `faultline download text`, pinned by sha256.

**Configurations and entry points.** Each `faultline model …` command defaults to the configuration shown and writes its report under `reports/data/` with the configuration hash and git SHA.

| phase | command | configuration |
|---|---|---|
| telemetry shards | `faultline telemetry shards` (pass the v2 tokenizer config; the CLI default is v0) | `configs/data/telemetry_v4.yaml`, `configs/data/splits_v3.yaml`, `configs/tokenizer/quantile_bins_v2.yaml` |
| text tokenizer / pretraining | `faultline text bpe`; `faultline model text-pretrain` | `configs/tokenizer/text_bpe_v1.yaml`; `configs/train/text_v1.yaml` |
| mixture shards | `faultline model mixture-shards --config configs/train/joint_v1.yaml` | `configs/train/joint_v1.yaml` (then `joint_v2.yaml`) |
| ADR-0021 gate | `faultline model gate-check` | `configs/train/gate_check_v0.yaml` |
| ADR-0023 §a–§d | `faultline model probe-control` | `configs/train/probe_control_v{0,1,2,3}.yaml` |
| ADR-0024 G1, G2, G3, F3 | `paired-control`, `bag-of-tokens`, `probe-cadence`, `seed-replication` | `paired_control_v0`, `bag_of_tokens_v0`, `probe_cadence_v0`, `seed_replication_v0` |
| ADR-0022 addendum, F5, F6-0 | `checkpoint-selection`, `axis-gate`, `care-attribution` | `seed_replication_v0`, `configs/eval/axis_gate_v0.yaml`, `configs/eval/care_attribution_v0.yaml` |
| ADR-0025 (H1) | `h1-controls`, `h1-arms`, `h1-score`, `h1-gate` | `bag_of_tokens_v1`, `h1_arms_v0`, `configs/eval/h1_gate_v0.yaml` |
| ADR-0026 (H1′) | `readout`, `readout-gate` | `configs/eval/readout_v0.yaml` |
| ADR-0027 | `ablation-arms`, `ablation-gate` | `configs/eval/ablation_gate_v0.yaml` (arms `configs/train/joint_v2.yaml`, `ablation_arms_v0.yaml`) |
| ADR-0028 | `abstention-score`, `abstention-ece`, `abstention-operating-point`, `abstention-outcome` | `configs/eval/abstention_v0.yaml` |
| figures | `faultline model figures` | reads committed reports only |

**GPU hours.** The programme floor is **18.2 GPU-hours** (README). It is 12.6 h summed from timing sidecars (98 records, eleven run directories), plus F8-2's 3.37 h and F9-2's 2.24 h. The telemetry ladder, text pretraining and order-blind comparators wrote no sidecar and are timed only in their own reports. Per phase, as each outcome in DECISIONS.md reports its wall clock:

| phase | GPU hours |
|---|---:|
| ADR-0023 probe control, §a–§d | 1.42 |
| ADR-0024 G1 (re-run probe, re-scorings, CPU bootstraps) | 0.84 |
| ADR-0024 F3 (two pretrainings, six probes; two invocations) | 2.66 + 2.20 |
| ADR-0022 F5 (five CARE scorings) | 1.72 |
| ADR-0022 F6-0a (nine masked scorings) | 1.02 |
| ADR-0025 F6-3 (27 scorings) | 3.33 |
| ADR-0026 F7′ (12 probes, 12 scorings) | 3.15 |
| ADR-0027 F8-2 (6 pretrainings, 9 probes, 9 scorings) | 3.37 |
| ADR-0028 F9-2 (21 scorings) | 2.24 |

These wall-clock figures are not additive with the sidecar floor: some include CPU bootstrap time (G1), F3's two invocations overlap, and F6-2 is not itemised.
