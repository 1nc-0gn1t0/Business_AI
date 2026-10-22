"""Read-only BA-008 evaluation on the local real OSM dataset. Does not call an LLM."""

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    example = (
        Path(__file__).resolve().parents[1] / "docs/examples/BA-007-kazan-coffee.json"
    )
    archived = json.loads(example.read_text(encoding="utf-8"))
    original = archived["request"]
    # Caller-supplied scenario snapshot; no stored conversation is read or confirmed.
    original["profile"]["confirmation_state"] = "confirmed"
    results: dict[str, Any] = {}

    def run(name: str, request: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        req = Request(
            args.api.rstrip("/") + "/api/v1/geo/kazan-centre/rankings",
            data=json.dumps(request, ensure_ascii=False).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=30) as response:
            data: dict[str, Any] = json.load(response)
        results[name] = {
            "request": request,
            "response": data,
            "http_seconds": round(time.perf_counter() - started, 3),
        }
        return data

    edge = run("original_BA007_zones", {"candidates": original})
    assert {f["id"] for f in edge["candidates"]["features"]} == {
        f["id"] for f in archived["response"]["features"]
    }
    assert edge["status"] == "insufficient_data", edge
    assert all(e["score"] is None for e in edge["evaluations"])

    # Explicitly change the BA-007 search region, not the observation radius or coverage rules.
    interior = original | {
        "search_bbox": {"west": 49.065, "south": 55.71, "east": 49.235, "north": 55.84}
    }
    request = {"candidates": interior}
    first = run("covered_BA007_zones", request)
    repeat = run("pinned_replay", request | {"scoring": first["policy"]["config"]})
    assert first["status"] == "ok" and len(first["comparison_ids"]) == 5, first
    assert first["request_fingerprint"] == repeat["request_fingerprint"]
    assert [
        (e["candidate_id"], e["score"], e["rank"], e["raw"], e["components"])
        for e in first["evaluations"]
    ] == [
        (e["candidate_id"], e["score"], e["rank"], e["raw"], e["components"])
        for e in repeat["evaluations"]
    ]
    transport = run(
        "explicit_transit_weight_only",
        request
        | {
            "scoring": {
                "weights": {
                    "transit": 1,
                    "infrastructure": 0,
                    "complementary": 0,
                    "competitors": 0,
                }
            }
        },
    )
    assert first["policy"]["fingerprint"] != transport["policy"]["fingerprint"]
    assert [(e["candidate_id"], e["score"]) for e in first["evaluations"]] != [
        (e["candidate_id"], e["score"]) for e in transport["evaluations"]
    ]
    results["original_BA007_zones"]["response"] = {
        "status": edge["status"],
        "reasons": edge["reasons"],
        "source_geometry_archive": "BA-007-kazan-coffee.json",
        "data_version": edge["candidates"]["dataset"]["data_version"],
        "evaluations": [
            {key: e[key] for key in ("candidate_id", "score", "rank", "status")}
            | {
                "coverage_margin_m": e["raw"]["coverage_margin_m"],
                "fully_covered": e["raw"]["fully_covered"],
            }
            for e in edge["evaluations"]
        ],
    }
    results["explicit_transit_weight_only"]["response"] = {
        "status": transport["status"],
        "policy": transport["policy"],
        "request_fingerprint": transport["request_fingerprint"],
        "evaluations": [
            {key: e[key] for key in ("candidate_id", "rank", "score", "components")}
            for e in transport["evaluations"]
        ],
    }
    # Replay output is redundant; its assertions have checked all raw/component/score values.
    results["pinned_replay"] = {
        "checks": "same_fingerprint_raw_components_scores_ranks"
    }
    report = {
        "source": "OpenStreetMap via Overpass API / ODbL-1.0",
        "checks": {
            "original_ids_preserved": True,
            "edge_scores_withheld": True,
            "five_covered_zones_ranked": True,
            "pinned_replay": True,
        },
        "scenarios": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                name: {
                    "status": value["response"]["status"],
                    "http_seconds": value["http_seconds"],
                }
                for name, value in results.items()
                if "response" in value
            },
            ensure_ascii=False,
        )
    )
    features = {f["id"]: f for f in first["candidates"]["features"]}
    for e in first["evaluations"]:
        feature = features[e["candidate_id"]]
        print(
            json.dumps(
                {
                    "rank": e["rank"],
                    "score": e["score"],
                    "cell": [
                        feature["properties"]["grid_i"],
                        feature["properties"]["grid_j"],
                    ],
                    "point": feature["properties"]["representative_point"][
                        "coordinates"
                    ],
                    "raw": {
                        key: e["raw"][key]
                        for key in (
                            "nearest_transit_m",
                            "transit_count",
                            "competitor_count",
                            "infrastructure_count",
                            "complementary_count",
                        )
                    },
                    "components": {
                        c["criterion"]: c["normalized"] for c in e["components"]
                    },
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
