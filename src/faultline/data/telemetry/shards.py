"""Token shards and the window index (M1b step 12).

``faultline telemetry shards`` reads the tokenizer configuration, the tokenizer fitted from
it and the final tables, and writes, per site and split, under
``data/shards/telemetry/<tokenizer>/``:

* ``<source>__<split>.bin``: the fixed-order token stream as memory-mappable ``uint16``,
  thirteen tokens a step -- ``<sep>``, then one bin token for each core channel in
  identifier order (``JointVocab.encode_steps``). A missing value is ``<nan>``, and so is
  every value of a channel the tokenizer configuration excludes at a source (CARE power).
  No channel token is written: position identifies the channel, and the channel block
  stays reserved for the variable-set ablation over extended channels (ADR-0003);
* ``<source>__<split>.windows.parquet``: the window index. One row per step that ends an
  admissible window at some horizon: the turbine, the calendar year, the window's first
  and last step in the shard, and per label set and horizon the label and whether it is
  known. A window is known at a horizon only where it is admissible there
  (``windows.window_ends``: context inside one segment, horizon inside the split, no
  training window reading an excluded outage) *and* its label is not NA, so an NA label
  excludes the window at that horizon rather than counting as a negative. The narrow label
  is carried twice: as labelled, and without the events opened by the split
  specification's ``report_without_messages`` (ADR-0009): the second number every
  late-test result is reported with;
* ``manifest.json``: the layout, the tokenizer and every file's size.

Nothing is held whole: the stream is appended one turbine-year at a time and the index is
written a row group per turbine-year. A window never crosses a turbine-year: segments are
cut per turbine-year by the filter stage, which is also how the final stage counts them.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from faultline.config import config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.data.common.splits import SPLITS, SplitsConfig
from faultline.data.common.windows import assert_windows_within_splits, window_ends
from faultline.data.telemetry.adapters import ADAPTERS
from faultline.data.telemetry.bins import QuantileBinsConfig
from faultline.data.telemetry.harmonise import horizon_labels, to_seconds
from faultline.data.telemetry.labels import (
    LABEL_SETS,
    EventLabelsConfig,
    grid_coverage,
    label_column,
)
from faultline.data.telemetry.pipeline import (
    load_telemetry_config,
    parquet_files,
    stage_source_dir,
)
from faultline.data.telemetry.schemas import CHANNEL_NAMES
from faultline.data.telemetry.verify import opening_messages
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.tokenizers.joint import JointVocab
from faultline.tokenizers.layout import (
    BIN_OFFSET,
    CAPACITIES,
    CHANNEL_OFFSET,
    TELEMETRY_PREFIX_SIZE,
    VocabLayout,
)
from faultline.tokenizers.quantile_bins import QuantileBinTokenizer

logger = get_logger(__name__)

#: The on-disk token type: every telemetry identifier is below 1,184, and the joint
#: vocabulary with a full text block stays below 65,536 (ADR-0003).
TOKEN_DTYPE = np.uint16
#: Suffix of the narrow label recomputed without the events the listed messages open.
WITHOUT = "without"


def tokenizer_path(paths: ProjectPaths, config: QuantileBinsConfig) -> Path:
    """Where ``faultline telemetry bins`` wrote the tokenizer a configuration names."""
    return paths.tokenizers_dir / f"quantile_bins_v{config.version}_{config_hash(config)}.json"


def shards_dir(paths: ProjectPaths, tokenizer: Path) -> Path:
    """The directory one tokenizer's shards are written to, under the data root."""
    return paths.data_root / "shards" / "telemetry" / tokenizer.stem


# =====================================================================================
# the labels without the listed messages
# =====================================================================================


@dataclass
class EventStarts:
    """One source's narrow event starts per turbine, integer seconds.

    Attributes:
        every: Every narrow event, as the labels were built from.
        kept: Every narrow event not opened by a listed message.
        removed: Events opened by a listed message.
        covered: Per turbine, the steps the event record covers (the cleaned grid).
    """

    every: dict[str, np.ndarray]
    kept: dict[str, np.ndarray]
    removed: int
    covered: dict[str, np.ndarray]


def event_starts(
    paths: ProjectPaths, source: str, rules: EventLabelsConfig, messages: Sequence[str]
) -> EventStarts | None:
    """Read a status-string source's narrow events and drop those the messages open.

    Only a source whose events carry status strings can be read this way; at the others
    the narrow label has no message to be without, and ``None`` is returned.

    Args:
        paths: Resolved project paths.
        source: Source identifier.
        rules: The labelling file.
        messages: Normalised status messages whose events are left out.

    Returns:
        The event starts per turbine, both ways, and the grid coverage the labels used.
    """
    rule = rules.harmonised
    labels_dir = stage_source_dir(paths, "cleaned", source) / "labels"
    events_path = labels_dir / "events_narrow.parquet"
    stream_path = labels_dir / "status_stream.parquet"
    if (
        rule is None
        or source not in rules.status_strings.sources
        or not events_path.is_file()
        or not stream_path.is_file()
    ):
        return None
    events = pd.read_parquet(events_path)
    removed = np.zeros(len(events), dtype=bool)
    if messages and len(events):
        opened = opening_messages(
            events, pd.read_parquet(stream_path), rule.narrow_causes[0], rule.stop_status
        )
        removed = opened.isin(list(messages)).fillna(False).to_numpy(dtype=bool)
    seconds = to_seconds(events["start_utc"]) if len(events) else np.zeros(0, dtype=np.int64)
    turbines = events["turbine_id"].astype(str).to_numpy()
    every: dict[str, np.ndarray] = {}
    kept: dict[str, np.ndarray] = {}
    for turbine in np.unique(turbines):
        mine = turbines == turbine
        every[str(turbine)] = np.sort(seconds[mine])
        kept[str(turbine)] = np.sort(seconds[mine & ~removed])
    covered = grid_coverage(parquet_files(stage_source_dir(paths, "cleaned", source)))
    return EventStarts(every=every, kept=kept, removed=int(removed.sum()), covered=covered)


def _starts(seconds: np.ndarray) -> pd.Series[Any]:
    return pd.Series(pd.to_datetime(seconds, unit="s", utc=True))


def relabel(
    stamps: pd.Series[Any], starts: EventStarts, turbine: str, horizon: int, kept: bool
) -> pd.Series[Any]:
    """The narrow label of each step from event starts, as the label stage computes it.

    Args:
        stamps: The steps, UTC.
        starts: The source's event starts.
        turbine: The turbine.
        horizon: The horizon, in steps.
        kept: Use only the events no listed message opens.

    Returns:
        A nullable boolean Series aligned with ``stamps``.
    """
    chosen = (starts.kept if kept else starts.every).get(turbine, np.zeros(0, dtype=np.int64))
    covered = starts.covered.get(turbine, np.zeros(0, dtype=np.int64))
    return horizon_labels(stamps.reset_index(drop=True), _starts(chosen), horizon, covered)


# =====================================================================================
# the writer
# =====================================================================================


@dataclass
class ShardSet:
    """The shard files of one tokenizer, opened for appending.

    Attributes:
        root: The directory written to.
        steps: Steps written per (source, split).
    """

    root: Path
    steps: Counter[tuple[str, str]] = field(default_factory=Counter)
    _handles: dict[tuple[str, str], IO[bytes]] = field(default_factory=dict)
    _writers: dict[tuple[str, str], pq.ParquetWriter] = field(default_factory=dict)

    def tokens_path(self, key: tuple[str, str]) -> Path:
        """The token file of a (source, split)."""
        return self.root / f"{key[0]}__{key[1]}.bin"

    def index_path(self, key: tuple[str, str]) -> Path:
        """The window index of a (source, split)."""
        return self.root / f"{key[0]}__{key[1]}.windows.parquet"

    def write(self, key: tuple[str, str], steps: np.ndarray) -> int:
        """Append steps to a shard and return the step they start at."""
        offset = self.steps[key]
        if key not in self._handles:
            self._handles[key] = self.tokens_path(key).open("ab")
        self._handles[key].write(np.ascontiguousarray(steps, dtype=TOKEN_DTYPE).tobytes())
        self.steps[key] += len(steps)
        return offset

    def index(self, key: tuple[str, str], rows: pa.Table) -> None:
        """Append a row group to a window index."""
        if rows.num_rows == 0:
            return
        if key not in self._writers:
            self._writers[key] = pq.ParquetWriter(self.index_path(key), rows.schema)
        self._writers[key].write_table(rows)

    def close(self) -> None:
        """Close every open file."""
        for handle in self._handles.values():
            handle.close()
        for writer in self._writers.values():
            writer.close()
        self._handles.clear()
        self._writers.clear()


# =====================================================================================
# the tallies
# =====================================================================================


@dataclass
class ShardTally:
    """Everything the report counts.

    Attributes:
        steps: Steps per (split, source).
        nan: ``<nan>`` value tokens per (split, source).
        nan_by_channel: ``<nan>`` tokens per (source, channel).
        steps_by_source: Steps per source.
        histogram: Occurrences of every token identifier.
        windows: Known windows per (split, source, column).
        positive: Positive known windows per (split, source, column).
        by_year: Known and positive windows per (source, year, column).
        mismatches: Per source, stored labels differing from those recomputed from events.
        compared: Per source, labels compared.
        removed: Per source, events a listed message opens.
        checked: Windows re-checked for leakage.
    """

    steps: Counter[tuple[str, str]] = field(default_factory=Counter)
    nan: Counter[tuple[str, str]] = field(default_factory=Counter)
    nan_by_channel: Counter[tuple[str, str]] = field(default_factory=Counter)
    steps_by_source: Counter[str] = field(default_factory=Counter)
    histogram: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    windows: Counter[tuple[str, str, str]] = field(default_factory=Counter)
    positive: Counter[tuple[str, str, str]] = field(default_factory=Counter)
    by_year: Counter[tuple[str, int, str, str]] = field(default_factory=Counter)
    mismatches: Counter[str] = field(default_factory=Counter)
    compared: Counter[str] = field(default_factory=Counter)
    removed: dict[str, int] = field(default_factory=dict)
    checked: int = 0


def index_columns(horizons: Sequence[int]) -> list[tuple[str, int]]:
    """The label columns of the window index with their horizons; each has a ``_known`` twin."""
    columns = [(label_column(label_set, h), h) for label_set in LABEL_SETS for h in horizons]
    columns += [(f"{label_column('narrow', h)}_{WITHOUT}", h) for h in horizons]
    return columns


def encode_turbine_year(
    frame: pd.DataFrame,
    vocab: JointVocab,
    masked: Sequence[str],
    splits: SplitsConfig,
    horizons: Sequence[int],
    starts: EventStarts | None,
    shards: ShardSet,
    tally: ShardTally,
) -> None:
    """Encode one turbine-year into its shards and its window index.

    Args:
        frame: The final rows of one turbine-year.
        vocab: The vocabulary the stream is encoded with.
        masked: Channels emitted as ``<nan>`` at this source.
        splits: The split specification.
        horizons: Horizons, in steps.
        starts: The source's event starts, for the narrow label without the listed
            messages; ``None`` where the source carries no status strings.
        shards: The shard files.
        tally: The counts for the report, updated in place.

    Raises:
        ValueError: If a split's rows are not one contiguous run of the turbine-year.
    """
    frame = frame.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)
    source = str(frame["source"].iloc[0])
    turbine = str(frame["turbine_id"].iloc[0])
    stamps = pd.to_datetime(frame["timestamp_utc"], utc=True)
    years = stamps.dt.year.to_numpy()
    split = frame["split"].to_numpy(dtype=object)
    steps = vocab.encode_steps(frame, masked)
    nan_id = vocab.special("<nan>")
    channels = vocab.bin_tokenizer.channels if vocab.bin_tokenizer else []

    labels: dict[str, pd.Series[Any]] = {}
    for label_set in LABEL_SETS:
        for h in horizons:
            column = label_column(label_set, h)
            labels[column] = (
                frame[column].astype("boolean")
                if column in frame.columns
                else pd.Series(pd.NA, index=frame.index, dtype="boolean")
            )
    for h in horizons:
        column = label_column("narrow", h)
        if starts is None:
            labels[f"{column}_{WITHOUT}"] = labels[column]
            continue
        recomputed = relabel(stamps, starts, turbine, h, kept=False)
        stored = labels[column].reset_index(drop=True)
        differ = (recomputed.isna() != stored.isna()) | (
            recomputed.fillna(False) != stored.fillna(False)
        )
        tally.mismatches[source] += int(differ.sum())
        tally.compared[source] += len(stored)
        labels[f"{column}_{WITHOUT}"] = relabel(stamps, starts, turbine, h, kept=True)

    admissible = {h: window_ends(frame, splits, h) for h in horizons}
    for h in horizons:
        tally.checked += assert_windows_within_splits(frame, admissible[h], splits, h)
    context = splits.windows.context_steps

    for name in pd.unique(split):
        rows = np.flatnonzero(split == name)
        if rows.size and not (np.diff(rows) == 1).all():
            raise ValueError(f"{source} {turbine}: split {name} is not one run of the turbine-year")
        key = (source, str(name))
        offset = shards.write(key, steps[rows])
        block = steps[rows]
        tally.steps[(str(name), source)] += int(rows.size)
        tally.steps_by_source[source] += int(rows.size)
        values = block[:, 1:]
        tally.nan[(str(name), source)] += int((values == nan_id).sum())
        for position, channel in enumerate(channels):
            tally.nan_by_channel[(source, channel)] += int((values[:, position] == nan_id).sum())
        tally.histogram += np.bincount(block.ravel(), minlength=tally.histogram.size)

        candidate = np.zeros(rows.size, dtype=bool)
        for h in horizons:
            candidate |= admissible[h][rows]
        chosen = rows[candidate]
        end = offset + np.flatnonzero(candidate)
        start = end - (context - 1)
        if chosen.size and start.min() < offset:
            raise ValueError(f"{source} {turbine}: a window starts before its turbine-year")
        columns: dict[str, Any] = {
            "turbine_id": pa.array([turbine] * chosen.size, type=pa.string()),
            "year": pa.array(years[chosen].astype(np.int16)),
            "start_step": pa.array(start.astype(np.int64)),
            "end_step": pa.array(end.astype(np.int64)),
        }
        for column, h in index_columns(horizons):
            values_ = labels[column].to_numpy(dtype=object)[chosen]
            known = admissible[h][chosen] & np.array([v is not pd.NA for v in values_], dtype=bool)
            positive = known & np.array([v is True for v in values_], dtype=bool)
            columns[column] = pa.array(positive)
            columns[f"{column}_known"] = pa.array(known)
            tally.windows[(str(name), source, column)] += int(known.sum())
            tally.positive[(str(name), source, column)] += int(positive.sum())
            for year in np.unique(years[chosen]):
                here = years[chosen] == year
                tally.by_year[(source, int(year), column, "windows")] += int((known & here).sum())
                tally.by_year[(source, int(year), column, "positive")] += int(
                    (positive & here).sum()
                )
        shards.index(key, pa.table(columns))


# =====================================================================================
# the report
# =====================================================================================


def _pct(part: int, whole: int, digits: int = 2) -> str:
    return f"{part / whole * 100:.{digits}f}%" if whole else "n/a"


def _order(key: tuple[str, str]) -> tuple[int, str]:
    return (SPLITS.index(key[0]) if key[0] in SPLITS else len(SPLITS), key[1])


def render_shards(
    header: str,
    tally: ShardTally,
    shards: ShardSet,
    vocab: JointVocab,
    horizons: Sequence[int],
    splits: SplitsConfig,
    dataset_level: Sequence[str],
    masked: Mapping[str, Sequence[str]],
) -> str:
    """Render the shard report.

    Args:
        header: The report header.
        tally: The counts.
        shards: The shard files written.
        vocab: The vocabulary.
        horizons: Horizons, in steps.
        splits: The split specification.
        dataset_level: Sources scored per dataset (ADR-0010).
        masked: Per source, channels emitted as ``<nan>``.

    Returns:
        A Markdown document.
    """
    assert vocab.bin_tokenizer is not None
    channels = vocab.bin_tokenizer.channels
    per_step = 1 + len(channels)
    context = splits.windows.context_steps
    stream = kv_table(
        {
            "a step": f"{per_step} tokens: `<sep>`, then one bin token for each of "
            f"{', '.join(f'`{c}`' for c in channels)}",
            "channel tokens": "none emitted: position in the step is the channel. The channel "
            f"block ({CAPACITIES['channel']} identifiers from {CHANNEL_OFFSET}) stays reserved "
            "for the variable-set ablation over extended channels (ADR-0003)",
            "bin tokens": f"{vocab.bin_tokenizer.n_bins} local bins from identifier {BIN_OFFSET}",
            "missing value": "`<nan>`",
            "emitted as `<nan>` whatever the value": "; ".join(
                f"{s}: {', '.join(names)}" for s, names in masked.items()
            )
            or "nothing",
            "vocabulary": f"the telemetry prefix, {TELEMETRY_PREFIX_SIZE:,} identifiers; no text",
            "on disk": "uint16, memory-mappable, one file per site and split",
            "a window": f"{context} steps, {context * per_step:,} tokens",
        }
    )
    rows: list[tuple[str, ...]] = []
    totals: Counter[str] = Counter()
    for key in sorted(tally.steps, key=_order):
        split, source = key
        steps = tally.steps[key]
        tokens = steps * per_step
        size = shards.tokens_path((source, split)).stat().st_size
        totals[split] += tokens
        rows.append(
            (
                split,
                source,
                f"{steps:,}",
                f"{tokens:,}",
                f"{size:,}",
                _pct(tally.nan[key], steps * len(channels)),
            )
        )
    for split in SPLITS:
        if totals[split]:
            rows.append((f"**{split}**", "all", "", f"**{totals[split]:,}**", "", ""))
    tokens_section = section(
        "Tokens per split and site",
        table(
            [
                "split",
                "source",
                "steps",
                "tokens",
                "bytes on disk",
                "`<nan>` share of value tokens",
            ],
            rows,
        ),
    )
    used = np.flatnonzero(tally.histogram)
    kinds = Counter(vocab.decode(int(i)).kind for i in used)
    nan_total = int(tally.histogram[vocab.special("<nan>")])
    all_tokens = int(tally.histogram.sum())
    nan_rows = [
        (
            f"`{channel}`",
            *(
                _pct(tally.nan_by_channel[(source, channel)], tally.steps_by_source[source], 1)
                for source in tally.steps_by_source
            ),
        )
        for channel in channels
    ]
    unique_section = section(
        "Tokens in use",
        kv_table(
            {
                "distinct tokens in the shards": f"{used.size:,} of {TELEMETRY_PREFIX_SIZE:,}",
                "of which": ", ".join(f"{kind} {count}" for kind, count in sorted(kinds.items())),
                "`<nan>` tokens": f"{nan_total:,} of {all_tokens:,} "
                f"({_pct(nan_total, all_tokens)})",
            }
        )
        + "\n**`<nan>` share per channel and site** (every split)\n\n"
        + table(["channel", *tally.steps_by_source], nan_rows),
    )

    window_body = (
        "A window is counted at a horizon where it is admissible there and its label is known; "
        "an NA label excludes it at that horizon, and is never a negative. `positive` is the "
        "share of those windows whose horizon holds an event.\n"
    )
    listed = ", ".join(f"`{m}`" for m in splits.report_without_messages)
    for label_set in (*LABEL_SETS, f"narrow {WITHOUT}"):
        columns = (
            [f"{label_column('narrow', h)}_{WITHOUT}" for h in horizons]
            if label_set.endswith(WITHOUT)
            else [label_column(label_set, h) for h in horizons]
        )
        headers = ["split", "source"]
        for column in columns:
            name = column.split("_within_")[1].removesuffix(f"_{WITHOUT}")
            headers += [f"windows {name}", f"positive {name}"]
        rows = []
        for key in sorted(tally.steps, key=_order):
            split, source = key
            if source in dataset_level and label_set != "narrow":
                continue
            cells: list[str] = [split, source]
            for column in columns:
                count = tally.windows[(split, source, column)]
                positive = tally.positive[(split, source, column)]
                cells += [
                    f"{count:,}",
                    "per dataset"
                    if source in dataset_level
                    else f"{positive:,} ({_pct(positive, count)})",
                ]
            rows.append(tuple(cells))
        title = (
            f"**Narrow, without the events {listed} opens** "
            "(ADR-0009: every late-test result is also reported this way)"
            if label_set.endswith(WITHOUT)
            else f"**{label_set.capitalize()} label**"
        )
        window_body += f"\n{title}\n\n" + table(headers, rows)
    for source in splits.per_year_sites:
        years = sorted({y for s, y, _, _ in tally.by_year if s == source})
        rows = []
        for year in years:
            cells = [str(year)]
            for label_set in LABEL_SETS:
                for h in horizons:
                    column = label_column(label_set, h)
                    count = tally.by_year[(source, year, column, "windows")]
                    positive = tally.by_year[(source, year, column, "positive")]
                    cells.append(f"{count:,} ({_pct(positive, count)})")
            rows.append(tuple(cells))
        window_body += (
            f"\n**{source}, per calendar year** (`per_year_sites`: never pooled only). Known "
            "windows, and the positive share\n\n"
            + table(["year", *(label_column(s, h) for s in LABEL_SETS for h in horizons)], rows)
        )
    windows_section = section("Windows per split and horizon", window_body)

    checks = kv_table(
        {
            "windows re-checked for leakage (every horizon)": f"{tally.checked:,}, none crossing "
            "a split, leaving a segment or reading an excluded outage",
            **{
                f"{source}: stored narrow labels equal to those recomputed from events": (
                    f"{tally.compared[source] - tally.mismatches[source]:,} of "
                    f"{tally.compared[source]:,}"
                )
                for source in tally.compared
            },
            **{
                f"{source}: narrow events opened by the listed messages": f"{count:,}"
                for source, count in tally.removed.items()
            },
            "every token file holds steps x tokens x 2 bytes": "yes",
        }
    )
    total_train = totals["train"]
    sizing = kv_table(
        {
            "training tokens": f"{total_train:,}",
            "training steps": f"{total_train // per_step:,}",
            "reading": "the model size and context length are chosen from this count at gate 3, "
            "not here",
        }
    )
    return "".join(
        [
            header,
            section("The stream", stream),
            tokens_section,
            unique_section,
            windows_section,
            section("Checks", checks),
            section("For gate 3", sizing),
        ]
    )


def build_shards(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """Write the token shards, the window index and the manifest, and report them.

    Args:
        paths: Resolved project paths.
        config_path: The tokenizer configuration.

    Returns:
        The manifest and the report.

    Raises:
        FileNotFoundError: If the tokenizer the configuration names was never fitted.
        ValueError: If a token file's size disagrees with its steps.
    """
    config = load_config(config_path, QuantileBinsConfig)
    source_tokenizer = tokenizer_path(paths, config)
    if not source_tokenizer.is_file():
        raise FileNotFoundError(f"{source_tokenizer} not found: run `faultline telemetry bins`")
    tokenizer = QuantileBinTokenizer.load(source_tokenizer)
    telemetry = load_telemetry_config(paths.repo_root / config.telemetry_config)
    splits = load_config(paths.repo_root / telemetry.final.splits_config, SplitsConfig)
    rules = load_config(paths.repo_root / str(telemetry.events.labels_config), EventLabelsConfig)
    horizons = list(telemetry.events.horizons_steps)
    layout = VocabLayout.from_sizes(0, len(CHANNEL_NAMES), tokenizer.n_bins)
    vocab = JointVocab(layout, bin_tokenizer=tokenizer)

    root = shards_dir(paths, source_tokenizer)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    shards = ShardSet(root)
    tally = ShardTally(histogram=np.zeros(layout.total_size, dtype=np.int64))
    try:
        for source in ADAPTERS:
            files = parquet_files(stage_source_dir(paths, "final", source))
            if not files:
                continue
            logger.info("%s: encoding %d turbine-years", source, len(files))
            starts = event_starts(paths, source, rules, splits.report_without_messages)
            if starts is not None:
                tally.removed[source] = starts.removed
            for path in files:
                frame = pd.read_parquet(path)
                if frame.empty or "split" not in frame.columns:
                    continue
                encode_turbine_year(
                    frame,
                    vocab,
                    config.excluded.get(source, []),
                    splits,
                    horizons,
                    starts,
                    shards,
                    tally,
                )
    finally:
        shards.close()

    per_step = 1 + len(tokenizer.channels)
    entries: dict[str, dict[str, Any]] = {}
    for (source, split), steps in sorted(shards.steps.items()):
        tokens_file = shards.tokens_path((source, split))
        size = tokens_file.stat().st_size
        if size != steps * per_step * np.dtype(TOKEN_DTYPE).itemsize:
            raise ValueError(f"{tokens_file} holds {size} bytes for {steps} steps")
        index_file = shards.index_path((source, split))
        entries[f"{source}__{split}"] = {
            "tokens": tokens_file.name,
            "steps": steps,
            "tokens_count": steps * per_step,
            "bytes": size,
            "windows": index_file.name if index_file.is_file() else None,
        }
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "tokenizer": source_tokenizer.relative_to(paths.repo_root).as_posix(),
                "edges_hash": tokenizer.meta.get("config_hash"),
                "tokenizer_config": config_path.as_posix(),
                "telemetry_config": config.telemetry_config,
                "splits_config": telemetry.final.splits_config,
                "dtype": "uint16",
                "tokens_per_step": per_step,
                "step": ["<sep>", *tokenizer.channels],
                "specials": {"<sep>": vocab.special("<sep>"), "<nan>": vocab.special("<nan>")},
                "bin_offset": BIN_OFFSET,
                "vocabulary_size": layout.total_size,
                "context_steps": splits.windows.context_steps,
                "horizons_steps": horizons,
                "masked": config.excluded,
                "files": entries,
                "git_sha": git_sha(paths.repo_root),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    dataset_level = list(rules.event_info.sources)
    header = "# Token shards and the window index (M1b step 12)\n\n" + kv_table(
        {
            "tokenizer config": config_path.as_posix(),
            "tokenizer": source_tokenizer.relative_to(paths.repo_root).as_posix(),
            "edges hash": tokenizer.meta.get("config_hash", ""),
            "telemetry config": config.telemetry_config,
            "splits": telemetry.final.splits_config,
            "shards": root.relative_to(paths.data_root).as_posix()
            + " (under the data root; never committed)",
            "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "git_sha": git_sha(paths.repo_root),
            "generated by": "faultline telemetry shards",
        }
    )
    report = render_shards(
        header, tally, shards, vocab, horizons, splits, dataset_level, config.excluded
    )
    destination = paths.data_reports_dir / f"shards_{datetime.now(tz=UTC):%Y%m%d}.md"
    destination.write_text(report, encoding="utf-8")
    logger.info("wrote %s and %s", manifest, destination)
    return manifest, destination
