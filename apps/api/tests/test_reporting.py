from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.api.schemas import BusinessProfile
from app.domain.enums import ConfirmationState
from app.reporting.schemas import ReportSnapshot


def snapshot() -> ReportSnapshot:
    return ReportSnapshot(
        id=UUID(int=1),
        created_at=datetime(2026, 10, 25, tzinfo=UTC),
        profile_updated_at=datetime(2026, 10, 24, tzinfo=UTC),
        profile_version=2,
        profile=BusinessProfile(
            id=UUID(int=3),
            conversation_id=UUID(int=2),
            city="Казань",
            category="кофейня",
            budget=Decimal("2000000"),
            confirmation_state=ConfirmationState.CONFIRMED,
        ),
        geo=None,
        selected_zone=None,
        finance=None,
        bank=None,
        walking=None,
        providers=(),
        summary=("Недостаточно данных для инвестиционного решения.",),
        missing_sections=("geo", "finance", "bank", "walking"),
    )


def test_snapshot_preserves_provenance_and_contains_no_guest_secrets() -> None:
    from app.reporting.service import serialize

    value = serialize(snapshot())
    assert "Казань" in value.decode()
    assert b"user_input" in value
    assert b"access_token" not in value and b"messages" not in value
    assert serialize(snapshot()) == value


def test_pdf_is_structural_cyrillic_and_deterministic() -> None:
    from io import BytesIO

    from pypdf import PdfReader

    from app.reporting.pdf import render

    value = render(snapshot())
    assert value == render(snapshot())
    reader = PdfReader(BytesIO(value), strict=True)
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert "Казань" in text and "кофейня" in text and "₽" in text
    assert "Источники" in text and "Данные в ВТБ не отправляются" in text
    assert reader.pages[0].get("/Resources") is not None
