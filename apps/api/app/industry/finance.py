"""Typed projection to existing v1 base-scenario inputs, never new formulas/defaults."""

from decimal import Decimal

from app.domain.enums import DataOrigin
from app.industry.registry import missing
from app.industry.schemas import CoffeeDriverInputs, UniversalProfile


def coffee_inputs(profile: UniversalProfile) -> CoffeeDriverInputs | None:
    if (
        profile.industry != "coffee_shop"
        or profile.confirmed_revision != profile.revision
        or missing(profile)
    ):
        return None
    inputs: dict[str, object] = {}
    for key in ("average_check", "sales_per_day"):
        entry = profile.extensions.get("coffee_shop", {}).get(key)
        if entry is None or entry.review != "confirmed" or entry.origin != DataOrigin.USER_INPUT:
            continue
        # v1 average_check must be positive. Explicit zero is retained in v2,
        # but cannot be silently converted to a positive sale price.
        if key == "average_check" and Decimal(str(entry.value)) <= 0:
            continue
        inputs[key] = {
            "value": entry.value,
            "source": {
                "origin": "user_input",
                "source_name": "Подтверждённые вводные пользователя",
                "data_version": f"profile-v2-{profile.revision}",
                "confidence": "low",
                "limitations": ["Пользовательская вводная, не подтверждённая рыночная статистика."],
                "evidence_ref": f"profile:{profile.id}:{profile.revision}:{key}",
            },
        }
    return CoffeeDriverInputs.model_validate(inputs)
