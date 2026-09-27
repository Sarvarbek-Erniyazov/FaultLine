"""The Lesson 11 API on a tiny random model: load once, bounds, 422/404/500/503, bundle headline."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

# Imported by name: ``deployment`` (like ``evaluation``) shares its name with a folder under
# tests/, which the two pinned ruff versions sort differently.
app_module = importlib.import_module("deployment.app")
_spec = importlib.util.spec_from_file_location(
    "tiny_export", Path(__file__).with_name("tiny_export.py")
)
assert _spec is not None and _spec.loader is not None
tiny = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tiny)

END = "2023-06-01T12:00:00Z"


@pytest.fixture(scope="module")
def loaded(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, Path]:
    return tiny.load_tiny(tmp_path_factory.mktemp("tiny"))


def settings(bundle: Path) -> Any:
    return app_module.Settings(
        model_path=Path("unused"),
        tokenizer_dir=Path("unused"),
        bundle_path=bundle,
        allowed_origins=["http://localhost:8080"],
        git_sha="abc123",
    )


@pytest.fixture
def client(loaded: tuple[Any, Path]) -> Any:
    engine, bundle = loaded
    calls = []

    def loader(_: Any) -> Any:
        calls.append(1)
        return engine, app_module.read_bundle(bundle)

    app = app_module.create_app(settings(bundle), loader=loader)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        test_client.calls = calls  # type: ignore[attr-defined]
        yield test_client


def raw_body(**extra: Any) -> dict[str, Any]:
    values = np.random.default_rng(2).uniform(0, 10, (144, 12)).tolist()
    values[3][1] = None
    return {"values": values, "end_utc": END, **extra}


def test_health_and_load_once(client: Any) -> None:
    for _ in range(3):
        body = client.get("/health").json()
    assert body["model_loaded"] is True and body["git_sha"] == "abc123"
    assert set(body["sha256"]) >= {"model", "tokenizer_bins", "tokenizer_text", "bundle"}
    client.post("/generate", json={"prompt": "yaw", "max_new_tokens": 2})
    client.post("/predict", json={"window_id": "K4-20230601T1200"})
    assert client.calls == [1]


def test_503_until_loaded(loaded: tuple[Any, Path]) -> None:
    def broken(_: Any) -> Any:
        raise RuntimeError("no model")

    app = app_module.create_app(settings(loaded[1]), loader=broken)
    with TestClient(app) as c:
        assert c.get("/health").status_code == 503
        assert c.get("/health").json()["model_loaded"] is False
        assert c.post("/generate", json={"prompt": "x"}).status_code == 503
        assert c.post("/predict", json={"window_id": "K4-20230601T1200"}).status_code == 503


def test_bundle_window_headline_is_the_recorded_score(client: Any) -> None:
    body = client.post("/predict", json={"window_id": "K4-20230601T1200"}).json()
    assert body["headline"]["source"] == "as evaluated in the record"
    assert body["headline"]["score"] == pytest.approx(-4.29, abs=1e-6)
    assert body["headline"]["percentile"] == 61.0
    assert body["live"]["source"] == "recomputed live, CPU fp32"
    assert body["recorded"]["logit"] == pytest.approx(-0.5)
    assert body["hours_since_last_fault"] == 2.0
    assert body["hours_since_last_fault_percentile"] == 97.5
    assert body["note"] == "ranking score, not a calibrated probability"
    assert body["n_status_messages"] == 1 and body["has_text"]


def test_raw_window_gets_an_integer_percentile_and_the_resolution_note(client: Any) -> None:
    body = client.post(
        "/predict",
        json=raw_body(status_messages=[{"start_utc": "2023-06-01T11:00:00Z", "text": "Yaw error"}]),
    ).json()
    assert body["headline"] == body["live"] and body["recorded"] is None
    assert body["live"]["percentile"] == int(body["live"]["percentile"])
    assert body["percentile_note"].startswith("±1 pp resolution: reference scores are bf16")
    assert body["hours_since_last_fault"] is None and body["n_status_messages"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"window_id": "K4-20230601T1200", "values": [[0.0] * 12] * 144, "end_utc": END},
        {"values": [[0.0] * 12] * 143, "end_utc": END},
        {"values": [[0.0] * 11] * 144, "end_utc": END},
        {"values": [[0.0] * 12] * 144},
        {"values": [[0.0] * 12] * 144, "end_utc": "2023-06-01T12:03:00Z"},
        {"window_id": "K4-20230601T1200", "end_utc": END},
    ],
)
def test_invalid_predict_is_422(client: Any, payload: dict[str, Any]) -> None:
    assert client.post("/predict", json=payload).status_code == 422


def test_unknown_window_is_404(client: Any) -> None:
    assert client.post("/predict", json={"window_id": "nope"}).status_code == 404
    assert client.get("/demo/windows/nope").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"max_new_tokens": 201},
        {"max_new_tokens": 0},
        {"temperature": 2.5},
        {"top_p": 0.0},
        {"repetition_penalty": 0.9},
        {"prompt": "x" * 2001},
    ],
)
def test_generate_bounds_are_422(client: Any, payload: dict[str, Any]) -> None:
    assert client.post("/generate", json=payload).status_code == 422


def test_generate_is_seeded(client: Any) -> None:
    body = {"prompt": "gearbox", "temperature": 1.0, "seed": 3, "max_new_tokens": 5}
    one, two = (
        client.post("/generate", json=body).json(),
        client.post("/generate", json=body).json(),
    )
    assert one["text"] == two["text"] and one["tokens"] <= 5
    assert one["stop_reason"] in {"sep", "max_new_tokens"}


def test_demo_windows_reveal_labels_only_when_asked(client: Any) -> None:
    hidden = client.get("/demo/windows").json()["windows"]
    assert len(hidden) == 2 and all("labels" not in w for w in hidden)
    shown = client.get("/demo/windows", params={"reveal": "true"}).json()["windows"]
    assert list(shown[0]["labels"]) == ["variant", "registered"]
    assert shown[0]["labels"] == {"variant": False, "registered": True}
    one = client.get("/demo/windows/K5-20230601T1200").json()
    assert len(one["values"]) == 144 and one["values"][10][0] is None and "labels" not in one


def test_schema_lists_the_channels_with_units(client: Any) -> None:
    body = client.get("/schema").json()
    assert body["steps"] == 144 and len(body["channels"]) == 12
    assert body["channels"][0] == {
        "name": "wind_speed_ms",
        "unit": body["channels"][0]["unit"],
        "description": body["channels"][0]["description"],
    }
    assert all(c["unit"] for c in body["channels"])


def test_unexpected_errors_are_500_without_a_trace(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = client.app.state.served.engine

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("secret internals")

    monkeypatch.setattr(engine, "generate_text", boom)
    response = client.post("/generate", json={"prompt": "x"})
    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
    assert "secret" not in response.text


def test_cors_allows_only_the_configured_origin(client: Any) -> None:
    ok = client.get("/health", headers={"Origin": "http://localhost:8080"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:8080"
    other = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers
