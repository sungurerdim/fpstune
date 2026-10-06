"""Message-signaled interrupts: read and write a device's MSI registry value in Python.

``PYTHON_DETECTORS`` / ``PYTHON_ACTIONS`` entries for the GPU and NIC ``msi_mode``
rows. They moved out of PowerShell because the answer to "what does reset restore"
comes from the device's driver INF (``settings/inf_defaults.py``), and because the
device is found through cfgmgr32 and the interface LUID, which start no process.

Reset writes the value the device's own INF installs, or deletes ``MSISupported``
when the INF sets none; it never records what fpstune overwrote (C6). When the INF
cannot be resolved the detector answers ``not_available``, so the row is not
offered at all — an enable with no derivable way back is not a tweak (C1).
"""

from __future__ import annotations

import re
import sys
from typing import Any

from fpstune.settings.applicability import (
    ALREADY_AT_HARDWARE_DEFAULT,
    NOT_AVAILABLE,
    NOT_SUPPORTED,
)
from fpstune.settings.inf_defaults import interrupt_defaults
from fpstune.utils.logger import get_logger

logger = get_logger()

_ENUM = r"SYSTEM\CurrentControlSet\Enum"
_MSI_KEY = r"Device Parameters\Interrupt Management\MessageSignaledInterruptProperties"
# The value an earlier fpstune release stashed the prior MSISupported in. Reset now
# derives the default from the INF, so the stash is dead weight on a machine that
# still carries it, and it is deleted wherever it is found.
RETIRED_STASH = "fpstuneOriginalMSISupported"

_GPU_VENDORS = re.compile(r"VEN_10DE|VEN_1002", re.IGNORECASE)


def msi_key_path(instance_id: str) -> str:
    return rf"{_ENUM}\{instance_id}\{_MSI_KEY}"


def resolve_instance_id(args: dict[str, Any]) -> str | None:
    """The PnP instance id the row addresses, found from its own identity (C5)."""
    if args.get("device") == "gpu":
        from fpstune.utils.winapi.devnode import CLASS_DISPLAY, present_device_ids

        # The vendor id, never position: on a hybrid laptop the integrated GPU may
        # enumerate first and its key never carries MSISupported.
        return next((i for i in present_device_ids(CLASS_DISPLAY) if _GPU_VENDORS.search(i)), None)
    from fpstune.utils.winapi.netluid import adapter_instance_id

    return adapter_instance_id(int(args["ifindex"]))


def _read_dword(path: str, name: str) -> int | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ) as key:
            value, kind = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return None
    return int(value) if kind == winreg.REG_DWORD else None


def _write_dword(path: str, name: str, value: int) -> None:
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)


def _delete_value(path: str, name: str) -> None:
    """Delete one value; a value or key that is already gone is the goal, not an error."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        pass


def msi_mode_status(args: dict[str, Any]) -> str:
    """``enabled`` / ``default``, or the sentinel that says why the row is not offered."""
    if sys.platform != "win32":
        return NOT_AVAILABLE
    instance_id = resolve_instance_id(args)
    if instance_id is None:
        return NOT_SUPPORTED
    defaults = interrupt_defaults(instance_id)
    if defaults is None:
        return NOT_AVAILABLE
    try:
        current = _read_dword(msi_key_path(instance_id), "MSISupported")
    except OSError as exc:
        logger.warning(
            "Cannot read MSISupported of %s (Windows error %s)", instance_id, exc.winerror
        )
        return NOT_AVAILABLE
    # A driver that installs MSISupported=1 is already at the tuned state: "default"
    # and "enabled" are one value there, so nothing is left to apply. A machine
    # drifted off that value still reads "default" and is put back.
    if defaults.msi_supported == 1 and current == 1:
        return ALREADY_AT_HARDWARE_DEFAULT
    return "enabled" if current == 1 else "default"


def _failure(instance_id: str, exc: OSError) -> tuple[bool, str]:
    from fpstune.utils.admin import registry_denied

    if isinstance(exc, PermissionError):
        return False, registry_denied("writing", f"the interrupt key of {instance_id}")
    return False, f"Windows error {exc.winerror} writing the interrupt key of {instance_id}"


def msi_mode_write(args: dict[str, Any]) -> tuple[bool, str | None]:
    """``enabled`` writes MSISupported=1; ``default`` writes what the driver's INF installs."""
    if sys.platform != "win32":
        return False, "Not available on this platform"
    instance_id = resolve_instance_id(args)
    if instance_id is None:
        return False, "The device is not present on this machine"
    path = msi_key_path(instance_id)
    value = args.get("value")
    try:
        if value == "enabled":
            _write_dword(path, "MSISupported", 1)
        elif value == "default":
            defaults = interrupt_defaults(instance_id)
            if defaults is None:
                return False, (
                    "The driver's own default could not be read from its INF, "
                    "so there is nothing to reset to"
                )
            if defaults.msi_supported is None:
                _delete_value(path, "MSISupported")
            else:
                _write_dword(path, "MSISupported", defaults.msi_supported)
            if defaults.message_number_limit is not None:
                _write_dword(path, "MessageNumberLimit", defaults.message_number_limit)
        else:
            return False, f"Unknown interrupt mode {value!r}"
        _delete_value(path, RETIRED_STASH)
    except OSError as exc:
        return _failure(instance_id, exc)
    return True, None


def remove_retired_stash() -> list[str]:
    """Delete the retired stash from every PCI device that still carries it.

    Run once at start-up, so a row that is not applicable on this machine (the
    driver already ships MSI on) cannot leave the value behind. Returns the
    instance ids cleaned.
    """
    if sys.platform != "win32":
        return []
    import winreg

    cleaned: list[str] = []
    try:
        pci = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"{_ENUM}\PCI")
    except OSError as exc:
        logger.warning("Cannot enumerate PCI devices to remove the retired MSI stash: %s", exc)
        return cleaned
    with pci:
        for hardware in _subkeys(pci):
            try:
                with winreg.OpenKey(pci, hardware) as hardware_key:
                    instances = _subkeys(hardware_key)
            except OSError as exc:
                logger.warning("Cannot open PCI\\%s (Windows error %s)", hardware, exc.winerror)
                continue
            for instance in instances:
                instance_id = rf"PCI\{hardware}\{instance}"
                path = msi_key_path(instance_id)
                try:
                    if _has_value(path, RETIRED_STASH):
                        _delete_value(path, RETIRED_STASH)
                        cleaned.append(instance_id)
                        logger.info("Removed the retired MSI stash from %s", instance_id)
                except OSError as exc:
                    logger.warning(
                        "Cannot remove the retired MSI stash from %s (Windows error %s)",
                        instance_id,
                        exc.winerror,
                    )
    return cleaned


def _subkeys(key: Any) -> list[str]:
    import winreg

    names: list[str] = []
    while True:
        try:
            names.append(winreg.EnumKey(key, len(names)))
        except OSError:
            return names


def _has_value(path: str, name: str) -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return False
    return True
