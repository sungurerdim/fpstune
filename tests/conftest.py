"""Pytest configuration and fixtures for fpstune tests."""

from __future__ import annotations

import logging
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Mock Windows-specific modules when running on non-Windows
if sys.platform != "win32":
    sys.modules["winreg"] = MagicMock()
    # Mock subprocess.CREATE_NO_WINDOW for non-Windows
    if not hasattr(__import__("subprocess"), "CREATE_NO_WINDOW"):
        import subprocess

        subprocess.CREATE_NO_WINDOW = 0x08000000


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
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_subprocess() -> Generator[MagicMock, None, None]:
    """Mock subprocess calls."""
    with patch("subprocess.run") as mock:
        mock.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        yield mock


@pytest.fixture
def mock_admin() -> Generator[MagicMock, None, None]:
    """Mock admin check to always return True."""
    with patch("fpstune.utils.admin.is_admin") as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def sample_config() -> dict:
    """Sample configuration for tests."""
    return {
        "profile": "balanced",
        "modules": {
            "timer": {
                "enabled": True,
                "hpet": "disabled",
                "dynamic_tick": "default",
                "resolution_ms": 0.5,
            },
            "game": {
                "enabled": True,
                "game_mode": "enabled",
                "game_bar": "disabled",
                "hags": "enabled",
            },
            "services": {
                "disable": ["SysMain", "DiagTrack"],
            },
            "priority": {
                "gpu_priority": 8,
                "game_priority": 6,
                "system_responsiveness": 0,
            },
        },
        "safety": {
            "create_restore_point": True,
            "backup_registry": True,
        },
    }


@pytest.fixture
def mock_os_info():
    """Mock OS info for tests."""
    with patch("fpstune.utils.detect.get_os_info") as mock:
        mock.return_value = MagicMock(
            platform="win32",
            version="10.0.22621",
            build="22621",
            edition="Windows 11 Pro",
            is_windows_10=False,
            is_windows_11=True,
            is_supported=True,
        )
        yield mock


@pytest.fixture
def mock_gpu_info():
    """Mock GPU info for tests."""
    with patch("fpstune.utils.detect.get_gpu_info") as mock:
        from fpstune.utils.detect import GpuVendor

        mock.return_value = MagicMock(
            vendor=GpuVendor.NVIDIA,
            name="NVIDIA GeForce RTX 4080",
            driver_version="555.42",
            vram_mb=16384,
        )
        yield mock


@pytest.fixture
def mock_platform_windows() -> Generator[MagicMock, None, None]:
    """Mock sys.platform to return win32."""
    with patch("sys.platform", "win32"):
        yield MagicMock()


@pytest.fixture
def mock_bcdedit() -> Generator[MagicMock, None, None]:
    """Mock BcdEdit subprocess calls."""
    with patch("subprocess.run") as mock:
        # Default: bcdedit commands succeed
        mock.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        yield mock


@pytest.fixture
def mock_bcdedit_values() -> Generator[MagicMock, None, None]:
    """Mock BcdEdit with sample values for enum."""
    with patch("subprocess.run") as mock:

        def mock_bcdedit(*args: Any, **_kwargs: Any) -> MagicMock:
            cmd = args[0] if args else []
            result = MagicMock(returncode=0, stdout="", stderr="")

            if "/enum" in cmd:
                result.stdout = """
Windows Boot Loader
-------------------
identifier              {current}
useplatformclock        No
disabledynamictick      Yes
"""
            return result

        mock.side_effect = mock_bcdedit
        yield mock


@pytest.fixture
def mock_powershell() -> Generator[MagicMock, None, None]:
    """Mock PowerShell execution."""
    with patch("subprocess.run") as mock:
        mock.return_value = MagicMock(
            returncode=0,
            stdout="Success",
            stderr="",
        )
        yield mock


@pytest.fixture
def mock_netsh() -> Generator[MagicMock, None, None]:
    """Mock netsh network commands."""
    with patch("subprocess.run") as mock:

        def mock_netsh(*args: Any, **_kwargs: Any) -> MagicMock:
            cmd = args[0] if args else []
            result = MagicMock(returncode=0, stdout="", stderr="")

            if "interface" in cmd and "show" in cmd:
                result.stdout = """
Querying active state...

TCP Global Parameters
----------------------------------------------
Receive-Side Scaling State          : enabled
Chimney Offload State               : automatic
NetDMA State                        : enabled
"""
            return result

        mock.side_effect = mock_netsh
        yield mock


@pytest.fixture
def test_client():
    """Create FastAPI TestClient."""
    from fastapi.testclient import TestClient

    from fpstune.api.main import app

    return TestClient(app)


@pytest.fixture
def sample_module_status() -> dict[str, Any]:
    """Sample module status response."""
    return {
        "name": "timer",
        "display_name": "Timer Resolution",
        "description": "Optimize system timer settings",
        "status": "not_applied",
        "is_available": True,
        "requires_reboot": True,
        "message": "",
        "details": [],
        "settings": [
            {
                "name": "hpet",
                "display_name": "HPET (High Precision Event Timer)",
                "description": "Platform timer setting",
                "current_value": "enabled",
                "recommended_value": "disabled",
                "default_value": "enabled",
                "value_type": "choice",
                "choices": ["enabled", "disabled"],
                "requires_reboot": True,
                "is_action": False,
            }
        ],
    }


@pytest.fixture
def sample_detection_response() -> dict[str, Any]:
    """Sample category detection response."""
    return {
        "category": "core",
        "modules": {
            "timer": {
                "hpet": "disabled",
                "dynamic_tick": "disabled",
                "resolution_ms": 0.5,
            },
            "priority": {
                "gpu_priority": 8,
                "system_responsiveness": 0,
            },
        },
        "detection_time_ms": 150,
    }


@pytest.fixture
def mock_nvidia_available() -> Generator[MagicMock, None, None]:
    """Mock NVIDIA GPU as available."""
    with patch("fpstune.utils.detect.get_gpu_info") as mock:
        from fpstune.utils.detect import GpuVendor

        mock.return_value = MagicMock(
            vendor=GpuVendor.NVIDIA,
            name="NVIDIA GeForce RTX 4080",
            driver_version="555.42",
            vram_mb=16384,
        )
        yield mock


@pytest.fixture
def mock_amd_available() -> Generator[MagicMock, None, None]:
    """Mock AMD GPU as available."""
    with patch("fpstune.utils.detect.get_gpu_info") as mock:
        from fpstune.utils.detect import GpuVendor

        mock.return_value = MagicMock(
            vendor=GpuVendor.AMD,
            name="AMD Radeon RX 7900 XTX",
            driver_version="24.3.1",
            vram_mb=24576,
        )
        yield mock


@pytest.fixture
def mock_no_gpu() -> Generator[MagicMock, None, None]:
    """Mock no GPU detected."""
    with patch("fpstune.utils.detect.get_gpu_info") as mock:
        mock.return_value = None
        yield mock
