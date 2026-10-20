import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
import sqlalchemy as sa
from psycopg import sql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.schemas import AnalysisRun, BusinessProfile, MetricWithProvenance
from app.db.models import AnalysisRunRecord, BusinessProfileRecord, LocationMetricRecord
from app.domain.enums import Confidence, DataOrigin

pytestmark = pytest.mark.skipif(
    os.environ.get("BA_RUN_DB_TESTS") != "1", reason="Run with Docker Compose test profile"
)
CONFIG = Path(__file__).resolve().parents[2] / "alembic.ini"
TABLES = {"business_profiles", "analysis_runs", "location_metrics"}


def migrate(database: str, *arguments: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(CONFIG), *arguments],
        env={**os.environ, "PGDATABASE": database},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout + result.stderr


@pytest.fixture(scope="module")
def temporary_database() -> Iterator[str]:
    # Never downgrade the application's database. Only our newly created DB is dropped.
    name = "ba003_test_" + uuid4().hex
    with psycopg.connect(dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield name
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture(scope="module")
def migrated_database(temporary_database: str) -> Iterator[tuple[Engine, UUID]]:
    migrate(temporary_database, "upgrade", "head")
    engine = sa.create_engine("postgresql+psycopg://", connect_args={"dbname": temporary_database})
    run = AnalysisRun(
        profile_snapshot=BusinessProfile(conversation_id=uuid4()),
        dataset_versions={"seed": "v1"},
        algorithm_version="test-v1",
        tool_trace_id=uuid4(),
    )
    with Session(engine) as session:
        session.add(
            AnalysisRunRecord(
                **run.model_dump(mode="json")
                | {
                    "id": run.id,
                    "tool_trace_id": run.tool_trace_id,
                    "created_at": run.created_at,
                }
            )
        )
        session.commit()
    try:
        yield engine, run.id
    finally:
        engine.dispose()


def test_upgrade_is_repeatable_and_matches_models(temporary_database: str) -> None:
    migrate(temporary_database, "upgrade", "head")
    migrate(temporary_database, "upgrade", "head")
    migrate(temporary_database, "check")


def test_downgrade_and_reupgrade_do_not_drop_postgis() -> None:
    # A separate temporary DB keeps this destructive lifecycle independent of other tests.
    name = "ba003_test_" + uuid4().hex
    with psycopg.connect(dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            migrate(name, "upgrade", "head")
            migrate(name, "downgrade", "base")
            with psycopg.connect(dbname=name) as connection:
                rows = connection.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                ).fetchall()
                assert TABLES.isdisjoint(row[0] for row in rows)
                assert connection.execute("SELECT PostGIS_Version()").fetchone()
                enums = connection.execute(
                    "SELECT typname FROM pg_type WHERE typname IN "
                    "('data_origin', 'confidence', 'funding', 'confirmation_state')"
                ).fetchall()
                assert enums == []
            migrate(name, "upgrade", "head")
            migrate(name, "check")
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.mark.parametrize("origin", list(DataOrigin))
def test_orm_round_trip_retains_provenance_and_snapshot(
    migrated_database: tuple[Engine, UUID],
    origin: DataOrigin,
) -> None:
    engine, run_id = migrated_database
    profile = BusinessProfile(conversation_id=uuid4(), budget=Decimal("2000000.10"))
    dto = MetricWithProvenance(
        metric="test_metric",
        value=1800.0,
        unit="test_units",
        origin=origin,
        source_name="integration_test_seed",
        observed_at=None,
        generated_at=datetime.now(UTC),
        data_version="v1",
        confidence=Confidence.NOT_APPLICABLE,
        limitations=("Synthetic fixture, not a measured value",),
    )
    record = LocationMetricRecord(analysis_run_id=run_id, candidate_id=uuid4(), **dto.model_dump())
    with Session(engine) as session:
        session.add(BusinessProfileRecord(**profile.model_dump()))
        session.add(record)
        session.commit()
        stored = MetricWithProvenance.model_validate(
            {name: getattr(record, name) for name in MetricWithProvenance.model_fields}
        )
        assert stored == dto
        stored_profile = session.get(BusinessProfileRecord, profile.id)
        assert stored_profile is not None and stored_profile.budget == Decimal("2000000.10")
        run = session.get(AnalysisRunRecord, run_id)
        assert run is not None
        assert BusinessProfile.model_validate(run.profile_snapshot).conversation_id


@pytest.mark.parametrize(
    ("field", "invalid", "state"),
    [
        ("origin", None, "23502"),
        ("origin", "real", "22P02"),
        ("source_name", None, "23502"),
        ("source_name", " ", "23514"),
        ("data_version", "", "23514"),
        ("value", float("nan"), "23514"),
        ("value", float("inf"), "23514"),
        ("value", float("-inf"), "23514"),
        ("limitations", "[]", "23514"),
        ("confidence", "high", "23514"),
        ("observed_at", datetime(2030, 1, 1, tzinfo=UTC), "23514"),
        ("analysis_run_id", uuid4(), "23503"),
    ],
)
def test_database_rejects_unlabelled_or_invalid_metrics(
    migrated_database: tuple[Engine, UUID],
    field: str,
    invalid: Any,
    state: str,
) -> None:
    engine, run_id = migrated_database
    values: dict[str, Any] = {
        "id": uuid4(),
        "analysis_run_id": run_id,
        "candidate_id": uuid4(),
        "metric": "test_metric",
        "value": 1800.0,
        "unit": "test_units",
        "origin": "synthetic",
        "source_name": "integration_test_seed",
        "observed_at": None,
        "generated_at": datetime.now(UTC),
        "data_version": "v1",
        "confidence": "not_applicable",
        "limitations": '["Synthetic test value"]',
    }
    if invalid is None:
        del values[field]  # Exercise missing columns, not only explicit NULL.
    else:
        values[field] = invalid
    columns = ", ".join(values)
    parameters = ", ".join(":" + key for key in values)
    with pytest.raises(DBAPIError) as error, engine.begin() as connection:
        connection.execute(
            sa.text(f"INSERT INTO location_metrics ({columns}) VALUES ({parameters})"), values
        )
    assert getattr(error.value.orig, "sqlstate", None) == state
