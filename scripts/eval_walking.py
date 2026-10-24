"""Real local PostGIS HTTP verification; no synthetic inputs substituted for OSM results."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def post(suffix: str, body: object) -> tuple[dict, float]:
        start = perf_counter()
        req = Request(
            args.api + "/api/v1/geo/kazan-centre/" + suffix,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=60) as response:
            result = json.load(response)
        return result, round((perf_counter() - start) * 1000, 3)

    cases = []
    for lon, lat in ((49.119, 55.788), (49.132, 55.789), (49.155, 55.788)):
        body = {"longitude": lon, "latitude": lat, "distance_m": 600, "max_snap_m": 30}
        data, elapsed = post("catchment", body)
        data["network"]["features"] = data["network"]["features"][:20]
        data["pois"]["features"] = data["pois"]["features"][:10]
        cases.append(
            {"request": body, "http_elapsed_ms": elapsed, "response_excerpt": data}
        )
    profile = {
        "conversation_id": "00000000-0000-0000-0000-000000000013",
        "city": "Казань",
        "category": "кофейня",
        "budget": "2000000",
        "funding": "own_funds",
        "preferences": {"format": "навынос"},
        "confirmation_state": "confirmed",
    }
    ranking_request = {
        "ranking": {
            "candidates": {
                "profile": profile,
                "search_bbox": {
                    "west": 49.094,
                    "south": 55.770,
                    "east": 49.165,
                    "north": 55.810,
                },
                "cell_size_m": 500,
                "min_separation_m": 1000,
                "limit": 5,
            },
            "scoring": {"radius_m": 500},
        },
        "max_snap_m": 30,
    }
    ranking, elapsed = post("walking-rankings", ranking_request)
    rows = []
    for f in ranking["baseline"]["candidates"]["features"]:
        key = f["id"]
        a = next(
            e for e in ranking["baseline"]["evaluations"] if e["candidate_id"] == key
        )
        b = next(
            e for e in ranking["network"]["evaluations"] if e["candidate_id"] == key
        )
        c = ranking["catchments"][key]
        rows.append(
            {
                "id": key,
                "point": f["properties"]["representative_point"]["coordinates"],
                "straight": a,
                "network": b,
                "catchment_summary": {
                    k: c[k]
                    for k in (
                        "status",
                        "reasons",
                        "source_snap_m",
                        "source_component_nodes",
                        "on_largest_component",
                        "straight_line_poi_count",
                        "reachable_poi_count",
                        "unsnapped_poi_count",
                        "runtime_ms",
                    )
                },
            }
        )
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "source": "Real local PostGIS API",
        "excerpt_notice": "Geometry limited to first 20 segments, POI to first 10; counts are from full responses. Re-run saved requests to retrieve complete GeoJSON.",
        "cases": cases,
        "ranking": {
            "request": ranking_request,
            "http_elapsed_ms": elapsed,
            "network_status": ranking["network"]["status"],
            "rows": rows,
            "baseline_algorithm": ranking["baseline"]["algorithm_version"],
            "network_algorithm": ranking["network"]["algorithm_version"],
            "network_fingerprint": ranking["network"]["request_fingerprint"],
        },
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "points": [
                    {
                        "point": r["request"],
                        "count": r["response_excerpt"]["reachable_poi_count"],
                        "status": r["response_excerpt"]["status"],
                    }
                    for r in cases
                ],
                "ranking": [
                    {
                        "point": r["point"],
                        "straight": r["straight"]["score"],
                        "network": r["network"]["score"],
                        "component": r["catchment_summary"]["source_component_nodes"],
                    }
                    for r in rows
                ],
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
