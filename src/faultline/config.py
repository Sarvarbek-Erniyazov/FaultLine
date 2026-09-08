"""Configuration loading, validation and hashing.

Every pipeline run is driven by exactly one YAML file. Unknown keys are a hard
error (``extra="forbid"``) so that a typo in a threshold name fails loudly instead
of silently falling back to a default. The 8-character configuration hash is
recorded in the run identifier and in every report, which is what makes a run
reproducible from the repository alone.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base model for all configuration objects: unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)


ConfigT = TypeVar("ConfigT", bound=StrictModel)


def load_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file into a plain dictionary.

    Args:
        path: Path to the YAML document.

    Returns:
        The parsed mapping.

    Raises:
        FileNotFoundError: If the file does not exist.
        TypeError: If the document's top level is not a mapping.
    """
    if not path.is_file():
        raise FileNotFoundError(f"config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle)
    if not isinstance(parsed, dict):
        raise TypeError(f"config root must be a mapping, got {type(parsed).__name__}: {path}")
    return parsed


def load_config(path: Path, model: type[ConfigT]) -> ConfigT:
    """Load and validate a YAML configuration into a pydantic model.

    Args:
        path: Path to the YAML document.
        model: Configuration model class to validate against.

    Returns:
        The validated configuration instance.
    """
    return model.model_validate(load_yaml(path))


def canonical_json(payload: Any) -> str:
    """Serialize a configuration to a stable JSON string.

    Keys are sorted and separators fixed so that the hash depends on content only,
    not on key order or formatting.

    Args:
        payload: A pydantic model, mapping, or any JSON-serializable object.

    Returns:
        The canonical JSON representation.
    """
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def config_hash(payload: Any, length: int = 8) -> str:
    """Compute the short content hash identifying a configuration.

    Args:
        payload: A pydantic model, mapping, or JSON-serializable object.
        length: Number of leading hex characters to keep.

    Returns:
        The first ``length`` hex characters of the SHA-256 of the canonical JSON.
    """
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return digest[:length]


def file_hash(path: Path, length: int = 8) -> str:
    """Compute the short SHA-256 of a file's raw bytes.

    Args:
        path: File to hash.
        length: Number of leading hex characters to keep.

    Returns:
        The first ``length`` hex characters of the file digest.
    """
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest[:length]


class RunMeta(StrictModel):
    """Immutable identity of a single pipeline run.

    Attributes:
        run_id: Timestamped identifier, unique per run.
        config_path: Path of the YAML that drove the run, relative to the repo root.
        config_hash: Short hash of the validated configuration.
        git_sha: Commit the code was at, or ``unknown`` outside a git checkout.
        created_at: UTC timestamp at which the run started.
    """

    run_id: str
    config_path: str
    config_hash: str
    git_sha: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
