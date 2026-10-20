import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.main import app

from .support import isolated_database, migrate

pytestmark = pytest.mark.skipif(
    os.environ.get("BA_RUN_DB_TESTS") != "1", reason="Requires Postgres"
)


@pytest.fixture
def client(migrated_database: tuple[Engine, UUID]) -> Iterator[TestClient]:
    engine, _ = migrated_database

    def session() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as db, db.begin():
            yield db

    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_session)


def create(client: TestClient) -> tuple[dict[str, Any], dict[str, str], str]:
    response = client.post("/api/v1/conversations")
    assert response.status_code == 201, response.text
    body = response.json()
    headers = {"X-Conversation-Token": body["access_token"]}
    return body, headers, "/api/v1/conversations/" + body["id"]


def test_real_multi_turn_correction_confirmation_and_history(client: TestClient) -> None:
    view, headers, url = create(client)
    for text in ["Хочу кофейню в Казани с бюджетом 2 млн", "навынос", "свои средства"]:
        response = client.post(
            url + "/messages",
            headers=headers,
            json={
                "content": text,
                "expected_version": view["version"],
            },
        )
        assert response.status_code == 200, response.text
        view = response.json()
    assert view["state"] == "awaiting_confirmation"
    assert Decimal(view["profile"]["budget"]) == Decimal("2000000")
    confirmed = client.post(
        url + "/profile/confirm",
        headers=headers,
        json={
            "expected_version": view["version"],
        },
    ).json()
    assert confirmed["state"] == "confirmed"
    corrected = client.patch(
        url + "/profile",
        headers=headers,
        json={
            "expected_version": confirmed["version"],
            "patch": {"city": "Тверь", "preferences": {"format": "с залом"}},
        },
    ).json()
    assert corrected["state"] == "awaiting_confirmation"
    assert corrected["profile"]["confirmation_state"] == "draft"
    assert corrected["profile"]["city"] == "Тверь"
    result = client.post(
        url + "/messages",
        headers=headers,
        json={
            "content": "Подтверждаю",
            "expected_version": corrected["version"],
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["state"] == "confirmed"
    assert (
        client.get(url + "/profile", headers=headers).json()["version"] == result.json()["version"]
    )
    history = client.get(url + "/history", headers=headers).json()
    assert len(history) == result.json()["version"] + 1
    assert history[3]["profile"]["city"] == "Казань"
    assert history[4]["source"] == "confirmation"
    assert history[-1]["profile"]["city"] == "Тверь"
    messages = client.get(url + "/messages", headers=headers).json()
    assert any(row["role"] == "user" and row["content"] == "Подтверждаю" for row in messages)
    assert len(client.get(url + "/messages?offset=1&limit=2", headers=headers).json()) == 2
    assert len(client.get(url + "/history?offset=1&limit=2", headers=headers).json()) == 2
    assert client.get(url + "/history?limit=101", headers=headers).status_code == 422


def test_access_control_and_sessions_do_not_share_data(client: TestClient) -> None:
    first, headers, url = create(client)
    _, other_headers, other_url = create(client)
    for path in ["", "/profile", "/history", "/messages"]:
        assert client.get(url + path).status_code == 401
        denied = client.get(url + path, headers=other_headers)
        assert denied.status_code == 404
        assert first["access_token"] not in denied.text
    assert (
        client.patch(
            url + "/profile",
            headers=other_headers,
            json={
                "expected_version": 0,
                "patch": {"city": "Москва"},
            },
        ).status_code
        == 404
    )
    assert client.get(other_url, headers=other_headers).json()["profile"]["city"] is None
    assert client.get(url, headers=headers).json()["version"] == 0
    assert client.get(url, headers=headers).json().get("access_token") is None


def test_invalid_updates_are_atomic_and_do_not_confirm(client: TestClient) -> None:
    _, headers, url = create(client)
    assert (
        client.post(
            url + "/profile/confirm", headers=headers, json={"expected_version": 0}
        ).status_code
        == 409
    )
    invalid = client.post(
        url + "/messages",
        headers=headers,
        json={
            "expected_version": 0,
            "content": "бюджет: -2 млн",
        },
    )
    assert invalid.status_code == 422, invalid.text
    assert client.get(url, headers=headers).json()["version"] == 0
    assert len(client.get(url + "/history", headers=headers).json()) == 1
    assert len(client.get(url + "/messages", headers=headers).json()) == 1
    assert (
        client.post(
            url + "/messages",
            headers=headers,
            json={
                "expected_version": 0,
                "content": " ",
            },
        ).status_code
        == 422
    )


def test_stale_and_concurrent_writes_cannot_lose_updates(client: TestClient) -> None:
    _, headers, url = create(client)

    def patch(city: str) -> int:
        return client.patch(
            url + "/profile",
            headers=headers,
            json={
                "expected_version": 0,
                "patch": {"city": city},
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(patch, ["Казань", "Москва"])) == [200, 409]
    current = client.get(url, headers=headers).json()
    assert current["version"] == 1
    assert len(client.get(url + "/history", headers=headers).json()) == 2
    conflict = client.post(
        url + "/messages",
        headers=headers,
        json={
            "expected_version": 0,
            "content": "Хочу пекарню",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "version_conflict"


def test_database_rejects_profile_without_conversation(
    migrated_database: tuple[Engine, UUID],
) -> None:
    engine, _ = migrated_database
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text("""
            INSERT INTO business_profiles (id, conversation_id, preferences)
            VALUES (:id, :conversation_id, '{}'::jsonb)
        """),
            {"id": uuid4(), "conversation_id": uuid4()},
        )


def test_upgrade_preserves_legacy_profiles_and_downgrade_keeps_them() -> None:
    with isolated_database() as name:
        migrate(name, "upgrade", "0001_contracts")
        legacy_profile_lifecycle(name)


def legacy_profile_lifecycle(temporary_database: str) -> None:
    migrate(temporary_database, "downgrade", "0001_contracts")
    old_profile = uuid4()
    old_conversation = uuid4()
    with psycopg.connect(dbname=temporary_database) as connection:
        connection.execute(
            """
            INSERT INTO business_profiles (id, conversation_id, city, budget, preferences)
            VALUES (%s, %s, 'Тверь', 2000000.10, '{}'::jsonb)
        """,
            (old_profile, old_conversation),
        )
    migrate(temporary_database, "upgrade", "head")
    with psycopg.connect(dbname=temporary_database) as connection:
        row = connection.execute(
            "SELECT token_hash FROM conversations WHERE id=%s", (old_conversation,)
        ).fetchone()
        assert row == ("0" * 64,)
        snapshot = connection.execute(
            "SELECT profile_snapshot FROM profile_revisions WHERE conversation_id=%s",
            (old_conversation,),
        ).fetchone()
        assert snapshot is not None and snapshot[0]["budget"] == "2000000.10"
    migrate(temporary_database, "check")
    migrate(temporary_database, "downgrade", "0001_contracts")
    with psycopg.connect(dbname=temporary_database) as connection:
        assert connection.execute(
            "SELECT city FROM business_profiles WHERE id=%s", (old_profile,)
        ).fetchone() == ("Тверь",)
    migrate(temporary_database, "upgrade", "head")
