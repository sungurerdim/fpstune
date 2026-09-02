"""System detection utilities for OS and GPU information."""

from __future__ import annotations

import base64
import contextlib
import platform
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from fpstune.utils.edid import parse_edid
from fpstune.utils.monitor_topology import (
    MonitorRow,
    build_monitor_rows,
    parse_wmi_monitor_lines,
)
from fpstune.utils.winapi import display as winapi_display
from fpstune.utils.winapi.cpu_topology import core_split

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
    """Detailed CPU information.

    There is deliberately no max/boost clock field: Win32_Processor exposes one
    clock (MaxClockSpeed, which reports the rated base — live, 2304 on a CPU
    whose boost is 4.6 GHz), and a field that duplicates another under a
    different name is a claim nothing measured (C11). Core counts are summed
    across sockets; ``is_hybrid`` is None when the P/E topology could not be
    read — unknown, never "not hybrid".
    """

    name: str
    physical_cores: int
    logical_cores: int
    base_clock_mhz: int
    architecture: str
    cache_l3_mb: int
    sockets: int = 1
    p_cores: int = 0
    e_cores: int = 0
    is_hybrid: bool | None = None


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
    # The EDID preferred timing's own rate; 0 when the EDID was unreadable —
    # never a copy of the mode-list maximum (the two answer different questions
    # and may legitimately disagree). Serialized as None when 0.
    native_refresh_rate_hz: int = 0
    # Maximum values from EnumDisplaySettings (may include OC modes)
    max_refresh_rate_hz: int = 0
    # VRR (G-Sync/FreeSync) support: the EDID's declaration, tri-state.
    # None means the EDID could not be read — unknown, not "no", and nothing
    # that needs a VRR panel may register against it.
    supports_vrr: bool | None = None
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
        """Check if current refresh rate reaches the panel's ceiling.

        The ceiling is the mode-list maximum first, the EDID preferred rate
        only as a fallback — a high-refresh panel's EDID often *prefers* 60 Hz
        while its mode list reaches 300, and judging against the preferred rate
        would call a panel driven at a fraction of its ceiling optimal.
        Returns False when both are unknown (0) — unknown never claims optimal.
        """
        target = self.max_refresh_rate_hz or self.native_refresh_rate_hz
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


# VRAM comes from the driver's own HardwareInformation.qwMemorySize (a QWORD),
# reached through the device's Enum key → Driver value → Class key: an exact
# per-device binding, no name matching. Win32_VideoController.AdapterRAM is a
# 32-bit field that clamps at 4 GB — live, a card with 8192 MB reported
# 4293918720 (4095 MB) — so it is never read, not even as a sort key: sorting
# clamped values to pick "the biggest card" is undefined once two cards clamp.
# The pick is the adapter with the most driver-reported memory; a machine where
# no driver reports any leaves VRAM 0, which is "unknown", never a guess.
_GPU_DETECT_PS = (
    "$ErrorActionPreference = 'SilentlyContinue'; "
    "$best = $null; $bestQw = [int64]-1; "
    "foreach ($c in @(Get-CimInstance -ClassName Win32_VideoController)) { "
    "$qw = [int64]0; "
    '$drv = (Get-ItemProperty -Path ("HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\" + $c.PNPDeviceID) '
    "-Name Driver -ErrorAction SilentlyContinue).Driver; "
    "if ($drv) { "
    '$qw = [int64](Get-ItemProperty -Path ("HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\" + $drv) '
    "-Name 'HardwareInformation.qwMemorySize' -ErrorAction SilentlyContinue)."
    "'HardwareInformation.qwMemorySize' }; "
    "if ($qw -gt $bestQw) { $bestQw = $qw; $best = $c } "
    "} "
    "if ($best) { "
    '"Name=$($best.Name)"; "Driver=$($best.DriverVersion)"; '
    'if ($bestQw -gt 0) { "VramBytes=$bestQw" }; "PNP=$($best.PNPDeviceID)" }'
)


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
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", _GPU_DETECT_PS],
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
                elif line.startswith("VramBytes="):
                    try:
                        vram_str = line.split("=", 1)[1].strip()
                        if vram_str:
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


# All sockets are read and their core counts summed — Select-Object -First 1
# silently halved a dual-socket machine. The one clock WMI has is MaxClockSpeed,
# which reports the *rated* clock (live: 2304 on a CPU whose boost is 4.6 GHz);
# it is emitted as the base clock and nothing invents a boost figure from it.
#
# The P/E-core split is deliberately not in here. It comes from
# GetLogicalProcessorInformationEx through `utils/winapi/cpu_topology.py`
# (ctypes). It used to be a C# class compiled at run time with Add-Type, the
# pattern Windows Defender flagged as trojan behaviour on 2026-09-02 — see the
# winapi package docstring.
_CPU_DETECT_PS = r"""
$cpus = @(Get-CimInstance -ClassName Win32_Processor)
if ($cpus.Count -gt 0) {
    "Name=$($cpus[0].Name)"
    "Sockets=$($cpus.Count)"
    "PhysicalCores=$(($cpus | Measure-Object -Property NumberOfCores -Sum).Sum)"
    "LogicalCores=$(($cpus | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum)"
    "BaseClock=$($cpus[0].MaxClockSpeed)"
    "L3Cache=$(($cpus | Measure-Object -Property L3CacheSize -Sum).Sum)"
}
"""


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
        architecture = platform.machine() or ""
        cache_l3_mb = 0
        sockets = 1
        p_cores = 0
        e_cores = 0
        is_hybrid: bool | None = None

        try:
            # Get ALL CPU info in single PowerShell call (optimized)
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", _CPU_DETECT_PS],
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
                elif line.startswith("Sockets="):
                    with contextlib.suppress(ValueError, TypeError):
                        sockets = int(line.split("=", 1)[1].strip()) or 1
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

        split = core_split()
        if split is None:
            logger.debug("CPU P/E topology unknown: GetLogicalProcessorInformationEx gave nothing")
        else:
            p_cores, e_cores, is_hybrid = split.p_cores, split.e_cores, split.is_hybrid

        _cpu_detailed_cache = CpuDetailedInfo(
            name=name,
            physical_cores=physical_cores,
            logical_cores=logical_cores,
            base_clock_mhz=base_clock_mhz,
            architecture=architecture,
            cache_l3_mb=cache_l3_mb,
            sockets=sockets,
            p_cores=p_cores,
            e_cores=e_cores,
            is_hybrid=is_hybrid,
        )
        return _cpu_detailed_cache


# WMI answers identity: which panels exist (hardware id, the UID Windows gave the
# instance, the friendly name, the EDID the panel handed the OS) and the modes
# the panel itself lists. Everything about the desktop — which adapter head is
# attached, which is primary, what mode it runs — comes from user32 through
# `utils/winapi/display.py`, in Python, and the join lives in
# `utils/monitor_topology.py`. The two used to share one PowerShell script that
# compiled two C# classes with Add-Type: the pattern Windows Defender flagged as
# trojan behaviour on 2026-09-02, and a compile per scan. The records here are
# positional and locale-free — numbers and base64 only, the friendly name last
# because a name may contain the separator.
_MONITOR_WMI_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID 2>$null | ForEach-Object {
    $parts = $_.InstanceName -split '\\'
    if ($parts.Count -ge 2) {
        $hwId = $parts[1]
        $chars = $_.UserFriendlyName | Where-Object { $_ -gt 0 }
        $name = if ($chars) { -join [char[]]$chars } else { "" }
        $uid = if ($_.InstanceName -match 'UID(\d+)') { $Matches[1] } else { '' }
        $edidB64 = ''
        if ($uid) {
            # The instance name doubles as the device's registry path: the EDID
            # the panel handed the OS sits under its Device Parameters key.
            $inst = $_.InstanceName -replace '_\d+$', ''
            $edid = (Get-ItemProperty `
                -Path "HKLM:\SYSTEM\CurrentControlSet\Enum\$inst\Device Parameters" `
                -Name EDID -ErrorAction SilentlyContinue).EDID
            if ($edid) { $edidB64 = [Convert]::ToBase64String([byte[]]$edid) }
        }
        "WMI|$hwId|$uid|$edidB64|$name"
    }
}
Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorListedSupportedSourceModes 2>$null | ForEach-Object {
    $parts = $_.InstanceName -split '\\'
    if ($parts.Count -ge 2) {
        $nW = 0; $nH = 0; $maxPx = 0
        foreach ($mode in $_.MonitorSourceModes) {
            $px = $mode.HorizontalActivePixels * $mode.VerticalActivePixels
            if ($px -gt $maxPx) {
                $maxPx = $px
                $nW = $mode.HorizontalActivePixels
                $nH = $mode.VerticalActivePixels
            }
        }
        if ($nW -gt 0) { "NATIVE|$($parts[1])|$nW|$nH" }
    }
}
"""


def _monitor_from_row(row: MonitorRow) -> MonitorInfo | None:
    """One report row to a MonitorInfo, or None when there is nothing to report.

    The native refresh rate and VRR support are the EDID's answers. No EDID, or
    one that fails its own checksum, means both stay unknown — 0 and None —
    never a guess from the mode list.
    """
    edid_info = None
    if row.edid_b64:
        try:
            edid_info = parse_edid(base64.b64decode(row.edid_b64))
        except Exception:
            edid_info = None
    native_refresh = (edid_info.native_refresh_hz or 0) if edid_info else 0
    supports_vrr = edid_info.supports_vrr if edid_info else None

    # A row is reported when it is active with a resolution, present-but-inactive
    # with a native resolution from WMI, or carries an identity at all — a panel
    # WMI names is a fact worth reporting even when it reports no modes.
    has_resolution = row.width > 0 and row.height > 0
    has_native = row.native_width > 0 and row.native_height > 0
    if not (has_resolution or has_native or row.hardware_id):
        return None
    return MonitorInfo(
        name=row.name,
        width=row.width if row.width > 0 else row.native_width,
        height=row.height if row.height > 0 else row.native_height,
        refresh_rate_hz=row.refresh_hz,
        is_primary=row.primary,
        friendly_name=row.friendly_name,
        native_width=row.native_width if row.native_width > 0 else row.width,
        native_height=row.native_height if row.native_height > 0 else row.height,
        native_refresh_rate_hz=native_refresh,
        max_refresh_rate_hz=row.max_refresh_hz if row.max_refresh_hz > 0 else row.refresh_hz,
        supports_vrr=supports_vrr,
        is_active=row.is_active,
        hardware_id=row.hardware_id,
    )


def get_monitors() -> list[MonitorInfo]:
    """Connected monitors: identity from WMI, desktop state and modes from user32.

    Returns:
        List of MonitorInfo for each present display, attached heads first.
    """
    import logging

    from fpstune.utils.debug import debug_context, debug_log

    logger = logging.getLogger("fpstune.detect")
    debug_log("hardware", "get_monitors() called")

    if sys.platform != "win32":
        debug_log("hardware", "Not on Windows, returning empty list")
        return []

    monitors: list[MonitorInfo] = []
    try:
        with debug_context("get_monitors", "hardware") as dbg:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    _MONITOR_WMI_PS,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,  # type: ignore[unused-ignore]
                encoding="utf-8",
                errors="replace",
            )
            dbg.set_detail("exit_code", result.returncode)
            dbg.set_detail("stdout_preview", result.stdout[:1000] if result.stdout else "(empty)")
            if result.stderr:
                logger.debug(f"Monitor WMI stderr: {result.stderr[:200]}")
                dbg.add_warning(f"stderr: {result.stderr[:200]}")
            if not result.stdout.strip():
                dbg.add_error("Empty stdout from the WMI monitor query")
                logger.warning("Monitor WMI query returned empty output")

            facts = parse_wmi_monitor_lines(result.stdout)
            records = winapi_display.enumerate_adapters()
            dbg.set_detail("wmi_panels", len(facts.names))
            dbg.set_detail("adapter_records", len(records))
            debug_log("hardware", f"Monitor WMI panels={len(facts.names)} heads={len(records)}")
            rows = build_monitor_rows(
                facts, records, winapi_display.current_mode, winapi_display.max_refresh_at
            )

        for row in rows:
            info = _monitor_from_row(row)
            if info is not None:
                monitors.append(info)

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
