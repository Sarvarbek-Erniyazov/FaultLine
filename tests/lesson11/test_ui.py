"""The demo page: its endpoint paths are the app's, it renders with textContent only, banners."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

UI = Path(__file__).resolve().parents[2] / "ui" / "index.html"
# Imported by name: ``deployment`` shares its name with tests/deployment (the ruff clash).
app_module = importlib.import_module("deployment.app")


def page() -> str:
    return UI.read_text(encoding="utf-8")


def called_paths(text: str) -> set[str]:
    """Every path the page passes to ``call(...)``, with ``+ id`` read as a path parameter."""
    paths = set()
    for match in re.finditer(r'call\("(/[^"?]*)"\s*(\+\s*encodeURIComponent)?', text):
        path = match.group(1)
        paths.add(path + "{window_id}" if match.group(2) else path)
    return paths


def test_every_endpoint_the_page_calls_is_the_app_s() -> None:
    app = app_module.create_app(
        app_module.Settings(Path("x"), Path("x"), Path("x"), [], "x"), loader=lambda _: None
    )
    routes = {getattr(r, "path", "") for r in app.routes}
    called = called_paths(page())
    assert called == {
        "/health",
        "/schema",
        "/demo/windows",
        "/demo/windows/{window_id}",
        "/predict",
        "/generate",
    }
    assert called <= routes


def test_rendering_uses_text_content_only() -> None:
    text = page()
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert sink not in text
    assert "textContent" in text


def test_the_banner_and_the_api_override() -> None:
    text = page()
    assert (
        "Held-out 2023 Kelmarsh windows. The model does not beat time since the last fault "
        "(ADR-0029). Scores are rankings, not calibrated probabilities."
    ) in text
    assert (
        "Demo set is enriched: 100 of 300 windows are positive, and 73 of those are "
        "anemometer-defect events (not positive under the ADR-0009 variant)."
    ) in text
    assert 'const DEFAULT_API = "http://localhost:8000";' in text
    assert '.get("api")' in text
    # Reveal lists the variant first.
    assert text.index('"ADR-0009 variant') < text.index('"Registered (narrow_within_24h)"')
