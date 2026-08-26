#!/usr/bin/env python3
"""Build script for complete fpstune release package."""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_command(cmd: list[str], cwd: Path | None = None) -> bool:
    """Run a command and return success status."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode == 0


def _npm() -> str | None:
    """The npm this machine actually has, or None.

    On Windows npm is `npm.cmd`, and `subprocess.run(["npm", ...])` without a
    shell raises WinError 2 rather than running it. That is not hypothetical:
    this script swallowed exactly that error and built an executable around a
    three-day-old UI bundle, reporting success the whole way.
    """
    return shutil.which("npm")


def build_frontend(project_root: Path) -> bool:
    """Build the React frontend."""
    frontend_dir = project_root / "frontend"

    if not frontend_dir.exists():
        print("Frontend directory not found")
        return False

    print("\n" + "=" * 40)
    print("Building Frontend")
    print("=" * 40)

    npm = _npm()
    if npm is None:
        print("npm not found on PATH — install Node.js, or pass --skip-frontend")
        return False

    # Install dependencies
    if not run_command([npm, "install"], cwd=frontend_dir):
        print("Failed to install npm dependencies")
        return False

    # Build
    if not run_command([npm, "run", "build"], cwd=frontend_dir):
        print("Failed to build frontend")
        return False

    return True


def build_python_package(project_root: Path) -> bool:
    """Build the Python package."""
    print("\n" + "=" * 40)
    print("Building Python Package")
    print("=" * 40)

    # Build wheel
    if not run_command([sys.executable, "-m", "build"], cwd=project_root):
        print("Failed to build Python package")
        return False

    return True


def build_exe(project_root: Path) -> bool:
    """Build the Windows executable."""
    print("\n" + "=" * 40)
    print("Building Windows Executable")
    print("=" * 40)

    build_script = project_root / "scripts" / "build_exe.py"

    if not run_command([sys.executable, str(build_script)], cwd=project_root):
        print("Failed to build executable")
        return False

    return True


def run_tests(project_root: Path) -> bool:
    """Run the test suite."""
    print("\n" + "=" * 40)
    print("Running Tests")
    print("=" * 40)

    if not run_command([sys.executable, "-m", "pytest", "-v"], cwd=project_root):
        print("Tests failed!")
        return False

    return True


def create_release_package(project_root: Path) -> bool:
    """Create the release package."""
    print("\n" + "=" * 40)
    print("Creating Release Package")
    print("=" * 40)

    dist_dir = project_root / "dist"
    release_dir = dist_dir / "release"

    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True)

    # Copy executable. Its absence is a failed build, not an empty release.
    exe_path = dist_dir / "fpstune.exe"
    if not exe_path.exists():
        print(f"No executable at {exe_path} — nothing to package")
        return False
    shutil.copy(exe_path, release_dir)
    print("Copied: fpstune.exe")

    # Copy README
    readme_path = project_root / "README.md"
    if readme_path.exists():
        shutil.copy(readme_path, release_dir)
        print("Copied: README.md")

    # Create version file
    from fpstune import __version__

    version_file = release_dir / "VERSION"
    version_file.write_text(f"{__version__}\n")
    print("Created: VERSION")

    # Create zip archive
    timestamp = datetime.now().strftime("%Y%m%d")
    zip_name = f"fpstune-{__version__}-{timestamp}"
    zip_path = dist_dir / zip_name

    shutil.make_archive(str(zip_path), "zip", release_dir)
    print(f"\nRelease package: {zip_path}.zip")

    return True


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("fpstune Complete Build Script")
    print("=" * 60)
    print(f"Started: {datetime.now().isoformat()}")

    project_root = Path(__file__).parent.parent

    # Add src to path for imports
    sys.path.insert(0, str(project_root / "src"))

    # Run tests first
    if "--skip-tests" not in sys.argv and not run_tests(project_root):
        print("\nBuild aborted due to test failures")
        return 1

    # Build the frontend, and stop if it fails.
    #
    # This used to swallow the failure and carry on. The consequence is worse
    # than a missing UI: `fpstune.spec` refuses to build with no `frontend/dist`
    # at all, so a *stale* one is the only case that gets through — and it gets
    # through silently, shipping an executable that starts, works, and shows the
    # interface from whenever the last successful build happened.
    if "--skip-frontend" not in sys.argv and not build_frontend(project_root):
        print("\nBuild aborted: the UI is served from inside the executable")
        return 1

    # Build Python package
    if "--skip-package" not in sys.argv:
        try:
            build_python_package(project_root)
        except Exception as e:
            print(f"Package build skipped: {e}")

    # Build executable
    if "--skip-exe" not in sys.argv and not build_exe(project_root):
        print("\nExecutable build failed")
        return 1

    # Create release package
    if not create_release_package(project_root):
        print("\nRelease package creation failed")
        return 1

    print("\n" + "=" * 60)
    print("Build Complete!")
    print("=" * 60)
    print(f"Finished: {datetime.now().isoformat()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
