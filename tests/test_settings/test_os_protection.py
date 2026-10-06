"""Keys Windows' User Choice Protection Driver guards are "not on offer", never "refused".

Failure these guard against (measured 2026-10-06, #104): ``system:widgets`` was offered,
the elevated write to ``HKLM\\...\\Dsh\\AllowNewsAndInterests`` was refused by UCPD, and the
row ended as a failed apply with a permissions message no administrator can act on.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import replace

import pytest

from fpstune.settings import os_protection
from fpstune.settings.applicability import ApplicabilityChecker, HardwareContext
from fpstune.settings.base import DetectType, SettingExecutor
from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.settings.os_protection import (
    PROTECTED_KEYS,
    blocked_write,
    guard_is_up,
    protected_write_targets,
    ucpd_active,
)
from fpstune.settings.registry import SettingsRegistry

_RUNNING = 4
_STOPPED = 1
_START_PENDING = 2


@pytest.fixture(autouse=True)
def _fresh_ucpd_cache() -> Iterator[None]:
    ucpd_active.cache_clear()
    yield
    ucpd_active.cache_clear()


def _guard(monkeypatch: pytest.MonkeyPatch, *, up: bool) -> None:
    monkeypatch.setattr(os_protection, "_read_start", lambda: 2 if up else None)
    monkeypatch.setattr(os_protection, "_read_state", lambda: _RUNNING if up else None)
    ucpd_active.cache_clear()


@pytest.fixture(scope="module")
def settings() -> list[SettingExecutor]:
    return SettingsRegistry(discover_dynamic=False).get_all()


def _registry_write(hive: str, path: str, name: str) -> SettingExecutor:
    from fpstune.settings.base import SettingCategory

    return SettingExecutor(
        id="test:write",
        category=SettingCategory.SYSTEM,
        display_name="t",
        description="A test row.",
        choices=("a", "b"),
        apply_type=DetectType.REGISTRY,
        apply_args={"hive": hive, "path": path, "name": name, "type": "REG_DWORD"},
    )


def _widgets(settings: list[SettingExecutor]) -> SettingExecutor:
    return next(s for s in settings if s.id == "system:widgets")


class TestGuardIsUp:
    """The driver's own state decides; Start only answers when the state is unreadable."""

    @pytest.mark.parametrize("state", [_RUNNING, _START_PENDING])
    def test_running_driver_is_up_even_when_start_says_disabled(self, state: int) -> None:
        # Disabled in the registry but not yet rebooted: still filtering.
        assert guard_is_up(4, state) is True

    def test_stopped_driver_is_down_even_when_start_says_auto(self) -> None:
        assert guard_is_up(2, _STOPPED) is False

    @pytest.mark.parametrize("start", [0, 1, 2])
    def test_unreadable_state_falls_back_to_loaded_at_boot_starts(self, start: int) -> None:
        assert guard_is_up(start, None) is True

    @pytest.mark.parametrize("start", [3, 4])
    def test_unreadable_state_with_manual_or_disabled_start_is_down(self, start: int) -> None:
        assert guard_is_up(start, None) is False

    def test_no_driver_at_all_is_down(self) -> None:
        assert guard_is_up(None, None) is False


class TestUcpdActive:
    def test_reads_once_per_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        def start() -> int:
            calls.append(1)
            return 2

        monkeypatch.setattr(os_protection, "_read_start", start)
        monkeypatch.setattr(os_protection, "_read_state", lambda: _RUNNING)
        assert ucpd_active() is True
        assert ucpd_active() is True
        assert len(calls) == 1

    @pytest.mark.skipif(sys.platform != "win32", reason="Service Control Manager")
    def test_service_query_reads_a_real_running_service(self) -> None:
        # EventLog runs on every Windows 11 machine; a wrong struct layout or a missing
        # argtypes prototype (64-bit handle truncation) would not return 4 here.
        assert os_protection._read_state("EventLog") == _RUNNING

    @pytest.mark.skipif(sys.platform != "win32", reason="Service Control Manager")
    def test_service_query_of_a_missing_service_is_unknown_not_stopped(self) -> None:
        assert os_protection._read_state("FpstuneNoSuchService") is None


class TestProtectedList:
    @pytest.mark.parametrize(
        ("hive", "path", "name"),
        [
            ("HKLM", r"SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests"),
            ("HKLM", r"software\policies\microsoft\dsh\sub", "x"),
            ("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\Windows Feeds", "EnableFeeds"),
            (
                "HKCU",
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
                "TaskbarDa",
            ),
            (
                "HKCU",
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
                "ProgId",
            ),
            (
                "HKCU",
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoiceLatest",
                "ProgId",
            ),
        ],
    )
    def test_listed_write_is_a_target(self, hive: str, path: str, name: str) -> None:
        assert protected_write_targets(_registry_write(hive, path, name))

    @pytest.mark.parametrize(
        ("hive", "path", "name"),
        [
            # The same Advanced key holds many values UCPD does not filter.
            ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "LaunchTo"),
            # A sibling whose name merely starts like a guarded key.
            ("HKLM", r"SOFTWARE\Policies\Microsoft\Dshx", "AllowNewsAndInterests"),
            # Right path, wrong hive.
            ("HKCU", r"SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests"),
            ("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "LetAppsRunInBackground"),
            # An extension the driver does not guard.
            (
                "HKCU",
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.txt\UserChoice",
                "ProgId",
            ),
        ],
    )
    def test_unlisted_write_is_not_a_target(self, hive: str, path: str, name: str) -> None:
        assert protected_write_targets(_registry_write(hive, path, name)) == ()

    def test_script_that_names_a_guarded_value_is_a_target(self) -> None:
        setting = replace(
            _registry_write("HKLM", "", ""),
            apply_type=DetectType.POWERSHELL,
            apply_command="x",
            apply_args={
                "path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
            },
        )
        # Path alone, with no TaskbarDa value, is the whole Advanced key: not guarded.
        assert protected_write_targets(setting) == ()
        named = replace(
            setting,
            apply_args={
                "cmd": r"Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced' TaskbarDa 0"
            },
        )
        assert protected_write_targets(named)


class TestNotApplicable:
    def test_widgets_is_not_applicable_while_ucpd_guards_its_key(
        self, monkeypatch: pytest.MonkeyPatch, settings: list[SettingExecutor]
    ) -> None:
        _guard(monkeypatch, up=True)
        ctx = HardwareContext(is_windows_11=True, windows_build=26200)

        ok, reason = ApplicabilityChecker(ctx).is_applicable(_widgets(settings))

        assert ok is False
        assert "User Choice Protection Driver" in reason
        assert r"HKLM\SOFTWARE\Policies\Microsoft\Dsh" in reason

    def test_widgets_stays_applicable_when_the_driver_is_not_running(
        self, monkeypatch: pytest.MonkeyPatch, settings: list[SettingExecutor]
    ) -> None:
        _guard(monkeypatch, up=False)
        ctx = HardwareContext(is_windows_11=True, windows_build=26200)

        assert ApplicabilityChecker(ctx).is_applicable(_widgets(settings)) == (True, "")

    def test_check_does_not_depend_on_declared_conditions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _guard(monkeypatch, up=True)
        row = _registry_write("HKLM", r"SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests")
        assert row.applicable_conditions == {}

        assert ApplicabilityChecker(HardwareContext()).is_applicable(row)[0] is False

    def test_unrelated_write_is_untouched_while_the_guard_is_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _guard(monkeypatch, up=True)
        row = _registry_write("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "x")
        assert blocked_write(row) == ""


def _flatten(setting: SettingExecutor) -> str:
    """Every string an apply could carry, with no knowledge of how the checker reads them."""
    parts = [setting.apply_command, *map(str, setting.apply_args.values())]
    parts.append(ACTION_COMMANDS.get(setting.apply_command, ""))
    return "\n".join(parts).lower().replace("/", "\\").replace("\\\\", "\\")


# Tail of each guarded key as plain text, written independently of the regexes in
# ``PROTECTED_KEYS`` so a mistake in one cannot hide in the other.
_TAILS = (
    r"policies\microsoft\dsh",
    r"policies\microsoft\windows\windows feeds",
    "taskbarda",
    r"\userchoice",
)


class TestEveryProtectedWriteGoesThroughTheCheck:
    def test_every_definition_naming_a_guarded_key_is_blocked_while_the_guard_is_up(
        self, monkeypatch: pytest.MonkeyPatch, settings: list[SettingExecutor]
    ) -> None:
        """A new row that writes a guarded key must be caught, or this fails by id.

        Brute-force text over every apply field; the checker under test reads the same
        rows by structure. A row that names a guarded tail but is not blocked is a write
        that would ship as an apply that Windows refuses.
        """
        _guard(monkeypatch, up=True)
        ctx = HardwareContext(is_windows_11=True, windows_build=26200)
        checker = ApplicabilityChecker(ctx)

        escaped = [
            s.id
            for s in settings
            if any(tail in _flatten(s) for tail in _TAILS) and checker.is_applicable(s)[0]
        ]

        assert escaped == [], f"writes a UCPD-guarded key but is still offered: {escaped}"

    def test_the_audit_finds_widgets(self, settings: list[SettingExecutor]) -> None:
        """The scan is not vacuous: it sees the one row this class was found on."""
        hits = [s.id for s in settings if any(t in _flatten(s) for t in _TAILS)]
        assert "system:widgets" in hits

    def test_the_two_readings_agree(self, settings: list[SettingExecutor]) -> None:
        """The structured list and the independent text scan name the same rows."""
        by_text = {s.id for s in settings if any(t in _flatten(s) for t in _TAILS)}
        by_list = {s.id for s in settings if protected_write_targets(s)}
        assert by_list == by_text

    def test_every_protected_key_is_readable_in_a_reason(self) -> None:
        assert all(key.label.startswith(("HKLM\\", "HKCU\\")) for key in PROTECTED_KEYS)
