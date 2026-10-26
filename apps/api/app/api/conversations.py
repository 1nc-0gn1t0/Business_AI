import asyncio
from threading import Event
from typing import Annotated
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security
from fastapi.security import APIKeyHeader
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.llm import LLMError
from app.api.conversation_schemas import (
    ConfirmRequest,
    ConversationCreated,
    ConversationView,
    MessageRequest,
    MessageView,
    PatchRequest,
    RevisionView,
)
from app.db.session import get_session, get_session_factory
from app.services.conversations import (
    ConversationNotFound,
    Conversations,
    IncompleteProfile,
    VersionConflict,
)
from app.services.dialogue import send_message

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])
access_key = APIKeyHeader(name="X-Conversation-Token", auto_error=False)


def get_token(value: Annotated[str | None, Security(access_key)]) -> str:
    if value is None or not 32 <= len(value) <= 128:
        raise HTTPException(401, detail={"code": "conversation_token_required"})
    return value


Token = Annotated[str, Depends(get_token)]
Database = Annotated[Session, Depends(get_session, scope="function")]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


def get_service(session: Database) -> Conversations:
    return Conversations(session)


Service = Annotated[Conversations, Depends(get_service)]


@router.post("", response_model=ConversationCreated, status_code=201)
def create(service: Service) -> ConversationCreated:
    return service.create()


@router.get("/{conversation_id}", response_model=ConversationView)
@router.get("/{conversation_id}/profile", response_model=ConversationView)
def get(conversation_id: UUID, token: Token, service: Service) -> ConversationView:
    return service.get(conversation_id, token)


@router.post("/{conversation_id}/messages", response_model=ConversationView)
async def send(
    conversation_id: UUID,
    body: MessageRequest,
    token: Token,
    request: Request,
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> ConversationView:
    cancelled = Event()
    work = asyncio.create_task(
        send_message(
            factory, conversation_id, token, body.expected_version, body.content, cancelled
        )
    )

    async def disconnected() -> None:
        while (await request.receive())["type"] != "http.disconnect":
            pass
        cancelled.set()

    watch = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait((work, watch), return_when=asyncio.FIRST_COMPLETED)
        if watch in done:
            raise HTTPException(499, detail={"code": "request_cancelled"})
        return await work
    finally:
        cancelled.set()
        work.cancel()
        watch.cancel()
        with anyio.CancelScope(shield=True):
            await asyncio.gather(work, watch, return_exceptions=True)


@router.patch("/{conversation_id}/profile", response_model=ConversationView)
def patch(
    conversation_id: UUID, body: PatchRequest, token: Token, service: Service
) -> ConversationView:
    return service.update(conversation_id, token, body.expected_version, patch=body.patch)


@router.post("/{conversation_id}/profile/confirm", response_model=ConversationView)
def confirm(
    conversation_id: UUID, body: ConfirmRequest, token: Token, service: Service
) -> ConversationView:
    return service.update(conversation_id, token, body.expected_version, confirmation=True)


@router.get("/{conversation_id}/messages", response_model=list[MessageView])
def messages(
    conversation_id: UUID,
    token: Token,
    service: Service,
    offset: Offset = 0,
    limit: Limit = 50,
) -> list[MessageView]:
    return service.messages(conversation_id, token, offset, limit)


@router.get("/{conversation_id}/history", response_model=list[RevisionView])
def history(
    conversation_id: UUID,
    token: Token,
    service: Service,
    offset: Offset = 0,
    limit: Limit = 50,
) -> list[RevisionView]:
    return service.history(conversation_id, token, offset, limit)


# Error handlers are installed on the application so every route shares stable codes.
def error_detail(error: Exception) -> tuple[int, dict[str, object]]:
    if isinstance(error, LLMError):
        return error.status, {"code": error.code, "trace_id": error.trace_id}
    if isinstance(error, ConversationNotFound):
        return 404, {"code": "conversation_not_found"}
    if isinstance(error, VersionConflict):
        return 409, {"code": "version_conflict", "current_version": error.version}
    if isinstance(error, IncompleteProfile):
        return 409, {"code": "profile_incomplete", "missing_fields": error.missing}
    if isinstance(error, ValidationError):
        return 422, {
            "code": "invalid_profile",
            "errors": error.errors(include_input=False, include_context=False),
        }
    raise error
