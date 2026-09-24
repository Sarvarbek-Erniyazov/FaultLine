# ADR-0028: calibration, abstention and H2 (F9-3)

Step 0 stopped F9-3 once: the brief assumed `tel_only` (a)'s test scores were on the M1 1,872-token windows; they are on R0 (ADR-0028 §1, control iii), as are its validation scorings, and the author ruled to proceed as registered with the arm relabelled.

| field | value |
| --- | --- |
| record | ADR-0028 §1-§4, F9-3 |
| config | configs/eval/abstention_v0.yaml (30c9c714), registered in 8f7f10e |
| operating point | reports/data/abstention_operating_points_v0.json, committed alone in **1ad1890** before any test file was opened |
| split | clean test: 137,025 windows, 5,312 positive, 5,799 two-day blocks |
| interval | block bootstrap, 10,000 replicates, seed 20260916, 95%; more than 1% discarded is untrusted |
| random reference | 100 permutations, seeds from default_rng(20260924) |
| git | 1ad18908ca346c5c432bedda13d6a70734bede40 |


**Arm naming.** "tel_only backbone, (a), on R0 windows (ADR-0025 control iii)" is the `tel_only` backbone read through (a) on the joint R0 windows. It is **not** F3's `tel_only` (a) on the 1,872-token M1 windows that serves as the H1/H1′ comparator, and its calibration is not that baseline's.

## Operating points (validation only)

| arm | τ | κ | margin cut | Platt a | Platt b |
| --- | --- | --- | --- | --- | --- |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii) | 0.0353 | 0.3257 | 0.0059 | 1.1837 | 0.6964 |
| joint (a), on R0 windows (ADR-0025 S1) | 0.0410 | 0.3322 | 0.0111 | 1.0273 | 0.1584 |
| joint (d), on R0 windows (ADR-0026 R-joint-d) | 0.0637 | 0.3388 | 0.0312 | 1.0279 | 0.1366 |


## Part A: calibration on clean test (reported, no verdict)

| arm | ECE, prior-corrected | ECE, Platt (validation) | mean p, corrected | mean p, Platt | base rate | caveats |
| --- | --- | --- | --- | --- | --- | --- |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii) | 0.0181 [0.0143, 0.0219] | 0.0181 [0.0144, 0.0219] | 0.0207 [0.0206, 0.0208] | 0.0206 [0.0205, 0.0207] | 0.0388 | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |
| joint (a), on R0 windows (ADR-0025 S1) | 0.0194 [0.0157, 0.0232] | 0.0184 [0.0147, 0.0222] | 0.0193 [0.0191, 0.0195] | 0.0204 [0.0202, 0.0206] | 0.0388 | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |
| joint (d), on R0 windows (ADR-0026 R-joint-d) | 0.0172 [0.0135, 0.0209] | 0.0164 [0.0127, 0.0201] | 0.0216 [0.0212, 0.0220] | 0.0224 [0.0220, 0.0228] | 0.0388 | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |


Stated before the run: F3 read `tel_only`'s corrected mean test probability at 0.0176, 0.0173, 0.0189 against the test base rate 0.0388. The Platt map is fitted at the validation base rate 0.0211 and does not remove that shift.

## Part A: risk–coverage on clean test

| arm | AURC (disagreement) | AURC (random, mean of 100) | full-coverage selective risk | coverage at (τ, κ) | selective risk at (τ, κ) | AUPRC | caveats |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii) | 0.0477 [0.0436, 0.0520] | 0.0635 [0.0595, 0.0676] | 0.0635 | 0.8911 [0.8878, 0.8944] | 0.0577 [0.0537, 0.0618] | 0.0479 [0.0426, 0.0536] | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |
| joint (a), on R0 windows (ADR-0025 S1) | 0.0646 [0.0603, 0.0689] | 0.0830 [0.0784, 0.0876] | 0.0830 | 0.8854 [0.8825, 0.8883] | 0.0729 [0.0686, 0.0773] | 0.0567 [0.0499, 0.0643] | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |
| joint (d), on R0 windows (ADR-0026 R-joint-d) | 0.0413 [0.0377, 0.0449] | 0.0689 [0.0643, 0.0735] | 0.0689 | 0.8816 [0.8779, 0.8853] | 0.0496 [0.0458, 0.0534] | 0.0793 [0.0687, 0.0916] | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |


The random-ordering AURC's expectation is the full-coverage selective risk; the two columns are the sanity check the brief asked for.

**Margin signal, reported only** (covered when |p − τ| ≥ the validation cut):

| arm | coverage | selective risk | AURC (margin) | caveats |
| --- | --- | --- | --- | --- |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii) | 0.9145 [0.9117, 0.9173] | 0.0472 [0.0434, 0.0511] | 0.0424 [0.0382, 0.0469] | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |
| joint (a), on R0 windows (ADR-0025 S1) | 0.9033 [0.8996, 0.9069] | 0.0583 [0.0542, 0.0624] | 0.0706 [0.0651, 0.0762] | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |
| joint (d), on R0 windows (ADR-0026 R-joint-d) | 0.8876 [0.8828, 0.8924] | 0.0457 [0.0419, 0.0494] | 0.0717 [0.0653, 0.0780] | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |


**Risk–coverage curves** (disagreement ascending; selective risk at each coverage):

| coverage | tel_only backbone, (a), on R0 windows (ADR-0025 control iii) | joint (a), on R0 windows (ADR-0025 S1) | joint (d), on R0 windows (ADR-0026 R-joint-d) |
| --- | --- | --- | --- |
| 0.05 | 0.0366 | 0.0598 | 0.0336 |
| 0.10 | 0.0401 | 0.0598 | 0.0360 |
| 0.15 | 0.0411 | 0.0600 | 0.0351 |
| 0.20 | 0.0419 | 0.0602 | 0.0363 |
| 0.25 | 0.0432 | 0.0593 | 0.0370 |
| 0.30 | 0.0440 | 0.0596 | 0.0372 |
| 0.35 | 0.0441 | 0.0598 | 0.0379 |
| 0.40 | 0.0453 | 0.0603 | 0.0382 |
| 0.45 | 0.0458 | 0.0613 | 0.0385 |
| 0.50 | 0.0463 | 0.0620 | 0.0392 |
| 0.55 | 0.0471 | 0.0632 | 0.0402 |
| 0.60 | 0.0485 | 0.0643 | 0.0412 |
| 0.65 | 0.0495 | 0.0651 | 0.0422 |
| 0.70 | 0.0509 | 0.0665 | 0.0432 |
| 0.75 | 0.0521 | 0.0679 | 0.0446 |
| 0.80 | 0.0540 | 0.0695 | 0.0461 |
| 0.85 | 0.0559 | 0.0712 | 0.0478 |
| 0.90 | 0.0581 | 0.0739 | 0.0506 |
| 0.95 | 0.0610 | 0.0770 | 0.0547 |
| 1.00 | 0.0635 | 0.0830 | 0.0689 |


## Gate A: does seed disagreement order risk better than chance?

> PASS iff the 95% upper bound of AURC(seed disagreement) − AURC(random) is below zero; FAIL → abstention on that arm NOT EVALUABLE.

| arm | Δ AURC | discarded | outcome | caveats |
| --- | --- | --- | --- | --- |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii) | -0.0158 [-0.0177, -0.0140] | 0 | PASS | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |
| joint (a), on R0 windows (ADR-0025 S1) | -0.0184 [-0.0206, -0.0163] | 0 | PASS | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |
| joint (d), on R0 windows (ADR-0026 R-joint-d) | -0.0275 [-0.0302, -0.0250] | 0 | PASS | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |


## Gate B: does k = 8 damage joint (d)'s ranking?

> Paired Δ AUPRC(ensemble, k=8) − AUPRC(ensemble, clean); damage iff the upper bound is below zero, else H2 NOT TESTABLE.

| arm | Δ AUPRC | discarded | outcome | caveats |
| --- | --- | --- | --- | --- |
| joint (d), on R0 windows (ADR-0026 R-joint-d) | -0.0039 [-0.0082, -0.0001] | 0 | DAMAGE | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |


## H2

> SUPPORTED if the upper bound of Δcov is below zero AND the upper bound of Δrisk is below +0.005. REFUTED if the lower bound of Δcov is at or above zero AND the lower bound of Δrisk is above zero. Otherwise INCONCLUSIVE. Requires Gate A PASS on joint (d) and Gate B damage.

| arm | Gate A | Gate B | Δcov | Δrisk | verdict | caveats |
| --- | --- | --- | --- | --- | --- | --- |
| joint (d), on R0 windows (ADR-0026 R-joint-d) | PASS | DAMAGE | -0.0797 [-0.0841, -0.0753] | +0.0053 [+0.0033, +0.0074] | **INCONCLUSIVE** | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |


## The severity ladder on joint (d), as measured (no verdict)

| k | coverage | selective risk | AUPRC | ECE | mean p | margin coverage | margin risk | caveats |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0.8816 [0.8779, 0.8853] | 0.0496 [0.0458, 0.0534] | 0.0793 [0.0687, 0.0916] | 0.0172 [0.0135, 0.0209] | 0.0216 [0.0212, 0.0220] | 0.8876 [0.8828, 0.8924] | 0.0457 [0.0419, 0.0494] | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |
| 2 | 0.8960 [0.8927, 0.8993] | 0.0565 [0.0525, 0.0605] | 0.0867 [0.0748, 0.1005] | 0.0101 [0.0070, 0.0140] | 0.0286 [0.0283, 0.0290] | 0.8077 [0.8019, 0.8135] | 0.0483 [0.0444, 0.0521] | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |
| 4 | 0.8866 [0.8833, 0.8898] | 0.0557 [0.0517, 0.0596] | 0.0868 [0.0749, 0.1006] | 0.0080 [0.0061, 0.0116] | 0.0314 [0.0311, 0.0318] | 0.7442 [0.7384, 0.7501] | 0.0502 [0.0461, 0.0544] | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |
| 6 | 0.8467 [0.8429, 0.8503] | 0.0558 [0.0518, 0.0597] | 0.0823 [0.0714, 0.0950] | 0.0072 [0.0055, 0.0108] | 0.0323 [0.0319, 0.0327] | 0.7232 [0.7173, 0.7291] | 0.0521 [0.0478, 0.0564] | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |
| 8 | 0.8019 [0.7976, 0.8060] | 0.0549 [0.0509, 0.0589] | 0.0754 [0.0657, 0.0865] | 0.0068 [0.0050, 0.0100] | 0.0335 [0.0331, 0.0339] | 0.6758 [0.6697, 0.6817] | 0.0537 [0.0493, 0.0581] | ADR-0009 · forward in time, same sites · message-volume shift · three-seed ensemble · operating point at validation base rate 0.0211 vs test 0.0388 |


Channels masked at each k (nested): k=2: nacelle_position_deg, ambient_temp_c; k=4: nacelle_position_deg, ambient_temp_c, generator_speed_rpm, rotor_speed_rpm; k=6: nacelle_position_deg, ambient_temp_c, generator_speed_rpm, rotor_speed_rpm, generator_bearing_temp_c, power_pu; k=8: nacelle_position_deg, ambient_temp_c, generator_speed_rpm, rotor_speed_rpm, generator_bearing_temp_c, power_pu, pitch_angle_deg, generator_winding_temp_c.

## Claims the ADR-0028 outcome cites

| claim | source (this JSON) | reported | second reading | how | matches |
| --- | --- | --- | --- | --- | --- |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): ece_prior_corrected | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].ece_prior_corrected.value` | 0.018066 | 0.018066 | separate implementation on the scores | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): ece_prior_corrected 95% interval | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].ece_prior_corrected.low/high` | [0.014320, 0.021871] | [0.014320, 0.021871] | percentiles re-read from the replicate vector | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): mean_p_prior_corrected | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].mean_p_prior_corrected.value` | 0.020701 | 0.020701 | separate implementation on the scores | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): mean_p_prior_corrected 95% interval | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].mean_p_prior_corrected.low/high` | [0.020619, 0.020780] | [0.020619, 0.020780] | percentiles re-read from the replicate vector | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): coverage_at_operating_point | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].coverage_at_operating_point.value` | 0.891137 | 0.891137 | separate implementation on the scores | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): coverage_at_operating_point 95% interval | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].coverage_at_operating_point.low/high` | [0.887759, 0.894358] | [0.887759, 0.894358] | percentiles re-read from the replicate vector | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): selective_risk_at_operating_point | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].selective_risk_at_operating_point.value` | 0.057695 | 0.057695 | separate implementation on the scores | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): selective_risk_at_operating_point 95% interval | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].selective_risk_at_operating_point.low/high` | [0.053722, 0.061806] | [0.053722, 0.061806] | percentiles re-read from the replicate vector | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): aurc | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].aurc.value` | 0.047671 | 0.047671 | separate implementation on the scores | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): aurc 95% interval | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].aurc.low/high` | [0.043572, 0.051972] | [0.043572, 0.051972] | percentiles re-read from the replicate vector | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): aurc_random | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].aurc_random.value` | 0.063499 | 0.063499 | separate implementation on the scores | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): aurc_random 95% interval | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].aurc_random.low/high` | [0.059539, 0.067584] | [0.059539, 0.067584] | percentiles re-read from the replicate vector | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): ece_platt | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].ece_platt.value` | 0.018135 | 0.018135 | equal_mass_ece's table path | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): ece_platt 95% interval | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].ece_platt.low/high` | [0.014391, 0.021935] | [0.014391, 0.021935] | percentiles re-read from the replicate vector | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): random-ordering AURC ≈ full-coverage selective risk | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].aurc_random.value vs full_coverage_selective_risk` | 0.063499 | 0.063536 | sanity check: within 0.001 | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): Gate A Δ AURC | `gate_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].delta_aurc.value` | -0.015829 | -0.015829 | curve means, explicit permutations | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): Gate A Δ AURC 95% interval | `gate_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].delta_aurc.low/high` | [-0.017714, -0.013964] | [-0.017714, -0.013964] | percentiles re-read from the replicate vector | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): Gate A outcome | `gate_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].outcome` | pass | pass | the §2 sentence, applied by hand | yes |
| joint (a), on R0 windows (ADR-0025 S1): ece_prior_corrected | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].ece_prior_corrected.value` | 0.019440 | 0.019440 | separate implementation on the scores | yes |
| joint (a), on R0 windows (ADR-0025 S1): ece_prior_corrected 95% interval | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].ece_prior_corrected.low/high` | [0.015720, 0.023238] | [0.015720, 0.023238] | percentiles re-read from the replicate vector | yes |
| joint (a), on R0 windows (ADR-0025 S1): mean_p_prior_corrected | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].mean_p_prior_corrected.value` | 0.019326 | 0.019326 | separate implementation on the scores | yes |
| joint (a), on R0 windows (ADR-0025 S1): mean_p_prior_corrected 95% interval | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].mean_p_prior_corrected.low/high` | [0.019134, 0.019516] | [0.019134, 0.019516] | percentiles re-read from the replicate vector | yes |
| joint (a), on R0 windows (ADR-0025 S1): coverage_at_operating_point | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].coverage_at_operating_point.value` | 0.885393 | 0.885393 | separate implementation on the scores | yes |
| joint (a), on R0 windows (ADR-0025 S1): coverage_at_operating_point 95% interval | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].coverage_at_operating_point.low/high` | [0.882455, 0.888303] | [0.882455, 0.888303] | percentiles re-read from the replicate vector | yes |
| joint (a), on R0 windows (ADR-0025 S1): selective_risk_at_operating_point | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].selective_risk_at_operating_point.value` | 0.072947 | 0.072947 | separate implementation on the scores | yes |
| joint (a), on R0 windows (ADR-0025 S1): selective_risk_at_operating_point 95% interval | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].selective_risk_at_operating_point.low/high` | [0.068570, 0.077345] | [0.068570, 0.077345] | percentiles re-read from the replicate vector | yes |
| joint (a), on R0 windows (ADR-0025 S1): aurc | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].aurc.value` | 0.064567 | 0.064567 | separate implementation on the scores | yes |
| joint (a), on R0 windows (ADR-0025 S1): aurc 95% interval | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].aurc.low/high` | [0.060295, 0.068884] | [0.060295, 0.068884] | percentiles re-read from the replicate vector | yes |
| joint (a), on R0 windows (ADR-0025 S1): aurc_random | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].aurc_random.value` | 0.082987 | 0.082987 | separate implementation on the scores | yes |
| joint (a), on R0 windows (ADR-0025 S1): aurc_random 95% interval | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].aurc_random.low/high` | [0.078383, 0.087644] | [0.078383, 0.087644] | percentiles re-read from the replicate vector | yes |
| joint (a), on R0 windows (ADR-0025 S1): ece_platt | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].ece_platt.value` | 0.018379 | 0.018379 | equal_mass_ece's table path | yes |
| joint (a), on R0 windows (ADR-0025 S1): ece_platt 95% interval | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].ece_platt.low/high` | [0.014662, 0.022182] | [0.014662, 0.022182] | percentiles re-read from the replicate vector | yes |
| joint (a), on R0 windows (ADR-0025 S1): random-ordering AURC ≈ full-coverage selective risk | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].aurc_random.value vs full_coverage_selective_risk` | 0.082987 | 0.083014 | sanity check: within 0.001 | yes |
| joint (a), on R0 windows (ADR-0025 S1): Gate A Δ AURC | `gate_a['joint (a), on R0 windows (ADR-0025 S1)'].delta_aurc.value` | -0.018420 | -0.018420 | curve means, explicit permutations | yes |
| joint (a), on R0 windows (ADR-0025 S1): Gate A Δ AURC 95% interval | `gate_a['joint (a), on R0 windows (ADR-0025 S1)'].delta_aurc.low/high` | [-0.020615, -0.016285] | [-0.020615, -0.016285] | percentiles re-read from the replicate vector | yes |
| joint (a), on R0 windows (ADR-0025 S1): Gate A outcome | `gate_a['joint (a), on R0 windows (ADR-0025 S1)'].outcome` | pass | pass | the §2 sentence, applied by hand | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): ece_prior_corrected | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].ece_prior_corrected.value` | 0.017168 | 0.017168 | separate implementation on the scores | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): ece_prior_corrected 95% interval | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].ece_prior_corrected.low/high` | [0.013497, 0.020908] | [0.013497, 0.020908] | percentiles re-read from the replicate vector | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): mean_p_prior_corrected | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].mean_p_prior_corrected.value` | 0.021599 | 0.021599 | separate implementation on the scores | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): mean_p_prior_corrected 95% interval | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].mean_p_prior_corrected.low/high` | [0.021247, 0.021963] | [0.021247, 0.021963] | percentiles re-read from the replicate vector | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): coverage_at_operating_point | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].coverage_at_operating_point.value` | 0.881591 | 0.881591 | separate implementation on the scores | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): coverage_at_operating_point 95% interval | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].coverage_at_operating_point.low/high` | [0.877944, 0.885265] | [0.877944, 0.885265] | percentiles re-read from the replicate vector | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): selective_risk_at_operating_point | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].selective_risk_at_operating_point.value` | 0.049611 | 0.049611 | separate implementation on the scores | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): selective_risk_at_operating_point 95% interval | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].selective_risk_at_operating_point.low/high` | [0.045795, 0.053396] | [0.045795, 0.053396] | percentiles re-read from the replicate vector | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): aurc | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].aurc.value` | 0.041317 | 0.041317 | separate implementation on the scores | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): aurc 95% interval | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].aurc.low/high` | [0.037735, 0.044936] | [0.037735, 0.044936] | percentiles re-read from the replicate vector | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): aurc_random | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].aurc_random.value` | 0.068853 | 0.068853 | separate implementation on the scores | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): aurc_random 95% interval | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].aurc_random.low/high` | [0.064296, 0.073454] | [0.064296, 0.073454] | percentiles re-read from the replicate vector | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): ece_platt | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].ece_platt.value` | 0.016381 | 0.016381 | equal_mass_ece's table path | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): ece_platt 95% interval | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].ece_platt.low/high` | [0.012707, 0.020118] | [0.012707, 0.020118] | percentiles re-read from the replicate vector | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): random-ordering AURC ≈ full-coverage selective risk | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].aurc_random.value vs full_coverage_selective_risk` | 0.068853 | 0.068907 | sanity check: within 0.001 | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): Gate A Δ AURC | `gate_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].delta_aurc.value` | -0.027536 | -0.027536 | curve means, explicit permutations | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): Gate A Δ AURC 95% interval | `gate_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].delta_aurc.low/high` | [-0.030228, -0.025014] | [-0.030228, -0.025014] | percentiles re-read from the replicate vector | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): Gate A outcome | `gate_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].outcome` | pass | pass | the §2 sentence, applied by hand | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): tau | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].operating_point.tau` | 0.035302 | 0.035302 | the committed validation record | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): kappa | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].operating_point.kappa` | 0.325722 | 0.325722 | the committed validation record | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): mean_p_platt | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].mean_p_platt.value` | 0.020632 | 0.020632 | mean of the Platt-mapped scores | yes |
| tel_only backbone, (a), on R0 windows (ADR-0025 control iii): mean_p_platt 95% interval | `part_a['tel_only backbone, (a), on R0 windows (ADR-0025 control iii)'].mean_p_platt.low/high` | [0.020534, 0.020728] | [0.020534, 0.020728] | percentiles re-read from the replicate vector | yes |
| joint (a), on R0 windows (ADR-0025 S1): tau | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].operating_point.tau` | 0.040962 | 0.040962 | the committed validation record | yes |
| joint (a), on R0 windows (ADR-0025 S1): kappa | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].operating_point.kappa` | 0.332228 | 0.332228 | the committed validation record | yes |
| joint (a), on R0 windows (ADR-0025 S1): mean_p_platt | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].mean_p_platt.value` | 0.020388 | 0.020388 | mean of the Platt-mapped scores | yes |
| joint (a), on R0 windows (ADR-0025 S1): mean_p_platt 95% interval | `part_a['joint (a), on R0 windows (ADR-0025 S1)'].mean_p_platt.low/high` | [0.020177, 0.020595] | [0.020177, 0.020595] | percentiles re-read from the replicate vector | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): tau | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].operating_point.tau` | 0.063736 | 0.063736 | the committed validation record | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): kappa | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].operating_point.kappa` | 0.338802 | 0.338802 | the committed validation record | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): mean_p_platt | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].mean_p_platt.value` | 0.022385 | 0.022385 | mean of the Platt-mapped scores | yes |
| joint (d), on R0 windows (ADR-0026 R-joint-d): mean_p_platt 95% interval | `part_a['joint (d), on R0 windows (ADR-0026 R-joint-d)'].mean_p_platt.low/high` | [0.022006, 0.022777] | [0.022006, 0.022777] | percentiles re-read from the replicate vector | yes |
| ladder k=2: coverage | `ladder[k=2].coverage.value` | 0.896048 | 0.896048 | separate implementation on the scores | yes |
| ladder k=2: coverage 95% interval | `ladder[k=2].coverage.low/high` | [0.892718, 0.899284] | [0.892718, 0.899284] | percentiles re-read from the replicate vector | yes |
| ladder k=2: risk | `ladder[k=2].risk.value` | 0.056548 | 0.056548 | separate implementation on the scores | yes |
| ladder k=2: risk 95% interval | `ladder[k=2].risk.low/high` | [0.052516, 0.060521] | [0.052516, 0.060521] | percentiles re-read from the replicate vector | yes |
| ladder k=2: auprc | `ladder[k=2].auprc.value` | 0.086710 | 0.086710 | separate implementation on the scores | yes |
| ladder k=2: auprc 95% interval | `ladder[k=2].auprc.low/high` | [0.074848, 0.100483] | [0.074848, 0.100483] | percentiles re-read from the replicate vector | yes |
| ladder k=2: ece | `ladder[k=2].ece.value` | 0.010118 | 0.010118 | separate implementation on the scores | yes |
| ladder k=2: ece 95% interval | `ladder[k=2].ece.low/high` | [0.007002, 0.013957] | [0.007002, 0.013957] | percentiles re-read from the replicate vector | yes |
| ladder k=2: mean_p | `ladder[k=2].mean_p.value` | 0.028649 | 0.028649 | separate implementation on the scores | yes |
| ladder k=2: mean_p 95% interval | `ladder[k=2].mean_p.low/high` | [0.028279, 0.029027] | [0.028279, 0.029027] | percentiles re-read from the replicate vector | yes |
| ladder k=4: coverage | `ladder[k=4].coverage.value` | 0.886648 | 0.886648 | separate implementation on the scores | yes |
| ladder k=4: coverage 95% interval | `ladder[k=4].coverage.low/high` | [0.883344, 0.889842] | [0.883344, 0.889842] | percentiles re-read from the replicate vector | yes |
| ladder k=4: risk | `ladder[k=4].risk.value` | 0.055666 | 0.055666 | separate implementation on the scores | yes |
| ladder k=4: risk 95% interval | `ladder[k=4].risk.low/high` | [0.051726, 0.059571] | [0.051726, 0.059571] | percentiles re-read from the replicate vector | yes |
| ladder k=4: auprc | `ladder[k=4].auprc.value` | 0.086777 | 0.086777 | separate implementation on the scores | yes |
| ladder k=4: auprc 95% interval | `ladder[k=4].auprc.low/high` | [0.074933, 0.100558] | [0.074933, 0.100558] | percentiles re-read from the replicate vector | yes |
| ladder k=4: ece | `ladder[k=4].ece.value` | 0.008041 | 0.008041 | separate implementation on the scores | yes |
| ladder k=4: ece 95% interval | `ladder[k=4].ece.low/high` | [0.006090, 0.011628] | [0.006090, 0.011628] | percentiles re-read from the replicate vector | yes |
| ladder k=4: mean_p | `ladder[k=4].mean_p.value` | 0.031423 | 0.031423 | separate implementation on the scores | yes |
| ladder k=4: mean_p 95% interval | `ladder[k=4].mean_p.low/high` | [0.031051, 0.031808] | [0.031051, 0.031808] | percentiles re-read from the replicate vector | yes |
| ladder k=6: coverage | `ladder[k=6].coverage.value` | 0.846678 | 0.846678 | separate implementation on the scores | yes |
| ladder k=6: coverage 95% interval | `ladder[k=6].coverage.low/high` | [0.842895, 0.850335] | [0.842895, 0.850335] | percentiles re-read from the replicate vector | yes |
| ladder k=6: risk | `ladder[k=6].risk.value` | 0.055829 | 0.055829 | separate implementation on the scores | yes |
| ladder k=6: risk 95% interval | `ladder[k=6].risk.low/high` | [0.051775, 0.059744] | [0.051775, 0.059744] | percentiles re-read from the replicate vector | yes |
| ladder k=6: auprc | `ladder[k=6].auprc.value` | 0.082273 | 0.082273 | separate implementation on the scores | yes |
| ladder k=6: auprc 95% interval | `ladder[k=6].auprc.low/high` | [0.071412, 0.094987] | [0.071412, 0.094987] | percentiles re-read from the replicate vector | yes |
| ladder k=6: ece | `ladder[k=6].ece.value` | 0.007216 | 0.007216 | separate implementation on the scores | yes |
| ladder k=6: ece 95% interval | `ladder[k=6].ece.low/high` | [0.005476, 0.010760] | [0.005476, 0.010760] | percentiles re-read from the replicate vector | yes |
| ladder k=6: mean_p | `ladder[k=6].mean_p.value` | 0.032320 | 0.032320 | separate implementation on the scores | yes |
| ladder k=6: mean_p 95% interval | `ladder[k=6].mean_p.low/high` | [0.031940, 0.032712] | [0.031940, 0.032712] | percentiles re-read from the replicate vector | yes |
| ladder k=8: coverage | `ladder[k=8].coverage.value` | 0.801912 | 0.801912 | separate implementation on the scores | yes |
| ladder k=8: coverage 95% interval | `ladder[k=8].coverage.low/high` | [0.797649, 0.806036] | [0.797649, 0.806036] | percentiles re-read from the replicate vector | yes |
| ladder k=8: risk | `ladder[k=8].risk.value` | 0.054941 | 0.054941 | separate implementation on the scores | yes |
| ladder k=8: risk 95% interval | `ladder[k=8].risk.low/high` | [0.050882, 0.058886] | [0.050882, 0.058886] | percentiles re-read from the replicate vector | yes |
| ladder k=8: auprc | `ladder[k=8].auprc.value` | 0.075449 | 0.075449 | separate implementation on the scores | yes |
| ladder k=8: auprc 95% interval | `ladder[k=8].auprc.low/high` | [0.065702, 0.086507] | [0.065702, 0.086507] | percentiles re-read from the replicate vector | yes |
| ladder k=8: ece | `ladder[k=8].ece.value` | 0.006763 | 0.006763 | separate implementation on the scores | yes |
| ladder k=8: ece 95% interval | `ladder[k=8].ece.low/high` | [0.004971, 0.009968] | [0.004971, 0.009968] | percentiles re-read from the replicate vector | yes |
| ladder k=8: mean_p | `ladder[k=8].mean_p.value` | 0.033492 | 0.033492 | separate implementation on the scores | yes |
| ladder k=8: mean_p 95% interval | `ladder[k=8].mean_p.low/high` | [0.033134, 0.033863] | [0.033134, 0.033863] | percentiles re-read from the replicate vector | yes |
| Gate B Δ AUPRC (k=8 − clean) | `gate_b.delta_auprc.value` | -0.003865 | -0.003865 | separate implementation on both sides | yes |
| Gate B Δ AUPRC (k=8 − clean) 95% interval | `gate_b.delta_auprc.low/high` | [-0.008225, -0.000066] | [-0.008225, -0.000066] | percentiles of the re-read paired difference | yes |
| H2 Δcov (k=8 − clean) | `h2.delta_coverage.value` | -0.079679 | -0.079679 | separate implementation on both sides | yes |
| H2 Δcov (k=8 − clean) 95% interval | `h2.delta_coverage.low/high` | [-0.084126, -0.075349] | [-0.084126, -0.075349] | percentiles of the re-read paired difference | yes |
| H2 Δrisk (k=8 − clean) | `h2.delta_selective_risk.value` | 0.005330 | 0.005330 | separate implementation on both sides | yes |
| H2 Δrisk (k=8 − clean) 95% interval | `h2.delta_selective_risk.low/high` | [0.003268, 0.007421] | [0.003268, 0.007421] | percentiles of the re-read paired difference | yes |
| Gate B outcome | `gate_b.outcome` | damage | damage | the §3 sentence by hand | yes |
| H2 verdict | `h2.verdict` | inconclusive | inconclusive | the §3 clauses by hand | yes |


## Reliability after Platt: tel_only backbone, (a), on R0 windows (ADR-0025 control iii)

| bin | windows | p range | mean p | positive share | gap |
| --- | --- | --- | --- | --- | --- |
| 1 | 9,135 | 0.0071–0.0130 | 0.0112 | 0.0385 | -0.0274 |
| 2 | 9,135 | 0.0130–0.0144 | 0.0138 | 0.0380 | -0.0242 |
| 3 | 9,135 | 0.0144–0.0153 | 0.0149 | 0.0299 | -0.0150 |
| 4 | 9,135 | 0.0153–0.0161 | 0.0157 | 0.0298 | -0.0140 |
| 5 | 9,135 | 0.0161–0.0168 | 0.0165 | 0.0285 | -0.0120 |
| 6 | 9,135 | 0.0168–0.0175 | 0.0172 | 0.0292 | -0.0121 |
| 7 | 9,135 | 0.0175–0.0183 | 0.0179 | 0.0308 | -0.0129 |
| 8 | 9,135 | 0.0183–0.0192 | 0.0187 | 0.0336 | -0.0149 |
| 9 | 9,135 | 0.0192–0.0202 | 0.0197 | 0.0350 | -0.0153 |
| 10 | 9,135 | 0.0202–0.0214 | 0.0208 | 0.0381 | -0.0173 |
| 11 | 9,135 | 0.0214–0.0229 | 0.0222 | 0.0404 | -0.0182 |
| 12 | 9,135 | 0.0229–0.0251 | 0.0239 | 0.0482 | -0.0243 |
| 13 | 9,135 | 0.0251–0.0286 | 0.0267 | 0.0588 | -0.0321 |
| 14 | 9,135 | 0.0286–0.0329 | 0.0307 | 0.0467 | -0.0161 |
| 15 | 9,135 | 0.0329–0.1037 | 0.0397 | 0.0560 | -0.0164 |


## Reliability after Platt: joint (a), on R0 windows (ADR-0025 S1)

| bin | windows | p range | mean p | positive share | gap |
| --- | --- | --- | --- | --- | --- |
| 1 | 9,135 | 0.0067–0.0107 | 0.0098 | 0.0243 | -0.0145 |
| 2 | 9,135 | 0.0107–0.0116 | 0.0112 | 0.0261 | -0.0149 |
| 3 | 9,135 | 0.0116–0.0124 | 0.0120 | 0.0262 | -0.0141 |
| 4 | 9,135 | 0.0124–0.0132 | 0.0128 | 0.0247 | -0.0120 |
| 5 | 9,135 | 0.0132–0.0139 | 0.0135 | 0.0275 | -0.0139 |
| 6 | 9,135 | 0.0139–0.0148 | 0.0143 | 0.0286 | -0.0142 |
| 7 | 9,135 | 0.0148–0.0157 | 0.0152 | 0.0292 | -0.0140 |
| 8 | 9,135 | 0.0157–0.0168 | 0.0162 | 0.0339 | -0.0177 |
| 9 | 9,135 | 0.0168–0.0183 | 0.0175 | 0.0359 | -0.0184 |
| 10 | 9,135 | 0.0183–0.0202 | 0.0192 | 0.0407 | -0.0216 |
| 11 | 9,135 | 0.0202–0.0226 | 0.0214 | 0.0451 | -0.0237 |
| 12 | 9,135 | 0.0226–0.0257 | 0.0241 | 0.0484 | -0.0243 |
| 13 | 9,135 | 0.0257–0.0305 | 0.0279 | 0.0556 | -0.0277 |
| 14 | 9,135 | 0.0305–0.0401 | 0.0346 | 0.0622 | -0.0276 |
| 15 | 9,135 | 0.0401–0.1793 | 0.0560 | 0.0731 | -0.0171 |


## Reliability after Platt: joint (d), on R0 windows (ADR-0026 R-joint-d)

| bin | windows | p range | mean p | positive share | gap |
| --- | --- | --- | --- | --- | --- |
| 1 | 9,135 | 0.0054–0.0095 | 0.0086 | 0.0207 | -0.0121 |
| 2 | 9,135 | 0.0095–0.0107 | 0.0101 | 0.0219 | -0.0118 |
| 3 | 9,135 | 0.0107–0.0117 | 0.0112 | 0.0219 | -0.0107 |
| 4 | 9,135 | 0.0117–0.0125 | 0.0121 | 0.0222 | -0.0101 |
| 5 | 9,135 | 0.0125–0.0133 | 0.0129 | 0.0207 | -0.0078 |
| 6 | 9,135 | 0.0133–0.0142 | 0.0138 | 0.0215 | -0.0077 |
| 7 | 9,135 | 0.0142–0.0152 | 0.0147 | 0.0270 | -0.0123 |
| 8 | 9,135 | 0.0152–0.0163 | 0.0158 | 0.0229 | -0.0071 |
| 9 | 9,135 | 0.0163–0.0177 | 0.0170 | 0.0298 | -0.0128 |
| 10 | 9,135 | 0.0177–0.0196 | 0.0186 | 0.0321 | -0.0135 |
| 11 | 9,135 | 0.0196–0.0223 | 0.0208 | 0.0367 | -0.0158 |
| 12 | 9,135 | 0.0223–0.0263 | 0.0241 | 0.0452 | -0.0211 |
| 13 | 9,135 | 0.0263–0.0332 | 0.0294 | 0.0633 | -0.0339 |
| 14 | 9,135 | 0.0332–0.0497 | 0.0400 | 0.0849 | -0.0449 |
| 15 | 9,135 | 0.0497–0.4111 | 0.0866 | 0.1108 | -0.0242 |


## Caveats, on every row (ADR-0028 §4)

- ADR-0009: one harmonised event rule across sites
- forward in time, same sites (ADR-0022): never site shift
- message-volume shift (ADR-0025)
- a three-seed ensemble is a small ensemble
- operating point fixed at validation base rate 0.0211
- Message-volume shift: Kelmarsh positives average 67.2 status tokens in train (stride 6) and 190.1 in test (stride 12).
