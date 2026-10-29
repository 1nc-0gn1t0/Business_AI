"""H-04: isolated populated 0007 -> 0008, transactional failures and recovery.

The helpers are also used by the opt-in local backup drill. All tokens are newly
created synthetic fixture credentials; never publish the private state file.
"""

import hashlib
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from psycopg import sql
from pypdf import PdfReader
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.schemas import AnalysisRun, MetricWithProvenance
from app.data.importer import import_dataset
from app.db.models import (
    AnalysisRunRecord,
    Base,
    GeoDatasetRecord,
    GeoDistrictRecord,
    LocationMetricRecord,
)
from app.db.session import get_session, get_session_factory
from app.domain.enums import Confidence, DataOrigin
from app.geo.ingest import import_snapshot
from app.geo.provider import load_snapshot
from app.geo.walk_import import import_graph
from app.main import app

from .support import CONFIG, isolated_database, migrate
from .test_conversations import create
from .test_data_providers import seed as provider_seed
from .test_leads import action, decision
from .test_reports import setup
from .test_walking import seed as walking_seed

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires PostGIS")
PREVIOUS = "0007_data_providers"


@contextmanager
def api(engine: Engine) -> Iterator[TestClient]:
    def session() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as db, db.begin():
            yield db

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_session_factory] = lambda: sessionmaker(
        engine, expire_on_commit=False
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def fingerprints(database: str) -> dict[str, Any]:
    result = {}
    with psycopg.connect(dbname=database) as db:
        for table in sorted(Base.metadata.tables):
            if not db.execute("SELECT to_regclass(%s)", ("public." + table,)).fetchall()[0][0]:
                continue
            rows = db.execute(
                sql.SQL(
                    "SELECT to_jsonb(t)::text FROM public.{} t "
                    'ORDER BY to_jsonb(t)::text COLLATE "C"'
                ).format(sql.Identifier(table))
            ).fetchall()
            result[table] = {
                "rows": len(rows),
                "sha256": hashlib.sha256("".join(r[0] + "\n" for r in rows).encode()).hexdigest(),
            }
        assert (
            db.execute("SELECT count(*) FROM pg_constraint WHERE NOT convalidated").fetchall()[0][0]
            == 0
        )
        assert (
            db.execute("SELECT count(*) FROM pg_index WHERE NOT indisvalid").fetchall()[0][0] == 0
        )
        assert db.execute("SELECT bool_and(ST_IsValid(geom)) FROM geo_pois").fetchall()[0][0]
        assert db.execute("SELECT bool_and(ST_SRID(geom)=4326) FROM geo_pois").fetchall()[0][0]
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
            db.execute(
                "UPDATE messages SET conversation_id=%s WHERE id=(SELECT id FROM messages LIMIT 1)",
                (uuid4(),),
            )
        with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
            db.execute("INSERT INTO business_profiles SELECT * FROM business_profiles LIMIT 1")
    return result


def populate(engine: Engine) -> dict[str, Any]:
    with api(engine) as client:
        url, headers, report_body = setup(client)  # Works on 0007: no report write yet.
        other, other_headers, _ = create(client)
        assert decision(client, url, headers, "marketing", "decline").status_code == 200
        assert decision(client, url, headers, "demo_lead").status_code == 200
        catalogue = client.get("/api/v1/bank-products").json()
        request = {
            "expected_profile_version": 2,
            "catalogue_fingerprint": catalogue["fingerprint"],
            "product_ids": ["vtb-rko"],
            "fields": {"city": "Казань", "category": "кофейня", "budget": "2000000"},
        }
        prepared = client.post(url + "/leads/drafts", headers=headers, json=request)
        assert prepared.status_code == 201, prepared.text
        draft = prepared.json()
        endpoint = url + "/leads/drafts/" + draft["id"]
        assert (
            client.post(endpoint + "/confirm", headers=headers, json=action(draft)).status_code
            == 200
        )
        submitted = client.post(
            endpoint + "/submit",
            headers=headers,
            json={**action(draft), "idempotency_key": str(uuid4())},
        )
        assert submitted.status_code == 200, submitted.text
        assert client.post(url + "/leads/drafts", headers=headers, json=request).status_code == 201
        assert decision(client, url, headers, "demo_lead", "withdraw", 1).status_code == 200
        state = {
            "url": url,
            "headers": headers,
            "other_headers": other_headers,
            "other_id": other["id"],
            "report_body": report_body,
            "profile": client.get(url, headers=headers).json(),
            "receipt": submitted.json(),
        }
    with Session(engine) as db, db.begin():
        manifest, document = load_snapshot(Path(__file__).parent / "fixtures/kazan.raw.json")
        import_snapshot(db, manifest, document)
        slug, walk, document = walking_seed(db)
        import_graph(db, walk, document)
        dataset_id = db.scalar(sa.select(GeoDatasetRecord.id).where(GeoDatasetRecord.slug == slug))
        assert dataset_id is not None
        db.add(
            GeoDistrictRecord(
                dataset_id=dataset_id,
                osm_id=999,
                osm_version=1,
                observed_at=walk.osm_base,
                name="Synthetic H-04 polygon",
                admin_level=8,
                geom="SRID=4326;MULTIPOLYGON(((49.12 55.78,49.13 55.78,49.13 55.79,49.12 55.78)))",
            )
        )
        import_dataset(db, provider_seed("h04-synthetic"))
        run = AnalysisRun(
            profile_snapshot=state["profile"]["profile"],
            dataset_versions={"fixture": "h04-v1"},
            algorithm_version="h04-fixture-v1",
            tool_trace_id=uuid4(),
        )
        db.add(
            AnalysisRunRecord(
                **run.model_dump(mode="json")
                | {"id": run.id, "created_at": run.created_at, "tool_trace_id": run.tool_trace_id}
            )
        )
        db.flush()
        metric = MetricWithProvenance(
            metric="h04_test",
            value=1,
            unit="fixture_units",
            origin=DataOrigin.SYNTHETIC,
            source_name="H-04 authored fixture",
            data_version="h04-v1",
            generated_at=run.created_at,
            confidence=Confidence.NOT_APPLICABLE,
            observed_at=None,
            limitations=("Not market data",),
        )
        db.add(
            LocationMetricRecord(
                analysis_run_id=run.id, candidate_id=uuid4(), **metric.model_dump()
            )
        )
    return state


def add_report(engine: Engine, state: dict[str, Any]) -> None:
    with api(engine) as client:
        response = client.post(
            state["url"] + "/reports", headers=state["headers"], json=state["report_body"]
        )
        assert response.status_code == 201, response.text
        state["report_id"] = response.json()["id"]
        for format_ in ("pdf", "json"):
            raw = client.get(
                state["url"] + "/reports/" + state["report_id"] + "/file?format=" + format_,
                headers=state["headers"],
            )
            assert raw.status_code == 200
            state[format_ + "_sha256"] = hashlib.sha256(raw.content).hexdigest()
    # U-02 tables participate in populated backup/fingerprint checks too. This is
    # an explicitly cancelled synthetic job; it never grants network permission.
    from app.data.acquisition.service import emit
    from app.db.models import AcquisitionJobRecord, AcquisitionRequestRecord

    with Session(engine) as db, db.begin():
        now = datetime.now(UTC)
        job = AcquisitionJobRecord(
            id=uuid4(),
            state="cancelled",
            stage="cancelled",
            request={
                "source_id": "osm",
                "category": "geo.mapped_poi",
                "territory": "ru-moscow",
                "aoi": {"west": 37.61, "south": 55.75, "east": 37.612, "north": 55.752},
                "freshness": "current",
                "idempotency_key": "h04-u02-cancelled-fixture",
            },
            scope_hash="a" * 64,
            policy_hash="b" * 64,
            expected_version=None,
            attempt=0,
            fencing_token=0,
            event_cursor=0,
            installation=None,
            lease_until=None,
            created_at=now,
            updated_at=now,
            next_attempt_at=now,
            artifact=None,
            checkpoint={},
            result=None,
            error_code=None,
        )
        db.add(job)
        db.flush()
        emit(db, job, "cancelled", "cancelled", "synthetic_fixture_cancelled")
        db.add(
            AcquisitionRequestRecord(
                key="h04-u02-cancelled-fixture",
                payload_hash="c" * 64,
                job_id=job.id,
            )
        )
        # U-03 metadata is synthetic/terminal; preserve every-table population checks.
        from uuid import UUID

        from app.agent.schemas import AgentResponse
        from app.db.models import AgentRunRecord

        owner = UUID(state["url"].split("/")[-1])
        run_id = uuid4()
        agent_response = AgentResponse(
            request_id=run_id,
            conversation_id=owner,
            profile_version=state["profile"]["version"],
            state="cancelled",
            message="H04 fixture",
            next_step="done",
            code="cancelled_fixture",
            model="synthetic_fixture",
        )
        db.add(
            AgentRunRecord(
                id=run_id,
                conversation_id=owner,
                request_hash="d" * 64,
                expected_version=agent_response.profile_version,
                consent_revision=1,
                operator=False,
                state="cancelled",
                created_at=now,
                deadline_at=now,
                job_ids=[],
                response=agent_response.model_dump(mode="json"),
            )
        )
        # U-04 is an extension of the same profile/CAS; seeding it must not mutate
        # the old profile, consent, lead or immutable report bytes.
        from app.db.models import IndustryProfileRecord
        from app.industry.service import IndustryProfiles

        universal = IndustryProfiles(db).load(owner, state["headers"]["X-Conversation-Token"])
        db.add(
            IndustryProfileRecord(
                profile_id=universal.id, document=universal.model_dump(mode="json")
            )
        )


def verify_api(engine: Engine, state: dict[str, Any], *, reports: bool = True) -> None:
    with api(engine) as client:
        url, headers = state["url"], state["headers"]
        assert client.get(url, headers=headers).json() == state["profile"]
        assert client.get(url, headers=state["other_headers"]).status_code == 404
        assert client.get(url + "/leads", headers=headers).json()["receipts"] == [state["receipt"]]
        assert state["receipt"]["sent_to_bank"] is False
        assert client.get(url + "/leads", headers=state["other_headers"]).status_code == 404
        assert client.get(url + "/audit", headers=headers).status_code == 200
        if not reports:
            return
        base = url + "/reports/" + state["report_id"]
        assert client.get(base, headers=state["other_headers"]).status_code == 404
        assert client.get(base).status_code == 401
        for format_ in ("pdf", "json"):
            raw = client.get(base + "/file?format=" + format_, headers=headers)
            assert raw.status_code == 200, raw.text[:100]
            assert hashlib.sha256(raw.content).hexdigest() == state[format_ + "_sha256"]
            if format_ == "pdf":
                text = "".join(
                    p.extract_text() for p in PdfReader(BytesIO(raw.content), strict=True).pages
                )
                assert "Казань" in text and "СИНТЕТИКА" in text and "₽" in text
            else:
                assert raw.json()["finance"]["startup"]["total_initial_funding"] == "700000.00"


def test_populated_previous_upgrade_preserves_data_and_report_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setattr("app.leads.service.today", lambda: date(2026, 10, 23))
    with isolated_database() as name:
        migrate(name, "upgrade", PREVIOUS)
        engine = sa.create_engine("postgresql+psycopg://", connect_args={"dbname": name})
        try:
            state = populate(engine)
            before = fingerprints(name)
            verify_api(engine, state, reports=False)
            # Current report code on the unsupported 0007 schema fails safely;
            # do not deploy it until upgrade, even though older routes still read.
            with api(engine) as client:
                response = client.get(
                    state["url"] + "/reports/" + str(uuid4()), headers=state["headers"]
                )
                assert response.status_code == 503
                assert response.json()["detail"] == {"code": "database_unavailable"}
                assert response.json()["request_id"] == response.headers["x-request-id"]
            assert fingerprints(name) == before
            migrate(name, "upgrade", "head")
            assert {k: v for k, v in fingerprints(name).items() if k in before} == before
            add_report(engine, state)
            complete = fingerprints(name)
            assert all(v["rows"] > 0 for v in complete.values()), complete
            migrate(name, "upgrade", "head")
            migrate(name, "check")
            assert fingerprints(name) == complete
            verify_api(engine, state)
        finally:
            engine.dispose()


def test_tiger_filter_still_detects_real_application_drift() -> None:
    with isolated_database() as name:
        with psycopg.connect(dbname=name, autocommit=True) as db:
            db.execute("CREATE EXTENSION postgis")
            db.execute("CREATE EXTENSION fuzzystrmatch")
            db.execute("CREATE EXTENSION postgis_tiger_geocoder")
            db.execute(
                sql.SQL("ALTER DATABASE {} SET search_path TO public,tiger").format(
                    sql.Identifier(name)
                )
            )
        migrate(name, "upgrade", "head")
        migrate(name, "check")
        with psycopg.connect(dbname=name, autocommit=True) as db:
            db.execute("ALTER TABLE public.messages ADD COLUMN h04_unexpected text")
            db.execute("CREATE TABLE public.h04_unexpected(id integer PRIMARY KEY)")
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(CONFIG), "check"],
            env={**os.environ, "PGDATABASE": name},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "h04_unexpected" in result.stdout + result.stderr
        assert "remove_table" in result.stdout + result.stderr
        assert "remove_column" in result.stdout + result.stderr
        assert "addrfeat" not in result.stdout + result.stderr


@pytest.mark.parametrize("interrupt", [False, True], ids=["sql-error", "terminate-backend"])
def test_failed_transactional_upgrade_retries_without_partial_objects(interrupt: bool) -> None:
    with isolated_database() as name:
        migrate(name, "upgrade", PREVIOUS)
        with psycopg.connect(dbname=name, autocommit=True) as db:
            db.execute("CREATE TABLE h04_committed(id integer PRIMARY KEY, value text)")
            db.execute("INSERT INTO h04_committed VALUES (1,'synthetic committed data')")
        # Temporary migration source: installed history is copied, never edited.
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(CONFIG.parent / "migrations", root / "migrations")
            migration = root / "migrations/versions/0008_analytical_reports.py"
            payload = migration.read_text()
            injection = (
                "op.execute('SELECT pg_sleep(30)')" if interrupt else "op.execute('SELECT 1/0')"
            )
            payload = payload.replace(
                "    op.create_index(", "    " + injection + "\n    op.create_index("
            )
            migration.write_text(payload)
            config = root / "alembic.ini"
            config.write_text(
                "[alembic]\nscript_location="
                + str(root / "migrations")
                + "\nprepend_sys_path="
                + str(CONFIG.parent)
                + "\n"
            )
            process = subprocess.Popen(
                [sys.executable, "-m", "alembic", "-c", str(config), "upgrade", "head"],
                env={**os.environ, "PGDATABASE": name, "PGAPPNAME": "h04-fault"},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if interrupt:
                with psycopg.connect(dbname="postgres", autocommit=True) as admin:
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        row = admin.execute(
                            "SELECT pid FROM pg_stat_activity WHERE datname=%s "
                            "AND application_name='h04-fault' AND wait_event='PgSleep'",
                            (name,),
                        ).fetchone()
                        if row:
                            assert admin.execute("SELECT pg_terminate_backend(%s)", row).fetchall()[
                                0
                            ][0]
                            break
                        time.sleep(0.05)
                    else:
                        process.kill()
                        pytest.fail("Fault migration did not enter pg_sleep")
            process.communicate(timeout=30)
            assert process.returncode != 0
        with psycopg.connect(dbname=name) as db:
            assert (
                db.execute("SELECT version_num FROM alembic_version").fetchall()[0][0] == PREVIOUS
            )
            assert (
                db.execute("SELECT to_regclass('public.analytical_reports')").fetchall()[0][0]
                is None
            )
            assert (
                db.execute("SELECT value FROM h04_committed").fetchall()[0][0]
                == "synthetic committed data"
            )

        migrate(name, "upgrade", "head")
        migrate(name, "upgrade", "head")
        with psycopg.connect(dbname=name) as db:
            assert (
                db.execute("SELECT value FROM h04_committed").fetchall()[0][0]
                == "synthetic committed data"
            )


@pytest.mark.parametrize("failure", ["no-access", "wrong-config"])
def test_database_connection_failures_have_safe_responses(failure: str) -> None:
    args: dict[str, Any] = {"connect_timeout": 1}
    if failure == "no-access":
        args["user"] = "h04_nonexistent_" + uuid4().hex
    else:
        args.update(host="127.0.0.1", port=1)
    engine = sa.create_engine("postgresql+psycopg://", connect_args=args)
    try:
        with api(engine) as client:
            response = client.post("/api/v1/conversations")
            assert response.status_code == 503
            assert response.json()["detail"] == {"code": "database_unavailable"}
            assert response.json()["request_id"] == response.headers["x-request-id"]
            assert "Traceback" not in response.text and "password" not in response.text
    finally:
        engine.dispose()


def test_cli_downgrade_refuses_before_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGHOST", "127.0.0.1")
    monkeypatch.setenv("PGPORT", "1")
    for database, extra in (
        ("business_ai", []),
        ("business_ai", ["-x", "allow_test_downgrade=true"]),
        ("business_ai_test_" + uuid4().hex, []),
    ):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(CONFIG), *extra, "downgrade", "base"],
            env={**os.environ, "PGDATABASE": database},
            text=True,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode != 0
        assert "Downgrade refused" in result.stderr
        assert "connection refused" not in result.stderr.lower()
