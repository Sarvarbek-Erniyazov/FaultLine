"""The status code book's readiness measurements and its card."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from faultline.data.text.code_book import (
    CodeBookMeasurement,
    every_token_frequent,
    every_word_frequent,
    groups,
    nearest_rank,
    render_code_book_card,
    site_membership,
    summarise_lengths,
    train_token_frequency,
    words,
)
from faultline.download.nrc_text import CodeBookSpec
from faultline.paths import ProjectPaths


def test_words_is_the_h3_rule() -> None:
    # Digits and punctuation separate words; case is folded.
    assert words("4-20mA anemometer 1") == ["ma", "anemometer"]
    assert words("Wind < start wind") == ["wind", "start", "wind"]
    assert words("Deviation winddirection > 60°") == ["deviation", "winddirection"]


def test_nearest_rank_returns_observed_values() -> None:
    values = [5, 1, 4, 2, 3]
    assert nearest_rank(values, 0.25) == 2
    assert nearest_rank(values, 0.50) == 3
    assert nearest_rank(values, 0.95) == 5
    assert nearest_rank([7], 0.25) == 7
    with pytest.raises(ValueError):
        nearest_rank([], 0.5)
    with pytest.raises(ValueError):
        nearest_rank([1], 0.0)


def test_summarise_lengths_reports_the_tail_not_only_the_mean() -> None:
    encoded = {"a": [1, 2], "b": [1, 2, 3], "c": [1] * 20}
    summary = summarise_lengths(["a", "b", "c"], encoded)
    assert (summary.minimum, summary.maximum) == (2, 20)
    assert summary.quantiles["median"] == 3
    assert summary.quantiles["p95"] == 20
    assert summary.histogram == [(2, 1), (3, 1), (20, 1)]
    assert summary.chars_per_token == pytest.approx(3 / 25)


def test_site_membership_matches_lowercased_stream_messages() -> None:
    book = ["System OK", "Wind < start wind", "Grid loss"]
    streams = {"k": ["system ok", "grid loss"], "p": ["system ok", "wind < start wind"]}
    assert site_membership(book, streams) == {
        "k": ["Grid loss", "System OK"],
        "p": ["System OK", "Wind < start wind"],
    }


def test_site_membership_refuses_a_silent_miss() -> None:
    with pytest.raises(ValueError, match="not in the code book"):
        site_membership(["System OK"], {"k": ["system ok", "unheard of"]})
    with pytest.raises(ValueError, match="collide"):
        site_membership(["System OK", "system ok"], {})


def test_groups_split_site_only_and_shared() -> None:
    grouped = groups({"k": ["a", "b"], "p": ["b", "c"]}, ["a", "b", "c"])
    assert grouped == {
        "pooled": ["a", "b", "c"],
        "k": ["a", "b"],
        "p": ["b", "c"],
        "k only": ["a"],
        "p only": ["c"],
        "shared": ["b"],
    }


def test_train_token_frequency_reads_training_shards_only_and_drops_sep(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"dtype": "uint16", "vocabulary_size": 5}), encoding="utf-8"
    )
    np.array([0, 1, 1, 4, 3], dtype=np.uint16).tofile(tmp_path / "a__train.bin")
    np.array([1, 4], dtype=np.uint16).tofile(tmp_path / "b__train.bin")
    np.array([2, 2, 2], dtype=np.uint16).tofile(tmp_path / "a__val.bin")
    counts = train_token_frequency(tmp_path, vocab_size=4)  # 4 is <sep>
    assert counts.tolist() == [1, 3, 0, 1]


def test_frequent_checks_are_inclusive_at_the_floor() -> None:
    frequency = np.array([100, 99, 250])
    assert every_token_frequent([0, 2], frequency, 100)
    assert not every_token_frequent([0, 1], frequency, 100)
    assert every_word_frequent("Grid loss", Counter({"grid": 100, "loss": 300}), 100)
    assert not every_word_frequent("Grid loss", Counter({"grid": 99, "loss": 300}), 100)


def test_card_labels_token_and_word_level_and_states_role(tmp_paths: ProjectPaths) -> None:
    lengths = {
        name: summarise_lengths(members, {"a": [1, 2], "b": [1, 2, 3], "c": [1]})
        for name, members in groups({"k": ["a", "b"], "p": ["b", "c"]}, ["a", "b", "c"]).items()
    }
    measurement = CodeBookMeasurement(
        strings=["a", "b", "c"],
        by_site={"k": ["a", "b"], "p": ["b", "c"]},
        lengths=lengths,
        token_frequent=dict.fromkeys(lengths, 1),
        word_frequent=dict.fromkeys(lengths, 1),
        word_types={"k": {"a", "b"}, "p": {"b", "c"}},
        tokenizer_file="tok.json",
        shard_dir="tok",
        corpus_name="corpus",
        train_tokens=10,
        rare_ids=3,
        vocab_size=4,
    )
    spec = CodeBookSpec(
        provider="Cubico", license="CC BY 4.0", attribution="Cubico", telemetry_sources=["k", "p"]
    )
    card = render_code_book_card(measurement, spec, tmp_paths, {"nrc": 4.7})
    assert "TOKEN-level" in card and "WORD-level" in card
    assert "not training data" in card
    assert "derived, not downloaded" in card
    assert "| p95 |" in card
