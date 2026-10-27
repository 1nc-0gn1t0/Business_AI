from datetime import date, timedelta
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.conversation_schemas import ConversationView
from app.api.conversations import get_service
from app.api.schemas import BusinessProfile
from app.bank.matching import catalogue_view, load_catalogue, match
from app.bank.schemas import BankingNeeds, Catalogue
from app.main import app
from app.services.conversations import Conversations

AS_OF = date(2026, 10, 23)
ID = "00000000-0000-0000-0000-000000000011"


def profile(**patch: object) -> BusinessProfile:
    return BusinessProfile.model_validate(
        {
            "id": ID,
            "conversation_id": ID,
            "city": "Казань",
            "category": "кофейня",
            "budget": "2000000",
            "funding": "own_funds",
            "preferences": {"format": "навынос"},
            "confirmation_state": "confirmed",
            **patch,
        }
    )


def verified() -> Catalogue:
    data = load_catalogue().model_dump(mode="json")
    for source in data["sources"]:
        source.update(
            verification="verified", last_verified_at=AS_OF.isoformat(), content_sha256="a" * 64
        )
    for product in data["products"]:
        product.update(mode="public_reference", status="published")
    return Catalogue.model_validate(data)


def needs() -> BankingNeeds:
    return BankingNeeds(
        registration_status="ip",
        launch_stage="preparing",
        sales_channel="offline",
        needs_settlement_account=True,
        needs_registration_help=False,
        accepts_card_payments=True,
        needs_expense_card=True,
        financing_interest=False,
    )


def test_packaged_catalogue_is_only_demo_not_current_offers() -> None:
    result = match(profile(), 3, needs(), catalogue_view(load_catalogue(), AS_OF))
    assert result.recommended_ids == ()
    assert set(result.demonstration_ids) == {
        "vtb-rko",
        "vtb-merchant-acquiring",
        "vtb-business-card",
    }
    assert all(e.availability == "demonstration_only" for e in result.catalogue.products)
    assert all(s.last_verified_at is None for p in result.catalogue.products for s in p.sources)


def test_verified_relevance_is_not_approval_and_has_evidence() -> None:
    result = match(profile(), 3, needs(), catalogue_view(verified(), AS_OF))
    assert set(result.recommended_ids) == {"vtb-rko", "vtb-merchant-acquiring", "vtb-business-card"}
    assert result.credit_decision == "not_assessed"
    online = next(d for d in result.decisions if d.entry.product.id == "vtb-internet-acquiring")
    assert online.status == "not_matched"
    assert online.reasons == (
        "Условие потребности не выполнено: Онлайн-продажи или совмещённый канал.",
    )
    for decision in result.decisions:
        assert decision.reasons and decision.evaluations and decision.entry.sources
        assert decision.entry.product.unknown_conditions
        for evaluation in decision.evaluations:
            assert evaluation.rule.origin == "application_policy"
            assert evaluation.rule.purpose == "relevance_only_not_bank_eligibility"


def test_unknown_needs_do_not_match_even_a_coffee_profile() -> None:
    result = match(profile(), 3, BankingNeeds(), catalogue_view(verified(), AS_OF))
    assert result.recommended_ids == () and result.missing_fields
    assert all(d.status == "needs_clarification" for d in result.decisions)


def test_registration_before_launch_and_online_payment_channel() -> None:
    context = needs().model_copy(
        update={"registration_status": "not_registered", "needs_registration_help": True}
    )
    result = match(profile(), 3, context, catalogue_view(verified(), AS_OF))
    assert result.recommended_ids == ("vtb-registration",)
    online = needs().model_copy(update={"sales_channel": "online"})
    result = match(profile(), 3, online, catalogue_view(verified(), AS_OF))
    assert "vtb-internet-acquiring" in result.recommended_ids
    assert "vtb-merchant-acquiring" not in result.recommended_ids


def test_funding_interest_uses_explicit_profile_but_never_assesses_credit() -> None:
    context = BankingNeeds()
    result = match(profile(funding="loan"), 3, context, catalogue_view(verified(), AS_OF))
    decision = next(
        d for d in result.decisions if d.entry.product.id == "vtb-financing-information"
    )
    assert decision.status == "information_only"
    assert decision.evaluations[0].input_path == "profile.funding"
    assert decision.evaluations[0].actual_value == "loan"
    assert decision.evaluations[0].evaluated_value is True
    context = context.model_copy(update={"financing_interest": False})
    changed = match(profile(funding="loan"), 3, context, catalogue_view(verified(), AS_OF))
    assert "vtb-financing-information" not in changed.recommended_ids
    assert changed.request_fingerprint != result.request_fingerprint
    assert changed.credit_decision == "not_assessed"


@pytest.mark.parametrize("days,allowed", [(30, True), (31, False), (-1, False)])
def test_review_freshness_and_future_dates(days: int, allowed: bool) -> None:
    view = catalogue_view(verified(), AS_OF + timedelta(days=days))
    assert all((p.availability != "blocked") is allowed for p in view.products)
    result = match(profile(), 3, needs(), view)
    assert bool(result.recommended_ids) is allowed


@pytest.mark.parametrize("status", ["unconfirmed", "unavailable", "retired"])
def test_inactive_products_are_not_recommended(status: str) -> None:
    data = verified().model_dump(mode="json")
    for product in data["products"]:
        product["status"] = status
    result = match(profile(), 3, needs(), catalogue_view(Catalogue.model_validate(data), AS_OF))
    assert result.recommended_ids == () and result.demonstration_ids == ()
    assert result.status == "catalogue_unavailable"


@pytest.mark.parametrize("verification", ["cached_only", "unavailable"])
def test_unverified_or_unavailable_evidence_blocks_public_products(verification: str) -> None:
    data = verified().model_dump(mode="json")
    for source in data["sources"]:
        source["verification"] = verification
    result = match(profile(), 3, needs(), catalogue_view(Catalogue.model_validate(data), AS_OF))
    assert result.recommended_ids == ()


def test_determinism_order_and_no_budget_or_osm_risk_scoring() -> None:
    view = catalogue_view(verified(), AS_OF)
    original = match(profile(), 3, needs(), view)
    assert original == match(profile(), 3, needs(), view)
    reversed_catalogue = verified().model_copy(
        update={"products": tuple(reversed(verified().products))}
    )
    assert (
        original.decisions
        == match(profile(), 3, needs(), catalogue_view(reversed_catalogue, AS_OF)).decisions
    )
    changed = match(profile(city="Москва", category="пекарня", budget="1"), 4, needs(), view)
    assert original.recommended_ids == changed.recommended_ids
    assert original.request_fingerprint != changed.request_fingerprint


def test_draft_profile_and_empty_catalogue_are_explicit() -> None:
    view = catalogue_view(verified(), AS_OF)
    result = match(profile(confirmation_state="draft"), 1, needs(), view)
    assert result.status == "needs_confirmation" and not result.decisions
    empty = verified().model_copy(update={"products": ()})
    assert (
        match(profile(), 1, needs(), catalogue_view(empty, AS_OF)).status == "catalogue_unavailable"
    )


@pytest.mark.parametrize(
    "body",
    [
        {"accepts_card_payments": "yes"},
        {"financing_interest": 1},
        {"registration_status": "unknown"},
        {"credit_score": 100},
        {"sales_channel": ["online"]},
    ],
)
def test_needs_strictly_validate(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BankingNeeds.model_validate(body)


def test_catalogue_validates_references_rules_and_evidence() -> None:
    data = verified().model_dump(mode="json")
    data["products"][0]["source_ids"] = ["missing-source"]
    with pytest.raises(ValidationError):
        Catalogue.model_validate(data)
    data = verified().model_dump(mode="json")
    data["products"][0]["rules"][0]["one_of"] = ["invented-value"]
    with pytest.raises(ValidationError):
        Catalogue.model_validate(data)
    data = verified().model_dump(mode="json")
    data["sources"][0]["url"] = "https://attacker.example/"
    with pytest.raises(ValidationError):
        Catalogue.model_validate(data)


def test_api_authorised_read_only_profile_version_and_catalogue_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.bank.today", lambda: AS_OF)
    service = Mock(spec=Conversations)
    service.get.return_value = ConversationView.model_validate(
        {
            "id": ID,
            "version": 3,
            "state": "confirmed",
            "profile": profile(),
            "missing_fields": [],
            "assistant_message": "ok",
            "created_at": "2026-10-23T00:00:00Z",
            "updated_at": "2026-10-23T00:00:00Z",
        }
    )
    app.dependency_overrides[get_service] = lambda: service
    try:
        with TestClient(app) as client:
            catalogue = client.get("/api/v1/bank-products")
            assert catalogue.status_code == 200
            path = f"/api/v1/conversations/{ID}/bank-products/matches"
            body = {
                "expected_version": 3,
                "needs": needs().model_dump(),
                "catalogue_fingerprint": catalogue.json()["fingerprint"],
            }
            assert client.post(path, json=body).status_code == 401
            headers = {"X-Conversation-Token": "x" * 64}
            response = client.post(path, json=body, headers=headers)
            assert response.status_code == 200 and response.json()["recommended_ids"] == []
            service.get.assert_called_with(UUID(ID), "x" * 64)
            body["expected_version"] = 2
            assert (
                client.post(path, json=body, headers=headers).json()["detail"]["code"]
                == "version_conflict"
            )
            body.update(expected_version=3, catalogue_fingerprint="f" * 64)
            assert (
                client.post(path, json=body, headers=headers).json()["detail"]["code"]
                == "bank_catalogue_version_conflict"
            )
            body["needs"] = {"financing_interest": 1}
            assert client.post(path, json=body, headers=headers).status_code == 422
            body["needs"] = {}
            body["as_of"] = "2020-01-01"
            assert client.post(path, json=body, headers=headers).status_code == 422
            body.pop("as_of")
            body["profile"] = {"confirmation_state": "confirmed"}
            assert client.post(path, json=body, headers=headers).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_broken_catalogue_is_sanitised_and_does_not_use_internet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BANK_CATALOGUE_PATH", "private-missing-file.json")
    with TestClient(app) as client:
        response = client.get("/api/v1/bank-products")
    assert response.status_code == 503
    assert response.json()["detail"] == {"code": "bank_catalogue_unavailable"}
    assert response.json()["request_id"] == response.headers["x-request-id"]
