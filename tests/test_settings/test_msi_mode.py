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
    assert (
        "'error:Windows refused the write: this device key accepts changes from SYSTEM only'"
        in script
    )
