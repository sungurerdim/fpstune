"""Tests for priority setting definitions."""

import pytest

from fpstune.settings.base import SettingExecutor, SettingValueType
from fpstune.settings.definitions import priority as priority_module
from fpstune.settings.definitions.priority import (
    GAME_PRIORITY,
    GAMES_KEY,
    GPU_PRIORITY,
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
            GPU_PRIORITY,
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
        """PRIORITY_SETTINGS list should contain all priority settings."""
        setting_ids = [s.id for s in PRIORITY_SETTINGS]
        assert "priority:gpu_priority" in setting_ids
        assert "priority:game_priority" in setting_ids
        assert "priority:system_responsiveness" in setting_ids
        assert "priority:scheduling_category" in setting_ids
        assert "priority:win32_priority_separation" in setting_ids
        # Named here for the first time: the count assertion this replaced was
        # the only thing that knew it existed.
        assert "priority:sfio_priority" in setting_ids


class TestGPUPriority:
    """Tests for GPU Priority setting."""

    def test_value_type(self) -> None:
        """GPU Priority should be INT type."""
        assert GPU_PRIORITY.value_type == SettingValueType.INT

    def test_bounds(self) -> None:
        """GPU Priority should have correct min/max bounds."""
        assert GPU_PRIORITY.min_value == 0
        assert GPU_PRIORITY.max_value == 31

    def test_default_value(self) -> None:
        """GPU Priority default should be 8."""
        assert GPU_PRIORITY.default_value == 8

    def test_recommended_value(self) -> None:
        """GPU Priority recommended should be 8."""
        assert GPU_PRIORITY.recommended_value == 8

    def test_default_in_bounds(self) -> None:
        """Default value should be within bounds."""
        assert GPU_PRIORITY.min_value <= GPU_PRIORITY.default_value <= GPU_PRIORITY.max_value

    def test_recommended_in_bounds(self) -> None:
        """Recommended value should be within bounds."""
        assert GPU_PRIORITY.min_value <= GPU_PRIORITY.recommended_value <= GPU_PRIORITY.max_value


class TestGamePriority:
    """Tests for Game Priority setting."""

    def test_value_type(self) -> None:
        """Game Priority should be INT type."""
        assert GAME_PRIORITY.value_type == SettingValueType.INT

    def test_bounds(self) -> None:
        """Game Priority should have correct min/max bounds."""
        assert GAME_PRIORITY.min_value == 1
        assert GAME_PRIORITY.max_value == 6

    def test_default_value(self) -> None:
        """Game Priority default should be 2."""
        assert GAME_PRIORITY.default_value == 2

    def test_recommended_value(self) -> None:
        """Game Priority recommended should be 6."""
        assert GAME_PRIORITY.recommended_value == 6

    def test_default_in_bounds(self) -> None:
        """Default value should be within bounds."""
        assert GAME_PRIORITY.min_value <= GAME_PRIORITY.default_value <= GAME_PRIORITY.max_value

    def test_recommended_in_bounds(self) -> None:
        """Recommended value should be within bounds."""
        assert GAME_PRIORITY.min_value <= GAME_PRIORITY.recommended_value <= GAME_PRIORITY.max_value


class TestSystemResponsiveness:
    """Tests for System Responsiveness setting."""

    def test_value_type(self) -> None:
        """System Responsiveness should be INT type."""
        assert SYSTEM_RESPONSIVENESS.value_type == SettingValueType.INT

    def test_bounds(self) -> None:
        """System Responsiveness should have correct min/max bounds."""
        assert SYSTEM_RESPONSIVENESS.min_value == 0
        assert SYSTEM_RESPONSIVENESS.max_value == 100

    def test_default_value(self) -> None:
        """System Responsiveness default should be 20."""
        assert SYSTEM_RESPONSIVENESS.default_value == 20

    def test_recommended_value(self) -> None:
        """System Responsiveness recommended should be 0."""
        assert SYSTEM_RESPONSIVENESS.recommended_value == 0

    def test_default_in_bounds(self) -> None:
        """Default value should be within bounds."""
        assert (
            SYSTEM_RESPONSIVENESS.min_value
            <= SYSTEM_RESPONSIVENESS.default_value
            <= SYSTEM_RESPONSIVENESS.max_value
        )

    def test_recommended_in_bounds(self) -> None:
        """Recommended value should be within bounds."""
        assert (
            SYSTEM_RESPONSIVENESS.min_value
            <= SYSTEM_RESPONSIVENESS.recommended_value
            <= SYSTEM_RESPONSIVENESS.max_value
        )


class TestWin32PrioritySeparation:
    """Tests for Win32 Priority Separation setting."""

    def test_value_type(self) -> None:
        """Win32 Priority Separation should be CHOICE type."""
        assert WIN32_PRIORITY_SEPARATION.value_type == SettingValueType.CHOICE

    def test_choices(self) -> None:
        """Win32 Priority Separation should have correct choices."""
        assert "standard" in WIN32_PRIORITY_SEPARATION.choices
        assert "gaming" in WIN32_PRIORITY_SEPARATION.choices
        assert "balanced" in WIN32_PRIORITY_SEPARATION.choices

    def test_value_map_roundtrip(self) -> None:
        """Value map should correctly map registry values to choices."""
        # Test gaming value
        assert WIN32_PRIORITY_SEPARATION.value_map[42] == "gaming"
        assert WIN32_PRIORITY_SEPARATION.apply_value_map["gaming"] == 42

        # Test balanced value
        assert WIN32_PRIORITY_SEPARATION.value_map[41] == "balanced"
        assert WIN32_PRIORITY_SEPARATION.apply_value_map["balanced"] == 41

        # Test default value
        assert WIN32_PRIORITY_SEPARATION.value_map[24] == "standard"
        assert WIN32_PRIORITY_SEPARATION.apply_value_map["standard"] == 24

    def test_legacy_values_map_to_default(self) -> None:
        """Legacy and non-optimal values should map to 'default'."""
        # 0x26 (38) = short VARIABLE quanta - common but not optimal
        assert WIN32_PRIORITY_SEPARATION.value_map[38] == "standard"
        # 0x02 (2) = legacy Windows default
        assert WIN32_PRIORITY_SEPARATION.value_map[2] == "standard"
        # None = key not present
        assert WIN32_PRIORITY_SEPARATION.value_map[None] == "standard"


class TestSchedulingCategory:
    """Tests for Scheduling Category setting."""

    def test_value_type(self) -> None:
        """Scheduling Category should be CHOICE type."""
        assert SCHEDULING_CATEGORY.value_type == SettingValueType.CHOICE

    def test_choices(self) -> None:
        """Scheduling Category should have correct choices."""
        assert "Low" in SCHEDULING_CATEGORY.choices
        assert "Medium" in SCHEDULING_CATEGORY.choices
        assert "High" in SCHEDULING_CATEGORY.choices

    def test_recommended_value(self) -> None:
        """Scheduling Category recommended should be High."""
        assert SCHEDULING_CATEGORY.recommended_value == "High"

    def test_uses_games_key(self) -> None:
        """Scheduling Category should use GAMES_KEY registry path."""
        assert SCHEDULING_CATEGORY.detect_args["path"] == GAMES_KEY
        assert SCHEDULING_CATEGORY.apply_args["path"] == GAMES_KEY
