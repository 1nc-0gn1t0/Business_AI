"""Isolated PostgreSQL/PostGIS. Financial values are explicit test scenarios."""

import os
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.llm import LLMError
from app.db.models import FinancialActionRecord
from app.finance.v2.llm import get_assumption_llm
from app.finance.v2.registry import configuration
from app.finance.v2.schemas import AssumptionProposal
from app.main import app

from .test_industry import edit, setup

pytestmark = pytest.mark.skipif(
    os.getenv("BA_RUN_DB_TESTS") != "1", reason="Isolated PostGIS required"
)


@pytest.fixture
def financial(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("BA_INDUSTRY_ENABLED", "1")
    monkeypatch.setenv("BA_FINANCE_V2_ENABLED", "1")
    yield client
    app.dependency_overrides.pop(get_assumption_llm, None)


def project(client: TestClient, model: str = "auto_repair") -> tuple[dict[str, str], str, str]:
    _, headers, url = setup(client)
    values = (
        dict(
            city="Москва",
            budget="8000000",
            specialization="ремонт",
            service_bays=4,
            physical_premises=True,
        )
        if model == "auto_repair"
        else dict(
            budget="1500000",
            audience="взрослые",
            format="онлайн",
            payment_model="за курс",
            students=20,
        )
    )
    patched = client.patch(
        url,
        headers=headers,
        json=dict(
            expected_version=0,
            industry=model,
            updates=[dict(field=k, value=v) for k, v in values.items()],
        ),
    )
    assert patched.status_code == 200, patched.text
    confirmed = client.post(url + "/confirm", headers=headers, json={"expected_version": 1})
    assert confirmed.status_code == 200, confirmed.text
    assert "finance" in confirmed.json()["plan"]["stages"]
    return headers, url.replace("industry-profile", "financial-scenarios"), url


def command(view: dict[str, Any], **extra: object) -> dict[str, Any]:
    return dict(
        request_id=str(uuid4()),
        expected_profile_revision=view["document"]["profile_revision"],
        expected_input_revision=view["document"]["revision"],
        **extra,
    )


def inputs(
    client: TestClient, headers: dict[str, str], url: str, model: str = "auto_repair"
) -> dict[str, Any]:
    view = client.get(url, headers=headers).json()
    values: dict[str, str | int] = dict(
        service_bays=4,
        working_days=25,
        orders_per_bay=2,
        utilization="0.75",
        average_order=10000,
        materials_per_order=3000,
        labor_per_order=1000,
        rent=100000,
        payroll=200000,
        utilities=20000,
        marketing=30000,
        other_fixed=50000,
        students=20,
        student_capacity=30,
        tuition=10000,
        course_months=3,
        variable_per_student=1000,
        fee_ratio="0.05",
        teachers=60000,
        platform=10000,
    )
    updates = [
        dict(
            parameter=p.id,
            unit=p.unit,
            base=str(values[p.id]),
            low=str(values[p.id]),
            high=str(values[p.id]),
        )
        for p in configuration(model).parameters
    ]
    result = client.patch(
        url,
        headers=headers,
        json=command(
            view,
            updates=updates,
            **({"billing_model": "monthly"} if model == "online_school" else {}),
        ),
    )
    assert result.status_code == 200, result.text
    return result.json()  # type: ignore[no-any-return]


def reviewed(
    client: TestClient, headers: dict[str, str], url: str, view: dict[str, Any]
) -> dict[str, Any]:
    result = client.post(
        url + "/review",
        headers=headers,
        json=command(view, confirm=list(view["document"]["entries"])),
    )
    assert result.status_code == 200, result.text
    return result.json()  # type: ignore[no-any-return]


def test_full_lifecycle_replay_snapshot_whatif_and_stale(financial: TestClient) -> None:
    headers, url, profile = project(financial)
    view = inputs(financial, headers, url)
    assert view["needs_review"] and view["result"] is None
    partial = financial.post(url + "/calculate", headers=headers, json=command(view))
    assert partial.json()["result"]["result"]["status"] == "partial"
    view = reviewed(financial, headers, url, partial.json())
    payload = command(view)
    response = financial.post(url + "/calculate", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["result"]["result"]["scenarios"][1]["operating_result"] == "500000.00"
    original = view["result"]
    # A new command ID with identical pinned inputs reuses the same saved result.
    assert (
        financial.post(url + "/calculate", headers=headers, json=command(view)).json()["result"]
        == original
    )
    assert (
        financial.post(url + "/calculate", headers=headers, json=payload).json()["result"]
        == original
    )
    assert financial.get(url, headers=headers).json()["result"] == original
    changed = dict(parameter="rent", unit="RUB/month", base="110000", low="110000", high="110000")
    preview = financial.post(
        url + "/what-if", headers=headers, json=command(view, updates=[changed])
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["persisted"] is False
    assert preview.json()["result"]["scenarios"][1]["operating_result"] == "490000.00"
    assert financial.get(url, headers=headers).json()["document"] == view["document"]
    patched = financial.patch(url, headers=headers, json=command(view, updates=[changed])).json()
    assert patched["result"] is None and "rent" in patched["needs_review"]
    assert financial.get(url + "/results/" + original["id"], headers=headers).json() == original
    assert (
        financial.post(url + "/calculate", headers=headers, json=command(view)).status_code == 409
    )
    # Profile edits invalidate the financial scope; old results remain historical.
    edit(financial, headers, profile, 2, industry="auto_repair", budget="9000000")
    stale = financial.get(url, headers=headers).json()
    assert not stale["current"] and stale["result"] is None
    assert (
        financial.post(url + "/calculate", headers=headers, json=command(patched)).status_code
        == 409
    )


def test_owner_consent_payload_and_idempotency_isolation(financial: TestClient) -> None:
    headers, url, profile = project(financial)
    other, _, _ = project(financial)
    assert financial.get(url).status_code == 401
    assert financial.get(url, headers=other).status_code == 404
    view = inputs(financial, headers, url)
    payload = command(view, confirm=list(view["document"]["entries"]))
    assert financial.post(url + "/review", headers=other, json=payload).status_code == 404
    assert financial.post(url + "/review", headers=headers, json=payload).status_code == 200
    assert financial.post(url + "/review", headers=headers, json=payload).status_code == 200
    payload["confirm"] = []
    assert financial.post(url + "/review", headers=headers, json=payload).status_code == 409
    update = dict(
        parameter="rent",
        base="1",
        low="1",
        high="1",
        unit="RUB/month",
        source={"origin": "open_data"},
    )
    assert (
        financial.patch(url, headers=headers, json=command(view, updates=[update])).status_code
        == 422
    )
    consenturl = profile.replace("/api/v2/", "/api/v1/").replace(
        "/industry-profile", "/consents/assistant"
    )
    assert (
        financial.put(
            consenturl,
            headers=headers,
            json=dict(expected_revision=1, text_version="assistant-demo-v1", decision="withdraw"),
        ).status_code
        == 200
    )
    assert financial.get(url, headers=headers).status_code == 403


def test_school_course_and_reload_no_geo(financial: TestClient) -> None:
    headers, url, _ = project(financial, "online_school")
    view = inputs(financial, headers, url, "online_school")
    result = financial.patch(url, headers=headers, json=command(view, billing_model="course"))
    view = reviewed(financial, headers, url, result.json())
    view = financial.post(url + "/calculate", headers=headers, json=command(view)).json()
    base = view["result"]["result"]["scenarios"][1]
    assert base["period"] == "course_cohort" and base["operating_result"] == "-280000.00"
    assert financial.get(url, headers=headers).json() == view


def test_proposal_provenance_rejection_and_single_call_replay(financial: TestClient) -> None:
    headers, url, _ = project(financial)
    calls = []

    class Fake:
        async def propose(self, *args: object) -> tuple[AssumptionProposal, float]:
            calls.append(1)
            return AssumptionProposal.model_validate(
                dict(
                    model="auto_repair",
                    assumptions=[
                        dict(
                            parameter="rent",
                            base="100000",
                            low="80000",
                            high="120000",
                            unit="RUB/month",
                            basis="Исследовательское допущение; проверить",
                        )
                    ],
                )
            ), 1

    app.dependency_overrides[get_assumption_llm] = lambda: Fake()
    view = financial.get(url, headers=headers).json()
    payload = command(view)
    result = financial.post(url + "/propose", headers=headers, json=payload)
    assert result.status_code == 200, result.text
    view = result.json()
    rent = view["document"]["entries"]["rent"]
    assert rent["review"] == "proposed" and rent["source"]["origin"] == "synthetic"
    assert financial.post(url + "/propose", headers=headers, json=payload).status_code == 200
    assert len(calls) == 1
    review = financial.post(url + "/review", headers=headers, json=command(view, confirm=["rent"]))
    assert review.json()["document"]["entries"]["rent"]["epistemic"] == "assumed"
    assert review.json()["document"]["entries"]["rent"]["source"]["origin"] == "synthetic"
    rejected = financial.post(
        url + "/review", headers=headers, json=command(review.json(), reject=["rent"])
    )
    assert "rent" in rejected.json()["missing"]


def test_late_proposal_has_no_connection_and_cannot_replace_edit(
    financial: TestClient, migrated_database: tuple[Engine, UUID]
) -> None:
    headers, url, _ = project(financial)
    engine, _ = migrated_database
    calls = []

    class Late:
        async def propose(self, *args: object) -> tuple[AssumptionProposal, float]:
            assert engine.pool.checkedout() == 0  # type: ignore[attr-defined]
            calls.append(1)
            # Simulate a concurrent confirmed-profile edit without retaining any inference DB lease.
            from app.db.models import ConversationRecord

            owner = UUID(url.split("/")[4])
            with Session(engine) as session, session.begin():
                row = session.get(ConversationRecord, owner)
                assert row is not None
                row.version += 1
            return AssumptionProposal.model_validate(dict(model="auto_repair", assumptions=[])), 1

    app.dependency_overrides[get_assumption_llm] = lambda: Late()
    response = financial.post(
        url + "/propose", headers=headers, json=command(financial.get(url, headers=headers).json())
    )
    assert response.status_code == 409, response.text
    with Session(engine) as session:
        row = session.scalar(
            sa.select(FinancialActionRecord).where(
                FinancialActionRecord.conversation_id == UUID(url.split("/")[4])
            )
        )
        assert row and row.state == "failed"
    assert calls == [1]


def test_model_unavailable_manual_inputs_still_calculate(
    financial: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BA_AGENT_ENABLED", "1")
    headers, url, _ = project(financial)

    class Offline:
        async def propose(self, *args: object) -> tuple[AssumptionProposal, float]:
            raise LLMError("llm_unavailable", 503)

    app.dependency_overrides[get_assumption_llm] = lambda: Offline()
    response = financial.post(
        url + "/propose", headers=headers, json=command(financial.get(url, headers=headers).json())
    )
    assert response.status_code == 503
    assert financial.get(url, headers=headers).json()["proposal_status"] == "failed"
    view = reviewed(financial, headers, url, inputs(financial, headers, url))
    assert (
        financial.post(url + "/calculate", headers=headers, json=command(view)).json()["result"][
            "result"
        ]["status"]
        == "calculated"
    )


def test_feature_flags_default_closed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    for industry, finance in (("0", "0"), ("0", "1"), ("1", "0")):
        monkeypatch.setenv("BA_INDUSTRY_ENABLED", industry)
        monkeypatch.setenv("BA_FINANCE_V2_ENABLED", finance)
        response = client.get(f"/api/v2/conversations/{uuid4()}/financial-scenarios")
        assert response.status_code == 503


def test_late_calculation_cannot_publish_after_profile_change(
    financial: TestClient, migrated_database: tuple[Engine, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.db.models import ConversationRecord, FinancialResultRecord
    from app.finance.v2.engine import calculate
    from app.finance.v2.schemas import FinancialCalculation, FinancialDocument

    headers, url, _ = project(financial)
    engine, _ = migrated_database
    view = reviewed(financial, headers, url, inputs(financial, headers, url))

    def late(doc: FinancialDocument) -> FinancialCalculation:
        assert engine.pool.checkedout() == 0  # type: ignore[attr-defined]
        with Session(engine) as db, db.begin():
            row = db.get(ConversationRecord, UUID(url.split("/")[4]))
            assert row
            row.version += 1
        return calculate(doc)

    monkeypatch.setattr("app.api.financial_scenarios.calculate", late)
    response = financial.post(url + "/calculate", headers=headers, json=command(view))
    assert response.status_code == 409
    with Session(engine) as db:
        assert (
            db.scalar(
                sa.select(sa.func.count())
                .select_from(FinancialResultRecord)
                .where(FinancialResultRecord.conversation_id == UUID(url.split("/")[4]))
            )
            == 0
        )


def test_concurrent_review_has_one_winner(financial: TestClient) -> None:
    from concurrent.futures import ThreadPoolExecutor

    headers, url, _ = project(financial)
    view = inputs(financial, headers, url)

    def review_once(_: int) -> int:
        return financial.post(
            url + "/review", headers=headers, json=command(view, confirm=["rent"])
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(review_once, range(2))) == [200, 409]


def test_school_proposal_needs_explicit_payment_basis(financial: TestClient) -> None:
    headers, url, _ = project(financial, "online_school")

    class Never:
        async def propose(self, *args: object) -> tuple[AssumptionProposal, float]:
            raise AssertionError("Ambiguous payment periods must not reach the model")

    app.dependency_overrides[get_assumption_llm] = lambda: Never()
    response = financial.post(
        url + "/propose", headers=headers, json=command(financial.get(url, headers=headers).json())
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "financial_billing_required"


def test_incompatible_profile_driver_does_not_block_manual_repair(financial: TestClient) -> None:
    headers, url, profile_url = project(financial)
    edited = edit(financial, headers, profile_url, 2, industry="auto_repair", service_bays=0)
    response = financial.post(
        profile_url + "/confirm",
        headers=headers,
        json=dict(expected_version=edited["profile"]["revision"]),
    )
    assert response.status_code == 200
    view = financial.get(url, headers=headers)
    assert view.status_code == 200, view.text
    assert "service_bays" in view.json()["missing"]
    assert "service_bays" not in view.json()["document"]["entries"]


def test_generic_unknown_business_uses_only_user_financial_units(financial: TestClient) -> None:
    _, headers, profile_url = setup(financial)
    values = dict(
        budget="2000000",
        business_model="сервис",
        physical_premises=False,
        audience="фермеры",
        revenue_streams="обслуживание одной робототеплицы",
    )
    patched = financial.patch(
        profile_url,
        headers=headers,
        json=dict(
            expected_version=0,
            industry="generic",
            raw_industry="Обслуживание робототеплиц",
            updates=[dict(field=k, value=v) for k, v in values.items()],
        ),
    )
    assert patched.status_code == 200
    confirmed = financial.post(
        profile_url + "/confirm", headers=headers, json={"expected_version": 1}
    )
    assert confirmed.status_code == 200 and confirmed.json()["plan"]["geo_required"] is False
    url = profile_url.replace("industry-profile", "financial-scenarios")
    view = financial.get(url, headers=headers).json()
    assert view["configuration"]["id"] == "generic"
    numbers = dict(
        unit_sales="100",
        unit_price="2000",
        variable_per_unit="500",
        rent="0",
        payroll="0",
        utilities="0",
        marketing="0",
        other_fixed="50000",
    )
    updates = [
        dict(
            parameter=p.id,
            base=numbers[p.id],
            low=numbers[p.id],
            high=numbers[p.id],
            unit=p.unit,
            kind="user_assumption",
        )
        for p in configuration("generic").parameters
    ]
    view = financial.patch(url, headers=headers, json=command(view, updates=updates)).json()
    view = reviewed(financial, headers, url, view)
    response = financial.post(url + "/calculate", headers=headers, json=command(view))
    assert response.status_code == 200, response.text
    base = response.json()["result"]["result"]["scenarios"][1]
    assert base["operating_result"] == "100000.00" and base["capacity"] is None
    assert base["volume_unit"] == "units" and base["break_even"]["units"] == "34"
