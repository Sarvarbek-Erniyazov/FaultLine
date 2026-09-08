# Reports

Tracked evidence. Markdown and small JSON only — no images over 1 MB, no data.

```
reports/
└── data/
    ├── <run_id>/                          one directory per pipeline run
    │   ├── <config>.yaml                  verbatim copy of the config that drove the run
    │   ├── <stage>_stats_report.md        one per stage
    │   ├── run.json                       config hash, git SHA, Python, platform, timings, counts
    │   └── run.log
    └── raw_inventory_<source>_<date>.md   archive inventory and the free-text verdict
```

`<run_id>` is `<YYYYMMDD-HHMMSS>_<stage>_<modality>_<config hash>`, so two runs of the
same configuration are recognisable at a glance and any report traces back to the exact
YAML that produced it.

## Why these are committed

A number in a paper or a README has to be traceable to something. These reports are
that something: what went in, what came out, what was dropped and why, under which
configuration and at which commit. They are small, they are text, and they diff —
which makes a change in the data as reviewable as a change in the code.

The raw inventory reports carry the answer to the question ADR-0001 rests on: whether
public SCADA event logs contain open-ended operator prose, or a controlled vocabulary
of template strings.
