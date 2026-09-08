"""Shared fixtures. Nothing here touches the network or any real corpus."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from faultline.paths import ProjectPaths, find_repo_root

REPO_ROOT = find_repo_root(Path(__file__).resolve())


@pytest.fixture
def repo_root() -> Path:
    """The real repository root."""
    return REPO_ROOT


@pytest.fixture
def fixtures_dir() -> Path:
    """The committed test fixture directory."""
    return REPO_ROOT / "tests" / "fixtures"


@pytest.fixture
def tmp_paths(tmp_path: Path) -> ProjectPaths:
    """Fully isolated paths: a temporary repo root and a temporary data root.

    Tests that write reports or stage data use this, so a test run never touches the
    real reports/ or data/ directories.
    """
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("# temporary repo root for tests\n", encoding="utf-8")
    return ProjectPaths.resolve(repo_root=root, data_root=tmp_path / "data")


@pytest.fixture
def repo_paths(tmp_path: Path) -> ProjectPaths:
    """Isolated paths with the real configs/ copied in.

    Tests that need the shipped configs (channel maps, the split spec) get them, but
    reports and data still land in a temporary directory. Pointing this at the real
    repository root would make a test run write into the tracked reports/ tree.
    """
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("# temporary repo root for tests\n", encoding="utf-8")
    shutil.copytree(REPO_ROOT / "configs", root / "configs")
    return ProjectPaths.resolve(repo_root=root, data_root=tmp_path / "data")
