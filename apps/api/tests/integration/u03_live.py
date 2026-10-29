"""Opt-in real local Qwen / isolated PostGIS probe. No acquisition worker or network fetch.

PG* must identify a disposable QA server with CREATE DATABASE privileges.
python -m tests.integration.u03_live --output docs/qa/u-03/live-qwen.json
"""

import argparse
import asyncio
import ctypes
import json
import os
import secrets
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.llm import LLMSettings, OllamaLLM
from app.data.acquisition.worker import peak_memory
from app.data.registry import load_registry
from app.data.registry_schemas import RegistryConfig
from app.db.models import AcquisitionJobRecord
from app.db.session import get_session, get_session_factory
from app.geo.ingest import import_snapshot
from app.geo.provider import load_snapshot
from app.main import app

from .support import isolated_database, migrate
from .test_conversations import create


def gpu() -> str:
    try:
        return subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=10,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def memory() -> int:
    if sys.platform != "win32":
        return peak_memory()

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    result = Counters()
    result.cb = ctypes.sizeof(result)
    process = ctypes.windll.kernel32.GetCurrentProcess
    process.restype = ctypes.c_void_p
    read = ctypes.windll.psapi.GetProcessMemoryInfo
    read.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    read.restype = ctypes.c_int
    if not read(process(), ctypes.byref(result), result.cb):
        return 0
    return int(result.PeakWorkingSetSize)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unload-first", action="store_true")
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    original_registry = load_registry()
    os.environ["BA_AGENT_ENABLED"] = "1"
    os.environ["LLM_PROVIDER"] = "ollama"
    output: dict[str, Any] = {
        "mode": "real Qwen, artificial geo fixture in disposable PostGIS; no Internet fetch",
        "timestamp": datetime.now(UTC).isoformat(),
        "cases": [],
    }
    if args.unload_first:

        async def unload() -> None:
            await OllamaLLM(LLMSettings()).achat(
                {"model": LLMSettings().model, "messages": [], "stream": False, "keep_alive": 0},
                attempts=1,
            )

        asyncio.run(unload())
        output["model_unloaded_before_first_case"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")

    with isolated_database() as name:
        migrate(name, "upgrade", "head")
        engine = sa.create_engine("postgresql+psycopg://", connect_args={"dbname": name})
        factory = sessionmaker(engine, expire_on_commit=False)

        def session() -> Iterator[Session]:
            with factory.begin() as db:
                yield db

        with factory.begin() as db:
            manifest, document = load_snapshot(Path(__file__).parent / "fixtures/kazan.raw.json")
            import_snapshot(db, manifest, document)
        output["geo_fixture"] = {
            "slug": manifest.slug,
            "data_version": manifest.sha256,
            "synthetic_test_material": True,
        }
        app.dependency_overrides[get_session] = session
        app.dependency_overrides[get_session_factory] = lambda: factory
        try:
            with TestClient(app) as client:
                cases = [
                    (
                        "kazan",
                        "Какие данные есть для кофейни в Казани? "
                        "Проверь POI и административные границы.",
                    ),
                    (
                        "moscow",
                        "Проверь POI и дорожную сеть автосервиса в Москве. Не запускай загрузку.",
                    ),
                    (
                        "unsupported",
                        "Можно загрузить точный автомобильный трафик всей Москвы? "
                        "Сначала проверь возможности системы.",
                    ),
                    (
                        "unknown_industry",
                        "Открываю сервис ремонта музыкальных автоматов в Москве. "
                        "Проверь покрытие POI, без отраслевых расчётов.",
                    ),
                    (
                        "multi_step",
                        "Сначала перечисли возможности получения данных, "
                        "затем проверь дорожную сеть и POI Москвы.",
                    ),
                ]
                for label, content in cases:
                    if args.case and label not in args.case:
                        continue
                    owner, headers, url = create(client)
                    payload = {
                        "request_id": str(uuid4()),
                        "expected_version": 0,
                        "content": content,
                    }
                    start = time.monotonic()
                    response = client.post(
                        "/api/v2/conversations/" + owner["id"] + "/agent",
                        headers=headers,
                        json=payload,
                    )
                    result = response.json()
                    output["cases"].append(
                        {
                            "case": label,
                            "request": payload,
                            "http_status": response.status_code,
                            "response": result,
                            "wall_seconds": time.monotonic() - start,
                            "python_peak_rss_bytes": memory(),
                            "gpu_used_mib_snapshot": gpu(),
                            "profile_unchanged": client.get(url, headers=headers).json()["profile"]
                            == owner["profile"],
                        }
                    )
                    save()
                    print(
                        label,
                        response.status_code,
                        result.get("state"),
                        result.get("code"),
                        flush=True,
                    )
                if "legacy_chat" in args.case:
                    owner, headers, url = create(client)
                    start = time.monotonic()
                    legacy = client.post(
                        url + "/messages",
                        headers=headers,
                        json={
                            "expected_version": 0,
                            "content": "Хочу кофейню в Казани, два миллиона рублей",
                        },
                    )
                    output["cases"].append(
                        {
                            "case": "legacy_chat",
                            "http_status": legacy.status_code,
                            "response": legacy.json(),
                            "wall_seconds": time.monotonic() - start,
                        }
                    )
                    save()
                    print("legacy_chat", legacy.status_code, flush=True)
                # The same real model dispatches a real durable job, but the worker is not run.
                # Source permission is an expiring QA fixture, not production approval.
                source = tuple(
                    s.model_copy(
                        update={
                            "network_permission": "permitted",
                            "availability": "ready",
                            "acquisition_scope": "operator_smoke",
                            "acquisition_approved_until": datetime.now(UTC) + timedelta(minutes=15),
                        }
                    )
                    if s.id == "osm"
                    else s
                    for s in original_registry.sources
                )
                reviewed = original_registry.model_copy(update={"sources": source})
                app.dependency_overrides[load_registry] = lambda: RegistryConfig.model_validate(
                    reviewed.model_dump()
                )
                operator_token = secrets.token_urlsafe(32)
                os.environ["BA_ACQUISITION_ENABLED"] = "1"
                os.environ["BA_ACQUISITION_OPERATOR_TOKEN"] = operator_token
                aoi = {"west": 37.611, "south": 55.760, "east": 37.613, "north": 55.762}
                scope = {"territory": "ru-moscow", "aoi": aoi}
                for label, privileged in (
                    ("guest_acquisition_denied", False),
                    ("operator_dispatch", True),
                ):
                    if args.case and label not in args.case:
                        continue
                    owner, headers, _ = create(client)
                    if privileged:
                        headers["X-Acquisition-Token"] = operator_token
                    payload = {
                        "request_id": str(uuid4()),
                        "expected_version": 0,
                        "content": "Поставь задание request_data_acquisition для OSM POI "
                        "по явно заданному участку Москвы. Не жди завершения загрузки.",
                        "acquisition_scope": scope,
                    }
                    endpoint = "/api/v2/conversations/" + owner["id"] + "/agent"
                    start = time.monotonic()
                    result = client.post(endpoint, headers=headers, json=payload)
                    replay = client.post(endpoint, headers=headers, json=payload)
                    output["cases"].append(
                        {
                            "case": label,
                            "request": payload,
                            "http_status": result.status_code,
                            "response": result.json(),
                            "wall_seconds": time.monotonic() - start,
                            "idempotent_replay_equal": replay.json() == result.json(),
                        }
                    )
                    save()
                    print(label, result.status_code, result.json().get("state"), flush=True)
                    if privileged:
                        jobs = [
                            t["result"].get("job_id")
                            for t in result.json().get("traces", [])
                            if t["status"] == "succeeded"
                            and t["tool"] == "request_data_acquisition"
                        ]
                        if jobs:
                            followup = {
                                "request_id": str(uuid4()),
                                "expected_version": result.json()["profile_version"],
                                "content": "Проверь статус задания "
                                + jobs[0]
                                + ". Не запускай новую загрузку.",
                            }
                            status = client.post(endpoint, headers=headers, json=followup)
                            output["cases"].append(
                                {
                                    "case": "operator_status",
                                    "request": followup,
                                    "http_status": status.status_code,
                                    "response": status.json(),
                                }
                            )
                            save()
                with factory() as db:
                    output["acquisition_jobs"] = [
                        {
                            "state": j.state,
                            "attempt": j.attempt,
                            "id": str(j.id),
                            "network_reservations": j.attempt,
                        }
                        for j in db.scalars(sa.select(AcquisitionJobRecord))
                    ]
                output["status"] = (
                    "recorded; inspect each scenario, do not equate HTTP200 with success"
                )
                save()
        finally:
            app.dependency_overrides.clear()
            engine.dispose()


if __name__ == "__main__":
    main()
