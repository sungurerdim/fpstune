"""The primary GPU's vendor is the PCI vendor ID in its PNPDeviceID, never a word in its name.

Guards against the old name match (`nvidia`/`geforce`, `radeon`/`rx `, `intel`):
a board whose name carries none of those words came back UNKNOWN, and a name
that carries another vendor's word came back as the wrong vendor (C10).
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import fpstune.utils.detect as detect
from fpstune.utils import process_watch
from fpstune.utils.detect import GpuVendor, gpu_vendor_from_pnp
from fpstune.utils.gpu_vendor_ids import vendor_id_of

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="GPU probe is Windows-only")


@pytest.mark.parametrize(
    ("pnp", "vendor"),
    [
        (r"PCI\VEN_10DE&DEV_2820&SUBSYS_0A5B1028&REV_A1\4&2B4F&0&0008", GpuVendor.NVIDIA),
        (r"PCI\VEN_1002&DEV_73DF&SUBSYS_E4521043&REV_C1\6&1C2B&0&00080008", GpuVendor.AMD),
        (r"PCI\VEN_8086&DEV_56A0&SUBSYS_10201DA2&REV_08\4&15D5&0&0008", GpuVendor.INTEL),
        (r"pci\ven_10de&dev_2204&subsys_00000000&rev_a1\4&0&0", GpuVendor.NVIDIA),
        (r"PCI\VEN_1414&DEV_008C&SUBSYS_00000000&REV_00\3&0&0", GpuVendor.UNKNOWN),
        ("", GpuVendor.UNKNOWN),
        ("ROOT\\BASICDISPLAY\\0000", GpuVendor.UNKNOWN),
    ],
)
def test_vendor_comes_from_the_pci_vendor_id(pnp: str, vendor: GpuVendor) -> None:
    assert gpu_vendor_from_pnp(pnp) == vendor


def test_vendor_id_of_reads_the_id_not_a_substring_of_the_device() -> None:
    # DEV_10DE is a device number, not a vendor: only VEN_ names the vendor.
    assert vendor_id_of(r"PCI\VEN_8086&DEV_10DE&SUBSYS_0\1") == "8086"


def _cim_probe(name: str, pnp: str) -> SimpleNamespace:
    out = f"Name={name}\nDriver=32.0.101.6881\nVramBytes=8589934592\nPNP={pnp}\n"
    return SimpleNamespace(returncode=0, stdout=out, stderr="")


@pytest.fixture
def no_nvidia_smi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detect, "nvidia_smi", lambda: None)
    monkeypatch.setattr(detect, "powershell_exe", lambda: "powershell.exe")


@pytest.mark.parametrize(
    ("name", "pnp", "vendor"),
    [
        # A board name with none of the old keywords: the name match said UNKNOWN.
        (
            "Navi Compute Board 6800M",
            r"PCI\VEN_1002&DEV_73EF&SUBSYS_1&REV_C3\6&0",
            GpuVendor.AMD,
        ),
        ("Arc A770 Graphics", r"PCI\VEN_8086&DEV_56A0&SUBSYS_1&REV_08\4&0", GpuVendor.INTEL),
        ("RTX A2000 Laptop GPU", r"PCI\VEN_10DE&DEV_25B8&SUBSYS_1&REV_A1\4&0", GpuVendor.NVIDIA),
        # Vendor-name and vendor-ID disagree: the ID wins. The name says Intel,
        # the silicon is NVIDIA's; the old name match returned INTEL.
        ("Intel-branded OEM board", r"PCI\VEN_10DE&DEV_2204&SUBSYS_1&REV_A1\4&0", GpuVendor.NVIDIA),
        ("NVIDIA GeForce lookalike", r"PCI\VEN_1002&DEV_73DF&SUBSYS_1&REV_C1\6&0", GpuVendor.AMD),
        # A vendor that is none of the three is unknown, whatever the name claims.
        (
            "NVIDIA GeForce RTX 4070",
            r"PCI\VEN_1414&DEV_008C&SUBSYS_0&REV_00\3&0",
            GpuVendor.UNKNOWN,
        ),
    ],
)
@pytest.mark.usefixtures("no_nvidia_smi")
def test_detected_vendor_follows_the_id_when_the_name_disagrees(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    pnp: str,
    vendor: GpuVendor,
) -> None:
    monkeypatch.setattr(process_watch, "run", lambda *_a, **_k: _cim_probe(name, pnp))

    info = detect._detect_gpu_sync()

    assert info is not None
    assert info.name == name
    assert info.vendor == vendor


@pytest.mark.usefixtures("no_nvidia_smi")
def test_no_pnp_id_means_unknown_vendor_not_a_name_guess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = "Name=NVIDIA GeForce RTX 4070\nDriver=591.59\n"
    monkeypatch.setattr(
        process_watch,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=out, stderr=""),
    )

    info = detect._detect_gpu_sync()

    assert info is not None
    assert info.vendor == GpuVendor.UNKNOWN


def test_nvidia_smi_path_is_nvidia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detect, "nvidia_smi", lambda: "nvidia-smi.exe")
    smi = SimpleNamespace(
        returncode=0, stdout="NVIDIA GeForce RTX 4070 Laptop GPU, 591.59, 8192\n", stderr=""
    )
    monkeypatch.setattr(process_watch, "run", lambda *_a, **_k: smi)

    info = detect._detect_gpu_sync()

    assert info is not None
    assert info.vendor == GpuVendor.NVIDIA
