"""Markdown report helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from faultline.config import RunMeta
from faultline.data.common.report import (
    counts_table,
    drop_reasons_table,
    header_block,
    kv_table,
    percentile_summary,
    section,
    table,
    top_values_table,
    truncate,
)


def meta() -> RunMeta:
    return RunMeta(
        run_id="20260909-120000_clean_text_abcd1234",
        config_path="configs/data/text_v0.yaml",
        config_hash="abcd1234",
        git_sha="0" * 40,
        created_at=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
    )


def test_header_block_carries_run_identity() -> None:
    rendered = header_block(meta(), "clean")
    assert rendered.startswith("# Clean stage report")
    for field in ("run_id", "config_hash", "git_sha", "created_at"):
        assert field in rendered


def test_kv_table_and_empty_case() -> None:
    rendered = kv_table({"documents": 1234, "ratio": 0.5, "flag": True})
    assert "| documents | 1,234 |" in rendered
    assert "| flag | yes |" in rendered
    assert "no entries" in kv_table({})


def test_table_and_empty_case() -> None:
    rendered = table(["a", "b"], [(1, 2), (3, 4)])
    assert rendered.splitlines()[0] == "| a | b |"
    assert "no rows" in table(["a"], [])


def test_counts_table_computes_deltas() -> None:
    rendered = counts_table([("clean", 100, 90)])
    assert "| clean | 100 | 90 | 10 | 90.00% |" in rendered
    assert "n/a" in counts_table([("empty", 0, 0)])


def test_drop_reasons_sorted_by_count() -> None:
    rendered = drop_reasons_table({"min_chars": 5, "alpha_ratio": 12}, total=100)
    lines = rendered.splitlines()
    assert "alpha_ratio" in lines[2]
    assert "min_chars" in lines[3]


def test_percentile_summary_reports_the_spread() -> None:
    rendered = percentile_summary(np.arange(1, 101), "length")
    for label in ("count", "mean", "p1", "p50", "p99", "max"):
        assert label in rendered


def test_percentile_summary_ignores_non_finite_values() -> None:
    rendered = percentile_summary([1.0, np.nan, np.inf, 3.0], "x")
    assert "| count | 2 |" in rendered


def test_percentile_summary_with_nothing_finite() -> None:
    assert "no finite values" in percentile_summary([np.nan], "x")


def test_top_values_table() -> None:
    rendered = top_values_table({"a": 3, "b": 1}, n=1, label="message")
    assert "message" in rendered
    assert "| a | 3 | 75.00% |" in rendered


def test_truncate_flattens_and_escapes() -> None:
    assert truncate("a\nb", 10) == "a\\nb"
    assert truncate("a|b", 10) == "a\\|b"
    assert truncate("x" * 20, 10).endswith("…")
    assert len(truncate("x" * 20, 10)) == 10


def test_section_renders_a_heading() -> None:
    assert section("Title", "body").startswith("\n## Title")
    assert section("Title", "body", level=3).startswith("\n### Title")
