"""Kelmarsh wind farm adapter (Cubico Sustainable Investments, CC BY 4.0).

Six Senvion MM92 turbines, 2016-2024, published as one zip per year plus a signal
mapping and a static metadata CSV. Kelmarsh and Penmanshiel come from the same
publisher and share a file layout, which is why both adapters are thin.

Discovery is implemented and exercised. The loaders are not: writing a column
parser before the archive has been inventoried would be guessing at a header
layout, and a wrong guess here is silent -- it produces a plausible table from the
wrong columns. See ``data/cards/kelmarsh.md`` for the open questions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pandas as pd

from faultline.data.telemetry.adapters.base import BaseAdapter, MemberKind, RawMember


@dataclass
class KelmarshAdapter(BaseAdapter):
    """Reads the Kelmarsh record into the canonical schema."""

    source_id: ClassVar[str] = "kelmarsh"
    site_name: ClassVar[str] = "Kelmarsh"

    PATTERNS: ClassVar[tuple[tuple[str, MemberKind], ...]] = (
        ("datasignalmapping", "metadata"),
        ("wt_static", "metadata"),
        ("alarm", "alarm_log"),
        ("status", "status_events"),
        ("event", "status_events"),
        ("turbine_data", "scada_10min"),
        ("scada", "scada_10min"),
        ("grid", "other"),
        ("pmu", "other"),
        (".kmz", "other"),
    )

    def load_scada(self, member: RawMember) -> pd.DataFrame:
        """Read one Kelmarsh SCADA member.

        Args:
            member: Member classified as SCADA.

        Returns:
            A canonical wide table.

        Raises:
            NotImplementedError: Until the member layout is confirmed by inspection.
        """
        raise NotImplementedError(
            "TODO(m1): confirm the Kelmarsh SCADA member layout (header rows, timestamp "
            "column and timezone, turbine identifier source) from the raw inventory "
            "report, then implement; see data/cards/kelmarsh.md"
        )

    def load_events(self, member: RawMember) -> pd.DataFrame | None:
        """Read one Kelmarsh status or event member.

        Args:
            member: Member classified as an event table.

        Returns:
            A canonical events table, or ``None``.

        Raises:
            NotImplementedError: Until the member layout is confirmed by inspection.
        """
        raise NotImplementedError(
            "TODO(m1): confirm whether the Kelmarsh archives carry a status/event table "
            "and whether its messages are free text; see data/cards/kelmarsh.md"
        )
