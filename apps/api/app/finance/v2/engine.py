"""Reviewed volume adapters → shared Decimal ledger; no LLM/formula evaluation."""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Context, Decimal, localcontext

from fastapi import HTTPException

from app.finance.engine import money
from app.finance.v2.registry import configuration, domain, validate
from app.finance.v2.schemas import (
    BreakEven,
    FinancialCalculation,
    FinancialDocument,
    FinancialScenario,
    FinancialSensitivity,
    Name,
    Range,
)

FORMULAS = {
    "auto_variable_unit": "materials_per_order + labor_per_order",
    "school_variable_unit": "variable_per_student + tuition*fee_ratio",
    "capacity_utilization": "units/capacity where known and >0",
    "auto_repair": "capacity=bays*working_days*orders_per_bay; "
    "units=capacity*utilization; months=1",
    "online_school": "units=paying_students; months=course_months if course else 1; "
    "revenue=units*tuition ONCE",
    "generic": "units=unit_sales; months=1; revenue=units*unit_price",
    "variable_costs": "round_HALF_UP(units*variable_per_unit + revenue*fee_ratio,2)",
    "fixed_costs": "round_HALF_UP(sum(monthly_fixed_items)*months,2)",
    "contribution": "rounded_revenue-rounded_variable_costs",
    "operating_result": "contribution-fixed_costs",
    "break_even": "ceil(fixed_costs/exact_unit_contribution); "
    "unavailable if margin<=0; compare capacity",
    "safety_margin_ratio": "(units-break_even_units)/units when units>0 and break-even defined",
}


def requirements(doc: FinancialDocument) -> tuple[str, ...]:
    return tuple(
        p.id
        for p in configuration(doc.model).parameters
        if not (p.id == "course_months" and doc.billing_model != "course")
    )


def lineage(doc: FinancialDocument) -> dict[str, tuple[str, ...]]:
    fixed: tuple[str, ...] = ("rent", "payroll", "utilities", "marketing", "other_fixed")
    volume: tuple[str, ...]
    price: tuple[str, ...]
    variable: tuple[str, ...]
    capacity: tuple[str, ...] = ()
    if doc.model == "auto_repair":
        capacity = ("service_bays", "working_days", "orders_per_bay")
        volume, price, variable = (
            (*capacity, "utilization"),
            ("average_order",),
            ("materials_per_order", "labor_per_order"),
        )
    elif doc.model == "online_school":
        capacity = ("student_capacity",)
        volume, price, variable = ("students",), ("tuition",), ("variable_per_student", "fee_ratio")
        fixed = ("teachers", "platform", "marketing", "other_fixed")
        if doc.billing_model == "course":
            fixed = (*fixed, "course_months")
    else:
        volume, price, variable = ("unit_sales",), ("unit_price",), ("variable_per_unit",)
    margin = (*price, *variable)
    operating = tuple(dict.fromkeys((*volume, *margin, *fixed)))
    return dict(
        units=volume,
        capacity=capacity,
        revenue=(*volume, *price),
        variable_costs=(*volume, *margin),
        fixed_costs=fixed,
        contribution=(*volume, *margin),
        operating_result=operating,
        contribution_per_unit=margin,
        capacity_utilization=(*volume, *capacity),
        safety_margin_ratio=operating,
        break_even=(*margin, *fixed, *capacity),
    )


def missing(doc: FinancialDocument) -> tuple[str, ...]:
    absent = tuple(
        k for k in requirements(doc) if k not in doc.entries or doc.entries[k].review != "confirmed"
    )
    return (
        ("billing_model", *absent)
        if doc.model == "online_school" and not doc.billing_model
        else absent
    )


def scenario(doc: FinancialDocument, name: Name, values: dict[str, Decimal]) -> FinancialScenario:
    domain(doc.model, values, doc.billing_model)
    capacity = None
    months = Decimal(1)
    fee = Decimal(0)
    fixed_keys: tuple[str, ...]
    if doc.model == "auto_repair":
        capacity = values["service_bays"] * values["working_days"] * values["orders_per_bay"]
        units = capacity * values["utilization"]
        price = values["average_order"]
        unit_cost = values["materials_per_order"] + values["labor_per_order"]
        fixed_keys = ("rent", "payroll", "utilities", "marketing", "other_fixed")
    elif doc.model == "online_school":
        units, capacity, price = values["students"], values["student_capacity"], values["tuition"]
        if doc.billing_model == "course":
            months = values["course_months"]
        unit_cost, fee = values["variable_per_student"], values["fee_ratio"]
        fixed_keys = ("teachers", "platform", "marketing", "other_fixed")
    else:
        units, price, unit_cost = (
            values["unit_sales"],
            values["unit_price"],
            values["variable_per_unit"],
        )
        fixed_keys = ("rent", "payroll", "utilities", "marketing", "other_fixed")
    revenue = money(units * price)
    variable = money(units * unit_cost + revenue * fee)
    fixed = money(sum((values[k] for k in fixed_keys), Decimal(0)) * months)
    margin = price * (1 - fee) - unit_cost
    be_units = (fixed / margin).to_integral_value(rounding=ROUND_CEILING) if margin > 0 else None
    be = BreakEven(
        status="nonpositive_margin"
        if be_units is None
        else "above_capacity"
        if capacity is not None and be_units > capacity
        else "calculated",
        units=be_units,
        revenue=money(be_units * price) if be_units is not None else None,
        capacity_utilization=be_units / capacity if be_units is not None and capacity else None,
    )
    return FinancialScenario(
        name=name,
        drivers=values,
        period="course_cohort" if doc.billing_model == "course" else "month",
        months=months,
        units=units,
        volume_unit="orders"
        if doc.model == "auto_repair"
        else "students"
        if doc.model == "online_school"
        else "units",
        capacity=capacity,
        revenue=revenue,
        variable_costs=variable,
        fixed_costs=fixed,
        contribution=revenue - variable,
        operating_result=money(revenue - variable - fixed),
        contribution_per_unit=margin,
        capacity_utilization=units / capacity if capacity else None,
        safety_margin_ratio=(units - be_units) / units if units and be_units is not None else None,
        break_even=be,
    )


def calculate(doc: FinancialDocument) -> FinancialCalculation:
    with localcontext(Context(prec=64, rounding=ROUND_HALF_UP)):
        config = configuration(doc.model)
        fields = {p.id: p for p in config.parameters}
        for key, entry in doc.entries.items():
            if key not in fields:
                from app.finance.v2.registry import reject

                reject("financial_parameter_unsupported")
            validate(fields[key], entry, entry.unit)
            if fields[key].direction == "context" and not entry.low == entry.base == entry.high:
                from app.finance.v2.registry import reject

                reject("financial_context_range_unsupported")
        absent = missing(doc)
        assumed = any(e.epistemic == "assumed" for e in doc.entries.values())
        if absent:
            return FinancialCalculation(
                status="partial",
                missing=absent,
                contains_assumptions=assumed,
                formulas=FORMULAS,
                limitations=config.limitations,
            )
        variants = []
        for name in ("conservative", "base", "optimistic"):
            values = {}
            for key in requirements(doc):
                e, p = doc.entries[key], fields[key]
                values[key] = (
                    e.base
                    if name == "base" or p.direction == "context"
                    else (
                        e.low if (name == "conservative") == (p.direction == "revenue") else e.high
                    )
                )
            variants.append(scenario(doc, name, values))
        base = variants[1]
        sensitivity = []
        for p in config.parameters:
            if p.direction == "context" or p.id not in base.drivers:
                continue
            for factor in (Decimal("0.9"), Decimal("1.1")):
                value = base.drivers[p.id] * factor
                value = (
                    value.to_integral_value(rounding=ROUND_HALF_UP)
                    if p.integer
                    else value.quantize(Decimal("0.000001"))
                )
                valid = p.minimum <= value <= p.maximum
                changed = None
                if valid:
                    try:
                        vals = {**base.drivers, p.id: value}
                        validate(p, Range(base=value, low=value, high=value), p.unit)
                        changed = scenario(doc, "base", vals)
                    except HTTPException:
                        valid = False
                sensitivity.append(
                    FinancialSensitivity(
                        parameter=p.id,
                        unit=p.unit,
                        value=value,
                        status="calculated" if valid else "outside_domain",
                        operating_result=changed.operating_result if changed else None,
                        difference_from_base=money(changed.operating_result - base.operating_result)
                        if changed
                        else None,
                    )
                )
        return FinancialCalculation(
            status="calculated",
            missing=(),
            scenarios=tuple(variants),
            sensitivity=tuple(sensitivity),
            contains_assumptions=assumed,
            formulas=FORMULAS,
            metric_inputs=lineage(doc),
            warnings=("scenario_labels_not_ordered_by_operating_result",)
            if [s.operating_result for s in variants]
            != sorted(s.operating_result for s in variants)
            else (),
            limitations=config.limitations,
        )
