"""Windows over the shards: the two strides, the labels, and the batch order.

Built on a synthetic shard rather than the real one, so the suite stays offline and fast.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from faultline.training.windows import ShardSet, WindowSampler, load_windows, source_of

TOKENS_PER_STEP = 13
CONTEXT_STEPS = 4
WIDTH = TOKENS_PER_STEP * CONTEXT_STEPS


def make_shards(root: Path, steps: int = 40, sources: tuple[str, ...] = ("alpha", "beta")) -> Path:
    """Write a synthetic shard directory: token streams, window indexes and a manifest."""
    root.mkdir(parents=True, exist_ok=True)
    files = {}
    for offset, source in enumerate(sources):
        key = f"{source}__train"
        stream = np.arange(steps * TOKENS_PER_STEP, dtype=np.uint16) + offset * 1000
        (root / f"{key}.bin").write_bytes(stream.tobytes())
        ends = np.arange(CONTEXT_STEPS - 1, steps)
        frame = pd.DataFrame(
            {
                "turbine_id": ["t1"] * ends.size,
                "year": np.full(ends.size, 2020 + offset, dtype=np.int16),
                "start_step": ends - CONTEXT_STEPS + 1,
                "end_step": ends,
                # every third window is positive, and every fifth is not known
                "narrow_within_24h": (np.arange(ends.size) % 3 == 0),
                "narrow_within_24h_known": (np.arange(ends.size) % 5 != 0),
            }
        )
        frame.to_parquet(root / f"{key}.windows.parquet", index=False)
        files[key] = {
            "tokens": f"{key}.bin",
            "steps": steps,
            "windows": f"{key}.windows.parquet",
        }
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "tokens_per_step": TOKENS_PER_STEP,
                "context_steps": CONTEXT_STEPS,
                "vocabulary_size": 1184,
                "specials": {"<sep>": 8, "<nan>": 9},
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    return root


@pytest.fixture
def shards(tmp_path: Path) -> ShardSet:
    return ShardSet.load(make_shards(tmp_path / "shards"))


def test_the_manifest_gives_the_context_in_tokens(shards: ShardSet) -> None:
    assert shards.tokens_per_step == TOKENS_PER_STEP
    assert shards.context_steps == CONTEXT_STEPS
    assert shards.context_tokens == WIDTH
    assert shards.keys("train") == ["alpha__train", "beta__train"]
    assert shards.keys("train", ["beta"]) == ["beta__train"]
    assert source_of("beta__train") == "beta"


def test_the_stride_thins_the_windows_and_one_keeps_them_all(shards: ShardSet) -> None:
    every = load_windows(shards, "alpha__train", stride=1)
    sixth = load_windows(shards, "alpha__train", stride=6)
    assert len(every) == 40 - CONTEXT_STEPS + 1
    assert len(sixth) == -(-len(every) // 6)
    # the thinned windows are a subset of the dense ones, taken in order
    assert sixth.starts.tolist() == every.starts[::6].tolist()


def test_a_stride_below_one_is_refused(shards: ShardSet) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        load_windows(shards, "alpha__train", stride=0)


def test_an_unknown_shard_key_is_refused(shards: ShardSet) -> None:
    with pytest.raises(KeyError, match="not in the shard manifest"):
        load_windows(shards, "gamma__train", stride=1)


def test_a_label_drops_the_windows_whose_label_is_not_known(shards: ShardSet) -> None:
    # An unknown label excludes the window at that horizon; it is never a negative, which
    # is the rule the shards were built under and would be easy to lose here.
    unlabelled = load_windows(shards, "alpha__train", stride=1)
    labelled = load_windows(shards, "alpha__train", stride=1, label="narrow_within_24h")
    assert len(labelled) < len(unlabelled)
    assert len(labelled) == sum(1 for i in range(len(unlabelled)) if i % 5 != 0)
    assert set(labelled.labels.tolist()) <= {0.0, 1.0}


def test_the_cap_subsamples_without_replacement_and_is_seeded(shards: ShardSet) -> None:
    first = load_windows(shards, "alpha__train", stride=1, limit=10, seed=7)
    again = load_windows(shards, "alpha__train", stride=1, limit=10, seed=7)
    other = load_windows(shards, "alpha__train", stride=1, limit=10, seed=8)
    assert len(first) == 10
    assert first.starts.tolist() == again.starts.tolist()
    assert len(set(first.starts.tolist())) == 10
    assert first.starts.tolist() != other.starts.tolist()
    # ordered, so the windows stay in time order within the subsample
    assert first.starts.tolist() == sorted(first.starts.tolist())


def test_a_batch_holds_the_tokens_the_window_index_points_at(shards: ShardSet) -> None:
    sets = [load_windows(shards, key, stride=1) for key in shards.keys("train")]
    sampler = WindowSampler(sets, 4, TOKENS_PER_STEP, CONTEXT_STEPS, labelled=False)
    tokens, _, which = next(sampler.epoch())
    assert tokens.shape == (4, WIDTH)
    for row, (set_index, window) in zip(tokens, sampler.index[:4], strict=True):
        start = int(sets[set_index].starts[window]) * TOKENS_PER_STEP
        expected = np.asarray(sets[set_index].tokens[start : start + WIDTH])
        assert row.numpy().tolist() == expected.tolist()
    assert which.tolist() == sampler.index[:4, 0].tolist()


def test_an_unshuffled_pass_covers_every_window_exactly_once(shards: ShardSet) -> None:
    sets = [load_windows(shards, key, stride=1) for key in shards.keys("train")]
    sampler = WindowSampler(sets, 5, TOKENS_PER_STEP, CONTEXT_STEPS, labelled=False)
    seen = np.concatenate([which for _, _, which in sampler.epoch()])
    assert seen.size == sampler.windows == sum(len(s) for s in sets)
    assert seen.tolist() == sampler.index[:, 0].tolist()
    assert len(sampler) == -(-sampler.windows // 5)


def test_a_shuffled_pass_still_covers_every_window_exactly_once(shards: ShardSet) -> None:
    sets = [load_windows(shards, key, stride=1) for key in shards.keys("train")]
    sampler = WindowSampler(sets, 5, TOKENS_PER_STEP, CONTEXT_STEPS, labelled=False)
    rng = np.random.default_rng(0)
    rows = np.concatenate([which for _, _, which in sampler.epoch(rng)])
    assert sorted(rows.tolist()) == sorted(sampler.index[:, 0].tolist())


def test_a_batch_carries_the_label_of_its_window(shards: ShardSet) -> None:
    sets = [
        load_windows(shards, key, stride=1, label="narrow_within_24h")
        for key in shards.keys("train")
    ]
    sampler = WindowSampler(sets, 6, TOKENS_PER_STEP, CONTEXT_STEPS, labelled=True)
    tokens, labels, which = next(sampler.epoch())
    assert labels.shape == (6,)
    for position, (set_index, window) in enumerate(sampler.index[:6]):
        assert float(labels[position]) == float(sets[set_index].labels[window])


def test_an_empty_split_is_refused_rather_than_yielding_nothing(shards: ShardSet) -> None:
    with pytest.raises(ValueError, match="no admissible windows"):
        WindowSampler([], 4, TOKENS_PER_STEP, CONTEXT_STEPS, labelled=False)


def test_the_endless_stream_reshuffles_rather_than_repeating_one_order(shards: ShardSet) -> None:
    sets = [load_windows(shards, "alpha__train", stride=1)]
    sampler = WindowSampler(sets, 4, TOKENS_PER_STEP, CONTEXT_STEPS, labelled=False)
    stream = sampler.forever(seed=3)
    first = [next(stream)[0].numpy().copy() for _ in range(len(sampler))]
    second = [next(stream)[0].numpy().copy() for _ in range(len(sampler))]
    assert not all(np.array_equal(a, b) for a, b in zip(first, second, strict=True))


def test_a_missing_manifest_says_what_to_run(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="faultline telemetry shards"):
        ShardSet.load(tmp_path / "nowhere")
