"""Run identity, run directories and the run record."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from faultline.config import config_hash
from faultline.paths import ProjectPaths
from faultline.runs import git_sha, new_run_id, start_run


def test_run_id_shape() -> None:
    stamp = datetime(2026, 9, 9, 12, 30, 45, tzinfo=UTC)
    run_id = new_run_id("clean", "text", "abcd1234", now=stamp)
    assert run_id == "20260909-123045_clean_text_abcd1234"


def test_git_sha_is_a_string_or_unknown(repo_root) -> None:
    sha = git_sha(repo_root)
    assert sha == "unknown" or len(sha) == 40


def test_git_sha_outside_a_checkout(tmp_path) -> None:
    assert git_sha(tmp_path / "does-not-exist") == "unknown"


def test_run_context_copies_config_and_writes_record(tmp_paths: ProjectPaths, tmp_path) -> None:
    config_path = tmp_path / "cfg.yaml"
    config_path.write_text("a: 1\n", encoding="utf-8")
    payload = {"a": 1}

    with start_run(config_path, payload, "clean", "text", tmp_paths) as ctx:
        ctx.record_stage("clean", rows_in=10, rows_out=8, extra={"dropped_empty": 2})
        report = ctx.write_report("clean", "# report\n")
        run_dir = ctx.run_dir

    assert (run_dir / "cfg.yaml").read_text(encoding="utf-8") == "a: 1\n"
    assert report.is_file()
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert record["status"] == "ok"
    assert record["config_hash"] == config_hash(payload)
    assert record["stages"][0]["rows_in"] == 10
    assert record["stages"][0]["dropped"] == 2
    assert record["elapsed_seconds"] >= 0


def test_run_context_records_failure(tmp_paths: ProjectPaths, tmp_path) -> None:
    config_path = tmp_path / "cfg.yaml"
    config_path.write_text("a: 1\n", encoding="utf-8")

    with pytest.raises(ValueError):
        with start_run(config_path, {"a": 1}, "clean", "text", tmp_paths) as ctx:
            run_dir = ctx.run_dir
            raise ValueError("boom")

    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert record["status"] == "failed"
    assert "boom" in record["error"]
