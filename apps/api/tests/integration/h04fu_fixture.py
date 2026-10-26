"""Bounded synthetic local-beta recovery fixture; never a working database.

Small: original H-04 relationships. Large: 200 owners, 40 extra turns each,
199 generated real PDFs, 20k authored POI and a 2500-node synthetic road grid.
No commercial values are measured; no Overpass/bank/LLM calls.
"""

import argparse
import json
import os
import re
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import psycopg
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.bank.matching import digest
from app.db.models import ConversationRecord, GeoDatasetRecord, MessageRecord, ProfileRevisionRecord
from app.domain.enums import MessageRole
from app.geo.schemas import Bounds
from app.geo.walk_import import import_graph
from app.geo.walk_schemas import WalkManifest
from app.limits.config import load

from .support import migrate
from .test_leads import action, decision
from .test_populated_upgrade import add_report, api, fingerprints, populate, verify_api
from .test_reports import setup


def large(engine: sa.Engine) -> None:
    now = datetime.now(UTC)
    # Create valid user profiles/reports with existing API services. History bulk
    # writes are fixture-only, equivalent version/role/revision shapes, no inference.
    with api(engine) as client:
        for index in range(198):
            url, headers, body = setup(client)
            owner = UUID(url.split("/")[-1])
            with Session(engine) as db, db.begin():
                record = db.get(ConversationRecord, owner)
                assert record is not None
                snapshot = body["finance"]["request"]["profile"]
                for version in range(3, 43):
                    text = f"Синтетическая история: owner={index}, turn={version}; "
                    for role in (MessageRole.USER, MessageRole.ASSISTANT):
                        db.add(
                            MessageRecord(
                                conversation_id=owner,
                                version=version,
                                role=role,
                                content=text + digest([index, version, role]) * 8,
                                created_at=now,
                            )
                        )
                    db.add(
                        ProfileRevisionRecord(
                            conversation_id=owner,
                            version=version,
                            source="message",
                            profile_snapshot=snapshot,
                            created_at=now,
                        )
                    )
                record.version = 42
            body["expected_version"] = 42
            response = client.post(url + "/reports", headers=headers, json=body)
            assert response.status_code == 201, response.text
            if index < 50:
                assert decision(client, url, headers, "demo_lead").status_code == 200
                catalogue = client.get("/api/v1/bank-products").json()
                request = {
                    "expected_profile_version": 42,
                    "catalogue_fingerprint": catalogue["fingerprint"],
                    "product_ids": ["vtb-rko"],
                    "fields": {"city": "Казань", "category": "кофейня"},
                }
                response = client.post(url + "/leads/drafts", headers=headers, json=request)
                assert response.status_code == 201, response.text
                draft = response.json()
                endpoint = url + "/leads/drafts/" + draft["id"]
                assert (
                    client.post(
                        endpoint + "/confirm", headers=headers, json=action(draft)
                    ).status_code
                    == 200
                )
                response = client.post(
                    endpoint + "/submit",
                    headers=headers,
                    json={**action(draft), "idempotency_key": str(uuid4())},
                )
                assert response.status_code == 200, response.text
                assert decision(client, url, headers, "demo_lead", "withdraw", 1).status_code == 200
    with engine.begin() as connection:
        dataset: UUID = connection.execute(
            sa.text("SELECT id FROM geo_datasets WHERE city='Synthetic test'")
        ).scalar_one()
        connection.execute(
            sa.text("""
            INSERT INTO geo_pois(dataset_id,osm_type,osm_id,osm_version,observed_at,
                                 name,categories,tags,representation,geom)
            SELECT :dataset,'node',10000+i,1,:now,'Synthetic recovery POI '||i,
                   ARRAY['amenity:cafe'],'{"fixture":"synthetic-h04fu-v1"}'::jsonb,'osm_node',
                   ST_SetSRID(ST_MakePoint(49.101+(i%190)*0.0002,55.761+(i/190)*0.0002),4326)
            FROM generate_series(1,20000) i
        """),
            {"dataset": dataset, "now": now},
        )
        connection.execute(
            sa.text(
                "UPDATE geo_datasets SET poi_count=20002,district_count=1, "
                "diagnostics=jsonb_build_object('synthetic_fixture',20000) WHERE id=:id"
            ),
            {"id": dataset},
        )
    with Session(engine) as db, db.begin():
        dataset_row = db.scalar(sa.select(GeoDatasetRecord).where(GeoDatasetRecord.id == dataset))
        assert dataset_row is not None
        elements = [
            {
                "type": "node",
                "id": y * 50 + x + 1,
                "lon": 49.101 + x * 0.0006,
                "lat": 55.761 + y * 0.0006,
            }
            for y in range(50)
            for x in range(50)
        ]
        for i in range(50):
            elements += [
                {
                    "type": "way",
                    "id": 10000 + i,
                    "nodes": [i * 50 + x + 1 for x in range(50)],
                    "tags": {"highway": "footway"},
                },
                {
                    "type": "way",
                    "id": 20000 + i,
                    "nodes": [y * 50 + i + 1 for y in range(50)],
                    "tags": {"highway": "footway"},
                },
            ]
        for element in elements:
            element.update(version=1, timestamp=now.isoformat())
        document = {"osm3s": {"timestamp_osm_base": now.isoformat()}, "elements": elements}
        manifest = WalkManifest(
            slug=dataset_row.slug,
            city="Synthetic test",
            bbox=Bounds.model_validate(dataset_row.bbox),
            source_url="https://example.invalid/synthetic-recovery-grid",
            query="authored synthetic grid",
            sha256=digest(document),
            source_sha256=digest(document),
            osm_base=now,
            fetched_at=now,
        )
        import_graph(db, manifest, document)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["seed", "verify"])
    parser.add_argument("--database", required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--size", choices=["small", "large"], default="small")
    args = parser.parse_args()
    if not re.fullmatch(r"f00_restore_[a-z0-9_]{1,48}", args.database):
        parser.error("Only isolated restore-named fixture databases")
    os.environ["LLM_PROVIDER"] = "stub"
    if args.operation == "seed":
        os.environ["BA_API_LIMITS_JSON"] = json.dumps(
            {"requests_per_window": 1000000, "heavy_per_window": 1000000}
        )
    engine = sa.create_engine("postgresql+psycopg://", connect_args={"dbname": args.database})
    state_path = args.private / (args.size + "-state.json")
    try:
        with (
            patch("app.leads.service.today", lambda: date(2026, 10, 23)),
            patch("app.limits.config.POLICY", load()),
        ):
            if args.operation == "seed":
                assert not state_path.exists()
                with psycopg.connect(dbname=args.database) as db:
                    assert db.execute(
                        "SELECT count(*) FROM pg_tables WHERE schemaname='public' "
                        "AND tablename <> 'spatial_ref_sys'"
                    ).fetchone() == (0,)
                migrate(args.database, "upgrade", "head")
                state = populate(engine)
                with api(engine) as client:
                    datasets = client.get("/api/v1/geo/datasets").json()
                    geo_version = next(
                        d["data_version"] for d in datasets if d["slug"] == "kazan-fixture"
                    )
                    ranking = {
                        "candidates": {
                            "profile": state["profile"]["profile"],
                            "data_version": geo_version,
                            "limit": 3,
                            "cell_size_m": 250,
                            "min_separation_m": 0,
                        },
                        "scoring": {
                            "radius_m": 50,
                            "weights": {
                                "transit": 0,
                                "infrastructure": 0,
                                "complementary": 0,
                                "competitors": 1,
                            },
                            "competitor_mode": "cluster",
                        },
                    }
                    ranked = client.post("/api/v1/geo/kazan-fixture/rankings", json=ranking)
                    assert ranked.status_code == 200, ranked.text
                    zones = ranked.json()
                    assert zones["candidates"]["features"]
                    state["report_body"]["geo"] = {
                        "dataset": "kazan-fixture",
                        "request": ranking,
                        "fingerprint": zones["request_fingerprint"],
                    }
                    state["report_body"]["selected_zone"] = zones["candidates"]["features"][0]["id"]
                add_report(engine, state)
                if args.size == "large":
                    large(engine)
                state["fingerprints"] = fingerprints(args.database)
                with state_path.open("x", encoding="utf8") as file:
                    state_path.chmod(0o600)
                    json.dump(state, file, ensure_ascii=False)
            else:
                state = json.loads(state_path.read_text(encoding="utf8"))
            migrate(args.database, "check")
            assert fingerprints(args.database) == state["fingerprints"]
            verify_api(engine, state)
            with psycopg.connect(dbname=args.database) as db:
                size = db.execute("SELECT pg_database_size(current_database())").fetchall()[0][0]
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "fixture": args.size,
                        "database_bytes": size,
                        "tables": state["fingerprints"],
                    }
                )
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
