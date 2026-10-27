"""Offline regression for build-integrity boundaries; no scanner/network required."""

import json
import re
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]


def test_external_docker_bases_are_digest_pinned() -> None:
    for path in (
        ROOT / "apps/api/Dockerfile",
        ROOT / "infra/docker/web.Dockerfile",
        ROOT / "infra/docker/postgis.Dockerfile",
    ):
        stages = set()
        for line in path.read_text().splitlines():
            if not line.startswith("FROM "):
                continue
            parts = line.split()
            if parts[1] not in stages:
                assert re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", parts[1]), path.name
            if len(parts) == 4:
                stages.add(parts[3])


def test_docker_python_requirements_have_per_artifact_hashes() -> None:
    requirements = (ROOT / "apps/api/requirements.txt").read_text()
    blocks = re.findall(r"^[a-zA-Z0-9][^\n]*(?:\n[ \t]+[^\n]*)*", requirements, re.M)
    assert len(blocks) > 20
    assert all("==" in block and "--hash=sha256:" in block for block in blocks)
    assert "--require-hashes" in (ROOT / "apps/api/Dockerfile").read_text()


def test_ci_actions_have_commit_pins_and_read_only_permissions() -> None:
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        source = path.read_text()
        actions = re.findall(r"uses:\s*([^\s#]+)", source)
        assert actions
        assert all(re.fullmatch(r"[^\s]+@[a-f0-9]{40}", action) for action in actions)
        assert "contents: read" in source
        assert "pull_request_target" not in source
        assert "write-all" not in source
        assert "persist-credentials: false" in source


def test_secret_scope_keeps_frontend_build_and_first_party_files() -> None:
    import tomllib

    config = tomllib.loads((ROOT / ".gitleaks-dir.toml").read_text())
    exclusions = [
        re.compile(pattern) for entry in config["allowlists"] for pattern in entry["paths"]
    ]
    for path in (
        ".env",
        "apps/web/dist/assets/app.js",
        "tests/fixture.json",
        "apps/api/app/main.py",
    ):
        assert not any(pattern.search(path) for pattern in exclusions)
    assert config["extend"]["path"] == ".gitleaks.toml"
    strict = tomllib.loads((ROOT / ".gitleaks.toml").read_text())
    assert strict["extend"]["useDefault"] is True
    assert "allowlists" not in strict
    assert not (ROOT / ".gitleaksignore").exists()


def test_build_contexts_exclude_credentials_and_backups() -> None:
    for component in ("api", "web"):
        patterns = (ROOT / f"apps/{component}/.dockerignore").read_text().splitlines()
        for required in ("*.key", "*.pem", "*.age", "*.dump", ".git"):
            assert required in patterns
        assert any(pattern.startswith(".env") for pattern in patterns)


def test_locked_package_sources_are_public_and_credential_free() -> None:
    urls = []
    lock = tomllib.loads((ROOT / "apps/api/uv.lock").read_text())
    for package in lock["package"]:
        source = package.get("source", {})
        if set(source) != {"registry"} and not (
            source == {"virtual": "."} and package["name"] == "business-ai-api"
        ):
            raise AssertionError("Unapproved dependency source kind; inspect lock privately")
        if "registry" in package.get("source", {}):
            urls.append(package["source"]["registry"])
        urls.extend(item["url"] for item in package.get("wheels", []))
        if "sdist" in package:
            urls.append(package["sdist"]["url"])
    npm = json.loads((ROOT / "apps/web/package-lock.json").read_text())
    urls.extend(p["resolved"] for p in npm["packages"].values() if "resolved" in p)
    for value in urls:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or url.username
            or url.password
            or url.query
            or url.hostname not in {"pypi.org", "files.pythonhosted.org", "registry.npmjs.org"}
        ):
            raise AssertionError("Unapproved package source; inspect lock privately")
