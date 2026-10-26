import asyncio
from collections.abc import Callable
from threading import Event
from typing import Protocol, runtime_checkable
from uuid import UUID

import anyio
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.llm import LLMError, LLMSettings, ProfileToolCall, Turn, get_llm
from app.api.conversation_schemas import ConversationView
from app.api.schemas import BusinessProfile
from app.limits import inference
from app.services.conversations import Conversations, MessageInput, needs_inference


@runtime_checkable
class AsyncLLM(Protocol):
    async def aextract(
        self, content: str, profile: BusinessProfile, history: tuple[Turn, ...]
    ) -> ProfileToolCall: ...


async def blocking[T](operation: Callable[[], T], cancelled: Event) -> T:
    # Do not abandon a DB worker mid-transaction, or release a sync adapter's GPU
    # slot while its thread is still running. Cancellation waits for its cleanup.
    worker = asyncio.create_task(asyncio.to_thread(operation))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancelled.set()
        with anyio.CancelScope(shield=True):
            try:
                await worker
            except Exception:
                pass
        raise


async def send_message(
    factory: sessionmaker[Session],
    owner: UUID,
    token: str,
    version: int,
    content: str,
    cancelled: Event,
) -> ConversationView:
    def read() -> MessageInput:
        with factory.begin() as session:
            return Conversations(session).message_input(owner, token, version)

    snapshot = await blocking(read, cancelled)
    call = None
    mode = None
    if needs_inference(content):
        async with inference.QUEUE.slot():
            llm = get_llm()
            settings = getattr(llm, "settings", LLMSettings())
            try:
                async with asyncio.timeout(settings.timeout):
                    if isinstance(llm, AsyncLLM):
                        call = await llm.aextract(content, snapshot.profile, snapshot.history)
                    else:
                        call = await blocking(
                            lambda: llm.extract(content, snapshot.profile, snapshot.history),
                            cancelled,
                        )
            except TimeoutError:
                raise LLMError("llm_timeout", 504) from None
            mode = llm.mode

    def write() -> ConversationView:
        with factory.begin() as session:
            if cancelled.is_set():
                raise asyncio.CancelledError
            result = Conversations(session).update(
                owner,
                token,
                snapshot.version,
                content=content,
                call=call,
                mode=mode,
                consent_revision=snapshot.consent_revision,
            )
            # A disconnect before this commit boundary rolls back even flushed SQL.
            if cancelled.is_set():
                raise asyncio.CancelledError
            return result

    return await blocking(write, cancelled)
