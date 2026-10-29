"""Artificial small Moscow POI fixtures in disposable DBs, never a live acquisition claim."""

import json
import os
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.data.acquisition import network, service
from app.data.acquisition.schemas import AcquisitionError, AcquisitionRequest
from app.data.acquisition.worker import ProcessLock, Worker
from app.data.coverage import coverage
from app.data.registry import load_registry
from app.data.registry_schemas import CoverageQuery, RegistryConfig
from app.db.models import AcquisitionJobRecord, GeoDatasetRecord
from app.db.session import get_session
from app.geo.ingest import import_snapshot
from app.geo.provider import load_snapshot
from app.main import app

from .support import isolated_database, migrate
from .test_populated_upgrade import fingerprints, populate

pytestmark = pytest.mark.skipif(
    os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires isolated PostGIS"
)
APPROVAL_END = datetime.now(UTC) + timedelta(hours=1)


@pytest.fixture
def database() -> Iterator[Engine]:
    with isolated_database() as name:
        migrate(name, "upgrade", "head")
        engine = sa.create_engine("postgresql+psycopg://", connect_args={"dbname": name})
        try:
            yield engine
        finally:
            engine.dispose()


def approved() -> RegistryConfig:
    original = load_registry()
    return original.model_copy(
        update={
            "sources": tuple(
                s.model_copy(
                    update={
                        "network_permission": "permitted",
                        "availability": "ready",
                        "acquisition_scope": "operator_smoke",
                        "acquisition_approved_until": APPROVAL_END,
                    }
                )
                if s.id == "osm"
                else s
                for s in original.sources
            )
        }
    )


def request(key: str = "integration-fixture") -> AcquisitionRequest:
    return AcquisitionRequest.model_validate(
        {
            "territory": "ru-moscow",
            "aoi": {"west": 37.61, "south": 55.75, "east": 37.612, "north": 55.752},
            "idempotency_key": key,
        }
    )


def create(engine: Engine, req: AcquisitionRequest | None = None) -> UUID:
    with Session(engine) as db, db.begin():
        return service.create(db, req or request(), approved()).id


def read(engine: Engine, job_id: UUID) -> AcquisitionJobRecord:
    with Session(engine, expire_on_commit=False) as db:
        return service.get_job(db, job_id)


def fake_fetch(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def fetch(query: str, destination: Path, cap: int, check: Any) -> int:
        calls.append(1)
        check()
        stamp = datetime.now(UTC).isoformat()
        raw = json.dumps(
            {
                "osm3s": {"timestamp_osm_base": stamp},
                "elements": [
                    {
                        "type": "node",
                        "id": 1,
                        "version": 1,
                        "timestamp": stamp,
                        "lon": 37.611,
                        "lat": 55.751,
                        "tags": {"amenity": "cafe", "name": "TEST FIXTURE ONLY"},
                    },
                ],
            }
        ).encode()
        destination.write_bytes(raw)
        return len(raw)

    monkeypatch.setattr(network, "fetch", fetch)
    return calls


def make_due(engine: Engine, job_id: UUID) -> None:
    with Session(engine) as db, db.begin():
        db.execute(
            sa.update(AcquisitionJobRecord)
            .where(AcquisitionJobRecord.id == job_id)
            .values(
                lease_until=datetime.now(UTC) - timedelta(seconds=1),
                next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )


def test_end_to_end_publish_coverage_cache_and_kazan_unchanged(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = approved()
    with Session(database) as db, db.begin():
        manifest, doc = load_snapshot(Path(__file__).parent / "fixtures/kazan.raw.json")
        imported = import_snapshot(db, manifest, doc)
        kazan_id, kazan_version, kazan_count = (
            imported.id,
            imported.data_version,
            imported.poi_count,
        )
    job_id = create(database)
    calls = fake_fetch(monkeypatch)
    with ProcessLock(tmp_path) as process:
        assert Worker(database, cfg, process).once()
    job = read(database, job_id)
    assert job.state == "succeeded" and job.result and job.result["poi_count"] == 1
    assert job.artifact is None and job.result["reused_cache"] == 0 and len(calls) == 1
    with Session(database) as db, db.begin():
        result = coverage(
            db,
            CoverageQuery(
                aoi=request().aoi,
                territory="ru-moscow",
                categories=("geo.mapped_poi", "geo.vehicle_network", "geo.admin_polygons"),
            ),
            cfg,
        )
        assert [a.local_status for a in result.assessments] == ["available", "missing", "missing"]
        city = coverage(
            db, CoverageQuery(territory="ru-moscow", categories=("geo.mapped_poi",)), cfg
        )
        assert city.assessments[0].local_status == "partial"
        assert db.get(GeoDatasetRecord, kazan_id).data_version == kazan_version  # type: ignore[union-attr]
        assert db.get(GeoDatasetRecord, kazan_id).poi_count == kazan_count  # type: ignore[union-attr]
        cached = service.create(db, request("another-cache-key"), cfg)
        assert cached.state == "succeeded" and cached.result and cached.result["reused_cache"] == 1
        assert service.create(db, request(), cfg).id == job_id


def test_idempotency_dedup_conflict_queue_and_aoi(database: Engine) -> None:
    job_id = create(database)
    assert create(database, request("second-dedup-key")) == job_id
    with pytest.raises(HTTPException) as error:
        with Session(database) as db, db.begin():
            service.create(db, request().model_copy(update={"territory": "ru-kazan"}), approved())
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        with Session(database) as db, db.begin():
            large = request("large-aoi-key").aoi.model_copy(update={"east": 37.7, "north": 55.8})
            service.create(
                db, request("large-aoi-key").model_copy(update={"aoi": large}), approved()
            )
    assert isinstance(error.value.detail, dict)
    assert error.value.detail["code"] == "acquisition_aoi_too_large"
    create(database, request("other-scope-key").model_copy(update={"territory": "ru-kazan"}))
    with pytest.raises(HTTPException) as error:
        create(
            database, request("third-scope-key").model_copy(update={"territory": "ru-novosibirsk"})
        )
    assert error.value.status_code == 429


def test_claim_is_atomic_and_second_heavy_execution_is_excluded(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = create(database)
    with ProcessLock(tmp_path) as process:
        workers = [Worker(database, approved(), process), Worker(database, approved(), process)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda w: w.claim(), workers))
        assert results.count(job_id) == 1 and results.count(None) == 1
        # Exercise the session-level lock while the winning worker performs external work.
        entered, finish = Event(), Event()
        winner = workers[results.index(job_id)]

        def hold() -> None:
            with database.connect() as connection:
                connection.execute(sa.text("SELECT pg_advisory_lock(782493202)"))
                connection.commit()
                entered.set()
                assert finish.wait(10)
                connection.execute(sa.text("SELECT pg_advisory_unlock(782493202)"))
                connection.commit()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(hold)
            assert entered.wait(10)
            try:
                assert not winner.once()
            finally:
                finish.set()
            future.result()


def test_restart_resumes_verified_checkpoint_and_fences_old_worker(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_fetch(monkeypatch)
    job_id = create(database)
    import app.data.acquisition.worker as module

    original = import_snapshot

    def crash(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("test process crash after durable download")

    monkeypatch.setattr(module, "import_snapshot", crash)
    with ProcessLock(tmp_path) as process:
        old = Worker(database, approved(), process)
        with pytest.raises(RuntimeError):
            old.once()
    assert read(database, job_id).artifact
    make_due(database, job_id)
    monkeypatch.setattr(module, "import_snapshot", original)
    with ProcessLock(tmp_path) as process:
        restarted = Worker(database, approved(), process)
        assert not restarted.once()  # Records recovery, preserves source cooldown.
        with Session(database) as db, db.begin():
            with pytest.raises(AcquisitionError, match="worker_fenced"):
                old.guard(db)
        make_due(database, job_id)
        assert restarted.once()
    assert read(database, job_id).state == "succeeded" and len(calls) == 1


@pytest.mark.parametrize("phase", ["download", "import"])
def test_cancellation_rolls_back_all_unpublished_data(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    fake_fetch(monkeypatch)
    job_id = create(database)
    import app.data.acquisition.worker as module

    with ProcessLock(tmp_path) as process:
        worker = Worker(database, approved(), process)

        def cancel() -> None:
            with Session(database) as db, db.begin():
                service.cancel(db, job_id)
            worker.last_heartbeat = 0

        if phase == "download":
            fetch = network.fetch

            def interrupted(*args: Any, **kwargs: Any) -> int:
                cancel()
                return fetch(*args, **kwargs)

            monkeypatch.setattr(network, "fetch", interrupted)
        else:
            original = import_snapshot

            def cancelled(*args: Any, **kwargs: Any) -> Any:
                value = original(*args, **kwargs)
                cancel()
                return value

            monkeypatch.setattr(module, "import_snapshot", cancelled)
        assert worker.once()
    assert read(database, job_id).state == "cancelled"
    with Session(database) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(GeoDatasetRecord)) == 0


def test_unverified_installation_never_restarts_old_heavy_work(
    database: Engine, tmp_path: Path
) -> None:
    job_id = create(database)
    with ProcessLock(tmp_path / "old") as process:
        assert Worker(database, approved(), process).claim() == job_id
    make_due(database, job_id)
    with ProcessLock(tmp_path / "different") as process:
        assert not Worker(database, approved(), process).once()
    assert read(database, job_id).state == "recovery_required"


def test_operator_api_events_and_guest_isolation(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def session() -> Iterator[Session]:
        with Session(database) as db, db.begin():
            yield db

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[load_registry] = approved
    monkeypatch.setenv("BA_ACQUISITION_ENABLED", "1")
    token = "synthetic-operator-fixture-32-characters"
    monkeypatch.setenv("BA_ACQUISITION_OPERATOR_TOKEN", token)
    headers = {"X-Acquisition-Token": token}
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/acquisitions", json=request().model_dump(mode="json"), headers=headers
            )
            assert response.status_code == 202, response.text
            job_id = response.json()["id"]
            url = "/api/v2/acquisitions/" + job_id
            for unauthorized in (
                {},
                {"X-Conversation-Token": "guest-fixture"},
                {"X-Acquisition-Token": "wrong"},
            ):
                assert client.get(url, headers=unauthorized).status_code == 401
            assert client.post(url + "/cancel", headers=headers).json()["state"] == "cancelled"
            events = client.get(url + "/events?after=0&limit=1", headers=headers).json()
            assert len(events) == 1 and events[0]["sequence"] == 1
            assert client.get(url + "/events?after=1", headers=headers).json()[0]["sequence"] == 2
            assert token not in client.get(url, headers=headers).text
    finally:
        app.dependency_overrides.clear()


def test_populated_0008_upgrade_is_additive_and_repeatable() -> None:
    with isolated_database() as name:
        migrate(name, "upgrade", "0008_analytical_reports")
        engine = sa.create_engine("postgresql+psycopg://", connect_args={"dbname": name})
        try:
            populate(engine)
            with Session(engine) as db, db.begin():
                manifest, doc = load_snapshot(Path(__file__).parent / "fixtures/kazan.raw.json")
                import_snapshot(db, manifest, doc)
            before = fingerprints(name)
            migrate(name, "upgrade", "head")
            migrate(name, "upgrade", "head")
            migrate(name, "check")
            after = fingerprints(name)
            assert {key: after[key] for key in before} == before
        finally:
            engine.dispose()


def test_retry_budget_and_resource_failure(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = create(database)

    def unavailable(*args: Any, **kwargs: Any) -> int:
        raise AcquisitionError("network_timeout", retryable=True, retry_after=300)

    monkeypatch.setattr(network, "fetch", unavailable)
    with ProcessLock(tmp_path) as process:
        worker = Worker(database, approved(), process)
        assert worker.once()
        failed_attempt = read(database, job_id)
        assert failed_attempt.state == "retry_wait"
        assert (failed_attempt.next_attempt_at - failed_attempt.updated_at).total_seconds() > 299
        make_due(database, job_id)
        # Test clock only: both simulated requests remain within the source budget.
        with Session(database) as db, db.begin():
            db.execute(
                sa.text(
                    "UPDATE acquisition_events SET timestamp=timestamp-interval '10 minutes' "
                    "WHERE message_code='fetch_reserved'"
                )
            )
        assert worker.once()
    assert read(database, job_id).state == "failed" and read(database, job_id).attempt == 2
    other = create(database, request("resource-failure-key"))
    import app.data.acquisition.worker as module

    monkeypatch.setattr(module, "peak_memory", lambda: 10**12)
    with ProcessLock(tmp_path) as process:
        assert Worker(database, approved(), process).once()
    assert read(database, other).error_code == "acquisition_memory_limit"


def test_failed_refresh_preserves_previous_active_version(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_fetch(monkeypatch)
    first = create(database)
    with ProcessLock(tmp_path) as process:
        assert Worker(database, approved(), process).once()
    result = read(database, first).result
    assert result
    slug, version = result["dataset_slug"], result["data_version"]
    # Only this disposable fixture is aged to require a refresh.
    with Session(database) as db, db.begin():
        db.execute(
            sa.update(GeoDatasetRecord)
            .where(GeoDatasetRecord.slug == slug)
            .values(osm_base=datetime.now(UTC) - timedelta(days=31))
        )
        db.execute(
            sa.text(
                "UPDATE acquisition_events SET timestamp=timestamp-interval '10 minutes' "
                "WHERE message_code='fetch_reserved'"
            )
        )
    second = create(database, request("refresh-failure-key"))
    import app.data.acquisition.worker as module

    original = import_snapshot

    def reject(*args: Any, **kwargs: Any) -> Any:
        original(*args, **kwargs)
        raise AcquisitionError("import_validation_failed")

    monkeypatch.setattr(module, "import_snapshot", reject)
    with ProcessLock(tmp_path) as process:
        assert Worker(database, approved(), process).once()
    assert read(database, second).state == "failed"
    with Session(database) as db:
        active = db.scalar(
            sa.select(GeoDatasetRecord).where(
                GeoDatasetRecord.slug == slug, GeoDatasetRecord.active
            )
        )
        assert active and active.data_version == version and active.poi_count == 1


def test_local_cache_does_not_require_remote_permission(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_fetch(monkeypatch)
    create(database)
    with ProcessLock(tmp_path) as process:
        assert Worker(database, approved(), process).once()
    with Session(database) as db, db.begin():
        result = service.create(db, request("offline-cache-key"), load_registry())
    assert result.state == "succeeded" and result.result and result.result["reused_cache"] == 1


@pytest.mark.parametrize("lost", ["lease", "fence"])
def test_late_publication_is_rolled_back(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lost: str
) -> None:
    fake_fetch(monkeypatch)
    job_id = create(database)
    import app.data.acquisition.worker as module

    original = import_snapshot

    def invalidate_after_import(*args: Any, **kwargs: Any) -> Any:
        value = original(*args, **kwargs)
        with Session(database) as db, db.begin():
            job = service.get_job(db, job_id, lock=True)
            if lost == "fence":
                job.fencing_token += 1
            else:
                job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        return value

    monkeypatch.setattr(module, "import_snapshot", invalidate_after_import)
    with ProcessLock(tmp_path) as process:
        assert Worker(database, approved(), process).once()
    assert read(database, job_id).state != "succeeded"
    with Session(database) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(GeoDatasetRecord)) == 0


def test_recovery_waits_for_old_server_statement(database: Engine, tmp_path: Path) -> None:
    job_id = create(database)
    with ProcessLock(tmp_path) as process:
        assert Worker(database, approved(), process).claim() == job_id
    make_due(database, job_id)

    def old_backend() -> None:
        with database.connect() as connection:
            connection.execute(
                sa.text("SELECT set_config('application_name',:tag,false)"),
                {"tag": "ba-acq-" + str(job_id)},
            )
            connection.execute(sa.text("SELECT pg_sleep(3)"))
            connection.rollback()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(old_backend)
        deadline = time.monotonic() + 2
        active = False
        while time.monotonic() < deadline:
            with database.connect() as connection:
                active = bool(
                    connection.scalar(
                        sa.text(
                            "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                            "WHERE application_name=:tag AND state='active')"
                        ),
                        {"tag": "ba-acq-" + str(job_id)},
                    )
                )
            if active:
                break
            time.sleep(0.01)
        assert active
        with Session(database) as db, db.begin():
            service.cancel(db, job_id)
        with ProcessLock(tmp_path) as process:
            assert not Worker(database, approved(), process).once()
        assert read(database, job_id).state == "recovery_required"
        future.result()
    with ProcessLock(tmp_path) as process:
        assert not Worker(database, approved(), process).once()
    assert read(database, job_id).state == "cancelled"


def test_skip_locked_does_not_hide_old_active_work(database: Engine, tmp_path: Path) -> None:
    first = create(database)
    second = create(
        database, request("queued-other-scope").model_copy(update={"territory": "ru-kazan"})
    )
    with ProcessLock(tmp_path) as process:
        assert Worker(database, approved(), process).claim() == first
    make_due(database, first)
    with Session(database) as locked, locked.begin():
        service.get_job(locked, first, lock=True)
        with ProcessLock(tmp_path) as process:
            assert not Worker(database, approved(), process).once()
    assert read(database, second).state == "queued"


def test_metadata_capacity_never_publishes_an_invisible_dataset(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(database) as db, db.begin():
        manifest, document = load_snapshot(Path(__file__).parent / "fixtures/kazan.raw.json")
        import_snapshot(db, manifest, document)
    cfg = approved().model_copy(update={"max_datasets": 1})
    with Session(database) as db, db.begin():
        job = service.create(db, request(), cfg)
    fake_fetch(monkeypatch)
    with ProcessLock(tmp_path) as process:
        assert Worker(database, cfg, process).once()
    assert read(database, job.id).error_code == "acquisition_metadata_limit"
    with Session(database) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(GeoDatasetRecord)) == 1


def test_changed_worker_resource_policy_never_fetches(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.data.acquisition.schemas import resources

    job_id = create(database)
    calls = fake_fetch(monkeypatch)
    with monkeypatch.context() as policy:
        policy.setenv("BA_ACQUISITION_LIMITS_JSON", '{"max_area_m2":100}')
        resources.cache_clear()
        try:
            with ProcessLock(tmp_path) as process:
                assert Worker(database, approved(), process).once()
        finally:
            resources.cache_clear()
    assert not calls and read(database, job_id).error_code == "acquisition_policy_changed"
