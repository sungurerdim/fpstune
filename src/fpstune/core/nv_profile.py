"""NVIDIA Profile Inspector integration for driver settings management.

This module provides:
- Automatic nvidiaProfileInspector download from GitHub
- .nip profile file generation
- Silent profile application
- Reading current settings (via exported profiles)

The NVIDIA Control Panel settings are stored in NVIDIA's DRS (Driver Settings)
database, not in Windows Registry. This tool allows programmatic access.

References:
- https://github.com/Orbmu2k/nvidiaProfileInspector
- NVAPI Setting IDs from NvApiDriverSettings.h
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen, urlretrieve
from xml.etree import ElementTree as ET

from fpstune.utils.config import get_config_dir
from fpstune.utils.logger import get_logger

# GitHub API for releases
NPI_GITHUB_REPO = "Orbmu2k/nvidiaProfileInspector"
NPI_RELEASES_URL = f"https://api.github.com/repos/{NPI_GITHUB_REPO}/releases/latest"


# NVAPI Setting IDs (from NvApiDriverSettings.h)
# These are the hex IDs used in .nip profile files
class NvApiSettings:
    """NVIDIA driver setting IDs."""

    # Power Management Mode (PREFERRED_PSTATE)
    POWER_MANAGEMENT_MODE = 0x1057EB71
    POWER_ADAPTIVE = 0x00000000
    POWER_PREFER_MAX = 0x00000001
    POWER_DRIVER_CONTROLLED = 0x00000002
    POWER_CONSISTENT_PERFORMANCE = 0x00000003
    POWER_PREFER_MIN = 0x00000004
    POWER_OPTIMAL = 0x00000005

    # Low Latency Mode (PRERENDER_LIMIT)
    LOW_LATENCY_MODE = 0x00707011
    LATENCY_OFF = 0x00000000  # Application controlled
    LATENCY_ON = 0x00000001  # On (1 frame)
    LATENCY_ULTRA = 0x00000002  # Ultra (0 frames)

    # Threaded Optimization
    THREADED_OPTIMIZATION = 0x00707010
    THREADED_AUTO = 0x00000000
    THREADED_ON = 0x00000001
    THREADED_OFF = 0x00000002

    # VSync
    VSYNC_MODE = 0x00707018
    VSYNC_OFF = 0x00000000
    VSYNC_ON = 0x00000001
    VSYNC_ADAPTIVE = 0x00000002
    VSYNC_ADAPTIVE_HALF = 0x00000003

    # Shader Cache
    SHADER_CACHE = 0x00707012
    SHADER_CACHE_OFF = 0x00000000
    SHADER_CACHE_ON = 0x00000001

    # Texture Filtering - Quality
    TEXTURE_QUALITY = 0x00707013
    TEXTURE_HIGH_QUALITY = 0x00000000
    TEXTURE_QUALITY_DEFAULT = 0x00000001
    TEXTURE_PERFORMANCE = 0x00000002
    TEXTURE_HIGH_PERFORMANCE = 0x00000003

    # Triple Buffering
    TRIPLE_BUFFER = 0x0070701A
    TRIPLE_BUFFER_OFF = 0x00000000
    TRIPLE_BUFFER_ON = 0x00000001

    # Maximum Pre-rendered Frames (separate from Low Latency)
    MAX_PRERENDERED_FRAMES = 0x00707008

    # Anisotropic Filtering
    ANISO_FILTER = 0x0070701E
    ANISO_APP_CONTROLLED = 0x00000000
    ANISO_2X = 0x00000002
    ANISO_4X = 0x00000004
    ANISO_8X = 0x00000008
    ANISO_16X = 0x00000010

    # Antialiasing Mode
    AA_MODE = 0x00707014
    AA_APP_CONTROLLED = 0x00000000
    AA_ENHANCE = 0x00000001
    AA_OVERRIDE = 0x00000002

    # Frame Rate Limiter (FRL)
    # Sets a global FPS cap. Better than VSync for low latency with tear prevention.
    FRL_FPS = 0x10835002
    FRL_OFF = 0x00000000  # No limit

    # G-Sync / VRR Mode
    VRR_MODE = 0x1194F158
    VRR_OFF = 0x00000000
    VRR_ON = 0x00000001
    VRR_FULLSCREEN = 0x00000002

    # G-Sync Application Override
    VRR_APP_OVERRIDE = 0x10A879CF
    VRR_APP_DRIVER = 0x00000000  # Use driver settings
    VRR_APP_ON = 0x00000001  # Enable per-app
    VRR_APP_OFF = 0x00000002  # Disable per-app

    # Background Application Max Frame Rate
    # Limits FPS for unfocused/background windows - saves power when alt-tabbed
    BG_APP_MAX_FPS = 0x10835004
    BG_APP_FPS_OFF = 0x00000000  # No limit

    # Anisotropic Filtering Sample Optimization
    # Reduces anisotropic samples for minor performance gain
    ANISO_SAMPLE_OPT = 0x00707019
    ANISO_SAMPLE_OPT_OFF = 0x00000000
    ANISO_SAMPLE_OPT_ON = 0x00000001

    # Texture Filtering - Negative LOD Bias
    # Clamp prevents blurry textures, Allow can sharpen distant textures
    TEXTURE_LOD_BIAS = 0x0070701B
    TEXTURE_LOD_ALLOW = 0x00000000
    TEXTURE_LOD_CLAMP = 0x00000001

    # OpenGL Threading Optimization
    # Improves performance for OpenGL games (Minecraft, emulators)
    OGL_THREAD_CONTROL = 0x20C1221E
    OGL_THREAD_AUTO = 0x00000000
    OGL_THREAD_ON = 0x00000001
    OGL_THREAD_OFF = 0x00000002

    # CUDA - Force P2 State
    # Forces higher GPU power state for CUDA applications
    CUDA_FORCE_P2 = 0x0070701C
    CUDA_P2_OFF = 0x00000000
    CUDA_P2_ON = 0x00000001


@dataclass
class NvidiaProfile:
    """NVIDIA driver profile settings.

    Use name="Base Profile" for system-wide settings that apply to ALL games.
    Use a custom name + executables for game-specific profiles.
    """

    # "Base Profile" applies to ALL applications system-wide
    name: str = "Base Profile"
    executables: list[str] | None = None

    # Core gaming settings (must match SettingExecutor default_values for SSOT)
    power_mode: str = "optimal"  # optimal, adaptive, maximum
    low_latency: str = "off"  # off, on, ultra (NVIDIA default is off)
    threaded_opt: str = "auto"  # off, on, auto (NVIDIA default is auto)
    vsync: str = "on"  # off, on, adaptive (NVIDIA default is on)
    shader_cache: str = "on"  # off, on
    texture_quality: str = "quality"  # high_quality, quality, performance, high_performance
    triple_buffer: str = "off"  # off, on

    # FPS Limiter - set to 0 (off) or specific FPS value
    fps_limit: int = 0  # 0 = off, 30-500 = FPS cap

    # Background Application Max Frame Rate — off by default, and deliberately so.
    # to_settings_dict() emits every key unconditionally, so this dataclass default
    # is written to the driver whenever *any* NVIDIA setting is applied. At 30 that
    # imposed a background cap on users who never asked for one, and the driver
    # applies that cap to focused games whose overlays defeat its foreground
    # detection — see gpu-nvidia:bg_app_fps for the evidence.
    bg_app_fps: int = 0  # 0 = off

    # G-Sync / VRR settings
    vrr_mode: str = "off"  # off, on, fullscreen

    # Anisotropic Filtering Sample Optimization - minor perf gain
    aniso_sample_opt: str = "on"  # off, on

    # Texture Filtering - Negative LOD Bias
    texture_lod_bias: str = "clamp"  # allow, clamp

    # OpenGL Threading Optimization - for OpenGL games
    ogl_thread_opt: str = "on"  # off, on, auto

    # CUDA Force P2 State - stable clocks for CUDA apps
    cuda_force_p2: str = "off"  # off, on

    # Maximum Pre-rendered Frames (separate from Low Latency)
    max_prerendered: int = 3  # 1-4, driver default is 3

    # G-Sync Application Override
    vrr_app_override: str = "driver_default"  # off, driver_default, force_on

    def to_settings_dict(self) -> dict[int, int]:
        """Convert profile to NVAPI setting ID -> value mapping."""
        settings = {}

        # Power Management Mode
        power_map = {
            "optimal": NvApiSettings.POWER_OPTIMAL,
            "adaptive": NvApiSettings.POWER_ADAPTIVE,
            "maximum": NvApiSettings.POWER_PREFER_MAX,
            "consistent": NvApiSettings.POWER_CONSISTENT_PERFORMANCE,
        }
        settings[NvApiSettings.POWER_MANAGEMENT_MODE] = power_map.get(
            self.power_mode, NvApiSettings.POWER_PREFER_MAX
        )

        # Low Latency Mode
        latency_map = {
            "off": NvApiSettings.LATENCY_OFF,
            "on": NvApiSettings.LATENCY_ON,
            "ultra": NvApiSettings.LATENCY_ULTRA,
        }
        settings[NvApiSettings.LOW_LATENCY_MODE] = latency_map.get(
            self.low_latency, NvApiSettings.LATENCY_ULTRA
        )

        # Threaded Optimization
        threaded_map = {
            "off": NvApiSettings.THREADED_OFF,
            "on": NvApiSettings.THREADED_ON,
            "auto": NvApiSettings.THREADED_AUTO,
        }
        settings[NvApiSettings.THREADED_OPTIMIZATION] = threaded_map.get(
            self.threaded_opt, NvApiSettings.THREADED_ON
        )

        # VSync
        vsync_map = {
            "off": NvApiSettings.VSYNC_OFF,
            "on": NvApiSettings.VSYNC_ON,
            "adaptive": NvApiSettings.VSYNC_ADAPTIVE,
        }
        settings[NvApiSettings.VSYNC_MODE] = vsync_map.get(self.vsync, NvApiSettings.VSYNC_OFF)

        # Shader Cache
        shader_map = {
            "off": NvApiSettings.SHADER_CACHE_OFF,
            "on": NvApiSettings.SHADER_CACHE_ON,
        }
        settings[NvApiSettings.SHADER_CACHE] = shader_map.get(
            self.shader_cache, NvApiSettings.SHADER_CACHE_ON
        )

        # Texture Quality
        texture_map = {
            "high_quality": NvApiSettings.TEXTURE_HIGH_QUALITY,
            "quality": NvApiSettings.TEXTURE_QUALITY_DEFAULT,
            "performance": NvApiSettings.TEXTURE_PERFORMANCE,
            "high_performance": NvApiSettings.TEXTURE_HIGH_PERFORMANCE,
        }
        settings[NvApiSettings.TEXTURE_QUALITY] = texture_map.get(
            self.texture_quality, NvApiSettings.TEXTURE_PERFORMANCE
        )

        # Triple Buffering
        triple_map = {
            "off": NvApiSettings.TRIPLE_BUFFER_OFF,
            "on": NvApiSettings.TRIPLE_BUFFER_ON,
        }
        settings[NvApiSettings.TRIPLE_BUFFER] = triple_map.get(
            self.triple_buffer, NvApiSettings.TRIPLE_BUFFER_OFF
        )

        # FPS Limiter (only add if set to a non-zero value)
        if self.fps_limit > 0:
            settings[NvApiSettings.FRL_FPS] = self.fps_limit
        else:
            settings[NvApiSettings.FRL_FPS] = NvApiSettings.FRL_OFF

        # G-Sync / VRR Mode
        vrr_map = {
            "off": NvApiSettings.VRR_OFF,
            "on": NvApiSettings.VRR_ON,
            "fullscreen": NvApiSettings.VRR_FULLSCREEN,
        }
        settings[NvApiSettings.VRR_MODE] = vrr_map.get(self.vrr_mode, NvApiSettings.VRR_OFF)

        # Background Application Max Frame Rate
        if self.bg_app_fps > 0:
            settings[NvApiSettings.BG_APP_MAX_FPS] = self.bg_app_fps
        else:
            settings[NvApiSettings.BG_APP_MAX_FPS] = NvApiSettings.BG_APP_FPS_OFF

        # Anisotropic Filtering Sample Optimization
        aniso_opt_map = {
            "off": NvApiSettings.ANISO_SAMPLE_OPT_OFF,
            "on": NvApiSettings.ANISO_SAMPLE_OPT_ON,
        }
        settings[NvApiSettings.ANISO_SAMPLE_OPT] = aniso_opt_map.get(
            self.aniso_sample_opt, NvApiSettings.ANISO_SAMPLE_OPT_ON
        )

        # Texture Filtering - Negative LOD Bias
        lod_bias_map = {
            "allow": NvApiSettings.TEXTURE_LOD_ALLOW,
            "clamp": NvApiSettings.TEXTURE_LOD_CLAMP,
        }
        settings[NvApiSettings.TEXTURE_LOD_BIAS] = lod_bias_map.get(
            self.texture_lod_bias, NvApiSettings.TEXTURE_LOD_CLAMP
        )

        # OpenGL Threading Optimization
        ogl_thread_map = {
            "off": NvApiSettings.OGL_THREAD_OFF,
            "on": NvApiSettings.OGL_THREAD_ON,
            "auto": NvApiSettings.OGL_THREAD_AUTO,
        }
        settings[NvApiSettings.OGL_THREAD_CONTROL] = ogl_thread_map.get(
            self.ogl_thread_opt, NvApiSettings.OGL_THREAD_ON
        )

        # CUDA Force P2 State
        cuda_p2_map = {
            "off": NvApiSettings.CUDA_P2_OFF,
            "on": NvApiSettings.CUDA_P2_ON,
        }
        settings[NvApiSettings.CUDA_FORCE_P2] = cuda_p2_map.get(
            self.cuda_force_p2, NvApiSettings.CUDA_P2_OFF
        )

        # Maximum Pre-rendered Frames
        settings[NvApiSettings.MAX_PRERENDERED_FRAMES] = max(1, min(4, self.max_prerendered))

        # G-Sync Application Override
        vrr_app_map = {
            "off": NvApiSettings.VRR_APP_OFF,
            "driver_default": NvApiSettings.VRR_APP_DRIVER,
            "force_on": NvApiSettings.VRR_APP_ON,
        }
        settings[NvApiSettings.VRR_APP_OVERRIDE] = vrr_app_map.get(
            self.vrr_app_override, NvApiSettings.VRR_APP_DRIVER
        )

        return settings


# Setting name mapping for human-readable output
SETTING_NAMES = {
    NvApiSettings.POWER_MANAGEMENT_MODE: "Power Management Mode",
    NvApiSettings.LOW_LATENCY_MODE: "Low Latency Mode",
    NvApiSettings.THREADED_OPTIMIZATION: "Threaded Optimization",
    NvApiSettings.VSYNC_MODE: "Vertical Sync",
    NvApiSettings.SHADER_CACHE: "Shader Cache",
    NvApiSettings.TEXTURE_QUALITY: "Texture Filtering - Quality",
    NvApiSettings.TRIPLE_BUFFER: "Triple Buffering",
    NvApiSettings.ANISO_FILTER: "Anisotropic Filtering",
    NvApiSettings.AA_MODE: "Antialiasing Mode",
    NvApiSettings.FRL_FPS: "Frame Rate Limiter",
    NvApiSettings.VRR_MODE: "G-Sync / VRR Mode",
    NvApiSettings.BG_APP_MAX_FPS: "Background Application Max Frame Rate",
    NvApiSettings.ANISO_SAMPLE_OPT: "Anisotropic Sample Optimization",
    NvApiSettings.TEXTURE_LOD_BIAS: "Texture Filtering - LOD Bias",
    NvApiSettings.OGL_THREAD_CONTROL: "OpenGL Threading Optimization",
    NvApiSettings.CUDA_FORCE_P2: "CUDA - Force P2 State",
    NvApiSettings.MAX_PRERENDERED_FRAMES: "Maximum Pre-rendered Frames",
    NvApiSettings.VRR_APP_OVERRIDE: "G-Sync Application Override",
}


class NvidiaProfileInspector:
    """NVIDIA Profile Inspector manager.

    Handles downloading, installing, and using nvidiaProfileInspector
    to manage NVIDIA driver settings programmatically.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        """Initialize the profile inspector manager.

        Args:
            data_dir: Directory to store tool and profiles.
        """
        self._data_dir = data_dir or get_config_dir() / "nvidia"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._tool_dir = self._data_dir / "nvidiaProfileInspector"
        self._profiles_dir = self._data_dir / "profiles"
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

        self._logger = get_logger()

    @property
    def exe_path(self) -> Path:
        """Path to nvidiaProfileInspector executable."""
        return self._tool_dir / "nvidiaProfileInspector.exe"

    def is_installed(self) -> bool:
        """Check if nvidiaProfileInspector is installed."""
        return self.exe_path.exists()

    def _verify_download(self, path: Path, version: str) -> bool:
        """Verify downloaded file against pinned SHA-256 checksums.

        The archive is extracted and its executable later runs elevated, so
        this gate FAILS CLOSED: a version with no pinned hash in
        resources/checksums.json — or an unreadable checksums file — is
        refused, never trusted. The computed hash is logged so a maintainer
        can vet the release independently and pin it.
        """
        checksums_path = Path(__file__).parent.parent / "resources" / "checksums.json"
        try:
            known = json.loads(checksums_path.read_text(encoding="utf-8"))
            expected = known.get("nvidiaProfileInspector", {}).get(version)
        except Exception as exc:
            self._logger.error(
                f"Cannot read pinned checksums ({exc}); refusing to trust the "
                f"nvidiaProfileInspector {version} download."
            )
            return False

        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

        if expected is None:
            self._logger.error(
                f"No pinned checksum for nvidiaProfileInspector {version}; refusing to "
                f"execute an unverified download (SHA-256: {sha256}). Verify the "
                "release independently and add its hash to resources/checksums.json."
            )
            return False

        if sha256 != expected:
            self._logger.error(
                f"Checksum mismatch for nvidiaProfileInspector {version}: "
                f"expected {expected}, got {sha256}"
            )
            return False

        return True

    def get_latest_release_url(self) -> tuple[str, str] | None:
        """Get the latest release download URL from GitHub.

        Returns:
            Tuple of (download_url, version) or None if failed.
        """
        try:
            req = Request(
                NPI_RELEASES_URL,
                headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "fpstune"},
            )
            with urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

            version = data.get("tag_name", "unknown")

            # Find the zip asset
            for asset in data.get("assets", []):
                name = asset.get("name", "").lower()
                if name.endswith(".zip") and "inspector" in name:
                    return asset["browser_download_url"], version

            # Fallback: use zipball
            return data.get("zipball_url"), version

        except Exception as e:
            self._logger.error(f"Failed to get release info: {e}")
            return None

    def install(self, progress_callback: Any = None) -> bool:
        """Download and install nvidiaProfileInspector.

        Args:
            progress_callback: Optional callback for progress updates.

        Returns:
            True if installation succeeded.
        """
        if sys.platform != "win32":
            self._logger.warning("nvidiaProfileInspector only works on Windows")
            return False

        release_info = self.get_latest_release_url()
        if not release_info:
            self._logger.error("Could not find release download URL")
            return False

        download_url, version = release_info
        self._logger.info(f"Downloading nvidiaProfileInspector {version}...")

        try:
            self._tool_dir.mkdir(parents=True, exist_ok=True)
            zip_path = self._tool_dir / "npi.zip"

            def reporthook(count: int, block_size: int, total_size: int) -> None:
                if progress_callback and total_size > 0:
                    progress = int(count * block_size * 100 / total_size)
                    progress_callback(min(progress, 100))

            urlretrieve(download_url, zip_path, reporthook)

            if not self._verify_download(zip_path, version):
                zip_path.unlink(missing_ok=True)
                return False

            self._logger.info("Extracting nvidiaProfileInspector...")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(self._tool_dir)

            # Find exe if in subdirectory and move up
            for exe in self._tool_dir.rglob("nvidiaProfileInspector.exe"):
                if exe.parent != self._tool_dir:
                    import shutil

                    for item in exe.parent.iterdir():
                        target = self._tool_dir / item.name
                        if not target.exists():
                            shutil.move(str(item), str(target))
                break

            # Cleanup
            zip_path.unlink(missing_ok=True)

            self._logger.info(f"nvidiaProfileInspector {version} installed")
            return self.is_installed()

        except Exception as e:
            self._logger.error(f"Installation failed: {e}")
            return False

    def generate_profile_xml(self, profile: NvidiaProfile) -> str:
        """Generate .nip XML content for a profile.

        NIP format requirements (from actual NPI exports):
        - SettingID: decimal integer (not hex)
        - SettingValue: decimal integer (not hex)
        - No SettingNameInfo or ValueType elements
        - Executeables spelled with 'ea' (not 'ab')

        Args:
            profile: NvidiaProfile with settings.

        Returns:
            XML string for .nip file.
        """
        # Build XML structure
        root = ET.Element("ArrayOfProfile")

        profile_elem = ET.SubElement(root, "Profile")
        ET.SubElement(profile_elem, "ProfileName").text = profile.name

        # Executables (empty for global profile) - note: NPI uses "Executeables"
        executables = ET.SubElement(profile_elem, "Executeables")
        if profile.executables:
            for exe in profile.executables:
                ET.SubElement(executables, "string").text = exe

        # Settings - NPI expects decimal values, not hex
        settings_elem = ET.SubElement(profile_elem, "Settings")

        for setting_id, value in profile.to_settings_dict().items():
            setting_elem = ET.SubElement(settings_elem, "ProfileSetting")
            # NPI uses decimal format for both ID and value
            ET.SubElement(setting_elem, "SettingID").text = str(setting_id)
            ET.SubElement(setting_elem, "SettingValue").text = str(value)

        # Format with XML declaration
        xml_str = ET.tostring(root, encoding="unicode")

        # Add XML declaration (UTF-16 for compatibility with NPI)
        return f'<?xml version="1.0" encoding="utf-16"?>\n{xml_str}'

    def save_profile(self, profile: NvidiaProfile, filename: str | None = None) -> Path:
        """Save profile to .nip file.

        Args:
            profile: NvidiaProfile to save.
            filename: Optional filename (without extension).

        Returns:
            Path to saved .nip file.
        """
        filename = filename or profile.name
        filepath = self._profiles_dir / f"{filename}.nip"

        xml_content = self.generate_profile_xml(profile)

        # Write as UTF-16 (NPI expects this)
        with open(filepath, "w", encoding="utf-16") as f:
            f.write(xml_content)

        self._logger.info(f"Profile saved: {filepath}")
        return filepath

    def check_nvapi_access(self) -> tuple[bool, str | None]:
        """Check if NVAPI is accessible before calling NPI.

        This pre-check helps avoid NPI showing error dialogs by detecting
        common issues beforehand.

        Returns:
            Tuple of (accessible, error_message).
        """
        if sys.platform != "win32":
            return False, "NVAPI only available on Windows"

        # Check 1: Verify nvidia-smi responds (driver is working)
        try:
            result = subprocess.run(
                ["nvidia-smi", "-L"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[unused-ignore]
            )
            if result.returncode != 0:
                return False, (
                    "NVIDIA driver not responding. Try restarting NVIDIA services or your computer."
                )
        except FileNotFoundError:
            return False, "nvidia-smi not found. NVIDIA driver may not be installed."
        except subprocess.TimeoutExpired:
            return False, "nvidia-smi timed out. NVIDIA driver may be stuck."
        except Exception as e:
            self._logger.warning(f"nvidia-smi check failed: {e}")
            # Continue anyway - nvidia-smi might not be in PATH

        # Check 2: Look for processes that might lock NVAPI
        blocking_processes = []
        try:
            # Use tasklist to find NVIDIA-related processes
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq nvcplui.exe", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[unused-ignore]
            )
            if "nvcplui.exe" in result.stdout:
                blocking_processes.append("NVIDIA Control Panel")
        except Exception:
            pass  # tasklist check is optional

        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq NVIDIA Share.exe", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[unused-ignore]
            )
            if "NVIDIA Share.exe" in result.stdout:
                blocking_processes.append("GeForce Experience Share")
        except Exception:
            pass

        if blocking_processes:
            return False, (
                f"NVAPI may be locked by: {', '.join(blocking_processes)}. "
                "Close these applications and try again."
            )

        return True, None

    def apply_profile(
        self, profile_path: Path, silent: bool = True, timeout: int = 60
    ) -> tuple[bool, str | None]:
        """Apply a .nip profile using nvidiaProfileInspector.

        Args:
            profile_path: Path to .nip file.
            silent: Run without GUI.
            timeout: Timeout in seconds (default 60).

        Returns:
            Tuple of (success, error_message).

        Note:
            NPI may show error windows for critical NVAPI errors even in silent mode.
            Common causes: NVIDIA Control Panel open, driver update in progress,
            or another process holding NVAPI lock.
        """
        if not self.is_installed():
            self._logger.info("nvidiaProfileInspector not installed, attempting download...")
            if not self.install():
                return False, "Failed to install nvidiaProfileInspector"

        if not profile_path.exists():
            error = f"Profile not found: {profile_path}"
            self._logger.error(error)
            return False, error

        # Pre-check NVAPI access to avoid NPI showing error dialogs
        nvapi_ok, nvapi_error = self.check_nvapi_access()
        if not nvapi_ok:
            self._logger.error(f"NVAPI pre-check failed: {nvapi_error}")
            return False, nvapi_error

        # Build command: flags first, then file path
        # According to source: ArgExists checks for flags, ArgFileIndex finds the file
        cmd = [str(self.exe_path)]
        if silent:
            cmd.extend(["-silentImport", "-silent"])
        cmd.append(str(profile_path))

        try:
            self._logger.info(f"Applying NVIDIA profile: {profile_path.name}")
            self._logger.debug(f"Command: {' '.join(cmd)}")

            # Use startupinfo to hide console window more aggressively
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW

            # Use Popen for better timeout handling - can kill process if stuck on dialog
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )

            try:
                stdout_bytes, stderr_bytes = process.communicate(timeout=timeout)
                stdout = (
                    stdout_bytes.decode("utf-8", errors="replace").strip() if stdout_bytes else ""
                )
                stderr = (
                    stderr_bytes.decode("utf-8", errors="replace").strip() if stderr_bytes else ""
                )
                returncode = process.returncode
            except subprocess.TimeoutExpired:
                # Kill the process if it's stuck (probably on a dialog)
                process.kill()
                process.wait()
                error = (
                    f"NVAPI access error: nvidiaProfileInspector timed out after {timeout}s. "
                    "This usually means NPI showed an error dialog. "
                    "Close NVIDIA Control Panel and GeForce Experience, then try again."
                )
                self._logger.error(error)
                return False, error

            if returncode == 0:
                self._logger.info("NVIDIA profile applied successfully")
                return True, None
            else:
                raw_error = stderr or stdout or f"Exit code: {returncode}"

                # Check for common NVAPI errors
                error_lower = raw_error.lower()
                if "nvapi" in error_lower or "access" in error_lower:
                    error = (
                        f"NVAPI access error: {raw_error}. "
                        "Close NVIDIA Control Panel and GeForce Experience, then try again."
                    )
                elif returncode != 0 and not raw_error:
                    # NPI showed an error window but didn't write to stdout/stderr
                    error = (
                        "NVAPI access error: nvidiaProfileInspector couldn't access NVIDIA driver. "
                        "Close NVIDIA Control Panel and GeForce Experience, then try again."
                    )
                else:
                    error = raw_error

                self._logger.error(f"Failed to apply NVIDIA profile: {error}")
                return False, error
        except FileNotFoundError:
            error = f"nvidiaProfileInspector.exe not found at {self.exe_path}"
            self._logger.error(error)
            return False, error
        except Exception as e:
            error = f"Failed to apply profile: {e}"
            self._logger.error(error)
            return False, error

    def apply_gaming_profile(
        self,
        power_mode: str = "optimal",
        low_latency: str = "off",
        threaded_opt: str = "auto",
        vsync: str = "on",
        shader_cache: str = "on",
        fps_limit: int = 0,
        vrr_mode: str = "off",
        bg_app_fps: int = 0,
        aniso_sample_opt: str = "off",
        texture_lod_bias: str = "allow",
        ogl_thread_opt: str = "auto",
        cuda_force_p2: str = "off",
        triple_buffer: str = "off",
        max_prerendered: int = 3,
        vrr_app_override: str = "driver_default",
    ) -> tuple[bool, str | None]:
        """Create and apply an optimized gaming profile.

        Uses caching: only regenerates profile if settings changed.

        Args:
            power_mode: Power management mode.
            low_latency: Low latency mode setting.
            threaded_opt: Threaded optimization setting.
            vsync: VSync setting.
            shader_cache: Shader cache setting.
            fps_limit: FPS cap (0 = off, 30-500 = limit).
            vrr_mode: G-Sync/VRR mode (off, on, fullscreen).
            bg_app_fps: Background app FPS limit (0 = off, 20-60 = limit).
            aniso_sample_opt: Anisotropic sample optimization (off, on).
            texture_lod_bias: Texture LOD bias (allow, clamp).
            ogl_thread_opt: OpenGL threading optimization (off, on, auto).
            cuda_force_p2: CUDA force P2 state (off, on).
            triple_buffer: Triple buffering (off, on).
            max_prerendered: Max pre-rendered frames (1-4).
            vrr_app_override: G-Sync app override (off, driver_default, force_on).

        Returns:
            Tuple of (success, error_message). error_message is None on success.
        """
        try:
            # Create profile hash to check if regeneration needed
            settings_key = (
                f"{power_mode}:{low_latency}:{threaded_opt}:{vsync}:{shader_cache}:"
                f"{fps_limit}:{vrr_mode}:{bg_app_fps}:{aniso_sample_opt}:"
                f"{texture_lod_bias}:{ogl_thread_opt}:{cuda_force_p2}:"
                f"{triple_buffer}:{max_prerendered}:{vrr_app_override}"
            )
            cache_marker = self._profiles_dir / ".last_settings"

            # Check if profile already exists with same settings
            profile_path = self._profiles_dir / "fpstune_gaming.nip"
            if profile_path.exists() and cache_marker.exists():
                cached_key = cache_marker.read_text(encoding="utf-8").strip()
                if cached_key == settings_key:
                    self._logger.debug("Using cached NVIDIA profile (settings unchanged)")
                    success, error = self.apply_profile(profile_path)
                    if not success:
                        # Clear cache marker on failure to force regeneration next time
                        cache_marker.unlink(missing_ok=True)
                        self._logger.warning(
                            "NPI apply failed with cached profile, cleared cache marker"
                        )
                    return success, error

            # Generate new profile
            self._logger.info("Generating new NVIDIA profile...")
            profile = NvidiaProfile(
                name="fpstune_gaming",
                power_mode=power_mode,
                low_latency=low_latency,
                threaded_opt=threaded_opt,
                vsync=vsync,
                shader_cache=shader_cache,
                texture_quality="performance",
                triple_buffer=triple_buffer,
                fps_limit=fps_limit,
                bg_app_fps=bg_app_fps,
                vrr_mode=vrr_mode,
                aniso_sample_opt=aniso_sample_opt,
                texture_lod_bias=texture_lod_bias,
                ogl_thread_opt=ogl_thread_opt,
                cuda_force_p2=cuda_force_p2,
                max_prerendered=max_prerendered,
                vrr_app_override=vrr_app_override,
            )

            profile_path = self.save_profile(profile)

            success, error = self.apply_profile(profile_path)

            if success:
                # Save settings key for cache check only on success
                cache_marker.write_text(settings_key, encoding="utf-8")
            else:
                # Clear cache marker on failure
                cache_marker.unlink(missing_ok=True)
                self._logger.warning("NPI apply failed, not saving cache marker")

            return success, error

        except Exception as e:
            error = f"Failed to create/apply NVIDIA profile: {e}"
            self._logger.error(error)
            return False, error

    def get_profiles_dir(self) -> Path:
        """Get the profiles directory."""
        return self._profiles_dir

    def list_saved_profiles(self) -> list[Path]:
        """List all saved .nip profiles."""
        return list(self._profiles_dir.glob("*.nip"))

    def read_applied_settings(self) -> dict[str, Any] | None:
        """Read settings from the last applied fpstune profile.

        Parses the saved .nip XML file to extract current setting values.

        Returns:
            Dict of setting_name -> value, or None if no profile found.
        """
        profile_path = self._profiles_dir / "fpstune_gaming.nip"
        if not profile_path.exists():
            return None

        try:
            # Read UTF-16 encoded XML
            with open(profile_path, encoding="utf-16") as f:
                content = f.read()

            root = ET.fromstring(content)

            # Parse settings from XML
            settings: dict[str, Any] = {}

            # Reverse maps: value -> name
            power_values = {
                NvApiSettings.POWER_OPTIMAL: "optimal",
                NvApiSettings.POWER_ADAPTIVE: "adaptive",
                NvApiSettings.POWER_PREFER_MAX: "maximum",
                NvApiSettings.POWER_CONSISTENT_PERFORMANCE: "consistent",
            }
            latency_values = {
                NvApiSettings.LATENCY_OFF: "off",
                NvApiSettings.LATENCY_ON: "on",
                NvApiSettings.LATENCY_ULTRA: "ultra",
            }
            threaded_values = {
                NvApiSettings.THREADED_OFF: "off",
                NvApiSettings.THREADED_ON: "on",
                NvApiSettings.THREADED_AUTO: "auto",
            }
            vsync_values = {
                NvApiSettings.VSYNC_OFF: "off",
                NvApiSettings.VSYNC_ON: "on",
                NvApiSettings.VSYNC_ADAPTIVE: "adaptive",
            }
            shader_values = {
                NvApiSettings.SHADER_CACHE_OFF: "off",
                NvApiSettings.SHADER_CACHE_ON: "on",
            }
            texture_values = {
                NvApiSettings.TEXTURE_HIGH_QUALITY: "high_quality",
                NvApiSettings.TEXTURE_QUALITY_DEFAULT: "quality",
                NvApiSettings.TEXTURE_PERFORMANCE: "performance",
                NvApiSettings.TEXTURE_HIGH_PERFORMANCE: "high_performance",
            }
            triple_buffer_values = {
                NvApiSettings.TRIPLE_BUFFER_OFF: "off",
                NvApiSettings.TRIPLE_BUFFER_ON: "on",
            }
            vrr_mode_values = {
                NvApiSettings.VRR_OFF: "off",
                NvApiSettings.VRR_ON: "on",
                NvApiSettings.VRR_FULLSCREEN: "fullscreen",
            }
            aniso_sample_opt_values = {
                NvApiSettings.ANISO_SAMPLE_OPT_OFF: "off",
                NvApiSettings.ANISO_SAMPLE_OPT_ON: "on",
            }
            texture_lod_bias_values = {
                NvApiSettings.TEXTURE_LOD_ALLOW: "allow",
                NvApiSettings.TEXTURE_LOD_CLAMP: "clamp",
            }
            ogl_thread_values = {
                NvApiSettings.OGL_THREAD_AUTO: "auto",
                NvApiSettings.OGL_THREAD_ON: "on",
                NvApiSettings.OGL_THREAD_OFF: "off",
            }
            cuda_p2_values = {
                NvApiSettings.CUDA_P2_OFF: "off",
                NvApiSettings.CUDA_P2_ON: "on",
            }
            vrr_app_override_values = {
                NvApiSettings.VRR_APP_DRIVER: "driver_default",
                NvApiSettings.VRR_APP_ON: "force_on",
                NvApiSettings.VRR_APP_OFF: "off",
            }

            # Find all ProfileSetting elements
            for setting_elem in root.findall(".//ProfileSetting"):
                setting_id_elem = setting_elem.find("SettingID")
                setting_value_elem = setting_elem.find("SettingValue")

                if setting_id_elem is None or setting_value_elem is None:
                    continue

                # NIP stores values as decimal (not hex)
                try:
                    setting_id = int(setting_id_elem.text or "0")
                    setting_value = int(setting_value_elem.text or "0")
                except ValueError:
                    continue

                # Map to human-readable names
                if setting_id == NvApiSettings.POWER_MANAGEMENT_MODE:
                    settings["power_mode"] = power_values.get(setting_value, "unknown")
                elif setting_id == NvApiSettings.LOW_LATENCY_MODE:
                    settings["low_latency"] = latency_values.get(setting_value, "unknown")
                elif setting_id == NvApiSettings.THREADED_OPTIMIZATION:
                    settings["threaded_opt"] = threaded_values.get(setting_value, "unknown")
                elif setting_id == NvApiSettings.VSYNC_MODE:
                    settings["vsync"] = vsync_values.get(setting_value, "unknown")
                elif setting_id == NvApiSettings.SHADER_CACHE:
                    settings["shader_cache"] = shader_values.get(setting_value, "unknown")
                elif setting_id == NvApiSettings.TEXTURE_QUALITY:
                    settings["texture_quality"] = texture_values.get(setting_value, "unknown")
                elif setting_id == NvApiSettings.TRIPLE_BUFFER:
                    settings["triple_buffer"] = triple_buffer_values.get(setting_value, "unknown")
                elif setting_id == NvApiSettings.FRL_FPS:
                    settings["fps_limit"] = setting_value  # Raw FPS integer (0 = off)
                elif setting_id == NvApiSettings.VRR_MODE:
                    settings["vrr_mode"] = vrr_mode_values.get(setting_value, "unknown")
                elif setting_id == NvApiSettings.BG_APP_MAX_FPS:
                    settings["bg_app_fps"] = setting_value  # Raw FPS integer (0 = off)
                elif setting_id == NvApiSettings.ANISO_SAMPLE_OPT:
                    settings["aniso_sample_opt"] = aniso_sample_opt_values.get(
                        setting_value, "unknown"
                    )
                elif setting_id == NvApiSettings.TEXTURE_LOD_BIAS:
                    settings["texture_lod_bias"] = texture_lod_bias_values.get(
                        setting_value, "unknown"
                    )
                elif setting_id == NvApiSettings.OGL_THREAD_CONTROL:
                    settings["ogl_thread_opt"] = ogl_thread_values.get(setting_value, "unknown")
                elif setting_id == NvApiSettings.CUDA_FORCE_P2:
                    settings["cuda_force_p2"] = cuda_p2_values.get(setting_value, "unknown")
                elif setting_id == NvApiSettings.MAX_PRERENDERED_FRAMES:
                    settings["max_prerendered"] = setting_value  # Raw integer (1-4)
                elif setting_id == NvApiSettings.VRR_APP_OVERRIDE:
                    settings["vrr_app_override"] = vrr_app_override_values.get(
                        setting_value, "unknown"
                    )

            return settings if settings else None

        except Exception as e:
            self._logger.debug(f"Failed to read profile: {e}")
            return None
