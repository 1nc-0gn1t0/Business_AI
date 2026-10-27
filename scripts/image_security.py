"""Scoped image gate: fail on known fixable HIGH/CRITICAL; report all findings.

Passing this gate is NOT release acceptance. Unfixed/unassessed HIGH/CRITICAL keep
the release baseline OPEN. There are no scanner exceptions or blanket ignores.
"""

import argparse
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path


def evaluate(document):
    if (
        document.get("SchemaVersion") != 2
        or not isinstance(document.get("Results"), list)
        or not document["Results"]
        or not document.get("Metadata", {}).get("OS", {}).get("Family")
    ):
        raise ValueError("Incomplete image scan")
    if not any(
        result.get("Class") == "os-pkgs" and result.get("Type")
        for result in document["Results"]
    ):
        raise ValueError("Missing OS package scan")
    findings = [
        value
        for result in document["Results"]
        for value in result.get("Vulnerabilities", [])
    ]
    important = [v for v in findings if v["Severity"] in ("HIGH", "CRITICAL")]
    fixable = [v for v in important if v.get("FixedVersion", "").strip()]
    eosl = bool(document["Metadata"]["OS"].get("EOSL"))
    return {
        "package_occurrences": dict(Counter(v["Severity"] for v in findings)),
        "fixable_critical_high": len(fixable),
        "critical_high": len(important),
        "eosl": eosl,
        "release_baseline": "OPEN" if important or eosl else "NO_HIGH_CRITICAL_FOUND",
        "gate": "FAIL" if fixable or eosl else "PASS",
    }


def fresh(metadata, now):
    updated = datetime.fromisoformat(metadata["UpdatedAt"])
    if updated.tzinfo is None or not timedelta(0) <= now - updated <= timedelta(
        hours=48
    ):
        raise ValueError("Advisory DB not fresh")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", required=True, help="label=path")
    parser.add_argument("--db-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        fresh(json.loads(args.db_metadata.read_text()), datetime.now(UTC))
        results = {}
        for item in args.report:
            label, path = item.split("=", 1)
            if label in results:
                raise ValueError("Duplicate image label")
            results[label] = evaluate(json.loads(Path(path).read_text(encoding="utf8")))
        args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf8")
        print(json.dumps(results))
        raise SystemExit(int(any(r["gate"] == "FAIL" for r in results.values())))
    except (ValueError, KeyError, OSError, TypeError):
        raise SystemExit("Image scan incomplete; no passing result") from None
