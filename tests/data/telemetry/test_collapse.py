"""The repeated-label collapse: lossless when the repeats are disjoint, fatal when not."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from faultline.data.telemetry.collapse import RepeatedLabelConflictError, collapse_repeated_labels

LABELS = ["2023-01-01 00:00:00", "2023-01-01 00:10:00", "2023-01-01 00:20:00"]


def repeated_export() -> pd.DataFrame:
    """The Kelmarsh 2023 shape in miniature: cumulative blocks, values on one row each."""
    blocks = [
        # block 1: the first label, with its values
        {"label": LABELS[0], "power": 1850.0, "wind": 9.1},
        # block 2 restarts: label 0 again, empty; label 1 with its values
        {"label": LABELS[0], "power": np.nan, "wind": np.nan},
        {"label": LABELS[1], "power": 1600.0, "wind": 8.2},
        # the final block: every label again, the last one with its values
        {"label": LABELS[0], "power": np.nan, "wind": np.nan},
        {"label": LABELS[1], "power": np.nan, "wind": np.nan},
        {"label": LABELS[2], "power": 1400.0, "wind": np.nan},
    ]
    return pd.DataFrame(blocks)


def test_a_repeated_export_collapses_to_one_row_per_label_without_losing_a_value() -> None:
    frame = repeated_export()
    collapsed, stats = collapse_repeated_labels(frame, ["label"], ["power", "wind"])

    assert list(collapsed["label"]) == LABELS
    assert list(collapsed["power"]) == [1850.0, 1600.0, 1400.0]
    # every non-null value in the input survives, and nothing is invented
    assert int(collapsed[["power", "wind"]].notna().sum().sum()) == int(
        frame[["power", "wind"]].notna().sum().sum()
    )
    assert np.isnan(collapsed.loc[2, "wind"])
    assert (stats.rows_raw, stats.rows_after_null_drop, stats.labels_distinct) == (6, 3, 3)
    assert stats.rows_out == 3
    assert stats.repeated_export


def test_an_export_that_does_not_repeat_reports_three_equal_counts() -> None:
    frame = pd.DataFrame({"label": LABELS, "power": [1.0, 2.0, 3.0]})
    collapsed, stats = collapse_repeated_labels(frame, ["label"], ["power"])
    assert stats.rows_raw == stats.rows_after_null_drop == stats.labels_distinct == 3
    assert not stats.repeated_export
    assert stats.labels_repeated == 0
    pd.testing.assert_frame_equal(collapsed, frame)


def test_rows_null_in_every_ingested_column_are_dropped_even_without_repeats() -> None:
    # A turbine that was not reporting: the label exists, nothing was measured.
    frame = pd.DataFrame({"label": LABELS, "power": [np.nan, 2.0, np.nan]})
    collapsed, stats = collapse_repeated_labels(frame, ["label"], ["power"])
    assert list(collapsed["label"]) == [LABELS[1]]
    assert (stats.rows_raw, stats.rows_after_null_drop, stats.labels_distinct) == (3, 1, 3)


def test_two_values_for_one_label_and_column_stop_the_ingest() -> None:
    frame = pd.DataFrame(
        {"label": [LABELS[0], LABELS[0]], "power": [1850.0, 1851.0], "wind": [9.1, np.nan]}
    )
    with pytest.raises(RepeatedLabelConflictError, match=r"columns \['power'\]"):
        collapse_repeated_labels(frame, ["label"], ["power", "wind"])


def test_identical_repeated_values_collapse_to_the_one_value() -> None:
    # The rule counts distinct values, not non-null cells (M1a step 6c): the repeated
    # Kelmarsh rows carry the same availability figure on several rows of a label, and
    # keeping that one value loses nothing.
    frame = pd.DataFrame(
        {
            "label": [LABELS[0], LABELS[0], LABELS[1]],
            "power": [1850.0, np.nan, 1600.0],
            "avail": [100.0, 100.0, 98.0],
        }
    )
    collapsed, stats = collapse_repeated_labels(frame, ["label"], ["power", "avail"])
    assert list(collapsed["power"]) == [1850.0, 1600.0]
    assert list(collapsed["avail"]) == [100.0, 98.0]
    assert stats.labels_repeated == 1


def test_a_label_with_one_value_and_a_different_one_is_a_conflict() -> None:
    frame = pd.DataFrame(
        {"label": [LABELS[0], LABELS[0], LABELS[0]], "avail": [100.0, 100.0, 97.0]}
    )
    with pytest.raises(RepeatedLabelConflictError, match="two different values"):
        collapse_repeated_labels(frame, ["label"], ["avail"])


def test_the_conflict_is_not_a_value_error() -> None:
    # The ingest stage logs and skips members that raise ValueError; this must stop it.
    assert not issubclass(RepeatedLabelConflictError, ValueError)


def test_a_turbine_column_is_part_of_the_key() -> None:
    # Hill of Towie publishes all 21 turbines in one monthly file: the same label on two
    # stations is two observations, not a repeat.
    frame = pd.DataFrame(
        {"label": [LABELS[0], LABELS[0]], "station": [1, 2], "power": [1850.0, 1600.0]}
    )
    collapsed, stats = collapse_repeated_labels(frame, ["label", "station"], ["power"])
    assert len(collapsed) == 2
    assert stats.labels_distinct == 2
    assert not stats.repeated_export
