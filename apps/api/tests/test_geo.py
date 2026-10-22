import io
import json
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest
from pydantic import ValidationError

from app.geo.provider import (
    GeoImportError,
    OverpassProvider,
    build_query,
    load_snapshot,
    parse_document,
    save_snapshot,
)
from app.geo.schemas import Bounds, SpatialQuery

FIXTURE = Path(__file__).parent / "integration/fixtures/kazan.raw.json"


@pytest.mark.parametrize("bbox", ["1,2,0,3", "0,0,2,2", "nan,0,1,1", "0,0,1", "180,0,181,1"])
def test_bad_bounds(bbox: str) -> None:
    with pytest.raises(ValueError):
        Bounds.parse(bbox)


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"longitude": 49, "latitude": 55},
        {"radius_m": 100},
        {"longitude": 49, "latitude": 55, "radius_m": 10001},
        {"district_id": -1},
        {"district_id": 1, "limit": 501},
        {"district_id": 1, "offset": 10001},
        {"district_id": 1, "longitude": float("inf")},
    ],
)
def test_query_limits(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SpatialQuery.model_validate(values)


def test_bbox_order_and_real_snapshot() -> None:
    manifest, document = load_snapshot(FIXTURE)
    assert "(55.785,49.115,55.79,49.12)" in build_query(manifest.bbox)
    assert document["osm3s"]["timestamp_osm_base"]
    assert len(document["elements"]) == 159
    assert manifest.origin == "open_data"


def test_cache_replay_and_tamper_rejected(tmp_path: Path) -> None:
    manifest, _ = load_snapshot(FIXTURE)
    path = tmp_path / "copy.raw.json"
    saved = save_snapshot(
        FIXTURE.read_bytes(),
        path,
        slug="copy",
        city="Kazan",
        bbox=manifest.bbox,
        endpoint=manifest.source_url,
    )
    assert load_snapshot(path)[0] == saved
    assert saved.normalization == "poi_minimal_v1" and saved.source_sha256
    assert all(
        "uid" not in item and "user" not in item for item in load_snapshot(path)[1]["elements"]
    )
    with pytest.raises(GeoImportError, match="already exist"):
        save_snapshot(
            FIXTURE.read_bytes(),
            path,
            slug="copy",
            city="Kazan",
            bbox=manifest.bbox,
            endpoint=manifest.source_url,
        )
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(GeoImportError, match="checksum"):
        load_snapshot(path)


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[]",
        b"{}",
        b'{"elements": []}',
        b'{"elements": [], "remark":"runtime timeout"}',
    ],
)
def test_partial_or_invalid_source_rejected(raw: bytes) -> None:
    with pytest.raises(GeoImportError):
        parse_document(raw)


def test_provider_does_not_hide_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        def open(self, *args: Any, **kwargs: Any) -> io.BytesIO:
            raise URLError("private proxy details")

    monkeypatch.setattr("app.geo.provider.build_opener", lambda *args: Broken())
    with pytest.raises(GeoImportError, match="unavailable") as caught:
        OverpassProvider().fetch(Bounds.parse("49.1,55.7,49.2,55.8"))
    assert "private" not in str(caught.value)


def test_provider_sends_only_bounded_selected_query(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, _ = load_snapshot(FIXTURE)

    class Source:
        def open(self, request: Any, timeout: int) -> io.BytesIO:
            assert request.data.decode() == build_query(manifest.bbox)
            assert timeout == 120
            return io.BytesIO(FIXTURE.read_bytes())

    monkeypatch.setattr("app.geo.provider.build_opener", lambda *args: Source())
    assert json.loads(OverpassProvider().fetch(manifest.bbox))["elements"]
