"""System detection utilities for OS and GPU information."""

from __future__ import annotations

import contextlib
import platform
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

# GPU cache with TTL
_gpu_cache: GpuInfo | None = None
_gpu_cache_time: float = 0
_gpu_cache_lock = threading.Lock()
_gpu_detecting = False
_GPU_CACHE_TTL = float("inf")  # Never expires - detect once per session

# Signalled when no background GPU detection is in flight. Starts set because
# nothing is running yet, so a waiter that arrives before any detection returns
# immediately instead of blocking for the full timeout.
_gpu_detection_done = threading.Event()
_gpu_detection_done.set()

# How long a caller will wait for an in-flight background detection before
# giving up and answering with whatever is cached.
GPU_DETECTION_WAIT_TIMEOUT = 15.0

# OS info cache (edition + display version in single call)
_os_info_cache: dict[str, str] | None = None
_os_info_lock = threading.Lock()

# CPU caches — session-stable data, so one subprocess per process lifetime (C7).
# A failed detailed detection is not cached: None means "retry next call", the
# same contract the GPU cache uses.
_cpu_info_cache: dict[str, str] | None = None
_cpu_info_lock = threading.Lock()
_cpu_detailed_cache: CpuDetailedInfo | None = None
_cpu_detailed_lock = threading.Lock()


class GpuVendor(StrEnum):
    """GPU vendor types."""

    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    UNKNOWN = "unknown"


@dataclass
class OsInfo:
    """Operating system information."""

    platform: str  # win32, linux, darwin
    version: str  # e.g., "10.0.19045"
    build: str  # e.g., "19045"
    edition: str  # e.g., "Windows 11 Pro"
    display_version: str  # e.g., "24H2", "23H2"
    is_windows_10: bool
    is_windows_11: bool

    @property
    def is_supported(self) -> bool:
        """Check if the OS is supported (Windows 10 1903+ or Windows 11)."""
        if not (self.is_windows_10 or self.is_windows_11):
            return False

        try:
            build_num = int(self.build)
            # Windows 10 1903 = build 18362
            # Windows 11 21H2 = build 22000
            return build_num >= 18362
        except ValueError:
            return False


@dataclass
class GpuInfo:
    """GPU information."""

    vendor: GpuVendor
    name: str
    driver_version: str
    vram_mb: int
    pnp_device_id: str = ""  # PCI VEN+DEV portion (e.g. PCI\VEN_10DE&DEV_2204) — hardware-stable ID


@dataclass
class CpuDetailedInfo:
    """Detailed CPU information."""

    name: str
    physical_cores: int
    logical_cores: int
    base_clock_mhz: int
    max_clock_mhz: int
    architecture: str
    cache_l3_mb: int


@dataclass
class MonitorInfo:
    """Monitor/display information."""

    name: str  # Device name (e.g., "\\.\DISPLAY1")
    width: int
    height: int
    refresh_rate_hz: int
    is_primary: bool
    # Monitor brand/model from EDID (e.g., "ASUS VG27AQ1A", "Dell U2722D")
    friendly_name: str = ""
    # Native values from preferred mode (what Windows read from EDID)
    native_width: int = 0
    native_height: int = 0
    native_refresh_rate_hz: int = 0
    # Maximum values from EnumDisplaySettings (may include OC modes)
    max_refresh_rate_hz: int = 0
    # VRR (G-Sync/FreeSync) support
    supports_vrr: bool = False
    # Is display active (attached to desktop) or disconnected
    is_active: bool = True
    # Hardware ID for matching (e.g., "DEL4265", "SAM0F75")
    hardware_id: str = ""

    @property
    def is_resolution_optimal(self) -> bool:
        """Check if current resolution matches native.

        Returns False if native resolution is unknown (0).
        """
        if self.native_width == 0 or self.native_height == 0:
            return False  # Unknown - don't claim optimal
        return self.width == self.native_width and self.height == self.native_height

    @property
    def is_refresh_optimal(self) -> bool:
        """Check if current refresh rate matches native.

        Returns False if native refresh rate is unknown (0).
        Falls back to max refresh if native is unknown.
        """
        target = self.native_refresh_rate_hz or self.max_refresh_rate_hz
        if target == 0:
            return False  # Unknown - don't claim optimal
        return self.refresh_rate_hz >= target

    @property
    def is_resolution_known(self) -> bool:
        """Check if native resolution was detected."""
        return self.native_width > 0 and self.native_height > 0

    @property
    def is_refresh_known(self) -> bool:
        """Check if native or max refresh rate was detected."""
        return self.native_refresh_rate_hz > 0 or self.max_refresh_rate_hz > 0


def get_os_info() -> OsInfo:
    """Detect operating system information.

    Returns:
        OsInfo with detected system information.
    """
    plat = sys.platform

    if plat != "win32":
        return OsInfo(
            platform=plat,
            version=platform.release(),
            build="0",
            edition=platform.system(),
            display_version="",
            is_windows_10=False,
            is_windows_11=False,
        )

    try:
        version = platform.version()  # e.g., "10.0.22621"
        parts = version.split(".")
        build = parts[2] if len(parts) > 2 else "0"
        build_num = int(build)

        # Windows 11 starts at build 22000
        is_windows_11 = build_num >= 22000
        is_windows_10 = not is_windows_11 and build_num >= 10240

        # Get edition via WMI
        edition = _get_windows_edition()

        # Get display version (e.g., "24H2", "23H2")
        display_version = _get_windows_display_version()

        return OsInfo(
            platform=plat,
            version=version,
            build=build,
            edition=edition,
            display_version=display_version,
            is_windows_10=is_windows_10,
            is_windows_11=is_windows_11,
        )
    except (ValueError, TypeError):
        return OsInfo(
            platform=plat,
            version=platform.version(),
            build="0",
            edition="Windows",
            display_version="",
            is_windows_10=False,
            is_windows_11=False,
        )


def _get_os_info_batch() -> dict[str, str]:
    """Get Windows edition and display version in a single PowerShell call.

    Returns:
        Dict with 'edition' and 'display_version' keys.
    """
    global _os_info_cache

    import logging

    logger = logging.getLogger("fpstune.detect")

    # The lock spans the check, the subprocess and the store. Releasing it
    # around the subprocess would let every concurrent caller see an empty
    # cache and spawn its own PowerShell — the deduplication this cache exists
    # for only holds if the whole check-then-set is atomic.
    with _os_info_lock:
        if _os_info_cache is not None:
            return _os_info_cache

        result_dict = {"edition": "Windows", "display_version": ""}

        try:
            # Batch query: get both edition and display version in single call
            ps_script = """
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$os = Get-CimInstance -ClassName Win32_OperatingSystem
$reg = Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion' -ErrorAction SilentlyContinue
"Edition=$($os.Caption)"
"DisplayVersion=$($reg.DisplayVersion)"
"""
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW  # Windows-only
                if sys.platform == "win32"
                else 0,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("Edition="):
                        result_dict["edition"] = line.split("=", 1)[1].strip() or "Windows"
                    elif line.startswith("DisplayVersion="):
                        result_dict["display_version"] = line.split("=", 1)[1].strip()

        except (subprocess.SubprocessError, OSError) as e:
            logger.debug("Batch OS info query failed: %s", e)

        _os_info_cache = result_dict
        return result_dict


def _get_windows_edition() -> str:
    """Get Windows edition name (uses cached batch query)."""
    return _get_os_info_batch()["edition"]


def _get_windows_display_version() -> str:
    """Get Windows display version (uses cached batch query)."""
    return _get_os_info_batch()["display_version"]


def get_gpu_vendor() -> GpuVendor:
    """Detect the primary GPU vendor.

    Returns:
        GpuVendor enum value.
    """
    gpu_info = get_gpu_info()
    return gpu_info.vendor if gpu_info else GpuVendor.UNKNOWN


def get_gpu_info(use_cache: bool = True) -> GpuInfo | None:
    """Detect GPU information with caching.

    Args:
        use_cache: If True, return cached result if available.

    Returns:
        GpuInfo with detected GPU information, or None if detection fails.
    """
    global _gpu_cache, _gpu_cache_time

    with _gpu_cache_lock:
        # Return cached result if valid
        if use_cache and _gpu_cache is not None and time.time() - _gpu_cache_time < _GPU_CACHE_TTL:
            return _gpu_cache
        detecting = _gpu_detecting

    # Wait for background detection if running (avoid duplicate detection)
    if detecting:
        wait_for_gpu_detection()
        with _gpu_cache_lock:
            if _gpu_cache is not None:
                return _gpu_cache

    result = _detect_gpu_sync()

    # Update cache
    with _gpu_cache_lock:
        _gpu_cache = result
        _gpu_cache_time = time.time()

    return result


def get_gpu_info_cached() -> tuple[GpuInfo | None, bool]:
    """Get cached GPU info without blocking.

    Returns:
        Tuple of (GpuInfo or None, is_detecting).
        If cache is empty and detection not running, starts background detection.
    """
    with _gpu_cache_lock:
        # Return cache if available
        if _gpu_cache is not None:
            return _gpu_cache, False
        detecting = _gpu_detecting

    # Outside the lock: start_gpu_detection_async() takes the same
    # non-reentrant lock to claim the detection.
    if not detecting:
        start_gpu_detection_async()

    return None, is_gpu_detecting()


def start_gpu_detection_async(callback: Callable[[GpuInfo | None], None] | None = None) -> None:
    """Start GPU detection in background thread.

    Args:
        callback: Optional callback when detection completes.
    """
    global _gpu_detecting

    # Claiming the detection happens here, in the calling thread, not inside
    # the spawned one. Setting the flag inside the thread left a window in
    # which the lifespan hook and the first request both read False and both
    # spawned a full hardware probe.
    with _gpu_cache_lock:
        if _gpu_detecting:
            return
        _gpu_detecting = True
        _gpu_detection_done.clear()

    def detect_thread() -> None:
        global _gpu_detecting, _gpu_cache, _gpu_cache_time
        try:
            result = _detect_gpu_sync()
            with _gpu_cache_lock:
                _gpu_cache = result
                _gpu_cache_time = time.time()
            if callback:
                callback(result)
        finally:
            with _gpu_cache_lock:
                _gpu_detecting = False
            _gpu_detection_done.set()

    thread = threading.Thread(target=detect_thread, daemon=True)
    thread.start()


def is_gpu_detecting() -> bool:
    """Check if GPU detection is in progress."""
    with _gpu_cache_lock:
        return _gpu_detecting


def wait_for_gpu_detection(timeout: float = GPU_DETECTION_WAIT_TIMEOUT) -> bool:
    """Block until the background GPU detection finishes.

    Args:
        timeout: Seconds to wait before giving up.

    Returns:
        True if no detection is in flight by the time this returns.
    """
    return _gpu_detection_done.wait(timeout)


def _detect_gpu_sync() -> GpuInfo | None:
    """Synchronous GPU detection (internal).

    Returns:
        GpuInfo with detected GPU information, or None if detection fails.
    """
    import logging

    logger = logging.getLogger("fpstune.detect")

    if sys.platform != "win32":
        logger.warning("GPU detection: Not on Windows platform")
        return None

    name = ""
    driver = ""
    vram = 0
    vendor = GpuVendor.UNKNOWN
    pnp_raw = ""

    # Try nvidia-smi first (most reliable for NVIDIA GPUs).
    # Pass argv list (no shell) so PATH lookup happens through CreateProcess
    # without exposing a shell=True interpolation surface.
    try:
        logger.info("GPU detection: Trying nvidia-smi...")
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode == 0 and result.stdout.strip():
            # Parse: "NVIDIA GeForce RTX 4070 Laptop GPU, 591.59, 8192"
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 3:
                name = parts[0].strip()
                driver = parts[1].strip()
                try:
                    vram = int(float(parts[2].strip()))  # Already in MB
                except (ValueError, TypeError):
                    vram = 0
                vendor = GpuVendor.NVIDIA
                logger.info(
                    f"GPU detected via nvidia-smi: {name} (Driver: {driver}, VRAM: {vram}MB)"
                )
        else:
            logger.debug(f"nvidia-smi returned: {result.returncode}, stderr: {result.stderr}")

    except Exception as e:
        logger.debug(f"nvidia-smi failed: {e}")

    # Try PowerShell Get-CimInstance if nvidia-smi didn't work
    if not name:
        try:
            logger.info("GPU detection: Using PowerShell Get-CimInstance...")
            # Sort by AdapterRAM descending to get dedicated GPU first (more VRAM than integrated)
            ps_script = (
                "Get-CimInstance -ClassName Win32_VideoController | "
                "Sort-Object -Property AdapterRAM -Descending | "
                "Select-Object -First 1 Name, DriverVersion, AdapterRAM, PNPDeviceID | "
                'ForEach-Object { "Name=$($_.Name)"; "Driver=$($_.DriverVersion)"; "VRAM=$($_.AdapterRAM)"; "PNP=$($_.PNPDeviceID)" }'
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )

            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("Name="):
                    name = line.split("=", 1)[1].strip()
                elif line.startswith("Driver="):
                    driver = line.split("=", 1)[1].strip()
                elif line.startswith("VRAM="):
                    try:
                        vram_str = line.split("=", 1)[1].strip()
                        if vram_str and vram_str != "":
                            vram = int(vram_str) // (1024 * 1024)
                    except (ValueError, TypeError):
                        vram = 0
                elif line.startswith("PNP="):
                    pnp_raw = line.split("=", 1)[1].strip()

        except Exception as e:
            logger.warning(f"PowerShell GPU detection failed: {e}")

    if not name:
        logger.warning("GPU detection: No GPU found")
        return None

    # Determine vendor from name if not already set
    if vendor == GpuVendor.UNKNOWN:
        name_lower = name.lower()
        if "nvidia" in name_lower or "geforce" in name_lower or "quadro" in name_lower:
            vendor = GpuVendor.NVIDIA
        elif "amd" in name_lower or "radeon" in name_lower or "rx " in name_lower:
            vendor = GpuVendor.AMD
        elif "intel" in name_lower:
            vendor = GpuVendor.INTEL

    # Extract stable VEN+DEV portion from PNPDeviceID (e.g. "PCI\VEN_10DE&DEV_2204&...")
    pnp_stable = ""
    if pnp_raw:
        import re

        match = re.match(r"(PCI\\VEN_[0-9A-Fa-f]+&DEV_[0-9A-Fa-f]+)", pnp_raw)
        if match:
            pnp_stable = match.group(1).upper()

    logger.info(f"GPU detected: {name} ({vendor.value})")

    return GpuInfo(
        vendor=vendor,
        name=name,
        driver_version=driver,
        vram_mb=vram,
        pnp_device_id=pnp_stable,
    )


def get_cpu_info() -> dict[str, str]:
    """Get basic CPU information (cached — one subprocess per session).

    Returns:
        Dictionary with cpu_name and core_count.
    """
    global _cpu_info_cache

    import os

    # Held across the subprocess, same as the OS and detailed-CPU caches: a
    # cache whose check and store are separately locked still spawns one
    # PowerShell per concurrent caller.
    with _cpu_info_lock:
        if _cpu_info_cache is not None:
            return _cpu_info_cache

        cpu_name = platform.processor() or "Unknown"
        core_count = str(os.cpu_count() or 0)

        if sys.platform == "win32":
            # Try PowerShell first (Windows 11 compatible)
            try:
                result = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                        "(Get-CimInstance -ClassName Win32_Processor).Name",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    encoding="utf-8",
                    errors="replace",
                )
                if result.returncode == 0 and result.stdout.strip():
                    cpu_name = result.stdout.strip()
            except (subprocess.SubprocessError, OSError):
                # Fallback to WMIC for older Windows
                try:
                    result = subprocess.run(
                        ["wmic", "cpu", "get", "Name", "/value"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        encoding="utf-8",
                        errors="replace",
                    )
                    for line in result.stdout.splitlines():
                        if line.startswith("Name="):
                            cpu_name = line.split("=", 1)[1].strip()
                            break
                except (subprocess.SubprocessError, OSError):
                    pass

        # The PowerShell path may have fallen back to platform.processor(); that
        # fallback is as session-stable as the real name, so it is cached too.
        _cpu_info_cache = {
            "cpu_name": cpu_name,
            "core_count": core_count,
        }
        return _cpu_info_cache


def get_ram_info() -> dict[str, int]:
    """Get RAM information in MB.

    Returns:
        Dictionary with total_mb and available_mb.
    """
    import logging

    logger = logging.getLogger("fpstune.detect")
    if sys.platform == "win32":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))

            return {
                "total_mb": stat.ullTotalPhys // (1024 * 1024),
                "available_mb": stat.ullAvailPhys // (1024 * 1024),
            }
        except (OSError, AttributeError) as e:
            logger.debug("Failed to get RAM info: %s", e)

    return {"total_mb": 0, "available_mb": 0}


def get_cpu_detailed_info() -> CpuDetailedInfo | None:
    """Get detailed CPU information (cached — one PowerShell call per session).

    Returns:
        CpuDetailedInfo with cores, clocks, cache info, or None if detection fails.
    """
    global _cpu_detailed_cache

    import logging
    import os

    logger = logging.getLogger("fpstune.detect")

    # Held across the subprocess so concurrent callers share one PowerShell.
    # A failed detection still leaves the cache empty, so the next caller
    # retries — that contract is unchanged by the wider lock.
    with _cpu_detailed_lock:
        if _cpu_detailed_cache is not None:
            return _cpu_detailed_cache

        if sys.platform != "win32":
            return None

        name = platform.processor() or "Unknown"
        physical_cores = 0
        logical_cores = os.cpu_count() or 0
        base_clock_mhz = 0
        max_clock_mhz = 0
        architecture = platform.machine() or ""
        cache_l3_mb = 0

        try:
            # Get ALL CPU info in single PowerShell call (optimized)
            ps_script = """
$cpu = Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1
"Name=$($cpu.Name)"
"PhysicalCores=$($cpu.NumberOfCores)"
"LogicalCores=$($cpu.NumberOfLogicalProcessors)"
"BaseClock=$($cpu.MaxClockSpeed)"
"MaxClock=$($cpu.MaxClockSpeed)"
"L3Cache=$($cpu.L3CacheSize)"
"""
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )

            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("Name="):
                    name = line.split("=", 1)[1].strip()
                elif line.startswith("PhysicalCores="):
                    with contextlib.suppress(ValueError, TypeError):
                        physical_cores = int(line.split("=", 1)[1].strip())
                elif line.startswith("LogicalCores="):
                    with contextlib.suppress(ValueError, TypeError):
                        logical_cores = int(line.split("=", 1)[1].strip())
                elif line.startswith("BaseClock="):
                    with contextlib.suppress(ValueError, TypeError):
                        base_clock_mhz = int(line.split("=", 1)[1].strip())
                elif line.startswith("MaxClock="):
                    with contextlib.suppress(ValueError, TypeError):
                        max_clock_mhz = int(line.split("=", 1)[1].strip())
                elif line.startswith("L3Cache="):
                    try:
                        # L3 cache is in KB, convert to MB
                        cache_kb = int(line.split("=", 1)[1].strip())
                        cache_l3_mb = cache_kb // 1024
                    except (ValueError, TypeError):
                        pass

        except Exception as e:
            logger.debug("Failed to get detailed CPU info: %s", e)
            return None

        _cpu_detailed_cache = CpuDetailedInfo(
            name=name,
            physical_cores=physical_cores,
            logical_cores=logical_cores,
            base_clock_mhz=base_clock_mhz,
            max_clock_mhz=max_clock_mhz or base_clock_mhz,
            architecture=architecture,
            cache_l3_mb=cache_l3_mb,
        )
        return _cpu_detailed_cache


# The EnumDisplayDevices loop lives inside the C# class. Calling the API from
# PowerShell with [ref] is the proven failure: the identical call returned every
# adapter from a loop inside C# and returned False with an empty name when the
# method was invoked from PowerShell with [ref] (declared cb=840, ret=False) —
# same session, same API, only the binder differs. So the struct never crosses
# that boundary. Each record is "deviceName|stateFlags|monitorInterfacePath";
# StateFlags rides along because bit 0 (ATTACHED_TO_DESKTOP) is the attachment
# answer WMI cannot give (WMI reports Active=True for a panel not on the desktop).
_DISPLAY_DEVICES_CSHARP = r"""
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class DisplayDevices {
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern bool EnumDisplayDevices(
        string lpDevice, uint iDevNum,
        ref DISPLAY_DEVICE lpDisplayDevice, uint dwFlags);
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct DISPLAY_DEVICE {
        public int cb;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string DeviceName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string DeviceString;
        public int StateFlags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string DeviceID;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string DeviceKey;
    }
    private const uint EDD_GET_DEVICE_INTERFACE_NAME = 1;
    public static string[] EnumerateAdapters() {
        var results = new System.Collections.Generic.List<string>();
        for (uint i = 0; ; i++) {
            DISPLAY_DEVICE ad = new DISPLAY_DEVICE();
            ad.cb = Marshal.SizeOf(typeof(DISPLAY_DEVICE));
            if (!EnumDisplayDevices(null, i, ref ad, 0)) { break; }
            DISPLAY_DEVICE mon = new DISPLAY_DEVICE();
            mon.cb = Marshal.SizeOf(typeof(DISPLAY_DEVICE));
            string monId = "";
            if (EnumDisplayDevices(ad.DeviceName, 0, ref mon, EDD_GET_DEVICE_INTERFACE_NAME)) {
                monId = mon.DeviceID;
            }
            results.Add(ad.DeviceName.TrimEnd('\0', ' ') + "|" + ad.StateFlags + "|" + monId);
        }
        return results.ToArray();
    }
}
'@
"""

# Correlation is a pure function so the contract tests can run the shipped text
# against a described host. The join is by UID — the interface path's UID
# segment is the same number WmiMonitorID.InstanceName carries — never by
# position. There is deliberately no order-based fallback: zipping two
# independently sorted lists handed a panel its neighbour's mode table the
# moment a laptop's internal panel sorted first, and a wrong map is worse than
# an empty one — empty means "could not correlate", which is visible and
# reportable, where a plausible wrong map reports success.
_CORRELATE_MONITORS_PS = r"""
function Build-DeviceHwIdMap {
    param([string[]]$adapterRecords, [hashtable]$uidToHwId)
    $map = @{}
    foreach ($rec in $adapterRecords) {
        $f = $rec -split '\|', 3
        if ($f.Count -ge 3 -and $f[2] -match 'UID(\d+)' -and $uidToHwId.ContainsKey($Matches[1])) {
            $map[$f[0]] = $uidToHwId[$Matches[1]]
        }
    }
    return $map
}
"""


def get_monitors() -> list[MonitorInfo]:
    """Get connected monitors using WMI for actual monitor capabilities.

    Uses WmiMonitorListedSupportedSourceModes for real monitor-supported modes
    (not GPU capabilities). This gives accurate native resolution per monitor.

    Returns:
        List of MonitorInfo for each connected display.
    """
    import logging

    from fpstune.utils.debug import debug_log

    logger = logging.getLogger("fpstune.detect")
    debug_log("hardware", "get_monitors() called")

    if sys.platform != "win32":
        debug_log("hardware", "Not on Windows, returning empty list")
        return []

    monitors: list[MonitorInfo] = []

    # Monitor detection: AllScreens enumerates the desktop, EnumDisplaySettings
    # reads modes for the device names AllScreens provides, and the C# constant
    # above correlates each \\.\DISPLAYn to its monitor hardware id by UID.
    ps_script = (
        r"""
$ErrorActionPreference = 'SilentlyContinue'

# Load Windows Forms for reliable screen enumeration
Add-Type -AssemblyName System.Windows.Forms 2>$null

# Add EnumDisplaySettings via P/Invoke for refresh rate and mode enumeration
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class DisplaySettings {
    [DllImport("user32.dll", CharSet = CharSet.Ansi)]
    public static extern bool EnumDisplaySettings(string lpszDeviceName, int iModeNum, ref DEVMODE lpDevMode);
    public const int ENUM_CURRENT_SETTINGS = -1;
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct DEVMODE {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmDeviceName;
        public short dmSpecVersion;
        public short dmDriverVersion;
        public short dmSize;
        public short dmDriverExtra;
        public int dmFields;
        public int dmPositionX;
        public int dmPositionY;
        public int dmDisplayOrientation;
        public int dmDisplayFixedOutput;
        public short dmColor;
        public short dmDuplex;
        public short dmYResolution;
        public short dmTTOption;
        public short dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmFormName;
        public short dmLogPixels;
        public int dmBitsPerPel;
        public int dmPelsWidth;
        public int dmPelsHeight;
        public int dmDisplayFlags;
        public int dmDisplayFrequency;
        public int dmICMMethod;
        public int dmICMIntent;
        public int dmMediaType;
        public int dmDitherType;
        public int dmReserved1;
        public int dmReserved2;
        public int dmPanningWidth;
        public int dmPanningHeight;
    }
}
'@
"""
        + _DISPLAY_DEVICES_CSHARP
        + r"""
# Build WMI lookup tables (keyed by hardware ID like "DEL4265", "SAM0F75")
$wmiNames = @{}
$wmiNative = @{}
$uidToHwId = @{}   # UID number string → hwId (e.g. "12345" → "DEL4265")
Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID 2>$null | ForEach-Object {
    $parts = $_.InstanceName -split '\\'
    if ($parts.Count -ge 2) {
        $hwId = $parts[1]
        $chars = $_.UserFriendlyName | Where-Object { $_ -gt 0 }
        $name = if ($chars) { -join [char[]]$chars } else { "" }
        $wmiNames[$hwId] = $name
        if ($_.InstanceName -match 'UID(\d+)') { $uidToHwId[$Matches[1]] = $hwId }
    }
}

Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorListedSupportedSourceModes 2>$null | ForEach-Object {
    $parts = $_.InstanceName -split '\\'
    if ($parts.Count -ge 2) {
        $hwId = $parts[1]
        $nW = 0; $nH = 0; $maxPx = 0
        foreach ($mode in $_.MonitorSourceModes) {
            $px = $mode.HorizontalActivePixels * $mode.VerticalActivePixels
            if ($px -gt $maxPx) {
                $maxPx = $px
                $nW = $mode.HorizontalActivePixels
                $nH = $mode.VerticalActivePixels
            }
        }
        if ($nW -gt 0) { $wmiNative[$hwId] = @{W = $nW; H = $nH} }
    }
}

"""
        + _CORRELATE_MONITORS_PS
        + r"""
# DeviceName → hwId, joined by UID inside Build-DeviceHwIdMap. A screen the
# join cannot place keeps hwId "" — reported as uncorrelated, never guessed.
$deviceHwIdMap = Build-DeviceHwIdMap `
    -adapterRecords ([DisplayDevices]::EnumerateAdapters()) -uidToHwId $uidToHwId

# Helper: current display mode (physical pixels, not DPI-scaled logical pixels)
function Get-CurrentMode {
    param([string]$dev)
    $dm = New-Object DisplaySettings+DEVMODE
    $dm.dmSize = [System.Runtime.InteropServices.Marshal]::SizeOf($dm)
    if ([DisplaySettings]::EnumDisplaySettings($dev, [DisplaySettings]::ENUM_CURRENT_SETTINGS, [ref]$dm)) {
        return @{ Hz = $dm.dmDisplayFrequency; W = $dm.dmPelsWidth; H = $dm.dmPelsHeight }
    }
    return @{ Hz = 0; W = 0; H = 0 }
}

# Helper: max refresh rate at a specific resolution
function Get-MaxHz {
    param([string]$dev, [int]$w, [int]$h)
    $maxHz = 0
    $dm = New-Object DisplaySettings+DEVMODE
    $dm.dmSize = [System.Runtime.InteropServices.Marshal]::SizeOf($dm)
    $n = 0
    while ([DisplaySettings]::EnumDisplaySettings($dev, $n, [ref]$dm)) {
        if ($dm.dmPelsWidth -eq $w -and $dm.dmPelsHeight -eq $h -and $dm.dmDisplayFrequency -gt $maxHz) {
            $maxHz = $dm.dmDisplayFrequency
        }
        $n++
    }
    return $maxHz
}

# Enumerate active displays via AllScreens (primary first, then sorted by device name)
$screens = [System.Windows.Forms.Screen]::AllScreens |
    Sort-Object @{Expression={if ($_.Primary) {0} else {1}}}, DeviceName

foreach ($screen in $screens) {
    $deviceName = $screen.DeviceName   # e.g., \\.\DISPLAY1
    $isPrimary = $screen.Primary

    # Physical resolution + refresh rate via EnumDisplaySettings (avoids DPI-scaled Bounds)
    $mode = Get-CurrentMode -dev $deviceName
    $curW = if ($mode.W -gt 0) { $mode.W } else { $screen.Bounds.Width }
    $curH = if ($mode.H -gt 0) { $mode.H } else { $screen.Bounds.Height }
    $curHz = $mode.Hz

    # Look up hardware ID from pre-built correlation map (index-independent)
    $cleanDevName = $deviceName.TrimEnd([char]0, ' ')
    $hwId = if ($deviceHwIdMap.ContainsKey($cleanDevName)) { $deviceHwIdMap[$cleanDevName] } else { "" }

    # Native resolution from WMI; fallback to current resolution
    $nativeW = 0; $nativeH = 0
    if ($hwId -and $wmiNative.ContainsKey($hwId)) {
        $nativeW = $wmiNative[$hwId].W
        $nativeH = $wmiNative[$hwId].H
    }
    if ($nativeW -eq 0) { $nativeW = $curW }
    if ($nativeH -eq 0) { $nativeH = $curH }

    # Max refresh rate at native resolution
    $maxHz = Get-MaxHz -dev $deviceName -w $nativeW -h $nativeH
    if ($maxHz -le 0) { $maxHz = $curHz }

    # Friendly name from WMI; fallback to display number
    $friendlyName = ""
    if ($hwId -and $wmiNames.ContainsKey($hwId)) { $friendlyName = $wmiNames[$hwId] }
    if (-not $friendlyName) {
        $dispNum = if ($deviceName -match 'DISPLAY(\d+)') { $Matches[1] } else { "?" }
        $friendlyName = "Display $dispNum"
    }

    $supportsVRR = ($maxHz -gt 60)

    Write-Output "Monitor=$deviceName|Width=$curW|Height=$curH|Refresh=$curHz|Primary=$isPrimary|NativeW=$nativeW|NativeH=$nativeH|NativeRefresh=$maxHz|MaxRefresh=$maxHz|FriendlyName=$friendlyName|MonitorId=$hwId|SupportsVRR=$supportsVRR|IsActive=True"
}
"""
    )

    try:
        from fpstune.utils.debug import debug_context, debug_log

        debug_log("hardware", "Starting PowerShell monitor detection")

        with debug_context("get_monitors", "hardware") as dbg:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=60,  # Complex script: WMI + EnumDisplaySettings P/Invoke
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,  # type: ignore[unused-ignore]
                encoding="utf-8",
                errors="replace",
            )

            dbg.set_detail("exit_code", result.returncode)
            dbg.set_detail("stdout_length", len(result.stdout))
            dbg.set_detail("stderr_length", len(result.stderr))
            dbg.set_detail("stdout_preview", result.stdout[:1000] if result.stdout else "(empty)")
            dbg.set_detail("stderr_preview", result.stderr[:500] if result.stderr else "(empty)")

            # Always log regardless of DEBUG_ENABLED (stored in entries)
            debug_log("hardware", f"Monitor PS exit_code={result.returncode}")
            debug_log("hardware", f"Monitor PS stdout_len={len(result.stdout)}")
            debug_log("hardware", f"Monitor PS stdout: {result.stdout[:800]}")
            if result.stderr:
                debug_log("hardware", f"Monitor PS stderr: {result.stderr[:500]}")

            logger.debug(f"Monitor detection: exit={result.returncode}")
            if result.stderr:
                logger.debug(f"Monitor stderr: {result.stderr[:200]}")
                dbg.add_warning(f"stderr: {result.stderr[:200]}")

            # Log raw output for debugging
            if not result.stdout.strip():
                dbg.add_error("Empty stdout from PowerShell")
                logger.warning("Monitor detection returned empty output")
                debug_log("hardware", "PROBLEM: Empty stdout from monitor detection!")

        lines_found = 0
        monitor_lines = []
        for line in result.stdout.splitlines():
            line = line.strip()
            lines_found += 1
            if not line.startswith("Monitor="):
                continue
            monitor_lines.append(line)

        debug_log(
            "hardware",
            f"Total lines in output: {lines_found}, Monitor= lines: {len(monitor_lines)}",
        )
        for ml in monitor_lines:
            debug_log("hardware", f"Monitor line: {ml[:200]}")

        for line in monitor_lines:
            parts = dict(p.split("=", 1) for p in line.split("|") if "=" in p)
            name = parts.get("Monitor", "Display")
            width = int(parts.get("Width", 0) or 0)
            height = int(parts.get("Height", 0) or 0)
            is_primary = parts.get("Primary", "False").lower() == "true"
            refresh_rate = int(parts.get("Refresh", 0) or 0)
            native_width = int(parts.get("NativeW", 0) or 0)
            native_height = int(parts.get("NativeH", 0) or 0)
            native_refresh = int(parts.get("NativeRefresh", 0) or 0)
            max_refresh = int(parts.get("MaxRefresh", 0) or 0)
            friendly_name = parts.get("FriendlyName", "").strip()
            supports_vrr = parts.get("SupportsVRR", "False").lower() == "true"
            is_active = parts.get("IsActive", "True").lower() == "true"
            hardware_id = parts.get("MonitorId", "").strip()

            # Include monitor if:
            # - Active with resolution, OR
            # - Disconnected with native resolution (from EnumDisplaySettings)
            has_resolution = width > 0 and height > 0
            has_native = native_width > 0 and native_height > 0

            if has_resolution or has_native:
                mon_info = MonitorInfo(
                    name=name,
                    width=width if width > 0 else native_width,
                    height=height if height > 0 else native_height,
                    refresh_rate_hz=refresh_rate,
                    is_primary=is_primary,
                    friendly_name=friendly_name,
                    native_width=native_width if native_width > 0 else width,
                    native_height=native_height if native_height > 0 else height,
                    native_refresh_rate_hz=native_refresh if native_refresh > 0 else max_refresh,
                    max_refresh_rate_hz=max_refresh if max_refresh > 0 else refresh_rate,
                    supports_vrr=supports_vrr,
                    is_active=is_active,
                    hardware_id=hardware_id,
                )
                monitors.append(mon_info)

    except Exception as e:
        logger.warning("Failed to get monitor info: %s", e)
        debug_log("hardware", f"EXCEPTION in get_monitors: {type(e).__name__}: {e}")

    debug_log("hardware", f"get_monitors() returning {len(monitors)} monitors")

    # Log summary once
    if monitors:
        summary = ", ".join(
            f"{m.friendly_name or m.name}: {m.width}x{m.height}@{m.refresh_rate_hz}Hz "
            f"(native: {m.native_width}x{m.native_height}@{m.native_refresh_rate_hz}Hz, "
            f"VRR: {'Yes' if m.supports_vrr else 'No'})"
            for m in monitors
        )
        logger.debug(f"Monitors ({len(monitors)}): {summary}")
    else:
        logger.warning("No monitors detected")

    return monitors
