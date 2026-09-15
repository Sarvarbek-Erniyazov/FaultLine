"""Staging of the NRC operator-narrative text corpus (M2a).

Two document families, both served from ``www.nrc.gov`` under 17 U.S.C. 105 (works of
the United States federal government carry no domestic copyright), both permitted by
``nrc.gov/robots.txt``'s general ``User-agent: *`` rule:

* **Event Notification Reports** -- one HTML page per report day, each holding one or
  more dated events with a free-text "Event Text" narrative. Native HTML since the
  collection began.
* **Generic communications** (Information Notices, Bulletins, Generic Letters,
  Regulatory Issue Summaries, Preliminary Notifications) -- a per-document page per
  year. Older documents are native HTML pages on ``nrc.gov`` itself; newer ones link
  to a PDF instead, served from two different paths depending on collection and
  year: ``/docs/`` (an ADAMS accession, which returns ``403 Access Denied`` from the
  edge to a plain HTTP client -- measured directly, not inferred from robots.txt,
  which does not disallow it for a generic user agent) and
  ``/sites/default/files/doc_library/...`` (a different hosting path entirely,
  which answers ``200`` but is still a PDF -- found only because Regulatory Issue
  Summaries' 2003-onward documents come through it, and a ``/docs/``-only filter
  silently miscounted every one of them as native HTML). This module keeps a link
  only when it points at a same-collection document page and does **not** end in
  ``.pdf`` -- the file extension decides, not which path serves it. What either PDF
  route excludes is recorded per source in ``configs/data/sources_text.yaml`` and in
  ADR-0016, not silently dropped.

Politeness is structural, not a courtesy comment: every request through
:class:`NrcTextClient` waits for a minimum interval since the last one, in addition to
the retrying transport ``download/zenodo.py`` already establishes the pattern for. A
persistent failure on one page is logged and skipped rather than raised, so a
multi-hour crawl survives a handful of bad pages.
"""

from __future__ import annotations

import html
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

import requests
from pydantic import Field
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from faultline import __version__
from faultline.config import StrictModel, load_config
from faultline.data.common.manifest import (
    FileRecord,
    SourceManifest,
    hash_file,
    load_manifest,
    manifest_path,
    write_manifest,
    write_manifest_sharded,
)
from faultline.download.robots import RobotsPolicy
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths

logger = get_logger(__name__)

#: Identifies this project to nrc.gov, the same way ``download/zenodo.py`` does for
#: Zenodo. The header name is the sole permitted use of the word it carries; see
#: ADR-0002.
USER_AGENT = (
    f"FaultLine-downloader/{__version__} (+https://github.com/Sarvarbek-Erniyazov/FaultLine)"
)

#: Seconds enforced between requests, regardless of how fast the server answers.
#: Chosen empirically: bursts faster than this drew a transient Akamai 403 on
#: nrc.gov during M2a reconnaissance, which cleared on its own after a pause -- a
#: rate limit, not a rule the robots.txt states. This keeps every crawl under it.
MIN_REQUEST_INTERVAL = 1.5

_EVENT_BLOCK = re.compile(
    r'<div class="grid border" id="(en\d+)">(.*?)(?=<div class="grid border" id="en\d+">|\Z)',
    re.S,
)
_EVENT_TEXT = re.compile(r'<b>Event Text</b>\s*<div class="border">(.*?)</div>', re.S)
_BODY_FIELD = re.compile(r'field--name-field-body[^>]*>(.*?)<div class="last-modified', re.S)
_TITLE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
_YEAR_LINK = re.compile(r'href="(/[^"]*/((?:19|20)\d\d)/?)"')
_DOC_LINK = re.compile(r'href="([^"]+)"')
_BR = re.compile(r"(?i)<br\s*/?\??>")
_TAG = re.compile(r"(?s)<[^>]+>")
_WS = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")


def strip_html(fragment: str) -> str:
    """Reduce an HTML fragment to plain text.

    Args:
        fragment: Raw HTML.

    Returns:
        Text with tags removed, entities decoded and whitespace collapsed.
    """
    text = _BR.sub("\n", fragment)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = _WS.sub(" ", text)
    text = _BLANK_LINES.sub("\n", text)
    return text.strip()


@dataclass(frozen=True)
class FetchedDocument:
    """One retrieved document, ready to stage.

    Attributes:
        doc_id: Stable identifier, unique within its source.
        url: The URL it was fetched from.
        text: Extracted narrative text.
        title: Short label for the report, when the page carries one.
        template_era: Which template produced this document, for a source whose
            markup changed shape over the years it spans (event notifications);
            empty for every other source, which only ever has one template.
    """

    doc_id: str
    url: str
    text: str
    title: str = ""
    template_era: str = ""


# --------------------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------------------


class EventNotificationsSpec(StrictModel):
    """The NRC Event Notification Reports collection.

    Attributes:
        kind: Discriminator.
        enabled: Whether this source is staged.
        provider: Publishing organisation.
        license: Licence basis (public domain, with its statutory citation).
        attribution: Attribution string for dataset cards and any published output.
        base_url: Collection root; report days hang off ``<base_url>/<year>/<yyyymmdd>en``.
        year_start: First year with a report day (the collection's start).
        year_end: Last year to check; a year with no report days yields nothing.
        robots_basis: The exact robots.txt rule this access route relies on.
    """

    kind: Literal["event_notifications"] = "event_notifications"
    enabled: bool = True
    provider: str
    license: str
    attribution: str
    base_url: str
    year_start: int
    year_end: int
    robots_basis: str


class GenericCommSpec(StrictModel):
    """One NRC "generic communications" collection.

    Attributes:
        kind: Discriminator.
        enabled: Whether this source is staged.
        provider: Publishing organisation.
        license: Licence basis.
        attribution: Attribution string.
        label: Human-readable collection name.
        index_url: The collection's top index page, which lists every year.
        year_start: Earliest year measured to hold a year page.
        year_end: Latest year measured to hold a year page.
        robots_basis: The exact robots.txt rule this access route relies on.
        pdf_excluded: Whether this collection has documents this module deliberately
            does not fetch (the ``/docs/`` ADAMS PDF path, blocked at the edge -- see
            the module docstring). ``True`` for every collection actually measured.
    """

    kind: Literal["generic_comm"] = "generic_comm"
    enabled: bool = True
    provider: str
    license: str
    attribution: str
    label: str
    index_url: str
    year_start: int
    year_end: int
    robots_basis: str
    pdf_excluded: bool = True


class CodeBookSpec(StrictModel):
    """The Kelmarsh/Penmanshiel status-message code book.

    Not fetched over the network: extracted from the already-staged telemetry event
    tables (ADR-0007's tiny separately-carded source).

    Attributes:
        kind: Discriminator.
        enabled: Whether this source is built.
        provider: Publishing organisation.
        license: Licence basis, inherited from the telemetry records it is drawn from.
        attribution: Attribution string.
        telemetry_sources: Telemetry source ids to pool distinct messages from.
    """

    kind: Literal["status_code_book"] = "status_code_book"
    enabled: bool = True
    provider: str
    license: str
    attribution: str
    telemetry_sources: list[str]


class SocrataAttachment(StrictModel):
    """One file attached to a Socrata catalogue record.

    Attributes:
        asset_id: The attachment's ``assetId`` in the record's ``metadata.attachments``.
        filename: The attachment's ``filename``.
        pipeline_type: Short hyphenated key for what the file covers; prefixes each
            document id and names the manifest shard its documents are recorded in.
    """

    asset_id: str
    filename: str
    pipeline_type: str = Field(pattern=r"^[a-z0-9-]+$")


class SocrataAttachmentsSpec(StrictModel):
    """Tabular incident files attached to a DOT Socrata record, one narrative per row.

    PHMSA's per-type incident flat files (ADR-0016, 2026-09-16): each attachment is a
    zip holding one tab-delimited table, one row per report, whose ``narrative_column``
    is the operator's free-text account. Each non-empty narrative is one document.

    Attributes:
        kind: Discriminator.
        enabled: Whether this source is staged.
        provider: Publishing organisation.
        license: Licence basis.
        attribution: Attribution string.
        view: Socrata view id the attachments belong to.
        archive_source: Manifest id the zip archives themselves are recorded under.
        narrative_column: Column holding the narrative.
        id_column: Column holding the report number, unique within one file.
        robots_basis: The exact robots.txt reading this access route relies on.
        attachments: The files staged, in order.
    """

    kind: Literal["socrata_attachments"] = "socrata_attachments"
    enabled: bool = True
    provider: str
    license: str
    attribution: str
    view: str
    archive_source: str
    narrative_column: str
    id_column: str
    robots_basis: str
    attachments: list[SocrataAttachment]


TextSourceSpec = Annotated[
    EventNotificationsSpec | GenericCommSpec | CodeBookSpec | SocrataAttachmentsSpec,
    Field(discriminator="kind"),
]


class ExcludedCandidate(StrictModel):
    """A source considered and not staged, with the evidence recorded rather than dropped.

    Attributes:
        status: ``blocked`` (no route, automated or manual-bulk, is open) or
            ``excluded`` (a route is open but the source fails on other grounds --
            terms not clearly permissive per ADR-0004's default, or measured
            thinness) or ``manual_pending`` (the automated route is blocked, but a
            human downloading a named public-domain file is an open, ordinary
            route, not attempted yet) or ``pending_measurement`` (a permitted route
            is open and the stage-or-exclude verdict waits on a pre-registered
            measurement). ``manual_pending`` is not a synonym for ``blocked``:
            conflating "this project's automated client cannot fetch it" with "no
            permitted route exists" is exactly the distinction ADR-0016 was
            corrected to draw.
        reason: One-line reason.
        evidence: What was actually observed -- a status code, a robots.txt line, a
            DNS failure -- not a paraphrase of it.
        manual_route: For ``manual_pending``, the exact file(s) a human would
            download, and where that URL was read from.
    """

    status: Literal["blocked", "excluded", "manual_pending", "pending_measurement"]
    reason: str
    evidence: str
    manual_route: str | None = None


class SourcesTextConfig(StrictModel):
    """Top level of ``configs/data/sources_text.yaml``.

    Attributes:
        version: Version of this specification.
        sources: Staged sources keyed by source id.
        excluded_candidates: Sources considered and not staged, keyed by candidate id.
    """

    version: int = 1
    sources: dict[str, TextSourceSpec]
    excluded_candidates: dict[str, ExcludedCandidate] = Field(default_factory=dict)


def load_sources_text_config(path: Path) -> SourcesTextConfig:
    """Load and validate the text source specification.

    Args:
        path: Path to the YAML file.

    Returns:
        The validated configuration.
    """
    return load_config(path, SourcesTextConfig)


# --------------------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------------------


class NrcTextClient:
    """A paced, retrying, robots.txt-gated HTTP client.

    **Every request checks its host's robots.txt before it is made, not after the
    fact.** Two queries against ``openenergyhub.ornl.gov``'s ``/api/`` path -- one in
    the original M2a reconnaissance, one in the 2026-09-13 correction of it -- went out
    before anyone had read that this project's user agent falls under a ``Disallow:
    /api/`` rule (ADR-0016). This client exists so that mistake has to be structural to
    happen again: the policy is fetched and parsed once per host, cached, and consulted
    before the transport layer ever sees the URL. A disallowed path returns ``None``
    with a logged reason and is never requested.

    Attributes:
        session: Underlying requests session carrying the project identification.
        min_interval: Minimum seconds enforced between requests.
    """

    def __init__(
        self,
        min_interval: float = MIN_REQUEST_INTERVAL,
        retries: int = 4,
        session: requests.Session | None = None,
    ) -> None:
        """Create the client.

        Args:
            min_interval: Minimum seconds between requests.
            retries: Retries for transient transport failures (429/500/502/503/504).
                A ``403`` is not in this list: on nrc.gov it was observed to be both a
                transient rate-limit response (which the pacing below prevents) and,
                on the ADAMS ``/docs/`` path, a structural block this module must not
                work around (see the module docstring). Either way, retrying it
                blindly risks looking like exactly the burst that caused it.
            session: An injected session, for tests that must observe (or forbid)
                exactly which URLs reach the transport layer. A real session, with the
                retry policy below mounted, when omitted.
        """
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        if session is None:
            policy = Retry(
                total=retries,
                connect=retries,
                read=retries,
                status=retries,
                backoff_factor=2.0,
                backoff_max=120.0,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET", "HEAD"}),
                respect_retry_after_header=True,
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=policy)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)
        self.min_interval = min_interval
        self._last_request = 0.0
        self._robots: dict[str, RobotsPolicy] = {}

    def _pace(self, interval: float) -> None:
        """Sleep until ``interval`` seconds have passed since the last request."""
        wait = interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _robots_for(self, url: str) -> RobotsPolicy:
        """Fetch and parse one host's robots.txt, once, caching the result.

        Follows the convention :mod:`urllib.robotparser`'s ``read()`` uses for an
        unreadable file, through this client's own paced session: a ``401``/``403`` on
        robots.txt itself means "assume the whole host is closed", anything else
        unreadable (a ``404``, a connection failure) means "no policy was stated,
        assume open" -- the standard reading of an absent robots.txt, not this
        project's own invention. Parsing is :class:`~faultline.download.robots.RobotsPolicy`,
        not the stdlib parser, which silently drops rules on files this project
        actually reads (see that module's docstring).

        Args:
            url: A URL on the host whose policy is needed.

        Returns:
            The parsed policy for that host.
        """
        host = urlsplit(url)
        key = f"{host.scheme}://{host.netloc}"
        if key in self._robots:
            return self._robots[key]
        robots_url = f"{key}/robots.txt"
        self._pace(self.min_interval)
        try:
            response = self.session.get(robots_url, timeout=40)
        except requests.RequestException:
            policy = RobotsPolicy(allow_all=True)
        else:
            if response.status_code == 200:
                policy = RobotsPolicy.parse(response.text, host.netloc)
            elif response.status_code in (401, 403):
                policy = RobotsPolicy(disallow_all=True)
            else:
                policy = RobotsPolicy(allow_all=True)
        self._robots[key] = policy
        return policy

    def get(self, url: str, timeout: int = 40) -> requests.Response | None:
        """Fetch a URL, enforcing the minimum interval, tolerating one failure.

        The interval is the longer of this client's own ``min_interval`` and the
        host's stated ``Crawl-delay`` for this user agent.

        Args:
            url: URL to fetch.
            timeout: Per-request timeout in seconds.

        Returns:
            The response if it came back ``200``, otherwise ``None`` (logged). Also
            ``None``, and never sent, if the host's robots.txt disallows this path for
            this project's user agent.
        """
        robots = self._robots_for(url)
        if not robots.can_fetch(USER_AGENT, url):
            logger.warning("%s: disallowed by robots.txt for this user agent; not requested", url)
            return None
        self._pace(max(self.min_interval, robots.crawl_delay(USER_AGENT) or 0.0))
        try:
            response = self.session.get(url, timeout=timeout)
        except requests.RequestException as exc:
            logger.warning("%s: request failed: %s", url, exc)
            return None
        if response.status_code != 200:
            logger.warning("%s: HTTP %d, skipping", url, response.status_code)
            return None
        return response


# --------------------------------------------------------------------------------------
# event notification reports
# --------------------------------------------------------------------------------------


def event_notification_day_urls(
    client: NrcTextClient, spec: EventNotificationsSpec
) -> list[tuple[int, str]]:
    """Enumerate every report-day URL the collection publishes.

    Args:
        client: HTTP client.
        spec: Source specification.

    Returns:
        ``(year, url)`` pairs, in year order.
    """
    day_pattern = re.compile(r'href="([^"]*/((?:19|20)\d\d)/(\d{8})en)"')
    urls: list[tuple[int, str]] = []
    for year in range(spec.year_start, spec.year_end + 1):
        index_url = f"{spec.base_url}/{year}/index"
        response = client.get(index_url)
        if response is None:
            continue
        seen: set[str] = set()
        for href, _year, _ymd in day_pattern.findall(response.text):
            target = href if href.startswith("http") else f"https://www.nrc.gov{href}"
            if target not in seen:
                seen.add(target)
                urls.append((year, target))
    return urls


def _extract_events_modern(html_text: str, day_id: str, day_url: str) -> list[FetchedDocument]:
    """Extract events from the current (2024-onward, and 2026) USWDS template.

    ``<div class="grid border" id="enNNNNN">`` per event, ``<b>Event Text</b>``
    followed by ``<div class="border">`` for the narrative.

    Args:
        html_text: The page's HTML.
        day_id: The report day's identifier, for the document id.
        day_url: URL the page came from, for the citation.

    Returns:
        One document per event block that carries non-empty event text.
    """
    documents = []
    for event_number, block in _EVENT_BLOCK.findall(html_text):
        match = _EVENT_TEXT.search(block)
        if match is None:
            continue
        text = strip_html(match.group(1))
        if text:
            documents.append(
                FetchedDocument(
                    doc_id=f"{day_id}_{event_number}", url=f"{day_url}#{event_number}", text=text
                )
            )
    return documents


_MIDERA_BLOCK = re.compile(r'<a name="(en\d+)"></a>(.*?)(?=<a name="en\d+"></a>|\Z)', re.S)
_MIDERA_EVENT_TEXT = re.compile(
    # This collection's own markup is not consistent year to year -- measured
    # 2026-09-13 across three genuinely different pages: 2018 has no space around
    # the "Event Text" heading and a class on <table>; 2017 has a space on each
    # side of the heading and no class; 2019 has neither space nor class; 2020 adds
    # a scope="row" attribute to <td> that none of the others carry. A regex exact
    # enough to match one missed the rest silently -- the page fetched fine (200
    # OK), so nothing about extract_events finding zero events for that day looked
    # like a failure. Rather than enumerate every attribute combination as it turns
    # up, every tag below tolerates arbitrary attributes ([^>]*) and every boundary
    # tolerates arbitrary whitespace (\s*); only the tag names and the nesting are
    # load-bearing.
    r"<p[^>]*>\s*<b[^>]*>Event Text</b>\s*</p>\s*<table[^>]*>\s*"
    r"<tbody[^>]*>\s*<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*</tr>\s*"
    r"</tbody>\s*</table>",
    re.S,
)


def _extract_events_midera(html_text: str, day_id: str, day_url: str) -> list[FetchedDocument]:
    """Extract events from the 2010s table-based template.

    ``<a name="enNNNNN"></a>`` per event, no ``id`` attribute to anchor on; ``<p><b>Event
    Text</b></p>`` followed by a ``<table class="table">`` holding the narrative in one
    cell.

    Args:
        html_text: The page's HTML.
        day_id: The report day's identifier, for the document id.
        day_url: URL the page came from, for the citation.

    Returns:
        One document per event block that carries non-empty event text.
    """
    documents = []
    for event_number, block in _MIDERA_BLOCK.findall(html_text):
        match = _MIDERA_EVENT_TEXT.search(block)
        if match is None:
            continue
        text = strip_html(match.group(1))
        if text:
            documents.append(
                FetchedDocument(
                    doc_id=f"{day_id}_{event_number}", url=f"{day_url}#{event_number}", text=text
                )
            )
    return documents


_LEGACY_PRE = re.compile(r"<pre>(.*?)</pre>", re.S)
_LEGACY_BOX_LINE = re.compile(r"^\+-+\+[ \t]*$", re.M)
_LEGACY_EVENT_NUMBER = re.compile(r"Event Number:\s*(\d+)", re.I)
_LEGACY_EVENT_TEXT_HEADING = re.compile(r"^\s*EVENT TEXT\s*$", re.M)


def _extract_events_legacy(html_text: str, day_id: str, day_url: str) -> list[FetchedDocument]:
    """Extract events from the pre-2017-ish plain-text template.

    The whole report is one ``<pre>`` block: a fixed-width ASCII layout, box-drawn
    with ``+---+`` lines, each event's metadata followed by an ``EVENT TEXT`` heading
    and a boxed narrative. There is no per-event anchor to key off; the nearest
    preceding ``Event Number:`` is used instead.

    Args:
        html_text: The page's HTML.
        day_id: The report day's identifier, for the document id.
        day_url: URL the page came from, for the citation.

    Returns:
        One document per ``EVENT TEXT`` section that carries non-empty text.
    """
    pre_match = _LEGACY_PRE.search(html_text)
    if pre_match is None:
        return []
    pre_text = html.unescape(pre_match.group(1))
    numbers = [(m.start(), m.group(1)) for m in _LEGACY_EVENT_NUMBER.finditer(pre_text)]
    documents = []
    for heading in _LEGACY_EVENT_TEXT_HEADING.finditer(pre_text):
        event_number = None
        for pos, number in numbers:
            if pos < heading.start():
                event_number = number
            else:
                break
        after = pre_text[heading.end() :]
        box_lines = list(_LEGACY_BOX_LINE.finditer(after))
        if not box_lines:
            continue
        start = box_lines[0].end()
        end = box_lines[1].start() if len(box_lines) > 1 else len(after)
        lines = []
        for raw_line in after[start:end].split("\n"):
            line = raw_line.strip()
            line = line.removeprefix("|").removesuffix("|")
            lines.append(line.rstrip())
        text = "\n".join(lines).strip()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        if text and event_number is not None:
            documents.append(
                FetchedDocument(
                    doc_id=f"{day_id}_en{event_number}",
                    url=f"{day_url}#en{event_number}",
                    text=text,
                )
            )
    return documents


def extract_events(html_text: str, day_url: str) -> list[FetchedDocument]:
    """Pull every dated event out of one report-day page.

    A report day can name several unrelated events; each is its own document, because
    they are independent narratives about independent occurrences. The collection
    spans three HTML templates over 1999-2026 -- a fixed-width ``<pre>`` layout, a
    2010s table-based layout, and the current USWDS layout (measured while staging,
    not assumed from the date alone: the transition years are not a clean cutover, so
    every page tries the current template first, then the two earlier ones, and keeps
    whichever one actually matches).

    Args:
        html_text: The page's HTML.
        day_url: URL the page came from, for the document id and citation.

    Returns:
        One document per event block that carries non-empty event text, from whichever
        template the page turns out to use; each carries that template's name as
        ``template_era``, the actual extractor that produced it rather than a guess
        from the page's markup alone.
    """
    day_id = day_url.rstrip("/").rsplit("/", 1)[-1]
    for era, extractor in (
        ("modern", _extract_events_modern),
        ("midera", _extract_events_midera),
        ("legacy", _extract_events_legacy),
    ):
        documents = extractor(html_text, day_id, day_url)
        if documents:
            return [replace(document, template_era=era) for document in documents]
    return []


_MODERN_MARKER = re.compile(r'<div class="grid border"')
_MIDERA_MARKER = re.compile(r'<a name="en\d+"></a>')
_LEGACY_MARKER = re.compile(r"<pre>")

TemplateEra = Literal["modern", "midera", "legacy", "unrecognised"]


def template_of(html_text: str) -> TemplateEra:
    """Identify which of the three report-day templates a page uses.

    Independent of :func:`extract_events`: this looks for each template's own
    structural marker rather than trying to extract text, so it still names a page's
    era when that day happens to report zero events (a legitimate ``EVENT TEXT``-free
    day is not "unrecognised"). Checked in the same precedence order extraction
    uses, since a page can carry more than one marker (the modern template's block
    still contains an ``<a name=`` from residual markup on some captured pages).

    Args:
        html_text: The page's HTML.

    Returns:
        Which era the page's markup belongs to, or ``"unrecognised"`` if none of the
        three markers appear at all.
    """
    if _MODERN_MARKER.search(html_text):
        return "modern"
    if _MIDERA_MARKER.search(html_text):
        return "midera"
    if _LEGACY_MARKER.search(html_text):
        return "legacy"
    return "unrecognised"


def fetch_event_notifications(
    client: NrcTextClient, spec: EventNotificationsSpec
) -> Iterator[FetchedDocument]:
    """Stage every event this collection publishes.

    A generator, not a list: a full run crawls thousands of report days over several
    hours, and yielding lets the caller stage each document as it arrives rather than
    holding everything in memory until the last page answers.

    Args:
        client: HTTP client.
        spec: Source specification.

    Yields:
        Every extracted event, across every report day.
    """
    day_urls = event_notification_day_urls(client, spec)
    logger.info("event notifications: %d report days to fetch", len(day_urls))
    for index, (_year, url) in enumerate(day_urls):
        if index and index % 100 == 0:
            logger.info("event notifications: %d/%d report days fetched", index, len(day_urls))
        response = client.get(url)
        if response is None:
            continue
        yield from extract_events(response.text, url)


# --------------------------------------------------------------------------------------
# generic communications
# --------------------------------------------------------------------------------------


def generic_comm_year_urls(client: NrcTextClient, spec: GenericCommSpec) -> list[str]:
    """Enumerate the collection's year-index pages.

    Args:
        client: HTTP client.
        spec: Source specification.

    Returns:
        Year-page URLs found on the collection's top index.
    """
    response = client.get(spec.index_url)
    if response is None:
        return []
    found = sorted({href for href, _year in _YEAR_LINK.findall(response.text)})
    urls = []
    for href in found:
        urls.append(href if href.startswith("http") else f"https://www.nrc.gov{href}")
    return urls


def filter_native_document_links(html_text: str) -> list[str]:
    """Pick out the document links on a year page that are native HTML, not a PDF.

    A ``/docs/*.pdf`` link is an ADAMS accession; this module does not follow it (see
    the module docstring). **A link is excluded by its file extension, not by which
    path it sits under** -- measured 2026-09-13, after ``/docs/``-only filtering
    silently mis-scored Regulatory Issue Summaries' 2003-onward documents as native:
    those are ``.pdf`` files served from ``/sites/default/files/doc_library/...``, an
    entirely different path than ADAMS, so a check that only excluded ``/docs/``
    counted them as native HTML and every one of them then failed extraction
    silently (200 OK, no ``field--name-field-body`` to find, no warning logged --
    the failure mode a bare "did the request succeed" check cannot see). Any link
    ending in ``.pdf``, wherever it is hosted, is excluded here; everything else
    pointing at a same-collection document page is native HTML and is kept. Pure and
    network-free, so it is testable directly against a captured page.

    Args:
        html_text: One collection year's index page.

    Returns:
        Absolute document URLs, native HTML only, deduplicated.
    """
    kept = []
    for href in _DOC_LINK.findall(html_text):
        if "index" in href or href.lower().endswith(".pdf"):
            continue
        if not re.search(r"/(19|20)\d\d/[a-zA-Z0-9_.-]+$", href):
            continue
        kept.append(href if href.startswith("http") else f"https://www.nrc.gov{href}")
    return sorted(set(kept))


def html_native_document_urls(client: NrcTextClient, year_url: str) -> list[str]:
    """List the documents on one year page that stay on ``nrc.gov`` outside ``/docs/``.

    Args:
        client: HTTP client.
        year_url: One collection year's index page.

    Returns:
        Document URLs, native HTML only.
    """
    response = client.get(year_url)
    if response is None:
        return []
    return filter_native_document_links(response.text)


def extract_generic_comm_document(html_text: str, url: str) -> FetchedDocument | None:
    """Pull the body text out of one generic-communication document page.

    Args:
        html_text: The page's HTML.
        url: URL the page came from.

    Returns:
        The document, or ``None`` if the page carries no recognisable body.
    """
    match = _BODY_FIELD.search(html_text)
    if match is None:
        return None
    text = strip_html(match.group(1))
    if not text:
        return None
    title_match = _TITLE.search(html_text)
    title = strip_html(title_match.group(1)) if title_match else ""
    doc_id = url.rstrip("/").rsplit("/", 1)[-1]
    return FetchedDocument(doc_id=doc_id, url=url, text=text, title=title)


def fetch_generic_comm(client: NrcTextClient, spec: GenericCommSpec) -> Iterator[FetchedDocument]:
    """Stage every native-HTML document in one generic-communications collection.

    A generator, for the same reason :func:`fetch_event_notifications` is one.

    Args:
        client: HTTP client.
        spec: Source specification.

    Yields:
        Every extracted document.
    """
    year_urls = generic_comm_year_urls(client, spec)
    logger.info("%s: %d year pages to fetch", spec.label, len(year_urls))
    fetched = 0
    for year_url in year_urls:
        for doc_url in html_native_document_urls(client, year_url):
            response = client.get(doc_url)
            if response is None:
                continue
            document = extract_generic_comm_document(response.text, doc_url)
            if document is not None:
                fetched += 1
                if fetched % 50 == 0:
                    logger.info("%s: %d documents fetched so far", spec.label, fetched)
                yield document


# --------------------------------------------------------------------------------------
# staging
# --------------------------------------------------------------------------------------


def build_status_code_book(spec: CodeBookSpec, paths: ProjectPaths) -> list[FetchedDocument]:
    """Pool the distinct status-message strings out of the staged telemetry sources.

    Not a network fetch: this reads the raw archives already staged for M1 through
    the same profiling functions ``faultline inspect telemetry`` uses, so the code
    book is exactly the distinct strings the M0/M1 dataset cards already measured (217
    Kelmarsh, 231 Penmanshiel; a union of 264 once the two overlap). One message
    string is one document, not the whole book concatenated, so a token count and a
    length can be reported per string (ADR-0007 readiness).

    Args:
        spec: The code book's source specification.
        paths: Resolved project paths.

    Returns:
        One document per distinct message string, pooled across the configured
        telemetry sources and sorted for a deterministic id assignment.
    """
    from collections import Counter

    from faultline.data.telemetry.adapters import get_adapter
    from faultline.data.telemetry.inspect import collect_event_evidence, inventory_members

    pooled: Counter[str] = Counter()
    for source in spec.telemetry_sources:
        adapter = get_adapter(source, paths.configs_dir)
        raw_dir = paths.source_dir("raw", "telemetry", source)
        members = inventory_members(adapter, raw_dir)
        evidence = collect_event_evidence(adapter, members, max_event_members=5000)
        for profile in evidence.profiles:
            pooled.update(profile.get("message_counts", Counter()))
    documents = []
    for index, message in enumerate(sorted(pooled)):
        documents.append(
            FetchedDocument(
                doc_id=f"msg_{index:04d}",
                url="telemetry:" + ",".join(spec.telemetry_sources),
                text=message,
            )
        )
    return documents


#: Documents between manifest flushes during a long crawl. Small enough that a
#: killed process loses at most this many documents' worth of manifest bookkeeping
#: (the raw .txt files themselves are written per document, not batched); large
#: enough that a multi-hour crawl is not dominated by rewriting the manifest file.
MANIFEST_FLUSH_EVERY = 25


def event_notification_shard_key(record: FileRecord) -> str:
    """Group an event-notification file record by its report year.

    Args:
        record: A file record whose ``filename`` is ``{YYYYMMDD}en_en{N}.txt``.

    Returns:
        The four-digit year, as a string (a valid shard-file stem).
    """
    return record.filename[:4]


def pipeline_type_shard_key(record: FileRecord) -> str:
    """Group an incident-narrative file record by its pipeline type.

    Args:
        record: A file record whose ``filename`` is ``{pipeline_type}_{report}.txt``.

    Returns:
        The pipeline-type key (a valid shard-file stem).
    """
    return record.filename.split("_", 1)[0]


def shard_key_for(source: str, spec: TextSourceSpec) -> Callable[[FileRecord], str] | None:
    """The manifest shard key a source needs, or ``None`` for a single-file manifest.

    Args:
        source: Source id.
        spec: The source's specification.

    Returns:
        The key function for a source whose record count outgrows one manifest file.
    """
    if source == "nrc_event_notifications":
        return event_notification_shard_key
    if isinstance(spec, SocrataAttachmentsSpec):
        return pipeline_type_shard_key
    return None


def stage_documents(
    source: str,
    spec: TextSourceSpec,
    documents: Iterator[FetchedDocument],
    paths: ProjectPaths,
    shard_key_of: Callable[[FileRecord], str] | None = None,
) -> SourceManifest:
    """Write documents to raw staging and update the source's manifest.

    A document already staged and hashed the same as before is left alone -- the
    resume half of the pattern ``download/zenodo.py`` establishes for large binary
    archives, applied here to many small text files instead of HTTP ranges. Documents
    are consumed from an iterator and written as they arrive, and the manifest is
    flushed every :data:`MANIFEST_FLUSH_EVERY` documents rather than only at the end,
    so an interrupted multi-hour crawl leaves a manifest that matches what actually
    reached disk.

    Args:
        source: Source id.
        spec: Source specification (for provider/licence metadata).
        documents: Documents to stage.
        paths: Resolved project paths.
        shard_key_of: When given, the manifest is written sharded (see
            :func:`~faultline.data.common.manifest.write_manifest_sharded`) instead
            of as one file -- only ``nrc_event_notifications`` needs this, the one
            source whose record count has twice outgrown a single indented JSON
            file's size limit.

    Returns:
        The updated manifest.
    """
    target_dir = paths.source_dir("raw", "text", source)
    manifest = load_manifest(paths.manifests_dir, source) or SourceManifest(
        source=source, provider=spec.provider, license=spec.license
    )
    known = manifest.by_filename()
    since_flush = 0

    def flush() -> None:
        manifest.generated_at = datetime.now(tz=UTC)
        if shard_key_of is not None:
            write_manifest_sharded(paths.manifests_dir, source, manifest, shard_key_of)
        else:
            write_manifest(manifest_path(paths.manifests_dir, source), manifest)

    for document in documents:
        filename = f"{document.doc_id}.txt"
        destination = target_dir / filename
        digest = None
        if destination.is_file():
            digest = hash_file(destination, "sha256")
        new_bytes = document.text.encode("utf-8")
        if (
            digest is None
            or known.get(filename) is None
            or destination.stat().st_size != len(new_bytes)
        ):
            destination.write_bytes(new_bytes)
            digest = hash_file(destination, "sha256")
        manifest.upsert(
            FileRecord(
                filename=filename,
                relative_path=f"raw/text/{source}/{filename}",
                size_bytes=destination.stat().st_size,
                sha256=digest,
                url=document.url,
                # license omitted: every document of one of these sources shares the
                # manifest's own license (unlike a Zenodo record, which can mix
                # licences across files), so it is not repeated per file
                retrieved_at=datetime.now(tz=UTC),
                verified=True,
                template_era=document.template_era or None,
            )
        )
        since_flush += 1
        if since_flush >= MANIFEST_FLUSH_EVERY:
            flush()
            since_flush = 0
    flush()
    return manifest


def fetch_source(
    source: str, spec: TextSourceSpec, client: NrcTextClient, paths: ProjectPaths
) -> Iterator[FetchedDocument]:
    """Dispatch to the right fetcher for one configured source.

    Args:
        source: Source id, for logging only.
        spec: The source's specification.
        client: HTTP client (unused for the code-book source, which reads local
            telemetry archives instead).
        paths: Resolved project paths.

    Yields:
        Every document the source yields.

    Raises:
        AssertionError: If a new ``kind`` is added to the config schema without a
            matching branch here -- caught at test time, not at the end of a run.
    """
    if isinstance(spec, EventNotificationsSpec):
        yield from fetch_event_notifications(client, spec)
    elif isinstance(spec, GenericCommSpec):
        yield from fetch_generic_comm(client, spec)
    elif isinstance(spec, CodeBookSpec):
        yield from build_status_code_book(spec, paths)
    elif isinstance(spec, SocrataAttachmentsSpec):
        # deferred: phmsa_manual imports this module's client at its own import time
        from faultline.data.text.phmsa_manual import fetch_incident_narratives

        yield from fetch_incident_narratives(client, spec, paths)
    else:  # pragma: no cover - exhaustiveness guard, not a reachable branch
        raise AssertionError(f"{source}: unhandled source kind {spec.kind!r}")


def assemble_corpus(paths: ProjectPaths, sources: list[str], corpus_name: str) -> Path:
    """Combine several sources' staged raw text into one JSON Lines corpus.

    The text pipeline (``faultline text run``) reads exactly one JSONL file per
    corpus; this is the step between per-source staging (many small text files, one
    manifest each) and that input. Every record carries ``source`` and ``doc_id``
    alongside ``text``, which survives cleaning (``CleanStage`` preserves extra
    fields) so a held-out split and a loss figure can be reported per source rather
    than pooled.

    Args:
        paths: Resolved project paths.
        sources: Source ids to combine, each already staged.
        corpus_name: Name of the assembled corpus; written to
            ``data/raw/text/<corpus_name>.jsonl``.

    Returns:
        The path written.

    Raises:
        FileNotFoundError: If a named source has no manifest yet.
    """
    import json

    destination = paths.stage_dir("raw", "text") / f"{corpus_name}.jsonl"
    count = 0
    with destination.open("w", encoding="utf-8") as handle:
        for source in sources:
            manifest = load_manifest(paths.manifests_dir, source)
            if manifest is None:
                path = manifest_path(paths.manifests_dir, source)
                raise FileNotFoundError(f"{source}: no manifest at {path}; stage it first")
            source_dir = paths.source_dir("raw", "text", source)
            for record in sorted(manifest.files, key=lambda item: item.filename):
                text = (source_dir / record.filename).read_text(encoding="utf-8")
                doc_id = record.filename.removesuffix(".txt")
                handle.write(
                    json.dumps(
                        {
                            "text": text,
                            "source": source,
                            "doc_id": doc_id,
                            "url": record.url,
                            "template_era": record.template_era,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                count += 1
    logger.info("assembled %d documents from %s into %s", count, sources, destination)
    return destination
