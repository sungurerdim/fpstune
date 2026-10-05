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
