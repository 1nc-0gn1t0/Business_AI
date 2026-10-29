"""One operator-started process. Durable checkpoints; no subprocess import or LLM calls."""

import argparse
import hashlib
import os
import shutil
import sys
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.data.acquisition import network
from app.data.acquisition.schemas import TERMINAL, AcquisitionError, AcquisitionRequest, resources
from app.data.acquisition.service import emit, get_job, lock_control, policy_hash, validate
from app.data.registry import load_registry
from app.data.registry_schemas import RegistryConfig
from app.db.models import AcquisitionEventRecord, AcquisitionJobRecord, GeoDatasetRecord
from app.db.session import get_engine
from app.geo.ingest import import_snapshot
from app.geo.provider import (
    GeoImportError,
    build_poi_query,
    load_snapshot,
    parse_document,
    save_snapshot,
)


def peak_memory() -> int:
    if sys.platform != "linux":
        return 0
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


class ProcessLock(AbstractContextManager["ProcessLock"]):
    """Mandatory stable shared state directory; OS lock proves previous process stopped.

    Other installations cannot recover an expired job. A lost DB session alone never
    releases this lock. No child heavy processes exist to outlive its owner.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.handle: Any = None
        self.installation = ""

    def __enter__(self) -> "ProcessLock":
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.handle = (self.root / "worker.lock").open("a+b")
        try:
            if sys.platform == "win32":
                import msvcrt

                self.handle.seek(0)
                if not self.handle.read(1):
                    self.handle.write(b"0")
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise AcquisitionError("worker_already_running") from None
        identity = self.root / "installation"
        if not identity.exists():
            identity.write_text(str(uuid4()), encoding="ascii")
        self.installation = str(UUID(identity.read_text(encoding="ascii").strip()))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.handle:
            self.handle.close()


class Worker:
    def __init__(self, engine: Engine, registry: RegistryConfig, process: ProcessLock) -> None:
        if not process.handle or process.handle.closed or not process.installation:
            raise AcquisitionError("worker_process_lock_required")
        self.engine, self.registry, self.process = engine, registry, process
        self.job_id: UUID | None = None
        self.token = 0
        self.started = 0.0
        self.cpu_started = 0.0
        self.last_heartbeat = 0.0

    def claim(self) -> UUID | None:
        with Session(self.engine) as session, session.begin():
            lock_control(session)
            now = datetime.now(UTC)
            busy_ids = set(
                session.scalars(
                    sa.select(AcquisitionJobRecord.id).where(
                        AcquisitionJobRecord.state.not_in((*TERMINAL, "queued", "retry_wait")),
                    )
                ).all()
            )
            jobs = session.scalars(
                sa.select(AcquisitionJobRecord)
                .where(
                    AcquisitionJobRecord.state.not_in(TERMINAL),
                )
                .order_by(AcquisitionJobRecord.created_at)
                .with_for_update(skip_locked=True)
            ).all()
            # SKIP LOCKED must never hide an old active job and admit another heavy task.
            if not busy_ids <= {j.id for j in jobs}:
                return None
            if session.scalar(
                sa.text(
                    "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                    "WHERE application_name LIKE 'ba-acq-%' AND datname=current_database() "
                    "AND pid<>pg_backend_pid() AND state='active')"
                )
            ):
                for pending in jobs:
                    if pending.id in busy_ids and pending.state != "recovery_required":
                        emit(
                            session,
                            pending,
                            "recovery_required",
                            pending.stage,
                            "import_backend_still_running",
                        )
                return None
            for job in jobs:
                if job.state in {"queued", "retry_wait"}:
                    continue
                if job.lease_until is not None and job.lease_until > now:
                    return None
                # Same stable installation + held process lock: old in-process work stopped.
                if job.installation != self.process.installation:
                    if job.state != "recovery_required":
                        emit(
                            session,
                            job,
                            "recovery_required",
                            job.stage,
                            "worker_identity_unverified",
                        )
                    return None
                job.fencing_token += 1
                cancelled = (
                    job.state == "cancel_requested"
                    or job.checkpoint.get("cancel_requested") is True
                )
                state = (
                    "cancelled"
                    if cancelled
                    else "failed"
                    if job.attempt >= resources().max_attempts
                    else "retry_wait"
                )
                emit(
                    session,
                    job,
                    state,
                    "cancelled" if cancelled else "recovering",
                    "stopped_worker_recovered",
                )
                job.next_attempt_at = now + timedelta(seconds=resources().request_interval_seconds)
                if state in TERMINAL:
                    job.artifact = None
            session.flush()
            selected = next(
                (
                    j
                    for j in jobs
                    if j.state in {"queued", "retry_wait"} and j.next_attempt_at <= now
                ),
                None,
            )
            if selected is None:
                return None
            job = selected
            job.attempt += 1
            job.fencing_token += 1
            job.installation = self.process.installation
            job.lease_until = now + timedelta(seconds=resources().lease_seconds)
            job.error_code = None
            emit(session, job, "claimed", "checking_permissions", "worker_claimed")
            self.job_id, self.token = job.id, job.fencing_token
            self.started, self.last_heartbeat = time.monotonic(), 0
            self.cpu_started = time.process_time()
            return job.id

    def guard(self, session: Session) -> AcquisitionJobRecord:
        assert self.job_id is not None
        job = get_job(session, self.job_id, lock=True)
        if job.fencing_token != self.token or job.installation != self.process.installation:
            raise AcquisitionError("worker_fenced")
        if job.state == "cancel_requested" or job.checkpoint.get("cancel_requested") is True:
            raise AcquisitionError("acquisition_cancelled")
        if job.state in TERMINAL or job.lease_until is None or job.lease_until <= datetime.now(UTC):
            raise AcquisitionError("worker_lease_lost")
        if job.policy_hash != policy_hash(self.registry):
            raise AcquisitionError("acquisition_policy_changed")
        validate(AcquisitionRequest.model_validate(job.request), self.registry)
        return job

    def check(self) -> None:
        if time.monotonic() - self.started > resources().job_seconds:
            raise AcquisitionError("acquisition_deadline")
        if peak_memory() > resources().max_rss_bytes:
            raise AcquisitionError("acquisition_memory_limit")
        if time.monotonic() - self.last_heartbeat < 1:
            return
        with Session(self.engine) as session, session.begin():
            job = self.guard(session)
            job.lease_until = datetime.now(UTC) + timedelta(seconds=resources().lease_seconds)
        self.last_heartbeat = time.monotonic()

    def stage(self, state: str, stage: str) -> None:
        self.check()
        with Session(self.engine) as session, session.begin():
            emit(session, self.guard(session), state, stage, state)

    def reserve_fetch(self) -> None:
        with Session(self.engine) as session, session.begin():
            job = self.guard(session)
            since = datetime.now(UTC) - timedelta(days=1)
            stamps = session.scalars(
                sa.select(AcquisitionEventRecord.timestamp)
                .where(
                    AcquisitionEventRecord.message_code == "fetch_reserved",
                    AcquisitionEventRecord.timestamp >= since,
                )
                .order_by(AcquisitionEventRecord.timestamp.desc())
                .limit(11)
            ).all()
            if (
                len(stamps) >= resources().requests_per_day
                or stamps
                and (datetime.now(UTC) - stamps[0]).total_seconds()
                < resources().request_interval_seconds
            ):
                raise AcquisitionError("source_rate_limited", retryable=True)
            emit(session, job, "fetching", "downloading", "fetch_reserved")

    def execute(self) -> None:
        assert self.job_id is not None
        self.check()
        with Session(self.engine) as session:
            job = get_job(session, self.job_id)
            request = AcquisitionRequest.model_validate(job.request)
            artifact, checkpoint = job.artifact, job.checkpoint
            expected = job.expected_version
            slug = "acq-osm-" + job.scope_hash[:32]
        city = validate(request, self.registry)
        if shutil.disk_usage(self.process.root).free < resources().min_free_bytes:
            raise AcquisitionError("acquisition_disk_limit")
        with workspace(self.process) as folder:
            path = folder / "snapshot.json"
            if artifact is None:
                self.reserve_fetch()
                download_started = time.monotonic()
                raw_path = folder / "download.json"
                size = network.fetch(
                    build_poi_query(request.aoi), raw_path, resources().max_bytes, self.check
                )
                download_seconds = time.monotonic() - download_started
                self.stage("validating", "checking_file")
                raw = raw_path.read_bytes()
                document = parse_document(raw)
                if len(document["elements"]) > resources().max_elements:
                    raise AcquisitionError("acquisition_element_limit")
                source_elements = len(document["elements"])
                # Reject malformed objects rather than claim complete layer coverage.
                if any(not isinstance(e, dict) for e in document["elements"]):
                    raise AcquisitionError("source_format_invalid")
                del document
                manifest = save_snapshot(
                    raw,
                    path,
                    slug=slug,
                    city=city,
                    bbox=request.aoi,
                    endpoint=network.ENDPOINT,
                    query=build_poi_query(request.aoi),
                )
                del raw
                artifact = path.read_bytes()
                if len(artifact) > resources().max_bytes:
                    raise AcquisitionError("download_size_exceeded")
                checkpoint = {
                    "manifest": manifest.model_dump(mode="json"),
                    "raw_bytes": size,
                    "download_seconds": download_seconds,
                    "artifact_sha256": manifest.sha256,
                    "source_elements": source_elements,
                }
                self.check()
                with Session(self.engine) as session, session.begin():
                    job = self.guard(session)
                    job.artifact, job.checkpoint = artifact, checkpoint
                    emit(session, job, "validating", "checking_file", "artifact_checkpoint_saved")
            else:
                if len(artifact) > resources().max_bytes or hashlib.sha256(
                    artifact
                ).hexdigest() != checkpoint.get("artifact_sha256"):
                    raise AcquisitionError("checkpoint_invalid")
                path.write_bytes(artifact)
                path.with_suffix(".manifest.json").write_text(
                    json_dump(checkpoint["manifest"]), encoding="utf-8"
                )
            del artifact
            manifest, document = load_snapshot(path)
            if (
                manifest.slug != slug
                or manifest.bbox != request.aoi
                or manifest.query != build_poi_query(request.aoi)
            ):
                raise AcquisitionError("checkpoint_invalid")
            self.stage("importing", "importing_postgis")
            started, cpu = time.monotonic(), time.process_time()
            with Session(self.engine) as session, session.begin():
                session.execute(sa.text("SET LOCAL statement_timeout='25000'"))
                session.execute(
                    sa.text("SELECT set_config('application_name',:tag,true)"),
                    {"tag": "ba-acq-" + str(self.job_id)},
                )
                before = session.scalar(sa.text("SELECT pg_database_size(current_database())"))
                session.execute(
                    sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                    {"key": "business-ai:osm:" + slug},
                )
                current = session.scalar(
                    sa.select(GeoDatasetRecord).where(
                        GeoDatasetRecord.slug == slug, GeoDatasetRecord.active
                    )
                )
                if (current.data_version if current else None) != expected:
                    raise AcquisitionError("dataset_version_conflict")
                if current is None:
                    metadata_count = session.scalar(
                        sa.text(
                            "SELECT (SELECT count(*) FROM geo_datasets WHERE active) + "
                            "(SELECT count(*) FROM walk_graphs WHERE active)"
                        )
                    )
                    if metadata_count is None or metadata_count >= self.registry.max_datasets:
                        raise AcquisitionError("acquisition_metadata_limit")
                record = import_snapshot(session, manifest, document, checkpoint=self.check)
                self.stage("verifying", "checking_postgis")
                # Data and activation are still invisible; failure below rolls everything back.
                invalid = session.scalar(
                    sa.text(
                        "SELECT count(*) FROM geo_pois WHERE dataset_id=:id "
                        "AND (NOT ST_IsValid(geom) OR ST_SRID(geom)<>4326)"
                    ),
                    {"id": record.id},
                )
                if invalid or any(
                    record.diagnostics.get(key, 0)
                    for key in (
                        "invalid_metadata",
                        "invalid_tags",
                        "missing_location",
                        "invalid_element",
                    )
                ):
                    raise AcquisitionError("import_validation_failed")
                self.check()
                job = self.guard(session)
                after = session.scalar(sa.text("SELECT pg_database_size(current_database())"))
                emit(session, job, "activating", "publishing_dataset", "dataset_verified")
                job.result = {
                    "dataset_slug": slug,
                    "data_version": record.data_version,
                    "poi_count": record.poi_count,
                    "reused_cache": 0,
                    "raw_bytes": checkpoint["raw_bytes"],
                    "artifact_bytes": path.stat().st_size,
                    "download_seconds": checkpoint["download_seconds"],
                    "import_seconds": time.monotonic() - started,
                    "import_cpu_seconds": time.process_time() - cpu,
                    "active_cpu_seconds": time.process_time() - self.cpu_started,
                    "active_seconds": time.monotonic() - self.started,
                    "temporary_bytes": sum(
                        p.stat().st_size for p in folder.iterdir() if p.is_file()
                    ),
                    "peak_rss_bytes": peak_memory(),
                    "postgres_growth_bytes": max(0, (after or 0) - (before or 0)),
                }
                job.artifact = None
                emit(session, job, "succeeded", "completed", "dataset_published")

    def finish_error(self, error: AcquisitionError) -> None:
        assert self.job_id is not None
        with Session(self.engine) as session, session.begin():
            job = get_job(session, self.job_id, lock=True)
            if job.fencing_token != self.token or job.state in TERMINAL:
                return
            cancelled = (
                job.state == "cancel_requested"
                or job.checkpoint.get("cancel_requested") is True
                or error.code == "acquisition_cancelled"
            )
            retry = error.retryable and job.attempt < resources().max_attempts and not cancelled
            state = "cancelled" if cancelled else "retry_wait" if retry else "failed"
            job.error_code = error.code
            job.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=max(resources().request_interval_seconds, error.retry_after)
            )
            emit(session, job, state, "cancelled" if cancelled else job.stage, error.code)
            if state in TERMINAL:
                job.artifact = None

    def once(self) -> bool:
        # DB session advisory lock supplements process lock; explicit unlock before pool return.
        with self.engine.connect() as lock:
            acquired = lock.scalar(sa.text("SELECT pg_try_advisory_lock(782493202)"))
            lock.commit()
            if not acquired:
                return False
            try:
                if self.claim() is None:
                    return False
                try:
                    self.execute()
                except AcquisitionError as error:
                    self.finish_error(error)
                except GeoImportError:
                    self.finish_error(AcquisitionError("source_format_invalid"))
                except (ValueError, KeyError, TypeError, OSError):
                    self.finish_error(AcquisitionError("artifact_invalid"))
                # Unexpected DB/process failures propagate, retaining the durable recovery state.
                return True
            finally:
                lock.execute(sa.text("SELECT pg_advisory_unlock(782493202)"))
                lock.commit()


def json_dump(value: object) -> str:
    import json

    return json.dumps(value)


@contextmanager
def workspace(process: ProcessLock) -> Iterator[Path]:
    path = process.root / "staging"

    def clean() -> None:
        if path.is_symlink() or path.resolve().parent != process.root:
            raise AcquisitionError("staging_ownership_invalid")
        if path.exists():
            if not any(path.iterdir()):
                path.rmdir()
            elif (path / "owner").read_text(encoding="ascii") == process.installation:
                shutil.rmtree(path)
            else:
                raise AcquisitionError("staging_ownership_invalid")

    # Held process lock proves no previous in-process importer can still use these files.
    clean()
    path.mkdir(mode=0o700)
    (path / "owner").write_text(process.installation, encoding="ascii")
    try:
        yield path
    finally:
        clean()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if sys.platform != "linux" or os.getenv("BA_ACQUISITION_ENABLED") != "1":
        raise SystemExit("Worker requires Linux/WSL2 and explicit acquisition enablement")
    try:
        with ProcessLock(args.state_dir) as process:
            worker = Worker(get_engine(), load_registry(), process)
            while True:
                worker.once()
                if args.once:
                    break
                time.sleep(2)
    except Exception:
        # Never print exception strings, response bodies, DSNs, URLs, tokens or local paths.
        raise SystemExit("Acquisition worker stopped; inspect durable job status safely") from None


if __name__ == "__main__":
    main()
