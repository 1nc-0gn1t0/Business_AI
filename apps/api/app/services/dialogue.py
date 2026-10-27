import asyncio
import time
from collections.abc import Callable
from threading import Event
from typing import Protocol, runtime_checkable
from uuid import UUID

import anyio
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.llm import LLMError, LLMSettings, ProfileToolCall, Turn, get_llm
from app.api.conversation_schemas import ConversationView
from app.api.schemas import BusinessProfile
from app.diagnostics import event
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
            started = time.monotonic()
            status, code = 200, "ok"
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
                status, code = 504, "llm_timeout"
                raise LLMError("llm_timeout", 504) from None
            except LLMError as error:
                status, code = error.status, error.code
                raise
            except asyncio.CancelledError:
                status, code = 499, "request_cancelled"
                raise
            except Exception:
                status, code = 500, "inference_failed"
                raise
            finally:
                event("inference", status, time.monotonic() - started, code)
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
