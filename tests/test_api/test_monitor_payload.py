"""A monitor's payload names the key its own settings carry.

Each monitor gets its own card on the Hardware page, and the card finds its
display-mode tweak by `display:<setting_key>:`. The failure this guards: two
identical panels share a model id, so a key the frontend re-derived from the
model would put both monitors' tweaks on both cards.
"""

from __future__ import annotations

from fpstune.api.schemas import MonitorInfo
from fpstune.settings.definitions.display import create_monitor_mode_setting
from fpstune.settings.display_mode import monitor_key
from fpstune.utils.detect import MonitorInfo as DetectedMonitorInfo


def _panel(name: str, *, primary: bool) -> DetectedMonitorInfo:
    return DetectedMonitorInfo(
        name=name,
        width=2560,
        height=1440,
        refresh_rate_hz=60,
        is_primary=primary,
        friendly_name="Example 27Q",
        hardware_id="EXM2701",
    )


def test_payload_key_is_the_one_in_the_monitor_setting_id() -> None:
    monitors = [_panel(r"\\.\DISPLAY1", primary=True), _panel(r"\\.\DISPLAY2", primary=False)]
    payloads = [MonitorInfo.from_detected(m, monitors) for m in monitors]

    setting = create_monitor_mode_setting(
        monitor_key(monitors[1], monitors),
        "Example 27Q",
        primary=False,
        refresh_hz=60,
        max_refresh_hz=165,
    )

    assert setting.id.startswith(f"display:{payloads[1].setting_key}:")
    # Twins of one model still get two keys, so each card holds only its own.
    assert payloads[0].setting_key != payloads[1].setting_key
