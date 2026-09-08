# Kelmarsh fixture excerpt

## Provenance and licence

These two files are **verbatim excerpts of third-party data**, not synthetic. They are
redistributed here under the terms of the licence below.

> Cubico Sustainable Investments Ltd, Kelmarsh wind farm data, Zenodo,
> doi:[10.5281/zenodo.5841833](https://doi.org/10.5281/zenodo.5841833)
> (version-pinned record [16807551](https://zenodo.org/records/16807551)),
> licensed **CC BY 4.0**.

**Changes made:** truncation only. The commented preamble is kept byte for byte and
the retained data rows are contiguous and unaltered. No value was changed,
reordered, resampled or anonymised.

The SCADA window deliberately straddles the point where the turbine starts
reporting (2016-01-23 12:10 UTC): 8 all-NaN rows followed by 32 rows with real
values. The first rows of the file are all NaN -- the turbine was commissioned in
April 2016 -- so an excerpt taken from the top would test the parser against
nothing but missing data.

| file | source member (in `Kelmarsh_SCADA_2016_3082.zip`) | rows kept | size |
| --- | --- | --- | --- |
| `Turbine_Data_Kelmarsh_1_excerpt.csv` | `Turbine_Data_Kelmarsh_1_2016-01-03_-_2017-01-01_228.csv` | 40 (rows 2945-2984) | 69 KB |
| `Status_Kelmarsh_1_excerpt.csv` | `Status_Kelmarsh_1_2016-01-03_-_2017-01-01_228.csv` | 200 | 25 KB |

Extracted 2026-09-09. Total 94 KB, well inside the repository's 5 MB per-file limit.

## Why real bytes rather than a synthetic fixture

The rest of the test suite runs on synthetic data on purpose: it is licence-free,
it makes the expected counts obvious, and it can be shaped to hit every branch.

These two files are the deliberate exception, because the adapter's job is to survive
one specific provider's quirks, and a synthetic fixture would only ever reproduce the
quirks the author already knew about. Concretely, these excerpts pin:

- the nine-line `#` preamble, and the fact that the **turbine-data header is itself a
  comment line** while the status header is not — the difference that produced a
  confidently wrong inspection verdict before it was noticed;
- the `# Turbine:` and `# Time zone: UTC` lines the adapter reads instead of guessing
  the turbine from a file name or assuming a timezone;
- the real 299-column header, including quoted fields containing commas
  (`"Wind speed, Standard deviation (m/s)"`), which naive comma-splitting gets wrong;
- genuine `NaN` values alongside real readings, so the loader is tested against real
  missingness rather than a tidy synthetic block;
- real status rows with their `Code`, `Message` and `Status` columns, which is the
  evidence behind the free-text verdict in ADR-0001.

Only 40 SCADA rows are kept: at 299 columns a row is ~1.5 KB, so 200 would cost
300 KB for no extra coverage. The status file keeps the full 200 rows.

## Regenerating

Re-extract from the staged archive after running
`faultline download telemetry --tier 1 --source kelmarsh`. Do not hand-edit these
files: an edited excerpt is no longer the provider's data, and the whole point is that
it is.
