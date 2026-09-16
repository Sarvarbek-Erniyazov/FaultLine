"""Shards for the M3 mixture's three streams, and the token counts the arms are budgeted from.

``tel`` is the M1 shards as they are: the joint vocabulary encodes telemetry to the same
bytes (ADR-0003 note of 2026-09-16), so nothing is rewritten. Only a run index is added, so
a context of ``context_tokens`` can be drawn without crossing a segment.

``txt`` is the M2 text shards at joint ids: every local id ``i`` becomes ``1184 + i``, and
the local ``<sep>`` (32,768) becomes the structural ``<sep>`` (8). Token counts are
unchanged.

``tel+status`` is written here, twice: once with normalized status strings (the default,
ADR-0017) and once with the provider's own casing (the ablation). A step is its 13 telemetry
tokens, then ``<txt> message </txt>`` for each status message attached to it.

**The attachment rule, chosen so no window reveals a message early.** A message is attached
to the first step at or after its start, its start rounded **up** to the 10-minute grid. An
event label at step ``t`` looks for starts in ``(t, t + H]`` (``harmonise.horizon_labels``),
so a message starting at 12:13 appears after step 12:20. Step 12:20's label no longer counts
that start as future. Rounding down would put it after step 12:10, whose label still does. A
message whose step is not in the final rows (a filtered outage, another split) is not
written, and is counted.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from faultline.config import config_hash, load_config
from faultline.data.common.report import kv_table, section, table
from faultline.data.telemetry.bins import QuantileBinsConfig
from faultline.data.telemetry.pipeline import parquet_files, stage_source_dir
from faultline.data.telemetry.schemas import CHANNEL_NAMES
from faultline.data.telemetry.shards import shards_dir as telemetry_shards_dir
from faultline.data.telemetry.shards import tokenizer_path as telemetry_tokenizer_path
from faultline.data.text.code_book import CODE_BOOK_SOURCE
from faultline.data.text.shards import load_text_shards_config
from faultline.data.text.shards import shards_dir as text_shards_dir
from faultline.data.text.shards import tokenizer_path as text_tokenizer_path
from faultline.data.text.status_convention import normalize_status
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.tokenizers.joint import JointVocab
from faultline.tokenizers.layout import TEXT_OFFSET, VocabLayout
from faultline.tokenizers.quantile_bins import QuantileBinTokenizer
from faultline.tokenizers.text_bpe import TextBPETokenizer
from faultline.training.mixture import STREAM_DIRS, STREAMS, JointMixtureConfig, StreamName

logger = get_logger(__name__)

#: One grid step.
STEP = "10min"

#: The two ``tel+status`` variants: the default and the ablation.
CONVENTIONS: dict[str, Callable[[str], str]] = {
    "normalized": normalize_status,
    "raw": lambda text: text,
}

#: Measured throughput of the M2 text rungs at context 2,048 (training tokens over wall
#: clock, periodic validation included), for the GPU-hour projection only.
M2_TOKENS_PER_SECOND: dict[str, float] = {"S2": 10_027_008 / 6107.8, "S3": 10_027_008 / 7207.0}


def nanoseconds(values: Any, ceil: bool = False) -> np.ndarray:
    """UTC times as integer nanoseconds, whatever resolution or backing they were read with.

    Args:
        values: Timestamps.
        ceil: Round each up to the grid step first.

    Returns:
        Integer nanoseconds since the epoch.
    """
    index = pd.DatetimeIndex(pd.to_datetime(values, utc=True))
    if ceil:
        index = index.ceil(STEP)
    return np.asarray(index.as_unit("ns").asi8, dtype=np.int64)  # type: ignore[attr-defined]


def attach_steps(starts: Any, step_stamps: np.ndarray) -> np.ndarray:
    """The step each message is attached to, or -1 where that step is not in the rows.

    Args:
        starts: Message start times, UTC.
        step_stamps: The rows' step timestamps as integer nanoseconds, ascending.

    Returns:
        Per message, the index of the first step at or after its start, or -1.
    """
    keys = nanoseconds(starts, ceil=True)
    position = np.searchsorted(step_stamps, keys)
    found = position < step_stamps.size
    found[found] = step_stamps[position[found]] == keys[found]
    return np.where(found, position, -1)


def interleave(
    steps: np.ndarray, message_steps: np.ndarray, messages: list[np.ndarray]
) -> tuple[np.ndarray, np.ndarray]:
    """Write each step's telemetry tokens, then its messages' tokens, in step order.

    Args:
        steps: ``(n, tokens_per_step)`` telemetry tokens.
        message_steps: Per message, its step index, ascending (ties in message order).
        messages: Per message, its tokens including ``<txt>`` and ``</txt>``.

    Returns:
        The flat token stream, and the token offset of every step.
    """
    n, width = steps.shape
    lengths = np.array([m.size for m in messages], dtype=np.int64)
    extra = np.bincount(message_steps, weights=lengths, minlength=n).astype(np.int64)
    step_lengths = width + extra
    offsets = np.concatenate([[0], np.cumsum(step_lengths)[:-1]]).astype(np.int64)
    out = np.empty(int(step_lengths.sum()), dtype=np.uint16)
    out[(offsets[:, None] + np.arange(width)).ravel()] = steps.ravel()
    if messages:
        before = np.cumsum(lengths) - lengths
        first = np.searchsorted(message_steps, message_steps, side="left")
        within = before - before[first]
        starts = offsets[message_steps] + width + within
        positions = np.repeat(starts, lengths) + (
            np.arange(int(lengths.sum())) - np.repeat(before, lengths)
        )
        out[positions] = np.concatenate(messages)
    return out, offsets


def contiguous_runs(frame: pd.DataFrame) -> Iterator[tuple[str, int, np.ndarray]]:
    """Runs of rows sharing a split and a segment, in row order.

    Args:
        frame: One turbine-year, sorted by time.

    Yields:
        The split, the segment and the row indices of each run.
    """
    split = frame["split"].astype(str).to_numpy()
    segment = frame["segment_id"].to_numpy()
    change = np.flatnonzero((split[1:] != split[:-1]) | (segment[1:] != segment[:-1])) + 1
    for rows in np.split(np.arange(len(frame)), change):
        if rows.size:
            yield str(split[rows[0]]), int(segment[rows[0]]), rows


@dataclass
class StreamTally:
    """What one stream file holds, for the report.

    Attributes:
        tokens: Tokens written.
        steps: Telemetry steps.
        windows: Admissible context windows at the configured stride.
        messages: Status messages written.
        message_tokens: Tokens those messages cost, wrappers included.
    """

    tokens: int = 0
    steps: int = 0
    windows: int = 0
    messages: int = 0
    message_tokens: int = 0


@dataclass
class MixtureTally:
    """Counts across the build.

    Attributes:
        files: Per ``(stream, variant, source, split)``, its tally.
        dropped: Per source, messages whose step is not in the final rows.
        unmatched: Per source, messages with no text.
    """

    files: dict[tuple[str, str, str, str], StreamTally] = field(default_factory=dict)
    dropped: Counter[str] = field(default_factory=Counter)
    unmatched: Counter[str] = field(default_factory=Counter)

    def at(self, stream: str, variant: str, source: str, split: str) -> StreamTally:
        """The tally of one file, created on first use."""
        return self.files.setdefault((stream, variant, source, split), StreamTally())


def windows_in_run(step_offsets: np.ndarray, run_tokens: int, context: int, stride: int) -> int:
    """Context windows that start on a stride step and end inside the run.

    Args:
        step_offsets: Token offsets of the run's steps, from the run's start.
        run_tokens: Tokens in the run.
        context: Window length in tokens.
        stride: Steps between window starts.

    Returns:
        The admissible window count.
    """
    starts = step_offsets[::stride]
    return int((starts + context <= run_tokens).sum())


def code_book_casing(paths: ProjectPaths) -> dict[str, str]:
    """Lowercase status string to the provider's own casing, from the staged code book."""
    book = paths.stage_dir("raw", "text") / f"{CODE_BOOK_SOURCE}.jsonl"
    strings = [
        str(json.loads(line)["text"])
        for line in book.read_text(encoding="utf-8").splitlines()
        if line
    ]
    return {s.lower(): s for s in strings}


class _Writer:
    """Appends tokens and run rows to one stream directory."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.handles: dict[str, Any] = {}
        self.written: Counter[str] = Counter()
        self.runs: dict[str, list[dict[str, Any]]] = {}

    def append(self, key: str, tokens: np.ndarray, run: dict[str, Any]) -> None:
        if key not in self.handles:
            self.handles[key] = (self.root / f"{key}.bin").open("wb")
        run = {**run, "first_token": int(self.written[key]), "tokens": int(tokens.size)}
        tokens.astype(np.uint16).tofile(self.handles[key])
        self.written[key] += int(tokens.size)
        self.runs.setdefault(key, []).append(run)

    def close(self) -> None:
        for handle in self.handles.values():
            handle.close()
        for key, rows in self.runs.items():
            pq.write_table(pa.Table.from_pylist(rows), self.root / f"{key}.runs.parquet")


def build_mixture_shards(paths: ProjectPaths, config_path: Path) -> tuple[Path, Path]:
    """Write the ``txt`` and ``tel+status`` shards and every stream's run index, and report.

    Args:
        paths: Resolved project paths.
        config_path: The joint mixture configuration.

    Returns:
        The report and its JSON record.
    """
    config = load_config(config_path, JointMixtureConfig)
    bins_config = load_config(
        paths.repo_root / config.telemetry_tokenizer_config, QuantileBinsConfig
    )
    bins_file = telemetry_tokenizer_path(paths, bins_config)
    bins = QuantileBinTokenizer.load(bins_file)
    text_config_path = paths.repo_root / config.text_shards_config
    text_config = load_text_shards_config(text_config_path)
    text_file = text_tokenizer_path(paths, paths.repo_root / text_config.tokenizer_config)
    text = TextBPETokenizer.load(text_file)
    layout = VocabLayout.from_sizes(text.vocab_size, len(CHANNEL_NAMES), bins.n_bins)
    vocab = JointVocab(layout, text, bins)
    context, stride = config.context_tokens, config.window_stride_steps

    root = paths.data_root / "shards" / "joint" / f"joint_v{config.version}_{config_hash(config)}"
    tally = MixtureTally()

    # -- txt: remap the M2 text shards to joint ids ---------------------------------
    text_root = text_shards_dir(paths, text_file)
    text_manifest = json.loads((text_root / "manifest.json").read_text(encoding="utf-8"))
    local_sep = int(text_manifest["specials"]["<sep>"])
    txt_dir = root / STREAM_DIRS["txt"]
    txt_dir.mkdir(parents=True, exist_ok=True)
    for key, record in sorted(text_manifest["files"].items()):
        local = np.fromfile(text_root / str(record["tokens"]), dtype=np.uint16).astype(np.int64)
        joint = np.where(local == local_sep, vocab.special("<sep>"), local + TEXT_OFFSET)
        joint.astype(np.uint16).tofile(txt_dir / f"{key}.bin")
        source, split = key.rsplit("__", 1)
        entry = tally.at("txt", "-", source, split)
        entry.tokens = int(joint.size)
        entry.windows = max(0, int(joint.size) - context + 1)

    # -- tel and tel+status: one pass over the final telemetry -----------------------
    casing = code_book_casing(paths)
    encoded_cache: dict[tuple[str, str], np.ndarray] = {}

    def message_tokens(message: str, variant: str) -> np.ndarray:
        key = (message, variant)
        if key not in encoded_cache:
            provider = casing.get(message.lower(), message)
            encoded_cache[key] = np.asarray(
                vocab.encode_text(CONVENTIONS[variant](provider)), dtype=np.int64
            )
        return encoded_cache[key]

    tel_runs: dict[str, list[dict[str, Any]]] = {}
    tel_position: Counter[str] = Counter()
    status_writers = {
        variant: _Writer(root / f"{STREAM_DIRS['tel+status']}_{variant}") for variant in CONVENTIONS
    }
    telemetry_root = telemetry_shards_dir(paths, bins_file)
    telemetry_manifest = json.loads((telemetry_root / "manifest.json").read_text(encoding="utf-8"))
    m1_tokens = {
        key: np.memmap(telemetry_root / str(record["tokens"]), dtype=np.uint16, mode="r")
        for key, record in telemetry_manifest["files"].items()
    }
    try:
        from faultline.data.telemetry.adapters import ADAPTERS

        for source in ADAPTERS:
            files = parquet_files(stage_source_dir(paths, "final", source))
            if not files:
                continue
            stream = None
            if source in config.status_sources:
                path = (
                    paths.source_dir("cleaned", "telemetry", source)
                    / "labels"
                    / "status_stream.parquet"
                )
                stream = pd.read_parquet(path, columns=["turbine_id", "start_utc", "message"])
                tally.unmatched[source] += int(stream["message"].isna().sum())
                stream = stream.dropna(subset=["message"]).sort_values(
                    ["turbine_id", "start_utc"], kind="stable"
                )
            by_turbine = (
                dict(tuple(stream.groupby("turbine_id", sort=False))) if stream is not None else {}
            )
            masked = bins_config.excluded.get(source, [])
            logger.info("%s: %d turbine-years", source, len(files))
            for path in files:
                frame = pd.read_parquet(path)
                if frame.empty or "split" not in frame.columns:
                    continue
                frame = frame.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)
                turbine = str(frame["turbine_id"].iloc[0])
                year = int(pd.to_datetime(frame["timestamp_utc"].iloc[0], utc=True).year)
                steps = vocab.encode_steps(frame, masked)
                stamps = nanoseconds(frame["timestamp_utc"])
                attached = np.full(0, -1, dtype=np.int64)
                texts: list[str] = []
                if turbine in by_turbine:
                    messages = by_turbine[turbine]
                    attached = attach_steps(messages["start_utc"], stamps)
                    texts = [str(m) for m in messages["message"]]
                for split, segment, rows in contiguous_runs(frame):
                    run = {
                        "turbine_id": turbine,
                        "year": year,
                        "segment_id": segment,
                        "steps": int(rows.size),
                    }
                    block = steps[rows]
                    tel_tokens = block.ravel()
                    key = f"{source}__{split}"
                    # tel is the M1 shard itself: check this run against its bytes, write nothing
                    first = tel_position[key]
                    if not np.array_equal(
                        m1_tokens[key][first : first + tel_tokens.size], tel_tokens
                    ):
                        raise ValueError(
                            f"tel run of {turbine} {year} differs from the M1 shard {key}"
                        )
                    tel_runs.setdefault(key, []).append(
                        {**run, "first_token": int(first), "tokens": int(tel_tokens.size)}
                    )
                    tel_position[key] += int(tel_tokens.size)
                    entry = tally.at("tel", "-", source, split)
                    entry.tokens += int(tel_tokens.size)
                    entry.steps += int(rows.size)
                    entry.windows += windows_in_run(
                        np.arange(rows.size) * block.shape[1], tel_tokens.size, context, stride
                    )
                    if stream is None:
                        continue
                    inside = (attached >= rows[0]) & (attached <= rows[-1])
                    chosen = np.flatnonzero(inside)
                    order = chosen[np.argsort(attached[chosen], kind="stable")]
                    local_steps = attached[order] - rows[0]
                    for variant, writer in status_writers.items():
                        encoded = [message_tokens(texts[i], variant) for i in order]
                        tokens, offsets = interleave(block, local_steps, encoded)
                        writer.append(key, tokens, run)
                        entry = tally.at("tel+status", variant, source, split)
                        entry.tokens += int(tokens.size)
                        entry.steps += int(rows.size)
                        entry.messages += len(encoded)
                        entry.message_tokens += int(sum(e.size for e in encoded))
                        entry.windows += windows_in_run(offsets, tokens.size, context, stride)
            if stream is not None:
                # a message is written in at most one turbine-year: the one holding its step
                written = sum(
                    entry.messages
                    for (name, variant, src, _split), entry in tally.files.items()
                    if name == "tel+status" and variant == "normalized" and src == source
                )
                tally.dropped[source] = len(stream) - written
    finally:
        for writer in status_writers.values():
            writer.close()

    tel_dir = root / STREAM_DIRS["tel"]
    tel_dir.mkdir(parents=True, exist_ok=True)
    for key, runs in tel_runs.items():
        if tel_position[key] != m1_tokens[key].size:
            raise ValueError(
                f"tel {key}: {tel_position[key]} tokens against the M1 shard's "
                f"{m1_tokens[key].size}"
            )
        pq.write_table(pa.Table.from_pylist(runs), tel_dir / f"{key}.runs.parquet")

    manifest = {
        "config": config_path.as_posix(),
        "config_hash": config_hash(config),
        "telemetry_shards": telemetry_root.relative_to(paths.repo_root).as_posix(),
        "text_shards": text_root.relative_to(paths.repo_root).as_posix(),
        "dtype": "uint16",
        "vocabulary_size": layout.total_size,
        "context_tokens": context,
        "window_stride_steps": stride,
        "streams": {name: STREAM_DIRS[name] for name in STREAMS},
        "tel_status_variants": sorted(CONVENTIONS),
        "git_sha": git_sha(paths.repo_root),
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return write_mixture_report(paths, config, config_path, tally, root)


def train_tokens(
    tally: MixtureTally, config: JointMixtureConfig, stream: StreamName, variant: str
) -> int:
    """Training tokens one stream holds, over the arms' training sources where that applies."""
    return sum(
        entry.tokens
        for (name, var, source, split), entry in tally.files.items()
        if name == stream
        and split == "train"
        and (stream == "txt" or (source in config.training_sources and var == variant))
    )


def write_mixture_report(
    paths: ProjectPaths,
    config: JointMixtureConfig,
    config_path: Path,
    tally: MixtureTally,
    root: Path,
) -> tuple[Path, Path]:
    """Render per-stream token counts and per-arm projected budgets.

    Args:
        paths: Resolved project paths.
        config: The mixture configuration.
        config_path: Where it was read from.
        tally: The build's counts.
        root: The shard directory.

    Returns:
        The report and its JSON record.
    """
    order: list[str] = list(STREAMS)
    rows = []
    for (stream, variant, source, split), entry in sorted(
        tally.files.items(),
        key=lambda item: (order.index(item[0][0]), *item[0][1:]),
    ):
        rows.append(
            [
                stream,
                variant,
                source,
                split,
                f"{entry.tokens:,}",
                f"{entry.steps:,}" if entry.steps else "-",
                f"{entry.messages:,}" if stream == "tel+status" else "-",
                f"{entry.message_tokens / entry.tokens:.1%}"
                if stream == "tel+status" and entry.tokens
                else "-",
                f"{entry.windows:,}",
            ]
        )
    arm_rows = []
    record_arms = []
    for arm in config.arms:
        variant = arm.status_convention
        planned = config.stream_tokens(arm)
        cells = [arm.name, arm.role, variant if arm.share("tel+status") else "-"]
        passes = {}
        for stream in STREAMS:
            available = train_tokens(
                tally, config, stream, variant if stream == "tel+status" else "-"
            )
            passes[stream] = planned[stream] / available if available else float("nan")
            cells.append(
                f"{planned[stream]:,} ({arm.share(stream):.0%}; {passes[stream]:.2f} passes)"
            )
        hours = {
            rung: config.tokens_per_arm / rate / 3600 for rung, rate in M2_TOKENS_PER_SECOND.items()
        }
        cells += [f"{config.tokens_per_arm:,}", ", ".join(f"{r} {h:.1f}" for r, h in hours.items())]
        arm_rows.append(cells)
        record_arms.append(
            {
                "arm": arm.model_dump(mode="json"),
                "tokens": planned,
                "passes": passes,
                "projected_gpu_hours": hours,
            }
        )

    pairs: tuple[tuple[StreamName, str], ...] = (
        ("tel", "-"),
        ("txt", "-"),
        ("tel+status", "normalized"),
        ("tel+status", "raw"),
    )
    available_rows = [
        [stream, variant, f"{train_tokens(tally, config, stream, variant):,}"]
        for stream, variant in pairs
    ]
    body = "".join(
        [
            "# M3 mixture: stream token counts and per-arm budgets\n\n",
            kv_table(
                {
                    "configuration": config_path.as_posix(),
                    "config hash": config_hash(config),
                    "shards": root.relative_to(paths.repo_root).as_posix(),
                    "context (tokens)": f"{config.context_tokens:,}",
                    "window stride (steps)": config.window_stride_steps,
                    "budget": f"{config.tokens_per_arm:,} training tokens per arm, "
                    "equal across arms",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline model mixture-shards",
                }
            ),
            section(
                "1. Per-stream token counts",
                table(
                    [
                        "stream",
                        "status convention",
                        "source",
                        "split",
                        "tokens",
                        "steps",
                        "messages",
                        "message share",
                        f"{config.context_tokens:,}-token windows",
                    ],
                    rows,
                )
                + "\n`tel` is counted from the same encoding as the M1 shards and checked equal to "
                "them byte for byte; only its run index is kept. `txt` windows are counted at "
                "stride 1 over each source's stream. Messages not written: "
                + (
                    ", ".join(
                        f"{s} {n:,} (step not in the final rows)"
                        for s, n in sorted(tally.dropped.items())
                    )
                    or "none"
                )
                + "; messages with no text: "
                + (", ".join(f"{s} {n:,}" for s, n in sorted(tally.unmatched.items())) or "none")
                + ".\n",
            ),
            section(
                "2. Training tokens available to the arms",
                table(["stream", "status convention", "train tokens"], available_rows)
                + "\n`tel` and `tel+status` count the train split of "
                + ", ".join(config.training_sources)
                + "; `txt` counts every narrative source's train split.\n",
            ),
            section(
                "3. Projected per-arm budgets",
                table(
                    [
                        "arm",
                        "role",
                        "status convention",
                        *(f"{s} tokens" for s in STREAMS),
                        "total tokens",
                        "projected GPU-hours (observation, not a bound)",
                    ],
                    arm_rows,
                )
                + "\n**The bound is tokens seen, and it binds by construction.** Every arm "
                f"stops at {config.tokens_per_arm:,} training tokens. GPU-hours are projected "
                "from the M2 text rungs' measured rate at context 2,048, which includes "
                "periodic validation. "
                "They are an observation to plan by, and no run is cut by them. `passes` is the "
                "planned tokens over the stream's training tokens: above 1, the stream repeats. "
                "No run was made.\n",
            ),
        ]
    )
    stem = f"joint_mixture_v{config.version}_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(body, encoding="utf-8", newline="\n")
    record = {
        "files": [
            {"stream": k[0], "variant": k[1], "source": k[2], "split": k[3], **entry.__dict__}
            for k, entry in sorted(tally.files.items())
        ],
        "dropped": dict(tally.dropped),
        "unmatched": dict(tally.unmatched),
        "arms": record_arms,
    }
    json_path = paths.data_reports_dir / f"{stem}.json"
    json_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s and %s", report, json_path)
    return report, json_path
