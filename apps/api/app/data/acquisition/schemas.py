import json
import os
from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints

from app.api.schemas import Contract
from app.data.registry_schemas import Key
from app.geo.schemas import Bounds

State = Literal[
    "queued",
    "claimed",
    "fetching",
    "validating",
    "importing",
    "verifying",
    "activating",
    "retry_wait",
    "cancel_requested",
    "cancelled",
    "failed",
    "recovery_required",
    "succeeded",
]
TERMINAL = ("succeeded", "failed", "cancelled")


class AcquisitionRequest(Contract):
    source_id: Key = "osm"
    category: Key = "geo.mapped_poi"
    territory: Key
    aoi: Bounds
    freshness: Literal["current"] = "current"
    idempotency_key: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{8,64}$")]


class Resources(Contract):
    # Per-operation small POI profile; not a universal import or city budget.
    max_area_m2: int = Field(default=250000, ge=100, le=1000000)
    max_bytes: int = Field(default=4 * 1024 * 1024, ge=1024, le=8 * 1024 * 1024)
    max_elements: int = Field(default=10000, ge=1, le=25000)
    min_free_bytes: int = Field(default=256 * 1024 * 1024, ge=1048576)
    job_seconds: int = Field(default=180, ge=30, le=600)
    lease_seconds: int = Field(default=60, ge=10, le=120)
    max_rss_bytes: int = Field(default=256 * 1024 * 1024, ge=67108864)
    request_interval_seconds: int = Field(default=60, ge=60, le=86400)
    requests_per_day: int = Field(default=10, ge=1, le=10)
    max_pending: int = Field(default=2, ge=1, le=2)
    max_retained_jobs: int = Field(default=100, ge=1, le=1000)
    max_attempts: int = Field(default=2, ge=1, le=2)


@lru_cache
def resources() -> Resources:
    return Resources.model_validate(json.loads(os.getenv("BA_ACQUISITION_LIMITS_JSON") or "{}"))


class JobView(Contract):
    id: UUID
    state: State
    stage: str
    source_id: str
    category: str
    territory: str
    aoi: Bounds
    attempt: int
    fencing_token: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    next_attempt_at: AwareDatetime
    result: dict[str, str | int | float] | None
    error_code: str | None
    event_cursor: int


class AcquisitionEvent(Contract):
    schema_version: Literal["acquisition-event-v2"] = "acquisition-event-v2"
    job_id: UUID
    sequence: int
    timestamp: AwareDatetime
    stage: str
    state: State
    message_code: str
    completed: int | None
    total: int | None
    unit: Literal["bytes"] | None


class AcquisitionError(Exception):
    def __init__(self, code: str, *, retryable: bool = False, retry_after: int = 60) -> None:
        self.code = code
        self.retryable = retryable
        self.retry_after = max(60, min(retry_after, 86400))
        super().__init__(code)
