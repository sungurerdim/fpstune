"""Pytest configuration and fixtures for fpstune tests."""

from __future__ import annotations

import glob
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# --- User-profile roots: nothing in a test may reach the real profile (#104) ---
#
# On 2026-10-06 a sweep applying every setting rewrote the developer's real Call
# of Duty options file and Battle.net.config, because only USERPROFILE was
# redirected and the writers read %LOCALAPPDATA% and %APPDATA%. This block runs
# before any fpstune import, so module-level constants that resolve a root at
# import (headroom.json) land in a throwaway tree too. Each test then gets its
# own tree (`_isolated_profile`), and the real files' modification times are a
# backstop (`_real_profile_untouched`): metadata only, no content is ever read.
_REAL_PROFILE_MARK = "FPSTUNE_TEST_REAL_PROFILE"
_ROOT_VARIABLES = ("LOCALAPPDATA", "APPDATA", "USERPROFILE")

if _REAL_PROFILE_MARK in os.environ:
    # A pytest-xdist worker inherits the controller's already-redirected
    # environment; the real roots travel in the mark instead.
    REAL_PROFILE_ROOTS: dict[str, str] = json.loads(os.environ[_REAL_PROFILE_MARK])
else:
    REAL_PROFILE_ROOTS = {
        name: os.environ[name] for name in _ROOT_VARIABLES if os.environ.get(name)
    }
    os.environ[_REAL_PROFILE_MARK] = json.dumps(REAL_PROFILE_ROOTS)


def _point_roots_at(home: Path) -> None:
    """Send every user-profile root of this process into ``home``."""
    local = home / "AppData" / "Local"
    roaming = home / "AppData" / "Roaming"
    local.mkdir(parents=True, exist_ok=True)
    roaming.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    os.environ["LOCALAPPDATA"] = str(local)
    os.environ["APPDATA"] = str(roaming)


_SESSION_PROFILE = tempfile.TemporaryDirectory(prefix="fpstune-test-profile-")
_point_roots_at(Path(_SESSION_PROFILE.name))


def _real_profile_files() -> list[Path]:
    """The real files a writer in this product could rewrite, found by their own globs."""
    files: list[Path] = []
    local = REAL_PROFILE_ROOTS.get("LOCALAPPDATA")
    roaming = REAL_PROFILE_ROOTS.get("APPDATA")
    home = REAL_PROFILE_ROOTS.get("USERPROFILE")
    if local:
        game = Path(local) / "Activision" / "Call of Duty"
        for pattern in ("players*/s.*.cod26*.txt", "players*/*/g.*.cod26.[0-9]*.l.txt"):
            files.extend(Path(m) for m in glob.glob(str(game / pattern)))
    if roaming:
        files.append(Path(roaming) / "Battle.net" / "Battle.net.config")
    if home:
        files.append(Path(home) / ".fpstune" / "headroom.json")
    return files


_REAL_FILES = _real_profile_files()


def _stamps() -> dict[Path, int | None]:
    stamps: dict[Path, int | None] = {}
    for path in _REAL_FILES:
        try:
            stamps[path] = path.stat().st_mtime_ns
        except OSError:
            stamps[path] = None
    return stamps


from fpstune.settings.applicability import HardwareContext  # noqa: E402

# Mock Windows-specific modules when running on non-Windows
if sys.platform != "win32":
    # mimetypes binds winreg at import time and walks it on first use; importing
    # it before the stub keeps it off the registry path it cannot have here.
    import mimetypes

    mimetypes.init()
    sys.modules["winreg"] = MagicMock()
    # Mock subprocess.CREATE_NO_WINDOW for non-Windows
    if not hasattr(__import__("subprocess"), "CREATE_NO_WINDOW"):
        import subprocess

        subprocess.CREATE_NO_WINDOW = 0x08000000


@pytest.fixture(autouse=True, scope="session")
def _operation_lock_per_process() -> None:
    """Each test process takes its own operation lock, never the machine's.

    The lock is a machine-wide named mutex on purpose: one apply, cleanup or
    bench at a time. The suite runs in parallel worker processes, so under the
    shipped name a test in one worker holding the lock read as "the machine is
    busy" to a bench test in another, and three suite-route tests went red. A
    running fpstune on the developer's machine would do the same.
    """
    import os

    from fpstune.benchmark import operation_lock

    operation_lock.OPERATION_MUTEX = f"{operation_lock.OPERATION_MUTEX}-test-{os.getpid()}"


@pytest.fixture(autouse=True)
def _no_real_shell_folders(monkeypatch: pytest.MonkeyPatch) -> None:
    """Game config paths come from the test, never from the runner's own profile.

    The product reads the console user's Shell Folders first, so a test that
    builds a fake install under a temporary %LOCALAPPDATA% would otherwise be
    pointed at the real one on a Windows runner.
    """
    from fpstune.settings.executors import game_config_cache

    monkeypatch.setattr(game_config_cache, "_console_user_folder", lambda _name: None)


@pytest.fixture
def windows_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let Windows-gated pure-Python logic run on a development host.

    Game config files are plain text rewritten in Python, but every reader and
    writer answers "not installed" off Windows. A test that builds its install
    under ``tmp_path`` asks for this fixture to exercise that logic anyway.

    On Windows it does nothing, so the real system mutex stays under test there.
    Elsewhere it fakes the platform and sends ``file_lock`` to its documented
    process-local fallback, because kernel32 does not exist to be called.
    """
    if sys.platform == "win32":
        return
    # Imported against the real platform first: the power definitions adopt
    # Windows' own defaults from the registry at import, and a faked platform
    # would send that one-time read to the winreg stub above.
    from fpstune.settings.definitions import get_all_static_settings
    from fpstune.settings.executors import game_config_writer

    get_all_static_settings()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(game_config_writer, "_take_system_mutex", lambda _name: None)


@pytest.fixture(autouse=True)
def _isolated_profile(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every test gets its own user profile, never the runner's.

    `utils.user_paths` resolves every root (home, %LOCALAPPDATA%, %APPDATA%,
    ~/.fpstune) at call time, and the suite drives the real apply, scan and
    bench paths: without this, a run wrote bench results, the self-check and
    game config lines into the developer's own profile, and read them back in
    the next test. The process-wide stores are dropped too, so none carries one
    test's state into another.

    The helper is also wrapped so that a root which resolves to the real profile
    fails the test at the moment it is handed out: a test that un-redirects a
    variable is refused before anything is written.
    """
    from fpstune.safety import history
    from fpstune.settings import cleanup_targets, performance_headroom
    from fpstune.utils import user_paths

    home = tmp_path_factory.mktemp("home")
    # monkeypatch.setenv registers the restore; _point_roots_at assigns.
    for name in ("HOME", *_ROOT_VARIABLES):
        monkeypatch.setenv(name, os.environ[name])
    _point_roots_at(home)
    monkeypatch.setattr(history, "_journal", None)
    monkeypatch.setattr(performance_headroom, "HEADROOM_PATH", home / ".fpstune" / "headroom.json")
    # Documents is read from the registry on Windows, which the env redirect
    # cannot reach; the profile fallback is the redirected one.
    monkeypatch.setattr(cleanup_targets, "_documents_dir", lambda: str(home / "Documents"))

    real = {os.path.normcase(os.path.normpath(v)) for v in REAL_PROFILE_ROOTS.values()}
    resolve = user_paths.profile_env

    def guarded(name: str) -> str | None:
        value = resolve(name)
        if value is not None and os.path.normcase(os.path.normpath(value)) in real:
            raise AssertionError(f"{name} resolves to the real user profile: {value}")
        return value

    monkeypatch.setattr(user_paths, "profile_env", guarded)


@pytest.fixture(autouse=True)
def _real_profile_untouched():
    """Backstop: fail the test during which a real game or launcher file changed."""
    before = _stamps()
    yield
    changed = [str(path) for path, stamp in _stamps().items() if stamp != before[path]]
    assert not changed, f"a test touched the real user profile: {changed}"


@pytest.fixture(autouse=True)
def _quiet_logging():
    """Reduce logging noise during tests."""
    # Save original levels
    root_level = logging.root.level
    fpstune_logger = logging.getLogger("fpstune")
    fpstune_level = fpstune_logger.level

    # Set to WARNING to reduce noise
    logging.root.setLevel(logging.WARNING)
    fpstune_logger.setLevel(logging.WARNING)

    yield

    # Restore original levels
    logging.root.setLevel(root_level)
    fpstune_logger.setLevel(fpstune_level)


@pytest.fixture
def test_client():
    """Create FastAPI TestClient."""
    from fastapi.testclient import TestClient

    from fpstune.api.main import app

    return TestClient(app)


def neutral_hardware_context() -> HardwareContext:
    """The context of a machine nothing was detected on, and no guard is up.

    What a test hands to a patched `_get_hardware_context`: production never
    returns None there, so a stub that does exercises a state it cannot reach.
    Every field is its default, which `ApplicabilityChecker` reads as "nothing
    known"; a setting with no `applicable_conditions` is applicable against it,
    and a test that needs a condition met states it by building its own context.
    """
    return HardwareContext()
