"""Actual populated U-04 schema upgrade; no owner database or live LLM is used."""

import os

import pytest
import sqlalchemy as sa

from .support import isolated_database, migrate
from .test_conversations import create
from .test_populated_upgrade import api
from .test_reports import setup

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Isolated PostGIS")


def test_0011_to_0012_preserves_profile_and_immutable_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BA_INDUSTRY_ENABLED", "1")
    monkeypatch.setenv("BA_FINANCE_V2_ENABLED", "0")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    with isolated_database() as name:
        migrate(name, "upgrade", "0011_industry_profile")
        engine = sa.create_engine("postgresql+psycopg://", connect_args={"dbname": name})
        try:
            with api(engine) as client:
                old, headers, _ = create(client)
                profile = f"/api/v2/conversations/{old['id']}/industry-profile"
                r = client.patch(
                    profile,
                    headers=headers,
                    json={
                        "expected_version": 0,
                        "industry": "online_school",
                        "updates": [
                            {"field": k, "value": v}
                            for k, v in {
                                "budget": "1500000",
                                "audience": "взрослые",
                                "format": "онлайн",
                                "payment_model": "курс",
                                "students": 20,
                            }.items()
                        ],
                    },
                )
                assert r.status_code == 200
                before = r.json()["profile"]
                url, report_headers, body = setup(client)
                report = client.post(url + "/reports", headers=report_headers, json=body)
                assert report.status_code == 201
                files = url + "/reports/" + report.json()["id"] + "/file?format="
                original = {
                    f: client.get(files + f, headers=report_headers).content
                    for f in ("pdf", "json")
                }
            migrate(name, "upgrade", "head")
            migrate(name, "upgrade", "head")
            migrate(name, "check")
            with api(engine) as client:
                assert client.get(profile, headers=headers).json()["profile"] == before
                for f, content in original.items():
                    r = client.get(files + f, headers=report_headers)
                    assert r.status_code == 200 and r.content == content
            with engine.connect() as db:
                assert (
                    db.scalar(sa.text("SELECT version_num FROM alembic_version"))
                    == "0012_financial_scenarios"
                )
                for table in ("financial_workspaces", "financial_actions", "financial_results"):
                    assert db.scalar(sa.select(sa.func.count()).select_from(sa.table(table))) == 0
        finally:
            engine.dispose()
