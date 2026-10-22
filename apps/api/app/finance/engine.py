import hashlib
import json
from decimal import ROUND_CEILING, ROUND_HALF_UP, Context, Decimal, localcontext
from typing import Any

from pydantic import ValidationError

from app.finance.schemas import (
    Driver,
    FinanceRequest,
    FinanceResult,
    FinancialMetric,
    FixedCosts,
    MetricName,
    ScenarioInputs,
    ScenarioName,
    ScenarioResult,
    SensitivityPoint,
)

ALGORITHM_VERSION = "business-finance-decimal-v1"
NAMES: tuple[ScenarioName, ...] = ("conservative", "base", "optimistic")
DRIVERS: tuple[Driver, ...] = ("average_check", "sales_per_day", "rent", "variable_cost_ratio")
FORMULAS: dict[MetricName, str] = {
    "monthly_sales": "sales_per_day * working_days_per_month",
    "monthly_revenue": "average_check * monthly_sales",
    "monthly_variable_cost": "round_half_up(monthly_revenue * variable_cost_ratio, 2)",
    "monthly_fixed_cost": "rent + payroll + utilities + other",
    "contribution_per_sale_exact": "average_check * (1 - variable_cost_ratio)",
    "contribution_per_sale": "round_half_up(contribution_per_sale_exact, 2); display only",
    "monthly_contribution": "monthly_revenue - monthly_variable_cost",
    "operating_result": "monthly_contribution - monthly_fixed_cost",
    "break_even_sales_per_day": "ceil(monthly_fixed_cost / "
    "(contribution_per_sale_exact * working_days_per_month))",
}
LIMITATIONS = (
    "Scenario arithmetic, not a forecast, premises offer or proof of market prices/demand.",
    "Operating result covers the supplied costs only, before unmodelled taxes, depreciation, "
    "interest and other excluded costs; it is not net profit or cash flow.",
    "Startup funding includes deposit, inventory and reserve; not all items are expenses/CAPEX. "
    "Initial inventory is not added again to monthly variable costs as a separate expense.",
    "No cash-flow schedule, payback, loan/repayment model, seasonality or working-capital "
    "turnover is calculated. Reserve does not prove funding adequacy after launch.",
    "Source attestation is supplied by the caller, not independently verified by this service.",
    "Selected zone is an unverified context reference; OSM score has no numerical effect.",
)
MISSING_DATA = (
    "independently_verified_premises_availability_and_cost",
    "observed_future_sales_and_demand",
    "taxes_depreciation_interest_and_principal_schedule",
    "inventory_and_cashflow_timing",
    "seasonality_and_verified_market_forecast",
)


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    return value


def scenario(
    name: ScenarioName,
    inputs: ScenarioInputs,
    fixed: FixedCosts,
    days: int,
) -> ScenarioResult:
    count = inputs.sales_per_day.value * days
    revenue = money(inputs.average_check.value * count)
    variable = money(revenue * inputs.variable_cost_ratio.value)
    fixed_total = sum(
        (fixed.rent.value, fixed.payroll.value, fixed.utilities.value, fixed.other.value),
        Decimal(0),
    )
    per_sale = inputs.average_check.value * (1 - inputs.variable_cost_ratio.value)
    contribution = revenue - variable
    operating = contribution - fixed_total
    breakeven = (fixed_total / (per_sale * days)).to_integral_value(rounding=ROUND_CEILING)
    root = f"scenarios.{name}"
    fixed_root = root + ".fixed_costs" if inputs.fixed_costs is not None else "monthly_fixed_costs"
    volume_paths = (root + ".sales_per_day", "working_days_per_month")
    revenue_paths = (root + ".average_check", *volume_paths)
    margin_paths = (*revenue_paths, root + ".variable_cost_ratio")
    cost_paths = tuple(fixed_root + "." + key for key in ("rent", "payroll", "utilities", "other"))
    values: dict[MetricName, tuple[Decimal, str, tuple[str, ...]]] = {
        "monthly_sales": (Decimal(count), "sales/month", volume_paths),
        "monthly_revenue": (revenue, "RUB", revenue_paths),
        "monthly_variable_cost": (variable, "RUB", margin_paths),
        "monthly_fixed_cost": (money(fixed_total), "RUB", cost_paths),
        "contribution_per_sale_exact": (
            per_sale,
            "RUB/sale",
            (root + ".average_check", root + ".variable_cost_ratio"),
        ),
        "contribution_per_sale": (
            money(per_sale),
            "RUB/sale",
            (root + ".average_check", root + ".variable_cost_ratio"),
        ),
        "monthly_contribution": (contribution, "RUB", margin_paths),
        "operating_result": (money(operating), "RUB", (*margin_paths, *cost_paths)),
        "break_even_sales_per_day": (
            breakeven,
            "sales/day",
            (
                root + ".average_check",
                root + ".variable_cost_ratio",
                "working_days_per_month",
                *cost_paths,
            ),
        ),
    }
    metrics = {
        key: FinancialMetric.model_validate(
            {
                "value": value,
                "unit": unit,
                "algorithm_version": ALGORITHM_VERSION,
                "formula_id": key,
                "input_paths": paths,
            }
        )
        for key, (value, unit, paths) in values.items()
    }
    warnings = []
    if operating < 0:
        warnings.append("negative_operating_result")
    if money(per_sale) == 0:
        warnings.append("positive_exact_margin_below_display_precision")
    if breakeven > 1000000:
        warnings.append("break_even_above_model_input_sales_limit")
    return ScenarioResult(
        name=name,
        inputs=inputs.model_copy(update={"fixed_costs": fixed}),
        metrics=metrics,
        warnings=tuple(warnings),
    )


def sensitivity(request: FinanceRequest, baseline: ScenarioResult) -> tuple[SensitivityPoint, ...]:
    inputs = request.scenarios.base
    fixed = inputs.fixed_costs or request.monthly_fixed_costs
    result = []
    for driver in DRIVERS:
        old = fixed.rent.value if driver == "rent" else getattr(inputs, driver).value
        for change in request.sensitivity_changes:
            value = Decimal(old) * (1 + change)
            value = (
                value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                if driver == "sales_per_day"
                else (
                    value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                    if driver == "variable_cost_ratio"
                    else money(value)
                )
            )
            valid = (
                0 <= value < 1
                if driver == "variable_cost_ratio"
                else (
                    0 <= value <= 1000000
                    if driver == "sales_per_day"
                    else (value > 0 if driver == "average_check" else value >= 0)
                )
            )
            operating = breakeven = difference = None
            if valid:
                adjusted, adjusted_fixed = inputs, fixed
                try:
                    original = fixed.rent if driver == "rent" else getattr(inputs, driver)
                    changed = type(original).model_validate(
                        original.model_dump()
                        | {"value": int(value) if driver == "sales_per_day" else value}
                    )
                    if driver == "rent":
                        adjusted_fixed = fixed.model_copy(update={"rent": changed})
                    else:
                        adjusted = inputs.model_copy(update={driver: changed})
                except ValidationError:
                    valid = False
            if valid:
                calculated = scenario(
                    "base", adjusted, adjusted_fixed, request.working_days_per_month.value
                )
                operating = calculated.metrics["operating_result"].value
                breakeven = calculated.metrics["break_even_sales_per_day"].value
                difference = money(operating - baseline.metrics["operating_result"].value)
            result.append(
                SensitivityPoint(
                    driver=driver,
                    relative_change=change,
                    actual_value=value,
                    status="calculated" if valid else "outside_domain",
                    operating_result=operating,
                    difference_from_base=difference,
                    break_even_sales_per_day=breakeven,
                    explanation="One-at-a-time modelled perturbation of the base scenario; "
                    "not market data. Money rounds to kopecks, ratio to 6 decimals, "
                    "sales/day to whole sales. "
                    + (
                        "Other inputs held constant."
                        if valid
                        else "Changed value is outside model domain."
                    ),
                )
            )
    return tuple(result)


def calculate(request: FinanceRequest) -> FinanceResult:
    # Never depend on the ambient Decimal context (e.g. a caller's precision/rounding).
    with localcontext(Context(prec=64, rounding=ROUND_HALF_UP)):
        payload = request.model_dump()
        for key in ("id", "conversation_id", "confirmation_state"):
            payload["profile"].pop(key)
        digest = hashlib.sha256(
            json.dumps(
                [ALGORITHM_VERSION, canonical(payload)],
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            ).encode()
        ).hexdigest()
        startup = request.startup
        launch = sum(
            (
                startup.equipment.value,
                startup.renovation.value,
                startup.rent_deposit.value,
                startup.initial_inventory.value,
                startup.registration.value,
                startup.other.value,
            ),
            Decimal(0),
        )
        total = money(launch + startup.working_capital_reserve.value)
        budget = request.profile.budget
        remaining = money(budget - total) if budget is not None else None
        scenarios = tuple(
            scenario(
                name,
                getattr(request.scenarios, name),
                getattr(request.scenarios, name).fixed_costs or request.monthly_fixed_costs,
                request.working_days_per_month.value,
            )
            for name in NAMES
        )
        base = scenarios[1]
        comparisons = [
            {
                "scenario": s.name,
                "revenue_difference_from_base": money(
                    s.metrics["monthly_revenue"].value - base.metrics["monthly_revenue"].value
                ),
                "operating_result_difference_from_base": money(
                    s.metrics["operating_result"].value - base.metrics["operating_result"].value
                ),
            }
            for s in scenarios
        ]
        warnings = []
        if budget is None:
            warnings.append("profile_budget_missing")
        if request.profile.confirmation_state != "confirmed":
            warnings.append("profile_snapshot_not_confirmed")
        if [s.metrics["operating_result"].value for s in scenarios] != sorted(
            s.metrics["operating_result"].value for s in scenarios
        ):
            warnings.append("scenario_labels_not_ordered_by_operating_result")
        return FinanceResult.model_validate(
            {
                "algorithm_version": ALGORITHM_VERSION,
                "request_fingerprint": digest,
                "request_snapshot": request,
                "rounding": "Decimal precision=64; monthly variable costs "
                "round HALF_UP to 2 decimals before subtraction. Unit margin is display-only; "
                "break-even uses unrounded contribution. "
                "All calculated money/count results are decimal strings.",
                "startup": {
                    "items": startup,
                    "launch_uses_excluding_reserve": money(launch),
                    "working_capital_reserve": money(startup.working_capital_reserve.value),
                    "total_initial_funding": total,
                    "formula": "sum(startup items, including reserve)",
                },
                "budget": {
                    "status": "budget_unknown"
                    if budget is None
                    else ("within_model_budget" if budget >= total else "model_budget_shortfall"),
                    "budget": money(budget) if budget is not None else None,
                    "startup_required": total,
                    "remaining": remaining,
                    "funding_gap": money(max(Decimal(0), total - budget))
                    if budget is not None
                    else None,
                    "limitations": (
                        "Comparison of supplied inputs only; not verified premises cost "
                        "or proof of affordable/available property.",
                    ),
                },
                "scenarios": scenarios,
                "comparison": comparisons,
                "sensitivity": sensitivity(request, base),
                "formulas": FORMULAS,
                "missing_data": MISSING_DATA,
                "limitations": LIMITATIONS,
                "warnings": warnings,
                "zone_reference_status": "not_verified_by_finance_service"
                if request.selected_zone
                else "not_provided",
            }
        )
