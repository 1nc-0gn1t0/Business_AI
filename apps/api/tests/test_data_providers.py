import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.data.importer import dataset_hash
from app.data.schemas import Indicator, IndicatorQuery, IndicatorResult, SyntheticDataset

SEED = Path(__file__).resolve().parents[3] / "data/synthetic/coffee-kazan-v1.json"


def test_synthetic_contract_is_reproducible_and_cannot_change_origin() -> None:
    first = SyntheticDataset.model_validate_json(SEED.read_bytes())
    assert first == SyntheticDataset.model_validate_json(SEED.read_bytes())
    data = first.model_dump(mode="json")
    data["measurements"][0]["origin"] = "open_data"
    with pytest.raises(ValidationError):
        SyntheticDataset.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("value", -1),
        ("unit", "USD"),
        ("observed_at", "2026-10-23T00:00:00Z"),
        ("data_version", "other"),
    ],
)
def test_import_rejects_inconsistent_measurements(field: str, value: object) -> None:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    data["measurements"][0][field] = value
    with pytest.raises(ValidationError):
        SyntheticDataset.model_validate(data)


def test_missing_indicator_cannot_have_value_or_silently_imply_zero() -> None:
    with pytest.raises(ValidationError):
        Indicator(
            metric="mapped_poi_count",
            name="POI",
            unit="features",
            status="available",
            measurement=None,
            reason=None,
        )
    with pytest.raises(ValidationError):
        IndicatorQuery(
            provider="osm", dataset="kazan", data_version="a" * 64, metrics=("invented_demand",)
        )


@pytest.mark.parametrize("mutation", ["origin", "version", "mode"])
def test_result_rejects_mixed_provenance_or_implicit_demo(mutation: str) -> None:
    seed = SyntheticDataset.model_validate_json(SEED.read_bytes())
    version = dataset_hash(seed)
    measurement = seed.measurements[0].model_dump(mode="json") | {"data_version": version}
    if mutation == "origin":
        measurement["origin"] = "open_data"
    if mutation == "version":
        measurement["data_version"] = "b" * 64
    data = {
        "dataset": {
            "provider": "synthetic",
            "slug": seed.slug,
            "revision": seed.revision,
            "data_version": version,
            "active": True,
            "bbox": seed.bbox.model_dump(),
            "origin": "synthetic",
            "source_name": seed.source_name,
            "source_url": None,
            "license": seed.license,
            "attribution": seed.attribution,
            "observed_at": None,
            "generated_at": seed.generated_at,
            "stale": False,
            "stale_after_days": 365,
            "quality": "not_applicable",
            "limitations": seed.limitations,
        },
        "selection": {
            "mode": "real" if mutation == "mode" else "demo",
            "demo_enabled": True,
            "allowed_providers": ["osm", "synthetic"],
            "limitations": [],
        },
        "bbox": seed.bbox.model_dump(),
        "indicators": [
            {
                "metric": measurement["metric"],
                "name": "Test",
                "unit": measurement["unit"],
                "status": "available",
                "measurement": measurement,
                "reason": None,
            }
        ],
        "algorithm_version": "test-v1",
        "request_fingerprint": "a" * 64,
        "limitations": [],
    }
    with pytest.raises(ValidationError):
        IndicatorResult.model_validate(data)
