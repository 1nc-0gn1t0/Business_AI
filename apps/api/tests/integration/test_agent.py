"""Artificial PostGIS fixtures + scripted model; live Qwen is recorded separately."""

import asyncio
import os
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.agent.llm import AgentLLM, get_agent_llm
from app.agent.schemas import AgentLimits, AgentRequest, ModelTiming, PlanProposal
from app.agent.store import RunStore
from app.agent.tools import TOOLS
from app.api.conversation_schemas import ProfilePatch
from app.api.schemas import Contract
from app.data.registry import load_registry
from app.db.models import AcquisitionJobRecord, AgentRunRecord
from app.geo.ingest import import_snapshot
from app.geo.provider import load_snapshot
from app.main import app
from app.services.conversations import Conversations, VersionConflict

from .test_acquisition import approved
from .test_conversations import create

pytestmark = pytest.mark.skipif(
    os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires isolated PostGIS"
)


@pytest.fixture
def agent_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("BA_AGENT_ENABLED", "1")
    # An explicit test-only scripted dependency, not a hidden stub-mode agent.
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_agent_llm, None)
        app.dependency_overrides.pop(load_registry, None)


def proposal(tool: str = "check_data_coverage", **arguments: Any) -> PlanProposal:
    definition = TOOLS[tool]
    return PlanProposal.model_validate(
        {
            "goal": "fixture",
            "tool": tool,
            "capability": definition.capability,
            "expected_result": definition.result_type,
            "arguments": arguments,
            "reason": "explicit synthetic model fixture",
        }
    )


def finish() -> PlanProposal:
    return PlanProposal(
        goal="done",
        tool="finish",
        capability="conversation.respond",
        arguments={},
        reason="done",
        expected_result="response",
    )


class AutoSynthesis(AgentLLM):
    def __init__(self, values: list[Contract]):
        self.model = "explicit-synthetic-model"
        self.values = iter(values)

    async def call(
        self, document: dict[str, Any], kind: Literal["proposal", "synthesis"]
    ) -> tuple[Contract, ModelTiming]:
        if kind == "synthesis":
            from app.agent.orchestrator import grounded_answer
            from app.agent.schemas import Synthesis, ToolTrace

            # Model context intentionally excludes private diagnostic trace fields.
            traces = tuple(
                ToolTrace.model_validate(
                    t
                    | {
                        "capability": TOOLS[t["tool"]].capability,
                        "mutating": TOOLS[t["tool"]].mutating,
                        "timestamp": datetime.now(UTC),
                        "argument_sha256": "a" * 64,
                    }
                )
                for t in document["results"]
            )
            return Synthesis(
                evidence_ids=tuple(t.sequence for t in traces if t.status == "succeeded"),
                next_step=grounded_answer(traces)[1],
            ), ModelTiming(purpose=kind, queue_ms=0, inference_ms=0)
        return next(self.values), ModelTiming(purpose=kind, queue_ms=0, inference_ms=0)


def script(*values: Contract) -> None:
    app.dependency_overrides[get_agent_llm] = lambda: AutoSynthesis(list(values))


def endpoint(body: dict[str, Any]) -> str:
    return "/api/v2/conversations/" + str(body["id"]) + "/agent"


def request(version: int = 0, **extra: Any) -> dict[str, Any]:
    return {
        "request_id": str(uuid4()),
        "expected_version": version,
        "content": "Artificial fixture question",
        **extra,
    }


def test_coverage_history_profile_and_idempotent_owner_isolation(
    agent_client: TestClient, migrated_database: tuple[Engine, UUID]
) -> None:
    c = agent_client
    engine, _ = migrated_database
    with Session(engine) as db, db.begin():
        m, doc = load_snapshot(Path(__file__).parent / "fixtures/kazan.raw.json")
        import_snapshot(db, m, doc)
    owner, headers, url = create(c)
    _, other, _ = create(c)
    before = c.get(url, headers=headers).json()["profile"]
    script(proposal(territory="ru-kazan", categories=["geo.mapped_poi"]), finish())
    body = request()
    result = c.post(endpoint(owner), headers=headers, json=body)
    assert result.status_code == 200, result.text
    data = result.json()
    assert (
        data["state"] == "succeeded"
        and data["traces"][0]["result"]["assessments"][0]["local_status"] == "partial"
    )
    assert data["profile_version"] == 1
    assert c.get(url, headers=headers).json()["profile"] == before
    assert len(c.get(url + "/messages", headers=headers).json()) == 3
    assert c.post(endpoint(owner), headers=headers, json=body).json() == data
    assert c.get(endpoint(owner) + "/" + body["request_id"], headers=other).status_code == 404
    assert c.post(endpoint(owner), headers=other, json=request()).status_code == 404
    assert (
        c.post(endpoint(owner), headers=headers, json=body | {"content": "changed"}).status_code
        == 409
    )


def test_moscow_missing_online_and_unknown_category(agent_client: TestClient) -> None:
    c = agent_client
    for tool in (
        proposal(territory="ru-moscow", categories=["geo.vehicle_network"]),
        proposal(
            "check_data_sufficiency", territory="ru-novosibirsk", template="nonspatial_inputs_v1"
        ),
        proposal(territory="ru-moscow", categories=["unknown.traffic"]),
    ):
        owner, h, _ = create(c)
        script(tool, finish())
        result = c.post(endpoint(owner), headers=h, json=request())
        assert result.status_code == 200, result.text
        trace = result.json()["traces"][0]
        if tool.arguments.get("categories") == ["unknown.traffic"]:
            assert trace["status"] == "rejected" and trace["code"] == "unknown_data_category"
        elif tool.tool == "check_data_sufficiency":
            assert all(
                not a["category"].startswith("geo.")
                for a in trace["result"]["coverage"]["assessments"]
            )
        else:
            assert trace["result"]["assessments"][0]["local_status"] == "missing"


AOI = {"west": 37.61, "south": 55.75, "east": 37.612, "north": 55.752}


def test_operator_create_cache_scope_grant_and_guest_denial(
    agent_client: TestClient,
    migrated_database: tuple[Engine, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = agent_client
    engine, _ = migrated_database
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("BA_ACQUISITION_ENABLED", "1")
    monkeypatch.setenv("BA_ACQUISITION_OPERATOR_TOKEN", token)
    app.dependency_overrides[load_registry] = approved
    p = proposal(
        "request_data_acquisition",
        source_id="osm",
        category="geo.mapped_poi",
        territory="ru-moscow",
        aoi=AOI,
    )
    owner, h, _ = create(c)
    scope = {"territory": "ru-moscow", "aoi": AOI}
    script(p)
    denied = c.post(endpoint(owner), headers=h, json=request(acquisition_scope=scope))
    assert (
        denied.status_code == 200
        and denied.json()["traces"][0]["code"] == "operator_permission_required"
    )
    with Session(engine) as db:
        before = db.scalar(sa.select(sa.func.count()).select_from(AcquisitionJobRecord)) or 0
    operator = h | {"X-Acquisition-Token": token}
    script(p)
    body = request(version=1, acquisition_scope=scope)
    result = c.post(endpoint(owner), headers=operator, json=body)
    assert result.status_code == 200, result.text
    job = result.json()["traces"][0]["result"]["job_id"]
    assert result.json()["next_step"] == "wait_for_job"
    assert c.post(endpoint(owner), headers=operator, json=body).json() == result.json()
    assert c.get(endpoint(owner) + "/" + body["request_id"], headers=h).status_code == 404
    assert (
        c.post(
            endpoint(owner),
            headers=operator | {"X-Acquisition-Token": "forged"},
            json=request(version=2),
        ).status_code
        == 401
    )
    with Session(engine) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(AcquisitionJobRecord)) == before + 1
    script(proposal("get_acquisition_status", job_id=job), finish())
    status = c.post(endpoint(owner), headers=operator, json=request(version=2))
    assert (
        status.status_code == 200
        and status.json()["traces"][0]["result"]["latest_event"]["sequence"] == 1
    )
    other, other_h, _ = create(c)
    script(proposal("get_acquisition_status", job_id=job))
    denied_job = c.post(
        endpoint(other), headers=other_h | {"X-Acquisition-Token": token}, json=request()
    )
    assert (
        denied_job.status_code == 200
        and denied_job.json()["traces"][0]["code"] == "acquisition_job_not_found"
    )


@pytest.mark.parametrize("change", ["version", "consent", "operator", "deadline", "cancel"])
def test_guard_revalidates_before_effects(
    agent_client: TestClient,
    migrated_database: tuple[Engine, UUID],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    c = agent_client
    engine, _ = migrated_database
    owner, h, _ = create(c)
    factory = sessionmaker(engine, expire_on_commit=False)
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("BA_ACQUISITION_ENABLED", "1")
    monkeypatch.setenv("BA_ACQUISITION_OPERATOR_TOKEN", token)
    req = AgentRequest.model_validate(
        request(acquisition_scope={"territory": "ru-moscow", "aoi": AOI})
    )
    store = RunStore(
        factory, UUID(owner["id"]), h["X-Conversation-Token"], token, req, AgentLimits(), Event()
    )
    store.start("fixture")
    with factory.begin() as db:
        if change == "version":
            Conversations(db).update(
                UUID(owner["id"]), h["X-Conversation-Token"], 0, patch=ProfilePatch(city="Омск")
            )
        elif change == "consent":
            from app.db.models import ConsentRecord

            row = db.scalar(
                sa.select(ConsentRecord).where(ConsentRecord.conversation_id == UUID(owner["id"]))
            )
            assert row
            row.document = row.document | {"status": "withdrawn"}
        elif change == "deadline":
            run = db.get(AgentRunRecord, req.request_id)
            assert run
            run.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    if change == "operator":
        monkeypatch.setenv("BA_ACQUISITION_OPERATOR_TOKEN", secrets.token_urlsafe(32))
    if change == "cancel":
        store.cancelled.set()
    from fastapi import HTTPException

    from app.agent.tools import AgentError
    from app.leads.policy import LeadError

    with pytest.raises(
        (VersionConflict, AgentError, LeadError, HTTPException, asyncio.CancelledError)
    ):
        store.tool(
            proposal(
                "request_data_acquisition",
                source_id="osm",
                category="geo.mapped_poi",
                territory="ru-moscow",
                aoi=AOI,
            ),
            approved(),
            1,
        )
    with factory() as db:
        run = db.get(AgentRunRecord, req.request_id)
        assert run and not run.job_ids


def test_limits_retention_running_and_body_boundary(
    agent_client: TestClient,
    migrated_database: tuple[Engine, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = agent_client
    engine, _ = migrated_database
    owner, h, _ = create(c)
    req = AgentRequest.model_validate(request())
    store = RunStore(
        sessionmaker(engine, expire_on_commit=False),
        UUID(owner["id"]),
        h["X-Conversation-Token"],
        None,
        req,
        AgentLimits(),
        Event(),
    )
    store.start("fixture")
    script(finish())
    assert c.post(endpoint(owner), headers=h, json=req.model_dump(mode="json")).status_code == 409
    assert c.post(endpoint(owner), headers=h, json=request()).status_code == 409
    assert c.post(endpoint(owner), headers=h, json=request(content="x" * 70000)).status_code == 413
    with Session(engine) as db, db.begin():
        run = db.get(AgentRunRecord, req.request_id)
        assert run
        run.state = "failed"
    monkeypatch.setenv("BA_AGENT_LIMITS_JSON", '{"owner_runs":1}')
    assert c.post(endpoint(owner), headers=h, json=request()).status_code == 429


def test_concurrent_admission_and_no_connection_held_after_start(
    agent_client: TestClient, migrated_database: tuple[Engine, UUID]
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from fastapi import HTTPException

    engine, _ = migrated_database
    owner, h, _ = create(agent_client)
    factory = sessionmaker(engine, expire_on_commit=False)

    def start() -> str:
        store = RunStore(
            factory,
            UUID(owner["id"]),
            h["X-Conversation-Token"],
            None,
            AgentRequest.model_validate(request()),
            AgentLimits(),
            Event(),
        )
        try:
            return store.start("fixture").state
        except HTTPException as error:
            assert error.status_code == 409
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(), range(2)))
    assert sorted(results) == ["conflict", "running"]
    assert isinstance(engine.pool, sa.pool.QueuePool) and engine.pool.checkedout() == 0


@pytest.mark.parametrize("cancel", [False, True])
def test_oversized_result_rolls_back_new_job_and_grant(
    agent_client: TestClient,
    migrated_database: tuple[Engine, UUID],
    monkeypatch: pytest.MonkeyPatch,
    cancel: bool,
) -> None:
    from app.agent import tools

    engine, _ = migrated_database
    owner, h, _ = create(agent_client)
    operator_token = secrets.token_urlsafe(32)
    monkeypatch.setenv("BA_ACQUISITION_ENABLED", "1")
    monkeypatch.setenv("BA_ACQUISITION_OPERATOR_TOKEN", operator_token)
    req = AgentRequest.model_validate(
        request(acquisition_scope={"territory": "ru-moscow", "aoi": AOI})
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    store = RunStore(
        factory,
        UUID(owner["id"]),
        h["X-Conversation-Token"],
        operator_token,
        req,
        AgentLimits(result_bytes=1024),
        Event(),
    )
    store.start("fixture")
    original = tools.execute

    def oversize(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original(*args, **kwargs)
        if cancel:
            store.cancelled.set()
            return result
        return result | {"pad": "x" * 2048}

    monkeypatch.setattr(tools, "execute", oversize)
    with factory() as db:
        before = db.scalar(sa.select(sa.func.count()).select_from(AcquisitionJobRecord))
    p = proposal(
        "request_data_acquisition",
        source_id="osm",
        category="geo.mapped_poi",
        territory="ru-moscow",
        aoi=AOI,
    )
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            store.tool(p, approved(), 1)
    else:
        trace_ = store.tool(p, approved(), 1)
        assert trace_.code == "tool_result_too_large"
    with factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(AcquisitionJobRecord)) == before
        run = db.get(AgentRunRecord, req.request_id)
        assert run and not run.job_ids


def test_interrupted_run_expiry_and_lazy_retention(
    agent_client: TestClient, migrated_database: tuple[Engine, UUID]
) -> None:
    engine, _ = migrated_database
    owner, h, _ = create(agent_client)
    req = AgentRequest.model_validate(request())
    factory = sessionmaker(engine, expire_on_commit=False)
    store = RunStore(
        factory, UUID(owner["id"]), h["X-Conversation-Token"], None, req, AgentLimits(), Event()
    )
    store.start("fixture")
    with factory.begin() as db:
        run = db.get(AgentRunRecord, req.request_id)
        assert run
        run.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    result = agent_client.get(endpoint(owner) + "/" + str(req.request_id), headers=h)
    assert result.json()["state"] == "interrupted"
    with factory.begin() as db:
        run = db.get(AgentRunRecord, req.request_id)
        assert run
        run.created_at = datetime.now(UTC) - timedelta(days=8)
    assert (
        agent_client.get(endpoint(owner) + "/" + str(req.request_id), headers=h).status_code == 410
    )
    script(finish())
    assert agent_client.post(endpoint(owner), headers=h, json=request()).status_code == 200
    with factory() as db:
        assert db.get(AgentRunRecord, req.request_id) is None


def test_bulk_interruption_replay_never_reenters_model(
    agent_client: TestClient, migrated_database: tuple[Engine, UUID]
) -> None:
    engine, _ = migrated_database
    owner, h, _ = create(agent_client)
    factory = sessionmaker(engine, expire_on_commit=False)
    req = AgentRequest.model_validate(request())
    store = RunStore(
        factory, UUID(owner["id"]), h["X-Conversation-Token"], None, req, AgentLimits(), Event()
    )
    store.start("fixture")
    with factory.begin() as db:
        old = db.get(AgentRunRecord, req.request_id)
        assert old
        old.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    other = RunStore(
        factory,
        UUID(owner["id"]),
        h["X-Conversation-Token"],
        None,
        AgentRequest.model_validate(request()),
        AgentLimits(),
        Event(),
    )
    other.start("fixture")
    replay = store.start("fixture")
    assert replay.state == "interrupted" and replay.code == "agent_interrupted"


def test_clarification_without_tools_is_saved_as_dialogue(agent_client: TestClient) -> None:
    owner, h, url = create(agent_client)
    script(finish())
    response = agent_client.post(endpoint(owner), headers=h, json=request())
    assert response.status_code == 200 and response.json()["next_step"] == "clarify"
    assert response.json()["profile_version"] == 1
    messages = agent_client.get(url + "/messages", headers=h).json()
    assert len(messages) == 3
