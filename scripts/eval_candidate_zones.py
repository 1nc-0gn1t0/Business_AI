"""Opt-in, read-only evaluation against an imported real OSM dataset (no LLM needed)."""

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--slug", default="kazan-centre")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = {
        "profile": {
            # Technical IDs for a supplied snapshot, not a lookup of a stored conversation.
            "id": "00000000-0000-0000-0000-000000000007",
            "conversation_id": "00000000-0000-0000-0000-000000000007",
            "city": "Казань",
            "category": "кофейня",
            "budget": "2000000",
            "preferences": {"format": "навынос"},
        },
        "cell_size_m": 500,
        "min_separation_m": 1000,
        "limit": 5,
    }
    durations = []

    def run(body: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        req = Request(
            args.api.rstrip("/") + f"/api/v1/geo/{args.slug}/candidates",
            data=json.dumps(body, ensure_ascii=False).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=30) as response:
            data: dict[str, Any] = json.load(response)
        durations.append(round(time.perf_counter() - started, 3))
        return data

    first = run(request)
    pinned = request | {"data_version": first["dataset"]["data_version"]}
    second = run(pinned)
    assert len(first["features"]) == 5, first
    assert first["features"] == second["features"], (
        "Pinned replay changed candidate output"
    )
    assert len({f["id"] for f in first["features"]}) == 5
    report = {
        "request": pinned,
        "response": first,
        "http_seconds": durations,
        "checks": {"five_zones": True, "unique_ids": True, "pinned_replay": True},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": first["status"],
                "eligible_count": first["eligible_count"],
                "http_seconds": durations,
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    for feature in first["features"]:
        props = feature["properties"]
        print(
            json.dumps(
                {
                    "cell": [props["grid_i"], props["grid_j"]],
                    "point": props["representative_point"]["coordinates"],
                    "area_m2": round(props["area_m2"], 1),
                    "anchor": props["anchor"]["id"],
                    "name": props["anchor"]["properties"]["name"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
