import asyncio
import json
import time
from collections import Counter
from threading import Event
from typing import Any, Literal

from app.adapters.llm import LLMError
from app.agent.llm import AgentLLM
from app.agent.schemas import (
    AgentResponse,
    ModelTiming,
    NextStep,
    PlanProposal,
    Synthesis,
    ToolTrace,
)
from app.agent.store import RunStore
from app.agent.tools import AgentError
from app.data.acquisition.service import digest
from app.data.registry_schemas import RegistryConfig
from app.services.dialogue import blocking

ERRORS = {
    "operator_permission_required": "Для загрузки и чтения задания нужно разрешение оператора.",
    "source_not_permitted": "Загрузка из источника не разрешена. Локальные данные сохраняются.",
    "explicit_acquisition_scope_required": "Для загрузки укажите небольшой участок на карте.",
    "acquisition_scope_mismatch": "Участок не совпадает с явно разрешённой территорией.",
    "acquisition_category_unsupported": "Загружаются только OSM POI. Этот слой не поддерживается.",
    "unknown_data_category": "Запрошенная категория данных не поддерживается.",
    "unsupported_tool": "Запрошенный инструмент не поддерживается.",
    "acquisition_job_not_found": "Задание не найдено в разрешённом контексте проекта.",
}
LABELS = {
    "geo.mapped_poi": "Объекты OSM",
    "geo.vehicle_network": "Дорожная сеть",
    "geo.admin_polygons": "Административные границы",
    "geo.pedestrian_network": "Пешеходная сеть",
}
STATES = {
    "available": "доступны в заявленном охвате",
    "partial": "частичное покрытие",
    "stale": "требуют обновления",
    "missing": "нет подтверждённого локального набора",
    "unknown": "наличие не установлено",
}


def grounded_answer(traces: tuple[ToolTrace, ...]) -> tuple[str, NextStep]:
    lines: list[str] = []
    next_step: NextStep = "done"
    for trace in traces:
        result = trace.result
        if trace.status != "succeeded":
            lines.append(
                ERRORS.get(trace.code, "Не удалось выполнить действие: " + trace.code + ".")
            )
            next_step = (
                "operator_permission_required"
                if trace.code == "operator_permission_required"
                else "provide_aoi"
                if trace.code == "explicit_acquisition_scope_required"
                else "data_unavailable"
            )
            continue
        if trace.tool == "list_data_capabilities":
            lines.append(
                "В реестре "
                + str(len(result["categories"]))
                + " категорий. Загрузка реализована только для OSM POI; "
                "нужны разрешения оператора и источника."
            )
        evidence = result.get("coverage", result)
        if "assessments" in evidence:
            query = evidence["query"]
            lines.append(
                "Проверена территория: " + str(query.get("territory") or "заданный участок") + "."
            )
            for item in evidence["assessments"]:
                lines.append(
                    LABELS.get(item["category"], item["category"])
                    + ": "
                    + STATES[item["local_status"]]
                    + "."
                )
                if item["local_status"] != "available":
                    next_step = "data_unavailable"
            lines.append(
                "Покрытие относится к импортированным данным; "
                "полнота сведений о реальном рынке не подтверждена."
            )
            if "sufficiency" in result:
                lines.append(
                    "Проверена только достаточность данных; отраслевой расчёт не выполнялся."
                )
        if "job_id" in result:
            lines.append(
                "Задание "
                + result["job_id"]
                + ": "
                + result["state"]
                + ", этап "
                + result["stage"]
                + "."
            )
            if result["state"] not in {"succeeded", "failed", "cancelled"}:
                next_step = "wait_for_job"
                lines.append(
                    "Подготовка продолжается отдельно. Доступность worker пока не подтверждена."
                )
            elif result["state"] != "succeeded":
                next_step = "data_unavailable"
            else:
                lines.append(
                    "Подготовка завершена; доступность категорий проверьте через Coverage."
                )
    return (
        "\n".join(lines) if lines else "Уточните территорию и данные, которые нужно проверить.",
        next_step if lines else "clarify",
    )


async def run_agent(store: RunStore, llm: AgentLLM, registry: RegistryConfig) -> AgentResponse:
    cancelled: Event = store.cancelled
    response = await blocking(lambda: store.start(llm.model), cancelled)
    if response.state != "running":
        return response
    started = time.monotonic()
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    code = "ok"

    async def model(kind: Literal["proposal", "synthesis"]) -> Any:
        nonlocal response
        if len(response.model_timings) >= store.cfg.llm_calls:
            raise AgentError("agent_budget_exceeded")
        document: dict[str, Any] = {
            "message": store.request.content,
            "explicit_acquisition_scope": store.request.acquisition_scope.model_dump(mode="json")
            if store.request.acquisition_scope
            else None,
            "results": [
                {
                    "sequence": t.sequence,
                    "tool": t.tool,
                    "status": t.status,
                    "code": t.code,
                    "result": t.result,
                }
                for t in response.traces
            ],
        }
        if kind == "synthesis":
            _, safe_next = grounded_answer(response.traces)
            allowed: list[str] = [safe_next]
            if safe_next == "done":
                allowed += ["clarify", "data_unavailable"]
            if (
                len(response.model_timings) + 2 < store.cfg.llm_calls
                and len(response.traces) < store.cfg.tool_calls
                and response.traces
                and response.traces[-1].status == "succeeded"
                and response.traces[-1].tool
                not in {"request_data_acquisition", "get_acquisition_status"}
            ):
                allowed.append("continue")
            document["allowed_next_steps"] = allowed
        if len(json.dumps(document, ensure_ascii=False).encode()) > store.cfg.context_bytes:
            raise AgentError("agent_context_limit")
        # Persist the budget charge before inference, including interrupted/failed attempts.
        pending = ModelTiming(purpose=kind, code="started", queue_ms=None, inference_ms=None)
        response = response.model_copy(
            update={"model_timings": response.model_timings + (pending,)}
        )
        await blocking(lambda: store.checkpoint(response), cancelled)
        calling = time.monotonic()
        try:
            value, timing = await llm.call(document, kind)
        except LLMError as error:
            timing = pending.model_copy(
                update={"code": error.code, "elapsed_ms": (time.monotonic() - calling) * 1000}
            )
            response = response.model_copy(
                update={"model_timings": response.model_timings[:-1] + (timing,)}
            )
            raise
        response = response.model_copy(
            update={"model_timings": response.model_timings[:-1] + (timing,)}
        )
        await blocking(lambda: store.checkpoint(response), cancelled)
        return value

    try:
        async with asyncio.timeout(store.cfg.deadline_seconds):
            while (
                len(response.traces) < store.cfg.tool_calls
                and len(response.model_timings) < store.cfg.llm_calls - 1
            ):
                proposal: PlanProposal = await model("proposal")
                finished = proposal.tool == "finish"
                if finished:
                    if (
                        proposal.capability != "conversation.respond"
                        or proposal.arguments
                        or proposal.expected_result != "response"
                    ):
                        raise AgentError("invalid_finish_proposal")
                else:
                    key = digest({"tool": proposal.tool, "arguments": proposal.arguments})
                    if key in seen:
                        raise AgentError("repeated_tool_call")
                    if (
                        counts[proposal.tool] >= store.cfg.per_tool_calls
                        or proposal.tool == "request_data_acquisition"
                        and counts[proposal.tool]
                    ):
                        raise AgentError("agent_tool_limit")
                    seen.add(key)
                    counts[proposal.tool] += 1
                    trace = await blocking(
                        lambda: store.tool(proposal, registry, len(response.traces) + 1), cancelled
                    )
                    response = response.model_copy(update={"traces": response.traces + (trace,)})
                synthesis: Synthesis = await model("synthesis")
                _, expected_next = grounded_answer(response.traces)
                if set(synthesis.evidence_ids) != {
                    t.sequence for t in response.traces if t.status == "succeeded"
                }:
                    raise AgentError("invalid_synthesis")
                if synthesis.next_step != "continue":
                    if synthesis.next_step != expected_next and not (
                        expected_next == "done"
                        and synthesis.next_step in {"clarify", "data_unavailable"}
                    ):
                        raise AgentError("invalid_synthesis")
                    break
                if (
                    finished
                    or len(response.traces) >= store.cfg.tool_calls
                    or len(response.model_timings) + 1 >= store.cfg.llm_calls
                    or response.traces[-1].status != "succeeded"
                    or response.traces[-1].tool
                    in {"request_data_acquisition", "get_acquisition_status"}
                ):
                    raise AgentError("agent_budget_exceeded")
    except (AgentError, LLMError) as error:
        code = error.code
    except TimeoutError:
        code = "agent_deadline_exceeded"
    except BaseException:
        # Clean up even when a caller disconnects; never abandon an active DB mutation.
        await blocking(
            lambda: store.abandon("agent_cancelled" if cancelled.is_set() else "agent_failed"),
            Event(),
        )
        raise
    message, next_step = grounded_answer(response.traces)
    if code != "ok":
        message += "\nОтвет ограничен проверенными действиями (" + code + ")."
    response = response.model_copy(
        update={
            "state": "succeeded"
            if code == "ok" and all(t.status == "succeeded" for t in response.traces)
            else "partial"
            if response.traces
            else "failed",
            "code": code,
            "message": message,
            "next_step": next_step,
            "total_ms": (time.monotonic() - started) * 1000,
        }
    )
    try:
        return await blocking(lambda: store.finish(response), cancelled)
    except BaseException:
        await blocking(
            lambda: store.abandon(code if code != "ok" else "agent_publication_conflict"), Event()
        )
        raise
