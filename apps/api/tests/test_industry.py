from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.schemas import BusinessProfile
from app.industry.llm import grounded
from app.industry.registry import FIELDS, INDUSTRIES, definitions, missing, validate_value
from app.industry.schemas import FieldUpdate, IndustryProposal, UniversalProfile
from app.industry.service import IndustryProfiles


def profile() -> UniversalProfile:
    legacy = BusinessProfile(conversation_id=uuid4())
    return UniversalProfile(
        id=legacy.id, conversation_id=legacy.conversation_id, revision=0, legacy_snapshot=legacy
    )


@pytest.mark.parametrize("industry", INDUSTRIES)
def test_config_references(industry: str) -> None:
    config = INDUSTRIES[industry]
    assert set(config.required) <= definitions(industry).keys()
    assert config.version == "u04-v1"
    assert config.finance_adapter is None or industry == "coffee_shop"


@pytest.mark.parametrize(
    "field,raw",
    [
        ("budget", "NaN"),
        ("budget", "-1"),
        ("budget", "1.001"),
        ("budget", True),
        ("physical_premises", "yes"),
        ("funding", "approved"),
    ],
)
def test_invalid_common_values(field: str, raw: object) -> None:
    with pytest.raises(HTTPException):
        validate_value(FIELDS[field], raw)  # type: ignore[arg-type]


def test_decimal_and_industry_units() -> None:
    assert Decimal(str(validate_value(FIELDS["budget"], "1500000"))) == Decimal("1500000")
    assert definitions("auto_repair")["service_bays"].unit == "bays"
    with pytest.raises(HTTPException):
        validate_value(definitions("auto_repair")["service_bays"], "4.5")
    with pytest.raises(ValidationError):
        FieldUpdate.model_validate({"field": "budget", "value": 1.5})


def test_generic_preserves_idea_and_extensions_on_correction() -> None:
    p = profile().model_copy(update={"idea": "Роботизированные теплицы"})
    p = IndustryProfiles.edit(
        p, (FieldUpdate(field="service_bays", value=4),), "auto_repair", "user_edit"
    )
    p = IndustryProfiles.edit(p, (), "generic", "user_edit")
    assert p.idea == "Роботизированные теплицы"
    assert p.extensions["auto_repair"]["service_bays"].value == 4
    assert "city" not in missing(p)
    with pytest.raises(HTTPException):
        IndustryProfiles.edit(p, (FieldUpdate(field="service_bays", value=4),), None, "user_edit")


def test_school_has_no_mandatory_city_or_premises() -> None:
    p = profile().model_copy(update={"industry": "online_school"})
    assert not {"city", "physical_premises"} & set(missing(p))


@pytest.mark.parametrize(
    "document",
    [
        dict(industry="rocket_shop", industry_evidence="теплицы"),
        dict(capabilities=["finance.magic"]),
        dict(updates=[dict(field="budget", value="2000000", evidence="8 млн рублей")]),
        dict(updates=[dict(field="city", value="Казань", evidence="Москва")]),
        dict(updates=[dict(field="physical_premises", value=True, evidence="не нужно помещение")]),
        dict(updates=[dict(field="rent", value="0", evidence="теплицы")]),
    ],
)
def test_ungrounded_or_unsupported_proposal_rejected(document: dict[str, object]) -> None:
    with pytest.raises(HTTPException):
        grounded(
            IndustryProposal.model_validate(document),
            "Москва, 8 млн рублей, теплицы, не нужно помещение",
            profile(),
        )


def test_quote_is_not_truth_and_confirmation_preserves_origin() -> None:
    proposal = IndustryProposal.model_validate(
        dict(
            industry="auto_repair",
            industry_evidence="автосервис",
            resolution="known",
            updates=[dict(field="service_bays", value="4", evidence="четыре поста")],
        )
    )
    grounded(proposal, "автосервис, четыре поста", profile())
    p = IndustryProfiles.edit(profile(), proposal.updates, "auto_repair", "user_message")
    p = IndustryProfiles.confirm_values(p)
    value = p.extensions["auto_repair"]["service_bays"]
    assert value.review == "confirmed"
    assert value.origin == "user_input" and value.epistemic == "user_provided"


def test_partial_extraction_retains_only_independently_grounded_values() -> None:
    proposal = IndustryProposal.model_validate(
        dict(
            industry="coffee_shop",
            industry_evidence="кофейню",
            updates=[
                dict(field="budget", value="2000000", evidence="2 миллиона рублей"),
                dict(field="business_model", value="кофейня", evidence="кофейню"),
            ],
        )
    )
    result = grounded(proposal, "кофейню, 2 миллиона рублей", profile(), allow_partial=True)
    assert [u.field for u in result.updates] == ["budget"]
    assert result.clarification == "business_model"
    with pytest.raises(HTTPException):
        grounded(
            proposal.model_copy(update={"capabilities": ("finance.magic",)}),
            "кофейню, 2 миллиона рублей",
            profile(),
            allow_partial=True,
        )


def test_currency_cannot_be_omitted_from_quote_to_forge_rubles() -> None:
    proposal = IndustryProposal.model_validate(
        dict(updates=[dict(field="budget", value="8000000", evidence="8 миллионов")])
    )
    result = grounded(proposal, "Бюджет 8 миллионов долларов", profile(), allow_partial=True)
    assert not result.updates


def test_coffee_driver_projection_requires_confirmation_and_never_creates_scenarios() -> None:
    from app.industry.finance import coffee_inputs

    p = IndustryProfiles.edit(
        profile(),
        tuple(
            FieldUpdate.model_validate({"field": k, "value": v})
            for k, v in dict(
                city="Казань",
                budget="2000000",
                format="навынос",
                funding="own_funds",
                average_check="400",
                sales_per_day=80,
            ).items()
        ),
        "coffee_shop",
        "user_edit",
    )
    assert coffee_inputs(p) is None
    confirmed = coffee_inputs(IndustryProfiles.confirm_values(p))
    assert confirmed and confirmed.average_check and confirmed.sales_per_day
    assert confirmed.average_check.value == Decimal("400")
    assert confirmed.average_check.source.origin == "user_input"
    assert confirmed.sales_per_day.value == 80
    assert coffee_inputs(p.model_copy(update={"industry": "online_school"})) is None


def test_negative_industry_evidence_cannot_become_positive_selection() -> None:
    proposal = IndustryProposal(industry="coffee_shop", industry_evidence="не кофейню")
    with pytest.raises(HTTPException):
        grounded(proposal, "Хочу не кофейню, а сервис теплиц", profile())


def test_boolean_float_is_not_a_typed_premises_answer() -> None:
    with pytest.raises(ValidationError):
        FieldUpdate.model_validate({"field": "physical_premises", "value": 1.0})


@pytest.mark.parametrize(
    "raw",
    [b"null", b"[]", b"[" * 1500, b'{"done":true,"done_reason":"stop","message":null}'],
    ids=["null", "array", "excessive_nesting", "wrong_message_shape"],
)
def test_invalid_envelopes_fail_safely(raw: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from app.adapters.llm import LLMError, LLMSettings, OllamaLLM
    from app.industry.llm import IndustryLLM

    backend = OllamaLLM(LLMSettings())

    async def invalid(body: dict[str, object], *, attempts: int = 1) -> bytes:
        return raw

    monkeypatch.setattr(backend, "achat", invalid)
    with pytest.raises(LLMError, match="llm_invalid_response"):
        asyncio.run(IndustryLLM(backend).propose("Test idea", profile()))
