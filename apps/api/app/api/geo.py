from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.geo.candidate_schemas import CandidateCollection, CandidateRequest
from app.geo.candidates import generate
from app.geo.ranking import rank_candidates
from app.geo.ranking_schemas import RankingCollection, RankingRequest
from app.geo.schemas import (
    Bounds,
    CategoriesView,
    DatasetView,
    DistrictCollection,
    POICollection,
    Slug,
    SpatialQuery,
)
from app.geo.service import GeoData
from app.geo.walk_ranking import WalkingRankingRequest, WalkingRankingResult, rank_walking
from app.geo.walk_schemas import CatchmentRequest, CatchmentResult, WalkGraphView
from app.geo.walking import catchment, graph_for

router = APIRouter(prefix="/api/v1/geo", tags=["geo"])
Database = Annotated[Session, Depends(get_session, scope="function")]
Version = Annotated[str | None, Query(pattern=r"^[0-9a-f]{64}$")]


@router.get("/{slug}/walking-graph", response_model=WalkGraphView | None)
def walking_graph(
    slug: Slug, session: Database, graph_version: Version = None
) -> WalkGraphView | None:
    GeoData(session).dataset(slug)
    return graph_for(session, slug, graph_version)


@router.post("/{slug}/catchment", response_model=CatchmentResult)
def walking_catchment(slug: Slug, request: CatchmentRequest, session: Database) -> CatchmentResult:
    return catchment(session, slug, request)


@router.post("/{slug}/walking-rankings", response_model=WalkingRankingResult)
def walking_rankings(
    slug: Slug, request: WalkingRankingRequest, session: Database
) -> WalkingRankingResult:
    return rank_walking(session, slug, request)


@router.post("/{slug}/rankings", response_model=RankingCollection)
def rankings(slug: Slug, request: RankingRequest, session: Database) -> RankingCollection:
    return rank_candidates(session, slug, request)


@router.post("/{slug}/candidates", response_model=CandidateCollection)
def candidates(slug: Slug, request: CandidateRequest, session: Database) -> CandidateCollection:
    return generate(session, slug, request)


@router.get("/datasets", response_model=list[DatasetView])
def datasets(session: Database) -> list[dict[str, Any]]:
    return GeoData(session).datasets()


@router.get("/{slug}/pois", response_model=POICollection)
def pois(
    slug: Slug,
    session: Database,
    bbox: str | None = None,
    longitude: float | None = None,
    latitude: float | None = None,
    radius_m: float | None = None,
    district_id: int | None = None,
    category: str | None = None,
    limit: int = 100,
    offset: int = 0,
    data_version: Version = None,
) -> dict[str, Any]:
    try:
        query = SpatialQuery(
            bbox=Bounds.parse(bbox) if bbox is not None else None,
            longitude=longitude,
            latitude=latitude,
            radius_m=radius_m,
            district_id=district_id,
            category=category,
            limit=limit,
            offset=offset,
            data_version=data_version,
        )
        if offset and not data_version:
            raise ValueError("Pagination must pin data_version")
    except (ValueError, ValidationError):
        raise HTTPException(422, detail={"code": "invalid_geo_query"}) from None
    return GeoData(session).pois(slug, query)


@router.get("/{slug}/districts", response_model=DistrictCollection)
def districts(slug: Slug, session: Database, data_version: Version = None) -> dict[str, Any]:
    return GeoData(session).districts(slug, data_version)


@router.get("/{slug}/categories", response_model=CategoriesView)
def categories(slug: Slug, session: Database) -> dict[str, Any]:
    return GeoData(session).categories(slug)
