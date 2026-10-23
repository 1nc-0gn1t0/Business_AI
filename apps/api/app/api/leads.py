from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.conversations import Database, Limit, Offset, Token
from app.leads.policy import TEXTS
from app.leads.schemas import (
    AuditView,
    ConsentDecision,
    ConsentState,
    ConsentText,
    DraftAction,
    DraftEdit,
    DraftInput,
    LeadDraft,
    LeadReceipt,
    LeadWorkspace,
    Purpose,
    SubmitRequest,
)
from app.leads.service import Leads

router = APIRouter(
    prefix="/api/v1/conversations/{conversation_id}", tags=["consents-and-demo-leads"]
)
public_router = APIRouter(tags=["consents-and-demo-leads"])


@public_router.get("/api/v1/consent-texts", response_model=tuple[ConsentText, ...])
def texts() -> tuple[ConsentText, ...]:
    return TEXTS


def get_leads(session: Database) -> Leads:
    return Leads(session)


Service = Annotated[Leads, Depends(get_leads)]


@router.get("/consents", response_model=ConsentState)
def consents(conversation_id: UUID, token: Token, service: Service) -> ConsentState:
    service.authorise(conversation_id, token)
    return service.consents(conversation_id)


@router.put("/consents/{purpose}", response_model=ConsentState)
def decide(
    conversation_id: UUID, purpose: Purpose, body: ConsentDecision, token: Token, service: Service
) -> ConsentState:
    service.authorise(conversation_id, token)
    return service.decide(conversation_id, purpose, body)


@router.get("/leads", response_model=LeadWorkspace)
def workspace(conversation_id: UUID, token: Token, service: Service) -> LeadWorkspace:
    return service.workspace(service.authorise(conversation_id, token))


@router.post("/leads/drafts", response_model=LeadDraft, status_code=201)
def prepare(conversation_id: UUID, body: DraftInput, token: Token, service: Service) -> LeadDraft:
    return service.prepare(service.authorise(conversation_id, token), body)


@router.get("/leads/drafts/{draft_id}", response_model=LeadDraft)
def draft(conversation_id: UUID, draft_id: UUID, token: Token, service: Service) -> LeadDraft:
    return service.draft(service.authorise(conversation_id, token), draft_id)[1]


@router.put("/leads/drafts/{draft_id}", response_model=LeadDraft)
def edit(
    conversation_id: UUID, draft_id: UUID, body: DraftEdit, token: Token, service: Service
) -> LeadDraft:
    return service.prepare(service.authorise(conversation_id, token), body, draft_id)


@router.post("/leads/drafts/{draft_id}/confirm", response_model=LeadDraft)
def confirm(
    conversation_id: UUID, draft_id: UUID, body: DraftAction, token: Token, service: Service
) -> LeadDraft:
    return service.confirm(service.authorise(conversation_id, token), draft_id, body)


@router.post("/leads/drafts/{draft_id}/submit", response_model=LeadReceipt)
def submit(
    conversation_id: UUID, draft_id: UUID, body: SubmitRequest, token: Token, service: Service
) -> LeadReceipt:
    return service.submit(service.authorise(conversation_id, token), draft_id, body)


@router.get("/audit", response_model=list[AuditView])
def audit(
    conversation_id: UUID, token: Token, service: Service, offset: Offset = 0, limit: Limit = 50
) -> list[AuditView]:
    service.authorise(conversation_id, token)
    return service.events(conversation_id, offset, limit)
