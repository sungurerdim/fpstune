"""Pytest configuration and fixtures for fpstune tests."""

from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock

import pytest

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
def _isolated_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """Every test gets its own ~/.fpstune, never the runner's.

    `utils.config.get_config_dir` resolves the home directory at call time, and
    the suite drives the real apply, scan and bench paths: without this, a run
    wrote the change history, the undo record, bench results and the self-check
    into the developer's own profile — and read them back in the next test.
    The process-wide stores are dropped too, so none carries one test's state
    into another.
    """
    from fpstune.safety import history, originals

    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(history, "_journal", None)
    monkeypatch.setattr(originals, "_store", None)


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
