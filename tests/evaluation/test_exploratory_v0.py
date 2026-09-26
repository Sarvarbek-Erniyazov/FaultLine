"""ADR-0029's persistence builders on synthetic data, and the shipped config against its record."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from faultline.config import load_config
from faultline.data.common.splits import SplitsConfig
from faultline.data.telemetry.verify import opening_messages
from faultline.evaluation.exploratory_v0 import (
    ExploratoryConfig,
    by_turbine,
    flagged_in_spans,
    flagged_in_steps,
    flagged_stop_times,
    hours_since_last,
    model_window_flags,
    opening_codes,
    opening_rows,
    starts_within,
)
from faultline.evaluation.gate_check import GateCheckConfig
from faultline.training.joint_windows import SEP_ID, TXT_CLOSE_ID, TXT_OPEN_ID

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/eval/exploratory_v0.yaml"
HEADING = "## ADR-0029 Post-closure exploratory analyses"
DAY = 86_400


def _utc(text: str) -> pd.Timestamp:
    return pd.Timestamp(text, tz="UTC")


def _s(text: str) -> int:
    return int(_utc(text).timestamp())


# =====================================================================================
# P1 and P2
# =====================================================================================


def test_starts_within_is_half_open_on_the_left_and_per_turbine() -> None:
    t0 = _s("2022-06-01 12:00")
    starts = {"A": np.array([t0 - DAY, t0 - DAY + 600, t0 + 600]), "B": np.array([t0])}
    t = np.array([t0, t0, t0 - 600, t0 + 600])
    turbines = np.array(["A", "B", "A", "C"])
    # A at t0: t0 - 24 h is excluded, t0 - 23 h 50 is inside, the future start is not.
    # B at t0: a start exactly at t is known at t. C has no events at all.
    assert starts_within(t, turbines, starts, DAY).tolist() == [True, True, True, False]
    assert starts_within(np.array([t0]), np.array(["A"]), {"A": np.array([t0 - DAY])}, DAY)[0] == 0


def test_hours_since_last_caps_and_reads_the_cap_without_an_earlier_event() -> None:
    t0 = _s("2022-06-01 12:00")
    starts = {"A": np.array([t0 - 40 * DAY, t0 - 3 * 3600, t0 + 600])}
    t = np.array([t0, t0 - 4 * 3600, t0 - 41 * DAY, t0 - 3 * 3600])
    hours = hours_since_last(t, np.array(["A", "A", "A", "A"]), starts, 720.0)
    # 3 h; the one before is 40 days old, so it caps; none earlier caps; an event at t is 0 h.
    assert hours.tolist() == [3.0, 720.0, 720.0, 0.0]
    assert hours_since_last(np.array([t0]), np.array(["Z"]), starts, 720.0).tolist() == [720.0]


def test_by_turbine_sorts_each_group() -> None:
    grouped = by_turbine(np.array(["B", "A", "B"]), np.array([30, 20, 10]))
    assert {k: v.tolist() for k, v in grouped.items()} == {"A": [20], "B": [10, 30]}


# =====================================================================================
# the opening rows and the code set
# =====================================================================================


def _stream() -> pd.DataFrame:
    rows = [
        # turbine, start, code, message, status, cause
        ("A", "2019-01-01 10:03", "3000", "frequency converter not ready", "Stop", "technical"),
        ("A", "2019-01-01 10:05", "4510", "tower oscillation y level 1", "Stop", "technical"),
        ("A", "2019-01-01 09:00", "100", "safety chain open", "Stop", "technical"),
        ("A", "2019-01-01 10:01", "8000", "high wind", "Stop", "environmental"),
        ("A", "2019-01-01 10:02", "999", "a warning", "Warning", "technical"),
        ("B", "2021-05-01 00:00", "6530", "anemometer defect", "Stop", "technical"),
        ("B", "2019-03-01 00:00", "6120", "uncontrolled yaw movement", "Stop", "technical"),
    ]
    return pd.DataFrame(
        {
            "turbine_id": [r[0] for r in rows],
            "start_utc": [_utc(r[1]) for r in rows],
            "code": pd.array([r[2] for r in rows], dtype="string"),
            "message": pd.array([r[3] for r in rows], dtype="string"),
            "provider_status": [r[4] for r in rows],
            "cause": [r[5] for r in rows],
        }
    )


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "turbine_id": ["A", "A", "B", "B", "C"],
            "start_utc": [
                _utc("2019-01-01 10:00"),  # opened in its first step: the first row, 3000
                _utc("2019-01-01 09:30"),  # nothing in its step: the last one before, 100
                _utc("2021-05-01 00:00"),  # after the training cut
                _utc("2019-03-01 00:00"),
                _utc("2019-03-01 00:00"),  # a turbine with no stop row: no opener
            ],
        }
    )


def test_opening_rows_follow_opening_messages() -> None:
    stream, events = _stream(), _events()
    rows = opening_rows(events, stream, "technical", "Stop")
    assert rows.tolist() == [0, 2, 5, 6, -1]
    messages = opening_messages(events, stream, "technical", "Stop")
    for position, row in enumerate(rows):
        if row < 0:
            assert pd.isna(messages.iloc[position])
        else:
            assert messages.iloc[position] == stream["message"].iloc[row]


def test_opening_codes_count_only_the_training_split() -> None:
    table = opening_codes(
        _events(), _stream(), "technical", "Stop", "2020-12-31T23:59:59Z"
    ).sort_values("code")
    assert table.to_dict("records") == [
        {"code": "100", "message": "safety chain open", "events": 1},
        {"code": "3000", "message": "frequency converter not ready", "events": 1},
        {"code": "6120", "message": "uncontrolled yaw movement", "events": 1},
        {"code": "<none>", "message": "<none>", "events": 1},
    ]


# =====================================================================================
# P3 and P4
# =====================================================================================


def test_flagged_stop_times_keep_stop_rows_of_the_set_rounded_up() -> None:
    times = flagged_stop_times(_stream(), ["3000", "100", "8000", "999"], "Stop")
    # 10:03 rounds up to 10:10; 9:00 stays; high wind is a Stop row of the set, whatever its
    # cause; the warning is not a Stop row.
    assert {k: v.tolist() for k, v in times.items()} == {
        "A": [_s("2019-01-01 09:00"), _s("2019-01-01 10:10"), _s("2019-01-01 10:10")]
    }
    t = np.array([_s("2019-01-01 10:00"), _s("2019-01-01 10:10")])
    assert starts_within(t, np.array(["A", "A"]), {"A": times["A"][1:]}, DAY).tolist() == [
        False,
        True,
    ]


def test_flagged_in_spans_counts_a_message_with_any_token_inside() -> None:
    opens, closes = np.array([2, 10, 20]), np.array([5, 13, 24])
    flags = np.array([True, False, True])
    first = np.array([0, 4, 5, 6, 21, 24])
    last = np.array([2, 8, 20, 21, 30, 30])
    # [0,2) touches nothing; [4,8) holds token 4 of message 0; [5,20) holds only the unflagged
    # message; [6,21) holds token 20 of message 2; [21,30) holds its tail; [24,30) nothing.
    assert flagged_in_spans(opens, closes, flags, first, last).tolist() == [
        False,
        True,
        False,
        True,
        True,
        False,
    ]


def test_flagged_in_steps_reads_closed_step_ranges() -> None:
    steps, flags = np.array([1, 3, 3, 7]), np.array([False, False, True, True])
    first, last = np.array([0, 4, 3, 8]), np.array([2, 7, 3, 9])
    assert flagged_in_steps(steps, flags, first, last).tolist() == [False, True, True, False]


def _synthetic_stream() -> tuple[np.ndarray, np.ndarray]:
    value, text = 100, 2000
    step = [SEP_ID, value]
    parts = [
        step,
        [*step, TXT_OPEN_ID, text, TXT_CLOSE_ID],  # message 0 follows step 1
        step,
        [*step, TXT_OPEN_ID, text, text, TXT_CLOSE_ID],  # message 1 follows step 3
        step,
        step,
    ]
    return np.array([t for p in parts for t in p], dtype=np.uint16), np.array([1, 3])


def test_model_window_flags_follow_the_tail_anchored_window_and_its_cap() -> None:
    stream, steps = _synthetic_stream()
    ends = np.array([3, 4, 5])
    # Plenty of room: a window holds its three steps and their messages.
    capped, uncapped = model_window_flags(stream, steps, np.array([True, False]), ends, 3, 64, 2)
    assert capped.tolist() == [True, False, False]
    assert uncapped.tolist() == [True, False, False]
    # Eight tokens: steps 1-3 of the window ending at 3 need 13, so step 1 and its message are
    # dropped whole; the uncapped twin still sees it.
    capped, uncapped = model_window_flags(stream, steps, np.array([True, False]), ends, 3, 8, 2)
    assert capped.tolist() == [False, False, False]
    assert uncapped.tolist() == [True, False, False]
    capped, _ = model_window_flags(stream, steps, np.array([False, True]), ends, 3, 8, 2)
    assert capped.tolist() == [True, True, False]


def test_model_window_flags_refuse_messages_on_other_steps() -> None:
    stream, _ = _synthetic_stream()
    try:
        model_window_flags(
            stream, np.array([1, 2]), np.array([True, True]), np.array([3]), 3, 64, 2
        )
    except ValueError as error:
        assert "do not follow" in str(error)
    else:
        raise AssertionError("a misaligned message list was accepted")


# =====================================================================================
# the shipped configuration against ADR-0029
# =====================================================================================


def _adr_0029() -> str:
    decisions = (REPO / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert decisions.count(HEADING) == 1
    start = decisions.index(HEADING)
    return decisions[start : decisions.index("\n## ", start + 1)]


def test_config_restates_adr_0029() -> None:
    config = load_config(CONFIG, ExploratoryConfig)
    adr = _adr_0029()
    assert "**Status: EXPLORATORY.**" in adr
    table = adr[adr.index("**18 codes:**") :]
    codes = re.findall(r"^\| (\d+) \| [^|]+ \| (\d+) \|", table, flags=re.MULTILINE)
    listed = {c for pair in codes for c in pair}
    assert len(listed) == 18
    assert sorted(config.persistence.codes, key=int) == sorted(listed, key=int)
    assert config.persistence.cap_hours == 720 and "capped at 720 h (30 days)" in adr
    assert config.persistence.window_hours == 24
    assert config.variant_label == "narrow_within_24h_without" in adr
    assert (config.windows, config.positives) == (137_025, 5_312)


def test_config_estimator_and_cut_are_the_record_s() -> None:
    config = load_config(CONFIG, ExploratoryConfig)
    gate = load_config(REPO / "configs/train/gate_check_v0.yaml", GateCheckConfig)
    assert config.bootstrap == gate.bootstrap
    splits = load_config(REPO / "configs/data/splits_v3.yaml", SplitsConfig)
    assert _utc(config.persistence.train_until) == _utc(str(splits.time.train_until))
    assert list(splits.report_without_messages) == ["anemometer defect"]
