"""Frame caps for Fortnite and Rainbow Six Siege, derived from the primary panel.

Both files hold a frame cap the game honours, and its right value is a property
of the panel: the one cap rule on a VRR panel, none on a fixed one. The primary
monitor decides, because a VRR second screen says nothing about the one the
game runs on.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fpstune.settings.panel import primary_monitor, refresh_ceiling_hz

if TYPE_CHECKING:
    from fpstune.settings.discovery import Registrar
    from fpstune.settings.discovery.probes import HardwareProbes

logger = logging.getLogger(__name__)


def discover_title_frame_caps(registry: Registrar, probes: HardwareProbes) -> int:  # noqa: ARG001
    """Register each title's frame cap.

    Returns:
        Count registered; 0 when the panel or its refresh rate is unknown, which
        must not become a cap chosen for a 60 Hz panel nobody has.
    """
    from fpstune.settings.definitions.game_configs_titles import (
        create_fortnite_fps_cap_setting,
        create_siege_fps_cap_setting,
    )
    from fpstune.utils.hardware_manager import hardware_manager

    try:
        monitors = hardware_manager.detect_monitors()
    except Exception as e:
        logger.warning("Game frame caps skipped, monitor detection failed: %s", e)
        return 0

    monitor = primary_monitor(monitors)
    max_hz = refresh_ceiling_hz(monitor) if monitor is not None else 0
    if not max_hz:
        logger.debug("Game frame caps skipped: primary panel refresh rate unknown")
        return 0

    vrr = bool(getattr(monitor, "supports_vrr", False))
    registry.register(create_fortnite_fps_cap_setting(max_hz, vrr=vrr))
    registry.register(create_siege_fps_cap_setting(max_hz, vrr=vrr))
    return 2
