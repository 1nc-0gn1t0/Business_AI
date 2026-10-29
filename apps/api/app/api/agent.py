"""Explicit opt-in v2 dialogue; legacy extraction remains independent."""

import asyncio
import os
from threading import Event
from typing import Annotated
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from app.agent.llm import AgentLLM, get_agent_llm
from app.agent.orchestrator import run_agent
from app.agent.schemas import AgentRequest, AgentResponse, limits
from app.agent.store import RunStore, read_run
from app.api.conversations import Database, Token
from app.api.registry import Registry
from app.db.session import get_session_factory


def enabled() -> None:
    if os.getenv("BA_AGENT_ENABLED") != "1":
        raise HTTPException(503, detail={"code": "agent_disabled"})


router = APIRouter(prefix="/api/v2/conversations", tags=["agent"], dependencies=[Depends(enabled)])
OperatorToken = Annotated[str | None, Header(alias="X-Acquisition-Token", max_length=128)]


@router.post("/{conversation_id}/agent", response_model=AgentResponse)
async def send(
    conversation_id: UUID,
    body: AgentRequest,
    token: Token,
    registry: Registry,
    request: Request,
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    llm: Annotated[AgentLLM, Depends(get_agent_llm)],
    operator_token: OperatorToken = None,
) -> AgentResponse:
    cancelled = Event()
    store = RunStore(factory, conversation_id, token, operator_token, body, limits(), cancelled)
    work = asyncio.create_task(run_agent(store, llm, registry))

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


@router.get("/{conversation_id}/agent/{request_id}", response_model=AgentResponse)
def read(
    conversation_id: UUID,
    request_id: UUID,
    token: Token,
    session: Database,
    operator_token: OperatorToken = None,
) -> AgentResponse:
    return read_run(session, conversation_id, token, request_id, operator_token)
