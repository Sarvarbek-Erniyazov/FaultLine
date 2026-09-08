"""The text corpus pipeline: configuration, stage classes and orchestration.

Five stages map onto the four data-stage directories:

``raw -> clean -> cleaned/`` , ``cleaned -> filter -> filtered/`` , then ``dedup``
and ``pii`` which refine the filtered corpus in place (as ``*.dedup.jsonl`` and
``*.pii.jsonl``), and finally ``final`` which assigns splits and shards into
``final/``. The stage order is the reference notebook's order; the directory
mapping is documented in ``data/README.md``.

Every stage streams JSON Lines: no stage ever holds the corpus in memory. The
deduplicator keeps digests only, and reports keep bounded reservoir samples.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from pydantic import Field, model_validator

from faultline.config import RunMeta, StrictModel, load_config
from faultline.data.common.stage import Stage, StageResult
from faultline.data.text import report as text_report
from faultline.data.text.clean import CleanConfig, clean_text
from faultline.data.text.dedup import DedupConfig, ExactDeduplicator
from faultline.data.text.filter import (
    FilterConfig,
    alphabetic_ratio,
    filter_reason,
    repeated_line_ratio,
)
from faultline.data.text.pii import PII_KINDS, PIIConfig, scrub_pii
from faultline.logging_utils import get_logger
from faultline.paths import Modality, ProjectPaths
from faultline.runs import RunContext

logger = get_logger(__name__)

#: Stage names in pipeline order.
STAGE_ORDER: tuple[str, ...] = ("clean", "filter", "dedup", "pii", "final")


# --------------------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------------------


class TextIOConfig(StrictModel):
    """Where the corpus comes from and which field holds the text.

    Attributes:
        corpus_name: Identifier used for every intermediate file name.
        input_path: Explicit path to the raw JSON Lines file. When omitted the
            pipeline reads ``<data_root>/raw/text/<corpus_name>.jsonl``.
        text_field: Name of the JSON field holding the document body.
    """

    corpus_name: str
    input_path: str | None = None
    text_field: str = "text"


class FinalConfig(StrictModel):
    """Split assignment and sharding of the finished corpus.

    Attributes:
        shard_size: Documents per output shard.
        split_fractions: Fractions per split; must sum to 1.
        split_seed: Seed mixed into the per-document hash, so the assignment is
            deterministic and independent of document order.
    """

    shard_size: int = 5_000
    split_fractions: dict[str, float] = Field(
        default_factory=lambda: {"train": 0.98, "val": 0.01, "test": 0.01}
    )
    split_seed: int = 20260909

    @model_validator(mode="after")
    def _fractions_sum_to_one(self) -> FinalConfig:
        """Reject split fractions that do not form a probability distribution."""
        total = sum(self.split_fractions.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"final.split_fractions must sum to 1.0, got {total}")
        if any(value < 0 for value in self.split_fractions.values()):
            raise ValueError("final.split_fractions must be non-negative")
        return self


class TextReportConfig(StrictModel):
    """How much evidence each stage report carries.

    Attributes:
        sample_size: Number of documents sampled per report section.
        sample_chars: Truncation length for sampled documents.
        sample_seed: Seed for the reservoir samplers.
    """

    sample_size: int = 5
    sample_chars: int = 200
    sample_seed: int = 20260909


class TextPipelineConfig(StrictModel):
    """Full configuration of one text pipeline run.

    Attributes:
        io: Input location and field names.
        clean: Cleaning switches.
        filter: Quality thresholds.
        dedup: Deduplication settings.
        pii: PII masking policy.
        final: Split and shard settings.
        report: Report sampling settings.
    """

    io: TextIOConfig
    clean: CleanConfig = Field(default_factory=CleanConfig)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    pii: PIIConfig = Field(default_factory=PIIConfig)
    final: FinalConfig = Field(default_factory=FinalConfig)
    report: TextReportConfig = Field(default_factory=TextReportConfig)


class TextConfigFile(StrictModel):
    """Top level of ``configs/data/text_*.yaml``.

    Attributes:
        text: The pipeline configuration, namespaced under the ``text`` key so the
            same file layout can later carry a ``telemetry`` block.
    """

    text: TextPipelineConfig


def load_text_config(path: Path) -> TextPipelineConfig:
    """Load and validate a text pipeline configuration file.

    Args:
        path: Path to the YAML configuration.

    Returns:
        The validated ``text`` block.
    """
    return load_config(path, TextConfigFile).text


# --------------------------------------------------------------------------------------
# layout and IO
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TextLayout:
    """Resolved file locations for one corpus across the four stages.

    Attributes:
        raw: Input JSON Lines file.
        cleaned: Output of the cleaning stage.
        filtered: Output of the quality filter.
        deduped: Output of the deduplicator.
        scrubbed: Output of the PII stage.
        final_dir: Directory holding the sharded final corpus.
    """

    raw: Path
    cleaned: Path
    filtered: Path
    deduped: Path
    scrubbed: Path
    final_dir: Path

    @classmethod
    def build(cls, config: TextPipelineConfig, paths: ProjectPaths) -> TextLayout:
        """Derive every path from the configuration and the data root.

        Args:
            config: Pipeline configuration.
            paths: Resolved project paths.

        Returns:
            The layout for this corpus.
        """
        name = config.io.corpus_name
        raw = (
            Path(config.io.input_path)
            if config.io.input_path
            else paths.stage_dir("raw", "text") / f"{name}.jsonl"
        )
        filtered_dir = paths.stage_dir("filtered", "text")
        return cls(
            raw=raw,
            cleaned=paths.stage_dir("cleaned", "text") / f"{name}.jsonl",
            filtered=filtered_dir / f"{name}.jsonl",
            deduped=filtered_dir / f"{name}.dedup.jsonl",
            scrubbed=filtered_dir / f"{name}.pii.jsonl",
            final_dir=paths.stage_dir("final", "text") / name,
        )


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Stream a JSON Lines file one record at a time.

    Args:
        path: File to read.

    Yields:
        One parsed record per non-empty line.

    Raises:
        FileNotFoundError: If the input file does not exist.
    """
    if not path.is_file():
        raise FileNotFoundError(f"input not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                record: dict[str, Any] = json.loads(line)
                yield record


def write_jsonl(path: Path, records: Iterator[dict[str, Any]]) -> int:
    """Stream records into a JSON Lines file.

    Args:
        path: Destination file; parent directories are created.
        records: Records to write.

    Returns:
        The number of records written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


class Reservoir:
    """Fixed-size uniform random sample over a stream.

    Attributes:
        size: Maximum number of items retained.
    """

    def __init__(self, size: int, seed: int) -> None:
        """Initialize an empty reservoir.

        Args:
            size: Maximum number of items to retain.
            seed: Seed for the sampling decisions.
        """
        self.size = size
        self._rng = random.Random(seed)
        self._items: list[str] = []
        self._seen = 0

    def offer(self, item: str) -> None:
        """Offer one item to the sample.

        Args:
            item: Candidate item.
        """
        self._seen += 1
        if len(self._items) < self.size:
            self._items.append(item)
            return
        index = self._rng.randrange(self._seen)
        if index < self.size:
            self._items[index] = item

    @property
    def items(self) -> list[str]:
        """The retained sample, in reservoir order."""
        return list(self._items)


def assign_split(text: str, config: FinalConfig) -> str:
    """Assign a document to a split deterministically from its content.

    Hashing the document rather than drawing a random number makes the assignment
    stable under re-runs, re-ordering and sharding changes, which is what keeps a
    validation document out of training after a pipeline edit.

    Args:
        text: Document body.
        config: Split settings.

    Returns:
        The chosen split name.
    """
    digest = hashlib.sha256(f"{config.split_seed}:{text}".encode()).digest()[:8]
    position = int.from_bytes(digest, "big") / 2**64
    cumulative = 0.0
    name = next(iter(config.split_fractions))
    for name, fraction in config.split_fractions.items():
        cumulative += fraction
        if position < cumulative:
            return name
    return name


class ShardWriter:
    """Writes documents into per-split, size-limited JSON Lines shards.

    Attributes:
        directory: Output directory.
        shard_size: Maximum documents per shard file.
    """

    def __init__(self, directory: Path, shard_size: int) -> None:
        """Initialize the writer.

        Args:
            directory: Output directory; created on demand.
            shard_size: Maximum documents per shard.
        """
        self.directory = directory
        self.shard_size = shard_size
        directory.mkdir(parents=True, exist_ok=True)
        self._counts: dict[str, int] = {}
        self._shards: dict[str, int] = {}
        self._files: dict[str, Any] = {}
        self._per_file: dict[str, int] = {}

    def write(self, split: str, record: dict[str, Any]) -> None:
        """Write one record into the current shard of a split.

        Args:
            split: Split name.
            record: Record to serialize.
        """
        if split not in self._files or self._per_file[split] >= self.shard_size:
            self._roll(split)
        self._files[split].write(json.dumps(record, ensure_ascii=False) + "\n")
        self._per_file[split] += 1
        self._counts[split] = self._counts.get(split, 0) + 1

    def _roll(self, split: str) -> None:
        """Close the current shard of a split and open the next one.

        Args:
            split: Split name.
        """
        if split in self._files:
            self._files[split].close()
        index = self._shards.get(split, 0)
        self._shards[split] = index + 1
        path = self.directory / f"{split}-{index:05d}.jsonl"
        self._files[split] = path.open("w", encoding="utf-8")
        self._per_file[split] = 0

    def close(self) -> None:
        """Close every open shard."""
        for handle in self._files.values():
            handle.close()
        self._files.clear()

    @property
    def counts(self) -> dict[str, int]:
        """Documents written per split."""
        return dict(self._counts)

    @property
    def shard_counts(self) -> dict[str, int]:
        """Shard files opened per split."""
        return dict(self._shards)

    def written_files(self) -> dict[str, int]:
        """Return the documents written per shard file.

        Returns:
            A mapping from file name to document count.
        """
        result: dict[str, int] = {}
        for split, shards in self._shards.items():
            remaining = self._counts.get(split, 0)
            for index in range(shards):
                size = min(self.shard_size, remaining)
                result[f"{split}-{index:05d}.jsonl"] = size
                remaining -= size
        return result


# --------------------------------------------------------------------------------------
# stages
# --------------------------------------------------------------------------------------


@dataclass
class TextStage(Stage):
    """Base class carrying the configuration and layout shared by text stages.

    Attributes:
        config: Pipeline configuration.
        layout: Resolved file locations.
    """

    config: TextPipelineConfig
    layout: TextLayout
    modality: ClassVar[Modality] = "text"
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
        return text_report.render(self._meta, result)


class CleanStage(TextStage):
    """Decode entities, strip markup, normalize Unicode and whitespace."""

    name: ClassVar[str] = "clean"

    def run(self, ctx: RunContext) -> StageResult:
        """Clean every raw document and write the cleaned corpus.

        Args:
            ctx: Active run context.

        Returns:
            Counts, character totals, length percentiles and a document sample.
        """
        self._meta = ctx.meta
        field_name = self.config.io.text_field
        rows_in = 0
        chars_in = 0
        chars_out = 0
        empty_removed = 0
        lengths: list[int] = []
        samples = Reservoir(self.config.report.sample_size, self.config.report.sample_seed)

        def records() -> Iterator[dict[str, Any]]:
            nonlocal rows_in, chars_in, chars_out, empty_removed
            for record in read_jsonl(self.layout.raw):
                rows_in += 1
                original = str(record.get(field_name, ""))
                chars_in += len(original)
                cleaned = clean_text(original, self.config.clean)
                if not cleaned and self.config.clean.drop_empty:
                    empty_removed += 1
                    continue
                chars_out += len(cleaned)
                lengths.append(len(cleaned))
                samples.offer(f"{original[:100]} -> {cleaned[:100]}")
                yield {field_name: cleaned}

        rows_out = write_jsonl(self.layout.cleaned, records())
        logger.info("clean: %d -> %d documents", rows_in, rows_out)
        return StageResult(
            name=self.name,
            rows_in=rows_in,
            rows_out=rows_out,
            counters={"empty_after_cleaning": empty_removed},
            details={
                "chars_in": chars_in,
                "chars_out": chars_out,
                "lengths": lengths,
                "samples": samples.items,
            },
            outputs=[self.layout.cleaned],
        )


class FilterStage(TextStage):
    """Apply length, alphabetic-ratio and repeated-line quality rules."""

    name: ClassVar[str] = "filter"

    def run(self, ctx: RunContext) -> StageResult:
        """Filter the cleaned corpus and write the surviving documents.

        Args:
            ctx: Active run context.

        Returns:
            Counts, per-rule drop counts, kept-document distributions and a sample
            of removed documents.
        """
        self._meta = ctx.meta
        field_name = self.config.io.text_field
        rows_in = 0
        counters: dict[str, int] = {}
        lengths: list[int] = []
        alpha_ratios: list[float] = []
        repeated_ratios: list[float] = []
        removed = Reservoir(self.config.report.sample_size, self.config.report.sample_seed)

        def records() -> Iterator[dict[str, Any]]:
            nonlocal rows_in
            for record in read_jsonl(self.layout.cleaned):
                rows_in += 1
                text = str(record.get(field_name, ""))
                reason = filter_reason(text, self.config.filter)
                if reason is not None:
                    counters[reason] = counters.get(reason, 0) + 1
                    removed.offer(f"[{reason}] {text}")
                    continue
                lengths.append(len(text))
                alpha_ratios.append(alphabetic_ratio(text))
                repeated_ratios.append(repeated_line_ratio(text))
                yield record

        rows_out = write_jsonl(self.layout.filtered, records())
        logger.info("filter: %d -> %d documents", rows_in, rows_out)
        return StageResult(
            name=self.name,
            rows_in=rows_in,
            rows_out=rows_out,
            counters=counters,
            details={
                "thresholds": self.config.filter.model_dump(),
                "lengths": lengths,
                "alpha_ratios": alpha_ratios,
                "repeated_ratios": repeated_ratios,
                "removed_samples": removed.items,
            },
            outputs=[self.layout.filtered],
        )


class DedupStage(TextStage):
    """Remove exact duplicates by SHA-256 of the normalized document."""

    name: ClassVar[str] = "dedup"

    def run(self, ctx: RunContext) -> StageResult:
        """Deduplicate the filtered corpus.

        Args:
            ctx: Active run context.

        Returns:
            Counts, duplicate rate and a sample of removed duplicates.
        """
        self._meta = ctx.meta
        field_name = self.config.io.text_field
        deduper = ExactDeduplicator(self.config.dedup)
        rows_in = 0
        duplicates = Reservoir(self.config.report.sample_size, self.config.report.sample_seed)

        def records() -> Iterator[dict[str, Any]]:
            nonlocal rows_in
            for record in read_jsonl(self.layout.filtered):
                rows_in += 1
                text = str(record.get(field_name, ""))
                if not deduper.accept(text):
                    duplicates.offer(text)
                    continue
                yield record

        rows_out = write_jsonl(self.layout.deduped, records())
        logger.info("dedup: %d -> %d documents", rows_in, rows_out)
        return StageResult(
            name=self.name,
            rows_in=rows_in,
            rows_out=rows_out,
            counters={"duplicate": deduper.duplicates},
            details={
                "settings": self.config.dedup.model_dump(),
                "duplicate_samples": duplicates.items,
            },
            outputs=[self.layout.deduped],
        )


class PIIStage(TextStage):
    """Mask email addresses, phone numbers and long digit runs per policy."""

    name: ClassVar[str] = "pii"

    def run(self, ctx: RunContext) -> StageResult:
        """Scrub PII from the deduplicated corpus.

        Args:
            ctx: Active run context.

        Returns:
            Counts, replacement totals per class and a sample of edited documents.
        """
        self._meta = ctx.meta
        field_name = self.config.io.text_field
        rows_in = 0
        counters = dict.fromkeys(PII_KINDS, 0)
        docs_touched = dict.fromkeys(PII_KINDS, 0)
        samples = Reservoir(self.config.report.sample_size, self.config.report.sample_seed)

        def records() -> Iterator[dict[str, Any]]:
            nonlocal rows_in
            for record in read_jsonl(self.layout.deduped):
                rows_in += 1
                text = str(record.get(field_name, ""))
                scrubbed, stats = scrub_pii(text, self.config.pii)
                for kind, count in stats.items():
                    counters[kind] += count
                    if count:
                        docs_touched[kind] += 1
                if any(stats.values()):
                    samples.offer(scrubbed)
                yield {**record, field_name: scrubbed}

        rows_out = write_jsonl(self.layout.scrubbed, records())
        logger.info("pii: %d documents, replacements %s", rows_out, counters)
        return StageResult(
            name=self.name,
            rows_in=rows_in,
            rows_out=rows_out,
            counters=counters,
            details={
                "policy": self.config.pii.model_dump(),
                "docs_touched": docs_touched,
                "samples": samples.items,
            },
            outputs=[self.layout.scrubbed],
        )


class FinalStage(TextStage):
    """Assign splits deterministically and write sharded output."""

    name: ClassVar[str] = "final"

    def run(self, ctx: RunContext) -> StageResult:
        """Shard the scrubbed corpus into train/val/test files.

        Args:
            ctx: Active run context.

        Returns:
            Counts per split, shard counts and final length percentiles.
        """
        self._meta = ctx.meta
        field_name = self.config.io.text_field
        writer = ShardWriter(self.layout.final_dir, self.config.final.shard_size)
        rows_in = 0
        lengths: list[int] = []
        try:
            for record in read_jsonl(self.layout.scrubbed):
                rows_in += 1
                text = str(record.get(field_name, ""))
                lengths.append(len(text))
                writer.write(assign_split(text, self.config.final), record)
        finally:
            writer.close()

        counts = writer.counts
        rows_out = sum(counts.values())
        logger.info("final: %d documents into %s", rows_out, self.layout.final_dir)
        return StageResult(
            name=self.name,
            rows_in=rows_in,
            rows_out=rows_out,
            counters={},
            details={
                "splits": counts,
                "shards": writer.shard_counts,
                "outputs": writer.written_files(),
                "lengths": lengths,
                "directory": str(self.layout.final_dir),
            },
            outputs=[self.layout.final_dir / name for name in writer.written_files()],
        )


STAGE_CLASSES: dict[str, type[TextStage]] = {
    "clean": CleanStage,
    "filter": FilterStage,
    "dedup": DedupStage,
    "pii": PIIStage,
    "final": FinalStage,
}


def build_stages(
    config: TextPipelineConfig, layout: TextLayout, selection: str = "all"
) -> list[TextStage]:
    """Instantiate the requested stages in pipeline order.

    Args:
        config: Pipeline configuration.
        layout: Resolved file locations.
        selection: A stage name, or ``all`` for the whole pipeline.

    Returns:
        The stages to execute, in order.

    Raises:
        ValueError: If the selection names no known stage.
    """
    if selection == "all":
        names = list(STAGE_ORDER)
    elif selection in STAGE_CLASSES:
        names = [selection]
    else:
        raise ValueError(
            f"unknown stage {selection!r}; expected one of all, {', '.join(STAGE_ORDER)}"
        )
    return [STAGE_CLASSES[name](config=config, layout=layout) for name in names]
