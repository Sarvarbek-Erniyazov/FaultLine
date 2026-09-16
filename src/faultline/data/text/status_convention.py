"""H3' Stage A: whether the status strings' token-level gap is surface convention (ADR-0017).

At the token level 18 of 264 status strings have every BPE token frequent in training; at
the word level 80 do (`data/cards/status_code_book.md`). A status string starts a line
and is capitalised, so its first word encodes as a string-initial piece that prose rarely
produces. Stage A re-encodes every string the way prose writes a word, lowercased after a
single space, with the **frozen** tokenizer, and re-measures token-level coverage with the
card's own instrument (:func:`faultline.data.text.code_book.every_token_frequent`, the
same :data:`~faultline.data.text.code_book.RARE_THRESHOLD`). Nothing is refitted and no
shard is rewritten: normalization happens at encode time.

**The decision rule, fixed in ADR-0017 before the normalized count was computed.** More
than :data:`CONVENTION_DOMINANT_ABOVE` of 264 strings covered after normalization confirms
surface convention as the dominant barrier. At or below it, convention is only partial and
the residual is segmentation-level; that is the finding, and the claim is not re-worded.

Two single-change conventions (a leading space alone, lowercase alone) are reported beside
the pre-registered one, as context for which half of the change does the work. The
verdict reads the pre-registered convention only.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from faultline.data.common.report import kv_table, section, table
from faultline.data.text.bpe_fit import compression_by_source, read_split
from faultline.data.text.code_book import (
    CODE_BOOK_SOURCE,
    RARE_THRESHOLD,
    every_token_frequent,
    every_word_frequent,
    train_token_frequency,
    train_word_frequency,
)
from faultline.data.text.shards import shards_dir
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.tokenizers.text_bpe import TextBPETokenizer

logger = get_logger(__name__)

#: ADR-0017's pre-registered line: strictly more than this many of 264 strings covered
#: after normalization confirms convention as the dominant barrier.
CONVENTION_DOMINANT_ABOVE = 50

#: The convention the verdict reads.
NORMALIZED = "normalized"

#: The convention status strings are staged in.
RAW = "raw"


def normalize_status(text: str) -> str:
    """Write a status string the way prose writes a word: lowercased, after one space.

    The H3' encoding convention (ADR-0017). It is applied at encode time and changes
    neither the tokenizer nor the vocabulary.

    Args:
        text: A status string as the provider writes it.

    Returns:
        The string lowercased, with a single leading space.
    """
    return " " + text.lower()


#: Every convention measured, in report order. Only :data:`NORMALIZED` is pre-registered.
CONVENTIONS: dict[str, Callable[[str], str]] = {
    RAW: lambda text: text,
    "leading space only": lambda text: " " + text,
    "lowercase only": str.lower,
    NORMALIZED: normalize_status,
}


@dataclass(frozen=True)
class ConventionCoverage:
    """Token-level coverage of the code book under one encoding convention.

    Attributes:
        convention: The convention's name.
        covered: Strings whose every token is frequent.
        tokens: Tokens over all strings.
        chars: Characters over all encoded texts, any added space included.
        utf8_bytes: UTF-8 bytes over the same texts.
    """

    convention: str
    covered: int
    tokens: int
    chars: int
    utf8_bytes: int

    @property
    def chars_per_token(self) -> float:
        """Characters per token."""
        return self.chars / self.tokens

    @property
    def bytes_per_token(self) -> float:
        """UTF-8 bytes per token, the unit the narrative sources report."""
        return self.utf8_bytes / self.tokens


@dataclass(frozen=True)
class StringChange:
    """A status string that changes side between the raw and normalized encodings.

    Attributes:
        text: The string as staged.
        gained: True if normalization covers it, False if normalization loses it.
        raw_pieces: Its raw encoding, one decoded piece per token.
        normalized_pieces: Its normalized encoding, likewise.
        first_token_only: Whether its raw encoding's only rare token was the first.
    """

    text: str
    gained: bool
    raw_pieces: list[str]
    normalized_pieces: list[str]
    first_token_only: bool


@dataclass
class StageAResult:
    """Everything Stage A reports.

    Attributes:
        strings: Strings measured.
        coverage: Coverage per convention, in :data:`CONVENTIONS` order.
        changes: Strings that change side, raw to normalized.
        first_token_failures: Raw strings whose only rare token is their first.
        first_token_fixed: Of those, strings covered after normalization.
        word_covered: Strings whose every word is frequent, the card's word-level count.
        normalized_not_word: Covered at the token level after normalization, not at the
            word level: a rare word that still splits into frequent pieces.
        word_not_normalized: Covered at the word level, not at the token level after
            normalization: frequent words the tokenizer splits into rare pieces.
        narrative_bytes_per_token: Held-out bytes per token per narrative source.
        tokenizer_file: The frozen tokenizer measured with.
        shard_dir: Its training shards, for token frequency.
        corpus_name: The corpus the narrative baseline comes from.
        threshold: The frequency floor.
    """

    strings: int
    coverage: list[ConventionCoverage]
    changes: list[StringChange]
    first_token_failures: int
    first_token_fixed: int
    word_covered: int
    normalized_not_word: list[str]
    word_not_normalized: list[str]
    narrative_bytes_per_token: dict[str, float]
    tokenizer_file: str
    shard_dir: str
    corpus_name: str
    threshold: int = RARE_THRESHOLD

    def covered(self, convention: str) -> int:
        """Strings covered under a named convention."""
        return next(c.covered for c in self.coverage if c.convention == convention)

    def convention_dominant(self) -> bool:
        """The pre-registered verdict: more than the line covered after normalization."""
        return self.covered(NORMALIZED) > CONVENTION_DOMINANT_ABOVE


def first_token_only(ids: Sequence[int], frequency: np.ndarray, threshold: int) -> bool:
    """Whether a string's only rare token is its first, the card's definition.

    Args:
        ids: The string's token ids.
        frequency: Training frequency per id.
        threshold: The frequency floor, inclusive.

    Returns:
        True if position 0 is the one position below the floor.
    """
    return [p for p, i in enumerate(ids) if int(frequency[i]) < threshold] == [0]


def compare_with_word_level(
    normalized_covered: set[str], word_covered: set[str]
) -> tuple[list[str], list[str]]:
    """The strings on which normalized token-level and word-level coverage disagree.

    Equal counts do not mean equal sets, so the sets are compared rather than the counts.

    Args:
        normalized_covered: Strings covered at the token level after normalization.
        word_covered: Strings covered at the word level.

    Returns:
        Strings covered only after normalization, and strings covered only by words.
    """
    return sorted(normalized_covered - word_covered), sorted(word_covered - normalized_covered)


def measure_conventions(
    strings: Sequence[str],
    encode: Callable[[str], Sequence[int]],
    decode_piece: Callable[[int], str],
    frequency: np.ndarray,
    threshold: int = RARE_THRESHOLD,
) -> tuple[list[ConventionCoverage], list[StringChange], int, int]:
    """Measure token-level coverage under every convention, and the raw-to-normalized diff.

    Args:
        strings: The code book.
        encode: The frozen tokenizer's encoder.
        decode_piece: Decodes one token id to its text piece, for the diff.
        frequency: Training frequency per token id.
        threshold: The frequency floor, inclusive.

    Returns:
        Coverage per convention, the strings that change side, the raw first-token
        failures, and how many of those normalization covers.
    """
    encoded: dict[str, dict[str, list[int]]] = {
        name: {s: list(encode(convert(s))) for s in strings}
        for name, convert in CONVENTIONS.items()
    }
    coverage = [
        ConventionCoverage(
            convention=name,
            covered=sum(every_token_frequent(ids, frequency, threshold) for ids in by.values()),
            tokens=sum(len(ids) for ids in by.values()),
            chars=sum(len(CONVENTIONS[name](s)) for s in strings),
            utf8_bytes=sum(len(CONVENTIONS[name](s).encode("utf-8")) for s in strings),
        )
        for name, by in encoded.items()
    ]
    changes: list[StringChange] = []
    failures = 0
    fixed = 0
    for s in strings:
        raw_ids, normal_ids = encoded[RAW][s], encoded[NORMALIZED][s]
        before = every_token_frequent(raw_ids, frequency, threshold)
        after = every_token_frequent(normal_ids, frequency, threshold)
        first_only = first_token_only(raw_ids, frequency, threshold)
        failures += first_only
        fixed += first_only and after
        if before != after:
            changes.append(
                StringChange(
                    text=s,
                    gained=after,
                    raw_pieces=[decode_piece(i) for i in raw_ids],
                    normalized_pieces=[decode_piece(i) for i in normal_ids],
                    first_token_only=first_only,
                )
            )
    return coverage, changes, failures, fixed


def measure_stage_a(paths: ProjectPaths, tokenizer_file: Path, corpus_name: str) -> StageAResult:
    """Measure Stage A on the staged code book with the frozen tokenizer.

    Args:
        paths: Resolved project paths.
        tokenizer_file: The fitted text tokenizer; its shards give token frequency.
        corpus_name: The corpus it was fitted on, for the narrative bytes/token baseline.

    Returns:
        The measurement.

    Raises:
        FileNotFoundError: If the code book is not staged.
    """
    book_path = paths.stage_dir("raw", "text") / f"{CODE_BOOK_SOURCE}.jsonl"
    if not book_path.is_file():
        raise FileNotFoundError(f"{book_path}: stage the code book with `faultline download text`")
    strings = [
        str(json.loads(line)["text"])
        for line in book_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    tokenizer = TextBPETokenizer.load(tokenizer_file)
    shard_dir = shards_dir(paths, tokenizer_file)
    frequency = train_token_frequency(shard_dir, tokenizer.vocab_size)
    coverage, changes, failures, fixed = measure_conventions(
        strings, tokenizer.encode, lambda i: tokenizer.decode([i]), frequency
    )
    word_frequency, _documents = train_word_frequency(paths, corpus_name)
    word_covered = {s for s in strings if every_word_frequent(s, word_frequency, RARE_THRESHOLD)}
    normalized_covered = {
        s
        for s in strings
        if every_token_frequent(tokenizer.encode(normalize_status(s)), frequency, RARE_THRESHOLD)
    }
    normalized_only, word_only = compare_with_word_level(normalized_covered, word_covered)
    held_out = [*read_split(paths, corpus_name, "val"), *read_split(paths, corpus_name, "test")]
    baseline = {
        source: byte_count / token_count
        for source, (byte_count, token_count) in compression_by_source(tokenizer, held_out).items()
    }
    return StageAResult(
        strings=len(strings),
        coverage=coverage,
        changes=changes,
        first_token_failures=failures,
        first_token_fixed=fixed,
        word_covered=len(word_covered),
        normalized_not_word=normalized_only,
        word_not_normalized=word_only,
        narrative_bytes_per_token=dict(sorted(baseline.items())),
        tokenizer_file=tokenizer_file.relative_to(paths.repo_root).as_posix()
        if tokenizer_file.is_relative_to(paths.repo_root)
        else tokenizer_file.as_posix(),
        shard_dir=shard_dir.name,
        corpus_name=corpus_name,
    )


def _pieces(pieces: Sequence[str]) -> str:
    # a space-separated run of code spans: a pipe would split the table cell
    return " ".join(f"`{p}`".replace("|", "\\|") for p in pieces)


def render_stage_a_report(result: StageAResult, paths: ProjectPaths) -> str:
    """Render the Stage A report.

    Args:
        result: The measurement.
        paths: Resolved project paths.

    Returns:
        The Markdown report.
    """
    n = result.strings
    raw = result.covered(RAW)
    normal = result.covered(NORMALIZED)
    parts = [
        "# H3' Stage A: status strings under the prose convention\n\n",
        kv_table(
            {
                "decision record": "docs/DECISIONS.md, ADR-0017 (rule fixed before this run)",
                "code book": f"data/raw/text/{CODE_BOOK_SOURCE}.jsonl",
                "tokenizer (frozen, not refitted)": result.tokenizer_file,
                "token frequency from": f"training shards `{result.shard_dir}`",
                "frequent means": f"seen at least {result.threshold} times in training",
                "normalization": 'at encode time: `" " + s.lower()`',
                "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "git_sha": git_sha(paths.repo_root),
                "generated by": "faultline inspect status-convention",
            }
        ),
    ]
    rows = [
        [
            c.convention + (" (pre-registered)" if c.convention == NORMALIZED else ""),
            f"{c.covered} / {n}",
            f"{c.covered / n:.1%}",
            f"{c.tokens:,}",
            f"{c.tokens / n:.2f}",
            f"{c.chars_per_token:.2f}",
            f"{c.bytes_per_token:.2f}",
        ]
        for c in result.coverage
    ]
    parts.append(
        section(
            "1. Token-level coverage per convention",
            table(
                [
                    "convention",
                    "every token frequent",
                    "share",
                    "tokens",
                    "tokens/string",
                    "chars/token",
                    "bytes/token",
                ],
                rows,
            )
            + "\nCharacters and bytes count the encoded text, so the added space is included. "
            "Held-out narrative bytes/token, same tokenizer (val and test together): "
            + ", ".join(f"{s} {v:.2f}" for s, v in result.narrative_bytes_per_token.items())
            + ".\n",
        )
    )
    verdict = (
        f"**{normal} / {n} > {CONVENTION_DOMINANT_ABOVE}: surface convention is CONFIRMED as "
        "the dominant barrier among the recoverable strings.**"
        if result.convention_dominant()
        else f"**{normal} / {n} <= {CONVENTION_DOMINANT_ABOVE}: convention is only PARTIAL. "
        "The residual is segmentation-level: the words are frequent but these strings do not "
        "split into frequent pieces. This is the finding; the claim is not re-worded.**"
    )
    parts.append(
        section(
            "2. The pre-registered verdict",
            f"Rule (ADR-0017): more than {CONVENTION_DOMINANT_ABOVE} of {n} covered after "
            "normalization confirms convention as the dominant barrier; "
            f"{CONVENTION_DOMINANT_ABOVE} or fewer means convention is partial.\n\n"
            f"{verdict}\n\n"
            f"Raw {raw} -> normalized {normal}: {normal - raw:+d} strings. "
            f"First-token failures (the only rare token is the first, raw): "
            f"**{result.first_token_fixed} of {result.first_token_failures} fixed** by "
            "normalization.\n",
        )
    )
    gained = [c for c in result.changes if c.gained]
    lost = [c for c in result.changes if not c.gained]
    for title, members in (
        (f"3. Strings normalization covers ({len(gained)})", gained),
        (f"4. Strings normalization loses ({len(lost)})", lost),
    ):
        body = (
            table(
                ["string", "raw pieces", "normalized pieces", "raw first-token failure"],
                [
                    [
                        f"`{c.text}`",
                        _pieces(c.raw_pieces),
                        _pieces(c.normalized_pieces),
                        "yes" if c.first_token_only else "no",
                    ]
                    for c in sorted(members, key=lambda c: c.text.lower())
                ],
            )
            if members
            else "None.\n"
        )
        parts.append(section(title, body))
    agree = normal - len(result.normalized_not_word)
    parts.append(
        section(
            "5. Against the word-level count",
            f"Word level (lowercase `[a-z]+`, every word seen at least {result.threshold} "
            f"times in `{result.corpus_name}` training): **{result.word_covered} / {n}**. "
            f"Normalized token level: **{normal} / {n}**. **Equal counts are not equal sets**: "
            f"{agree} strings are covered by both.\n\n"
            + table(
                ["disagreement", "strings", "which"],
                [
                    [
                        "token-covered after normalization, a word rare",
                        str(len(result.normalized_not_word)),
                        ", ".join(f"`{t}`" for t in result.normalized_not_word) or "none",
                    ],
                    [
                        "every word frequent, a token rare after normalization",
                        str(len(result.word_not_normalized)),
                        ", ".join(f"`{t}`" for t in result.word_not_normalized) or "none",
                    ],
                ],
            )
            + "\nThe second row is the residual below the word level: every word is frequent, "
            "yet some piece is rare, because the frozen tokenizer splits a word into rare "
            "pieces or because the string carries digits or punctuation the word rule "
            "ignores. The first row is a caveat on the instrument itself: frequent pieces are "
            "not a known word (`Yaw error` is token-covered raw as `Y` `aw` ` error`, and "
            "`yaw` is absent from the corpus).\n",
        )
    )
    return "".join(parts)


def inspect_status_convention(
    paths: ProjectPaths, tokenizer_file: Path, corpus_name: str
) -> tuple[Path, Path]:
    """Measure Stage A and write its report and JSON record.

    Args:
        paths: Resolved project paths.
        tokenizer_file: The frozen text tokenizer.
        corpus_name: The corpus it was fitted on.

    Returns:
        The Markdown report and the JSON record.
    """
    result = measure_stage_a(paths, tokenizer_file, corpus_name)
    stem = f"h3prime_stage_a_v1_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(render_stage_a_report(result, paths), encoding="utf-8", newline="\n")
    record: dict[str, object] = asdict(result)
    record["convention_dominant"] = result.convention_dominant()
    record["line"] = CONVENTION_DOMINANT_ABOVE
    json_path = paths.data_reports_dir / f"{stem}.json"
    json_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, json_path)
    return report, json_path
