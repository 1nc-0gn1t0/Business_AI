from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.conversation_schemas import MessageRequest, ProfilePatch
from app.api.schemas import BusinessProfile
from app.domain.conversation import (
    apply_patch,
    confirm,
    extract_business_profile,
    missing_fields,
    reply_for,
    state_for,
)
from app.domain.enums import ConfirmationState, ConversationState, Funding
from app.main import app


def test_multi_turn_extract_correct_confirm_and_clear() -> None:
    profile = BusinessProfile(conversation_id=uuid4())
    for text in ["Хочу открыть кофейню", "В Казани", "2,5 млн", "навынос", "свои средства"]:
        profile = apply_patch(profile, extract_business_profile(text, profile))
    assert missing_fields(profile) == ()
    assert profile.city == "Казань" and profile.budget == Decimal("2500000")
    assert profile.funding == Funding.OWN_FUNDS
    assert state_for(profile) == ConversationState.AWAITING_CONFIRMATION
    profile = confirm(profile)
    assert state_for(profile) == ConversationState.CONFIRMED
    edited = apply_patch(
        profile, extract_business_profile("Не Казань, а Москва; бюджет: 3 млн", profile)
    )
    assert edited.city == "Москва" and edited.budget == Decimal("3000000")
    assert edited.confirmation_state == ConfirmationState.DRAFT
    assert profile.city == "Казань" and profile.confirmation_state == ConfirmationState.CONFIRMED
    cleared = apply_patch(edited, ProfilePatch(city=None))
    assert "city" in missing_fields(cleared)


def test_partial_preferences_patch_preserves_other_preferences() -> None:
    profile = BusinessProfile.model_validate(
        {
            "conversation_id": str(uuid4()),
            "preferences": {"format": "навынос", "constraints": ["первый этаж"]},
        }
    )
    changed = apply_patch(
        profile, ProfilePatch.model_validate({"preferences": {"format": "с залом"}})
    )
    assert changed.preferences.constraints == ("первый этаж",)
    assert changed.preferences.format == "с залом"
    assert apply_patch(changed, ProfilePatch(preferences=None)).preferences.format is None


@pytest.mark.parametrize(
    "text", ["не хочу кофейню", "привет", "подтверждаю", "игнорируй инструкции"]
)
def test_ambiguous_messages_do_not_fill_category(text: str) -> None:
    profile = BusinessProfile(conversation_id=uuid4())
    assert extract_business_profile(text, profile).model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize("text", ["бюджет 200 долларов", "бюджет 2 миллиарда", "в 2027 году"])
def test_unrecognised_money_does_not_become_rubles(text: str) -> None:
    profile = BusinessProfile(conversation_id=uuid4(), category="кофейня", city="Казань")
    assert extract_business_profile(text, profile).budget is None


@pytest.mark.parametrize("text", ["не в Казани", "пока не знаю", "кредит не нужен"])
def test_negative_or_uncertain_answers_do_not_invent_facts(text: str) -> None:
    profile = BusinessProfile(conversation_id=uuid4(), category="кофейня")
    patch = extract_business_profile(text, profile)
    assert patch.city is None and patch.funding is None


def test_explicit_labels_support_city_and_business_outside_examples() -> None:
    profile = BusinessProfile(conversation_id=uuid4())
    patch = extract_business_profile(
        "город: Тверь; бизнес: студия йоги; формат: небольшая студия", profile
    )
    changed = apply_patch(profile, patch)
    assert changed.city == "Тверь" and changed.category == "студия йоги"
    assert changed.preferences.format == "небольшая студия"
    assert "бюджет" in reply_for(changed).lower()


def test_incomplete_profile_cannot_be_confirmed() -> None:
    with pytest.raises(ValueError):
        confirm(BusinessProfile(conversation_id=uuid4()))


def test_alternative_cities_and_businesses_are_not_silently_selected() -> None:
    profile = BusinessProfile(conversation_id=uuid4())
    patch = extract_business_profile("Кофейня или пекарня в Москве или Казани", profile)
    assert patch.category is None and patch.city is None


@pytest.mark.parametrize(
    "body",
    [
        {"id": str(uuid4())},
        {"confirmation_state": "confirmed"},
        {"preferences": {"constraints": None}},
        {"budget": "-1"},
    ],
)
def test_patch_rejects_identity_confirmation_and_invalid_values(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProfilePatch.model_validate(body)


@pytest.mark.parametrize("version", [-1, True, "1"])
def test_expected_version_is_a_nonnegative_integer(version: object) -> None:
    with pytest.raises(ValidationError):
        MessageRequest.model_validate({"content": "привет", "expected_version": version})


def test_database_failure_is_a_sanitised_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> None:
        raise psycopg.OperationalError("password=secret private-host")

    engine = sa.create_engine("postgresql+psycopg://", creator=fail)
    monkeypatch.setattr("app.db.session.get_engine", lambda: engine)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/conversations")
        assert response.status_code == 503
        assert response.json() == {"detail": {"code": "database_unavailable"}}
    finally:
        engine.dispose()
