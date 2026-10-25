"""Opt-in BA-016 evaluation through a separately deployed Business AI API.

Fictional inputs only. Credentials and conversation IDs never enter results.
Each completed dialogue is checkpointed, so an interrupted run can resume.
"""

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8016")
    parser.add_argument(
        "--cases", type=Path, default=Path("tests/evaluation/qwen-v2.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-isolated-local-evaluation", action="store_true", required=True
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--case-id", action="append", default=[])
    args = parser.parse_args()
    endpoint = urlsplit(args.api)
    if endpoint.hostname not in {"localhost", "127.0.0.1"} or endpoint.port != 8016:
        parser.error("Use the isolated local evaluation API on port 8016")
    suite = json.loads(args.cases.read_text(encoding="utf-8"))
    digest = hashlib.sha256(args.cases.read_bytes()).hexdigest()
    if not 1 <= args.repeat <= 5:
        parser.error("repeat must be between 1 and 5")
    if set(args.case_id) - {case["id"] for case in suite["dialogues"]}:
        parser.error("Unknown case ID")
    report = (
        json.loads(args.output.read_text(encoding="utf-8"))
        if args.output.exists()
        else {
            "suite_version": suite["version"],
            "corpus_sha256": digest,
            "started_at": datetime.now(UTC).isoformat(),
            "provider": "real Ollama through isolated Business AI HTTP API",
            "model": "qwen3:4b-instruct-2507-q4_K_M",
            "results": [],
        }
    )
    if (
        report["suite_version"] != suite["version"]
        or report.get("corpus_sha256") != digest
    ):
        parser.error("Output belongs to a different corpus; use a new output file")

    for attempt in range(15):
        try:
            with urlopen(args.api + "/healthz", timeout=2) as reply:
                if json.load(reply).get("database") == "ok":
                    break
        except (URLError, OSError, HTTPException, ValueError):
            pass
        time.sleep(1)
    else:
        parser.error("Isolated API is not ready; no dialogue requests sent")

    def request(path, method="GET", body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Conversation-Token"] = token
        req = Request(
            args.api + path,
            data=json.dumps(body, ensure_ascii=False).encode()
            if body is not None
            else None,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(req, timeout=190) as reply:
                return reply.status, json.load(reply)
        except HTTPError as error:
            return error.code, json.load(error)

    def equal(actual, expected, key):
        if isinstance(expected, list):
            return any(equal(actual, value, key) for value in expected)
        if key == "budget" and actual is not None and expected is not None:
            return Decimal(str(actual)) == Decimal(str(expected))
        return actual == expected

    for repetition in range(args.repeat):
        for case in suite["dialogues"]:
            if args.case_id and case["id"] not in args.case_id:
                continue
            run_id = f"{case['id']}/r{repetition + 1}"
            if any(row["id"] == run_id for row in report["results"]):
                continue
            status, view = request("/api/v1/conversations", "POST")
            assert status == 201
            token = view["access_token"]
            path = "/api/v1/conversations/" + view["id"]
            status, consents = request(path + "/consents", token=token)
            assert status == 200
            version = next(
                t["version"] for t in consents["texts"] if t["purpose"] == "assistant"
            )
            status, _ = request(
                path + "/consents/assistant",
                "PUT",
                {
                    "expected_revision": 0,
                    "text_version": version,
                    "decision": "grant",
                },
                token,
            )
            assert status == 200
            steps = []
            for index, step in enumerate(case["steps"]):
                started = time.monotonic()
                status, body = request(
                    path + "/messages",
                    "POST",
                    {
                        "content": step["message"],
                        "expected_version": view["version"],
                    },
                    token,
                )
                seconds = round(time.monotonic() - started, 3)
                checks = {"http_200": status == 200}
                profile = body.get("profile", {})
                checks["real_ollama"] = body.get("extraction_mode") == "ollama"
                for key, value in step["expected"].items():
                    actual = profile
                    for part in key.split("."):
                        actual = actual.get(part) if isinstance(actual, dict) else None
                    checks[key] = equal(actual, value, key)
                if status == 200:
                    view = body
                    _, stored = request(path, token=token)
                    checks["persisted"] = stored == body
                    _, history = request(path + "/history", token=token)
                    _, messages = request(path + "/messages", token=token)
                    checks["history"] = (
                        len(history) == view["version"] + 1
                        and len(messages) == 2 * view["version"] + 1
                    )
                steps.append(
                    {
                        "step": index + 1,
                        "input": step["message"],
                        "expected": step["expected"],
                        "status": status,
                        "seconds": seconds,
                        "checks": checks,
                        "passed": all(checks.values()),
                        "profile": {
                            key: profile.get(key)
                            for key in (
                                "city",
                                "category",
                                "budget",
                                "funding",
                                "preferences",
                                "confirmation_state",
                            )
                        },
                        "assistant_message": body.get("assistant_message"),
                        "error_code": body.get("detail") if status != 200 else None,
                    }
                )
                print(
                    f"{run_id} step={index + 1} status={status} seconds={seconds} failed={[k for k, v in checks.items() if not v]}",
                    flush=True,
                )
            report["results"].append(
                {
                    "id": run_id,
                    "category": case["category"],
                    "steps": steps,
                    "passed": all(s["passed"] for s in steps),
                }
            )
            report["updated_at"] = datetime.now(UTC).isoformat()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            pending = args.output.with_suffix(".pending")
            pending.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            pending.replace(args.output)
    if not all(r["passed"] for r in report["results"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
