"""Which turbine-year the streaming trace runs on: the two rules, declared in one place.

The trace is a demonstration, and a demonstration chooses its example. Choosing it badly
is how a demonstration quietly becomes a claim, so both rules live here, written down
before any score was looked at, and both are reported side by side wherever either trace
appears.

**The most-events rule** picks the densest turbine-year the site has. It is the clearest
picture -- a year with enough labelled events to see the trace against -- and it selects
an atypical turbine-year by construction, which is the whole of its bias.

**The typical-rate rule** picks the turbine-year whose positive-window rate is closest to
the pooled test base rate the gates were read on. It is the least unlike the pooled split,
and it is chosen on labels alone: the rate is a property of the label column and the
window index, and no score is read to compute it.

Neither is an evaluation result. Two turbine-years are not a sample, the rules were not
pre-registered in ``docs/DECISIONS.md`` because nothing here decides anything, and the
numbers each trace reports describe that turbine-year and nothing else.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from faultline.data.common.report import table

#: The turbine with the most labelled narrow event starts in the year.
MOST_EVENTS = "most_events"

#: The turbine whose positive-window rate is closest to the pooled test base rate.
TYPICAL_RATE = "typical_rate"

#: Both rules, in the order the traces were written.
RULES: tuple[str, ...] = (MOST_EVENTS, TYPICAL_RATE)

#: Per rule, the short name it is referred to by.
RULE_NAMES = {MOST_EVENTS: "most events", TYPICAL_RATE: "typical event rate"}

#: Per rule, the criterion exactly as it was declared, before any score was looked at.
RULE_CRITERIA = {
    MOST_EVENTS: "the turbine with the most labelled narrow event starts in the year",
    TYPICAL_RATE: "the turbine whose positive-window rate in the year is closest to the "
    "pooled test base rate",
}

#: Per rule, what it selects for -- which is to say, how it is biased.
RULE_SELECTS = {
    MOST_EVENTS: "the densest turbine-year the site has, which is an atypical one by construction",
    TYPICAL_RATE: "the turbine-year least unlike the pooled test split the gates were read on",
}

#: Ties under either rule go to the lowest turbine id, so the choice is a function of the
#: labels and nothing else.
TIE_BREAK = "ties broken by the lowest turbine id"

#: The record both traces write themselves into, under ``reports/data/``.
TRACE_RECORD = "stream_traces_v0.json"

#: The sentence that stands over both traces wherever either of them is shown.
STANDING = (
    "Two turbine-years are traced, under two selection rules declared before any score was "
    "looked at: one chosen for the most events, one chosen for a typical event rate. Both "
    "are shown. Neither is an evaluation result."
)


def rules_block(entries: Sequence[Mapping[str, Any]] = ()) -> str:
    """The two rules side by side, with whichever trace each one has produced.

    Args:
        entries: Written traces, from :func:`read_traces`; an empty sequence renders the
            rules with their turbine-year column left open.

    Returns:
        A Markdown paragraph and table.
    """
    by_rule = {str(entry["rule"]): entry for entry in entries}
    rows = []
    for rule in RULES:
        entry = by_rule.get(rule)
        rows.append(
            [
                RULE_NAMES[rule],
                f"{RULE_CRITERIA[rule]}, {TIE_BREAK}",
                RULE_SELECTS[rule],
                f"{entry['turbine']}, {entry['year']}" if entry else "_(not yet traced)_",
                f"`{entry['stem']}.md`" if entry else "",
            ]
        )
    return (
        STANDING
        + "\n\n"
        + table(["rule", "criterion, as declared", "what it selects for", "chose", "files"], rows)
    )


def read_traces(path: Path) -> list[dict[str, Any]]:
    """Read the trace record, in rule order.

    Args:
        path: The record under ``reports/data/``.

    Returns:
        One entry a written trace, ordered by :data:`RULES`; empty when absent.
    """
    if not path.is_file():
        return []
    parsed = json.loads(path.read_text(encoding="utf-8"))
    return _ordered(list(parsed["traces"]))


def write_trace(path: Path, entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Add or replace one rule's entry in the record, leaving the other rule's alone.

    A trace is rerun on its own, so the record is merged rather than overwritten: the
    second rule's run must not drop the first rule's entry.

    Args:
        path: The record under ``reports/data/``.
        entry: The trace, carrying at least ``rule`` and ``stem``.

    Returns:
        The record as written.
    """
    kept = [existing for existing in read_traces(path) if existing["rule"] != entry["rule"]]
    traces = _ordered([*kept, dict(entry)])
    path.write_text(json.dumps({"traces": traces}, indent=2) + "\n", encoding="utf-8", newline="\n")
    return traces


def _ordered(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort entries into rule order, unknown rules last, by stem inside a rule.

    Args:
        traces: The entries.

    Returns:
        The same entries, ordered.
    """
    order = {rule: index for index, rule in enumerate(RULES)}

    def rank(entry: dict[str, Any]) -> tuple[int, str]:
        return order.get(str(entry["rule"]), len(RULES)), str(entry["stem"])

    return sorted(traces, key=rank)
