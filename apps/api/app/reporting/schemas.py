from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.api.schemas import BusinessProfile, Contract
from app.bank.schemas import MatchRequest, MatchResult
from app.data.schemas import IndicatorQuery, IndicatorResult
from app.finance.schemas import FinanceRequest, FinanceResult
from app.geo.candidate_schemas import Version
from app.geo.ranking_schemas import RankingCollection, RankingRequest
from app.geo.schemas import Slug
from app.geo.walk_schemas import CatchmentRequest, CatchmentResult
from app.limits.config import VersionNumber


class GeoReportInput(Contract):
    dataset: Slug
    request: RankingRequest
    fingerprint: Version


class FinanceReportInput(Contract):
    request: FinanceRequest
    fingerprint: Version


class BankReportInput(Contract):
    request: MatchRequest
    fingerprint: Version


class WalkReportInput(Contract):
    dataset: Slug
    request: CatchmentRequest
    fingerprint: Version


class ProviderReportInput(Contract):
    request: IndicatorQuery
    fingerprint: Version


class ReportRequest(Contract):
    expected_version: VersionNumber
    geo: GeoReportInput | None = None
    selected_zone: Version | None = None
    finance: FinanceReportInput | None = None
    bank: BankReportInput | None = None
    walking: WalkReportInput | None = None
    providers: tuple[ProviderReportInput, ...] = Field(default=(), max_length=3)


class ReportSnapshot(Contract):
    schema_version: Literal["business-ai-report-v1"] = "business-ai-report-v1"
    renderer_version: Literal["reportlab-dejavu-v1"] = "reportlab-dejavu-v1"
    id: UUID
    created_at: AwareDatetime
    profile_version: int
    profile_updated_at: AwareDatetime
    profile: BusinessProfile
    geo: RankingCollection | None
    selected_zone: str | None
    finance: FinanceResult | None
    bank: MatchResult | None
    walking: CatchmentResult | None
    providers: tuple[IndicatorResult, ...]
    summary: tuple[str, ...]
    missing_sections: tuple[str, ...]
    provenance_rules: tuple[str, ...] = (
        (
            "Profile parameters are user_input, source: confirm"
            "ed BusinessProfile, version: profile_version; date"
            ": profile_updated_at."
        ),
        (
            "Geo raw metrics inherit each evaluation.provenance"
            " (open_data); scores and zones are modelled, not p"
            "rofit forecasts."
        ),
        (
            "Financial results are modelled and link formula_id"
            "/input_paths to request_snapshot and formulas; eac"
            "h input carries source."
        ),
        (
            "Financial assumptions without generation dates wer"
            "e fixed at report.created_at, not independently ob"
            "served then."
        ),
        (
            "Provider values inherit dataset geography/license/"
            "quality and retain measurement.origin/version/date"
            "/unit."
        ),
        (
            "Bank catalogue sources and reviewed_at are informa"
            "tion only; credit_decision=not_assessed. No bank s"
            "ubmission occurs."
        ),
    )
    metric_units: dict[str, str] = Field(
        default_factory=lambda: {
            "profile.budget": "RUB",
            "geo.evaluations[].score": "points_0_100",
            "geo.evaluations[].components": "unit is declared by each component",
            "geo.evaluations[].raw.*_count": "mapped_features",
            "geo.evaluations[].raw.*_m": "m_geodesic_straight_line",
            "geo.evaluations[].raw.competitor_features_per_km2": "mapped_features/km2",
            "geo.candidates.features[].properties.area_m2": "m2",
            "walking.request_snapshot.distance_m": "m_network_including_modelled_connectors",
            "walking.*_poi_count": "mapped_features",
            "finance.startup,finance.budget": "RUB",
            "finance.request_snapshot.startup,monthly_fixed_costs": "RUB",
            "finance.request_snapshot.working_days_per_month": "days/month",
            "finance.request_snapshot.scenarios.*.average_check": "RUB/sale",
            "finance.request_snapshot.scenarios.*.sales_per_day": "sales/day",
            "finance.request_snapshot.scenarios.*.variable_cost_ratio": "fraction_0_1",
            "finance.scenarios[].metrics": "unit declared by each FinancialMetric",
            "finance.sensitivity.relative_change": "fraction",
            "finance.sensitivity.actual_value": "driver units: average_check=RUB/sale; "
            "sales_per_day=sales/day; rent=RUB/month; variable_cost_ratio=fraction",
            "finance.sensitivity.operating_result,difference_from_base": "RUB/month",
            "finance.sensitivity.break_even_sales_per_day": "sales/day",
        }
    )
    limitations: tuple[str, ...] = (
        (
            "Географические зоны не являются свободными помещен"
            "иями; OSM-score не прогнозирует прибыль."
        ),
        "Синтетические вводные и провайдерские значения не являются рынком Казани.",
        "Операционный результат не является чистой прибылью или денежным потоком.",
        "Экспорт не отправляет заявку или данные в ВТБ и не подтверждает кредитное одобрение.",
    )


class ReportView(Contract):
    id: UUID
    created_at: AwareDatetime
    profile_version: int
    snapshot_sha256: Version
    pdf_sha256: Version
    status: Literal["current", "outdated"]
    reasons: tuple[str, ...]
    missing_sections: tuple[str, ...]
    json_bytes: int
    pdf_bytes: int
