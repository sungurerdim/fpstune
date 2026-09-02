"""Build-gated settings take the documented path on every Windows build.

#83 Phase 2, the build host: 23H2 (22631), 24H2 (26100) and 25H2 (26200) are
the three Windows 11 builds a user can be on today, and Windows 10 22H2 (19045)
is what a machine that has not moved yet reports. Nothing here reads this
machine's build — each test hands the build in and checks what the product
derives from it, the way the developer's own machine never could.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from fpstune.settings.applicability import ApplicabilityChecker, HardwareContext
from fpstune.settings.base import SettingExecutor
from fpstune.settings.discovery import display as display_discovery
from fpstune.settings.discovery.probes import HardwareProbes
from fpstune.settings.registry import SettingsRegistry
from fpstune.utils.hardware_manager import hardware_manager

DWM_PATH = r"SOFTWARE\Microsoft\Windows\Dwm"
GFX_PATH = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"

WINDOWS_11_BUILDS = (22631, 26100, 26200)


class _Registrar:
    def __init__(self) -> None:
        self.registered: dict[str, SettingExecutor] = {}

    def register(self, setting: SettingExecutor) -> None:
        self.registered[setting.id] = setting

    def get(self, setting_id: str) -> SettingExecutor | None:
        return self.registered.get(setting_id)

    def get_all(self) -> list[SettingExecutor]:
        return list(self.registered.values())


# The discoverer takes probes it never reads (the build comes from the OS, not a probe).
NO_PROBES = cast(HardwareProbes, None)


class TestTheMpoDiscovererFollowsTheRunningBuild:
    @pytest.mark.parametrize(
        ("build", "path", "name"),
        [
            (22631, DWM_PATH, "OverlayTestMode"),
            (26100, DWM_PATH, "OverlayTestMode"),
            (26200, GFX_PATH, "DisableOverlays"),
        ],
    )
    def test_the_registered_setting_writes_what_that_build_honours(
        self, build: int, path: str, name: str, monkeypatch
    ) -> None:
        """The defect this guards: GraphicsDrivers\\DisableOverlays written on every
        build, a silent no-op on 23H2 and 24H2 that verified as success."""
        monkeypatch.setattr(
            hardware_manager, "detect_os", lambda: SimpleNamespace(build=str(build))
        )
        registrar = _Registrar()

        assert display_discovery.discover_mpo_setting(registrar, NO_PROBES) == 1

        setting = registrar.get("display:mpo_disable")
        assert setting is not None
        assert (setting.detect_args["path"], setting.detect_args["name"]) == (path, name)

    def test_an_unknown_build_registers_nothing_rather_than_guessing(self, monkeypatch) -> None:
        """No build → the static default stays; a guess would be the defect again."""
        monkeypatch.setattr(hardware_manager, "detect_os", lambda: SimpleNamespace(build=""))
        registrar = _Registrar()
        assert display_discovery.discover_mpo_setting(registrar, NO_PROBES) == 0
        assert registrar.get_all() == []


def _checker(build: int, *, windows_11: bool) -> ApplicabilityChecker:
    return ApplicabilityChecker(HardwareContext(windows_build=build, is_windows_11=windows_11))


@pytest.fixture(scope="module")
def shipped():
    return SettingsRegistry(discover_dynamic=False).get_all()


@pytest.fixture(scope="module")
def min_build_settings(shipped):
    found = [s for s in shipped if "min_windows_build" in (s.applicable_conditions or {})]
    assert found, "no build-gated setting is shipped; this suite would prove nothing"
    return found


@pytest.fixture(scope="module")
def windows_11_only_settings(shipped):
    found = [s for s in shipped if (s.applicable_conditions or {}).get("is_windows_11")]
    assert found, "no Windows-11-only setting is shipped; this suite would prove nothing"
    return found


class TestBuildGatedSettingsOnEveryBuild:
    @pytest.mark.parametrize("build", WINDOWS_11_BUILDS)
    def test_every_min_build_setting_applies_on_each_windows_11_build(
        self, build: int, min_build_settings
    ) -> None:
        checker = _checker(build, windows_11=True)
        for setting in min_build_settings:
            assert checker.is_applicable(setting) == (True, ""), (setting.id, build)

    @pytest.mark.parametrize("build", WINDOWS_11_BUILDS)
    def test_every_windows_11_only_setting_applies_on_each_windows_11_build(
        self, build: int, windows_11_only_settings
    ) -> None:
        checker = _checker(build, windows_11=True)
        for setting in windows_11_only_settings:
            assert checker.is_applicable(setting) == (True, ""), (setting.id, build)

    def test_windows_10_is_told_which_settings_need_11_and_why(
        self, windows_11_only_settings, min_build_settings
    ) -> None:
        """22H2 (19045) is above every min_windows_build fpstune ships, so those
        still apply; the Windows-11-only ones say so in words the user can read."""
        checker = _checker(19045, windows_11=False)
        for setting in windows_11_only_settings:
            assert checker.is_applicable(setting) == (False, "Requires Windows 11"), setting.id
        for setting in min_build_settings:
            assert checker.is_applicable(setting) == (True, ""), setting.id

    def test_a_build_below_the_floor_names_the_floor(self, min_build_settings) -> None:
        for setting in min_build_settings:
            floor = setting.applicable_conditions["min_windows_build"]
            ok, reason = _checker(floor - 1, windows_11=False).is_applicable(setting)
            assert (ok, reason) == (False, f"Requires Windows build {floor}+"), setting.id

    def test_an_unreadable_build_is_zero_and_gates_conservatively(self, min_build_settings) -> None:
        """`build_hardware_context` turns a non-numeric build into 0; a setting that
        needs a floor must then hold back rather than assume the newest Windows."""
        checker = _checker(0, windows_11=False)
        for setting in min_build_settings:
            assert checker.is_applicable(setting)[0] is False, setting.id
