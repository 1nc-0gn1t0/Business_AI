"""Cheap dependency probes and opt-in local diagnostic bundle (no inference)."""

import asyncio
import json

import httpx2
import psycopg
from pydantic import BaseModel

from app.adapters.llm import LLMError, get_llm

SCHEMA = "0008_analytical_reports"


class Readiness(BaseModel):
    status: str
    database: str
    postgis: str
    schema_status: str


async def database_probe() -> Readiness:
    database, postgis, schema = "unavailable", "unknown", "unknown"
    try:
        async with asyncio.timeout(4):
            async with await psycopg.AsyncConnection.connect(
                connect_timeout=2, options="-c statement_timeout=1000", autocommit=True
            ) as connection:
                database = "ok"
                cursor = await connection.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='postgis')"
                )
                row = await cursor.fetchone()
                postgis = "ok" if row and row[0] else "missing"
                if postgis == "ok":
                    await connection.execute("SELECT PostGIS_Version()")
                cursor = await connection.execute("SELECT version_num FROM public.alembic_version")
                versions = await cursor.fetchall()
                schema = "ok" if versions == [(SCHEMA,)] else "incompatible"
    except psycopg.errors.UndefinedTable:
        schema = "incompatible"
    except psycopg.errors.UndefinedFunction:
        postgis = "unavailable"
    except (psycopg.Error, TimeoutError):
        return Readiness(
            status="unavailable", database=database, postgis=postgis, schema_status=schema
        )
    return Readiness(
        status="ok" if database == postgis == schema == "ok" else "unavailable",
        database=database,
        postgis=postgis,
        schema_status=schema,
    )


async def ollama_probe() -> dict[str, str]:
    try:
        llm = get_llm()
        if llm.mode == "stub":
            return {
                "provider": "stub",
                "ollama": "not_checked",
                "model": "not_checked",
                "inference": "not_tested",
            }
        settings = getattr(llm, "settings")
        async with (
            asyncio.timeout(3),
            httpx2.AsyncClient(
                timeout=2,
                trust_env=False,
                follow_redirects=False,
                headers={"Accept-Encoding": "identity"},
            ) as client,
        ):
            async with client.stream(
                "GET", settings.base_url.rstrip("/") + "/api/tags"
            ) as response:
                response.raise_for_status()
                raw = bytearray()
                async for chunk in response.aiter_raw():
                    if len(raw) + len(chunk) > 65536:
                        raise ValueError
                    raw.extend(chunk)
            models = json.loads(raw)["models"]
            present = any(m.get("name") == settings.model for m in models)
        return {
            "provider": "ollama",
            "ollama": "ok",
            "model": "present" if present else "missing",
            "inference": "not_tested",
        }
    except LLMError:
        reason = "configuration_error"
    except (httpx2.HTTPError, TimeoutError, ValueError, KeyError, TypeError, AttributeError):
        reason = "unavailable_or_invalid"
    return {"provider": "ollama", "ollama": reason, "model": "unknown", "inference": "not_tested"}


async def bundle() -> dict[str, object]:
    # CLI or separately authenticated operator route; never public health output.
    from app.db.session import get_engine
    from app.diagnostics import OBSERVATIONS
    from app.limits import inference
    from app.limits.config import policy

    db, model = await asyncio.gather(database_probe(), ollama_probe())
    pool = get_engine().pool
    return {
        "version": 1,
        "status": (
            "unavailable"
            if db.status != "ok"
            else "ready_unverified"
            if model["model"] == "present"
            else "degraded"
        ),
        "database": db.model_dump(),
        "llm": model,
        "queue": {
            "active": inference.QUEUE.active,
            "waiting": len(inference.QUEUE.waiters),
            "active_limit": 1,
            "waiting_limit": policy().inference_queue_size,
        },
        "export": "not_checked",
        "pool_checked_out": getattr(pool, "checkedout", lambda: None)(),
        "counters": OBSERVATIONS.snapshot(),
        "limitations": (
            "Process-local counters; CLI is a new process. "
            "No inference/export quality certification."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(bundle()), ensure_ascii=False, indent=2))
