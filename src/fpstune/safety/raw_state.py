"""The exact stored state behind a setting, for an undo that loses nothing.

Undo used to write back the *display* value it recorded, through the setting's
apply map. That is lossy wherever several stored values read as one choice:
``Win32PrioritySeparation`` 2, 24 and 38 all display as "standard", so undoing on
a stock machine (2) wrote 24 — the background-services quantum. A policy value
that was absent came back as an explicit write, a service that was Automatic
(Delayed) came back as Manual.

So alongside the display value, the full scan records the stored state itself:

* ``registry`` — the value the setting writes, with its type, or that it was
  absent. Restoring writes it back verbatim or deletes it.
* ``service`` — the service's ``Start`` and ``DelayedAutostart`` values.
  Restoring sets that start type through sc.exe, which also tells the service
  manager, rather than editing the registry behind its back.

Settings whose state lives elsewhere (powercfg, netsh, scripts) have no raw
capture and keep the display-value undo.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING, Any

from fpstune.utils import process_watch
from fpstune.utils.logger import get_logger

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor

logger = get_logger()

_SERVICES_KEY = r"SYSTEM\CurrentControlSet\Services"

# sc.exe start= names for the Start values a service can hold.
_START_MODES = {0: "boot", 1: "system", 2: "auto", 3: "demand", 4: "disabled"}


def _registry_target(setting: SettingExecutor) -> tuple[str, str, str] | None:
    from fpstune.settings.base import DetectType

    if setting.apply_type != DetectType.REGISTRY:
        return None
    args = setting.apply_args
    path, name = args.get("path"), args.get("name")
    if not path or not name:
        return None
    return str(args.get("hive", "HKLM")), str(path), str(name)


def _service_name(setting: SettingExecutor) -> str | None:
    if setting.apply_command != "service_toggle":
        return None
    name = setting.apply_args.get("service")
    return str(name) if name else None


def _read_value(hive: str, path: str, name: str) -> tuple[Any, int] | None:
    import winreg

    from fpstune.utils.winapi.session import registry_root

    hkey, target = registry_root(hive, path)
    try:
        with winreg.OpenKey(hkey, target, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            value, reg_type = winreg.QueryValueEx(key, name)
            return value, int(reg_type)
    except FileNotFoundError:
        return None


def capture(setting: SettingExecutor) -> dict[str, Any] | None:
    """The stored state behind ``setting`` now, or None when it has no raw form."""
    if sys.platform != "win32":
        return None
    try:
        target = _registry_target(setting)
        if target is not None:
            read = _read_value(*target)
            if read is None:
                return {"kind": "registry", "present": False}
            value, reg_type = read
            if isinstance(value, bytes):
                value = value.hex()
            return {"kind": "registry", "present": True, "value": value, "type": reg_type}

        service = _service_name(setting)
        if service is not None:
            start = _read_value("HKLM", rf"{_SERVICES_KEY}\{service}", "Start")
            if start is None:
                return {"kind": "service", "present": False}
            delayed = _read_value("HKLM", rf"{_SERVICES_KEY}\{service}", "DelayedAutostart")
            return {
                "kind": "service",
                "present": True,
                "start": int(start[0]),
                "delayed": bool(delayed and delayed[0]),
            }
    except OSError as exc:
        logger.debug("raw capture of %s failed: %s", setting.id, exc)
    return None


def restore(setting: SettingExecutor, raw: dict[str, Any]) -> tuple[bool, str | None]:
    """Put the recorded stored state back exactly."""
    if sys.platform != "win32":
        return False, "Not available on this platform"
    kind = raw.get("kind")
    if kind == "registry":
        return _restore_registry(setting, raw)
    if kind == "service":
        return _restore_service(setting, raw)
    return False, f"Unknown recorded state for {setting.id}"


def _restore_registry(setting: SettingExecutor, raw: dict[str, Any]) -> tuple[bool, str | None]:
    import winreg

    from fpstune.utils.winapi.session import registry_root

    target = _registry_target(setting)
    if target is None:
        return False, f"{setting.id} no longer writes a registry value"
    hive, path, name = target
    hkey, key_path = registry_root(hive, path)
    try:
        if not raw.get("present"):
            try:
                with winreg.OpenKey(
                    hkey, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
                ) as key:
                    winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
            return True, None
        value = raw.get("value")
        reg_type = int(raw.get("type", winreg.REG_DWORD))
        if reg_type == winreg.REG_BINARY and isinstance(value, str):
            value = bytes.fromhex(value)
        with winreg.CreateKeyEx(
            hkey, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
        ) as key:
            winreg.SetValueEx(key, name, 0, reg_type, value)
        return True, None
    except PermissionError:
        return False, f"Permission denied writing {hive}\\{path}\\{name} - run as administrator"
    except OSError as exc:
        return False, f"Registry write error: {exc}"


def _restore_service(setting: SettingExecutor, raw: dict[str, Any]) -> tuple[bool, str | None]:
    service = _service_name(setting)
    if service is None:
        return False, f"{setting.id} no longer controls a service"
    if not raw.get("present"):
        # It did not exist when first seen; there is no start type to restore.
        return True, None
    start = int(raw.get("start", -1))
    mode = _START_MODES.get(start)
    if mode is None:
        return False, f"Recorded start type {start} for {service} is not one sc.exe can set"
    if mode == "auto" and raw.get("delayed"):
        mode = "delayed-auto"

    from fpstune.utils.system_tools import system_tool

    sc = system_tool("sc.exe")
    try:
        result = process_watch.run([sc, "config", service, "start=", mode], process_watch.CHANGE)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"Could not run sc.exe for {service}: {exc}"
    if result.returncode != 0:
        return False, f"sc.exe could not set {service} to {mode} (exit code {result.returncode})"
    return True, None
