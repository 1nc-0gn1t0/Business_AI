import hashlib
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

from app.api.schemas import BusinessProfile
from app.bank.schemas import (
    BankingNeeds,
    Catalogue,
    CatalogueView,
    MatchResult,
    ProductDecision,
    ProductView,
    RuleEvaluation,
)
from app.domain.enums import ConfirmationState, Funding

ALGORITHM_VERSION = "bank-relevance-three-valued-v1"
LIMITATIONS = (
    "Подбор отражает соответствие заявленной потребности назначению продукта, не решение банка.",
    "Тарифы, документы, региональная доступность и полные условия требуют проверки в ВТБ.",
    "Кредитоспособность, вероятность одобрения, лимит и ставка не рассчитываются.",
    "Данные не передаются в банк; заявок и банковской интеграции нет.",
    "Демонстрационные совпадения не являются действующими предложениями ВТБ.",
)


def today() -> date:
    return datetime.now(UTC).date()


def load_catalogue() -> Catalogue:
    path = Path(
        os.environ.get("BANK_CATALOGUE_PATH", str(Path(__file__).with_name("catalogue.json")))
    )
    return Catalogue.model_validate_json(path.read_text(encoding="utf-8"))


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def catalogue_view(catalogue: Catalogue, as_of: date) -> CatalogueView:
    sources = {s.id: s for s in catalogue.sources}
    entries = []
    for product in sorted(catalogue.products, key=lambda p: p.id):
        evidence = tuple(sources[key] for key in sorted(product.source_ids))
        reasons = []
        availability = "blocked"
        dates = [product.last_reviewed_at, *(s.reviewed_at for s in evidence)]
        if any(value > as_of for value in dates):
            reasons.append("Дата проверки находится в будущем; запись заблокирована.")
        elif any((as_of - value).days > catalogue.review_window_days for value in dates):
            reasons.append("Истёк срок пересмотра каталога; запись заблокирована.")
        elif product.status in ("retired", "unavailable") or any(
            s.verification == "unavailable" for s in evidence
        ):
            reasons.append("Продукт или источник недоступен/снят; запись заблокирована.")
        elif product.mode == "demonstration":
            availability = "demonstration_only"
            reasons.append("Демо-карточка: актуальные условия и доступность не подтверждены.")
        elif product.status != "published" or any(
            s.verification != "verified"
            or s.last_verified_at is None
            or (as_of - s.last_verified_at).days > catalogue.review_window_days
            for s in evidence
        ):
            reasons.append("Нет актуального подтверждения официального источника.")
        else:
            availability = "verified_reference"
            reasons.append(
                "Назначение продукта проверено по официальному источнику; "
                "условия клиента неизвестны."
            )
        entries.append(
            ProductView.model_validate(
                {
                    "product": product,
                    "sources": evidence,
                    "availability": availability,
                    "availability_reasons": reasons,
                }
            )
        )
    return CatalogueView(
        version=catalogue.version,
        fingerprint=digest(catalogue.model_dump(mode="json")),
        as_of=as_of,
        review_window_days=catalogue.review_window_days,
        products=tuple(entries),
        limitations=LIMITATIONS,
    )


def match(
    profile: BusinessProfile, version: int, needs: BankingNeeds, catalogue: CatalogueView
) -> MatchResult:
    fingerprint = digest(
        {
            "algorithm": ALGORITHM_VERSION,
            "catalogue": catalogue.fingerprint,
            "as_of": catalogue.as_of.isoformat(),
            "profile_version": version,
            "profile": profile.model_dump(mode="json"),
            "needs": needs.model_dump(mode="json"),
        }
    )
    decisions = []
    confirmed = profile.confirmation_state == ConfirmationState.CONFIRMED
    if confirmed:
        for entry in catalogue.products:
            evaluations = []
            for rule in entry.product.rules:
                value = getattr(needs, rule.field)
                actual = value
                path = f"needs.{rule.field}"
                if (
                    rule.field == "financing_interest"
                    and value is None
                    and profile.funding
                    in (
                        Funding.LOAN,
                        Funding.MIXED,
                    )
                ):
                    value = True
                    actual = profile.funding.value
                    path = "profile.funding"
                status = (
                    "unknown"
                    if value is None
                    else ("matched" if value in rule.one_of else "not_matched")
                )
                evaluations.append(
                    RuleEvaluation.model_validate(
                        {
                            "rule": rule,
                            "status": status,
                            "actual_value": actual,
                            "evaluated_value": value,
                            "input_path": path,
                        }
                    )
                )
            missing = tuple(sorted(e.rule.field for e in evaluations if e.status == "unknown"))
            if entry.availability == "blocked":
                state = "unavailable"
                reasons = entry.availability_reasons
            elif any(e.status == "not_matched" for e in evaluations):
                state = "not_matched"
                reasons = tuple(
                    f"Условие потребности не выполнено: {e.rule.explanation}"
                    for e in evaluations
                    if e.status == "not_matched"
                )
            elif missing:
                state = "needs_clarification"
                reasons = tuple(e.rule.question for e in evaluations if e.status == "unknown")
            else:
                informational = entry.product.category == "financing_information"
                state = (
                    ("demo_information" if informational else "demo_match")
                    if (entry.availability == "demonstration_only")
                    else ("information_only" if informational else "potential_match")
                )
                reasons = tuple(
                    f"Ваши ответы соответствуют условию: {e.rule.explanation}" for e in evaluations
                )
            decisions.append(
                ProductDecision.model_validate(
                    {
                        "entry": entry,
                        "status": state,
                        "reasons": reasons,
                        "evaluations": evaluations,
                        "missing_fields": missing,
                    }
                )
            )
    return MatchResult(
        status="needs_confirmation"
        if not confirmed
        else (
            "catalogue_unavailable"
            if not any(e.availability != "blocked" for e in catalogue.products)
            else "evaluated"
        ),
        algorithm_version=ALGORITHM_VERSION,
        catalogue=catalogue,
        request_fingerprint=fingerprint,
        profile_snapshot=profile,
        profile_version=version,
        needs_snapshot=needs,
        decisions=tuple(decisions),
        recommended_ids=tuple(
            d.entry.product.id
            for d in decisions
            if d.status in ("potential_match", "information_only")
        ),
        demonstration_ids=tuple(
            d.entry.product.id for d in decisions if d.status in ("demo_match", "demo_information")
        ),
        missing_fields=tuple(
            sorted(
                {
                    f
                    for d in decisions
                    if d.status == "needs_clarification"
                    for f in d.missing_fields
                }
            )
        ),
        limitations=LIMITATIONS,
    )
