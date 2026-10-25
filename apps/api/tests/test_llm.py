import io
import json
from collections.abc import Callable
from decimal import Decimal
from email.message import Message
from typing import Any
from urllib.error import HTTPError, URLError
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.adapters.llm import (
    LLMError,
    LLMSettings,
    OllamaLLM,
    ProfileToolCall,
    StubLLM,
    get_llm,
)
from app.api.schemas import BusinessProfile


def profile() -> BusinessProfile:
    return BusinessProfile(conversation_id=uuid4())


def response(arguments: dict[str, Any], evidence: str = "test") -> bytes:
    return json.dumps(
        {
            "done": True,
            "done_reason": "stop",
            "message": {
                "content": json.dumps(
                    {
                        "tool": "extract_business_profile",
                        "extracted": [
                            {"field": key, "value": value, "evidence": evidence}
                            for key, value in arguments.items()
                        ],
                        "needs_clarification": None,
                        "intent": "profile",
                    }
                )
            },
        }
    ).encode()


def transport(monkeypatch: pytest.MonkeyPatch, operation: Callable[..., io.BytesIO]) -> None:
    class Opener:
        open = staticmethod(operation)

    monkeypatch.setattr("app.adapters.llm.build_opener", lambda *args: Opener())


def test_real_adapter_contract_and_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    def send(request: Any, timeout: float) -> io.BytesIO:
        payload = json.loads(request.data)
        assert request.full_url == "http://127.0.0.1:11434/api/chat"
        assert payload["stream"] is False
        assert payload["options"]["num_ctx"] == 4096
        assert payload["format"]["properties"]["tool"]["const"] == "extract_business_profile"
        assert (
            json.loads(payload["messages"][-1]["content"])["message"]
            == "Кофейня в Казани, два миллиона рублей"
        )
        assert timeout <= 120
        return io.BytesIO(
            response(
                {"city": "Казань", "category": "кофейня", "budget": "2000000"},
                evidence="Кофейня в Казани, два миллиона рублей",
            )
        )

    transport(monkeypatch, send)
    call = OllamaLLM(LLMSettings()).extract("Кофейня в Казани, два миллиона рублей", profile(), ())
    assert call.arguments.city == "Казань"
    assert call.arguments.budget == 2000000
    assert "funding" not in call.arguments.model_fields_set


@pytest.mark.parametrize(
    "text,value",
    [
        ("Бюджет минус 500 рублей", "500"),
        ("Бюджет -500 рублей", "500"),
        ("Бюджет 2000000,50 рублей", "2000000"),
        ("Бюджет 2 миллиона рублей", "3000000"),
        ("Бюджет 2000 долларов", "2000"),
    ],
)
def test_budget_contradiction_requests_clarification(
    monkeypatch: pytest.MonkeyPatch, text: str, value: str
) -> None:
    transport(monkeypatch, lambda *args, **kwargs: io.BytesIO(response({"budget": value}, text)))
    call = OllamaLLM(LLMSettings()).extract(text, profile(), ())
    assert call.clarification == "budget"
    assert "budget" not in call.arguments.model_fields_set


@pytest.mark.parametrize(
    "text,value",
    [
        ("2 миллиона рублей", "2000000"),
        ("2000000,50 рублей", "2000000.50"),
        ("500 тысяч рублей", "500000"),
    ],
)
def test_budget_grounding_preserves_correct_values(
    monkeypatch: pytest.MonkeyPatch, text: str, value: str
) -> None:
    transport(monkeypatch, lambda *args, **kwargs: io.BytesIO(response({"budget": value}, text)))
    call = OllamaLLM(LLMSettings()).extract(text, profile(), ())
    assert call.arguments.budget == Decimal(value)


@pytest.mark.parametrize("text", ["Бюджет минус 500 рублей", "Бюджет минус пятьсот рублей"])
def test_negative_correction_equal_to_old_budget_still_clarifies(
    monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    transport(monkeypatch, lambda *args, **kwargs: io.BytesIO(response({"budget": "500"}, text)))
    call = OllamaLLM(LLMSettings()).extract(
        text, profile().model_copy(update={"budget": Decimal(500)}), ()
    )
    assert call.clarification == "budget"


@pytest.mark.parametrize(
    "text,evidence,value",
    [
        ("Бюджет 2000000,50 рублей", "2000000", "2000000"),
        ("Бюджет 2 миллиона рублей", "2", "2"),
        ("Бюджет 1500000 рублей", "500000", "500000"),
    ],
)
def test_partial_literal_quote_cannot_ground_wrong_amount(
    monkeypatch: pytest.MonkeyPatch, text: str, evidence: str, value: str
) -> None:
    transport(
        monkeypatch, lambda *args, **kwargs: io.BytesIO(response({"budget": value}, evidence))
    )
    call = OllamaLLM(LLMSettings()).extract(text, profile(), ())
    assert call.clarification == "budget"


def test_non_numeric_model_budget_with_numeric_evidence_is_safe_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport(monkeypatch, lambda *args, **kwargs: io.BytesIO(response({"budget": "abc"}, "500")))
    with pytest.raises(LLMError, match="llm_invalid_response"):
        OllamaLLM(LLMSettings()).extract("Бюджет 500 рублей", profile(), ())


def test_timeout_cannot_exceed_budget_after_clock_rounding(monkeypatch: pytest.MonkeyPatch) -> None:
    # Adding 120 to this counter then subtracting it yields 120.00000000000001.
    monkeypatch.setattr("app.adapters.llm.time.monotonic", lambda: 8.002)

    def send(request: Any, timeout: float) -> io.BytesIO:
        assert 0 < timeout <= 120
        return io.BytesIO(response({"city": "Казань"}, evidence="Казань"))

    transport(monkeypatch, send)
    assert OllamaLLM(LLMSettings()).extract("Казань", profile(), ()).arguments.city == "Казань"


@pytest.mark.parametrize(
    "arguments",
    [
        {"budget": "-1"},
        {"budget": "NaN"},
        {"city": ""},
        {"city": "x" * 201},
        {"funding": "approved"},
        {"confirmation_state": "confirmed"},
        {"sql": "DROP DATABASE"},
    ],
)
def test_invalid_model_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch, arguments: dict[str, Any]
) -> None:
    transport(monkeypatch, lambda *args, **kwargs: io.BytesIO(response(arguments)))
    with pytest.raises(LLMError, match="llm_invalid_response"):
        OllamaLLM(LLMSettings()).extract("test", profile(), ())


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[]",
        b"{}",
        b"x" * 65537,
        b'{"done":true,"done_reason":"length","message":{"content":"{}"}}',
        b'{"done":true,"done_reason":"stop","message":{"content":"{}","tool_calls":[{}]}}',
    ],
    ids=["non-json", "array", "empty", "oversized", "truncated", "native-tool"],
)
def test_bad_responses(monkeypatch: pytest.MonkeyPatch, raw: bytes) -> None:
    transport(monkeypatch, lambda *args, **kwargs: io.BytesIO(raw))
    with pytest.raises(LLMError) as caught:
        OllamaLLM(LLMSettings()).extract("test", profile(), ())
    assert caught.value.status == 502


@pytest.mark.parametrize(
    "error,status,attempts",
    [
        (TimeoutError("secret"), 504, 1),
        (URLError(TimeoutError()), 504, 1),
        (URLError("secret"), 503, 2),
        (HTTPError("secret", 404, "model missing", Message(), None), 503, 1),
        (HTTPError("secret", 503, "loading", Message(), None), 503, 2),
    ],
)
def test_network_errors_are_bounded_and_sanitized(
    monkeypatch: pytest.MonkeyPatch, error: Exception, status: int, attempts: int
) -> None:
    count = 0

    def fail(*args: Any, **kwargs: Any) -> io.BytesIO:
        nonlocal count
        count += 1
        raise error

    transport(monkeypatch, fail)
    monkeypatch.setattr("app.adapters.llm.time.sleep", lambda _: None)
    with pytest.raises(LLMError) as caught:
        OllamaLLM(LLMSettings()).extract("test", profile(), ())
    assert caught.value.status == status
    assert "secret" not in str(caught.value)
    assert count == attempts


def test_ambiguity_and_tool_whitelist() -> None:
    call = ProfileToolCall.model_validate(
        {
            "tool": "extract_business_profile",
            "arguments": {},
            "clarification": "city",
        }
    )
    assert call.clarification == "city"
    for value in [
        {"tool": "execute_sql", "arguments": {}},
        {
            "tool": "extract_business_profile",
            "arguments": {"city": "Казань"},
            "clarification": "city",
        },
    ]:
        with pytest.raises(ValidationError):
            ProfileToolCall.model_validate(value)


@pytest.mark.parametrize(
    "updates",
    [
        [{"field": "city", "value": "Казань", "evidence": "not in message"}],
        [{"field": "city", "value": "Казань", "evidence": "test"}] * 2,
        [{"field": "sql", "value": "DROP DATABASE", "evidence": "test"}],
    ],
)
def test_invented_evidence_and_duplicate_fields_fail(
    monkeypatch: pytest.MonkeyPatch, updates: list[dict[str, str]]
) -> None:
    raw = json.dumps(
        {
            "done": True,
            "done_reason": "stop",
            "message": {
                "content": json.dumps(
                    {
                        "tool": "extract_business_profile",
                        "extracted": updates,
                        "needs_clarification": None,
                        "intent": "profile",
                    }
                )
            },
        }
    ).encode()
    transport(monkeypatch, lambda *args, **kwargs: io.BytesIO(raw))
    with pytest.raises(LLMError, match="llm_invalid_response"):
        OllamaLLM(LLMSettings()).extract("test", profile(), ())


def test_ambiguous_value_is_never_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = json.dumps(
        {
            "done": True,
            "done_reason": "stop",
            "message": {
                "content": json.dumps(
                    {
                        "tool": "extract_business_profile",
                        "extracted": [{"field": "city", "value": "Казань", "evidence": "test"}],
                        "needs_clarification": "city",
                        "intent": "profile",
                    }
                )
            },
        }
    ).encode()
    transport(monkeypatch, lambda *args, **kwargs: io.BytesIO(raw))
    call = OllamaLLM(LLMSettings()).extract("test", profile(), ())
    assert call.arguments.model_fields_set == set()
    assert call.clarification == "city"


def test_repeated_old_values_cannot_overwrite_new_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = BusinessProfile(conversation_id=uuid4(), city="Казань", budget=Decimal("2000000.00"))
    raw = json.dumps(
        {
            "done": True,
            "done_reason": "stop",
            "message": {
                "content": json.dumps(
                    {
                        "tool": "extract_business_profile",
                        "extracted": [
                            {"field": "city", "value": "Казань", "evidence": "old history"},
                            {"field": "budget", "value": "2000000", "evidence": "old history"},
                            {"field": "funding", "value": "own_funds", "evidence": "сбережения"},
                        ],
                        "needs_clarification": None,
                        "intent": "profile",
                    }
                )
            },
        }
    ).encode()
    transport(monkeypatch, lambda *args, **kwargs: io.BytesIO(raw))
    call = OllamaLLM(LLMSettings()).extract("Свои сбережения", existing, ())
    assert call.arguments.model_fields_set == {"funding"}


def test_explicit_stub_and_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    llm = get_llm()
    assert isinstance(llm, StubLLM)
    assert (
        llm.extract("Хочу кофейню в Казани с бюджетом 2 млн", profile(), ()).arguments.budget
        == 2000000
    )
    monkeypatch.setenv("LLM_PROVIDER", "unknown")
    with pytest.raises(LLMError, match="llm_configuration_error"):
        get_llm()
    for values in [{"base_url": "https://ollama.com"}, {"model": "x:cloud"}, {"timeout": 0}]:
        with pytest.raises(ValidationError):
            LLMSettings.model_validate(values)
