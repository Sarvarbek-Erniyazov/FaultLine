"""The demo bundle: the format round-trips without pickle; the committed bundle keeps its rule."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from inference.bundle import PER_MESSAGE, PER_WINDOW, bundle_channels, read_bundle, write_bundle

DEMO = Path(__file__).resolve().parents[2] / "lesson11" / "demo"


def tiny_arrays() -> dict[str, np.ndarray]:
    values = np.random.default_rng(0).normal(size=(2, 144, 12))
    values[0, 3, 4] = np.nan
    end = int(pd.Timestamp("2023-03-01 10:00", tz="UTC").timestamp())
    return {
        "window_id": np.array(["K4-20230301T1000", "K5-20230301T1000"]),
        "row": np.array([7, 9], dtype=np.int64),
        "turbine": np.array(["Kelmarsh 4", "Kelmarsh 5"]),
        "end_utc_s": np.array([end, end], dtype=np.int64),
        "values": values,
        "label_registered": np.array([True, False]),
        "label_variant": np.array([False, False]),
        "label_variant_known": np.array([True, True]),
        "hours_since_last_fault": np.array([3.5, 720.0]),
        "hours_since_last_fault_percentile": np.array([91.0, 28.9]),
        "recorded_logit": np.array([-0.5, -1.25], dtype=np.float32),
        "recorded_score": np.array([-4.29, -5.04], dtype=np.float32),
        "recorded_percentile": np.array([60.0, 20.0]),
        "message_window": np.array([1, 1], dtype=np.int64),
        "message_start_ns": np.array([(end - 600) * 10**9, (end - 60) * 10**9], dtype=np.int64),
        "message_text": np.array(["Yaw error", "Gearbox oil pressure low"]),
        "channels": np.array([f"c{i}" for i in range(12)]),
    }


def test_the_format_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "b.npz"
    arrays = tiny_arrays()
    write_bundle(path, arrays)
    windows = read_bundle(path)
    assert [w.window_id for w in windows] == list(arrays["window_id"])
    assert np.array_equal(windows[0].raw.values, arrays["values"][0], equal_nan=True)
    assert windows[0].raw.messages == ()
    assert [m.text for m in windows[1].raw.messages] == ["Yaw error", "Gearbox oil pressure low"]
    assert windows[1].raw.end_utc == pd.Timestamp("2023-03-01 10:00", tz="UTC")
    assert windows[0].label_registered and not windows[1].label_registered
    assert windows[1].hours_since_last_fault == 720.0
    assert bundle_channels(path) == [f"c{i}" for i in range(12)]


def test_the_writer_refuses_what_would_not_load_cleanly(tmp_path: Path) -> None:
    arrays = tiny_arrays()
    with pytest.raises(ValueError, match="missing"):
        write_bundle(tmp_path / "a.npz", {k: v for k, v in arrays.items() if k != "row"})
    with pytest.raises(ValueError, match="object"):
        write_bundle(tmp_path / "b.npz", {**arrays, "turbine": np.array(["x", None])})
    with pytest.raises(ValueError, match="entries"):
        write_bundle(tmp_path / "c.npz", {**arrays, "row": np.array([1], dtype=np.int64)})
    with pytest.raises(ValueError, match="message"):
        write_bundle(tmp_path / "d.npz", {**arrays, "message_text": np.array(["one"])})


def test_the_committed_bundle_keeps_its_rule() -> None:
    bundle = DEMO / "kelmarsh_demo_v0.npz"
    if not bundle.exists():
        pytest.skip("the demo bundle is not built")
    manifest = json.loads((DEMO / "manifest.json").read_text(encoding="utf-8"))
    assert bundle.stat().st_size <= 5_000_000
    with np.load(bundle, allow_pickle=False) as data:
        assert set(data.files) == {*PER_WINDOW, *PER_MESSAGE, "channels"}
        turbines = set(data["turbine"].tolist())
        years = pd.to_datetime(data["end_utc_s"], unit="s", utc=True).year
        registered = data["label_registered"]
        assert data["values"].shape == (manifest["windows"], 144, 12)
    assert turbines == {"Kelmarsh 4", "Kelmarsh 5"}
    assert set(years) == {2023}
    assert int(registered.sum()) == manifest["counts"]["positives_chosen"] == 100
    assert int((~registered).sum()) == manifest["counts"]["negatives_chosen"] == 200
    assert "CC BY 4.0" in (DEMO / "ATTRIBUTION").read_text(encoding="utf-8")
    windows = read_bundle(bundle)
    assert len({w.window_id for w in windows}) == len(windows) == 300
    assert all(0.0 <= w.hours_since_last_fault <= 720.0 for w in windows)
