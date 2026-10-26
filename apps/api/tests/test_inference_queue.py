import asyncio
from threading import Event

import pytest

from app.adapters.llm import LLMError
from app.limits import config
from app.limits.http import Admission
from app.limits.inference import InferenceQueue
from app.services.dialogue import blocking


def test_fifo_overflow_timeout_and_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config, "POLICY", config.policy().model_copy(update={"inference_wait_seconds": 0.03})
    )

    async def scenario() -> None:
        gate = InferenceQueue()

        async def queued() -> None:
            async with gate.slot():
                raise AssertionError("Expired waiter entered inference")

        async with gate.slot():
            pending = asyncio.create_task(queued())
            await asyncio.sleep(0)
            assert len(gate.waiters) == 1
            with pytest.raises(LLMError, match="llm_queue_full"):
                async with gate.slot():
                    pass
            with pytest.raises(LLMError, match="llm_queue_timeout"):
                await pending
            assert not gate.waiters and gate.active
        async with gate.slot():
            assert gate.active
        assert not gate.active

    asyncio.run(scenario())


@pytest.mark.parametrize("promoted", [False, True])
def test_cancel_waiting_or_just_promoted_ticket(promoted: bool) -> None:
    async def scenario() -> None:
        gate = InferenceQueue()

        async def operation() -> None:
            async with gate.slot():
                await asyncio.Event().wait()

        owner = gate.slot()
        await owner.__aenter__()
        waiter = asyncio.create_task(operation())
        await asyncio.sleep(0)
        if promoted:
            # Exit promotes the ticket synchronously; cancel before it can resume.
            await owner.__aexit__(None, None, None)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        if not promoted:
            await owner.__aexit__(None, None, None)
        assert not gate.active and not gate.waiters
        async with gate.slot():
            pass

    asyncio.run(scenario())


def test_sync_fallback_cancellation_does_not_release_slot_while_worker_runs() -> None:
    entered, release, cancelled = Event(), Event(), Event()

    async def scenario() -> None:
        gate = InferenceQueue()

        def worker() -> None:
            entered.set()
            assert release.wait(3)

        async def operation() -> None:
            async with gate.slot():
                await blocking(worker, cancelled)

        pending = asyncio.create_task(operation())
        assert await asyncio.to_thread(entered.wait, 2)
        pending.cancel()
        await asyncio.sleep(0.01)
        assert gate.active and not pending.done() and cancelled.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert not gate.active

    try:
        asyncio.run(scenario())
    finally:
        release.set()


def test_models_keep_heavy_frequency_but_not_analytical_active_slots() -> None:
    admission = Admission()
    admission.enter(False, model=True)
    assert admission.active == admission.heavy == 1 and admission.active_heavy == 0
    admission.enter(True)
    assert admission.active_heavy == 1
    admission.leave(False)
    admission.leave(True)
    assert admission.active == admission.active_heavy == 0
