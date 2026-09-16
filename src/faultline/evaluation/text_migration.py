"""The text checkpoints' migration to the joint vocabulary, checked on the real files (E2).

:mod:`faultline.model.checkpoints` holds the migration and its unit tests. This module runs
it on the two M2 text checkpoints and reports three things, each able to fail:

1. **Where the separator row sits**, from five independent sources (manifest, tokenizer,
   checkpoint rows, the training streams' maximum and their last ids), with the row
   asserted to be 32,768, the end of the text region.
2. **That the row mapped to joint id 8 is the one the model uses as a separator.** On
   held-out narrative streams, the probability the migrated model gives joint ``<sep>`` at the
   last token of a document is compared with the probability it gives it everywhere else. A
   row taken from the wrong place would not carry that contrast.
3. **That the migrated model scores text exactly as the text-only model did.** Every
   per-string NLL of the behavioural H3' record (E1) is recomputed through the migration
   and compared with that record.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F

from faultline.data.common.report import kv_table, section, table
from faultline.data.text.shards import shards_dir
from faultline.data.text.status_convention import CONVENTIONS
from faultline.evaluation.status_nll import PROSE_CONTEXT, load_text_decoder, sequence_nll
from faultline.logging_utils import get_logger
from faultline.model.checkpoints import (
    TEXT_CHECKPOINT_ROWS,
    SeparatorLocation,
    embedding_rows,
    locate_separator_row,
)
from faultline.paths import ProjectPaths
from faultline.runs import git_sha
from faultline.tokenizers.layout import TEXT_CAPACITY, TEXT_OFFSET, VocabLayout
from faultline.tokenizers.text_bpe import TextBPETokenizer

logger = get_logger(__name__)

#: Held-out tokens read per validation stream for the separator contrast.
SEPARATOR_TOKENS = 20_000

#: Window length for that read.
SEPARATOR_WINDOW = 2_048

#: Largest per-string NLL difference, in nats, accepted as the same score (float32 kernels).
NLL_TOLERANCE = 1e-3


@dataclass(frozen=True)
class SeparatorBehaviour:
    """Probability of joint ``<sep>`` where a document ends, against everywhere else.

    Attributes:
        boundaries: Positions scored whose next token is a separator.
        others: Other positions scored.
        mean_logp_at_boundary: Mean log-probability of joint id 8 at the boundaries.
        mean_logp_elsewhere: The same at every other position.
        median_rank_at_boundary: Median rank of id 8 among the text support at boundaries,
            1 being the most probable.
        contrast_last_bpe_row: The boundary-minus-elsewhere log-probability contrast of the
            last BPE row (joint ``TEXT_OFFSET + 32,767``), the row an off-by-one would map.
    """

    boundaries: int
    others: int
    mean_logp_at_boundary: float
    mean_logp_elsewhere: float
    median_rank_at_boundary: float
    contrast_last_bpe_row: float


@torch.no_grad()
def separator_behaviour(
    model: torch.nn.Module,
    support: torch.Tensor,
    shard_dir: Path,
    device: torch.device,
) -> SeparatorBehaviour:
    """Measure how the migrated model predicts joint ``<sep>`` on held-out narrative streams.

    Args:
        model: The migrated decoder.
        support: Its text support (local id to joint id).
        shard_dir: The text shards, for the validation streams.
        device: Where the model lives.

    Returns:
        The contrast.
    """
    manifest = json.loads((shard_dir / "manifest.json").read_text(encoding="utf-8"))
    sep_local = int(manifest["specials"]["<sep>"])
    sep_position = TEXT_CAPACITY  # the separator's position in the support, local order
    last_bpe = TEXT_CAPACITY - 1
    support = support.to(device)
    at_sep: list[np.ndarray] = []
    at_last: list[np.ndarray] = []
    ranks: list[np.ndarray] = []
    is_boundary: list[np.ndarray] = []
    for key in sorted(k for k in manifest["files"] if k.endswith("__val")):
        stream = np.fromfile(shard_dir / manifest["files"][key]["tokens"], dtype=manifest["dtype"])
        stream = stream[:SEPARATOR_TOKENS].astype(np.int64)
        for start in range(0, stream.size - 1, SEPARATOR_WINDOW):
            piece = torch.from_numpy(stream[start : start + SEPARATOR_WINDOW + 1]).to(device)
            if piece.numel() < 2:
                continue
            logits = model.logits(model(support[piece[:-1]].unsqueeze(0))).float()[0]  # type: ignore[operator]
            logp = F.log_softmax(logits[:, support], dim=-1)
            at_sep.append(logp[:, sep_position].cpu().numpy())
            at_last.append(logp[:, last_bpe].cpu().numpy())
            ranks.append(
                (logp > logp[:, sep_position : sep_position + 1]).sum(dim=-1).cpu().numpy() + 1
            )
            is_boundary.append((piece[1:] == sep_local).cpu().numpy())
    sep_lp, last_lp = np.concatenate(at_sep), np.concatenate(at_last)
    rank, boundary = np.concatenate(ranks), np.concatenate(is_boundary)
    return SeparatorBehaviour(
        boundaries=int(boundary.sum()),
        others=int((~boundary).sum()),
        mean_logp_at_boundary=float(sep_lp[boundary].mean()),
        mean_logp_elsewhere=float(sep_lp[~boundary].mean()),
        median_rank_at_boundary=float(np.median(rank[boundary])),
        contrast_last_bpe_row=float(last_lp[boundary].mean() - last_lp[~boundary].mean()),
    )


@dataclass
class MigrationCheck:
    """What the migration check measured, per checkpoint.

    Attributes:
        location: Per checkpoint, where its separator row sits and why.
        behaviour: Per checkpoint, the separator contrast.
        nll_compared: Per checkpoint, per-string NLLs compared with the E1 record.
        nll_max_difference: Per checkpoint, the largest absolute difference, nats.
        record: The E1 record compared against.
    """

    location: dict[str, SeparatorLocation]
    behaviour: dict[str, SeparatorBehaviour]
    nll_compared: dict[str, int]
    nll_max_difference: dict[str, float]
    record: str

    def passed(self) -> bool:
        """Every NLL within tolerance, and the separator more probable at boundaries."""
        return all(v <= NLL_TOLERANCE for v in self.nll_max_difference.values()) and all(
            b.mean_logp_at_boundary > b.mean_logp_elsewhere for b in self.behaviour.values()
        )


def check_migration(
    paths: ProjectPaths,
    tokenizer_file: Path,
    checkpoints: dict[str, Path],
    layout: VocabLayout,
    behavioural_record: Path,
    device: torch.device,
) -> MigrationCheck:
    """Run the three checks on the text checkpoints.

    Args:
        paths: Resolved project paths.
        tokenizer_file: The frozen text tokenizer.
        checkpoints: Per rung, its text-only checkpoint.
        layout: The joint layout.
        behavioural_record: The E1 JSON record, scored before the migration existed.
        device: Where to run.

    Returns:
        The measurements.
    """
    tokenizer = TextBPETokenizer.load(tokenizer_file)
    shard_dir = shards_dir(paths, tokenizer_file)
    record: dict[str, Any] = json.loads(behavioural_record.read_text(encoding="utf-8"))
    sep = tokenizer.vocab_size
    contexts = {"<sep>": [sep], "mid-prose": [sep, *tokenizer.encode(PROSE_CONTEXT)]}
    locations: dict[str, SeparatorLocation] = {}
    behaviours: dict[str, SeparatorBehaviour] = {}
    compared: dict[str, int] = {}
    worst: dict[str, float] = {}
    for name, path in checkpoints.items():
        locations[name] = locate_separator_row(
            shard_dir, tokenizer.vocab_size, embedding_rows(path)
        )
        model, support = load_text_decoder(path, layout, shard_dir, tokenizer.vocab_size, device)
        behaviours[name] = separator_behaviour(model, support, shard_dir, device)
        differences: list[float] = []
        for context, prefix in contexts.items():
            for convention, convert in CONVENTIONS.items():
                encoded = [tokenizer.encode(convert(s["text"])) for s in record["strings"]]
                scored = sequence_nll(model, prefix, encoded, device, to_model=support)
                for entry, nll in zip(record["strings"], scored, strict=True):
                    before = float(entry["nll"][name][context][convention])
                    differences.append(abs(float(nll.sum()) - before))
        compared[name] = len(differences)
        worst[name] = max(differences)
        logger.info(
            "%s: %d NLLs compared, largest difference %.2e", name, len(differences), worst[name]
        )
        del model
    return MigrationCheck(
        location=locations,
        behaviour=behaviours,
        nll_compared=compared,
        nll_max_difference=worst,
        record=behavioural_record.resolve().relative_to(paths.repo_root.resolve()).as_posix(),
    )


def render_migration_report(check: MigrationCheck, layout: VocabLayout, paths: ProjectPaths) -> str:
    """Render the migration check.

    Args:
        check: The measurements.
        layout: The joint layout.
        paths: Resolved project paths.

    Returns:
        The report as Markdown.
    """
    location_rows = [
        (
            name,
            f"**{loc.row:,}**",
            f"{loc.manifest_sep:,}",
            f"{loc.manifest_vocabulary:,}",
            f"{loc.tokenizer_size:,}",
            f"{loc.checkpoint_rows:,}",
            f"{loc.stream_maximum:,}",
            f"{loc.streams_ending_in_sep[0]} of {loc.streams_ending_in_sep[1]}",
            loc.adjacent_separators,
            f"{loc.separators:,}",
        )
        for name, loc in check.location.items()
    ]
    behaviour_rows = [
        (
            name,
            f"{b.boundaries:,} / {b.others:,}",
            f"{b.mean_logp_at_boundary:.3f}",
            f"{b.mean_logp_elsewhere:.3f}",
            f"{b.mean_logp_at_boundary - b.mean_logp_elsewhere:+.3f}",
            f"{b.median_rank_at_boundary:.0f}",
            f"{b.contrast_last_bpe_row:+.3f}",
        )
        for name, b in check.behaviour.items()
    ]
    nll_rows = [
        (name, f"{check.nll_compared[name]:,}", f"{check.nll_max_difference[name]:.2e}")
        for name in check.nll_compared
    ]
    verdict = "PASS" if check.passed() else "FAIL"
    return "".join(
        [
            f"# Text checkpoints onto the joint vocabulary: migration check, {verdict}\n\n",
            kv_table(
                {
                    "migration": "faultline.model.checkpoints.migrate_text_checkpoint",
                    "text checkpoint rows": f"{TEXT_CHECKPOINT_ROWS:,}",
                    "joint vocabulary": f"{layout.total_size:,} ids; text block "
                    f"{TEXT_OFFSET:,} to {TEXT_OFFSET + TEXT_CAPACITY - 1:,}; "
                    f"<sep> {layout.special_id('<sep>')}",
                    "generated (UTC)": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    "git_sha": git_sha(paths.repo_root),
                    "generated by": "faultline check text-migration",
                }
            ),
            section(
                "1. Where the extra embedding row sits, asserted from every source",
                table(
                    [
                        "checkpoint",
                        "separator row",
                        "manifest <sep>",
                        "manifest vocabulary",
                        "tokenizer ids",
                        "checkpoint rows",
                        "largest training id",
                        "training streams ending in it",
                        "adjacent separators",
                        "separators in training",
                    ],
                    location_rows,
                )
                + "\nThe separator is row **32,768, the last row**, so rows 0 to 32,767 are "
                "exactly the BPE ids. Each column is read independently, and the migration "
                "refuses to run if any of them disagrees. BPE row `i` goes to joint "
                f"`{TEXT_OFFSET:,} + i` unchanged, and row 32,768 goes to joint id 8. The other "
                "1,183 prefix rows are initialised as any embedding row is.\n",
            ),
            section(
                "2. The row mapped to id 8 is the model's separator, behaviourally",
                table(
                    [
                        "checkpoint",
                        "boundaries / other positions",
                        "mean log p(<sep>) at a document end",
                        "elsewhere",
                        "contrast",
                        "median rank at a document end",
                        "contrast of the last BPE row",
                    ],
                    behaviour_rows,
                )
                + f"\nThe first {SEPARATOR_TOKENS:,} tokens of every validation stream, scored "
                "over the text support. A row taken from the wrong index would not be more "
                "probable exactly where a document ends. The last BPE row, the row an "
                "off-by-one would have mapped, is shown for contrast.\n",
            ),
            section(
                "3. Migrated scores equal the text-only scores",
                table(
                    ["checkpoint", "per-string NLLs compared", "largest difference (nats)"],
                    nll_rows,
                )
                + f"\nCompared with `{check.record}`. Tolerance {NLL_TOLERANCE:g} nats. The "
                "migrated decoder, restricted to the text support, is the text-only model.\n",
            ),
        ]
    )


def write_migration_report(
    paths: ProjectPaths,
    tokenizer_file: Path,
    checkpoints: dict[str, Path],
    layout: VocabLayout,
    behavioural_record: Path,
    device: torch.device,
) -> tuple[Path, MigrationCheck]:
    """Run the migration check and write its report.

    Args:
        paths: Resolved project paths.
        tokenizer_file: The frozen text tokenizer.
        checkpoints: Per rung, its text-only checkpoint.
        layout: The joint layout.
        behavioural_record: The E1 JSON record.
        device: Where to run.

    Returns:
        The report and the measurements.
    """
    check = check_migration(paths, tokenizer_file, checkpoints, layout, behavioural_record, device)
    stem = f"text_checkpoint_migration_v1_{datetime.now(tz=UTC):%Y%m%d}"
    report = paths.data_reports_dir / f"{stem}.md"
    report.write_text(render_migration_report(check, layout, paths), encoding="utf-8", newline="\n")
    json_path = paths.data_reports_dir / f"{stem}.json"
    json_path.write_text(json.dumps(asdict(check), indent=2) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %s", report)
    return report, check
