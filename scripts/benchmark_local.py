"""Small serial local benchmark, not a load test or production SLA. No LLM inference."""

import argparse
import json
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8016")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (
        urlsplit(args.api).hostname not in {"localhost", "127.0.0.1"}
        or urlsplit(args.api).port != 8016
    ):
        parser.error("Use the isolated local evaluation API on port 8016")

    def request(path, body=None, token=None, method=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Conversation-Token"] = token
        req = Request(
            args.api + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method=method or ("POST" if body is not None else "GET"),
        )
        try:
            with urlopen(req, timeout=60) as reply:
                return json.load(reply)
        except HTTPError as error:
            detail = json.load(error).get("detail")
            raise RuntimeError(f"Benchmark HTTP {error.code}: {detail}") from None

    finance = json.loads(
        Path("docs/examples/BA-009-coffee-result.json").read_text(encoding="utf8")
    )["response"]["request_snapshot"]
    ranking = json.loads(
        Path("docs/examples/BA-008-kazan-coffee.json").read_text(encoding="utf8")
    )["scenarios"]["covered_BA007_zones"]["request"]
    created = request("/api/v1/conversations", method="POST")
    token, path = created["access_token"], "/api/v1/conversations/" + created["id"]
    request(
        path + "/consents/assistant",
        {
            "expected_revision": 0,
            "text_version": "assistant-demo-v1",
            "decision": "grant",
        },
        token,
        "PUT",
    )
    patch = {
        k: v
        for k, v in finance["profile"].items()
        if k in {"city", "category", "budget", "funding", "preferences"}
    }
    patch["funding"] = "own_funds"
    patch["preferences"] = {"format": "навынос"}
    request(path + "/profile", {"expected_version": 0, "patch": patch}, token, "PATCH")
    profile = request(path + "/profile/confirm", {"expected_version": 1}, token)[
        "profile"
    ]
    finance["profile"] = profile
    finance["selected_zone"] = None
    financial = request("/api/v1/finance/calculate", finance)
    report = {
        "expected_version": 2,
        "finance": {
            "request": finance,
            "fingerprint": financial["request_fingerprint"],
        },
    }
    cases = [
        ("health", "/healthz", None, None),
        ("ranking_5_zones", "/api/v1/geo/kazan-centre/rankings", ranking, None),
        (
            "catchment_600m",
            "/api/v1/geo/kazan-centre/catchment",
            {
                "longitude": 49.119,
                "latitude": 55.788,
                "distance_m": 600,
                "max_snap_m": 30,
            },
            None,
        ),
        ("finance_3_scenarios", "/api/v1/finance/calculate", finance, None),
        ("report_finance_pdf_json", path + "/reports", report, token),
    ]
    rows = []
    for name, url, body, credential in cases:
        request(url, body, credential)  # one explicit warm-up, excluded
        elapsed, fingerprints = [], []
        for _ in range(5):
            start = time.perf_counter()
            data = request(url, body, credential)
            elapsed.append(round(1000 * (time.perf_counter() - start), 3))
            if data.get("request_fingerprint"):
                fingerprints.append(data["request_fingerprint"])
        assert len(set(fingerprints)) <= 1
        rows.append(
            {
                "id": name,
                "n": 5,
                "unit": "ms",
                "samples": elapsed,
                "median": statistics.median(elapsed),
                "p95_nearest_rank": sorted(elapsed)[math.ceil(0.95 * len(elapsed)) - 1],
                "fingerprint_stable": bool(fingerprints) if fingerprints else None,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "checked_at": datetime.now(UTC).isoformat(),
                "method": "serial HTTP, 1 excluded warm-up then 5 samples per endpoint; no concurrent LLM or load test; report is finance-only, 6 local snapshots created",
                "results": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf8",
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
