"""Golden diff between the ported regexes (v0) and FaultLine's (v1).

The point of these tests is not that v1 is better. It is that the difference is
*enumerated*: every string on which the two versions disagree is listed here with
both outputs, and every string on which they agree is listed too. A change to either
regex that moves a case from one list to the other fails, and the diff shows exactly
which case moved.

That matters because v0 is a port whose value is being checkable against its source
(``docs/COURSE_PORT.md``). "We improved the regex" is not checkable; "these four
strings changed and no others did" is.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultline.config import load_config
from faultline.data.text.clean import CleanConfig, clean_text, remove_html
from faultline.data.text.patterns import PHONE_PATTERNS, PatternVersion
from faultline.data.text.pii import PIIConfig, scrub_pii
from faultline.data.text.pipeline import TextConfigFile

# -- the golden cases ------------------------------------------------------------------
#
# (name, input, v0 output, v1 output). A case where the two outputs are equal is a
# case the versions deliberately agree on, and it is here for exactly that reason.

TAG_CASES: tuple[tuple[str, str, str, str], ...] = (
    ("open and close tag", "<p>hello</p>", " hello ", " hello "),
    ("self-closing tag", "a <br/> b", "a   b", "a   b"),
    ("tag with attributes", "<div class='x'>y</div>", " y ", " y "),
    ("no markup", "no markup here", "no markup here", "no markup here"),
    ("html comment", "a <!-- note --> b", "a   b", "a   b"),
    # The cases that differ. All four are prose using < or > as an operator, which v0
    # reads as a tag because it only requires a closing >.
    ("prose comparison", "2 < 3 and 4 > 1", "2   1", "2 < 3 and 4 > 1"),
    (
        "kelmarsh status message with a later close",
        "Wind < start wind. Temperature > limit",
        "Wind   limit",
        "Wind < start wind. Temperature > limit",
    ),
    (
        "threshold description",
        "trip if speed < 4 m/s or pitch > 88 deg",
        "trip if speed   88 deg",
        "trip if speed < 4 m/s or pitch > 88 deg",
    ),
    (
        "markup and a comparison in one document",
        "<b>alarm</b> raised when P < 50 kW and T > 90 C",
        " alarm  raised when P   90 C",
        " alarm  raised when P < 50 kW and T > 90 C",
    ),
)

#: Tag cases the two versions disagree on. Stated once, checked twice: as a set here
#: and case by case above.
TAG_DIFFERING = {
    "prose comparison",
    "kelmarsh status message with a later close",
    "threshold description",
    "markup and a comparison in one document",
}

PHONE_CASES: tuple[tuple[str, str, str, str], ...] = (
    (
        "international number",
        "call +44 1234 567890 today",
        "call <PHONE> today",
        "call <PHONE> today",
    ),
    (
        "national trunk number",
        "control room at 020 7946 0958 before isolating",
        "control room at <PHONE> before isolating",
        "control room at <PHONE> before isolating",
    ),
    (
        "parenthesised area code",
        "duty line (0123) 456 7890 out of hours",
        "duty line (<PHONE> out of hours",
        "duty line <PHONE> out of hours",
    ),
    ("short number", "rated at 2050 kW", "rated at 2050 kW", "rated at 2050 kW"),
    (
        "magnitude that ADR-0005 protects",
        "held at 850000 kW for six minutes",
        "held at 850000 kW for six minutes",
        "held at 850000 kW for six minutes",
    ),
    # The cases that differ. Every one is a v0 false positive: a run of digits that
    # is not a telephone number.
    (
        "serial number",
        "Serial number 8812349900 was recorded",
        "Serial number <PHONE> was recorded",
        "Serial number 8812349900 was recorded",
    ),
    (
        "work order reference",
        "raised under 4471829001 last week",
        "raised under <PHONE> last week",
        "raised under 4471829001 last week",
    ),
    (
        "spaced digit sequence",
        "1 2 3 4 5 6 7 8 9 0 1 2",
        "<PHONE>",
        "1 2 3 4 5 6 7 8 9 0 1 2",
    ),
    (
        "year range",
        "covering 2016 - 2024 inclusive",
        "covering <PHONE> inclusive",
        "covering 2016 - 2024 inclusive",
    ),
)

#: Differing cases where v0 masked something that is not a telephone number at all.
PHONE_FALSE_POSITIVES = {
    "serial number",
    "work order reference",
    "spaced digit sequence",
    "year range",
}

#: The one differing case where both versions mask a real number, but v0 starts one
#: character late and strands the opening bracket.
PHONE_PARTIAL_MATCHES = {"parenthesised area code"}

PHONE_DIFFERING = PHONE_FALSE_POSITIVES | PHONE_PARTIAL_MATCHES


# -- case by case ----------------------------------------------------------------------


@pytest.mark.parametrize(("name", "raw", "v0", "v1"), TAG_CASES, ids=[c[0] for c in TAG_CASES])
def test_tag_case(name: str, raw: str, v0: str, v1: str) -> None:
    assert remove_html(raw, "v0") == v0
    assert remove_html(raw, "v1") == v1


@pytest.mark.parametrize(("name", "raw", "v0", "v1"), PHONE_CASES, ids=[c[0] for c in PHONE_CASES])
def test_phone_case(name: str, raw: str, v0: str, v1: str) -> None:
    assert scrub_pii(raw, PIIConfig(phone_pattern="v0"))[0] == v0
    assert scrub_pii(raw, PIIConfig(phone_pattern="v1"))[0] == v1


def test_exactly_these_tag_cases_differ() -> None:
    differing = {name for name, _, v0, v1 in TAG_CASES if v0 != v1}
    assert differing == TAG_DIFFERING


def test_exactly_these_phone_cases_differ() -> None:
    differing = {name for name, _, v0, v1 in PHONE_CASES if v0 != v1}
    assert differing == PHONE_DIFFERING


def test_every_tag_difference_is_v0_destroying_prose() -> None:
    # v1 never removes something v0 kept; it only stops removing things that were
    # never markup. A future edit that made v1 *more* aggressive would fail here.
    for _, _raw, v0, v1 in TAG_CASES:
        assert len(v1) >= len(v0)


def test_the_false_positives_survive_v1_untouched() -> None:
    for name, raw, _, v1 in PHONE_CASES:
        if name in PHONE_FALSE_POSITIVES:
            assert "<PHONE>" not in v1, f"{name} should survive v1"
            assert v1 == raw, f"{name} should be unchanged by v1"


def test_the_partial_match_is_masked_by_both_but_only_v1_takes_the_bracket() -> None:
    # Not a false positive: (0123) 456 7890 is a telephone number, and both versions
    # mask it. v0's match starts one character late, leaving a stray "(" in the text.
    for name, _, v0, v1 in PHONE_CASES:
        if name in PHONE_PARTIAL_MATCHES:
            assert "<PHONE>" in v0 and "<PHONE>" in v1
            assert "(<PHONE>" in v0
            assert "(" not in v1


# -- the committed corpus --------------------------------------------------------------


def corpus(fixtures_dir: Path) -> list[dict[str, str]]:
    path = fixtures_dir / "text" / "sample.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_exactly_two_fixture_documents_change_under_the_v1_phone_regex(
    fixtures_dir: Path,
) -> None:
    changed = [
        doc["id"]
        for doc in corpus(fixtures_dir)
        if PHONE_PATTERNS["v0"].sub("<PHONE>", doc["text"])
        != PHONE_PATTERNS["v1"].sub("<PHONE>", doc["text"])
    ]
    # doc-033 carries "Serial number 8812349900"; doc-041 is a line of single digits
    # and spaces. Both were masked whole by v0. The two documents holding real
    # telephone numbers, doc-030 and doc-031, are masked identically by both.
    assert changed == ["doc-033", "doc-041"]


def test_the_real_telephone_numbers_are_still_masked(fixtures_dir: Path) -> None:
    documents = {doc["id"]: doc["text"] for doc in corpus(fixtures_dir)}
    for doc_id in ("doc-030", "doc-031"):
        scrubbed, stats = scrub_pii(documents[doc_id], PIIConfig(phone_pattern="v1"))
        assert stats["phone"] == 1
        assert "<PHONE>" in scrubbed


def test_no_fixture_document_changes_under_the_v1_tag_regex(fixtures_dir: Path) -> None:
    # An honest negative result: the committed corpus contains no bare "<" used as a
    # comparison, so it does not exercise the tag fix at all. The TAG_CASES table
    # above is what covers it, and this test exists so that the gap in the fixture is
    # asserted rather than assumed.
    changed = [
        doc["id"]
        for doc in corpus(fixtures_dir)
        if remove_html(doc["text"], "v0") != remove_html(doc["text"], "v1")
    ]
    assert changed == []


# -- the configurations -----------------------------------------------------------------


def test_v0_config_still_selects_the_ported_regexes(repo_root: Path) -> None:
    config = load_config(repo_root / "configs" / "data" / "text_v0.yaml", TextConfigFile).text
    assert config.clean.html_tag_pattern == "v0"
    assert config.pii.phone_pattern == "v0"


def test_v1_config_differs_from_v0_in_exactly_two_keys(repo_root: Path) -> None:
    configs = repo_root / "configs" / "data"
    v0 = load_config(configs / "text_v0.yaml", TextConfigFile).text.model_dump()
    v1 = load_config(configs / "text_v1.yaml", TextConfigFile).text.model_dump()
    differing = {
        f"{block}.{key}"
        for block in v0
        if isinstance(v0[block], dict)
        for key in v0[block]
        if v0[block][key] != v1[block][key]
    }
    assert differing == {"clean.html_tag_pattern", "pii.phone_pattern"}
    # and nothing outside those two blocks moved
    assert {b for b in v0 if v0[b] != v1[b]} == {"clean", "pii"}


def test_the_defaults_are_the_ported_behaviour() -> None:
    # A caller who constructs a config without saying anything gets the port, not
    # FaultLine's version. Silently defaulting to v1 would make the port
    # uncheckable.
    assert CleanConfig().html_tag_pattern == "v0"
    assert PIIConfig().phone_pattern == "v0"
    assert clean_text("2 < 3 and 4 > 1") == "2 1"


def test_v1_cleaning_preserves_a_status_message_end_to_end() -> None:
    # The case ADR-0007 turns from a curiosity into a defect.
    config = CleanConfig(html_tag_pattern="v1")
    message = "Wind < start wind logged before the trip; T > 90 C afterwards"
    assert clean_text(message, config) == message
    assert clean_text(message) != message  # v0 loses the middle


@pytest.mark.parametrize("version", ["v0", "v1"])
def test_both_versions_still_strip_real_markup(version: PatternVersion) -> None:
    config = CleanConfig(html_tag_pattern=version)
    assert clean_text("<p>The <b>converter</b> tripped.</p>", config) == "The converter tripped."
