"""A setting whose hardware default already is the tuned state reports so.

The failures these guard (reported from a Windows run, 2026-10-05): "reset all"
failed verify on receive_buffers (expected default, detected maximum) and on
the Wi-Fi / Ethernet msi_mode (expected default, detected enabled). Both
drivers ship the tuned value themselves — a receive default equal to the
maximum, an INF that sets MSISupported=1 — so "default" and "tuned" are one
state and no reset could ever read back as "default".
"""

from __future__ import annotations

from fpstune.settings.applicability import (
    ALREADY_AT_HARDWARE_DEFAULT,
    absent_reason,
    is_absent_reading,
)
from fpstune.settings.definitions.network import (
    create_msi_mode_setting,
    create_receive_buffers_setting,
)


def test_the_sentinel_marks_the_row_not_applicable_with_its_own_reason() -> None:
    assert is_absent_reading(ALREADY_AT_HARDWARE_DEFAULT)
    assert "already ships this tuned" in absent_reason(None, ALREADY_AT_HARDWARE_DEFAULT)
    assert "already ships" not in absent_reason(None, "not_supported")


def test_receive_buffers_reports_a_driver_default_at_its_maximum() -> None:
    script = create_receive_buffers_setting(7, "Ethernet").detect_command
    # Checked before the 'maximum' branch, against the driver's own default.
    assert script.index("DefaultRegistryValue") < script.index("'maximum'")
    assert f"'{ALREADY_AT_HARDWARE_DEFAULT}'" in script


def test_msi_mode_reads_the_drivers_stock_value_not_just_the_current_one() -> None:
    script = create_msi_mode_setting(7, "Wi-Fi").detect_command
    # The stock value is fpstune's recorded original when it wrote, else today's.
    assert "fpstuneOriginalMSISupported" in script
    assert f"if ($stock -eq 1) {{ '{ALREADY_AT_HARDWARE_DEFAULT}' }}" in script
