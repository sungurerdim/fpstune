"""MW3's hardware-derived settings.

Refresh rate, in-game frame cap and fullscreen resolution are properties of the
attached monitor, and the VRAM share is a property of the card, so a literal in
the definitions goes stale the moment either changes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fpstune.settings.panel import primary_monitor, refresh_ceiling_hz

if TYPE_CHECKING:
    from fpstune.settings.discovery import Registrar
    from fpstune.settings.discovery.probes import HardwareProbes

logger = logging.getLogger(__name__)


def discover_mw3_display_settings(registry: Registrar, probes: HardwareProbes) -> int:  # noqa: ARG001
    """Register the MW3 display settings whose correct value comes from hardware.

    Returns:
        Count of settings registered (0 if no monitor could be read).
    """
    from fpstune.settings.definitions.game_configs import (
        create_mw3_aa_technique_setting,
        create_mw3_fps_cap_setting,
        create_mw3_menu_fps_cap_setting,
        create_mw3_refresh_rate_setting,
        create_mw3_resolution_setting,
        create_mw3_vram_scale_setting,
    )
    from fpstune.utils.detect import get_gpu_info
    from fpstune.utils.hardware_manager import hardware_manager

    # VRAM headroom is a property of the card, not of the monitor, so it is
    # registered independently of the refresh/resolution guards below.
    # There is no static fallback to fall back to: the setting's whole value
    # is that 70% suits an 8 GB card and 95% suits a 24 GB one, so a machine
    # whose VRAM cannot be read gets no setting rather than a recommendation
    # about a card it does not have.
    try:
        gpu = get_gpu_info()
        if gpu and gpu.vram_mb:
            registry.register(create_mw3_vram_scale_setting(gpu.vram_mb))
        else:
            logger.debug("MW3 VRAM scale not registered: the card's VRAM is unknown")

        # Same shape as MW4's, and for the same reason: one setting with three
        # right answers. The static entry recommended DLSS on every machine,
        # which an AMD or Intel card cannot run — so those owners were left on
        # a software AA path with no upscale at all (C10).
        vendor = (getattr(gpu, "vendor", "") or "").lower() if gpu else ""
        if vendor in ("nvidia", "amd", "intel"):
            registry.register(create_mw3_aa_technique_setting(vendor))
        else:
            logger.debug("MW3 AA technique not registered: GPU vendor unknown")
    except Exception as e:  # pragma: no cover - environment dependent
        logger.debug("MW3 VRAM scale not registered: %s", e)

    try:
        monitors = hardware_manager.detect_monitors()
    except Exception as e:
        logger.warning("MW3 display settings skipped, monitor detection failed: %s", e)
        return 0

    monitor = primary_monitor(monitors)
    if monitor is None:
        logger.debug("MW3 display settings skipped: no monitor detected")
        return 0

    max_hz = refresh_ceiling_hz(monitor)
    width = monitor.native_width or monitor.width
    height = monitor.native_height or monitor.height

    registered = 0
    # Each guard is separate: an unknown refresh rate must not also suppress the
    # resolution setting, and a zero here means "not detected", not "60".
    if max_hz:
        label = monitor.friendly_name or monitor.name
        registry.register(create_mw3_refresh_rate_setting(max_hz, label))
        registry.register(create_mw3_fps_cap_setting(max_hz))
        # The menu cap is derived from the same refresh rate: a fixed 90 would
        # exceed a 60 Hz panel and render frames it never shows.
        registry.register(create_mw3_menu_fps_cap_setting(max_hz))
        registered += 3
    else:
        logger.debug("MW3 refresh/cap settings skipped: monitor refresh rate unknown")

    if width and height:
        registry.register(create_mw3_resolution_setting(width, height))
        registered += 1
    else:
        logger.debug("MW3 resolution setting skipped: native resolution unknown")

    return registered
