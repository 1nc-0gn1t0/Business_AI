import logging
from typing import Annotated, Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app.db.health import check_postgis

logger = logging.getLogger(__name__)
app = FastAPI(title="Business AI", version="0.1.0")


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
