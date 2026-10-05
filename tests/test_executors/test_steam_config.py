"""Steam's config files are edited in-process, one value, nothing else touched.

The PowerShell writer this replaces — an elevated script reading config.vdf byte
by byte — is what Defender's ML heuristic flagged as Trojan:Win32/Bearfoos.A!ml.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from fpstune.settings.applicability import NOT_INSTALLED
from fpstune.settings.executors import steam_config

CONFIG = '"InstallConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"AllowDownloadsDuringGameplay"\t\t"1"\n\t\t\t\t"Other"\t\t"x"\n\t\t\t}\n\t\t}\n\t}\n}\n'


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.vdf").write_bytes(b"\xef\xbb\xbf" + CONFIG.encode())
    return tmp_path


def _text(root: Path) -> bytes:
    return (root / "config" / "config.vdf").read_bytes()


def test_an_existing_key_changes_and_nothing_else(root: Path) -> None:
    steam_config.write_raw("config", "AllowDownloadsDuringGameplay", "0", root)
    after = _text(root)
    assert after.startswith(b"\xef\xbb\xbf"), "the BOM Steam wrote is kept"
    assert (
        after == b"\xef\xbb\xbf" + CONFIG.replace('Gameplay"\t\t"1"', 'Gameplay"\t\t"0"').encode()
    )


def test_a_missing_key_is_added_under_the_steam_block(root: Path) -> None:
    steam_config.write_raw("config", "DownloadThrottleKbps", "-1", root)
    assert steam_config.read_raw("config", "DownloadThrottleKbps", root) == "-1"
    assert steam_config.read_raw("config", "Other", root) == "x"


def test_a_value_that_would_break_the_file_is_refused(root: Path) -> None:
    before = _text(root)
    with pytest.raises(ValueError, match="break the file"):
        steam_config.write_raw("config", "Other", 'x"\n"Injected" "1', root)
    assert _text(root) == before


def test_the_newest_users_localconfig_is_the_one_read(tmp_path: Path) -> None:
    import os

    for user, mtime in (("111", 1_000), ("222", 2_000)):
        folder = tmp_path / "userdata" / user / "config"
        folder.mkdir(parents=True)
        (folder / "localconfig.vdf").write_text(
            f'"system"\n{{\n\t"EnableGameOverlay"\t"{user}"\n}}\n'
        )
        os.utime(folder / "localconfig.vdf", (mtime, mtime))
    assert steam_config.read_raw("localconfig", "EnableGameOverlay", tmp_path) == "222"


class TestTheDetectorAnswersInTheSettingsOwnWords:
    ARGS = {
        "scope": "config",
        "key": "DownloadThrottleKbps",
        "map": {"-1": "unlimited", "0": "unlimited"},
        "otherwise": "limited",
        "absent": "unlimited",
    }

    def _read(self, root: Path | None) -> str:
        with patch.object(steam_config, "steam_root", return_value=root):
            return steam_config.steam_vdf_read(self.ARGS)

    def test_absent_key_is_steams_default(self, root: Path) -> None:
        assert self._read(root) == "unlimited"

    def test_an_unlisted_value_is_the_other_choice(self, root: Path) -> None:
        steam_config.write_raw("config", "DownloadThrottleKbps", "10240", root)
        assert self._read(root) == "limited"

    def test_no_steam_is_not_installed(self) -> None:
        assert self._read(None) == NOT_INSTALLED


def test_every_steam_setting_goes_through_python() -> None:
    from fpstune.settings.definitions.launchers import LAUNCHER_SETTINGS

    vdf = [s for s in LAUNCHER_SETTINGS if s.detect_command == "steam_vdf_read"]
    assert len(vdf) == 6
    assert all(s.apply_command == "steam_vdf_write" for s in vdf)
