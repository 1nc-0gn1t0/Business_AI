import math
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from app.api.schemas import Contract

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
Coordinate = Annotated[float, Field(allow_inf_nan=False)]
OSM_TAG_KEYS = {
    "name",
    "name:ru",
    "amenity",
    "shop",
    "highway",
    "brand",
    "operator",
    "addr:street",
    "addr:housenumber",
    "wheelchair",
    "opening_hours",
    "boundary",
    "admin_level",
    "type",
}


class Bounds(Contract):
    west: Coordinate = Field(ge=-180, le=180)
    south: Coordinate = Field(ge=-85, le=85)
    east: Coordinate = Field(ge=-180, le=180)
    north: Coordinate = Field(ge=-85, le=85)

    @model_validator(mode="after")
    def valid_extent(self) -> Self:
        if not self.west < self.east or not self.south < self.north:
            raise ValueError("Bounds must be west,south,east,north; antimeridian unsupported")
        if (self.east - self.west) * (self.north - self.south) > 0.1:
            raise ValueError("Use a city-sized extract (at most 0.1 square degrees)")
        return self

    @classmethod
    def parse(cls, value: str) -> "Bounds":
        west, south, east, north = map(float, value.split(","))
        return cls(west=west, south=south, east=east, north=north)

    def contains(self, lon: float, lat: float) -> bool:
        return self.west <= lon <= self.east and self.south <= lat <= self.north


class SnapshotManifest(Contract):
    schema_version: Literal[1] = 1
    slug: Slug
    city: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    bbox: Bounds
    source_url: str
    query: str
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    source_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None
    normalization: Literal["none", "poi_minimal_v1"] = "none"
    fetched_at: AwareDatetime
    osm_base: AwareDatetime
    origin: Literal["open_data"] = "open_data"
    source_name: Literal["OpenStreetMap via Overpass API"] = "OpenStreetMap via Overpass API"
    license: Literal["ODbL-1.0"] = "ODbL-1.0"
    attribution: Literal["© OpenStreetMap contributors"] = "© OpenStreetMap contributors"


class SpatialQuery(Contract):
    bbox: Bounds | None = None
    longitude: Coordinate | None = Field(default=None, ge=-180, le=180)
    latitude: Coordinate | None = Field(default=None, ge=-85, le=85)
    radius_m: Coordinate | None = Field(default=None, gt=0, le=10000)
    district_id: int | None = Field(default=None, gt=0)
    category: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0, le=10000)
    data_version: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None

    @model_validator(mode="after")
    def spatial_filter(self) -> Self:
        parts = [self.longitude, self.latitude, self.radius_m]
        if any(item is not None for item in parts) and not all(item is not None for item in parts):
            raise ValueError("longitude,latitude,radius_m must be supplied together")
        if self.bbox is None and self.radius_m is None and self.district_id is None:
            raise ValueError("Supply bbox, a radius, or district_id")
        return self


def valid_coordinate(lon: float, lat: float) -> bool:
    return math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90


class DatasetView(Contract):
    slug: Slug
    city: str
    bbox: Bounds
    data_version: str
    origin: Literal["open_data"]
    source_name: str
    source_url: str
    license: Literal["ODbL-1.0"]
    license_url: str
    attribution: str
    osm_base: AwareDatetime
    fetched_at: AwareDatetime
    imported_at: AwareDatetime
    age_days: int
    stale: bool
    stale_after_days: int
    poi_count: int
    district_count: int
    diagnostics: dict[str, int]
    limitations: tuple[str, ...]


class PointGeometry(Contract):
    type: Literal["Point"]
    coordinates: tuple[Coordinate, Coordinate]


class MultiPolygonGeometry(Contract):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[tuple[Coordinate, Coordinate]]]]


class POIProperties(Contract):
    osm_type: Literal["node", "way", "relation"]
    osm_id: int
    osm_version: int
    observed_at: AwareDatetime
    name: str | None
    categories: tuple[str, ...]
    tags: dict[str, str]
    representation: Literal["osm_node", "osm_bbox_center"]
    distance_m: float | None


class POIFeature(Contract):
    type: Literal["Feature"]
    id: str
    geometry: PointGeometry
    properties: POIProperties


class POICollection(Contract):
    type: Literal["FeatureCollection"]
    features: tuple[POIFeature, ...]
    dataset: DatasetView
    returned_count: int
    next_offset: int | None
    coverage: Literal["saved_bbox_only"]


class DistrictProperties(Contract):
    osm_id: int
    osm_version: int
    observed_at: AwareDatetime
    name: str | None
    admin_level: int


class DistrictFeature(Contract):
    type: Literal["Feature"]
    id: str
    geometry: MultiPolygonGeometry
    properties: DistrictProperties


class DistrictCollection(Contract):
    type: Literal["FeatureCollection"]
    features: tuple[DistrictFeature, ...]
    truncated: bool
    dataset: DatasetView


class CategoryCount(Contract):
    category: str
    mapped_features: int


class CategoriesView(Contract):
    dataset: DatasetView
    categories: tuple[CategoryCount, ...]
