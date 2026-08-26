"""MW4's hardware-derived settings, and the ranges the installed build declares.

Everything MW4-specific that depends on this machine lives here: adding or
moving one of these settings is a change to this file and nothing else.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fpstune.settings.panel import primary_monitor, refresh_ceiling_hz

if TYPE_CHECKING:
    from fpstune.settings.discovery import Registrar
    from fpstune.settings.discovery.probes import HardwareProbes

logger = logging.getLogger(__name__)


def discover_mw4_display_settings(registry: Registrar, probes: HardwareProbes) -> int:  # noqa: ARG001
    """Register the MW4 settings whose correct value is a property of hardware.

    The two frame caps come from the panel and the VRAM budget from the card.
    None of them has a static fallback: a 120 menu cap on a 60 Hz panel never
    binds, and a VRAM share picked without knowing the card is the defect
    MW3's sibling already shipped once. A machine whose monitor or VRAM
    cannot be read gets no setting rather than a claim about hardware that is
    not there.

    Returns:
        Count registered — 0 to 3 depending on what could be read.
    """
    from fpstune.settings.definitions.game_configs_mw4 import (
        create_mw4_aa_technique_setting,
        create_mw4_fps_cap_setting,
        create_mw4_menu_fps_cap_setting,
        create_mw4_refresh_rate_setting,
        create_mw4_resolution_setting,
        create_mw4_vram_scale_setting,
    )
    from fpstune.utils.detect import get_gpu_info
    from fpstune.utils.hardware_manager import hardware_manager

    registered = 0

    try:
        gpu = get_gpu_info()
        if gpu and gpu.vram_mb:
            registry.register(create_mw4_vram_scale_setting(gpu.vram_mb))
            registered += 1
        else:
            logger.debug("MW4 VRAM budget not registered: the card's VRAM is unknown")

        # One setting with three right answers: each vendor's own upscaler
        # doubles as its best anti-aliasing, so a single static entry would
        # recommend NVIDIA's on an AMD card (C10).
        vendor = (getattr(gpu, "vendor", "") or "").lower() if gpu else ""
        if vendor in ("nvidia", "amd", "intel"):
            registry.register(create_mw4_aa_technique_setting(vendor))
            registered += 1
        else:
            logger.debug("MW4 AA technique not registered: GPU vendor unknown")
    except Exception as e:  # pragma: no cover - environment dependent
        logger.debug("MW4 VRAM budget not registered: %s", e)

    try:
        monitors = hardware_manager.detect_monitors()
    except Exception as e:  # pragma: no cover - environment dependent
        logger.debug("MW4 frame caps not registered, monitor detection failed: %s", e)
        return registered

    monitor = primary_monitor(monitors)
    if monitor is None:
        logger.debug("MW4 frame caps not registered: no monitor detected")
        return registered

    max_hz = refresh_ceiling_hz(monitor)
    if not max_hz:
        # Zero means "not detected" and must never become 60: a 240 Hz panel
        # told it is 60 loses three quarters of the frames it can show.
        logger.debug("MW4 frame caps not registered: panel refresh rate unknown")
        return registered

    registry.register(create_mw4_fps_cap_setting(max_hz))
    registry.register(create_mw4_menu_fps_cap_setting(max_hz))
    registry.register(create_mw4_refresh_rate_setting(max_hz))
    registered += 3

    # Native mode is separate from refresh: a panel can report one and not
    # the other, and a resolution guessed from the current desktop mode would
    # pin the game to whatever the user last set rather than to the panel.
    width = getattr(monitor, "native_width", 0) or 0
    height = getattr(monitor, "native_height", 0) or 0
    if width > 0 and height > 0:
        registry.register(create_mw4_resolution_setting(int(width), int(height)))
        registered += 1
    else:
        logger.debug("MW4 resolution not registered: the panel's native mode is unknown")

    return registered


def adopt_mw4_ranges(registry: Registrar, probes: HardwareProbes) -> int:  # noqa: ARG001
    """Adopt the ranges the installed MW4 build states for itself.

    MW4 documents every setting's range or value list on the setting's own
    line, so on a machine that has the game the file is the authority and
    the declared ``choices`` are only a fallback. A patch that adds a
    quality tier or moves a numeric bound then moves the UI with it, rather
    than leaving a control that offers a value the game rejects (C9).

    A discovered list is adopted only when it still contains this setting's
    default and recommended values. Anything else would leave a setting
    recommending something outside its own choices, which C6 forbids and
    which the UI has no way to render — safer to keep the declared list and
    let the writer refuse the value if it truly is gone.

    The adopted range is written onto a **copy**. ``MW4_SETTINGS`` holds
    module-level singletons, so mutating them in place would leak one
    registry's discovery into the next one built in the same process — and
    into the declared fallback itself, which then stops being a fallback.

    Returns:
        Number of settings whose range came from the file. Zero when MW4 is
        not installed, which is not a failure.
    """
    from dataclasses import replace

    from fpstune.settings.base import SettingValueType
    from fpstune.settings.executors.game_config_cache import get_mw4_metadata

    adopted = 0
    for setting in registry.get_all():
        setting_id = setting.id
        if not setting_id.startswith("game_config:mw4:"):
            continue

        key = setting.detect_args.get("batch_key")
        if not key:
            continue

        try:
            meta = get_mw4_metadata(str(key), str(setting.detect_args.get("batch_source")))
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.debug("MW4 range lookup failed for %s: %s", setting_id, exc)
            continue
        if not meta:
            continue

        choices = meta.get("choices")
        if choices:
            required = {str(setting.default_value), str(setting.recommended_value)}
            if not required.issubset({str(c) for c in choices}):
                logger.debug(
                    "MW4 %s: file lists %s, which is missing %s — keeping declared choices",
                    setting_id,
                    choices,
                    sorted(required - {str(c) for c in choices}),
                )
                continue
            discovered = tuple(str(c) for c in choices)
            if discovered != setting.choices:
                registry.register(
                    replace(
                        setting,
                        choices=discovered,
                        apply_value_map={c: c for c in discovered},
                    )
                )
                adopted += 1
            continue

        low, high = meta.get("minimum"), meta.get("maximum")
        if low is None or high is None:
            continue
        # A numeric range belongs to a numeric setting. MW4 writes `// 0 to
        # 200` on `ResolutionMultiplier`, which fpstune ships as a choice of
        # seven tiers, and adopting the range there published `min_value: 0`
        # on a control whose lowest option is 50 — a consumer rendering a
        # slider from it would offer a resolution of zero. Measured on the
        # installed build 2026-08-25.
        if setting.value_type not in (SettingValueType.INT, SettingValueType.FLOAT):
            continue
        if (low, high) != (setting.min_value, setting.max_value):
            registry.register(replace(setting, min_value=low, max_value=high))
            adopted += 1

    if adopted:
        logger.debug("MW4: %d setting ranges taken from the installed config", adopted)
    return adopted
