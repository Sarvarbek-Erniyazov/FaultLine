"""Exact document deduplication.

Ported from the course reference notebook (cells 27-28); see ``docs/COURSE_PORT.md``.
Documents are hashed after a light normalization (strip and lowercase, both course
defaults) so that whitespace-only and case-only differences collapse.

Near-duplicate detection (MinHash / LSH) is an M2 item: it matters for the operator
narrative corpus, where the same incident is often republished with small edits, and
it would be dead weight on today's fixtures. See ``dedup.strategy`` in the config.
"""

from __future__ import annotations

import hashlib

from faultline.config import StrictModel


class DedupConfig(StrictModel):
    """Deduplication settings.

    Attributes:
        strategy: ``exact`` is the only implemented strategy at M0. ``minhash`` is
            reserved for M2 and is rejected until it is implemented.
        lowercase: Lowercase the document before hashing.
        strip: Strip leading and trailing whitespace before hashing.
    """

    strategy: str = "exact"
    lowercase: bool = True
    strip: bool = True


def normalize_for_hash(text: str, config: DedupConfig | None = None) -> str:
    """Apply the pre-hash normalization.

    Args:
        text: Document to normalize.
        config: Deduplication settings; course defaults when omitted.

    Returns:
        The normalized string that gets hashed.
    """
    cfg = config or DedupConfig()
    if cfg.strip:
        text = text.strip()
    if cfg.lowercase:
        text = text.lower()
    return text


def document_hash(text: str, config: DedupConfig | None = None) -> str:
    """Compute the SHA-256 identity of a document.

    Args:
        text: Document to hash.
        config: Deduplication settings; course defaults when omitted.

    Returns:
        The hex digest of the normalized document.
    """
    normalized = normalize_for_hash(text, config)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ExactDeduplicator:
    """Streaming exact-duplicate detector.

    Only digests are retained, so memory grows with the number of unique documents
    rather than with corpus size.

    Attributes:
        config: The settings used for normalization and hashing.
        duplicates: Number of documents rejected so far.
    """

    def __init__(self, config: DedupConfig | None = None) -> None:
        """Initialize an empty detector.

        Args:
            config: Deduplication settings; course defaults when omitted.

        Raises:
            NotImplementedError: If a strategy other than ``exact`` is configured.
        """
        self.config = config or DedupConfig()
        if self.config.strategy != "exact":
            raise NotImplementedError(
                f"dedup.strategy={self.config.strategy!r} is not implemented; "
                "TODO(m2): MinHash/LSH near-duplicate removal"
            )
        self._seen: set[str] = set()
        self.duplicates = 0

    def __len__(self) -> int:
        """Return the number of unique documents accepted so far."""
        return len(self._seen)

    def accept(self, text: str) -> bool:
        """Test a document and remember it.

        Args:
            text: Candidate document.

        Returns:
            ``True`` if this is the first time the document is seen.
        """
        digest = document_hash(text, self.config)
        if digest in self._seen:
            self.duplicates += 1
            return False
        self._seen.add(digest)
        return True
