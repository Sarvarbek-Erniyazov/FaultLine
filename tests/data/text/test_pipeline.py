"""End-to-end text pipeline over the committed synthetic fixture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultline.data.common.stage import run_pipeline
from faultline.data.text.pipeline import (
    STAGE_ORDER,
    TextLayout,
    assign_split,
    build_stages,
    load_text_config,
    read_jsonl,
    write_jsonl,
)
from faultline.paths import ProjectPaths
from faultline.runs import start_run

CONFIG = Path("configs/data/text_v0.yaml")


@pytest.fixture
def config_path(repo_root: Path) -> Path:
    return repo_root / CONFIG


@pytest.fixture
def fixture_corpus(fixtures_dir: Path) -> Path:
    return fixtures_dir / "text" / "sample.jsonl"


def test_shipped_config_loads(config_path: Path) -> None:
    config = load_text_config(config_path)
    # course defaults, preserved verbatim (docs/COURSE_PORT.md)
    assert config.filter.min_chars == 200
    assert config.filter.max_chars == 100_000
    assert config.filter.min_alpha_ratio == 0.30
    assert config.filter.max_repeated_line_ratio == 0.30
    # the one behavioural change (ADR-0005)
    assert config.pii.mask_digits is False
    assert config.pii.mask_emails is True


def test_jsonl_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "docs.jsonl"
    records = [{"id": str(index), "text": f"doc {index}"} for index in range(3)]
    assert write_jsonl(path, iter(records)) == 3
    assert list(read_jsonl(path)) == records


def test_read_jsonl_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        list(read_jsonl(tmp_path / "absent.jsonl"))


def test_fixture_corpus_is_well_formed(fixture_corpus: Path) -> None:
    records = list(read_jsonl(fixture_corpus))
    assert len(records) == 55
    assert all("text" in record for record in records)


def run_full_pipeline(
    config_path: Path, fixture_corpus: Path, paths: ProjectPaths
) -> tuple[list, Path]:
    config = load_text_config(config_path)
    config = config.model_copy(
        update={"io": config.io.model_copy(update={"input_path": str(fixture_corpus)})}
    )
    layout = TextLayout.build(config, paths)
    stages = build_stages(config, layout, "all")
    with start_run(config_path, config, "all", "text", paths) as ctx:
        results = run_pipeline(stages, ctx)
        run_dir = ctx.run_dir
    return results, run_dir


def test_pipeline_smoke(config_path: Path, fixture_corpus: Path, tmp_paths: ProjectPaths) -> None:
    results, run_dir = run_full_pipeline(config_path, fixture_corpus, tmp_paths)
    by_name = {result.name: result for result in results}
    assert list(by_name) == list(STAGE_ORDER)

    clean, filtered, dedup, pii, final = (by_name[name] for name in STAGE_ORDER)

    # 55 documents in; exactly one cleans to an empty string and is dropped
    assert clean.rows_in == 55
    assert clean.counters["empty_after_cleaning"] == 1
    assert clean.rows_out == 54

    # the fixture carries 5 short, 3 low-alpha and 3 repeated-line documents
    assert filtered.counters["min_chars"] == 5
    assert filtered.counters["alpha_ratio"] == 3
    assert filtered.counters["repeated_lines"] == 3
    assert filtered.rows_out == filtered.rows_in - 11

    # 5 exact duplicates, including one uppercased and one whitespace-padded
    assert dedup.counters["duplicate"] == 5
    assert dedup.rows_out == dedup.rows_in - 5

    # emails and phones masked; digits left alone (ADR-0005)
    assert pii.counters["email"] >= 3
    assert pii.counters["phone"] >= 2
    assert pii.counters["digits"] == 0
    assert pii.rows_in == pii.rows_out

    assert final.rows_out == final.rows_in
    assert sum(final.details["splits"].values()) == final.rows_out


def test_pipeline_writes_a_report_per_stage_and_a_run_record(
    config_path: Path, fixture_corpus: Path, tmp_paths: ProjectPaths
) -> None:
    _, run_dir = run_full_pipeline(config_path, fixture_corpus, tmp_paths)
    for stage in STAGE_ORDER:
        report = run_dir / f"{stage}_stats_report.md"
        assert report.is_file(), f"missing report for {stage}"
        text = report.read_text(encoding="utf-8")
        assert "config_hash" in text
        assert "git_sha" in text

    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert record["status"] == "ok"
    assert [stage["name"] for stage in record["stages"]] == list(STAGE_ORDER)
    assert (run_dir / "text_v0.yaml").is_file()
    assert (run_dir / "run.log").is_file()


def test_filter_report_samples_removed_documents(
    config_path: Path, fixture_corpus: Path, tmp_paths: ProjectPaths
) -> None:
    _, run_dir = run_full_pipeline(config_path, fixture_corpus, tmp_paths)
    report = (run_dir / "filter_stats_report.md").read_text(encoding="utf-8")
    assert "Sampled removed documents" in report
    # the reason label is carried into the sample so a threshold can be audited
    assert "[min_chars]" in report or "[alpha_ratio]" in report


def test_pii_stage_preserves_magnitudes(
    config_path: Path, fixture_corpus: Path, tmp_paths: ProjectPaths
) -> None:
    config = load_text_config(config_path)
    config = config.model_copy(
        update={"io": config.io.model_copy(update={"input_path": str(fixture_corpus)})}
    )
    layout = TextLayout.build(config, tmp_paths)
    with start_run(config_path, config, "all", "text", tmp_paths) as ctx:
        run_pipeline(build_stages(config, layout, "all"), ctx)

    body = layout.scrubbed.read_text(encoding="utf-8")
    assert "<EMAIL>" in body
    assert "9876543" in body  # a magnitude, deliberately not masked
    assert "example.org" not in body


def test_final_stage_splits_and_shards(
    config_path: Path, fixture_corpus: Path, tmp_paths: ProjectPaths
) -> None:
    results, _ = run_full_pipeline(config_path, fixture_corpus, tmp_paths)
    final = results[-1]
    shards = list(Path(final.details["directory"]).glob("*.jsonl"))
    assert shards
    assert sum(len(list(read_jsonl(shard))) for shard in shards) == final.rows_out


def test_split_assignment_is_deterministic_and_content_addressed() -> None:
    from faultline.data.text.pipeline import FinalConfig

    config = FinalConfig()
    assert assign_split("a document", config) == assign_split("a document", config)
    # a different seed can move a document, which is what makes the seed meaningful
    other = FinalConfig(split_seed=1)
    assignments = {assign_split(f"doc {index}", config) for index in range(200)}
    assert assignments <= {"train", "val", "test"}
    assert any(
        assign_split(f"doc {index}", config) != assign_split(f"doc {index}", other)
        for index in range(200)
    )


def test_unknown_stage_is_rejected(config_path: Path, tmp_paths: ProjectPaths) -> None:
    config = load_text_config(config_path)
    layout = TextLayout.build(config, tmp_paths)
    with pytest.raises(ValueError, match="unknown stage"):
        build_stages(config, layout, "polish")
