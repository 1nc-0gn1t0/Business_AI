import hashlib
import os
from datetime import UTC, datetime
from typing import Literal, Protocol

import sqlalchemy as sa
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.schemas import MetricWithProvenance
from app.data.importer import dataset_hash
from app.data.schemas import (
    METRICS,
    DataMode,
    DataPolicy,
    Indicator,
    IndicatorQuery,
    IndicatorResult,
    ProviderDataset,
    ProviderId,
    ProviderInfo,
    SyntheticDataset,
)
from app.db.models import GeoDatasetRecord, ProviderDatasetRecord
from app.domain.enums import Confidence, DataOrigin
from app.geo.schemas import Bounds
from app.geo.service import LIMITATIONS

VERSION = "provider-indicators-v1"
DEMO_LIMITATIONS = (
    "Синтетический сценарий: не измерения рынка Казани и не сведения о свободном помещении.",
    "Показатели не передаются автоматически в рейтинг, catchment или финансовый расчёт.",
)


def demo_enabled() -> bool:
    return os.environ.get("DATA_DEMO_ENABLED", "false").lower() == "true"


def policy(mode: DataMode) -> DataPolicy:
    enabled = demo_enabled()
    if mode == "demo" and not enabled:
        raise HTTPException(403, detail={"code": "demo_data_disabled"})
    return DataPolicy(
        mode=mode,
        demo_enabled=enabled,
        allowed_providers=("osm", "synthetic") if mode == "demo" else ("osm",),
        limitations=(
            "Источник и версия выбираются явно; автоматической подмены данных нет.",
            *DEMO_LIMITATIONS,
        ),
    )


class DataProvider(Protocol):
    def datasets(self, session: Session) -> list[ProviderDataset]: ...
    def read(self, session: Session, request: IndicatorQuery) -> IndicatorResult: ...


def result(
    metadata: ProviderDataset,
    request: IndicatorQuery,
    values: dict[str, MetricWithProvenance],
    method: str,
    outside: bool = False,
) -> IndicatorResult:
    bounds = request.bbox or metadata.bbox
    indicators = []
    for key in request.metrics:
        value = None if outside else values.get(key)
        status: Literal["available", "stale", "missing", "outside_coverage"] = (
            "outside_coverage"
            if outside
            else "missing"
            if value is None
            else "stale"
            if metadata.stale
            else "available"
        )
        reason = {
            "outside_coverage": "Область не поддерживается набором; экстраполяция запрещена.",
            "missing": "Показатель отсутствует. Синтетическая подмена не выполняется.",
            "stale": "Превышен срок пересмотра источника; значение сохранено с предупреждением.",
            "available": None,
        }[status]
        indicators.append(
            Indicator(
                metric=key,
                name=METRICS[key][0],
                unit=METRICS[key][1],
                status=status,
                measurement=value,
                reason=reason,
            )
        )
    canonical = request.model_copy(update={"bbox": bounds}).model_dump_json()
    fingerprint = hashlib.sha256((VERSION + method + canonical).encode()).hexdigest()
    return IndicatorResult(
        dataset=metadata,
        selection=policy(request.mode),
        bbox=bounds,
        indicators=tuple(indicators),
        algorithm_version=VERSION + ":" + method,
        request_fingerprint=fingerprint,
        limitations=metadata.limitations,
    )


class OSMProvider:
    @staticmethod
    def metadata(record: GeoDatasetRecord) -> ProviderDataset:
        return ProviderDataset(
            provider="osm",
            slug=record.slug,
            revision=record.data_version,
            data_version=record.data_version,
            active=record.active,
            bbox=Bounds.model_validate(record.bbox),
            origin=DataOrigin.OPEN_DATA,
            source_name="OpenStreetMap via Overpass API",
            source_url=record.source_url,
            license="ODbL-1.0",
            attribution="© OpenStreetMap contributors",
            observed_at=record.osm_base,
            generated_at=record.fetched_at,
            stale=(datetime.now(UTC) - record.osm_base).days > 30,
            stale_after_days=30,
            quality="mapping_completeness_unknown",
            limitations=tuple(LIMITATIONS),
        )

    def datasets(self, session: Session) -> list[ProviderDataset]:
        return [
            self.metadata(r)
            for r in session.scalars(
                sa.select(GeoDatasetRecord).order_by(
                    GeoDatasetRecord.slug,
                    GeoDatasetRecord.imported_at.desc(),
                    GeoDatasetRecord.data_version,
                )
            )
        ]

    def read(self, session: Session, request: IndicatorQuery) -> IndicatorResult:
        record = session.scalar(
            sa.select(GeoDatasetRecord).where(
                GeoDatasetRecord.slug == request.dataset,
                GeoDatasetRecord.data_version == request.data_version,
            )
        )
        if record is None:
            raise HTTPException(409, detail={"code": "provider_version_not_found"})
        metadata = self.metadata(record)
        b = request.bbox or metadata.bbox
        if not (
            metadata.bbox.contains(b.west, b.south) and metadata.bbox.contains(b.east, b.north)
        ):
            return result(metadata, request, {}, "osm-bbox-count-v1", outside=True)
        row = (
            session.execute(
                sa.text("""SELECT count(*) AS poi,
            count(*) FILTER (WHERE categories @> ARRAY['amenity:cafe']::text[]) AS cafe
            FROM geo_pois WHERE dataset_id=:id
            AND geom && ST_MakeEnvelope(:west,:south,:east,:north,4326)"""),
                {"id": record.id, **b.model_dump()},
            )
            .mappings()
            .one()
        )
        values = {}
        for key, count in (("mapped_poi_count", row["poi"]), ("mapped_cafe_count", row["cafe"])):
            values[key] = MetricWithProvenance(
                metric=key,
                value=float(count),
                unit="features",
                origin=DataOrigin.OPEN_DATA,
                source_name=metadata.source_name,
                observed_at=record.osm_base,
                generated_at=datetime.now(UTC),
                data_version=record.data_version,
                confidence=Confidence.LOW,
                limitations=metadata.limitations
                + (
                    "Count of mapped OSM features, not traffic or verified businesses; "
                    "osm_base is snapshot/edit time, not a field observation.",
                ),
            )
        return result(metadata, request, values, "osm-bbox-count-v1")


class SyntheticProvider:
    @staticmethod
    def metadata(record: ProviderDatasetRecord) -> ProviderDataset:
        try:
            data = SyntheticDataset.model_validate(record.document)
        except ValidationError:
            raise HTTPException(503, detail={"code": "provider_dataset_invalid"}) from None
        if (
            dataset_hash(data) != record.data_version
            or data.slug != record.slug
            or data.revision != record.revision
        ):
            raise HTTPException(503, detail={"code": "provider_dataset_invalid"})
        return ProviderDataset(
            provider="synthetic",
            slug=data.slug,
            revision=data.revision,
            data_version=record.data_version,
            active=record.active,
            bbox=data.bbox,
            origin=DataOrigin.SYNTHETIC,
            source_name=data.source_name,
            source_url=None,
            license=data.license,
            attribution=data.attribution,
            observed_at=None,
            generated_at=data.generated_at,
            stale=(datetime.now(UTC) - data.generated_at).days > 365,
            stale_after_days=365,
            quality="not_applicable",
            limitations=(
                *data.limitations,
                "Generation: " + data.generation_method,
                *DEMO_LIMITATIONS,
            ),
        )

    def datasets(self, session: Session) -> list[ProviderDataset]:
        if not demo_enabled():
            return []
        return [
            self.metadata(r)
            for r in session.scalars(
                sa.select(ProviderDatasetRecord)
                .where(ProviderDatasetRecord.provider == "synthetic")
                .order_by(
                    ProviderDatasetRecord.slug,
                    ProviderDatasetRecord.imported_at.desc(),
                    ProviderDatasetRecord.data_version,
                )
            )
        ]

    def read(self, session: Session, request: IndicatorQuery) -> IndicatorResult:
        if request.mode != "demo" or not demo_enabled():
            raise HTTPException(403, detail={"code": "demo_data_disabled"})
        record = session.get(
            ProviderDatasetRecord, ("synthetic", request.dataset, request.data_version)
        )
        if record is None:
            raise HTTPException(409, detail={"code": "provider_version_not_found"})
        metadata = self.metadata(record)
        data = SyntheticDataset.model_validate(record.document)
        # Scenario values refer to this entire fictional extent; never interpolate or rescale.
        outside = request.bbox is not None and request.bbox != data.bbox
        values = {
            m.metric: MetricWithProvenance.model_validate(
                m.model_dump() | {"data_version": record.data_version}
            )
            for m in data.measurements
        }
        return result(metadata, request, values, data.generation_method, outside)


class UnavailableProvider:
    def datasets(self, session: Session) -> list[ProviderDataset]:
        return []

    def read(self, session: Session, request: IndicatorQuery) -> IndicatorResult:
        raise HTTPException(503, detail={"code": "provider_not_integrated"})


class GHSLProvider(UnavailableProvider):
    """Future verified population raster adapter. No verified local dataset yet."""


class LicensedProvider(UnavailableProvider):
    """Future contract-authorized adapter. No credentials, scraping or bank integration."""


def providers() -> dict[ProviderId, DataProvider]:
    return {
        "osm": OSMProvider(),
        "synthetic": SyntheticProvider(),
        "ghsl": GHSLProvider(),
        "licensed": LicensedProvider(),
    }


def sources() -> list[ProviderInfo]:
    return [
        ProviderInfo(
            id="osm",
            name="OpenStreetMap",
            origin=DataOrigin.OPEN_DATA,
            status="ready",
            limitations=("Только ранее импортированные данные; полнота картирования неизвестна.",),
        ),
        ProviderInfo(
            id="synthetic",
            name="Синтетический сценарий кофейни",
            origin=DataOrigin.SYNTHETIC,
            status="ready" if demo_enabled() else "disabled",
            limitations=DEMO_LIMITATIONS,
        ),
        ProviderInfo(
            id="ghsl",
            name="GHSL — будущий адаптер",
            origin=DataOrigin.MODELLED,
            status="not_integrated",
            limitations=(
                "Набор не загружен; модельное население не является потоком покупателей.",
            ),
        ),
        ProviderInfo(
            id="licensed",
            name="Лицензированные источники — будущий контракт",
            origin=DataOrigin.LICENSED,
            status="not_integrated",
            limitations=("Нет договора и интеграции; коммерческие API не вызываются.",),
        ),
    ]
