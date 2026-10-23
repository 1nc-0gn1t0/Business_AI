import socket
from datetime import UTC, datetime
from decimal import Decimal
from typing import NoReturn
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.schemas import BusinessProfile
from app.bank.matching import catalogue_view, load_catalogue
from app.leads.policy import LeadError, MockLeadAdapter, check_action, fingerprint
from app.leads.schemas import DraftAction, DraftInput, LeadDraft, LeadFields, LeadPayload


def test_mock_receipt_is_local_and_action_bound_to_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date

    def no_network(*args: object, **kwargs: object) -> NoReturn:
        pytest.fail("A mock lead must never open a network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)

    catalogue = catalogue_view(load_catalogue(), date(2026, 10, 23))
    payload = LeadPayload(
        fields=LeadFields(city="Казань", category="кофейня", budget=Decimal("2000000")),
        products=(catalogue.products[0],),
        catalogue_version=catalogue.version,
        catalogue_fingerprint=catalogue.fingerprint,
        field_origins={"city": "confirmed_profile"},
    )
    now = datetime.now(UTC)
    draft = LeadDraft(
        id=uuid4(),
        revision=1,
        profile_version=2,
        profile_snapshot=BusinessProfile(conversation_id=uuid4()),
        consents=(),
        payload=payload,
        payload_fingerprint=fingerprint(payload, 2),
        state="confirmed",
        created_at=now,
        updated_at=now,
        confirmed_at=now,
    )
    action = DraftAction(
        expected_revision=1, confirmed=True, payload_fingerprint=draft.payload_fingerprint
    )
    check_action(draft, action)
    receipt = MockLeadAdapter().submit(draft, consents=(), created_at=now)
    assert not receipt.sent_to_bank
    assert receipt.status == "demo_created"
    assert receipt.message == "Демонстрационная заявка создана. Данные в ВТБ не отправлены"
    assert "external_reference" not in receipt.model_dump()
    for changed in ({"revision": 2}, {"stale": True}, {"payload_fingerprint": "0" * 64}):
        with pytest.raises(LeadError):
            check_action(draft.model_copy(update=changed), action)
    assert fingerprint(payload, 2) == fingerprint(payload, 2)
    assert fingerprint(payload, 3) != fingerprint(payload, 2)


@pytest.mark.parametrize(
    "fields",
    [
        {"city": "", "category": "кофейня"},
        {"city": "Казань", "category": "кофейня", "budget": "-1"},
        {"city": "Казань", "category": "кофейня", "budget": "NaN"},
        {"city": "Казань", "category": "кофейня", "passport": "forbidden"},
        {"city": "Казань", "category": "кофейня", "funding": "approved_loan"},
    ],
)
def test_payload_validation(fields: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        LeadFields.model_validate(fields)


def test_no_duplicate_products_or_false_confirmation() -> None:
    with pytest.raises(ValidationError):
        DraftInput.model_validate(
            {
                "expected_profile_version": 2,
                "catalogue_fingerprint": "0" * 64,
                "product_ids": ["vtb-rko", "vtb-rko"],
                "fields": {"city": "Казань", "category": "кофейня"},
            }
        )
    with pytest.raises(ValidationError):
        DraftAction.model_validate(
            {"expected_revision": 1, "confirmed": False, "payload_fingerprint": "0" * 64}
        )


@pytest.mark.parametrize("value", [1, "true", None])
def test_confirmation_must_be_explicit_boolean(value: object) -> None:
    with pytest.raises(ValidationError):
        DraftAction.model_validate(
            {"expected_revision": 1, "confirmed": value, "payload_fingerprint": "0" * 64}
        )
