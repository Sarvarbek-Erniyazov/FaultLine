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
from faultline.data.common.report import header_block, kv_table, section, table, top_values_table
from faultline.data.common.stage import StageResult
from faultline.data.telemetry.adapters import get_adapter
from faultline.data.telemetry.adapters.base import read_csv_member
from faultline.data.telemetry.downtime import read_downtime
from faultline.data.telemetry.events import EventConfig, label_horizon, normalize_message
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


class EventLabelsConfig(StrictModel):
    """Top level of ``configs/data/events_v*.yaml``.

    Attributes:
        version: Version of this file.
        status_strings: The status-string rule.
        downtime: The downtime rule.
        event_info: The event_info rule.
    """

    version: int
    status_strings: StatusStringsConfig
    downtime: DowntimeConfig
    event_info: EventInfoConfig


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


def _years(paths: Sequence[Path]) -> set[int]:
    """The years a set of turbine-year files covers."""
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
        years = _years(grid_files)
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
        table_ = read_csv_member(descriptions)
        stopping = {
            str(int(code)): bool(int(flag))
            for code, flag in zip(table_["Alarm Code"], table_["Stopping"], strict=True)
        }
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
        return render_label_report(self._meta, result)


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
