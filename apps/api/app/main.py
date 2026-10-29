import logging
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.adapters.llm import LLMError
from app.agent.tools import AgentError
from app.api.acquisition import router as acquisition_router
from app.api.agent import router as agent_router
from app.api.bank import router as bank_router
from app.api.conversations import error_detail, router
from app.api.data import router as data_router
from app.api.finance import router as finance_router
from app.api.geo import router as geo_router
from app.api.industry import router as industry_router
from app.api.leads import public_router as consent_text_router
from app.api.leads import router as leads_router
from app.api.registry import router as registry_router
from app.api.reports import router as reports_router
from app.api.schemas import Contract
from app.db.health import check_postgis
from app.diagnostics import Diagnostics, configure_logging, database_failure_code
from app.leads.policy import LeadError
from app.limits.http import ApiLimits, reset_admission
from app.limits.inference import reset_inference
from app.readiness import Readiness, bundle, database_probe
from app.services.conversations import ConversationNotFound, IncompleteProfile, VersionConflict

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    reset_admission()
    reset_inference()
    yield


app = FastAPI(title="Business AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(ApiLimits)
app.add_middleware(Diagnostics)
app.include_router(router)
app.include_router(geo_router)
app.include_router(finance_router)
app.include_router(bank_router)
app.include_router(data_router)
app.include_router(registry_router)
app.include_router(acquisition_router)
app.include_router(agent_router)
app.include_router(industry_router)
app.include_router(leads_router)
app.include_router(consent_text_router)
app.include_router(reports_router)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
    # Preserve useful type/known field locations; never reflect input, ctx or arbitrary keys.
    names = {"body", "path", "query", "header", "report_id"}
    models = list(Contract.__subclasses__())
    while models:
        model = models.pop()
        names.update(model.model_fields)
        models.extend(model.__subclasses__())
    messages = {
        "string_too_long": "Строка превышает допустимую длину",
        "too_long": "Слишком много элементов",
        "missing": "Обязательное поле",
        "extra_forbidden": "Лишние поля не принимаются",
    }
    details = [
        {
            "type": item["type"],
            "loc": [v if isinstance(v, int) or v in names else "<field>" for v in item["loc"][:16]],
            "msg": messages.get(item["type"], "Недопустимое значение или тип"),
        }
        for item in error.errors()[:16]
    ]
    return JSONResponse(status_code=422, content={"detail": details})


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
    # SQLAlchemy exception strings can contain SQL parameters and connection details.
    logger.warning("Database operation failed")
    return JSONResponse(status_code=503, content={"detail": {"code": database_failure_code(error)}})


@app.exception_handler(LeadError)
async def lead_error(request: Request, error: LeadError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content={"detail": {"code": error.code}})


@app.exception_handler(AgentError)
async def agent_error(request: Request, error: AgentError) -> JSONResponse:
    return JSONResponse(
        status_code=504 if error.code == "agent_deadline_exceeded" else 422,
        content={"detail": {"code": error.code}},
    )


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


@app.get("/livez")
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", response_model=Readiness)
async def readyz() -> JSONResponse:
    result = await database_probe()
    payload = result.model_dump()
    if result.status != "ok":
        code = (
            "database_schema_incompatible"
            if result.schema_status == "incompatible"
            else "postgis_unavailable"
            if result.postgis in {"missing", "unavailable"}
            else "database_unavailable"
        )
        return JSONResponse({**payload, "detail": {"code": code}}, 503)
    return JSONResponse(payload)


@app.get("/api/v1/diagnostics", include_in_schema=False)
async def diagnostics(request: Request) -> dict[str, object]:
    secret = os.getenv("BA_DIAGNOSTICS_TOKEN", "")
    if len(secret) < 32 or not secrets.compare_digest(
        request.headers.get("X-Diagnostics-Token", "").encode(), secret.encode()
    ):
        raise HTTPException(404, detail={"code": "not_found"})
    return await bundle()
