"""CARE to Compare adapter (Fraunhofer IEE, CC BY-SA 4.0).

Thirty-six turbines across three anonymised farms, 89 turbine-years, 95 datasets
of which 45 carry labelled anomaly events with descriptions.

Two things make this source different from the other three. Its licence is
share-alike, so it is evaluation-only and nothing derived from it is redistributed
(docs/DATA_LICENSES.md). And it is anonymised: channel names are ``sensor_NN``, and
the README says "the sensor data and time stamps are anonymized". The channel map is
therefore written per farm from the three ``feature_description.csv`` lookups, and the
timestamps are read as labels on a shifted calendar -- their spacing is real, their
dates are not (``absolute_time: false`` in the source specification).

The layout, per the README and confirmed on the staged archive:
``Wind Farm <x>/{event_info.csv, feature_description.csv, datasets/<event_id>.csv}``,
semicolon-separated. Each dataset is one turbine's history leading up to one event, so
two datasets of the same turbine can overlap in time. The dataset, not the turbine, is
the unit: its ``turbine_id`` is ``<farm>:asset<asset_id>:dataset<event_id>``, and the
event it was built around carries the same id.

Its role is evaluation and label cross-check, not training.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import pandas as pd

from faultline.data.telemetry.adapters.base import (
    BaseAdapter,
    FileAccount,
    MemberKind,
    RawMember,
    header_columns,
    load_channel_map,
    load_farm_blocks,
    read_csv_member,
    read_csv_member_columns,
    resolved_columns,
)
from faultline.data.telemetry.collapse import collapse_repeated_labels
from faultline.data.telemetry.schemas import EVENT_COLUMNS

TIME_STAMP = "time_stamp"
ASSET = "asset_id"

#: The turbine column of event_info. The README calls it ``asset``, and farm A's file
#: does; farms B and C name it ``asset_id``, as the datasets do (read 2026-09-10).
EVENT_INFO_ASSET: tuple[str, ...] = ("asset", "asset_id")

#: event_info columns besides the turbine, per the README.
EVENT_INFO_COLUMNS: tuple[str, ...] = (
    "event_id",
    "event_label",
    "event_start",
    "event_end",
    "event_description",
)


def dataset_turbine_id(farm: str, asset: object, dataset: object) -> str:
    """The identifier shared by a dataset's SCADA rows and the event it was built around.

    Args:
        farm: Farm id, such as ``farm_a``.
        asset: Anonymised turbine id.
        dataset: Dataset id, which is the event id.

    Returns:
        ``<farm>:asset<asset>:dataset<dataset>``.
    """
    return f"{farm}:asset{int(float(str(asset)))}:dataset{int(float(str(dataset)))}"


@dataclass
class CareAdapter(BaseAdapter):
    """Reads the CARE farms A/B/C record into the canonical schema.

    Attributes:
        farm_maps: Canonical channel to dataset column, per farm.
        farm_directories: Archive directory of each farm.
        farm_scales: Factors converting a farm's column to the canonical unit.
    """

    farm_maps: dict[str, dict[str, str]] = field(default_factory=dict)
    farm_directories: dict[str, str] = field(default_factory=dict)
    farm_scales: dict[str, dict[str, float]] = field(default_factory=dict)

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

    @classmethod
    def from_configs(cls, configs_dir: Path) -> CareAdapter:
        """Build the adapter with every farm's map loaded.

        Args:
            configs_dir: The repository ``configs`` directory.

        Returns:
            A configured adapter.
        """
        path = configs_dir / "data" / "channel_map" / f"{cls.source_id}.yaml"
        blocks = load_farm_blocks(path)
        return cls(
            channel_map=load_channel_map(path),
            farm_maps={farm: resolved_columns(block) for farm, block in blocks.items()},
            farm_directories={
                farm: str(block["directory"])
                for farm, block in blocks.items()
                if "directory" in block
            },
            farm_scales={
                farm: {str(k): float(v) for k, v in (block.get("scale") or {}).items()}
                for farm, block in blocks.items()
            },
        )

    def farm_of(self, member: RawMember) -> str:
        """Name the farm a member belongs to, from its archive directory.

        Args:
            member: A member of the archive.

        Returns:
            The farm id.

        Raises:
            RuntimeError: If the member sits in no directory the channel map names.
        """
        for farm, directory in self.farm_directories.items():
            if f"/{directory}/" in f"/{member.name}":
                return farm
        raise RuntimeError(
            f"{member.label} is in none of the farm directories the channel map names "
            f"({', '.join(self.farm_directories.values()) or 'none'})"
        )

    def load_scada_with_stats(self, member: RawMember) -> tuple[pd.DataFrame, FileAccount]:
        """Read one CARE dataset's mapped sensors into the canonical wide schema.

        Args:
            member: One ``datasets/<event_id>.csv``.

        Returns:
            A canonical wide table and the file's row accounting.

        Raises:
            RuntimeError: If the farm has no channel map or the dataset lacks its keys.
        """
        farm = self.farm_of(member)
        mapping = self.farm_maps.get(farm)
        if not mapping:
            raise RuntimeError(f"care: no channel map for {farm}")
        wanted = {column: canonical for canonical, column in mapping.items()}
        available = set(header_columns(member))
        if not {TIME_STAMP, ASSET} <= available:
            raise RuntimeError(f"{member.label}: no {TIME_STAMP!r} and {ASSET!r} columns")
        present = [column for column in wanted if column in available]

        frame = read_csv_member_columns(member, [TIME_STAMP, ASSET, *present])
        for column in present:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        for canonical, factor in self.farm_scales.get(farm, {}).items():
            target = mapping.get(canonical)
            if target is not None and target in frame.columns:
                frame[target] = frame[target] * factor
        collapsed, stats = collapse_repeated_labels(frame, [TIME_STAMP], present)

        assets = collapsed[ASSET].dropna().unique()
        if len(assets) != 1:
            raise RuntimeError(f"{member.label}: expected one asset, found {list(assets)}")
        dataset = member.name.rsplit("/", 1)[-1].removesuffix(".csv")
        turbine = dataset_turbine_id(farm, assets[0], dataset)

        result = collapsed.drop(columns=[ASSET]).rename(
            columns={TIME_STAMP: "timestamp_utc", **{c: wanted[c] for c in present}}
        )
        # An anonymised calendar: the spacing is real and the dates are not. Labelled
        # UTC only so the grid code has a timezone to carry; see absolute_time.
        result["timestamp_utc"] = pd.to_datetime(result["timestamp_utc"], errors="coerce", utc=True)
        result = result[result["timestamp_utc"].notna()]
        result.insert(0, "turbine_id", turbine)
        result.insert(0, "site", self.site_name)
        result.insert(0, "source", self.source_id)
        return result.reset_index(drop=True), FileAccount(member.label, turbine, stats)

    def load_events(self, member: RawMember) -> pd.DataFrame | None:
        """Read one farm's ``event_info.csv`` into the canonical events schema.

        One row per dataset: an ``anomaly`` event, with its root-cause description
        where the provider wrote one, or a ``normal`` window with none.

        Args:
            member: A farm's ``event_info.csv``.

        Returns:
            A canonical events table.

        Raises:
            RuntimeError: If the event_info columns are absent.
        """
        farm = self.farm_of(member)
        frame = read_csv_member(member)
        missing = [column for column in EVENT_INFO_COLUMNS if column not in frame.columns]
        asset_column = next((c for c in EVENT_INFO_ASSET if c in frame.columns), None)
        if asset_column is None:
            missing.insert(0, " or ".join(EVENT_INFO_ASSET))
        if missing or asset_column is None:
            raise RuntimeError(f"{member.label}: event_info is missing columns {missing}")
        label = frame["event_label"].astype("string").str.strip()
        description = frame["event_description"].astype("string").str.strip()
        events = pd.DataFrame(
            {
                "source": self.source_id,
                "site": self.site_name,
                "turbine_id": [
                    dataset_turbine_id(farm, asset, event)
                    for asset, event in zip(frame[asset_column], frame["event_id"], strict=True)
                ],
                "start_utc": pd.to_datetime(frame["event_start"], errors="coerce", utc=True),
                "end_utc": pd.to_datetime(frame["event_end"], errors="coerce", utc=True),
                "code": label,
                "message": description.where(description.notna() & (description != ""), None),
                "category": label,
                "is_fault": pd.Series([None] * len(frame), dtype="object"),
                "raw": frame.to_json(orient="records", lines=True).splitlines(),
            }
        )
        events = events[events["start_utc"].notna()]
        return events[list(EVENT_COLUMNS)].reset_index(drop=True)
