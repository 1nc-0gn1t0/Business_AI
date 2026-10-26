"""Real age v1.3.2; disposable synthetic identities, no bank/LLM/network calls."""

import contextlib
import importlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
b = importlib.import_module("encrypted_backup")


class Fake:
    """DB fixture only; encryption processes and files are real."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail
        self.source = {
            "database": "f00_restore_fixture",
            "role": "fixture",
            "tables": {"messages": {"rows": 10, "sha256": "a" * 64}},
            "schema_sha256": "b" * 64,
            "extensions": [["postgis", "3.5.2"]],
            "invalid_indexes": 0,
            "server_version": "17.5",
        }

    @contextlib.contextmanager
    def snapshot(self, database: str | None, processes: Any) -> Iterator[dict[str, Any]]:
        yield self.source

    def dump(self, source: Any, processes: Any) -> Any:
        code = "import sys; sys.stdout.buffer.write(b'PGDMP-synthetic-private-content'*4096)"
        if self.fail:
            code += ";sys.stderr.write('DO-NOT-LOG-THIS');sys.exit(1)"
        return processes.start([sys.executable, "-c", code], stdout=subprocess.PIPE)

    def create(self, source: Any, target: str) -> None:
        self.calls.append("create")

    def restore(self, source: Any, target: str, plaintext: Any) -> None:
        self.calls.append("restore")
        assert plaintext.read().startswith(b"PGDMP-synthetic")

    def inspect(self, target: str) -> dict[str, Any]:
        self.calls.append("inspect")
        return self.source


@pytest.fixture(scope="module")
def identities(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Path, str, Path]]:
    binary = os.getenv("BA_AGE_BINARY") or shutil.which("age")
    assert binary, "Install pinned age with scripts/install_age.ps1 and set BA_AGE_BINARY"
    binary = str(Path(binary).resolve())
    keygen = str(Path(binary).with_name("age-keygen.exe" if os.name == "nt" else "age-keygen"))
    directory = b.private(tmp_path_factory.mktemp("age-parent") / "identities")
    keys = [directory / "synthetic-key.txt", directory / "wrong-synthetic-key.txt"]
    for key in keys:
        subprocess.run(
            [keygen, "-o", str(key)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        key.chmod(0o600)
    recipient = subprocess.run(
        [keygen, "-y", str(keys[0])], check=True, capture_output=True, text=True
    ).stdout.strip()
    try:
        yield binary, keys[0], recipient, keys[1]
    finally:
        for key in keys:
            key.unlink(missing_ok=True)


@pytest.fixture
def config(tmp_path: Path, identities: tuple[str, Path, str, Path]) -> dict[str, Any]:
    return {
        "root": str(tmp_path / "ciphertext"),
        "age_binary": identities[0],
        "recipient": identities[2],
        "database": "f00_restore_fixture",
    }


def test_encrypted_roundtrip_and_no_plaintext(config: dict[str, Any], identities: Any) -> None:
    fake = Fake()
    result = b.backup(config, fake)
    root = Path(config["root"])
    bundle = root / result["id"]
    assert set(p.name for p in bundle.iterdir()) == {
        "database.age",
        "metadata.age",
        "manifest.json",
    }
    assert all(b"synthetic-private-content" not in p.read_bytes() for p in bundle.iterdir())
    assert b.recover(config, bundle, identities[1])["status"] == "AUTHENTICATED"
    restored = b.recover(config, bundle, identities[1], "f00_restore_target", fake)
    assert restored["status"] == "PASS" and fake.calls == ["create", "restore", "inspect"]
    assert not list(root.glob(".restore-*")) and not list(root.glob(".partial-*"))


@pytest.mark.parametrize(
    "damage", ["wrong-key", "missing-key", "tamper", "truncate", "missing-file"]
)
def test_authentication_rejects_before_database(
    config: dict[str, Any],
    identities: Any,
    damage: str,
) -> None:
    result = b.backup(config, Fake())
    bundle = Path(config["root"]) / result["id"]
    identity = identities[1]
    if damage == "wrong-key":
        identity = identities[3]
    elif damage == "missing-key":
        identity = Path(config["root"]).parent / "not-present.key"
    else:
        path = bundle / "database.age"
        raw = path.read_bytes()
        if damage == "missing-file":
            path.unlink()
        else:
            path.write_bytes(raw[:-20] if damage == "truncate" else raw[:-1] + bytes([raw[-1] ^ 1]))
            # Bypass plain SHA to prove real AEAD authentication, not just checksum rejection.
            value = json.loads((bundle / "manifest.json").read_text())
            value["files"]["database.age"] = {
                "sha256": b.base.file_hash(path),
                "bytes": path.stat().st_size,
            }
            (bundle / "manifest.json").write_text(json.dumps(value))
    fake = Fake()
    with pytest.raises((OSError, ValueError, RuntimeError)):
        b.recover(config, bundle, identity, "f00_restore_target", fake)
    assert fake.calls == []
    assert not list(Path(config["root"]).glob(".restore-*"))


def test_failure_keeps_previous_copy_and_logs_no_secret(
    config: dict[str, Any], capsys: Any, monkeypatch: Any, tmp_path: Path
) -> None:
    b.scheduled(config, Fake())
    before = b.status(config["root"])
    with pytest.raises(RuntimeError):
        b.scheduled(config, Fake(fail=True))
    assert b.status(config["root"])["id"] == before["id"]
    assert b.status(config["root"])["last_attempt_failed"] is True
    assert len(list(Path(config["root"]).glob("backup-*"))) == 1
    assert not list(Path(config["root"]).glob(".partial-*"))
    assert "DO-NOT-LOG-THIS" not in capsys.readouterr().out
    assert "DO-NOT-LOG-THIS" not in (Path(config["root"]) / "events.jsonl").read_text()
    file = tmp_path / "config.json"
    file.write_text(json.dumps(config), encoding="utf8")
    monkeypatch.setattr(sys, "argv", ["tool", "status", "--config", str(file)])
    assert b.main() == 2


def test_missing_encryption_tool_does_not_publish(config: dict[str, Any]) -> None:
    config["age_binary"] = str(Path(config["root"]) / "missing-age")
    with pytest.raises(OSError):
        b.backup(config, Fake())
    assert not list(Path(config["root"]).glob("backup-*"))


def test_interrupted_encryption_has_no_published_artifact(
    config: dict[str, Any], monkeypatch: Any
) -> None:
    def interrupted(*args: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(b, "encrypt", interrupted)
    with pytest.raises(KeyboardInterrupt):
        b.backup(config, Fake())
    assert not list(Path(config["root"]).glob("backup-*"))
    assert not list(Path(config["root"]).glob(".partial-*"))


def test_os_lock_excludes_other_process_and_recovers(config: dict[str, Any]) -> None:
    root = b.private(config["root"])
    code = (
        "import sys;sys.path.insert(0,sys.argv[1]);import encrypted_backup as b;\n"
        "with b.lock(b.private(sys.argv[2])): pass"
    )
    with b.lock(root):
        result = subprocess.run(
            [sys.executable, "-c", code, str(SCRIPTS), str(root)], capture_output=True
        )
        assert result.returncode != 0 and b"backup_busy" in result.stderr
    with b.lock(root):
        pass


def test_stale_missing_and_corrupt_recovery_points(config: dict[str, Any]) -> None:
    assert b.status(config["root"])["status"] == "MISSING"
    result = b.backup(config, Fake())
    snapshot = datetime.fromisoformat(result["snapshot_at"])
    assert b.status(config["root"], snapshot + timedelta(hours=24))["status"] == "OK"
    assert b.status(config["root"], snapshot + timedelta(hours=24, seconds=1))["status"] == "STALE"
    (Path(config["root"]) / result["id"] / "database.age").write_bytes(b"damaged")
    assert b.status(config["root"])["status"] == "MISSING"
    assert b.status(config["root"])["invalid_bundles"] == 1


def test_retention_never_deletes_pinned_or_last_good_copy(config: dict[str, Any]) -> None:
    root = Path(config["root"])
    first = b.backup(config, Fake())
    (root / first["id"] / "PIN").touch()
    second = b.backup(config, Fake())
    third = b.backup(config, Fake())
    plan = b.prune(root, keep=1)
    assert plan["dry_run"] and plan["remove"] == [second["id"]]
    b.prune(root, keep=1, apply=True)
    assert (root / first["id"]).exists() and (root / third["id"]).exists()
    with pytest.raises(ValueError):
        b.prune(root, keep=0, apply=True)


def test_restore_failure_removes_temporary_plaintext(
    config: dict[str, Any], identities: Any
) -> None:
    result = b.backup(config, Fake())

    class Failing(Fake):
        def restore(self, source: Any, target: str, plaintext: Any) -> None:
            raise RuntimeError("synthetic restore interruption")

    with pytest.raises(RuntimeError):
        b.recover(
            config,
            Path(config["root"]) / result["id"],
            identities[1],
            "f00_restore_target",
            Failing(),
        )
    assert not list(Path(config["root"]).glob(".restore-*"))


def test_unsafe_restore_target_never_reaches_db(config: dict[str, Any], identities: Any) -> None:
    result = b.backup(config, Fake())
    fake = Fake()
    with pytest.raises(ValueError):
        b.recover(config, Path(config["root"]) / result["id"], identities[1], "business_ai", fake)
    assert fake.calls == []


def test_watch_dispatches_two_scheduled_real_encryptions(
    config: dict[str, Any], monkeypatch: Any, tmp_path: Path
) -> None:
    file = tmp_path / "config.json"
    file.write_text(json.dumps(config))
    real_backup = b.backup
    delays: list[float] = []
    monkeypatch.setattr(b, "backup", lambda c, backend=None: real_backup(c, Fake()))
    monkeypatch.setattr(b.time, "sleep", delays.append)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tool",
            "watch",
            "--config",
            str(file),
            "--test-interval-seconds",
            "2",
            "--test-runs",
            "2",
        ],
    )
    assert b.main() == 0
    assert delays == [2] and len(list(Path(config["root"]).glob("backup-*"))) == 2


def test_destination_failure_preserves_previous_backup(
    config: dict[str, Any], monkeypatch: Any
) -> None:
    result = b.backup(config, Fake())
    monkeypatch.setattr(b, "encrypt", lambda *a: (_ for _ in ()).throw(PermissionError("fixture")))
    with pytest.raises(PermissionError):
        b.backup(config, Fake())
    assert b.status(config["root"])["id"] == result["id"]
    assert not list(Path(config["root"]).glob(".partial-*"))


def test_real_encryption_process_timeout_cleans_staging(
    config: dict[str, Any], monkeypatch: Any
) -> None:
    real = b.Processes
    monkeypatch.setattr(b, "Processes", lambda: real(timeout=0.001))
    with pytest.raises((OSError, ValueError, RuntimeError)):
        b.backup(config, Fake())
    assert not list(Path(config["root"]).glob("backup-*"))
    assert not list(Path(config["root"]).glob(".partial-*"))
