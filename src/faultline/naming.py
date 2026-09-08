"""Naming discipline scanner (ADR-0002).

FaultLine must be, and must read as, independent of the author's funded and
doctoral work. A handful of strings carry that other identity, so they are banned
from the repository outright and the ban is mechanically checked rather than
remembered.

The scan covers git-tracked text files only, so it cannot be defeated by an
untracked scratch file and cannot be slowed down by a staged corpus.
``docs/DECISIONS.md`` is the single exemption: ADR-0002 has to spell the words out
in order to define the rule.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# The scanner cannot spell the strings it bans, or it would fail its own check and
# would have to exempt itself -- which is exactly the loophole the rule exists to
# close. They are stored reversed and flipped at import time. Only
# ``docs/DECISIONS.md`` writes them out, because ADR-0002 has to state the rule.
_REVERSED_FORBIDDEN: tuple[str, ...] = ("tolipoc", "ppv", "tnalp rewop lautriv", "tnega")

#: Strings that must not appear anywhere in the repository, case-insensitive.
FORBIDDEN: tuple[str, ...] = tuple(term[::-1] for term in _REVERSED_FORBIDDEN)

#: Files exempt from the scan, repository-relative POSIX paths.
EXEMPT_FILES: frozenset[str] = frozenset({"docs/DECISIONS.md"})

#: The one permitted context for the last forbidden string: the HTTP header name,
#: and the Python constant that carries it.
_ALLOWED_CONTEXT = re.compile(rf"user[-_ ]?{FORBIDDEN[-1]}", re.IGNORECASE)

#: Directories never scanned when falling back to a working-tree walk.
SKIPPED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "__pycache__",
        "htmlcov",
        "node_modules",
        "checkpoints",
        "raw",
        "cleaned",
        "filtered",
        "final",
        "_reference",
    }
)

#: Extensions treated as text; everything else is skipped as binary.
TEXT_SUFFIXES: frozenset[str] = frozenset(
    {
        "",
        ".cff",
        ".cfg",
        ".csv",
        ".in",
        ".ini",
        ".ipynb",
        ".json",
        ".jsonl",
        ".md",
        ".py",
        ".pyi",
        ".rst",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)


@dataclass(frozen=True)
class Violation:
    """One forbidden string found in a tracked file.

    Attributes:
        path: Repository-relative path.
        line_no: 1-based line number.
        term: The forbidden string that matched.
        line: The offending line, stripped.
    """

    path: str
    line_no: int
    term: str
    line: str

    def __str__(self) -> str:
        """Render the violation as a single reviewable line."""
        return f"{self.path}:{self.line_no}: {self.term!r} in {self.line[:120]!r}"


def tracked_files(repo_root: Path) -> list[str]:
    """List the repository's git-tracked files.

    Args:
        repo_root: Repository root.

    Returns:
        Repository-relative POSIX paths, empty outside a git checkout.
    """
    try:
        completed = subprocess.run(
            ["git", "ls-files"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def scan_text(text: str, path: str = "<memory>") -> list[Violation]:
    """Scan one document for forbidden strings.

    The permitted context (the HTTP header name) is removed before matching, so a
    legitimate header does not trip the scan while any other use still does.

    Args:
        text: Document contents.
        path: Path reported in violations.

    Returns:
        One violation per offending line and term.
    """
    violations: list[Violation] = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        masked = _ALLOWED_CONTEXT.sub("", raw_line).lower()
        for term in FORBIDDEN:
            if term in masked:
                violations.append(
                    Violation(path=path, line_no=line_no, term=term, line=raw_line.strip())
                )
    return violations


def walked_files(repo_root: Path) -> list[str]:
    """List candidate text files by walking the working tree.

    Used when ``git ls-files`` returns nothing: before the first commit, or in an
    exported copy with no git metadata. Directories that never belong in the scan --
    the environment, the data stages, the reference notebook, caches -- are skipped.

    Args:
        repo_root: Repository root.

    Returns:
        Repository-relative POSIX paths.
    """
    found: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(repo_root)
        if any(part in SKIPPED_DIRECTORIES for part in relative.parts[:-1]):
            continue
        found.append(relative.as_posix())
    return sorted(found)


def scannable_files(repo_root: Path) -> list[str]:
    """List the files the scan should cover.

    Args:
        repo_root: Repository root.

    Returns:
        Git-tracked files when git knows about any, otherwise a filtered walk.
    """
    return tracked_files(repo_root) or walked_files(repo_root)


def scan_repository(repo_root: Path, extra_exempt: frozenset[str] = frozenset()) -> list[Violation]:
    """Scan every tracked text file in the repository.

    Args:
        repo_root: Repository root.
        extra_exempt: Additional repository-relative paths to skip.

    Returns:
        Every violation found, in file order.
    """
    exempt = EXEMPT_FILES | extra_exempt
    violations: list[Violation] = []
    for relative in scannable_files(repo_root):
        if relative in exempt:
            continue
        path = repo_root / relative
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        violations.extend(scan_text(text, relative))
    return violations
