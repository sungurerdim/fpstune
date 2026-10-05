"""MSI mode's apply must report a refused write instead of saying 'ok'.

The failure this guards: New-Item and Set-ItemProperty raise non-terminating
errors, so a write Windows refused never reached the script's catch, the script
printed 'ok', and the row failed verify with no reason anyone could act on.
"""

from __future__ import annotations

import re

from fpstune.settings.definitions.gpu import GPU_HARDWARE_SETTINGS

MSI = next(s for s in GPU_HARDWARE_SETTINGS if s.id == "gpu-hardware:msi_mode")


def test_every_registry_write_stops_on_error() -> None:
    script = MSI.apply_command
    for cmdlet in ("New-Item", "Set-ItemProperty", "Remove-ItemProperty"):
        for call in re.findall(rf"{cmdlet} [^;{{}}]*", script):
            assert "-ErrorAction Stop" in call, call


def test_a_permission_refusal_is_named_by_exception_type_not_message() -> None:
    script = MSI.apply_command
    assert (
        "catch [System.UnauthorizedAccessException], [System.Security.SecurityException]" in script
    )
    assert "'error:Windows refused the registry write (access denied)'" in script


def test_detect_reads_the_drivers_stock_value_not_just_the_current_one() -> None:
    from fpstune.settings.applicability import ALREADY_AT_HARDWARE_DEFAULT

    script = MSI.detect_command
    # Modern GPU INFs set MSISupported=1 themselves: "default" is "enabled" there,
    # so reset can never read back as 'default' and the row is not applicable.
    assert "fpstuneOriginalMSISupported" in script
    assert f"if ($stock -eq 1) {{ '{ALREADY_AT_HARDWARE_DEFAULT}' }}" in script


def test_apply_records_the_original_and_default_restores_it_instead_of_deleting() -> None:
    script = MSI.apply_command
    enable, _, default = script.partition("} elseif ($null -ne $cur.fpstuneOriginalMSISupported)")
    # Enabling records what was there (-1 = absent) before its first write.
    assert "Set-ItemProperty -Path $rp -Name 'fpstuneOriginalMSISupported'" in enable
    # Default puts the recorded value back; with nothing recorded it writes nothing,
    # so a driver-shipped MSISupported=1 is never forced to line-based interrupts.
    assert "$was = [int]$cur.fpstuneOriginalMSISupported" in default
    assert "Set-ItemProperty -Path $rp -Name 'MSISupported' -Value $was" in default
    assert "Remove-ItemProperty -Path $rp -Name 'fpstuneOriginalMSISupported'" in default
    # The unconditional delete is gone: removal only happens when the recorded
    # original was "absent".
    assert default.index("$was -eq -1") < default.index(
        "Remove-ItemProperty -Path $rp -Name 'MSISupported'"
    )
