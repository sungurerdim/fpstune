"""Sync version from pyproject.toml (SSOT) to __init__.py and package.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


def read_pyproject_version() -> str:
    import tomllib

    with open(ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def sync_python_init(version: str) -> None:
    path = ROOT / "src" / "fpstune" / "__init__.py"
    text = path.read_text(encoding="utf-8")
    updated = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', text)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        print(f"Updated {path.relative_to(ROOT)}")
    else:
        print(f"Already up-to-date: {path.relative_to(ROOT)}")


def sync_package_json(version: str) -> None:
    path = ROOT / "frontend" / "package.json"
    pkg = json.loads(path.read_text(encoding="utf-8"))
    if pkg.get("version") == version:
        print(f"Already up-to-date: {path.relative_to(ROOT)}")
        return
    pkg["version"] = version
    path.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {path.relative_to(ROOT)}")


def main() -> None:
    version = read_pyproject_version()
    print(f"Version from pyproject.toml: {version}")
    sync_python_init(version)
    sync_package_json(version)
    print("Done.")


if __name__ == "__main__":
    main()
