# PHMSA gate: decision brief

**Scope:** read-only investigation. No config, code, ADR or memory file edited; no corpus
data downloaded or staged; nothing committed. Network requests were made with plain
clients and default User-Agents (curl/8.15.0, from this machine's home network), with no
retry, spoofing, proxy or mirror. Requests went out between 20:16 and 20:18 UTC on
2026-09-15 (server `Date` headers).

**Headline:** the named zip is still blocked (403 from Akamai, now from a third client and
network). But the catalogue record ADR-0016 calls "does the same", `27nc-rsge`, carries
**15 per-type incident-data zips hosted on data.transportation.gov itself**. All 15
answered `200 OK` to a headers-only request, on a path robots.txt permits. ADR-0016 and
`sources_text.yaml` record that no such route exists. That changes the options below.

---

## 1. What the download failure actually is

### 1a. Is a copy already on the machine? (measured)

Searched `~/Downloads`, `~/Desktop`, `~/Documents` (depth 4) and `~/OneDrive` (depth 5)
for `*phmsa*`, `*flagged*` and `*pipeline*incident*`, any extension. Windows known-folder
paths resolve to the same three directories (`[Environment]::GetFolderPath`), so nothing
is redirected elsewhere.

- **No match in any location.** No `.zip`, `.zip.part`, `.crdownload` or `.html` by those
  names.
- As a second pass, every `.zip/.crdownload/.part/.html/.htm/.xlsx/.csv/.tmp` modified
  since 2026-09-12 in those folders: one `.zip` with an unrelated name. It was not opened,
  and nothing PHMSA-shaped is present.
- The file does not exist, so there is nothing to run `file` or a magic-byte check on.
  **The "saved an HTML error page as .zip" explanation is ruled out:** no file was saved.
- Incidental, possibly relevant, UNMEASURED: a VPN client installer is in `~/Downloads`.
  Whether the author's browser attempt went through a VPN is not known. Akamai edges
  often treat VPN egress addresses differently, so this is worth asking about, not
  concluding from.

### 1b. One honest request from this machine (measured)

```
curl -sS -v --max-time 30 -o body -D headers \
  "https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/PHMSA_Pipeline_Safety_Flagged_Incidents.zip"
```

| item | result |
| --- | --- |
| DNS | `www.phmsa.dot.gov` -> CNAME `www.phmsa.dot.gov.edgekey.net` -> `e7202.dsca.akamaiedge.net`; A `23.221.152.147`; AAAA `2600:1410:6000:284::1c22`, `…:289::1c22` (curl used IPv4; this network has no IPv6 route) |
| TLS | Handshake succeeded (schannel, ALPN http/1.1). The server requested renegotiation twice **after** the request was sent; both renegotiations completed. |
| User-Agent sent | `curl/8.15.0` (default), `Accept: */*` |
| HTTP status | **`403 Forbidden`** |
| Redirects | None. The 403 was the first and only response. |
| Server | `AkamaiGHost` |
| Content-Type | `text/html` |
| Content-Length | `519` |
| Body, first 200 bytes | `<HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>\n<H1>Access Denied</H1>\n \nYou don't have permission to access "http&#58;&#47;&#47;www&#46;phmsa&#46;dot&#46;gov&#47;sites&#47;phmsa&#46;dot&#46;g` |
| Reference in body | `#18.ce354317.1789503390.8406901` (`errors.edgesuite.net`) |

This is the third independent path, after `requests` and WebFetch, and it gets the same
result: an Akamai edge denial served before the origin, with no redirect, challenge page
or retry-after.

**UNMEASURED: why it is denied.** One honest request cannot separate a User-Agent or
fingerprint rule from an IP-reputation rule. The only experiment that would separate
them is a spoofed-UA request, which 1c forbids. So why the author's *browser* fails is
still unknown, and "nothing is downloading" is not explained by this evidence.

### 1c. Constraint honoured

One request, then stopped. No browser User-Agent, no other crawler's identity, no proxy,
mirror or cache. `www.phmsa.dot.gov/robots.txt` was **not** re-fetched, to keep to one
request against that host; ADR-0016 already records that it returns 403.

### 1d. Analysis only: driving the author's real Chrome session

**The ADR's line** (`docs/DECISIONS.md`, ADR-0016, "The user's decision" paragraph) sets
"a **human** downloading a public-domain file in their own browser" apart from "any
other automated presentation of this project's client as something it is not". It calls
the first "a different act from that, not a smaller version of it".

**My reading: contrary to the ADR's line.** The ADR's test is about who performs the
act, not only which software sends the bytes. An agent driving the author's Chrome
(CDP, Playwright attached to the real profile, or similar) is an automated client. It
presents itself as a human-operated browser session, which it is not, to an edge rule
whose evident purpose is to separate automated traffic from human traffic. Borrowing a
real browser and a real session makes the automation harder for that rule to detect.
That is the reason it would work, and it is the same property the ADR refuses in UA
spoofing. The ADR's own "not a smaller version of it" phrasing argues against treating
this as a middle ground.

**Strongest counter-argument.** The ADR's worked examples all misrepresent *software*: a
spoofed UA, impersonating another crawler. A real Chrome announces exactly what it is.
Nothing about the client is falsified, the author starts and can watch the one request,
the file is public domain, and PHMSA publishes no policy saying otherwise: its
robots.txt itself returns 403, so no `Disallow` is being crossed. On that reading, an
author-initiated, supervised, single-file download through their own browser is the
manual route with the clicking delegated. Provenance can still be written plainly:
"retrieved via the author's Chrome session, agent-driven, supervised."

**Why this may be moot:** see 2b. A permitted automated route to the underlying incident
data appears to exist, so the question only matters if the specific *flagged* file is
wanted rather than the incident data itself. The author rules on this.

---

## 2. What PHMSA would actually buy

### 2a. data.transportation.gov robots.txt (measured, fetched first)

`GET https://data.transportation.gov/robots.txt` -> `200 OK`, nginx. Relevant content,
quoted:

```
User-agent: *
Crawl-delay: 1
...
Disallow: /OData.svc/
Disallow: /api/odata/
Disallow: /browse/embed
Disallow: /login
Disallow: /reset_password/
Disallow: /tiles/
Disallow: /views/INLINE/rows.json?*method=clustered2*
Disallow: /api/collocate*
```

The remaining rules disallow faceted `/browse`, `/page`, `/catalog` and `/facet` query
strings, plus `*/alt`, `*/edit` and `widget_preview`. **No rule matches `/api/views/…`,
so every path used below is allowed for `User-agent: *`.** Crawl-delay 1 was honoured:
at least 1.5 s between requests.

**Side finding, measured:** Python's `urllib.robotparser` reads this file as allow-all.
The file puts blank lines between `Crawl-delay` and the `Disallow` rules, and the
stdlib parser ends the `User-agent: *` group at a blank line. As served, it answers
`can_fetch('*', '/api/odata/x') = True` and `/login = True`. With blank lines removed,
both are `False`. `NrcTextClient`'s pre-request robots gate uses this parser
(`src/faultline/download/nrc_text.py:38`, `:361`, `:395`), so it is weaker than ADR-0016
describes for any host that formats robots.txt this way. Whether `nrc.gov`'s file does
is UNMEASURED here. This did not affect anything in this brief, because the rules were
read by hand.

### 2b. Socrata metadata (measured)

`GET /api/views/qdme-9bbm.json` -> 200 (8,310 bytes). `GET /api/views/27nc-rsge.json` ->
200 (12,108 bytes).

| field | `qdme-9bbm` | `27nc-rsge` |
| --- | --- | --- |
| name | Pipeline Incident Flagged Files | Gas Distribution, Gas Transmission & Gathering, LNG incidents and Hazardous Liquid Accident and Incident Data |
| assetType | `href` | `href` |
| **row count** | **none: 0 columns, no row data** | **none: 0 columns, no row data** |
| **columns** | **0** | **0** |
| licence (Common Core `License`) | `http://www.usa.gov/publicdomain/label/1.0/` | `http://www.usa.gov/publicdomain/label/1.0/` |
| update cadence (`Update Frequency`) | `R/P1M` (monthly) | `R/P1M` (monthly) |
| temporal applicability | `R/1992-01-01/P1M` | `R/1970-01-01/P1M` |
| created / rowsUpdatedAt | 2018-12-17 / 2018-12-17 | 2018-12-17 / 2018-12-17 |
| viewLastModified | 2026-09-03 | 2026-09-02 |
| accessPoints | `zip`: the named phmsa.dot.gov flagged zip | `HTML`: the phmsa.dot.gov landing page |
| **attachments** | none | **15 zip files, hosted on data.transportation.gov** |

Descriptions, quoted:

- `qdme-9bbm`: *"In the flagged files, PHMSA add data that are routinely used during data
  analysis and when presenting certain 20-year trends. Information includes: serious
  incidents …, significant incidents …, reported incidents …, consequences …, and
  state-based reports."*
- `27nc-rsge`: *"… requires pipeline operators to submit incident reports within 30 days
  … Specific information includes the time and location of the incident(s), number of
  any injuries and/or fatalities, commodity spilled/gas released, causes of failure and
  evacuation procedures."*

**Row counts and column names/types/descriptions are UNMEASURED.** Both records are
pointers; Socrata holds no schema for either.

**New finding: the 15 `27nc-rsge` attachments.** Each was checked with one headers-only
request (`curl -I`, no body downloaded) to
`https://data.transportation.gov/api/views/27nc-rsge/files/<assetId>?download=true&filename=…`,
which robots.txt permits:

| attachment | status | Content-Type | bytes |
| --- | --- | --- | --- |
| Gas Distribution Incident Data - January 2010 to present.zip | 200 | application/octet-stream | 1,566,027 |
| Gas Distribution Incident Data - March 2004 to December 2009.zip | 200 | application/octet-stream | 1,076,055 |
| Gas Distribution Incident Data - mid 1984 to February 2004.zip | 200 | application/octet-stream | 676,906 |
| Gas Distribution Incident Data - 1970 to mid 1984.zip | 200 | application/octet-stream | 1,079,036 |
| Hazardous Liquid Accident Data - January 2010 to present.zip | 200 | application/octet-stream | 4,597,548 |
| Hazardous Liquid Accident Data - January 2002 to December 2009.zip | 200 | application/octet-stream | 1,892,458 |
| Hazardous Liquid Accident Data 1986 to January 2002.zip | 200 | application/octet-stream | 958,446 |
| Hazardous Liquid Accident Data - Pre 1986.zip | 200 | application/octet-stream | 275,191 |
| Gas Transmission & Gathering Incident Data - January 2010 to present.zip | 200 | application/octet-stream | 2,241,740 |
| Gas Transmission & Gathering Incident Data - 2002 to December 2009.zip | 200 | application/octet-stream | 1,240,023 |
| Gas Transmission & Gathering Incident Data - mid 1984 to 2001.zip | 200 | application/octet-stream | 329,445 |
| Gas Transmission & Gathering Incident Data - 1970 to mid 1984.zip | 200 | application/octet-stream | 548,513 |
| Liquefied Natural Gas (LNG) Incident Data - January 2011 to present.zip | 200 | application/octet-stream | 459,113 |
| Hazardous Liquid Gravity & Reporting-Regulated-Only Jul 2020_present.zip | 200 | application/octet-stream | 560,015 |
| Type R Reporting-Regulated Gas Gathering May 2022 to Present.zip | 200 | application/octet-stream | 490,509 |
| **total** | | | **17,991,025** |

Responses carry `Content-disposition: attachment`, an `ETag` equal to the asset id, and
**no `Last-Modified`**. **UNMEASURED: whether these attachments are current.** The view
was modified in September 2026, but the row timestamps date from 2018, and nothing in
the headers dates the files. They are also not the flagged file: they are the per-type
incident flat files that the flagged file is derived from.

This contradicts two records:

- `configs/data/sources_text.yaml:183-188`: *"a sibling dataset (27nc-rsge …) does the
  same … No independently-hosted export exists for this data at any host checked."*
- `docs/DECISIONS.md:1707` (ADR-0016, PHMSA row): *"there is no independently-hosted
  export for this data, only a catalogue pointer back to the blocked host."*

Both describe `27nc-rsge`'s `accessPoints`, which do point back to phmsa.dot.gov. Neither
looked at its `metadata.attachments`.

### 2c. Narrative field or coded register? (judgement, flagged)

**From permitted metadata alone, this cannot be decided.** There are no columns to read,
and neither description mentions a narrative field. `27nc-rsge`'s description lists only
fields that are coded in a typical incident register: time, location,
injuries/fatalities, commodity, cause, evacuation. On metadata alone this looks like the
OE-417 question again, and the honest answer is UNMEASURED.

**Prior knowledge, not measured, stated so it can be checked.** PHMSA's 2010-onward
incident report forms (gas distribution F 7100.1, gas transmission/gathering F 7100.2,
hazardous liquid F 7000-1) include a free-text "narrative description" part, and the
2010-to-present flat files are commonly published with a narrative column. If that holds
for these attachments, PHMSA is **not** OE-417: it would be a coded register *plus* one
genuine free-text field per report. Pre-2010 files are more likely to carry little or no
narrative (UNMEASURED).

**Order-of-magnitude estimate, with the reasoning exposed:**

- Reports, 2010 to present, all types: UNMEASURED. My prior is about 10^4 (a few hundred
  hazardous-liquid accidents a year plus on the order of a hundred each for gas
  distribution and transmission, over about 16 years).
- Narrative length: UNMEASURED. My prior is tens to a few hundred words per report.
- **Estimate: about 10^6 whitespace tokens, plausible range roughly 0.5M-3M, for the
  2010-onward narratives.** A loose ceiling: the six 2010-onward zips total 9.9 MB
  compressed. At a text-like 4-6x expansion that is roughly 40-60 MB across **all**
  columns, and a narrative column is a minority of a wide coded row, so a figure above
  about 8M words is implausible.
- **Uncertainty: at least a factor of 3 either way, and zero is not excluded.** If the
  attachments carry no narrative column, the yield is near zero. The flagged file most
  likely overlaps the same incidents rather than adding to them (UNMEASURED).

For scale, the corrected NRC corpus is 6,387,362 whitespace tokens. At the central
estimate PHMSA adds roughly +15%, at most about +50%. Either way the corpus stays near a
fifth to a third of the 30M floor.

---

## 3. Reversibility: the actual crux

### Measurements from the code and records

- **The M2 brief is not a file in this repository.** Its rules survive only as
  quotations, so the exact scope of "One fit; no iteration" is UNMEASURED from its
  source. The quotations:
  - `configs/tokenizer/text_bpe_v1.yaml:3-4`: *"One fit; no iteration -- the M2 brief
    pre-registers this, so there is no candidate sweep here the way
    configs/tokenizer/quantile_bins_v*.yaml compares bin counts."*
  - `src/faultline/data/text/bpe_fit.py:4-7`: *"there is no candidate sweep here … because
    a BPE vocabulary has no analogous cheap axis to compare fits along before
    committing."*
- **Layout** (`src/faultline/tokenizers/layout.py:70`, ADR-0003 v2 at
  `docs/DECISIONS.md:239`): `TEXT_CAPACITY = 32768`, text region `[1184, 33952)`.
  `text_bpe_v1.yaml` sets `vocab_size: 32768`, which fills the region **exactly**. No
  headroom remains: text is the last block, and growing past 32,768 raises in
  `VocabLayout.__post_init__` and "supersedes ADR-0003".
- **Byte-level BPE** (`src/faultline/tokenizers/text_bpe.py:23-25`, `:58`): ids 0-255 are
  raw bytes; merges fill 256 up to `vocab_size`. There is no `<unk>` path, so **OOV
  share is 0 by construction** for any text, PHMSA included. The quantity that moves on
  foreign text is bytes per token.
- **What M2c reports** (`bpe_fit.py:116-133`, `:201-221`): bytes/token per source and
  per held-out split, never pooled, plus the share of the vocabulary seen fewer than 100
  times in the *training* frequency.
- **What M2d/M2e report** (`src/faultline/evaluation/text_ladder.py:19-23`, `:168-213`):
  per-source loss in nats/token and bits/byte, each source divided by its own UTF-8
  bytes. `<sep>` is the local id `tokenizer.vocab_size` (`shards.py:138-139`).
- **Precedents.**
  - Refit on a data change: `ace1e7f` "re-run the pipeline, re-fit the tokenizer and
    re-shard under the three gate-3 decisions" (telemetry, M1c).
  - Freeze once downstream depends on it: ADR-0015, `docs/DECISIONS.md:1633-1640`.
    `quantile_bins_v2` is "FROZEN for Phase A … The joint model needs one frozen
    telemetry vocabulary … refitting … would re-shard everything … and invalidate the
    ladder it is the baseline for."
  - `docs/ROADMAP.md:416`, M3: "Concatenate the M1 and M2 vocabularies per ADR-0003; no
    retokenization."

### Answers

**Does "One fit; no iteration" forbid a later refit?** On the quoted wording, it forbids
a *candidate sweep*: fitting several vocabularies and choosing among them by a number.
It does not speak to refitting because the corpus itself changed under a new version
file (`text_bpe_v2.yaml`), which is how `ace1e7f` handled telemetry. However, ADR-0015
shows the project's own rule once a vocabulary has consumers: it is frozen for the
phase. A refit that happens after M2e perplexities exist would be hard to distinguish
from iteration unless it was pre-registered beforehand, for example "refit if and only
if PHMSA is staged". Exact brief wording: UNMEASURED.

**Does the region `[1184, 1184+32768)` survive a refit?** The *region* does: same
offset, same capacity, same size. The *ids inside it* do not keep their meaning.
Byte ids 1184-1439 are identical under any fit; every merge id from 1440 up would
generally decode to a different string. Consequences:

- The M1 telemetry prefix (< 1184), its shards and its checkpoints are **untouched**.
- Every text shard and every model trained on text ids (the M2d/M2e S2 and S3
  checkpoints, and any M3 joint shard or checkpoint containing text) is **invalidated**.
- The M3 concatenation still works mechanically, but only against the refit vocabulary.
  An M2d checkpoint trained on v1 ids cannot initialise a v2-vocabulary joint model.

### Cost of each path, concretely

| | A. Fit now on NRC; PHMSA later tokenized with that vocabulary | B. Fit now on NRC; refit with PHMSA later | C. Wait for PHMSA, fit once |
| --- | --- | --- | --- |
| Re-run | Nothing already done. **If PHMSA is to be pretrained on:** PHMSA shards (minutes) plus S2/S3 retrained, up to about 8 GPU-h (4 h cap each, `text_ladder.py:9-17`). **If PHMSA is evaluation-only:** PHMSA shards only. | Tokenizer fit (runtime UNMEASURED; pure-Python BPE to 32,512 merges), all text shards, S2 and S3 (up to about 8 GPU-h). Also any M3 text-bearing artefact, if the refit comes after M3 starts. | Nothing. |
| Re-report | M2c compression table gains a PHMSA row (bytes/token on a vocabulary not fit to it; expected worse, magnitude UNMEASURED). Rare-token share is unchanged if PHMSA stays out of the fit's training frequency; if PHMSA joins the train split, report both. OOV stays 0. Per-source ladder gains a PHMSA row, which is **zero-shot out-of-distribution** unless S2/S3 are retrained. | Everything M2c/M2d/M2e reported: compression per source, rare share, nats and bits/byte per source, the Gate 6 report, and dataset-card stats. Bits/byte is comparable across the two fits; nats/token is not. | Nothing. |
| Becomes un-defensible | "The text tokenizer was fit on the M2 corpus", if the corpus later includes PHMSA; needs rewording to "fit on NRC only". Also H3's "narrative pretraining" arm, if the M3 narrative corpus differs from what M2d pretrained on. | A refit after results exist looks like iteration unless the trigger is written down before the fit. It also contradicts the ADR-0015 freeze pattern if done inside Phase A after M2 closes. | Nothing, beyond calendar time. |
| Buys | Progress now. | Progress now, and a PHMSA-inclusive vocabulary eventually. | One vocabulary that includes PHMSA. |

**The dominant cost is not the tokenizer.** Retraining S2 and S3 (up to about 8 GPU-h) is
forced by *adding PHMSA to the pretraining corpus*, under **either** A or B. Waiting (C)
therefore saves, at most: one tokenizer fit, one shard pass, up to about 8 GPU-h, and a
round of re-reporting. And it saves those only if PHMSA actually arrives and carries
narrative worth training on, which is UNMEASURED (2c). If PHMSA would only be
evaluation-only, A costs almost nothing and waiting buys nothing.

---

## 4. What depends on corpus breadth

### Measurements (read-only, from data already on disk)

**Composition of the corrected final corpus** (`data/final/text/nrc_operator_narratives`,
run `20260913-142340_all_text_2a6ec5b7`):

- 6,024 of 21,882 event notifications (27.5%) have "AGREEMENT STATE" in their title
  line. These are materials-licensee reports (medical, gauges, radiography), not plant
  events.
- The four generic-communications collections (Information Notices, Bulletins, Generic
  Letters, Regulatory Issue Summaries) hold 1,448,211 of 6,387,362 whitespace tokens
  (22.7%). They are regulator-authored guidance, not operator narrative.

**Per-source split sizes** (documents, whitespace tokens):

| source | train | val | test |
| --- | --- | --- | --- |
| nrc_event_notifications | 21,424 / 4,833,287 | 220 / 48,730 | 238 / 57,134 |
| nrc_info_notices | 410 / 388,811 | 8 / 7,561 | 4 / 3,509 |
| nrc_gen_letters | 549 / 679,812 | **3 / 1,557** | 4 / 5,134 |
| nrc_bulletins | 223 / 265,471 | 3 / 3,495 | **2 / 1,324** |
| nrc_reg_issues | 53 / 91,537 | **0** | **0** |

`shards.py:168-176` gives a stream shorter than the 2,048-token context **zero windows**,
with a logged warning. `nrc_reg_issues` has no held-out documents at all. Bulletins-test
and gen-letters-val are 1,324 and 1,557 *words*; whether they reach 2,048 BPE tokens is
UNMEASURED until the fit.

**Status code book against the NRC train split** (`data/raw/text/status_code_book.jsonl`:
264 strings, 297 word types, 883 word tokens):

- Word types seen at least 100 times in NRC train: **191 of 297 (64.3%), covering 70.2%
  of code-book word tokens.** Seen at least once: 266 (89.6%).
- Absent entirely (31): `adaption, anemometer, asymmetry, autounwind, bladeangle, conv,
  dev, drivetrain, earthed, electr, err, freq, implausible, login, mains, mconfig,
  nacelle, nat, obstacle, overfrequency, parameterized, parkmaster, pmu, rotorbearing,
  sntp, synchronisation, thermistor, transf, twistangle, winddirection, yaw`.
- Seen 1-99 times, among others: `pitch, rotor, gearbox, converter, icing, gust, stator,
  vane, rpm, brake, lubrication, curtailment`.
- Status strings whose every word is seen at least 100 times: **76 of 264**.

### Judgement

**H3 and the domain gap.** H3 (`docs/DECISIONS.md:554-556`, `docs/ROADMAP.md:365-367`)
is tested by comparing event types whose status strings "share vocabulary with the
narrative corpus" against those that do not (`docs/DECISIONS.md:558-560`). The NRC corpus
already supplies most of the *generic* electrical and mechanical vocabulary: generator,
turbine, breaker, transformer, pump, fan, battery, overload. What it lacks is
*wind-specific* vocabulary: yaw, nacelle, pitch, rotor, blade angle, anemometer,
drivetrain.

Pipeline incident narratives would plausibly add compressor, valve, pressure, SCADA,
control room and corrosion. They would plausibly **not** add yaw, nacelle, pitch, rotor
or anemometer. **My reading: PHMSA is a third unrelated domain.** It would move the H3
vocabulary split little, because the gap H3 depends on is wind-specific and neither
agency writes about wind turbines. The size of that effect is UNMEASURED without PHMSA
text; the list of absent words above is what it would be measured against.

A side effect worth noting: the event-type split H3 uses is defined against "the
narrative corpus". If that corpus changes between M2 and M3, the split changes with it.

**M2b per-source held-out reporting with five collections from one agency.**

- **It can show** a register difference: licensee-submitted event reports against
  regulator-authored guidance. And for event notifications only (about 49k val and 57k
  test words), a stable held-out number.
- **It cannot show** cross-agency or cross-domain generalisation, because every source
  is one agency writing about one regulated industry. For four of the five sources it
  cannot give a stable number at all: held-out sets of 0 to 8 documents, some possibly
  shorter than one context window.
- **PHMSA would add** the first held-out row from a different agency and domain, which
  is the one thing per-source reporting could newly demonstrate.
- **Independent of PHMSA:** the tiny held-out splits are a pre-M2c problem (split
  fractions of 1%/1% on sources of 53-563 documents) that needs a ruling either way.

**ADR-0001.** Its framing survives an NRC-only corpus as written. It asks for "a separate
public-domain operator-narrative corpus (M2)" (`docs/DECISIONS.md:42-44`), not a
multi-agency one. Its change trigger, "no adequately licensed narrative corpus is
reachable" (`:53-56`), has not fired. Two points of precision, not reversals: about 23%
of tokens are not *operator* narrative, and the domain is nuclear and radioactive
materials.

### Exact places whose wording no longer matches the measured corpus

| file:line | current wording | issue |
| --- | --- | --- |
| `README.md:5-6` | "an English operator-narrative corpus (public-domain incident and event reports about power and process plants)" | Single agency, nuclear. 27.5% of event notifications are materials-licensee reports, not plants. Nothing supports "process plants". |
| `README.md:78-81` | "Public-domain operator-narrative sources — incident and event reports from public safety and regulatory bodies. They are specified with `enabled: false` … nothing is downloaded" | Stale: one regulatory body, and the sources are enabled and staged. |
| `README.md:14` | "M0 — skeleton, pipelines and data staging. No model has been trained." | Stale status line (not a breadth issue; noted in passing). |
| `docs/DECISIONS.md:42-44` (ADR-0001) | "a separate public-domain operator-narrative corpus" | Survives; could gain a dated note that the corpus is single-agency, and that about 23% is regulator-authored rather than operator narrative. |
| `docs/DECISIONS.md:554-560`, `docs/ROADMAP.md:365-374` (H3) | "Pretraining on the operator-narrative corpus improves cross-OEM transfer …" | Wording survives. The test now runs against a nuclear corpus that is missing the wind-specific status vocabulary measured above; worth recording before M3 so a flat result is not blamed on the text pathway alone. |
| `docs/DECISIONS.md:1707` (ADR-0016, PHMSA row) and `configs/data/sources_text.yaml:183-188` | "no independently-hosted export for this data" | Contradicted by the 15 `27nc-rsge` attachments (2b). |
| `docs/ROADMAP.md:344-346`, `:357` | "add MinHash near-duplicate removal (`dedup.strategy: minhash`)" | Superseded by the keyed dedup of 2026-09-13 (not a breadth issue; noted in passing). |

---

## 5. State

| item | value |
| --- | --- |
| HEAD | `d1c08b30f36ce4aa770e9ec5cbead6beefbfd85c` ("docs(m2): run the real pipeline with the Gate-6 corrections, re-measure (a)/(d)") |
| commits ahead of `origin/main` | 50 |
| working tree | clean before this brief; this report file is the only new, uncommitted file |
| `data/raw/text/phmsa/` | does not exist |

**What `faultline inspect phmsa` expects** (`src/faultline/cli.py:205-258`,
`src/faultline/data/text/phmsa_manual.py`):

- **Path and filename:** `--file` defaults to
  `data/raw/text/phmsa/PHMSA_Pipeline_Safety_Flagged_Incidents.zip`. `--url` defaults to
  the named phmsa.dot.gov URL. `--retrieved-at` takes an ISO time and defaults to *now*.
- **Archive members:** no specific names are expected. Every non-directory member is
  read if its suffix is `.csv`, `.txt`, `.xlsx` or `.xls` (`phmsa_manual.py:79`). CSV and
  TXT go through `pd.read_csv` with the default comma separator and `on_bad_lines="skip"`;
  Excel goes through `pd.read_excel` (openpyxl 3.1.5 is installed).
- **Narrative detection:** a column counts as narrative if its name contains
  narrative/description/summary/comment/remark/additional_info/detail, **or** it is a
  string column averaging more than 80 characters (`:64-76`, `:194-204`).
- **Classification:** pipeline type and form generation are guessed from filenames only
  (`:84-123`).
- **Output:** writes `reports/data/phmsa_manual_<YYYYMMDD>.md` and upserts a manifest
  record with `retrieval_method="manual, author, browser"` and `verified=True`
  (`:246-289`).

**If the file is absent:** prints `… does not exist yet; nothing to inspect` and exits
with code 1 (`cli.py:247-249`). No manifest is written.

**If the file is malformed** (for example an HTML page saved as `.zip`), there is a
defect. `record_manual_retrieval` runs **before** `inspect_archive` (`cli.py:252-253`),
so the file is hashed and written into the tracked manifest as `verified=True` first.
Only then does `zipfile.ZipFile` raise `BadZipFile`, which nothing catches (no handler in
`phmsa_manual.py`). Result: a traceback, no report, and a manifest entry recording an
error page as verified data.

Further gaps:

- A nested `.zip` inside the archive is silently skipped as non-tabular.
- A tab-delimited `.txt` would parse through the comma reader as one wide column.
  UNMEASURED whether PHMSA's files are tab-delimited; a prior, not a measurement.
- An undecodable member is logged at info and dropped.
- The command expects the *flagged* file by name, so it would need `--file` and `--url`
  for a `27nc-rsge` attachment.

---

## My read

**Recommendation: do not wait on the flagged zip. Also do not rule on "proceed without
PHMSA" yet. Resolve the one unmeasured fact first, because it is now cheap.** The author
would need to approve using the `27nc-rsge` attachments as a route. That is new, since
ADR-0016 records no such route. If approved:

1. Fetch **one** attachment through the project's own robots-gated client (for example
   "Hazardous Liquid Accident Data - January 2010 to present.zip", 4.6 MB). Profile it
   with `inspect phmsa --file … --url …`, after fixing the manifest-before-validation
   defect.
2. That single measurement settles whether PHMSA has a narrative column, and roughly
   what it yields.
3. Then rule:
   - **No narrative, or well under 1M tokens:** exclude it for thinness on the OE-417
     precedent and fit NRC-only now.
   - **Narrative in volume:** stage it through the same pipeline and fit once, including
     it.

Either way, fix the degenerate per-source held-out splits (§4) before M2c; that issue
exists with or without PHMSA.

If the author does not want the new route used, choose **path A** (fit on NRC now and
freeze): the reversibility analysis shows waiting saves at most one fit plus about
8 GPU-h, and only if a blocked file eventually arrives. Also correct `README.md:5-6`,
`:78-81` and ADR-0016's "no independently-hosted export" line.

**Strongest argument against:** using the `27nc-rsge` attachments reopens a source
decision that the author already made on stated evidence. It swaps the named file for
different files whose currency is unmeasured (no `Last-Modified`; row timestamps from
2018). It spends effort on a source that, on the H3 analysis, probably does not close
the gap that matters, since wind-specific vocabulary is absent either way. Seen that
way, the disciplined move is to fit NRC-only now, record PHMSA as future work, and treat
the attachment finding as a correction to ADR-0016 rather than a reason to delay M2c by
even one more measurement.
