"""U-06 integration on isolated PostGIS; all numeric inputs here are synthetic."""

import os
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.finance.v2.schemas import FinancialCommand
from app.finance.v2.service import FinancialService

from .test_finance_v2 import command, inputs, project, reviewed
from .test_finance_v2 import financial as financial_fixture

financial = financial_fixture

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Isolated PostGIS")


@pytest.mark.parametrize(
    "model,overall,geography",
    [
        ("online_school", "completed", "not_required"),
        ("auto_repair", "partial", "unsupported"),
    ],
)
def test_current_integrated_result_and_bank_boundary(
    financial: TestClient,
    model: str,
    overall: str,
    geography: str,
) -> None:
    headers, url, profile = project(financial, model)
    view = reviewed(financial, headers, url, inputs(financial, headers, url, model))
    saved = financial.post(url + "/calculate", headers=headers, json=command(view))
    assert saved.status_code == 200, saved.text
    snapshot = saved.json()["result"]
    report_url = url.replace("financial-scenarios", "analysis-result")
    result = financial.get(report_url, headers=headers)
    assert result.status_code == 200, result.text
    report = result.json()
    assert report["financial"] == snapshot
    assert report["state"] == overall
    assert {s["id"]: s["state"] for s in report["sections"]}["geography"] == geography
    assert financial.get(report_url).status_code == 401
    other = {"X-Conversation-Token": "x" * 64}
    assert financial.get(report_url, headers=other).status_code == 404
    bank_url = url.replace("financial-scenarios", "bank-products/matches")
    bank = financial.post(
        bank_url,
        headers=headers,
        json={
            "expected_version": view["document"]["profile_revision"],
            "needs": {"needs_settlement_account": True, "registration_status": "not_registered"},
        },
    )
    assert bank.status_code == 200, bank.text
    assert bank.json()["status"] == "evaluated"
    assert bank.json()["credit_decision"] == "not_assessed"
    # The informational adapter must never persist v1 confirmation.
    legacy = profile.replace("/api/v2/", "/api/v1/").replace("industry-profile", "profile")
    assert (
        financial.get(legacy, headers=headers).json()["profile"]["confirmation_state"]
        != "confirmed"
    )
    changed = financial.patch(
        url,
        headers=headers,
        json=command(
            view,
            updates=[
                {
                    "parameter": "marketing",
                    "unit": "RUB/month",
                    "base": "1234",
                    "low": "1234",
                    "high": "1234",
                }
            ],
        ),
    )
    assert changed.status_code == 200, changed.text
    current = financial.get(report_url, headers=headers).json()
    assert current["financial"] is None and current["state"] == "partial"
    historical = financial.get(url + "/results/" + snapshot["id"], headers=headers)
    assert historical.json() == snapshot
    changed_profile = financial.patch(
        profile,
        headers=headers,
        json={
            "expected_version": view["document"]["profile_revision"],
            "updates": [{"field": "budget", "value": "9000000"}],
        },
    )
    assert changed_profile.status_code == 200
    assert financial.get(report_url, headers=headers).json()["state"] == "collecting"
    assert (
        financial.post(
            bank_url,
            headers=headers,
            json={
                "expected_version": changed_profile.json()["profile"]["revision"],
                "needs": {},
            },
        ).status_code
        == 409
    )
    consent = legacy.replace("profile", "consents")
    revision = next(
        c["revision"]
        for c in financial.get(consent, headers=headers).json()["consents"]
        if c["purpose"] == "assistant"
    )
    assert (
        financial.put(
            consent + "/assistant",
            headers=headers,
            json={
                "expected_revision": revision,
                "text_version": "assistant-demo-v1",
                "decision": "withdraw",
            },
        ).status_code
        == 200
    )
    assert financial.get(report_url, headers=headers).status_code == 403


def test_restored_action_cancel_is_idempotent_and_fences_old_worker(
    financial: TestClient,
    migrated_database: tuple[Engine, UUID],
) -> None:
    engine, _ = migrated_database
    headers, url, _ = project(financial)
    view = financial.get(url, headers=headers).json()
    body = FinancialCommand.model_validate(command(view))
    owner = UUID(url.split("/")[4])
    token = headers["X-Conversation-Token"]
    with Session(engine) as session, session.begin():
        started = FinancialService(session).begin(owner, token, body, "propose")
        assert started is not None
        consent = started[2]
    observed = financial.get(url, headers=headers).json()
    assert observed["operation"]["request_id"] == str(body.request_id)
    assert observed["operation"]["state"] == "running"
    wrong = financial.post(
        url + "/cancel",
        headers={"X-Conversation-Token": "z" * 64},
        json=body.model_dump(mode="json"),
    )
    assert wrong.status_code == 404
    for _ in range(2):
        response = financial.post(
            url + "/cancel", headers=headers, json=body.model_dump(mode="json")
        )
        assert response.status_code == 200, response.text
        assert response.json()["operation"]["state"] == "cancelled"
    with Session(engine) as session, session.begin():
        with pytest.raises(HTTPException) as error:
            FinancialService(session).fence(owner, token, body, "propose", consent)
        assert error.value.status_code == 409
    assert financial.get(url, headers=headers).json()["result"] is None
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.finance.v2.llm import get_assumption_llm
    from app.main import app

    model = SimpleNamespace(propose=AsyncMock(side_effect=AssertionError("Replay must not infer")))
    app.dependency_overrides[get_assumption_llm] = lambda: model
    replay = financial.post(url + "/propose", headers=headers, json=body.model_dump(mode="json"))
    assert replay.status_code == 200 and replay.json()["operation"]["state"] == "cancelled"

    model.propose.assert_not_called()


def test_cancel_stops_actual_async_operation_without_open_transaction(
    financial: TestClient,
    migrated_database: tuple[Engine, UUID],
) -> None:
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    import sqlalchemy as sa

    from app.finance.v2.llm import get_assumption_llm
    from app.finance.v2.schemas import AssumptionProposal
    from app.main import app

    started, stopped = Event(), Event()

    class WaitingModel:
        async def propose(self, *args: object) -> tuple[AssumptionProposal, float]:
            started.set()
            try:
                await asyncio.sleep(30)
                raise AssertionError("Cancelled model must not finish")
            finally:
                stopped.set()

    app.dependency_overrides[get_assumption_llm] = WaitingModel
    headers, url, _ = project(financial)
    view = financial.get(url, headers=headers).json()
    body = command(view)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(financial.post, url + "/propose", headers=headers, json=body)
        assert started.wait(5)
        with migrated_database[0].connect() as connection:
            count = connection.scalar(
                sa.text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                    "AND state='idle in transaction' AND pid<>pg_backend_pid()"
                )
            )
            assert count == 0
        observed = financial.get(url, headers=headers).json()
        assert observed["operation"]["state"] == "running"
        cancelled = financial.post(url + "/cancel", headers=headers, json=body)
        assert cancelled.status_code == 200
        response = pending.result(timeout=5)
        assert response.status_code == 499
        assert response.json()["detail"]["code"] == "financial_operation_cancelled"
        assert stopped.wait(2)
    final = financial.get(url, headers=headers).json()
    assert final["operation"]["state"] == "cancelled" and final["result"] is None
