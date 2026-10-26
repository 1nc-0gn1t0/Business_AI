"""Opt-in H-04-FU clean-project drill, synthetic credentials/data only.

Requires an operator-created private context and fixture-state file. Never starts,
stops or switches the regular Business AI Compose project. Does not clean up on
failure; the owning operator reviews the exact UUID project before removal.
"""

import argparse
import hashlib
import json
import secrets
import shutil
import socket
import time
import urllib.request
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import encrypted_backup as b


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(base, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    value = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(value, timeout=200) as response:
        return response.read()


def run(context, bundle):
    start = time.monotonic()
    phases = []

    def measure(label, operation):
        before = time.monotonic()
        result = operation()
        phases.append({"stage": label, "seconds": round(time.monotonic() - before, 3)})
        return result

    root = b.private(Path(context["private"]) / ("rehearsal-" + uuid4().hex))
    storage = b.private(root / "archives")
    project = "h04fu-recovery-" + uuid4().hex[:12]
    target = "f00_restore_fu_" + uuid4().hex
    api_port, web_port = port(), port()
    password = secrets.token_urlsafe(24)  # Disposable QA database credential only.
    images = {
        name: b.base.checked(
            ["docker", "image", "inspect", tag, "--format", "{{.Id}}"],
            stdout=b.subprocess.PIPE,
        )
        .stdout.decode()
        .strip()
        for name, tag in (
            ("api", "business-ai-migrate:latest"),
            ("db", "postgis/postgis:17-3.5"),
            ("web", "business-ai-web:latest"),
        )
    }
    compose = root / "compose.yaml"
    compose.write_text(
        f"""services:
  db:
    image: {images["db"]}
    environment:
      POSTGRES_DB: bootstrap
      POSTGRES_USER: business_ai
      POSTGRES_PASSWORD: '{password}'
    volumes: [data:/var/lib/postgresql/data]
    healthcheck:
      test: [CMD-SHELL, 'pg_isready -h 127.0.0.1 -U business_ai -d bootstrap']
      interval: 2s
      retries: 40
  api:
    image: {images["api"]}
    environment:
      PGHOST: db
      PGPORT: '5432'
      PGUSER: business_ai
      PGPASSWORD: '{password}'
      PGDATABASE: {target}
      LLM_PROVIDER: ollama
      OLLAMA_BASE_URL: http://host.docker.internal:11434
      OLLAMA_MODEL: qwen3:4b-instruct-2507-q4_K_M
    ports: ['127.0.0.1:{api_port}:8000']
    healthcheck:
      test: [CMD, python, -c, "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=5)"]
      interval: 2s
      retries: 40
  web:
    image: {images["web"]}
    ports: ['127.0.0.1:{web_port}:80']
    healthcheck:
      test: [CMD, wget, -q, --spider, http://127.0.0.1/healthz]
      interval: 2s
      retries: 40
volumes:
  data:
""",
        encoding="utf8",
    )
    config = {
        "root": str(storage),
        "age_binary": context["age_binary"],
        "project": project,
        "compose_files": [str(compose)],
    }
    phases.append(
        {
            "stage": "01_prepare_clean_project_and_cached_images",
            "seconds": round(time.monotonic() - start, 3),
        }
    )
    copied = storage / bundle.name
    measure("02_retrieve_local_encrypted_copy", lambda: shutil.copytree(bundle, copied))
    public = measure("03_ciphertext_checksums", lambda: b.manifest(copied))

    class Timed(b.Compose):
        def create(self, source, database):
            measure(
                "05_start_clean_PostgreSQL_PostGIS",
                lambda: b.base.checked(
                    [*self.prefix, "up", "-d", "--wait", "--wait-timeout", "120", "db"],
                    stdout=b.subprocess.PIPE,
                ),
            )
            super().create(source, database)

        def inspect(self, database):
            return measure(
                "07_08_schema_extensions_counts_fingerprints",
                lambda: super(Timed, self).inspect(database),
            )

    backend = Timed(config)
    recovered = b.recover(
        config,
        copied,
        Path(context["private"]) / "synthetic-keys/temporary-identity.txt",
        target,
        backend,
    )
    phases += [
        {
            "stage": "04_decrypt_authenticate_private_temporary_file",
            "seconds": recovered["authentication_seconds"],
        },
        {
            "stage": "06_createdb_pg_restore_including_stage05",
            "seconds": recovered["restore_seconds"],
        },
    ]
    measure(
        "08b_alembic_check",
        lambda: b.base.checked(
            [
                *backend.prefix,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "api",
                "alembic",
                "check",
            ],
            stdout=b.subprocess.PIPE,
        ),
    )
    measure(
        "09_start_backend_and_frontend_readiness",
        lambda: b.base.checked(
            [
                *backend.prefix,
                "up",
                "-d",
                "--no-deps",
                "--wait",
                "--wait-timeout",
                "120",
                "api",
                "web",
            ],
            stdout=b.subprocess.PIPE,
        ),
    )
    api = "http://127.0.0.1:" + str(api_port)
    web = "http://127.0.0.1:" + str(web_port)
    measure("10_readiness_HTTP", lambda: request(web, "/healthz"))
    state = json.loads(
        (Path(context["private"]) / "fixture/large-state.json").read_text(
            encoding="utf8"
        )
    )

    def smoke():
        headers, url = state["headers"], state["url"]
        assert json.loads(request(api, url, headers=headers)) == state["profile"]
        try:
            request(api, url, headers=state["other_headers"])
            raise AssertionError("Foreign owner accepted")
        except urllib.error.HTTPError as error:
            assert error.code == 404
        assert json.loads(request(api, url + "/leads", headers=headers))[
            "receipts"
        ] == [state["receipt"]]
        assert json.loads(request(api, url + "/audit", headers=headers))
        assert json.loads(request(api, "/api/v1/geo/datasets"))
        assert json.loads(request(api, "/api/v1/bank-products"))
        geo = state["report_body"]["geo"]
        ranked = json.loads(
            request(api, "/api/v1/geo/kazan-fixture/rankings", geo["request"])
        )
        assert ranked["request_fingerprint"] == geo["fingerprint"]
        finance = state["report_body"]["finance"]
        calculated = json.loads(
            request(api, "/api/v1/finance/calculate", finance["request"])
        )
        assert calculated["request_fingerprint"] == finance["fingerprint"]
        for format_ in ("pdf", "json"):
            raw = request(
                web,
                url + "/reports/" + state["report_id"] + "/file?format=" + format_,
                headers=headers,
            )
            assert hashlib.sha256(raw).hexdigest() == state[format_ + "_sha256"]
        created = json.loads(request(api, "/api/v1/conversations", {}))
        new_url = "/api/v1/conversations/" + created["id"]
        token = {"X-Conversation-Token": created["access_token"]}
        consent = urllib.request.Request(
            api + new_url + "/consents/assistant",
            method="PUT",
            data=json.dumps(
                {
                    "expected_revision": 0,
                    "text_version": "assistant-demo-v1",
                    "decision": "grant",
                }
            ).encode(),
            headers={"Content-Type": "application/json", **token},
        )
        urllib.request.urlopen(consent, timeout=20).close()
        reply = json.loads(
            request(
                api,
                new_url + "/messages",
                {
                    "expected_version": 0,
                    "content": "Хочу открыть кофейню в Казани. Бюджет 2 миллиона рублей",
                },
                token,
            )
        )
        assert reply["extraction_mode"] == "ollama"
        assert reply["profile"]["city"] == "Казань" and Decimal(
            reply["profile"]["budget"]
        ) == Decimal(2000000)
        return {
            "owner_isolation": "PASS",
            "receipt_audit": "PASS",
            "geo_finance_bank": "PASS",
            "pdf_json": "byte-identical",
            "real_qwen": "PASS",
        }

    checks = measure("11_HTTP_user_scenarios_including_real_Qwen", smoke)
    total = time.monotonic() - start
    (bundle / "PIN").touch(
        mode=0o600
    )  # Preserve the last actually rehearsed good copy.
    report = {
        "status": "PASS",
        "total_rto_seconds": round(total, 3),
        "phases": phases,
        "checks": checks,
        "tables": recovered["tables"],
        "archive": public,
        "project": project,
        "target": target,
        "compose_file": str(compose),
        "api_url": api,
        "web_url": web,
        "cached_image_ids": images,
        "limitations": [
            "Local warm host; cached images/age/Ollama model and private test identity available",
            "No OS reinstall, remote/offsite transfer, key-loss or Ollama model-volume rebuild",
            "Stage06 includes stage05; stages are not additive; total is independent wall clock",
        ],
    }
    b.write_json(root / "result.json", report)
    print(
        json.dumps(
            {
                "status": "PASS",
                "rto_seconds": round(total, 3),
                "result": str(root / "result.json"),
            }
        )
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    run(json.loads(args.context.read_text(encoding="utf8")), args.bundle)
