"""H-02 stock quotas: isolated databases only; small bounded concurrency probes."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import ReportRecord
from app.limits import config
from app.limits.storage import TABLES

from .test_conversations import create
from .test_leads import action, decision
from .test_leads import setup as lead_setup
from .test_reports import setup as report_setup

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.bank.today", lambda: date(2026, 10, 23))
    monkeypatch.setattr("app.leads.service.today", lambda: date(2026, 10, 23))


def counts(engine: Engine) -> dict[str, int]:
    with Session(engine) as session:
        return {
            key: session.scalar(sa.select(sa.func.count()).select_from(table)) or 0
            for key, table in TABLES.items()
        }


def limits(monkeypatch: pytest.MonkeyPatch, **values: Any) -> None:
    cfg = config.policy().model_dump()
    for key, value in values.items():
        cfg[key] = cfg[key] | value if isinstance(value, dict) else value
    monkeypatch.setattr(config, "POLICY", config.Limits.model_validate(cfg))


def test_parallel_new_sessions_cannot_bypass_global_stock(
    client: TestClient, migrated_database: tuple[Engine, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = migrated_database
    before = counts(engine)
    limits(monkeypatch, global_records={"conversations": before["conversations"] + 1})
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: client.post("/api/v1/conversations"), range(2)))
    assert sorted(r.status_code for r in results) == [201, 429]
    rejected = next(r for r in results if r.status_code == 429)
    assert "retry-after" not in rejected.headers
    assert rejected.json()["detail"]["scope"] == "deployment"
    after = counts(engine)
    assert after == {
        **before,
        "conversations": before["conversations"] + 1,
        "messages": before["messages"] + 1,
        "revisions": before["revisions"] + 1,
    }
    assert client.post("/api/v1/conversations").status_code == 429
    assert counts(engine) == after


def test_profile_message_and_confirmation_share_stock_no_inference_or_writes(
    client: TestClient, migrated_database: tuple[Engine, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = migrated_database
    view, headers, url = create(client)
    before = counts(engine)
    limits(monkeypatch, owner_records={"revisions": 1})

    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Rejected operation started inference")

    monkeypatch.setattr("app.services.conversations.get_llm", never)
    for endpoint, method, body in (
        ("/messages", "post", {"expected_version": 0, "content": "Кофейня в Казани"}),
        ("/profile", "patch", {"expected_version": 0, "patch": {"city": "Казань"}}),
        ("/profile/confirm", "post", {"expected_version": 0}),
    ):
        response = getattr(client, method)(url + endpoint, headers=headers, json=body)
        assert response.status_code == 429, response.text
        assert "retry-after" not in response.headers
    assert counts(engine) == before
    assert client.get(url, headers=headers).json()["version"] == view["version"]
    assert (
        client.patch(url + "/profile", json={"expected_version": 0, "patch": {}}).status_code == 401
    )
    assert (
        client.patch(
            url + "/profile",
            headers={"X-Conversation-Token": "x" * 64},
            json={"expected_version": 0, "patch": {}},
        ).status_code
        == 404
    )


def test_http_and_full_profile_refusals_create_nothing(
    client: TestClient, migrated_database: tuple[Engine, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = migrated_database
    _, headers, url = create(client)
    before = counts(engine)

    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Rejected request invoked Qwen")

    monkeypatch.setattr("app.services.conversations.get_llm", never)
    assert client.post(url + "/messages", headers=headers, content=b"x" * 65537).status_code == 413
    assert (
        client.post(
            url + "/messages", headers=headers, json={"expected_version": 0, "content": "я" * 4001}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            url + "/profile",
            headers=headers,
            json={"expected_version": 0, "patch": {"city": "я" * 201}},
        ).status_code
        == 422
    )
    assert counts(engine) == before


def test_withdrawal_survives_full_storage_and_admission_but_grant_does_not(
    client: TestClient, migrated_database: tuple[Engine, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = migrated_database
    _, headers, url = create(client)
    before = counts(engine)
    limits(
        monkeypatch,
        global_records={"consents": before["consents"], "audit": before["audit"]},
        requests_per_window=1,
        heavy_per_window=1,
    )
    # Consume the process window; consent GET/PUT remains accessible, auth still required.
    client.get("/api/v1/geo/datasets")
    assert client.get("/api/v1/geo/datasets").status_code == 429
    response = decision(client, url, headers, "assistant", "withdraw", revision=1)
    assert response.status_code == 200, response.text
    assert decision(client, url, headers, "assistant", "grant", revision=2).status_code == 429
    assert decision(client, url, headers, "marketing").status_code == 429
    assert client.get(url + "/consents", headers=headers).status_code == 200
    assert client.get(url + "/consents").status_code == 401
    after = counts(engine)
    assert after == {**before, "consents": before["consents"] + 1, "audit": before["audit"] + 1}


def test_draft_quota_rejection_and_receipt_replay_have_no_new_audit(
    client: TestClient, migrated_database: tuple[Engine, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = migrated_database
    url, headers, body = lead_setup(client)
    assert decision(client, url, headers, "demo_lead").status_code == 200
    endpoint = url + "/leads/drafts"
    draft = client.post(endpoint, headers=headers, json=body).json()
    before = counts(engine)
    limits(monkeypatch, owner_records={"drafts": 1})
    assert client.post(endpoint, headers=headers, json=body).status_code == 429
    assert counts(engine) == before
    endpoint += "/" + draft["id"]
    confirmed = client.post(endpoint + "/confirm", headers=headers, json=action(draft))
    assert confirmed.status_code == 200, confirmed.text
    submit = {**action(confirmed.json()), "idempotency_key": str(uuid4())}
    response = client.post(endpoint + "/submit", headers=headers, json=submit)
    assert response.status_code == 200, response.text
    before = counts(engine)
    limits(monkeypatch, global_records={"receipts": before["receipts"], "audit": before["audit"]})
    replay = client.post(endpoint + "/submit", headers=headers, json=submit)
    assert replay.status_code == 200 and replay.json() == response.json()
    assert counts(engine) == before


def test_report_stock_preflight_and_bytes_reject_without_record(
    client: TestClient, migrated_database: tuple[Engine, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = migrated_database
    url, headers, body = report_setup(client)
    limits(monkeypatch, report_storage_bytes=1)
    before = counts(engine)
    response = client.post(url + "/reports", headers=headers, json=body)
    assert response.status_code == 429, response.text
    assert response.json()["detail"]["resource"] == "report_bytes"
    assert counts(engine) == before
    limits(monkeypatch, report_storage_bytes=134217728)
    response = client.post(url + "/reports", headers=headers, json=body)
    assert response.status_code == 201, response.text
    with Session(engine) as session:
        current_bytes = session.scalar(
            sa.select(
                sa.func.sum(
                    sa.func.octet_length(ReportRecord.pdf)
                    + sa.func.octet_length(sa.cast(ReportRecord.snapshot, sa.Text))
                )
            )
        )
    assert current_bytes
    limits(monkeypatch, report_storage_bytes=int(current_bytes))

    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Quota-full request started report calculation")

    monkeypatch.setattr("app.reporting.service.calculate", never)
    before = counts(engine)
    rejected = client.post(url + "/reports", headers=headers, json=body)
    assert rejected.status_code == 429 and counts(engine) == before
    # Existing data remains accessible after operator lowers a quota.
    assert client.get(url + "/reports/" + response.json()["id"], headers=headers).status_code == 200


def test_parallel_reports_respect_one_global_slot(
    client: TestClient, migrated_database: tuple[Engine, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = migrated_database
    requests = [report_setup(client), report_setup(client)]
    before = counts(engine)
    limits(monkeypatch, global_records={"reports": before["reports"] + 1})

    def prepare(values: Any) -> Any:
        url, headers, body = values
        return client.post(url + "/reports", headers=headers, json=body)

    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(prepare, requests))
    assert sorted(r.status_code for r in responses) == [201, 429], [r.text for r in responses]
    assert counts(engine) == {**before, "reports": before["reports"] + 1}


def test_receipt_cap_checked_before_adapter_and_does_not_partially_write(
    client: TestClient, migrated_database: tuple[Engine, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = migrated_database
    url, headers, body = lead_setup(client)
    assert decision(client, url, headers, "demo_lead").status_code == 200
    endpoint = url + "/leads/drafts"
    draft = client.post(endpoint, headers=headers, json=body).json()
    endpoint += "/" + draft["id"]
    assert (
        client.post(endpoint + "/confirm", headers=headers, json=action(draft)).status_code == 200
    )
    before = counts(engine)
    limits(
        monkeypatch,
        global_records={"receipts": max(1, before["receipts"]), "audit": before["audit"]},
    )

    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Rejected request reached mock sender")

    monkeypatch.setattr("app.leads.policy.MockLeadAdapter.submit", never)
    submit = {**action(draft), "idempotency_key": str(uuid4())}
    response = client.post(endpoint + "/submit", headers=headers, json=submit)
    assert response.status_code == 429, response.text
    assert counts(engine) == before
    assert client.get(endpoint, headers=headers).json()["state"] == "confirmed"
