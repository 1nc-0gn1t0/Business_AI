"""The executable catalog. Descriptions never create authority or adapters."""

import json
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent.schemas import (
    AcquisitionArguments,
    AgentRequest,
    CoverageArguments,
    NoArguments,
    PlanProposal,
    StatusArguments,
    SufficiencyArguments,
)
from app.api.schemas import Contract
from app.data.acquisition import service as acquisition
from app.data.acquisition.schemas import AcquisitionRequest
from app.data.coverage import assess_sufficiency, coverage
from app.data.registry import acquisition as acquisition_option
from app.data.registry_schemas import CoverageQuery, CoverageResult, DataRequirement, RegistryConfig
from app.db.models import AcquisitionEventRecord, AgentRunRecord


class AgentError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    capability: str
    result_type: str
    arguments: type[Contract]
    mutating: bool = False
    permission: str = "conversation_owner"
    revision: str = "v1"


TOOLS = {
    t.id: t
    for t in (
        ToolDefinition("list_data_capabilities", "data.describe", "capabilities", NoArguments),
        ToolDefinition("check_data_coverage", "data.coverage", "coverage", CoverageArguments),
        ToolDefinition(
            "check_data_sufficiency", "data.sufficiency", "sufficiency", SufficiencyArguments
        ),
        ToolDefinition(
            "request_data_acquisition",
            "data.acquire",
            "acquisition_job",
            AcquisitionArguments,
            True,
            "operator",
        ),
        ToolDefinition(
            "get_acquisition_status",
            "data.job_status",
            "acquisition_job",
            StatusArguments,
            False,
            "operator_and_job_grant",
        ),
    )
}
TEMPLATES = {
    "mapped_poi_v1": ("geo.mapped_poi",),
    "vehicle_context_v1": ("geo.mapped_poi", "geo.vehicle_network"),
    "nonspatial_inputs_v1": ("user.budget", "user.costs"),
}


def validate_proposal(proposal: PlanProposal) -> tuple[ToolDefinition, Contract]:
    definition = TOOLS.get(proposal.tool)
    if definition is None:
        raise AgentError("unsupported_tool")
    if proposal.capability != definition.capability:
        raise AgentError("unsupported_capability")
    if proposal.expected_result != definition.result_type:
        raise AgentError("unexpected_result_type")
    if len(json.dumps(proposal.arguments).encode()) > 2048:
        raise AgentError("tool_arguments_too_large")
    try:
        arguments = definition.arguments.model_validate(proposal.arguments)
    except (ValueError, ValidationError):
        raise AgentError("invalid_tool_arguments") from None
    return definition, arguments


def compact_coverage(result: CoverageResult) -> dict[str, Any]:
    document = result.model_dump(mode="json")
    for assessment in document["assessments"]:
        evidence = assessment["datasets"]
        assessment["dataset_count"] = len(evidence)
        assessment["evidence_truncated"] = len(evidence) > 2
        assessment["datasets"] = evidence[:2]
        for dataset in assessment["datasets"]:
            # No raw POI names, geometry or arbitrary source descriptions in model context.
            dataset["metadata"].pop("source_name", None)
    return document


def execute(
    session: Session,
    proposal: PlanProposal,
    definition: ToolDefinition,
    args: Contract,
    registry: RegistryConfig,
    run: AgentRunRecord,
    request: AgentRequest,
) -> dict[str, Any]:
    if isinstance(args, NoArguments):
        categories = [c.id for c in registry.categories]
        local = {}
        for index in range(0, len(categories), 10):
            result = coverage(
                session, CoverageQuery(categories=tuple(categories[index : index + 10])), registry
            )
            local.update({a.category: a.local_status for a in result.assessments})
        return {
            "categories": [
                {
                    "id": c.id,
                    "local_status": local[c.id],
                    "private": c.private,
                    "acquisition_adapter": "osm_poi_v1" if c.id == "geo.mapped_poi" else None,
                }
                for c in registry.categories
            ],
            "sources": [
                {
                    "id": s.id,
                    "categories": list(s.categories),
                    "acquisition": acquisition_option(
                        s, "local_analysis", "geo.mapped_poi"
                    ).model_dump(mode="json"),
                    "acquisition_scope": s.acquisition_scope,
                    "approval_expires_at": s.acquisition_approved_until.isoformat()
                    if s.acquisition_approved_until
                    else None,
                }
                for s in registry.sources
            ],
            "tools": [
                {
                    "id": d.id,
                    "capability": d.capability,
                    "result_type": d.result_type,
                    "mutating": d.mutating,
                    "permission": d.permission,
                    "revision": d.revision,
                }
                for d in TOOLS.values()
            ],
            "unsupported_operations": [
                "web_search",
                "download_road_network",
                "industry_ranking",
                "shell",
                "sql",
            ],
            "limitations": [
                "Local presence is not full city coverage; only OSM POI has an acquisition adapter."
            ],
        }
    if isinstance(args, CoverageArguments):
        if args.territory is None and args.aoi is None:
            raise AgentError("territory_or_aoi_required")
        return compact_coverage(coverage(session, args.query(), registry))
    if isinstance(args, SufficiencyArguments):
        categories_ = TEMPLATES[args.template]
        result = coverage(
            session,
            CoverageQuery(territory=args.territory, aoi=args.aoi, categories=categories_),
            registry,
        )
        requirements = tuple(DataRequirement(id=c, category=c) for c in categories_)
        return {
            "template": args.template,
            "coverage": compact_coverage(result),
            "sufficiency": assess_sufficiency(requirements, result, args.template).model_dump(
                mode="json"
            ),
            "executor_supported": False,
            "limitations": [
                "Data eligibility is not an implemented industry algorithm "
                "or reliable economic recommendation."
            ],
        }
    if isinstance(args, AcquisitionArguments):
        scope = request.acquisition_scope
        if scope is None:
            raise AgentError("explicit_acquisition_scope_required")
        if scope.territory != args.territory or scope.aoi != args.aoi:
            raise AgentError("acquisition_scope_mismatch")
        # Keys are backend-derived, never model-controlled; U-02 retains global scope dedup.
        key = acquisition.digest(
            {
                "owner": str(run.conversation_id),
                "run": str(run.id),
                "arguments": args.model_dump(mode="json"),
            }
        )
        job = acquisition.create(
            session, AcquisitionRequest(**args.model_dump(), idempotency_key=key), registry
        )
        run.job_ids = list(set(run.job_ids) | {job.id})
        return {
            "job_id": str(job.id),
            "state": job.state,
            "stage": job.stage,
            "event_cursor": job.event_cursor,
            "result": job.result,
            "worker_availability": "unknown",
            "error_code": job.error_code,
        }
    if isinstance(args, StatusArguments):
        granted = session.scalar(
            sa.select(AgentRunRecord)
            .where(
                AgentRunRecord.conversation_id == run.conversation_id,
                AgentRunRecord.operator.is_(True),
                AgentRunRecord.job_ids.contains([args.job_id]),
            )
            .limit(1)
        )
        if granted is None:
            raise AgentError("acquisition_job_not_found")
        job = acquisition.view(acquisition.get_job(session, args.job_id))
        latest = session.scalar(
            sa.select(AcquisitionEventRecord)
            .where(AcquisitionEventRecord.job_id == job.id)
            .order_by(AcquisitionEventRecord.sequence.desc())
            .limit(1)
        )
        return {
            "job_id": str(job.id),
            "state": job.state,
            "stage": job.stage,
            "event_cursor": job.event_cursor,
            "result": job.result,
            "error_code": job.error_code,
            "latest_event": {
                "sequence": latest.sequence,
                "timestamp": latest.timestamp.isoformat(),
                "stage": latest.stage,
                "message_code": latest.message_code,
            }
            if latest
            else None,
            "worker_availability": "unknown",
        }
    raise HTTPException(422, detail={"code": "unsupported_tool"})
