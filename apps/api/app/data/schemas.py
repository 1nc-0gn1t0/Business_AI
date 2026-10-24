from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from app.api.schemas import Contract, MetricWithProvenance, NonEmptyText
from app.domain.enums import DataOrigin
from app.geo.schemas import Bounds, Slug

ProviderId = Literal["osm", "synthetic", "ghsl", "licensed"]
DataMode = Literal["real", "demo"]
Version = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
METRICS = {
    "mapped_poi_count": ("Нанесённые объекты OSM", "features"),
    "mapped_cafe_count": ("Нанесённые кафе OSM", "features"),
    "pedestrian_flow_daily": ("Условный пешеходный поток", "people_per_day"),
    "rent_monthly_rub": ("Условная месячная аренда", "RUB_per_month"),
    "purchases_daily": ("Сценарное количество покупок", "purchases_per_day"),
}


class DataSelection(Contract):
    mode: DataMode = "real"


class DataPolicy(Contract):
    version: Literal["explicit-provider-v1"] = "explicit-provider-v1"
    mode: DataMode
    demo_enabled: bool
    allowed_providers: tuple[ProviderId, ...]
    limitations: tuple[str, ...]


class ProviderInfo(Contract):
    id: ProviderId
    name: str
    origin: DataOrigin
    status: Literal["ready", "disabled", "not_integrated"]
    limitations: tuple[str, ...]


class ProviderDataset(Contract):
    provider: ProviderId
    slug: Slug
    revision: str
    data_version: Version
    active: bool
    bbox: Bounds
    origin: DataOrigin
    source_name: str
    source_url: str | None
    license: str
    attribution: str
    observed_at: AwareDatetime | None
    generated_at: AwareDatetime
    stale: bool
    stale_after_days: int
    quality: Literal["mapping_completeness_unknown", "not_applicable"]
    limitations: tuple[str, ...]


class Indicator(Contract):
    metric: str
    name: str
    value_type: Literal["number"] = "number"
    unit: str
    status: Literal["available", "stale", "missing", "outside_coverage"]
    measurement: MetricWithProvenance | None
    reason: str | None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.status in {"available", "stale"}) != (self.measurement is not None):
            raise ValueError("Only available/stale indicators have a measurement")
        if self.measurement and (
            self.measurement.metric != self.metric or self.measurement.unit != self.unit
        ):
            raise ValueError("Indicator and provenance must identify the same metric/unit")
        if self.status != "available" and not self.reason:
            raise ValueError("Missing/stale indicators require an explanation")
        return self


class IndicatorQuery(Contract):
    provider: ProviderId
    dataset: Slug
    data_version: Version
    mode: DataMode = "real"
    bbox: Bounds | None = None
    metrics: tuple[NonEmptyText, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def known_metrics(self) -> Self:
        if len(set(self.metrics)) != len(self.metrics) or any(
            m not in METRICS for m in self.metrics
        ):
            raise ValueError("Select distinct supported metric identifiers")
        return self


class IndicatorResult(Contract):
    dataset: ProviderDataset
    selection: DataPolicy
    bbox: Bounds
    indicators: tuple[Indicator, ...]
    algorithm_version: str
    request_fingerprint: Version
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def consistent_source(self) -> Self:
        for indicator in self.indicators:
            measurement = indicator.measurement
            if measurement and (
                measurement.origin != self.dataset.origin
                or measurement.data_version != self.dataset.data_version
                or measurement.source_name != self.dataset.source_name
            ):
                raise ValueError("A result cannot mix origins, sources or dataset versions")
        if self.dataset.origin == DataOrigin.SYNTHETIC and self.selection.mode != "demo":
            raise ValueError("Synthetic results require explicit demo selection")
        return self


class SyntheticDataset(Contract):
    schema_version: Literal[1] = 1
    slug: Slug
    revision: NonEmptyText
    origin: Literal[DataOrigin.SYNTHETIC] = DataOrigin.SYNTHETIC
    source_name: NonEmptyText
    generated_at: AwareDatetime
    bbox: Bounds
    license: Literal["CC0-1.0"] = "CC0-1.0"
    attribution: Literal["Sab0tage — synthetic demonstration"]
    generation_method: Literal["fixed-authored-scenario-v1"]
    limitations: tuple[NonEmptyText, ...] = Field(min_length=1)
    measurements: tuple[MetricWithProvenance, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def only_synthetic(self) -> Self:
        names = [m.metric for m in self.measurements]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate metrics")
        for m in self.measurements:
            if (
                m.metric not in {"pedestrian_flow_daily", "rent_monthly_rub", "purchases_daily"}
                or m.unit != METRICS[m.metric][1]
                or m.origin != DataOrigin.SYNTHETIC
                or m.observed_at is not None
                or m.generated_at != self.generated_at
                or m.data_version != self.revision
                or m.source_name != self.source_name
                or m.value < 0
            ):
                raise ValueError("Synthetic scenario provenance/unit/value mismatch")
        return self
