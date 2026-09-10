"""Kelmarsh wind farm adapter (Cubico Sustainable Investments, CC BY 4.0).

Six Senvion MM92 turbines, 2016-2024, published as one zip per year plus a signal
mapping and a static metadata CSV. Each yearly archive holds, per turbine, a
``Turbine_Data_*.csv`` of 10-minute SCADA and a ``Status_*.csv`` of status events.

The files are Greenbyte exports, read by :class:`GreenbyteAdapter`. The layout was
confirmed against the staged archives (``reports/data/raw_inventory_kelmarsh_20260910.md``),
not inferred from file names.

One Kelmarsh quirk the shared reader exists to survive: the 2023 and 2024 exports
repeat every timestamp about 41 times, as cumulative blocks that re-emit earlier labels
with the measured channels empty. The reader collapses them only after proving no
label carries two values for one channel (:mod:`faultline.data.telemetry.collapse`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from faultline.data.telemetry.adapters.greenbyte import (
    SCADA_TIMESTAMP,
    STATUS_CATEGORY,
    STATUS_CODE,
    STATUS_END,
    STATUS_MESSAGE,
    STATUS_START,
    GreenbyteAdapter,
)

__all__ = [
    "SCADA_TIMESTAMP",
    "STATUS_CATEGORY",
    "STATUS_CODE",
    "STATUS_END",
    "STATUS_MESSAGE",
    "STATUS_START",
    "KelmarshAdapter",
]


@dataclass
class KelmarshAdapter(GreenbyteAdapter):
    """Reads the Kelmarsh record into the canonical schema."""

    source_id: ClassVar[str] = "kelmarsh"
    site_name: ClassVar[str] = "Kelmarsh"
