"""NVIDIA Profile executor for GPU settings detection and application."""

from __future__ import annotations

import json
import sys
import threading
from typing import TYPE_CHECKING, Any

from fpstune.settings.executors import BaseExecutor
from fpstune.settings.performance_headroom import frame_cap_for_refresh
from fpstune.utils.config import get_config_dir
from fpstune.utils.logger import get_logger

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor

logger = get_logger()


# fpstune setting key -> NVAPI DRS setting ID. Only the ID is written by hand;
# the raw-value meanings are derived from NvidiaProfile below so this cannot
# drift from the values fpstune actually writes.
_DRIVER_READABLE: dict[str, int] = {}
_REVERSE_VALUE_MAPS: dict[str, dict[int, str]] = {}
_DRIVER_MAP_LOCK = threading.Lock()
_DRIVER_MAPS_BUILT = False


def _build_driver_maps() -> None:
    """Derive raw->display maps by asking NvidiaProfile what each choice emits.

    Writing these tables by hand would duplicate the apply path's mapping, and a
    wrong entry would silently misreport a setting. Round-tripping each choice
    through the same code that generates the .nip keeps one source of truth.
    """
    global _DRIVER_MAPS_BUILT

    from fpstune.core.nv_profile import NvApiSettings, NvidiaProfile

    ids: dict[str, int] = {
        "power_mode": NvApiSettings.POWER_MANAGEMENT_MODE,
        "low_latency": NvApiSettings.LOW_LATENCY_MODE,
        "threaded_opt": NvApiSettings.THREADED_OPTIMIZATION,
        "vsync": NvApiSettings.VSYNC_MODE,
        "shader_cache": NvApiSettings.SHADER_CACHE,
        "triple_buffer": NvApiSettings.TRIPLE_BUFFER,
    }
    choices: dict[str, tuple[str, ...]] = {
        "power_mode": ("optimal", "adaptive", "maximum"),
        "low_latency": ("off", "on", "ultra"),
        "threaded_opt": ("off", "on", "auto"),
        "vsync": ("off", "on", "adaptive"),
        "shader_cache": ("off", "on"),
        "triple_buffer": ("off", "on"),
    }

    for key, setting_id in ids.items():
        reverse: dict[int, str] = {}
        for choice in choices[key]:
            try:
                kwargs: dict[str, Any] = {key: choice}
                emitted = NvidiaProfile(**kwargs).to_settings_dict()
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Could not derive driver map for %s=%s: %s", key, choice, exc)
                continue
            raw = emitted.get(setting_id)
            if raw is not None:
                # First choice wins, so an ambiguous raw value keeps the
                # earliest (canonical) label rather than the last one.
                reverse.setdefault(int(raw), choice)
        if reverse:
            _DRIVER_READABLE[key] = setting_id
            _REVERSE_VALUE_MAPS[key] = reverse

    _DRIVER_MAPS_BUILT = True


def read_setting_from_driver(setting_key: str) -> str | None:
    """Read one setting straight from the driver, or None if not possible.

    None means "no observation available" — the key is not driver-readable,
    NVAPI is unusable, or the setting is absent from the profile (in which case
    the driver default applies and the caller's own default is the right
    answer).
    """
    global _DRIVER_MAPS_BUILT

    if not _DRIVER_MAPS_BUILT:
        with _DRIVER_MAP_LOCK:
            if not _DRIVER_MAPS_BUILT:
                _build_driver_maps()

    setting_id = _DRIVER_READABLE.get(setting_key)
    if setting_id is None:
        return None

    from fpstune.core.nvapi import read_driver_settings

    values = read_driver_settings([setting_id])
    if not values:
        return None

    raw = values.get(setting_id)
    if raw is None:
        return None
    return _REVERSE_VALUE_MAPS[setting_key].get(raw)


class NvProfileExecutor(BaseExecutor):
    """Executor for NVIDIA GPU settings via nvidiaProfileInspector.

    NVIDIA DRS settings cannot be easily read from Windows.
    This executor:
    - Detection: Reads from fpstune's saved settings cache
    - Apply: Uses nvidiaProfileInspector to apply, then caches values

    Uses CLASS-LEVEL cache to ensure all instances share the same state.
    This prevents cache inconsistency between detection and apply operations.
    """

    # Class-level cache - shared across all instances
    _cache_file_path = get_config_dir() / "nvidia" / "settings_cache.json"
    _cache: dict[str, Any] | None = None
    _primary_monitor_info: tuple[int, bool | None] | None = None  # (refresh_rate, supports_vrr)

    def __init__(self) -> None:
        """Initialize NvProfile executor."""
        # Ensure directory exists
        NvProfileExecutor._cache_file_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_primary_monitor_info(self) -> tuple[int, bool | None]:
        """The primary panel's ceiling and VRR answer, from the one derivation.

        ``settings/panel.py`` owns which panel counts and what its rate is —
        this module carried its own sixth copy for as long as it existed, with
        a hardcoded 60 Hz / no-VRR fallback that panel.py's own rule forbids:
        an unknown rate stays 0 and never becomes 60, because a 240 Hz display
        told it is 60 loses three quarters of the frames it can show. Unknown
        here means (0, None): the caller recommends nothing VRR-shaped from it.
        """
        if NvProfileExecutor._primary_monitor_info is not None:
            return NvProfileExecutor._primary_monitor_info

        from fpstune.settings.panel import primary_monitor, refresh_ceiling_hz
        from fpstune.utils.hardware_manager import hardware_manager

        refresh = 0
        supports_vrr: bool | None = None
        try:
            monitor = primary_monitor(hardware_manager.detect_monitors())
            if monitor is not None:
                refresh = refresh_ceiling_hz(monitor) or monitor.refresh_rate_hz or 0
                supports_vrr = monitor.supports_vrr
                logger.debug(
                    "Primary monitor: %dHz, VRR=%s - %s",
                    refresh,
                    supports_vrr,
                    monitor.friendly_name or monitor.name,
                )
        except Exception as e:
            logger.warning("Failed to detect monitor info: %s", e)

        # Only a real answer is cached; an unknown stays uncached so the next
        # caller retries rather than inheriting a blank.
        if refresh or supports_vrr is not None:
            NvProfileExecutor._primary_monitor_info = (refresh, supports_vrr)
        return (refresh, supports_vrr)

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

    def get_vrr_optimization_info(self) -> dict[str, Any]:
        """Get VRR optimization info for the primary monitor (legacy).

        Returns:
            Dict with monitor info and recommended VRR settings.
        """
        refresh_rate, supports_vrr = self._get_primary_monitor_info()
        return self.get_vrr_optimization_info_for_monitor(refresh_rate, supports_vrr)

    @classmethod
    def _load_cache(cls) -> dict[str, Any]:
        """Load cached settings from JSON file.

        Uses class-level cache for consistency across all instances.
        Always reads from file on first access to ensure fresh state after restart.
        """
        from fpstune.utils.debug import debug_log

        if cls._cache is not None:
            return cls._cache

        if cls._cache_file_path.exists():
            try:
                with open(cls._cache_file_path, encoding="utf-8") as f:
                    cls._cache = json.load(f)
                    debug_log("nvprofile", f"Loaded cache from file: {cls._cache}")
                    return cls._cache
            except (json.JSONDecodeError, OSError) as e:
                debug_log("nvprofile", f"Failed to load cache file: {e}")

        # Also try to read from nvidiaProfileInspector's saved profile
        nip_profile = get_config_dir() / "nvidia" / "profiles" / "fpstune_gaming.nip"
        if nip_profile.exists():
            try:
                from fpstune.core.nv_profile import NvidiaProfileInspector

                nv = NvidiaProfileInspector()
                settings = nv.read_applied_settings()
                if settings:
                    cls._cache = settings
                    debug_log("nvprofile", f"Loaded cache from NIP profile: {cls._cache}")
                    return cls._cache
            except Exception as e:
                debug_log("nvprofile", f"Failed to read NIP profile: {e}")

        cls._cache = {}
        debug_log("nvprofile", "Cache is empty - no prior settings found")
        return cls._cache

    @classmethod
    def _save_cache(cls, settings: dict[str, Any]) -> None:
        """Save settings to cache file.

        Uses class-level cache for consistency across all instances.
        """
        from fpstune.utils.debug import debug_log

        cls._cache_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cls._cache_file_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        cls._cache = settings
        debug_log("nvprofile", f"Saved cache to file: {settings}")

    def detect(self, setting: SettingExecutor) -> tuple[Any | None, str | None]:
        """Detect an NVIDIA setting, preferring a real driver read.

        NVAPI's DRS API is read directly when available, so verification
        compares against the driver instead of against fpstune's own cache.
        When NVAPI cannot be used the cache remains the fallback — the value is
        then a record of what was applied, not an observation, which is why
        verification reports those as unverified.
        """
        from fpstune.utils.debug import debug_log

        if sys.platform != "win32":
            return None, "Not available on this platform"

        # Get setting key from detect_args
        setting_key = setting.detect_args.get("setting", "")
        if not setting_key:
            return None, "No setting key specified"

        driver_value = read_setting_from_driver(setting_key)
        if driver_value is not None:
            debug_log("nvprofile", f"DETECT {setting.id}: key={setting_key}, driver={driver_value}")
            return driver_value, None

        cache = NvProfileExecutor._load_cache()
        value = cache.get(setting_key)

        debug_log(
            "nvprofile",
            f"DETECT {setting.id}: key={setting_key}, cached={value}, default={setting.default_value}",
        )

        if value is not None:
            return value, None

        # Return default value when not applied by fpstune
        # This indicates "Windows/NVIDIA default" state
        return setting.default_value, None

    def apply(self, setting: SettingExecutor, value: Any) -> tuple[bool, str | None]:
        """Apply NVIDIA setting via nvidiaProfileInspector.

        This applies the setting and caches the value for future detection.
        """
        from fpstune.utils.debug import debug_log

        if sys.platform != "win32":
            return False, "Not available on this platform"

        setting_key = setting.apply_args.get("setting", "")
        if not setting_key:
            return False, "No setting key specified in apply_args"

        debug_log("nvprofile", f"APPLY {setting.id}: key={setting_key}, value={value}")

        try:
            from fpstune.core.nv_profile import NvidiaProfileInspector

            nv = NvidiaProfileInspector()

            # Load current cache and update the specific setting
            cache = NvProfileExecutor._load_cache().copy()  # Copy to avoid modifying shared cache
            old_value = cache.get(setting_key)
            cache[setting_key] = value

            debug_log("nvprofile", f"APPLY {setting.id}: old_value={old_value}, new cache={cache}")

            # Apply all cached settings via nvidiaProfileInspector
            # Note: NPI applies all settings as a profile, so we need to include all
            # VRR/FPS settings are user-controlled via UI, not auto-calculated
            # IMPORTANT: Defaults here must match Windows/NVIDIA defaults, NOT optimized values!
            # This ensures reset properly reverts to actual defaults, not cached optimized values.
            success, error = nv.apply_gaming_profile(
                power_mode=cache.get("power_mode", "optimal"),  # NVIDIA default
                low_latency=cache.get("low_latency", "off"),  # NVIDIA default (not "ultra")
                threaded_opt=cache.get("threaded_opt", "auto"),  # NVIDIA default (not "on")
                vsync=cache.get("vsync", "on"),  # NVIDIA default (not "off")
                shader_cache=cache.get("shader_cache", "on"),  # NVIDIA default
                fps_limit=cache.get("fps_limit", 0),  # No limit
                vrr_mode=cache.get("vrr_mode", "off"),  # Off by default
                bg_app_fps=cache.get("bg_app_fps", 0),  # Off — see gpu-nvidia:bg_app_fps
                aniso_sample_opt=cache.get("aniso_sample_opt", "off"),  # NVIDIA default (not "on")
                texture_lod_bias=cache.get(
                    "texture_lod_bias", "allow"
                ),  # NVIDIA default (not "clamp")
                ogl_thread_opt=cache.get("ogl_thread_opt", "auto"),  # NVIDIA default (not "on")
                cuda_force_p2=cache.get("cuda_force_p2", "off"),  # Off by default
                triple_buffer=cache.get("triple_buffer", "off"),  # Off by default
                max_prerendered=cache.get("max_prerendered", 3),  # NVIDIA default
                vrr_app_override=cache.get("vrr_app_override", "driver_default"),
            )

            debug_log(
                "nvprofile", f"APPLY {setting.id}: NPI result success={success}, error={error}"
            )

            if success:
                # Save to cache on success
                NvProfileExecutor._save_cache(cache)
                return True, None
            else:
                # Don't restore old value - cache wasn't modified yet (we used a copy)
                # Return the actual error from NPI
                return False, error or "nvidiaProfileInspector returned an error"

        except ImportError as e:
            return False, f"Failed to import NvidiaProfileInspector: {e}"
        except Exception as e:
            return False, f"NVIDIA apply failed: {e}"

    @classmethod
    def apply_bulk(cls, updates: dict[str, Any]) -> tuple[bool, str | None]:
        """Apply multiple NVIDIA settings in a single nvidiaProfileInspector call.

        Merges updates into the current cache, writes one combined profile.
        All settings succeed or fail together (NPI is all-or-nothing).

        Args:
            updates: {setting_key: value} pairs to apply (keys match apply_args["setting"]).

        Returns:
            (success, error)
        """
        from fpstune.utils.debug import debug_log

        if sys.platform != "win32":
            return False, "Not available on this platform"

        if not updates:
            return True, None

        try:
            from fpstune.core.nv_profile import NvidiaProfileInspector

            nv = NvidiaProfileInspector()
            cache = cls._load_cache().copy()
            cache.update(updates)

            debug_log("nvprofile", f"BULK APPLY: {len(updates)} settings, cache={cache}")

            success, error = nv.apply_gaming_profile(
                power_mode=cache.get("power_mode", "optimal"),
                low_latency=cache.get("low_latency", "off"),
                threaded_opt=cache.get("threaded_opt", "auto"),
                vsync=cache.get("vsync", "on"),
                shader_cache=cache.get("shader_cache", "on"),
                fps_limit=cache.get("fps_limit", 0),
                vrr_mode=cache.get("vrr_mode", "off"),
                bg_app_fps=cache.get("bg_app_fps", 0),
                aniso_sample_opt=cache.get("aniso_sample_opt", "off"),
                texture_lod_bias=cache.get("texture_lod_bias", "allow"),
                ogl_thread_opt=cache.get("ogl_thread_opt", "auto"),
                cuda_force_p2=cache.get("cuda_force_p2", "off"),
                triple_buffer=cache.get("triple_buffer", "off"),
                max_prerendered=cache.get("max_prerendered", 3),
                vrr_app_override=cache.get("vrr_app_override", "driver_default"),
            )

            if success:
                cls._save_cache(cache)
                debug_log("nvprofile", "BULK APPLY: success, cache saved")
            else:
                debug_log("nvprofile", f"BULK APPLY: failed — {error}")

            return success, error

        except ImportError as e:
            return False, f"Failed to import NvidiaProfileInspector: {e}"
        except Exception as e:
            return False, f"NVIDIA bulk apply failed: {e}"

    @classmethod
    def invalidate_cache(cls) -> None:
        """Clear the settings cache (class-level and file)."""
        from fpstune.utils.debug import debug_log

        cls._cache = None
        cls._primary_monitor_info = None
        if cls._cache_file_path.exists():
            cls._cache_file_path.unlink()
            debug_log("nvprofile", "Cache file deleted")
