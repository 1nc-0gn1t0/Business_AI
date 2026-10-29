import asyncio
import os
from threading import Event
from typing import Annotated
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.llm import LLMError
from app.api.conversation_schemas import ConfirmRequest
from app.api.conversations import Database, Token
from app.db.session import get_session_factory
from app.industry.llm import IndustryLLM, get_industry_llm, grounded
from app.industry.registry import INDUSTRIES, missing
from app.industry.schemas import IndustryCatalog, UniversalMessage, UniversalPatch, UniversalView
from app.industry.service import IndustryProfiles
from app.services.dialogue import blocking

router = APIRouter(prefix="/api/v2", tags=["industry"])


def enabled() -> bool:
    return os.getenv("BA_INDUSTRY_ENABLED", "0") == "1"


def require_enabled() -> None:
    if not enabled():
        raise HTTPException(503, detail={"code": "industry_disabled"})


@router.get("/industry-capabilities", response_model=IndustryCatalog)
def catalog() -> IndustryCatalog:
    return IndustryCatalog(enabled=enabled(), industries=tuple(INDUSTRIES.values()))


BASE = "/conversations/{conversation_id}/industry-profile"


@router.get(BASE, response_model=UniversalView, dependencies=[Depends(require_enabled)])
def get(conversation_id: UUID, token: Token, session: Database) -> UniversalView:
    return IndustryProfiles(session).view(conversation_id, token)


@router.patch(BASE, response_model=UniversalView, dependencies=[Depends(require_enabled)])
def patch(
    conversation_id: UUID, body: UniversalPatch, token: Token, session: Database
) -> UniversalView:
    service = IndustryProfiles(session)
    current = service.load(conversation_id, token, lock=True)
    updated = service.edit(current, body.updates, body.industry, "user_edit")
    if body.defer_fields:
        if not set(body.defer_fields) <= set(missing(updated)):
            raise HTTPException(422, detail={"code": "invalid_deferred_field"})
        updated = updated.model_copy(
            update={
                "deferred_fields": tuple(
                    sorted(set(updated.deferred_fields) | set(body.defer_fields))
                )
            }
        )
    updated = updated.model_copy(
        update={
            "raw_industry": body.raw_industry
            or (current.raw_industry if updated.industry == current.industry else None),
            "resolution": "known" if updated.industry != "generic" else "unknown",
        }
    )
    return service.save(conversation_id, token, body.expected_version, updated)


@router.post(
    BASE + "/confirm", response_model=UniversalView, dependencies=[Depends(require_enabled)]
)
def confirm(
    conversation_id: UUID, body: ConfirmRequest, token: Token, session: Database
) -> UniversalView:
    service = IndustryProfiles(session)
    return service.save(
        conversation_id,
        token,
        body.expected_version,
        service.load(conversation_id, token, lock=True),
        confirmation=True,
    )


@router.post(
    BASE + "/messages", response_model=UniversalView, dependencies=[Depends(require_enabled)]
)
async def message(
    conversation_id: UUID,
    body: UniversalMessage,
    token: Token,
    request: Request,
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    llm: Annotated[IndustryLLM, Depends(get_industry_llm)],
) -> UniversalView:
    cancelled = Event()
    work = asyncio.create_task(run_message(conversation_id, body, token, factory, llm, cancelled))

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


async def run_message(
    conversation_id: UUID,
    body: UniversalMessage,
    token: str,
    factory: sessionmaker[Session],
    llm: IndustryLLM,
    cancelled: Event,
) -> UniversalView:

    def read() -> tuple[UniversalView, int]:
        from app.leads.consents import require_consent
        from app.services.conversations import VersionConflict

        with factory.begin() as session:
            service = IndustryProfiles(session)
            view = service.view(conversation_id, token)
            if view.conversation.version != body.expected_version:
                raise VersionConflict(view.conversation.version)
            return view, require_consent(session, conversation_id, "assistant").revision

    snapshot, consent = await blocking(read, cancelled)
    proposal = None
    fallback = False
    try:
        proposal, _ = await llm.propose(body.content, snapshot.profile)
        proposal = grounded(proposal, body.content, snapshot.profile)
    except LLMError as error:
        if error.code != "llm_invalid_response":
            raise
        fallback = True
    except HTTPException as error:
        if error.status_code != 422:
            raise
        fallback = True

    def write() -> UniversalView:
        with factory.begin() as session:
            service = IndustryProfiles(session)
            profile = snapshot.profile
            answer = None
            if proposal and not fallback:
                if proposal.resolution == "ambiguous":
                    answer = "Какую одну бизнес-идею выбираете?"
                    profile = profile.model_copy(
                        update={"resolution": "ambiguous", "confirmed_revision": None}
                    )
                else:
                    profile = service.edit(
                        profile,
                        proposal.updates,
                        proposal.industry,
                        "user_message",
                        {u.field: u.evidence for u in proposal.updates},
                    )
                    profile = profile.model_copy(
                        update={
                            "raw_industry": proposal.raw_industry or profile.raw_industry,
                            "industry_evidence": proposal.industry_evidence
                            or profile.industry_evidence,
                            "resolution": "known" if profile.industry != "generic" else "unknown",
                        }
                    )
            if not profile.idea:
                profile = profile.model_copy(update={"idea": body.content})
            if fallback:
                answer = (
                    "Не удалось уверенно разобрать ответ. "
                    "Уточните параметры или измените их вручную."
                )
                if missing(profile):
                    from app.industry.registry import definitions

                    answer += " " + definitions(profile.industry)[missing(profile)[0]].question
            if cancelled.is_set():
                raise asyncio.CancelledError
            result = service.save(
                conversation_id,
                token,
                body.expected_version,
                profile,
                content=body.content,
                consent_revision=consent,
                answer=answer,
                extraction="clarification_fallback" if fallback else "ollama",
            )
            if cancelled.is_set():
                raise asyncio.CancelledError
            return result

    return await blocking(write, cancelled)
