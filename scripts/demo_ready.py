"""Read-only local demo preflight. Never imports data or calls Overpass/bank/LLM inference."""

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--ollama", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/demo-manifest.json")
    )
    parser.add_argument("--require-demo-data", action="store_true")
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Opt-in protected bounded bundle; token from environment only",
    )
    args = parser.parse_args()
    for url in (args.api, args.ollama):
        parsed = urlsplit(url)
        if (
            parsed.hostname not in {"localhost", "127.0.0.1"}
            or parsed.username
            or parsed.password
        ):
            parser.error("Preflight only supports local endpoints without credentials")
    pins = json.loads(args.manifest.read_text(encoding="utf8"))
    checks = []

    def fetch(base, path, headers=None):
        request = Request(base.rstrip("/") + path, headers=headers or {})
        with urlopen(request, timeout=10) as reply:
            raw = reply.read(1048577)
            if len(raw) > 1048576:
                raise ValueError("Preflight response too large")
            return json.loads(raw)

    def check(name, operation):
        try:
            passed = bool(operation())
            checks.append({"id": name, "status": "PASS" if passed else "FAIL"})
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
        ):
            checks.append(
                {
                    "id": name,
                    "status": "FAIL",
                    "reason": "unavailable_or_invalid_response",
                }
            )

    check("postgres_postgis", lambda: fetch(args.api, "/healthz")["database"] == "ok")
    if args.diagnostics:
        check("schema_ready", lambda: fetch(args.api, "/readyz")["status"] == "ok")
        check(
            "protected_diagnostics",
            lambda: (
                fetch(
                    args.api,
                    "/api/v1/diagnostics",
                    {"X-Diagnostics-Token": os.getenv("BA_DIAGNOSTICS_TOKEN", "")},
                )["version"]
                == 1
            ),
        )
    check(
        "pinned_osm",
        lambda: any(
            d["slug"] == pins["dataset_slug"]
            and d["data_version"] == pins["osm_data_version"]
            and not d["stale"]
            for d in fetch(args.api, "/api/v1/geo/datasets")
        ),
    )
    check(
        "pinned_walking_graph",
        lambda: (
            fetch(args.api, "/api/v1/geo/" + pins["dataset_slug"] + "/walking-graph")[
                "graph_version"
            ]
            == pins["graph_version"]
        ),
    )
    check(
        "installed_qwen",
        lambda: any(
            m["name"] == pins["model"] and m["digest"] == pins["model_digest"]
            for m in fetch(args.ollama, "/api/tags")["models"]
        ),
    )

    def demo_catalogue():
        catalogue = fetch(args.api, "/api/v1/bank-products")
        return bool(catalogue["products"]) and all(
            p["product"]["mode"] == "demonstration"
            and p["availability"] == "demonstration_only"
            for p in catalogue["products"]
        )

    check("demo_bank_catalogue", demo_catalogue)
    if args.require_demo_data:
        check(
            "explicit_demo_enabled",
            lambda: (
                fetch(args.api, "/api/v1/data-providers/policy")["demo_enabled"] is True
            ),
        )
        check(
            "pinned_synthetic",
            lambda: any(
                d["data_version"] == pins["synthetic_data_version"]
                for d in fetch(
                    args.api, "/api/v1/data-providers/synthetic/datasets?mode=demo"
                )
            ),
        )
    print(
        json.dumps(
            {
                "manifest_version": pins["version"],
                "checks": checks,
                "limitations": "Installed model is not proof of API extraction_mode; verify the UI says local Qwen. No inference performed.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    raise SystemExit(0 if all(c["status"] == "PASS" for c in checks) else 1)


if __name__ == "__main__":
    main()
