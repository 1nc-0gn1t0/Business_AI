import json
import os
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Resource = Literal[
    "conversations", "messages", "revisions", "consents", "drafts", "receipts", "audit", "reports"
]
Count = Annotated[int, Field(strict=True, ge=1, le=1000000)]
GLOBAL_RECORDS: dict[Resource, int] = dict(
    conversations=500,
    messages=20000,
    revisions=10000,
    consents=5000,
    drafts=1000,
    receipts=1000,
    audit=20000,
    reports=200,
)
OWNER_RECORDS: dict[Resource, int] = dict(
    messages=400,
    revisions=200,
    consents=60,
    drafts=20,
    receipts=20,
    audit=300,
    reports=20,
)


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    body_bytes: Count = 65536
    report_body_bytes: Count = 131072
    header_bytes: Count = 16384
    query_bytes: Count = 4096
    path_bytes: Count = 2048
    body_timeout_seconds: float = Field(default=10, gt=0, le=120)
    profile_chars: Count = 200
    profile_items: Count = 20
    message_chars: Count = 4000
    text_chars: Count = 4096
    collection_items: Count = 128
    json_nodes: Count = 4096
    json_depth: Count = 16
    version_max: int = Field(default=2147483647, strict=True, ge=1, le=2147483647)
    window_seconds: Count = 60
    requests_per_window: Count = 600
    heavy_per_window: Count = 120
    active_requests: Count = 8
    active_heavy: Count = 2
    inference_queue_size: int = Field(default=1, strict=True, ge=0, le=4)
    inference_wait_seconds: float = Field(default=10, gt=0, le=30)
    report_storage_bytes: int = Field(default=134217728, strict=True, ge=1, le=1073741824)
    global_records: dict[Resource, Count] = Field(default_factory=GLOBAL_RECORDS.copy)
    owner_records: dict[Resource, Count] = Field(default_factory=OWNER_RECORDS.copy)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        resources = {
            "conversations",
            "messages",
            "revisions",
            "consents",
            "drafts",
            "receipts",
            "audit",
            "reports",
        }
        if set(self.global_records) != resources or set(self.owner_records) != resources - {
            "conversations"
        }:
            raise ValueError("Storage budgets must cover all resource types")
        if (
            self.report_body_bytes < self.body_bytes
            or self.text_chars < max(self.message_chars, self.profile_chars)
            or self.profile_items > self.collection_items
        ):
            raise ValueError("Report/body/text budgets are inconsistent")
        if (
            self.active_heavy > self.active_requests
            or self.heavy_per_window > self.requests_per_window
        ):
            raise ValueError("Heavy budget must fit the total budget")
        return self


def load() -> Limits:
    try:
        if int(os.getenv("WEB_CONCURRENCY", "1")) != 1:
            raise ValueError("Only one API worker is supported")
        overrides = json.loads(os.getenv("BA_API_LIMITS_JSON") or "{}")
        defaults = Limits().model_dump()
        for key in ("global_records", "owner_records"):
            if key in overrides:
                overrides[key] = defaults[key] | overrides[key]
        return Limits.model_validate(defaults | overrides)
    except (ValueError, TypeError):
        raise RuntimeError(
            "Invalid BA_API_LIMITS_JSON or unsupported worker configuration"
        ) from None


POLICY = load()


def policy() -> Limits:
    return POLICY


VersionNumber = Annotated[int, Field(strict=True, ge=0, le=POLICY.version_max)]
