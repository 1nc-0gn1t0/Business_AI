from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.schemas import AnalysisRun, BusinessProfile
from app.db.models import AnalysisRunRecord
from app.db.session import get_session
from app.main import app

from .support import isolated_database, migrate


@pytest.fixture
def client(
    migrated_database: tuple[Engine, UUID], monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    engine, _ = migrated_database

    def session() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as db, db.begin():
            yield db

    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_session)


@pytest.fixture(scope="module")
def temporary_database() -> Iterator[str]:
    with isolated_database() as name:
        yield name


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
