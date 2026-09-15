"""robots.txt policy parsing, against two real captured files and RFC 9309 cases.

``tests/fixtures/robots/`` holds two files byte for byte as served (see the README
there): ``data_transportation_gov.txt``, whose blank lines made ``urllib.robotparser``
read every ``Disallow`` as absent, and ``www_nrc_gov.txt``, whose full-URL values the
stdlib parser can never match.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from faultline.download.nrc_text import USER_AGENT
from faultline.download.robots import RobotsPolicy

DOT = "https://data.transportation.gov"
NRC = "https://www.nrc.gov"


@pytest.fixture
def dot_policy(fixtures_dir: Path) -> RobotsPolicy:
    raw = (fixtures_dir / "robots" / "data_transportation_gov.txt").read_bytes()
    return RobotsPolicy.parse(raw.decode("utf-8"), "data.transportation.gov")


@pytest.fixture
def nrc_policy(fixtures_dir: Path) -> RobotsPolicy:
    raw = (fixtures_dir / "robots" / "www_nrc_gov.txt").read_bytes()
    return RobotsPolicy.parse(raw.decode("utf-8"), "www.nrc.gov")


class TestDataTransportationGov:
    """The blank-line regression: rules separated from ``User-agent: *`` still apply."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/odata/x",
            "/login",
            "/OData.svc/anything",
            "/api/collocate?x=1",
            "/browse?page=2&q=pipeline",
            "/dataset/alt",
        ],
    )
    def test_disallowed_paths_are_refused(self, dot_policy: RobotsPolicy, path: str) -> None:
        assert not dot_policy.can_fetch(USER_AGENT, DOT + path)

    @pytest.mark.parametrize(
        "path",
        [
            "/api/views/27nc-rsge.json",
            "/api/views/27nc-rsge/files/abc?download=true&filename=x.zip",
            "/robots.txt",
            "/browse",
        ],
    )
    def test_permitted_paths_are_allowed(self, dot_policy: RobotsPolicy, path: str) -> None:
        assert dot_policy.can_fetch(USER_AGENT, DOT + path)

    def test_crawl_delay_is_read(self, dot_policy: RobotsPolicy) -> None:
        assert dot_policy.crawl_delay(USER_AGENT) == 1.0


class TestWwwNrcGov:
    """Full-URL values naming this host are read as their paths."""

    @pytest.mark.parametrize(
        "path", ["/site-help/search", "/site-help/search.html", "/autodiscover/autodiscover.xml"]
    )
    def test_full_url_disallows_are_refused(self, nrc_policy: RobotsPolicy, path: str) -> None:
        assert not nrc_policy.can_fetch(USER_AGENT, NRC + path)

    def test_the_crawled_collections_stay_allowed(self, nrc_policy: RobotsPolicy) -> None:
        for path in (
            "/reading-rm/doc-collections/event-status/event/2020/20200101en.html",
            "/reading-rm/doc-collections/gen-comm/info-notices/1999/in99001.html",
            "/documents-reports/generic-communications/bulletins/index.html",
        ):
            assert nrc_policy.can_fetch(USER_AGENT, NRC + path)

    def test_another_crawlers_group_does_not_apply(self, nrc_policy: RobotsPolicy) -> None:
        # /docs/ is disallowed only for Akamai-SiteSnapshot and Amazonbot
        assert nrc_policy.can_fetch(USER_AGENT, NRC + "/docs/ML0000.pdf")
        assert not nrc_policy.can_fetch("Amazonbot/0.1", NRC + "/docs/ML0000.pdf")


class TestRfc9309Semantics:
    def test_longest_match_wins_and_allow_wins_a_tie(self) -> None:
        policy = RobotsPolicy.parse(
            "User-agent: *\nDisallow: /a/\nAllow: /a/b/\nDisallow: /a/b/\nAllow: /a/b/\n",
            "example.org",
        )
        assert not policy.can_fetch(USER_AGENT, "https://example.org/a/x")
        assert policy.can_fetch(USER_AGENT, "https://example.org/a/b/x")

    def test_dollar_anchors_the_end(self) -> None:
        policy = RobotsPolicy.parse("User-agent: *\nDisallow: /*.pdf$\n", "example.org")
        assert not policy.can_fetch(USER_AGENT, "https://example.org/x/y.pdf")
        assert policy.can_fetch(USER_AGENT, "https://example.org/x/y.pdf.html")

    def test_a_named_group_replaces_the_star_group(self) -> None:
        policy = RobotsPolicy.parse(
            "User-agent: *\nDisallow: /\n\nUser-agent: FaultLine-downloader\nDisallow: /x/\n",
            "example.org",
        )
        assert policy.can_fetch(USER_AGENT, "https://example.org/y")
        assert not policy.can_fetch(USER_AGENT, "https://example.org/x/1")

    def test_consecutive_user_agent_lines_share_one_group(self) -> None:
        policy = RobotsPolicy.parse(
            "User-agent: other\n\nUser-agent: *\nDisallow: /p/\n", "example.org"
        )
        assert not policy.can_fetch(USER_AGENT, "https://example.org/p/1")

    def test_a_full_url_for_another_host_states_nothing_here(self) -> None:
        policy = RobotsPolicy.parse(
            "User-agent: *\nDisallow: https://elsewhere.org/p/\n", "example.org"
        )
        assert policy.can_fetch(USER_AGENT, "https://example.org/p/1")

    def test_an_empty_disallow_allows_everything(self) -> None:
        policy = RobotsPolicy.parse("User-agent: *\nDisallow:\n", "example.org")
        assert policy.can_fetch(USER_AGENT, "https://example.org/anything")
