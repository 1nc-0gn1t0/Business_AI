"""Real Qwen assumptions + confirmation + deterministic finance on disposable PostGIS.

Run as python -m tests.integration.u05_live --output <QA.json> from apps/api.
No acquisition, real market data, credentials or report PDF modifications.
"""

import argparse
import json
import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_session, get_session_factory
from app.finance.v2 import llm as assumptions
from app.finance.v2.schemas import AssumptionProposal, FinancialDocument
from app.main import app

from .support import isolated_database, migrate
from .test_conversations import create
from .u03_live import gpu, memory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ.update(BA_INDUSTRY_ENABLED="1", BA_FINANCE_V2_ENABLED="1", LLM_PROVIDER="ollama")
    evidence: dict[str, Any] = dict(
        timestamp=datetime.now(UTC).isoformat(),
        cases=[],
        scope="Real local Qwen; user costs below are explicit testing assumptions, "
        "not market observations. No data import.",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    validated: list[dict[str, Any]] = []
    original = assumptions.validate_proposal

    def capture(proposal: AssumptionProposal, doc: FinancialDocument) -> None:
        item: dict[str, Any] = dict(proposal=proposal.model_dump(mode="json"))
        validated.append(item)
        try:
            original(proposal, doc)
            item["accepted"] = True
        except Exception as error:
            item["accepted"] = False
            item["error"] = getattr(error, "detail", type(error).__name__)
            raise

    assumptions.validate_proposal = capture

    def save() -> None:
        evidence["python_peak_memory"] = memory()
        evidence["gpu_snapshot"] = gpu()
        args.output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    with isolated_database() as name:
        migrate(name, "upgrade", "head")
        engine = sa.create_engine("postgresql+psycopg://", connect_args={"dbname": name})
        factory = sessionmaker(engine, expire_on_commit=False)

        def database() -> Iterator[Session]:
            with factory.begin() as session:
                yield session

        app.dependency_overrides[get_session] = database
        app.dependency_overrides[get_session_factory] = lambda: factory
        try:
            with TestClient(app) as client:
                cases = (
                    (
                        "auto_repair",
                        "Хочу открыть автосервис в Москве, бюджет 8 миллионов рублей, "
                        "четыре поста. "
                        "Предложи предварительные сценарные параметры для финансового анализа.",
                        dict(
                            city="Москва",
                            budget="8000000",
                            specialization="ремонт",
                            service_bays=4,
                            physical_premises=True,
                        ),
                        dict(
                            rent=("100000", "RUB/month"),
                            payroll=("200000", "RUB/month"),
                            utilities=("20000", "RUB/month"),
                            marketing=("30000", "RUB/month"),
                            other_fixed=("50000", "RUB/month"),
                        ),
                    ),
                    (
                        "online_school",
                        "Хочу открыть онлайн-школу программирования. Бюджет 1,5 миллиона рублей. "
                        "Помоги рассчитать экономику.",
                        dict(
                            budget="1500000",
                            audience="взрослые",
                            format="онлайн",
                            payment_model="помесячно",
                            students=20,
                        ),
                        dict(
                            student_capacity=("100", "students"),
                            teachers=("60000", "RUB/month"),
                            platform=("10000", "RUB/month"),
                            marketing=("30000", "RUB/month"),
                            other_fixed=("10000", "RUB/month"),
                        ),
                    ),
                    (
                        "generic",
                        "Хочу открыть сервис по обслуживанию автономных роботизированных теплиц.",
                        dict(
                            budget="2000000",
                            business_model="сервис",
                            physical_premises=False,
                            audience="фермеры",
                            revenue_streams="обслуживание одной теплицы",
                        ),
                        dict(
                            rent=("10000", "RUB/month"),
                            payroll=("100000", "RUB/month"),
                            utilities=("5000", "RUB/month"),
                            marketing=("10000", "RUB/month"),
                            other_fixed=("5000", "RUB/month"),
                        ),
                    ),
                )
                for model, content, values, known in cases:
                    item: dict[str, Any] = dict(
                        model=model, request=content, manual_testing_values=known
                    )
                    evidence["cases"].append(item)
                    created, headers, _ = create(client)
                    url = f"/api/v2/conversations/{created['id']}/industry-profile"
                    started = time.perf_counter()
                    response = client.post(
                        url + "/messages",
                        headers=headers,
                        json=dict(expected_version=0, content=content),
                    )
                    item["classification_seconds"] = time.perf_counter() - started
                    item["classification_status"] = response.status_code
                    current = client.get(url, headers=headers).json()
                    response = client.patch(
                        url,
                        headers=headers,
                        json=dict(
                            expected_version=current["profile"]["revision"],
                            industry=model,
                            updates=[dict(field=k, value=v) for k, v in values.items()],
                        ),
                    )
                    assert response.status_code == 200, response.text
                    response = client.post(
                        url + "/confirm",
                        headers=headers,
                        json=dict(expected_version=response.json()["profile"]["revision"]),
                    )
                    assert response.status_code == 200, response.text
                    item["profile"] = response.json()["profile"]
                    url = url.replace("industry-profile", "financial-scenarios")
                    view = client.get(url, headers=headers).json()

                    def command(**extra: object) -> dict[str, Any]:
                        return dict(
                            request_id=str(uuid4()),
                            expected_profile_revision=view["document"]["profile_revision"],
                            expected_input_revision=view["document"]["revision"],
                            **extra,
                        )

                    response = client.patch(
                        url,
                        headers=headers,
                        json=command(
                            updates=[
                                dict(
                                    parameter=k,
                                    base=v,
                                    low=v,
                                    high=v,
                                    unit=u,
                                    kind="user_assumption",
                                    basis="Явно заданное тестовое сценарное значение",
                                )
                                for k, (v, u) in known.items()
                            ],
                            **({"billing_model": "monthly"} if model == "online_school" else {}),
                        ),
                    )
                    assert response.status_code == 200, response.text
                    view = response.json()
                    response = client.post(
                        url + "/review",
                        headers=headers,
                        json=command(confirm=list(view["document"]["entries"])),
                    )
                    assert response.status_code == 200, response.text
                    view = response.json()
                    item["before_proposal"] = view
                    validated.clear()
                    started = time.perf_counter()
                    payload = command()
                    response = client.post(url + "/propose", headers=headers, json=payload)
                    item["proposal_seconds"] = time.perf_counter() - started
                    item["proposal_status"] = response.status_code
                    item["proposal_checks"] = list(validated)
                    item["proposal_response"] = response.json()
                    if response.status_code != 200:
                        save()
                        continue
                    view = response.json()
                    hypotheses = [
                        k
                        for k, e in view["document"]["entries"].items()
                        if e["review"] == "proposed"
                    ]
                    item["hypotheses"] = hypotheses
                    repeat = client.post(url + "/propose", headers=headers, json=payload)
                    item["replay_status"] = repeat.status_code
                    item["replay_added_model_calls"] = len(validated) - len(item["proposal_checks"])
                    response = client.post(
                        url + "/review", headers=headers, json=command(confirm=hypotheses)
                    )
                    if response.status_code != 200:
                        item["review_error"] = response.json()
                        save()
                        continue
                    view = response.json()
                    started = time.perf_counter()
                    response = client.post(url + "/calculate", headers=headers, json=command())
                    item["calculation_http_seconds"] = time.perf_counter() - started
                    item["calculation_status"] = response.status_code
                    item["result"] = response.json()
                    if response.status_code == 200 and response.json()["result"]:
                        from app.finance.v2.engine import calculate

                        doc = FinancialDocument.model_validate(response.json()["document"])
                        times = []
                        for _ in range(20):
                            started = time.perf_counter()
                            calculate(doc)
                            times.append((time.perf_counter() - started) * 1000)
                        item["python_calculation_ms"] = dict(
                            min=min(times), max=max(times), mean=sum(times) / len(times)
                        )
                    save()
        finally:
            assumptions.validate_proposal = original
            app.dependency_overrides.clear()
            engine.dispose()
    save()


if __name__ == "__main__":
    main()
