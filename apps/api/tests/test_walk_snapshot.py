import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.geo.provider import GeoImportError
from app.geo.schemas import Bounds
from app.geo.walk_import import load, query
from app.geo.walk_schemas import WalkManifest


def test_manifest_checks_hash_query_time_and_normalization(tmp_path: Path) -> None:
    doc = {"elements": [], "osm3s": {"timestamp_osm_base": "2020-01-01T00:00:00Z"}}
    raw = json.dumps(doc).encode()
    bbox = Bounds(west=49.10, south=55.76, east=49.14, north=55.80)
    manifest = WalkManifest(
        slug="test",
        city="Test",
        bbox=bbox,
        source_url="https://example.invalid/test",
        query=query(bbox),
        sha256=hashlib.sha256(raw).hexdigest(),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        osm_base=datetime(2020, 1, 1, tzinfo=UTC),
        fetched_at=datetime(2020, 1, 2, tzinfo=UTC),
    )
    path = tmp_path / "test.raw.json"
    path.write_bytes(raw)
    path.with_suffix(".manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    assert load(path)[0] == manifest
    path.write_bytes(raw + b" ")
    with pytest.raises(GeoImportError):
        load(path)
    path.write_bytes(raw)
    path.with_suffix(".manifest.json").write_text(
        manifest.model_copy(update={"query": "forged"}).model_dump_json(), encoding="utf-8"
    )
    with pytest.raises(GeoImportError):
        load(path)
