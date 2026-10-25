import json
import os
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.data.importer import import_dataset
from app.db.models import ReportRecord
from app.geo.ingest import import_snapshot
from app.geo.provider import load_snapshot

from .test_conversations import create
from .test_data_providers import seed

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")


def setup(client: TestClient) -> tuple[str, dict[str, str], dict[str, Any]]:
    _, headers, url = create(client)
    response = client.patch(
        url + "/profile",
        headers=headers,
        json={
            "expected_version": 0,
            "patch": {
                "city": "Казань",
                "category": "кофейня",
                "budget": "2000000",
                "funding": "own_funds",
                "preferences": {"format": "навынос"},
            },
        },
    )
    assert response.status_code == 200
    response = client.post(url + "/profile/confirm", headers=headers, json={"expected_version": 1})
    assert response.status_code == 200
    profile = response.json()["profile"]
    source = {
        "origin": "synthetic",
        "source_name": "Explicit synthetic test assumptions",
        "data_version": "test-v1",
        "confidence": "not_applicable",
        "limitations": ["Not market data"],
    }

    def amount(v: str | int) -> dict[str, Any]:
        return {"value": v, "source": source}

    fixed = {k: amount("10000") for k in ("rent", "payroll", "utilities", "other")}
    finance = {
        "profile": profile,
        "startup": {
            k: amount("100000")
            for k in (
                "equipment",
                "renovation",
                "rent_deposit",
                "initial_inventory",
                "registration",
                "other",
                "working_capital_reserve",
            )
        },
        "monthly_fixed_costs": fixed,
        "working_days_per_month": amount(30),
        "scenarios": {
            name: {
                "average_check": amount("350"),
                "sales_per_day": amount(sales),
                "variable_cost_ratio": amount("0.4"),
            }
            for name, sales in (("conservative", 10), ("base", 90), ("optimistic", 120))
        },
        "sensitivity_changes": ["-0.1", "0.1"],
    }
    result = client.post("/api/v1/finance/calculate", json=finance)
    assert result.status_code == 200, result.text
    return (
        url,
        headers,
        {
            "expected_version": 2,
            "finance": {"request": finance, "fingerprint": result.json()["request_fingerprint"]},
        },
    )


def test_pdf_json_one_snapshot_no_lead_consent_and_session_isolation(client: TestClient) -> None:
    url, headers, body = setup(client)
    before = client.get(url + "/consents", headers=headers).json()
    response = client.post(url + "/reports", headers=headers, json=body)
    assert response.status_code == 201, response.text
    metadata = response.json()
    base = url + "/reports/" + metadata["id"]
    raw = client.get(base + "/file?format=json", headers=headers)
    pdf = client.get(base + "/file?format=pdf", headers=headers)
    assert raw.status_code == pdf.status_code == 200
    assert raw.headers["x-report-snapshot-sha256"] == pdf.headers["x-report-snapshot-sha256"]
    assert "attachment;" in pdf.headers["content-disposition"]
    assert pdf.headers["content-type"] == "application/pdf"
    assert raw.headers["content-type"].startswith("application/json")
    assert raw.headers["cache-control"] == "private, no-store"
    snapshot = raw.json()
    assert client.get(base + "/snapshot", headers=headers).json() == snapshot
    finance = snapshot["finance"]
    assert finance["startup"]["total_initial_funding"] == "700000.00"
    assert finance["scenarios"][1]["metrics"]["monthly_revenue"]["value"] == "945000.00"
    assert finance["scenarios"][1]["metrics"]["operating_result"]["value"] == "527000.00"
    text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf.content), strict=True).pages)
    assert "СИНТЕТИКА" in text and "Казань" in text and "₽" in text
    assert "527000.00" in text and "945000.00" in text
    assert b"access_token" not in raw.content and b"messages" not in raw.content
    assert b"X-Conversation-Token" not in raw.content
    assert client.get(base + "/file?format=pdf", headers=headers).content == pdf.content
    assert client.get(base + "/file?format=json", headers=headers).content == raw.content
    assert client.get(url + "/consents", headers=headers).json() == before
    _, other_headers, other_url = create(client)
    assert (
        client.get(other_url + "/reports/" + metadata["id"], headers=other_headers).status_code
        == 404
    )
    assert client.get(base, headers=other_headers).status_code == 404
    assert client.get(base).status_code == 401
    assert client.get(base + "/file?format=exe", headers=headers).status_code == 422
    # Repeated preparation is explicit: a new immutable report, not a modified old snapshot.
    assert client.post(url + "/reports", headers=headers, json=body).status_code == 201


def test_stale_profile_changed_inputs_and_integrity(
    client: TestClient, migrated_database: tuple[Engine, UUID]
) -> None:
    url, headers, body = setup(client)
    response = client.post(url + "/reports", headers=headers, json=body)
    assert response.status_code == 201, response.text
    metadata = response.json()
    base = url + "/reports/" + metadata["id"]
    original = client.get(base + "/file?format=json", headers=headers).content
    changed = json.loads(json.dumps(body))
    changed["finance"]["request"]["monthly_fixed_costs"]["rent"]["value"] = "50000"
    assert client.post(url + "/reports", headers=headers, json=changed).status_code == 409
    assert (
        client.patch(
            url + "/profile",
            headers=headers,
            json={"expected_version": 2, "patch": {"budget": "2100000"}},
        ).status_code
        == 200
    )
    assert client.get(base, headers=headers).json()["status"] == "outdated"
    assert client.get(base + "/file?format=pdf", headers=headers).status_code == 409
    assert (
        client.get(base + "/file?format=json&historical=true", headers=headers).content == original
    )
    assert client.post(url + "/reports", headers=headers, json=body).status_code == 409
    engine, _ = migrated_database
    with Session(engine) as db, db.begin():
        row = db.get(ReportRecord, UUID(metadata["id"]))
        assert row is not None
        row.pdf = b"tampered"
    assert client.get(base, headers=headers).status_code == 503


def test_partial_and_invalid_reports_and_body_bound(client: TestClient) -> None:
    _, headers, url = create(client)
    assert (
        client.post(url + "/reports", headers=headers, json={"expected_version": 0}).status_code
        == 422
    )
    url, headers, body = setup(client)
    assert (
        client.post(url + "/reports", headers=headers, json={"expected_version": 2}).status_code
        == 422
    )
    huge = client.post(
        url + "/reports",
        headers={**headers, "Content-Type": "application/json"},
        content=b"x" * 131073,
    )
    assert huge.status_code == 413
    body["selected_zone"] = "a" * 64
    assert client.post(url + "/reports", headers=headers, json=body).status_code == 422


def test_geo_bank_snapshot_and_stale_source(
    client: TestClient, migrated_database: tuple[Engine, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.bank.today", lambda: date(2026, 10, 23))
    engine, _ = migrated_database
    with Session(engine) as db, db.begin():
        manifest, document = load_snapshot(Path(__file__).parent / "fixtures/kazan.raw.json")
        import_snapshot(db, manifest, document)
    url, headers, body = setup(client)
    profile = body["finance"]["request"]["profile"]
    metadata = client.get("/api/v1/geo/datasets").json()[0]
    ranking = {
        "candidates": {
            "profile": profile,
            "data_version": metadata["data_version"],
            "cell_size_m": 250,
            "min_separation_m": 0,
            "limit": 3,
        },
        "scoring": {
            "radius_m": 50,
            "weights": {"transit": 0, "infrastructure": 0, "complementary": 0, "competitors": 1},
            "competitor_mode": "cluster",
        },
    }
    geo = client.post("/api/v1/geo/kazan-fixture/rankings", json=ranking).json()
    body["geo"] = {
        "dataset": "kazan-fixture",
        "request": ranking,
        "fingerprint": geo["request_fingerprint"],
    }
    body["selected_zone"] = geo["candidates"]["features"][0]["id"]
    catalogue = client.get("/api/v1/bank-products").json()
    bank_request = {
        "expected_version": 2,
        "catalogue_fingerprint": catalogue["fingerprint"],
        "needs": {"needs_settlement_account": True},
    }
    matches = client.post(url + "/bank-products/matches", headers=headers, json=bank_request).json()
    body["bank"] = {"request": bank_request, "fingerprint": matches["request_fingerprint"]}
    response = client.post(url + "/reports", headers=headers, json=body)
    assert response.status_code == 201, response.text
    base = url + "/reports/" + response.json()["id"]
    snapshot = client.get(base + "/file?format=json", headers=headers).json()
    assert snapshot["geo"]["candidates"]["dataset"]["data_version"] == metadata["data_version"]
    assert snapshot["bank"]["credit_decision"] == "not_assessed"
    monkeypatch.setattr("app.api.bank.today", lambda: date(2026, 10, 24))
    assert client.get(base, headers=headers).json()["status"] == "outdated"


def test_synthetic_provider_provenance_survives_export_and_disable(
    client: TestClient, migrated_database: tuple[Engine, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DEMO_ENABLED", "true")
    engine, _ = migrated_database
    with Session(engine) as db, db.begin():
        version = import_dataset(db, seed("report-demo"))
    url, headers, body = setup(client)
    query = {
        "provider": "synthetic",
        "dataset": "report-demo",
        "data_version": version,
        "mode": "demo",
        "metrics": ["rent_monthly_rub", "mapped_poi_count"],
    }
    indicators = client.post("/api/v1/data-providers/indicators", json=query).json()
    body["providers"] = [{"request": query, "fingerprint": indicators["request_fingerprint"]}]
    response = client.post(url + "/reports", headers=headers, json=body)
    assert response.status_code == 201, response.text
    base = url + "/reports/" + response.json()["id"]
    value = client.get(base + "/file?format=json", headers=headers).json()["providers"][0]
    assert value["indicators"][0]["measurement"]["origin"] == "synthetic"
    assert value["indicators"][0]["measurement"]["data_version"] == version
    assert value["indicators"][1]["measurement"] is None
    pdf = client.get(base + "/file?format=pdf", headers=headers)
    text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
    assert "СИНТЕТИЧЕСКИЕ ДАННЫЕ" in text and "НЕ РЫНОК КАЗАНИ" in text
    monkeypatch.setenv("DATA_DEMO_ENABLED", "false")
    assert (
        client.get(base + "/file?format=json&historical=true", headers=headers).status_code == 403
    )
    assert client.post(url + "/reports", headers=headers, json=body).status_code == 403
