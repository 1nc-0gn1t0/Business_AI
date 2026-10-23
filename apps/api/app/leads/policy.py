from uuid import uuid4

from app.bank.matching import digest
from app.leads.schemas import ConsentText, DraftAction, LeadDraft, LeadPayload, LeadReceipt

TEXTS = (
    ConsentText(
        purpose="assistant",
        version="assistant-demo-v1",
        title="Использование ассистента",
        text="Согласен на локальную обработку параметров бизнес-идеи для работы Business AI. "
        "Не сообщайте паспортные, контактные и банковские данные. Отзыв останавливает "
        "новые сообщения и изменения профиля; просмотр истории и базовые расчёты доступны.",
    ),
    ConsentText(
        purpose="marketing",
        version="marketing-demo-v1",
        title="Маркетинговые рекомендации",
        text="Отдельно согласен на маркетинговые рекомендации. Это необязательно. "
        "Рассылки и внешний маркетинг в прототипе не реализованы. Отказ не блокирует "
        "аналитику, финансы, просмотр каталога и подбор по моему запросу.",
    ),
    ConsentText(
        purpose="demo_lead",
        version="demo-lead-v1",
        title="Подготовка и демонстрационная передача",
        text="Согласен на подготовку, хранение и создание локальной демонстрационной заявки "
        "из показанных полей и выбранных продуктов. Данные в ВТБ не отправляются. "
        "Получатель — только локальный mock Business AI. Это не банковская заявка. "
        "Отзыв блокирует дальнейшую подготовку, изменение, подтверждение и отправку; "
        "история согласий, квитанций и аудит сохраняются.",
    ),
)


class LeadError(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code = code
        self.status = status


def fingerprint(payload: LeadPayload, profile_version: int) -> str:
    return digest({"payload": payload.model_dump(mode="json"), "profile_version": profile_version})


def check_action(draft: LeadDraft, action: DraftAction) -> None:
    if draft.revision != action.expected_revision:
        raise LeadError("lead_revision_conflict")
    if draft.payload_fingerprint != action.payload_fingerprint:
        raise LeadError("lead_payload_conflict")
    if draft.stale:
        raise LeadError("lead_profile_stale")


class MockLeadAdapter:
    """Local receipt factory. No transport, HTTP client or bank reference exists."""

    def submit(self, draft: LeadDraft, **values: object) -> LeadReceipt:
        return LeadReceipt.model_validate(
            {
                "id": uuid4(),
                "draft_id": draft.id,
                "draft_revision": draft.revision,
                "profile_version": draft.profile_version,
                "payload": draft.payload,
                "payload_fingerprint": draft.payload_fingerprint,
                **values,
            }
        )
