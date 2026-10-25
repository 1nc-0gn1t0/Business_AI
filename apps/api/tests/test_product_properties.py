"""BA-016 mathematical/state invariants. Seeds are versioned; Hypothesis shrinks failures."""

from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import given, seed, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from test_finance import request
from test_scoring import raw

from app.api.conversation_schemas import ProfilePatch
from app.domain.conversation import apply_patch, confirm, missing_fields
from app.domain.enums import Funding
from app.finance.engine import calculate
from app.finance.schemas import FinanceRequest
from app.geo.ranking_schemas import ScoringConfig
from app.geo.scoring import normalize_values, score_components

pytestmark = pytest.mark.extended


@seed(16001)
@settings(max_examples=300, deadline=None)
@given(
    cents=st.integers(1, 100_000_000),
    sales=st.integers(0, 1_000_000),
    days=st.integers(1, 31),
    ratio=st.integers(0, 999999),
    rent=st.integers(0, 100_000_000),
)
def test_financial_rational_oracle(
    cents: int, sales: int, days: int, ratio: int, rent: int
) -> None:
    data = request().model_dump(mode="json")
    data["scenarios"]["base"]["average_check"]["value"] = str(Decimal(cents) / 100)
    data["scenarios"]["base"]["sales_per_day"]["value"] = sales
    data["scenarios"]["base"]["variable_cost_ratio"]["value"] = str(Decimal(ratio) / 1000000)
    data["working_days_per_month"]["value"] = days
    data["monthly_fixed_costs"]["rent"]["value"] = rent
    inputs = FinanceRequest.model_validate(data)
    result = calculate(inputs)
    assert result == calculate(inputs)
    metrics = result.scenarios[1].metrics
    revenue = Fraction(cents * sales * days, 100)
    variable = revenue * Fraction(ratio, 1000000)
    # Integer half-up oracle, independent of Decimal quantize in the engine.
    rounded_variable = (variable * 100 + Fraction(1, 2)).numerator // (
        variable * 100 + Fraction(1, 2)
    ).denominator
    expected = revenue - Fraction(rounded_variable, 100) - (rent + 220000)
    assert metrics["operating_result"].value == Decimal(expected.numerator) / expected.denominator
    margin = Fraction(cents, 100) * (1 - Fraction(ratio, 1000000)) * days
    be = Fraction(rent + 220000) / margin
    assert metrics["break_even_sales_per_day"].value == -(-be.numerator // be.denominator)
    assert all(metric.origin == "modelled" for metric in metrics.values())
    assert result.request_snapshot.monthly_fixed_costs.rent.source.origin == "synthetic"


@seed(16002)
@settings(max_examples=250, deadline=None)
@given(rent=st.integers(0, 10_000_000), delta=st.integers(1, 10_000_000))
def test_rent_metamorphic_change(rent: int, delta: int) -> None:
    data = request().model_dump(mode="json")
    data["monthly_fixed_costs"]["rent"]["value"] = rent
    before = calculate(FinanceRequest.model_validate(data))
    data["monthly_fixed_costs"]["rent"]["value"] = rent + delta
    after = calculate(FinanceRequest.model_validate(data))
    assert before.request_fingerprint != after.request_fingerprint
    for a, b in zip(before.scenarios, after.scenarios, strict=True):
        assert a.metrics["operating_result"].value - delta == b.metrics["operating_result"].value
        assert a.metrics["monthly_revenue"] == b.metrics["monthly_revenue"]


@seed(16003)
@settings(max_examples=250, deadline=None)
@given(value=st.integers(max_value=-1))
def test_negative_money_cannot_enter_or_confirm_profile(value: int) -> None:
    with pytest.raises(ValidationError):
        ProfilePatch(budget=Decimal(value))
    profile = request().profile
    invalid = profile.model_copy(
        update={
            "budget": Decimal(value),
            "funding": Funding.OWN_FUNDS,
            "preferences": profile.preferences.model_copy(update={"format": "навынос"}),
        }
    )
    assert missing_fields(invalid) == ("budget",)
    with pytest.raises(ValueError, match="incomplete"):
        confirm(invalid)


@seed(16004)
@settings(max_examples=250, deadline=None)
@given(count=st.integers(0, 1000000), other=st.integers(0, 1000000))
def test_incomplete_coverage_never_contributes(count: int, other: int) -> None:
    metrics = {"full": raw(count), "edge": raw(other, False)}
    components, comparable = score_components(metrics, ScoringConfig())
    assert not comparable
    assert all(
        c.contribution == 0 if c.status == "disabled" else c.contribution is None
        for c in components["edge"]
    )
    assert score_components(dict(reversed(list(metrics.items()))), ScoringConfig()) == (
        components,
        comparable,
    )


@seed(16005)
@settings(max_examples=250, deadline=None)
@given(values=st.lists(st.integers(0, 1000000), min_size=2, max_size=20))
def test_normalization_order_and_scale(values: list[int]) -> None:
    data = [float(v) for v in values]
    normal = normalize_values(data)
    assert normal == normalize_values([value * 2 for value in data])
    for left, right, a, b in zip(values, values[1:], normal, normal[1:]):
        if a is not None and b is not None:
            assert 0 <= a <= 1 and 0 <= b <= 1
            assert (left <= right) == (a <= b)


@seed(16006)
@settings(max_examples=250, deadline=None)
@given(budget=st.integers(0, 10**15), delta=st.integers(1, 10**9))
def test_confirmed_profile_edit_invalidates_confirmation(budget: int, delta: int) -> None:
    profile = request().profile.model_copy(update={"budget": Decimal(budget)})
    changed = apply_patch(profile, ProfilePatch(budget=Decimal(budget + delta)))
    assert changed.confirmation_state == "draft"
    assert changed.budget == budget + delta
    assert apply_patch(profile, ProfilePatch()).confirmation_state == "confirmed"
