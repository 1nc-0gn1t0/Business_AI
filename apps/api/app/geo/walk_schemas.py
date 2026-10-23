from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.api.schemas import Contract
from app.geo.candidate_schemas import Version
from app.geo.schemas import Bounds, PointGeometry, Slug


class WalkManifest(Contract):
    origin: Literal["open_data"] = "open_data"
    source_name: Literal["OpenStreetMap via Overpass API"] = "OpenStreetMap via Overpass API"
    slug: Slug
    city: str = Field(min_length=1, max_length=200)
    bbox: Bounds
    source_url: str
    query: str
    sha256: Version
    source_sha256: Version
    osm_base: AwareDatetime
    fetched_at: AwareDatetime
    normalization: Literal["walking_minimal_v1"] = "walking_minimal_v1"
    license: Literal["ODbL-1.0"] = "ODbL-1.0"
    attribution: Literal["© OpenStreetMap contributors"] = "© OpenStreetMap contributors"


class WalkGraphView(Contract):
    id: UUID
    manifest: WalkManifest
    graph_version: Version
    build_version: str
    spatial_runtime: str
    metric_crs: int
    edge_count: int
    node_count: int
    component_count: int
    diagnostics: dict[str, int]
    imported_at: AwareDatetime


class CatchmentRequest(Contract):
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    latitude: float = Field(ge=-85, le=85, allow_inf_nan=False)
    distance_m: int = Field(default=500, strict=True, ge=50, le=2000)
    max_snap_m: int = Field(default=30, strict=True, ge=0, le=100)
    data_version: Version | None = None
    graph_version: Version | None = None


class WalkLine(Contract):
    type: Literal["LineString"] = "LineString"
    coordinates: list[tuple[float, float]]


class ReachableSegment(Contract):
    type: Literal["Feature"] = "Feature"
    geometry: WalkLine
    properties: dict[str, int | float]


class ReachableNetwork(Contract):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: tuple[ReachableSegment, ...] = ()


class WalkingPOI(Contract):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: PointGeometry
    properties: dict[str, Any]


class WalkingPOIs(Contract):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: tuple[WalkingPOI, ...] = ()


class CatchmentResult(Contract):
    status: Literal[
        "ok",
        "partial",
        "graph_unavailable",
        "outside_coverage",
        "no_network_access",
        "resource_limit",
    ]
    reasons: tuple[str, ...]
    algorithm_version: str
    request_fingerprint: Version
    request_snapshot: CatchmentRequest
    graph: WalkGraphView | None = None
    poi_data_version: Version
    origin: Literal["modelled"] = "modelled"
    distance_method: Literal["directed_osm_network_plus_explicit_snap_connectors"] = (
        "directed_osm_network_plus_explicit_snap_connectors"
    )
    source_snap_m: float | None = None
    coverage_margin_m: float | None = None
    fully_covered: bool = False
    network: ReachableNetwork = Field(default_factory=ReachableNetwork)
    pois: WalkingPOIs = Field(default_factory=WalkingPOIs)
    category_counts: dict[str, int] = Field(default_factory=dict)
    reachable_poi_count: int = 0
    straight_line_poi_count: int = 0
    unsnapped_poi_count: int = 0
    no_route_in_loaded_graph_count: int = 0
    visited_nodes: int = 0
    loaded_edges: int = 0
    source_component_nodes: int | None = None
    on_largest_component: bool | None = None
    runtime_ms: float = 0
    limitations: tuple[str, ...]
