"""The boot-configuration guards read numbers from the store's hive and remove only what they find.

Failures these tests guard against:

- a guard that reads the boot editor's printed text, which is translated: the shipped detect
  must be the hive's bytes, the same in every Windows language;
- an unreadable store answering "stock": a failed read must surface as a failed read (#104),
  or a machine that is forcing HPET would be told it is fine;
- the element id and the name the removal command is given drifting apart, so the guard
  reads one value and deletes another (each pair is pinned below by a stand-in command that
  only knows the name);
- a removal that touches an entry that is not a Windows boot loader, or another element of
  the one it cleans;
- a drift state being offered as something to write back.

The tree is a copy of the store under a throwaway key in the current user's hive, and the
removal command is a PowerShell function shadowing the real one, so nothing here can reach
the machine's own boot configuration. The shipped script runs unchanged under the real
runner (Windows only, for that reason).
"""

from __future__ import annotations

import dataclasses
import sys
import uuid
from collections.abc import Iterator
from typing import Any, NamedTuple

import pytest

from fpstune.settings.applicability import values_equal
from fpstune.settings.base import SettingExecutor
from fpstune.settings.definitions.timer import DYNAMIC_TICK, PLATFORM_CLOCK, TSC_SYNC_POLICY
from fpstune.settings.executors import CommandExecutor
from fpstune.utils.powershell import run_powershell

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="runs the shipped PowerShell text and winreg"
)

LOADER = 0x10200003
LOADER_GROUP = 0x20200003
BOOT_MANAGER = 0x10100002

BOOLEAN_ON = b"\x01"
BOOLEAN_OFF = b"\x00"
INTEGER_ENHANCED = (2).to_bytes(8, "little")
INTEGER_DEFAULT = (0).to_bytes(8, "little")


# One script builder serves all three guards; the slow paths (a real PowerShell each) run on the
# first, and the integer element is checked on its own where its encoding differs.
class _Guard(NamedTuple):
    """One row, the name its removal command is given, its element, and a value that is drift."""

    row: SettingExecutor
    name: str
    element: str
    forced: bytes


GUARDS = [
    pytest.param(
        _Guard(PLATFORM_CLOCK, "useplatformclock", "260000a2", BOOLEAN_ON), id="platform_clock"
    ),
    pytest.param(
        _Guard(DYNAMIC_TICK, "disabledynamictick", "260000a5", BOOLEAN_ON), id="dynamic_tick"
    ),
    pytest.param(
        _Guard(TSC_SYNC_POLICY, "tscsyncpolicy", "250000a6", INTEGER_ENHANCED), id="tsc_sync_policy"
    ),
]
OTHER_ELEMENT = "26000010"  # an element none of the guards owns; it must survive every removal


class _Store:
    """A copy of the boot store: ``Objects\\{guid}\\Description\\Type`` and ``Elements\\<hex>\\Element``."""

    def __init__(self) -> None:
        import winreg

        self.base = rf"Software\fpstune-test-boot-{uuid.uuid4().hex}"
        self.objects = rf"{self.base}\Objects"
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.objects).Close()

    def add(self, kind: int, elements: dict[str, bytes]) -> str:
        import winreg

        guid = "{" + str(uuid.uuid4()) + "}"
        entry = rf"{self.objects}\{guid}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{entry}\Description") as key:
            winreg.SetValueEx(key, "Type", 0, winreg.REG_DWORD, kind)
        for element, data in elements.items():
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{entry}\Elements\{element}") as key:
                winreg.SetValueEx(key, "Element", 0, winreg.REG_BINARY, data)
        return guid

    def has(self, guid: str, element: str) -> bool:
        import winreg

        try:
            winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, rf"{self.objects}\{guid}\Elements\{element}"
            ).Close()
        except FileNotFoundError:
            return False
        return True

    def drop(self) -> None:
        import winreg

        def walk(path: str) -> None:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
            except FileNotFoundError:
                return
            with key:
                names = []
                index = 0
                while True:
                    try:
                        names.append(winreg.EnumKey(key, index))
                    except OSError:
                        break
                    index += 1
            for name in names:
                walk(rf"{path}\{name}")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)

        walk(self.base)


@pytest.fixture
def store() -> Iterator[_Store]:
    fake = _Store()
    try:
        yield fake
    finally:
        fake.drop()


def _stand_in(store: _Store, *, refuse: bool = False) -> str:
    """A PowerShell function that answers to the removal command by name alone."""
    return (
        "function bcdedit { $global:LASTEXITCODE = 0; "
        f"if ({'$true' if refuse else '$false'}) {{ $global:LASTEXITCODE = 5; "
        "'Access is denied.'; return }; "
        "$hex = @{ useplatformclock = '260000a2'; disabledynamictick = '260000a5'; "
        "tscsyncpolicy = '250000a6' }[$args[2]]; "
        "if ($args[0] -ne '/deletevalue' -or -not $hex) { $global:LASTEXITCODE = 1; "
        "'The element was not found.'; return }; "
        "$k = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("
        f"'{store.objects}\\' + $args[1] + '\\Elements', $true); "
        "$k.DeleteSubKeyTree($hex); 'The operation completed successfully.' }; "
    )


def _on(row: SettingExecutor, store: _Store) -> SettingExecutor:
    """The shipped row, pointed at the copy of the store."""
    where = {"root": "CurrentUser", "store": store.objects}
    return dataclasses.replace(row, detect_args=where, apply_args=where)


@pytest.fixture
def run_on(monkeypatch: pytest.MonkeyPatch, store: _Store) -> Any:
    def install(*, refuse: bool = False) -> None:
        stand_in = _stand_in(store, refuse=refuse)

        def run(command: str, *args: Any, **kwargs: Any) -> tuple[bool, str]:
            return run_powershell(stand_in + command, *args, **kwargs)

        monkeypatch.setattr("fpstune.settings.executors.powershell.run_powershell", run)

    return install


@pytest.mark.parametrize("guard", GUARDS)
def test_detect_apply_reset_round_trip(guard: _Guard, store: _Store, run_on: Any) -> None:
    row, element, forced = guard.row, guard.element, guard.forced
    run_on()
    loader = store.add(LOADER, {element: forced, OTHER_ELEMENT: BOOLEAN_ON})
    group = store.add(LOADER_GROUP, {element: forced})
    not_a_loader = store.add(BOOT_MANAGER, {element: forced})
    on = _on(row, store)

    drifted, error = CommandExecutor.detect(on)
    assert (drifted, error) == ("changed", None)
    assert not values_equal(drifted, on.recommended_value)

    ok, error = CommandExecutor.apply(on, on.recommended_value)
    assert (ok, error) == (True, None)
    after, error = CommandExecutor.detect(on)
    assert (after, error) == ("stock", None)
    assert values_equal(after, on.recommended_value)
    assert not store.has(loader, element)
    assert not store.has(group, element)
    assert store.has(loader, OTHER_ELEMENT), "another element of the same entry was removed"
    assert store.has(not_a_loader, element), "an entry that is not a Windows loader was edited"

    ok, error = CommandExecutor.apply(on, on.default_value)
    assert (ok, error) == (True, None)
    back, error = CommandExecutor.detect(on)
    assert (back, error) == ("stock", None)
    assert values_equal(back, on.default_value)


@pytest.mark.parametrize("guard", [GUARDS[0], GUARDS[2]])
def test_a_value_that_means_the_default_is_not_drift(
    guard: _Guard, store: _Store, run_on: Any
) -> None:
    run_on()
    store.add(LOADER, {guard.element: INTEGER_DEFAULT if len(guard.forced) == 8 else BOOLEAN_OFF})

    assert CommandExecutor.detect(_on(guard.row, store)) == ("stock", None)


@pytest.mark.parametrize("guard", GUARDS[:1])
def test_a_store_with_no_such_element_is_stock(guard: _Guard, store: _Store, run_on: Any) -> None:
    run_on()
    store.add(LOADER, {OTHER_ELEMENT: BOOLEAN_ON})

    assert CommandExecutor.detect(_on(guard.row, store)) == ("stock", None)


@pytest.mark.parametrize("guard", GUARDS[:1])
def test_an_unreadable_store_is_a_failed_read_never_stock(
    guard: _Guard, store: _Store, run_on: Any
) -> None:
    run_on()
    gone = dataclasses.replace(
        guard.row,
        detect_args={"root": "CurrentUser", "store": store.objects + "-missing"},
    )

    value, error = CommandExecutor.detect(gone)

    assert value is None
    assert error is not None and "not readable" in error


@pytest.mark.parametrize("guard", GUARDS[:1])
def test_a_refused_removal_is_a_readable_error_and_changes_nothing(
    guard: _Guard, store: _Store, run_on: Any
) -> None:
    run_on(refuse=True)
    element = guard.element
    loader = store.add(LOADER, {element: guard.forced})
    on = _on(guard.row, store)

    ok, error = CommandExecutor.apply(on, on.recommended_value)

    assert ok is False
    assert error is not None
    assert "Windows refused" in error and loader in error and "Access is denied." in error
    assert store.has(loader, element)
    assert CommandExecutor.detect(on) == ("changed", None)


@pytest.mark.parametrize("guard", GUARDS)
def test_the_row_is_a_guard_that_reads_numbers_and_never_writes_its_drift_state(
    guard: _Guard,
) -> None:
    row, name, element = guard.row, guard.name, guard.element
    assert row.recommended_value == row.default_value == "stock"
    assert row.unwritable_values == ("changed",)
    assert row.requires_reboot
    assert row.default_source is not None and row.default_source.value == "windows_stock"
    # The hive's bytes, not the boot editor's translated text.
    assert "bcdedit" not in row.detect_command.lower()
    assert f"Elements\\{element}" in row.detect_command
    assert f"/deletevalue $n {name} " in row.apply_command
