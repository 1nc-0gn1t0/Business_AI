import logging
from typing import Annotated, Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from app.adapters.llm import LLMError
from app.api.conversations import error_detail, router
from app.api.geo import router as geo_router
from app.db.health import check_postgis
from app.services.conversations import ConversationNotFound, IncompleteProfile, VersionConflict

logger = logging.getLogger(__name__)
app = FastAPI(title="Business AI", version="0.1.0")
app.include_router(router)
app.include_router(geo_router)


async def conversation_error(request: Request, error: Exception) -> JSONResponse:
    if isinstance(error, LLMError):
        logger.warning("Local LLM failed code=%s trace_id=%s", error.code, error.trace_id)
    status, detail = error_detail(error)
    return JSONResponse(status_code=status, content={"detail": detail})


for error_type in (
    ConversationNotFound,
    IncompleteProfile,
    VersionConflict,
    ValidationError,
    LLMError,
):
    app.add_exception_handler(error_type, conversation_error)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"
    postgis_version: str


def get_postgis_version() -> str:
    try:
        return check_postgis()
    except psycopg.Error:
        # Do not include connection strings or database errors in public responses/logs.
        logger.warning("Database readiness check failed")
        raise HTTPException(status_code=503, detail="Database is unavailable") from None


@app.get("/healthz", response_model=HealthResponse)
def healthz(postgis_version: Annotated[str, Depends(get_postgis_version)]) -> HealthResponse:
    return HealthResponse(postgis_version=postgis_version)
