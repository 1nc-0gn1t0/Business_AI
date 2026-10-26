"""BA-016: real transactions, controlled Ollama transport, no GPU/network dependency."""

import json
import os
from collections.abc import AsyncIterator
from decimal import Decimal

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.adapters.llm import LLMSettings, OllamaLLM

from .test_conversations import create

pytestmark = pytest.mark.skipif(
    os.environ.get("BA_RUN_DB_TESTS") != "1", reason="Requires Postgres"
)


@pytest.mark.parametrize("old_budget", [None, "500"])
def test_invalid_budget_grounding_preserves_transactional_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, old_budget: str | None
) -> None:
    _, headers, url = create(client)
    patched = client.patch(
        url + "/profile",
        headers=headers,
        json={
            "expected_version": 0,
            "patch": {"city": "Казань", "budget": old_budget},
        },
    )
    assert patched.status_code == 200
    text = "Бюджет минус 500 рублей"
    raw = json.dumps(
        {
            "done": True,
            "done_reason": "stop",
            "message": {
                "content": json.dumps(
                    {
                        "tool": "extract_business_profile",
                        "extracted": [
                            {"field": "budget", "value": "500", "evidence": text},
                        ],
                        "intent": "profile",
                        "needs_clarification": None,
                    }
                )
            },
        }
    ).encode()

    class ResponseStream(httpx2.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield raw

    real_client = httpx2.AsyncClient
    transport = httpx2.MockTransport(lambda request: httpx2.Response(200, stream=ResponseStream()))
    monkeypatch.setattr(
        "app.adapters.llm.httpx2.AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    monkeypatch.setattr("app.services.dialogue.get_llm", lambda: OllamaLLM(LLMSettings()))
    response = client.post(
        url + "/messages",
        headers=headers,
        json={
            "expected_version": 1,
            "content": text,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["city"] == "Казань"
    assert (
        body["profile"]["budget"] is None
        if old_budget is None
        else Decimal(body["profile"]["budget"]) == Decimal(old_budget)
    )
    assert "Уточните общий бюджет" in body["assistant_message"]
    assert body["profile"]["confirmation_state"] == "draft"
    assert client.get(url, headers=headers).json() == body
    assert len(client.get(url + "/history", headers=headers).json()) == 3
    assert any(m["content"] == text for m in client.get(url + "/messages", headers=headers).json())
