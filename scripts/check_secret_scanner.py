"""Offline positive/negative/redaction checks with synthetic, unusable credentials."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    args = parser.parse_args()
    policy = Path(__file__).resolve().parents[1] / ".gitleaks.toml"
    with tempfile.TemporaryDirectory(
        prefix="business-ai-scanner-selftest-"
    ) as temporary:
        root = Path(temporary)
        fixtures = root / "fixtures"
        fixtures.mkdir()
        report = root / "report.json"
        command = [
            args.binary,
            "dir",
            str(fixtures),
            "--config",
            str(policy),
            "--redact=100",
            "--ignore-gitleaks-allow",
            "--report-format",
            "json",
            "--report-path",
            str(report),
            "--no-banner",
            "--log-level",
            "error",
        ]
        clean = subprocess.run(command, capture_output=True, timeout=30, check=False)
        if clean.returncode != 0:
            raise SystemExit("Secret scanner clean-fixture check failed")
        fake = [
            "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
            "AGE-SECRET-KEY-1" + "A" * 58,
            "postgresql://synthetic:" + "h06_never_real_password@localhost/test",
        ]
        (fixtures / "synthetic.txt").write_text(
            "\n".join(value + " # gitleaks:allow" for value in fake), encoding="utf8"
        )
        found = subprocess.run(command, capture_output=True, timeout=30, check=False)
        raw = report.read_text(encoding="utf8") if report.exists() else "[]"
        rules = {entry["RuleID"] for entry in json.loads(raw)}
        if (
            found.returncode != 1
            or not {"github-pat", "age-private-identity", "database-password-url"}
            <= rules
        ):
            raise SystemExit("Secret scanner positive-fixture check failed")
        # Neither output nor the machine-readable report may disclose marker values.
        if any(
            value
            in raw
            + found.stdout.decode(errors="replace")
            + found.stderr.decode(errors="replace")
            for value in fake
        ):
            raise SystemExit("Secret scanner redaction check failed")
    print("PASS: clean fixture, three synthetic credential rules, redacted output")


if __name__ == "__main__":
    main()
