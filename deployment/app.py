"""The Lesson 11 API: the research model served locally, for ranking and for text.

Run from the repository root: ``uvicorn deployment.app:app``. The model is loaded **once**, in
the lifespan, on CPU in float32; until it has loaded (or if loading failed) every model endpoint
answers 503.

- ``GET /health``: whether the model is loaded, the SHA-256 of what was loaded, the git SHA.
- ``POST /predict``: a demo-bundle window by ``window_id``, or a raw 144 x 12 window. For a
  bundle window the headline is the **recorded** score and percentile ("as evaluated in the
  record"); the live CPU score is returned beside it, with hours since the last fault. A raw
  window gets the live score with an integer percentile and the ±1 pp resolution note.
- ``POST /generate``: a text continuation, restricted to text ids.
- ``GET /demo/windows``: the bundle's windows; labels only with ``?reveal=true``, the ADR-0009
  variant first. ``GET /demo/windows/{window_id}`` adds the values and the messages.
- ``GET /schema``: the channel order and units a raw window is read in.

Configuration comes from the environment (``deployment/.env.example``): ``FAULTLINE_MODEL``,
``FAULTLINE_TOKENIZERS``, ``FAULTLINE_BUNDLE``, ``FAULTLINE_GIT_SHA`` and ``ALLOWED_ORIGINS``.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from inference.bundle import DemoWindow, read_bundle
from inference.engine import Engine, RawWindow, StatusMessage, sha256_file
from inference.sampling import SamplingParams

from faultline.data.telemetry.schemas import CHANNELS_BY_NAME

from .schemas import (
    RESOLUTION_NOTE,
    GenerateRequest,
    GenerateResponse,
    PredictRequest,
    PredictResponse,
    ScoreOut,
)

logger = logging.getLogger("faultline.lesson11")

REPO_ROOT = Path(__file__).resolve().parents[1]
RECORDED = "as evaluated in the record"
LIVE = "recomputed live, CPU fp32"
UNAVAILABLE = "model not loaded"


@dataclass(frozen=True)
class Settings:
    """Where the model, tokenizers and bundle are, and who may call the API."""

    model_path: Path
    tokenizer_dir: Path
    bundle_path: Path
    allowed_origins: list[str]
    git_sha: str

    @classmethod
    def from_env(cls) -> Settings:
        """Read the environment, with repository defaults."""
        origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080")
        return cls(
            model_path=Path(os.environ.get("FAULTLINE_MODEL", REPO_ROOT / "checkpoints/model.pt")),
            tokenizer_dir=Path(
                os.environ.get("FAULTLINE_TOKENIZERS", REPO_ROOT / "data/tokenizers")
            ),
            bundle_path=Path(
                os.environ.get("FAULTLINE_BUNDLE", REPO_ROOT / "lesson11/demo/kelmarsh_demo_v0.npz")
            ),
            allowed_origins=[o.strip() for o in origins.split(",") if o.strip()],
            git_sha=os.environ.get("FAULTLINE_GIT_SHA") or _git_sha(),
        )


def _git_sha() -> str:
    try:
        from faultline.runs import git_sha

        return git_sha(REPO_ROOT)
    except Exception:  # no git in the image: the build passes FAULTLINE_GIT_SHA instead
        return "unknown"


@dataclass
class Served:
    """What the lifespan loaded, once."""

    engine: Engine | None = None
    windows: dict[str, DemoWindow] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


Loader = Callable[[Settings], tuple[Engine, list[DemoWindow]]]


def load(settings: Settings) -> tuple[Engine, list[DemoWindow]]:
    """The engine and the demo bundle's windows."""
    engine = Engine.load(settings.model_path, settings.tokenizer_dir)
    windows = read_bundle(settings.bundle_path) if settings.bundle_path.exists() else []
    return engine, windows


def create_app(settings: Settings | None = None, loader: Loader = load) -> FastAPI:
    """Build the app; the model is loaded by ``loader`` once, when the app starts.

    Args:
        settings: Paths, origins and the git SHA; read from the environment when omitted.
        loader: Loads the engine and the bundle (a tiny model in the tests).

    Returns:
        The app.
    """
    settings = settings or Settings.from_env()
    served = Served()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        started = time.perf_counter()
        try:
            engine, windows = loader(settings)
            served.windows = {w.window_id: w for w in windows}
            served.hashes = {"model": str(engine.meta.get("model_sha256", "unknown"))}
            for role, record in engine.meta.get("tokenizers", {}).items():
                served.hashes[f"tokenizer_{role}"] = str(record["sha256"])
            if settings.bundle_path.exists():
                served.hashes["bundle"] = sha256_file(settings.bundle_path)
            served.engine = engine
            logger.info("model loaded in %.1f s", time.perf_counter() - started)
        except Exception:
            logger.exception("model failed to load; model endpoints answer 503")
        yield

    app = FastAPI(title="FaultLine Lesson 11", version="0", lifespan=lifespan)
    app.state.served = served
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def log_latency(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        logger.info(
            "%s %s %d %.1f ms",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000.0,
        )
        return response

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    def engine_or_503() -> Engine:
        if served.engine is None:
            raise HTTPException(status_code=503, detail=UNAVAILABLE)
        return served.engine

    @app.get("/health")
    def health() -> JSONResponse:
        loaded = served.engine is not None
        body = {"model_loaded": loaded, "sha256": served.hashes, "git_sha": settings.git_sha}
        return JSONResponse(status_code=200 if loaded else 503, content=body)

    @app.get("/schema")
    def schema() -> dict[str, Any]:
        engine = engine_or_503()
        return {
            "steps": engine.context_steps,
            "step_minutes": 10,
            "channels": [
                {
                    "name": name,
                    "unit": CHANNELS_BY_NAME[name].unit,
                    "description": CHANNELS_BY_NAME[name].description,
                }
                for name in engine.channels
            ],
            "status_convention": "messages are read lower-cased, as the model was trained",
        }

    @app.post("/predict", response_model=PredictResponse)
    def predict(request: PredictRequest) -> PredictResponse:
        engine = engine_or_503()
        demo: DemoWindow | None = None
        if request.window_id is not None:
            demo = served.windows.get(request.window_id)
            if demo is None:
                raise HTTPException(status_code=404, detail="unknown window_id")
            raw = demo.raw
        else:
            assert request.values is not None and request.end_utc is not None
            raw = RawWindow(
                values=np.array(
                    [[math.nan if v is None else v for v in row] for row in request.values],
                    dtype=np.float64,
                ),
                end_utc=_timestamp(request.end_utc),
                messages=tuple(
                    StatusMessage(start_utc=_timestamp(m.start_utc), text=m.text)
                    for m in request.status_messages
                ),
            )
        try:
            with served.lock:
                out = engine.predict(raw)
        except ValueError as problem:
            raise HTTPException(status_code=422, detail=str(problem)) from problem
        if demo is None:
            live = ScoreOut(
                logit=out.logit, score=out.score, percentile=round(out.percentile), source=LIVE
            )
            return PredictResponse(
                headline=live,
                live=live,
                percentile_note=RESOLUTION_NOTE.format(n=int(engine.scores.values.size)),
                has_text=out.has_text,
                n_status_messages=out.n_status_messages,
                time_ms=out.time_ms,
            )
        live = ScoreOut(logit=out.logit, score=out.score, percentile=out.percentile, source=LIVE)
        recorded = ScoreOut(
            logit=demo.recorded_logit,
            score=demo.recorded_score,
            percentile=demo.recorded_percentile,
            source=RECORDED,
        )
        return PredictResponse(
            headline=recorded,
            live=live,
            recorded=recorded,
            hours_since_last_fault=demo.hours_since_last_fault,
            hours_since_last_fault_percentile=demo.hours_since_last_fault_percentile,
            has_text=out.has_text,
            n_status_messages=out.n_status_messages,
            time_ms=out.time_ms,
        )

    @app.post("/generate", response_model=GenerateResponse)
    def generate(request: GenerateRequest) -> GenerateResponse:
        engine = engine_or_503()
        params = SamplingParams(
            temperature=request.temperature,
            top_k=request.top_k,
            top_p=request.top_p,
            repetition_penalty=request.repetition_penalty,
            seed=request.seed,
        )
        with served.lock:
            out = engine.generate_text(request.prompt, params, request.max_new_tokens)
        return GenerateResponse(
            text=out.text,
            tokens=len(out.token_ids),
            stop_reason=out.stop_reason,
            prompt_tokens=out.prompt_tokens,
            time_ms=out.time_ms,
        )

    @app.get("/demo/windows")
    def demo_windows(reveal: bool = Query(default=False)) -> dict[str, Any]:
        engine_or_503()
        return {
            "windows": [_summary(w, reveal) for w in served.windows.values()],
            "labels_revealed": reveal,
        }

    @app.get("/demo/windows/{window_id}")
    def demo_window(window_id: str, reveal: bool = Query(default=False)) -> dict[str, Any]:
        engine = engine_or_503()
        window = served.windows.get(window_id)
        if window is None:
            raise HTTPException(status_code=404, detail="unknown window_id")
        values = [[None if math.isnan(v) else float(v) for v in row] for row in window.raw.values]
        return {
            **_summary(window, reveal),
            "channels": engine.channels,
            "values": values,
            "status_messages": [
                {"start_utc": m.start_utc.isoformat(), "text": m.text} for m in window.raw.messages
            ],
        }

    return app


def _timestamp(value: Any) -> Any:
    import pandas as pd

    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _summary(window: DemoWindow, reveal: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "window_id": window.window_id,
        "turbine": window.turbine,
        "end_utc": window.raw.end_utc.isoformat(),
        "n_status_messages": len(window.raw.messages),
    }
    if reveal:
        # The ADR-0009 variant first (A10): 73 of the 100 registered positives are
        # anemometer-defect events that the variant does not count.
        out["labels"] = {
            "variant": window.label_variant,
            "registered": window.label_registered,
        }
    return out


app = create_app()
