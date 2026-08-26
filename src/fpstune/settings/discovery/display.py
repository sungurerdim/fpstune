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

    if not any(m.supports_vrr for m in monitors):
        logger.debug("VRR-dependent settings skipped: no VRR monitor detected")
        return 0

    registry.register(create_nvidia_vsync_setting(vrr_available=True))
    registered = 1

    # The same reading the MW3 and MW4 caps derive from, so the driver cap and
    # the in-game cap cannot be built from two different readings of one panel.
    monitor = primary_monitor(monitors)
    max_hz = refresh_ceiling_hz(monitor) if monitor is not None else 0
    if max_hz:
        registry.register(create_nvidia_fps_limiter_setting(vrr_available=True, max_hz=max_hz))
        registered += 1
    else:
        logger.debug("Driver frame cap left uncapped: the panel's refresh rate is unknown")

    return registered
