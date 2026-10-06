""" "Could not read it" is not "it is not on this machine" -- three more detects.

Issue #104, the class fixed for the adapter detects in 33263ed, in the shapes its
guard missed:

- ``privacy:recall`` caught a failed feature read into ``$f = $null`` and the next
  statement answered ``not_available``;
- ``system:xmp_expo`` (RAM speed) and ``system:vbs_core_isolation`` (HVCI) read
  CIM with ``-ErrorAction SilentlyContinue`` and answered ``not_available`` for an
  empty result, whether the query had failed or had run and found nothing.

The scripts are PowerShell text, so they run under the real runner with the cmdlets
replaced by functions (a function shadows a cmdlet of the same name). Windows only,
for that reason.
"""

from __future__ import annotations

import sys

import pytest

from fpstune.settings.applicability import is_absent_reading
from fpstune.settings.registry import SettingsRegistry
from fpstune.utils.powershell import run_powershell

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="runs the shipped PowerShell text; there is none elsewhere"
)

ELEVATION = "throw 'The requested operation requires elevation.'"


@pytest.fixture(scope="module")
def registry() -> SettingsRegistry:
    return SettingsRegistry(discover_dynamic=False)


def _detect(registry: SettingsRegistry, setting_id: str, stub: str) -> tuple[bool, str]:
    setting = registry.get(setting_id)
    assert setting is not None, setting_id
    ok, out = run_powershell(stub + setting.detect_command)
    return ok, out.strip().splitlines()[-1] if ok and out.strip() else out.strip()


def _cim(body: str) -> str:
    return (
        f"function Get-CimInstance {{ [CmdletBinding()] param($Namespace, $ClassName) {body} }}; "
    )


class TestRecall:
    @staticmethod
    def _stub(named: str | None, listed: list[str] | None, policy: int | None = None) -> str:
        """``named``: the feature's State, ``None`` = that read raises; ``listed``: the
        whole-list read, ``None`` = it raises too (unelevated)."""
        named_body = f"[pscustomobject]@{{ State = '{named}' }}" if named is not None else ELEVATION
        whole_body = (
            ELEVATION
            if listed is None
            else "@("
            + ", ".join(f"[pscustomobject]@{{ FeatureName = '{n}' }}" for n in listed)
            + ")"
        )
        policy_body = (
            "[pscustomobject]@{ AllowRecallEnablement = " + str(policy) + " }"
            if policy is not None
            else ""
        )
        return (
            "function Get-WindowsOptionalFeature { [CmdletBinding()] "
            "param([switch]$Online, $FeatureName) "
            f"if ($FeatureName) {{ {named_body} }} else {{ {whole_body} }} }}; "
            "function Get-ItemProperty { [CmdletBinding()] param($Path, $Name) "
            f"{policy_body} }}; "
        )

    def test_unreadable_both_ways_is_a_failed_read_not_not_available(
        self, registry: SettingsRegistry
    ) -> None:
        ok, out = _detect(registry, "privacy:recall", self._stub(None, listed=None))
        assert not ok, out
        assert not is_absent_reading(out)

    def test_a_listed_feature_whose_own_read_failed_is_a_failed_read(
        self, registry: SettingsRegistry
    ) -> None:
        ok, out = _detect(registry, "privacy:recall", self._stub(None, listed=["Recall"]))
        assert not ok, out

    def test_a_readable_list_without_recall_proves_it_absent(
        self, registry: SettingsRegistry
    ) -> None:
        ok, out = _detect(registry, "privacy:recall", self._stub(None, listed=["Other"]))
        assert ok, out
        assert out == "not_available"

    @pytest.mark.parametrize(
        ("policy", "expected"), [(0, "disabled"), (1, "enabled"), (None, "enabled")]
    )
    def test_a_machine_with_recall_reads_its_policy(
        self, registry: SettingsRegistry, policy: int | None, expected: str
    ) -> None:
        ok, out = _detect(
            registry, "privacy:recall", self._stub("Disabled", listed=[], policy=policy)
        )
        assert ok, out
        assert out == expected


class TestRamRatedSpeed:
    def test_a_failed_wmi_query_is_a_failed_read_not_not_available(
        self, registry: SettingsRegistry
    ) -> None:
        ok, out = _detect(registry, "system:xmp_expo", _cim("throw 'WMI provider failure'"))
        assert not ok, out
        assert not is_absent_reading(out)

    def test_a_query_that_ran_and_listed_no_module_is_not_available(
        self, registry: SettingsRegistry
    ) -> None:
        ok, out = _detect(registry, "system:xmp_expo", _cim(""))
        assert ok, out
        assert out == "not_available"

    @pytest.mark.parametrize(
        ("configured", "expected"), [(5600, "xmp_active"), (4800, "xmp_inactive")]
    )
    def test_a_readable_module_reads_active_or_inactive(
        self, registry: SettingsRegistry, configured: int, expected: str
    ) -> None:
        stub = _cim(f"[pscustomobject]@{{ Speed = 5600; ConfiguredClockSpeed = {configured} }}")
        ok, out = _detect(registry, "system:xmp_expo", stub)
        assert ok, out
        assert out == expected


class TestMemoryIntegrity:
    def test_a_failed_device_guard_query_is_a_failed_read_not_not_available(
        self, registry: SettingsRegistry
    ) -> None:
        ok, out = _detect(
            registry, "system:vbs_core_isolation", _cim("throw 'WMI provider failure'")
        )
        assert not ok, out
        assert not is_absent_reading(out)

    def test_a_query_that_ran_and_returned_nothing_is_not_available(
        self, registry: SettingsRegistry
    ) -> None:
        ok, out = _detect(registry, "system:vbs_core_isolation", _cim(""))
        assert ok, out
        assert out == "not_available"

    @pytest.mark.parametrize(("running", "expected"), [("1, 2", "enabled"), ("1", "disabled")])
    def test_hvci_enforced_means_service_2_is_running(
        self, registry: SettingsRegistry, running: str, expected: str
    ) -> None:
        stub = _cim(f"[pscustomobject]@{{ SecurityServicesRunning = @({running}) }}")
        ok, out = _detect(registry, "system:vbs_core_isolation", stub)
        assert ok, out
        assert out == expected
