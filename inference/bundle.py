"""The held-out demo bundle (Lesson 11): raw Kelmarsh windows and their record, no pickle.

The bundle is one ``.npz`` built by ``lesson11/build_demo_bundle.py``. Per window it holds what a
client would send (the 144 x 12 values, the status messages, the end time) and what the record
says about it: both labels, hours since the last fault (ADR-0029's P2) with its percentile, and
the saved seed-1 logit. Every array is a plain numpy dtype, so it loads with
``allow_pickle=False``. Only numpy is needed to read it; the server does not import the
evaluation code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from inference.engine import RawWindow, StatusMessage

#: The arrays a bundle holds, one entry per window unless named otherwise.
PER_WINDOW = (
    "window_id",
    "row",
    "turbine",
    "end_utc_s",
    "values",
    "label_registered",
    "label_variant",
    "label_variant_known",
    "hours_since_last_fault",
    "hours_since_last_fault_percentile",
    "recorded_logit",
    "recorded_score",
    "recorded_percentile",
)
#: Arrays with one entry per message, and the channel order.
PER_MESSAGE = ("message_window", "message_start_ns", "message_text")


@dataclass(frozen=True)
class DemoWindow:
    """One bundle window.

    Attributes:
        window_id: A stable name, ``K<turbine>-<end>``.
        row: Its row in the recorded seed-1 test scores.
        turbine: The turbine.
        raw: What a client would send.
        label_registered: ``narrow_within_24h``.
        label_variant: ADR-0009's variant label.
        hours_since_last_fault: ADR-0029's P2 magnitude, capped at 720 h.
        hours_since_last_fault_percentile: P2's mid-rank percentile over the recorded test rows.
        recorded_logit: The saved seed-1 head logit (bfloat16 scoring).
        recorded_score: The recorded logit plus the prior offset, in float32.
        recorded_percentile: The recorded score's percentile among the seed-1 test scores.
    """

    window_id: str
    row: int
    turbine: str
    raw: RawWindow
    label_registered: bool
    label_variant: bool
    hours_since_last_fault: float
    hours_since_last_fault_percentile: float
    recorded_logit: float
    recorded_score: float
    recorded_percentile: float


def write_bundle(path: Path, arrays: dict[str, np.ndarray]) -> None:
    """Write a bundle, refusing arrays that would need pickle or do not line up.

    Args:
        path: The ``.npz``.
        arrays: :data:`PER_WINDOW`, :data:`PER_MESSAGE` and ``channels``.

    Raises:
        ValueError: If an array is missing, has an object dtype, or has the wrong length.
    """
    names = (*PER_WINDOW, *PER_MESSAGE, "channels")
    missing = sorted(set(names) - set(arrays))
    if missing:
        raise ValueError(f"missing arrays: {missing}")
    windows = len(arrays["window_id"])
    for name in names:
        if arrays[name].dtype == object:
            raise ValueError(f"{name} has an object dtype")
        if name in PER_WINDOW and len(arrays[name]) != windows:
            raise ValueError(f"{name} has {len(arrays[name])} entries for {windows} windows")
    messages = len(arrays["message_window"])
    if any(len(arrays[name]) != messages for name in PER_MESSAGE):
        raise ValueError("the message arrays differ in length")
    payload: dict[str, Any] = {name: arrays[name] for name in names}
    np.savez_compressed(path, **payload)


def read_bundle(path: Path) -> list[DemoWindow]:
    """Read a bundle's windows, in bundle order.

    Args:
        path: The ``.npz``.

    Returns:
        The windows.
    """
    with np.load(path, allow_pickle=False) as data:
        a = {name: data[name] for name in data.files}
    out = []
    for i in range(len(a["window_id"])):
        mine = np.flatnonzero(a["message_window"] == i)
        messages = tuple(
            StatusMessage(
                start_utc=pd.Timestamp(int(a["message_start_ns"][j]), unit="ns", tz="UTC"),
                text=str(a["message_text"][j]),
            )
            for j in mine
        )
        raw = RawWindow(
            values=np.asarray(a["values"][i], dtype=np.float64),
            end_utc=pd.Timestamp(int(a["end_utc_s"][i]), unit="s", tz="UTC"),
            messages=messages,
        )
        out.append(
            DemoWindow(
                window_id=str(a["window_id"][i]),
                row=int(a["row"][i]),
                turbine=str(a["turbine"][i]),
                raw=raw,
                label_registered=bool(a["label_registered"][i]),
                label_variant=bool(a["label_variant"][i]),
                hours_since_last_fault=float(a["hours_since_last_fault"][i]),
                hours_since_last_fault_percentile=float(a["hours_since_last_fault_percentile"][i]),
                recorded_logit=float(a["recorded_logit"][i]),
                recorded_score=float(a["recorded_score"][i]),
                recorded_percentile=float(a["recorded_percentile"][i]),
            )
        )
    return out


def bundle_channels(path: Path) -> list[str]:
    """The channel order of a bundle's values.

    Args:
        path: The ``.npz``.

    Returns:
        The channel names.
    """
    with np.load(path, allow_pickle=False) as data:
        return [str(c) for c in data["channels"]]
