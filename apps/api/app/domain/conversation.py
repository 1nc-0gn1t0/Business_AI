import re
from decimal import Decimal

from app.api.conversation_schemas import ProfilePatch
from app.api.schemas import BusinessProfile
from app.domain.enums import ConfirmationState, ConversationState, Funding

QUESTIONS = {
    "category": "Какой бизнес вы хотите открыть?",
    "city": "В каком городе?",
    "budget": "Какой у вас бюджет в рублях?",
    "preferences.format": "Какой формат бизнеса рассматриваете?",
    "funding": "На какие средства: свои, кредит, смешанные или пока не решили?",
}
CONFIRMATIONS = {"подтверждаю", "всё верно", "все верно", "да, всё верно", "да, все верно"}
CITY_FORMS = {
    "казань": "Казань",
    "казани": "Казань",
    "москва": "Москва",
    "москве": "Москва",
    "санкт-петербург": "Санкт-Петербург",
    "санкт-петербурге": "Санкт-Петербург",
    "новосибирск": "Новосибирск",
    "новосибирске": "Новосибирск",
}
CATEGORIES = {
    "кофейн": "кофейня",
    "пекарн": "пекарня",
    "салон красот": "салон красоты",
    "магазин": "магазин",
    "ресторан": "ресторан",
}
AMOUNT = (
    r"(?P<amount>[+-]?\d(?:[\d \u00a0]*\d)?(?:[.,]\d{1,2})?)\s*"
    r"(?P<scale>млн|миллион\w*|тыс\.?|тысяч\w*|[кk])?\s*(?:₽|руб\w*\.?)?"
)


def negated(prefix: str) -> bool:
    return bool(re.search(r"\bне(?:\s+(?:в|хочу|нужен|нужна|планирую|открывать)){0,3}\s*$", prefix))


def missing_fields(profile: BusinessProfile) -> tuple[str, ...]:
    present = {
        "category": profile.category is not None,
        "city": profile.city is not None,
        "budget": profile.budget is not None and profile.budget > 0,
        "preferences.format": profile.preferences.format is not None,
        "funding": profile.funding is not None,
    }
    return tuple(key for key, supplied in present.items() if not supplied)


def state_for(profile: BusinessProfile) -> ConversationState:
    if missing_fields(profile):
        return ConversationState.COLLECTING
    if profile.confirmation_state == ConfirmationState.CONFIRMED:
        return ConversationState.CONFIRMED
    return ConversationState.AWAITING_CONFIRMATION


def reply_for(profile: BusinessProfile) -> str:
    missing = missing_fields(profile)
    if missing:
        return QUESTIONS[missing[0]]
    if profile.confirmation_state == ConfirmationState.CONFIRMED:
        return "Профиль подтверждён. Можно выбрать локацию."
    return "Всё необходимое собрано. Проверьте ваш проект."


def apply_patch(profile: BusinessProfile, patch: ProfilePatch) -> BusinessProfile:
    values = profile.model_dump()
    updates = patch.model_dump(exclude_unset=True)
    preferences = updates.pop("preferences", ...)
    values.update(updates)
    if preferences is None:
        values["preferences"] = {}
    elif preferences is not ...:
        values["preferences"] = profile.preferences.model_dump() | preferences
    candidate = BusinessProfile.model_validate(values)
    if candidate != profile:
        values["confirmation_state"] = ConfirmationState.DRAFT
    return BusinessProfile.model_validate(values)


def confirm(profile: BusinessProfile) -> BusinessProfile:
    if missing_fields(profile):
        raise ValueError("Profile is incomplete")
    return BusinessProfile.model_validate(
        profile.model_dump() | {"confirmation_state": ConfirmationState.CONFIRMED}
    )


def extract_business_profile(message: str, profile: BusinessProfile) -> ProfilePatch:
    """Conservative local rules, not an LLM. Unrecognised text never becomes a fact."""
    text = message.casefold().replace("ё", "е").strip()
    values: dict[str, object] = {}
    # Explicit labels accept arbitrary cities/categories/formats, not only demo examples.
    for label, field in [("город", "city"), ("бизнес", "category"), ("категория", "category")]:
        match = re.search(rf"\b{label}\s*[:=]\s*([^;\n,]+)", message, re.IGNORECASE)
        if match:
            values[field] = match.group(1).strip()
    if "city" not in values:
        cities = list(re.finditer(r"\b(" + "|".join(CITY_FORMS) + r")\b", text))
        positive = [city for city in cities if not negated(text[: city.start()])]
        if positive and len({CITY_FORMS[city.group(1)] for city in positive}) == 1:
            values["city"] = CITY_FORMS[positive[-1].group(1)]
    if "category" not in values:
        recognised = set()
        for stem, category in CATEGORIES.items():
            match = re.search(r"\b" + stem, text)
            if match and not negated(text[: match.start()]):
                recognised.add(category)
        if len(recognised) == 1:
            values["category"] = recognised.pop()
    format_match = re.search(r"\bформат\s*[:=]\s*([^;\n,]+)", message, re.IGNORECASE)
    if format_match:
        values["preferences"] = {"format": format_match.group(1).strip()}
    elif re.search(r"(?:с собой|навынос)", text) and not re.search(r"не (?:с собой|навынос)", text):
        values["preferences"] = {"format": "навынос"}
    budget = re.search(
        r"\bбюджет(?:ом)?\s*[:=]?\s*" + AMOUNT + r"(?=$|[;,!?]|\s+(?:и|на|для|в)\b)", text
    )
    if budget and negated(text[: budget.start()]):
        budget = None
    standalone = re.fullmatch(AMOUNT + r"[.!]?", text)
    if (
        budget is None
        and standalone
        and (
            standalone.group("scale")
            or re.search(r"₽|руб", text)
            or (missing_fields(profile) and missing_fields(profile)[0] == "budget")
        )
    ):
        budget = standalone
    if budget:
        amount = Decimal(
            budget.group("amount").replace(" ", "").replace("\u00a0", "").replace(",", ".")
        )
        scale = budget.group("scale") or ""
        multiplier = 1_000_000 if scale.startswith("м") else 1_000 if scale else 1
        values["budget"] = amount * multiplier
    credit = re.search(r"\bкредит\w*", text)
    credit_declined = bool(
        re.search(r"(?:не хочу|не нужен|без)\s+кредит|кредит\w*\s+не нужен", text)
    )
    own = bool(re.search(r"без кредита|свои средства|собственн\w* средств", text))
    if "смешан" in text or (own and credit and not credit_declined):
        values["funding"] = Funding.MIXED
    elif own:
        values["funding"] = Funding.OWN_FUNDS
    elif credit and not credit_declined:
        values["funding"] = Funding.LOAN
    elif re.search(r"не решил|пока не знаю", text) and (
        missing_fields(profile) == ("funding",) or "финансирован" in text
    ):
        values["funding"] = Funding.UNDECIDED
    # Arbitrary business categories use an explicit label; unknown cities need a name.
    missing = missing_fields(profile)
    if (
        not values
        and missing
        and text not in CONFIRMATIONS
        and text not in {"привет", "да", "нет"}
        and not text.startswith("не ")
        and not re.search(r"\bили\b", text)
        and not any(
            word in text for word in ["не знаю", "не хочу", "игнорируй", "удали", "покажи", "?"]
        )
    ):
        field = missing[0]
        if field in {"city", "category", "preferences.format"} and re.fullmatch(
            r"[а-яa-z][а-яa-z -]{1,99}", text
        ):
            if field == "preferences.format":
                values["preferences"] = {"format": message.strip()}
            elif field == "city" and message.strip().istitle():
                values[field] = message.strip()
    return ProfilePatch.model_validate(values)
