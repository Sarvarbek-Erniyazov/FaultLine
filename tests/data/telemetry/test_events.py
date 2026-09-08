"""Event normalization and horizon labelling."""

from __future__ import annotations

import numpy as np
import pandas as pd

from faultline.data.telemetry.events import (
    EventConfig,
    derive_is_fault,
    event_summary,
    label_horizon,
    normalize_events,
    normalize_message,
    raw_payload,
)


def test_normalize_message() -> None:
    config = EventConfig()
    assert normalize_message("  Gearbox   OIL  low ", config) == "gearbox oil low"
    assert normalize_message(None, config) == ""
    assert normalize_message(np.nan, config) == ""
    assert normalize_message("Keep Case", EventConfig(lowercase_messages=False)) == "Keep Case"


def test_unmapped_codes_are_unknown_not_benign() -> None:
    # An unmapped code must not be silently labelled a non-fault: that would inflate
    # precision by counting unchecked events as negatives.
    config = EventConfig()
    assert derive_is_fault("9001", None, config) is None
    assert derive_is_fault(None, None, config) is None


def test_mapped_codes_and_categories() -> None:
    config = EventConfig(fault_codes=["9001"], fault_categories=["shutdown"])
    assert derive_is_fault("9001", None, config) is True
    assert derive_is_fault(None, "Shutdown", config) is True
    assert derive_is_fault("0001", "information", config) is False


def test_normalize_events_fills_canonical_columns() -> None:
    frame = pd.DataFrame(
        {
            "source": ["kelmarsh"] * 2,
            "site": ["Kelmarsh"] * 2,
            "turbine_id": ["T1", "T2"],
            "start_utc": ["2020-01-01 00:00", "not a date"],
            "code": [" 9001 ", "9002"],
            "message": ["Gearbox  OIL low", None],
        }
    )
    events = normalize_events(frame, EventConfig(fault_codes=["9001"]))

    assert len(events) == 1  # the unparseable timestamp is dropped
    row = events.iloc[0]
    assert row["code"] == "9001"
    assert row["message"] == "gearbox oil low"
    assert bool(row["is_fault"]) is True  # pandas hands back np.True_
    assert "end_utc" in events.columns
    assert "raw" in events.columns


def test_normalize_empty_events() -> None:
    assert normalize_events(pd.DataFrame(), EventConfig()).empty


def test_raw_payload_is_stable_json() -> None:
    assert raw_payload({"b": 2, "a": 1}) == '{"a":1,"b":2}'


def test_label_horizon() -> None:
    grid = pd.date_range("2020-01-01 00:00", periods=10, freq="10min", tz="UTC")
    events = pd.DataFrame(
        {
            "source": ["k"],
            "site": ["K"],
            "turbine_id": ["T1"],
            "start_utc": [pd.Timestamp("2020-01-01 00:50", tz="UTC")],
            "is_fault": [True],
        }
    )
    # horizon of 3 steps is 30 minutes, so the steps at 00:20, 00:30 and 00:40 see the
    # 00:50 event; earlier steps are too far away and later ones are past it
    labels = label_horizon(grid, events, EventConfig(horizon_steps=3), turbine_id="T1")
    assert list(labels) == [False, False, True, True, True, False, False, False, False, False]


def test_label_horizon_ignores_other_turbines() -> None:
    grid = pd.date_range("2020-01-01 00:00", periods=5, freq="10min", tz="UTC")
    events = pd.DataFrame(
        {
            "source": ["k"],
            "site": ["K"],
            "turbine_id": ["T2"],
            "start_utc": [pd.Timestamp("2020-01-01 00:20", tz="UTC")],
            "is_fault": [True],
        }
    )
    assert not label_horizon(grid, events, EventConfig(), turbine_id="T1").any()


def test_label_horizon_ignores_non_fault_events_by_default() -> None:
    grid = pd.date_range("2020-01-01 00:00", periods=5, freq="10min", tz="UTC")
    events = pd.DataFrame(
        {
            "source": ["k"],
            "site": ["K"],
            "turbine_id": ["T1"],
            "start_utc": [pd.Timestamp("2020-01-01 00:20", tz="UTC")],
            "is_fault": [None],
        }
    )
    assert not label_horizon(grid, events, EventConfig(), turbine_id="T1").any()
    assert label_horizon(grid, events, EventConfig(), turbine_id="T1", fault_only=False).any()


def test_label_horizon_with_no_events() -> None:
    grid = pd.date_range("2020-01-01", periods=3, freq="10min", tz="UTC")
    assert not label_horizon(grid, pd.DataFrame(), EventConfig()).any()


def test_event_summary_counts_free_text() -> None:
    events = pd.DataFrame(
        {
            "code": ["1", "2", "2"],
            "message": ["gearbox oil low", "", "pitch fault"],
            "is_fault": [True, None, False],
        }
    )
    summary = event_summary(events)
    assert summary["events"] == 3
    assert summary["unique_codes"] == 2
    assert summary["unique_messages"] == 2
    assert summary["free_text_fraction"] == 2 / 3
    assert summary["fault_events"] == 1
    assert summary["unknown_fault_status"] == 1


def test_event_summary_empty() -> None:
    assert event_summary(pd.DataFrame())["events"] == 0
