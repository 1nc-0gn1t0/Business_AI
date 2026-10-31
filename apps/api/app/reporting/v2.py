"""Read-only integration of current U-04 applicability and immutable U-05 inputs.

Coverage is explicitly a current metadata assessment, not part of the historical
financial snapshot. No v1 report bytes or stored snapshots are changed.
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from app.api.schemas import Contract
from app.finance.v2.registry import DEFINITIONS, enabled
from app.finance.v2.schemas import FinancialSnapshot
from app.finance.v2.service import FinancialService
from app.industry.schemas import AdaptivePlan, UniversalProfile
from app.industry.service import IndustryProfiles


class AnalysisSection(Contract):
    id: str
    state: Literal["completed", "partial", "not_required", "unsupported", "missing", "needs_review"]
    explanation: str


class AnalysisResult(Contract):
    schema_version: Literal["analysis-result-v2"] = "analysis-result-v2"
    conversation_id: UUID
    profile_revision: int
    assessed_at: datetime
    state: Literal["collecting", "partial", "completed"]
    profile: UniversalProfile
    plan: AdaptivePlan
    financial: FinancialSnapshot | None
    sections: tuple[AnalysisSection, ...]
    limitations: tuple[str, ...]


def analysis_result(session: Session, owner: UUID, token: str) -> AnalysisResult:
    # Short row lock gives one coherent profile/input/result revision; no model or
    # network call occurs here. It is released when the request transaction ends.
    service = IndustryProfiles(session)
    service.load(owner, token, lock=True)
    view = service.view(owner, token)
    confirmed = view.profile.confirmed_revision == view.profile.revision
    finance = (
        FinancialService(session).view(owner, token)
        if enabled() and view.profile.industry in DEFINITIONS
        else None
    )
    snapshot = finance.result if finance and finance.current and confirmed else None
    financial_state = (
        "completed"
        if snapshot and snapshot.result.status == "calculated"
        else "partial"
        if snapshot
        else "needs_review"
        if finance and finance.needs_review
        else "missing"
        if finance
        else "unsupported"
    )
    geo = next(c for c in view.plan.capabilities if c.id == "geo.analysis")
    geo_state = (
        "not_required"
        if geo.status == "not_required"
        else "unsupported"
        if geo.status == "unsupported"
        else "needs_review"
        if geo.status == "needs_confirmation"
        else "partial"
        if geo.status in {"available", "partial"}
        else "missing"
    )
    sections = (
        AnalysisSection(
            id="profile",
            state="completed" if confirmed else "needs_review",
            explanation="Подтверждённые вводные." if confirmed else "Проверьте профиль.",
        ),
        AnalysisSection.model_validate(
            dict(id="geography", state=geo_state, explanation=geo.reason)
        ),
        AnalysisSection.model_validate(
            dict(
                id="finance",
                state=financial_state,
                explanation="Сценарная арифметика по сохранённым вводным, не прогноз спроса."
                if snapshot
                else "Нужны совместимые подтверждённые финансовые вводные.",
            )
        ),
        AnalysisSection(
            id="banking",
            state="partial",
            explanation="Отдельный подбор по заявленным потребностям; банковского одобрения нет. "
            "Mock-заявки новых отраслей не поддерживаются; данные никуда не отправлены.",
        ),
    )
    # Financial completion is different from whole-analysis completeness.
    complete = confirmed and financial_state == "completed" and geo_state == "not_required"
    if view.profile.resolution != "known":
        complete = False
    return AnalysisResult(
        conversation_id=owner,
        profile_revision=view.profile.revision,
        assessed_at=datetime.now(UTC),
        state="collecting" if not confirmed else "completed" if complete else "partial",
        profile=view.profile,
        plan=view.plan,
        financial=snapshot,
        sections=sections,
        limitations=(
            "Гипотезы остаются предположениями после подтверждения пользователем.",
            "Coverage оценён на assessed_at; "
            "он не является частью исторического финансового snapshot.",
            "Для новых отраслей доступен JSON. PDF остаётся в прежнем маршруте кофейни.",
            "Сценарные результаты не являются инвестиционным прогнозом или кредитным решением.",
        ),
    )
