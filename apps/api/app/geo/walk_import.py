import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.bank.matching import digest
from app.db.models import WalkGraphRecord
from app.geo.candidate_policy import city_key
from app.geo.provider import DEFAULT_ENDPOINT, MAX_BYTES, GeoImportError, NoRedirect, parse_document
from app.geo.schemas import Bounds, valid_coordinate
from app.geo.service import GeoData
from app.geo.walk_graph import BUILD_VERSION, directions, permitted
from app.geo.walk_schemas import WalkGraphView, WalkManifest

TAGS = {
    "highway",
    "foot",
    "access",
    "barrier",
    "locked",
    "oneway",
    "oneway:foot",
    "foot:forward",
    "foot:backward",
    "bridge",
    "tunnel",
    "layer",
    "sidewalk",
    "area",
    "name",
    "type",
    "restriction",
    "restriction:foot",
    "except",
}


def query(bbox: Bounds) -> str:
    extent = f"{bbox.south},{bbox.west},{bbox.north},{bbox.east}"
    # Retrieve full way nodes, node barriers, and foot-specific restriction relations.
    return (
        "[out:json][timeout:90][maxsize:134217728];"
        f'way["highway"]({extent})->.roads;'
        '(.roads;node(w.roads);rel(bw.roads)["type"="restriction"];);out meta;'
    )


def fetch(
    path: Path, bbox: Bounds, slug: str, city: str, endpoint: str = DEFAULT_ENDPOINT
) -> WalkManifest:
    if path.exists() or path.with_suffix(".manifest.json").exists():
        raise GeoImportError("Choose a new snapshot filename")
    url = urlsplit(endpoint)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise GeoImportError("Expected HTTPS endpoint without credentials")
    request = Request(
        endpoint,
        data=query(bbox).encode(),
        method="POST",
        headers={"User-Agent": "BusinessAI-BA013/1.0", "Content-Type": "text/plain"},
    )
    with build_opener(NoRedirect()).open(request, timeout=120) as response:
        raw = response.read(MAX_BYTES + 1)
    doc = parse_document(raw)
    source_hash = hashlib.sha256(raw).hexdigest()
    for e in doc["elements"]:
        for field in ("user", "uid", "changeset"):
            e.pop(field, None)
        if "tags" in e:
            e["tags"] = {
                k: v
                for k, v in e["tags"].items()
                if k in TAGS
                or k.endswith(":conditional")
                or k.startswith("abandoned:")
                or k.startswith("disused:")
            }
    raw = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    manifest = WalkManifest(
        slug=slug,
        city=city,
        bbox=bbox,
        source_url=endpoint,
        query=query(bbox),
        sha256=hashlib.sha256(raw).hexdigest(),
        source_sha256=source_hash,
        osm_base=doc["osm3s"]["timestamp_osm_base"],
        fetched_at=datetime.now(UTC),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.with_suffix(".manifest.json").write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def load(path: Path) -> tuple[WalkManifest, dict[str, Any]]:
    if path.stat().st_size > MAX_BYTES:
        raise GeoImportError("Road snapshot exceeds size limit")
    raw = path.read_bytes()
    manifest = WalkManifest.model_validate_json(path.with_suffix(".manifest.json").read_bytes())
    doc = parse_document(raw)
    if hashlib.sha256(raw).hexdigest() != manifest.sha256 or manifest.query != query(manifest.bbox):
        raise GeoImportError("Road snapshot checksum/query mismatch")
    if any(
        {"user", "uid", "changeset"}.intersection(e)
        or any(
            k not in TAGS
            and not k.endswith(":conditional")
            and not k.startswith(("abandoned:", "disused:"))
            for k in e.get("tags", {})
        )
        for e in doc["elements"]
    ):
        raise GeoImportError("Road snapshot violates walking_minimal_v1 normalization")
    if (
        datetime.fromisoformat(doc["osm3s"]["timestamp_osm_base"].replace("Z", "+00:00"))
        != manifest.osm_base
        or manifest.osm_base > manifest.fetched_at
    ):
        raise GeoImportError("Inconsistent road snapshot timestamps")
    return manifest, doc


def segments(
    manifest: WalkManifest, doc: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    nodes: dict[int, dict[str, Any]] = {}
    ways = []
    excluded_ways: set[int] = set()
    diagnostics: Counter[str] = Counter()
    identities: set[tuple[str, int]] = set()
    for e in doc["elements"]:
        key = (e["type"], e["id"])
        if (
            key in identities
            or type(e["id"]) is not int
            or e["id"] <= 0
            or type(e.get("version")) is not int
            or e["version"] < 1
        ):
            raise GeoImportError("Invalid/duplicate OSM identity/version")
        identities.add(key)
        timestamp = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp > manifest.osm_base:
            raise GeoImportError("Invalid OSM element timestamp")
        tags = e.get("tags", {})
        if e["type"] == "node":
            if not valid_coordinate(e["lon"], e["lat"]):
                raise GeoImportError("Invalid OSM coordinate")
            nodes[e["id"]] = e
        elif e["type"] == "way":
            ways.append(e)
        elif e["type"] == "relation":
            # No foot turn-state engine in v1: exclude involved ways conservatively.
            if any(k.startswith("restriction:foot") for k in tags):
                excluded_ways.update(m["ref"] for m in e.get("members", []) if m["type"] == "way")
                diagnostics["restricted_relations"] += 1
    result: list[dict[str, Any]] = []
    for way in sorted(ways, key=lambda w: w["id"]):
        tags = way.get("tags", {})
        if (
            way["id"] in excluded_ways
            or not permitted(tags)
            or any(k.startswith(("abandoned:", "disused:")) for k in tags)
        ):
            diagnostics["excluded_ways"] += 1
            continue
        forward, backward = directions(tags)
        if not forward and not backward:
            diagnostics["unsupported_direction"] += 1
            continue
        refs = way.get("nodes", [])
        if len(refs) < 2 or any(ref not in nodes for ref in refs):
            raise GeoImportError("Missing way nodes: partial road response rejected")
        for u, v in zip(refs, refs[1:]):
            a, b = nodes[u], nodes[v]
            if not permitted(a.get("tags", {}), node=True) or not permitted(
                b.get("tags", {}), node=True
            ):
                diagnostics["blocked_segments"] += 1
                continue
            if not manifest.bbox.contains(a["lon"], a["lat"]) or not manifest.bbox.contains(
                b["lon"], b["lat"]
            ):
                diagnostics["boundary_segments_excluded"] += 1
                continue
            if u == v or (a["lon"], a["lat"]) == (b["lon"], b["lat"]):
                diagnostics["zero_segments_excluded"] += 1
                continue
            result.append(
                {
                    "edge_id": len(result) + 1,
                    "way_id": way["id"],
                    "u": u,
                    "v": v,
                    "forward": forward,
                    "backward": backward,
                    "line": f"LINESTRING({a['lon']} {a['lat']},{b['lon']} {b['lat']})",
                    "tags": json.dumps(
                        {**tags, "osm_version": way["version"], "observed_at": way["timestamp"]}
                    ),
                }
            )
    return result, dict(diagnostics)


def import_graph(session: Session, manifest: WalkManifest, doc: dict[str, Any]) -> WalkGraphView:
    dataset = GeoData(session).dataset(manifest.slug)
    bounds = Bounds.model_validate(dataset.bbox)
    if city_key(dataset.city) != city_key(manifest.city) or not (
        bounds.contains(manifest.bbox.west, manifest.bbox.south)
        and bounds.contains(manifest.bbox.east, manifest.bbox.north)
    ):
        raise GeoImportError("Road coverage must be inside the matching POI dataset")
    session.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": "walk:" + manifest.slug},
    )
    runtime = str(session.scalar(sa.text("SELECT postgis_full_version()")))
    crs = (32600 if manifest.bbox.south >= 0 else 32700) + int((manifest.bbox.west + 180) / 6) + 1
    version = digest(
        {
            "data": manifest.sha256,
            "bbox": manifest.bbox.model_dump(),
            "build": BUILD_VERSION,
            "runtime": runtime,
            "crs": crs,
        }
    )
    existing = session.scalar(
        sa.select(WalkGraphRecord).where(
            WalkGraphRecord.slug == manifest.slug, WalkGraphRecord.graph_version == version
        )
    )
    active = session.scalar(
        sa.select(WalkGraphRecord).where(
            WalkGraphRecord.slug == manifest.slug, WalkGraphRecord.active
        )
    )
    if (
        active
        and WalkGraphView.model_validate(active.document).manifest.osm_base > manifest.osm_base
    ):
        raise GeoImportError("Older graph cannot replace the active graph")
    if existing:
        return WalkGraphView.model_validate(existing.document)
    edges, diagnostics = segments(manifest, doc)
    if not edges or len(edges) > 200000:
        raise GeoImportError("Empty or oversized walking graph rejected")
    parents: dict[int, int] = {}

    def root(n: int) -> int:
        parents.setdefault(n, n)
        while parents[n] != n:
            parents[n] = parents[parents[n]]
            n = parents[n]
        return n

    for edge in edges:
        parents[root(edge["u"])] = root(edge["v"])
    components = len({root(n) for n in parents})
    sizes = Counter(root(n) for n in parents)
    largest = max(sizes.values())
    for edge in edges:
        attributes = json.loads(edge["tags"])
        attributes["component_nodes"] = sizes[root(edge["u"])]
        attributes["on_largest_component"] = sizes[root(edge["u"])] == largest
        edge["tags"] = json.dumps(attributes)
    graph_id = uuid5(NAMESPACE_URL, manifest.slug + ":" + version)
    view = WalkGraphView(
        id=graph_id,
        manifest=manifest,
        graph_version=version,
        build_version=BUILD_VERSION,
        spatial_runtime=runtime,
        metric_crs=crs,
        edge_count=len(edges),
        node_count=len(parents),
        component_count=components,
        diagnostics=diagnostics,
        imported_at=datetime.now(UTC),
    )
    if active:
        active.active = False
        session.flush()
    session.add(
        WalkGraphRecord(
            id=graph_id,
            slug=manifest.slug,
            graph_version=version,
            active=True,
            document=view.model_dump(mode="json"),
        )
    )
    session.flush()
    statement = sa.text("""INSERT INTO walk_edges
    (graph_id,edge_id,way_id,u,v,forward,backward,length_m,geom,tags)
    SELECT :graph_id,:edge_id,:way_id,:u,:v,:forward,:backward,
    ST_Length(g::geography),g,CAST(:tags AS jsonb)
    FROM (SELECT ST_GeomFromText(:line,4326) g) t""")
    for offset in range(0, len(edges), 500):
        session.execute(
            statement, [{"graph_id": graph_id, **e} for e in edges[offset : offset + 500]]
        )
    session.execute(sa.text("ANALYZE walk_edges"))
    return view
