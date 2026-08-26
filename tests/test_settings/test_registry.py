"""Tests for SettingsRegistry and the adapter filter discovery actually runs.

The adapter-name *pattern* is a constant, and it is tested where the one
surviving copy lives: ``test_network.py::TestAdapterNamePattern``. A second,
more permissive copy used to sit in ``discovery/network.py`` and was tested here
as though it were the applied rule. Neither copy was ever applied to anything,
so the two could disagree about whether a real adapter validates and no test
could notice. What is tested here now is the only name handling discovery runs.
"""

import pytest

from fpstune.settings.discovery.network import filter_valid_adapters
from fpstune.settings.registry import SettingsRegistry

# A non-ASCII first letter, written as a code point so this file stays ASCII.
# Windows names adapters in the system language and both patterns were re.ASCII,
# so both would have rejected a name like this one.
NON_ASCII_NAME = chr(0x0410) + "dapter"  # Cyrillic capital A


class TestAdapterFiltering:
    """Which adapters survive discovery, and which do not."""

    @pytest.mark.parametrize(
        "name",
        [
            "Ethernet",
            "Wi-Fi",
            "Ethernet 2",
            # A vendor string carries parentheses, dots and a "#N" instance
            # suffix. The narrower pattern matched none of these, so applying it
            # would have dropped real hardware out of the tweak list entirely.
            "Intel(R) Wi-Fi 6E AX211 160MHz",
            "Realtek PCIe 2.5GbE Family Controller #2",
            NON_ASCII_NAME,
            # A user may rename an adapter to anything. It is still kept,
            # because fpstune never emits the name: powershell.py rewrites
            # `-InterfaceIndex N` into a `-Name $var` lookup PowerShell runs for
            # itself, so the name crosses no string boundary fpstune builds, and
            # every other use is an f-string inside a setting's display_name.
            "eth0; ls",
        ],
    )
    def test_named_adapters_survive(self, name: str) -> None:
        """A named adapter is never dropped, whatever characters it carries."""
        assert filter_valid_adapters([(12, name, "802.3")]) == [(12, name, "802.3")]

    def test_unnamed_adapter_is_dropped(self) -> None:
        """An empty name is the one rejection: the card would have no label."""
        assert filter_valid_adapters([(12, "", "802.3")]) == []

    def test_drops_only_the_unnamed_one(self) -> None:
        """Filtering is per-adapter; one nameless entry must not take the others."""
        adapters = [(12, "Ethernet", "802.3"), (0, "", ""), (14, "Wi-Fi", "Native 802.11")]

        assert filter_valid_adapters(adapters) == [
            (12, "Ethernet", "802.3"),
            (14, "Wi-Fi", "Native 802.11"),
        ]

    def test_empty_input(self) -> None:
        """No adapters in, no adapters out."""
        assert filter_valid_adapters([]) == []


class TestSettingsRegistryInitialization:
    """Tests for SettingsRegistry initialization."""

    def test_registry_loads_static_settings(self) -> None:
        """Registry should load static settings on init."""
        registry = SettingsRegistry(discover_dynamic=False)
        assert registry.count() > 0, "Registry should have static settings"

    def test_registry_get_returns_setting(self) -> None:
        """get() should return a setting by ID."""
        registry = SettingsRegistry(discover_dynamic=False)
        # Try to get a known static setting
        setting = registry.get("priority:gpu_priority")
        assert setting is not None, "Should find priority:gpu_priority setting"
        assert setting.id == "priority:gpu_priority"

    def test_registry_get_returns_none_for_unknown(self) -> None:
        """get() should return None for unknown IDs."""
        registry = SettingsRegistry(discover_dynamic=False)
        setting = registry.get("nonexistent:setting")
        assert setting is None

    def test_registry_get_by_category(self) -> None:
        """get_by_category() should filter settings correctly."""
        registry = SettingsRegistry(discover_dynamic=False)
        core_settings = registry.get_by_category("core")
        assert len(core_settings) > 0, "Should have core settings"
        for setting in core_settings:
            assert setting.category.value == "core"

    def test_registry_count(self) -> None:
        """count() should return total settings count."""
        registry = SettingsRegistry(discover_dynamic=False)
        count = registry.count()
        assert count > 0
        assert count == len(registry.get_all())

    def test_registry_count_by_category(self) -> None:
        """count_by_category() should return dict of counts."""
        registry = SettingsRegistry(discover_dynamic=False)
        counts = registry.count_by_category()
        assert isinstance(counts, dict)
        assert "core" in counts or "network" in counts  # Should have at least one category
        # Sum should equal total count
        assert sum(counts.values()) == registry.count()

    def test_registry_get_categories(self) -> None:
        """get_categories() should return unique category names."""
        registry = SettingsRegistry(discover_dynamic=False)
        categories = registry.get_categories()
        assert len(categories) > 0
        assert len(categories) == len(set(categories)), "Categories should be unique"

    def test_registry_custom_timeout(self) -> None:
        """Registry should accept custom adapter discovery timeout."""
        registry = SettingsRegistry(
            discover_dynamic=False,
            adapter_discovery_timeout=5.0,
        )
        assert registry._probes.adapter_discovery_timeout == 5.0


class TestSettingsRegistryDynamic:
    """Tests for dynamic settings discovery."""

    def test_discover_dynamic_returns_count(self) -> None:
        """discover_dynamic_settings() should return adapter count."""
        registry = SettingsRegistry(discover_dynamic=False)
        # This may return 0 on Linux/CI where PowerShell isn't available
        count = registry.discover_dynamic_settings()
        assert isinstance(count, int)
        assert count >= 0

    def test_registry_register_and_unregister(self) -> None:
        """register() and unregister() should work correctly."""
        from fpstune.settings.base import (
            SettingCategory,
            SettingExecutor,
            SettingValueType,
        )

        registry = SettingsRegistry(discover_dynamic=False)
        initial_count = registry.count()

        # Create a test setting
        test_setting = SettingExecutor(
            id="test:dummy_setting",
            category=SettingCategory.CORE,
            display_name="Dummy Setting",
            description="Test setting",
            value_type=SettingValueType.BOOL,
            choices=(),
        )

        # Register
        registry.register(test_setting)
        assert registry.count() == initial_count + 1
        assert registry.get("test:dummy_setting") is not None

        # Unregister
        result = registry.unregister("test:dummy_setting")
        assert result is True
        assert registry.count() == initial_count
        assert registry.get("test:dummy_setting") is None

        # Unregister non-existent
        result = registry.unregister("test:dummy_setting")
        assert result is False
