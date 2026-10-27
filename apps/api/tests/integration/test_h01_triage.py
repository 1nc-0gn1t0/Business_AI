"""H-01: isolated UUID databases only; no real Ollama or bank HTTP calls."""

import json
import os
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Event
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from app.adapters.llm import Mode, ProfileToolCall, Turn
from app.api.schemas import BusinessProfile
from app.db.models import AuditEventRecord, LeadSubmissionRecord, ProfileRevisionRecord

from .test_conversations import create
from .test_leads import action, decision, setup

pytestmark = pytest.mark.skipif(
    os.environ.get("BA_RUN_DB_TESTS") != "1", reason="Requires Postgres"
)


def test_h01_receipt_and_audit_rollback_after_successful_flush(
    client: TestClient,
    migrated_database: tuple[Engine, UUID],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("app.api.bank.today", lambda: date(2026, 10, 23))
    monkeypatch.setattr("app.leads.service.today", lambda: date(2026, 10, 23))
    url, headers, body = setup(client)
    assert decision(client, url, headers, "demo_lead").status_code == 200
    draft = client.post(url + "/leads/drafts", headers=headers, json=body).json()
    endpoint = url + "/leads/drafts/" + draft["id"]
    assert (
        client.post(endpoint + "/confirm", headers=headers, json=action(draft)).status_code == 200
    )
    before = client.get(url + "/audit", headers=headers).json()
    original = Session.flush
    injected = []

    def fail_after_flush(session: Session, objects: Sequence[Any] | None = None) -> None:
        watched = any(
            isinstance(row, AuditEventRecord) and row.action == "demo_submission_created"
            for row in session.new
        )
        original(session, objects)
        if watched:
            injected.append(True)
            raise SQLAlchemyError("H01_SYNTHETIC_SQL_SECRET")

    with monkeypatch.context() as fault:
        fault.setattr(Session, "flush", fail_after_flush)
        response = client.post(
            endpoint + "/submit",
            headers=headers,
            json={**action(draft), "idempotency_key": str(uuid4())},
        )
    assert injected == [True]
    assert response.status_code == 503
    assert response.json()["detail"] == {"code": "database_unavailable"}
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "H01_SYNTHETIC_SQL_SECRET" not in response.text + caplog.text
    assert client.get(endpoint, headers=headers).json()["state"] == "confirmed"
    assert client.get(url + "/audit", headers=headers).json() == before
    engine, _ = migrated_database
    with Session(engine) as db:
        count = db.scalar(
            sa.select(sa.func.count())
            .select_from(LeadSubmissionRecord)
            .where(LeadSubmissionRecord.conversation_id == UUID(url.rsplit("/", 1)[-1]))
        )
    assert count == 0


def test_h01_profile_and_history_rollback_after_successful_flush(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers, url = create(client)
    before = client.get(url, headers=headers).json()
    history = client.get(url + "/history", headers=headers).json()
    messages = client.get(url + "/messages", headers=headers).json()
    owner = UUID(url.rsplit("/", 1)[-1])
    original = Session.flush
    injected = []

    def fail_after_flush(session: Session, objects: Sequence[Any] | None = None) -> None:
        watched = any(
            isinstance(row, ProfileRevisionRecord) and row.conversation_id == owner
            for row in session.new
        )
        original(session, objects)
        if watched:
            injected.append(True)
            raise SQLAlchemyError("H01_SYNTHETIC_PROFILE_FAILURE")

    with monkeypatch.context() as fault:
        fault.setattr(Session, "flush", fail_after_flush)
        response = client.patch(
            url + "/profile",
            headers=headers,
            json={"expected_version": 0, "patch": {"city": "Казань"}},
        )
    assert injected == [True]
    assert response.status_code == 503
    assert client.get(url, headers=headers).json() == before
    assert client.get(url + "/history", headers=headers).json() == history
    assert client.get(url + "/messages", headers=headers).json() == messages


class RetainedInferenceTransaction(AssertionError):
    pass


def test_h01_no_idle_transaction_during_inference(
    client: TestClient,
    migrated_database: tuple[Engine, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release = Event(), Event()

    class ControlledLLM:
        mode: Mode = "stub"

        def extract(
            self,
            content: str,
            profile: BusinessProfile,
            history: tuple[Turn, ...],
        ) -> ProfileToolCall:
            entered.set()
            assert release.wait(10)
            return ProfileToolCall.model_validate(
                {"tool": "extract_business_profile", "arguments": {"city": "Казань"}}
            )

    monkeypatch.setattr("app.services.dialogue.get_llm", ControlledLLM)
    _, headers, url = create(client)
    engine, _ = migrated_database
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            client.post,
            url + "/messages",
            headers=headers,
            json={"expected_version": 0, "content": "В Казани"},
        )
        try:
            assert entered.wait(5)
            assert isinstance(engine.pool, QueuePool)
            held = engine.pool.checkedout()
            with engine.connect() as inspector:
                idle = inspector.scalar(
                    sa.text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                        "AND state='idle in transaction' AND pid<>pg_backend_pid()"
                    )
                )
            started = perf_counter()
            assert client.get(url, headers=headers).status_code == 200
            print(
                json.dumps(
                    {
                        "probe": "H01-P1-02",
                        "idle_in_transaction": idle,
                        "pool_checked_out_during_inference": held,
                        "concurrent_read_ms": round((perf_counter() - started) * 1000, 2),
                    }
                )
            )
        finally:
            release.set()
        assert pending.result(timeout=10).status_code == 200
    if idle or held:
        raise RetainedInferenceTransaction(f"Observed {idle} idle transaction(s) in isolated DB")
