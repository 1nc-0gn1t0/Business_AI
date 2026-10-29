"""Short owner/CAS/consent transactions; never hold a connection during inference."""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.agent import tools
from app.agent.schemas import (
    AgentLimits,
    AgentRequest,
    AgentResponse,
    PlanProposal,
    ToolTrace,
    limits,
)
from app.api.acquisition import operator
from app.data.acquisition.schemas import AcquisitionError
from app.data.acquisition.service import digest
from app.data.registry_schemas import RegistryConfig
from app.db.models import AgentRunRecord
from app.leads.consents import require_consent
from app.leads.policy import LeadError
from app.services.conversations import Conversations, VersionConflict


class RunStore:
    def __init__(
        self,
        factory: sessionmaker[Session],
        owner: UUID,
        token: str,
        operator_token: str | None,
        request: AgentRequest,
        cfg: AgentLimits,
        cancelled: Event,
    ):
        self.factory, self.owner, self.token = factory, owner, token
        self.operator_token, self.request, self.cfg = operator_token, request, cfg
        self.cancelled = cancelled

    def authenticate_operator(self) -> None:
        if self.operator_token is None:
            raise tools.AgentError("operator_permission_required")
        operator(self.operator_token)

    def start(self, model: str) -> AgentResponse:
        with self.factory.begin() as session:
            # One admission lock bounds global retention and serializes duplicate creation.
            session.execute(sa.text("SELECT pg_advisory_xact_lock(782493202)"))
            service = Conversations(session)
            view = service.get(self.owner, self.token, lock=True)
            consent = require_consent(session, self.owner, "assistant")
            if self.operator_token is not None:
                self.authenticate_operator()
            fingerprint = digest(self.request.model_dump(mode="json"))
            existing = session.get(AgentRunRecord, self.request.request_id)
            if existing is not None:
                if (
                    existing.conversation_id != self.owner
                    or existing.request_hash != fingerprint
                    or existing.operator != (self.operator_token is not None)
                ):
                    raise HTTPException(409, detail={"code": "agent_request_conflict"})
                if existing.consent_revision != consent.revision:
                    raise LeadError("consent_revision_conflict")
                if existing.created_at < datetime.now(UTC) - timedelta(
                    days=self.cfg.retention_days
                ):
                    raise HTTPException(410, detail={"code": "agent_run_expired"})
                if existing.state == "running":
                    if existing.deadline_at <= datetime.now(UTC):
                        existing.state = "interrupted"
                        response = AgentResponse.model_validate(existing.response).model_copy(
                            update={
                                "state": "interrupted",
                                "code": "agent_interrupted",
                                "message": "Операция прервана. Проверьте сохранённые действия.",
                            }
                        )
                        existing.response = response.model_dump(mode="json")
                        return response
                    raise HTTPException(409, detail={"code": "agent_request_running"})
                cached = AgentResponse.model_validate(existing.response)
                if existing.state == "interrupted":
                    cached = cached.model_copy(
                        update={
                            "state": "interrupted",
                            "code": "agent_interrupted",
                            "message": "Операция прервана. Проверьте сохранённые действия.",
                        }
                    )
                    existing.response = cached.model_dump(mode="json")
                return cached.model_copy(update={"state": existing.state})
            now = datetime.now(UTC)
            # Expired runs cannot execute tools/publication; no automatic resumption.
            session.execute(
                sa.update(AgentRunRecord)
                .where(
                    AgentRunRecord.conversation_id == self.owner,
                    AgentRunRecord.state == "running",
                    AgentRunRecord.deadline_at <= now,
                )
                .values(state="interrupted")
            )
            session.execute(
                sa.delete(AgentRunRecord).where(
                    AgentRunRecord.state != "running",
                    AgentRunRecord.created_at < now - timedelta(days=self.cfg.retention_days),
                )
            )
            if session.scalar(
                sa.select(AgentRunRecord.id).where(
                    AgentRunRecord.conversation_id == self.owner, AgentRunRecord.state == "running"
                )
            ):
                raise HTTPException(409, detail={"code": "agent_owner_busy"})
            if (
                session.scalar(sa.select(sa.func.count()).select_from(AgentRunRecord)) or 0
            ) >= self.cfg.retained_runs or (
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(AgentRunRecord)
                    .where(AgentRunRecord.conversation_id == self.owner)
                )
                or 0
            ) >= self.cfg.owner_runs:
                raise HTTPException(429, detail={"code": "agent_storage_limit"})
            snapshot = service.message_input(self.owner, self.token, self.request.expected_version)
            response = AgentResponse(
                request_id=self.request.request_id,
                conversation_id=self.owner,
                profile_version=view.version,
                state="running",
                message="Проверяю доступные данные.",
                next_step="done",
                code="running",
                model=model,
            )
            session.add(
                AgentRunRecord(
                    id=self.request.request_id,
                    conversation_id=self.owner,
                    request_hash=fingerprint,
                    expected_version=snapshot.version,
                    consent_revision=snapshot.consent_revision,
                    operator=self.operator_token is not None,
                    state="running",
                    created_at=now,
                    deadline_at=now + timedelta(seconds=self.cfg.deadline_seconds),
                    job_ids=[],
                    response=response.model_dump(mode="json"),
                )
            )
            return response

    def guard(self, session: Session) -> AgentRunRecord:
        if self.cancelled.is_set():
            raise asyncio.CancelledError
        view = Conversations(session).get(self.owner, self.token, lock=True)
        consent = require_consent(session, self.owner, "assistant")
        run = session.get(AgentRunRecord, self.request.request_id, with_for_update=True)
        if run is None or run.conversation_id != self.owner:
            raise tools.AgentError("agent_run_not_found")
        if run.state != "running" or run.deadline_at <= datetime.now(UTC):
            raise tools.AgentError("agent_deadline_exceeded")
        if view.version != run.expected_version:
            raise VersionConflict(view.version)
        if consent.revision != run.consent_revision:
            raise LeadError("consent_revision_conflict")
        if run.operator:
            self.authenticate_operator()
        return run

    def tool(self, proposal: PlanProposal, registry: RegistryConfig, sequence: int) -> ToolTrace:
        started = time.monotonic()
        definition = tools.TOOLS.get(proposal.tool)
        status: Literal["succeeded", "rejected", "failed"] = "succeeded"
        code, result = "ok", {}
        validated_arguments = {}
        validation_ms = execution_ms = 0.0
        with self.factory.begin() as session:
            run = self.guard(session)
            try:
                definition, args = tools.validate_proposal(proposal)
                validated_arguments = args.model_dump(mode="json", exclude_none=True)
                if definition.permission != "conversation_owner":
                    self.authenticate_operator()
                validation_ms = (time.monotonic() - started) * 1000
                executing = time.monotonic()
                with session.begin_nested():
                    result = tools.execute(
                        session, proposal, definition, args, registry, run, self.request
                    )
                    if len(json.dumps(result, ensure_ascii=False).encode()) > self.cfg.result_bytes:
                        raise tools.AgentError("tool_result_too_large")
                    # Revalidate cancellation/consent/CAS after the short operation too.
                    self.guard(session)
                execution_ms = (time.monotonic() - executing) * 1000
            except (tools.AgentError, AcquisitionError, HTTPException) as error:
                status = "rejected"
                code = (
                    error.code
                    if isinstance(error, (tools.AgentError, AcquisitionError))
                    else (
                        str(error.detail.get("code", "tool_execution_failed"))
                        if isinstance(error.detail, dict)
                        else "tool_execution_failed"
                    )
                )
                result = {"code": code}
            trace = ToolTrace(
                sequence=sequence,
                tool=proposal.tool,
                capability=proposal.capability,
                mutating=definition.mutating if definition else False,
                timestamp=datetime.now(UTC),
                status=status,
                code=code,
                argument_sha256=digest(proposal.arguments),
                arguments=validated_arguments,
                reason=proposal.reason,
                result=result,
                validation_ms=validation_ms,
                execution_ms=execution_ms,
            )
            response = AgentResponse.model_validate(run.response)
            run.response = response.model_copy(
                update={"traces": response.traces + (trace,)}
            ).model_dump(mode="json")
            return trace

    def checkpoint(self, response: AgentResponse) -> None:
        with self.factory.begin() as session:
            run = self.guard(session)
            run.response = response.model_dump(mode="json")

    def finish(self, response: AgentResponse) -> AgentResponse:
        with self.factory.begin() as session:
            run = self.guard(session)
            if response.traces or response.state == "succeeded":
                view = Conversations(session).agent_reply(
                    self.owner,
                    self.token,
                    run.expected_version,
                    run.consent_revision,
                    self.request.content,
                    response.message,
                )
                response = response.model_copy(update={"profile_version": view.version})
            run.state, run.response = response.state, response.model_dump(mode="json")
            if self.cancelled.is_set():
                raise asyncio.CancelledError
            return response

    def abandon(self, code: str) -> None:
        with self.factory.begin() as session:
            # A failure must release the run even when consent/version has changed.
            Conversations(session).get(self.owner, self.token, lock=True)
            run = session.get(AgentRunRecord, self.request.request_id, with_for_update=True)
            if run and run.conversation_id == self.owner and run.state == "running":
                response = AgentResponse.model_validate(run.response).model_copy(
                    update={
                        "state": "cancelled" if self.cancelled.is_set() else "failed",
                        "code": code,
                        "message": "Операция не завершена. Проверьте сохранённые действия.",
                    }
                )
                run.state, run.response = response.state, response.model_dump(mode="json")


def read_run(
    session: Session, owner: UUID, token: str, run_id: UUID, operator_token: str | None
) -> AgentResponse:
    Conversations(session).get(owner, token)
    require_consent(session, owner, "assistant")
    run = session.get(AgentRunRecord, run_id)
    if run is None or run.conversation_id != owner:
        raise HTTPException(404, detail={"code": "agent_run_not_found"})
    if run.operator:
        if operator_token is None:
            raise HTTPException(404, detail={"code": "agent_run_not_found"})
        operator(operator_token)
    if run.created_at < datetime.now(UTC) - timedelta(days=limits().retention_days):
        raise HTTPException(410, detail={"code": "agent_run_expired"})
    response = AgentResponse.model_validate(run.response)
    if run.state == "interrupted" or (
        run.state == "running" and run.deadline_at <= datetime.now(UTC)
    ):
        run.state = "interrupted"
        response = response.model_copy(
            update={
                "state": "interrupted",
                "code": "agent_interrupted",
                "message": "Операция прервана. Проверьте сохранённые действия.",
            }
        )
        run.response = response.model_dump(mode="json")
    return response.model_copy(update={"state": run.state})
