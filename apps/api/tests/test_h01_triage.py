"""Bounded audit probes. Strict XFAIL is an open finding, never a security PASS."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.schemas import BusinessProfile
from app.db.session import get_session
from app.main import app


class OversizedProfileAccepted(AssertionError):
    pass


class ValidationInputReflected(AssertionError):
    pass


@pytest.mark.xfail(
    strict=True,
    raises=OversizedProfileAccepted,
    reason="H01-P1-01: full BusinessProfile lacks a city length bound; H-02",
)
def test_h01_full_profile_bounds_oversized_city() -> None:
    try:
        BusinessProfile(conversation_id=uuid4(), city="x" * 4096)
    except ValidationError:
        return
    raise OversizedProfileAccepted("4096-character city accepted; no load test performed")


@pytest.mark.xfail(
    strict=True,
    raises=ValidationInputReflected,
    reason="H01-P2-01: default request-validation error reflects supplied input; H-02/H-05",
)
def test_h01_validation_error_omits_input(caplog: pytest.LogCaptureFixture) -> None:
    def unbound_session() -> Iterator[Session]:
        # Validation must finish before the endpoint queries any DB.
        with Session() as session:
            yield session

    marker = "H01_SYNTHETIC_NOT_A_REAL_SECRET"
    app.dependency_overrides[get_session] = unbound_session
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/conversations/{uuid4()}/messages",
                headers={"X-Conversation-Token": "x" * 64},
                json={"expected_version": 0, "content": "hello", "unexpected": marker},
            )
        assert response.status_code == 422
        assert marker not in caplog.text
        assert "Traceback" not in response.text
        if marker in response.text:
            raise ValidationInputReflected("422 includes the sender's synthetic input")
    finally:
        app.dependency_overrides.pop(get_session)
