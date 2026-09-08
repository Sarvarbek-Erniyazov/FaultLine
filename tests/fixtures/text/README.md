# Text fixture corpus

## Provenance

`sample.jsonl` is **synthetic**. Every document was generated for this repository by
a seeded script; none of it is copied, scraped or adapted from any third-party
corpus, and none of it describes a real event, site, person or organisation.

- Written: 2026-09-09, seed `20260909`
- Licence: MIT, same as the rest of this repository
- Size: 55 documents, ~35 KB

The email addresses (`example.org`, `example.com`, `example.net`) and telephone
numbers use ranges reserved for documentation and fiction, so nothing here reaches a
real mailbox or handset. Names and equipment references are generic.

## What it is for

To exercise every branch of the text pipeline without a network or a real corpus. It
is deliberately unrepresentative — a real corpus is not 9% duplicates — because the
job of a fixture is to hit the edges, not to look typical.

| documents | what they exercise |
| --- | --- |
| 30 | ordinary paragraphs that pass every quality rule |
| 4 | email addresses, telephone numbers and large digit runs, so the PII policy of ADR-0005 is visible: emails and phones are masked, magnitudes such as `1850 kW` and `9876543 kWh` survive |
| 4 | HTML tags and entities, CRLF line endings, em-dashes, curly quotes, degree signs and full-width digits, so entity decoding, tag stripping and NFKC normalisation are all covered |
| 3 | a dozen identical lines each, tripping the repeated-line ratio |
| 3 | digits and punctuation only, tripping the alphabetic-ratio rule |
| 5 | under 200 characters, tripping the minimum-length rule |
| 5 | exact duplicates of earlier documents, including one uppercased and one whitespace-padded, so the case- and whitespace-insensitive hash is covered |
| 1 | markup and whitespace only, cleaning to an empty string |

## Regenerating

The generator is not committed as a script, because the fixture is an artefact under
test: regenerating it would change the counts that the pipeline tests assert, which is
precisely the kind of silent drift a fixture is supposed to prevent. Treat
`sample.jsonl` as the source of truth and edit it by hand if a new case is needed.
