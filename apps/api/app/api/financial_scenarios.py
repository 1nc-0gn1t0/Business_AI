import asyncio
from threading import Event
from typing import Annotated
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.llm import LLMError
from app.api.conversations import Database, Token
from app.db.models import FinancialActionRecord
from app.db.session import get_session_factory
from app.finance.v2.engine import calculate
from app.finance.v2.llm import AssumptionLLM, get_assumption_llm
from app.finance.v2.registry import enabled
from app.finance.v2.schemas import (
    FinancialCommand,
    FinancialDocument,
    FinancialSnapshot,
    FinancialView,
    InputPatch,
    ReviewCommand,
    WhatIf,
    WhatIfResult,
)
from app.finance.v2.service import FinancialService, patch_document
from app.industry.schemas import UniversalProfile
from app.services.dialogue import blocking


def require_enabled() -> None:
    if not enabled():
        raise HTTPException(503, detail={"code": "financial_v2_disabled"})


router = APIRouter(
    prefix="/api/v2/conversations/{conversation_id}/financial-scenarios",
    tags=["financial-scenarios"],
    dependencies=[Depends(require_enabled)],
)


@router.get("", response_model=FinancialView)
def get(conversation_id: UUID, token: Token, session: Database) -> FinancialView:
    return FinancialService(session).view(conversation_id, token)


@router.patch("", response_model=FinancialView)
def patch(
    conversation_id: UUID, body: InputPatch, token: Token, session: Database
) -> FinancialView:
    return FinancialService(session).patch(conversation_id, token, body)


@router.post("/review", response_model=FinancialView)
def review(
    conversation_id: UUID, body: ReviewCommand, token: Token, session: Database
) -> FinancialView:
    return FinancialService(session).review(conversation_id, token, body)


@router.get("/results/{result_id}", response_model=FinancialSnapshot)
def result(
    conversation_id: UUID, result_id: UUID, token: Token, session: Database
) -> FinancialSnapshot:
    return FinancialService(session).result(conversation_id, token, result_id)


@router.post("/cancel", response_model=FinancialView)
def cancel(
    conversation_id: UUID, body: FinancialCommand, token: Token, session: Database
) -> FinancialView:
    return FinancialService(session).cancel(conversation_id, token, body)


@router.post("/what-if", response_model=WhatIfResult)
def what_if(conversation_id: UUID, body: WhatIf, token: Token, session: Database) -> WhatIfResult:
    service = FinancialService(session)
    _, doc = service.guard(conversation_id, token, body)
    updated = patch_document(doc, body.updates)
    # Explicit preview request authorizes these hypothetical values only, not saving.
    updated = updated.model_copy(
        update={
            "entries": {
                k: v.model_copy(update={"review": "confirmed"})
                if k in {u.parameter for u in body.updates}
                else v
                for k, v in updated.entries.items()
            }
        }
    )
    return WhatIfResult(input_revision=doc.revision, result=calculate(updated))


Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]


async def operation(
    conversation_id: UUID,
    token: str,
    body: FinancialCommand,
    factory: sessionmaker[Session],
    llm: AssumptionLLM | None,
    cancelled: Event,
) -> FinancialView:
    kind = "propose" if llm else "calculate"

    def read() -> tuple[UniversalProfile, FinancialDocument, int] | None:
        with factory.begin() as session:
            return FinancialService(session).begin(conversation_id, token, body, kind)

    # Explicit type avoids keeping a DB session across queue/inference/calculation.
    snapshot = await blocking(read, cancelled)
    if snapshot is None:

        def replay() -> FinancialView:
            with factory.begin() as session:
                return FinancialService(session).view(conversation_id, token)

        return await blocking(replay, cancelled)
    profile, doc, consent = snapshot
    try:
        proposal = (await llm.propose(profile, doc))[0] if llm else None
        calculated = None if llm else await blocking(lambda: calculate(doc), cancelled)

        def write() -> FinancialView:
            with factory.begin() as session:
                if cancelled.is_set():
                    raise asyncio.CancelledError
                service = FinancialService(session)
                if proposal is not None:
                    view = service.publish_proposal(
                        conversation_id,
                        token,
                        body,
                        proposal,
                        consent,
                        getattr(llm, "model_name", "scripted_test_fixture"),
                    )
                else:
                    assert calculated is not None
                    view = service.publish_result(conversation_id, token, body, calculated, consent)
                if cancelled.is_set():
                    raise asyncio.CancelledError
                return view

        return await blocking(write, cancelled)
    except BaseException as error:
        interrupted = isinstance(error, asyncio.CancelledError)
        code = (
            error.code
            if isinstance(error, LLMError)
            else ("request_cancelled" if interrupted else "financial_operation_failed")
        )

        def fail() -> None:
            with factory.begin() as session:
                row = session.get(
                    FinancialActionRecord, (conversation_id, body.request_id), with_for_update=True
                )
                if row and row.state == "running":
                    row.state, row.error_code = "interrupted" if interrupted else "failed", code

        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(fail)
        raise


async def watch_operation(
    conversation_id: UUID,
    token: str,
    body: FinancialCommand,
    request: Request,
    factory: sessionmaker[Session],
    llm: AssumptionLLM | None,
) -> FinancialView:
    cancelled = Event()
    work = asyncio.create_task(operation(conversation_id, token, body, factory, llm, cancelled))

    async def disconnected() -> None:
        while (await request.receive())["type"] != "http.disconnect":
            pass
        cancelled.set()

    watch = asyncio.create_task(disconnected())

    async def cancellation() -> None:
        while True:
            await asyncio.sleep(0.5)

            def state() -> bool:
                with factory() as session:
                    row = session.get(FinancialActionRecord, (conversation_id, body.request_id))
                    return row is not None and row.state == "cancelled"

            if await anyio.to_thread.run_sync(state):
                cancelled.set()
                return

    stop = asyncio.create_task(cancellation())
    try:
        done, _ = await asyncio.wait((work, watch, stop), return_when=asyncio.FIRST_COMPLETED)
        if stop in done:
            raise HTTPException(499, detail={"code": "financial_operation_cancelled"})
        if watch in done:
            raise HTTPException(499, detail={"code": "request_cancelled"})
        return await work
    finally:
        cancelled.set()
        work.cancel()
        watch.cancel()
        stop.cancel()
        with anyio.CancelScope(shield=True):
            await asyncio.gather(work, watch, stop, return_exceptions=True)


@router.post("/propose", response_model=FinancialView)
async def propose(
    conversation_id: UUID,
    body: FinancialCommand,
    token: Token,
    request: Request,
    factory: Factory,
    llm: Annotated[AssumptionLLM, Depends(get_assumption_llm)],
) -> FinancialView:
    return await watch_operation(conversation_id, token, body, request, factory, llm)


@router.post("/calculate", response_model=FinancialView)
async def run(
    conversation_id: UUID, body: FinancialCommand, token: Token, request: Request, factory: Factory
) -> FinancialView:
    return await watch_operation(conversation_id, token, body, request, factory, None)
