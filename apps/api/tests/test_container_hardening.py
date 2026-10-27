"""H-06-FU fail-closed policy and explicit upgrade invariants, no Docker/network."""

import copy
import importlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
gate = importlib.import_module("image_security")
upgrade = importlib.import_module("restore_container_upgrade")


def scan(severity: str, fixed: str = "") -> dict[str, Any]:
    return {
        "SchemaVersion": 2,
        "Metadata": {"OS": {"Family": "debian"}},
        "Results": [
            {
                "Class": "os-pkgs",
                "Type": "debian",
                "Vulnerabilities": [{"Severity": severity, "FixedVersion": fixed}],
            }
        ],
    }


@pytest.mark.parametrize("severity", ["CRITICAL", "HIGH"])
def test_fixable_blocks_gate_unfixed_keeps_release_open(severity: str) -> None:
    assert gate.evaluate(scan(severity, "2.0"))["gate"] == "FAIL"
    actual = gate.evaluate(scan(severity))
    assert actual["gate"] == "PASS"
    assert actual["release_baseline"] == "OPEN"
    assert actual["critical_high"] == 1


def test_medium_is_reported_without_becoming_high() -> None:
    actual = gate.evaluate(scan("MEDIUM", "2.0"))
    assert actual["gate"] == "PASS"
    assert actual["package_occurrences"] == {"MEDIUM": 1}


def test_unsupported_os_does_not_pass_even_without_fixable_advisories() -> None:
    document = scan("LOW")
    document["Metadata"]["OS"]["EOSL"] = True
    actual = gate.evaluate(document)
    assert actual["gate"] == "FAIL"
    assert actual["release_baseline"] == "OPEN"


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"SchemaVersion": 2},
        {"SchemaVersion": 2, "Results": []},
        {"SchemaVersion": 2, "Metadata": {"OS": {"Family": "debian"}}, "Results": [{}]},
    ],
)
def test_incomplete_scan_never_passes(document: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        gate.evaluate(document)


def test_advisory_clock_boundaries() -> None:
    now = datetime(2026, 10, 27, tzinfo=UTC)
    gate.fresh({"UpdatedAt": (now - timedelta(hours=48)).isoformat()}, now)
    for delta in (timedelta(hours=48, seconds=1), -timedelta(seconds=1)):
        with pytest.raises(ValueError):
            gate.fresh({"UpdatedAt": (now - delta).isoformat()}, now)


def states() -> tuple[dict[str, Any], dict[str, Any]]:
    before = {
        "server_version": "17.5 (Debian)",
        "extensions": [["plpgsql", "1.0"], ["postgis", "3.5.2"]],
        "tables": {"messages": {"rows": 2, "sha256": "a" * 64}},
        "schema_sha256": "b" * 64,
        "invalid_indexes": 0,
    }
    after = copy.deepcopy(before)
    after.update(
        server_version="17.11 (Debian)", extensions=[["plpgsql", "1.0"], ["postgis", "3.6.4"]]
    )
    return before, after


@pytest.mark.parametrize("full_extensions", [False, True])
def test_only_explicit_version_change_allowed_with_exact_data(full_extensions: bool) -> None:
    before, after = states()
    if full_extensions:
        before["extensions"] += [
            ["fuzzystrmatch", "1.2"],
            ["postgis_topology", "3.5.2"],
            ["postgis_tiger_geocoder", "3.5.2"],
        ]
        after["extensions"] += [
            ["fuzzystrmatch", "1.2"],
            ["postgis_topology", "3.6.4"],
            ["postgis_tiger_geocoder", "3.6.4"],
        ]
    upgrade.verify_transition(before, after)


@pytest.mark.parametrize(
    "field,value",
    [
        ("server_version", "18.6 (Debian)"),
        ("extensions", [["postgis", "3.6.4"], ["unexpected", "1"]]),
        ("tables", {"messages": {"rows": 1, "sha256": "a" * 64}}),
        ("tables", {"messages": {"rows": 2, "sha256": "c" * 64}}),
        ("schema_sha256", "c" * 64),
        ("invalid_indexes", 1),
    ],
)
def test_upgrade_mismatch_is_never_waived(field: str, value: Any) -> None:
    before, after = states()
    after[field] = value
    with pytest.raises(ValueError):
        upgrade.verify_transition(before, after)
