"""Manual H-04 helper inside the integration image; exclusively fresh QA databases.

Run seed on an empty database; restore verification accepts only the private seed
state. The operator backup tool, not this helper, creates/restores the archive.
"""

import argparse
import json
import os
import re
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
import sqlalchemy as sa

from .support import migrate
from .test_populated_upgrade import PREVIOUS, add_report, fingerprints, populate, verify_api


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["seed", "verify"])
    parser.add_argument("--database", required=True)
    parser.add_argument("--private", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"f00_restore_h04_[a-f0-9]{32}", args.database):
        parser.error("Only a fresh, operator-created H-04 UUID database is allowed")
    os.environ["LLM_PROVIDER"] = "stub"
    engine = sa.create_engine("postgresql+psycopg://", connect_args={"dbname": args.database})
    state_file = args.private / "fixture-state.json"
    try:
        with patch("app.leads.service.today", lambda: date(2026, 10, 23)):
            if args.operation == "seed":
                assert not state_file.exists()
                with psycopg.connect(dbname=args.database) as db:
                    assert db.execute(
                        "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
                    ).fetchone() == (0,)
                migrate(args.database, "upgrade", PREVIOUS)
                state = populate(engine)
                before = fingerprints(args.database)
                migrate(args.database, "upgrade", "head")
                after = fingerprints(args.database)
                assert {k: v for k, v in after.items() if k in before} == before
                add_report(engine, state)
                state["fingerprints"] = fingerprints(args.database)
                with state_file.open("x", encoding="utf8") as handle:
                    state_file.chmod(0o600)
                    json.dump(state, handle, ensure_ascii=False)
            else:
                state = json.loads(state_file.read_text(encoding="utf8"))
            migrate(args.database, "upgrade", "head")
            migrate(args.database, "check")
            assert fingerprints(args.database) == state["fingerprints"]
            verify_api(engine, state)
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "tables": state["fingerprints"],
                        "pdf_sha256": state["pdf_sha256"],
                        "json_sha256": state["json_sha256"],
                    }
                )
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
