import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

CONFIG = Path(__file__).resolve().parents[2] / "alembic.ini"


@contextmanager
def isolated_database() -> Iterator[str]:
    name = "business_ai_test_" + uuid4().hex
    with psycopg.connect(dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield name
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def migrate(database: str, *arguments: str) -> str:
    options = ["-x", "allow_test_downgrade=true"] if "downgrade" in arguments else []
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(CONFIG), *options, *arguments],
        env={**os.environ, "PGDATABASE": database},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout + result.stderr
