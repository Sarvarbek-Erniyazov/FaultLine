"""A robots.txt policy parser that reads the files this project actually crawls.

:mod:`urllib.robotparser` was the first gate (ADR-0016) and is replaced here, because
three of its behaviours silently turn a stated ``Disallow`` into an allow, each
measured against a real, live file rather than assumed:

* **A blank line ends a group.** ``data.transportation.gov/robots.txt`` puts blank
  lines between ``User-agent: *``/``Crawl-delay: 1`` and every one of its ``Disallow``
  rules; the stdlib parser attaches none of them to any group and answers
  ``can_fetch`` ``True`` for ``/api/odata/x`` and ``/login``. RFC 9309 does not treat
  blank lines as group separators: a group ends where the next ``User-agent`` line
  follows a rule.
* **Full-URL values never match.** ``www.nrc.gov/robots.txt`` writes
  ``Disallow: https://www.nrc.gov/site-help/search``; the stdlib parser stores it as
  ``https%3A//www.nrc.gov/...`` and compares it against a path, so it matches nothing.
  RFC 9309 expects a path, but the publisher's intent is unambiguous, so a full-URL
  value naming *this* host is read as its path, and one naming any other host is
  dropped (it cannot describe a path here). This is this module's stated reading, not
  the RFC's.
* **No wildcards.** ``*`` and a trailing ``$`` are compared literally, so
  ``Disallow: /api/collocate*`` matches nothing longer than itself.

Matching follows RFC 9309 section 2.2.2: the longest matching pattern decides, an
``Allow`` wins a tie, a path no rule matches is allowed, and ``/robots.txt`` itself is
always allowed. A crawler's groups are those whose ``User-agent`` value equals its
product token (case-insensitive); only when none does are the ``*`` groups used, and
several groups naming the same agent are merged, as the RFC requires.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


@dataclass(frozen=True)
class Rule:
    """One ``Allow`` or ``Disallow`` line.

    Attributes:
        allow: ``True`` for ``Allow``, ``False`` for ``Disallow``.
        pattern: The path pattern, percent-decoded, possibly holding ``*`` and ``$``.
    """

    allow: bool
    pattern: str

    def matches(self, path: str) -> bool:
        """Whether this rule's pattern matches a percent-decoded path (and query).

        Args:
            path: The request path, with its query string if any.

        Returns:
            ``True`` when the pattern matches from the start of the path.
        """
        return _compile(self.pattern).match(path) is not None


def _compile(pattern: str) -> re.Pattern[str]:
    """Translate a robots.txt pattern (``*`` any run, trailing ``$`` end) to a regex."""
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(regex + ("$" if anchored else ""), re.S)


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    crawl_delay: float | None = None


@dataclass(frozen=True)
class RobotsPolicy:
    """A parsed robots.txt, answering whether one crawler may fetch one URL.

    Attributes:
        groups: ``(agents, rules, crawl_delay)`` per group, in file order.
        allow_all: The policy is "no rules at all" (no robots.txt was stated).
        disallow_all: The policy is "the whole host is closed" (robots.txt refused).
    """

    groups: tuple[tuple[tuple[str, ...], tuple[Rule, ...], float | None], ...] = ()
    allow_all: bool = False
    disallow_all: bool = False

    @classmethod
    def parse(cls, text: str, host: str) -> RobotsPolicy:
        """Parse a robots.txt body.

        Args:
            text: The file's text, any line endings.
            host: The ``netloc`` the file was served from, for reading full-URL values.

        Returns:
            The parsed policy.
        """
        groups: list[_Group] = []
        current: _Group | None = None
        in_rules = False
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if ":" not in line:
                continue  # blank, comment-only, or malformed: never a group boundary
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if current is None or in_rules:
                    current = _Group()
                    groups.append(current)
                    in_rules = False
                current.agents.append(value.lower())
            elif key in ("allow", "disallow"):
                if current is None:
                    continue  # a rule before any User-agent line belongs to no group
                in_rules = True
                pattern = _path_of(value, host)
                if pattern:  # an empty value states no rule
                    current.rules.append(Rule(allow=key == "allow", pattern=pattern))
            elif key == "crawl-delay" and current is not None:
                in_rules = True
                try:
                    current.crawl_delay = float(value)
                except ValueError:
                    pass
        return cls(
            groups=tuple(
                (tuple(group.agents), tuple(group.rules), group.crawl_delay) for group in groups
            )
        )

    def _groups_for(
        self, user_agent: str
    ) -> list[tuple[tuple[str, ...], tuple[Rule, ...], float | None]]:
        token = user_agent.split("/", 1)[0].strip().lower()
        named = [group for group in self.groups if token in group[0]]
        return named or [group for group in self.groups if "*" in group[0]]

    def can_fetch(self, user_agent: str, url: str) -> bool:
        """Whether ``user_agent`` may fetch ``url`` under this policy.

        Args:
            user_agent: The full User-Agent string; its product token (before ``/``)
                selects the group.
            url: The absolute URL to be requested.

        Returns:
            ``True`` when allowed.
        """
        if self.disallow_all:
            return False
        if self.allow_all:
            return True
        parts = urlsplit(url)
        path = unquote(parts.path or "/") + (f"?{unquote(parts.query)}" if parts.query else "")
        if path == "/robots.txt":
            return True
        best: Rule | None = None
        for _agents, rules, _delay in self._groups_for(user_agent):
            for rule in rules:
                if not rule.matches(path):
                    continue
                if (
                    best is None
                    or len(rule.pattern) > len(best.pattern)
                    or (len(rule.pattern) == len(best.pattern) and rule.allow)
                ):
                    best = rule
        return best is None or best.allow

    def crawl_delay(self, user_agent: str) -> float | None:
        """The largest ``Crawl-delay`` stated for this crawler's groups, if any.

        Args:
            user_agent: The full User-Agent string.

        Returns:
            Seconds, or ``None`` when no applicable group states one.
        """
        delays = [delay for _a, _r, delay in self._groups_for(user_agent) if delay is not None]
        return max(delays) if delays else None


def _path_of(value: str, host: str) -> str:
    """A rule value as a percent-decoded path pattern; ``""`` when it states none here.

    Args:
        value: The raw ``Allow``/``Disallow`` value.
        host: The ``netloc`` the robots.txt was served from.

    Returns:
        The path pattern, or ``""`` for an empty value or a full URL naming another host.
    """
    if "://" in value:
        parts = urlsplit(value)
        if parts.netloc.lower() != host.lower():
            return ""
        value = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return unquote(value)
