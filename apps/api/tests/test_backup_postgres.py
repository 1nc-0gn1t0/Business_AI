"""Operator safety checks, offline; real restore evidence belongs to F-00 runbook."""

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

TOOL: dict[str, Any] = runpy.run_path(
    str(Path(__file__).resolve().parents[3] / "scripts" / "backup_postgres.py")
)


@pytest.mark.parametrize(
    "name",
    ["business_ai", "postgres", "f00_restore_", "f00_restore_x;DROP", "f00_restore_" + "x" * 49],
)
def test_restore_rejects_unsafe_target(name: str) -> None:
    with pytest.raises(ValueError):
        TOOL["restore_target"](name)


def test_restore_accepts_isolated_name() -> None:
    assert TOOL["restore_target"]("f00_restore_20261025_a1") == "f00_restore_20261025_a1"


def test_backup_refuses_repository_storage() -> None:
    with pytest.raises(ValueError):
        TOOL["private_directory"](TOOL["ROOT"] / "tmp" / "private-backup")


def test_archive_tampering_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "database.dump").write_bytes(b"original")
    (tmp_path / "backup.json").write_text(
        json.dumps(
            {"format": "f00-pgdump-v1", "archive_sha256": hashlib.sha256(b"original").hexdigest()}
        ),
        encoding="utf8",
    )
    assert TOOL["archive_metadata"](tmp_path)["format"] == "f00-pgdump-v1"
    (tmp_path / "database.dump").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        TOOL["archive_metadata"](tmp_path)


def test_oneoff_and_stopped_containers_never_supply_backup(monkeypatch: pytest.MonkeyPatch) -> None:
    def checked(args: list[str], **kwargs: Any) -> SimpleNamespace:
        states = {"regular": b"False running", "qa": b"True running", "old": b"False exited"}
        return SimpleNamespace(stdout=b"qa old regular" if "ps" in args else states[args[-1]])

    monkeypatch.setitem(TOOL["service_container"].__globals__, "checked", checked)
    assert TOOL["service_container"]("api") == "regular"


def test_ambiguous_regular_containers_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def checked(args: list[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(stdout=b"a b" if "ps" in args else b"False running")

    monkeypatch.setitem(TOOL["service_container"].__globals__, "checked", checked)
    with pytest.raises(RuntimeError, match="exactly one"):
        TOOL["service_container"]("api")


def test_worker_targets_explicit_regular_container(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        TOOL["worker_command"].__globals__, "service_container", lambda _: "regular"
    )
    command = TOOL["worker_command"]("f00_restore_test")
    assert command[:3] == ["docker", "exec", "-i"]
    assert "regular" in command and "PGDATABASE=f00_restore_test" in command


def test_invalid_backup_source_rejected_before_creating_files(tmp_path: Path) -> None:
    target = tmp_path / "not-created"
    with pytest.raises(ValueError):
        TOOL["backup"](target, "business_ai")
    assert not target.exists()


def test_corrupt_archive_never_creates_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "database.dump").write_bytes(b"corrupt")
    (tmp_path / "backup.json").write_text(
        json.dumps({"format": "f00-pgdump-v1", "archive_sha256": "0" * 64})
    )
    globals_ = TOOL["restore"].__globals__
    monkeypatch.setitem(
        globals_, "service_container", lambda _: pytest.fail("Must not access Docker")
    )
    with pytest.raises(ValueError, match="checksum"):
        TOOL["restore"](tmp_path, "f00_restore_test")


def test_existing_target_refuses_without_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    globals_ = TOOL["restore"].__globals__
    monkeypatch.setitem(
        globals_, "archive_metadata", lambda _: {"source": {"database": "source", "role": "test"}}
    )
    monkeypatch.setitem(globals_, "service_container", lambda _: "test-container")

    def checked(args: list[str], **kwargs: Any) -> None:
        calls.append(args)
        raise RuntimeError("Operation failed (details withheld)")

    monkeypatch.setitem(globals_, "checked", checked)
    with pytest.raises(RuntimeError):
        TOOL["restore"](tmp_path, "f00_restore_existing")
    assert len(calls) == 1 and "createdb" in calls[0]
    assert not (tmp_path / "f00_restore_existing.json").exists()


def test_worker_failures_do_not_echo_secret_arguments_or_stderr() -> None:
    import sys

    with pytest.raises(RuntimeError) as error:
        TOOL["checked"](
            [sys.executable, "-c", "import sys; sys.stderr.write('secret-fixture'); sys.exit(1)"]
        )
    assert "secret-fixture" not in str(error.value)


def test_archive_size_mismatch_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "database.dump").write_bytes(b"fixture")
    (tmp_path / "backup.json").write_text(
        json.dumps(
            {
                "format": "f00-pgdump-v1",
                "archive_sha256": hashlib.sha256(b"fixture").hexdigest(),
                "archive_bytes": 999,
            }
        )
    )
    with pytest.raises(ValueError, match="size"):
        TOOL["archive_metadata"](tmp_path)
