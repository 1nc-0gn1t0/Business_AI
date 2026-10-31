"""Reviewed drivers, units and domains. No expressions from users or the model."""

import os
from decimal import Decimal
from typing import NoReturn

from fastapi import HTTPException

from app.finance.v2.schemas import FinancialDefinition, Range
from app.finance.v2.schemas import FinancialParameter as P


def enabled() -> bool:
    return (
        os.getenv("BA_INDUSTRY_ENABLED", "0") == "1"
        and os.getenv("BA_FINANCE_V2_ENABLED", "0") == "1"
    )


def reject(code: str, status: int = 422) -> NoReturn:
    raise HTTPException(status, detail={"code": code})


def p(
    key: str,
    label: str,
    unit: str,
    direction: str = "cost",
    maximum: int = 1000000000,
    minimum: int = 0,
    integer: bool = False,
) -> P:
    return P.model_validate(
        dict(
            id=key,
            label=label,
            unit=unit,
            direction=direction,
            minimum=minimum,
            maximum=maximum,
            integer=integer,
        )
    )


FIXED = (
    p("rent", "Аренда", "RUB/month"),
    p("payroll", "Постоянная оплата труда", "RUB/month"),
    p("utilities", "Коммунальные расходы", "RUB/month"),
    p("marketing", "Маркетинг", "RUB/month"),
    p("other_fixed", "Другие постоянные расходы", "RUB/month"),
)
LIMITATIONS = (
    "Предварительный сценарный расчёт при заданных вводных, не рыночный прогноз.",
    "Операционный результат до налогов, амортизации и процентов; "
    "не чистая прибыль и не денежный поток.",
    "Бюджет не является выручкой. CAPEX, окупаемость и runway "
    "без графика инвестиций не рассчитаны.",
    "Диапазоны не являются доверительными интервалами; вероятность сценариев неизвестна.",
    "Нулевые расходы допустимы только как явно введённые и подтверждённые значения.",
)
DEFINITIONS = {
    "auto_repair": FinancialDefinition(
        id="auto_repair",
        parameters=(
            p("service_bays", "Ремонтные посты", "bays", "context", 1000, 1, True),
            p("working_days", "Рабочие дни", "days/month", "context", 31, 1, True),
            p(
                "orders_per_bay",
                "Мощность поста в день (при полной загрузке)",
                "orders/bay/day",
                "context",
                100,
                1,
            ),
            p("utilization", "Загрузка (0–1)", "ratio", "revenue", 1),
            p("average_order", "Выручка на заказ, включая запчасти", "RUB/order", "revenue"),
            p("materials_per_order", "Материалы на заказ", "RUB/order"),
            p("labor_per_order", "Переменная оплата труда на заказ", "RUB/order"),
            *FIXED,
        ),
        limitations=(
            *LIMITATIONS,
            "Мощность = посты × дни × заказы на пост при полной загрузке. "
            "Загрузка применяется один раз.",
            "Материалы и переменная оплата не должны дублироваться в постоянных расходах.",
        ),
    ),
    "online_school": FinancialDefinition(
        id="online_school",
        parameters=(
            p("students", "Платящие ученики", "students", "revenue", 1000000, 0, True),
            p(
                "student_capacity",
                "Предельная вместимость",
                "students",
                "context",
                1000000,
                1,
                True,
            ),
            p("tuition", "Цена за выбранный период оплаты", "RUB/student/payment", "revenue"),
            p(
                "course_months",
                "Длительность курса (для разовой оплаты)",
                "months",
                "context",
                36,
                1,
                True,
            ),
            p(
                "variable_per_student",
                "Переменные расходы на ученика за период оплаты",
                "RUB/student/payment",
            ),
            p("fee_ratio", "Комиссии с выручки (0–1)", "ratio", maximum=1),
            p("teachers", "Постоянные расходы на преподавателей", "RUB/month"),
            p("platform", "Учебная платформа", "RUB/month"),
            p("marketing", "Маркетинг", "RUB/month"),
            p("other_fixed", "Другие постоянные расходы", "RUB/month"),
        ),
        limitations=(
            *LIMITATIONS,
            "monthly/subscription: один выбранный месяц; продление, churn и CAC не прогнозируются.",
            "course: одна оплаченная когорта за всю длительность курса; "
            "выручка не повторяется ежемесячно.",
            "Переменная и постоянная оплата преподавателей не должны дублироваться.",
        ),
    ),
    "generic": FinancialDefinition(
        id="generic",
        parameters=(
            p(
                "unit_sales",
                "Количество однородных услуг/продаж за месяц",
                "units/month",
                "revenue",
                1000000,
            ),
            p("unit_price", "Цена одной услуги/единицы", "RUB/unit", "revenue"),
            p("variable_per_unit", "Переменные расходы на единицу", "RUB/unit"),
            *FIXED,
        ),
        limitations=(
            *LIMITATIONS,
            "Одна однородная единица продажи. Разнородные потоки с разными маржами "
            "не агрегируются автоматически.",
            "Физическая мощность неизвестна; расчёт не доказывает реализуемость объёма продаж.",
        ),
    ),
}


def configuration(model: str) -> FinancialDefinition:
    if model not in DEFINITIONS:
        reject("financial_model_unsupported")
    return DEFINITIONS[model]


def validate(parameter: P, entry: Range, unit: str) -> None:
    if unit != parameter.unit:
        reject("financial_unit_mismatch")
    for value in (entry.low, entry.base, entry.high):
        if not parameter.minimum <= value <= parameter.maximum:
            reject("financial_value_outside_domain")
        if parameter.integer and value != value.to_integral_value():
            reject("financial_integer_required")


def domain(model: str, entries: dict[str, Decimal], billing: str | None) -> None:
    if model == "online_school" and entries["students"] > entries["student_capacity"]:
        reject("financial_capacity_exceeded")
    if model == "online_school" and billing not in {"monthly", "subscription", "course"}:
        reject("financial_billing_required")
