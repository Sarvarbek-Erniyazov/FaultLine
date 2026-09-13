"""Pure-function tests for the NRC text downloader. No network, no live pages.

Every fixture here is a trimmed excerpt of a real page's structure, captured during
M2a reconnaissance and cited in the fixture file's own header comment, so a change to
the real page layout is what would break these tests -- not a guess about markup that
was never actually served.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests
from pydantic import ValidationError

from faultline.download.nrc_text import (
    EventNotificationsSpec,
    GenericCommSpec,
    NrcTextClient,
    SourcesTextConfig,
    extract_events,
    extract_generic_comm_document,
    filter_native_document_links,
    strip_html,
)


class _FakeSession(requests.Session):
    """A session standing in for the transport layer.

    Lets a test see exactly which URLs reached it -- and, for the robots.txt gate,
    prove that a disallowed one never does.

    Attributes:
        responses: Canned ``(status_code, text)`` per URL; a URL not listed raises,
            the same way a real connection failure would.
        requested: Every URL actually passed to :meth:`get`, in order.
    """

    def __init__(self, responses: dict[str, tuple[int, str]]) -> None:
        super().__init__()
        self.responses = responses
        self.requested: list[str] = []

    def get(self, url: str, *args: object, **kwargs: object) -> requests.Response:
        self.requested.append(url)
        if url not in self.responses:
            raise requests.ConnectionError(f"no canned response for {url}")
        status, text = self.responses[url]
        response = requests.Response()
        response.status_code = status
        response._content = text.encode("utf-8")
        response.url = url
        return response


@pytest.fixture
def event_day_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "nrc_text" / "event_day.html").read_text(encoding="utf-8")


@pytest.fixture
def event_day_midera_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "nrc_text" / "event_day_midera.html").read_text(encoding="utf-8")


@pytest.fixture
def event_day_midera_variant_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "nrc_text" / "event_day_midera_variant.html").read_text(encoding="utf-8")


@pytest.fixture
def event_day_legacy_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "nrc_text" / "event_day_legacy.html").read_text(encoding="utf-8")


@pytest.fixture
def generic_comm_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "nrc_text" / "generic_comm_doc.html").read_text(encoding="utf-8")


@pytest.fixture
def year_index_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "nrc_text" / "year_index.html").read_text(encoding="utf-8")


def test_strip_html_decodes_entities_and_breaks() -> None:
    assert strip_html("&quot;Hello&quot;<br />World") == '"Hello"\nWorld'


def test_strip_html_collapses_blank_lines() -> None:
    assert strip_html("a<br /><br /><br />b") == "a\nb"


class TestExtractEvents:
    def test_extracts_one_document_per_event_with_text(self, event_day_html: str) -> None:
        documents = extract_events(
            event_day_html,
            "https://www.nrc.gov/documents-reports/.../2024/20241231en",
        )
        # the second event's Event Text div is empty and yields no document
        assert len(documents) == 1
        assert documents[0].doc_id == "20241231en_en57533"

    def test_event_text_is_cleaned_and_complete(self, event_day_html: str) -> None:
        [document] = extract_events(event_day_html, ".../2024/20241231en")
        assert document.text.startswith("AGREEMENT STATE REPORT - UNQUALIFIED PERSONNEL")
        assert "Arizona Incident Number: 25-002" in document.text
        # the structured header fields (Rep Org, Licensee, Region) are not the
        # narrative and must not leak into it
        assert "Rep Org" not in document.text
        assert "<" not in document.text and ">" not in document.text

    def test_no_events_yields_no_documents(self) -> None:
        assert extract_events("<p>no events today</p>", ".../x") == []

    def test_midera_template_extracts_every_event(self, event_day_midera_html: str) -> None:
        documents = extract_events(
            event_day_midera_html,
            "https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2018/20180703en",
        )
        assert [d.doc_id for d in documents] == [
            "20180703en_en53468",
            "20180703en_en53470",
            "20180703en_en53484",
            "20180703en_en53485",
            "20180703en_en53486",
        ]
        assert documents[0].text.startswith("AGREEMENT STATE REPORT - DOSE MISADMINISTRATION")
        assert "Rep Org" not in documents[0].text
        assert "<" not in documents[0].text and ">" not in documents[0].text

    def test_midera_template_tolerates_whitespace_and_attribute_variants(
        self, event_day_midera_variant_html: str
    ) -> None:
        """Discovered only by re-checking staged counts, not by any warning.

        A regex tight enough to match one year's exact markup silently missed two
        others -- every one of these pages fetches at 200 OK; only the extraction, a
        content-shaped failure, was silent. This fixture is the specific page that
        exposed the third variant (a `scope="row"` attribute on `<td>`, on top of the
        whitespace and `class` differences the other midera fixture and tests cover).
        """
        documents = extract_events(
            event_day_midera_variant_html,
            "https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2020/20201015en",
        )
        assert [d.doc_id for d in documents] == [
            "20201015en_en54933",
            "20201015en_en54936",
        ]
        assert "AGREEMENT STATE REPORT - REPORT OF LOST STATIC ELIMINATOR" in documents[0].text
        assert "<" not in documents[0].text and ">" not in documents[0].text

    def test_legacy_template_extracts_every_event(self, event_day_legacy_html: str) -> None:
        documents = extract_events(
            event_day_legacy_html,
            "https://www.nrc.gov/reading-rm/doc-collections/event-status/event/1999/19990104en",
        )
        # the fixture keeps only the first two of the real page's seven events, so the
        # second is the last event on the (trimmed) page -- both boundary cases fire
        assert [d.doc_id for d in documents] == [
            "19990104en_en35207",
            "19990104en_en35208",
        ]
        assert documents[0].text.startswith(
            "CONTROL ROOM VENTILATION OUTSIDE DESIGN BASIS CALCULATION"
        )
        assert documents[1].text.startswith("INOPERABLE ATMOSPHERIC RELIEF VALVES")
        # box-drawing and pipe characters must not leak into the narrative
        for document in documents:
            assert "+--" not in document.text
            assert not document.text.startswith("|")

    def test_modern_template_is_tried_before_the_others(self, event_day_html: str) -> None:
        """A modern page has no `<pre>` and no `<a name="en...">`.

        So it must never fall through to the legacy or midera extractors with a
        false match.
        """
        documents = extract_events(event_day_html, ".../2024/20241231en")
        assert len(documents) == 1  # unchanged from the modern-only test above


class TestGenericCommDocument:
    def test_extracts_body_and_title(self, generic_comm_html: str) -> None:
        document = extract_generic_comm_document(
            generic_comm_html,
            "https://www.nrc.gov/reading-rm/doc-collections/gen-comm/bulletins/1988/bl88011",
        )
        assert document is not None
        assert document.doc_id == "bl88011"
        assert document.title == "Bulletin 88-11: Pressurizer Surge Line Thermal Stratification"
        assert "PRESSURIZER SURGE LINE THERMAL STRATIFICATION" in document.text
        assert "Page Last Reviewed" not in document.text  # footer excluded

    def test_page_without_a_body_field_yields_none(self) -> None:
        assert extract_generic_comm_document("<html><body>redirect</body></html>", "u") is None


class TestHtmlNativeFiltering:
    def test_keeps_native_pages_and_drops_pdfs_from_either_path(self, year_index_html: str) -> None:
        kept = filter_native_document_links(year_index_html)
        assert kept == sorted(
            {
                "https://www.nrc.gov/reading-rm/doc-collections/gen-comm/bulletins/1988/bl88011",
                "https://www.nrc.gov/reading-rm/doc-collections/gen-comm/bulletins/1988/bl88010",
            }
        )
        # the ADAMS PDF redirect is present on the page and must never be kept
        assert not any("/docs/" in link for link in kept)
        # nor the /sites/default/files/... PDF path -- a link is excluded by its
        # .pdf extension, not by which path serves it (this is what /docs/-only
        # filtering missed: reg-issues 2003-onward documents come through this path)
        assert not any(link.lower().endswith(".pdf") for link in kept)
        assert not any("doc_library" in link for link in kept)


class TestSourcesTextConfig:
    def test_shipped_config_loads(self, repo_root: Path) -> None:
        from faultline.download.nrc_text import load_sources_text_config

        config = load_sources_text_config(repo_root / "configs" / "data" / "sources_text.yaml")
        assert config.version >= 1
        assert config.sources

    def test_discriminates_source_kinds(self) -> None:
        config = SourcesTextConfig(
            sources={
                "a": EventNotificationsSpec(
                    provider="p",
                    license="l",
                    attribution="a",
                    base_url="https://example.org",
                    year_start=2000,
                    year_end=2001,
                    robots_basis="r",
                ),
                "b": GenericCommSpec(
                    provider="p",
                    license="l",
                    attribution="a",
                    label="B",
                    index_url="https://example.org/b",
                    year_start=2000,
                    year_end=2001,
                    robots_basis="r",
                ),
            }
        )
        assert config.sources["a"].kind == "event_notifications"
        assert config.sources["b"].kind == "generic_comm"

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            EventNotificationsSpec(
                provider="p",
                license="l",
                attribution="a",
                base_url="u",
                year_start=2000,
                year_end=2001,
                robots_basis="r",
                unknown_field=True,  # type: ignore[call-arg]
            )


class TestRobotsGating:
    """Every request checks its host's robots.txt before it is made.

    ADR-0016's corrected record of the two ORNL /api/ queries that went out before
    anyone had checked. These tests exercise the mechanism against a fake transport,
    so a disallowed URL provably never reaches it, rather than trusting that it would
    not.
    """

    def test_a_disallowed_path_is_refused_and_never_requested(self) -> None:
        session = _FakeSession(
            {
                "https://example.org/robots.txt": (
                    200,
                    "User-agent: *\nDisallow: /private/\n",
                )
            }
        )
        client = NrcTextClient(min_interval=0, session=session)

        result = client.get("https://example.org/private/secret")

        assert result is None
        assert session.requested == ["https://example.org/robots.txt"]

    def test_an_allowed_path_is_requested_after_the_robots_check(self) -> None:
        session = _FakeSession(
            {
                "https://example.org/robots.txt": (200, "User-agent: *\nDisallow: /private/\n"),
                "https://example.org/public/page": (200, "hello"),
            }
        )
        client = NrcTextClient(min_interval=0, session=session)

        result = client.get("https://example.org/public/page")

        assert result is not None
        assert result.text == "hello"
        assert session.requested == [
            "https://example.org/robots.txt",
            "https://example.org/public/page",
        ]

    def test_robots_txt_is_fetched_once_per_host_and_cached(self) -> None:
        session = _FakeSession(
            {
                "https://example.org/robots.txt": (200, "User-agent: *\nAllow: /\n"),
                "https://example.org/a": (200, "a"),
                "https://example.org/b": (200, "b"),
            }
        )
        client = NrcTextClient(min_interval=0, session=session)

        client.get("https://example.org/a")
        client.get("https://example.org/b")

        assert session.requested.count("https://example.org/robots.txt") == 1

    def test_a_403_on_robots_txt_itself_disallows_the_whole_host(self) -> None:
        session = _FakeSession({"https://example.org/robots.txt": (403, "")})
        client = NrcTextClient(min_interval=0, session=session)

        result = client.get("https://example.org/anything")

        assert result is None
        assert session.requested == ["https://example.org/robots.txt"]

    def test_a_missing_robots_txt_allows_everything(self) -> None:
        session = _FakeSession(
            {
                "https://example.org/robots.txt": (404, ""),
                "https://example.org/page": (200, "content"),
            }
        )
        client = NrcTextClient(min_interval=0, session=session)

        result = client.get("https://example.org/page")

        assert result is not None
        assert result.text == "content"

    def test_an_unreachable_robots_txt_allows_everything(self) -> None:
        # no canned response at all -> the fake session raises, matching a real
        # connection failure
        session = _FakeSession({"https://example.org/page": (200, "content")})
        client = NrcTextClient(min_interval=0, session=session)

        result = client.get("https://example.org/page")

        assert result is not None
        assert result.text == "content"

    def test_different_hosts_are_checked_independently(self) -> None:
        session = _FakeSession(
            {
                "https://allowed.org/robots.txt": (200, "User-agent: *\nAllow: /\n"),
                "https://allowed.org/page": (200, "ok"),
                "https://blocked.org/robots.txt": (200, "User-agent: *\nDisallow: /\n"),
            }
        )
        client = NrcTextClient(min_interval=0, session=session)

        allowed = client.get("https://allowed.org/page")
        blocked = client.get("https://blocked.org/page")

        assert allowed is not None
        assert blocked is None
        assert "https://blocked.org/page" not in session.requested
