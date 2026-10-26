"""Local Compose backup/restore drill. Never replaces or deletes an existing database.

Run from the repository root. Archives contain private application data: keep the
directory outside Git on protected local storage. This is not cluster/PITR backup.
"""

import argparse
import hashlib
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Runs inside the existing API image: psycopg/libpq use its PG* environment.
# Only aggregate hashes/counts leave the DB. A held exported snapshot binds those
# hashes and pg_dump to the same committed data, even with concurrent writers.
WORKER = r"""
import hashlib, json, sys
import psycopg
from psycopg import sql
with psycopg.connect(autocommit=True, connect_timeout=5) as db:
    db.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
    db.execute("SET LOCAL statement_timeout = '60s'")
    db.execute("SET LOCAL idle_in_transaction_session_timeout = '600s'")
    snapshot = db.execute("SELECT pg_export_snapshot()").fetchone()[0]
    name, role, version = db.execute(
        "SELECT current_database(), current_user, current_setting('server_version')"
    ).fetchone()
    tables = db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
    result = {}
    for (table,) in tables:
        count, digest = 0, hashlib.sha256()
        query = sql.SQL('SELECT to_jsonb(t)::text FROM public.{} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(sql.Identifier(table))
        with db.cursor(name='fingerprint') as rows:
            rows.execute(query)
            for (row,) in rows:
                digest.update(row.encode('utf8') + b'\n')
                count += 1
        result[table] = {"rows": count, "sha256": digest.hexdigest()}
    definitions = []
    for query in [
        "SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position",
        "SELECT r.relname,c.conname,pg_get_constraintdef(c.oid),c.convalidated FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='public' ORDER BY r.relname,c.conname",
        "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname",
        "SELECT schemaname,sequencename,last_value FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename",
    ]:
        definitions.append(db.execute(query).fetchall())
    schema_hash = hashlib.sha256(json.dumps(definitions,default=str).encode()).hexdigest()
    extensions = db.execute("SELECT extname,extversion FROM pg_extension ORDER BY extname").fetchall()
    invalid = db.execute("SELECT count(*) FROM pg_index WHERE NOT indisvalid").fetchone()[0]
    print(json.dumps(dict(database=name,role=role,server_version=version,snapshot=snapshot,
        tables=result,schema_sha256=schema_hash,extensions=extensions,invalid_indexes=invalid)),flush=True)
    if sys.argv[1] == 'hold':
        sys.stdin.readline()
"""


def checked(args, **kwargs):
    result = subprocess.run(
        args, stderr=subprocess.PIPE, timeout=600, check=False, **kwargs
    )
    if result.returncode:
        # SQL errors can contain row data; do not put raw stderr in public logs.
        raise RuntimeError(
            f"Operation failed (exit {result.returncode}); details withheld"
        )
    return result


def compose(*args):
    return ["docker", "compose", *args]


def service_container(service):
    ids = checked(compose("ps", "--all", "--quiet", service), stdout=subprocess.PIPE)
    regular = []
    for identifier in ids.stdout.decode().split():
        state = (
            checked(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "com.docker.compose.oneoff"}} {{.State.Status}}',
                    identifier,
                ],
                stdout=subprocess.PIPE,
            )
            .stdout.decode()
            .strip()
        )
        if state.lower() == "false running":
            regular.append(identifier)
    if len(regular) != 1:
        raise RuntimeError(
            f"Expected exactly one running non-oneoff {service} container"
        )
    return regular[0]


def worker_command(database=None, mode="inspect"):
    options = ["-e", f"PGDATABASE={database}"] if database else []
    return [
        "docker",
        "exec",
        "-i",
        *options,
        service_container("api"),
        "python",
        "-c",
        WORKER,
        mode,
    ]


def private_directory(path):
    resolved = Path(path).resolve()
    if resolved.is_relative_to(ROOT):
        raise ValueError("Backup directory must be outside the repository")
    return resolved


def restore_target(value):
    if not re.fullmatch(r"f00_restore_[a-z0-9_]{1,48}", value):
        raise ValueError("Target must be a new f00_restore_<lowercase-id> database")
    return value


def file_hash(path):
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()


def archive_metadata(directory):
    if any(
        (directory / name).is_symlink() for name in ("backup.json", "database.dump")
    ):
        raise ValueError("Backup files must not be symbolic links")
    metadata = json.loads((directory / "backup.json").read_text(encoding="utf8"))
    if metadata.get("format") != "f00-pgdump-v1":
        raise ValueError("Unsupported backup format")
    if file_hash(directory / "database.dump") != metadata["archive_sha256"]:
        raise ValueError("Archive checksum mismatch; restore refused")
    if (
        "archive_bytes" in metadata
        and (directory / "database.dump").stat().st_size != metadata["archive_bytes"]
    ):
        raise ValueError("Archive size mismatch; restore refused")
    return metadata


def backup(directory, database=None):
    if database is not None:
        database = restore_target(
            database
        )  # Explicit QA source only; never arbitrary names.
    directory = private_directory(directory)
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    start = time.monotonic()
    keeper = subprocess.Popen(
        worker_command(database, mode="hold"),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf8",
    )
    try:
        source = json.loads(keeper.stdout.readline())
        container = service_container("db")
        with (directory / "database.dump").open("xb") as archive:
            (directory / "database.dump").chmod(0o600)
            checked(
                [
                    "docker",
                    "exec",
                    container,
                    "pg_dump",
                    "-U",
                    source["role"],
                    "-d",
                    source["database"],
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--lock-wait-timeout=5s",
                    f"--snapshot={source['snapshot']}",
                ],
                stdout=archive,
            )
        keeper.communicate("done\n", timeout=15)
        if keeper.returncode:
            raise RuntimeError("Snapshot connection failed")
    finally:
        if keeper.poll() is None:
            keeper.kill()
            keeper.communicate()
    metadata = {
        "format": "f00-pgdump-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "source": source,
        "archive_sha256": file_hash(directory / "database.dump"),
        "archive_bytes": (directory / "database.dump").stat().st_size,
        "backup_seconds": round(time.monotonic() - start, 3),
        "limitations": [
            "Single database; no roles, tablespaces, WAL/PITR or encryption",
            "Trusted local archive only; protect directory with OS ACL/encrypted storage",
            "Do not run DDL or sequence-changing writers during backup",
        ],
    }
    (directory / "backup.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf8"
    )
    (directory / "backup.json").chmod(0o600)
    print(
        json.dumps(
            {
                k: metadata[k]
                for k in ["format", "archive_sha256", "archive_bytes", "backup_seconds"]
            }
        )
    )


def restore(directory, database):
    database = restore_target(database)
    directory = private_directory(directory)
    metadata = archive_metadata(directory)  # Validate before CREATE DATABASE.
    source = metadata["source"]
    if database == source["database"]:
        raise ValueError("Restoring into source is forbidden")
    container = service_container("db")
    start = time.monotonic()
    # createdb fails if the target exists. Never --clean, --create or DROP.
    checked(
        [
            "docker",
            "exec",
            container,
            "createdb",
            "-U",
            source["role"],
            "--template=template0",
            database,
        ],
        stdout=subprocess.PIPE,
    )
    with (directory / "database.dump").open("rb") as archive:
        checked(
            [
                "docker",
                "exec",
                "-i",
                container,
                "pg_restore",
                "-U",
                source["role"],
                "-d",
                database,
                "--single-transaction",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
            ],
            stdin=archive,
            stdout=subprocess.PIPE,
        )
    restored_seconds = time.monotonic() - start
    verify_start = time.monotonic()
    observed = json.loads(
        checked(worker_command(database), stdout=subprocess.PIPE).stdout
    )
    keys = [
        "tables",
        "schema_sha256",
        "extensions",
        "invalid_indexes",
        "server_version",
    ]
    checks = {key: observed[key] == source[key] for key in keys}
    report = {
        "database": database,
        "checked_at": datetime.now(UTC).isoformat(),
        "restore_verify_seconds": round(time.monotonic() - start, 3),
        "restore_seconds": round(restored_seconds, 3),
        "verification_seconds": round(time.monotonic() - verify_start, 3),
        "checks": checks,
        "tables": observed["tables"],
        "status": "PASS" if all(checks.values()) else "FAIL",
    }
    # An exclusive report also prevents silently replacing an earlier drill result.
    with (directory / f"{database}.json").open("x", encoding="utf8") as handle:
        (directory / f"{database}.json").chmod(0o600)
        json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))
    if not all(checks.values()):
        raise RuntimeError(
            "Restored data differs from exported snapshot; keep DB for diagnosis"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "verify", "restore"])
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument(
        "--database",
        help="New f00_restore_<id> target, or explicit isolated QA backup source",
    )
    args = parser.parse_args()
    if args.operation == "restore" and not args.database:
        parser.error("restore requires --database")
    try:
        if args.operation == "backup":
            backup(args.directory, args.database)
        elif args.operation == "restore":
            restore(args.directory, args.database)
        else:
            archive_metadata(private_directory(args.directory))
            print("Archive checksum PASS (trusted local manifest; not authentication)")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyError):
        # Preserve partial artifacts/DB; no automatic cleanup of potentially useful data.
        parser.exit(
            1,
            "Backup/restore failed safely. Existing databases were not replaced; partial artifacts retained.\n",
        )


if __name__ == "__main__":
    main()
