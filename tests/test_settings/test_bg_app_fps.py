"""No fpstune code path may impose a background frame cap.

Reported on the dev machine: MW3 ran at background speed with the cap applied.
NVIDIA's driver treats an application as backgrounded when its foreground
detection fails — an overlay, a separate render process, or an executable with
no driver profile — and then the background cap becomes the game's cap. This is
documented for Portal RTX (attributed to its overlay), VS Code, Electron apps,
TETR.IO and Chromium browsers; MW3 runs under Battle.net/Steam/CoD HQ overlays,
which is the same shape.

Writes are per setting now, so applying any other NVIDIA setting can no longer
carry a background cap along with it; the remaining guards are the
recommendation and the key the setting writes.
"""

from __future__ import annotations

from fpstune.core import nv_drs
from fpstune.settings.registry import SettingsRegistry


def test_the_setting_recommends_off() -> None:
    setting = SettingsRegistry(discover_dynamic=False).get("gpu-nvidia:bg_app_fps")
    assert setting is not None
    assert setting.recommended_value == 0, (
        "recommending any background cap re-introduces the MW3 report; "
        "NVIDIA's own recommended value for this option is Off"
    )
    assert setting.default_value == 0


def test_off_restores_the_driver_default_on_the_real_key() -> None:
    """Off deletes "Frame Rate Limiter - Background Application" (0x10835005).

    The previous table wrote 0x10835004, a key the driver does not read, so a
    cap set in NVIDIA Control Panel could never be cleared.
    """
    key = nv_drs.KEYS["bg_app_fps"]
    assert key.ids == (0x10835005,)
    assert key.changes_for(0) == {0x10835005: None}


def test_applying_another_nvidia_setting_writes_only_its_own_keys() -> None:
    for name, key in nv_drs.KEYS.items():
        if name == "bg_app_fps":
            continue
        assert nv_drs.FRL_BACKGROUND not in key.ids, name
