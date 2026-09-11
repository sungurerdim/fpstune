"""The delete is handed the list the sizer walked, and it starts one process.

Two properties, both of them defects the audit measured on 2026-09-10:

  * every mismatch in its table was a second path list drifting from the first —
    `%TEMP%` walked twice and deleted once (109 MB shown, 54 MB there), a
    Battle.net cache deleted and never counted, a Prefetch subdirectory counted
    and never deletable. There is now one list and both halves are given it.
  * a cleanup Run spawned three PowerShell processes — before-size, delete,
    after-size — and process start, not folder walking, was most of what a scan
    cost: 6 759-10 551 ms for `powershell -NoProfile -Command exit` alone under
    load. For a folder target it is now one.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.cleanup_targets import (
    CLEANUP_TARGETS,
    EXTERNAL,
    CleanupTarget,
    UnsafePath,
    delete_arguments,
    resolved_paths,
)
from fpstune.settings.executors.powershell import PowerShellExecutor
from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS


def _cleanup_setting(cleanup_type: str, apply_command: str) -> SettingExecutor:
    return SettingExecutor(
        id=f"cleanup:{cleanup_type}",
        category=SettingCategory.MAINTENANCE,
        display_name="Cleanup",
        description="Files nothing came back for. Clearing them returns the space.",
        value_type=SettingValueType.BOOL,
        choices=(),
        default_value=False,
        recommended_value=True,
        is_action=True,
        detect_type=DetectType.POWERSHELL,
        detect_command="cleanup_status",
        detect_args={"type": cleanup_type},
        apply_type=DetectType.POWERSHELL,
        apply_command=apply_command,
    )


#: Every path-based cleanup and the command its setting names, read off the
#: shipped registry so a new one cannot be added without landing here too.
def _registered_pairs() -> list[tuple[str, str]]:
    from fpstune.settings.definitions import get_all_static_settings

    pairs = []
    for setting in get_all_static_settings():
        if setting.detect_command.strip() != "cleanup_status":
            continue
        cleanup_type = str(setting.detect_args.get("type", ""))
        target = CLEANUP_TARGETS.get(cleanup_type)
        if target is not None and target.delete_mode != EXTERNAL:
            pairs.append((cleanup_type, setting.apply_command.strip()))
    return pairs


class TestTheDeleteConsumesTheSizersList:
    @pytest.mark.parametrize(("cleanup_type", "command"), _registered_pairs())
    def test_every_path_cleanup_asks_for_the_list(self, cleanup_type: str, command: str) -> None:
        """A script that builds its own list is a second list, and it drifts."""
        assert "%paths%" in ACTION_COMMANDS[command], cleanup_type

    def test_the_command_receives_exactly_what_the_walk_measured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The same resolved paths, in the same order, in one argument."""
        first = tmp_path / "Cache"
        second = tmp_path / "Code Cache"
        first.mkdir()
        second.mkdir()
        target = CleanupTarget("pip_cache", lambda: [str(first), str(second)])
        monkeypatch.setitem(CLEANUP_TARGETS, "pip_cache", target)

        ran: list[str] = []

        def fake_run(cmd: str, timeout: int = 30) -> tuple[bool, str]:  # noqa: ARG001
            ran.append(cmd)
            return True, "done"

        with patch("fpstune.settings.executors.powershell.run_powershell", fake_run):
            ok, error = PowerShellExecutor().apply(
                _cleanup_setting("pip_cache", "pip_cache_cleanup"), True
            )

        assert (ok, error) == (True, None)
        assert len(ran) == 1
        for path in resolved_paths(target):
            assert path in ran[0]

    def test_a_cleanup_run_starts_one_powershell_and_no_more(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The delete. The two sizings around it are directory walks now.

        Three processes per Run, on a machine where starting one measured
        6 759-10 551 ms under game load, is most of what a cleanup cost.
        """
        cache_dir = tmp_path / "pip" / "Cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "wheel.whl").write_bytes(b"x" * 4096)
        monkeypatch.setitem(
            CLEANUP_TARGETS, "pip_cache", CleanupTarget("pip_cache", lambda: [str(cache_dir)])
        )

        from fpstune.settings.cleanup_cache import CleanupSizeCache
        from fpstune.settings.cleanup_measure import freed_after_cleanup, measure_cleanup_size

        setting = _cleanup_setting("pip_cache", "pip_cache_cleanup")
        started: list[str] = []

        def fake_run(cmd: str, timeout: int = 30) -> tuple[bool, str]:  # noqa: ARG001
            started.append(cmd)
            # What the real delete does to the same paths.
            for child in cache_dir.iterdir():
                child.unlink()
            return True, "done"

        with (
            patch("fpstune.settings.executors.powershell.run_powershell", fake_run),
            patch("fpstune.settings.cleanup_cache.cleanup_size_cache", CleanupSizeCache()),
        ):
            before = measure_cleanup_size(setting)
            PowerShellExecutor().apply(setting, True)
            freed = freed_after_cleanup(setting, before)

        assert len(started) == 1
        assert before is not None
        assert (before.status, before.size_bytes) == ("ready", 4096)
        assert (freed.freed_bytes, freed.size_after_bytes) == (4096, 0)

    def test_a_path_it_cannot_carry_safely_is_refused_rather_than_escaped(
        self, tmp_path: Path
    ) -> None:
        """The separator is illegal in a Windows path; a path holding one is not
        a path this process discovered, and splitting it would delete two others."""
        target = CleanupTarget("pip_cache", lambda: [str(tmp_path / "we|rd")])
        with pytest.raises(UnsafePath):
            delete_arguments(target)

    def test_a_cleanup_with_no_target_refuses_instead_of_running_empty(self) -> None:
        """A script reaching PowerShell with `%paths%` unfilled would delete
        nothing and report success, which is worse than saying no."""
        setting = _cleanup_setting("no_such_target", "pip_cache_cleanup")
        started: list[str] = []

        def fake_run(cmd: str, timeout: int = 30) -> tuple[bool, str]:  # noqa: ARG001
            started.append(cmd)
            return True, "done"

        with patch("fpstune.settings.executors.powershell.run_powershell", fake_run):
            ok, error = PowerShellExecutor().apply(setting, True)

        assert ok is False
        assert error is not None and "no path target" in error
        assert started == []


class TestTheDeleteStoppedSizingItself:
    """Audit Q3: ~15 actions recomputed their own size to print an unread line.

    `Get-ChildItem -Recurse | Measure-Object` was the slowest of the five methods
    tried — 3 229-4 698 ms over a 229 MB tree against 584-702 ms for the walk it
    imitated — and `temp`, `prefetch` and `thumbnail_cache` each paid it twice.
    """

    @pytest.mark.parametrize(("cleanup_type", "command"), _registered_pairs())
    def test_no_delete_measures_what_it_is_about_to_delete(
        self, cleanup_type: str, command: str
    ) -> None:
        script = ACTION_COMMANDS[command]
        assert "Measure-Object" not in script, cleanup_type

    @pytest.mark.parametrize(("cleanup_type", "command"), _registered_pairs())
    def test_no_delete_enumerates_a_tree_to_remove_it(
        self, cleanup_type: str, command: str
    ) -> None:
        """The recursion belongs to `Remove-Item`, never to `Get-ChildItem`.

        Enumerating every file and dispatching a removal for each is what ran
        `cleanup:prefetch` past its apply timeout on a real machine: Temp held
        12 719 files under 438 top-level entries, so the loop paid a command
        dispatch thirty times over for nothing.
        """
        script = ACTION_COMMANDS[command]
        for line in script.splitlines():
            if "Get-ChildItem" in line:
                assert "-Recurse" not in line, f"{cleanup_type}: {line.strip()}"
