"""NVIDIA driver settings: detect and apply through NVAPI's settings database.

Every read comes from the driver itself and every write goes to it directly —
nothing is cached, so verifying a setting is an observation, never fpstune
comparing a value with its own record of it. Which DRS keys a setting touches
lives in ``core/nv_drs.py``; the session handling in ``core/nvapi.py``.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from fpstune.core.nv_drs import EnumKey, NumberKey, lookup
from fpstune.settings.applicability import NOT_AVAILABLE
from fpstune.settings.executors import BaseExecutor
from fpstune.settings.performance_headroom import frame_cap_for_refresh
from fpstune.utils.logger import get_logger

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor

logger = get_logger()


def read_setting_from_driver(setting_key: str) -> Any | None:
    """The setting's current value as the driver reports it, or None.

    None means no observation: the key is unknown, NVAPI is unusable here, or
    the driver holds a state none of the setting's choices describes.
    """
    drs = lookup(setting_key)
    if drs is None:
        return None

    from fpstune.core.nvapi import read_driver_settings

    raw = read_driver_settings(list(drs.read_ids))
    if raw is None:
        return None
    return drs.decode(raw)


class NvProfileExecutor(BaseExecutor):
    """Executor for NVIDIA Control Panel global settings."""

    def get_vrr_optimization_info_for_monitor(
        self, refresh_rate: int, supports_vrr: bool | None
    ) -> dict[str, Any]:
        """Get VRR optimization info for a specific monitor.

        Args:
            refresh_rate: Monitor's native/max refresh rate in Hz.
            supports_vrr: The EDID's declaration — None when it could not be
                read. Unknown recommends nothing VRR-shaped, same as False;
                the caller owns saying "unknown" rather than "unsupported".

        Returns:
            Dict with recommended VRR settings for the monitor.
        """
        # Calculate recommended FPS limit (refresh - 3 for G-Sync optimal)
        # A VRR panel whose rate is unknown gets no cap: frame_cap_for_refresh(0)
        # would floor at 30 — a fabricated ceiling on an unread panel.
        recommended_fps_limit = (
            frame_cap_for_refresh(refresh_rate) if supports_vrr and refresh_rate > 0 else 0
        )

        # The three values below are one configuration, not three preferences, and
        # this panel used to hand back a version of it that undid itself:
        #
        #   "fullscreen" is NVCP's "Enable G-SYNC for full screen mode", which
        #   leaves VRR switched off in borderless — the mode most modern titles
        #   default to and the one game_config:mw3:display_mode recommends. The
        #   setting gpu-nvidia:vrr_mode has recommended "on" for exactly this
        #   reason, so this panel was telling the user to undo it.
        #
        #   V-Sync "off" is right on a fixed-refresh display, where it costs
        #   8-16 ms. Under a below-refresh cap on a VRR panel it is never reached,
        #   so it costs nothing and is what keeps tearing away in the moments the
        #   cap is overshot. gpu-nvidia:vsync already derives this per panel.
        return {
            "monitor_refresh_hz": refresh_rate,
            "supports_vrr": supports_vrr,
            "recommended_fps_limit": recommended_fps_limit,
            "recommended_vrr_mode": "on" if supports_vrr else "off",
            "recommended_vsync": "on" if supports_vrr else "off",
            "explanation": (
                f"FPS limit {recommended_fps_limit} keeps G-Sync active at {refresh_rate}Hz, "
                "in borderless as well as fullscreen. Driver V-Sync stays on as the safety "
                "net above the cap, where it costs no latency. Result: no tearing + lowest "
                "latency."
                if supports_vrr
                else "Monitor doesn't support G-Sync/FreeSync. VRR disabled, FPS uncapped, "
                "VSync off to avoid its 8-16 ms cost."
            ),
        }

    def detect(self, setting: SettingExecutor) -> tuple[Any | None, str | None]:
        if sys.platform != "win32":
            return None, "Not available on this platform"

        setting_key = str(setting.detect_args.get("setting", ""))
        drs = lookup(setting_key)
        if drs is None:
            return None, f"No NVIDIA driver key is defined for '{setting_key}'"

        from fpstune.core.nvapi import read_driver_settings

        raw = read_driver_settings(list(drs.read_ids))
        if raw is None:
            # No NVIDIA driver answering here: the setting does not apply.
            return NOT_AVAILABLE, None

        value = drs.decode(raw)
        if value is None:
            readings = ", ".join(f"{i:#010x}={raw.get(i, 'default')}" for i in drs.read_ids)
            return None, (
                f"The NVIDIA driver holds a {setting_key} state none of this "
                f"setting's choices describes ({readings}); applying a choice replaces it."
            )
        return value, None

    def apply(self, setting: SettingExecutor, value: Any) -> tuple[bool, str | None]:
        if sys.platform != "win32":
            return False, "Not available on this platform"

        setting_key = str(setting.apply_args.get("setting", ""))
        drs = lookup(setting_key)
        if drs is None:
            return False, f"No NVIDIA driver key is defined for '{setting_key}'"

        try:
            if isinstance(drs, NumberKey):
                changes = drs.changes_for(int(value))
            else:
                assert isinstance(drs, EnumKey)
                changes = drs.changes_for(str(value))
        except (TypeError, ValueError) as exc:
            return False, f"Invalid value for {setting.id}: {exc}"

        from fpstune.core.nvapi import NvapiError, NvapiUnavailable, write_driver_settings

        try:
            write_driver_settings(changes)
        except NvapiUnavailable as exc:
            return False, f"The NVIDIA driver settings interface is not available: {exc}"
        except (NvapiError, OSError) as exc:
            return False, f"The NVIDIA driver did not accept the change: {exc}"
        return True, None
