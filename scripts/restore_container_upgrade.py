"""Opt-in H-06-FU drill: authenticated PG17 dump into a NEW isolated cluster.

The normal H-04-FU restore remains strict about equal server/extension versions.
This separate tool permits ONLY the explicitly tested 17.5/3.5.2 -> 17.11/3.6.4
transition. It never starts containers, replaces a DB, deletes data or changes apps.
"""

import argparse
import io
import json
import subprocess
import tempfile
import time
from pathlib import Path

import encrypted_backup as b


def verify_transition(source, restored):
    if not source["server_version"].startswith("17.5 ") or not restored[
        "server_version"
    ].startswith("17.11 "):
        raise ValueError("Unsupported server transition")
    before = dict(source["extensions"])
    after = dict(restored["extensions"])
    allowed = {
        "plpgsql": ("1.0", "1.0"),
        "postgis": ("3.5.2", "3.6.4"),
        "fuzzystrmatch": ("1.2", "1.2"),
        "postgis_topology": ("3.5.2", "3.6.4"),
        "postgis_tiger_geocoder": ("3.5.2", "3.6.4"),
    }
    if (
        before.keys() != after.keys()
        or not {"plpgsql", "postgis"} <= before.keys()
        or any(
            name not in allowed or (version, after[name]) != allowed[name]
            for name, version in before.items()
        )
    ):
        raise ValueError("Unsupported extension transition; no automatic waiver")
    for field in ("tables", "schema_sha256", "invalid_indexes"):
        if source[field] != restored[field]:
            raise ValueError("Upgrade fingerprint mismatch: " + field)
    if restored["invalid_indexes"] != 0:
        raise ValueError("Invalid indexes")


def run(config, bundle, identity, target):
    if not config.get("project", "").startswith("h06futarget-"):
        raise ValueError("Only the explicitly isolated H-06-FU target project")
    b.base.restore_target(target)
    start = time.monotonic()
    public = b.manifest(bundle)
    binary = b.age_binary(config)
    identity = b.key_path(identity, Path(config["root"]))
    backend = b.Compose(config)
    # Authentication and bounded SHA checks complete BEFORE createdb. Plaintext is
    # delete-on-close in a protected operator directory, never a published dump.
    root = b.private(Path(config["root"]))
    with b.Processes() as processes:
        metadata_buffer = io.BytesIO()
        b.decrypt(
            bundle / "metadata.age",
            metadata_buffer,
            binary,
            identity,
            processes,
            b.MAX_METADATA,
        )
        metadata = json.loads(metadata_buffer.getvalue())
        if (metadata["format"], metadata["id"], metadata["snapshot_at"]) != (
            b.FORMAT,
            public["id"],
            public["snapshot_at"],
        ):
            raise ValueError("Authenticated manifest mismatch")
        source = metadata["source"]
        if target == source["database"]:
            raise ValueError("Source overwrite forbidden")
        with tempfile.TemporaryFile(dir=root) as plaintext:
            observed = b.decrypt(
                bundle / "database.age",
                plaintext,
                binary,
                identity,
                processes,
            )
            if observed != metadata["plaintext"]:
                raise ValueError("Plaintext checksum mismatch")
            authenticated = time.monotonic()
            backend.create(source, target)  # Existing target is refused by createdb.
            plaintext.seek(0)
            backend.restore(source, target, plaintext)
            completed = time.monotonic()
            restored = backend.inspect(target)
            verify_transition(source, restored)
    return {
        "status": "PASS",
        "source_server": source["server_version"],
        "target_server": restored["server_version"],
        "source_extensions": source["extensions"],
        "target_extensions": restored["extensions"],
        "tables": restored["tables"],
        "schema_sha256": restored["schema_sha256"],
        "authentication_seconds": round(authenticated - start, 3),
        "restore_seconds": round(completed - authenticated, 3),
        "verification_seconds": round(time.monotonic() - completed, 3),
        "total_seconds": round(time.monotonic() - start, 3),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf8"))
        print(json.dumps(run(config, args.bundle, args.identity, args.target)))
    except (
        ValueError,
        KeyError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        # DB/subprocess/crypto details can contain secrets; never echo them.
        raise SystemExit(
            "Upgrade drill failed ("
            + type(error).__name__
            + "); preserve isolated target"
        ) from None
