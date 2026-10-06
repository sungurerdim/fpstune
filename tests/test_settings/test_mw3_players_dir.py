"""MW3's options live in one of two folders; the one the game last wrote wins.

The standalone install writes Documents/Call of Duty MWIII/players, a Call of
Duty HQ install writes Documents/Call of Duty/players. Pinned to the first, every
MW3 setting read "not installed" on an HQ machine — or edited a stale copy the
game no longer reads when both folders exist.
"""

from __future__ import annotations

import os
from pathlib import Path

from fpstune.settings.executors import game_config_cache as gcc
from fpstune.settings.executors.mw3_paths import MW3_OPTIONS_FILE, MW3_PLAYERS_PS
from fpstune.utils import user_paths


def _options(documents: Path, folder: str, mtime: float) -> Path:
    path = documents / folder / "players" / MW3_OPTIONS_FILE
    path.parent.mkdir(parents=True)
    path.write_text('ShadowQuality:0.0 = "Low"\n', encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_an_hq_only_install_is_found(tmp_path: Path) -> None:
    _options(tmp_path, "Call of Duty", 1_700_000_000)
    assert gcc.mw3_players_dir(tmp_path) == tmp_path / "Call of Duty" / "players"


def test_the_folder_written_last_wins(tmp_path: Path) -> None:
    _options(tmp_path, "Call of Duty MWIII", 1_700_000_000)
    _options(tmp_path, "Call of Duty", 1_700_100_000)
    assert gcc.mw3_players_dir(tmp_path) == tmp_path / "Call of Duty" / "players"


def test_the_standalone_folder_wins_when_newer(tmp_path: Path) -> None:
    _options(tmp_path, "Call of Duty MWIII", 1_700_100_000)
    _options(tmp_path, "Call of Duty", 1_700_000_000)
    assert gcc.mw3_players_dir(tmp_path) == tmp_path / "Call of Duty MWIII" / "players"


def test_no_install_is_none(tmp_path: Path) -> None:
    assert gcc.mw3_players_dir(tmp_path) is None


def test_powershell_probes_both_folders_by_write_time() -> None:
    # The detect commands and apply actions must make the same choice.
    assert "'Call of Duty MWIII\\players', 'Call of Duty\\players'" in MW3_PLAYERS_PS
    assert "LastWriteTimeUtc" in MW3_PLAYERS_PS


def test_no_shipped_mw3_command_pins_one_folder() -> None:
    from fpstune.settings.definitions.game_configs import GAME_CONFIG_SETTINGS
    from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

    pinned = "MWIII\\players\\options"
    for setting in GAME_CONFIG_SETTINGS:
        assert pinned not in setting.detect_command, setting.id
    for name, script in ACTION_COMMANDS.items():
        assert pinned not in script, name


def test_mw4_reads_the_console_users_local_app_data(tmp_path: Path, monkeypatch: object) -> None:
    # Elevated under another administrator, %LOCALAPPDATA% is that admin's,
    # which holds no MW4 config; the console user's Shell Folders entry is the
    # folder the game wrote.
    import pytest

    mp: pytest.MonkeyPatch = monkeypatch  # type: ignore[assignment]
    console = tmp_path / "console"
    console.mkdir()
    mp.setattr(gcc.sys, "platform", "win32")
    mp.setenv("LOCALAPPDATA", str(tmp_path / "elevated-admin"))
    mp.setattr(
        user_paths, "shell_folder", lambda name: console if name == "Local AppData" else None
    )
    assert gcc._local_app_data_dir() == console
