"""The joint arm's windows (ADR-0025 §2, §3) and the mixture sampler, on synthetic shards."""

from __future__ import annotations

import numpy as np
import pytest
import torch

from faultline.data.joint.mixture_shards import interleave
from faultline.evaluation.bag_of_tokens import BagOfTokens
from faultline.evaluation.variance_probe import TelWindows
from faultline.model.risk import RiskModel, RiskSpec
from faultline.model.transformer import ModelSpec
from faultline.training.joint_windows import (
    PAD_ID,
    SEP_ID,
    TXT_CLOSE_ID,
    TXT_OPEN_ID,
    JointWindowSampler,
    JointWindowSet,
    MixtureSampler,
    StreamWindows,
    drop_messages,
    gather_padded,
    last_real_index,
    message_spans,
    mixture_schedule,
    step_message_counts,
    step_offsets,
    tail_anchored,
    tile_starts,
)
from faultline.training.windows import WindowSet

WIDTH = 13  # tokens per step
STEPS = 144  # an M1 window
CONTEXT = 2048


def _steps(n: int) -> np.ndarray:
    """``n`` telemetry steps: ``<sep>`` then 12 bin ids, distinct per step."""
    block = np.zeros((n, WIDTH), dtype=np.int64)
    block[:, 0] = SEP_ID
    block[:, 1:] = 96 + (np.arange(n)[:, None] * 12 + np.arange(12)) % 1024
    return block


def _message(tokens: int, first: int = 2000) -> np.ndarray:
    """One message of ``tokens`` text tokens, wrappers added."""
    return np.concatenate([[TXT_OPEN_ID], first + np.arange(tokens) % 3000, [TXT_CLOSE_ID]])


def _stream(n: int, messages: dict[int, list[int]]) -> tuple[np.ndarray, np.ndarray]:
    """A ``tel+status`` stream of ``n`` steps, with messages of the given lengths on some steps."""
    at = sorted((step, length) for step, lengths in messages.items() for length in lengths)
    steps = np.array([s for s, _ in at], dtype=np.int64)
    tokens, offsets = interleave(_steps(n), steps, [_message(length) for _, length in at])
    return tokens, offsets


def test_step_offsets_and_message_spans_read_the_builders_layout() -> None:
    tokens, offsets = _stream(10, {2: [5, 3], 7: [4]})
    assert np.array_equal(step_offsets(tokens), offsets)
    opens, closes = message_spans(tokens)
    assert opens.size == 3 and np.all(tokens[opens] == TXT_OPEN_ID)
    assert np.all(tokens[closes - 1] == TXT_CLOSE_ID)
    assert step_message_counts(tokens, offsets).tolist() == [0, 0, 2, 0, 0, 0, 0, 1, 0, 0]


def test_a_window_without_messages_is_the_m1_window() -> None:
    tokens, offsets = _stream(200, {})
    span = tail_anchored(offsets, tokens.size, np.array([150, 199]), STEPS, CONTEXT, WIDTH)
    assert span.steps_retained.tolist() == [144, 144]
    assert span.length.tolist() == [144 * WIDTH] * 2
    assert span.first.tolist() == [offsets[150 - 143], offsets[199 - 143]]
    assert not span.head_cut.any() and span.status_tokens.tolist() == [0, 0]


def test_many_messages_truncate_at_a_sep_and_keep_the_right_step_count() -> None:
    # 300 steps; four 400-token messages (402 with wrappers) inside the window ending at t = 299.
    tokens, offsets = _stream(300, {200: [400], 250: [400], 280: [400], 299: [400]})
    t = 299
    span = tail_anchored(offsets, tokens.size, np.array([t]), STEPS, CONTEXT, WIDTH)
    first, length, kept = int(span.first[0]), int(span.length[0]), int(span.steps_retained[0])
    assert tokens[first] == SEP_ID
    assert length <= CONTEXT
    # By hand: from the end of step t, step by step back until the next step would not fit.
    stop = tokens.size
    expected = next(s for s in range(t - STEPS + 1, t + 1) if stop - offsets[s] <= CONTEXT)
    assert kept == t - expected + 1
    assert first == offsets[expected]
    assert kept < STEPS  # truncated
    kept_messages = sum(step >= expected for step in (200, 250, 280, 299))
    assert expected == 236 and kept_messages == 3
    assert int(span.status_tokens[0]) == kept_messages * 402
    assert not span.head_cut[0]


def test_a_window_never_reaches_before_t_minus_143() -> None:
    # Short steps and no messages: 157 steps would fit in 2,048 tokens, and 144 are kept.
    tokens, offsets = _stream(400, {100: [3]})
    ends = np.arange(STEPS - 1, 400)
    span = tail_anchored(offsets, tokens.size, ends, STEPS, CONTEXT, WIDTH)
    assert span.steps_retained.max() == STEPS
    assert np.all(span.first >= offsets[ends - STEPS + 1])
    with pytest.raises(ValueError, match="outside"):
        tail_anchored(offsets, tokens.size, np.array([STEPS - 2]), STEPS, CONTEXT, WIDTH)


def test_a_step_longer_than_the_context_is_head_cut_and_counted() -> None:
    tokens, offsets = _stream(200, {170: [3000]})
    span = tail_anchored(offsets, tokens.size, np.array([169, 170, 171]), STEPS, CONTEXT, WIDTH)
    assert span.head_cut.tolist() == [False, True, False]
    assert int(span.length[1]) == CONTEXT
    assert int(span.steps_retained[1]) == 0
    assert int(span.first[1]) == offsets[171] - CONTEXT
    assert int(span.status_tokens[1]) == CONTEXT  # step 170's telemetry is cut off entirely
    # t = 171: step 170's message cannot fit behind it, so only step 171 is kept.
    assert int(span.steps_retained[2]) == 1


def _window_set(tokens: np.ndarray, ends: np.ndarray, n: int) -> JointWindowSet:
    m1 = WindowSet(
        key="site__test",
        tokens=np.zeros(0, np.uint16),  # type: ignore[arg-type]
        starts=ends - STEPS + 1,
        ends=ends,
        labels=(ends % 2).astype(np.float32),
        years=np.full(ends.size, 2022),
    )
    return JointWindowSet.frame(m1, tokens, STEPS, CONTEXT, WIDTH, n)


def test_r2_removes_the_flagged_messages_and_the_window_is_reframed() -> None:
    tokens, offsets = _stream(300, {200: [900], 250: [900], 299: [10]})
    dropped = np.array([False, True, False])  # stream order: steps 200, 250, 299
    filtered = drop_messages(tokens, dropped)
    assert filtered.size == tokens.size - 902
    assert message_spans(filtered)[0].size == 2
    assert np.array_equal(step_offsets(filtered)[:251], offsets[:251])
    r0 = _window_set(tokens, np.array([299]), 300)
    r2 = _window_set(filtered, np.array([299]), 300)
    # R0: 902 + 12 message tokens leave room for 87 steps (1,131 tokens); step 200 is out.
    assert (int(r0.steps_retained[0]), int(r0.status_tokens[0])) == (87, 914)
    # R2: step 250's message is gone; step 200's 902 still cannot fit, so steps 201..299 stay.
    assert (int(r2.steps_retained[0]), int(r2.status_tokens[0])) == (99, 12)
    with pytest.raises(ValueError, match="flags"):
        drop_messages(tokens, np.array([True]))


def test_the_joint_set_keeps_the_m1_rows_and_refuses_a_stream_of_other_steps() -> None:
    tokens, _ = _stream(300, {250: [100]})
    ends = np.array([150, 299])
    window = _window_set(tokens, ends, 300)
    assert window.ends.tolist() == [150, 299] and window.labels.tolist() == [0.0, 1.0]
    with pytest.raises(ValueError, match="steps"):
        _window_set(tokens, ends, 301)


def test_padded_batches_carry_the_last_real_index() -> None:
    tokens, _ = _stream(400, {390: [1500]})
    window = _window_set(tokens, np.array([200, 399]), 400)
    sampler = JointWindowSampler(
        [window], batch_size=2, tokens_per_step=WIDTH, context_steps=STEPS, labelled=True
    )
    batch, labels, _ = next(sampler.epoch())
    assert batch.shape == (2, CONTEXT)
    lengths = window.length.tolist()
    assert last_real_index(batch).tolist() == [n - 1 for n in lengths]
    assert int(batch[0, lengths[0]]) == PAD_ID and int(batch[0, 0]) == SEP_ID
    first = int(window.first[1])
    assert np.array_equal(batch[1, : lengths[1]].numpy(), tokens[first : first + lengths[1]])
    assert labels.tolist() == [0.0, 1.0]
    again, _, _ = gather_padded([window], np.array([[0, 1]]), False)
    assert torch.equal(again[0], batch[1])


def test_a_padded_windows_pooled_state_equals_the_unpadded_windows() -> None:
    torch.manual_seed(0)
    spec = ModelSpec(name="T", d_model=32, n_layer=2, n_head=4, context=64, vocab_size=5000)
    padded = RiskModel(spec, RiskSpec(), frozen=True, pad_id=PAD_ID).eval()
    plain = RiskModel(spec, RiskSpec(), frozen=True).eval()
    plain.load_state_dict(padded.state_dict())
    short = torch.tensor([SEP_ID, 100, 101, 102, TXT_OPEN_ID, 2000, TXT_CLOSE_ID])
    long = torch.randint(10, 4000, (64,))
    batch = torch.full((2, 64), PAD_ID)
    batch[0, : short.numel()] = short
    batch[1] = long
    with torch.no_grad():
        both = padded(batch)
        alone = plain(short[None])
        full = plain(long[None])
    assert torch.allclose(both[0], alone[0], atol=1e-5)
    assert torch.allclose(both[1], full[0], atol=1e-5)
    # Without a pad id the model reads the last position, as every probe before ADR-0025 did.
    with torch.no_grad():
        assert torch.allclose(plain(batch)[1], full[0], atol=1e-5)


def test_bag_of_tokens_status_only_counts_the_status_region_and_an_empty_one_is_zero() -> None:
    vocab = 3200
    bag = BagOfTokens(vocab, None, "status_only", PAD_ID)
    empty = torch.full((1, 40), PAD_ID)
    empty[0, :26] = torch.from_numpy(_steps(2).ravel())
    assert float(bag.features(empty).abs().sum()) == 0.0
    tokens, _ = _stream(3, {1: [4]})
    window = torch.full((1, 64), PAD_ID)
    window[0, : tokens.size] = torch.from_numpy(tokens.astype(np.int64))
    features = bag.features(window)[0]
    assert float(features[TXT_OPEN_ID]) == pytest.approx(1 / 3)  # one message over 3 <sep>
    assert float(features[SEP_ID]) == 0.0 and float(features[96:1184].sum()) == 0.0
    assert float(features[1184:].sum()) == pytest.approx(4 / 3)
    every = BagOfTokens(vocab, None, "all", PAD_ID).features(window)[0]
    assert float(every[PAD_ID]) == 0.0 and float(every[SEP_ID]) == pytest.approx(1.0)


def test_bag_of_tokens_v0_arithmetic_is_unchanged() -> None:
    tokens = torch.from_numpy(_steps(144).ravel()[None].astype(np.int64))
    bag = BagOfTokens(1184, 144)
    counts = torch.zeros(1, 1184)
    counts.scatter_add_(1, tokens, torch.ones_like(tokens, dtype=torch.float32))
    assert torch.equal(bag.features(tokens), counts / 144)
    assert set(bag.state_dict()) == {"linear.weight", "linear.bias"}


# =====================================================================================
# the mixture sampler
# =====================================================================================


def _pool(name: str, keys: int, windows: int, context: int, rng: int) -> StreamWindows:
    streams = {
        f"{name}{k}": np.random.default_rng([rng, k]).integers(10, 30000, windows * context + 7)
        for k in range(keys)
    }
    index = np.concatenate(
        [
            np.stack([np.full(windows, k), tile_starts(windows * context + 7, context)], axis=1)
            for k in range(keys)
        ]
    )
    return StreamWindows(
        streams=streams,  # type: ignore[arg-type]
        keys=list(streams),
        index=index.astype(np.int64),
        context=context,
        train_tokens=keys * (windows * context + 7),
    )


def test_the_schedule_holds_every_stream_within_one_window_of_its_share() -> None:
    shares = {"tel": 0.30, "txt": 0.20, "tel+status": 0.50}
    schedule = mixture_schedule(shares, 24416)  # type: ignore[arg-type]
    for n in (1, 7, 100, 1001, 24416):
        for position, share in enumerate(shares.values()):
            assert abs(int((schedule[:n] == position).sum()) - share * n) <= 1.0


def test_the_mixture_draws_its_ratio_and_repeats_no_window_before_its_budget() -> None:
    context = 16
    pools = {
        "tel": _pool("tel", 2, 400, context, 1),
        "txt": _pool("txt", 3, 100, context, 2),
        "tel+status": _pool("ts", 2, 700, context, 3),
    }
    shares = {"tel": 0.30, "txt": 0.20, "tel+status": 0.50}
    sampler = MixtureSampler(pools=pools, shares=shares, seed=7, batch=4, keep_rows=True)  # type: ignore[arg-type]
    windows = 1200
    sampler.refuse_repeats(windows)
    batches = sampler.forever()
    drawn = [next(batches) for _ in range(windows // 4)]
    assert all(t.shape == (4, context) for t, _, _ in drawn)
    for stream, share in shares.items():
        assert abs(sampler.drawn[stream] - share * windows) <= 1  # type: ignore[index]
        rows = sampler.drawn_rows[stream]  # type: ignore[index]
        assert len(set(rows)) == len(rows)  # no repeat within the budget
    assert sampler.plan(windows) == sampler.drawn
    # txt: 240 of 300 tiles, 0.8 of one pass.
    assert sampler.drawn["txt"] / len(pools["txt"]) == pytest.approx(0.8)
    with pytest.raises(ValueError, match="repeat"):
        sampler.refuse_repeats(2000)
    # A window's tokens are its stream's slice.
    tokens, _, which = drawn[0]
    assert which.tolist()[0] == 2  # the first window is tel+status, the largest share


def test_a_tel_only_mixture_draws_pretrain_tels_windows_in_its_order() -> None:
    context, batch = 16, 4
    pool = _pool("tel", 2, 250, context, 5)  # 500 windows: a pass is 125 whole batches
    tel = TelWindows(
        streams=pool.streams,  # type: ignore[arg-type]
        keys=pool.keys,
        index=pool.index,
        context=context,
    )
    mixture = MixtureSampler(pools={"tel": pool}, shares={"tel": 1.0}, seed=11, batch=batch)
    ours, theirs = mixture.forever(), tel.forever(11, batch)
    for _ in range(300):  # 2.4 passes
        assert torch.equal(next(ours)[0], next(theirs)[0])


def test_a_tel_only_mixture_differs_only_after_a_pass_that_ends_mid_batch() -> None:
    context, batch = 16, 4
    pool = _pool("tel", 1, 499, context, 6)  # 499 windows: pretrain_tel skips 3 at a pass's end
    tel = TelWindows(streams=pool.streams, keys=pool.keys, index=pool.index, context=context)  # type: ignore[arg-type]
    mixture = MixtureSampler(pools={"tel": pool}, shares={"tel": 1.0}, seed=3, batch=batch)
    ours, theirs = mixture.forever(), tel.forever(3, batch)
    same = [torch.equal(next(ours)[0], next(theirs)[0]) for _ in range(125)]
    assert all(same[:124]) and not same[124]
