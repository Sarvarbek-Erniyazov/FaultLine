"""Text-only checkpoints reach the joint vocabulary through one migration, and no other way (E2)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest
import torch

from faultline.evaluation.status_nll import sequence_nll
from faultline.model.checkpoints import (
    TEXT_CHECKPOINT_ROWS,
    TextCheckpointRefusedError,
    embedding_rows,
    locate_separator_row,
    migrate_text_checkpoint,
    migrate_text_state,
    read_checkpoint,
    text_support,
)
from faultline.model.transformer import ModelSpec, TelemetryDecoder
from faultline.tokenizers.layout import TEXT_CAPACITY, TEXT_OFFSET, VocabLayout

REPO = Path(__file__).resolve().parents[2]
LAYOUT = VocabLayout.from_sizes(TEXT_CAPACITY, 12, 256)
SEP = TEXT_CAPACITY


def _text_state(width: int = 4) -> dict[str, torch.Tensor]:
    generator = torch.Generator().manual_seed(7)
    return {
        "tokens.weight": torch.randn((TEXT_CHECKPOINT_ROWS, width), generator=generator),
        "positions.weight": torch.randn((16, width), generator=generator),
    }


def _shards(
    root: Path, streams: dict[str, list[int]], sep: int = SEP, vocab: int = SEP + 1
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    files = {}
    for key, ids in streams.items():
        np.asarray(ids, dtype=np.uint16).tofile(root / f"{key}.bin")
        files[key] = {"tokens": f"{key}.bin"}
    manifest = {
        "dtype": "uint16",
        "specials": {"<sep>": sep},
        "vocabulary_size": vocab,
        "files": files,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


GOOD_STREAMS = {"a__train": [5, 6, SEP, 7, 32767, SEP], "b__train": [1, SEP], "a__val": [3, SEP]}


# ------------------------------------------------------------------ the migration


def test_every_bpe_row_is_copied_unchanged_and_the_separator_goes_to_joint_8() -> None:
    state = _text_state()
    migrated = migrate_text_state(state, LAYOUT, separator_row=SEP)
    table, joint = state["tokens.weight"], migrated["tokens.weight"]
    assert joint.shape == (LAYOUT.total_size, 4) == (33_952, 4)
    # row for row, every non-separator row: local i sits at TEXT_OFFSET + i, bit for bit
    assert torch.equal(joint[TEXT_OFFSET : TEXT_OFFSET + TEXT_CAPACITY], table[:TEXT_CAPACITY])
    for i in (0, 1, 255, 256, 12_345, TEXT_CAPACITY - 1):
        assert torch.equal(joint[TEXT_OFFSET + i], table[i])
    assert LAYOUT.special_id("<sep>") == 8
    assert torch.equal(joint[8], table[SEP])
    # the separator is not also left inside the text block, and the last BPE row is not it
    assert not torch.equal(joint[TEXT_OFFSET + TEXT_CAPACITY - 1], table[SEP])
    assert migrated["positions.weight"] is state["positions.weight"]


def test_the_untrained_prefix_rows_are_seeded_and_small() -> None:
    first = migrate_text_state(_text_state(), LAYOUT, SEP, seed=3)["tokens.weight"]
    again = migrate_text_state(_text_state(), LAYOUT, SEP, seed=3)["tokens.weight"]
    assert torch.equal(first, again)
    prefix = torch.cat([first[:8], first[9:TEXT_OFFSET]])
    assert prefix.std().item() == pytest.approx(0.02, rel=0.2)


def test_a_state_that_is_not_32769_rows_is_refused() -> None:
    state = {"tokens.weight": torch.zeros(TEXT_CAPACITY, 4)}
    with pytest.raises(ValueError, match="32,769 rows"):
        migrate_text_state(state, LAYOUT, SEP)


def test_a_separator_row_other_than_the_last_is_refused() -> None:
    with pytest.raises(ValueError, match="separator row must be 32,768"):
        migrate_text_state(_text_state(), LAYOUT, separator_row=0)


def test_the_text_support_is_the_text_block_then_joint_sep() -> None:
    support = text_support(LAYOUT)
    assert support.shape == (TEXT_CHECKPOINT_ROWS,)
    assert support[0].item() == TEXT_OFFSET
    assert support[TEXT_CAPACITY - 1].item() == TEXT_OFFSET + TEXT_CAPACITY - 1
    assert support[TEXT_CAPACITY].item() == 8


def test_a_migrated_model_over_its_text_support_scores_exactly_as_the_text_model() -> None:
    torch.manual_seed(0)
    native = TelemetryDecoder(
        ModelSpec(
            name="T", d_model=8, n_layer=1, n_head=2, context=16, vocab_size=TEXT_CHECKPOINT_ROWS
        ),
        fused=False,
    ).eval()
    migrated = TelemetryDecoder(
        ModelSpec(
            name="T", d_model=8, n_layer=1, n_head=2, context=16, vocab_size=LAYOUT.total_size
        ),
        fused=False,
    ).eval()
    migrated.load_state_dict(migrate_text_state(native.state_dict(), LAYOUT, SEP))
    sequences = [[5, 32767, SEP, 100], [0, 1], [SEP, 31000, 2]]
    cpu = torch.device("cpu")
    before = sequence_nll(native, [SEP], sequences, cpu)
    after = sequence_nll(migrated, [SEP], sequences, cpu, to_model=text_support(LAYOUT))
    for a, b in zip(before, after, strict=True):
        np.testing.assert_allclose(a, b, rtol=1e-5, atol=1e-5)
    # over the whole joint vocabulary the untrained rows take mass: not the same model
    unrestricted = sequence_nll(migrated, [8], [[TEXT_OFFSET + 5, 8]], cpu)
    assert not np.allclose(unrestricted[0], before[0][:2])


# ------------------------------------------------------------------ locating the row


def test_the_separator_row_is_located_from_every_source(tmp_path: Path) -> None:
    location = locate_separator_row(
        _shards(tmp_path, GOOD_STREAMS), TEXT_CAPACITY, TEXT_CHECKPOINT_ROWS
    )
    assert location.row == SEP
    assert location.stream_maximum == SEP
    assert location.streams_ending_in_sep == (2, 2)
    assert location.separators == 3


@pytest.mark.parametrize(
    ("streams", "sep", "vocab", "tokenizer", "rows", "message"),
    [
        (GOOD_STREAMS, 0, SEP + 1, TEXT_CAPACITY, TEXT_CHECKPOINT_ROWS, "manifest <sep>"),
        (GOOD_STREAMS, SEP, SEP + 1, TEXT_CAPACITY, TEXT_CAPACITY, "checkpoint's rows"),
        (GOOD_STREAMS, SEP, SEP + 1, TEXT_CAPACITY - 1, TEXT_CHECKPOINT_ROWS, "tokenizer size"),
        ({"a__train": [5, SEP, 7]}, SEP, SEP + 1, TEXT_CAPACITY, TEXT_CHECKPOINT_ROWS, "ending in"),
        (
            {"a__train": [5, SEP, SEP]},
            SEP,
            SEP + 1,
            TEXT_CAPACITY,
            TEXT_CHECKPOINT_ROWS,
            "adjacent",
        ),
        ({"a__train": [5, 6]}, SEP, SEP + 1, TEXT_CAPACITY, TEXT_CHECKPOINT_ROWS, "largest"),
    ],
)
def test_any_source_that_disagrees_refuses_the_location(
    tmp_path: Path,
    streams: dict[str, list[int]],
    sep: int,
    vocab: int,
    tokenizer: int,
    rows: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        locate_separator_row(_shards(tmp_path, streams, sep, vocab), tokenizer, rows)


# ------------------------------------------------------------------ the refusal


def test_a_32769_row_checkpoint_is_refused_except_through_the_migration(tmp_path: Path) -> None:
    path = tmp_path / "S2_text_seed1.pt"
    torch.save({"spec": {"vocab_size": TEXT_CHECKPOINT_ROWS}, "state": _text_state()}, path)
    with pytest.raises(TextCheckpointRefusedError, match="migrate_text_checkpoint"):
        read_checkpoint(path)
    assert embedding_rows(path) == TEXT_CHECKPOINT_ROWS
    payload, location = migrate_text_checkpoint(
        path, LAYOUT, _shards(tmp_path / "shards", GOOD_STREAMS), TEXT_CAPACITY
    )
    assert location.row == SEP
    assert payload["spec"]["vocab_size"] == LAYOUT.total_size
    assert payload["state"]["tokens.weight"].shape[0] == LAYOUT.total_size


def test_a_risk_model_holding_32769_rows_is_refused_too(tmp_path: Path) -> None:
    path = tmp_path / "risk.pt"
    torch.save({"state": {"backbone.tokens.weight": torch.zeros(TEXT_CHECKPOINT_ROWS, 2)}}, path)
    with pytest.raises(TextCheckpointRefusedError):
        read_checkpoint(path)


def test_a_joint_or_telemetry_checkpoint_reads_normally(tmp_path: Path) -> None:
    for rows in (1184, LAYOUT.total_size):
        path = tmp_path / f"{rows}.pt"
        torch.save({"state": {"tokens.weight": torch.zeros(rows, 2)}}, path)
        assert read_checkpoint(path)["state"]["tokens.weight"].shape[0] == rows


def test_no_module_but_the_checkpoints_module_calls_torch_load() -> None:
    offenders = [
        path.relative_to(REPO).as_posix()
        for path in (REPO / "src").rglob("*.py")
        if re.search(r"torch\.load\(", path.read_text(encoding="utf-8"))
        and path.name != "checkpoints.py"
    ]
    assert offenders == []
