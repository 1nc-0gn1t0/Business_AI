from decimal import Decimal, Inexact, Rounded, localcontext
from fractions import Fraction
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.finance.engine import calculate
from app.finance.schemas import FinanceRequest
from app.main import app


def source(origin: str = "synthetic") -> dict[str, object]:
    return {
        "origin": origin,
        "source_name": "Explicit test assumption",
        "data_version": "test-v1",
        "confidence": "not_applicable",
        "limitations": ["Test only; not market data"],
    }


def amount(value: str | int, origin: str = "synthetic") -> dict[str, object]:
    return {"value": value, "source": source(origin)}


def request() -> FinanceRequest:
    fixed = {
        key: amount(value)
        for key, value in {
            "rent": "80000",
            "payroll": "180000",
            "utilities": "20000",
            "other": "20000",
        }.items()
    }
    return FinanceRequest.model_validate(
        {
            "profile": {
                "conversation_id": str(uuid4()),
                "city": "Казань",
                "category": "кофейня",
                "budget": "2000000",
                "confirmation_state": "confirmed",
            },
            "startup": {
                key: amount(value)
                for key, value in {
                    "equipment": "700000",
                    "renovation": "400000",
                    "rent_deposit": "160000",
                    "initial_inventory": "100000",
                    "registration": "40000",
                    "other": "100000",
                    "working_capital_reserve": "300000",
                }.items()
            },
            "monthly_fixed_costs": fixed,
            "working_days_per_month": amount(30),
            "scenarios": {
                name: {
                    "average_check": amount(check),
                    "sales_per_day": amount(sales),
                    "variable_cost_ratio": amount(ratio),
                }
                for name, check, sales, ratio in (
                    ("conservative", "250", 60, "0.4"),
                    ("base", "300", 100, "0.35"),
                    ("optimistic", "350", 130, "0.32"),
                )
            },
            "sensitivity_changes": ["-0.1", "0.1"],
        }
    )


def test_formulas_three_scenarios_budget_and_negative_result() -> None:
    result = calculate(request())
    assert result.startup.total_initial_funding == Decimal("1800000.00")
    assert result.startup.launch_uses_excluding_reserve == Decimal("1500000.00")
    assert result.budget.status == "within_model_budget"
    assert result.budget.remaining == Decimal("200000.00")
    for scenario, revenue, variable, profit, breakeven in zip(
        result.scenarios,
        (450000, 900000, 1365000),
        (180000, 315000, 436800),
        (-30000, 285000, 628200),
        (67, 52, 43),
        strict=True,
    ):
        assert scenario.metrics["monthly_revenue"].value == revenue
        assert scenario.metrics["monthly_variable_cost"].value == variable
        assert scenario.metrics["operating_result"].value == profit
        assert scenario.metrics["break_even_sales_per_day"].value == breakeven
        assert scenario.metrics["monthly_fixed_cost"].value == 300000
        assert all(m.origin == "modelled" and m.input_paths for m in scenario.metrics.values())


def test_independent_fraction_reference_and_rounding() -> None:
    payload = request().model_dump(mode="json")
    payload["scenarios"]["base"]["average_check"]["value"] = "1.01"
    payload["scenarios"]["base"]["variable_cost_ratio"]["value"] = "0.5"
    payload["scenarios"]["base"]["sales_per_day"]["value"] = 1
    payload["working_days_per_month"]["value"] = 1
    scenario = calculate(FinanceRequest.model_validate(payload)).scenarios[1]
    assert scenario.metrics["contribution_per_sale_exact"].value == Decimal("0.505")
    assert scenario.metrics["contribution_per_sale"].value == Decimal("0.51")
    assert scenario.metrics["monthly_variable_cost"].value == Decimal("0.51")
    assert scenario.metrics["operating_result"].value == Decimal("-299999.50")
    # Rational arithmetic is independent of Decimal and the implementation's rounding helper.
    per_sale = Fraction(101, 100) * Fraction(1, 2)
    needed = Fraction(300000) / per_sale
    expected_ceiling = -(-needed.numerator // needed.denominator)
    assert scenario.metrics["break_even_sales_per_day"].value == expected_ceiling


def test_repeatability_decimal_context_and_zone_independence() -> None:
    inputs = request()
    first = calculate(inputs)
    with localcontext() as context:
        context.prec = 9
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        assert calculate(inputs) == first
    data = inputs.model_dump(mode="json")
    data["profile"]["id"] = str(uuid4())
    assert (
        calculate(FinanceRequest.model_validate(data)).request_fingerprint
        == first.request_fingerprint
    )
    data["selected_zone"] = {
        "dataset_slug": "kazan-centre",
        "data_version": "a" * 64,
        "candidate_id": "b" * 64,
        "ranking_fingerprint": "c" * 64,
    }
    other = calculate(FinanceRequest.model_validate(data))
    assert other.scenarios == first.scenarios
    assert other.budget == first.budget
    assert other.request_fingerprint != first.request_fingerprint


@pytest.mark.parametrize(
    "field,value",
    [
        ("average_check", "0"),
        ("average_check", "-1"),
        ("average_check", "NaN"),
        ("average_check", "1.001"),
        ("average_check", 0.1),
        ("average_check", True),
        ("variable_cost_ratio", "1"),
        ("variable_cost_ratio", "-0.1"),
        ("variable_cost_ratio", "Infinity"),
        ("variable_cost_ratio", "0.1234567"),
        ("sales_per_day", -1),
        ("sales_per_day", "1"),
        ("sales_per_day", True),
    ],
)
def test_invalid_economic_inputs(field: str, value: object) -> None:
    payload = request().model_dump(mode="json")
    payload["scenarios"]["base"][field]["value"] = value
    with pytest.raises(ValidationError):
        FinanceRequest.model_validate(payload)


def test_zero_sales_zero_fixed_and_tiny_positive_margin() -> None:
    data = request().model_dump(mode="json")
    data["scenarios"]["base"]["sales_per_day"]["value"] = 0
    result = calculate(FinanceRequest.model_validate(data))
    assert result.scenarios[1].metrics["operating_result"].value == -300000
    for item in data["monthly_fixed_costs"].values():
        item["value"] = "0"
    scenario = calculate(FinanceRequest.model_validate(data)).scenarios[1]
    assert scenario.metrics["operating_result"].value == 0
    assert scenario.metrics["break_even_sales_per_day"].value == 0
    data["scenarios"]["base"]["average_check"]["value"] = "0.01"
    data["scenarios"]["base"]["variable_cost_ratio"]["value"] = "0.999999"
    data["monthly_fixed_costs"]["rent"]["value"] = "300000"
    tiny = calculate(FinanceRequest.model_validate(data)).scenarios[1]
    assert tiny.metrics["contribution_per_sale"].value == 0
    assert tiny.metrics["contribution_per_sale_exact"].value == Decimal("0.00000001")
    assert tiny.metrics["break_even_sales_per_day"].value == 1000000000000
    assert "positive_exact_margin_below_display_precision" in tiny.warnings


def test_budget_unknown_shortfall_and_source_classification() -> None:
    data = request().model_dump(mode="json")
    data["profile"]["budget"] = "1000000"
    shortage = calculate(FinanceRequest.model_validate(data))
    assert shortage.budget.status == "model_budget_shortfall"
    assert shortage.budget.funding_gap == 800000
    assert shortage.budget.remaining == -800000
    data["profile"]["budget"] = None
    unknown = calculate(FinanceRequest.model_validate(data))
    assert unknown.budget.status == "budget_unknown"
    assert unknown.budget.funding_gap is None and unknown.budget.remaining is None
    assert unknown.budget.budget_origin == "user_input"
    assert unknown.request_snapshot.startup.equipment.source.origin == "synthetic"
    assert "profile_budget_missing" in unknown.warnings


def test_sensitivity_and_overrides_are_recalculations_not_market_data() -> None:
    inputs = request()
    result = calculate(inputs)
    effects = {(s.driver, s.relative_change): s for s in result.sensitivity}
    assert len(effects) == 8
    assert effects[("average_check", Decimal("0.1"))].difference_from_base == 58500
    assert effects[("sales_per_day", Decimal("-0.1"))].difference_from_base == -58500
    assert effects[("rent", Decimal("0.1"))].difference_from_base == -8000
    assert effects[("variable_cost_ratio", Decimal("0.1"))].difference_from_base == -31500
    data = inputs.model_dump(mode="json")
    data["scenarios"]["base"]["fixed_costs"] = data["monthly_fixed_costs"] | {
        "rent": amount("100000")
    }
    changed = calculate(FinanceRequest.model_validate(data))
    assert changed.scenarios[1].metrics["operating_result"].value == 265000
    assert changed.scenarios[0] == result.scenarios[0]
    assert (
        changed.scenarios[1].metrics["monthly_fixed_cost"].input_paths[0]
        == "scenarios.base.fixed_costs.rent"
    )
    data["scenarios"]["base"]["variable_cost_ratio"]["value"] = "0.9"
    data["sensitivity_changes"] = ["1"]
    outside = calculate(FinanceRequest.model_validate(data))
    invalid = next(s for s in outside.sensitivity if s.driver == "variable_cost_ratio")
    assert invalid.status == "outside_domain" and invalid.operating_result is None
    data["scenarios"]["base"]["average_check"]["value"] = "9999999999999999.99"
    maximum = calculate(FinanceRequest.model_validate(data))
    assert (
        next(s for s in maximum.sensitivity if s.driver == "average_check").status
        == "outside_domain"
    )


@pytest.mark.parametrize(
    "path,value",
    [
        (("startup", "equipment", "value"), "-0.01"),
        (("monthly_fixed_costs", "rent", "value"), "-1"),
        (("working_days_per_month", "value"), 0),
        (("working_days_per_month", "value"), 32),
        (("working_days_per_month", "value"), 30.0),
        (("sensitivity_changes",), ["0"]),
        (("sensitivity_changes",), ["0.1", "0.1"]),
        (("sensitivity_changes",), ["-1"]),
        (("sensitivity_changes",), [0.1]),
        (("startup", "equipment", "source", "limitations"), []),
        (("startup", "equipment", "source", "confidence"), "high"),
        (("startup", "equipment", "source", "source_attested"), True),
        (("startup", "equipment", "source", "origin"), "licensed"),
    ],
)
def test_strict_dates_sources_costs_and_settings(path: tuple[str, ...], value: object) -> None:
    data = request().model_dump(mode="json")
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        FinanceRequest.model_validate(data)


def test_documented_fact_requires_evidence_but_is_not_independently_verified() -> None:
    data = request().model_dump(mode="json")
    data["monthly_fixed_costs"]["rent"]["source"] = source("licensed") | {
        "source_attested": True,
        "evidence_ref": "test-contract:rent-1",
        "observed_at": "2026-10-23T00:00:00Z",
        "confidence": "medium",
    }
    result = calculate(FinanceRequest.model_validate(data))
    assert result.request_snapshot.monthly_fixed_costs.rent.source.source_attested
    assert any("not independently verified" in note for note in result.limitations)


def test_api_roundtrip_recalculation_and_no_database_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_database() -> None:
        raise AssertionError("Financial engine must not query the database")

    monkeypatch.setattr("app.db.session.get_engine", no_database)
    with TestClient(app) as client:
        data = request().model_dump(mode="json")
        response = client.post("/api/v1/finance/calculate", json=data)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["scenarios"][1]["metrics"]["operating_result"]["value"] == "285000.00"
        assert result["scenarios"][1]["metrics"]["break_even_sales_per_day"]["value"] == "52"
        repeated = client.post("/api/v1/finance/calculate", json=data).json()
        assert repeated == result
        data["scenarios"]["base"]["sales_per_day"]["value"] = 90
        updated = client.post("/api/v1/finance/calculate", json=data).json()
        assert updated["scenarios"][1]["metrics"]["operating_result"]["value"] == "226500.00"
        assert updated["request_fingerprint"] != result["request_fingerprint"]
        del data["scenarios"]["base"]["average_check"]
        assert client.post("/api/v1/finance/calculate", json=data).status_code == 422
        data = request().model_dump(mode="json")
        data["selected_zone"] = {"score": 99}
        assert client.post("/api/v1/finance/calculate", json=data).status_code == 422
