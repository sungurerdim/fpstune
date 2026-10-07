"""Reserved Storage: detect, apply and reset round-trip, and a refused change reads as a reason.

Failures these tests guard against:

- the row detecting through text (``DISM`` / the cmdlet's printed state), which is
  translated, instead of the one DWORD Windows keeps the flag in;
- an apply that Windows refuses (it will not change the reserve while an update is
  pending or installing) surfacing as a crash or a bare "Command failed" instead of
  a readable error, with the machine left as it was;
- a reset that does not return to Windows' own state, so "Windows default" is a
  claim and not a round trip;
- a Windows without the feature reading as "the reserve is off" instead of "not here".

The machine is a fake: ``winreg`` answers from a dict, and the Dism cmdlet is a
PowerShell function shadowing the real one, so the *shipped* apply script runs
unchanged under the real runner (Windows only, for that reason).
"""

from __future__ import annotations

import re
import sys
from typing import Any

import pytest

from fpstune.settings.applicability import ABSENT_READINGS, values_equal
from fpstune.settings.definitions.system import SYSTEM_RESERVED_STORAGE as ROW
from fpstune.settings.executors import CommandExecutor
from fpstune.utils.powershell import run_powershell

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="runs the shipped PowerShell text and winreg"
)

KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\ReserveManager"


class _Machine:
    """What the registry flag and the Dism cmdlet look like on one fake Windows."""

    def __init__(self, flag: int | None, *, update_pending: bool = False) -> None:
        self.flag = flag
        self.update_pending = update_pending
        self.states_asked: list[str] = []

    def stub(self) -> str:
        if self.update_pending:
            body = "throw 'The operation cannot be performed: servicing is in progress.'"
        else:
            body = "Write-Output ('STUB-STATE:' + $State)"
        return (
            "function Set-WindowsReservedStorageState { [CmdletBinding()] "
            f"param($State) {body} }}; "
        )

    def run_powershell(self, command: str, *args: Any, **kwargs: Any) -> tuple[bool, str]:
        ok, out = run_powershell(self.stub() + command, *args, **kwargs)
        wrote = re.search(r"STUB-STATE:(\w+)", out)
        if ok and wrote:
            self.states_asked.append(wrote.group(1))
            self.flag = 1 if wrote.group(1) == "Enabled" else 0
        return ok, out


@pytest.fixture
def machine(monkeypatch: pytest.MonkeyPatch) -> Any:
    import winreg

    def build(flag: int | None, *, update_pending: bool = False) -> _Machine:
        fake = _Machine(flag, update_pending=update_pending)

        class _Key:
            def __enter__(self) -> _Key:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        def open_key(_root: int, path: str, *_args: Any) -> _Key:
            if path != KEY:
                raise FileNotFoundError(path)
            return _Key()

        def query(_key: _Key, name: str) -> tuple[int, int]:
            if name != "ShippedWithReserves" or fake.flag is None:
                raise FileNotFoundError(name)
            return fake.flag, winreg.REG_DWORD

        monkeypatch.setattr(winreg, "OpenKey", open_key)
        monkeypatch.setattr(winreg, "QueryValueEx", query)
        monkeypatch.setattr(
            "fpstune.settings.executors.powershell.run_powershell", fake.run_powershell
        )
        return fake

    return build


def test_the_row_is_a_window_stock_reserve_that_is_offered_not_assumed() -> None:
    assert ROW.default_value == "enabled"
    assert ROW.recommended_value == "disabled"
    assert ROW.default_source is not None and ROW.default_source.value == "windows_stock"
    assert ROW.scope.value == "complete"
    assert ROW.risk_warning


def test_detect_apply_reset_round_trip(machine: Any) -> None:
    fake = machine(1)

    stock, error = CommandExecutor.detect(ROW)
    assert (stock, error) == ("enabled", None)
    assert values_equal(stock, ROW.default_value)

    ok, error = CommandExecutor.apply(ROW, ROW.recommended_value)
    assert (ok, error) == (True, None)
    optimized, error = CommandExecutor.detect(ROW)
    assert (optimized, error) == ("disabled", None)
    assert values_equal(optimized, ROW.recommended_value)

    ok, error = CommandExecutor.apply(ROW, ROW.default_value)
    assert (ok, error) == (True, None)
    back, error = CommandExecutor.detect(ROW)
    assert (back, error) == ("enabled", None)
    assert values_equal(back, ROW.default_value)

    # The cmdlet was asked in its own spelling, in the order the round trip ran.
    assert fake.states_asked == ["Disabled", "Enabled"]


def test_a_refused_change_is_a_readable_error_and_changes_nothing(machine: Any) -> None:
    fake = machine(1, update_pending=True)

    ok, error = CommandExecutor.apply(ROW, "disabled")

    assert ok is False
    assert error is not None
    assert "update is pending or installing" in error
    assert "servicing is in progress" in error  # Windows' own words survive
    assert "\n" not in error
    assert fake.flag == 1
    assert CommandExecutor.detect(ROW) == ("enabled", None)


def test_a_windows_without_the_feature_is_not_here_rather_than_off(machine: Any) -> None:
    machine(None)

    reading, error = CommandExecutor.detect(ROW)

    assert error is None
    assert reading in ABSENT_READINGS
    assert reading not in ROW.choices
