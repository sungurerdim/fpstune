#!/usr/bin/env python3
"""Build script for creating fpstune Windows executable."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def check_requirements() -> bool:
    """Check if build requirements are installed."""
    try:
        import PyInstaller

        return True
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        return True


def clean_build() -> None:
    """Clean previous build artifacts."""
    project_root = Path(__file__).parent.parent

    dirs_to_clean = ["build", "dist", "__pycache__"]

    for dir_name in dirs_to_clean:
        dir_path = project_root / dir_name
        if dir_path.exists():
            print(f"Removing {dir_path}")
            shutil.rmtree(dir_path)

    # Remove .pyc files
    for pyc in project_root.rglob("*.pyc"):
        pyc.unlink()


def build_exe() -> bool:
    """Build the executable using PyInstaller."""
    project_root = Path(__file__).parent.parent
    spec_file = project_root / "fpstune.spec"

    if not spec_file.exists():
        print(f"Spec file not found: {spec_file}")
        return False

    print("Building fpstune executable...")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            str(spec_file),
        ],
        cwd=str(project_root),
    )

    if result.returncode != 0:
        print("Build failed!")
        return False

    # Check if exe was created
    exe_path = project_root / "dist" / "fpstune.exe"
    if exe_path.exists():
        print(f"\nBuild successful!")
        print(f"Executable: {exe_path}")
        print(f"Size: {exe_path.stat().st_size / (1024 * 1024):.1f} MB")
        return True
    else:
        print("Build completed but executable not found!")
        return False


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("fpstune Windows Executable Builder")
    print("=" * 60)

    if sys.platform != "win32":
        print("\nWarning: Building on non-Windows platform.")
        print("The resulting executable should be built on Windows for best results.")

    # Check requirements
    print("\nChecking requirements...")
    if not check_requirements():
        return 1

    # Clean previous builds
    print("\nCleaning previous builds...")
    clean_build()

    # Build
    print("\nBuilding executable...")
    if not build_exe():
        return 1

    print("\n" + "=" * 60)
    print("Build complete!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
