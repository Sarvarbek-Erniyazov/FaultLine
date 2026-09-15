"""Text-source dataset cards: every field from the manifest, the corpus or the spec."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from faultline.data.common.manifest import FileRecord, SourceManifest, manifest_path, write_manifest
from faultline.data.text.cards import build_text_card
from faultline.download.nrc_text import CodeBookSpec, GenericCommSpec
from faultline.paths import ProjectPaths

CORPUS = "card_corpus"


@pytest.fixture
def text_config(tmp_path: Path) -> Path:
    path = tmp_path / "text_test.yaml"
    path.write_text(
        "text:\n"
        f"  io: {{corpus_name: {CORPUS}}}\n"
        "  final:\n"
        "    source_split_fractions:\n"
        "      nrc_bulletins: {train: 0.8, val: 0.1, test: 0.1}\n",
        encoding="utf-8",
    )
    return path


def _spec() -> GenericCommSpec:
    return GenericCommSpec(
        provider="U.S. Nuclear Regulatory Commission",
        license="public domain (17 U.S.C. 105)",
        attribution="NRC Bulletins",
        label="Bulletins",
        index_url="https://www.nrc.gov/bulletins",
        year_start=1971,
        year_end=2026,
        robots_basis="nothing disallowed",
    )


def _stage(paths: ProjectPaths) -> None:
    write_manifest(
        manifest_path(paths.manifests_dir, "nrc_bulletins"),
        SourceManifest(
            source="nrc_bulletins",
            provider="NRC",
            license="public domain",
            files=[
                FileRecord(
                    filename=f"b{i}.txt",
                    relative_path=f"raw/text/nrc_bulletins/b{i}.txt",
                    size_bytes=100,
                    sha256="0" * 64,
                    url="https://www.nrc.gov/b",
                    retrieved_at=datetime(2026, 9, 13, tzinfo=UTC),
                    verified=True,
                )
                for i in range(3)
            ],
        ),
    )
    final_dir = paths.stage_dir("final", "text") / CORPUS
    final_dir.mkdir(parents=True, exist_ok=True)
    rows = {
        "train": [("nrc_bulletins", "one bulletin about pump seals"), ("other", "not this one")],
        "val": [("nrc_bulletins", "a second bulletin about valves")],
    }
    for split, docs in rows.items():
        with (final_dir / f"{split}-00000.jsonl").open("w", encoding="utf-8") as handle:
            for source, text in docs:
                handle.write(json.dumps({"text": text, "source": source}) + "\n")


def test_card_reads_manifest_corpus_and_config(tmp_paths: ProjectPaths, text_config: Path) -> None:
    _stage(tmp_paths)
    card = build_text_card("nrc_bulletins", _spec(), tmp_paths, text_config).read_text(
        encoding="utf-8"
    )
    assert "| documents staged | 3 |" in card
    assert "| documents after the pipeline | 2 |" in card
    assert "| val | 10% | 1 | 5 |" in card
    assert "Free-text verdict: VERIFIED short written descriptions" in card
    assert "not this one" not in card
    assert "PDF" in card  # the route's exclusion is stated


def test_an_unstaged_source_is_unverified_not_blank(
    tmp_paths: ProjectPaths, text_config: Path
) -> None:
    card = build_text_card("nrc_bulletins", _spec(), tmp_paths, text_config).read_text(
        encoding="utf-8"
    )
    assert "UNVERIFIED - no manifest" in card
    assert "UNVERIFIED - no documents" in card


def test_the_code_book_is_refused(tmp_paths: ProjectPaths, text_config: Path) -> None:
    spec = CodeBookSpec(provider="p", license="l", attribution="a", telemetry_sources=["k"])
    with pytest.raises(ValueError, match="not a narrative source"):
        build_text_card("status_code_book", spec, tmp_paths, text_config)


def test_a_small_set_of_long_unique_documents_is_written_descriptions(
    tmp_paths: ProjectPaths, text_config: Path
) -> None:
    final_dir = tmp_paths.stage_dir("final", "text") / CORPUS
    final_dir.mkdir(parents=True, exist_ok=True)
    with (final_dir / "train-00000.jsonl").open("w", encoding="utf-8") as handle:
        for index in range(3):
            text = f"summary {index} " + "regulatory guidance on inspection " * 10
            handle.write(json.dumps({"text": text, "source": "nrc_bulletins"}) + "\n")
    card = build_text_card("nrc_bulletins", _spec(), tmp_paths, text_config).read_text(
        encoding="utf-8"
    )
    assert "Free-text verdict: VERIFIED written descriptions" in card
