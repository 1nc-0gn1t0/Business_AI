"""BA-016 pairwise input matrix; no claim of market coverage for unknown industries."""

from decimal import Decimal
from itertools import product
from uuid import UUID

import pytest
from pydantic import ValidationError
from test_finance import request

from app.api.conversation_schemas import MessageRequest, ProfilePatch
from app.domain.conversation import apply_patch, confirm
from app.finance.engine import calculate
from app.finance.schemas import FinanceRequest
from app.geo.ranking_schemas import ScoringConfig
from app.geo.scoring import resolve_policy

pytestmark = pytest.mark.extended

BUSINESSES = (
    "кофейня",
    "пекарня",
    "ресторан",
    "продуктовый магазин",
    "барбершоп",
    "салон красоты",
    "цветочный магазин",
    "автосервис",
    "пункт выдачи заказов",
    "магазин одежды",
    "онлайн-магазин",
    "производство мебели",
)
CITIES = ("Казань", "Самара", "Москва", "Санкт-Петербург", "Иннополис", "Несуществующеград")
BUDGETS = (None, "0", "100000", "500000.01", "2000000", "10000000")
PAIRS = [
    (b, c, BUDGETS[(i + j) % 6]) for i, b in enumerate(BUSINESSES) for j, c in enumerate(CITIES)
]


@pytest.mark.parametrize("business,city,budget", PAIRS, ids=[f"PAIR-{i + 1:03}" for i in range(72)])
def test_profile_finance_pairwise(business: str, city: str, budget: str | None) -> None:
    payload = request().model_dump(mode="json")
    payload["profile"].update(
        {
            "category": business,
            "city": city,
            "budget": budget,
            "funding": "own_funds",
            "preferences": {"format": "отдельное помещение"},
        }
    )
    inputs = FinanceRequest.model_validate(payload)
    result = calculate(inputs)
    assert result.request_snapshot.profile.city == city
    assert result.request_snapshot.profile.category == business
    assert result.request_snapshot.profile.budget == (
        Decimal(budget) if budget is not None else None
    )
    assert result.budget.status == (
        "budget_unknown"
        if budget is None
        else "model_budget_shortfall"
        if Decimal(budget) < 1800000
        else "within_model_budget"
    )
    policy = resolve_policy(business, ScoringConfig())
    if business in ("автосервис", "пункт выдачи заказов", "онлайн-магазин", "производство мебели"):
        assert not policy.competitors and not policy.complementary
    # A change of city must invalidate consent to this profile, including uncovered cities.
    changed = apply_patch(inputs.profile, ProfilePatch(city=city + " новый"))
    assert changed.confirmation_state == "draft"
    if budget is not None and Decimal(budget) > 0:
        assert confirm(changed).confirmation_state == "confirmed"
    else:
        with pytest.raises(ValueError, match="incomplete"):
            confirm(changed)
    assert result == calculate(inputs)


@pytest.mark.parametrize(
    "field,value", list(product(("city", "category"), ("", " ", "x" * 201, 42, False, ["Казань"])))
)
def test_profile_text_adversarial(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ProfilePatch.model_validate({field: value})


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "-Infinity", "1.001", "1e30", {}, []])
def test_profile_budget_adversarial(value: object) -> None:
    with pytest.raises(ValidationError):
        ProfilePatch.model_validate({"budget": value})


@pytest.mark.parametrize("text", ["", " ", "a" * 4001])
def test_message_resource_limits(text: str) -> None:
    with pytest.raises(ValidationError):
        MessageRequest(content=text, expected_version=0)


def test_matrix_has_all_declared_pair_projections() -> None:
    assert {(b, c) for b, c, _ in PAIRS} == set(product(BUSINESSES, CITIES))
    assert {(b, n) for b, _, n in PAIRS} == set(product(BUSINESSES, BUDGETS))
    assert {(c, n) for _, c, n in PAIRS} == set(product(CITIES, BUDGETS))
    assert UUID(str(request().profile.conversation_id))
