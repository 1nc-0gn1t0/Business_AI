"""Deterministic applicability and data eligibility. No industry-specific invented scores."""

from sqlalchemy.orm import Session

from app.data.coverage import assess_sufficiency, coverage
from app.data.registry import load_registry
from app.data.registry_schemas import CoverageQuery, DataRequirement
from app.industry.registry import configuration, definitions, missing, value
from app.industry.schemas import AdaptivePlan, CapabilityDecision, UniversalProfile


def plan(session: Session, profile: UniversalProfile) -> AdaptivePlan:
    from app.finance.v2.registry import DEFINITIONS
    from app.finance.v2.registry import enabled as finance_enabled

    config = configuration(profile.industry)
    v2_finance = finance_enabled() and profile.industry in DEFINITIONS
    absent = missing(profile)
    unanswered = tuple(k for k in absent if k not in profile.deferred_fields)
    ambiguous = profile.resolution == "ambiguous"
    confirmed = profile.confirmed_revision == profile.revision
    geo = config.geo_policy != "none" and value(profile, "physical_premises") is not False
    if config.geo_policy == "optional" and value(profile, "physical_premises") is None:
        geo = False
    registry = load_registry()
    city = str(value(profile, "city") or "").casefold()
    territory = next(
        (
            t.id
            for t in registry.territories
            if city in [a.casefold() for a in (t.name, *t.aliases)]
        ),
        None,
    )
    result = None
    sufficient = None
    # Never query all territories when the requested city cannot be resolved.
    categories = config.data_categories if geo else ()
    if categories and territory:
        result = coverage(
            session, CoverageQuery(territory=territory, categories=categories), registry
        )
        sufficient = assess_sufficiency(
            tuple(DataRequirement(id=c, category=c, allow_partial=True) for c in categories),
            result,
            config.version,
        )
    geo_status = "not_required" if not geo else "unsupported"
    geo_reason = (
        "Географический анализ не требуется."
        if not geo
        else "Подходящий отраслевой геоалгоритм пока не реализован."
    )
    if geo and config.geo_adapter:
        states = [a.local_status for a in result.assessments] if result else []
        geo_status = (
            "partial"
            if states and all(s in {"available", "partial"} for s in states)
            else "unavailable"
        )
        geo_reason = (
            "Доступна оценка OSM в пределах snapshot; полнота рынка неизвестна."
            if geo_status == "partial"
            else "Нет подтверждённого пригодного покрытия выбранной территории."
        )
    decisions = (
        CapabilityDecision(
            id="data.coverage",
            status="available",
            method="app.data.coverage.coverage",
            reason="Проверка metadata, без сетевого запроса.",
        ),
        CapabilityDecision(
            id="data.sufficiency",
            status="available",
            method="app.data.coverage.assess_sufficiency",
            reason="Техническая достаточность не доказывает качество бизнес-вывода.",
        ),
        CapabilityDecision.model_validate(
            dict(
                id="geo.analysis",
                status=geo_status if confirmed else "needs_confirmation" if geo else "not_required",
                method=config.geo_adapter,
                reason=geo_reason,
            )
        ),
        CapabilityDecision(
            id="finance.analysis",
            status="available"
            if confirmed and (config.finance_adapter or v2_finance) and not absent
            else "unavailable"
            if confirmed and absent and (config.finance_adapter or v2_finance)
            else "needs_confirmation"
            if config.finance_adapter or v2_finance
            else "unsupported",
            method=f"financial_v2.{profile.industry}" if v2_finance else config.finance_adapter,
            reason="Предварительные финансовые сценарии по подтверждённым вводным."
            if v2_finance
            else "Проверенный финансовый движок кофейни; вводные задаются явно."
            if config.finance_adapter
            else "Отраслевой финансовый адаптер пока не поддерживается. Прибыль не рассчитана.",
        ),
        CapabilityDecision(
            id="profile.summary",
            status="available",
            method="profile_v2_projection",
            reason="Структурированные вводные и ограничения, без выдуманных вычислений.",
        ),
    )
    stages: list[str] = ["clarify" if unanswered or ambiguous else "confirm"]
    if confirmed:
        stages = []
        if not absent and config.geo_adapter and geo_status in {"partial", "available"}:
            stages.append("location")
        if (config.finance_adapter or v2_finance) and not absent:
            stages.append("finance")
        if not config.finance_adapter:
            stages.append("banking")
        stages.append("partial_result")
    return AdaptivePlan.model_validate(
        dict(
            profile_revision=profile.revision,
            industry_version=config.version,
            outcome="collecting"
            if unanswered or ambiguous
            else "partial"
            if absent
            or not (config.finance_adapter or v2_finance)
            or geo_status in {"partial", "unavailable", "unsupported"}
            else "ready",
            missing_fields=("industry", *absent) if ambiguous else absent,
            next_question="Какую одну бизнес-идею выбираете?"
            if ambiguous
            else definitions(profile.industry)[unanswered[0]].question
            if unanswered
            else None,
            geo_required=geo,
            capabilities=decisions,
            stages=stages,
            coverage=result,
            sufficiency=sufficient,
        )
    )
