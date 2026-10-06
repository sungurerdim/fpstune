""" "Could not read it" is not "it is turned off".

`system:hyper_v` and `system:vm_platform` read Windows optional features with
`Get-WindowsOptionalFeature -Online`, which requires elevation. The shipped
command swallowed the elevation failure with `-ErrorAction SilentlyContinue`,
left `$f` null, and fell through to the else branch — so it answered
**'disabled'** for a machine it had not managed to read.

That is the defect this codebase keeps paying for, in a new place: a failure
reported as a value. A user whose Hyper-V is on and costing them frames was told
it was off, and fpstune called the setting already optimal.

There is a second cost. The raise also travelled out of the shared detect
session's scriptblock, so both settings lost their batched result and fell back
to a process each — two of the twenty-five a cold scan spawned.
"""

from __future__ import annotations

import re
import sys

import pytest

from fpstune.settings.applicability import is_absent_reading
from fpstune.settings.executors.ps_batch import command_is_batchable
from fpstune.settings.registry import SettingsRegistry
from fpstune.utils.powershell import run_powershell

FEATURE_SETTINGS = ("system:hyper_v", "system:vm_platform")


@pytest.fixture(scope="module")
def registry() -> SettingsRegistry:
    return SettingsRegistry(discover_dynamic=False)


@pytest.mark.parametrize("setting_id", FEATURE_SETTINGS)
class TestItSaysWhenItCouldNotRead:
    def test_an_unreadable_feature_is_not_reported_as_disabled(
        self, registry: SettingsRegistry, setting_id: str
    ) -> None:
        setting = registry.get(setting_id)
        assert setting is not None
        command = setting.detect_command

        # The failure path raises: the row reads "unknown" with the reason. It
        # answers an absent reading only when a readable feature list proves the
        # feature is not on this edition (see TestAbsentOnlyWhenTheListProvesIt),
        # never straight from the catch -- that was the same masking again, as
        # "not applicable" instead of "disabled".
        catch = command[command.index("catch") :]
        assert re.search(r"\belse \{ throw \}", catch), (
            f"{setting_id}: a failed read must end the script, not answer a value"
        )
        assert not re.search(r"catch\s*\{\s*'[^']+'\s*\}", command)
        assert "-ErrorAction Stop" in catch  # the list read must not swallow either

    def test_it_does_not_swallow_the_error_into_a_null(
        self, registry: SettingsRegistry, setting_id: str
    ) -> None:
        """`-ErrorAction SilentlyContinue` is exactly how the null got there."""
        setting = registry.get(setting_id)
        assert setting is not None
        assert "SilentlyContinue" not in setting.detect_command
        assert "-ErrorAction Stop" in setting.detect_command

    def test_both_real_states_are_still_reachable(
        self, registry: SettingsRegistry, setting_id: str
    ) -> None:
        """Refusing to guess must not cost the answers it can actually give."""
        setting = registry.get(setting_id)
        assert setting is not None
        assert "'enabled'" in setting.detect_command
        assert "'disabled'" in setting.detect_command
        assert set(setting.choices) >= {"enabled", "disabled"}

    def test_it_can_share_a_batched_session(
        self, registry: SettingsRegistry, setting_id: str
    ) -> None:
        """A command that raises costs itself its batched result.

        Nothing is wrong with the value when it falls back — it just pays for a
        process to get the same answer the session already had a slot for.
        """
        setting = registry.get(setting_id)
        assert setting is not None
        assert command_is_batchable(setting.detect_command.strip())
        assert not any(key.startswith("batch_") for key in setting.detect_args)


# ---------------------------------------------------------------------------
# the scripts, run for real against stubbed cmdlets
# ---------------------------------------------------------------------------


def _stub(feature_state: str | None, listed: list[str] | None, hypervisor: bool = True) -> str:
    """Get-WindowsOptionalFeature as a function; ``None`` state = the named read raises.

    ``listed`` is the answer to the whole-list read, ``None`` meaning it raises too
    (the unelevated case: both reads fail).
    """
    named = (
        f"[pscustomobject]@{{ State = '{feature_state}' }}"
        if feature_state is not None
        else "throw 'The requested operation requires elevation.'"
    )
    whole = (
        "throw 'The requested operation requires elevation.'"
        if listed is None
        else "@(" + ", ".join(f"[pscustomobject]@{{ FeatureName = '{n}' }}" for n in listed) + ")"
    )
    return (
        "function Get-WindowsOptionalFeature { [CmdletBinding()] "
        "param([switch]$Online, $FeatureName) "
        f"if ($FeatureName) {{ {named} }} else {{ {whole} }} }}; "
        "function Get-CimInstance { [CmdletBinding()] param($ClassName) "
        f"[pscustomobject]@{{ HypervisorPresent = ${str(hypervisor).lower()} }} }}; "
    )


FEATURE_NAMES = {
    "system:hyper_v": "Microsoft-Hyper-V",
    "system:vm_platform": "VirtualMachinePlatform",
}

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="runs the shipped PowerShell text; there is none elsewhere"
)


@windows_only
@pytest.mark.parametrize("setting_id", FEATURE_SETTINGS)
class TestAbsentOnlyWhenTheListProvesIt:
    def _detect(self, registry: SettingsRegistry, setting_id: str, stub: str) -> tuple[bool, str]:
        setting = registry.get(setting_id)
        assert setting is not None
        return run_powershell(stub + setting.detect_command)

    @pytest.mark.parametrize("state", ["Enabled", "Disabled"])
    def test_a_readable_feature_is_its_own_state(
        self, registry: SettingsRegistry, setting_id: str, state: str
    ) -> None:
        ok, out = self._detect(registry, setting_id, _stub(state, listed=[]))
        assert ok, out
        assert out.strip().splitlines()[-1] == state.lower()

    def test_unreadable_both_ways_is_a_failed_read_not_a_value(
        self, registry: SettingsRegistry, setting_id: str
    ) -> None:
        # Unelevated: the named read and the whole-list read both raise.
        ok, out = self._detect(registry, setting_id, _stub(None, listed=None))
        assert not ok, out
        assert not is_absent_reading(out.strip())

    def test_a_readable_list_that_lacks_the_feature_is_absent(
        self, registry: SettingsRegistry, setting_id: str
    ) -> None:
        # An edition without the feature: the named read raises, the list is
        # readable and proves it is not there.
        ok, out = self._detect(registry, setting_id, _stub(None, listed=["SomethingElse"]))
        assert ok, out
        assert is_absent_reading(out.strip().splitlines()[-1])

    def test_a_listed_feature_whose_read_failed_is_a_failed_read(
        self, registry: SettingsRegistry, setting_id: str
    ) -> None:
        # The list says the feature exists, so the named read's failure is a real
        # failure and must not be reported as absence.
        ok, out = self._detect(
            registry, setting_id, _stub(None, listed=[FEATURE_NAMES[setting_id]])
        )
        assert not ok, out
