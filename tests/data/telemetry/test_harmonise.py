"""The harmonised event rule (ADR-0009), on synthetic stops."""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from faultline.data.telemetry.harmonise import (
    CAUSES,
    alarm_override_steps,
    downtime_stop_steps,
    horizon_labels,
    select_events,
    status_stop_steps,
    to_seconds,
    wind_state,
)

T0 = pd.Timestamp("2020-01-01", tz="UTC")
STEP = pd.Timedelta(minutes=10)
S = pd.Timedelta(seconds=1)


def stops(*rows: tuple[str, pd.Timestamp, pd.Timestamp | None, str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "turbine_id": [r[0] for r in rows],
            "start_utc": pd.to_datetime([r[1] for r in rows], utc=True),
            "end_utc": pd.to_datetime([r[2] for r in rows], utc=True),
            "cause": [r[3] for r in rows],
        }
    )


def steps_of(frame: pd.DataFrame) -> pd.DataFrame:
    return status_stop_steps(frame, frame["cause"])[0]


# -- status rows to steps --------------------------------------------------------------


def test_a_row_spanning_steps_is_allocated_to_each_step() -> None:
    table = steps_of(stops(("K1", T0 + 5 * 60 * S, T0 + 25 * 60 * S, "technical")))
    assert list(table["timestamp_utc"]) == [T0, T0 + STEP, T0 + 2 * STEP]
    assert list(table["technical_s"]) == [300.0, 600.0, 300.0]
    assert list(table["total_s"]) == [300.0, 600.0, 300.0]


def test_two_rows_about_one_stop_count_its_seconds_once() -> None:
    # "Frequency converter not ready" and "error", overlapping: one stop, 70 s.
    table = steps_of(
        stops(
            ("K1", T0 + 10 * S, T0 + 60 * S, "technical"),
            ("K1", T0 + 30 * S, T0 + 80 * S, "technical"),
        )
    )
    assert table["technical_s"].tolist() == [70.0]
    assert table["total_s"].tolist() == [70.0]


def test_the_total_is_the_union_over_causes() -> None:
    table = steps_of(
        stops(
            ("K1", T0, T0 + 120 * S, "technical"),
            ("K1", T0 + 60 * S, T0 + 180 * S, "planned"),
        )
    )
    row = table.iloc[0]
    assert (row["technical_s"], row["planned_s"], row["total_s"]) == (120.0, 120.0, 180.0)


def test_a_row_without_an_end_is_counted_and_not_allocated() -> None:
    frame = stops(("K1", T0, None, "technical"), ("K1", T0 + STEP, T0 + STEP + 90 * S, "grid"))
    table, dropped = status_stop_steps(frame, frame["cause"])
    assert dropped == 1
    assert table["technical_s"].sum() == 0.0


def test_an_unknown_cause_is_rejected() -> None:
    frame = stops(("K1", T0, T0 + STEP, "weather"))
    with pytest.raises(ValueError, match="outside the vocabulary"):
        status_stop_steps(frame, frame["cause"])


# -- the rule --------------------------------------------------------------------------


def test_the_rule_takes_no_source_argument() -> None:
    # One function applied identically at every site: it cannot branch on a site it is
    # never told about.
    assert list(inspect.signature(select_events).parameters) == [
        "steps",
        "causes",
        "min_duration_s",
    ]


def test_the_rule_gives_the_same_events_whichever_site_the_steps_came_from() -> None:
    frame = stops(
        ("A", T0, T0 + 3 * STEP, "technical"),
        ("A", T0 + 5 * STEP, T0 + 6 * STEP, "environmental"),
    )
    senvion = select_events(steps_of(frame), ["technical"], 60)
    siemens = select_events(steps_of(frame.assign(turbine_id="T01")), ["technical"], 60)
    pd.testing.assert_frame_equal(
        senvion.drop(columns="turbine_id"), siemens.drop(columns="turbine_id")
    )


def test_narrow_keeps_technical_downtime_and_broad_keeps_any() -> None:
    frame = stops(
        ("K1", T0, T0 + 2 * STEP, "environmental"),
        ("K1", T0 + 2 * STEP, T0 + 3 * STEP, "technical"),
        ("K1", T0 + 6 * STEP, T0 + 7 * STEP, "planned"),
    )
    table = steps_of(frame)
    narrow = select_events(table, ["technical"], 60)
    broad = select_events(table, list(CAUSES), 60)
    assert list(narrow["start_utc"]) == [T0 + 2 * STEP]
    # the wind stop and the fault touch, so they are one broad run; the planned stop
    # is separated by a gap and is its own
    assert list(broad["start_utc"]) == [T0, T0 + 6 * STEP]
    assert list(broad["dominant_cause"]) == ["environmental", "planned"]
    assert list(broad["first_cause"]) == ["environmental", "planned"]


def test_the_minimum_duration_counts_seconds_of_the_chosen_causes() -> None:
    frame = stops(
        ("K1", T0, T0 + 45 * S, "technical"),
        ("K1", T0 + 3 * STEP, T0 + 3 * STEP + 75 * S, "technical"),
    )
    table = steps_of(frame)
    assert len(select_events(table, ["technical"], 60)) == 1
    assert len(select_events(table, ["technical"], 1)) == 2
    assert select_events(table, ["technical"], 60)["duration_s"].tolist() == [75.0]


def test_a_missing_step_or_another_turbine_ends_a_run() -> None:
    frame = stops(
        ("K1", T0, T0 + STEP, "technical"),
        ("K1", T0 + 2 * STEP, T0 + 3 * STEP, "technical"),
        ("K2", T0 + STEP, T0 + 2 * STEP, "technical"),
    )
    events = select_events(steps_of(frame), ["technical"], 60)
    assert len(events) == 3


# -- downtime series and stop classes ---------------------------------------------------


def downtime(values: list[float], turbine: str = "T01") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "turbine_id": turbine,
            "timestamp_utc": [T0 + i * STEP for i in range(len(values))],
            "downtime_s": values,
        }
    )


def classes(tur: list[float], env: list[float], turbine: str = "T01") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "turbine_id": turbine,
            "timestamp_utc": [T0 + i * STEP for i in range(len(tur))],
            "wtc_ScTurSto_timeon": tur,
            "wtc_ScEnvSto_timeon": env,
        }
    )


CLASS_CAUSES = {"wtc_ScTurSto_timeon": "technical", "wtc_ScEnvSto_timeon": "environmental"}
NO_OVERRIDES = pd.DataFrame(columns=["turbine_id", "timestamp_utc", "code", "cause"])


def test_timers_split_the_downtime_and_the_rest_is_unknown() -> None:
    table, stats = downtime_stop_steps(
        downtime([600, 600, 0, 400]),
        classes([600, 0, 0, 100], [0, 200, 0, 0]),
        CLASS_CAUSES,
        NO_OVERRIDES,
    )
    assert table["technical_s"].tolist() == [600.0, 0.0, 100.0]
    assert table["environmental_s"].tolist() == [0.0, 200.0, 0.0]
    assert table["unknown_s"].tolist() == [0.0, 400.0, 300.0]
    assert stats.down_steps == 3
    assert stats.unattributed_down_steps == 0


def test_a_timer_never_exceeds_the_downtime_it_splits() -> None:
    table, _ = downtime_stop_steps(downtime([120]), classes([600], [0]), CLASS_CAUSES, NO_OVERRIDES)
    assert table["technical_s"].tolist() == [120.0]


def test_a_down_step_with_no_timer_row_is_unknown_and_counted() -> None:
    table, stats = downtime_stop_steps(
        downtime([600, 600]), classes([600], [0]), CLASS_CAUSES, NO_OVERRIDES
    )
    assert table["unknown_s"].tolist() == [0.0, 600.0]
    assert stats.unclassified_down_steps == 1


def lubrication(start: pd.Timestamp, end: pd.Timestamp | None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "turbine_id": ["T01"],
            "code": ["3130"],
            "start_utc": pd.to_datetime([start], utc=True),
            "end_utc": pd.to_datetime([end], utc=True),
        }
    )


def test_pitch_lubrication_is_excluded_by_cause_not_by_duration() -> None:
    # Filed under turbine error by the provider; a three-minute stop and a long one alike
    # are planned, while a turbine error outside the alarm stays technical.
    alarms = pd.concat(
        [
            lubrication(T0 + 30 * S, T0 + 210 * S),
            lubrication(T0 + 3 * STEP, T0 + 5 * STEP + 60 * S),
        ]
    )
    overrides = alarm_override_steps(alarms, {"3130": "planned"})
    table, stats = downtime_stop_steps(
        downtime([180, 0, 0, 600, 600, 600, 0, 600]),
        classes([180, 0, 0, 600, 600, 600, 0, 600], [0] * 8),
        CLASS_CAUSES,
        overrides,
    )
    narrow = select_events(table, ["technical"], 60)
    assert list(narrow["start_utc"]) == [T0 + 7 * STEP]
    assert table["planned_s"].sum() == 180.0 + 3 * 600.0
    assert [(o.code, o.cause, o.steps) for o in stats.overrides] == [("3130", "planned", 4)]


def test_an_alarm_is_active_from_its_start_step_through_its_end_step() -> None:
    steps = alarm_override_steps(
        lubrication(T0 + 9 * 60 * S, T0 + 21 * 60 * S), {"3130": "planned"}
    )
    assert list(steps["timestamp_utc"]) == [T0, T0 + STEP, T0 + 2 * STEP]
    only_start = alarm_override_steps(lubrication(T0 + 9 * 60 * S, None), {"3130": "planned"})
    assert list(only_start["timestamp_utc"]) == [T0]


def test_the_attribution_counts_can_be_limited_to_the_labelled_grid() -> None:
    # The series runs past the labelled grid (the year after, read for the horizon);
    # those steps have no stop classes and must not be counted as unclassified.
    later = pd.Timestamp("2021-01-01", tz="UTC")
    series = pd.concat([downtime([600]), downtime([600]).assign(timestamp_utc=later)])
    grid = {"T01": to_seconds(pd.Series([T0]))}
    _, stats = downtime_stop_steps(series, classes([600], [0]), CLASS_CAUSES, NO_OVERRIDES, grid)
    assert (stats.down_steps, stats.unclassified_down_steps) == (1, 0)


# -- labels and diagnostics --------------------------------------------------------------


def test_a_label_past_the_record_is_unknown_unless_an_event_was_seen() -> None:
    stamps = pd.Series([T0 + i * STEP for i in range(10)])
    covered = to_seconds(stamps)  # the record ends with the grid
    starts = pd.Series([T0 + 8 * STEP])
    labels = horizon_labels(stamps, starts, 3, covered)
    assert labels.iloc[:5].tolist() == [False, False, False, False, False]
    assert labels.iloc[5:8].tolist() == [True, True, True]
    # steps 8 and 9 look past the end of the record and saw nothing: unknown, not False
    assert labels.iloc[8:].isna().all()


def test_a_gap_in_the_record_makes_the_labels_that_look_into_it_unknown() -> None:
    stamps = pd.Series([T0 + i * STEP for i in range(6)])
    covered = to_seconds(stamps.drop(index=3))
    labels = horizon_labels(stamps, pd.Series([], dtype="datetime64[ns, UTC]"), 1, covered)
    assert pd.isna(labels.iloc[2])
    assert not pd.isna(labels.iloc[3])
    assert not labels.iloc[3]


def test_wind_state_reads_the_step_an_event_starts_in() -> None:
    events = pd.DataFrame(
        {
            "turbine_id": ["T01"] * 4,
            "start_utc": [T0 + 30 * S, T0 + STEP, T0 + 2 * STEP, T0 + 5 * STEP],
        }
    )
    wind = pd.DataFrame(
        {
            "turbine_id": "T01",
            "timestamp_utc": [T0, T0 + STEP, T0 + 2 * STEP],
            "wind_speed_ms": [2.0, 25.0, 9.0],
        }
    )
    states = wind_state(events, wind, 3.0, 20.0)
    assert states.tolist() == ["below_cut_in", "above_cut_out", "inside", "unknown"]


def test_seconds_do_not_depend_on_the_timestamp_resolution() -> None:
    stamps = pd.Series([T0, T0 + STEP])
    assert np.array_equal(to_seconds(stamps), to_seconds(stamps.astype("datetime64[s, UTC]")))
