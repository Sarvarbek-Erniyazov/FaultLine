"""Token shards and the window index (M1b step 12), end to end on synthetic tables."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from faultline.config import load_config
from faultline.data.common.splits import SplitsConfig
from faultline.data.common.windows import window_ends
from faultline.data.telemetry.bins import QuantileBinsConfig
from faultline.data.telemetry.harmonise import horizon_labels, to_seconds
from faultline.data.telemetry.labels import label_column
from faultline.data.telemetry.pipeline import stage_source_dir
from faultline.data.telemetry.schemas import CORE_CHANNELS
from faultline.data.telemetry.shards import build_shards, shards_dir, tokenizer_path
from faultline.paths import ProjectPaths
from faultline.tokenizers.layout import BIN_OFFSET, SPECIAL_TOKENS
from faultline.tokenizers.quantile_bins import QuantileBinTokenizer

ROWS = 400
HORIZONS = [6, 36, 144]
SEP = SPECIAL_TOKENS.index("<sep>")
NAN = SPECIAL_TOKENS.index("<nan>")


def config_path(paths: ProjectPaths) -> Path:
    return paths.repo_root / "configs" / "tokenizer" / "quantile_bins_v0.yaml"


def fit_tokenizer(paths: ProjectPaths) -> None:
    config = load_config(config_path(paths), QuantileBinsConfig)
    rng = np.random.default_rng(12)
    values = {name: rng.uniform(0, 100, 5000) for name in CORE_CHANNELS}
    tokenizer = QuantileBinTokenizer.fit_values(
        values, list(CORE_CHANNELS), config.n_bins, point_masses=True
    )
    tokenizer.save(tokenizer_path(paths, config))


def stage_kelmarsh(paths: ProjectPaths) -> pd.DataFrame:
    """One Kelmarsh turbine-year: a cleaned grid, events, a status stream, final rows."""
    source, turbine = "kelmarsh", "Kelmarsh 1"
    stamps = pd.Series(pd.date_range("2019-06-01", periods=ROWS, freq="10min", tz="UTC"))
    cleaned = stage_source_dir(paths, "cleaned", source)
    (cleaned / "labels").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"turbine_id": turbine, "timestamp_utc": stamps}).to_parquet(
        cleaned / "Kelmarsh_1__2019.parquet", index=False
    )
    # two narrow events: the first opened by "anemometer defect", the second by a converter
    starts = pd.Series([stamps[150] + pd.Timedelta(minutes=3), stamps[300]])
    pd.DataFrame(
        {"turbine_id": turbine, "start_utc": starts, "end_utc": starts + pd.Timedelta(hours=1)}
    ).to_parquet(cleaned / "labels" / "events_narrow.parquet", index=False)
    pd.DataFrame(
        {
            "turbine_id": turbine,
            "start_utc": starts,
            "message": ["anemometer defect", "frequency converter error"],
            "provider_status": "Stop",
            "cause": "technical",
        }
    ).to_parquet(cleaned / "labels" / "status_stream.parquet", index=False)

    rng = np.random.default_rng(13)
    frame = pd.DataFrame({name: rng.uniform(0, 100, ROWS) for name in CORE_CHANNELS})
    frame.loc[10, "pitch_angle_deg"] = np.nan
    frame.insert(0, "timestamp_utc", stamps)
    frame.insert(0, "turbine_id", turbine)
    frame.insert(0, "site", "Kelmarsh")
    frame.insert(0, "source", source)
    frame["split"] = "train"
    frame["segment_id"] = 0
    covered = np.sort(to_seconds(stamps))
    for label_set in ("narrow", "broad"):
        for h in HORIZONS:
            frame[label_column(label_set, h)] = horizon_labels(
                stamps, starts, h, covered
            ).to_numpy()
    final = stage_source_dir(paths, "final", source)
    frame.to_parquet(final / "Kelmarsh_1__2019.parquet", index=False)
    return frame


def stage_care(paths: ProjectPaths) -> None:
    rng = np.random.default_rng(14)
    frame = pd.DataFrame({name: rng.uniform(0, 1, 200) for name in CORE_CHANNELS})
    frame.insert(
        0, "timestamp_utc", pd.date_range("2022-01-01", periods=200, freq="10min", tz="UTC")
    )
    frame.insert(0, "turbine_id", "farm_a:0")
    frame.insert(0, "site", "farm_a")
    frame.insert(0, "source", "care")
    frame["split"] = "test"
    frame["segment_id"] = 0
    frame.to_parquet(stage_source_dir(paths, "final", "care") / "farm_a__2022.parquet", index=False)


@pytest.fixture
def built(repo_paths: ProjectPaths) -> tuple[ProjectPaths, pd.DataFrame, Path, Path]:
    fit_tokenizer(repo_paths)
    frame = stage_kelmarsh(repo_paths)
    stage_care(repo_paths)
    manifest, report = build_shards(repo_paths, config_path(repo_paths))
    return repo_paths, frame, manifest, report


def test_the_stream_is_thirteen_uint16_tokens_a_step(
    built: tuple[ProjectPaths, pd.DataFrame, Path, Path],
) -> None:
    paths, frame, manifest, _ = built
    root = manifest.parent
    tokens = np.memmap(root / "kelmarsh__train.bin", dtype=np.uint16, mode="r").reshape(-1, 13)
    assert tokens.shape == (ROWS, 13)
    assert (tokens[:, 0] == SEP).all()
    assert (tokens[:, 1:] >= BIN_OFFSET).sum() == ROWS * 12 - 1
    pitch = 1 + list(CORE_CHANNELS).index("pitch_angle_deg")
    assert tokens[10, pitch] == NAN
    written = json.loads(manifest.read_text(encoding="utf-8"))
    assert written["tokens_per_step"] == 13
    assert written["files"]["kelmarsh__train"]["bytes"] == ROWS * 13 * 2
    assert root == shards_dir(
        paths, tokenizer_path(paths, load_config(config_path(paths), QuantileBinsConfig))
    )


def test_care_power_is_nan_whatever_its_value(
    built: tuple[ProjectPaths, pd.DataFrame, Path, Path],
) -> None:
    _, _, manifest, _ = built
    tokens = np.memmap(manifest.parent / "care__test.bin", dtype=np.uint16, mode="r").reshape(
        -1, 13
    )
    power = 1 + list(CORE_CHANNELS).index("power_kw")
    assert (tokens[:, power] == NAN).all()
    assert (tokens[:, 1] != NAN).all()


def test_the_index_holds_every_admissible_window_with_known_labels(
    built: tuple[ProjectPaths, pd.DataFrame, Path, Path],
) -> None:
    paths, frame, manifest, _ = built
    index = pq.read_table(manifest.parent / "kelmarsh__train.windows.parquet").to_pandas()
    splits = load_config(paths.repo_root / "configs" / "data" / "splits_v2.yaml", SplitsConfig)
    ends = window_ends(frame, splits, 6)
    labelled = frame["narrow_within_1h"].notna().to_numpy()
    # known is admissible AND labelled: the last hour's horizon runs past the turbine-year,
    # so its labels are NA and its admissible windows are left out, never counted negative
    assert int(index["narrow_within_1h_known"].sum()) == int((ends & labelled).sum())
    assert int(ends.sum()) > int((ends & labelled).sum())
    assert (index["end_step"] - index["start_step"] == 143).all()
    assert index["start_step"].min() == 0
    # a 24-hour horizon runs past the turbine-year for its last day: not known, not negative
    known_24h = index["narrow_within_24h_known"].to_numpy()
    assert known_24h.sum() < index["narrow_within_1h_known"].sum()
    labels = frame["narrow_within_1h"].to_numpy(dtype=object)[index["end_step"].to_numpy()]
    known = index["narrow_within_1h_known"].to_numpy()
    assert (index["narrow_within_1h"].to_numpy()[known] == (labels[known] == True)).all()  # noqa: E712


def test_the_narrow_label_without_the_listed_message_drops_its_event(
    built: tuple[ProjectPaths, pd.DataFrame, Path, Path],
) -> None:
    _, _, manifest, report = built
    index = pq.read_table(manifest.parent / "kelmarsh__train.windows.parquet").to_pandas()
    for h in ("1h", "6h"):
        with_ = int(index[f"narrow_within_{h}"].sum())
        without = int(index[f"narrow_within_{h}_without"].sum())
        assert 0 < without < with_
    text = report.read_text(encoding="utf-8")
    assert (
        "| kelmarsh: stored narrow labels equal to those recomputed from events | 1,200 of 1,200 |"
    ) in text
    assert "| kelmarsh: narrow events opened by the listed messages | 1 |" in text
    assert "Narrow, without the events `anemometer defect` opens" in text
