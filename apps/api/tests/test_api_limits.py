"""H-02 bounded probes: no network, GPU, database or load generation."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.conversation_schemas import MessageRequest
from app.api.schemas import BusinessProfile
from app.limits import config, http


@pytest.fixture(autouse=True)
def fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "POLICY", config.Limits())
    monkeypatch.setattr(http, "CONTROLLER", http.Admission())


def probe(
    chunks: list[bytes], *, path: str = "/api/v1/conversations", headers: list[Any] | None = None
) -> tuple[int, dict[str, Any], list[Any], int, int]:
    sent: list[Any] = []
    reads = effects = 0

    async def receive() -> Any:
        nonlocal reads
        index = reads
        reads += 1
        return {"type": "http.request", "body": chunks[index], "more_body": index < len(chunks) - 1}

    async def endpoint(scope: Any, receive: Any, send: Any) -> None:
        nonlocal effects
        assert (await receive())["body"] == b"".join(chunks)
        effects += 1
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async def send(message: Any) -> None:
        sent.append(message)

    asyncio.run(
        http.ApiLimits(endpoint)(
            {"type": "http", "path": path, "method": "POST", "headers": headers or []},
            receive,
            send,
        )
    )
    return sent[0]["status"], json.loads(sent[1]["body"]), sent[0]["headers"], reads, effects


@pytest.mark.parametrize("value", ["К" * 200, "🌍" * 200])
def test_profile_boundary_and_previous_patch_contract(value: str) -> None:
    assert BusinessProfile(conversation_id=uuid4(), city=value).city == value
    with pytest.raises(ValidationError):
        BusinessProfile(conversation_id=uuid4(), city=value + "я")


@pytest.mark.parametrize("field", ["city", "category"])
@pytest.mark.parametrize("value", ["", "  ", "x" * 201, [], {"nested": "x"}])
def test_full_profile_rejects_invalid_text(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        BusinessProfile.model_validate({"conversation_id": uuid4(), field: value})


def test_message_and_version_boundaries() -> None:
    assert MessageRequest(expected_version=2147483647, content="я" * 4000)
    for values in (
        {"expected_version": 2147483648, "content": "hi"},
        {"expected_version": True, "content": "hi"},
        {"expected_version": 0, "content": "я" * 4001},
    ):
        with pytest.raises(ValidationError):
            MessageRequest.model_validate(values)


def test_profile_collection_boundary() -> None:
    values = {"conversation_id": uuid4(), "preferences": {"constraints": ["условие"] * 20}}
    assert len(BusinessProfile.model_validate(values).preferences.constraints) == 20
    values["preferences"] = {"constraints": ["условие"] * 21}
    with pytest.raises(ValidationError):
        BusinessProfile.model_validate(values)


def test_validation_error_redacts_arbitrary_keys_and_values() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    marker = "H02_NOT_A_SECRET"
    with TestClient(app) as client:
        response = client.post("/api/v1/finance/calculate", json={marker: marker})
    assert response.status_code == 422
    assert marker not in response.text
    assert all("input" not in item and "ctx" not in item for item in response.json()["detail"])


@pytest.mark.parametrize("length", [65536, 65537])
@pytest.mark.parametrize("declared", [False, True])
def test_body_boundary_without_side_effects(length: int, declared: bool) -> None:
    body = b"{}" + b" " * (length - 2)
    headers = [(b"content-length", str(length).encode())] if declared else []
    status, _, _, reads, effects = probe([body[:100], body[100:]], headers=headers)
    assert status == (200 if length == 65536 else 413)
    assert effects == int(length == 65536)
    if declared and length > 65536:
        assert reads == 0


def test_understated_length_chunked_and_report_specific_cap() -> None:
    status, _, _, reads, effects = probe(
        [b"{}", b" " * 65535, b"unread"], headers=[(b"content-length", b"2")]
    )
    assert (status, reads, effects) == (413, 2, 0)
    assert probe([b"{}" + b" " * 131070], path="/api/v1/conversations/id/reports")[0] == 200
    assert probe([b"x" * 131073], path="/api/v1/conversations/id/reports")[1] == {
        "detail": {"code": "report_request_too_large"}
    }


@pytest.mark.parametrize("body", [b"[]", b"null", b"{", b'{"x": NaN}', b'{"x": Infinity}'])
def test_bad_json_rejected_before_handler(body: bytes) -> None:
    result = probe([body])
    assert result[0] == 422 and result[-1] == 0


def test_structure_text_collection_nodes_and_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    assert probe([json.dumps({"x": "я" * 4096}).encode()])[0] == 200
    assert probe([json.dumps({"x": "я" * 4097}).encode()])[0] == 422
    assert probe([json.dumps({"x": list(range(128))}).encode()])[0] == 200
    assert probe([json.dumps({"x": list(range(129))}).encode()])[0] == 422
    monkeypatch.setattr(config, "POLICY", config.policy().model_copy(update={"json_nodes": 3}))
    assert probe([b'{"x": [1]}'])[0] == 200
    assert probe([b'{"x": [1,2]}'])[0] == 422
    monkeypatch.setattr(config, "POLICY", config.policy().model_copy(update={"json_depth": 2}))
    assert probe([b'{"x": [[1]]}'])[0] == 422


@pytest.mark.parametrize(
    "raw",
    [
        '{"body_bytes":0}',
        '{"surprise":1}',
        "[]",
        "null",
        "{",
        '{"global_records":{"reports":false}}',
    ],
)
def test_invalid_configuration_fails_closed(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("BA_API_LIMITS_JSON", raw)
    with pytest.raises(RuntimeError, match="Invalid BA_API_LIMITS_JSON"):
        config.load()


def test_config_partial_merge_and_unsupported_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BA_API_LIMITS_JSON", '{"global_records":{"reports":10}}')
    assert config.load().global_records["reports"] == 10
    assert config.load().global_records["messages"] == 20000
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    with pytest.raises(RuntimeError):
        config.load()


def test_rate_shared_between_endpoints_and_only_real_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config,
        "POLICY",
        config.policy().model_copy(
            update={
                "requests_per_window": 1,
                "heavy_per_window": 1,
            }
        ),
    )
    assert probe([b"{}"])[0] == 200
    result = probe([b"{}"], path="/api/v1/finance/calculate")
    assert result[0] == 429 and (b"retry-after", b"60") in result[2]
    assert result[-1] == 0
    now = [0.0]
    control = http.Admission(lambda: now[0])
    control.enter(False)
    control.leave(False)
    now[0] = 61
    control.enter(True)
    control.leave(True)


def test_parallel_admission_is_atomic_and_released(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "POLICY", config.policy().model_copy(update={"active_heavy": 1}))
    control = http.Admission()
    barrier = Barrier(2)

    def attempt() -> bool:
        accepted = False
        try:
            control.enter(True)
            accepted = True
        except http.Rejected as error:
            assert error.status == 429 and error.retry is None
        barrier.wait(timeout=5)
        if accepted:
            control.leave(True)
        return accepted

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(lambda _: attempt(), range(2))) == [False, True]
    assert control.active == control.active_heavy == 0


def test_metadata_and_disconnect_timeout_release(monkeypatch: pytest.MonkeyPatch) -> None:
    assert probe([b"{}"], headers=[(b"x", b"x" * 16384)])[0] == 431
    assert probe([b"{}"], path="/api/v1/" + "x" * 2048)[0] == 414
    assert http.consent_control("/api/v1/conversations/id/consents/demo_lead", "PUT")
    assert not http.consent_control("/api/v1/conversations/id/messages", "POST")
    assert not http.consent_control("/api/v1/conversations/id/consents/demo_lead/submit", "PUT")
    monkeypatch.setattr(
        config, "POLICY", config.policy().model_copy(update={"body_timeout_seconds": 0.01})
    )
    sent = []

    async def stalled() -> Any:
        await asyncio.sleep(0.05)

    async def never(*args: Any) -> None:
        raise AssertionError("Rejected request reached handler")

    async def send(value: Any) -> None:
        sent.append(value)

    asyncio.run(
        http.ApiLimits(never)(
            {"type": "http", "path": "/api/v1/test", "method": "POST", "headers": []}, stalled, send
        )
    )
    assert sent[0]["status"] == 408
    assert http.CONTROLLER.active == 0
