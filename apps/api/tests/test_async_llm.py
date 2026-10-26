import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx2
import pytest

from app.adapters.llm import LLMError, LLMSettings, OllamaLLM
from app.api.schemas import BusinessProfile


class Bytes(httpx2.AsyncByteStream):
    def __init__(self, value: bytes):
        self.value = value

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self.value[:100]
        yield self.value[100:]


def reply(status: int, value: bytes = b"", **kw: Any) -> httpx2.Response:
    return httpx2.Response(status, stream=Bytes(value), **kw)


def install(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    client = httpx2.AsyncClient
    monkeypatch.setattr(
        "app.adapters.llm.httpx2.AsyncClient",
        lambda **kw: client(
            transport=httpx2.MockTransport(handler),
            **kw,
        ),
    )


def wire() -> dict[str, Any]:
    return {
        "done": True,
        "done_reason": "stop",
        "message": {
            "content": json.dumps(
                {
                    "tool": "extract_business_profile",
                    "extracted": [
                        {"field": "city", "value": "Казань", "evidence": "Казани"},
                        {"field": "budget", "value": "2000000", "evidence": "2 млн"},
                    ],
                    "needs_clarification": None,
                    "intent": "profile",
                },
                ensure_ascii=False,
            )
        },
    }


def test_async_transport_same_grounding_and_bounded_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        calls.append(body)
        assert body["stream"] is False and body["options"]["num_predict"] == 384
        assert request.headers["accept-encoding"] == "identity"
        return reply(503) if len(calls) == 1 else reply(200, json.dumps(wire()).encode())

    install(monkeypatch, handler)
    result = asyncio.run(
        OllamaLLM(LLMSettings()).aextract(
            "Кофейня в Казани, бюджет 2 млн",
            BusinessProfile(conversation_id=uuid4()),
            (),
        )
    )
    assert len(calls) == 2 and result.arguments.city == "Казань"
    assert result.arguments.budget == 2000000


@pytest.mark.parametrize(
    "status,body,code",
    [
        (200, b"{", "llm_invalid_response"),
        (200, b"x" * 65537, "llm_invalid_response"),
        (302, b"", "llm_unavailable"),
    ],
    ids=["invalid-json", "too-large", "redirect"],
)
def test_bad_response_never_succeeds_or_retries(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    body: bytes,
    code: str,
) -> None:
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return reply(status, body, headers={"location": "http://other.invalid"})

    install(monkeypatch, handler)
    with pytest.raises(LLMError, match=code):
        asyncio.run(
            OllamaLLM(LLMSettings()).aextract("hello", BusinessProfile(conversation_id=uuid4()), ())
        )
    assert len(calls) == 1


@pytest.mark.parametrize("cancel", [False, True])
def test_deadline_and_cancellation_close_transport(
    monkeypatch: pytest.MonkeyPatch, cancel: bool
) -> None:
    stopped = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        try:
            await asyncio.sleep(5)
            return reply(200, json.dumps(wire()).encode())
        finally:
            stopped.append(True)

    install(monkeypatch, handler)

    async def scenario() -> None:
        pending = asyncio.create_task(
            OllamaLLM(LLMSettings(timeout=1)).aextract(
                "hello",
                BusinessProfile(conversation_id=uuid4()),
                (),
            )
        )
        if cancel:
            await asyncio.sleep(0.02)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            with pytest.raises(LLMError, match="llm_timeout"):
                await pending

    asyncio.run(scenario())
    assert stopped == [True]
