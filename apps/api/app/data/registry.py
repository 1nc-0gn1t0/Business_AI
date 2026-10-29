"""One operator-configured registry, also projected to the unchanged v1 source list."""

import hashlib
import os
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError

from app.data.registry_schemas import (
    AcquisitionOption,
    Freshness,
    FreshnessPolicy,
    RegistryConfig,
    SourceDefinition,
)


@lru_cache
def load_registry() -> RegistryConfig:
    path = Path(os.getenv("BA_DATA_REGISTRY_PATH", str(Path(__file__).with_name("registry.json"))))
    try:
        if path.stat().st_size > 131072:
            raise ValueError
        return RegistryConfig.model_validate_json(path.read_bytes())
    except (OSError, ValueError, ValidationError):
        raise HTTPException(503, detail={"code": "data_registry_invalid"}) from None


def config_hash(registry: RegistryConfig) -> str:
    return hashlib.sha256(registry.model_dump_json().encode()).hexdigest()


def source_definition(registry: RegistryConfig, source_id: str) -> SourceDefinition:
    source = next((s for s in registry.sources if s.id == source_id), None)
    if source is None:
        raise HTTPException(404, detail={"code": "data_source_not_found"})
    return source


def freshness(
    policy: FreshnessPolicy,
    now: datetime,
    source_time: datetime | None,
    generated_at: datetime | None,
    period_end: datetime | None = None,
) -> Freshness:
    stamp = {
        "source_timestamp": source_time,
        "generated_at": generated_at,
        "period_end": period_end,
        "unknown": None,
    }[policy.basis]
    if stamp is None or stamp > now or policy.max_age_days is None:
        return "unknown"
    return "stale" if now - stamp > timedelta(days=policy.max_age_days) else "current"


def permitted(source: SourceDefinition, purpose: str) -> bool:
    return source.license_status == "verified_local_use" and purpose in source.allowed_uses


def acquisition(
    source: SourceDefinition, purpose: str, category: str | None = None
) -> AcquisitionOption:
    status = "unknown"
    reason = "permission_or_remote_availability_unknown"
    if source.license_status == "forbidden" or source.network_permission == "forbidden":
        status, reason = "forbidden", "source_use_not_permitted"
    elif source.license_status == "review_required":
        status, reason = "unknown", "source_license_review_required"
    elif not permitted(source, purpose):
        status, reason = "forbidden", "source_use_not_permitted"
    elif source.adapter_status == "not_integrated":
        status, reason = "not_integrated", "adapter_not_integrated"
    elif source.availability == "unavailable":
        status, reason = "unavailable", "source_unavailable"
    elif (
        source.network_permission == "permitted"
        and source.availability in {"ready", "degraded"}
        and "operator_fetch" in source.acquisition_methods
    ):
        status, reason = "permitted", "operator_acquisition_permitted"
    return AcquisitionOption.model_validate(
        {
            "source_id": source.id,
            "acquirability": status,
            "reason": reason,
            "network_permission": source.network_permission,
            "availability": source.availability,
            "potentially_available": "operator_fetch" in source.acquisition_methods,
            "adapter_status": source.adapter_status,
            "license_status": source.license_status,
            "local_use_permitted": permitted(source, purpose),
            "automatic_acquisition_implemented": source.id == "osm"
            and category == "geo.mapped_poi",
        }
    )
