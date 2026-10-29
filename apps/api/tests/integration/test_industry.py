"""Isolated PostGIS; scripted proposals are fixtures, live Qwen is recorded separately."""

import os
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.schemas import BusinessProfile
from app.db.models import BusinessProfileRecord, IndustryProfileRecord
from app.industry.llm import get_industry_llm
from app.industry.schemas import IndustryProposal
from app.main import app

from .test_conversations import create

pytestmark = pytest.mark.skipif(
    os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires isolated PostGIS"
)


@pytest.fixture
def industry(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("BA_INDUSTRY_ENABLED", "1")
    yield client
    app.dependency_overrides.pop(get_industry_llm, None)


def setup(client: TestClient) -> tuple[dict[str, Any], dict[str, str], str]:
    body, headers, _ = create(client)
    return body, headers, f"/api/v2/conversations/{body['id']}/industry-profile"


def edit(
    client: TestClient,
    headers: dict[str, str],
    url: str,
    version: int = 0,
    industry: str = "online_school",
    **values: object,
) -> dict[str, Any]:
    response = client.patch(
        url,
        headers=headers,
        json=dict(
            expected_version=version,
            industry=industry,
            updates=[dict(field=k, value=v) for k, v in values.items()],
        ),
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def test_school_no_map_and_no_fake_finance(industry: TestClient) -> None:
    _, headers, url = setup(industry)
    result = edit(
        industry,
        headers,
        url,
        budget="1500000",
        audience="взрослые",
        format="онлайн",
        payment_model="за курс",
        students=20,
    )
    assert result["plan"]["missing_fields"] == []
    result = industry.post(url + "/confirm", headers=headers, json={"expected_version": 1}).json()
    assert result["plan"]["stages"] == ["partial_result"]
    assert result["plan"]["coverage"] is None
    assert result["plan"]["geo_required"] is False
    assert result["profile"]["confirmed_revision"] == 2
    assert result["conversation"]["profile"]["confirmation_state"] == "draft"
    assert (
        next(c for c in result["plan"]["capabilities"] if c["id"] == "finance.analysis")["status"]
        == "unsupported"
    )
    # Reload and extension edit invalidate confirmation through the same CAS counter.
    assert industry.get(url, headers=headers).json()["profile"]["confirmed_revision"] == 2
    edited = edit(industry, headers, url, 2, students=30)
    assert edited["profile"]["confirmed_revision"] is None


def test_auto_moscow_missing_and_unsupported_geo(industry: TestClient) -> None:
    _, headers, url = setup(industry)
    result = edit(
        industry,
        headers,
        url,
        industry="auto_repair",
        city="Москва",
        budget="8000000",
        specialization="ремонт",
        service_bays=4,
        physical_premises=True,
    )
    assert not result["plan"]["missing_fields"]
    result = industry.post(url + "/confirm", headers=headers, json={"expected_version": 1}).json()
    assert all(a["local_status"] == "missing" for a in result["plan"]["coverage"]["assessments"])
    assert (
        next(c for c in result["plan"]["capabilities"] if c["id"] == "geo.analysis")["status"]
        == "unsupported"
    )
    assert result["profile"]["extensions"]["auto_repair"]["service_bays"]["unit"] == "bays"


def test_coffee_bridge_and_v1_reconciliation(industry: TestClient) -> None:
    body, headers, url = setup(industry)
    result = edit(
        industry,
        headers,
        url,
        industry="coffee_shop",
        city="Казань",
        budget="2000000",
        format="навынос",
        funding="own_funds",
    )
    assert not result["plan"]["missing_fields"]
    result = industry.post(url + "/confirm", headers=headers, json={"expected_version": 1}).json()
    assert result["conversation"]["profile"]["confirmation_state"] == "confirmed"
    v1url = f"/api/v1/conversations/{body['id']}/profile"
    assert (
        industry.patch(
            v1url, headers=headers, json={"expected_version": 2, "patch": {"budget": "3000000"}}
        ).status_code
        == 200
    )
    reloaded = industry.get(url, headers=headers).json()
    assert reloaded["profile"]["values"]["budget"]["value"] == "3000000.00"
    assert reloaded["profile"]["confirmed_revision"] is None


def test_owner_consent_cas_payload_and_forgery(industry: TestClient) -> None:
    body, headers, url = setup(industry)
    _, other, _ = setup(industry)
    assert industry.get(url, headers=other).status_code == 404
    assert (
        industry.patch(
            url, headers=headers, json={"expected_version": 0, "industry": "made_up"}
        ).status_code
        == 422
    )
    assert (
        industry.patch(
            url,
            headers=headers,
            json={
                "expected_version": 0,
                "updates": [{"field": "budget", "value": "1", "unit": "USD"}],
            },
        ).status_code
        == 422
    )
    assert (
        industry.patch(
            url, headers=headers, json={"expected_version": 0, "consent": True}
        ).status_code
        == 422
    )
    assert (
        industry.patch(
            url, headers=headers, json={"expected_version": 0, "schema_version": "v99"}
        ).status_code
        == 422
    )
    edit(industry, headers, url, budget="1500000")
    assert industry.patch(url, headers=headers, json={"expected_version": 0}).status_code == 409
    assert (
        industry.post(url + "/confirm", headers=headers, json={"expected_version": 1}).status_code
        == 409
    )
    state = industry.get(f"/api/v1/conversations/{body['id']}/consents", headers=headers).json()
    consent = next(c for c in state["consents"] if c["purpose"] == "assistant")
    industry.put(
        f"/api/v1/conversations/{body['id']}/consents/assistant",
        headers=headers,
        json={
            "expected_revision": consent["revision"],
            "text_version": consent["text_version"],
            "decision": "withdraw",
        },
    )
    assert industry.get(url, headers=headers).status_code == 403


def test_live_boundary_invalid_proposal_has_safe_fallback(industry: TestClient) -> None:
    class Scripted:
        async def propose(self, *args: object) -> tuple[IndustryProposal, float]:
            return IndustryProposal(industry="coffee_shop", industry_evidence="теплиц"), 1.0

    app.dependency_overrides[get_industry_llm] = lambda: Scripted()
    _, headers, url = setup(industry)
    response = industry.post(
        url + "/messages",
        headers=headers,
        json={"expected_version": 0, "content": "Сервис автономных теплиц"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["extraction"] == "clarification_fallback"
    assert result["profile"]["industry"] == "generic"
    assert result["profile"]["idea"] == "Сервис автономных теплиц"


def test_model_mode_survives_reload_without_false_no_ai_banner(industry: TestClient) -> None:
    class Scripted:
        async def propose(self, *args: object) -> tuple[IndustryProposal, float]:
            return IndustryProposal(), 1.0

    app.dependency_overrides[get_industry_llm] = lambda: Scripted()
    body, headers, url = setup(industry)
    response = industry.post(
        url + "/messages",
        headers=headers,
        json={"expected_version": 0, "content": "Уточнить проект"},
    )
    assert response.status_code == 200
    assert response.json()["conversation"]["extraction_mode"] == "ollama"
    assert industry.get(url, headers=headers).json()["conversation"]["extraction_mode"] == "ollama"
    assert (
        industry.get(f"/api/v1/conversations/{body['id']}", headers=headers).json()[
            "extraction_mode"
        ]
        == "ollama"
    )


def test_v1_conversion_preserves_original_snapshot(
    industry: TestClient, migrated_database: tuple[Engine, UUID]
) -> None:
    body, headers, url = setup(industry)
    v1url = f"/api/v1/conversations/{body['id']}/profile"
    response = industry.patch(
        v1url,
        headers=headers,
        json={
            "expected_version": 0,
            "patch": {
                "category": "сервис теплиц",
                "preferences": {"constraints": ["сохранить"], "preferred_districts": ["центр"]},
            },
        },
    )
    assert response.status_code == 200
    result = industry.get(url, headers=headers).json()
    assert result["profile"]["industry"] == "generic"
    assert result["profile"]["legacy_snapshot"] == result["conversation"]["profile"]
    edit(industry, headers, url, 1, "generic", budget="100")
    engine, _ = migrated_database
    with Session(engine) as session:
        record = session.scalar(
            sa.select(BusinessProfileRecord).where(
                BusinessProfileRecord.conversation_id == UUID(body["id"])
            )
        )
        assert record
        extension = session.get(IndustryProfileRecord, record.id)
        assert extension
        legacy = BusinessProfile.model_validate(extension.document["legacy_snapshot"])
        assert legacy.preferences.constraints == ("сохранить",)


def test_deferred_unknowns_allow_only_partial_confirmation(industry: TestClient) -> None:
    _, headers, url = setup(industry)
    first = industry.get(url, headers=headers).json()
    response = industry.patch(
        url,
        headers=headers,
        json={"expected_version": 0, "defer_fields": first["plan"]["missing_fields"]},
    )
    assert response.status_code == 200
    assert response.json()["plan"]["next_question"] is None
    result = industry.post(url + "/confirm", headers=headers, json={"expected_version": 1}).json()
    assert result["plan"]["stages"] == ["partial_result"]
    assert "budget" not in result["profile"]["values"]
    assert result["conversation"]["profile"]["budget"] is None
    assert result["profile"]["deferred_fields"]


def test_late_model_cannot_publish_after_concurrent_profile_edit(
    industry: TestClient, migrated_database: tuple[Engine, UUID]
) -> None:
    from app.api.conversation_schemas import ProfilePatch
    from app.services.conversations import Conversations

    body, headers, url = setup(industry)
    engine, _ = migrated_database

    class Racing:
        async def propose(self, *args: object) -> tuple[IndustryProposal, float]:
            # H-03 must not retain the snapshot's database connection.
            assert engine.pool.checkedout() == 0  # type: ignore[attr-defined]
            with Session(engine) as session, session.begin():
                Conversations(session).update(
                    UUID(body["id"]),
                    headers["X-Conversation-Token"],
                    0,
                    patch=ProfilePatch.model_validate({"budget": "123"}),
                )
            return IndustryProposal(), 1.0

    app.dependency_overrides[get_industry_llm] = lambda: Racing()
    result = industry.post(
        url + "/messages", headers=headers, json={"expected_version": 0, "content": "Поздний ответ"}
    )
    assert result.status_code == 409, result.text
    current = industry.get(url, headers=headers).json()
    assert current["profile"]["idea"] == ""
    assert current["profile"]["values"]["budget"]["value"] == "123.00"


def test_concurrent_compare_and_swap_and_confirmation_reset(industry: TestClient) -> None:
    from concurrent.futures import ThreadPoolExecutor

    _, headers, url = setup(industry)

    def writer(amount: str) -> int:
        return industry.patch(
            url,
            headers=headers,
            json={"expected_version": 0, "updates": [{"field": "budget", "value": amount}]},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(writer, ("1", "2"))) == [200, 409]


def test_invalid_json_and_forged_method_are_recoverable(industry: TestClient) -> None:
    from app.adapters.llm import LLMError

    class Broken:
        async def propose(self, *args: object) -> tuple[IndustryProposal, float]:
            raise LLMError("llm_invalid_response", 502)

    _, headers, url = setup(industry)
    app.dependency_overrides[get_industry_llm] = lambda: Broken()
    result = industry.post(
        url + "/messages",
        headers=headers,
        json={"expected_version": 0, "content": "Необычный бизнес"},
    )
    assert result.status_code == 200
    assert result.json()["extraction"] == "clarification_fallback"
    assert result.json()["profile"]["industry"] == "generic"
    assert (
        industry.patch(
            url, headers=headers, json={"expected_version": 1, "finance_adapter": "magic"}
        ).status_code
        == 422
    )
    assert (
        industry.post(
            url + "/messages", headers=headers, json={"expected_version": 1, "content": "x" * 1601}
        ).status_code
        == 422
    )


def test_configuration_change_requires_explicit_save_and_review(
    industry: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.industry.registry import INDUSTRIES

    _, headers, url = setup(industry)
    edit(
        industry,
        headers,
        url,
        budget="1500000",
        audience="взрослые",
        format="онлайн",
        payment_model="курс",
        students=20,
    )
    confirmed = industry.post(
        url + "/confirm", headers=headers, json={"expected_version": 1}
    ).json()
    old_hash = confirmed["profile"]["config_sha256"]
    monkeypatch.setitem(
        INDUSTRIES,
        "online_school",
        INDUSTRIES["online_school"].model_copy(update={"version": "u04-test-revision"}),
    )
    current = industry.get(url, headers=headers).json()
    assert current["profile"]["confirmed_revision"] is None
    assert (
        industry.post(url + "/confirm", headers=headers, json={"expected_version": 2}).status_code
        == 422
    )
    saved = industry.patch(url, headers=headers, json={"expected_version": 2}).json()
    assert saved["profile"]["config_sha256"] != old_hash
    assert saved["profile"]["configuration_snapshot"]["version"] == "u04-test-revision"
