"""The BCD store is read through CIM, from {current}, as typed values.

Two defects this file exists for. ``Get-WmiObject -Namespace root\\WMI -Class
BcdStore`` enumerates *instances* of the class, and BcdStore has none — so the
shipped read threw on every machine and detection fell back to ``bcdedit /enum``
text, whose value words are localized ("Yes" is "Evet" on this Windows). And the
WMI script walked to the boot manager's *default* entry, which on a dual-boot
machine is not the entry ``bcdedit /set {current}`` writes.

The fake here stands in for ``Invoke-CimMethod`` alone; the shipped script and
the shipped parser run as written. The one test that talks to the real store is
skipped unless the process is elevated, because that is what the store requires.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_script

from fpstune.settings.executors.bcdedit import (
    _BCD_STORE_SCRIPT,
    _CURRENT_ENTRY,
    BCD_ELEMENT_TYPES,
    BcdEditExecutor,
    parse_store_lines,
)
from fpstune.utils.admin import is_admin

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_PRELUDE = r"""
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json
function Invoke-CimMethod {
    [CmdletBinding()]
    param([string]$Namespace, [string]$ClassName, $InputObject, [string]$MethodName, [hashtable]$Arguments)
    switch ($MethodName) {
        'OpenStore' {
            if ($FpsFake.storeFails) { return [pscustomobject]@{ ReturnValue = $false; Store = $null } }
            return [pscustomobject]@{ ReturnValue = $true; Store = [pscustomobject]@{ Kind = 'store' } }
        }
        'OpenObject' {
            if ($Arguments.Id -eq $FpsFake.currentId) {
                return [pscustomobject]@{ ReturnValue = $true; Object = [pscustomobject]@{ Kind = 'loader'; Id = $Arguments.Id } }
            }
            return [pscustomobject]@{ ReturnValue = $false; Object = $null }
        }
        'GetElement' {
            $key = '0x{0:X8}' -f [uint32]$Arguments.Type
            $value = $FpsFake.elements.$key
            if ($null -eq $value) {
                if ($FpsFake.missingThrows) { throw "Not found" }
                return [pscustomobject]@{ ReturnValue = $false; Element = $null }
            }
            return [pscustomobject]@{
                ReturnValue = $true
                Element = [pscustomobject]@{ Boolean = $value.Boolean; Integer = $value.Integer }
            }
        }
    }
    throw "unexpected CIM method $MethodName"
}
"""


def _lines(host: dict, *, expect_exit: int = 0) -> list[str]:
    host.setdefault("currentId", _CURRENT_ENTRY)
    return run_shipped_script(
        _PRELUDE + _BCD_STORE_SCRIPT, host, expect_exit=expect_exit
    ).splitlines()


def _element(name: str) -> str:
    return f"0x{BCD_ELEMENT_TYPES[name]:08X}"


class TestTheShippedScript:
    def test_set_and_unset_elements_read_as_typed_values(self) -> None:
        lines = _lines(
            {
                "elements": {
                    _element("useplatformclock"): {"Boolean": True},
                    _element("disabledynamictick"): {"Boolean": False},
                    _element("tscsyncpolicy"): {"Integer": 2},
                }
            }
        )
        assert parse_store_lines(lines) == {
            "useplatformclock": "yes",
            "useplatformtick": None,
            "disabledynamictick": "no",
            "tscsyncpolicy": "enhanced",
        }

    def test_an_element_the_provider_reports_by_throwing_is_not_set(self) -> None:
        """Some builds answer a missing element with a CIM error instead of false."""
        lines = _lines({"elements": {}, "missingThrows": True})
        assert parse_store_lines(lines) == {
            "useplatformclock": None,
            "useplatformtick": None,
            "disabledynamictick": None,
            "tscsyncpolicy": None,
        }

    def test_the_current_entry_is_read_never_the_default_one(self) -> None:
        """A host whose only openable entry is a different GUID answers ERROR, so
        the script cannot have silently read another OS's entry."""
        lines = _lines(
            {"elements": {}, "currentId": "{11111111-2222-3333-4444-555555555555}"},
            expect_exit=1,
        )
        assert parse_store_lines(lines) is None
        assert any(line.startswith("ERROR:Cannot open boot entry") for line in lines)

    def test_a_store_that_will_not_open_is_an_error_not_a_set_of_defaults(self) -> None:
        lines = _lines({"elements": {}, "storeFails": True}, expect_exit=1)
        assert parse_store_lines(lines) is None

    def test_the_old_form_is_gone(self) -> None:
        assert "Get-WmiObject" not in _BCD_STORE_SCRIPT
        assert "[WMI]" not in _BCD_STORE_SCRIPT
        assert "Invoke-CimMethod" in _BCD_STORE_SCRIPT
        assert _CURRENT_ENTRY in _BCD_STORE_SCRIPT
        # The boot manager object, which the old script walked to for the default entry.
        assert "9dea862c-5cdd-4e70-acc1-f32b344d4795" not in _BCD_STORE_SCRIPT


class TestTheParserAlone:
    def test_an_error_line_anywhere_voids_the_answer(self) -> None:
        assert parse_store_lines(["useplatformclock=true", "ERROR:Cannot open boot entry"]) is None

    def test_tsc_policy_integers_are_named(self) -> None:
        assert parse_store_lines(["tscsyncpolicy=0"]) == {"tscsyncpolicy": "default"}
        assert parse_store_lines(["tscsyncpolicy=1"]) == {"tscsyncpolicy": "legacy"}
        assert parse_store_lines(["tscsyncpolicy=2"]) == {"tscsyncpolicy": "enhanced"}
        assert parse_store_lines(["tscsyncpolicy=notset"]) == {"tscsyncpolicy": None}


@pytest.mark.skipif(not is_admin(), reason="reading the BCD store needs an elevated process")
class TestAgainstTheRealStore:
    def test_the_running_machines_entry_reads_without_falling_back(self, monkeypatch) -> None:
        """Elevated only. The script must answer for all four elements from the
        store itself; a fallback to bcdedit text here would mean the CIM path
        failed on a real machine."""
        from fpstune.settings.executors import bcdedit as module

        def no_fallback() -> dict[str, str | None]:
            raise AssertionError("the CIM read fell back to bcdedit text on an elevated process")

        executor = BcdEditExecutor()
        monkeypatch.setattr(executor, "_get_all_values_bcdedit", no_fallback)
        module.BcdEditExecutor.invalidate_cache()
        values = executor._get_all_values_wmi()
        assert set(values) == {
            "useplatformclock",
            "useplatformtick",
            "disabledynamictick",
            "tscsyncpolicy",
        }
        for name, value in values.items():
            assert value in (None, "yes", "no", "default", "legacy", "enhanced"), (name, value)
