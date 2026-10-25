from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Response

from app.api.conversations import Database, Token
from app.data.providers import demo_enabled
from app.reporting.schemas import ReportRequest, ReportSnapshot, ReportView
from app.reporting.service import describe, fail, load, prepare, serialize

router = APIRouter(prefix="/api/v1/conversations/{conversation_id}/reports", tags=["reports"])


@router.post("", response_model=ReportView, status_code=201)
def create_report(
    conversation_id: UUID, body: ReportRequest, token: Token, session: Database
) -> ReportView:
    return prepare(session, conversation_id, token, body)


@router.get("/{report_id}", response_model=ReportView)
def report_metadata(
    conversation_id: UUID, report_id: UUID, token: Token, session: Database
) -> ReportView:
    row, snapshot, current = load(session, conversation_id, token, report_id)
    return describe(session, row, snapshot, current)


@router.get(
    "/{report_id}/file",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                "application/json": {"schema": {"$ref": "#/components/schemas/ReportSnapshot"}},
            }
        }
    },
)
def download_report(
    conversation_id: UUID,
    report_id: UUID,
    token: Token,
    session: Database,
    format: Literal["pdf", "json"],
    historical: bool = False,
) -> Response:
    row, snapshot, current = load(session, conversation_id, token, report_id)
    if any(p.dataset.provider == "synthetic" for p in snapshot.providers) and not demo_enabled():
        fail("demo_data_disabled", 403)
    metadata = describe(session, row, snapshot, current)
    if metadata.status == "outdated" and not historical:
        fail("report_outdated")
    value = row.pdf if format == "pdf" else serialize(snapshot)
    return Response(
        content=value,
        media_type="application/pdf" if format == "pdf" else "application/json",
        headers={
            "Content-Disposition": f'attachment; filename="BusinessAI-report-{row.id}.{format}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Report-Snapshot-SHA256": row.snapshot_sha256,
            "X-Report-Status": metadata.status,
        },
    )


@router.get("/{report_id}/snapshot", response_model=ReportSnapshot)
def report_snapshot(
    conversation_id: UUID,
    report_id: UUID,
    token: Token,
    session: Database,
    response: Response,
    historical: bool = False,
) -> ReportSnapshot:
    file = download_report(conversation_id, report_id, token, session, "json", historical)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return ReportSnapshot.model_validate_json(bytes(file.body))
