"""Opt-in faults against the exact disposable H-04-FU rehearsal project only."""

import json
import re
import shutil
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import encrypted_backup as b


def run(context_path, result_path):
    context = json.loads(Path(context_path).read_text(encoding="utf8"))
    report = json.loads(Path(result_path).read_text(encoding="utf8"))
    root = Path(context["private"])
    assert re.fullmatch(r"h04fu-recovery-[a-f0-9]{12}", report["project"])
    assert Path(report["compose_file"]).is_relative_to(root)
    config = {
        "root": str(root / "archives"),
        "age_binary": context["age_binary"],
        "project": report["project"],
        "compose_files": [report["compose_file"]],
    }
    backend = b.Compose(config)
    bundle = root / "archives" / report["archive"]["id"]
    identity = root / "synthetic-keys/temporary-identity.txt"
    wrong = root / "synthetic-keys/wrong-disposable-identity.txt"
    if not wrong.exists():
        b.base.checked(
            [context["age_keygen"], "-o", str(wrong)], stdout=b.subprocess.PIPE
        )
        wrong.chmod(0o600)
    db_container = b.base.service_container("db", backend.prefix)

    def sql(query, database="bootstrap"):
        return (
            b.base.checked(
                [
                    "docker",
                    "exec",
                    db_container,
                    "psql",
                    "-U",
                    "business_ai",
                    "-d",
                    database,
                    "-Atc",
                    query,
                ],
                stdout=b.subprocess.PIPE,
            )
            .stdout.decode()
            .strip()
        )

    def refused(operation):
        try:
            operation()
        except b.FAILURES:
            return "REFUSED"
        raise AssertionError("Fault unexpectedly succeeded")

    results = {}
    for case in (
        "wrong_key",
        "missing_identity",
        "missing_file",
        "tampered",
        "truncated",
    ):
        target = "f00_restore_fu_" + uuid4().hex
        candidate, key = bundle, identity
        if case == "wrong_key":
            key = wrong
        elif case == "missing_identity":
            key = root / "not-present.key"
        else:
            parent = b.private(root / ("negative-" + uuid4().hex))
            candidate = parent / bundle.name
            shutil.copytree(bundle, candidate)
            file = candidate / "database.age"
            if case == "missing_file":
                file.unlink()
            else:
                data = file.read_bytes()
                file.write_bytes(
                    data[:-20]
                    if case == "truncated"
                    else data[:-1] + bytes([data[-1] ^ 1])
                )
                public = json.loads(
                    (candidate / "manifest.json").read_text(encoding="utf8")
                )
                public["files"]["database.age"] = {
                    "sha256": b.base.file_hash(file),
                    "bytes": file.stat().st_size,
                }
                (candidate / "manifest.json").write_text(
                    json.dumps(public), encoding="utf8"
                )
        results[case] = refused(
            lambda candidate=candidate, key=key, target=target: b.recover(
                config, candidate, key, target, backend
            )
        )
        assert (
            sql("SELECT count(*) FROM pg_database WHERE datname='" + target + "'")
            == "0"
        )

    before = backend.inspect(report["target"])["tables"]
    results["existing_target"] = refused(
        lambda: b.recover(config, bundle, identity, report["target"], backend)
    )
    assert backend.inspect(report["target"])["tables"] == before
    b.base.checked([*backend.prefix, "stop", "db"], stdout=b.subprocess.PIPE)
    try:
        results["database_unavailable"] = refused(
            lambda: b.recover(
                config, bundle, identity, "f00_restore_fu_" + uuid4().hex, backend
            )
        )
    finally:
        b.base.checked(
            [*backend.prefix, "up", "-d", "--wait", "db"], stdout=b.subprocess.PIPE
        )
    assert backend.inspect(report["target"])["tables"] == before

    stop = threading.Event()
    killed = []
    target = "f00_restore_fu_" + uuid4().hex

    def terminate():
        deadline = time.monotonic() + 15
        while not stop.is_set() and time.monotonic() < deadline:
            if (
                sql(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='"
                    + target
                    + "' AND application_name='pg_restore'"
                )
                == "t"
            ):
                killed.append(True)
                return
            stop.wait(0.05)

    class Interrupt(b.Compose):
        def restore(self, source, database, plaintext):
            thread = threading.Thread(target=terminate)
            thread.start()
            try:
                super().restore(source, database, plaintext)
            finally:
                stop.set()
                thread.join(timeout=20)

    results["restore_interrupted"] = refused(
        lambda: b.recover(config, bundle, identity, target, Interrupt(config))
    )
    assert (
        killed
        and sql("SELECT count(*) FROM pg_tables WHERE schemaname='public'", target)
        == "0"
    )
    assert not list((root / "archives").glob(".restore-*"))
    snapshot = datetime.fromisoformat(b.manifest(bundle)["snapshot_at"])
    results["age_24h_exact"] = b.status(
        root / "archives", snapshot + timedelta(hours=24)
    )["status"]
    results["age_24h_plus1"] = b.status(
        root / "archives", snapshot + timedelta(hours=24, seconds=1)
    )["status"]
    # Other later healthy copies would change that threshold. Evaluate this copy in isolation.
    rpo_root = b.private(root / "rpo-isolated")
    if not (rpo_root / bundle.name).exists():
        shutil.copytree(bundle, rpo_root / bundle.name)
    results["isolated_age_24h"] = b.status(rpo_root, snapshot + timedelta(hours=24))[
        "status"
    ]
    results["isolated_age_24h_plus1"] = b.status(
        rpo_root, snapshot + timedelta(hours=24, seconds=1)
    )["status"]
    assert (
        results["isolated_age_24h"] == "OK"
        and results["isolated_age_24h_plus1"] == "STALE"
    )
    results["observed_rpo"] = b.status(root / "archives")
    results["partial_database_tables"] = 0
    results["plaintext_residue"] = False
    b.write_json(root / "negative-results.json", results)
    print(json.dumps(results))


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
