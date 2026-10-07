"""The thermal source runs the readers a machine needs, and no others.

An AMD reader on an NVIDIA machine would put "no AMD library found" on every
screen of every NVIDIA user: a question that does not apply is not a gap (C10). And
when Windows cannot say what hardware there is, no vendor reader may be guessed at —
"we did not know there was a card" is not "the card's tool was missing".
"""

from __future__ import annotations

from collections.abc import Callable

from fpstune.health import thermal_source as module
from fpstune.health.inventory import Disk, Inventory, parse
from fpstune.health.model import Gap
from fpstune.health.thermal import ThermalReading, ThermalSnapshot
from fpstune.health.thermal_source import NO_INVENTORY, thermal_source

_NVIDIA = {
    "kind": "adapter",
    "name": "NVIDIA GeForce RTX 3070 Laptop GPU",
    "pnp": "PCI\\VEN_10DE&DEV_249D&SUBSYS_1",
}
_INTEL = {
    "kind": "adapter",
    "name": "Intel(R) UHD Graphics",
    "pnp": "PCI\\VEN_8086&DEV_9A60&SUBSYS_1",
}
_AMD = {
    "kind": "adapter",
    "name": "AMD Radeon RX 7800 XT",
    "pnp": "PCI\\VEN_1002&DEV_747E&SUBSYS_1",
}
_NVME = {
    "kind": "disk",
    "number": "0",
    "unique_id": "eui.1",
    "name": "NVMe",
    "bus_type": "NVMe",
    "media_type": "SSD",
}
_USB = {
    "kind": "disk",
    "number": "3",
    "unique_id": "usb.9",
    "name": "Portable SSD",
    "bus_type": "USB",
    "media_type": "SSD",
}


def _spy(called: list[str], name: str) -> Callable[[], ThermalSnapshot]:
    def reader() -> ThermalSnapshot:
        called.append(name)
        return ThermalSnapshot()

    return reader


def _patched_readers(monkeypatch, called: list[str]) -> None:
    monkeypatch.setattr(module.gpu_nvidia, "read", _spy(called, "nvidia"))
    monkeypatch.setattr(module.gpu_intel, "read", _spy(called, "intel"))
    monkeypatch.setattr(module.gpu_amd, "read", _spy(called, "amd"))
    monkeypatch.setattr(
        module.nvme, "read", lambda _disks: (called.append("nvme"), ThermalSnapshot())[1]
    )
    monkeypatch.setattr(
        module.smartctl, "read", lambda _disks: (called.append("smartctl"), ThermalSnapshot())[1]
    )
    monkeypatch.setattr(module.acpi_zone, "read", _spy(called, "acpi"))


class TestOnlyTheReadersTheMachineNeedsRun:
    def test_an_nvidia_and_intel_laptop_never_asks_the_amd_reader(self, monkeypatch) -> None:
        called: list[str] = []
        _patched_readers(monkeypatch, called)

        thermal_source(lambda: parse([_NVIDIA, _INTEL, _NVME]))

        assert sorted(called) == ["acpi", "intel", "nvidia", "nvme", "smartctl"]

    def test_an_amd_machine_asks_only_the_amd_gpu_reader(self, monkeypatch) -> None:
        called: list[str] = []
        _patched_readers(monkeypatch, called)

        thermal_source(lambda: parse([_AMD, _NVME]))

        assert "amd" in called and "nvidia" not in called and "intel" not in called


class TestWhenWindowsCannotListTheHardware:
    def test_it_is_one_gap_and_no_reader_is_guessed_at(self, monkeypatch) -> None:
        called: list[str] = []
        _patched_readers(monkeypatch, called)

        result = thermal_source(lambda: Inventory(reason="Windows did not answer this query"))

        assert called == []
        assert result.findings == ()
        assert result.gaps == (Gap("thermal", NO_INVENTORY),)


class TestDrivesOnABusThatHidesTheSensor:
    def test_a_usb_drive_is_one_named_gap(self, monkeypatch) -> None:
        _patched_readers(monkeypatch, [])

        result = thermal_source(lambda: parse([_NVME, _USB]))

        (gap,) = [g for g in result.gaps if g.source == "storage_temperature"]
        assert "Portable SSD" in gap.reason

    def test_nvme_and_sata_drives_are_not_in_that_gap(self, monkeypatch) -> None:
        _patched_readers(monkeypatch, [])

        result = thermal_source(lambda: parse([_NVME]))

        assert [g for g in result.gaps if g.source == "storage_temperature"] == []


class TestTheVerdictRunsOverEveryReader:
    def test_a_hot_reading_from_any_reader_is_a_finding_and_the_cpu_gap_is_always_there(
        self,
    ) -> None:
        hot = ThermalReading(
            component="gpu",
            device_id="PCI\\VEN_10DE&DEV_249D",
            name="NVIDIA GeForce RTX 3070 Laptop GPU",
            temperature_c=99.0,
            limit_c=98.0,
            source="nvidia_smi",
        )

        result = thermal_source(
            lambda: Inventory(disks=(Disk(0, "eui.1", "NVMe", "NVMe", "SSD"),)),
            readers={"nvidia_smi": lambda: ThermalSnapshot(readings=(hot,))},
        )

        assert [(f.severity, f.title_key) for f in result.findings] == [
            ("critical", "health.gpu.temperature")
        ]
        assert "cpu_temperature" in [g.source for g in result.gaps]
