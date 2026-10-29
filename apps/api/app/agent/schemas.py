import json
import os
from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, StringConstraints, ValidationError, model_validator

from app.api.schemas import Contract
from app.data.registry_schemas import CoverageQuery, Key
from app.geo.schemas import Bounds

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
NextStep = Literal[
    "done",
    "clarify",
    "operator_permission_required",
    "provide_aoi",
    "wait_for_job",
    "data_unavailable",
]


class AgentLimits(Contract):
    llm_calls: int = Field(default=4, ge=2, le=6)
    tool_calls: int = Field(default=3, ge=1, le=4)
    per_tool_calls: int = Field(default=2, ge=1, le=2)
    deadline_seconds: int = Field(default=300, ge=10, le=600)
    result_bytes: int = Field(default=12000, ge=1024, le=16000)
    context_bytes: int = Field(default=22000, ge=4000, le=24000)
    retained_runs: int = Field(default=1000, ge=1, le=2000)
    owner_runs: int = Field(default=20, ge=1, le=50)
    retention_days: int = Field(default=7, ge=1, le=30)


def limits() -> AgentLimits:
    try:
        return AgentLimits.model_validate(json.loads(os.getenv("BA_AGENT_LIMITS_JSON") or "{}"))
    except (ValueError, ValidationError):
        raise HTTPException(503, detail={"code": "agent_configuration_error"}) from None


class AcquisitionScope(Contract):
    territory: Key
    aoi: Bounds


class AgentRequest(Contract):
    request_id: UUID
    expected_version: int = Field(ge=0, strict=True)
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1600)]
    acquisition_scope: AcquisitionScope | None = None


class PlanProposal(Contract):
    goal: Short
    capability: Literal[
        "data.describe",
        "data.coverage",
        "data.sufficiency",
        "data.acquire",
        "data.job_status",
        "conversation.respond",
    ]
    tool: Literal[
        "list_data_capabilities",
        "check_data_coverage",
        "check_data_sufficiency",
        "request_data_acquisition",
        "get_acquisition_status",
        "finish",
    ]
    # The LLM format is generated from the actual per-tool DTOs, not this generic envelope.
    arguments: dict[str, Any] = Field(max_length=8)
    reason: Short
    expected_result: Literal[
        "capabilities", "coverage", "sufficiency", "acquisition_job", "response"
    ]


class NoArguments(Contract):
    pass


class CoverageArguments(Contract):
    territory: Key | None = None
    aoi: Bounds | None = None
    categories: tuple[Key, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("Duplicate categories")
        return self

    def query(self) -> CoverageQuery:
        return CoverageQuery(**self.model_dump())


class SufficiencyArguments(Contract):
    territory: Key | None = None
    aoi: Bounds | None = None
    template: Literal["mapped_poi_v1", "vehicle_context_v1", "nonspatial_inputs_v1"]


class AcquisitionArguments(AcquisitionScope):
    source_id: Key
    category: Key


class StatusArguments(Contract):
    job_id: UUID


class Synthesis(Contract):
    # No ungrounded prose accepted: Qwen selects evidence and a safe next-step enum.
    evidence_ids: tuple[int, ...] = Field(max_length=4)
    next_step: NextStep | Literal["continue"]


class ToolTrace(Contract):
    sequence: int
    tool: str
    capability: str
    mutating: bool
    timestamp: datetime
    status: Literal["succeeded", "rejected", "failed"]
    code: str
    validation_ms: float = 0
    execution_ms: float = 0
    argument_sha256: str
    arguments: dict[str, Any] = Field(default_factory=dict, max_length=8)
    reason: str = Field(default="", max_length=200)
    result: dict[str, Any]


class ModelTiming(Contract):
    purpose: Literal["proposal", "synthesis"]
    code: str = "ok"
    queue_ms: float | None
    inference_ms: float | None
    elapsed_ms: float | None = None
    load_ms: float | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None


class AgentResponse(Contract):
    schema_version: Literal["agent-v2"] = "agent-v2"
    request_id: UUID
    conversation_id: UUID
    profile_version: int
    state: Literal["running", "succeeded", "partial", "failed", "cancelled", "interrupted"]
    message: str
    next_step: NextStep
    code: str
    model: str
    traces: tuple[ToolTrace, ...] = ()
    model_timings: tuple[ModelTiming, ...] = ()
    total_ms: float = 0
