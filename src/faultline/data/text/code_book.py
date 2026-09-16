"""The status-message code book as a derived text source: its card and its readiness.

The code book (ADR-0007) is the 264 distinct Kelmarsh/Penmanshiel status strings, pooled
from telemetry already staged for M1 (`faultline.download.nrc_text.build_status_code_book`).
It is not narrative, is never training data, and has no record of its own: its licence
and DOIs are the two telemetry records'. This module measures what M3 needs to know about
it and renders its dataset card from those measurements.

Three measurements, each stated in its own unit:

- **Tokens per string**, with the fitted BPE tokenizer, as a distribution (nearest-rank
  quantiles and a histogram): a joint context budget breaks on the tail, not the mean.
  Pooled and per site, since ADR-0007's cross-OEM argument needs the site vocabularies to
  be seen side by side.
- **Token-level coverage**: the share of strings whose every BPE token id was seen at
  least :data:`RARE_THRESHOLD` times in the tokenizer's training shards.
- **Word-level coverage**: the share of strings whose every word (lowercase ``[a-z]+``,
  the rule the H3 vocabulary measurement used) was seen at least as often in the training
  split's text. Word-level and token-level shares answer different questions and are
  always labelled.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from faultline.data.common.report import kv_table, section, table
from faultline.data.text.bpe_fit import compression_by_source, read_split
from faultline.download.nrc_text import CodeBookSpec
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.tokenizers.text_bpe import TextBPETokenizer

logger = get_logger(__name__)

#: The source id the code book is staged under.
CODE_BOOK_SOURCE = "status_code_book"

#: Seen at least this many times in training counts as frequent. The M2c tokenizer report
#: and the H3 vocabulary measurement use the same threshold.
RARE_THRESHOLD = 100

#: The word rule of the H3 vocabulary measurement: lowercase, maximal runs of ``a-z``.
#: Recovered by reproducing its recorded 297 word types and 883 word tokens exactly.
WORD_PATTERN = re.compile(r"[a-z]+")

#: The quantiles reported, as ``(label, q)``. Nearest rank, so every value is observed.
QUANTILES: tuple[tuple[str, float], ...] = (
    ("p25", 0.25),
    ("median", 0.50),
    ("p75", 0.75),
    ("p95", 0.95),
)

#: Turbine model per code-book site, from the telemetry cards (`data/cards/<site>.md`).
SITE_MODELS: dict[str, str] = {"kelmarsh": "Senvion MM92", "penmanshiel": "Senvion MM82"}


def words(text: str) -> list[str]:
    """Split text into words under the H3 vocabulary rule.

    Args:
        text: Any text.

    Returns:
        Lowercase runs of ``a-z``, in order; digits and punctuation separate words.
    """
    return WORD_PATTERN.findall(text.lower())


def nearest_rank(values: Sequence[int], q: float) -> int:
    """The nearest-rank quantile: the smallest value with at least ``q`` of values at or below.

    Args:
        values: Observations, in any order; not empty.
        q: Quantile in ``(0, 1]``.

    Returns:
        An observed value.

    Raises:
        ValueError: On an empty sequence or a quantile outside ``(0, 1]``.
    """
    if not values:
        raise ValueError("nearest_rank of no values")
    if not 0.0 < q <= 1.0:
        raise ValueError(f"quantile {q} outside (0, 1]")
    ordered = sorted(values)
    return ordered[max(1, math.ceil(q * len(ordered))) - 1]


@dataclass(frozen=True)
class LengthSummary:
    """Tokens per string over one group of strings.

    Attributes:
        strings: Strings in the group.
        tokens: Tokens over the group.
        chars: Characters over the group.
        utf8_bytes: UTF-8 bytes over the group.
        minimum: Fewest tokens in one string.
        quantiles: Nearest-rank quantiles, by label.
        maximum: Most tokens in one string.
        histogram: Strings per token count, ascending.
    """

    strings: int
    tokens: int
    chars: int
    utf8_bytes: int
    minimum: int
    quantiles: dict[str, int]
    maximum: int
    histogram: list[tuple[int, int]]

    @property
    def mean(self) -> float:
        """Mean tokens per string."""
        return self.tokens / self.strings

    @property
    def chars_per_token(self) -> float:
        """Characters per token over the group."""
        return self.chars / self.tokens

    @property
    def bytes_per_token(self) -> float:
        """UTF-8 bytes per token, the unit the narrative sources report."""
        return self.utf8_bytes / self.tokens


def summarise_lengths(strings: Sequence[str], encoded: dict[str, list[int]]) -> LengthSummary:
    """Summarise the token counts of a group of strings.

    Args:
        strings: The group; not empty.
        encoded: Token ids per string, covering the group.

    Returns:
        The group's length summary.
    """
    lengths = [len(encoded[s]) for s in strings]
    return LengthSummary(
        strings=len(strings),
        tokens=sum(lengths),
        chars=sum(len(s) for s in strings),
        utf8_bytes=sum(len(s.encode("utf-8")) for s in strings),
        minimum=min(lengths),
        quantiles={label: nearest_rank(lengths, q) for label, q in QUANTILES},
        maximum=max(lengths),
        histogram=sorted(Counter(lengths).items()),
    )


def site_membership(
    code_book: Iterable[str], stream_messages: Mapping[str, Iterable[str]]
) -> dict[str, list[str]]:
    """Assign each code-book string to the sites whose status stream carries it.

    The label stage stores messages lowercased, so matching is on the lowercased string;
    a code-book string that collides with another under lowercasing, or a stream message
    that is not in the code book, is an error rather than a silent miss.

    Args:
        code_book: The code-book strings as staged.
        stream_messages: Per site, the distinct messages of its status stream.

    Returns:
        Per site, the code-book strings it carries, sorted.

    Raises:
        ValueError: On a lowercasing collision or a stream message outside the code book.
    """
    by_lower: dict[str, str] = {}
    for string in code_book:
        key = string.lower()
        if key in by_lower:
            raise ValueError(f"code-book strings collide when lowercased: {string!r}")
        by_lower[key] = string
    out: dict[str, list[str]] = {}
    for site, messages in stream_messages.items():
        distinct = set(messages)
        unknown = sorted(m for m in distinct if m not in by_lower)
        if unknown:
            raise ValueError(f"{site}: {len(unknown)} stream messages not in the code book")
        out[site] = sorted(by_lower[m] for m in distinct)
    return out


def train_token_frequency(shard_dir: Path, vocab_size: int) -> np.ndarray:
    """Count each text id over a text shard directory's training shards.

    Args:
        shard_dir: A `faultline text shards` output directory.
        vocab_size: The text vocabulary; ids at or above it (``<sep>``) are dropped.

    Returns:
        Frequencies indexed by local text id, length ``vocab_size``.

    Raises:
        FileNotFoundError: If the directory holds no training shard.
    """
    manifest = json.loads((shard_dir / "manifest.json").read_text(encoding="utf-8"))
    dtype = np.dtype(manifest["dtype"])
    shards = sorted(shard_dir.glob("*__train.bin"))
    if not shards:
        raise FileNotFoundError(f"no training shards under {shard_dir}")
    counts = np.zeros(max(vocab_size, int(manifest["vocabulary_size"])), dtype=np.int64)
    for shard in shards:
        ids = np.fromfile(shard, dtype=dtype)
        counts += np.bincount(ids, minlength=counts.size)[: counts.size]
    return counts[:vocab_size]


def train_word_frequency(
    paths: ProjectPaths, corpus_name: str, keep: Callable[[str], bool] | None = None
) -> tuple[Counter[str], Counter[str]]:
    """Count words over a finished corpus's training split.

    Args:
        paths: Resolved project paths.
        corpus_name: The finished corpus.
        keep: Keep a document when this returns true for its source; every document when
            omitted.

    Returns:
        Word frequencies, and documents counted per source.
    """
    frequency: Counter[str] = Counter()
    documents: Counter[str] = Counter()
    for document in read_split(paths, corpus_name, "train"):
        if keep is not None and not keep(document.source):
            continue
        documents[document.source] += 1
        frequency.update(words(document.text))
    return frequency, documents


def every_token_frequent(ids: Iterable[int], frequency: np.ndarray, threshold: int) -> bool:
    """Whether every token id was seen at least ``threshold`` times.

    Args:
        ids: A string's token ids.
        frequency: Training frequency per id.
        threshold: The frequency floor, inclusive.

    Returns:
        True if no id falls below the floor.
    """
    return all(int(frequency[i]) >= threshold for i in ids)


def every_word_frequent(text: str, frequency: Counter[str], threshold: int) -> bool:
    """Whether every word of a string was seen at least ``threshold`` times.

    Args:
        text: The string.
        frequency: Training word frequencies.
        threshold: The frequency floor, inclusive.

    Returns:
        True if no word falls below the floor.
    """
    return all(frequency[w] >= threshold for w in words(text))


@dataclass
class CodeBookMeasurement:
    """Everything the code-book card reports.

    Attributes:
        strings: The code book, as staged.
        by_site: Per site, the strings its status stream carries.
        lengths: Length summary per group (``pooled``, each site, and the site-only and
            shared groups).
        token_frequent: Per group, strings whose every token is frequent.
        word_frequent: Per group, strings whose every word is frequent.
        word_types: Per site, its distinct words.
        tokenizer_file: The tokenizer measured with.
        shard_dir: The training shards token frequency came from.
        corpus_name: The corpus word frequency came from.
        train_tokens: Text tokens counted in the training shards.
        rare_ids: Vocabulary ids seen fewer than the threshold in those shards.
        vocab_size: The text vocabulary size.
        first_token_only: Strings whose only infrequent tokens are their first.
        leading_space_frequent: Strings whose every token is frequent when encoded after a
            space, as a word mid-sentence is.
        longest: The strings at the maximum token count, with their encodings.
    """

    strings: list[str]
    by_site: dict[str, list[str]]
    lengths: dict[str, LengthSummary]
    token_frequent: dict[str, int]
    word_frequent: dict[str, int]
    word_types: dict[str, set[str]]
    tokenizer_file: str
    shard_dir: str
    corpus_name: str
    train_tokens: int
    rare_ids: int
    vocab_size: int
    first_token_only: int = 0
    leading_space_frequent: int = 0
    longest: list[tuple[str, list[str]]] = field(default_factory=list)


def groups(by_site: dict[str, list[str]], strings: Sequence[str]) -> dict[str, list[str]]:
    """The string groups reported: pooled, each site, each site only, and shared.

    Args:
        by_site: Per site, its strings.
        strings: The pooled code book.

    Returns:
        Group name to strings, in report order; empty groups are left out.
    """
    out: dict[str, list[str]] = {"pooled": sorted(strings)}
    sets = {site: set(members) for site, members in by_site.items()}
    for site, members in sets.items():
        out[site] = sorted(members)
    for site, members in sets.items():
        others = set().union(*(m for s, m in sets.items() if s != site))
        out[f"{site} only"] = sorted(members - others)
    if sets:
        out["shared"] = sorted(set.intersection(*sets.values()))
    return {name: members for name, members in out.items() if members}


def measure_code_book(
    paths: ProjectPaths,
    spec: CodeBookSpec,
    tokenizer_file: Path,
    shard_dir: Path,
    corpus_name: str,
) -> CodeBookMeasurement:
    """Measure the staged code book against the fitted tokenizer and its training data.

    Args:
        paths: Resolved project paths.
        spec: The code book's source specification (names the sites).
        tokenizer_file: The fitted text tokenizer.
        shard_dir: That tokenizer's text shards, for token frequency.
        corpus_name: The finished corpus the tokenizer was fitted on, for word frequency.

    Returns:
        The measurement.

    Raises:
        FileNotFoundError: If the code book or a site's status stream is not staged.
    """
    book_path = paths.stage_dir("raw", "text") / f"{CODE_BOOK_SOURCE}.jsonl"
    if not book_path.is_file():
        raise FileNotFoundError(f"{book_path}: stage the code book with `faultline download text`")
    strings = [
        str(json.loads(line)["text"])
        for line in book_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    streams: dict[str, list[str]] = {}
    for site in spec.telemetry_sources:
        stream = paths.source_dir("cleaned", "telemetry", site) / "labels" / "status_stream.parquet"
        if not stream.is_file():
            raise FileNotFoundError(f"{stream}: run `faultline telemetry run --stage label`")
        messages = pd.read_parquet(stream, columns=["message"])["message"].dropna()
        streams[site] = [str(m) for m in messages.unique()]
    by_site = site_membership(strings, streams)

    tokenizer = TextBPETokenizer.load(tokenizer_file)
    encoded = {s: tokenizer.encode(s) for s in strings}
    token_freq = train_token_frequency(shard_dir, tokenizer.vocab_size)
    word_freq, _documents = train_word_frequency(paths, corpus_name)

    grouped = groups(by_site, strings)
    maximum = max(len(ids) for ids in encoded.values())
    blocked_first_only = 0
    for ids in encoded.values():
        rare = [position for position, i in enumerate(ids) if token_freq[i] < RARE_THRESHOLD]
        blocked_first_only += rare == [0]
    return CodeBookMeasurement(
        strings=strings,
        by_site=by_site,
        lengths={name: summarise_lengths(members, encoded) for name, members in grouped.items()},
        token_frequent={
            name: sum(every_token_frequent(encoded[s], token_freq, RARE_THRESHOLD) for s in members)
            for name, members in grouped.items()
        },
        word_frequent={
            name: sum(every_word_frequent(s, word_freq, RARE_THRESHOLD) for s in members)
            for name, members in grouped.items()
        },
        word_types={
            site: {w for s in members for w in words(s)} for site, members in by_site.items()
        },
        tokenizer_file=tokenizer_file.relative_to(paths.repo_root).as_posix()
        if tokenizer_file.is_relative_to(paths.repo_root)
        else tokenizer_file.as_posix(),
        shard_dir=shard_dir.name,
        corpus_name=corpus_name,
        train_tokens=int(token_freq.sum()),
        rare_ids=int((token_freq < RARE_THRESHOLD).sum()),
        vocab_size=tokenizer.vocab_size,
        first_token_only=blocked_first_only,
        leading_space_frequent=sum(
            every_token_frequent(tokenizer.encode(" " + s), token_freq, RARE_THRESHOLD)
            for s in strings
        ),
        longest=[
            (s, [tokenizer.decode([i]) for i in ids])
            for s, ids in encoded.items()
            if len(ids) == maximum
        ],
    )


def _share(part: int, whole: int) -> str:
    return f"{part:,} / {whole:,} ({part / whole:.1%})"


def render_code_book_card(
    measurement: CodeBookMeasurement,
    spec: CodeBookSpec,
    paths: ProjectPaths,
    narrative_bytes_per_token: dict[str, float],
) -> str:
    """Render the code book's dataset card from its measurement.

    Args:
        measurement: The code-book measurement.
        spec: The code book's source specification.
        paths: Resolved project paths.
        narrative_bytes_per_token: Held-out bytes/token per narrative source, for
            comparison.

    Returns:
        The card, as Markdown.
    """
    m = measurement
    pooled = m.lengths["pooled"]
    sites = list(m.by_site)
    parts = [f"# {CODE_BOOK_SOURCE}\n\n"]
    parts.append(
        section(
            "Identity",
            kv_table(
                {
                    "source id": CODE_BOOK_SOURCE,
                    "provider": spec.provider,
                    "licence": spec.license,
                    "attribution": spec.attribution,
                    "records and DOIs": "inherited, not its own: Kelmarsh (concept DOI "
                    "10.5281/zenodo.5841833, version 10.5281/zenodo.16807551) and Penmanshiel "
                    "(concept DOI 10.5281/zenodo.5946807, version 10.5281/zenodo.16807304), "
                    "both CC BY 4.0, via Zenodo; see `data/cards/kelmarsh.md` and "
                    "`data/cards/penmanshiel.md`",
                    "provenance": "**derived, not downloaded**: the distinct status-message "
                    "strings of the status tables already staged and md5-verified for M1, "
                    "pooled by `build_status_code_book` (`faultline download text`); no "
                    "network request is made for this source",
                    "access route": "not fetched over the network",
                }
            )
            + "\n_Identity fields are copied from `configs/data/sources_text.yaml` and the two "
            "telemetry cards._\n",
        )
    )
    site_rows = [
        (
            site,
            SITE_MODELS.get(site, "UNVERIFIED"),
            len(m.by_site[site]),
            m.lengths[f"{site} only"].strings if f"{site} only" in m.lengths else 0,
            len(m.word_types[site]),
        )
        for site in sites
    ]
    shared_types = set.intersection(*m.word_types.values()) if m.word_types else set()
    union_types = set().union(*m.word_types.values()) if m.word_types else set()
    parts.append(
        section(
            "Contents",
            kv_table(
                {
                    "strings (measured)": pooled.strings,
                    "strings shared by both sites": m.lengths["shared"].strings
                    if "shared" in m.lengths
                    else 0,
                    "characters": pooled.chars,
                    "language": "English (provider status labels)",
                    "note on the count": "264 is the measured count; the brief's ~230 was an "
                    "estimate",
                }
            )
            + "\n"
            + table(
                ["site", "turbine model", "strings", "strings at this site only", "word types"],
                site_rows,
            )
            + f"\nWord types (lowercase `[a-z]+`): {len(union_types)} in all, "
            f"{len(shared_types)} at both sites. **Both sites are Senvion**: the site split is "
            "between two turbine models of one manufacturer, not between manufacturers, so it "
            "shows how far one OEM's vocabulary moves between models; it is not evidence about "
            "the cross-OEM case ADR-0007 argues from, and the held-out Siemens site publishes "
            "alarm codes, not strings (ADR-0001 evidence).\n\n"
            "**Free-text verdict: VERIFIED no** - a code book, as the Kelmarsh and Penmanshiel "
            "cards already record from the raw inventory.\n",
        )
    )
    parts.append(
        section(
            "Staging",
            kv_table(
                {
                    "raw file": f"data/raw/text/{CODE_BOOK_SOURCE}.jsonl (one string a line)",
                    "manifest": f"data/cards/manifests/{CODE_BOOK_SOURCE}.json",
                    "site membership": "each site's `labels/status_stream.parquet`, matched "
                    "lowercased; every stream message is in the code book",
                }
            ),
        )
    )

    length_rows = [
        (
            name,
            s.strings,
            s.minimum,
            s.quantiles["p25"],
            s.quantiles["median"],
            s.quantiles["p75"],
            s.quantiles["p95"],
            s.maximum,
            f"{s.mean:.2f}",
            f"{s.chars_per_token:.2f}",
            f"{s.bytes_per_token:.2f}",
        )
        for name, s in m.lengths.items()
    ]
    top = max(pooled.maximum, *(s.maximum for s in m.lengths.values()))
    histogram_rows = [
        (n, *(dict(m.lengths[g].histogram).get(n, 0) for g in ["pooled", *sites]))
        for n in range(pooled.minimum, top + 1)
    ]
    coverage_rows = [
        (
            name,
            _share(m.token_frequent[name], s.strings),
            _share(m.word_frequent[name], s.strings),
        )
        for name, s in m.lengths.items()
    ]
    longest = "; ".join(
        f"`{text}` -> " + " | ".join(f"`{piece}`" for piece in pieces) for text, pieces in m.longest
    )
    parts.append(
        section(
            "Readiness for the joint vocabulary (ADR-0007, M3)",
            kv_table(
                {
                    "tokenizer": m.tokenizer_file,
                    "token frequency from": f"training shards `data/shards/text/{m.shard_dir}` "
                    f"({m.train_tokens:,} text tokens, `<sep>` excluded)",
                    "word frequency from": f"the `{m.corpus_name}` training split",
                    "frequent means": f"seen at least {RARE_THRESHOLD} times in training",
                    "quantiles": "nearest rank, so every value is an observed token count",
                    "vocabulary ids seen fewer than 100 times": _share(m.rare_ids, m.vocab_size),
                }
            )
            + "\n### Tokens per string\n\n"
            + table(
                [
                    "group",
                    "strings",
                    "min",
                    "p25",
                    "median",
                    "p75",
                    "p95",
                    "max",
                    "mean",
                    "chars/token",
                    "bytes/token",
                ],
                length_rows,
            )
            + "\nFor comparison, held-out bytes/token per narrative source (val and test "
            "together, same tokenizer): "
            + ", ".join(f"{k} {v:.2f}" for k, v in sorted(narrative_bytes_per_token.items()))
            + ". A lower figure means a string breaks into shorter pieces than the prose the "
            "tokenizer was fitted on.\n\n"
            f"Longest: {longest}.\n\n"
            "### Distribution (strings per token count)\n\n"
            + table(["tokens", "pooled", *sites], histogram_rows)
            + "\n### Coverage by the training data\n\n"
            + table(
                [
                    "group",
                    f"TOKEN-level: every BPE token seen >= {RARE_THRESHOLD}",
                    f"WORD-level: every word seen >= {RARE_THRESHOLD}",
                ],
                coverage_rows,
            )
            + "\n**Token-level coverage is the lower of the two.** The word rule lowercases "
            "and ignores position; the tokenizer does neither. A status string starts without "
            "a leading space and with a capital, so its first word encodes as a string-initial "
            "piece that prose rarely produces (`Wind` is `W` + `ind`, where prose writes "
            f"` wind`). {_share(m.first_token_only, pooled.strings)} strings are held below the "
            "floor by their first token alone; encoded after a single space, "
            f"{_share(m.leading_space_frequent, pooled.strings)} have every token frequent. "
            "Reported, not changed: how a status string is framed in the joint stream is an M3 "
            "decision. H3's vocabulary split is word-level "
            "(`reports/data/h3_vocab_overlap_v1_20260916.md`).\n",
        )
    )
    parts.append(
        section(
            "Use in FaultLine",
            kv_table(
                {
                    "intended role": "ADR-0007 readiness and the M3 joint vocabulary -- **not "
                    "training data**",
                    "PII policy (ADR-0005)": "not applicable: machine status labels, no person "
                    "named or described",
                    "excluded from this source": "Hill of Towie (alarm codes, no strings) and "
                    "CARE (written event descriptions, evaluation-only under CC BY-SA 4.0)",
                    "not applicable": "turbines, channels, timezone, sampling resolution "
                    "(carried on the two telemetry cards)",
                }
            ),
        )
    )
    parts.append(
        section(
            "Caveats",
            "**From the provider.** none beyond the telemetry records' own.\n\n"
            "**Found during measurement.** The code book is two Senvion models, not two "
            "manufacturers. Membership is by string identity: two strings that differ only in "
            "wording are different strings here.\n\n"
            "**Known limits of this card.** Readiness is measured against one tokenizer "
            "(`text_bpe_v1`); a refit makes every figure above stale.\n",
        )
    )
    parts.append(
        section(
            "Generation",
            kv_table(
                {
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline cards code-book",
                    "template": "docs/DATASET_CARD_TEMPLATE.md",
                    "generated from": "the staged code book, the Kelmarsh and Penmanshiel status "
                    "streams, the fitted tokenizer, its training shards and training split",
                    "hand-written": "identity, copied from configs/data/sources_text.yaml and "
                    "the telemetry cards",
                }
            ),
        )
    )
    return "".join(parts)


def build_code_book_card(
    paths: ProjectPaths,
    spec: CodeBookSpec,
    tokenizer_file: Path,
    shard_dir: Path,
    corpus_name: str,
) -> Path:
    """Measure the code book and write its card.

    Args:
        paths: Resolved project paths.
        spec: The code book's source specification.
        tokenizer_file: The fitted text tokenizer.
        shard_dir: That tokenizer's text shards.
        corpus_name: The corpus it was fitted on.

    Returns:
        The written card.
    """
    measurement = measure_code_book(paths, spec, tokenizer_file, shard_dir, corpus_name)
    tokenizer = TextBPETokenizer.load(tokenizer_file)
    held_out = [*read_split(paths, corpus_name, "val"), *read_split(paths, corpus_name, "test")]
    narrative_bytes_per_token = {
        source: byte_count / token_count
        for source, (byte_count, token_count) in compression_by_source(tokenizer, held_out).items()
    }
    destination = paths.cards_dir / f"{CODE_BOOK_SOURCE}.md"
    destination.write_text(
        render_code_book_card(measurement, spec, paths, narrative_bytes_per_token),
        encoding="utf-8",
        newline="\n",
    )
    logger.info("%s: wrote %s", CODE_BOOK_SOURCE, destination)
    return destination
