"""Filesystem layout for the repository and the four-stage data root.

The data root is configurable through the ``FAULTLINE_DATA_ROOT`` environment
variable so that bulk archives can live on a different drive from the code.
Every accessor creates the directory it returns, so callers never need ``mkdir``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

Stage = Literal["raw", "cleaned", "filtered", "final"]
Modality = Literal["telemetry", "text", "paired"]

STAGES: Final[tuple[Stage, ...]] = ("raw", "cleaned", "filtered", "final")
DATA_ROOT_ENV: Final[str] = "FAULTLINE_DATA_ROOT"


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the repository root by walking up to the directory holding ``pyproject.toml``.

    Args:
        start: Directory to start searching from. Defaults to this file's location.

    Returns:
        The repository root directory.

    Raises:
        RuntimeError: If no ``pyproject.toml`` is found in any parent directory.
    """
    here = (start or Path(__file__).resolve()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError(f"no pyproject.toml found above {here}")


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved locations of every directory the pipelines read or write.

    Attributes:
        repo_root: Repository root (the directory holding ``pyproject.toml``).
        data_root: Root of the four data stages, from ``FAULTLINE_DATA_ROOT``
            when set, otherwise ``<repo_root>/data``.
    """

    repo_root: Path
    data_root: Path

    @classmethod
    def resolve(cls, repo_root: Path | None = None, data_root: Path | None = None) -> ProjectPaths:
        """Build the path set from arguments, the environment, and repository layout.

        Args:
            repo_root: Explicit repository root; discovered when omitted.
            data_root: Explicit data root; taken from ``FAULTLINE_DATA_ROOT`` and
                then from ``<repo_root>/data`` when omitted.

        Returns:
            A resolved, frozen ``ProjectPaths``.
        """
        root = (repo_root or find_repo_root()).resolve()
        if data_root is not None:
            data = data_root
        else:
            env_value = os.environ.get(DATA_ROOT_ENV, "").strip()
            data = Path(env_value) if env_value else root / "data"
        return cls(repo_root=root, data_root=data.resolve())

    def _mk(self, path: Path) -> Path:
        """Create ``path`` (with parents) and return it."""
        path.mkdir(parents=True, exist_ok=True)
        return path

    def stage_dir(self, stage: Stage, modality: Modality) -> Path:
        """Return ``<data_root>/<stage>/<modality>``, creating it if needed.

        Args:
            stage: One of ``raw``, ``cleaned``, ``filtered``, ``final``.
            modality: One of ``telemetry``, ``text``, ``paired``.

        Returns:
            The stage directory for that modality.
        """
        return self._mk(self.data_root / stage / modality)

    def source_dir(self, stage: Stage, modality: Modality, source: str) -> Path:
        """Return the per-source subdirectory of a stage directory.

        Args:
            stage: Pipeline stage.
            modality: Data modality.
            source: Source identifier, e.g. ``kelmarsh``.

        Returns:
            The created ``<data_root>/<stage>/<modality>/<source>`` directory.
        """
        return self._mk(self.stage_dir(stage, modality) / source)

    @property
    def cards_dir(self) -> Path:
        """Directory holding tracked dataset cards."""
        return self._mk(self.repo_root / "data" / "cards")

    @property
    def manifests_dir(self) -> Path:
        """Directory holding tracked download manifests with checksums."""
        return self._mk(self.cards_dir / "manifests")

    @property
    def reports_dir(self) -> Path:
        """Root directory for tracked Markdown reports."""
        return self._mk(self.repo_root / "reports")

    @property
    def data_reports_dir(self) -> Path:
        """Directory holding per-run data pipeline reports."""
        return self._mk(self.reports_dir / "data")

    @property
    def configs_dir(self) -> Path:
        """Directory holding versioned run configurations."""
        return self.repo_root / "configs"

    def run_dir(self, run_id: str) -> Path:
        """Return (and create) the report directory for one run.

        Args:
            run_id: Identifier produced by :func:`faultline.runs.new_run_id`.

        Returns:
            The created ``reports/data/<run_id>`` directory.
        """
        return self._mk(self.data_reports_dir / run_id)
