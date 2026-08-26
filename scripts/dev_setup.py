"""Bootstrap a developer environment for fpstune.

Usage:
    python scripts/dev_setup.py

What it does:
    1. Verifies Python >= 3.11
    2. Installs Python deps from uv.lock if uv is available, otherwise
       falls back to ``pip install -e .[dev]``.
    3. Installs frontend node_modules via ``npm install``.
    4. Optionally installs lefthook git hooks (pre-commit) if available.
    5. Prints next-step commands for running tests and the dev server.

This script is intentionally idempotent: re-running is safe.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
MIN_PY = (3, 11)


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"$ {' '.join(cmd)} (cwd={cwd or REPO_ROOT})")
    result = subprocess.run(cmd, cwd=cwd or REPO_ROOT, check=False)
    return result.returncode


def check_python() -> None:
    if sys.version_info < MIN_PY:
        print(f"ERROR: Python {MIN_PY[0]}.{MIN_PY[1]}+ required, found {sys.version}")
        sys.exit(1)
    print(f"[ok] Python {sys.version.split()[0]}")


def install_python_deps() -> None:
    if shutil.which("uv"):
        print("[info] Using uv for fast resolution from uv.lock")
        if _run(["uv", "sync", "--frozen", "--extra", "dev"]) != 0:
            print("[warn] uv sync failed; falling back to pip")
        else:
            return
    print("[info] Falling back to pip install -e .[dev]")
    if _run([sys.executable, "-m", "pip", "install", "-e", ".[dev]"]) != 0:
        print("ERROR: pip install failed")
        sys.exit(2)


def install_frontend_deps() -> None:
    if not (FRONTEND_DIR / "package.json").exists():
        print("[skip] frontend/package.json not found")
        return
    if not shutil.which("npm"):
        print("[warn] npm not found; install Node.js to set up the frontend")
        return
    if _run(["npm", "install"], cwd=FRONTEND_DIR) != 0:
        print("ERROR: npm install failed")
        sys.exit(3)


def install_git_hooks() -> None:
    if not shutil.which("lefthook"):
        print("[skip] lefthook not installed (optional)")
        return
    _run(["lefthook", "install"])


def print_next_steps() -> None:
    print()
    print("Setup complete. Next steps:")
    print("  task serve              # start the FastAPI dev server")
    print("  task dev-frontend       # start the Vite dev server (in another terminal)")
    print("  task test-fast          # run Python tests without coverage")
    print("  task test-frontend      # run vitest suite")
    print("  task lint               # run ruff + mypy")
    print()
    print("(If `task` is not installed, see https://taskfile.dev/installation/)")


def main() -> None:
    check_python()
    install_python_deps()
    install_frontend_deps()
    install_git_hooks()
    print_next_steps()


if __name__ == "__main__":
    main()
