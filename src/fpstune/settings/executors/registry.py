"""Registry executor for Windows Registry detection and application."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from fpstune.settings.executors import BaseExecutor, map_raw_to_display
from fpstune.utils.winapi.session import registry_root

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor


def _access(base: int) -> int:
    """Add the 64-bit view to a registry access mask.

    Without KEY_WOW64_64KEY a 32-bit build is silently redirected to
    ``Wow6432Node`` for HKLM\\SOFTWARE. Detection and apply would share that
    redirection, so verification would pass while the real key never changed.
    Pinning the view makes the target explicit regardless of build bitness.
    """
    import winreg

    return base | winreg.KEY_WOW64_64KEY


class RegistryExecutor(BaseExecutor):
    """Execute Windows Registry operations.

    Handles reading and writing registry values for various settings.

    detect_args should contain:
        - path: Registry path (e.g., "SYSTEM\\CurrentControlSet\\...")
        - name: Value name
        - hive: "HKLM" or "HKCU" (default: "HKLM")

    apply_args should contain the same, plus:
        - type: REG_DWORD, REG_SZ, etc. (default: REG_DWORD)
    """

    def detect(self, setting: SettingExecutor) -> tuple[Any | None, str | None]:
        """Detect a registry value."""
        from fpstune.utils.debug import debug_log

        if sys.platform != "win32":
            return None, "Not available on this platform"

        path = setting.detect_args.get("path", "")
        name = setting.detect_args.get("name", "")
        hive = setting.detect_args.get("hive", "HKLM")

        debug_log("registry", f"DETECT {setting.id}: {hive}\\{path}\\{name}")

        if not path or not name:
            return None, "Missing 'path' or 'name' in detect_args"

        try:
            import winreg

            hkey, target_path = registry_root(hive, path)

            with winreg.OpenKey(hkey, target_path, 0, _access(winreg.KEY_READ)) as key:
                value, reg_type = winreg.QueryValueEx(key, name)

                debug_log(
                    "registry", f"DETECT RAW {setting.id}: value={repr(value)}, type={reg_type}"
                )

                # Map raw value to display value if mapping exists
                if setting.value_map:
                    mapped = map_raw_to_display(setting.value_map, value)
                    debug_log(
                        "registry", f"DETECT MAP {setting.id}: {repr(value)} -> {repr(mapped)}"
                    )
                    return mapped, None
                return value, None

        except FileNotFoundError:
            debug_log("registry", f"DETECT {setting.id}: Key/value not found")
            # Value doesn't exist - use None mapping if available
            if None in setting.value_map:
                mapped = setting.value_map[None]
                debug_log("registry", f"DETECT MAP {setting.id}: None -> {repr(mapped)}")
                return mapped, None
            return None, None  # Not an error, just not set
        except PermissionError:
            debug_log("registry", f"DETECT {setting.id}: Permission denied")
            return None, f"Permission denied reading {hive}\\{path}\\{name} - run as administrator"
        except Exception as e:
            debug_log("registry", f"DETECT {setting.id}: Error: {e}")
            return None, f"Registry read error: {e}"

    def apply(self, setting: SettingExecutor, value: Any) -> tuple[bool, str | None]:
        """Apply a registry value."""
        from fpstune.utils.debug import debug_log

        if sys.platform != "win32":
            return False, "Not available on this platform"

        path = setting.apply_args.get("path", "")
        name = setting.apply_args.get("name", "")
        hive = setting.apply_args.get("hive", "HKLM")
        reg_type_str = setting.apply_args.get("type", "REG_DWORD")

        if not path or not name:
            return False, "Missing 'path' or 'name' in apply_args"

        # Convert display value to raw value
        raw_value = setting.apply_value_map.get(value, value)

        # Skip sentinel values that indicate the setting is not applicable/installed
        if raw_value in ("not_available", "not_installed"):
            return True, None

        # Coerce value to match registry type
        if reg_type_str == "REG_DWORD" and not isinstance(raw_value, int):
            try:
                raw_value = int(raw_value)
            except (ValueError, TypeError):
                return False, f"Cannot convert {repr(raw_value)} to DWORD integer"
        elif reg_type_str in ("REG_SZ", "REG_EXPAND_SZ") and not isinstance(raw_value, str):
            raw_value = str(raw_value)

        debug_log("registry", f"APPLY {setting.id}: {hive}\\{path}\\{name}")
        debug_log(
            "registry",
            f"APPLY {setting.id}: display={repr(value)} -> raw={repr(raw_value)}, type={reg_type_str}",
        )

        # Handle delete case (raw_value is None)
        if raw_value is None:
            debug_log("registry", f"APPLY {setting.id}: Deleting value")
            return self._delete_value(hive, path, name)

        try:
            import winreg

            hkey, target_path = registry_root(hive, path)

            # Map type string to winreg constant
            reg_type_map = {
                "REG_DWORD": winreg.REG_DWORD,
                "REG_SZ": winreg.REG_SZ,
                "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ,
                "REG_BINARY": winreg.REG_BINARY,
                "REG_QWORD": winreg.REG_QWORD,
            }
            reg_type = reg_type_map.get(reg_type_str, winreg.REG_DWORD)

            # Create/open key with write access
            with winreg.CreateKeyEx(hkey, target_path, 0, _access(winreg.KEY_WRITE)) as key:
                winreg.SetValueEx(key, name, 0, reg_type, raw_value)

            debug_log("registry", f"APPLY {setting.id}: SUCCESS")
            return True, None

        except PermissionError:
            debug_log("registry", f"APPLY {setting.id}: Permission denied")
            return False, f"Permission denied writing {hive}\\{path}\\{name} - run as administrator"
        except Exception as e:
            debug_log("registry", f"APPLY {setting.id}: Error: {e}")
            return False, f"Registry write error: {e}"

    def _delete_value(self, hive: str, path: str, name: str) -> tuple[bool, str | None]:
        """Delete a registry value."""
        try:
            import winreg

            hkey, target_path = registry_root(hive, path)

            with winreg.OpenKey(hkey, target_path, 0, _access(winreg.KEY_WRITE)) as key:
                winreg.DeleteValue(key, name)

            return True, None

        except FileNotFoundError:
            # Value doesn't exist - that's OK
            return True, None
        except PermissionError:
            return False, "Permission denied - run as administrator"
        except Exception as e:
            return False, str(e)
