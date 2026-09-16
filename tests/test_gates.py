"""The gate chain gates: a failing stage fails the chain, piped output or not (audit entry 10)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")


def _bash() -> str | None:
    """A POSIX bash, preferring Git's on Windows (System32's bash is WSL and sees other paths)."""
    if os.name == "nt":
        return str(GIT_BASH) if GIT_BASH.is_file() else None
    return shutil.which("bash")


def _run(repo_root: Path, stages: list[str]) -> subprocess.CompletedProcess[str]:
    bash = _bash()
    if bash is None:
        pytest.skip("no bash to run scripts/gates.sh with")
    env = {**os.environ, "FAULTLINE_GATE_STAGES": "\n".join(stages), "FAULTLINE_GATE_TAIL": "3"}
    return subprocess.run(
        [bash, "scripts/gates.sh"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_failing_stage_fails_the_chain_although_its_output_is_piped_to_tail(
    repo_root: Path,
) -> None:
    # `false` piped to tail is exactly the shape that let a failing pytest through (C0)
    result = _run(repo_root, ["echo one", "echo 'boom'; exit 1", "echo three"])
    assert result.returncode == 1
    assert "GATE FAILED: echo 'boom'; exit 1" in result.stdout


def test_every_stage_runs_so_one_run_shows_every_red_gate(repo_root: Path) -> None:
    result = _run(repo_root, ["exit 2", "echo reached", "exit 3"])
    assert result.returncode == 1
    assert "reached" in result.stdout
    assert "GATE FAILED: exit 2" in result.stdout
    assert "GATE FAILED: exit 3" in result.stdout


def test_a_failure_inside_a_stage_pipeline_is_not_masked(repo_root: Path) -> None:
    # the stage itself pipes: its own left-hand failure must still count
    result = _run(repo_root, ["(echo x; exit 1) | cat"])
    assert result.returncode == 1


def test_all_green_stages_pass(repo_root: Path) -> None:
    result = _run(repo_root, ["echo a", "true"])
    assert result.returncode == 0, result.stdout
    assert "ALL GATES PASSED" in result.stdout


def test_the_shipped_chain_names_all_four_gates_and_pipefail(repo_root: Path) -> None:
    script = (repo_root / "scripts" / "gates.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in script
    assert "bash -o pipefail -c" in script
    for gate in ("ruff check .", "mypy --strict src/", "pytest -q", "faultline check naming"):
        assert f'"{gate}"' in script
