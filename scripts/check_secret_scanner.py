"""Offline positive/negative/redaction checks with synthetic, unusable credentials."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def check_history_scope(binary: str, policy: Path, root: Path) -> None:
    """Prove historical false-positive scope never hides another value/file/commit."""
    repo = root / "history"
    target = "apps/api/tests/integration/test_acquisition.py"
    value = "synthetic-" + "operator-fixture-32-characters"
    path = repo / target
    path.parent.mkdir(parents=True)
    path.write_text(
        'token = "' + value + '"\ntoken = "' + value[:-1] + 'Z"\n', encoding="utf8"
    )
    (repo / "other.py").write_text('token = "' + value + '"\n', encoding="utf8")
    hooks = root / "empty-hooks"
    hooks.mkdir()

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *arguments],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode:
            raise SystemExit("Secret scanner synthetic Git fixture failed")
        return result.stdout.strip()

    git("init", "--quiet")
    git("add", ".")
    git(
        "-c",
        "user.name=Scanner fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "-c",
        f"core.hooksPath={hooks.as_posix()}",
        "commit",
        "--quiet",
        "-m",
        "Unusable synthetic scope-control fixtures",
    )
    sha = git("rev-parse", "HEAD")
    historical = "c704abbd107e649f4e7c558deb982a3228ba19f0"
    config = policy.read_text(encoding="utf8")
    if config.count(historical) != 1:
        raise SystemExit("Historical fixture scope requires explicit review")
    for scoped in (False, True):
        fixture_config = root / ("scoped.toml" if scoped else "outside-commit.toml")
        fixture_config.write_text(
            config.replace(historical, sha) if scoped else config, encoding="utf8"
        )
        report = root / "scope-report.json"
        result = subprocess.run(
            [
                binary,
                "git",
                str(repo),
                "--config",
                str(fixture_config),
                "--redact=100",
                "--ignore-gitleaks-allow",
                "--no-banner",
                "--report-format",
                "json",
                "--report-path",
                str(report),
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        raw = report.read_text(encoding="utf8") if report.exists() else "[]"
        locations = {
            (e["File"], e["StartLine"])
            for e in json.loads(raw)
            if e["RuleID"] == "generic-api-key"
        }
        expected = {(target, 2), ("other.py", 1)}
        if not scoped:
            expected.add((target, 1))
        if result.returncode != 1 or locations != expected:
            raise SystemExit("Historical fixture scope hid another value/file/commit")
        output = (
            raw
            + result.stdout.decode(errors="replace")
            + result.stderr.decode(errors="replace")
        )
        if value in output or value[:-1] + "Z" in output:
            raise SystemExit("Historical fixture redaction failed")


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
        check_history_scope(args.binary, policy, root)
    print("PASS: clean/positive/redaction fixtures and exact historical scope controls")


if __name__ == "__main__":
    main()
