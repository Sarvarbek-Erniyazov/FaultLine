"""M3's joint vocabulary, verified before it is used rather than assumed (ADR-0003 v2).

ADR-0003 v2 promises that the M1 telemetry vocabulary and the M2 text tokenizer concatenate
into one identifier space without retokenizing anything: telemetry is a stable prefix
``[0, 1184)``, text is appended at ``[1184, 1184 + 32768)``. That promise is load-bearing
for M3, so it is checked against the artefacts on disk, four ways:

1. **No identifier collision.** Every identifier of ``[0, 33952)`` decodes to exactly one
   block, telemetry blocks inside ``[0, 1184)`` and text inside ``[1184, 33952)``, and no
   encodable telemetry id is also an encodable text id.
2. **Telemetry ids are bit-identical to M1's.** (a) Every M1 ladder checkpoint's token
   embedding has exactly 1184 rows, so row ``r`` is joint id ``r``; (b) the M1 layout and the
   joint layout decode every id below 1184 identically; (c) for every shard file, the first
   turbine-year written to it is re-encoded with the M1 vocabulary and with the joint
   vocabulary, and both equal the bytes on disk; (d) no id in any M1 shard reaches 1184.
3. **The text region is exactly full.** The fitted text tokenizer has 32,768 ids, the text
   capacity; the text ids are the contiguous range ``[1184, 33952)``; the id after the last
   is not encodable.
4. **Round trip.** A telemetry-and-text fixture encoded with the joint vocabulary splits back
   into a telemetry part identical to the M1 vocabulary's encoding and text parts identical
   to the text tokenizer's own ids, and each text part decodes to its input.

**A failing check is a finding, not a bug to patch here.** It supersedes ADR-0003 and stops
M3 (the M3 entry brief, step C1). The command exits non-zero if any check fails.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from faultline.data.common.report import kv_table, section, table
from faultline.data.telemetry.schemas import CHANNEL_NAMES
from faultline.logging_utils import get_logger
from faultline.model.checkpoints import embedding_rows
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.tokenizers.joint import JointVocab
from faultline.tokenizers.layout import (
    TELEMETRY_PREFIX_SIZE,
    TEXT_CAPACITY,
    TEXT_OFFSET,
    VocabLayout,
)
from faultline.tokenizers.quantile_bins import QuantileBinTokenizer
from faultline.tokenizers.text_bpe import TextBPETokenizer

logger = get_logger(__name__)

#: Blocks that belong to the telemetry prefix.
PREFIX_KINDS = ("special", "channel", "bin", "time")


@dataclass(frozen=True)
class Check:
    """One assertion and its outcome.

    Attributes:
        name: What was asserted.
        passed: Whether it held.
        detail: The measured values behind the outcome.
    """

    name: str
    passed: bool
    detail: str


def joint_layout(bin_tokenizer: QuantileBinTokenizer, n_text: int) -> VocabLayout:
    """The layout M3 concatenates to: M1's telemetry blocks plus ``n_text`` text ids."""
    return VocabLayout.from_sizes(n_text, len(CHANNEL_NAMES), bin_tokenizer.n_bins)


def m1_layout(bin_tokenizer: QuantileBinTokenizer) -> VocabLayout:
    """The layout the M1 shards were written with (``build_shards``: no text)."""
    return VocabLayout.from_sizes(0, len(CHANNEL_NAMES), bin_tokenizer.n_bins)


def check_no_collision(layout: VocabLayout) -> Check:
    """Every id decodes to one block, and the two modalities' encodable ids are disjoint.

    Args:
        layout: The joint layout.

    Returns:
        The check.
    """
    misplaced: list[int] = []
    for global_id in range(layout.total_size):
        kind = layout.decode(global_id).kind
        in_prefix = global_id < TELEMETRY_PREFIX_SIZE
        if (kind in PREFIX_KINDS) != in_prefix:
            misplaced.append(global_id)
    telemetry = {layout.special_id(name) for name in ("<sep>", "<nan>", "<tel>", "</tel>")}
    telemetry |= {layout.channel_id(i) for i in range(layout.n_channels)}
    telemetry |= {layout.bin_id(i) for i in range(layout.n_bins)}
    text = {layout.text_id(i) for i in range(layout.n_text)}
    shared = telemetry & text
    passed = not misplaced and not shared and len(text) == layout.n_text
    return Check(
        "no id collision across [0,1184) and [1184,33952)",
        passed,
        f"{layout.total_size:,} ids decoded; {len(misplaced)} outside their region; "
        f"{len(telemetry):,} encodable telemetry ids (max {max(telemetry)}), "
        f"{len(text):,} text ids (min {min(text) if text else '-'}, "
        f"max {max(text) if text else '-'}); {len(shared)} shared",
    )


def check_prefix_decodes_identically(m1: VocabLayout, joint: VocabLayout) -> Check:
    """Every id below 1184 decodes the same under the M1 layout and the joint layout.

    Args:
        m1: The M1 layout.
        joint: The joint layout.

    Returns:
        The check.
    """
    differing = [i for i in range(TELEMETRY_PREFIX_SIZE) if m1.decode(i) != joint.decode(i)]
    return Check(
        "telemetry prefix decodes identically under M1 and joint layouts",
        not differing and m1.total_size == TELEMETRY_PREFIX_SIZE,
        f"M1 layout size {m1.total_size:,}; {TELEMETRY_PREFIX_SIZE:,} ids compared; "
        f"{len(differing)} differ",
    )


def check_checkpoint_rows(checkpoints: Sequence[Path]) -> Check:
    """Every M1 checkpoint's token embedding has one row per telemetry-prefix id.

    Args:
        checkpoints: The M1 ladder checkpoints.

    Returns:
        The check.
    """
    rows: dict[str, int] = {}
    for path in checkpoints:
        rows[path.name] = embedding_rows(path)
    wrong = {name: n for name, n in rows.items() if n != TELEMETRY_PREFIX_SIZE}
    return Check(
        "every M1 checkpoint embeds exactly the 1184-id telemetry prefix",
        bool(rows) and not wrong,
        f"{len(rows)} checkpoints read; row counts {sorted(set(rows.values()))}; "
        f"{len(wrong)} differ" + (f": {wrong}" if wrong else ""),
    )


def check_shard_prefix(
    m1: JointVocab,
    joint: JointVocab,
    frame: pd.DataFrame,
    masked: Sequence[str],
    on_disk: np.ndarray,
) -> Check:
    """One turbine-year re-encoded both ways equals the steps an M1 shard holds.

    Args:
        m1: The vocabulary the shards were written with.
        joint: The joint vocabulary.
        frame: The turbine-year's rows of one split, in the order ``build_shards`` wrote.
        masked: Channels emitted as ``<nan>`` at this source.
        on_disk: The shard's first steps, ``(steps, tokens_per_step)``.

    Returns:
        The check.
    """
    a = m1.encode_steps(frame, masked)
    b = joint.encode_steps(frame, masked)
    same = a.shape == b.shape == on_disk.shape and bool((a == b).all() and (a == on_disk).all())
    return Check(
        "",
        same,
        f"{a.shape[0]:,} steps x {a.shape[1]} tokens; M1 == joint: "
        f"{bool(a.shape == b.shape and (a == b).all())}; == shard bytes: "
        f"{bool(a.shape == on_disk.shape and (a == on_disk).all())}",
    )


def check_shard_ids(files: Sequence[Path]) -> Check:
    """No id in any M1 shard reaches the text region.

    Args:
        files: The shard token files.

    Returns:
        The check.
    """
    highest = 0
    tokens = 0
    for path in files:
        ids = np.memmap(path, dtype=np.uint16, mode="r")
        tokens += int(ids.size)
        if ids.size:
            highest = max(highest, int(ids.max()))
    return Check(
        "no M1 shard id reaches the text region",
        bool(files) and highest < TELEMETRY_PREFIX_SIZE,
        f"{len(files)} shard files, {tokens:,} tokens; highest id {highest}",
    )


def check_text_region_full(layout: VocabLayout, text_tokenizer: TextBPETokenizer) -> Check:
    """The text block holds exactly its capacity, contiguously, and nothing after it.

    Args:
        layout: The joint layout.
        text_tokenizer: The fitted text tokenizer.

    Returns:
        The check.
    """
    ids = [layout.text_id(i) for i in range(layout.n_text)]
    contiguous = ids == list(range(TEXT_OFFSET, TEXT_OFFSET + layout.n_text))
    try:
        layout.text_id(layout.n_text)
        overflow_refused = False
    except IndexError:
        overflow_refused = True
    passed = (
        text_tokenizer.vocab_size == TEXT_CAPACITY == layout.n_text
        and layout.total_size == TEXT_OFFSET + TEXT_CAPACITY
        and contiguous
        and overflow_refused
    )
    return Check(
        "text region exactly full at 32,768, no gap or overflow",
        passed,
        f"tokenizer {text_tokenizer.vocab_size:,} ids, capacity {TEXT_CAPACITY:,}; joint size "
        f"{layout.total_size:,} (last id {layout.total_size - 1:,}); contiguous {contiguous}; "
        f"id after the last refused {overflow_refused}",
    )


def check_round_trip(
    m1: JointVocab,
    joint: JointVocab,
    text_tokenizer: TextBPETokenizer,
    frame: pd.DataFrame,
    texts: Sequence[str],
) -> Check:
    """A telemetry+text fixture through the joint vocabulary, split and decoded back.

    Args:
        m1: The telemetry-only vocabulary.
        joint: The joint vocabulary, both tokenizers bound.
        text_tokenizer: The text tokenizer, alone.
        frame: Telemetry rows.
        texts: Text documents.

    Returns:
        The check.
    """
    telemetry = joint.encode_steps(frame).ravel().astype(np.int64)
    documents = [joint.encode_text(text) for text in texts]
    stream = np.concatenate([telemetry, *[np.asarray(d, dtype=np.int64) for d in documents]])

    head = stream[: telemetry.size]
    telemetry_same = bool((head == m1.encode_steps(frame).ravel()).all())
    telemetry_region = bool((head < TELEMETRY_PREFIX_SIZE).all())
    position = telemetry.size
    text_same = True
    decoded_same = True
    for text, document in zip(texts, documents, strict=True):
        part = stream[position : position + len(document)]
        position += len(document)
        inner = [int(i) - TEXT_OFFSET for i in part[1:-1]]
        text_same &= inner == text_tokenizer.encode(text)
        text_same &= int(part[0]) == joint.special("<txt>") and int(part[-1]) == joint.special(
            "</txt>"
        )
        decoded_same &= text_tokenizer.decode(inner) == text
    passed = telemetry_same and telemetry_region and text_same and decoded_same
    return Check(
        "round trip: joint encode equals the single-modality tokenizers",
        passed,
        f"{len(frame)} telemetry steps ({telemetry.size} ids) and {len(texts)} documents "
        f"({stream.size - telemetry.size} ids); telemetry == M1 encode {telemetry_same}; "
        f"text == BPE encode {text_same}; text decodes to input {decoded_same}",
    )


def text_checkpoint_rows(checkpoints: Sequence[Path]) -> dict[str, int]:
    """Token-embedding rows of each text-only checkpoint, observed and not asserted.

    Args:
        checkpoints: The M2 text checkpoints.

    Returns:
        Rows per checkpoint file name.
    """
    rows: dict[str, int] = {}
    for path in checkpoints:
        rows[path.name] = embedding_rows(path)
    return rows


def render_report(
    checks: Sequence[Check],
    sources: dict[str, str],
    paths: ProjectPaths,
    text_rows: dict[str, int] | None = None,
) -> str:
    """Render the verification report.

    Args:
        checks: Every check, in order.
        sources: What was read, by role.
        paths: Resolved project paths.
        text_rows: Embedding rows of the text-only checkpoints, for the observation.

    Returns:
        The Markdown report.
    """
    failed = [c for c in checks if not c.passed]
    verdict = (
        "**Every assertion holds. ADR-0003 v2 stands: the M1 telemetry vocabulary and the M2 "
        "text tokenizer concatenate without renumbering anything.**"
        if not failed
        else f"**{len(failed)} assertion(s) FAILED. This supersedes ADR-0003. STOP: nothing "
        "is patched, and M3 does not proceed on this vocabulary.**"
    )
    return "".join(
        [
            "# Joint vocabulary: verified, not assumed\n\n",
            kv_table(
                {
                    **sources,
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline check joint-vocab",
                }
            ),
            section(
                "Assertions",
                table(
                    ["assertion", "result", "measured"],
                    [[c.name, "PASS" if c.passed else "FAIL", c.detail] for c in checks],
                )
                + f"\n{verdict}\n",
            ),
            section(
                "Observed, not asserted: the text checkpoints carry one row outside the region",
                (
                    "The M2 text-only checkpoints embed "
                    + ", ".join(f"`{name}` {n:,} rows" for name, n in sorted(text_rows.items()))
                    + f". The text shards append a local `<sep>` at id {TEXT_CAPACITY:,}, one past "
                    "the tokenizer, so a text checkpoint has one row more than the text region "
                    "holds. That row has no joint id in `[1184, 33952)`. The joint `<sep>` is the "
                    "structural token at id 8. A joint model initialised from a text checkpoint "
                    f"must map text rows `0..{TEXT_CAPACITY - 1:,}` to joint ids "
                    f"`{TEXT_OFFSET:,}..{TEXT_OFFSET + TEXT_CAPACITY - 1:,}` and row "
                    f"`{TEXT_CAPACITY:,}` to id 8, not append it. This does not bear on ADR-0003: "
                    "the region itself is neither over nor under full.\n"
                )
                if text_rows
                else "No text checkpoint was read.\n",
            ),
        ]
    )


def verify_joint_vocabulary(
    paths: ProjectPaths,
    bin_tokenizer_file: Path,
    text_tokenizer_file: Path,
    shard_dir: Path,
    checkpoint_dir: Path,
    masked: dict[str, list[str]],
) -> tuple[Path, list[Check]]:
    """Run every check against the artefacts on disk and write the report.

    Args:
        paths: Resolved project paths.
        bin_tokenizer_file: The M1 quantile bin tokenizer the shards were written with.
        text_tokenizer_file: The M2 text tokenizer.
        shard_dir: The M1 telemetry shards.
        checkpoint_dir: The M1 ladder checkpoints.
        masked: Per source, the channels the shards emit as ``<nan>``.

    Returns:
        The report, and the checks.
    """
    from faultline.data.telemetry.adapters import ADAPTERS
    from faultline.data.telemetry.pipeline import parquet_files, stage_source_dir
    from faultline.training.windows import ShardSet

    bins = QuantileBinTokenizer.load(bin_tokenizer_file)
    text = TextBPETokenizer.load(text_tokenizer_file)
    m1 = JointVocab(m1_layout(bins), bin_tokenizer=bins)
    joint = JointVocab(joint_layout(bins, text.vocab_size), text, bins)
    shards = ShardSet.load(shard_dir)
    per_step = shards.tokens_per_step

    checks = [
        check_no_collision(joint.layout),
        check_prefix_decodes_identically(m1.layout, joint.layout),
        check_checkpoint_rows(sorted(checkpoint_dir.glob("*.pt"))),
    ]
    first_frame: pd.DataFrame | None = None
    for source in ADAPTERS:
        seen: set[str] = set()
        for path in parquet_files(stage_source_dir(paths, "final", source)):
            frame = pd.read_parquet(path)
            if frame.empty or "split" not in frame.columns:
                continue
            frame = frame.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)
            for split in pd.unique(frame["split"]):
                key = f"{source}__{split}"
                if split in seen or key not in shards.files():
                    continue
                seen.add(str(split))
                rows = frame[frame["split"] == split].reset_index(drop=True)
                on_disk = np.fromfile(
                    shard_dir / str(shards.files()[key]["tokens"]),
                    dtype=np.uint16,
                    count=len(rows) * per_step,
                ).reshape(-1, per_step)
                result = check_shard_prefix(m1, joint, rows, masked.get(source, []), on_disk)
                checks.append(
                    Check(
                        f"`{key}`: first turbine-year ({path.stem}) bit-identical, M1 vs joint "
                        "vs shard",
                        result.passed,
                        result.detail,
                    )
                )
                if first_frame is None:
                    first_frame = rows.head(6)
    checks.append(check_shard_ids(sorted(shard_dir.glob("*.bin"))))
    checks.append(check_text_region_full(joint.layout, text))
    fixture = [
        " wind < start wind",
        "The licensee reported a trip of the main feedwater pump at 03:12.",
    ]
    if first_frame is not None:
        checks.append(check_round_trip(m1, joint, text, first_frame, fixture))

    sources = {
        "telemetry tokenizer (M1)": bin_tokenizer_file.name,
        "text tokenizer (M2)": text_tokenizer_file.name,
        "M1 shards": shard_dir.name,
        "M1 checkpoints": checkpoint_dir.name,
        "round-trip fixture": "the first 6 steps of the first turbine-year above, a normalized "
        "status string and a narrative sentence",
    }
    report = paths.data_reports_dir / f"joint_vocab_check_v1_{datetime.now(tz=UTC):%Y%m%d}.md"
    text_rows = text_checkpoint_rows(sorted((paths.checkpoints_dir / "text").glob("*.pt")))
    report.write_text(
        render_report(checks, sources, paths, text_rows), encoding="utf-8", newline="\n"
    )
    logger.info("wrote %s", report)
    return report, checks
