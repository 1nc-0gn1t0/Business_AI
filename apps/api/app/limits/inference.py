import asyncio
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.adapters.llm import LLMError
from app.limits.config import policy


class InferenceQueue:
    """One event loop/worker, one active call, bounded FIFO; no per-user maps."""

    def __init__(self) -> None:
        self.active = False
        self.waiters: deque[asyncio.Future[None]] = deque()

    def release(self) -> None:
        if self.waiters:
            self.waiters.popleft().set_result(None)
        else:
            self.active = False

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        if self.active:
            if len(self.waiters) >= policy().inference_queue_size:
                raise LLMError("llm_queue_full", 429)
            ticket: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            self.waiters.append(ticket)
            try:
                async with asyncio.timeout(policy().inference_wait_seconds):
                    await asyncio.shield(ticket)
            except BaseException as error:
                if ticket in self.waiters:
                    self.waiters.remove(ticket)
                else:
                    # Cancellation can race with promotion to the active slot.
                    self.release()
                if isinstance(error, TimeoutError):
                    raise LLMError("llm_queue_timeout", 429) from None
                raise
        else:
            self.active = True
        try:
            yield
        finally:
            self.release()


QUEUE = InferenceQueue()


def reset_inference() -> None:
    global QUEUE
    QUEUE = InferenceQueue()
