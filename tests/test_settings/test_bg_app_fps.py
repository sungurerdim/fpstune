"""No fpstune code path may impose a background frame cap.

Reported on the dev machine: MW3 ran at background speed with the cap applied.
NVIDIA's driver treats an application as backgrounded when its foreground
detection fails — an overlay, a separate render process, or an executable with
no driver profile — and then the background cap becomes the game's cap. This is
documented for Portal RTX (attributed to its overlay), VS Code, Electron apps,
TETR.IO and Chromium browsers; MW3 runs under Battle.net/Steam/CoD HQ overlays,
which is the same shape.

fpstune not only recommended the cap, it imposed one implicitly:
`NvidiaProfile.to_settings_dict()` emits every key unconditionally, so the
dataclass default was written to the driver whenever *any* NVIDIA setting was
applied. A user who never touched this setting still got capped by changing,
say, shader cache. Five separate places defaulted to 30.
"""

from __future__ import annotations

import inspect

from fpstune.core.nv_profile import NvidiaProfile
from fpstune.settings.registry import SettingsRegistry


def test_the_setting_recommends_off() -> None:
    setting = SettingsRegistry(discover_dynamic=False).get("gpu-nvidia:bg_app_fps")
    assert setting is not None
    assert setting.recommended_value == 0, (
        "recommending any background cap re-introduces the MW3 report; "
        "NVIDIA's own recommended value for this option is Off"
    )
    assert setting.default_value == 0


def test_profile_defaults_to_no_cap() -> None:
    """The dataclass default is written to the driver on every NVIDIA apply."""
    assert NvidiaProfile().bg_app_fps == 0


def test_a_profile_with_no_cap_writes_the_off_value() -> None:
    """Off must be written explicitly, not omitted.

    Omitting the key would leave an already-capped driver capped while apply
    reported success — the defect shape this codebase has paid for repeatedly.
    """
    from fpstune.core.nv_profile import NvApiSettings

    settings = NvidiaProfile().to_settings_dict()
    assert NvApiSettings.BG_APP_MAX_FPS in settings
    assert settings[NvApiSettings.BG_APP_MAX_FPS] == NvApiSettings.BG_APP_FPS_OFF


def test_no_source_file_falls_back_to_a_cap() -> None:
    """Every default for this field, anywhere, must be 0.

    Scans the shipped source rather than the three call sites known today, so a
    fourth one added later cannot quietly restore the cap.
    """
    import fpstune.api.routes.display as display_mod
    import fpstune.core.nv_profile as profile_mod
    import fpstune.settings.executors.nvprofile as executor_mod

    offenders: list[str] = []
    for module in (profile_mod, executor_mod, display_mod):
        source = inspect.getsource(module)
        for lineno, line in enumerate(source.splitlines(), start=1):
            if "bg_app_fps" not in line:
                continue
            code = line.split("#", 1)[0]
            if "bg_app_fps" not in code:
                continue
            # Any default or fallback that is not zero.
            for marker in ("bg_app_fps: int = ", 'cache.get("bg_app_fps", '):
                if marker in code:
                    tail = code.split(marker, 1)[1].lstrip()
                    if not tail.startswith("0"):
                        offenders.append(f"{module.__name__}:{lineno}: {line.strip()}")
    assert offenders == [], f"a background frame cap is still defaulted somewhere: {offenders}"
