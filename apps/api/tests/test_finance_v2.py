"""Independent arithmetic fixtures. All values below are scenarios, not market data."""

from datetime import UTC, datetime
from decimal import Decimal, Inexact, Rounded, localcontext

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.finance.v2.engine import calculate
from app.finance.v2.registry import configuration, validate
from app.finance.v2.schemas import FinancialDocument, FinancialInput, Range


def entry(
    value: str | int,
    unit: str,
    low: str | int | None = None,
    high: str | int | None = None,
    assumed: bool = False,
) -> FinancialInput:
    return FinancialInput.model_validate(
        dict(
            base=str(value),
            low=str(value if low is None else low),
            high=str(value if high is None else high),
            unit=unit,
            source=dict(
                origin="synthetic" if assumed else "user_input",
                source_name="Test fixture",
                data_version="test-v1",
                confidence="not_applicable" if assumed else "low",
                limitations=["Explicit artificial scenario, not market data"],
            ),
            epistemic="assumed" if assumed else "user_provided",
            review="confirmed",
            method="user_assumption" if assumed else "user_input",
            basis="Test",
            revision=1,
            created_at=datetime.now(UTC),
        )
    )


def document(model: str = "auto_repair", **overrides: str | int) -> FinancialDocument:
    defaults: dict[str, str | int] = {
        "service_bays": 4,
        "working_days": 25,
        "orders_per_bay": 2,
        "utilization": "0.75",
        "average_order": 10000,
        "materials_per_order": 3000,
        "labor_per_order": 1000,
        "rent": 100000,
        "payroll": 200000,
        "utilities": 20000,
        "marketing": 30000,
        "other_fixed": 50000,
        "students": 20,
        "student_capacity": 30,
        "tuition": 10000,
        "course_months": 3,
        "variable_per_student": 1000,
        "fee_ratio": "0.05",
        "teachers": 60000,
        "platform": 10000,
        "unit_sales": 100,
        "unit_price": 2000,
        "variable_per_unit": 500,
    }
    defaults.update(overrides)
    return FinancialDocument.model_validate(
        dict(
            profile_revision=2,
            profile_config_sha256="fixture",
            model=model,
            revision=1,
            billing_model="monthly" if model == "online_school" else None,
            entries={p.id: entry(defaults[p.id], p.unit) for p in configuration(model).parameters},
        )
    )


def test_auto_independent_orders_margin_capacity_and_three_scenarios() -> None:
    doc = document()
    doc.entries["utilization"] = entry("0.75", "ratio", "0.5", "1", True)
    result = calculate(doc)
    assert result.status == "calculated" and result.contains_assumptions
    assert len(result.scenarios) == 3
    # 4*25*2 = 200 capacity; 100/150/200 orders, margin 6000, fixed 400000.
    for scenario, units, revenue, profit in zip(
        result.scenarios,
        (100, 150, 200),
        (1000000, 1500000, 2000000),
        (200000, 500000, 800000),
        strict=True,
    ):
        assert scenario.units == units
        assert scenario.capacity == 200
        assert scenario.revenue == revenue
        assert scenario.fixed_costs == 400000
        assert scenario.operating_result == profit
        assert scenario.break_even.units == 67
        assert scenario.break_even.status == "calculated"
    assert calculate(doc) == result


@pytest.mark.parametrize(
    "billing,months,revenue,variable,fixed,profit",
    [
        ("monthly", 1, 200000, 30000, 150000, 20000),
        ("subscription", 1, 200000, 30000, 150000, 20000),
        ("course", 3, 200000, 30000, 450000, -280000),
    ],
)
def test_school_periods(
    billing: str, months: int, revenue: int, variable: int, fixed: int, profit: int
) -> None:
    doc = document("online_school")
    doc = doc.model_copy(update={"billing_model": billing})
    scenario = calculate(doc).scenarios[1]
    assert scenario.months == months and scenario.revenue == revenue
    assert scenario.variable_costs == variable and scenario.fixed_costs == fixed
    assert scenario.operating_result == profit
    assert scenario.break_even.status == ("above_capacity" if months == 3 else "calculated")


def test_generic_is_not_coffee_and_partial_unknown_is_not_zero() -> None:
    doc = document("generic", rent=0, payroll=0, utilities=0, marketing=0, other_fixed=50000)
    result = calculate(doc)
    assert result.scenarios[1].operating_result == 100000
    assert result.scenarios[1].capacity is None
    del doc.entries["unit_price"]
    partial = calculate(doc)
    assert partial.status == "partial" and "unit_price" in partial.missing
    assert not partial.scenarios


@pytest.mark.parametrize(
    "price,expected",
    [(4000, "nonpositive_margin"), (0, "nonpositive_margin"), (4001, "above_capacity")],
)
def test_nonpositive_margin_and_infeasible_break_even(price: int, expected: str) -> None:
    base = calculate(document(average_order=price)).scenarios[1]
    assert base.break_even.status == expected
    if expected == "nonpositive_margin":
        assert base.break_even.units is None


def test_zero_volume_and_no_division_by_zero() -> None:
    result = calculate(document(utilization=0)).scenarios[1]
    assert result.units == 0 and result.safety_margin_ratio is None
    assert result.operating_result == -400000


def test_more_sales_with_negative_margin_warns_instead_of_inventing_optimism() -> None:
    doc = document(average_order=3000)
    doc.entries["utilization"] = entry("0.75", "ratio", "0.5", "1")
    result = calculate(doc)
    assert [s.operating_result for s in result.scenarios] == [-500000, -550000, -600000]
    assert result.warnings == ("scenario_labels_not_ordered_by_operating_result",)


def test_capacity_rejects_overflow_in_all_scenarios() -> None:
    doc = document("online_school")
    doc.entries["students"] = entry(20, "students", 10, 31)
    with pytest.raises(HTTPException):
        calculate(doc)


@pytest.mark.parametrize("value", [True, 0.1, "NaN", "Infinity", "-1", "1e1000"])
def test_strict_decimal_domain(value: object) -> None:
    with pytest.raises(ValidationError):
        Range.model_validate(dict(base=value, low=value, high=value))


def test_unit_bounds_review_and_origin() -> None:
    with pytest.raises(HTTPException):
        validate(
            configuration("auto_repair").parameters[0],
            Range(base=Decimal(1), low=Decimal(1), high=Decimal(1)),
            "RUB",
        )
    doc = document()
    doc.entries["rent"] = doc.entries["rent"].model_copy(update={"review": "rejected"})
    assert calculate(doc).status == "partial"
    value = entry(1, "ratio", assumed=True).model_dump()
    value["epistemic"] = "user_provided"
    with pytest.raises(ValidationError):
        FinancialInput.model_validate(value)


def test_independent_rounding_and_ambient_context() -> None:
    doc = document(
        "generic",
        unit_sales=1,
        unit_price="1.015",
        variable_per_unit="0.005",
        rent=0,
        payroll=0,
        utilities=0,
        marketing=0,
        other_fixed=0,
    )
    result = calculate(doc)
    assert result.scenarios[1].operating_result == Decimal("1.01")
    with localcontext() as context:
        context.prec = 6
        context.traps[Inexact] = context.traps[Rounded] = True
        assert calculate(doc) == result


def test_sensitivity_holds_other_inputs_and_does_not_mutate() -> None:
    doc = document()
    before = doc.model_dump_json()
    result = calculate(doc)
    rent = next(s for s in result.sensitivity if s.parameter == "rent" and s.value == 110000)
    assert rent.difference_from_base == -10000
    assert before == doc.model_dump_json()


@pytest.mark.parametrize(
    "change",
    [
        {"parameter": "invented_driver"},
        {"unit": "USD/month"},
        {"base": "1000000000001"},
        {"epistemic": "observed"},
        {"source": "Rosstat"},
        {"basis": "По данным Росстат"},
        {"base": True},
        {"low": "200000"},
        {"formula": "__import__('os')"},
    ],
)
def test_untrusted_proposals_are_rejected(change: dict[str, object]) -> None:
    from app.finance.v2.llm import validate_proposal
    from app.finance.v2.schemas import AssumptionProposal

    doc = document()
    del doc.entries["rent"]
    suggestion = (
        dict(
            parameter="rent",
            unit="RUB/month",
            base="100000",
            low="80000",
            high="120000",
            basis="Исследовательское допущение",
        )
        | change
    )
    with pytest.raises((HTTPException, ValidationError)):
        proposal = AssumptionProposal.model_validate(
            dict(model="auto_repair", assumptions=[suggestion])
        )
        validate_proposal(proposal, doc)


def test_proposal_cannot_replace_confirmed_value_or_other_model() -> None:
    from app.finance.v2.llm import validate_proposal
    from app.finance.v2.schemas import AssumptionProposal

    doc = document()
    proposal = AssumptionProposal.model_validate(
        dict(
            model="auto_repair",
            assumptions=[
                dict(parameter="rent", unit="RUB/month", base="1", low="1", high="1", basis="Test")
            ],
        )
    )
    with pytest.raises(HTTPException):
        validate_proposal(proposal, doc)
    with pytest.raises(HTTPException):
        validate_proposal(proposal.model_copy(update={"model": "generic"}), doc)


def test_school_proposal_cannot_exceed_known_capacity() -> None:
    from app.finance.v2.llm import validate_proposal
    from app.finance.v2.schemas import AssumptionProposal

    doc = document("online_school")
    del doc.entries["students"]
    proposal = AssumptionProposal.model_validate(
        dict(
            model="online_school",
            assumptions=[
                dict(
                    parameter="students",
                    unit="students",
                    base="20",
                    low="10",
                    high="31",
                    basis="Test",
                )
            ],
        )
    )
    with pytest.raises(HTTPException):
        validate_proposal(proposal, doc)


@pytest.mark.parametrize(
    "raw",
    [
        b"null",
        b"[]",
        b"[" * 1500,
        b'{"done":true,"done_reason":"stop","message":null}',
        b'{"done":true,"done_reason":"stop","message":{"content":"not json"}}',
    ],
)
def test_invalid_ollama_envelopes_fail_safely(raw: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    from uuid import uuid4

    from app.adapters.llm import LLMError, LLMSettings, OllamaLLM
    from app.api.schemas import BusinessProfile
    from app.finance.v2.llm import AssumptionLLM
    from app.industry.schemas import UniversalProfile

    backend = OllamaLLM(LLMSettings())

    async def invalid(body: dict[str, object], *, attempts: int = 1) -> bytes:
        assert attempts == 1
        return raw

    monkeypatch.setattr(backend, "achat", invalid)
    legacy = BusinessProfile(conversation_id=uuid4())
    profile = UniversalProfile(
        id=legacy.id, conversation_id=legacy.conversation_id, revision=2, legacy_snapshot=legacy
    )
    doc = document()
    del doc.entries["rent"]
    with pytest.raises(LLMError, match="llm_invalid_response"):
        asyncio.run(AssumptionLLM(backend).propose(profile, doc))
