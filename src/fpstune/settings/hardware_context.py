"""What this machine is, in the terms applicability rules are written in.

Every path that reads or writes a setting needs the same answer to "what
hardware is this?" — the API when it serves the UI, the CLI when it reports
status, anything that comes later. The answer used to live inside the settings
*route*, which meant the only way to ask it from anywhere else was to import a
private function out of an HTTP module. Two callers, one of them reaching
through a layer it should not know exists, is how the second answer starts
drifting from the first.

So it lives here, next to `HardwareContext` itself and next to the applicability
rules that consume it. Nothing in this module knows what a request is.

The detection underneath is already cached — `get_gpu_info` has a module cache,
`hardware_manager` caches OS and CPU indefinitely and monitors for five minutes
— so calling this per request stays cheap and calling it once from a CLI stays
correct.
"""

from __future__ import annotations

import ctypes
import logging
import sys

from fpstune.settings.applicability import HardwareContext
from fpstune.settings.virtualization import virtualization_features
from fpstune.utils.admin import is_admin
from fpstune.utils.detect import get_gpu_info
from fpstune.utils.hardware_manager import hardware_manager

logger = logging.getLogger(__name__)

# Presence of a virtualization stack changes what is safe to recommend, so it is
# part of the machine's description rather than a check buried in one setting.
# The probing lives in `settings.virtualization`, which discovers each consumer
# rather than asserting where it lives — this used to be one hardcoded
# `C:\Program Files\Docker\...` path and missed a per-user Docker install
# entirely, so the machine running Docker was told to disable Hyper-V (C9).

# BatteryFlag values from GetSystemPowerStatus that mean "no battery to speak of".
_NO_BATTERY = 128
_BATTERY_UNKNOWN = 255


class _SystemPowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def is_portable_flag(battery_flag: int) -> bool:
    """Whether ``SYSTEM_POWER_STATUS.BatteryFlag`` describes a battery-powered machine.

    Split out from the probe so the interpretation can be tested without a
    machine of each kind. Both excluded values matter: 128 is "no system
    battery" and 255 is "the API does not know", and an earlier draft that
    treated only 128 as a desktop would have shown a laptop-only frame-cap
    warning on every machine whose firmware declined to answer.
    """
    return battery_flag not in (_NO_BATTERY, _BATTERY_UNKNOWN)


def has_battery() -> bool:
    """Whether this machine runs off a battery — i.e. whether it is portable.

    Read through ``GetSystemPowerStatus`` rather than
    ``Win32_ComputerSystem.PCSystemType``, which would be the more precise
    answer and costs a PowerShell process. This context is built per request
    (C7), so a subprocess here would be a process per request to learn something
    that cannot change while the machine is running.

    A desktop on a UPS can report a battery, and this will call it portable.
    That is tolerated rather than worked around, because nothing is *recommended*
    off this fact alone: the settings gated on it also require an NVIDIA GPU and
    the NVIDIA App's own support file, and on a desktop that file answers with an
    absence rather than a state.
    """
    if sys.platform != "win32":
        return False
    try:
        status = _SystemPowerStatus()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return False
        return is_portable_flag(status.BatteryFlag)
    except Exception as exc:  # pragma: no cover - a failed probe is not a battery
        logger.debug("Battery probe failed; treating the machine as desktop: %s", exc)
        return False


def build_hardware_context() -> HardwareContext:
    """Describe this machine for applicability checks.

    Never raises on a detection that fails: a machine whose monitors cannot be
    enumerated still has a CPU, a GPU and a Windows build, and answering "we
    could not tell" for the whole context because one probe failed would hide
    every setting rather than the one that depended on it.
    """
    gpu_info = get_gpu_info()
    os_info = hardware_manager.detect_os()
    cpu_info = hardware_manager.detect_cpu()

    gpu_vendor = gpu_info.vendor.value if gpu_info else None

    # Read off the CPU's own name string rather than a separate probe: it is the
    # one field every vendor fills in, on every Windows version.
    cpu_vendor: str | None = None
    if cpu_info:
        cpu_name_lower = cpu_info.name.lower()
        if "amd" in cpu_name_lower:
            cpu_vendor = "amd"
        elif "intel" in cpu_name_lower:
            cpu_vendor = "intel"

    gpu_vendors = [gpu_vendor] if gpu_vendor and gpu_vendor != "unknown" else []

    features, feature_labels = virtualization_features()
    # A class of machine the product had no notion of, which matters because two
    # NVIDIA features exist purely to cap frame rate on one.
    if has_battery():
        features.add("mobile")

    # None means the panels could not be probed, or none declared either way —
    # unknown, which is a different fact from "no VRR panel": a failed monitor
    # probe must not silently disable every VRR-dependent setting as if the
    # hardware itself had answered no.
    has_vrr: bool | None = None
    try:
        monitors = hardware_manager.detect_monitors()
        active = [m for m in monitors if m.is_active]
        if any(m.supports_vrr for m in active):
            has_vrr = True
        elif active and all(m.supports_vrr is False for m in active):
            has_vrr = False
    except Exception as exc:
        logger.warning("Monitor probe failed; VRR support is unknown: %s", exc)

    return HardwareContext(
        cpu_vendor=cpu_vendor,
        gpu_vendor=gpu_vendor if gpu_vendor != "unknown" else None,
        gpu_vendors=gpu_vendors,
        gpu_name=gpu_info.name if gpu_info else None,
        windows_build=int(os_info.build) if os_info and os_info.build.isdigit() else 0,
        windows_version=os_info.display_version if os_info else "",
        is_windows_11=os_info.is_windows_11 if os_info else False,
        is_admin=is_admin(),
        has_vrr_monitor=has_vrr,
        features=features,
        feature_labels=feature_labels,
    )
