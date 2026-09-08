"""Configuration loading, strictness and hashing."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from faultline.config import RunMeta, StrictModel, config_hash, load_config, load_yaml


class Sample(StrictModel):
    name: str
    threshold: float = 0.5
    tags: list[str] = []


def write(tmp_path: Path, payload: object, name: str = "cfg.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_load_config_validates(tmp_path: Path) -> None:
    path = write(tmp_path, {"name": "a", "threshold": 0.25})
    cfg = load_config(path, Sample)
    assert cfg.name == "a"
    assert cfg.threshold == 0.25


def test_unknown_keys_are_rejected(tmp_path: Path) -> None:
    # The whole point of extra="forbid": a mistyped threshold name must fail the run
    # rather than silently reverting to the default.
    path = write(tmp_path, {"name": "a", "treshold": 0.25})
    with pytest.raises(ValidationError):
        load_config(path, Sample)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_yaml(tmp_path / "absent.yaml")


def test_non_mapping_root_raises(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(TypeError):
        load_yaml(path)


def test_config_hash_is_stable_and_order_independent() -> None:
    first = Sample(name="a", threshold=0.25, tags=["x", "y"])
    second = Sample(name="a", threshold=0.25, tags=["x", "y"])
    assert config_hash(first) == config_hash(second)
    assert config_hash({"a": 1, "b": 2}) == config_hash({"b": 2, "a": 1})
    assert len(config_hash(first)) == 8


def test_config_hash_changes_with_content() -> None:
    assert config_hash(Sample(name="a")) != config_hash(Sample(name="b"))
    assert config_hash(Sample(name="a", threshold=0.5)) != config_hash(
        Sample(name="a", threshold=0.6)
    )


def test_run_meta_defaults_to_utc() -> None:
    meta = RunMeta(run_id="r", config_path="c.yaml", config_hash="abcd1234", git_sha="deadbeef")
    assert meta.created_at.tzinfo is not None
    assert meta.created_at.utcoffset() is not None
    assert meta.created_at.utcoffset().total_seconds() == 0
