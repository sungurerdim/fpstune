"""Setting definitions package.

Contains all static setting definitions organized by category.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor


def get_all_static_settings() -> list[SettingExecutor]:
    """Get all statically defined settings.

    Returns:
        List of all static SettingExecutor instances.
    """
    # Import here to avoid circular imports
    from fpstune.settings.definitions.audio import AUDIO_SETTINGS
    from fpstune.settings.definitions.display import DISPLAY_SETTINGS
    from fpstune.settings.definitions.game import GAME_SETTINGS
    from fpstune.settings.definitions.game_configs import GAME_CONFIG_SETTINGS
    from fpstune.settings.definitions.game_configs_mw4 import (
        MW4_CLEANUP_SETTINGS,
        MW4_SETTINGS,
    )
    from fpstune.settings.definitions.gpu import GPU_SETTINGS
    from fpstune.settings.definitions.launchers import LAUNCHER_SETTINGS
    from fpstune.settings.definitions.network import NETWORK_SETTINGS
    from fpstune.settings.definitions.power import POWER_SETTINGS
    from fpstune.settings.definitions.priority import PRIORITY_SETTINGS
    from fpstune.settings.definitions.storage import STORAGE_SETTINGS
    from fpstune.settings.definitions.system import SYSTEM_SETTINGS
    from fpstune.settings.definitions.timer import TIMER_SETTINGS
    from fpstune.settings.definitions.visual import VISUAL_SETTINGS

    return [
        *POWER_SETTINGS,
        *TIMER_SETTINGS,
        *PRIORITY_SETTINGS,
        *VISUAL_SETTINGS,
        *STORAGE_SETTINGS,
        *NETWORK_SETTINGS,
        *GPU_SETTINGS,
        *DISPLAY_SETTINGS,
        *SYSTEM_SETTINGS,
        *GAME_SETTINGS,
        *AUDIO_SETTINGS,
        *LAUNCHER_SETTINGS,
        *GAME_CONFIG_SETTINGS,
        *MW4_SETTINGS,
        *MW4_CLEANUP_SETTINGS,
    ]
