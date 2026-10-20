from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.schemas import AnalysisRun, BusinessProfile, MetricWithProvenance
from app.domain.enums import Confidence, DataOrigin


@pytest.fixture
def metric_payload() -> dict[str, Any]:
    return {
        "metric": "pedestrian_flow_daily",
        "value": 1800,
        "unit": "people_per_day",
        "origin": "synthetic",
        "source_name": "contract_test_seed",
        "observed_at": None,
        "generated_at": "2026-10-19T00:00:00Z",
        "data_version": "test-1",
        "confidence": "not_applicable",
        "limitations": ["Synthetic test value, not measured traffic"],
    }


@pytest.mark.parametrize("origin", list(DataOrigin))
def test_every_origin_survives_json_round_trip(
    metric_payload: dict[str, Any], origin: DataOrigin
) -> None:
    metric_payload["origin"] = origin.value
    metric = MetricWithProvenance.model_validate(metric_payload)
    restored = MetricWithProvenance.model_validate_json(metric.model_dump_json())
    assert restored == metric
    assert restored.origin == origin


@pytest.mark.parametrize(
    "field",
    [
        "origin",
        "source_name",
        "observed_at",
        "generated_at",
        "data_version",
        "confidence",
        "limitations",
    ],
)
def test_provenance_fields_are_required(metric_payload: dict[str, Any], field: str) -> None:
    del metric_payload[field]
    with pytest.raises(ValidationError):
        MetricWithProvenance.model_validate(metric_payload)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("origin", "real"),
        ("origin", None),
        ("source_name", "  "),
        ("data_version", ""),
        ("metric", "\t"),
        ("unit", ""),
        ("value", float("nan")),
        ("value", float("inf")),
        ("value", float("-inf")),
        ("value", True),
        ("value", "1800"),
        ("generated_at", "2026-10-19T00:00:00"),
        ("observed_at", "2026-10-20T00:00:00Z"),
        ("limitations", []),
        ("limitations", [""]),
        ("confidence", "high"),
        ("undeclared_source", "test"),
    ],
)
def test_invalid_metrics_are_rejected(
    metric_payload: dict[str, Any],
    field: str,
    invalid: Any,
) -> None:
    metric_payload[field] = invalid
    with pytest.raises(ValidationError):
        MetricWithProvenance.model_validate(metric_payload)


def test_synthetic_origin_cannot_be_assigned_away(metric_payload: dict[str, Any]) -> None:
    metric = MetricWithProvenance.model_validate(metric_payload)
    with pytest.raises(ValidationError, match="frozen"):
        metric.origin = DataOrigin.OPEN_DATA
    assert metric.origin == DataOrigin.SYNTHETIC
    assert metric.confidence == Confidence.NOT_APPLICABLE


def test_metric_contract_returns_422_when_used_by_fastapi(metric_payload: dict[str, Any]) -> None:
    # A test-only route checks FastAPI integration; BA-003 adds no product endpoint.
    app = FastAPI()

    @app.post("/metric")
    def validate_metric(metric: MetricWithProvenance) -> MetricWithProvenance:
        return metric

    with TestClient(app) as client:
        assert client.post("/metric", json=metric_payload).status_code == 200
        for field in ("origin", "source_name"):
            incomplete = {k: v for k, v in metric_payload.items() if k != field}
            response = client.post("/metric", json=incomplete)
            assert response.status_code == 422
            assert response.json()["detail"][0]["loc"] == ["body", field]
        schema = client.get("/openapi.json").json()["components"]["schemas"]["MetricWithProvenance"]
        assert {"origin", "source_name"} <= set(schema["required"])


def test_profile_snapshot_preserves_money_and_optional_fields() -> None:
    profile = BusinessProfile(conversation_id=uuid4(), budget=Decimal("2000000.10"))
    run = AnalysisRun(
        profile_snapshot=profile,
        dataset_versions={"test_seed": "v1"},
        algorithm_version="test-v1",
        tool_trace_id=uuid4(),
    )
    restored = AnalysisRun.model_validate_json(run.model_dump_json())
    assert restored.profile_snapshot.budget == Decimal("2000000.10")
    assert restored.profile_snapshot.city is None
    assert restored.created_at.tzinfo is not None


@pytest.mark.parametrize("budget", ["-1", "NaN", "Infinity", "0.001", "10000000000000000"])
def test_invalid_budget_is_rejected(budget: str) -> None:
    with pytest.raises(ValidationError):
        BusinessProfile.model_validate({"conversation_id": str(uuid4()), "budget": budget})


@pytest.mark.parametrize("versions", [{}, {"": "v1"}, {"seed": " "}])
def test_analysis_requires_dataset_versions(versions: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        AnalysisRun(
            profile_snapshot=BusinessProfile(conversation_id=uuid4()),
            dataset_versions=versions,
            algorithm_version="v1",
            tool_trace_id=uuid4(),
        )
