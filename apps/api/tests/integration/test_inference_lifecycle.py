"""H-03 controlled concurrency, real PostgreSQL; no working data or external models."""

import asyncio
import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, perf_counter, sleep
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.adapters.llm import LLMSettings, Mode, ProfileToolCall, Turn
from app.api.schemas import BusinessProfile
from app.db.session import get_session, get_session_factory
from app.limits import config, inference
from app.main import app
from app.services.conversations import Conversations

from .test_conversations import create
from .test_leads import decision

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")


class BlockedLLM:
    mode: Mode = "stub"

    def __init__(self) -> None:
        self.settings = LLMSettings()
        self.entered, self.release, self.stopped = Event(), Event(), Event()
        self.calls = self.active = self.maximum = 0

    def extract(
        self, content: str, profile: BusinessProfile, history: tuple[Turn, ...]
    ) -> ProfileToolCall:
        raise AssertionError("API should use cancellable async capability")

    async def aextract(
        self, content: str, profile: BusinessProfile, history: tuple[Turn, ...]
    ) -> ProfileToolCall:
        self.calls += 1
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        self.entered.set()
        try:
            async with asyncio.timeout(8):
                while not self.release.is_set():
                    await asyncio.sleep(0.005)
            return ProfileToolCall.model_validate(
                {
                    "tool": "extract_business_profile",
                    "arguments": {"city": "Казань", "budget": "2000000"},
                }
            )
        finally:
            self.active -= 1
            self.stopped.set()


@pytest.fixture
def narrow(
    migrated_database: tuple[Engine, UUID],
    temporary_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Engine]]:
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    engine = sa.create_engine(
        "postgresql+psycopg://",
        connect_args={"dbname": temporary_database},
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.5,
    )
    factory = sessionmaker(engine, expire_on_commit=False)

    def session() -> Iterator[Session]:
        with factory.begin() as db:
            yield db

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_session_factory] = lambda: factory
    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        app.dependency_overrides.pop(get_session)
        app.dependency_overrides.pop(get_session_factory)
        engine.dispose()


def checked_out(engine: Engine) -> int:
    assert isinstance(engine.pool, QueuePool)
    return engine.pool.checkedout()


def await_queue() -> None:
    deadline = monotonic() + 3
    while not inference.QUEUE.waiters and monotonic() < deadline:
        sleep(0.005)
    assert len(inference.QUEUE.waiters) == 1


def post(client: TestClient, headers: dict[str, str], url: str) -> Any:
    return client.post(
        url + "/messages", headers=headers, json={"expected_version": 0, "content": "В Казани"}
    )


def test_single_connection_returned_and_five_readers_work_during_inference(
    narrow: tuple[TestClient, Engine],
    migrated_database: tuple[Engine, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, engine = narrow
    llm = BlockedLLM()
    monkeypatch.setattr("app.services.dialogue.get_llm", lambda: llm)
    sessions: list[Session] = []
    original_read, original_write = Conversations.message_input, Conversations.update

    def read(service: Conversations, *args: Any, **kw: Any) -> Any:
        sessions.append(service.session)
        return original_read(service, *args, **kw)

    def write(service: Conversations, *args: Any, **kw: Any) -> Any:
        sessions.append(service.session)
        return original_write(service, *args, **kw)

    monkeypatch.setattr(Conversations, "message_input", read)
    monkeypatch.setattr(Conversations, "update", write)
    _, headers, url = create(client)

    def reader(_: int) -> float:
        started = perf_counter()
        result = client.get("/api/v1/geo/datasets")
        assert result.status_code == 200, result.text
        return (perf_counter() - started) * 1000

    with ThreadPoolExecutor(6) as pool:
        pending = pool.submit(post, client, headers, url)
        try:
            assert llm.entered.wait(3)
            assert checked_out(engine) == 0
            assert not sessions[0].in_transaction()
            with migrated_database[0].connect() as inspector:
                states: dict[str, int] = dict(
                    inspector.execute(
                        sa.text(
                            "SELECT state,count(*) FROM pg_stat_activity "
                            "WHERE datname=current_database() "
                            "AND pid<>pg_backend_pid() GROUP BY state"
                        )
                    ).all()
                )
            assert states.get("idle in transaction", 0) == 0
            times = list(pool.map(reader, range(5)))
            assert checked_out(engine) == 0
        finally:
            llm.release.set()
        assert pending.result(5).status_code == 200
    assert sessions[0] is not sessions[1]
    assert all(not session.in_transaction() for session in sessions)
    print(
        json.dumps(
            {
                "h03": "pool-one",
                "pg_states_during_inference": states,
                "checked_out": 0,
                "pool_size": 1,
                "readers": 5,
                "reader_ms": [round(t, 2) for t in times],
                "distinct_sessions": True,
            }
        )
    )


@pytest.mark.parametrize("change", [{"city": "Самара"}, {"budget": "3000000"}])
def test_concurrent_profile_change_wins(
    narrow: tuple[TestClient, Engine],
    monkeypatch: pytest.MonkeyPatch,
    change: dict[str, str],
) -> None:
    client, engine = narrow
    llm = BlockedLLM()
    monkeypatch.setattr("app.services.dialogue.get_llm", lambda: llm)
    _, headers, url = create(client)
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(post, client, headers, url)
        try:
            assert llm.entered.wait(3)
            edit = client.patch(
                url + "/profile", headers=headers, json={"expected_version": 0, "patch": change}
            )
            assert edit.status_code == 200, edit.text
        finally:
            llm.release.set()
        assert pending.result(5).status_code == 409
    assert client.get(url, headers=headers).json() == edit.json()
    assert len(client.get(url + "/messages", headers=headers).json()) == 2
    assert checked_out(engine) == 0


@pytest.mark.parametrize("regrant", [False, True])
def test_consent_revocation_and_regrant_invalidate_snapshot(
    narrow: tuple[TestClient, Engine],
    monkeypatch: pytest.MonkeyPatch,
    regrant: bool,
) -> None:
    client, engine = narrow
    llm = BlockedLLM()
    monkeypatch.setattr("app.services.dialogue.get_llm", lambda: llm)
    before, headers, url = create(client)
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(post, client, headers, url)
        try:
            assert llm.entered.wait(3)
            assert decision(client, url, headers, "assistant", "withdraw", 1).status_code == 200
            if regrant:
                assert decision(client, url, headers, "assistant", "grant", 2).status_code == 200
        finally:
            llm.release.set()
        response = pending.result(5)
        assert response.status_code == (409 if regrant else 403), response.text
    assert client.get(url, headers=headers).json()["profile"] == before["profile"]
    assert len(client.get(url + "/messages", headers=headers).json()) == 1
    assert checked_out(engine) == 0


@pytest.mark.parametrize("same_owner", [False, True])
def test_two_messages_fifo_overflow_and_cas(
    narrow: tuple[TestClient, Engine],
    monkeypatch: pytest.MonkeyPatch,
    same_owner: bool,
) -> None:
    client, engine = narrow
    llm = BlockedLLM()
    monkeypatch.setattr("app.services.dialogue.get_llm", lambda: llm)
    _, first_headers, first = create(client)
    _, other_headers, other = create(client)
    _, rejected_headers, rejected_url = create(client)
    if same_owner:
        other_headers, other = first_headers, first
    with ThreadPoolExecutor(2) as pool:
        active = pool.submit(post, client, first_headers, first)
        try:
            assert llm.entered.wait(3)
            queued = pool.submit(post, client, other_headers, other)
            await_queue()
            assert checked_out(engine) == 0
            overflow = post(client, rejected_headers, rejected_url)
            assert (
                overflow.status_code == 429
                and overflow.json()["detail"]["code"] == "llm_queue_full"
            )
            assert "retry-after" not in overflow.headers
            assert client.get(rejected_url, headers=rejected_headers).json()["version"] == 0
        finally:
            llm.release.set()
        statuses = sorted([active.result(5).status_code, queued.result(5).status_code])
    assert statuses == ([200, 409] if same_owner else [200, 200])
    assert llm.maximum == 1 and llm.calls == 2
    assert not inference.QUEUE.active and checked_out(engine) == 0
    assert len(client.get(first + "/messages", headers=first_headers).json()) == 3


def test_queue_wait_timeout_does_not_start_model_and_retry_succeeds(
    narrow: tuple[TestClient, Engine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, engine = narrow
    llm = BlockedLLM()
    monkeypatch.setattr("app.services.dialogue.get_llm", lambda: llm)
    monkeypatch.setattr(
        config, "POLICY", config.policy().model_copy(update={"inference_wait_seconds": 0.05})
    )
    _, headers, url = create(client)
    _, other_headers, other = create(client)
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(post, client, headers, url)
        try:
            assert llm.entered.wait(3)
            started = perf_counter()
            timed = post(client, other_headers, other)
            elapsed = perf_counter() - started
            assert (
                timed.status_code == 429 and timed.json()["detail"]["code"] == "llm_queue_timeout"
            )
            assert llm.calls == 1 and checked_out(engine) == 0
        finally:
            llm.release.set()
        assert pending.result(5).status_code == 200
    assert post(client, other_headers, other).status_code == 200
    print(
        json.dumps(
            {
                "h03": "queue-timeout",
                "configured_seconds": 0.05,
                "elapsed_seconds": round(elapsed, 4),
            }
        )
    )


def test_database_failure_after_inference_rolls_back_and_releases_slot(
    narrow: tuple[TestClient, Engine],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, engine = narrow
    llm = BlockedLLM()
    llm.release.set()
    monkeypatch.setattr("app.services.dialogue.get_llm", lambda: llm)
    before, headers, url = create(client)
    original = Conversations.update

    def fail(service: Conversations, *args: Any, **kw: Any) -> Any:
        original(service, *args, **kw)  # SQL was flushed successfully
        raise SQLAlchemyError("H03_SYNTHETIC_PRIVATE_DB_DETAIL")

    with monkeypatch.context() as fault:
        fault.setattr(Conversations, "update", fail)
        response = post(client, headers, url)
    assert (
        response.status_code == 503 and response.json()["detail"]["code"] == "database_unavailable"
    )
    assert "H03_SYNTHETIC_PRIVATE_DB_DETAIL" not in response.text + caplog.text
    assert client.get(url, headers=headers).json()["profile"] == before["profile"]
    assert len(client.get(url + "/messages", headers=headers).json()) == 1
    assert checked_out(engine) == 0 and not inference.QUEUE.active
    assert post(client, headers, url).status_code == 200


@pytest.mark.parametrize("queued", [False, True])
def test_http_disconnect_cancels_active_or_queued_without_writes(
    narrow: tuple[TestClient, Engine],
    monkeypatch: pytest.MonkeyPatch,
    queued: bool,
) -> None:
    client, engine = narrow
    llm = BlockedLLM()
    monkeypatch.setattr("app.services.dialogue.get_llm", lambda: llm)
    _, headers, url = create(client)
    _, second_headers, second = create(client)

    async def scenario() -> None:
        gate = inference.InferenceQueue()
        monkeypatch.setattr(inference, "QUEUE", gate)

        def request(
            path: str, credential: dict[str, str], gone: asyncio.Event
        ) -> tuple[Any, list[Any]]:
            sent: list[Any] = []
            read = False

            async def receive() -> Any:
                nonlocal read
                if not read:
                    read = True
                    return {
                        "type": "http.request",
                        "body": b'{"expected_version":0,"content":"hello"}',
                        "more_body": False,
                    }
                await gone.wait()
                return {"type": "http.disconnect"}

            async def send(message: Any) -> None:
                sent.append(message)

            scope = {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": path + "/messages",
                "root_path": "",
                "query_string": b"",
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"x-conversation-token", credential["X-Conversation-Token"].encode()),
                ],
                "server": ("test", 80),
                "client": ("test", 123),
            }
            return asyncio.create_task(app(scope, receive, send)), sent

        gone = asyncio.Event()
        active, sent = request(url, headers, gone)
        assert await asyncio.to_thread(llm.entered.wait, 3)
        if queued:
            other_gone = asyncio.Event()
            waiter, waiter_sent = request(second, second_headers, other_gone)
            async with asyncio.timeout(3):
                while not gate.waiters:
                    await asyncio.sleep(0.005)
            other_gone.set()
            await asyncio.wait_for(waiter, 2)
            assert waiter_sent[0]["status"] == 499 and not gate.waiters
            assert llm.calls == 1
        gone.set()
        await asyncio.wait_for(active, 2)
        assert sent[0]["status"] == 499
        assert llm.stopped.is_set() and not gate.active and checked_out(engine) == 0

    asyncio.run(scenario())
    for path, credential in ((url, headers), (second, second_headers)):
        assert client.get(path, headers=credential).json()["version"] == 0
        assert len(client.get(path + "/messages", headers=credential).json()) == 1


def test_inference_deadline_then_repeat_same_version(
    narrow: tuple[TestClient, Engine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, engine = narrow
    llm = BlockedLLM()
    llm.settings = LLMSettings(timeout=1)
    monkeypatch.setattr("app.services.dialogue.get_llm", lambda: llm)
    _, headers, url = create(client)
    response = post(client, headers, url)
    assert response.status_code == 504 and response.json()["detail"]["code"] == "llm_timeout"
    assert not inference.QUEUE.active and llm.stopped.is_set() and checked_out(engine) == 0
    assert client.get(url, headers=headers).json()["version"] == 0
    llm.release.set()
    assert post(client, headers, url).status_code == 200
