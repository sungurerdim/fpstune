"""PowerShell's module cache lands under %LOCALAPPDATA%, never in the working directory.

Observed: a full parallel scan left ``Microsoft\\Windows\\PowerShell\\ModuleAnalysisCache``
in the repository root, in about two runs of three of
``tests/test_api/test_detection.py::TestSettingsDetection::test_detect_settings``.
PowerShell 5.1 builds that path from ``GetFolderPath(LocalApplicationData)``, which
came back empty for some children, so the path turned relative. With
``PSModuleAnalysisCachePath`` pinned to an absolute path, five runs in a row left
nothing behind. For a user the working directory is wherever fpstune.exe was
started from, usually Downloads.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from fpstune.api.main import create_app
from fpstune.cli import main
from fpstune.utils.system_tools import MODULE_CACHE_VARIABLE, pin_powershell_module_cache


@pytest.fixture
def unpinned(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No cache path set; monkeypatch restores whatever the session had afterwards."""
    monkeypatch.delenv(MODULE_CACHE_VARIABLE, raising=False)
    return monkeypatch


def test_it_pins_the_stock_location_under_local_app_data(unpinned, tmp_path) -> None:
    local = tmp_path / "AppData" / "Local"
    unpinned.setenv("LOCALAPPDATA", str(local))

    pin_powershell_module_cache()

    assert os.environ[MODULE_CACHE_VARIABLE] == os.path.join(
        str(local), "Microsoft", "Windows", "PowerShell", "ModuleAnalysisCache"
    )


def test_a_path_the_user_already_set_is_kept(unpinned, tmp_path) -> None:
    chosen = str(tmp_path / "ps-cache" / "ModuleAnalysisCache")
    unpinned.setenv(MODULE_CACHE_VARIABLE, chosen)
    unpinned.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

    pin_powershell_module_cache()

    assert os.environ[MODULE_CACHE_VARIABLE] == chosen


@pytest.mark.parametrize("local", ["", "AppData\\Local"])
def test_no_absolute_folder_means_nothing_is_pinned(unpinned, local) -> None:
    """Pinning a relative path would reproduce the very leak this exists to stop."""
    unpinned.setenv("LOCALAPPDATA", local)

    pin_powershell_module_cache()

    assert MODULE_CACHE_VARIABLE not in os.environ


def test_missing_local_app_data_means_nothing_is_pinned(unpinned) -> None:
    unpinned.delenv("LOCALAPPDATA", raising=False)

    pin_powershell_module_cache()

    assert MODULE_CACHE_VARIABLE not in os.environ


def test_the_api_pins_it_before_any_route_can_start_powershell(unpinned, tmp_path) -> None:
    unpinned.setenv("LOCALAPPDATA", str(tmp_path))

    create_app()

    assert os.environ[MODULE_CACHE_VARIABLE].startswith(str(tmp_path))


@patch("fpstune.commands.utils.elevate_if_needed", return_value=False)
@patch("fpstune.commands.utils.is_admin", return_value=True)
@patch("fpstune.commands.gpu.get_gpu_info", return_value=None)
def test_the_cli_pins_it_before_any_command_runs(_gpu, _admin, _elevate, unpinned, tmp_path):
    """`gpu`, not `--help`: click answers --help before the group's own body runs."""
    unpinned.setenv("LOCALAPPDATA", str(tmp_path))

    result = CliRunner().invoke(main, ["gpu"])

    assert result.exit_code == 0
    assert os.environ[MODULE_CACHE_VARIABLE].startswith(str(tmp_path))
