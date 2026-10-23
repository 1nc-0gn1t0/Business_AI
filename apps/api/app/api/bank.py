from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.api.conversations import Service, Token
from app.bank.matching import catalogue_view, load_catalogue, match, today
from app.bank.schemas import CatalogueView, MatchRequest, MatchResult
from app.services.conversations import VersionConflict

router = APIRouter(tags=["bank-products"])


def current_catalogue() -> CatalogueView:
    try:
        return catalogue_view(load_catalogue(), today())
    except (OSError, ValueError, ValidationError):
        raise HTTPException(503, detail={"code": "bank_catalogue_unavailable"}) from None


@router.get("/api/v1/bank-products", response_model=CatalogueView)
def products() -> CatalogueView:
    return current_catalogue()


@router.post(
    "/api/v1/conversations/{conversation_id}/bank-products/matches", response_model=MatchResult
)
def matches(
    conversation_id: UUID, body: MatchRequest, token: Token, service: Service
) -> MatchResult:
    view = service.get(conversation_id, token)
    if view.version != body.expected_version:
        raise VersionConflict(view.version)
    catalogue = current_catalogue()
    if body.catalogue_fingerprint and body.catalogue_fingerprint != catalogue.fingerprint:
        raise HTTPException(409, detail={"code": "bank_catalogue_version_conflict"})
    return match(view.profile, view.version, body.needs, catalogue)
