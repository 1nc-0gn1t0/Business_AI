"""Operator-only fetch/import; no network fetch or write endpoint exposed by public API."""

import argparse
import json
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.geo.ingest import import_snapshot
from app.geo.provider import (
    DEFAULT_ENDPOINT,
    GeoImportError,
    OverpassProvider,
    load_snapshot,
    save_snapshot,
)
from app.geo.schemas import Bounds
from app.geo.service import GeoData


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch")
    fetch.add_argument("--bbox", required=True, help="west,south,east,north (WGS84)")
    fetch.add_argument("--slug", required=True)
    fetch.add_argument("--city", required=True)
    fetch.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    fetch.add_argument("--output", type=Path, required=True)
    ingest = commands.add_parser("import")
    ingest.add_argument("--snapshot", type=Path, required=True)
    ingest.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            bbox = Bounds.parse(args.bbox)
            provider = OverpassProvider(args.endpoint)
            manifest = save_snapshot(
                provider.fetch(bbox),
                args.output,
                slug=args.slug,
                city=args.city,
                bbox=bbox,
                endpoint=args.endpoint,
            )
            print(manifest.model_dump_json(indent=2))
        else:
            manifest, document = load_snapshot(args.snapshot)
            engine = sa.create_engine(
                "postgresql+psycopg://",
                connect_args={"connect_timeout": 5, "options": "-c statement_timeout=120000"},
            )
            try:
                with Session(engine) as session, session.begin():
                    record = import_snapshot(
                        session, manifest, document, allow_empty=args.allow_empty
                    )
                    result = GeoData.metadata(record)
                print(json.dumps(result, default=str, ensure_ascii=True, indent=2))
            finally:
                engine.dispose()
    except GeoImportError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except (ValueError, OSError):
        print(
            "OSM operation failed: invalid snapshot/configuration or file error.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    except SQLAlchemyError:
        print("OSM database operation failed; transaction rolled back.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
