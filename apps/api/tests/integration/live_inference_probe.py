"""Manual H-03 real Ollama + HTTP handler + PostgreSQL pool probe, never regular CI.

Run in db-tests with PGDATABASE=f00_restore_h03_<uuid>, LLM_PROVIDER=ollama.
Prints only aggregate metrics and expected synthetic scenario values, never credentials.
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from time import perf_counter, sleep
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from sqlalchemy.pool import QueuePool

from app.adapters.llm import OllamaLLM, ProfileToolCall, Turn
from app.api.schemas import BusinessProfile
from app.db.session import get_engine
from app.main import app


def main() -> None:
    name = os.environ.get("PGDATABASE", "")
    if (
        not re.fullmatch(r"f00_restore_h03_[a-f0-9]{32}", name)
        or os.getenv("LLM_PROVIDER") != "ollama"
    ):
        raise RuntimeError("Requires isolated H-03 restored DB and explicit real Ollama")
    active = Event()
    original = OllamaLLM.aextract

    async def observed(
        self: OllamaLLM, content: str, profile: BusinessProfile, history: tuple[Turn, ...]
    ) -> ProfileToolCall:
        active.set()
        try:
            return await original(self, content, profile, history)
        finally:
            active.clear()

    pool = get_engine().pool
    assert isinstance(pool, QueuePool)
    samples: list[tuple[int, int]] = []
    with patch.object(OllamaLLM, "aextract", observed), TestClient(app) as client:
        created = client.post("/api/v1/conversations")
        assert created.status_code == 201
        view = created.json()
        path = "/api/v1/conversations/" + view["id"]
        headers = {"X-Conversation-Token": view["access_token"]}
        assert (
            client.put(
                path + "/consents/assistant",
                headers=headers,
                json={
                    "expected_revision": 0,
                    "text_version": "assistant-demo-v1",
                    "decision": "grant",
                },
            ).status_code
            == 200
        )
        started = perf_counter()
        with (
            psycopg.connect(dbname="postgres", autocommit=True) as inspector,
            ThreadPoolExecutor(1) as workers,
        ):
            pending = workers.submit(
                client.post,
                path + "/messages",
                headers=headers,
                json={
                    "expected_version": 0,
                    "content": "Хочу открыть кофейню в Казани. Бюджет — 2 миллиона рублей.",
                },
            )
            while not pending.done():
                if active.is_set():
                    held = pool.checkedout()
                    row = inspector.execute(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=%s "
                        "AND state='idle in transaction'",
                        (name,),
                    ).fetchone()
                    if active.is_set():
                        assert row is not None
                        samples.append((held, row[0]))
                sleep(0.05)
            response = pending.result()
        assert response.status_code == 200, response.status_code
        result = response.json()
        assert result["extraction_mode"] == "ollama" and result["profile"]["city"] == "Казань"
        assert result["profile"]["category"] == "кофейня"
        assert Decimal(result["profile"]["budget"]) == 2000000
        assert samples and max(held for held, _ in samples) == max(idle for _, idle in samples) == 0
        assert pool.checkedout() == 0
        print(
            json.dumps(
                {
                    "h03": "live-qwen-pool",
                    "mode": "ollama",
                    "samples": len(samples),
                    "pool_checked_out_peak_during_inference": 0,
                    "idle_in_transaction_peak": 0,
                    "request_seconds": round(perf_counter() - started, 3),
                    "city": "Казань",
                    "category": "кофейня",
                    "budget": "2000000.00",
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
