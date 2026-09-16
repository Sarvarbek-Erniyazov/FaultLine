"""H3's vocabulary split, re-measured under three conditions, and its testability gate.

H3 (ADR-0007) predicts a larger held-out advantage on event types whose status strings
share vocabulary with the narrative corpus. The recorded split (191/297 word types seen at
least 100 times, 70.2% token coverage, 31 absent, 76/264 strings) was measured on the
NRC-only corpus **before** `4b8caa3` changed the per-source held-out shares, and the Gate 6
re-measurement changed the shares and added PHMSA at once. Three conditions separate them:

- ``A``: NRC only, the pre-`4b8caa3` shares (corpus ``nrc_operator_narratives``) --
  re-derived here, not transcribed;
- ``B``: NRC only, the current shares (corpus ``operator_narratives`` without PHMSA);
- ``C``: NRC and PHMSA, the current shares (corpus ``operator_narratives``).

A to B is the split confound; B to C is PHMSA's contribution.

**The gate, fixed in this module before any per-side event count was computed.**

- *Partition* (under ``C``): a status string is ``high`` overlap when every word
  (:func:`faultline.data.text.code_book.words`) is seen at least 100 times in ``C``'s
  training split, ``low`` otherwise.
- *Event type*: a narrow (technical) event's type is the status string that opens it, by
  the project's existing rule (:func:`faultline.data.telemetry.verify.opening_messages`:
  the first stop row of the event's cause in its first step, else the last before it),
  matched to the code book. An event with no code-book string opening it is on neither
  side and is counted as unmapped.
- *Held-out events*: every in-grid narrow event at Hill of Towie, and every CARE anomaly.
- *Trigger* (the M3 brief's, verbatim in substance): if either side carries fewer than
  :data:`MIN_EVENTS_PER_SIDE` labelled held-out events, or fewer than
  :data:`MIN_TYPES_PER_SIDE` distinct event types, H3 as worded is not testable at this
  data scale.

Two sensitivity readings are reported beside the rule and never replace it: at Hill of
Towie, the last *described* alarm raised by the event's first step, whatever its status
or cause; at CARE, the provider's written event description, split by the same word rule.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from faultline.config import load_config
from faultline.data.common.report import kv_table, section, table
from faultline.data.telemetry.labels import EventLabelsConfig
from faultline.data.telemetry.verify import opening_messages
from faultline.data.text.code_book import (
    CODE_BOOK_SOURCE,
    RARE_THRESHOLD,
    every_word_frequent,
    train_word_frequency,
    words,
)
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

logger = get_logger(__name__)

#: The trigger: fewer labelled held-out events than this on either side is not testable.
MIN_EVENTS_PER_SIDE = 30

#: The trigger: fewer distinct event types than this on either side is not testable.
MIN_TYPES_PER_SIDE = 3

#: The narrow cause, the label H3's advantage is measured on (ADR-0009's primary label).
NARROW_CAUSE = "technical"

#: Held-out sources, in report order: the held-out site, and the dataset-level probe.
HELD_OUT_SOURCES: tuple[str, ...] = ("hill_of_towie", "care")

#: Sources whose events open with code-book strings; counted for context, not the gate.
CODE_BOOK_SITES: tuple[str, ...] = ("kelmarsh", "penmanshiel")

#: The prediction on record for B -> C: pipeline text adds these words.
PREDICTED_PIPELINE_TERMS: tuple[str, ...] = ("compressor", "valve", "pressure", "corrosion")

#: Wind terms: any one moving between B and C refutes "no wind terms".
WIND_TERMS: tuple[str, ...] = (
    "yaw",
    "nacelle",
    "pitch",
    "rotor",
    "anemometer",
    "drivetrain",
    "bladeangle",
    "twistangle",
    "rotorbearing",
)

HIGH = "high"
LOW = "low"


@dataclass(frozen=True)
class Condition:
    """One corpus condition.

    Attributes:
        name: ``A``, ``B`` or ``C``.
        corpus_name: The finished corpus whose training split is counted.
        description: What the condition isolates.
        exclude_prefix: Sources starting with this are left out; empty keeps all.
    """

    name: str
    corpus_name: str
    description: str
    exclude_prefix: str = ""

    def keep(self) -> Callable[[str], bool]:
        """The source filter this condition applies."""
        prefix = self.exclude_prefix
        return lambda source: not (prefix and source.startswith(prefix))


CONDITIONS: tuple[Condition, ...] = (
    Condition("A", "nrc_operator_narratives", "NRC only, pre-4b8caa3 shares (text_v1.yaml)"),
    Condition("B", "operator_narratives", "NRC only, current shares (text_v2.yaml)", "phmsa"),
    Condition("C", "operator_narratives", "NRC + PHMSA, current shares (text_v2.yaml)"),
)


@dataclass
class ConditionResult:
    """The code book measured against one condition.

    Attributes:
        name: The condition.
        description: What it isolates.
        documents: Training documents counted, per source.
        types_frequent: Word types seen at least the threshold.
        types_seen: Word types seen at least once.
        types_total: Word types in the code book.
        token_coverage: Share of code-book word tokens whose type is frequent.
        absent: Word types never seen.
        strings_frequent: Strings whose every word is frequent.
        strings_total: Strings in the code book.
        counts: Training count per code-book word type.
    """

    name: str
    description: str
    documents: dict[str, int]
    types_frequent: int
    types_seen: int
    types_total: int
    token_coverage: float
    absent: list[str]
    strings_frequent: int
    strings_total: int
    counts: dict[str, int] = field(repr=False)


def measure_condition(
    name: str,
    description: str,
    code_book: Sequence[str],
    frequency: Mapping[str, int],
    documents: Mapping[str, int],
    threshold: int = RARE_THRESHOLD,
) -> ConditionResult:
    """Measure the code book's word coverage under one corpus's word frequencies.

    Args:
        name: Condition name.
        description: What it isolates.
        code_book: The status strings.
        frequency: Training word frequencies.
        documents: Documents counted per source.
        threshold: The frequent floor, inclusive.

    Returns:
        The condition's measurement.
    """
    tokens = [w for s in code_book for w in words(s)]
    types = sorted(set(tokens))
    counts = {t: int(frequency.get(t, 0)) for t in types}
    return ConditionResult(
        name=name,
        description=description,
        documents=dict(documents),
        types_frequent=sum(1 for t in types if counts[t] >= threshold),
        types_seen=sum(1 for t in types if counts[t] >= 1),
        types_total=len(types),
        token_coverage=sum(1 for w in tokens if counts[w] >= threshold) / len(tokens),
        absent=[t for t in types if counts[t] == 0],
        strings_frequent=sum(all(counts[w] >= threshold for w in words(s)) for s in code_book),
        strings_total=len(code_book),
        counts=counts,
    )


@dataclass(frozen=True)
class Move:
    """A code-book word type whose standing changed between two conditions.

    Attributes:
        word: The word type.
        before: Its count in the earlier condition.
        after: Its count in the later condition.
        kind: ``absent -> present``, ``rare -> frequent``, ``absent -> frequent``, or the
            reverse moves ``frequent -> rare`` and ``present -> absent``.
    """

    word: str
    before: int
    after: int
    kind: str


def moves(
    before: Mapping[str, int], after: Mapping[str, int], threshold: int = RARE_THRESHOLD
) -> list[Move]:
    """Every word type crossing absent/present or the frequent threshold, either way.

    Args:
        before: Counts per word type in the earlier condition.
        after: Counts per word type in the later condition.
        threshold: The frequent floor, inclusive.

    Returns:
        The moves, sorted by kind and then word.
    """
    out: list[Move] = []
    for word in sorted(set(before) | set(after)):
        b, a = int(before.get(word, 0)), int(after.get(word, 0))
        if b == 0 and a >= threshold:
            kind = "absent -> frequent"
        elif b == 0 and a > 0:
            kind = "absent -> present"
        elif b < threshold <= a:
            kind = "rare -> frequent"
        elif a == 0 < b:
            kind = "present -> absent"
        elif a < threshold <= b:
            kind = "frequent -> rare"
        else:
            continue
        out.append(Move(word, b, a, kind))
    return sorted(out, key=lambda m: (m.kind, m.word))


@dataclass(frozen=True)
class TermVerdict:
    """One term of the prediction, checked.

    Attributes:
        term: The word.
        in_code_book: Whether it is a code-book word type at all.
        count_b: Its count under B.
        count_c: Its count under C.
        moved: Whether it moved between B and C (absent -> present, or across the floor).
        verdict: The plain-language outcome.
    """

    term: str
    in_code_book: bool
    count_b: int
    count_c: int
    moved: bool
    verdict: str


def check_terms(
    terms: Sequence[str],
    code_book_types: set[str],
    freq_b: Mapping[str, int],
    freq_c: Mapping[str, int],
    expect_move: bool,
    threshold: int = RARE_THRESHOLD,
) -> list[TermVerdict]:
    """Check each term of a prediction against the B -> C counts.

    Args:
        terms: The terms.
        code_book_types: The code book's word types.
        freq_b: Word frequencies under B (the whole corpus, not only code-book words).
        freq_c: Word frequencies under C.
        expect_move: True for "PHMSA adds this term", False for "PHMSA adds no such term".
        threshold: The frequent floor, inclusive.

    Returns:
        One verdict per term.
    """
    out: list[TermVerdict] = []
    for term in terms:
        b, c = int(freq_b.get(term, 0)), int(freq_c.get(term, 0))
        moved = (b == 0 < c) or (b < threshold <= c)
        in_book = term in code_book_types
        if expect_move:
            corpus = (
                (f"corpus: confirmed, x{c / b:.1f}" if c > b > 0 else "corpus: confirmed, new")
                if c > b
                else "corpus: refuted, no rise"
            )
            if not in_book:
                split = "split: not a code-book word, cannot move it"
            elif moved:
                split = "split: confirmed, moved"
            elif b >= threshold:
                split = "split: no effect, already frequent under B"
            else:
                split = "split: refuted, did not cross the floor"
            verdict = f"{corpus}; {split}"
        else:
            verdict = "refutes 'no wind terms'" if moved else "confirmed: did not move"
        out.append(TermVerdict(term, in_book, b, c, moved, verdict))
    return out


def partition(
    code_book: Sequence[str], frequency: Mapping[str, int], threshold: int = RARE_THRESHOLD
) -> dict[str, str]:
    """The pre-registered high/low overlap partition of the status strings.

    Args:
        code_book: The status strings.
        frequency: Word frequencies of the condition the split is drawn under (C).
        threshold: The frequent floor, inclusive.

    Returns:
        Per lowercased string, ``high`` or ``low``.
    """
    counter = Counter(frequency)
    return {
        s.lower(): HIGH if every_word_frequent(s, counter, threshold) else LOW for s in code_book
    }


@dataclass
class SideCount:
    """Events per side at one source under one reading.

    Attributes:
        source: The source.
        reading: ``rule`` or the sensitivity reading's name.
        events: Events considered.
        unmapped: Events on neither side.
        per_side: Events per side.
        types_per_side: Distinct event types per side, with their event counts.
    """

    source: str
    reading: str
    events: int
    unmapped: int
    per_side: dict[str, int]
    types_per_side: dict[str, dict[str, int]]

    def testable(self) -> bool:
        """Whether both sides clear the pre-registered trigger."""
        return all(
            self.per_side.get(side, 0) >= MIN_EVENTS_PER_SIDE
            and len(self.types_per_side.get(side, {})) >= MIN_TYPES_PER_SIDE
            for side in (HIGH, LOW)
        )


def count_sides(
    source: str, reading: str, types: pd.Series[Any], side_of: Callable[[str], str | None]
) -> SideCount:
    """Count events and distinct types per side.

    Args:
        source: The source.
        reading: The reading's name.
        types: One event type per event; missing where none was found.
        side_of: The side of a type, or ``None`` when it is on neither.

    Returns:
        The count.
    """
    per_side: dict[str, int] = {HIGH: 0, LOW: 0}
    by_type: dict[str, Counter[str]] = {HIGH: Counter(), LOW: Counter()}
    unmapped = 0
    for value in types.tolist():
        if value is None or pd.isna(value):
            unmapped += 1
            continue
        side = side_of(str(value))
        if side is None:
            unmapped += 1
            continue
        per_side[side] += 1
        by_type[side][str(value)] += 1
    return SideCount(
        source=source,
        reading=reading,
        events=len(types),
        unmapped=unmapped,
        per_side=per_side,
        types_per_side={side: dict(c.most_common()) for side, c in by_type.items()},
    )


def _events(paths: ProjectPaths, source: str) -> pd.DataFrame:
    path = paths.source_dir("cleaned", "telemetry", source) / "labels" / "events_narrow.parquet"
    events = pd.read_parquet(path)
    return events[events["in_grid"]].reset_index(drop=True)


def _stream(paths: ProjectPaths, source: str) -> pd.DataFrame | None:
    path = paths.source_dir("cleaned", "telemetry", source) / "labels" / "status_stream.parquet"
    return pd.read_parquet(path) if path.is_file() else None


@dataclass
class OverlapResult:
    """Everything the H3 vocabulary report states.

    Attributes:
        conditions: A, B and C.
        split_moves: A -> B moves (the split confound).
        phmsa_moves: B -> C moves (PHMSA's contribution).
        pipeline_terms: The pipeline prediction, term by term.
        wind_terms: The wind prediction, term by term.
        side_strings: Strings per side under C.
        counts: Events per side, rule and sensitivity readings, every source.
        held_out_messages: Distinct described messages per held-out source and their
            causes, as the status stream carries them.
    """

    conditions: list[ConditionResult]
    split_moves: list[Move]
    phmsa_moves: list[Move]
    pipeline_terms: list[TermVerdict]
    wind_terms: list[TermVerdict]
    side_strings: dict[str, int]
    counts: list[SideCount]
    held_out_messages: dict[str, list[tuple[str, str, str, int]]]

    def rule_counts(self) -> list[SideCount]:
        """The held-out counts under the pre-registered rule."""
        return [c for c in self.counts if c.reading == "rule" and c.source in HELD_OUT_SOURCES]

    def testable(self) -> bool:
        """The gate's verdict: every held-out source clears the trigger under the rule."""
        return all(c.testable() for c in self.rule_counts())


def measure_overlap(paths: ProjectPaths, labels_config: Path) -> OverlapResult:
    """Run the three conditions, the prediction check and the gate.

    Args:
        paths: Resolved project paths.
        labels_config: The event labelling file the labels were built under.

    Returns:
        The measurement.
    """
    book_path = paths.stage_dir("raw", "text") / f"{CODE_BOOK_SOURCE}.jsonl"
    code_book = [
        str(json.loads(line)["text"])
        for line in book_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    frequencies: dict[str, Counter[str]] = {}
    results: list[ConditionResult] = []
    for condition in CONDITIONS:
        frequency, documents = train_word_frequency(paths, condition.corpus_name, condition.keep())
        frequencies[condition.name] = frequency
        results.append(
            measure_condition(
                condition.name, condition.description, code_book, frequency, documents
            )
        )
        logger.info("condition %s measured", condition.name)
    by_name = {r.name: r for r in results}
    book_types = set(by_name["C"].counts)

    sides = partition(code_book, frequencies["C"])
    rules = load_config(labels_config, EventLabelsConfig)
    stop_status = rules.harmonised.stop_status if rules.harmonised else "Stop"

    counts: list[SideCount] = []
    held_out_messages: dict[str, list[tuple[str, str, str, int]]] = {}
    for source in (*CODE_BOOK_SITES, *HELD_OUT_SOURCES):
        events = _events(paths, source)
        stream = _stream(paths, source)
        if stream is not None and len(events):
            opened = opening_messages(events, stream, NARROW_CAUSE, stop_status)
        else:
            opened = pd.Series(pd.NA, index=events.index, dtype="string")
        counts.append(count_sides(source, "rule", opened, sides.get))
        if source == "hill_of_towie" and stream is not None:
            described = stream[stream["message"].notna()]
            grouped = (
                described.groupby(["message", "provider_status", "cause"], dropna=False)
                .size()
                .sort_values(ascending=False)
            )
            held_out_messages[source] = [
                (str(key[0]), str(key[1]), str(key[2]), int(n))
                for key, n in zip(grouped.index.tolist(), grouped.tolist(), strict=True)
            ]
            relaxed = described.assign(provider_status="any", cause="any")
            last_described = opening_messages(events, relaxed, "any", "any")
            counts.append(
                count_sides(
                    source,
                    "sensitivity: last described alarm by the first step, any status or cause",
                    last_described,
                    lambda m: (
                        HIGH if every_word_frequent(m, frequencies["C"], RARE_THRESHOLD) else LOW
                    ),
                )
            )
        if source == "care":
            ingest = pd.read_parquet(
                paths.source_dir("cleaned", "telemetry", source) / "ingest" / "events.parquet"
            )
            anomalies = ingest[ingest["code"] == "anomaly"]
            held_out_messages[source] = [
                (str(m), "event description", "anomaly", int(n))
                for m, n in anomalies["message"].value_counts().items()
            ]
            counts.append(
                count_sides(
                    source,
                    "sensitivity: the written event description, same word rule",
                    anomalies["message"].reset_index(drop=True),
                    lambda m: (
                        HIGH if every_word_frequent(m, frequencies["C"], RARE_THRESHOLD) else LOW
                    ),
                )
            )

    return OverlapResult(
        conditions=results,
        split_moves=moves(by_name["A"].counts, by_name["B"].counts),
        phmsa_moves=moves(by_name["B"].counts, by_name["C"].counts),
        pipeline_terms=check_terms(
            PREDICTED_PIPELINE_TERMS, book_types, frequencies["B"], frequencies["C"], True
        ),
        wind_terms=check_terms(WIND_TERMS, book_types, frequencies["B"], frequencies["C"], False),
        side_strings=dict(Counter(sides.values())),
        counts=counts,
        held_out_messages=held_out_messages,
    )


def _moves_table(items: Sequence[Move]) -> str:
    return table(
        ["word", "before", "after", "move"], [(m.word, m.before, m.after, m.kind) for m in items]
    )


def _types(side: SideCount, name: str) -> str:
    types = side.types_per_side.get(name, {})
    if not types:
        return "none"
    return "; ".join(f"{t} ({n})" for t, n in types.items())


def render_overlap_report(result: OverlapResult, labels_config: Path, paths: ProjectPaths) -> str:
    """Render the H3 vocabulary report.

    Args:
        result: The measurement.
        labels_config: The labelling file the events were built under.
        paths: Resolved project paths.

    Returns:
        The report, as Markdown.
    """
    parts = ["# H3 vocabulary overlap, three conditions, and the testability gate\n\n"]
    parts.append(
        kv_table(
            {
                "code book": f"data/raw/text/{CODE_BOOK_SOURCE}.jsonl",
                "word rule": "lowercase `[a-z]+` (reproduces 297 types / 883 tokens)",
                "frequent": f"seen at least {RARE_THRESHOLD} times in the condition's training "
                "split",
                "labels": labels_config.as_posix(),
                "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "git_sha": git_sha(paths.repo_root),
                "generated by": "faultline inspect vocab-overlap",
            }
        )
    )
    rows = [
        (
            r.name,
            r.description,
            f"{sum(r.documents.values()):,}",
            f"{r.types_frequent}/{r.types_total}",
            f"{r.token_coverage:.2%}",
            r.types_seen,
            len(r.absent),
            f"{r.strings_frequent}/{r.strings_total}",
        )
        for r in result.conditions
    ]
    parts.append(
        section(
            "1. The three conditions",
            table(
                [
                    "condition",
                    "corpus",
                    "train documents",
                    "types seen >= 100",
                    "word-token coverage",
                    "types seen >= 1",
                    "types absent",
                    "strings, every word >= 100",
                ],
                rows,
            )
            + "\nWord-level throughout: these are word types and word tokens of the code "
            "book under the rule above, not BPE tokens (the token-level figures are on "
            "`data/cards/status_code_book.md`).\n\n"
            + "\n".join(
                f"- **{r.name}** documents per source: "
                + ", ".join(f"{k} {v:,}" for k, v in sorted(r.documents.items()))
                for r in result.conditions
            )
            + "\n\n"
            + "\n".join(
                f"- **{r.name}** absent ({len(r.absent)}): " + ", ".join(f"`{w}`" for w in r.absent)
                for r in result.conditions
            )
            + "\n",
        )
    )
    parts.append(
        section(
            "2. A -> B: the split confound",
            _moves_table(result.split_moves)
            + "\nNRC documents moved between train and held-out when the shares changed; "
            "nothing was added or removed from the corpus.\n",
        )
    )
    parts.append(
        section(
            "3. B -> C: what PHMSA adds",
            _moves_table(result.phmsa_moves)
            + "\nB is C without PHMSA, so counts can only rise; every code-book word type "
            "crossing absent -> present or the 100 floor is listed.\n\n"
            "### The prediction on record, term by term\n\n"
            "Pipeline text adds `compressor`, `valve`, `pressure`, `corrosion`:\n\n"
            + table(
                ["term", "code-book word", "count B", "count C", "moved", "verdict"],
                [
                    (t.term, t.in_code_book, t.count_b, t.count_c, t.moved, t.verdict)
                    for t in result.pipeline_terms
                ],
            )
            + "\n...and no wind terms:\n\n"
            + table(
                ["term", "code-book word", "count B", "count C", "moved", "verdict"],
                [
                    (t.term, t.in_code_book, t.count_b, t.count_c, t.moved, t.verdict)
                    for t in result.wind_terms
                ],
            ),
        )
    )
    count_rows = [
        (
            c.source,
            c.reading,
            c.events,
            c.unmapped,
            c.per_side[HIGH],
            len(c.types_per_side[HIGH]),
            c.per_side[LOW],
            len(c.types_per_side[LOW]),
            ("clears" if c.testable() else "TRIGGER")
            if c.source in HELD_OUT_SOURCES
            else ("context: would clear" if c.testable() else "context: would trigger"),
        )
        for c in result.counts
    ]
    message_rows = [
        (source, m, status, cause, n)
        for source, items in result.held_out_messages.items()
        for m, status, cause, n in items
    ]
    verdict = (
        "**H3 as worded is testable at this data scale.**"
        if result.testable()
        else "**H3 as worded is NOT testable at this data scale. The trigger fired: stop, "
        "and do not start Part C.**"
    )
    parts.append(
        section(
            "4. The gate",
            f"Partition under C: {result.side_strings.get(HIGH, 0)} strings high, "
            f"{result.side_strings.get(LOW, 0)} low. Trigger: fewer than "
            f"{MIN_EVENTS_PER_SIDE} labelled held-out events or fewer than "
            f"{MIN_TYPES_PER_SIDE} distinct event types on either side. The rule, the "
            "mapping and the trigger are fixed in `src/faultline/data/text/vocab_overlap.py`'s "
            "docstring; sensitivity readings are reported, never substituted.\n\n"
            + table(
                [
                    "source",
                    "reading",
                    "narrow events",
                    "on neither side",
                    "high events",
                    "high types",
                    "low events",
                    "low types",
                    "trigger",
                ],
                count_rows,
            )
            + "\nKelmarsh and Penmanshiel are training sites, counted over every in-grid "
            "narrow event for context only; they are not held out and do not enter the gate. "
            "Their high side is what the split looks like where status strings do exist.\n\n"
            + "\n".join(
                f"- **{c.source}**, {c.reading}: high = {_types(c, HIGH)}; low = {_types(c, LOW)}"
                for c in result.counts
            )
            + "\n\n**Reading the sensitivity rows.** A sensitivity row that clears does not "
            "overturn the rule. At Hill of Towie every described message is a generator "
            "switching alarm (non-stopping) or a planned or environmental stop; none is "
            "technical, so none can be the type of a narrow event. The relaxed reading gives "
            "a technical fault the name of whatever described alarm last fired, which is "
            "almost always a generator cut-in or cut-out: it measures what text the pathway "
            "would carry next to a fault, not what the fault was. At CARE the descriptions "
            "are written per event, so nearly every event is its own type, and 45 events "
            f"cannot put {MIN_EVENTS_PER_SIDE} on each side whatever the partition."
            + "\n\n### What the held-out sources carry as text\n\n"
            + table(["source", "message", "status", "cause", "rows"], message_rows)
            + f"\n{verdict}\n",
        )
    )
    return "".join(parts)


def inspect_vocab_overlap(paths: ProjectPaths, labels_config: Path) -> tuple[Path, Path]:
    """Measure the overlap and the gate, and write the report and its JSON.

    Args:
        paths: Resolved project paths.
        labels_config: The labelling file the events were built under.

    Returns:
        The Markdown report and the JSON record.
    """
    result = measure_overlap(paths, labels_config)
    stem = f"h3_vocab_overlap_v1_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(
        render_overlap_report(result, labels_config, paths), encoding="utf-8", newline="\n"
    )
    record = asdict(result)
    for condition in record["conditions"]:
        condition.pop("counts")
    record["testable"] = result.testable()
    json_path = paths.data_reports_dir / f"{stem}.json"
    json_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, json_path)
    return report, json_path
