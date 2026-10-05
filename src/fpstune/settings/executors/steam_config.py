"""Read and write one key in Steam's config.vdf / localconfig.vdf, in-process.

These two files are exactly what Steam account stealers go after, and the
PowerShell writer this replaces looked like one: an unsigned executable starting
a hidden, elevated PowerShell that read `config.vdf` byte by byte and wrote it
back. Windows Defender's machine-learning heuristic flagged the process tree as
`Trojan:Win32/Bearfoos.A!ml` while the Steam tweaks were being applied
(2026-10-05). The Battle.net writer took the same way out earlier
(`bnet_config.py`): no script, no child process — the file is read and one value
replaced here, the byte-order mark kept as found, and the result renamed into
place so a failed write leaves Steam's own file intact.

The edit itself is the one the script made: the first `"key" "value"` pair is
replaced; a missing key is added under the file's own block (`"Steam"` in
config.vdf, `"system"` in localconfig.vdf).
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

from fpstune.settings.applicability import NOT_INSTALLED

#: Which file a setting lives in, and the block a missing key is added under.
_FILES = {"config": ("Steam", "config.vdf"), "localconfig": ("system", "localconfig.vdf")}

# Every Steam setting shares two files and bulk apply runs settings in
# parallel, so the read-modify-write holds this for its whole length.
_lock = threading.Lock()


def steam_root() -> Path | None:
    """Steam's install folder from the registry, or None."""
    if sys.platform != "win32":
        return None
    import winreg

    for view in (r"SOFTWARE\Valve\Steam", r"SOFTWARE\WOW6432Node\Valve\Steam"):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, view) as key:
                value, _ = winreg.QueryValueEx(key, "InstallPath")
        except OSError:
            continue
        if value:
            return Path(str(value))
    return None


def vdf_path(scope: str, root: Path | None = None) -> Path | None:
    """The file `scope` names: config.vdf, or the newest user's localconfig.vdf."""
    root = root if root is not None else steam_root()
    if root is None:
        return None
    if scope == "config":
        path = root / "config" / "config.vdf"
        return path if path.is_file() else None
    candidates = list(root.glob("userdata/*/config/localconfig.vdf"))
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _pair(key: str) -> re.Pattern[str]:
    return re.compile(r'("' + re.escape(key) + r'"\s+)"([^"]*)"')


def read_raw(scope: str, key: str, root: Path | None = None) -> str | None:
    """The key's raw value, None when absent; raises FileNotFoundError when no file."""
    path = vdf_path(scope, root)
    if path is None:
        raise FileNotFoundError(scope)
    match = _pair(key).search(path.read_bytes().decode("utf-8-sig", errors="replace"))
    return match.group(2) if match else None


def write_raw(scope: str, key: str, value: str, root: Path | None = None) -> None:
    """Set `key` to `value` in the file, keeping everything else byte for byte."""
    block, _ = _FILES[scope]
    if any(ch in value for ch in '"\r\n'):
        # A quote or a line break would end the token and write VDF of our own.
        raise ValueError(f"refusing a value that would break the file: {value!r}")
    with _lock:
        path = vdf_path(scope, root)
        if path is None:
            raise FileNotFoundError(scope)
        data = path.read_bytes()
        bom = data.startswith(b"\xef\xbb\xbf")
        text = data[3:].decode("utf-8") if bom else data.decode("utf-8")
        pattern = _pair(key)
        if pattern.search(text):
            text = pattern.sub(lambda m: f'{m.group(1)}"{value}"', text, count=1)
        else:
            anchor = re.compile(r'("' + block + r'"\s*\n\s*\{)')
            if not anchor.search(text):
                raise ValueError(f'no "{block}" block to add {key} under')
            text = anchor.sub(lambda m: f'{m.group(1)}\n\t\t\t"{key}"\t\t"{value}"', text, count=1)
        payload = (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".fpstune-", suffix=".vdf")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            os.replace(temp, path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise


def steam_vdf_read(args: dict[str, Any]) -> str:
    """PYTHON_DETECTORS entry: the display value from the setting's own map."""
    try:
        raw = read_raw(str(args["scope"]), str(args["key"]))
    except FileNotFoundError:
        return NOT_INSTALLED
    if raw is None:
        return str(args["absent"])
    mapping: dict[str, str] = args.get("map", {})
    return mapping.get(raw, str(args.get("otherwise", args["absent"])))


def steam_vdf_write(args: dict[str, Any]) -> tuple[bool, str | None]:
    """PYTHON_ACTIONS entry: write the raw value `apply_value_map` resolved."""
    if sys.platform != "win32":
        return False, "Not available on this platform"
    try:
        write_raw(str(args["scope"]), str(args["key"]), str(args["value"]))
    except FileNotFoundError:
        return False, "Steam is not installed for this user"
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        return False, f"Steam's config could not be written: {exc}"
    return True, None
