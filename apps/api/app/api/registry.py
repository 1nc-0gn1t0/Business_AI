"""Public imported-data metadata only; no profile access, mutations or network dispatch."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import Contract
from app.data.coverage import coverage
from app.data.registry import config_hash, load_registry
from app.data.registry_schemas import (
    CoverageQuery,
    CoverageResult,
    DataCategory,
    FreshnessPolicy,
    RegistryConfig,
    SourceDefinition,
    Territory,
)
from app.data.schemas import Version
from app.db.session import get_session

router = APIRouter(prefix="/api/v2/data-registry", tags=["data-registry"])
Registry = Annotated[RegistryConfig, Depends(load_registry)]
Database = Annotated[Session, Depends(get_session, scope="function")]


class RegistryCatalog(Contract):
    schema_version: Literal["data-registry-v2"] = "data-registry-v2"
    revision: str
    config_sha256: Version
    sources: tuple[SourceDefinition, ...]
    categories: tuple[DataCategory, ...]
    freshness_policies: tuple[FreshnessPolicy, ...]
    territories: tuple[Territory, ...]


@router.get("", response_model=RegistryCatalog)
def catalog(registry: Registry) -> RegistryCatalog:
    return RegistryCatalog(
        revision=registry.revision,
        config_sha256=config_hash(registry),
        sources=registry.sources,
        categories=registry.categories,
        freshness_policies=registry.policies,
        territories=registry.territories,
    )


@router.post("/coverage", response_model=CoverageResult)
def check_coverage(query: CoverageQuery, registry: Registry, session: Database) -> CoverageResult:
    return coverage(session, query, registry)
