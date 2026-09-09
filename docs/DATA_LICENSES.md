# Data licences

Code in this repository is MIT (`LICENSE`). That covers the source only. Every
dataset keeps its own licence, and **no raw or derived data is redistributed from
this repository** — only dataset cards, checksum manifests and aggregate statistics.

Policy: ADR-0004. Only public-domain, CC0, CC BY, CC BY-SA, MIT or Apache-2.0
sources are admitted; licences are recorded per file in the manifests; sources with
unspecified terms are excluded until verified in writing.

## Admitted sources

| source | provider | licence | version-pinned record | attribution string |
| --- | --- | --- | --- | --- |
| Kelmarsh | Cubico Sustainable Investments Ltd | CC BY 4.0 | [16807551](https://zenodo.org/records/16807551) (concept DOI [10.5281/zenodo.5841833](https://doi.org/10.5281/zenodo.5841833)) | Cubico Sustainable Investments Ltd, Kelmarsh wind farm data, Zenodo, doi:10.5281/zenodo.5841833 (CC BY 4.0) |
| Penmanshiel | Cubico Sustainable Investments Ltd | CC BY 4.0 | [16807304](https://zenodo.org/records/16807304) (concept DOI [10.5281/zenodo.5946807](https://doi.org/10.5281/zenodo.5946807)) | Cubico Sustainable Investments Ltd, Penmanshiel wind farm data, Zenodo, doi:10.5281/zenodo.5946807 (CC BY 4.0) |
| Hill of Towie | RES on behalf of The Renewables Infrastructure Group | CC BY 4.0 | [14870023](https://zenodo.org/records/14870023) (DOI [10.5281/zenodo.14870023](https://doi.org/10.5281/zenodo.14870023)) | RES on behalf of The Renewables Infrastructure Group, Hill of Towie wind farm data, Zenodo, doi:10.5281/zenodo.14870023 (CC BY 4.0) |
| CARE to Compare | Fraunhofer IEE | **CC BY-SA 4.0** | [15846963](https://zenodo.org/records/15846963) (concept DOI [10.5281/zenodo.10958774](https://doi.org/10.5281/zenodo.10958774)) | Gück, Bruns, Dupont, CARE to Compare, Fraunhofer IEE, Zenodo, doi:10.5281/zenodo.10958774 (CC BY-SA 4.0) |

CARE has an accompanying publication that should be cited alongside the data:
Gück, Bruns, Dupont (2024), *CARE to Compare*, Data 9(12):138,
[doi:10.3390/data9120138](https://doi.org/10.3390/data9120138).

Records are pinned to a **version** id, not a concept DOI, so that a later upload by
the provider cannot silently change what a run consumed. The CARE pin is v6
(2025-07-09), which carries label corrections relative to v1 — training against v1
labels and reporting them as CARE results would be reporting known-superseded labels.

## Attribution in practice

Any published output — paper, poster, README, slide — that reports results computed
from these records must carry the attribution strings above. CC BY requires
attribution and a statement of changes; the changes made here are exactly the
pipeline stages recorded in `reports/data/<run_id>/`, so citing the run id alongside
the attribution satisfies that.

## Share-alike propagation (CARE)

CC BY-SA 4.0 obliges any **adapted material** that is distributed to carry CC BY-SA
4.0 as well. Concretely, for this project:

| artefact | is it adapted material? | consequence |
| --- | --- | --- |
| Raw archives | Not redistributed | Nothing to propagate; the repository never contains them |
| Cleaned, filtered or tokenised CARE tables | Would be adapted material | **Not redistributed.** They stay in the git-ignored data stages on the author's machine |
| Dataset cards, checksum manifests | Factual metadata about the record | Redistributed; no share-alike obligation attaches to a checksum and a file list |
| Aggregate statistics in stats reports (counts, coverage, percentiles) | Aggregate facts, not a substantial reproduction | Redistributed |
| Source code | Independent work, not a derivative of the data | MIT |
| **Trained model weights** | **Unresolved** | See below |

**The open question, stated rather than assumed away.** Whether model weights
trained on CC BY-SA data are "adapted material" is genuinely unsettled and the answer
differs by jurisdiction. This project does not need to resolve it in the abstract —
it needs to not be trapped by it. The plan: keep CARE out of the *training* corpus
entirely and use it only for evaluation and label cross-check, which is exactly the
role assigned on its dataset card. If CARE is ever admitted to training, that
decision gets its own ADR and the weights are released under CC BY-SA 4.0 or not
released at all.

**Enforced in code since 2026-09-09.** `configs/data/splits_v0.yaml` carries
`eval_only_sources: [care]`, and `assign_splits` labels every row of such a source
`test`, applied after both the site and the time axis so that neither can override
it. A frame that lacks the source column raises rather than silently skipping the
constraint — the failure mode worth guarding against is not a wrong label, it is a
licence rule that quietly did not run. The CARE adapter still does not load, so
nothing reaches the splitter yet; the restriction is in place ahead of the data
rather than after it.

## Excluded sources, and why

| source | status | reason |
| --- | --- | --- |
| EDP Open Data (Wind Farm 1/2) | **Excluded** | Terms of use are not clearly specified as an open licence. ADR-0004 excludes unspecified terms; the dataset is widely used in the literature, which is not a substitute for a licence. Revisit only if the publisher states terms in writing. |
| Any scraped web corpus | **Excluded** | No verifiable licence, and scraping against a site's terms is out of scope regardless of what it would add. |
| Operational data from any partner, employer or funded project | **Excluded permanently** | `docs/PROVENANCE.md`. Not a licensing question — an independence one. |

## If you reuse this repository

You get the code under MIT. You do **not** get the data: run
`faultline download telemetry` to fetch it yourself from the pinned records, under
the licences above, and carry the attribution. The manifests let you verify you
received the same bytes the reported results were computed from.
