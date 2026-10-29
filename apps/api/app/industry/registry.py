"""Reviewed configuration, independent of Qwen prompt text and executable expressions."""

import hashlib
from decimal import Decimal, InvalidOperation
from typing import NoReturn

from fastapi import HTTPException

from app.industry.schemas import FieldDefinition as F
from app.industry.schemas import IndustryDefinition, Scalar, UniversalProfile

COMMON = (
    F(id="city", label="Город", question="В каком городе планируете работать?"),
    F(
        id="business_model",
        label="Бизнес-модель",
        question="Как вы будете оказывать услуги или продавать продукт?",
    ),
    F(
        id="physical_premises",
        label="Помещение",
        question="Нужно ли отдельное помещение?",
        kind="boolean",
        unit="boolean",
    ),
    F(
        id="budget",
        label="Бюджет, ₽",
        question="Какой у вас бюджет в рублях?",
        kind="money",
        unit="RUB",
        maximum=9999999999999999,
    ),
    F(
        id="currency",
        label="Валюта",
        question="Уточните валюту бюджета.",
        kind="choice",
        choices=("RUB",),
    ),
    F(
        id="funding",
        label="Источник средств",
        question="Свои средства, кредит, смешанное финансирование или пока не решили?",
        kind="choice",
        choices=("own_funds", "loan", "mixed", "undecided"),
    ),
    F(id="format", label="Формат", question="Какой формат бизнеса рассматриваете?"),
    F(id="audience", label="Аудитория", question="Для кого ваш продукт или услуга?"),
    F(
        id="specialization",
        label="Специализация",
        question="На каких услугах или продуктах хотите специализироваться?",
    ),
    F(
        id="revenue_streams",
        label="Источники выручки",
        question="За что и как будут платить клиенты?",
        driver="revenue",
    ),
    F(
        id="cost_categories",
        label="Основные расходы",
        question="Какие основные расходы вы уже знаете?",
        driver="fixed_cost",
    ),
    F(id="sales_channels", label="Каналы продаж", question="Как планируете находить клиентов?"),
    F(id="constraints", label="Ограничения", question="Какие ограничения нужно учесть?"),
    F(id="preferences", label="Пожелания", question="Какие пожелания важны для вас?"),
    F(id="service_area", label="География работы", question="Где находятся ваши клиенты?"),
)


def number(
    key: str, label: str, question: str, unit: str, maximum: int = 1000000, driver: str = "capacity"
) -> F:
    return F.model_validate(
        dict(
            id=key,
            label=label,
            question=question,
            kind="integer",
            unit=unit,
            maximum=maximum,
            driver=driver,
        )
    )


def money(key: str, label: str, driver: str = "fixed_cost", unit: str = "RUB/month") -> F:
    return F.model_validate(
        dict(
            id=key,
            label=label,
            question=f"Укажите {label.lower()} в рублях.",
            kind="money",
            unit=unit,
            maximum=9999999999999999,
            driver=driver,
        )
    )


CONFIGS = (
    IndustryDefinition(
        id="coffee_shop",
        label="Кофейня",
        aliases=("кофейня", "кофейню", "coffee shop"),
        business_models=("retail", "food_service"),
        required=("city", "budget", "format", "funding"),
        fields=(
            number("seats", "Посадочные места", "Сколько посадочных мест планируете?", "seats"),
            number(
                "sales_per_day", "Продаж в день", "Сколько продаж в день планируете?", "sales/day"
            ),
            money("average_check", "Средний чек", "revenue", "RUB/sale"),
        ),
        data_categories=("geo.mapped_poi",),
        optional_categories=("geo.pedestrian_network",),
        geo_policy="required",
        geo_adapter="coffee_poi_v1",
        finance_adapter="coffee_finance_v1",
        limitations=("Рейтинг использует OSM-прокси, а не измеренный спрос или прогноз прибыли.",),
    ),
    IndustryDefinition(
        id="auto_repair",
        label="Автосервис",
        aliases=("автосервис", "автосервиса", "СТО"),
        business_models=("service",),
        required=("city", "budget", "specialization", "service_bays", "physical_premises"),
        fields=(
            number(
                "service_bays",
                "Ремонтные посты",
                "Сколько ремонтных постов планируете?",
                "bays",
                1000,
            ),
            F(id="services", label="Услуги", question="Какие услуги планируете?"),
            F(
                id="utilization",
                label="Загрузка",
                question="Какую загрузку предполагаете?",
                kind="ratio",
                unit="ratio",
            ),
            number(
                "working_days", "Рабочие дни", "Сколько рабочих дней в месяц?", "days/month", 31
            ),
            number(
                "orders_per_bay",
                "Заказов на пост",
                "Сколько заказов на пост в день планируете?",
                "orders/bay/day",
            ),
            money("average_order", "Средний заказ", "revenue", "RUB/order"),
            money("payroll", "Расходы на персонал"),
            money("materials", "Материалы", "variable_cost"),
            money("rent", "Аренда"),
        ),
        data_categories=("geo.mapped_poi", "geo.vehicle_network"),
        optional_categories=("geo.buildings", "geo.parking"),
        geo_policy="required",
        limitations=(
            "Автомобильный рейтинг и финансовый адаптер пока не реализованы.",
            "OSM POI не подтверждает дорожную сеть или автомобильный трафик.",
        ),
    ),
    IndustryDefinition(
        id="online_school",
        label="Онлайн-школа",
        aliases=("онлайн-школа", "онлайн-школу", "онлайн школа"),
        business_models=("digital", "subscription"),
        required=("budget", "audience", "format", "payment_model", "students"),
        fields=(
            F(
                id="payment_model",
                label="Модель оплаты",
                question="Как будут платить ученики: за курс, подписку или занятия?",
                driver="revenue",
            ),
            number(
                "students", "Число учеников", "Сколько учеников планируете на старте?", "students"
            ),
            money("tuition", "Стоимость обучения", "revenue", "RUB/student/payment"),
            F(
                id="payment_frequency",
                label="Период оплаты",
                question="Как часто оплачивают обучение?",
            ),
            money("teachers", "Оплата преподавателей"),
            money("marketing", "Маркетинг"),
        ),
        data_categories=(),
        optional_categories=("user.budget", "user.costs"),
        geo_policy="none",
        limitations=(
            "Финансовый адаптер цифрового обучения пока не реализован; "
            "прогноз прибыли не рассчитан.",
        ),
    ),
    IndustryDefinition(
        id="generic",
        label="Бизнес-проект",
        aliases=(),
        business_models=("other", "mixed"),
        required=("business_model", "physical_premises", "budget", "audience", "revenue_streams"),
        fields=(),
        data_categories=(),
        optional_categories=("user.budget", "user.costs"),
        geo_policy="optional",
        limitations=(
            "Специализированная модель не выбрана. Доступны профиль и проверка наличия данных.",
        ),
    ),
)
INDUSTRIES = {c.id: c for c in CONFIGS}
# Only real executors. A config cannot create a method by naming one.
CAPABILITIES = {
    "data.coverage",
    "data.sufficiency",
    "geo.coffee",
    "finance.coffee",
    "profile.summary",
}
FIELDS = {f.id: f for f in COMMON}


def reject(code: str) -> NoReturn:
    raise HTTPException(422, detail={"code": code})


def configuration(industry: str) -> IndustryDefinition:
    if industry not in INDUSTRIES:
        reject("unsupported_industry")
    return INDUSTRIES[industry]


def definitions(industry: str) -> dict[str, F]:
    return FIELDS | {f.id: f for f in configuration(industry).fields}


def configuration_hash(industry: str) -> str:
    document = (
        configuration(industry).model_dump_json()
        + "|"
        + "|".join(f.model_dump_json() for f in COMMON)
    )
    return hashlib.sha256(document.encode()).hexdigest()


def value(profile: UniversalProfile, key: str) -> Scalar | None:
    entry = profile.values.get(key) or profile.extensions.get(profile.industry, {}).get(key)
    return entry.value if entry else None


def validate_value(definition: F, raw: Scalar) -> Scalar:
    if definition.kind == "boolean":
        if not isinstance(raw, bool):
            reject("invalid_profile_value")
        return raw
    if isinstance(raw, bool):
        reject("invalid_profile_value")
    if definition.kind in {"money", "ratio", "integer"}:
        try:
            number = Decimal(str(raw))
            maximum = 1 if definition.kind == "ratio" else definition.maximum
            if not number.is_finite() or number < 0 or number > maximum:
                raise ValueError
            if definition.kind == "integer":
                if number != number.to_integral_value():
                    raise ValueError
                return int(number)
            if definition.kind == "money" and number != number.quantize(Decimal("0.01")):
                raise ValueError
            return str(number)
        except (InvalidOperation, ValueError):
            reject("invalid_profile_value")
    if not isinstance(raw, str) or (definition.choices and raw not in definition.choices):
        reject("invalid_profile_value")
    return raw


def missing(profile: UniversalProfile) -> tuple[str, ...]:
    required = configuration(profile.industry).required
    return tuple(
        k
        for k in required
        if value(profile, k) is None or (k == "budget" and Decimal(str(value(profile, k))) <= 0)
    )
