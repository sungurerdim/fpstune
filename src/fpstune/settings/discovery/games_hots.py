"""Heroes of the Storm settings derived from this machine's panel and audio device."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fpstune.settings.panel import primary_monitor, refresh_ceiling_hz

if TYPE_CHECKING:
    from fpstune.settings.discovery import Registrar
    from fpstune.settings.discovery.probes import HardwareProbes

logger = logging.getLogger(__name__)


def discover_hots_display_settings(registry: Registrar, probes: HardwareProbes) -> int:  # noqa: ARG001
    """Register the HotS refresh rate, which is a property of the panel.

    Measured on the dev machine: a 300 Hz display with ``refreshrate=270`` in
    Variables.txt. The game caps its own output to that number, so no
    graphics setting in the product could have won those 30 Hz back.

    Returns:
        1 when the panel reports a refresh rate, 0 otherwise. Zero means
        "not detected" and must not become 60.
    """
    from fpstune.settings.definitions.game_configs import create_hots_refresh_rate_setting
    from fpstune.utils.hardware_manager import hardware_manager

    try:
        monitors = hardware_manager.detect_monitors()
    except Exception as e:
        logger.warning("HotS display settings skipped, monitor detection failed: %s", e)
        return 0

    monitor = primary_monitor(monitors)
    if monitor is None:
        logger.debug("HotS display settings skipped: no monitor detected")
        return 0

    max_hz = refresh_ceiling_hz(monitor)
    if not max_hz:
        logger.debug("HotS refresh rate skipped: monitor refresh rate unknown")
        return 0

    registry.register(create_hots_refresh_rate_setting(max_hz))
    return 1


def discover_hots_audio_settings(registry: Registrar, probes: HardwareProbes) -> int:  # noqa: ARG001
    """Register the HotS mix rate, derived from this machine's output device.

    A rate below the endpoint's own throws away the high frequencies that
    carry direction, and the right value is whatever the device runs at — so
    a machine whose audio cannot be read gets no setting rather than 44100
    chosen on its behalf.

    Returns:
        1 when an active render endpoint reported a rate, 0 otherwise.
    """
    from fpstune.settings.definitions.game_configs import (
        create_hots_sound_sample_rate_setting,
    )
    from fpstune.utils.audio_format import get_output_sample_rate_hz

    try:
        device_hz = get_output_sample_rate_hz()
    except Exception as e:  # pragma: no cover - environment dependent
        logger.debug("HotS audio setting skipped, endpoint read failed: %s", e)
        return 0

    if not device_hz:
        logger.debug("HotS audio setting skipped: no output device rate detected")
        return 0

    registry.register(create_hots_sound_sample_rate_setting(device_hz))
    return 1
