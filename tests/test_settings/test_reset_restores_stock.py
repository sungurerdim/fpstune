"""Reset puts Windows' own state back — not an approximation of it."""

from __future__ import annotations

import os
import time

from fpstune.settings.cleanup_targets import CLEANUP_TARGETS, _dir_bytes, delete_arguments
from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.settings.registry import SettingsRegistry


def _registry() -> SettingsRegistry:
    return SettingsRegistry(discover_dynamic=False)


class TestServices:
    def test_reset_sets_the_stock_start_type_not_manual(self) -> None:
        script = ACTION_COMMANDS["service_toggle"]
        assert "StartupType Manual" not in script
        assert "start= $mode" in script

    def test_every_service_names_its_stock_start_type(self) -> None:
        for setting in _registry().get_all():
            if setting.apply_command == "service_toggle":
                assert setting.apply_args.get("start_mode") in ("auto", "delayed-auto", "demand"), (
                    setting.id
                )

    def test_the_search_indexer_returns_to_delayed_start(self) -> None:
        setting = _registry().get("services:WSearch")
        assert setting is not None
        assert setting.apply_args["start_mode"] == "delayed-auto"

    def test_mmcss_is_read_as_the_driver_it_is(self) -> None:
        """Get-Service never lists mmcss.sys, so the guard was invisible."""
        setting = _registry().get("services:MMCSS")
        assert setting is not None
        assert setting.detect_args["path"].endswith(r"Services\MMCSS")
        assert setting.apply_value_map == {"enabled": 2, "disabled": 4}


class TestCoreIsolationIsNeverWritten:
    def test_it_is_an_advisory(self) -> None:
        setting = _registry().get("system:vbs_core_isolation")
        assert setting is not None
        assert setting.is_readonly is True
        assert setting.apply_value_map == {}


class TestTempKeepsWhatRunningProgramsOwn:
    def test_the_one_file_unpack_folder_and_recent_entries_are_kept(self, tmp_path) -> None:
        target = CLEANUP_TARGETS["temp"]
        (tmp_path / "_MEI12345").mkdir()
        (tmp_path / "_MEI12345" / "index.html").write_bytes(b"x" * 100)
        (tmp_path / "fresh.log").write_bytes(b"x" * 10)
        old = tmp_path / "old.log"
        old.write_bytes(b"x" * 1000)
        stale = time.time() - 3 * 24 * 3600
        os.utime(old, (stale, stale))

        assert _dir_bytes(str(tmp_path), target) == 1000

    def test_the_delete_is_given_the_same_filter(self) -> None:
        args = delete_arguments(CLEANUP_TARGETS["temp"])
        assert "_MEI*" in args["keep_names"]
        assert args["keep_recent_hours"] == "24"
