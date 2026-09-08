"""The telemetry pipeline: configuration, stage classes and orchestration.

Four stages, mirroring the text pipeline stage for stage but with resampling,
plausibility bounds, gap segmentation and imputation in place of string cleaning:

``raw archives -> ingest -> cleaned/<source>/ingest/`` , then ``clean`` onto a
regular grid in ``cleaned/<source>/`` , ``filter`` for coverage and segmentation in
``filtered/<source>/`` , and ``final`` for imputation and split assignment in
``final/<source>/``. Each stage reads only its predecessor's directory.

The unit of work is one ``(source, turbine, year)`` Parquet file. That keeps peak
memory to a single turbine-year -- roughly 52,000 rows -- which matters on a
workstation with 32 GB shared with everything else.

At M0 the loaders are unimplemented for every source, so ``ingest`` reports what it
discovered and why it loaded nothing. The remaining stages are exercised on
synthetic fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
from pydantic import Field

from faultline.config import RunMeta, StrictModel, load_config
from faultline.data.common.splits import SplitsConfig, assign_splits, split_counts
from faultline.data.common.stage import Stage, StageResult
from faultline.data.telemetry import report as telemetry_report
from faultline.data.telemetry.adapters import ADAPTERS, get_adapter
from faultline.data.telemetry.clean import BoundSpec, TelemetryCleanConfig, clean_turbine_frame
from faultline.data.telemetry.events import EventConfig, normalize_events
from faultline.data.telemetry.filter import (
    TelemetryFilterConfig,
    channel_coverage,
    drop_short_segments,
    segment_ids,
    segment_lengths,
    select_channels,
)
from faultline.data.telemetry.impute import ImputeConfig, impute_frame
from faultline.logging_utils import get_logger
from faultline.paths import Modality, ProjectPaths
from faultline.runs import RunContext

logger = get_logger(__name__)

#: Stage names in pipeline order.
STAGE_ORDER: tuple[str, ...] = ("ingest", "clean", "filter", "final")


# --------------------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------------------


class TokenizerConfig(StrictModel):
    """Quantile-bin tokenizer fitting settings.

    Attributes:
        n_bins: Number of quantile bins per channel.
        sample_rows: Row cap used when estimating quantiles.
        seed: Seed for the row subsample.
    """

    n_bins: int = 64
    sample_rows: int | None = 500_000
    seed: int = 20260909


class TelemetryFinalConfig(StrictModel):
    """Settings for the final stage.

    Attributes:
        splits_config: Path to the split specification, relative to the repo root.
        write_masks: Write the ``<channel>__imputed`` companion columns.
    """

    splits_config: str = "configs/data/splits_v0.yaml"
    write_masks: bool = True


class TelemetryReportConfig(StrictModel):
    """Reporting settings.

    Attributes:
        top_n_messages: Number of event messages listed in reports.
        percentile_channels: Channels to profile; empty means every configured channel.
    """

    top_n_messages: int = 20
    percentile_channels: list[str] = Field(default_factory=list)


class TelemetryPipelineConfig(StrictModel):
    """Full configuration of one telemetry pipeline run.

    Attributes:
        freq: Grid resolution as a pandas offset alias.
        timezone_default: Timezone assumed for naive source timestamps.
        channels: Canonical channels, in the order that fixes channel token ids.
        bounds: Plausibility bounds per channel.
        bounds_overrides: Per-source bound overrides.
        clean: Cleaning switches.
        filter: Coverage and segmentation thresholds.
        impute: Short-gap imputation settings.
        events: Event normalization and labelling settings.
        tokenizer: Quantile-bin tokenizer settings.
        final: Final stage settings.
        report: Reporting settings.
    """

    freq: str = "10min"
    timezone_default: str = "UTC"
    channels: list[str]
    bounds: dict[str, BoundSpec] = Field(default_factory=dict)
    bounds_overrides: dict[str, dict[str, BoundSpec]] = Field(default_factory=dict)
    clean: TelemetryCleanConfig = Field(default_factory=TelemetryCleanConfig)
    filter: TelemetryFilterConfig = Field(default_factory=TelemetryFilterConfig)
    impute: ImputeConfig = Field(default_factory=ImputeConfig)
    events: EventConfig = Field(default_factory=EventConfig)
    tokenizer: TokenizerConfig = Field(default_factory=TokenizerConfig)
    final: TelemetryFinalConfig = Field(default_factory=TelemetryFinalConfig)
    report: TelemetryReportConfig = Field(default_factory=TelemetryReportConfig)

    def bounds_for(self, source: str) -> dict[str, BoundSpec]:
        """Return the plausibility bounds in force for one source.

        Args:
            source: Source identifier.

        Returns:
            The default bounds, updated with any per-source overrides.
        """
        merged = dict(self.bounds)
        merged.update(self.bounds_overrides.get(source, {}))
        return merged


class TelemetryConfigFile(StrictModel):
    """Top level of ``configs/data/telemetry_*.yaml``.

    Attributes:
        telemetry: The pipeline configuration.
    """

    telemetry: TelemetryPipelineConfig


def load_telemetry_config(path: Path) -> TelemetryPipelineConfig:
    """Load and validate a telemetry pipeline configuration file.

    Args:
        path: Path to the YAML configuration.

    Returns:
        The validated ``telemetry`` block.
    """
    return load_config(path, TelemetryConfigFile).telemetry


# --------------------------------------------------------------------------------------
# layout helpers
# --------------------------------------------------------------------------------------


def ingest_dir(paths: ProjectPaths, source: str) -> Path:
    """Return the ingest output directory for a source.

    Args:
        paths: Resolved project paths.
        source: Source identifier.

    Returns:
        The created ``cleaned/telemetry/<source>/ingest`` directory.
    """
    path = paths.source_dir("cleaned", "telemetry", source) / "ingest"
    path.mkdir(parents=True, exist_ok=True)
    return path


def stage_source_dir(paths: ProjectPaths, stage: str, source: str) -> Path:
    """Return a per-source stage directory.

    Args:
        paths: Resolved project paths.
        stage: One of ``cleaned``, ``filtered``, ``final``.
        source: Source identifier.

    Returns:
        The created directory.
    """
    if stage == "cleaned":
        return paths.source_dir("cleaned", "telemetry", source)
    if stage == "filtered":
        return paths.source_dir("filtered", "telemetry", source)
    if stage == "final":
        return paths.source_dir("final", "telemetry", source)
    raise ValueError(f"unknown telemetry stage directory {stage!r}")


def parquet_files(directory: Path) -> list[Path]:
    """List the Parquet files of a stage directory, excluding event tables.

    Args:
        directory: Directory to scan.

    Returns:
        Sorted Parquet paths, excluding ``events.parquet`` and nested stage dirs.
    """
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.parquet") if path.name != "events.parquet")


def turbine_year_name(turbine_id: str, year: int) -> str:
    """Build the file stem for one turbine-year.

    Args:
        turbine_id: Turbine identifier.
        year: Calendar year.

    Returns:
        A filesystem-safe stem.
    """
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in str(turbine_id))
    return f"{safe}__{year}"


# --------------------------------------------------------------------------------------
# stages
# --------------------------------------------------------------------------------------


@dataclass
class TelemetryStage(Stage):
    """Base class carrying the configuration and source selection.

    Attributes:
        config: Pipeline configuration.
        paths: Resolved project paths.
        sources: Source identifiers this run covers.
    """

    config: TelemetryPipelineConfig
    paths: ProjectPaths
    sources: list[str]
    modality: ClassVar[Modality] = "telemetry"
    _meta: RunMeta | None = field(default=None, init=False, repr=False)

    def report(self, result: StageResult) -> str:
        """Render this stage's Markdown report.

        Args:
            result: Result returned by :meth:`run`.

        Returns:
            A Markdown document.

        Raises:
            RuntimeError: If called before :meth:`run`.
        """
        if self._meta is None:
            raise RuntimeError("report() called before run(); the run metadata is unknown")
        return telemetry_report.render(self._meta, result)


class IngestStage(TelemetryStage):
    """Read staged archives through the source adapters into canonical Parquet."""

    name: ClassVar[str] = "ingest"

    def run(self, ctx: RunContext) -> StageResult:
        """Discover and load every staged member for the selected sources.

        Args:
            ctx: Active run context.

        Returns:
            Discovery counts, load counts and the adapters that are not yet
            implemented.
        """
        self._meta = ctx.meta
        summary: dict[str, dict[str, int]] = {}
        member_kinds: dict[str, int] = {}
        not_implemented: dict[str, str] = {}
        outputs: list[Path] = []
        rows_out = 0

        for source in self.sources:
            adapter = get_adapter(source, self.paths.configs_dir)
            raw_dir = self.paths.source_dir("raw", "telemetry", source)
            members = adapter.discover(raw_dir)
            info = {"members": len(members), "loaded": 0, "turbines": 0, "events": 0}
            for member in members:
                member_kinds[member.kind] = member_kinds.get(member.kind, 0) + 1

            destination = ingest_dir(self.paths, source)
            frames: list[pd.DataFrame] = []
            for member in [m for m in members if m.kind == "scada_10min"]:
                try:
                    frames.append(adapter.load_scada(member))
                except NotImplementedError as exc:
                    not_implemented[source] = str(exc)
                    break
                except (OSError, ValueError) as exc:
                    logger.error("%s: cannot load %s: %s", source, member.label, exc)

            events: list[pd.DataFrame] = []
            for member in [m for m in members if m.kind in ("status_events", "alarm_log")]:
                try:
                    loaded = adapter.load_events(member)
                except NotImplementedError as exc:
                    not_implemented.setdefault(source, str(exc))
                    break
                except (OSError, ValueError) as exc:
                    logger.error("%s: cannot load %s: %s", source, member.label, exc)
                    continue
                if loaded is not None and not loaded.empty:
                    events.append(loaded)

            if frames:
                combined = pd.concat(frames, ignore_index=True)
                rows_out += len(combined)
                info["loaded"] = len(combined)
                info["turbines"] = int(combined["turbine_id"].nunique())
                outputs.extend(self._write_turbine_years(combined, destination))
            if events:
                merged = normalize_events(pd.concat(events, ignore_index=True), self.config.events)
                info["events"] = len(merged)
                path = destination / "events.parquet"
                merged.to_parquet(path, index=False)
                outputs.append(path)
            summary[source] = info

        return StageResult(
            name=self.name,
            rows_in=0,
            rows_out=rows_out,
            counters={"sources": len(self.sources), "not_implemented": len(not_implemented)},
            details={
                "sources": summary,
                "member_kinds": member_kinds,
                "not_implemented": not_implemented,
            },
            outputs=outputs,
        )

    def _write_turbine_years(self, frame: pd.DataFrame, destination: Path) -> list[Path]:
        """Split a canonical table into one Parquet file per turbine-year.

        Args:
            frame: Canonical wide table.
            destination: Output directory.

        Returns:
            The files written.
        """
        written: list[Path] = []
        stamps = pd.to_datetime(frame["timestamp_utc"], utc=True)
        for (turbine, year), group in frame.groupby([frame["turbine_id"], stamps.dt.year]):
            path = destination / f"{turbine_year_name(str(turbine), int(str(year)))}.parquet"
            group.to_parquet(path, index=False)
            written.append(path)
        return written


class CleanStage(TelemetryStage):
    """Parse timestamps, collapse duplicates, build a regular grid, bound values."""

    name: ClassVar[str] = "clean"

    def run(self, ctx: RunContext) -> StageResult:
        """Clean every ingested turbine-year.

        Args:
            ctx: Active run context.

        Returns:
            Row counts, timestamp counters, bound flags and per-turbine coverage.
        """
        self._meta = ctx.meta
        counters: dict[str, int] = {}
        turbine_rows: list[tuple[Any, ...]] = []
        coverage_totals: dict[str, list[float]] = {}
        outputs: list[Path] = []
        rows_in = 0
        rows_out = 0

        for source in self.sources:
            bounds = self.config.bounds_for(source)
            destination = stage_source_dir(self.paths, "cleaned", source)
            for path in parquet_files(ingest_dir(self.paths, source)):
                frame = pd.read_parquet(path)
                rows_in += len(frame)
                cleaned, counts = clean_turbine_frame(
                    frame,
                    channels=self.config.channels,
                    bounds=bounds,
                    config=self.config.clean,
                    freq=self.config.freq,
                    timezone=self.config.timezone_default,
                )
                rows_out += len(cleaned)
                for key, value in counts.as_counters().items():
                    counters[key] = counters.get(key, 0) + value

                coverage = channel_coverage(cleaned, self.config.channels)
                for name, fraction in coverage.items():
                    coverage_totals.setdefault(name, []).append(fraction)
                stamps = pd.to_datetime(cleaned["timestamp_utc"], utc=True)
                turbine_rows.append(
                    (
                        path.stem,
                        len(cleaned),
                        str(stamps.min()) if len(cleaned) else "-",
                        str(stamps.max()) if len(cleaned) else "-",
                        f"{sum(coverage.values()) / max(len(coverage), 1) * 100:.1f}%",
                    )
                )
                out_path = destination / path.name
                cleaned.to_parquet(out_path, index=False)
                outputs.append(out_path)

        mean_coverage = {
            name: sum(values) / len(values) for name, values in coverage_totals.items() if values
        }
        return StageResult(
            name=self.name,
            rows_in=rows_in,
            rows_out=rows_out,
            counters=counters,
            details={
                "freq": self.config.freq,
                "timezone": self.config.timezone_default,
                "coverage": mean_coverage,
                "turbine_rows": turbine_rows,
            },
            outputs=outputs,
        )


class FilterStage(TelemetryStage):
    """Apply coverage thresholds and split the record into continuous segments."""

    name: ClassVar[str] = "filter"

    def run(self, ctx: RunContext) -> StageResult:
        """Filter every cleaned turbine-year.

        Args:
            ctx: Active run context.

        Returns:
            Row counts, kept channels, segment counters and segment lengths.
        """
        self._meta = ctx.meta
        counters: dict[str, int] = {}
        coverage_totals: dict[str, list[float]] = {}
        kept_channels: set[str] = set()
        lengths: list[int] = []
        outputs: list[Path] = []
        rows_in = 0
        rows_out = 0

        for source in self.sources:
            destination = stage_source_dir(self.paths, "filtered", source)
            for path in parquet_files(stage_source_dir(self.paths, "cleaned", source)):
                frame = pd.read_parquet(path)
                rows_in += len(frame)
                channels, coverage = select_channels(
                    frame, self.config.channels, self.config.filter
                )
                for name, value in coverage.items():
                    coverage_totals.setdefault(name, []).append(value)
                kept_channels.update(channels)

                ids = segment_ids(frame, channels, self.config.filter, freq=self.config.freq)
                filtered, segment_counters = drop_short_segments(frame, ids, self.config.filter)
                lengths.extend(segment_lengths(ids).values())
                for key, value in segment_counters.items():
                    counters[key] = counters.get(key, 0) + value
                rows_out += len(filtered)

                out_path = destination / path.name
                filtered.to_parquet(out_path, index=False)
                outputs.append(out_path)

        mean_coverage = {
            name: sum(values) / len(values) for name, values in coverage_totals.items() if values
        }
        return StageResult(
            name=self.name,
            rows_in=rows_in,
            rows_out=rows_out,
            counters=counters,
            details={
                "thresholds": self.config.filter.model_dump(),
                "coverage": mean_coverage,
                "channels_kept": sorted(kept_channels),
                "segment_lengths": lengths,
            },
            outputs=outputs,
        )


class FinalStage(TelemetryStage):
    """Impute short gaps, assign site and time splits, write the final tables."""

    name: ClassVar[str] = "final"

    def run(self, ctx: RunContext) -> StageResult:
        """Produce the final telemetry tables.

        Args:
            ctx: Active run context.

        Returns:
            Row counts, imputed steps per channel and split assignment counts.
        """
        self._meta = ctx.meta
        splits_path = self.paths.repo_root / self.config.final.splits_config
        splits_config = load_config(splits_path, SplitsConfig) if splits_path.is_file() else None
        if splits_config is None:
            logger.warning("split spec %s not found; rows are written unsplit", splits_path)

        imputed_totals: dict[str, int] = {}
        split_totals: dict[str, int] = {}
        outputs: dict[str, int] = {}
        written: list[Path] = []
        rows_in = 0
        rows_out = 0

        for source in self.sources:
            destination = stage_source_dir(self.paths, "final", source)
            for path in parquet_files(stage_source_dir(self.paths, "filtered", source)):
                frame = pd.read_parquet(path)
                rows_in += len(frame)
                imputed, counts = impute_frame(frame, self.config.channels, self.config.impute)
                for name, value in counts.items():
                    imputed_totals[name] = imputed_totals.get(name, 0) + value

                if splits_config is not None:
                    imputed["split"] = assign_splits(imputed, splits_config).to_numpy()
                    for name, value in split_counts(imputed["split"]).items():
                        split_totals[name] = split_totals.get(name, 0) + value

                rows_out += len(imputed)
                out_path = destination / path.name
                imputed.to_parquet(out_path, index=False)
                outputs[out_path.name] = len(imputed)
                written.append(out_path)

        return StageResult(
            name=self.name,
            rows_in=rows_in,
            rows_out=rows_out,
            counters={},
            details={
                "imputed": imputed_totals,
                "splits": split_totals,
                "outputs": outputs,
                "splits_config": str(splits_path),
            },
            outputs=written,
        )


STAGE_CLASSES: dict[str, type[TelemetryStage]] = {
    "ingest": IngestStage,
    "clean": CleanStage,
    "filter": FilterStage,
    "final": FinalStage,
}


def build_stages(
    config: TelemetryPipelineConfig,
    paths: ProjectPaths,
    selection: str = "all",
    source: str | None = None,
) -> list[TelemetryStage]:
    """Instantiate the requested telemetry stages in pipeline order.

    Args:
        config: Pipeline configuration.
        paths: Resolved project paths.
        selection: A stage name, or ``all`` for the whole pipeline.
        source: Restrict the run to one source; all registered sources when omitted.

    Returns:
        The stages to execute, in order.

    Raises:
        ValueError: If the selection names no known stage.
        KeyError: If the source is not registered.
    """
    if source is not None and source not in ADAPTERS:
        raise KeyError(f"unknown source {source!r}; known: {sorted(ADAPTERS)}")
    sources = [source] if source else list(ADAPTERS)

    if selection == "all":
        names = list(STAGE_ORDER)
    elif selection in STAGE_CLASSES:
        names = [selection]
    else:
        raise ValueError(
            f"unknown stage {selection!r}; expected one of all, {', '.join(STAGE_ORDER)}"
        )
    return [STAGE_CLASSES[name](config=config, paths=paths, sources=sources) for name in names]
