"""Record locked versions and installed license evidence; never reads environment values."""

import hashlib
import json
import re
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def license_file(path: str) -> bool:
    return bool(
        re.match(r"(?i)^(licen[cs]e|copying|notice)([.\-_].*)?$", Path(path).name)
    )


def main() -> None:
    python = []
    python_notices = ["Business AI: provided Python dependency license notices.\n"]
    runtime = set(
        re.findall(
            r"^([a-zA-Z0-9_-]+)==",
            (ROOT / "apps/api/requirements.txt").read_text(),
            re.MULTILINE,
        )
    )
    lock = tomllib.loads((ROOT / "apps/api/uv.lock").read_text())
    for package in lock["package"]:
        name, version = package["name"], package["version"]
        item = {
            "name": name,
            "version": version,
            "runtime": name in runtime,
            "source": package.get("source"),
            "license_status": "not_installed",
        }
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            python.append(item)
            continue
        if dist.version != version:
            raise SystemExit("Installed Python version differs from lock: " + name)
        texts = []
        files = []
        for file in dist.files or []:
            if license_file(str(file)):
                raw = dist.locate_file(file).read_bytes()
                files.append(
                    {"file": str(file).replace("\\", "/"), "sha256": digest(raw)}
                )
                texts.append(raw.decode("utf8", errors="replace"))
        item.update(
            license=dist.metadata.get("License-Expression")
            or dist.metadata.get("License"),
            license_files=files,
            license_status="installed_text" if files else "metadata_only",
        )
        python.append(item)
        if name in runtime:
            python_notices.append(
                f"\n{'=' * 60}\n{name} {version}\n" + "\n".join(texts)
            )

    npm = []
    web_notices = [
        "Business AI: provided browser runtime dependency license notices.\n"
    ]
    npm_lock = json.loads((ROOT / "apps/web/package-lock.json").read_text())
    for location, package in sorted(npm_lock["packages"].items()):
        if not location:
            continue
        folder = ROOT / "apps/web" / location
        files = []
        texts = []
        installed = folder / "package.json"
        if installed.exists():
            data = json.loads(installed.read_text(encoding="utf8"))
            if data["version"] != package["version"]:
                raise SystemExit("Installed npm version differs from lock: " + location)
            for path in sorted(folder.iterdir()):
                if path.is_file() and license_file(path.name):
                    raw = path.read_bytes()
                    files.append({"file": path.name, "sha256": digest(raw)})
                    texts.append(raw.decode("utf8", errors="replace"))
        runtime_package = not package.get("dev", False)
        name = location.split("node_modules/")[-1]
        if name == "murmurhash-js" and installed.exists() and not texts:
            readme = (folder / "README.md").read_text(encoding="utf8")
            marker = "## License (MIT)"
            if marker not in readme:
                raise SystemExit("Expected embedded murmurhash-js license is missing")
            text = readme[readme.index(marker) :]
            texts.append(text)
            files.append({"file": "README.md#License", "sha256": digest(text.encode())})
        npm.append(
            {
                "name": name,
                "version": package["version"],
                "runtime": runtime_package,
                "source": package.get("resolved"),
                "integrity": package.get("integrity"),
                "license": package.get("license"),
                "license_files": files,
                "license_status": "installed_text"
                if files
                else "registry_metadata_only",
            }
        )
        if runtime_package:
            web_notices.append(
                f"\n{'=' * 60}\n{name} {package['version']}\n" + "\n".join(texts)
            )
    result = {
        "schema_version": 1,
        "python": python,
        "npm": npm,
        "limitations": "Provided texts and metadata are evidence, not a legal compatibility opinion. Conditional/uninstalled packages and bundled native libraries need separate review.",
    }
    (ROOT / "docs/qa/H-06-dependencies.json").write_text(
        json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf8"
    )
    (ROOT / "apps/api/THIRD_PARTY_NOTICES.txt").write_text(
        "\n".join(python_notices), encoding="utf8"
    )
    public = ROOT / "apps/web/public"
    public.mkdir(exist_ok=True)
    (public / "THIRD_PARTY_NOTICES.txt").write_text(
        "\n".join(web_notices), encoding="utf8"
    )
    print(f"Inventoried {len(python)} Python lock entries and {len(npm)} npm entries")


if __name__ == "__main__":
    main()
