# Data

Two modalities, four stages, one contract. **Raw and derived data never enter git**;
dataset cards, checksum manifests and stats reports do, and they are what make the
staged corpus reconstructible from this repository plus the public archives.

## Layout

```
data/
├── cards/                       TRACKED
│   ├── <source>.md              generated dataset card, one per source
│   └── manifests/<source>.json  file list with sizes, md5, URLs, licence, retrieval date
├── raw/{telemetry,text}/<source>/       git-ignored: exactly what the provider published
├── cleaned/{telemetry,text}/            git-ignored
├── filtered/{telemetry,text}/           git-ignored
└── final/{telemetry,text,paired}/       git-ignored
```

The four stage directories are created on demand by `faultline.paths`; there are no
`.gitkeep` placeholders inside them, because an empty tracked file inside an ignored
directory invites exactly the accident the ignore rule exists to prevent.

Set `FAULTLINE_DATA_ROOT` to move the stage directories to another drive. `cards/`
always stays in the repository: it is code-adjacent evidence, not data.

## The stage contract

Both pipelines obey the same rules:

1. One YAML drives a run; the run copies it into `reports/data/<run_id>/` with its hash.
2. A stage reads **only** from the previous stage's directory.
3. A stage that cannot produce a Markdown stats report is not a stage. The abstract
   base class enforces this rather than leaving it to convention.
4. Nothing is edited in place. A stage writes forward; unwanted output is removed by
   removing a stage directory, never by rewriting a file.

## Text

| stage | reads | writes |
| --- | --- | --- |
| `clean` | `raw/text/<corpus>.jsonl` | `cleaned/text/<corpus>.jsonl` |
| `filter` | `cleaned/text/<corpus>.jsonl` | `filtered/text/<corpus>.jsonl` |
| `dedup` | `filtered/text/<corpus>.jsonl` | `filtered/text/<corpus>.dedup.jsonl` |
| `pii` | `filtered/text/<corpus>.dedup.jsonl` | `filtered/text/<corpus>.pii.jsonl` |
| `final` | `filtered/text/<corpus>.pii.jsonl` | `final/text/<corpus>/<split>-NNNNN.jsonl` |

Five stages over four directories: `dedup` and `pii` both refine the filtered corpus,
so they stay inside `filtered/` with distinct suffixes rather than inventing stage
directories the four-stage contract does not have.

## Telemetry

| stage | reads | writes |
| --- | --- | --- |
| `ingest` | `raw/telemetry/<source>/*.zip`, read in place | `cleaned/telemetry/<source>/ingest/<turbine>__<year>.parquet` and `events.parquet` |
| `clean` | `cleaned/telemetry/<source>/ingest/` | `cleaned/telemetry/<source>/` |
| `filter` | `cleaned/telemetry/<source>/` | `filtered/telemetry/<source>/` |
| `final` | `filtered/telemetry/<source>/` | `final/telemetry/<source>/` |

Archives are read **inside the zip**. Tier 1 is roughly 17 GB compressed; extracting
it would double that for no benefit, since `zipfile` hands pandas a perfectly usable
file object.

The unit of work is one `(source, turbine, year)` Parquet file, which caps peak memory
at a single turbine-year — about 52,000 rows at 10-minute resolution.

## `paired/`

Reserved for M3: aligned telemetry windows and text segments. Empty until the joint
model exists.

## Imputation masks

Every imputed channel in `final/telemetry/` carries a boolean `<channel>__imputed`
column. It is a model input, not bookkeeping: sensors fail around the events this
project predicts, so a model that cannot tell a measurement from an interpolation
would be scored partly on its own guesses (ADR-0006).
