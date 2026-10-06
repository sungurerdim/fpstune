"""MSI mode reads and writes the device's own key, and reset restores the driver's INF default.

The failures these guard (C6, one way back): a reset that deleted ``MSISupported`` on
hardware whose INF installs 1 (MSI switched *off*), a reset that wrote a number nobody
chose when the INF could not be read, and a stash value an earlier release left in the
registry. The registry is an in-memory fake: nothing here touches the real one.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from fpstune.settings.applicability import (
    ALREADY_AT_HARDWARE_DEFAULT,
    NOT_AVAILABLE,
    NOT_SUPPORTED,
)
from fpstune.settings.executors import msi_mode
from fpstune.settings.executors.msi_mode import (
    RETIRED_STASH,
    msi_key_path,
    msi_mode_status,
    msi_mode_write,
    remove_retired_stash,
)
from fpstune.settings.inf_defaults import InterruptDefaults

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

INTEL_IGPU = r"PCI\VEN_8086&DEV_46A6&SUBSYS_11471D05&REV_0C\3&11583659&0&10"
NVIDIA_DGPU = r"PCI\VEN_10DE&DEV_2560&SUBSYS_11471D05&REV_A1\4&2F8C5A4&0&0008"
AMD_DGPU = r"PCI\VEN_1002&DEV_73DF&SUBSYS_0E3A1002&REV_C1\4&2F8C5A4&0&0008"
REALTEK_NIC = r"PCI\VEN_10EC&DEV_8125&SUBSYS_11471D05&REV_05\01000000684CE00000"

GPU = {"device": "gpu"}
NIC = {"device": "nic", "ifindex": 17}


class _Key:
    def __init__(self, path: str) -> None:
        self.path = path

    def __enter__(self) -> _Key:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class FakeWinreg:
    """The slice of winreg the MSI module uses, over a dict of ``path -> {name: dword}``."""

    HKEY_LOCAL_MACHINE = _Key("")
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_DWORD = 4

    def __init__(self, values: dict[str, dict[str, int]] | None = None) -> None:
        self.values = values or {}
        self.deny_writes = False
        self.opened: list[str] = []

    def _full(self, root: _Key, sub: str) -> str:
        return f"{root.path}\\{sub}" if root.path else sub

    def _exists(self, path: str) -> bool:
        return any(k == path or k.startswith(path + "\\") for k in self.values)

    def OpenKey(self, root: _Key, sub: str, _reserved: int = 0, _access: int = 0) -> _Key:
        path = self._full(root, sub)
        self.opened.append(path)
        if not self._exists(path):
            raise FileNotFoundError(path)
        return _Key(path)

    def CreateKeyEx(self, root: _Key, sub: str, _reserved: int, _access: int) -> _Key:
        path = self._full(root, sub)
        if self.deny_writes:
            raise PermissionError(5, "denied")
        self.values.setdefault(path, {})
        return _Key(path)

    def EnumKey(self, key: _Key, index: int) -> str:
        prefix = key.path + "\\"
        children = sorted(
            {k[len(prefix) :].split("\\", 1)[0] for k in self.values if k.startswith(prefix)}
        )
        if index >= len(children):
            raise OSError("no more items")
        return children[index]

    def QueryValueEx(self, key: _Key, name: str) -> tuple[int, int]:
        try:
            return self.values[key.path][name], self.REG_DWORD
        except KeyError:
            raise FileNotFoundError(name) from None

    def SetValueEx(self, key: _Key, name: str, _res: int, kind: int, value: int) -> None:
        assert kind == self.REG_DWORD
        self.values.setdefault(key.path, {})[name] = value

    def DeleteValue(self, key: _Key, name: str) -> None:
        if self.deny_writes:
            raise PermissionError(5, "denied")
        try:
            del self.values[key.path][name]
        except KeyError:
            raise FileNotFoundError(name) from None


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> FakeWinreg:
    fake = FakeWinreg()
    monkeypatch.setitem(sys.modules, "winreg", fake)
    return fake


def host(
    monkeypatch: pytest.MonkeyPatch,
    *,
    display: list[str] | None = None,
    nic_instance: str | None = None,
    inf: InterruptDefaults | None = InterruptDefaults(1, None),
) -> list[str]:
    """Fake the device lookups and the INF; returns the instance ids the INF was asked for."""
    from fpstune.utils.winapi import devnode, netluid

    asked: list[str] = []

    def fake_defaults(instance_id: str) -> InterruptDefaults | None:
        asked.append(instance_id)
        return inf

    monkeypatch.setattr(devnode, "present_device_ids", lambda _guid: display or [])
    monkeypatch.setattr(netluid, "adapter_instance_id", lambda _index: nic_instance)
    monkeypatch.setattr(msi_mode, "interrupt_defaults", fake_defaults)
    return asked


def seed(registry: FakeWinreg, instance_id: str, **values: int) -> str:
    path = msi_key_path(instance_id)
    registry.values[path] = dict(values)
    return path


class TestDetect:
    def test_the_dgpu_key_is_read_when_the_igpu_enumerates_first(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Keyed on the vendor id, so enumeration order cannot pick the wrong device: the
        Intel device's key never carries MSISupported, and reading it would answer
        'default' on every hybrid laptop."""
        host(monkeypatch, display=[INTEL_IGPU, NVIDIA_DGPU], inf=InterruptDefaults(None, None))
        seed(registry, NVIDIA_DGPU, MSISupported=1)
        seed(registry, INTEL_IGPU)
        assert msi_mode_status(GPU) == "enabled"
        assert all("VEN_10DE" in p for p in registry.opened), registry.opened

    def test_an_amd_card_is_found_by_the_same_rule(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        host(monkeypatch, display=[INTEL_IGPU, AMD_DGPU], inf=InterruptDefaults(None, None))
        seed(registry, AMD_DGPU, MSISupported=1)
        assert msi_mode_status(GPU) == "enabled"
        assert all("VEN_1002" in p for p in registry.opened)

    def test_an_intel_only_machine_is_not_supported_and_nothing_is_opened(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = host(monkeypatch, display=[INTEL_IGPU])
        assert msi_mode_status(GPU) == NOT_SUPPORTED
        assert registry.opened == [] and asked == []

    def test_a_driver_that_installs_msi_on_is_not_applicable_not_enabled(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The INF installs 1 and the key holds 1: that is the stock state, so reset (which
        writes 1) could never read back as 'default'. Reporting 'enabled' here would make
        'reset all' fail verify."""
        host(monkeypatch, display=[NVIDIA_DGPU], inf=InterruptDefaults(1, 1))
        seed(registry, NVIDIA_DGPU, MSISupported=1)
        assert msi_mode_status(GPU) == ALREADY_AT_HARDWARE_DEFAULT

    @pytest.mark.parametrize("held", [{}, {"MSISupported": 0}])
    def test_a_machine_drifted_off_the_drivers_msi_on_reads_default(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch, held: dict[str, int]
    ) -> None:
        """Another 'optimizer' deleted or zeroed the value the INF installs: the row must be
        offered so that reset puts it back."""
        host(monkeypatch, display=[NVIDIA_DGPU], inf=InterruptDefaults(1, None))
        seed(registry, NVIDIA_DGPU, **held)
        assert msi_mode_status(GPU) == "default"

    @pytest.mark.parametrize(
        ("inf", "held", "expected"),
        [
            (InterruptDefaults(None, None), {}, "default"),
            (InterruptDefaults(None, None), {"MSISupported": 1}, "enabled"),
            (InterruptDefaults(0, None), {"MSISupported": 0}, "default"),
            (InterruptDefaults(0, None), {"MSISupported": 1}, "enabled"),
        ],
    )
    def test_a_driver_that_does_not_install_msi_on_is_tunable(
        self,
        registry: FakeWinreg,
        monkeypatch: pytest.MonkeyPatch,
        inf: InterruptDefaults,
        held: dict[str, int],
        expected: str,
    ) -> None:
        host(monkeypatch, nic_instance=REALTEK_NIC, inf=inf)
        seed(registry, REALTEK_NIC, **held)
        assert msi_mode_status(NIC) == expected

    def test_a_default_that_cannot_be_derived_is_not_offered(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An enable with no derivable way back is not a tweak."""
        host(monkeypatch, display=[NVIDIA_DGPU], inf=None)
        seed(registry, NVIDIA_DGPU, MSISupported=0)
        assert msi_mode_status(GPU) == NOT_AVAILABLE

    @pytest.mark.usefixtures("registry")
    def test_an_adapter_that_is_gone_is_not_supported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        host(monkeypatch, nic_instance=None)
        assert msi_mode_status({"device": "nic", "ifindex": 99}) == NOT_SUPPORTED


class TestWrite:
    def test_enabling_writes_msi_on_only_under_the_dgpu_and_records_nothing(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        host(monkeypatch, display=[INTEL_IGPU, NVIDIA_DGPU], inf=InterruptDefaults(None, None))
        dgpu = seed(registry, NVIDIA_DGPU, MSISupported=0)
        igpu = seed(registry, INTEL_IGPU)
        assert msi_mode_write({**GPU, "value": "enabled"}) == (True, None)
        assert registry.values[dgpu] == {"MSISupported": 1}  # no second value, no stash
        assert registry.values[igpu] == {}

    def test_enabling_creates_the_key_when_the_driver_never_made_it(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        host(monkeypatch, nic_instance=REALTEK_NIC, inf=InterruptDefaults(None, None))
        assert msi_mode_write({**NIC, "value": "enabled"}) == (True, None)
        assert registry.values[msi_key_path(REALTEK_NIC)] == {"MSISupported": 1}

    def test_reset_writes_what_the_inf_installs_not_a_recorded_original(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        host(monkeypatch, nic_instance=REALTEK_NIC, inf=InterruptDefaults(1, 16))
        path = seed(registry, REALTEK_NIC, MSISupported=0)
        assert msi_mode_write({**NIC, "value": "default"}) == (True, None)
        assert registry.values[path] == {"MSISupported": 1, "MessageNumberLimit": 16}

    def test_reset_writes_a_zero_the_inf_installs_rather_than_deleting(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        host(monkeypatch, nic_instance=REALTEK_NIC, inf=InterruptDefaults(0, None))
        path = seed(registry, REALTEK_NIC, MSISupported=1)
        msi_mode_write({**NIC, "value": "default"})
        assert registry.values[path] == {"MSISupported": 0}

    def test_reset_deletes_the_value_when_the_inf_sets_none(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        host(monkeypatch, display=[NVIDIA_DGPU], inf=InterruptDefaults(None, None))
        path = seed(registry, NVIDIA_DGPU, MSISupported=1, MessageNumberLimit=4)
        assert msi_mode_write({**GPU, "value": "default"}) == (True, None)
        assert registry.values[path] == {"MessageNumberLimit": 4}

    def test_reset_of_a_value_that_is_already_absent_succeeds(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        host(monkeypatch, display=[NVIDIA_DGPU], inf=InterruptDefaults(None, None))
        seed(registry, NVIDIA_DGPU)
        assert msi_mode_write({**GPU, "value": "default"}) == (True, None)

    def test_reset_with_no_derivable_default_writes_nothing_and_says_why(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        host(monkeypatch, display=[NVIDIA_DGPU], inf=None)
        path = seed(registry, NVIDIA_DGPU, MSISupported=1)
        ok, message = msi_mode_write({**GPU, "value": "default"})
        assert not ok and message and "INF" in message
        assert registry.values[path] == {"MSISupported": 1}

    @pytest.mark.parametrize("value", ["enabled", "default"])
    def test_the_retired_stash_is_deleted_on_apply_and_on_reset(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        host(monkeypatch, display=[NVIDIA_DGPU], inf=InterruptDefaults(None, None))
        path = seed(registry, NVIDIA_DGPU, MSISupported=0, **{RETIRED_STASH: -1})
        assert msi_mode_write({**GPU, "value": value}) == (True, None)
        assert RETIRED_STASH not in registry.values[path]

    def test_a_refused_write_is_reported_as_a_failure_not_ok(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Under Enum\\<device> Windows can let only SYSTEM write; a swallowed refusal
        said 'ok' and verify then read the old value."""
        host(monkeypatch, display=[NVIDIA_DGPU], inf=InterruptDefaults(None, None))
        seed(registry, NVIDIA_DGPU)
        registry.deny_writes = True
        ok, message = msi_mode_write({**GPU, "value": "enabled"})
        assert not ok and message

    def test_a_value_that_is_neither_mode_is_refused_before_anything_is_written(
        self, registry: FakeWinreg, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        host(monkeypatch, display=[NVIDIA_DGPU])
        path = seed(registry, NVIDIA_DGPU, MSISupported=1)
        ok, _ = msi_mode_write({**GPU, "value": "disabled"})
        assert not ok and registry.values[path] == {"MSISupported": 1}

    @pytest.mark.usefixtures("registry")
    def test_no_device_is_a_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        host(monkeypatch, display=[INTEL_IGPU])
        ok, _ = msi_mode_write({**GPU, "value": "enabled"})
        assert not ok


class TestRetiredStashSweep:
    def _tree(self) -> dict[str, dict[str, int]]:
        values: dict[str, dict[str, int]] = {}
        for instance_id, held in (
            (NVIDIA_DGPU, {"MSISupported": 1, RETIRED_STASH: 0}),
            (REALTEK_NIC, {"MSISupported": 1}),
            (INTEL_IGPU, {RETIRED_STASH: -1}),
        ):
            values[msi_key_path(instance_id)] = dict(held)
        # A device whose key has no interrupt properties at all.
        values[r"SYSTEM\CurrentControlSet\Enum\PCI\VEN_1234&DEV_5678\1\Device Parameters"] = {}
        return values

    def test_every_device_carrying_the_stash_is_cleaned_and_nothing_else_is_touched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeWinreg(self._tree())
        monkeypatch.setitem(sys.modules, "winreg", fake)
        assert sorted(remove_retired_stash()) == sorted([NVIDIA_DGPU, INTEL_IGPU])
        assert fake.values[msi_key_path(NVIDIA_DGPU)] == {"MSISupported": 1}
        assert fake.values[msi_key_path(INTEL_IGPU)] == {}
        assert fake.values[msi_key_path(REALTEK_NIC)] == {"MSISupported": 1}

    def test_a_second_sweep_finds_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeWinreg(self._tree())
        monkeypatch.setitem(sys.modules, "winreg", fake)
        remove_retired_stash()
        assert remove_retired_stash() == []

    def test_a_refused_delete_is_logged_and_does_not_stop_the_sweep(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        fake = FakeWinreg(self._tree())
        fake.deny_writes = True
        monkeypatch.setitem(sys.modules, "winreg", fake)
        with caplog.at_level("WARNING"):
            assert remove_retired_stash() == []
        assert "Cannot remove the retired MSI stash" in caplog.text


def test_the_python_dispatch_tables_carry_both_halves() -> None:
    from fpstune.settings.executors.python_actions import PYTHON_ACTIONS, PYTHON_DETECTORS

    detector: Any = PYTHON_DETECTORS["msi_mode_status"]
    action: Any = PYTHON_ACTIONS["msi_mode_write"]
    assert detector is msi_mode_status and action is msi_mode_write
