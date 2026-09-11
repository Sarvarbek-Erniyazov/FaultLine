"""Event labels per source, and the horizon labels every grid step carries.

Three sources publish three different kinds of event evidence, and each is turned into
canonical events by its own configured rule (``configs/data/events_v1.yaml``):

* **Kelmarsh, Penmanshiel** publish status strings. Each string maps to a category in
  the config, and ``is_fault`` follows from the category -- never from matching text in
  code. A string the config does not name is ``unmapped``, with ``is_fault`` unknown.
* **Hill of Towie** publishes seconds of downtime per 10-minute step. An event is a run
  of steps at or above a configured threshold. The provider's 12 described alarm codes
  carry a Stopping flag, and the stage measures how often the downtime series agrees
  with it.
* **CARE** publishes one labelled event per dataset; evaluation only.

Then every step of the cleaned grid is labelled for each configured horizon *H*: does a
fault event start in ``(t, t + H]``? No horizon is chosen as primary here.

The ``label`` stage reads the cleaned grid and the ingested events, writes one labels
table per turbine-year beside the cleaned grid, and reports base rates, event counts,
the unmapped-string fraction and the Stopping agreement.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from faultline.config import StrictModel, file_hash, load_config
from faultline.data.common.intervals import wilson_interval
from faultline.data.common.report import header_block, kv_table, section, table, top_values_table
from faultline.data.common.stage import StageResult
from faultline.data.telemetry.adapters import get_adapter
from faultline.data.telemetry.adapters.base import (
    BaseAdapter,
    RawMember,
    header_columns,
    read_csv_member,
)
from faultline.data.telemetry.downtime import read_downtime
from faultline.data.telemetry.events import EventConfig, label_horizon, normalize_message
from faultline.data.telemetry.harmonise import (
    CAUSES,
    EVENT_TABLE_COLUMNS,
    Cause,
    DowntimeAttribution,
    alarm_override_steps,
    downtime_stop_steps,
    empty_stop_steps,
    horizon_labels,
    select_events,
    status_stop_steps,
    to_seconds,
    wind_state,
)
from faultline.data.telemetry.pipeline import (
    TelemetryStage,
    ingest_dir,
    parquet_files,
    stage_source_dir,
)
from faultline.logging_utils import get_logger
from faultline.runs import RunContext

logger = get_logger(__name__)

STEP = pd.Timedelta(minutes=10)
UNMAPPED = "unmapped"
_IEC = re.compile(r'"IEC category":"([^"]*)"')
_STATUS = re.compile(r'"Status":"([^"]*)"')


# -------------------------------------------------------------------------------------
# configuration
# -------------------------------------------------------------------------------------


class StatusStringsConfig(StrictModel):
    """Status strings to categories, and categories to faults.

    Attributes:
        sources: Sources whose events are status strings.
        fault_categories: Categories whose events are faults.
        categories: Provider strings per category, as published.
    """

    sources: list[str]
    fault_categories: list[str]
    categories: dict[str, list[str]]

    @model_validator(mode="after")
    def _one_category_per_string(self) -> StatusStringsConfig:
        """Reject a string listed twice, or a fault category that is not defined.

        Raises:
            ValueError: On either.
        """
        undefined = [name for name in self.fault_categories if name not in self.categories]
        if undefined:
            raise ValueError(f"fault_categories names undefined categories {undefined}")
        seen: dict[str, str] = {}
        for category, strings in self.categories.items():
            for text in strings:
                key = normalize_message(text, EventConfig())
                if key in seen:
                    raise ValueError(
                        f"{text!r} is listed under both {seen[key]!r} and {category!r}"
                    )
                seen[key] = category
        return self

    def lookup(self, config: EventConfig) -> dict[str, str]:
        """Map each normalized string to its category.

        Args:
            config: Normalization settings, as the ingest applied them.

        Returns:
            Category per normalized string.
        """
        return {
            normalize_message(text, config): category
            for category, strings in self.categories.items()
            for text in strings
        }


class DowntimeConfig(StrictModel):
    """Events from a per-step downtime series.

    Attributes:
        sources: Sources whose events come from a downtime series.
        threshold_s: Downtime per step at or above which a step is down.
        sensitivity_thresholds_s: Thresholds the report also counts events at.
        cross_check_window_steps: Steps after the alarm's step searched for downtime.
    """

    sources: list[str]
    threshold_s: float = Field(gt=0)
    sensitivity_thresholds_s: list[float] = Field(default_factory=list)
    cross_check_window_steps: int = Field(default=1, ge=0)


class EventInfoConfig(StrictModel):
    """Events from a provider's labelled event table.

    Attributes:
        sources: Sources whose events come from an event_info table.
        fault_labels: Provider labels that are faults.
    """

    sources: list[str]
    fault_labels: list[str]


class StopClassesConfig(StrictModel):
    """A provider table of per-step stop-class timers, and the cause of each timer.

    Attributes:
        table: The provider table.
        fields: Timer field to cause.
    """

    table: str
    fields: dict[str, Cause]


class WindEnvelopeConfig(StrictModel):
    """The wind envelope, used as a diagnostic and a sensitivity check.

    Attributes:
        cut_in_ms: Wind below which a turbine would not be producing anyway.
        cut_out_ms: Wind above which it would be stopped for wind anyway.
        apply: Exclude narrow events starting outside the envelope. Off under rung (a)
            of ADR-0009, where the cause does the excluding.
        provenance: Where the two numbers come from.
    """

    cut_in_ms: float = Field(gt=0)
    cut_out_ms: float = Field(gt=0)
    apply: bool = False
    provenance: str

    @model_validator(mode="after")
    def _ordered(self) -> WindEnvelopeConfig:
        """Reject a cut-out at or below the cut-in.

        Raises:
            ValueError: If the envelope is empty.
        """
        if self.cut_out_ms <= self.cut_in_ms:
            raise ValueError("wind_envelope.cut_out_ms must be above cut_in_ms")
        return self


class HarmonisedConfig(StrictModel):
    """The one event rule for every site, and each source's translation into it (ADR-0009).

    Attributes:
        narrow_causes: Causes the narrow (primary) label keeps.
        min_duration_s: Shortest event kept, in seconds of downtime of the chosen causes.
        sensitivity_min_duration_s: Durations the report also counts events at.
        stop_status: Provider status marking a status row as a stop.
        category_causes: Configured status category to cause.
        stop_classes: Per-step stop-class timers, where a source publishes them.
        code_causes: Described alarm codes whose cause overrides the timer.
        emergency_stop_strings: Status strings counted as technical in a sensitivity check.
        wind_envelope: The wind envelope.
    """

    narrow_causes: list[Cause]
    min_duration_s: float = Field(gt=0)
    sensitivity_min_duration_s: list[float] = Field(default_factory=list)
    stop_status: str
    category_causes: dict[str, Cause]
    stop_classes: StopClassesConfig
    code_causes: dict[str, Cause] = Field(default_factory=dict)
    emergency_stop_strings: list[str] = Field(default_factory=list)
    wind_envelope: WindEnvelopeConfig

    @property
    def durations(self) -> list[float]:
        """Every duration the report counts at, the rule's own included, ascending."""
        return sorted({*self.sensitivity_min_duration_s, self.min_duration_s})


class EventLabelsConfig(StrictModel):
    """Top level of ``configs/data/events_v*.yaml``.

    Attributes:
        version: Version of this file.
        status_strings: The status-string rule.
        downtime: The downtime rule.
        event_info: The event_info rule.
        harmonised: The one event rule for every site; required from version 2.
    """

    version: int
    status_strings: StatusStringsConfig
    downtime: DowntimeConfig
    event_info: EventInfoConfig
    harmonised: HarmonisedConfig | None = None

    @model_validator(mode="after")
    def _harmonised_is_complete(self) -> EventLabelsConfig:
        """Require the harmonised rule from v2, a cause for every category, one threshold.

        Raises:
            ValueError: If v2 omits the rule, a status category has no cause, or the
                downtime cross-check threshold differs from the rule's minimum duration.
        """
        rule = self.harmonised
        if rule is None:
            if self.version >= 2:
                raise ValueError("an events file from version 2 must define `harmonised`")
            return self
        missing = sorted({*self.status_strings.categories, UNMAPPED} - set(rule.category_causes))
        if missing:
            raise ValueError(f"harmonised.category_causes gives no cause for {missing}")
        if self.downtime.threshold_s != rule.min_duration_s:
            raise ValueError(
                f"downtime.threshold_s ({self.downtime.threshold_s:g}) must equal "
                f"harmonised.min_duration_s ({rule.min_duration_s:g}) so they cannot drift"
            )
        return self


# -------------------------------------------------------------------------------------
# events per source
# -------------------------------------------------------------------------------------


def categorize_status_events(
    events: pd.DataFrame, rule: StatusStringsConfig, config: EventConfig
) -> pd.DataFrame:
    """Give every status event its configured category and a fault flag.

    The ingest leaves the provider's own Status in ``category``; it moves to
    ``provider_status`` here, with the IEC availability category from the raw row beside
    it, and ``category`` becomes the configured one.

    Args:
        events: Canonical events with normalized messages.
        rule: The status-string rule.
        config: Normalization settings, as the ingest applied them.

    Returns:
        The events with ``category``, ``is_fault``, ``provider_status`` and ``provider_iec``.
    """
    result = events.copy()
    raw = result["raw"].fillna("").astype(str)
    result["provider_status"] = raw.str.extract(_STATUS, expand=False)
    result["provider_iec"] = raw.str.extract(_IEC, expand=False)
    lookup = rule.lookup(config)
    messages = [normalize_message(value, config) for value in result["message"]]
    result["category"] = [lookup.get(message, UNMAPPED) for message in messages]
    faults = set(rule.fault_categories)
    result["is_fault"] = pd.array(
        [None if c == UNMAPPED else c in faults for c in result["category"]], dtype="boolean"
    )
    return result


def downtime_events(
    downtime: pd.DataFrame, threshold_s: float, source: str, site: str
) -> pd.DataFrame:
    """Turn a downtime series into events: one per run of down steps.

    A step is down when its downtime is at least ``threshold_s``. A run is a sequence of
    consecutive down steps of one turbine; a missing step ends it.

    Args:
        downtime: ``timestamp_utc``, ``turbine_id``, ``downtime_s``.
        threshold_s: Downtime at or above which a step is down.
        source: Source identifier.
        site: Site name.

    Returns:
        Canonical events, category ``shutdown``, is_fault ``True``.
    """
    frame = downtime.sort_values(["turbine_id", "timestamp_utc"]).reset_index(drop=True)
    down = (frame["downtime_s"] >= threshold_s).to_numpy()
    turbine = frame["turbine_id"].to_numpy()
    stamps = frame["timestamp_utc"]
    contiguous = (
        (turbine[1:] == turbine[:-1])
        & ((stamps.iloc[1:].to_numpy() - stamps.iloc[:-1].to_numpy()) == STEP)
        if len(frame) > 1
        else np.array([], dtype=bool)
    )
    continues = np.concatenate([[False], contiguous & down[:-1]]) if len(frame) else down
    starts = down & ~continues
    run = np.cumsum(starts)
    selected = frame.loc[down].assign(run=run[down])
    if selected.empty:
        return pd.DataFrame(
            columns=[
                "source",
                "site",
                "turbine_id",
                "start_utc",
                "end_utc",
                "code",
                "message",
                "category",
                "is_fault",
                "raw",
            ]
        )
    grouped = selected.groupby("run")
    runs = pd.DataFrame(
        {
            "turbine_id": grouped["turbine_id"].first(),
            "start_utc": grouped["timestamp_utc"].min(),
            "end_utc": grouped["timestamp_utc"].max() + STEP,
            "steps": grouped.size(),
            "downtime_s": grouped["downtime_s"].sum(),
        }
    ).reset_index(drop=True)
    return pd.DataFrame(
        {
            "source": source,
            "site": site,
            "turbine_id": runs["turbine_id"],
            "start_utc": runs["start_utc"],
            "end_utc": runs["end_utc"],
            "code": None,
            "message": None,
            "category": "shutdown",
            "is_fault": pd.array([True] * len(runs), dtype="boolean"),
            "raw": [
                json.dumps({"steps": int(s), "downtime_s": float(d)})
                for s, d in zip(runs["steps"], runs["downtime_s"], strict=True)
            ],
        }
    )


def stopping_cross_check(
    alarms: pd.DataFrame,
    downtime: pd.DataFrame,
    stopping: dict[str, bool],
    threshold_s: float,
    window_steps: int,
) -> pd.DataFrame:
    """Measure how often the downtime series agrees with the provider's Stopping flag.

    An occurrence of a described code *shows downtime* when a step with downtime of at
    least ``threshold_s`` falls between the step its ``TimeOn`` opens in and
    ``window_steps`` steps after the step its ``TimeOff`` opens in (``TimeOn`` when the
    log has no ``TimeOff``). It agrees when it shows downtime exactly when the code is
    described as stopping.

    Args:
        alarms: Canonical alarm events with ``code``, ``start_utc`` and ``end_utc``.
        downtime: ``timestamp_utc``, ``turbine_id``, ``downtime_s``.
        stopping: Stopping flag per described code.
        threshold_s: Downtime at or above which a step is down.
        window_steps: Steps after the last step searched.

    Returns:
        One row per described code: occurrences, occurrences showing downtime, and the
        agreement rate.
    """
    subset = alarms[alarms["code"].astype(str).isin(stopping)].copy()
    shown = np.zeros(len(subset), dtype=bool)
    if not subset.empty:
        down = downtime[downtime["downtime_s"] >= threshold_s]
        first = subset["start_utc"].dt.floor("10min")
        last = subset["end_utc"].fillna(subset["start_utc"]).dt.floor("10min") + STEP * window_steps
        subset = subset.assign(_first=first, _last=last, _pos=np.arange(len(subset)))
        for turbine, group in subset.groupby("turbine_id"):
            steps = np.sort(down.loc[down["turbine_id"] == turbine, "timestamp_utc"].to_numpy())
            lo = np.searchsorted(steps, group["_first"].to_numpy(), side="left")
            hi = np.searchsorted(steps, group["_last"].to_numpy(), side="right")
            shown[group["_pos"].to_numpy()] = hi > lo
    subset["shows_downtime"] = shown
    subset["stopping"] = subset["code"].astype(str).map(stopping)
    subset["agrees"] = subset["shows_downtime"] == subset["stopping"]
    rows = [
        {
            "code": str(code),
            "stopping": stopping[str(code)],
            "occurrences": int(len(group)),
            "showing_downtime": int(group["shows_downtime"].sum()),
            "agreeing": int(group["agrees"].sum()),
        }
        for code, group in subset.groupby("code")
    ]
    result = pd.DataFrame(
        rows, columns=["code", "stopping", "occurrences", "showing_downtime", "agreeing"]
    )
    result["agreement"] = result["agreeing"] / result["occurrences"].where(
        result["occurrences"] > 0
    )
    return result.sort_values("occurrences", ascending=False).reset_index(drop=True)


def horizon_name(steps: int) -> str:
    """Column name of a horizon label, in hours where the horizon is whole hours."""
    minutes = steps * 10
    return f"event_within_{minutes // 60}h" if minutes % 60 == 0 else f"event_within_{minutes}min"


def label_turbine_year(
    grid: pd.DataFrame,
    events: pd.DataFrame,
    horizons: Sequence[int],
    config: EventConfig,
    core: Sequence[str],
) -> pd.DataFrame:
    """Label one turbine-year of the cleaned grid for every horizon.

    Args:
        grid: Cleaned rows of one turbine, on the 10-minute grid.
        events: Fault events of that turbine.
        horizons: Horizons, in steps.
        config: Event settings.
        core: Core channels, for the ``has_data`` column.

    Returns:
        One row per grid step: identity, ``has_data`` and one boolean per horizon.
    """
    stamps = pd.to_datetime(grid["timestamp_utc"], utc=True).reset_index(drop=True)
    present = [name for name in core if name in grid.columns]
    labels = pd.DataFrame(
        {
            "source": grid["source"].to_numpy(),
            "turbine_id": grid["turbine_id"].to_numpy(),
            "timestamp_utc": stamps,
            "has_data": grid[present].notna().any(axis=1).to_numpy()
            if present
            else np.zeros(len(grid), dtype=bool),
        }
    )
    for steps in horizons:
        labels[horizon_name(steps)] = label_horizon(
            stamps, events, config, fault_only=True, horizon_steps=steps
        ).to_numpy()
    return labels


# -------------------------------------------------------------------------------------
# the stage
# -------------------------------------------------------------------------------------


@dataclass
class SiteLabels:
    """What labelling one source produced, for the report."""

    source: str
    turbines: int = 0
    steps: int = 0
    steps_with_data: int = 0
    positives: dict[str, int] = field(default_factory=dict)
    positives_with_data: dict[str, int] = field(default_factory=dict)
    fault_events: int = 0
    events_by_category: dict[str, int] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


def grid_years(paths: Sequence[Path]) -> set[int]:
    """The years a set of turbine-year files covers, read from their names.

    Args:
        paths: Turbine-year files named ``<turbine>__<year>.parquet``.

    Returns:
        The calendar years.
    """
    years = set()
    for path in paths:
        stem = path.stem.rsplit("__", 1)
        if len(stem) == 2 and stem[1].isdigit():
            years.add(int(stem[1]))
    return years


class LabelStage(TelemetryStage):
    """Build each source's events by its configured rule and label the cleaned grid."""

    name: ClassVar[str] = "label"

    def run(self, ctx: RunContext) -> StageResult:
        """Label every cleaned turbine-year of the selected sources.

        Args:
            ctx: Active run context.

        Returns:
            Base rates, event counts, the unmapped fraction and the Stopping agreement.

        Raises:
            ValueError: If the configuration names no labels file or no horizons.
        """
        self._meta = ctx.meta
        events_cfg = self.config.events
        if not events_cfg.labels_config or not events_cfg.horizons_steps:
            raise ValueError("events.labels_config and events.horizons_steps are required")
        rules_path = self.paths.repo_root / events_cfg.labels_config
        rules = load_config(rules_path, EventLabelsConfig)
        (ctx.run_dir / rules_path.name).write_text(
            rules_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        if rules.harmonised is not None:
            return self._run_harmonised(rules, rules.harmonised, rules_path)
        core = list(self.config.core_channels) or list(self.config.channels)
        sites: dict[str, SiteLabels] = {}
        outputs: list[Path] = []
        rows_in = rows_out = 0

        for source in self.sources:
            grid_files = parquet_files(stage_source_dir(self.paths, "cleaned", source))
            events_path = ingest_dir(self.paths, source) / "events.parquet"
            if not grid_files or not events_path.is_file():
                logger.warning("%s: nothing to label (no cleaned grid or no events)", source)
                continue
            events, site = self._events(source, events_path, rules, grid_files)
            destination = stage_source_dir(self.paths, "cleaned", source) / "labels"
            destination.mkdir(parents=True, exist_ok=True)
            events.to_parquet(destination / "events_labelled.parquet", index=False)
            faults = events[events["is_fault"].fillna(False).astype(bool)]
            site.fault_events = len(faults)
            site.events_by_category = {
                str(k): int(v) for k, v in events["category"].value_counts(dropna=False).items()
            }
            by_turbine = {str(k): g for k, g in faults.groupby("turbine_id")}
            turbines: set[str] = set()
            for path in grid_files:
                grid = pd.read_parquet(path)
                rows_in += len(grid)
                if grid.empty:
                    continue
                turbine = str(grid["turbine_id"].iloc[0])
                turbines.add(turbine)
                labels = label_turbine_year(
                    grid,
                    by_turbine.get(turbine, faults.iloc[0:0]),
                    events_cfg.horizons_steps,
                    events_cfg,
                    core,
                )
                out = destination / path.name
                labels.to_parquet(out, index=False)
                outputs.append(out)
                rows_out += len(labels)
                site.steps += len(labels)
                site.steps_with_data += int(labels["has_data"].sum())
                for steps in events_cfg.horizons_steps:
                    name = horizon_name(steps)
                    site.positives[name] = site.positives.get(name, 0) + int(labels[name].sum())
                    site.positives_with_data[name] = site.positives_with_data.get(name, 0) + int(
                        (labels[name] & labels["has_data"]).sum()
                    )
            site.turbines = len(turbines)
            sites[source] = site

        return StageResult(
            name=self.name,
            rows_in=rows_in,
            rows_out=rows_out,
            counters={"sources": len(sites)},
            details={
                "sites": sites,
                "horizons": [horizon_name(s) for s in events_cfg.horizons_steps],
                "labels_config": events_cfg.labels_config,
                "labels_config_hash": file_hash(rules_path),
            },
            outputs=outputs,
        )

    def _events(
        self,
        source: str,
        events_path: Path,
        rules: EventLabelsConfig,
        grid_files: Sequence[Path],
    ) -> tuple[pd.DataFrame, SiteLabels]:
        """Build one source's categorized events by its configured rule.

        Args:
            source: Source identifier.
            events_path: The source's ingested events.
            rules: The labelling rules.
            grid_files: The source's cleaned turbine-years.

        Returns:
            The events with category and is_fault, and the site record so far.

        Raises:
            ValueError: If no rule names the source.
        """
        site = SiteLabels(source=source)
        ingested = pd.read_parquet(events_path)
        if source in rules.status_strings.sources:
            events = categorize_status_events(ingested, rules.status_strings, self.config.events)
            site.extra["status"] = _status_summary(events)
            return events, site
        if source in rules.event_info.sources:
            events = ingested.copy()
            labels = set(rules.event_info.fault_labels)
            events["is_fault"] = pd.array(
                [c in labels for c in events["category"].astype(str)], dtype="boolean"
            )
            return events, site
        if source in rules.downtime.sources:
            return self._downtime_events(source, ingested, rules.downtime, grid_files, site)
        raise ValueError(f"{source}: no labelling rule in {self.config.events.labels_config}")

    def _downtime_events(
        self,
        source: str,
        alarms: pd.DataFrame,
        rule: DowntimeConfig,
        grid_files: Sequence[Path],
        site: SiteLabels,
    ) -> tuple[pd.DataFrame, SiteLabels]:
        """Build events from the downtime series and cross-check it against the alarm log.

        Args:
            source: Source identifier.
            alarms: The source's ingested alarm events.
            rule: The downtime rule.
            grid_files: The source's cleaned turbine-years.
            site: The site record to fill.

        Returns:
            The downtime events and the site record.

        Raises:
            FileNotFoundError: If the downtime series or code descriptions are not staged.
        """
        adapter = get_adapter(source, self.paths.configs_dir)
        members = adapter.discover(self.paths.source_dir("raw", "telemetry", source))
        series = [m for m in members if m.kind == "downtime_series"]
        if not series:
            raise FileNotFoundError(f"{source}: no downtime series staged")
        years = grid_years(grid_files)
        # A step late in December looks into January of the next year.
        downtime = read_downtime(series[0], years | {year + 1 for year in years})
        site_name = str(alarms["site"].iloc[0]) if not alarms.empty else source
        events = downtime_events(downtime, rule.threshold_s, source, site_name)

        sensitivity = {}
        for threshold in sorted({*rule.sensitivity_thresholds_s, rule.threshold_s}):
            counted = downtime_events(downtime, threshold, source, site_name)
            sensitivity[threshold] = int(len(counted))
        site.extra["sensitivity"] = sensitivity
        site.extra["down_steps"] = int((downtime["downtime_s"] >= rule.threshold_s).sum())
        site.extra["downtime_rows"] = int(len(downtime))

        descriptions = next(
            (
                m
                for m in members
                if adapter.CODE_DESCRIPTIONS and m.archive.name == adapter.CODE_DESCRIPTIONS
            ),
            None,
        )
        if descriptions is None:
            raise FileNotFoundError(f"{source}: {adapter.CODE_DESCRIPTIONS} is not staged")
        stopping = _stopping_flags(read_csv_member(descriptions))
        in_years = alarms[alarms["start_utc"].dt.year.isin(years)]
        checks = {
            threshold: stopping_cross_check(
                in_years, downtime, stopping, threshold, rule.cross_check_window_steps
            )
            for threshold in sorted({*rule.sensitivity_thresholds_s, rule.threshold_s})
        }
        site.extra["cross_check"] = checks
        site.extra["threshold"] = rule.threshold_s
        site.extra["window_steps"] = rule.cross_check_window_steps
        return events, site

    def report(self, result: StageResult) -> str:
        """Render the label report.

        Args:
            result: Result returned by :meth:`run`.

        Returns:
            A Markdown document.

        Raises:
            RuntimeError: If called before :meth:`run`.
        """
        if self._meta is None:
            raise RuntimeError("report() called before run(); the run metadata is unknown")
        if result.details.get("harmonised"):
            return render_harmonised_report(self._meta, result)
        return render_label_report(self._meta, result)

    # ---------------------------------------------------------------------------------
    # v2: the harmonised rule (ADR-0009)
    # ---------------------------------------------------------------------------------

    def _run_harmonised(
        self, rules: EventLabelsConfig, rule: HarmonisedConfig, rules_path: Path
    ) -> StageResult:
        """Reduce every source to seconds down per step by cause, apply one rule, label.

        Args:
            rules: The labelling file.
            rule: Its harmonised block.
            rules_path: Where the file was read from.

        Returns:
            Both label sets per site, the sensitivity counts and the diagnostics.
        """
        events_cfg = self.config.events
        core = list(self.config.core_channels) or list(self.config.channels)
        sites: dict[str, HarmonisedSite] = {}
        outputs: list[Path] = []
        rows_in = rows_out = 0
        for source in self.sources:
            grid_files = parquet_files(stage_source_dir(self.paths, "cleaned", source))
            events_path = ingest_dir(self.paths, source) / "events.parquet"
            if not grid_files or not events_path.is_file():
                logger.warning("%s: nothing to label (no cleaned grid or no events)", source)
                continue
            destination = stage_source_dir(self.paths, "cleaned", source) / "labels"
            destination.mkdir(parents=True, exist_ok=True)
            for stale in destination.glob("*.parquet"):
                stale.unlink()
            site = HarmonisedSite(source=source)
            covered = grid_coverage(grid_files)
            site.turbines = len(covered)
            site.steps = sum(len(stamps) for stamps in covered.values())
            ingested = pd.read_parquet(events_path)
            built = self._source_stops(source, ingested, rules, rule, grid_files, covered, site)

            narrow_in = in_grid(built.narrow, covered)
            broad_in = in_grid(built.broad, covered)
            site.events = {"narrow": int(narrow_in.sum()), "broad": int(broad_in.sum())}
            site.causes = {
                str(k): int(v)
                for k, v in built.broad.loc[broad_in, "dominant_cause"].value_counts().items()
            }
            site.by_year = _events_by_year(
                covered, {"narrow": built.narrow[narrow_in], "broad": built.broad[broad_in]}
            )
            for name, table_ in (("narrow", built.narrow), ("broad", built.broad)):
                path = destination / f"events_{name}.parquet"
                table_.assign(in_grid=in_grid(table_, covered)).to_parquet(path, index=False)
                outputs.append(path)
            if not built.stream.empty:
                path = destination / "status_stream.parquet"
                built.stream.to_parquet(path, index=False)
                outputs.append(path)

            by_set = {
                "narrow": {str(k): g for k, g in built.narrow.groupby("turbine_id")},
                "broad": {str(k): g for k, g in built.broad.groupby("turbine_id")},
            }
            coverage = {"narrow": built.narrow_covered, "broad": built.broad_covered}
            envelope = rule.wind_envelope
            for path in grid_files:
                grid = pd.read_parquet(path)
                rows_in += len(grid)
                if grid.empty:
                    continue
                turbine = str(grid["turbine_id"].iloc[0])
                labels = _label_both_sets(
                    grid, by_set, coverage, events_cfg.horizons_steps, core, site
                )
                narrow = by_set["narrow"].get(turbine)
                if narrow is not None and "wind_speed_ms" in grid.columns:
                    stamps = pd.to_datetime(grid["timestamp_utc"], utc=True)
                    inside = narrow[
                        (narrow["start_utc"] >= stamps.min())
                        & (narrow["start_utc"] <= stamps.max())
                    ]
                    states = wind_state(
                        inside,
                        grid.assign(timestamp_utc=stamps),
                        envelope.cut_in_ms,
                        envelope.cut_out_ms,
                    )
                    for state, count in states.value_counts().items():
                        site.wind[str(state)] = site.wind.get(str(state), 0) + int(count)
                out = destination / path.name
                labels.to_parquet(out, index=False)
                outputs.append(out)
                rows_out += len(labels)
            sites[source] = site

        return StageResult(
            name=self.name,
            rows_in=rows_in,
            rows_out=rows_out,
            counters={"sources": len(sites)},
            details={
                "harmonised": True,
                "sites": sites,
                "horizons": [horizon_name(s) for s in events_cfg.horizons_steps],
                "horizons_steps": list(events_cfg.horizons_steps),
                "labels_config": events_cfg.labels_config,
                "labels_config_hash": file_hash(rules_path),
                "rule": rule.model_dump(mode="json"),
                "cross_check_window_steps": rules.downtime.cross_check_window_steps,
            },
            outputs=outputs,
        )

    def _source_stops(
        self,
        source: str,
        ingested: pd.DataFrame,
        rules: EventLabelsConfig,
        rule: HarmonisedConfig,
        grid_files: Sequence[Path],
        covered: dict[str, np.ndarray],
        site: HarmonisedSite,
    ) -> SourceStops:
        """Build one source's per-step stop table and both label sets.

        Args:
            source: Source identifier.
            ingested: The source's ingested events.
            rules: The labelling file.
            rule: Its harmonised block.
            grid_files: The source's cleaned turbine-years.
            covered: Grid steps per turbine, integer seconds.
            site: The site record to fill.

        Returns:
            The stops, both event tables, what each covers, and the status stream.

        Raises:
            ValueError: If no rule names the source.
        """
        if source in rules.status_strings.sources:
            built = self._status_stops(ingested, rules, rule, covered, site)
        elif source in rules.downtime.sources:
            built = self._downtime_stops(source, ingested, rules, rule, grid_files, covered, site)
        elif source in rules.event_info.sources:
            return _event_info_stops(ingested, rules.event_info, covered, site)
        else:
            raise ValueError(f"{source}: no labelling rule in {self.config.events.labels_config}")
        for duration in rule.durations:
            for name, causes in (("narrow", rule.narrow_causes), ("broad", list(CAUSES))):
                counted = select_events(built.steps, causes, duration)
                site.sensitivity.setdefault(name, {})[duration] = int(
                    in_grid(counted, covered).sum()
                )
        built.narrow = select_events(built.steps, rule.narrow_causes, rule.min_duration_s)
        built.broad = select_events(built.steps, list(CAUSES), rule.min_duration_s)
        return built

    def _status_stops(
        self,
        ingested: pd.DataFrame,
        rules: EventLabelsConfig,
        rule: HarmonisedConfig,
        covered: dict[str, np.ndarray],
        site: HarmonisedSite,
    ) -> SourceStops:
        """Senvion: provider Stop rows, each with its configured category's cause.

        Args:
            ingested: The source's ingested status rows.
            rules: The labelling file.
            rule: Its harmonised block.
            covered: Grid steps per turbine, integer seconds.
            site: The site record to fill.

        Returns:
            The per-step stops and the status stream; the event tables are set later.
        """
        events = categorize_status_events(ingested, rules.status_strings, self.config.events)
        causes = events["category"].map(rule.category_causes).fillna("unknown")
        is_stop = (events["provider_status"] == rule.stop_status).to_numpy()
        stops = events[is_stop]
        steps, no_interval = status_stop_steps(stops, causes[is_stop])

        duration = (stops["end_utc"] - stops["start_utc"]).dt.total_seconds().to_numpy()
        technical = (causes[is_stop] == "technical").to_numpy()
        on_grid = in_grid(stops, covered)
        site.rows = {"any": int((technical & on_grid).sum())}
        for threshold in rule.durations:
            site.rows[f"{threshold:g}"] = int((technical & on_grid & (duration >= threshold)).sum())

        emergency = {
            normalize_message(text, self.config.events) for text in rule.emergency_stop_strings
        }
        flagged = events["message"].isin(emergency)
        alternative = causes.where(~flagged, "technical")
        steps_e, _ = status_stop_steps(stops, alternative[is_stop])
        narrow_e = select_events(steps_e, rule.narrow_causes, rule.min_duration_s)
        site.emergency = int(in_grid(narrow_e, covered).sum())
        site.extra.update(
            {
                "stop_rows": int(is_stop.sum()),
                "stop_rows_without_interval": no_interval,
                "emergency_stop_rows": int((flagged.to_numpy() & is_stop).sum()),
                "schema": {"status export": _raw_keys(ingested)},
            }
        )
        stream = pd.DataFrame(
            {
                "source": events["source"],
                "turbine_id": events["turbine_id"].astype(str),
                "start_utc": events["start_utc"],
                "end_utc": events["end_utc"],
                "code": events["code"].astype("string"),
                "message": events["message"].astype("string"),
                "provider_status": events["provider_status"].astype("string"),
                "category": events["category"].astype("string"),
                "cause": causes.astype("string"),
            }
        )
        site.stream = {
            "rows": len(stream),
            "provider Warning rows": int((events["provider_status"] == "Warning").sum()),
            "provider Stop rows": int(is_stop.sum()),
        }
        return SourceStops(
            steps=steps, narrow_covered=covered, broad_covered=covered, stream=stream
        )

    def _downtime_stops(
        self,
        source: str,
        alarms: pd.DataFrame,
        rules: EventLabelsConfig,
        rule: HarmonisedConfig,
        grid_files: Sequence[Path],
        covered: dict[str, np.ndarray],
        site: HarmonisedSite,
    ) -> SourceStops:
        """Hill of Towie: the downtime series, split into causes by the stop-class timers.

        Args:
            source: Source identifier.
            alarms: The source's ingested alarm log.
            rules: The labelling file.
            rule: Its harmonised block.
            grid_files: The source's cleaned turbine-years.
            covered: Grid steps per turbine, integer seconds.
            site: The site record to fill.

        Returns:
            The per-step stops, what each label set covers, and the status stream.

        Raises:
            FileNotFoundError: If the downtime series or code descriptions are not staged.
        """
        adapter = get_adapter(source, self.paths.configs_dir)
        members = adapter.discover(self.paths.source_dir("raw", "telemetry", source))
        series = [m for m in members if m.kind == "downtime_series"]
        if not series:
            raise FileNotFoundError(f"{source}: no downtime series staged")
        years = grid_years(grid_files)
        # A step late in December looks into January of the next year.
        downtime = read_downtime(series[0], years | {year + 1 for year in years})
        fields = rule.stop_classes.fields
        classes = adapter.read_stop_classes(members, years, rule.stop_classes.table, list(fields))
        overrides = alarm_override_steps(alarms, rule.code_causes)
        steps, attribution = downtime_stop_steps(
            downtime, classes, fields, overrides, count_steps=covered
        )
        descriptions = _code_descriptions(adapter, members)
        stopping = _stopping_flags(descriptions)
        described = {
            str(int(code)): str(text).strip()
            for code, text in zip(
                descriptions["Alarm Code"], descriptions["Description"], strict=True
            )
        }
        in_years = alarms[alarms["start_utc"].dt.year.isin(years)]
        site.extra.update(
            {
                "attribution": attribution,
                "descriptions": described,
                "cross_check": {
                    threshold: stopping_cross_check(
                        in_years,
                        downtime,
                        stopping,
                        threshold,
                        rules.downtime.cross_check_window_steps,
                    )
                    for threshold in rule.durations
                },
                "schema": _hill_of_towie_schema(members, series[0], rule.stop_classes.table),
                "stop_class_rows": len(classes),
            }
        )
        code = alarms["code"].astype(str)
        status = np.where(
            code.isin([c for c, flag in stopping.items() if flag]),
            "stopping",
            np.where(code.isin(list(stopping)), "non-stopping", "undescribed"),
        )
        stream = pd.DataFrame(
            {
                "source": alarms["source"],
                "turbine_id": alarms["turbine_id"].astype(str),
                "start_utc": alarms["start_utc"],
                "end_utc": alarms["end_utc"],
                "code": code.astype("string"),
                "message": code.map(described).astype("string"),
                "provider_status": pd.Series(status, index=alarms.index, dtype="string"),
                "category": pd.Series(pd.NA, index=alarms.index, dtype="string"),
                "cause": code.map(rule.code_causes).fillna("unknown").astype("string"),
            }
        )
        site.stream = {
            "rows": len(stream),
            **{f"{k} codes": int(v) for k, v in pd.Series(status).value_counts().items()},
        }
        return SourceStops(
            steps=steps,
            narrow_covered=_coverage(classes),
            broad_covered=_coverage(downtime),
            stream=stream,
        )


# -------------------------------------------------------------------------------------
# v2 helpers
# -------------------------------------------------------------------------------------

#: 10-minute steps in a mean calendar year.
STEPS_PER_YEAR = 6 * 24 * 365.25

LABEL_SETS: tuple[str, ...] = ("narrow", "broad")


def label_column(label_set: str, steps: int) -> str:
    """Column name of one label set at one horizon, e.g. ``narrow_within_1h``."""
    return f"{label_set}_{horizon_name(steps).removeprefix('event_')}"


@dataclass
class HarmonisedSite:
    """What labelling one source under the harmonised rule produced, for the report."""

    source: str
    turbines: int = 0
    steps: int = 0
    steps_with_data: int = 0
    events: dict[str, int] = field(default_factory=dict)
    sensitivity: dict[str, dict[float, int]] = field(default_factory=dict)
    positives: dict[str, int] = field(default_factory=dict)
    known: dict[str, int] = field(default_factory=dict)
    positives_with_data: dict[str, int] = field(default_factory=dict)
    known_with_data: dict[str, int] = field(default_factory=dict)
    causes: dict[str, int] = field(default_factory=dict)
    wind: dict[str, int] = field(default_factory=dict)
    rows: dict[str, int] = field(default_factory=dict)
    emergency: int | None = None
    stream: dict[str, int] = field(default_factory=dict)
    by_year: dict[int, dict[str, int]] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    #: One labelled event per dataset (CARE): reported per dataset, never beside the
    #: per-step rates of the other sites (ADR-0010).
    dataset_level: bool = False

    @property
    def turbine_years(self) -> float:
        """Grid time in turbine-years."""
        return self.steps / STEPS_PER_YEAR


def _events_by_year(
    covered: dict[str, np.ndarray], events: dict[str, pd.DataFrame]
) -> dict[int, dict[str, int]]:
    """Grid steps and events of each set per calendar year."""
    result: dict[int, dict[str, int]] = {}
    if covered:
        seconds = np.concatenate(list(covered.values()))
        years = pd.DatetimeIndex(pd.to_datetime(seconds, unit="s", utc=True)).year
        for year, count in pd.Series(years).value_counts().items():
            result.setdefault(int(str(year)), {})["steps"] = int(count)
    for name, table_ in events.items():
        starts = pd.to_datetime(table_["start_utc"], utc=True).dt.year
        for year, count in starts.value_counts().items():
            result.setdefault(int(str(year)), {})[name] = int(count)
    return dict(sorted(result.items()))


@dataclass
class SourceStops:
    """One source reduced to the common form.

    Attributes:
        steps: The per-step stop table.
        narrow_covered: Steps per turbine the narrow label's evidence covers.
        broad_covered: Steps per turbine the broad label's evidence covers.
        stream: The status rows the text pathway reads as inputs.
        narrow: Narrow events.
        broad: Broad events.
    """

    steps: pd.DataFrame
    narrow_covered: dict[str, np.ndarray]
    broad_covered: dict[str, np.ndarray]
    stream: pd.DataFrame
    narrow: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=list(EVENT_TABLE_COLUMNS))
    )
    broad: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=list(EVENT_TABLE_COLUMNS))
    )


def _coverage(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Sorted step seconds per turbine of a ``turbine_id``/``timestamp_utc`` table."""
    if frame.empty:
        return {}
    seconds = to_seconds(frame["timestamp_utc"])
    turbines = frame["turbine_id"].astype(str).to_numpy()
    return {
        str(turbine): np.unique(seconds[index])
        for turbine, index in pd.Series(turbines).groupby(turbines).indices.items()
    }


def grid_coverage(grid_files: Sequence[Path]) -> dict[str, np.ndarray]:
    """Grid steps per turbine across every cleaned turbine-year."""
    parts = [pd.read_parquet(path, columns=["turbine_id", "timestamp_utc"]) for path in grid_files]
    frames = [part for part in parts if not part.empty]
    return _coverage(pd.concat(frames, ignore_index=True)) if frames else {}


def in_grid(events: pd.DataFrame, covered: dict[str, np.ndarray]) -> np.ndarray:
    """Whether each event starts in a step of its turbine's cleaned grid."""
    mask = np.zeros(len(events), dtype=bool)
    if events.empty:
        return mask
    start = to_seconds(pd.to_datetime(events["start_utc"], utc=True).dt.floor("10min"))
    turbines = events["turbine_id"].astype(str).to_numpy()
    for turbine, index in pd.Series(turbines).groupby(turbines).indices.items():
        steps = covered.get(str(turbine))
        if steps is None or len(steps) == 0:
            continue
        wanted = start[index]
        position = np.minimum(np.searchsorted(steps, wanted), len(steps) - 1)
        mask[index] = steps[position] == wanted
    return mask


def _label_both_sets(
    grid: pd.DataFrame,
    by_set: dict[str, dict[str, pd.DataFrame]],
    coverage: dict[str, dict[str, np.ndarray]],
    horizons: Sequence[int],
    core: Sequence[str],
    site: HarmonisedSite,
) -> pd.DataFrame:
    """Label one turbine-year for both sets at every horizon, and tally the site.

    Args:
        grid: Cleaned rows of one turbine.
        by_set: Events per label set, per turbine.
        coverage: Steps per turbine each label set's evidence covers.
        horizons: Horizons, in steps.
        core: Core channels, for ``has_data``.
        site: The site record the tallies go to.

    Returns:
        One row per grid step: identity, ``has_data`` and a nullable boolean per set and
        horizon.
    """
    stamps = pd.to_datetime(grid["timestamp_utc"], utc=True).reset_index(drop=True)
    turbine = str(grid["turbine_id"].iloc[0])
    present = [name for name in core if name in grid.columns]
    has_data = (
        grid[present].notna().any(axis=1).to_numpy() if present else np.zeros(len(grid), dtype=bool)
    )
    labels = pd.DataFrame(
        {
            "source": grid["source"].to_numpy(),
            "turbine_id": grid["turbine_id"].to_numpy(),
            "timestamp_utc": stamps,
            "has_data": has_data,
        }
    )
    site.steps_with_data += int(has_data.sum())
    empty = np.array([], dtype=np.int64)
    for label_set in LABEL_SETS:
        events = by_set[label_set].get(turbine)
        starts = (
            events["start_utc"]
            if events is not None
            else pd.Series([], dtype="datetime64[ns, UTC]")
        )
        for steps in horizons:
            name = label_column(label_set, steps)
            column = horizon_labels(stamps, starts, steps, coverage[label_set].get(turbine, empty))
            labels[name] = column.to_numpy()
            known = column.notna().to_numpy()
            positive = column.fillna(False).to_numpy(dtype=bool)
            site.positives[name] = site.positives.get(name, 0) + int(positive.sum())
            site.known[name] = site.known.get(name, 0) + int(known.sum())
            site.positives_with_data[name] = site.positives_with_data.get(name, 0) + int(
                (positive & has_data).sum()
            )
            site.known_with_data[name] = site.known_with_data.get(name, 0) + int(
                (known & has_data).sum()
            )
    return labels


def _event_info_stops(
    ingested: pd.DataFrame,
    rule: EventInfoConfig,
    covered: dict[str, np.ndarray],
    site: HarmonisedSite,
) -> SourceStops:
    """CARE: one labelled anomaly per dataset is both label sets.

    Args:
        ingested: The source's ingested event_info rows.
        rule: The event_info rule.
        covered: Grid steps per turbine, integer seconds.
        site: The site record to fill.

    Returns:
        The anomaly events as both label sets, covering the grid.
    """
    labels = set(rule.fault_labels)
    category = ingested["category"].astype(str)
    anomaly = ingested[category.isin(labels)]
    events = pd.DataFrame(
        {
            "turbine_id": anomaly["turbine_id"].astype(str),
            "start_utc": anomaly["start_utc"],
            "end_utc": anomaly["end_utc"],
            "steps": np.nan,
            "duration_s": np.nan,
            "dominant_cause": "unknown",
            "first_cause": "unknown",
        }
    ).reset_index(drop=True)
    farm = ingested["turbine_id"].astype(str).str.split(":").str[0]
    farm_label = farm + " " + category
    site.extra["care"] = {
        "rows": len(ingested),
        "by farm and label": {
            str(key): int(count) for key, count in farm_label.value_counts().sort_index().items()
        },
        "anomaly starts inside their dataset's grid": int(in_grid(events, covered).sum()),
        "schema": _raw_keys(ingested),
    }
    site.extra["schema"] = {"event_info": _raw_keys(ingested)}
    site.dataset_level = True
    return SourceStops(
        steps=empty_stop_steps(),
        narrow_covered=covered,
        broad_covered=covered,
        stream=pd.DataFrame(),
        narrow=events,
        broad=events.copy(),
    )


def _raw_keys(events: pd.DataFrame) -> list[str]:
    """The provider's own column names, read back from the first preserved raw row."""
    for raw in events["raw"].dropna().head(1):
        try:
            return sorted(json.loads(str(raw)))
        except ValueError:
            return []
    return []


def _code_descriptions(adapter: BaseAdapter, members: Sequence[RawMember]) -> pd.DataFrame:
    """The provider's alarm-code description table.

    Raises:
        FileNotFoundError: If it is not staged.
    """
    member = next(
        (
            m
            for m in members
            if adapter.CODE_DESCRIPTIONS and m.archive.name == adapter.CODE_DESCRIPTIONS
        ),
        None,
    )
    if member is None:
        raise FileNotFoundError(f"{adapter.source_id}: {adapter.CODE_DESCRIPTIONS} is not staged")
    return read_csv_member(member)


def _stopping_flags(descriptions: pd.DataFrame) -> dict[str, bool]:
    """Stopping flag per described alarm code."""
    return {
        str(int(code)): bool(int(flag))
        for code, flag in zip(descriptions["Alarm Code"], descriptions["Stopping"], strict=True)
    }


def _hill_of_towie_schema(
    members: Sequence[RawMember], series: RawMember, table_name: str
) -> dict[str, list[str]]:
    """The published columns of every table the held-out site's labels read."""
    schema = {"ShutdownDuration.csv": header_columns(series)}
    alarm_log = next((m for m in members if m.kind == "alarm_log" and m.size > 0), None)
    if alarm_log is not None:
        schema["tblAlarmLog"] = header_columns(alarm_log)
    for member in members:
        if not member.in_archive and member.archive.name.endswith("alarms_description.csv"):
            schema[member.archive.name] = header_columns(member)
    stop_table = next(
        (
            m
            for m in members
            if m.name.rsplit("/", 1)[-1].startswith(f"{table_name}_") and m.size > 0
        ),
        None,
    )
    if stop_table is not None:
        schema[table_name] = header_columns(stop_table)
    return schema


def _status_summary(events: pd.DataFrame) -> dict[str, Any]:
    """The unmapped fractions and category counts of a categorized status table."""
    unmapped = events["category"] == UNMAPPED
    stop = events["provider_status"] == "Stop"
    forced = events["provider_iec"] == "Forced outage"
    return {
        "rows": int(len(events)),
        "unmapped_rows": int(unmapped.sum()),
        "stop_rows": int(stop.sum()),
        "unmapped_stop_rows": int((unmapped & stop).sum()),
        "forced_rows": int(forced.sum()),
        "unmapped_forced_rows": int((unmapped & forced).sum()),
        "distinct": int(events["message"].nunique()),
        "distinct_unmapped": int(events.loc[unmapped, "message"].nunique()),
        "top_unmapped": {
            str(k): int(v)
            for k, v in events.loc[unmapped, "message"].value_counts().head(15).items()
        },
        "stop_by_category": {
            str(k): int(v) for k, v in events.loc[stop, "category"].value_counts().items()
        },
    }


def _pct(part: int, whole: int, digits: int = 2) -> str:
    return f"{part / whole * 100:.{digits}f}%" if whole else "n/a"


def render_label_report(meta: Any, result: StageResult) -> str:
    """Render the label stage report.

    Args:
        meta: Run identity.
        result: Result of the label stage.

    Returns:
        A Markdown document.
    """
    details = result.details
    sites: dict[str, SiteLabels] = details.get("sites", {})
    horizons: list[str] = details.get("horizons", [])
    parts = [header_block(meta, result.name, "Telemetry pipeline - event labels")]
    parts.append(
        section(
            "Rules",
            kv_table(
                {
                    "labels config": details.get("labels_config", "-"),
                    "labels config sha256[:8]": details.get("labels_config_hash", "-"),
                    "horizons": ", ".join(horizons),
                    "positive": "a fault event starts in (t, t + H] for the step at t",
                    "primary horizon": "none chosen; all three are labelled side by side",
                }
            ),
        )
    )
    rows = []
    for source, site in sites.items():
        rows.append(
            (
                source,
                site.turbines,
                site.steps,
                site.steps_with_data,
                site.fault_events,
                *(_pct(site.positives.get(h, 0), site.steps, 3) for h in horizons),
                *(
                    _pct(site.positives_with_data.get(h, 0), site.steps_with_data, 3)
                    for h in horizons
                ),
            )
        )
    parts.append(
        section(
            "Positive base rate per site and horizon",
            "Share of grid steps whose horizon holds the start of a fault event. `all steps` "
            "counts every step of the cleaned grid, gaps included; `steps with data` counts "
            "the steps where at least one core channel has a value.\n\n"
            + table(
                [
                    "site",
                    "turbines",
                    "grid steps",
                    "steps with data",
                    "fault events",
                    *(f"{h} (all steps)" for h in horizons),
                    *(f"{h} (steps with data)" for h in horizons),
                ],
                rows,
            ),
        )
    )
    for source, site in sites.items():
        body = kv_table(
            {
                "events by category": ", ".join(
                    f"{k}: {v:,}" for k, v in site.events_by_category.items()
                )
            }
        )
        status = site.extra.get("status")
        if status:
            body += "\n" + kv_table(
                {
                    "status rows": status["rows"],
                    "distinct strings": status["distinct"],
                    "unmapped rows": f"{status['unmapped_rows']:,} "
                    f"({_pct(status['unmapped_rows'], status['rows'], 3)})",
                    "distinct strings unmapped": status["distinct_unmapped"],
                    "provider Stop rows unmapped": f"{status['unmapped_stop_rows']:,} of "
                    f"{status['stop_rows']:,} "
                    f"({_pct(status['unmapped_stop_rows'], status['stop_rows'])})",
                    "IEC Forced outage rows unmapped": f"{status['unmapped_forced_rows']:,} of "
                    f"{status['forced_rows']:,} "
                    f"({_pct(status['unmapped_forced_rows'], status['forced_rows'])})",
                    "provider Stop rows by configured category": ", ".join(
                        f"{k}: {v:,}" for k, v in status["stop_by_category"].items()
                    ),
                }
            )
            if status["top_unmapped"]:
                body += "\n**Most frequent unmapped strings**\n\n" + top_values_table(
                    status["top_unmapped"], n=15, label="string (normalized)"
                )
        if "sensitivity" in site.extra:
            body += "\n" + kv_table(
                {
                    "threshold (s)": site.extra["threshold"],
                    "downtime rows read (staged years and the year after)": site.extra[
                        "downtime_rows"
                    ],
                    "down steps at the threshold": site.extra["down_steps"],
                    "events at each threshold": ", ".join(
                        f"{t:g} s: {n:,}" for t, n in site.extra["sensitivity"].items()
                    ),
                }
            )
            for threshold, check in site.extra["cross_check"].items():
                total = int(check["occurrences"].sum())
                agree = int(check["agreeing"].sum())
                stop_rows = check[check["stopping"]]
                stop_agree = int(stop_rows["agreeing"].sum())
                stop_total = int(stop_rows["occurrences"].sum())
                body += (
                    f"\n**Downtime against the Stopping flag, threshold {threshold:g} s, "
                    f"window {site.extra['window_steps']} step(s)**: "
                    f"{agree:,} of {total:,} occurrences agree ({_pct(agree, total)}); "
                    f"stopping codes {stop_agree:,} of {stop_total:,} "
                    f"({_pct(stop_agree, stop_total)}); "
                    f"mean over codes {check['agreement'].mean() * 100:.1f}%\n\n"
                    + table(
                        [
                            "code",
                            "stopping",
                            "occurrences",
                            "showing downtime",
                            "agreeing",
                            "agreement",
                        ],
                        [
                            (
                                r.code,
                                bool(r.stopping),
                                int(r.occurrences),
                                int(r.showing_downtime),
                                int(r.agreeing),
                                f"{r.agreement * 100:.1f}%",
                            )
                            for r in check.itertuples(index=False)
                        ],
                    )
                )
        parts.append(section(f"Events: {source}", body))
    return "".join(parts)


# -------------------------------------------------------------------------------------
# v2 report
# -------------------------------------------------------------------------------------


def _rate(part: int, whole: int) -> str:
    return f"{part / whole * 100:.3f}%" if whole else "n/a"


def _per_year(count: int, site: HarmonisedSite) -> str:
    """A count with its rate per turbine-year of grid time."""
    years = site.turbine_years
    return f"{count:,} ({count / years:.1f})" if years else f"{count:,}"


def _rate_per_year(count: int, steps: int) -> str:
    """A count with its rate per turbine-year of the given grid steps."""
    return f"{count:,} ({count / (steps / STEPS_PER_YEAR):.1f})" if steps else f"{count:,}"


def _suffix(steps: int) -> str:
    """A horizon without the ``event_`` prefix, e.g. ``within_1h``."""
    return horizon_name(steps).removeprefix("event_")


def _cross_check_tables(checks: dict[float, Any], window: int) -> str:
    """The Stopping-flag agreement at each threshold."""
    body = ""
    for threshold, check in checks.items():
        total = int(check["occurrences"].sum())
        agree = int(check["agreeing"].sum())
        stop_rows = check[check["stopping"]]
        stop_agree = int(stop_rows["agreeing"].sum())
        stop_total = int(stop_rows["occurrences"].sum())
        body += (
            f"\n\n**Threshold {threshold:g} s, window {window} step(s)**: {agree:,} of {total:,} "
            f"occurrences agree ({_pct(agree, total)}); stopping codes {stop_agree:,} of "
            f"{stop_total:,} ({_pct(stop_agree, stop_total)})\n\n"
            + table(
                ["code", "stopping", "occurrences", "showing downtime", "agreeing", "agreement"],
                [
                    (
                        r.code,
                        bool(r.stopping),
                        int(r.occurrences),
                        int(r.showing_downtime),
                        int(r.agreeing),
                        f"{r.agreement * 100:.1f}%",
                    )
                    for r in check.itertuples(index=False)
                ],
            )
        )
    return body


def _label_table(sites: dict[str, HarmonisedSite], horizons: Sequence[int]) -> str:
    """Events per turbine-year and base rate per horizon, both sets."""
    rows = [
        (
            source,
            site.turbines,
            f"{site.turbine_years:.2f}",
            _per_year(site.events.get("narrow", 0), site),
            _per_year(site.events.get("broad", 0), site),
            *(
                _rate(
                    site.positives.get(label_column(s, h), 0),
                    site.known.get(label_column(s, h), 0),
                )
                for s in LABEL_SETS
                for h in horizons
            ),
        )
        for source, site in sites.items()
    ]
    return table(
        [
            "site",
            "turbines",
            "turbine-years",
            "narrow events (/ty)",
            "broad events (/ty)",
            *(f"{s} {_suffix(h)}" for s in LABEL_SETS for h in horizons),
        ],
        rows,
    )


def _with_data_table(sites: dict[str, HarmonisedSite], horizons: Sequence[int]) -> str:
    """Base rate on steps with data, and the share of labels that are unknown."""
    return table(
        [
            "site",
            *(f"{s} {_suffix(h)} with data" for s in LABEL_SETS for h in horizons),
            *(f"{s} {_suffix(h)} unknown" for s in LABEL_SETS for h in horizons),
        ],
        [
            (
                source,
                *(
                    _rate(
                        site.positives_with_data.get(label_column(s, h), 0),
                        site.known_with_data.get(label_column(s, h), 0),
                    )
                    for s in LABEL_SETS
                    for h in horizons
                ),
                *(
                    _rate(site.steps - site.known.get(label_column(s, h), 0), site.steps)
                    for s in LABEL_SETS
                    for h in horizons
                ),
            )
            for source, site in sites.items()
        ],
    )


def _attribution_section(source: str, site: HarmonisedSite) -> str:
    """How a downtime series was split into causes."""
    attribution: DowntimeAttribution = site.extra["attribution"]
    described: dict[str, str] = site.extra.get("descriptions", {})
    return section(
        f"{source}: how the downtime was attributed",
        kv_table(
            {
                "down steps in the labelled years": attribution.down_steps,
                "of which no stop-class row was published": attribution.unclassified_down_steps,
                "of which no stop class covers a second (cause unknown)": (
                    attribution.unattributed_down_steps
                ),
                "stop-class rows read": site.extra.get("stop_class_rows", 0),
            }
        )
        + "\nDescribed codes whose own description names a non-technical cause take the "
        "turbine-error seconds of the steps their alarm is active in:\n\n"
        + table(
            ["code", "description", "cause", "steps moved", "turbine-error seconds moved"],
            [
                (o.code, described.get(o.code, "-"), o.cause, o.steps, round(o.seconds))
                for o in attribution.overrides
            ],
        ),
    )


def _wind_section(sites: dict[str, HarmonisedSite], envelope: dict[str, Any]) -> str:
    """The wind state at the start of narrow events."""
    rows = [
        (
            source,
            site.events.get("narrow", 0),
            site.wind.get("below_cut_in", 0),
            site.wind.get("above_cut_out", 0),
            site.wind.get("inside", 0),
            site.wind.get("unknown", 0),
            _per_year(site.wind.get("inside", 0) + site.wind.get("unknown", 0), site),
        )
        for source, site in sites.items()
        if site.sensitivity
    ]
    return section(
        "Wind state at the start of narrow events",
        f"Diagnostic, not a filter (`apply: {str(envelope.get('apply', False)).lower()}`). "
        f"One envelope for every site: cut-in {envelope.get('cut_in_ms')} m/s, cut-out "
        f"{envelope.get('cut_out_ms')} m/s. Provenance: {envelope.get('provenance', '-')} "
        "The last column is the narrow rate a wind rule would leave.\n\n"
        + table(
            [
                "site",
                "narrow events",
                "below cut-in",
                "above cut-out",
                "inside",
                "unknown",
                "inside or unknown (/ty)",
            ],
            rows,
        ),
    )


def _emergency_section(sites: dict[str, HarmonisedSite]) -> str:
    """Narrow counts with the emergency-stop strings counted as technical."""
    rows = []
    for source, site in sites.items():
        if site.emergency is None:
            continue
        narrow = site.events.get("narrow", 0)
        change = (
            f"{(site.emergency - narrow) / site.turbine_years:+.2f}" if site.turbine_years else "-"
        )
        rows.append(
            (
                source,
                site.extra.get("emergency_stop_rows", 0),
                _per_year(narrow, site),
                _per_year(site.emergency, site),
                change,
            )
        )
    return section(
        "Sensitivity: emergency stops counted as faults",
        "The configured emergency-stop strings move from their category (manual operation, or "
        "unmapped) to technical. Hill of Towie describes no emergency-stop code, so it has no "
        "counterpart.\n\n"
        + table(
            ["site", "emergency stop rows", "narrow (/ty)", "with them (/ty)", "change (/ty)"],
            rows,
        ),
    )


def render_harmonised_report(meta: Any, result: StageResult) -> str:
    """Render the label report under the harmonised rule (ADR-0009).

    Args:
        meta: Run identity.
        result: Result of the label stage.

    Returns:
        A Markdown document.
    """
    details = result.details
    everywhere: dict[str, HarmonisedSite] = details.get("sites", {})
    # A source labelled one event per dataset (CARE) is reported per dataset in its own
    # section and left out of every table of per-step or per-turbine-year rates: its steps
    # are chosen datasets, not a whole record (ADR-0010).
    sites = {source: site for source, site in everywhere.items() if not site.dataset_level}
    level = {source: site for source, site in everywhere.items() if site.dataset_level}
    horizons: list[int] = details.get("horizons_steps", [])
    rule: dict[str, Any] = details.get("rule", {})
    durations = sorted(
        {*rule.get("sensitivity_min_duration_s", []), float(rule.get("min_duration_s", 0))}
    )
    parts = [header_block(meta, result.name, "Telemetry pipeline - event labels, harmonised")]
    parts.append(
        section(
            "Rules",
            kv_table(
                {
                    "labels config": details.get("labels_config", "-"),
                    "labels config sha256[:8]": details.get("labels_config_hash", "-"),
                    "decision": "ADR-0009: narrow the held-out site to the training "
                    "definition; do not widen the training sites",
                    "the rule": "an event is a run of consecutive 10-minute steps holding "
                    "downtime of the chosen causes, lasting at least the minimum duration; "
                    "one function (harmonise.select_events), with no source argument",
                    "narrow (primary)": ", ".join(rule.get("narrow_causes", [])),
                    "broad (secondary)": "any cause: " + ", ".join(CAUSES),
                    "minimum duration (s)": rule.get("min_duration_s"),
                    "horizons": ", ".join(horizon_name(s) for s in horizons),
                    "positive": "an event of the set starts in (t, t + H] for the step at t",
                    "unknown label": "no event seen, and the horizon runs past the record "
                    "the events were read from: NA, never False (ADR-0006)",
                    "events per turbine-year": "events starting in a step of the cleaned "
                    "grid, over grid steps / 52,596",
                }
            ),
        )
    )
    parts.append(
        section(
            "Label table: events per turbine-year and base rate, both sets",
            "Events with their rate per turbine-year of grid time in brackets. A base rate is "
            "positive steps over steps whose label is known. A source labelled one event per "
            "dataset is reported per dataset, in its own section below (ADR-0010).\n\n"
            + _label_table(sites, horizons),
        )
    )
    parts.append(
        section(
            "Base rate on steps with data, and how many labels are unknown",
            "`with data`: at least one core channel has a value. `unknown`: share of all grid "
            "steps whose label is NA because its horizon runs past the event record.\n\n"
            + _with_data_table(sites, horizons),
        )
    )
    parts.append(
        section(
            "Duration threshold sensitivity",
            "Events per set at each minimum duration, with the rate per turbine-year. The "
            "threshold applies to the seconds of downtime of the set's causes in the run.\n\n"
            + table(
                ["site", "set", *(f"{d:g} s" for d in durations)],
                [
                    (
                        source,
                        name,
                        *(_per_year(site.sensitivity[name].get(d, 0), site) for d in durations),
                    )
                    for source, site in sites.items()
                    for name in LABEL_SETS
                    if name in site.sensitivity
                ],
            ),
        )
    )
    status_sites = {s: site for s, site in sites.items() if site.rows}
    if status_sites:
        parts.append(
            section(
                "Training sites: status rows against episodes",
                "Gate 1 counted equipment-fault status rows (`rows, any duration`), and "
                "divided by turbine-year files (54, 98 and, at the held-out site, 42), which "
                "gave 19.5, 24.8 and 212.6; every rate here is over grid time instead. One "
                "fault episode is often several rows, and a Siemens downtime run is one event "
                "whatever it holds. The harmonised rule counts episodes at every site; this "
                "shows what that does to the training sites.\n\n"
                + table(
                    [
                        "site",
                        "technical rows, any duration (/ty)",
                        *(f"rows >= {d:g} s" for d in durations),
                        *(f"episodes >= {d:g} s" for d in durations),
                    ],
                    [
                        (
                            source,
                            _per_year(site.rows.get("any", 0), site),
                            *(_per_year(site.rows.get(f"{d:g}", 0), site) for d in durations),
                            *(
                                _per_year(site.sensitivity["narrow"].get(d, 0), site)
                                for d in durations
                            ),
                        )
                        for source, site in status_sites.items()
                    ],
                ),
            )
        )
    parts.append(
        section(
            "Events per calendar year",
            "Years with at least a day of grid. At the held-out site 2019 is before the AeroUp "
            "retrofit and 2023 after it, and 2019 publishes no wind direction.\n\n"
            + table(
                ["site", "year", "turbine-years", "narrow (/ty)", "broad (/ty)"],
                [
                    (
                        source,
                        str(year),
                        f"{counts.get('steps', 0) / STEPS_PER_YEAR:.2f}",
                        _rate_per_year(counts.get("narrow", 0), counts.get("steps", 0)),
                        _rate_per_year(counts.get("broad", 0), counts.get("steps", 0)),
                    )
                    for source, site in sites.items()
                    for year, counts in site.by_year.items()
                    if counts.get("steps", 0) >= 144
                ],
            ),
        )
    )
    parts.append(
        section(
            "Broad events by dominant cause",
            table(
                ["site", *CAUSES],
                [
                    (source, *(site.causes.get(c, 0) for c in CAUSES))
                    for source, site in sites.items()
                ],
            ),
        )
    )
    parts.append(
        section(
            "Where the cause comes from: the published columns",
            "Every column of every table the labels read, as published. At the held-out site "
            "neither `ShutdownDuration.csv` nor `tblAlarmLog` carries a cause or availability "
            "category. `tblSCTurFlag` does, as seconds per step in four stop classes: "
            "`wtc_ScTurSto_timeon` (the provider's description: 'Time turbine error active in "
            "period'), and `wtc_ScEnvSto_timeon`, `wtc_ScComSto_timeon` and "
            "`wtc_ScGrdSto_timeon` (not described). That is rung (a) of ADR-0009: exclusion "
            "by cause.\n\n"
            + table(
                ["site", "table", "columns", "names"],
                [
                    (source, name, len(columns), ", ".join(f"`{c}`" for c in columns))
                    for source, site in everywhere.items()
                    for name, columns in site.extra.get("schema", {}).items()
                ],
            ),
        )
    )
    for source, site in sites.items():
        if isinstance(site.extra.get("attribution"), DowntimeAttribution):
            parts.append(_attribution_section(source, site))
    parts.append(_wind_section(sites, rule.get("wind_envelope", {})))
    if any(site.emergency is not None for site in sites.values()):
        parts.append(_emergency_section(sites))
    for source, site in sites.items():
        checks = site.extra.get("cross_check")
        if checks:
            parts.append(
                section(
                    f"{source}: downtime against the provider's Stopping flag",
                    "An occurrence of a described code agrees when downtime at or above the "
                    "threshold appears from the step it opens in through the window after its "
                    "end, exactly when the code is described as stopping."
                    + _cross_check_tables(checks, details.get("cross_check_window_steps", 1)),
                )
            )
    parts.append(
        section(
            "Status stream: inputs, never targets",
            "Every status row and alarm is written to `labels/status_stream.parquet`, warnings "
            "and non-stopping codes included, for the text pathway to read as input. Targets "
            "are built from stops only -- a Senvion row whose provider status is Stop, the "
            "downtime series at Hill of Towie -- so a warning can inform a prediction and "
            "never be one.\n\n"
            + table(
                ["site", "counts"],
                [
                    (source, ", ".join(f"{k}: {v:,}" for k, v in site.stream.items()))
                    for source, site in sites.items()
                    if site.stream
                ],
            ),
        )
    )
    for source, site in level.items():
        care = site.extra.get("care", {})
        by_farm = care.get("by farm and label", {})
        parts.append(
            section(
                f"{source}: labelled events, per dataset",
                "One labelled window per dataset. An `anomaly` row is both label sets, and there "
                "is no stop evidence to apply the rule to. CARE is scored per dataset, with its "
                "own CARE score, so no per-step base rate and no rate per turbine-year is "
                "printed for it; the table after the counts is the interval a dataset-level rate "
                "near 50% can carry at these counts, with and without farm A (ADR-0004, "
                "ADR-0010).\n\n"
                + kv_table(
                    {
                        "event_info rows": care.get("rows", 0),
                        **by_farm,
                        "anomaly starts inside their dataset's grid": care.get(
                            "anomaly starts inside their dataset's grid", 0
                        ),
                    }
                )
                + "\n"
                + dataset_interval_table(by_farm),
            )
        )
    return "".join(parts)


def dataset_interval_table(by_farm_label: dict[str, int]) -> str:
    """Datasets per provider label, with and without farm A, and the interval a rate carries.

    Args:
        by_farm_label: Datasets per ``"<farm> <label>"``, as the label stage counts them.

    Returns:
        A Markdown table: label, farms, datasets and the Wilson 95% interval of a rate near
        one half at that count -- the widest a dataset-level rate can have.
    """
    totals: dict[tuple[str, str], int] = {}
    for key, count in by_farm_label.items():
        farm, _, label = str(key).rpartition(" ")
        totals[(label, "all farms")] = totals.get((label, "all farms"), 0) + int(count)
        if farm != "farm_a":
            totals[(label, "without farm A")] = totals.get((label, "without farm A"), 0) + int(
                count
            )
    rows = []
    for (label, farms), count in sorted(totals.items()):
        low, high = wilson_interval(round(count / 2), count) if count else (float("nan"),) * 2
        rows.append((label, farms, count, f"{low * 100:.0f}-{high * 100:.0f}%"))
    return table(["label", "farms", "datasets", "a rate near 50%, 95% interval"], rows)
