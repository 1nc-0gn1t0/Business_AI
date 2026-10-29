import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.data.coverage import LocalDataset, assess, assess_sufficiency, sufficiency
from app.data.registry import acquisition, config_hash, freshness, load_registry, source_definition
from app.data.registry_schemas import (
    CoverageQuery,
    CoverageResult,
    DataRequirement,
    FreshnessPolicy,
    RegistryConfig,
)
from app.data.schemas import ProviderDataset
from app.domain.enums import DataOrigin
from app.geo.schemas import Bounds
from app.main import app

NOW = datetime(2026, 10, 29, tzinfo=UTC)
BOX = Bounds(west=49.11, south=55.78, east=49.12, north=55.79)
QUERY = CoverageQuery(territory="ru-kazan", categories=("geo.mapped_poi",))
CONFIG = Path(__file__).parents[1] / "app/data/registry.json"


def registry() -> RegistryConfig:
    return RegistryConfig.model_validate_json(CONFIG.read_bytes())


def dataset(days: int = 0, origin: DataOrigin = DataOrigin.OPEN_DATA) -> LocalDataset:
    scenario = origin == DataOrigin.SYNTHETIC
    return LocalDataset(
        ProviderDataset(
            provider="synthetic" if scenario else "osm",
            slug="test-fixture",
            revision="test-v1",
            data_version="a" * 64,
            active=True,
            bbox=BOX,
            origin=origin,
            source_name="Synthetic test fixture" if scenario else "Test mapped context",
            source_url="https://private.invalid/token",
            license="CC0-1.0" if scenario else "ODbL-1.0",
            attribution="Test only",
            observed_at=None if scenario else NOW - timedelta(days=days),
            generated_at=NOW - timedelta(days=days),
            stale=False,
            stale_after_days=30,
            quality="not_applicable" if scenario else "mapping_completeness_unknown",
            limitations=("Test only",),
        ),
        "Казань",
        ("scenario.finance",) if scenario else ("geo.mapped_poi",),
    )


def check(
    query: CoverageQuery = QUERY,
    data: list[LocalDataset] | None = None,
    fit: str = "full_for_requested_scope",
    complete: bool = True,
    cfg: RegistryConfig | None = None,
) -> CoverageResult:
    return assess(query, cfg or registry(), data or [], complete, {0: fit}, NOW)


def test_catalog_reuses_provider_ids_without_industry_or_network_execution() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v2/data-registry")
        assert response.status_code == 200
        body = response.json()
        assert len(body["sources"]) == 4
        assert any(c["id"] == "user.budget" for c in body["categories"])
        assert "source_url" not in response.text and "base_url" not in response.text
        assert response.headers["X-Request-ID"]
        assert {s["id"] for s in client.get("/api/v1/data-providers/sources").json()} == {
            s["id"] for s in body["sources"]
        }


def test_given_requirements_gate_operations_without_a_planner() -> None:
    result = check(QUERY.model_copy(update={"aoi": BOX}), [dataset()])
    needs = (
        DataRequirement(
            id="mapped",
            category="geo.mapped_poi",
            critical_for=("mapped-context", "vehicle-analysis"),
        ),
        DataRequirement(
            id="roads", category="geo.vehicle_network", critical_for=("vehicle-analysis",)
        ),
        DataRequirement(
            id="optional", category="user.budget", required=False, critical_for=("mapped-context",)
        ),
    )
    assessed = assess_sufficiency(needs, result, "test-requirements-v1")
    assert assessed.allowed_tasks == ("mapped-context",)
    assert assessed.blocked_tasks == ("vehicle-analysis",)
    assert assessed.decisions[0].quality == "unknown"


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_source",
        "duplicate_category",
        "bad_policy",
        "fake_adapter",
        "relabel_scenario",
        "alias",
    ],
)
def test_registry_rejects_conflicts_and_unimplemented_claims(mutation: str) -> None:
    data = json.loads(CONFIG.read_text(encoding="utf8"))
    if mutation == "duplicate_source":
        data["sources"].append(data["sources"][0])
    elif mutation == "duplicate_category":
        data["categories"].append(data["categories"][0])
    elif mutation == "bad_policy":
        data["sources"][0]["freshness_policies"]["geo.mapped_poi"] = "invented"
    elif mutation == "fake_adapter":
        data["sources"][0]["adapter_id"] = "run_shell"
    elif mutation == "relabel_scenario":
        data["sources"][1]["origin"] = "open_data"
    else:
        data["territories"][1]["aliases"].append("Казань")
    with pytest.raises(ValidationError):
        RegistryConfig.model_validate(data)


def test_extensible_categories_and_source_ids_are_not_a_closed_industry_list() -> None:
    data = registry().model_dump(mode="json")
    data["categories"].append(
        dict(id="science.other", name="Other lawful data", spatial=False, unit="indicator")
    )
    source = data["sources"][3] | {
        "id": "new-source",
        "categories": ["science.other"],
        "freshness_policies": {"science.other": "unreviewed"},
    }
    data["sources"].append(source)
    cfg = RegistryConfig.model_validate(data)
    result = check(CoverageQuery(categories=("science.other",)), cfg=cfg)
    assert result.assessments[0].local_status == "missing"
    assert config_hash(cfg) != config_hash(registry())


def test_unknown_source_does_not_resolve_to_an_existing_provider() -> None:
    assert source_definition(registry(), "osm").adapter_id == "osm"
    with pytest.raises(HTTPException) as error:
        source_definition(registry(), "unknown-source")
    assert error.value.status_code == 404


@pytest.mark.parametrize(
    "days,expected", [(0, "current"), (30, "current"), (31, "stale"), (-1, "unknown")]
)
def test_freshness_boundary_and_future_clock(days: int, expected: str) -> None:
    p = registry().policies[0]
    assert freshness(p, NOW, NOW - timedelta(days=days), NOW) == expected


def test_download_today_does_not_make_unknown_measurement_fresh() -> None:
    p = FreshnessPolicy(
        id="observation-needed", basis="source_timestamp", max_age_days=1, rationale="Test"
    )
    assert freshness(p, NOW, None, NOW) == "unknown"
    p = p.model_copy(update={"basis": "period_end"})
    assert freshness(p, NOW, NOW, NOW, None) == "unknown"
    assert freshness(p, NOW, None, NOW, NOW - timedelta(days=2)) == "stale"


def test_snapshot_date_does_not_attest_a_whole_observation_period() -> None:
    body = QUERY.model_dump() | {
        "aoi": BOX,
        "period": {
            "start": NOW - timedelta(days=1),
            "end": NOW + timedelta(days=1),
        },
    }
    interval = check(CoverageQuery.model_validate(body), [dataset()]).assessments[0]
    assert interval.local_status == "unknown" and not interval.datasets[0].usable
    body["period"]["kind"] = "snapshot_window"
    window = check(CoverageQuery.model_validate(body), [dataset()]).assessments[0]
    assert window.local_status == "available"


@pytest.mark.parametrize(
    "fit,days,expected",
    [
        ("full_for_requested_scope", 0, "available"),
        ("full_for_requested_scope", 31, "stale"),
        ("partial", 0, "partial"),
        ("partial", 31, "partial"),
        ("unknown", 0, "unknown"),
    ],
)
def test_orthogonal_coverage_states(fit: str, days: int, expected: str) -> None:
    result = check(QUERY.model_copy(update={"aoi": BOX}), [dataset(days)], fit).assessments[0]
    assert result.local_status == expected
    assert result.datasets[0].observed_at is None
    assert result.datasets[0].source_timestamp == NOW - timedelta(days=days)
    assert "source_url" not in result.datasets[0].metadata.model_dump()
    if days == 31:
        assert result.freshness == "stale"


def test_city_without_boundary_is_partial_and_moscow_without_import_missing() -> None:
    assert check(data=[dataset()]).assessments[0].local_status == "partial"
    moscow = check(QUERY.model_copy(update={"territory": "ru-moscow"}), [dataset()]).assessments[0]
    assert moscow.local_status == "missing" and not moscow.datasets
    assert moscow.acquisition[0].potentially_available
    assert moscow.acquisition[0].acquirability == "unknown"
    assert check(complete=False).assessments[0].local_status == "unknown"


def test_online_private_inputs_and_unknown_territory_do_not_invent_coverage() -> None:
    online = check(CoverageQuery(categories=("user.budget", "user.costs")))
    assert all(a.local_status == "unknown" for a in online.assessments)
    assert all("private_inputs_not_in_public_catalog" in a.reasons for a in online.assessments)
    assert (
        check(QUERY.model_copy(update={"territory": "unknown-city"})).assessments[0].local_status
        == "unknown"
    )


def test_unreviewed_license_forbids_use_even_when_local_data_exists() -> None:
    data = registry().model_dump(mode="json")
    data["sources"][0]["license_status"] = "review_required"
    result = check(
        QUERY.model_copy(update={"aoi": BOX}), [dataset()], cfg=RegistryConfig.model_validate(data)
    )
    assert not result.assessments[0].datasets[0].usable
    assert not sufficiency((DataRequirement(id="r", category="geo.mapped_poi"),), result)[
        0
    ].technically_eligible


@pytest.mark.parametrize(
    "network,availability,expected",
    [
        ("permitted", "ready", "permitted"),
        ("permitted", "unavailable", "unavailable"),
        ("forbidden", "ready", "forbidden"),
        ("review_required", "ready", "unknown"),
    ],
)
def test_source_permission_and_availability_are_distinct(
    network: str, availability: str, expected: str
) -> None:
    source = (
        registry()
        .sources[0]
        .model_copy(update={"network_permission": network, "availability": availability})
    )
    assert acquisition(source, "local_analysis").acquirability == expected


def test_offline_source_does_not_hide_usable_cache() -> None:
    cfg = registry().model_dump(mode="json")
    cfg["sources"][0]["availability"] = "unavailable"
    result = check(
        QUERY.model_copy(update={"aoi": BOX}), [dataset()], cfg=RegistryConfig.model_validate(cfg)
    ).assessments[0]
    assert result.summary == "usable"
    assert result.acquisition[0].acquirability == "unavailable"


def test_sufficiency_not_quality_or_market_validity_and_scenario_review_is_not_observation() -> (
    None
):
    result = check(QUERY.model_copy(update={"aoi": BOX}), [dataset()])
    requirement = DataRequirement(id="r", category="geo.mapped_poi")
    assert sufficiency((requirement,), result)[0].technically_eligible
    assert not sufficiency(
        (requirement.model_copy(update={"require_known_quality": True}),), result
    )[0].technically_eligible
    scenario = check(
        CoverageQuery(categories=("scenario.finance",), mode="demo"),
        [dataset(origin=DataOrigin.SYNTHETIC)],
    )
    decision = sufficiency(
        (
            DataRequirement(
                id="s",
                category="scenario.finance",
                accepted_origins=(DataOrigin.SYNTHETIC,),
                allow_assumption=True,
            ),
        ),
        scenario,
    )[0]
    assert not decision.technically_eligible and decision.action == "ask_user"
    assert scenario.assessments[0].datasets[0].metadata.origin == DataOrigin.SYNTHETIC


def test_invalid_registry_safe_error_without_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "secret-config.json"
    target.write_text('{"secret":"synthetic-marker"}', encoding="utf8")
    monkeypatch.setenv("BA_DATA_REGISTRY_PATH", str(target))
    load_registry.cache_clear()
    try:
        with pytest.raises(HTTPException) as error:
            load_registry()
        detail: object = error.value.detail
        assert detail == {"code": "data_registry_invalid"}
    finally:
        load_registry.cache_clear()


@pytest.mark.parametrize(
    "body",
    [
        {"categories": []},
        {"categories": ["geo.mapped_poi"] * 2},
        {"categories": ["x"], "url": "http://localhost"},
        {"categories": ["x"], "conversation_id": "other-owner"},
        {"categories": ["x"], "aoi": {"west": 1, "east": 0, "south": 0, "north": 1}},
    ],
)
def test_api_rejects_invalid_inputs_and_private_parameters(body: dict[str, object]) -> None:
    with TestClient(app) as client:
        response = client.post("/api/v2/data-registry/coverage", json=body)
        assert response.status_code == 422
        assert response.headers["X-Request-ID"]
        assert "http://localhost" not in response.text
