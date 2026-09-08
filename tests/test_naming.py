"""ADR-0002: banned strings must not appear in tracked files."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultline.naming import EXEMPT_FILES, FORBIDDEN, scan_repository, scan_text, scannable_files
from faultline.paths import find_repo_root

REPO_ROOT = find_repo_root(Path(__file__).resolve())


def test_repository_is_clean() -> None:
    violations = scan_repository(REPO_ROOT)
    assert not violations, "ADR-0002 violations:\n" + "\n".join(str(v) for v in violations)


def test_scan_actually_scans_something() -> None:
    # A scanner that silently finds no files would pass the test above forever.
    # Before the first commit git lists nothing, so the walk fallback covers it.
    assert len(scannable_files(REPO_ROOT)) > 20


def test_only_the_decision_record_is_exempt() -> None:
    assert EXEMPT_FILES == frozenset({"docs/DECISIONS.md"})


def test_decision_record_actually_states_the_rule() -> None:
    # The exemption exists so ADR-0002 can spell the rule out. If it stopped doing so,
    # the exemption would be dead weight hiding a real violation.
    text = (REPO_ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8").lower()
    for term in FORBIDDEN:
        assert term in text


@pytest.mark.parametrize("term", FORBIDDEN)
def test_each_forbidden_term_is_detected(term: str) -> None:
    assert scan_text(f"a line mentioning {term} here")
    assert scan_text(f"a line mentioning {term.upper()} here")


def test_http_header_is_the_only_allowed_context() -> None:
    assert not scan_text('headers = {"User-Agent": USER_AGENT}')
    assert not scan_text("USER_AGENT = 'FaultLine-downloader/0.1.0'")
    assert not scan_text("user-agent: FaultLine")
    # Built from the scanner's own table rather than spelled out, so this file does
    # not need an exemption of its own.
    assert scan_text(f"this is an autonomous {FORBIDDEN[-1]}")


def test_clean_text_produces_no_violations() -> None:
    assert not scan_text("a perfectly ordinary line about wind turbine telemetry")
