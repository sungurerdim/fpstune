"""Tests for priority setting definitions."""

import pytest

from fpstune.settings.base import SettingExecutor, SettingValueType
from fpstune.settings.definitions import priority as priority_module
from fpstune.settings.definitions.priority import (
    GAME_PRIORITY,
    GAMES_KEY,
    PRIORITY_CONTROL_KEY,
    PRIORITY_SETTINGS,
    SCHEDULING_CATEGORY,
    SYSTEM_PROFILE_KEY,
    SYSTEM_RESPONSIVENESS,
    WIN32_PRIORITY_SEPARATION,
)


class TestPrioritySettingConstants:
    """Tests for priority setting registry path constants."""

    def test_games_key_path(self) -> None:
        """Verify Games registry key path."""
        assert GAMES_KEY == (
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
        )

    def test_system_profile_key_path(self) -> None:
        """Verify SystemProfile registry key path."""
        assert SYSTEM_PROFILE_KEY == (
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
        )

    def test_priority_control_key_path(self) -> None:
        """Verify PriorityControl registry key path."""
        assert PRIORITY_CONTROL_KEY == r"SYSTEM\CurrentControlSet\Control\PriorityControl"


class TestPrioritySettings:
    """Tests for priority settings."""

    @pytest.mark.parametrize(
        "setting",
        [
            GAME_PRIORITY,
            SYSTEM_RESPONSIVENESS,
            SCHEDULING_CATEGORY,
            WIN32_PRIORITY_SEPARATION,
        ],
    )
    def test_setting_has_required_fields(self, setting: SettingExecutor) -> None:
        """Each priority setting must have required fields."""
        assert setting.id, "Setting must have an ID"
        assert setting.category, "Setting must have a category"
        assert setting.display_name, "Setting must have a display name"
        assert ":" in setting.id, "Setting ID must contain ':' separator"

    def test_every_setting_defined_in_the_module_is_registered(self) -> None:
        """A definition written into priority.py and left out of the list ships to nobody.

        This replaces `len(PRIORITY_SETTINGS) == 6`, and the six is where that
        assertion gave itself away: the test named five ids and asserted a count
        of six, so `priority:sfio_priority` was covered by nothing but the
        arithmetic. A reader who added a seventh setting would have bumped the
        number to 7 and still never learned which settings the list is supposed
        to hold.

        Derived from the module either way, so adding a setting correctly needs no
        edit here and adding one incorrectly fails here.
        """
        defined = {
            value.id
            for value in vars(priority_module).values()
            if isinstance(value, SettingExecutor)
        }
        registered = {setting.id for setting in PRIORITY_SETTINGS}

        assert sorted(defined - registered) == [], (
            "defined in definitions/priority.py and absent from PRIORITY_SETTINGS, "
            "so the registry never discovers them"
        )
        assert sorted(registered - defined) == [], (
            "listed in PRIORITY_SETTINGS with no module-level definition, so this "
            "test can no longer see the whole set it is meant to guard"
        )

    def test_no_setting_is_registered_twice(self) -> None:
        """A duplicate entry makes detect and apply run the same command twice.

        The list is assembled by hand, so a copy-paste that repeats an entry is
        the failure mode. Two identical ids also collide in the registry's
        id-keyed map, where the second silently wins.
        """
        setting_ids = [setting.id for setting in PRIORITY_SETTINGS]
        duplicates = sorted({i for i in setting_ids if setting_ids.count(i) > 1})
        assert duplicates == [], f"registered more than once: {duplicates}"

    def test_priority_settings_list(self) -> None:
        setting_ids = {s.id for s in PRIORITY_SETTINGS}
        assert setting_ids == {
            "priority:game_priority",
            "priority:system_responsiveness",
            "priority:scheduling_category",
            "priority:win32_priority_separation",
        }

    def test_values_windows_does_not_read_are_not_offered(self) -> None:
        """MMCSS: GPU Priority "is not yet used", SFIO Priority "is not used"."""
        setting_ids = {s.id for s in PRIORITY_SETTINGS}
        assert "priority:gpu_priority" not in setting_ids
        assert "priority:sfio_priority" not in setting_ids


class TestEveryPrioritySettingGuardsStock:
    """Each recommendation is Windows' own value (Microsoft's MMCSS page and
    Windows Internals): the old ones were clamped, cancelled or harmful."""

    @pytest.mark.parametrize("setting", PRIORITY_SETTINGS, ids=lambda s: s.id)
    def test_recommended_is_the_windows_default(self, setting: SettingExecutor) -> None:
        assert setting.recommended_value == setting.default_value

    def test_responsiveness_stock_is_20(self) -> None:
        assert SYSTEM_RESPONSIVENESS.default_value == 20

    def test_game_priority_stock_is_2(self) -> None:
        assert GAME_PRIORITY.default_value == 2
        assert GAME_PRIORITY.value_type == SettingValueType.INT

    def test_scheduling_category_stock_is_medium(self) -> None:
        assert SCHEDULING_CATEGORY.default_value == "Medium"


class TestWin32PrioritySeparation:
    def test_stock_2_is_what_reset_writes(self) -> None:
        """24 (0x18) is the Server 'Background services' value; it is not stock."""
        assert WIN32_PRIORITY_SEPARATION.apply_value_map == {"standard": 2}

    def test_stock_readings_read_as_standard(self) -> None:
        from fpstune.settings.executors import map_raw_to_display

        for raw in (2, 38, None):
            assert map_raw_to_display(WIN32_PRIORITY_SEPARATION.value_map, raw) == "standard"

    def test_other_tools_values_read_as_changed(self) -> None:
        from fpstune.settings.executors import map_raw_to_display

        for raw in (24, 42, 41, 26):
            assert map_raw_to_display(WIN32_PRIORITY_SEPARATION.value_map, raw) == "changed"
