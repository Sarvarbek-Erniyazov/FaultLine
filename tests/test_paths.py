"""Path resolution and the FAULTLINE_DATA_ROOT override."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultline.paths import DATA_ROOT_ENV, STAGES, ProjectPaths, find_repo_root


def test_find_repo_root(repo_root: Path) -> None:
    assert (repo_root / "pyproject.toml").is_file()
    assert find_repo_root(repo_root / "src" / "faultline") == repo_root


def test_find_repo_root_raises_outside_a_project(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        find_repo_root(tmp_path)


def test_data_root_defaults_under_the_repo(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(DATA_ROOT_ENV, raising=False)
    resolved = ProjectPaths.resolve(repo_root=repo_root)
    assert resolved.data_root == (repo_root / "data").resolve()


def test_env_var_overrides_the_data_root(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path / "elsewhere"))
    resolved = ProjectPaths.resolve(repo_root=repo_root)
    assert resolved.data_root == (tmp_path / "elsewhere").resolve()


def test_blank_env_var_is_ignored(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATA_ROOT_ENV, "   ")
    resolved = ProjectPaths.resolve(repo_root=repo_root)
    assert resolved.data_root == (repo_root / "data").resolve()


def test_stage_dirs_are_created_on_demand(tmp_paths: ProjectPaths) -> None:
    for stage in STAGES:
        for modality in ("telemetry", "text", "paired"):
            directory = tmp_paths.stage_dir(stage, modality)
            assert directory.is_dir()
            assert directory.parts[-2:] == (stage, modality)


def test_source_and_report_dirs(tmp_paths: ProjectPaths) -> None:
    assert tmp_paths.source_dir("raw", "telemetry", "kelmarsh").is_dir()
    assert tmp_paths.manifests_dir.is_dir()
    assert tmp_paths.manifests_dir.parent == tmp_paths.cards_dir
    assert tmp_paths.run_dir("20260909-000000_clean_text_abcd1234").is_dir()
