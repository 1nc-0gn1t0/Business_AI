import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from .test_conversations import create

pytestmark = pytest.mark.skipif(
    os.environ.get("BA_RUN_DB_TESTS") != "1", reason="Requires Postgres"
)


@pytest.fixture(autouse=True)
def catalogue_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.bank.today", lambda: date(2026, 10, 23))
    monkeypatch.setattr("app.leads.service.today", lambda: date(2026, 10, 23))


def decision(
    client: TestClient,
    url: str,
    headers: dict[str, str],
    purpose: str,
    action: str = "grant",
    revision: int = 0,
) -> Any:
    versions = {
        "assistant": "assistant-demo-v1",
        "demo_lead": "demo-lead-v1",
        "marketing": "marketing-demo-v1",
    }
    return client.put(
        url + "/consents/" + purpose,
        headers=headers,
        json={
            "expected_revision": revision,
            "text_version": versions[purpose],
            "decision": action,
        },
    )


def setup(client: TestClient) -> tuple[str, dict[str, str], dict[str, Any]]:
    _, headers, url = create(client)
    patch = client.patch(
        url + "/profile",
        headers=headers,
        json={
            "expected_version": 0,
            "patch": {
                "city": "Казань",
                "category": "кофейня",
                "budget": "2000000",
                "funding": "own_funds",
                "preferences": {"format": "навынос"},
            },
        },
    )
    assert patch.status_code == 200, patch.text
    assert (
        client.post(
            url + "/profile/confirm", headers=headers, json={"expected_version": 1}
        ).status_code
        == 200
    )
    catalogue = client.get("/api/v1/bank-products").json()
    body = {
        "expected_profile_version": 2,
        "catalogue_fingerprint": catalogue["fingerprint"],
        "product_ids": ["vtb-rko"],
        "fields": {"city": "Казань", "category": "кофейня", "budget": "2000000"},
    }
    return url, headers, body


def action(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "expected_revision": draft["revision"],
        "confirmed": True,
        "payload_fingerprint": draft["payload_fingerprint"],
    }


def test_demo_lead_full_flow_idempotency_audit_and_isolation(client: TestClient) -> None:
    url, headers, body = setup(client)
    endpoint = url + "/leads/drafts"
    assert client.post(endpoint, headers=headers, json=body).status_code == 403
    assert decision(client, url, headers, "marketing", "decline").status_code == 200
    # Independent finance and geo tools must remain available after marketing refusal.
    assert client.get("/api/v1/geo/datasets").status_code == 200

    def amount(value: str | int) -> dict[str, Any]:
        return {
            "value": value,
            "source": {
                "origin": "synthetic",
                "source_name": "consent regression fixture",
                "data_version": "test-v1",
                "confidence": "not_applicable",
                "limitations": ["Test assumption, not a market fact"],
            },
        }

    profile = client.get(url, headers=headers).json()["profile"]
    finance = {
        "profile": profile,
        "startup": {
            key: amount("10000")
            for key in (
                "equipment",
                "renovation",
                "rent_deposit",
                "initial_inventory",
                "registration",
                "other",
                "working_capital_reserve",
            )
        },
        "monthly_fixed_costs": {
            key: amount("10000") for key in ("rent", "payroll", "utilities", "other")
        },
        "working_days_per_month": amount(30),
        "sensitivity_changes": ["-0.10", "0.10"],
        "scenarios": {
            name: {
                "average_check": amount("300"),
                "sales_per_day": amount(sales),
                "variable_cost_ratio": amount("0.4"),
            }
            for name, sales in (("conservative", 30), ("base", 60), ("optimistic", 90))
        },
    }
    financial = client.post("/api/v1/finance/calculate", json=finance)
    assert financial.status_code == 200, financial.text
    assert decision(client, url, headers, "demo_lead").status_code == 200
    created = client.post(endpoint, headers=headers, json=body)
    assert created.status_code == 201, created.text
    draft = created.json()
    endpoint += "/" + draft["id"]
    _, other_headers, other_url = create(client)
    assert client.get(endpoint, headers=other_headers).status_code == 404
    assert (
        client.get(other_url + "/leads/drafts/" + draft["id"], headers=other_headers).status_code
        == 404
    )
    assert client.get(endpoint).status_code == 401
    submit = {**action(draft), "idempotency_key": str(uuid4())}
    assert (
        client.post(endpoint + "/submit", headers=headers, json=submit).json()["detail"]["code"]
        == "lead_confirmation_required"
    )
    assert (
        client.post(endpoint + "/confirm", headers=headers, json=action(draft)).status_code == 200
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(endpoint + "/submit", headers=headers, json=submit), range(2)
            )
        )
    assert [r.status_code for r in responses] == [200, 200]
    receipt = responses[0].json()
    assert receipt == responses[1].json()
    assert receipt["message"] == "Демонстрационная заявка создана. Данные в ВТБ не отправлены"
    assert receipt["sent_to_bank"] is False
    assert {c["purpose"] for c in receipt["consents"]} == {"assistant", "demo_lead"}
    assert (
        client.post(
            endpoint + "/submit", headers=headers, json={**submit, "idempotency_key": str(uuid4())}
        ).status_code
        == 409
    )
    assert len(client.get(url + "/leads", headers=headers).json()["receipts"]) == 1
    events = client.get(url + "/audit", headers=headers).json()
    assert sum(e["action"] == "demo_submission_created" for e in events) == 1
    assert {"consent_grant", "consent_decline", "draft_created", "draft_confirmed"} <= {
        e["action"] for e in events
    }
    assert client.get(url + "/audit", headers=other_headers).status_code == 404
    assert decision(client, url, headers, "demo_lead", "withdraw", 1).status_code == 200
    assert client.post(endpoint + "/submit", headers=headers, json=submit).status_code == 403
    assert client.get(url + "/leads", headers=headers).json()["receipts"][0] == receipt


def test_edits_versions_revocation_and_reconfirmation(client: TestClient) -> None:
    url, headers, body = setup(client)
    assert decision(client, url, headers, "demo_lead").status_code == 200
    draft = client.post(url + "/leads/drafts", headers=headers, json=body).json()
    endpoint = url + "/leads/drafts/" + draft["id"]
    assert (
        client.post(endpoint + "/confirm", headers=headers, json=action(draft)).status_code == 200
    )
    edited = client.put(
        endpoint,
        headers=headers,
        json={**body, "expected_revision": 1, "fields": {"city": "Казань", "category": "кофейня"}},
    )
    assert edited.status_code == 200
    assert edited.json()["revision"] == 2 and edited.json()["confirmed_at"] is None
    assert edited.json()["payload"]["fields"]["budget"] is None
    assert (
        client.post(endpoint + "/confirm", headers=headers, json=action(draft)).status_code == 409
    )
    assert (
        client.put(endpoint, headers=headers, json={**body, "expected_revision": 1}).status_code
        == 409
    )
    draft = edited.json()
    assert (
        client.patch(
            url + "/profile",
            headers=headers,
            json={"expected_version": 2, "patch": {"budget": "1900000"}},
        ).status_code
        == 200
    )
    assert client.get(endpoint, headers=headers).json()["stale"]
    assert (
        client.post(endpoint + "/confirm", headers=headers, json=action(draft)).status_code == 409
    )
    assert (
        client.post(
            url + "/profile/confirm", headers=headers, json={"expected_version": 3}
        ).status_code
        == 200
    )
    refreshed = client.put(
        endpoint,
        headers=headers,
        json={
            **body,
            "expected_revision": 2,
            "expected_profile_version": 4,
            "fields": {"city": "Казань", "category": "кофейня", "budget": "1800000"},
        },
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["payload"]["field_origins"]["budget"] == "draft_user_input"
    assert (
        client.post(
            endpoint + "/confirm", headers=headers, json=action(refreshed.json())
        ).status_code
        == 200
    )
    assert decision(client, url, headers, "demo_lead", "withdraw", 1).status_code == 200
    assert (
        client.post(
            endpoint + "/submit",
            headers=headers,
            json={**action(refreshed.json()), "idempotency_key": str(uuid4())},
        ).status_code
        == 403
    )
    assert decision(client, url, headers, "demo_lead", revision=1).status_code == 409
    assert decision(client, url, headers, "demo_lead", revision=2).status_code == 200
    assert (
        client.post(endpoint + "/confirm", headers=headers, json=action(refreshed.json())).json()[
            "detail"
        ]["code"]
        == "lead_consent_changed"
    )
    assert decision(client, url, headers, "assistant", "withdraw", 1).status_code == 200
    assert (
        client.post(
            url + "/messages", headers=headers, json={"expected_version": 4, "content": "Привет"}
        ).status_code
        == 403
    )
    assert client.get(url + "/messages", headers=headers).status_code == 200


def test_service_consent_is_required_before_processing(client: TestClient) -> None:
    created = client.post("/api/v1/conversations").json()
    url = "/api/v1/conversations/" + created["id"]
    headers = {"X-Conversation-Token": created["access_token"]}
    response = client.post(
        url + "/messages", headers=headers, json={"expected_version": 0, "content": "Кофейня"}
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "consent_required_assistant"
    assert client.get(url, headers=headers).json()["version"] == 0
    assert decision(client, url, headers, "assistant", "decline").status_code == 200
    assert (
        client.patch(
            url + "/profile",
            headers=headers,
            json={"expected_version": 0, "patch": {"city": "Казань"}},
        ).status_code
        == 403
    )
    assert client.get(url + "/history", headers=headers).status_code == 200


def test_revocation_during_inference_prevents_write(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from threading import Event

    from app.adapters.llm import Mode, ProfileToolCall, Turn
    from app.api.schemas import BusinessProfile

    started, proceed = Event(), Event()

    class SlowLLM:
        mode: Mode = "ollama"

        def extract(
            self, content: str, profile: BusinessProfile, history: tuple[Turn, ...]
        ) -> ProfileToolCall:
            started.set()
            assert proceed.wait(10)
            return ProfileToolCall.model_validate(
                {"tool": "extract_business_profile", "arguments": {"city": "Казань"}}
            )

    monkeypatch.setattr("app.services.conversations.get_llm", SlowLLM)
    _, headers, url = create(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(
            client.post,
            url + "/messages",
            headers=headers,
            json={"expected_version": 0, "content": "В Казани"},
        )
        try:
            assert started.wait(5)
            assert decision(client, url, headers, "assistant", "withdraw", 1).status_code == 200
        finally:
            proceed.set()
        assert pending.result().status_code == 403
    assert client.get(url, headers=headers).json()["version"] == 0
    assert len(client.get(url + "/history", headers=headers).json()) == 1


def test_concurrent_draft_edits_and_expired_products(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    url, headers, body = setup(client)
    assert decision(client, url, headers, "demo_lead").status_code == 200
    draft = client.post(url + "/leads/drafts", headers=headers, json=body).json()
    endpoint = url + "/leads/drafts/" + draft["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.put(
                    endpoint, headers=headers, json={**body, "expected_revision": 1}
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    draft = client.get(endpoint, headers=headers).json()
    assert draft["revision"] == 2 and draft["state"] == "draft"
    assert (
        client.post(endpoint + "/confirm", headers=headers, json=action(draft)).status_code == 200
    )
    monkeypatch.setattr("app.leads.service.today", lambda: date(2026, 12, 1))
    response = client.post(
        endpoint + "/submit",
        headers=headers,
        json={**action(draft), "idempotency_key": str(uuid4())},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lead_product_unavailable"
    assert client.get(url + "/leads", headers=headers).json()["receipts"] == []


def test_products_payload_and_consent_text_cannot_be_forged(client: TestClient) -> None:
    url, headers, body = setup(client)
    assert decision(client, url, headers, "demo_lead").status_code == 200
    assert (
        client.post(
            url + "/leads/drafts", headers=headers, json={**body, "product_ids": ["forged"]}
        ).status_code
        == 409
    )
    assert (
        client.post(
            url + "/leads/drafts", headers=headers, json={**body, "catalogue_fingerprint": "0" * 64}
        ).status_code
        == 409
    )
    assert (
        client.post(
            url + "/leads/drafts",
            headers=headers,
            json={**body, "fields": {**body["fields"], "passport": "forbidden"}},
        ).status_code
        == 422
    )
    assert (
        client.put(
            url + "/consents/demo_lead",
            headers=headers,
            json={"expected_revision": 1, "text_version": "forged", "decision": "grant"},
        ).status_code
        == 409
    )
    # Marketing refusal never gates read-only, explicitly requested product matching.
    assert decision(client, url, headers, "marketing", "decline").status_code == 200
    assert (
        client.post(
            url + "/bank-products/matches", headers=headers, json={"expected_version": 2}
        ).status_code
        == 200
    )
