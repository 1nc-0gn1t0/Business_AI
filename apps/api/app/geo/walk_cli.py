import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.geo.schemas import Bounds
from app.geo.walk_import import fetch, import_graph, load


def main() -> None:
    parser = argparse.ArgumentParser(description="Versioned OSM walking graph; no bank/LLM calls")
    parser.add_argument("command", choices=("fetch", "import"))
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--slug", default="kazan-centre")
    parser.add_argument("--city", default="Казань")
    parser.add_argument("--bbox", default="49.08,55.76,49.18,55.82")
    parser.add_argument("--endpoint", default="https://overpass-api.de/api/interpreter")
    args = parser.parse_args()
    if args.command == "fetch":
        view = fetch(args.path, Bounds.parse(args.bbox), args.slug, args.city, args.endpoint)
        print(view.model_dump_json(indent=2))
    else:
        manifest, document = load(args.path)
        engine = create_engine("postgresql+psycopg://")
        try:
            with Session(engine) as session, session.begin():
                graph = import_graph(session, manifest, document)
            print(json.dumps(graph.model_dump(mode="json"), ensure_ascii=True, indent=2))
        finally:
            engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, SQLAlchemyError):
        print(
            "Walking graph operation failed: check snapshot/provider/database. "
            "No partial graph activated; existing data retained.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
