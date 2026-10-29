"""Operator-only acquisition; guest tokens never grant import or job visibility."""

import os
import secrets
from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.registry import Registry
from app.data.acquisition import service
from app.data.acquisition.schemas import (
    AcquisitionError,
    AcquisitionEvent,
    AcquisitionRequest,
    JobView,
)
from app.db.models import AcquisitionEventRecord
from app.db.session import get_session


def operator(token: Annotated[str | None, Header(alias="X-Acquisition-Token")] = None) -> None:
    expected = os.getenv("BA_ACQUISITION_OPERATOR_TOKEN", "")
    if os.getenv("BA_ACQUISITION_ENABLED") != "1" or len(expected) < 32:
        raise HTTPException(503, detail={"code": "acquisition_disabled"})
    if token is None or not secrets.compare_digest(expected.encode(), token.encode()):
        raise HTTPException(401, detail={"code": "acquisition_operator_required"})


router = APIRouter(
    prefix="/api/v2/acquisitions", tags=["acquisition"], dependencies=[Depends(operator)]
)
Database = Annotated[Session, Depends(get_session, scope="function")]


@router.post("", response_model=JobView, status_code=202)
def create_job(body: AcquisitionRequest, session: Database, registry: Registry) -> JobView:
    try:
        return service.create(session, body, registry)
    except AcquisitionError as error:
        raise HTTPException(
            403 if error.code == "source_not_permitted" else 422,
            detail={"code": error.code},
        ) from None


@router.get("/{job_id}", response_model=JobView)
def read_job(job_id: UUID, session: Database) -> JobView:
    return service.view(service.get_job(session, job_id))


@router.post("/{job_id}/cancel", response_model=JobView, status_code=202)
def cancel_job(job_id: UUID, session: Database) -> JobView:
    return service.cancel(session, job_id)


@router.get("/{job_id}/events", response_model=tuple[AcquisitionEvent, ...])
def events(
    job_id: UUID,
    session: Database,
    after: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> tuple[AcquisitionEvent, ...]:
    service.get_job(session, job_id)
    rows = session.scalars(
        sa.select(AcquisitionEventRecord)
        .where(
            AcquisitionEventRecord.job_id == job_id,
            AcquisitionEventRecord.sequence > after,
        )
        .order_by(AcquisitionEventRecord.sequence)
        .limit(limit)
    ).all()
    return tuple(
        AcquisitionEvent.model_validate(
            {
                "job_id": row.job_id,
                "sequence": row.sequence,
                "timestamp": row.timestamp,
                "stage": row.stage,
                "state": row.state,
                "message_code": row.message_code,
                "completed": None,
                "total": None,
                "unit": None,
            }
        )
        for row in rows
    )
