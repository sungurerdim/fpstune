"""The collection of settings this machine has.

The registry holds settings and answers questions about them. It does not know
how any of them were found: the static ones come from ``definitions``, and the
hardware-derived ones come from the discoverers in ``settings.discovery``, each
of which is handed the ``Registrar`` protocol and can only register and look up.
Adding a game is a new module there and one entry in ``all_discoverers()`` —
never an edit to this class, which also has nothing to do with network adapters.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fpstune.settings.base import SettingCategory
from fpstune.settings.discovery.probes import (
    DEFAULT_ADAPTER_DISCOVERY_TIMEOUT,
    HardwareProbes,
)

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor

logger = logging.getLogger(__name__)


class SettingsRegistry:
    """Central registry for all settings.

    Manages both static settings (always present) and dynamic settings
    (discovered at runtime, e.g., per-adapter network settings).
    """

    def __init__(
        self,
        discover_dynamic: bool = True,
        adapter_discovery_timeout: float = DEFAULT_ADAPTER_DISCOVERY_TIMEOUT,
    ) -> None:
        """Initialize the registry with static and optionally dynamic settings.

        Args:
            discover_dynamic: If True, discover dynamic per-adapter settings.
                Set to False for faster initialization when only static settings needed.
            adapter_discovery_timeout: Timeout in seconds for PowerShell adapter
                discovery command.
        """
        self._settings: dict[str, SettingExecutor] = {}
        # One probe cache per registry. Discovery asks for several of these
        # twice — the adapter list is wanted by the network pass and the MTU
        # pass — and the warm-up only pays off because the second ask is free.
        self._probes = HardwareProbes(adapter_discovery_timeout)
        self._load_static_settings()
        if discover_dynamic:
            self.discover_dynamic_settings()

    def _load_static_settings(self) -> None:
        """Load all statically defined settings."""
        from fpstune.settings.definitions import get_all_static_settings

        for setting in get_all_static_settings():
            self._settings[setting.id] = setting

    def discover_dynamic_settings(self) -> int:
        """Run every discovery pass against this machine.

        The probes are warmed first so the passes read caches rather than each
        spawning its own PowerShell; the order of the passes is
        ``all_discoverers()``' business and is load-bearing there.

        Returns:
            Total count of discovered dynamic settings.
        """
        from fpstune.settings.discovery import all_discoverers

        self._probes.warm()

        count = 0
        for discover in all_discoverers():
            count += discover(self, self._probes)
        return count

    def get(self, setting_id: str) -> SettingExecutor | None:
        """Get a setting by ID.

        Args:
            setting_id: The setting ID (e.g., "power:usb_selective_suspend").

        Returns:
            The SettingExecutor if found, None otherwise.
        """
        return self._settings.get(setting_id)

    def get_by_category(self, category: str | SettingCategory) -> list[SettingExecutor]:
        """Get all settings in a category.

        Args:
            category: Category name or SettingCategory enum.

        Returns:
            List of settings in the category.
        """
        if isinstance(category, SettingCategory):
            category = category.value

        return [s for s in self._settings.values() if s.category.value == category]

    def get_all(self) -> list[SettingExecutor]:
        """Get all registered settings.

        Returns:
            List of all SettingExecutor instances.
        """
        return list(self._settings.values())

    def get_categories(self) -> list[str]:
        """Get all unique categories.

        Returns:
            List of category names.
        """
        return list({s.category.value for s in self._settings.values()})

    def register(self, setting: SettingExecutor) -> None:
        """Register a setting, replacing any earlier one with the same id.

        Replacement is how a discovery pass re-values a setting an earlier pass
        registered — ``headroom`` raising a recommendation, ``adopt_mw4_ranges``
        adopting the installed build's choices — so there is no separate mutate.

        Args:
            setting: The setting to register.
        """
        self._settings[setting.id] = setting

    def unregister(self, setting_id: str) -> bool:
        """Unregister a setting.

        Args:
            setting_id: The setting ID to remove.

        Returns:
            True if setting was removed, False if not found.
        """
        if setting_id in self._settings:
            del self._settings[setting_id]
            return True
        return False

    def count(self) -> int:
        """Get total number of registered settings."""
        return len(self._settings)

    def count_by_category(self) -> dict[str, int]:
        """Get count of settings per category.

        Returns:
            Dict mapping category name to count.
        """
        counts: dict[str, int] = {}
        for setting in self._settings.values():
            cat = setting.category.value
            counts[cat] = counts.get(cat, 0) + 1
        return counts
