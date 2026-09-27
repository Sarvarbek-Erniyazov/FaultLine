"""The image's files: pins match uv.lock, and the Dockerfile keeps its promises (A5)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT = ROOT / "deployment"


def pins() -> dict[str, str]:
    out = {}
    for line in (DEPLOYMENT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            name, version = line.split("==")
            out[name.lower().replace("_", "-")] = version
    return out


def test_every_pin_is_uv_lock_s_version_where_the_lock_has_it() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked: dict[str, set[str]] = {}
    for package in lock["package"]:
        locked.setdefault(package["name"].lower(), set()).add(package["version"].split("+")[0])
    checked = 0
    for name, version in pins().items():
        if name in locked:
            assert version in locked[name], f"{name}=={version} is not uv.lock's {locked[name]}"
            checked += 1
    assert checked >= 20
    assert pins()["torch"] == "2.14.0"
    assert {"fastapi", "uvicorn", "starlette"} <= set(pins())


def test_the_dockerfile() -> None:
    text = (DEPLOYMENT / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM python:3\.12-slim$", text, re.M)
    assert "--index-url https://download.pytorch.org/whl/cpu torch==2.14.0" in text
    assert re.search(r"^USER faultline$", text, re.M)
    assert "HEALTHCHECK" in text and "/health" in text
    assert "${PORT:-8000}" in text
    assert "COPY checkpoints/model.pt" in text and "COPY lesson11/demo/" in text


def test_the_context_is_an_allow_list() -> None:
    lines = [
        line.strip()
        for line in (DEPLOYMENT / "Dockerfile.dockerignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert lines[0] == "*"
    assert set(lines) >= {
        "!src/",
        "!inference/",
        "!evaluation/",
        "!deployment/",
        "!checkpoints/model.pt",
        "!data/tokenizers/quantile_bins_v2_9cd52b65.json",
        "!data/tokenizers/text_bpe_v1_22c56e49.json",
        "!lesson11/demo/",
    }


def test_the_env_example_holds_no_secret() -> None:
    text = (DEPLOYMENT / ".env.example").read_text(encoding="utf-8")
    assert "ALLOWED_ORIGINS=" in text
    assert not re.search(r"(?i)(secret|token|password|api_key)\s*=", text)
