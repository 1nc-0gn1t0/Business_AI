import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.geo.schemas import OSM_TAG_KEYS, Bounds, SnapshotManifest

MAX_BYTES = 64 * 1024 * 1024
DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"


class GeoImportError(ValueError):
    """Safe operator-facing failure. Active data is never modified on failure."""


def build_query(bbox: Bounds) -> str:
    extent = f"{bbox.south},{bbox.west},{bbox.north},{bbox.east}"
    return (
        "[out:json][timeout:90][maxsize:134217728];"
        f'(nwr["amenity"]({extent});nwr["shop"]({extent});'
        f'nwr["highway"="bus_stop"]({extent});)->.poi;'
        'rel["boundary"="administrative"]["admin_level"~"^(8|9|10)$"]'
        f"({extent})->.districts;.poi out meta center;.districts out meta geom;"
    )


def parse_document(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_BYTES:
        raise GeoImportError("OSM snapshot exceeds 64 MiB")
    try:
        document = json.loads(raw)
        if not isinstance(document, dict) or not isinstance(document.get("elements"), list):
            raise ValueError
        if document.get("remark"):
            raise GeoImportError("Overpass reported an error/partial result; snapshot rejected")
        base = datetime.fromisoformat(
            document["osm3s"]["timestamp_osm_base"].replace("Z", "+00:00")
        )
        if base.tzinfo is None:
            raise ValueError
        if len(document["elements"]) > 100000:
            raise GeoImportError("OSM snapshot exceeds 100000 elements")
        return document
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        if isinstance(error, GeoImportError):
            raise
        raise GeoImportError("Invalid Overpass JSON or missing source timestamp") from None


class OSMProvider(Protocol):
    def fetch(self, bbox: Bounds) -> bytes: ...


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


class OverpassProvider:
    def __init__(self, endpoint: str = DEFAULT_ENDPOINT):
        url = urlsplit(endpoint)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise GeoImportError("Use an HTTPS Overpass endpoint without credentials")
        self.endpoint = endpoint

    def fetch(self, bbox: Bounds) -> bytes:
        request = Request(
            self.endpoint,
            data=build_query(bbox).encode(),
            headers={"Content-Type": "text/plain", "User-Agent": "BusinessAI-BA006/0.1"},
            method="POST",
        )
        try:
            with build_opener(NoRedirect()).open(request, timeout=120) as response:
                raw = bytes(response.read(MAX_BYTES + 1))
        except HTTPError as error:
            raise GeoImportError(
                f"Overpass HTTP {error.code}; use a verified cache or retry later"
            ) from None
        except (URLError, OSError):
            raise GeoImportError(
                "Overpass unavailable/timeout; use a verified cached snapshot"
            ) from None
        parse_document(raw)
        return raw


def normalize_document(document: dict[str, Any]) -> bytes:
    # Editor usernames/UIDs/change-set IDs are unnecessary for a business POI dataset.
    for element in document["elements"]:
        if isinstance(element, dict):
            for field in ("user", "uid", "changeset"):
                element.pop(field, None)
            if isinstance(element.get("tags"), dict):
                element["tags"] = {
                    key: value for key, value in element["tags"].items() if key in OSM_TAG_KEYS
                }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()


def save_snapshot(
    raw: bytes, path: Path, *, slug: str, city: str, bbox: Bounds, endpoint: str
) -> SnapshotManifest:
    document = parse_document(raw)
    source_sha256 = hashlib.sha256(raw).hexdigest()
    raw = normalize_document(document)
    manifest = SnapshotManifest(
        slug=slug,
        city=city,
        bbox=bbox,
        source_url=endpoint,
        query=build_query(bbox),
        sha256=hashlib.sha256(raw).hexdigest(),
        source_sha256=source_sha256,
        normalization="poi_minimal_v1",
        fetched_at=datetime.now(UTC),
        osm_base=document["osm3s"]["timestamp_osm_base"],
    )
    manifest_path = path.with_suffix(".manifest.json")
    if path.exists() or manifest_path.exists():
        raise GeoImportError("Snapshot paths already exist; choose a new filename")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest


def load_snapshot(path: Path) -> tuple[SnapshotManifest, dict[str, Any]]:
    if path.stat().st_size > MAX_BYTES:
        raise GeoImportError("OSM snapshot exceeds 64 MiB")
    raw = path.read_bytes()
    manifest = SnapshotManifest.model_validate_json(path.with_suffix(".manifest.json").read_bytes())
    document = parse_document(raw)
    if manifest.normalization == "poi_minimal_v1":
        if not manifest.source_sha256 or any(
            isinstance(element, dict) and {"user", "uid", "changeset"}.intersection(element)
            for element in document["elements"]
        ):
            raise GeoImportError("Invalid snapshot normalization")
    if hashlib.sha256(raw).hexdigest() != manifest.sha256:
        raise GeoImportError("Snapshot checksum mismatch")
    if manifest.query != build_query(manifest.bbox):
        raise GeoImportError("Unsupported snapshot query/filter version")
    base = datetime.fromisoformat(document["osm3s"]["timestamp_osm_base"].replace("Z", "+00:00"))
    if base != manifest.osm_base or base > manifest.fetched_at:
        raise GeoImportError("Inconsistent source timestamps")
    return manifest, document
