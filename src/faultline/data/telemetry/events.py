"""Canonical events and horizon labelling.

Events are where the supervision comes from. Each provider publishes its own alarm,
status or shutdown vocabulary, so this module normalizes them into the canonical
events table and turns them into the actual learning target: for every grid step,
does an event of interest begin within the next ``horizon_steps``?

Two deliberate choices:

* An unmapped code yields ``is_fault = None``, never ``False``. Silence about a code
  is not evidence that it is benign, and quietly labelling unknown codes as
  non-faults would inflate every precision number this project reports.
* Labelling is anchored on an event's **start**. The question is whether a fault is
  coming, not whether one is currently in progress.
"""

from __future__ import annotations

import json
import re
from typing import Any

import numpy as np
import pandas as pd
from pydantic import Field

from faultline.config import StrictModel
from faultline.data.telemetry.schemas import EVENT_COLUMNS, empty_events_frame
from faultline.logging_utils import get_logger

logger = get_logger(__name__)

_WHITESPACE = re.compile(r"\s+")


class EventConfig(StrictModel):
    """Event normalization and labelling settings.

    Attributes:
        horizon_steps: Risk horizon, in grid steps.
        lowercase_messages: Lowercase messages before comparison and counting.
        collapse_whitespace: Collapse whitespace runs in messages.
        fault_categories: Provider categories treated as faults.
        fault_codes: Provider codes treated as faults.
        default_is_fault: Label for codes matching neither list; ``None`` means
            unknown, which is the honest default.
    """

    horizon_steps: int = 144
    lowercase_messages: bool = True
    collapse_whitespace: bool = True
    fault_categories: list[str] = Field(default_factory=list)
    fault_codes: list[str] = Field(default_factory=list)
    default_is_fault: bool | None = None


def normalize_message(message: Any, config: EventConfig) -> str:
    """Normalize an event message for comparison and counting.

    Args:
        message: Raw message value; may be a string, ``None`` or a pandas NaN.
        config: Normalization settings.

    Returns:
        The normalized message, or an empty string when absent.
    """
    if message is None or (isinstance(message, float) and np.isnan(message)):
        return ""
    text = str(message).strip()
    if config.collapse_whitespace:
        text = _WHITESPACE.sub(" ", text)
    if config.lowercase_messages:
        text = text.lower()
    return text


def derive_is_fault(code: str | None, category: str | None, config: EventConfig) -> bool | None:
    """Decide whether one event counts as a fault.

    Args:
        code: Provider event code.
        category: Provider event category.
        config: Mapping of codes and categories to fault status.

    Returns:
        ``True`` or ``False`` when the code or category is mapped, otherwise
        ``config.default_is_fault`` (``None`` by default, meaning unknown).
    """
    code_text = "" if code is None else str(code).strip().lower()
    category_text = "" if category is None else str(category).strip().lower()
    if code_text and code_text in {value.lower() for value in config.fault_codes}:
        return True
    if category_text and category_text in {value.lower() for value in config.fault_categories}:
        return True
    if (config.fault_codes or config.fault_categories) and (code_text or category_text):
        return False
    return config.default_is_fault


def normalize_events(frame: pd.DataFrame, config: EventConfig) -> pd.DataFrame:
    """Normalize a provider event table into the canonical events schema.

    Args:
        frame: Table carrying at least ``source``, ``site``, ``turbine_id`` and
            ``start_utc``; other canonical columns are filled when absent.
        config: Normalization settings.

    Returns:
        A canonical events table with normalized messages and derived fault flags.
    """
    if frame.empty:
        return empty_events_frame()

    result = frame.copy()
    for column in EVENT_COLUMNS:
        if column not in result.columns:
            result[column] = None

    result["start_utc"] = pd.to_datetime(result["start_utc"], utc=True, errors="coerce")
    result["end_utc"] = pd.to_datetime(result["end_utc"], utc=True, errors="coerce")
    result["message"] = [normalize_message(value, config) for value in result["message"]]
    result["code"] = [None if value is None else str(value).strip() for value in result["code"]]
    result["is_fault"] = [
        derive_is_fault(code, category, config)
        for code, category in zip(result["code"], result["category"], strict=True)
    ]
    result = result[result["start_utc"].notna()]
    return result[list(EVENT_COLUMNS)].reset_index(drop=True)


def raw_payload(row: dict[str, Any]) -> str:
    """Serialize a provider row for the canonical ``raw`` column.

    Args:
        row: The provider row as a mapping.

    Returns:
        A compact JSON string preserving the original fields.
    """
    return json.dumps(row, sort_keys=True, default=str, separators=(",", ":"))


def label_horizon(
    timestamps: pd.DatetimeIndex | pd.Series[Any],
    events: pd.DataFrame,
    config: EventConfig,
    freq: str = "10min",
    turbine_id: str | None = None,
    fault_only: bool = True,
) -> pd.Series[Any]:
    """Label each grid step with whether an event starts within the horizon.

    Args:
        timestamps: Grid timestamps, UTC-aware and sorted.
        events: Canonical events table.
        config: Horizon and fault-mapping settings.
        freq: Grid resolution, used to convert the horizon into a duration.
        turbine_id: Restrict to one turbine when the events table covers several.
        fault_only: Consider only events whose ``is_fault`` is ``True``.

    Returns:
        A boolean Series, ``True`` where an event starts in ``(t, t + horizon]``.
    """
    index = pd.DatetimeIndex(pd.to_datetime(pd.Series(timestamps), utc=True))
    labels = pd.Series(False, index=range(len(index)), name="event_within_horizon")
    if events.empty or len(index) == 0:
        return labels

    selected = events
    if turbine_id is not None and "turbine_id" in selected.columns:
        selected = selected[selected["turbine_id"].astype(str) == str(turbine_id)]
    if fault_only and "is_fault" in selected.columns:
        selected = selected[selected["is_fault"].fillna(False).astype(bool)]
    if selected.empty:
        return labels

    horizon = pd.Timedelta(freq) * config.horizon_steps
    starts = pd.DatetimeIndex(pd.to_datetime(selected["start_utc"], utc=True)).sort_values()

    # For each grid step, the first event starting strictly after it must also fall
    # within the horizon for the step to be positive.
    positions = np.searchsorted(starts.to_numpy(), index.to_numpy(), side="right")
    within = np.zeros(len(index), dtype=bool)
    valid = positions < len(starts)
    if valid.any():
        next_start = starts.to_numpy()[positions[valid]]
        within[valid] = next_start <= (index.to_numpy()[valid] + horizon)
    return pd.Series(within, index=labels.index, name="event_within_horizon")


def event_summary(events: pd.DataFrame) -> dict[str, Any]:
    """Summarize an events table for a stats report.

    Args:
        events: Canonical events table.

    Returns:
        Counts of events, unique codes and messages, and the share of rows carrying
        a non-empty free-text message.
    """
    if events.empty:
        return {
            "events": 0,
            "unique_codes": 0,
            "unique_messages": 0,
            "free_text_fraction": 0.0,
            "fault_events": 0,
            "unknown_fault_status": 0,
        }
    messages = events["message"].fillna("").astype(str)
    non_empty = messages.str.strip().str.len() > 0
    return {
        "events": int(len(events)),
        "unique_codes": int(events["code"].nunique(dropna=True)),
        "unique_messages": int(messages[non_empty].nunique()),
        "free_text_fraction": float(non_empty.mean()),
        "fault_events": int(events["is_fault"].fillna(False).astype(bool).sum()),
        "unknown_fault_status": int(events["is_fault"].isna().sum()),
    }
