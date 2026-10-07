"""Which GPU is integrated and which is discrete comes from the PCI vendor ID.

`gpu_assignment` used to tell the two apart by matching `Win32_VideoController.Name`
against `Intel|UHD|Iris` and `NVIDIA|GeForce|Radeon`. A board whose name carries
none of those words (`RTX A2000 Laptop GPU`, `RX 6800M`) was invisible to the
probe, so a genuinely hybrid machine answered `single_gpu` and the setting that
exists to keep games off the integrated chip was never offered (C10: capability,
not model lists). The vendor ID in `PNPDeviceID` does not change with branding.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from fpstune.settings.applicability import classify_gpu_adapters
from fpstune.settings.definitions.gpu import _HYBRID_GUARD, GPU_LAPTOP_ASSIGNMENT
from fpstune.utils.system_tools import powershell_exe

INTEL_IGPU = r"PCI\VEN_8086&DEV_46A6&SUBSYS_11471D05&REV_0C\3&11583659&0&10"
NVIDIA_DGPU = r"PCI\VEN_10DE&DEV_2560&SUBSYS_11471D05&REV_A1\4&2F8C5A4&0&0008"
AMD_DGPU = r"PCI\VEN_1002&DEV_73DF&SUBSYS_0E3A1002&REV_C1\4&2F8C5A4&0&0008"
# A vendor ID no table lists: neither side, whatever the board is called.
UNLISTED = r"PCI\VEN_1234&DEV_0001&SUBSYS_00000000&REV_00\4&00000000&0&0000"

# (adapter names that no name pattern would recognise, PNPDeviceIDs, integrated?, discrete?)
CASES = [
    pytest.param(["Graphics"], [INTEL_IGPU], True, False, id="intel-igpu-alone"),
    pytest.param(
        ["Graphics", "RTX A2000 Laptop GPU"],
        [INTEL_IGPU, NVIDIA_DGPU],
        True,
        True,
        id="intel-plus-nvidia-named-without-vendor-word",
    ),
    pytest.param(
        ["Graphics", "RX 6800M"],
        [INTEL_IGPU, AMD_DGPU],
        True,
        True,
        id="intel-plus-amd-named-without-vendor-word",
    ),
    pytest.param(["NVIDIA GeForce"], [NVIDIA_DGPU], False, True, id="nvidia-alone"),
    pytest.param(
        ["Intel(R) Iris(R) Xe Graphics", "GeForce-lookalike"],
        [INTEL_IGPU, UNLISTED],
        True,
        False,
        id="a-name-that-says-geforce-on-an-unlisted-vendor-is-not-discrete",
    ),
    pytest.param(
        ["Intel(R) UHD Graphics"],
        [INTEL_IGPU.lower()],
        True,
        False,
        id="vendor-id-case-is-not-significant",
    ),
    pytest.param([], [], False, False, id="no-adapters"),
]


@pytest.mark.parametrize("case", [c.values for c in CASES], ids=[c.id for c in CASES])
def test_python_classification_reads_vendor_ids(
    case: tuple[list[str], list[str], bool, bool],
) -> None:
    _names, ids, igpu, dgpu = case
    assert classify_gpu_adapters(ids) == (igpu, dgpu)


@pytest.mark.skipif(sys.platform != "win32", reason="runs the shipped PowerShell guard")
def test_shipped_powershell_guard_agrees_with_python_classification() -> None:
    """The probe fpstune really sends to PowerShell, over each case's adapters."""
    cases = [(c.values[0], c.values[1], c.values[2], c.values[3]) for c in CASES]
    script_lines = []
    for index, (names, ids, _igpu, _dgpu) in enumerate(cases):
        adapters = ",".join(
            f"[pscustomobject]@{{Name='{n}';PNPDeviceID='{i}'}}"
            for n, i in zip(names, ids, strict=True)
        )
        # The guard's own first statement reads the live machine; replace it with
        # the case's adapters and run the rest of the shipped string verbatim.
        classify = _HYBRID_GUARD.split("; ", 1)[1]
        script_lines.append(
            f"$gpus = @({adapters}); {classify}'{index}|' + [bool]$igpu + '|' + [bool]$dgpu"
        )
    assert _HYBRID_GUARD.startswith("$gpus = Get-CimInstance Win32_VideoController")
    proc = subprocess.run(
        [powershell_exe(), "-NoProfile", "-NonInteractive", "-Command", "\n".join(script_lines)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={**os.environ},
    )
    assert proc.returncode == 0, proc.stderr
    got = {line.split("|")[0]: line.split("|")[1:] for line in proc.stdout.split()}
    for index, (_names, ids, igpu, dgpu) in enumerate(cases):
        assert got[str(index)] == [str(igpu), str(dgpu)], (ids, proc.stdout)


def test_the_guard_names_no_gpu_model_or_marketing_word() -> None:
    """No name pattern is left anywhere in the probe the setting sends."""
    for command in (GPU_LAPTOP_ASSIGNMENT.detect_command, GPU_LAPTOP_ASSIGNMENT.apply_command):
        assert command is not None
        assert "$_.Name" not in command
        for word in ("GeForce", "Radeon", "UHD", "Iris"):
            assert word not in command, word
