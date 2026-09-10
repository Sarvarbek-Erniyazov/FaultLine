"""CARE to Compare adapter (Fraunhofer IEE, CC BY-SA 4.0).

Thirty-six turbines across three anonymised farms, 89 turbine-years, 95 datasets
of which 45 carry labelled anomaly events with descriptions.

Two things make this source different from the other three. Its licence is
share-alike, so any derived dataset redistributed from this project would inherit
CC BY-SA 4.0 -- which is why only cards, manifests and statistics are
redistributed here (see docs/DATA_LICENSES.md). And its channels are anonymised
(sensor_NN), so the channel map cannot be written from the file names alone: it
needs the record README and, most likely, distributional matching against the
named sources.

Read on 2026-09-10, without extracting the archive: the README documents the
layout ``Wind Farm <x>/{event_info.csv, feature_description.csv,
datasets/<event_id>.csv}``. ``event_info.csv`` is one file per farm, not per
dataset, with one row per dataset (95 in all) and an ``event_description`` column
the README calls "additional information of the root cause for some anomaly
events". ``feature_description.csv`` gives each anonymised sensor a short
description and a unit, which is evidence the M1 channel map can use.

Its role is evaluation and label cross-check, not training.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pandas as pd

from faultline.data.telemetry.adapters.base import BaseAdapter, MemberKind, RawMember


@dataclass
class CareAdapter(BaseAdapter):
    """Reads the CARE farms A/B/C record into the canonical schema."""

    source_id: ClassVar[str] = "care"
    site_name: ClassVar[str] = "CARE farms A/B/C"

    PATTERNS: ClassVar[tuple[tuple[str, MemberKind], ...]] = (
        ("event_info", "status_events"),
        ("readme", "metadata"),
        ("feature_description", "metadata"),
        ("description", "metadata"),
        ("metadata", "metadata"),
        ("alarm", "alarm_log"),
        ("event", "status_events"),
        ("dataset", "scada_10min"),
    )

    CLASSIFICATION_SOURCE: ClassVar[str] = (
        "the file structure documented in the record README: Wind Farm <x>/event_info.csv, "
        "feature_description.csv and datasets/<event_id>.csv"
    )

    def load_scada(self, member: RawMember) -> pd.DataFrame:
        """Read one CARE farms A/B/C SCADA member.

        Args:
            member: Member classified as SCADA.

        Returns:
            A canonical wide table.

        Raises:
            NotImplementedError: Until the member layout is confirmed by inspection.
        """
        raise NotImplementedError(
            "TODO(m1): confirm the CARE dataset member layout (per-farm feature counts, "
            "resolution and whether values are physical or normalised); see data/cards/care.md"
        )

    def load_events(self, member: RawMember) -> pd.DataFrame | None:
        """Read one CARE farms A/B/C event member.

        Args:
            member: Member classified as an event table.

        Returns:
            A canonical events table, or ``None``.

        Raises:
            NotImplementedError: Until the member layout is confirmed by inspection.
        """
        raise NotImplementedError(
            "TODO(m1): parse the CARE event_info files and map their event descriptions onto the "
            "canonical events schema; see data/cards/care.md"
        )
