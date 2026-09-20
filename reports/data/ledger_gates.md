# Ledger. The pre-registered gates

Every rule was committed before the run it governs.

| ADR | question | registered | registering commit | outcome | outcome commit |
| --- | --- | --- | --- | --- | --- |
| ADR-0021 | The held-out-site gate: `tel_only` at full budget must put Hill of Towie's AUPRC interval above... | pre-registered 2026-09-16 | `ce9c8ad` | NOT EVALUABLE; leave-site-out is a reported negative, and the fallback is chosen under ADR-0022 | `ed60e8d` |
| ADR-0022 | The primary evaluation axis after ADR-0021: the selection rule, the CARE facts and scoring prot... | registered 2026-09-17 | `801ab71` | CARE is NOT EVALUABLE at chance on all three seeds; the in-distribution temporal split is EVALU... | `d87a524` |
| ADR-0023 | The random-init probe control: can the frozen probe see backbone quality? | pre-registered 2026-09-16 | `c9489a2` | FAIL: the final-position frozen probe cannot tell the trained backbone from an untrained one | `81a8fab` |
| ADR-0024 | The probe-sensitivity criterion is a paired test, and a bag-of-tokens comparator is reported be... | pre-registered 2026-09-17 | `79d4e97` | PASS: the final-position frozen probe sees the pretrained backbone; §a is the probe in force | `f6c2df0` |
| ADR-0025 | H1: the joint arm against `tel_only`, forward-in-time on the training sites | registered 2026-09-18 | `3e29202` | H1 is INCONCLUSIVE at this budget | `23699ee` |
| ADR-0026 | F7': is the read-out the limit? Text-aware linear probes on the existing joint backbones | registered 2026-09-20 | `319ae3b` | the gate PASSES and H1' is SUPPORTED | `9beebaa` |

6 gates, ADR-0021 through ADR-0026, each read from its section of `docs/DECISIONS.md`. The rule was written into that file and committed in its own commit before the run it governs; the outcome was written under the rule afterwards. The outcome commit is the commit that wrote the outcome section, found by log rather than self-cited.
