"""Short transactional job operations. All callers are operator-authorized."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.data.acquisition.schemas import (
    TERMINAL,
    AcquisitionError,
    AcquisitionRequest,
    JobView,
    resources,
)
from app.data.coverage import coverage
from app.data.registry import config_hash, permitted, source_definition
from app.data.registry_schemas import CoverageQuery, RegistryConfig
from app.db.models import (
    AcquisitionEventRecord,
    AcquisitionJobRecord,
    AcquisitionRequestRecord,
    GeoDatasetRecord,
)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def policy_hash(registry: RegistryConfig) -> str:
    return digest(
        {"registry": config_hash(registry), "resources": resources().model_dump(mode="json")}
    )


def validate(
    request: AcquisitionRequest, registry: RegistryConfig, *, need_network: bool = True
) -> str:
    source = source_definition(registry, request.source_id)
    if (
        source.id != "osm"
        or source.adapter_id != "osm"
        or source.adapter_status != "ready"
        or not permitted(source, "local_analysis")
    ):
        raise AcquisitionError("source_not_permitted")
    if need_network and (
        source.network_permission != "permitted"
        or source.availability not in {"ready", "degraded"}
        or "operator_fetch" not in source.acquisition_methods
        or source.acquisition_scope != "operator_smoke"
        or source.acquisition_approved_until is None
        or source.acquisition_approved_until <= datetime.now(UTC)
    ):
        raise AcquisitionError("source_not_permitted")
    if request.category != "geo.mapped_poi" or request.category not in source.categories:
        raise AcquisitionError("acquisition_category_unsupported")
    territory = next((t for t in registry.territories if t.id == request.territory), None)
    if territory is None:
        raise AcquisitionError("territory_unknown")
    return territory.name


def lock_control(session: Session) -> None:
    session.execute(sa.text("SELECT pg_advisory_xact_lock(782493201)"))


def emit(session: Session, job: AcquisitionJobRecord, state: str, stage: str, code: str) -> None:
    job.state, job.stage = state, stage
    job.updated_at = datetime.now(UTC)
    job.event_cursor += 1
    session.add(
        AcquisitionEventRecord(
            job_id=job.id,
            sequence=job.event_cursor,
            timestamp=job.updated_at,
            state=state,
            stage=stage,
            message_code=code,
        )
    )


def get_job(session: Session, job_id: UUID, *, lock: bool = False) -> AcquisitionJobRecord:
    statement = sa.select(AcquisitionJobRecord).where(AcquisitionJobRecord.id == job_id)
    job = session.scalar(statement.with_for_update() if lock else statement)
    if job is None:
        raise HTTPException(404, detail={"code": "acquisition_job_not_found"})
    return job


def view(job: AcquisitionJobRecord) -> JobView:
    request = AcquisitionRequest.model_validate(job.request)
    return JobView.model_validate(
        {
            "id": job.id,
            "state": job.state,
            "stage": job.stage,
            "source_id": request.source_id,
            "category": request.category,
            "territory": request.territory,
            "aoi": request.aoi,
            "attempt": job.attempt,
            "fencing_token": job.fencing_token,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "next_attempt_at": job.next_attempt_at,
            "result": job.result,
            "error_code": job.error_code,
            "event_cursor": job.event_cursor,
        }
    )


def create(session: Session, request: AcquisitionRequest, registry: RegistryConfig) -> JobView:
    validate(request, registry, need_network=False)
    lock_control(session)
    payload = request.model_dump(mode="json", exclude={"idempotency_key"})
    fingerprint = digest(payload)
    existing = session.get(AcquisitionRequestRecord, request.idempotency_key)
    if existing:
        if existing.payload_hash != fingerprint:
            raise HTTPException(409, detail={"code": "idempotency_conflict"})
        return view(get_job(session, existing.job_id))
    limits = resources()
    if (
        session.scalar(sa.select(sa.func.count()).select_from(AcquisitionJobRecord)) or 0
    ) >= limits.max_retained_jobs or (
        session.scalar(sa.select(sa.func.count()).select_from(AcquisitionRequestRecord)) or 0
    ) >= limits.max_retained_jobs * 2:
        raise HTTPException(429, detail={"code": "acquisition_storage_limit"})
    b = request.aoi
    area = session.scalar(
        sa.text("SELECT ST_Area(ST_MakeEnvelope(:w,:s,:e,:n,4326)::geography)"),
        {"w": b.west, "s": b.south, "e": b.east, "n": b.north},
    )
    if area is None or area > limits.max_area_m2:
        raise HTTPException(422, detail={"code": "acquisition_aoi_too_large"})
    scope = digest(payload | {"adapter_revision": "poi-v1"})
    active = session.scalar(
        sa.select(AcquisitionJobRecord).where(
            AcquisitionJobRecord.scope_hash == scope,
            AcquisitionJobRecord.state.not_in(TERMINAL),
        )
    )
    if active:
        if active.policy_hash != policy_hash(registry):
            raise HTTPException(409, detail={"code": "acquisition_policy_conflict"})
        job = active
    else:
        assessment = coverage(
            session,
            CoverageQuery(
                territory=request.territory,
                aoi=request.aoi,
                categories=(request.category,),
            ),
            registry,
        )
        matches = [
            e
            for e in assessment.assessments[0].datasets
            if e.usable and e.spatial_fit == "full_for_requested_scope" and e.freshness == "current"
        ]
        if not assessment.metadata_complete:
            raise HTTPException(409, detail={"code": "acquisition_metadata_review_required"})
        pending = (
            session.scalar(
                sa.select(sa.func.count())
                .select_from(AcquisitionJobRecord)
                .where(
                    AcquisitionJobRecord.state.not_in(TERMINAL),
                )
            )
            or 0
        )
        if not matches and pending >= limits.max_pending:
            raise HTTPException(429, detail={"code": "acquisition_queue_full"})
        if not matches:
            validate(request, registry)
        now = datetime.now(UTC)
        slug = "acq-osm-" + scope[:32]
        current = session.scalar(
            sa.select(GeoDatasetRecord).where(
                GeoDatasetRecord.slug == slug,
                GeoDatasetRecord.active,
            )
        )
        job = AcquisitionJobRecord(
            id=uuid4(),
            state="queued",
            stage="checking_local_data",
            request=request.model_dump(mode="json"),
            scope_hash=scope,
            policy_hash=policy_hash(registry),
            expected_version=current.data_version if current else None,
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
        session.add(job)
        session.flush()
        if matches:
            dataset = matches[0].metadata
            job.result = {
                "dataset_slug": dataset.slug,
                "data_version": dataset.data_version,
                "reused_cache": 1,
            }
            emit(session, job, "succeeded", "completed", "local_cache_reused")
        else:
            emit(session, job, "queued", "checking_local_data", "acquisition_queued")
    session.add(
        AcquisitionRequestRecord(
            key=request.idempotency_key, payload_hash=fingerprint, job_id=job.id
        )
    )
    session.flush()
    return view(job)


def cancel(session: Session, job_id: UUID) -> JobView:
    job = get_job(session, job_id, lock=True)
    if job.state not in TERMINAL:
        job.checkpoint = job.checkpoint | {"cancel_requested": True}
        immediate = job.state in {"queued", "retry_wait"}
        emit(
            session,
            job,
            "cancelled" if immediate else "cancel_requested",
            "cancelled" if immediate else job.stage,
            "cancellation_requested",
        )
        if immediate:
            job.artifact = None
    session.flush()
    return view(job)
