"""Request and response models of the Lesson 11 API, with their bounds.

Every bound is enforced by Pydantic, so an out-of-range request is a 422 before any model code
runs. The sampling bounds are :class:`inference.sampling.SamplingParams`'s.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

#: A raw window's shape.
STEPS, CHANNELS = 144, 12

#: What every score is.
RANKING_NOTE = "ranking score, not a calibrated probability"

#: Why a raw window's percentile is an integer (A9).
RESOLUTION_NOTE = "±1 pp resolution: reference scores are bf16-quantized ({n:,} distinct values)"


class StatusMessageIn(BaseModel):
    """One timestamped status message, as the provider's status log writes it."""

    start_utc: datetime
    text: str = Field(min_length=1, max_length=500)


class PredictRequest(BaseModel):
    """A demo-bundle window by id, or a raw window: exactly one of the two."""

    window_id: str | None = Field(default=None, max_length=64)
    values: list[list[float | None]] | None = Field(
        default=None,
        description=f"{STEPS} rows (10-minute steps, oldest first) x {CHANNELS} channels in "
        "GET /schema order; null is a missing value",
    )
    end_utc: datetime | None = Field(default=None, description="the last step, on the 10-min grid")
    status_messages: list[StatusMessageIn] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def _one_kind(self) -> PredictRequest:
        if (self.window_id is None) == (self.values is None):
            raise ValueError("give either window_id or values, not both and not neither")
        if self.values is not None:
            if self.end_utc is None:
                raise ValueError("a raw window needs end_utc")
            if len(self.values) != STEPS or any(len(row) != CHANNELS for row in self.values):
                raise ValueError(f"values must be exactly {STEPS} x {CHANNELS}")
        elif self.status_messages or self.end_utc is not None:
            raise ValueError("a bundle window takes only window_id")
        return self


class ScoreOut(BaseModel):
    """A score with its percentile among the recorded seed-1 test scores."""

    logit: float = Field(description="the (d) head's logit")
    score: float = Field(description="logit + the recorded prior offset")
    percentile: float
    source: str


class PredictResponse(BaseModel):
    """A scored window. For a bundle window the headline is the recorded score."""

    headline: ScoreOut
    live: ScoreOut
    recorded: ScoreOut | None = None
    percentile_note: str | None = None
    hours_since_last_fault: float | None = None
    hours_since_last_fault_percentile: float | None = None
    has_text: bool
    n_status_messages: int
    time_ms: float
    note: str = RANKING_NOTE


class GenerateRequest(BaseModel):
    """A text prompt and the decoding strategy."""

    prompt: str = Field(default="", max_length=2000)
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_k: int = Field(default=0, ge=0, le=32768)
    top_p: float = Field(default=1.0, gt=0.0, le=1.0)
    repetition_penalty: float = Field(default=1.0, ge=1.0, le=2.0)
    max_new_tokens: int = Field(default=64, ge=1, le=200)
    seed: int = Field(default=0, ge=0, le=2**31 - 1)


class GenerateResponse(BaseModel):
    """A continuation, restricted to text ids."""

    text: str
    tokens: int
    stop_reason: str
    prompt_tokens: int
    time_ms: float
