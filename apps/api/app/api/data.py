from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.data.providers import policy, providers, sources
from app.data.schemas import (
    DataPolicy,
    DataSelection,
    IndicatorQuery,
    IndicatorResult,
    ProviderDataset,
    ProviderId,
    ProviderInfo,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/data-providers", tags=["data-providers"])
Database = Annotated[Session, Depends(get_session, scope="function")]


@router.get("/sources", response_model=list[ProviderInfo])
def provider_sources() -> list[ProviderInfo]:
    return sources()


@router.get("/policy", response_model=DataPolicy)
def current_policy() -> DataPolicy:
    return policy("real")


@router.post("/selection", response_model=DataPolicy)
def select_mode(request: DataSelection) -> DataPolicy:
    # Request-scoped selection, no shared mutable user setting or cross-session leakage.
    return policy(request.mode)


@router.get("/{provider}/datasets", response_model=list[ProviderDataset])
def provider_datasets(provider: ProviderId, session: Database) -> list[ProviderDataset]:
    return providers()[provider].datasets(session)


@router.post("/indicators", response_model=IndicatorResult)
def indicators(request: IndicatorQuery, session: Database) -> IndicatorResult:
    policy(request.mode)
    return providers()[request.provider].read(session, request)
