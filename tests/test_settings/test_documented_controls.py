"""Each setting writes the control Windows actually reads, and does what it says.

Every case here shipped writing a value that changed nothing, or something
other than its name, while read-back reported success:

* background apps wrote the Windows 10 HKCU toggle Windows 11 dropped;
* the advertising ID wrote a value no per-user check reads;
* diagnostic data wrote 0, which Home and Pro read as 1, so verify and reality
  disagreed on the editions most players run;
* web search wrote DisableWebSearch, which Windows 11 search ignores;
* Recall was offered on machines that do not have it;
* Game Bar wrote only the Settings switch, leaving the capture hook loading;
* HAGS read "disabled" when the driver was in charge, and reset forced it off;
* mouse acceleration and Sticky Keys took effect only at the next sign-in;
* "Animations" wrote a menu hover delay and left every window animating;
* the Ryzen plan read its result back as the fourth word of a localized line.
"""

from __future__ import annotations

import pytest

from fpstune.settings.definitions.display import directx_flag_scripts
from fpstune.settings.definitions.game import GAME_BAR, HAGS, WINDOWS_VRR
from fpstune.settings.definitions.power import RYZEN_BALANCED_PLAN
from fpstune.settings.definitions.system import (
    BACKGROUND_APPS,
    PERF_FOCUS_ASSIST,
    PRIVACY_ADVERTISING_ID,
    PRIVACY_ALLOW_TELEMETRY,
    PRIVACY_RECALL,
    PRIVACY_WEB_SEARCH_POLICY,
    SYSTEM_HYPER_V,
)
from fpstune.settings.definitions.visual import ANIMATIONS
from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.settings.executors.python_actions import PYTHON_ACTIONS, PYTHON_DETECTORS
from fpstune.settings.registry import SettingsRegistry


class TestRetiredPlacebos:
    @pytest.mark.parametrize(
        "setting_id",
        [
            "privacy:cortana",  # the app is gone from Windows 11
            "privacy:tile_notifications",  # Live Tiles are Windows 10 only
            "privacy:ceip",  # SQMClient has not driven anything since Windows 10
            "privacy:accepted_policy",  # a consent flag, not a collection switch
            "privacy:bing_search",  # BingSearchEnabled is ignored by Windows 11 search
            "visual:smooth_scrolling",  # SmoothScroll is not the value Windows reads
        ],
    )
    def test_is_not_offered(self, setting_id: str) -> None:
        assert setting_id not in {s.id for s in SettingsRegistry().get_all()}


class TestPolicyTargets:
    def test_background_apps_uses_the_appprivacy_force_deny(self) -> None:
        args = BACKGROUND_APPS.apply_args
        assert (args["hive"], args["name"]) == ("HKLM", "LetAppsRunInBackground")
        assert args["path"] == r"SOFTWARE\Policies\Microsoft\Windows\AppPrivacy"
        assert BACKGROUND_APPS.apply_value_map == {"disabled": 2, "enabled": None}
        assert BACKGROUND_APPS.value_map[2] == "disabled"
        assert BACKGROUND_APPS.value_map[None] == "enabled"

    def test_advertising_id_uses_the_group_policy_value(self) -> None:
        args = PRIVACY_ADVERTISING_ID.apply_args
        assert args["path"] == r"SOFTWARE\Policies\Microsoft\Windows\AdvertisingInfo"
        assert args["name"] == "DisabledByGroupPolicy"
        assert PRIVACY_ADVERTISING_ID.apply_value_map == {"disabled": 1, "enabled": None}

    def test_diagnostic_data_writes_the_level_every_edition_honours(self) -> None:
        assert PRIVACY_ALLOW_TELEMETRY.apply_value_map["disabled"] == 1
        # A machine already at 0 (Enterprise) is at the minimum, not "enabled".
        assert PRIVACY_ALLOW_TELEMETRY.value_map[0] == "disabled"
        assert PRIVACY_ALLOW_TELEMETRY.value_map[1] == "disabled"
        assert PRIVACY_ALLOW_TELEMETRY.value_map[None] == "enabled"

    def test_web_search_uses_the_policy_windows_11_reads(self) -> None:
        args = PRIVACY_WEB_SEARCH_POLICY.apply_args
        assert args["path"] == r"SOFTWARE\Policies\Microsoft\Windows\Explorer"
        assert args["name"] == "DisableSearchBoxSuggestions"
        assert args == {**PRIVACY_WEB_SEARCH_POLICY.detect_args, "type": "REG_DWORD"}

    def test_notifications_master_switch_is_offered_not_assumed(self) -> None:
        # It silences every banner all day, security alerts included.
        assert PERF_FOCUS_ASSIST.scope.value == "complete"
        assert PERF_FOCUS_ASSIST.apply_value_map["enabled"] is None


class TestRecall:
    def test_machines_without_the_feature_read_not_available(self) -> None:
        assert "-FeatureName 'Recall'" in PRIVACY_RECALL.detect_command
        assert "'not_available'" in PRIVACY_RECALL.detect_command

    def test_needs_a_restart(self) -> None:
        assert PRIVACY_RECALL.requires_reboot is True


class TestHyperV:
    def test_no_running_hypervisor_reads_as_already_off(self) -> None:
        command = SYSTEM_HYPER_V.detect_command
        assert "HypervisorPresent" in command
        assert command.index("HypervisorPresent") < command.index("Get-WindowsOptionalFeature")


class TestGameBar:
    def test_writes_both_halves_of_capture(self) -> None:
        assert "AppCaptureEnabled" in GAME_BAR.apply_command
        assert "GameDVR_Enabled" in GAME_BAR.apply_command
        assert "GameDVR_Enabled" in GAME_BAR.detect_command

    def test_disabled_only_when_both_are_off(self) -> None:
        assert "$c -eq 0 -and $d -eq 0" in GAME_BAR.detect_command


class TestHags:
    def test_an_absent_value_is_the_driver_deciding(self) -> None:
        assert HAGS.value_map[None] == "driver_default"
        assert "driver_default" in HAGS.choices

    def test_reset_hands_the_choice_back_to_the_driver(self) -> None:
        assert HAGS.default_value == "driver_default"
        assert HAGS.apply_value_map["driver_default"] is None


class TestLiveInputChanges:
    """Mouse, accessibility and animation changes reach the running session.

    Through ctypes, not ``Add-Type``: the compile-in-PowerShell shape is what
    Windows Defender flags (tests/test_quality_gates.py::TestNoRuntimeCompile).
    """

    @pytest.mark.parametrize(
        "action", ["mouse_acceleration_toggle", "accessibility_popups_toggle", "animations_toggle"]
    )
    def test_is_a_python_action(self, action: str) -> None:
        assert action in PYTHON_ACTIONS
        assert action not in ACTION_COMMANDS

    def test_mouse_writes_the_profile_and_the_live_value(self, monkeypatch) -> None:
        from fpstune.settings.executors import python_actions
        from fpstune.utils.winapi import spi

        monkeypatch.setattr("sys.platform", "win32")
        written: list[tuple[str, dict[str, str]]] = []
        live: list[tuple[int, int, int]] = []
        monkeypatch.setattr(
            python_actions, "_write_user_strings", lambda p, v: written.append((p, v))
        )
        monkeypatch.setattr(spi, "set_mouse", lambda *v: live.append(v) or True)

        assert python_actions.mouse_acceleration({"value": "disable"}) == (True, None)
        assert written == [
            (
                r"Control Panel\Mouse",
                {"MouseThreshold1": "0", "MouseThreshold2": "0", "MouseSpeed": "0"},
            )
        ]
        assert live == [(0, 0, 0)]

    def test_a_refused_live_change_says_when_it_lands(self, monkeypatch) -> None:
        from fpstune.settings.executors import python_actions
        from fpstune.utils.winapi import spi

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(python_actions, "_write_user_strings", lambda *_: None)
        monkeypatch.setattr(spi, "set_access_flags", lambda *_: False)

        ok, message = python_actions.accessibility_popups({"value": "disable"})
        assert ok is True
        assert message is not None and "next sign-in" in message

    def test_every_accessibility_structure_gets_its_flags(self, monkeypatch) -> None:
        from fpstune.settings.executors import python_actions
        from fpstune.utils.winapi import spi

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(python_actions, "_write_user_strings", lambda *_: None)
        calls: list[tuple[tuple[int, int, int], int]] = []
        monkeypatch.setattr(spi, "set_access_flags", lambda s, f: calls.append((s, f)) or True)

        python_actions.accessibility_popups({"value": "disable"})
        assert calls == [(spi.STICKYKEYS, 506), (spi.FILTERKEYS, 122), (spi.TOGGLEKEYS, 58)]

    def test_animations_reads_and_writes_the_live_state(self) -> None:
        assert ANIMATIONS.detect_command == "animations_status"
        assert "animations_status" in PYTHON_DETECTORS
        assert ANIMATIONS.apply_command == "animations_toggle"

    @pytest.mark.parametrize(
        ("state", "reading"),
        [((False, False), "disabled"), ((True, False), "enabled"), ((False, True), "enabled")],
    )
    def test_animations_are_off_only_when_both_are(
        self, monkeypatch, state: tuple[bool, bool], reading: str
    ) -> None:
        from fpstune.settings.executors import python_actions
        from fpstune.utils.winapi import spi

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(spi, "animations", lambda: state)
        assert python_actions.animations_status({}) == reading


class TestDirectXFlags:
    @pytest.mark.parametrize("flag", ["SwapEffectUpgradeEnable", "VRROptimizeEnable"])
    def test_matches_the_whole_entry(self, flag: str) -> None:
        detect, apply = directx_flag_scripts(flag)
        assert f"'^\\s*{flag}='" in detect
        assert f"-notmatch '^\\s*{flag}='" in apply
        # Entries are rejoined and terminated once, never appended after a ';'.
        assert "-join ';') + ';'" in apply
        assert "-like" not in detect

    def test_windowed_vrr_uses_the_same_parser(self) -> None:
        assert (WINDOWS_VRR.detect_command, WINDOWS_VRR.apply_command) == directx_flag_scripts(
            "VRROptimizeEnable"
        )


def test_ryzen_plan_reads_the_active_guid_by_pattern() -> None:
    assert "-split ' '" not in RYZEN_BALANCED_PLAN.apply_command
    assert RYZEN_BALANCED_PLAN.apply_command.count("[regex]::Match") == 2
