"""The release build must not ship an executable around a stale UI.

Measured 2026-08-25: `scripts/build_all.py` reported "Build Complete!" and
produced a 36 MB executable whose bundled interface was three days old. Two
mistakes lined up to make that possible, and both are pinned here:

* On Windows npm is `npm.cmd`, so `subprocess.run(["npm", ...])` without a shell
  raises `WinError 2` instead of running it.
* That exception was caught and printed as "Frontend build skipped".

The second is what makes the first invisible, and it is the worse of the two:
`fpstune.spec` refuses to build with no `frontend/dist` at all, so a *stale*
bundle is the only failure mode that gets through — and it gets through as a
binary that starts, works, and shows the wrong interface.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def build_all():
    """Load `scripts/build_all.py`, which is a script rather than a package."""
    spec = importlib.util.spec_from_file_location(
        "fpstune_build_all", ROOT / "scripts" / "build_all.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_npm_is_resolved_rather_than_assumed(build_all) -> None:
    """`shutil.which` finds `npm.cmd`; the bare name does not run on Windows."""
    resolved = build_all._npm()
    if resolved is None:
        pytest.skip("no npm on this machine — nothing to resolve")
    assert Path(resolved).exists()


def test_a_missing_npm_fails_the_frontend_build(build_all, monkeypatch) -> None:
    """Not "skipped": a machine without npm cannot produce a release."""
    monkeypatch.setattr(build_all, "_npm", lambda: None)

    assert build_all.build_frontend(ROOT) is False


def test_a_failed_frontend_build_aborts_the_whole_build(build_all, monkeypatch) -> None:
    """The regression itself: the executable must not be built after this.

    A non-zero exit is the contract. If this ever passes again by returning 0,
    the release goes out with whatever `frontend/dist` happened to hold.
    """
    monkeypatch.setattr(sys, "argv", ["build_all.py", "--skip-tests"])
    monkeypatch.setattr(build_all, "build_frontend", lambda _root: False)

    def unreachable(*_args, **_kwargs):  # pragma: no cover - the point is it never runs
        raise AssertionError("the executable was built after the frontend failed")

    monkeypatch.setattr(build_all, "build_exe", unreachable)
    monkeypatch.setattr(build_all, "create_release_package", unreachable)
    monkeypatch.setattr(build_all, "build_python_package", unreachable)

    assert build_all.main() == 1


def test_a_missing_executable_is_not_packaged_as_a_release(build_all, tmp_path) -> None:
    """An empty zip named after the version is worse than a failed build."""
    assert build_all.create_release_package(tmp_path) is False
    assert not list(tmp_path.glob("dist/*.zip"))
