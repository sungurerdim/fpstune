"""The congestion provider is read from the API; a failed read raises, it is not CUBIC.

The defect: when ``Get-NetTCPSetting`` threw, the detect command fell back to
``netsh int tcp show global | Select-String 'Congestion'`` and answered CUBIC
whenever nothing matched — on a non-English Windows, always, because netsh's
labels are localized. A read failure was reported as a value (A11). The first fix
answered ``not_available``, which the detection engine turns into "not applicable":
the Internet template exists on every Windows 11, so a failed read of it was reported
as "this feature is not on the machine". Issue #104 (33263ed) made it raise, so the
row reads "unknown" with the reason.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import (
    FAILED_READ,
    HARNESS_ERROR,
    failed_read,
    run_shipped_command,
)

from fpstune.settings.registry import SettingsRegistry

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@pytest.fixture(scope="module")
def detect_command() -> str:
    setting = SettingsRegistry(discover_dynamic=False).get("network:congestion_provider")
    assert setting is not None
    return setting.detect_command


_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json
function Get-NetTCPSetting {
    [CmdletBinding()] param([string]$SettingName)
    if ($FpsFake.throws) { throw "the cmdlet is not available on this host" }
    [pscustomobject]@{ CongestionProvider = $FpsFake.provider }
}
function netsh { Write-Output "HARNESS_ERROR: netsh was called" }
"""


def test_the_api_answer_is_passed_through(detect_command: str) -> None:
    assert (
        run_shipped_command(_PRELUDE + detect_command, {"throws": False, "provider": "CUBIC"})
        == "CUBIC"
    )
    assert (
        run_shipped_command(_PRELUDE + detect_command, {"throws": False, "provider": "CTCP"})
        == "CTCP"
    )


def test_a_failed_read_raises_and_is_neither_a_value_nor_a_sentinel(detect_command: str) -> None:
    """The gate: the old fallback printed CUBIC here, the first fix `not_available`."""
    answer = run_shipped_command(
        _PRELUDE + failed_read(detect_command), {"throws": True, "provider": ""}
    )
    assert answer == f"{FAILED_READ}: the cmdlet is not available on this host"
    assert not answer.startswith(HARNESS_ERROR)


def test_no_localized_text_is_ever_parsed(detect_command: str) -> None:
    assert "netsh" not in detect_command
    assert "Select-String" not in detect_command
