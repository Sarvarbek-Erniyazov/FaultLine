# Configuration

Every run is driven by exactly one YAML file, and that file is evidence.

## Rules

1. **Naming:** `<family>/<name>_v<N>.yaml`. Families are `data/`, `tokenizer/`,
   `model/`, `train/`, `eval/`.
2. **One file per run.** A run reads one config and records its hash.
3. **A run never edits its own config.** Changing a threshold means writing
   `_v<N+1>.yaml`, not editing `_v<N>.yaml`. Older versions stay in the repository so
   that an old report remains reproducible.
4. **Every value carries its provenance in a comment.** Where a number came from,
   and what would change it. A threshold with no comment is a bug.
5. **Unknown keys are a hard error.** Configs are validated by pydantic models with
   `extra="forbid"`, so a typo fails the run instead of silently reverting to a
   default.
6. **Unknown values are written as `TODO(m<N>): <exact question>`,** never as an
   invented number.

## What a run leaves behind

`reports/data/<run_id>/` holds a verbatim copy of the config, one Markdown stats
report per stage, `run.log` and `run.json` (config hash, git SHA, Python version,
platform, elapsed time, per-stage row counts). The run id embeds the config hash, so
two runs of the same config are recognisable at a glance.

## Families

| family | status | contents |
| --- | --- | --- |
| `data/` | in use | text and telemetry pipelines, source specifications, channel maps, split specification |
| `tokenizer/` | M1/M2 | quantile-bin fitting, byte-level BPE training |
| `model/` | M1 | architecture and vocabulary layout sizes |
| `train/` | M1 | optimisation, schedule, checkpointing |
| `eval/` | M1 | risk, calibration and shift evaluation |
