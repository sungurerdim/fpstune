"""Display settings whose right answer is a property of the panel or the build.

Both passes here exist because their correct value cannot be written down: MPO's
registry value moved between Windows builds, and driver V-Sync and the driver
frame cap invert on a VRR panel. A literal in the definitions would be wrong on
half the machines fpstune runs on, and wrong silently in both cases.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fpstune.settings.panel import primary_monitor, refresh_ceiling_hz

if TYPE_CHECKING:
    from fpstune.settings.discovery import Registrar
    from fpstune.settings.discovery.probes import HardwareProbes

logger = logging.getLogger(__name__)


def discover_monitor_modes(registry: Registrar, probes: HardwareProbes) -> int:  # noqa: ARG001
    """One display-mode setting per connected monitor whose native mode is known.

    Every monitor, not only the primary: a secondary left at 60 Hz on a 144 Hz
    panel is a real loss even when no game runs there (cursor, video, the second
    screen a player watches). The primary's is recommended, the rest optional.

    Returns:
        How many monitors got a setting.
    """
    from fpstune.settings.definitions.display import create_monitor_mode_setting
    from fpstune.settings.display_mode import is_readable, monitor_key
    from fpstune.utils.hardware_manager import hardware_manager

    try:
        monitors = hardware_manager.detect_monitors()
    except Exception as e:  # pragma: no cover - environment dependent
        logger.debug("No per-monitor display settings: %s", e)
        return 0

    primary = primary_monitor(monitors)
    count = 0
    for monitor in monitors:
        if not is_readable(monitor):
            continue
        registry.register(
            create_monitor_mode_setting(
                monitor_key(monitor, monitors),
                monitor.friendly_name or monitor.name.removeprefix("\\\\.\\"),
                primary=monitor is primary,
            )
        )
        count += 1
    return count


def discover_mpo_setting(registry: Registrar, probes: HardwareProbes) -> int:  # noqa: ARG001
    """Register MPO against the value this Windows build actually honours.

    Which registry value disables MPO changes between Windows builds, and
    writing the wrong one fails silently — the value lands and detection
    reads it back as success.

    Returns:
        1 when the build could be read, 0 otherwise (leaving the static default).
    """
    from fpstune.settings.definitions.display import create_mpo_setting
    from fpstune.utils.hardware_manager import hardware_manager

    try:
        os_info = hardware_manager.detect_os()
        build = int(getattr(os_info, "build", 0) or 0)
    except Exception as e:  # pragma: no cover - environment dependent
        logger.debug("MPO setting left at its static default: %s", e)
        return 0

    if not build:
        logger.debug("MPO setting left at its static default: the Windows build is unknown")
        return 0

    registry.register(create_mpo_setting(build))
    return 1


def discover_vrr_dependent_settings(registry: Registrar, probes: HardwareProbes) -> int:  # noqa: ARG001
    """Re-register the settings whose right value flips on a VRR panel.

    Two of them, and they are two thirds of one configuration: driver V-Sync
    is "off" on a fixed-refresh display and "on" alongside G-Sync, and the
    driver frame cap is "none" on a fixed-refresh display and "refresh - 3"
    alongside it. Neither is a literal anyone can write down, because both
    answers depend on the panel that happens to be attached.

    The cap additionally needs the rate itself, so it is registered only when
    the panel reports one. A VRR panel whose refresh cannot be read leaves
    the cap at "none": wrong, but wrong in the direction that removes nothing
    the machine had.

    Returns:
        Count of settings registered (0 when no VRR monitor is present or
        monitor detection fails, leaving the static fixed-refresh defaults).
    """
    from fpstune.settings.definitions.gpu import (
        create_nvidia_fps_limiter_setting,
        create_nvidia_vsync_setting,
    )
    from fpstune.utils.hardware_manager import hardware_manager

    try:
        monitors = hardware_manager.detect_monitors()
    except Exception as e:
        logger.warning("VRR-dependent settings skipped, monitor detection failed: %s", e)
        return 0

    # The primary panel decides, the one games open on — the same reading the
    # MW3 and MW4 caps derive from, so the driver cap and the in-game cap cannot
    # be built from two different panels. A VRR second screen beside a fixed
    # primary would otherwise turn V-Sync on for the screen that has no VRR.
    monitor = primary_monitor(monitors)
    if monitor is None or not getattr(monitor, "supports_vrr", False):
        logger.debug("VRR-dependent settings skipped: the primary panel has no VRR")
        return 0

    registry.register(create_nvidia_vsync_setting(vrr_available=True))
    registered = 1

    max_hz = refresh_ceiling_hz(monitor)
    if max_hz:
        registry.register(create_nvidia_fps_limiter_setting(vrr_available=True, max_hz=max_hz))
        registered += 1
    else:
        logger.debug("Driver frame cap left uncapped: the panel's refresh rate is unknown")

    return registered
