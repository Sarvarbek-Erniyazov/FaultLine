"""Build the held-out Kelmarsh demo bundle (Lesson 11, C3) and measure serving parity on it.

**The rule, fixed before building.** Kelmarsh turbines 4 and 5; recorded seed-1 test windows
whose end falls in 2023; every positive of the registered label (``narrow_within_24h``) up to
100, and 200 negatives. One generator, ``default_rng(20260927)``, draws the positives first
(only when there are more than 100) and then the negatives. The windows are ordered by turbine,
then end time.

**Per window.** The raw 144 x 12 final-stage values and the status messages starting in the
window (what a client would send), the end time, both labels (registered and ADR-0009's
variant), hours since the last fault from ADR-0029's own :func:`persistence` (P2, capped at
720 h) with its mid-rank percentile over all 137,025 recorded test rows, and the saved seed-1
logit with its corrected score and percentile.

**Parity (A1 as revised by A9).** The bundle is written, read back, and every window **as read
from the bundle** goes through the serving engine next to the 20 fixed windows: tier 1 (identical
token ids), tier 2 (max |Δ| <= 0.02, ρ >= 0.999, max percentile shift <= 1.0 pp) and, with CUDA,
tier 3. The result goes to ``lesson11/demo/parity.json``. A failure exits non-zero: STOP.

Run from the repository root: ``python -m lesson11.build_demo_bundle``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from inference.bundle import PER_MESSAGE, PER_WINDOW, read_bundle, write_bundle
from inference.engine import Engine, RankTable, RawWindow
from inference.export import MODEL_FILE, tokenizer_files

from faultline.config import load_config
from faultline.evaluation.exploratory_v0 import ExploratoryConfig, persistence
from faultline.paths import ProjectPaths
from faultline.runs import git_sha

# Imported by name: the root package ``evaluation`` shares its name with ``tests/evaluation``,
# which the pinned pre-commit ruff sorts as first-party and the venv's ruff as third-party.
parity = importlib.import_module("evaluation.parity")

DEMO_DIR = Path(__file__).resolve().parent / "demo"
BUNDLE_FILE = "kelmarsh_demo_v0.npz"
SOURCE, TURBINES, YEAR = "kelmarsh", ("Kelmarsh 4", "Kelmarsh 5"), 2023
MAX_POSITIVES, NEGATIVES, SEED = 100, 200, 20260927
MAX_BYTES = 5_000_000

ATTRIBUTION = """\
The windows in kelmarsh_demo_v0.npz are derived from:

  Cubico Sustainable Investments Ltd, Kelmarsh wind farm data, Zenodo,
  doi:10.5281/zenodo.5841833 (version doi:10.5281/zenodo.16807551),
  licensed CC BY 4.0: https://creativecommons.org/licenses/by/4.0/

Changes made: the 10-minute SCADA values were harmonised, gap-imputed and restricted to 12
channels by the FaultLine pipeline; the status messages are the provider's status log, cleaned.
The labels, the hours since the last fault and the scores are FaultLine's, not the provider's.
The provider does not endorse this project.
"""


def end_years(t: np.ndarray) -> np.ndarray:
    """Calendar years of integer-second UTC times."""
    return t.astype("datetime64[s]").astype("datetime64[Y]").astype(np.int64) + 1970


def select(ctx: Any) -> tuple[np.ndarray, dict[str, int]]:
    """The bundle's recorded rows, by the rule, ordered by turbine then end time.

    Args:
        ctx: The parity context (the evaluation's rows and records).

    Returns:
        The rows and the counts the rule saw.
    """
    rows = ctx.rows
    sources = np.asarray(ctx.sources)[rows.which]
    candidates = (
        (sources == SOURCE) & np.isin(rows.turbines, TURBINES) & (end_years(rows.t) == YEAR)
    )
    positives = np.flatnonzero(candidates & rows.full)
    negatives = np.flatnonzero(candidates & ~rows.full)
    rng = np.random.default_rng(SEED)
    if positives.size > MAX_POSITIVES:
        positives = rng.choice(positives, MAX_POSITIVES, replace=False)
    chosen_negatives = rng.choice(negatives, NEGATIVES, replace=False)
    chosen = np.concatenate([positives, chosen_negatives]).astype(np.int64)
    chosen = chosen[np.lexsort((rows.t[chosen], rows.turbines[chosen]))]
    counts = {
        "candidates": int(candidates.sum()),
        "positives_available": int((candidates & rows.full).sum()),
        "negatives_available": int((candidates & ~rows.full).sum()),
        "positives_chosen": int(positives.size),
        "negatives_chosen": int(chosen_negatives.size),
    }
    return chosen, counts


def window_id(turbine: str, t: int) -> str:
    """``K<turbine number>-<end, YYYYmmddTHHMM>``."""
    stamp = np.datetime64(int(t), "s").astype(object).strftime("%Y%m%dT%H%M")
    return f"K{turbine.split()[-1]}-{stamp}"


def content_digest(path: Path) -> str:
    """SHA-256 over every array's name, dtype, shape and bytes (the zip's own timestamps vary)."""
    digest = hashlib.sha256()
    with np.load(path, allow_pickle=False) as data:
        for name in sorted(data.files):
            array = np.ascontiguousarray(data[name])
            digest.update(f"{name}|{array.dtype.str}|{array.shape}".encode())
            digest.update(array.tobytes())
    return digest.hexdigest()


def build(paths: ProjectPaths) -> dict[str, Any]:
    """Build the bundle, its manifest and attribution, and measure parity on it.

    Args:
        paths: Resolved project paths.

    Returns:
        The parity result.

    Raises:
        ValueError: If the bundle exceeds 5 MB or does not read back as written.
    """
    root = paths.repo_root
    engine = Engine.load(paths.checkpoints_dir / MODEL_FILE, tokenizer_files(paths)["bins"].parent)
    ctx = parity.open_context(paths)
    config = load_config(root / parity.EXPLORATORY_CONFIG, ExploratoryConfig)
    p2 = persistence(paths, config, ctx.rows).scores["P2"]
    p2_table = RankTable.from_scores(p2)

    chosen, counts = select(ctx)
    raws: list[RawWindow] = [ctx.raw_window(int(r), engine.channels) for r in chosen]
    recorded_logit = ctx.saved.logits[chosen].astype(np.float32)
    recorded_score = recorded_logit + np.float32(ctx.saved.prior_offset)
    turbines = ctx.rows.turbines[chosen].astype(str)
    message_window, message_start, message_text = [], [], []
    for position, raw in enumerate(raws):
        for message in raw.messages:
            message_window.append(position)
            message_start.append(int(message.start_utc.value))
            message_text.append(message.text)
    arrays: dict[str, np.ndarray] = {
        "window_id": np.array(
            [window_id(b, int(t)) for b, t in zip(turbines, ctx.rows.t[chosen], strict=True)]
        ),
        "row": chosen,
        "turbine": turbines,
        "end_utc_s": ctx.rows.t[chosen].astype(np.int64),
        "values": np.stack([raw.values for raw in raws]).astype(np.float64),
        "label_registered": ctx.rows.full[chosen].astype(bool),
        "label_variant": ctx.rows.variant[chosen].astype(bool),
        "label_variant_known": ctx.rows.variant_known[chosen].astype(bool),
        "hours_since_last_fault": (-p2[chosen]).astype(np.float64),
        "hours_since_last_fault_percentile": np.array([p2_table.percentile(x) for x in p2[chosen]]),
        "recorded_logit": recorded_logit,
        "recorded_score": recorded_score.astype(np.float32),
        "recorded_percentile": np.array(
            [engine.scores.percentile(float(x)) for x in recorded_score]
        ),
        "message_window": np.asarray(message_window, dtype=np.int64),
        "message_start_ns": np.asarray(message_start, dtype=np.int64),
        "message_text": np.asarray(message_text, dtype=np.str_),
        "channels": np.asarray(engine.channels, dtype=np.str_),
    }
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    bundle = DEMO_DIR / BUNDLE_FILE
    write_bundle(bundle, arrays)
    size = bundle.stat().st_size
    if size > MAX_BYTES:
        raise ValueError(f"{bundle} is {size:,} bytes, over the {MAX_BYTES:,} limit")

    # Parity runs on the windows as the bundle gives them back.
    windows = read_bundle(bundle)
    for window, raw in zip(windows, raws, strict=True):
        same_messages = [(m.start_utc, m.text) for m in window.raw.messages] == [
            (m.start_utc, m.text) for m in raw.messages
        ]
        if not (np.array_equal(window.raw.values, raw.values, equal_nan=True) and same_messages):
            raise ValueError(f"{window.window_id} does not read back as written")
    rows, bundle_raws, labels = parity.parity_windows(
        engine, ctx, extra=(chosen, [w.raw for w in windows])
    )
    result: dict[str, Any] = parity.measure(engine, ctx, rows, bundle_raws, labels)
    bundle_only = np.array([label == "bundle" for label in labels])
    per_set = {}
    for name, mask in (("fixed", ~bundle_only), ("bundle", bundle_only)):
        entries = [w for w, m in zip(result["windows"], mask, strict=True) if m]
        delta = np.array([w["abs_delta"] for w in entries])
        shift = np.array([w["percentile_shift"] for w in entries])
        per_set[name] = {
            "windows": len(entries),
            "ids_identical": int(sum(w["ids_identical"] for w in entries)),
            "max_abs_delta": float(delta.max()),
            "p99_abs_delta": float(np.quantile(delta, 0.99)),
            "mean_abs_delta": float(delta.mean()),
            "spearman": parity.spearman(
                np.array([w["live"] for w in entries]), np.array([w["recorded"] for w in entries])
            ),
            "max_percentile_shift": float(shift.max()),
        }
    result["by_set"] = per_set
    (DEMO_DIR / "parity.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")

    sources = engine.meta["sources"]
    manifest = {
        "bundle": BUNDLE_FILE,
        "bytes": size,
        "content_sha256": content_digest(bundle),
        "windows": int(chosen.size),
        "messages": len(message_window),
        "rule": {
            "source": SOURCE,
            "turbines": list(TURBINES),
            "end_year": YEAR,
            "split": "test (recorded seed-1 scoring rows, stride 12)",
            "positives": f"all registered-label positives up to {MAX_POSITIVES}",
            "negatives": NEGATIVES,
            "seed": SEED,
            "draw": "one default_rng(seed): positives first (only if more than the cap), "
            "then negatives; ordered by turbine, then end time",
        },
        "counts": {
            **counts,
            "variant_positives_in_bundle": int(arrays["label_variant"].sum()),
            "variant_unknown_in_bundle": int((~arrays["label_variant_known"]).sum()),
        },
        "labels": {"registered": config.label, "variant": config.variant_label},
        "hours_since_last_fault": {
            "definition": "ADR-0029 P2 magnitude: hours since the turbine's last narrow event "
            f"start at or before the window end, capped at {config.persistence.cap_hours} h",
            "code": "faultline.evaluation.exploratory_v0.persistence, imported, not re-implemented",
            "percentile": "mid-rank of P2 (= -hours) over all 137,025 recorded test rows; "
            "higher is more recent",
        },
        "recorded": {
            "logit": "saved seed-1 (d) head logit, bf16 scoring on CUDA",
            "score": "logit + prior offset, added in float32",
            "prior_offset": float(ctx.saved.prior_offset),
            "percentile": "mid-rank over the 137,025 recorded seed-1 test scores",
        },
        "channels": list(engine.channels),
        "per_window_arrays": list(PER_WINDOW),
        "per_message_arrays": list(PER_MESSAGE),
        "served_model": {
            "model_sha256": engine.meta["model_sha256"],
            "scores": sources["scores"],
            "probe": sources["probe"],
        },
        "licence": "CC-BY-4.0; see ATTRIBUTION",
        "built_at_git_sha": git_sha(root),
    }
    (DEMO_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    (DEMO_DIR / "ATTRIBUTION").write_text(ATTRIBUTION, encoding="utf-8")
    return result


def main() -> None:
    """Build, print the parity summary, and exit non-zero if parity failed."""
    result = build(ProjectPaths.resolve())
    summary = {k: v for k, v in result.items() if k != "windows"}
    print(json.dumps(summary, indent=1))
    if not result["passed"]:
        print("PARITY FAILED: STOP", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
