"""Pydantic schemas for FastAPI API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from fpstune.utils.detect import MonitorInfo as DetectedMonitorInfo


# Hardware detection schemas
class CpuInfo(BaseModel):
    """CPU information."""

    name: str
    physical_cores: int
    logical_cores: int
    # The rated clock WMI reports. There is no boost field: WMI has no boost
    # figure, and a duplicate under another name is a claim nothing measured.
    base_clock_mhz: int | None = None
    architecture: str = ""  # x64, ARM64
    cache_l3_mb: int | None = None
    sockets: int = 1
    # P/E topology; is_hybrid None = could not be read (unknown, not "no")
    p_cores: int = 0
    e_cores: int = 0
    is_hybrid: bool | None = None


class MonitorInfo(BaseModel):
    """Monitor/display information."""

    name: str
    width: int
    height: int
    refresh_rate_hz: int | None = None
    is_primary: bool = False
    # Monitor brand/model from EDID (e.g., "ASUS VG27AQ1A", "Dell U2722D")
    friendly_name: str | None = None
    # Native values from EDID preferred timing (optimal settings)
    native_width: int | None = None
    native_height: int | None = None
    native_refresh_rate_hz: int | None = None  # From EDID DTD
    # Maximum values from EnumDisplaySettings (may include OC modes)
    max_refresh_rate_hz: int | None = None
    # Detection status flags for frontend
    is_resolution_known: bool = True
    is_refresh_known: bool = True
    # Optimal status (computed from current vs native)
    is_resolution_optimal: bool = False
    is_refresh_optimal: bool = False
    # VRR (G-Sync/FreeSync) support — the EDID's declaration, tri-state.
    # None means the EDID could not be read: unknown, not "no".
    supports_vrr: bool | None = None
    # Is display active (attached to desktop) or disconnected. The UI renders a
    # "Disconnected" badge from this, so dropping it made a detached monitor
    # look live until the next refresh.
    is_active: bool = True
    # Hardware ID from EDID (e.g., "DEL4265") — the C5 stable identifier
    hardware_id: str | None = None

    @classmethod
    def from_detected(cls, mon: DetectedMonitorInfo) -> MonitorInfo:
        """Build the API payload from a detected monitor.

        The one serializer for every endpoint that returns monitors: /api/hardware
        and /display/* each had their own mapping and they disagreed on which
        fields exist. Unknown numeric values become None (0 means "not detected"
        in the dataclass); the known/optimal flags come from the dataclass
        properties so the logic is never restated here.
        """
        return cls(
            name=mon.name,
            width=mon.width,
            height=mon.height,
            refresh_rate_hz=mon.refresh_rate_hz or None,
            is_primary=mon.is_primary,
            friendly_name=mon.friendly_name or None,
            native_width=mon.native_width or None,
            native_height=mon.native_height or None,
            native_refresh_rate_hz=mon.native_refresh_rate_hz or None,
            max_refresh_rate_hz=mon.max_refresh_rate_hz or None,
            is_resolution_known=mon.is_resolution_known,
            is_refresh_known=mon.is_refresh_known,
            is_resolution_optimal=mon.is_resolution_optimal,
            is_refresh_optimal=mon.is_refresh_optimal,
            supports_vrr=mon.supports_vrr,
            is_active=mon.is_active,
            hardware_id=mon.hardware_id or None,
        )


class NetworkAdapterInfo(BaseModel):
    """Network adapter information.

    This is the most identifying payload the API returns — MAC address, IPv4 and
    IPv6 addresses, gateway, DNS servers, SSID and the PnP ``instance_id`` — and
    ``GET /api/hardware`` serves it with no authentication of any kind. What
    keeps that harmless is the loopback Host assertion and the cross-origin
    write refusal in ``api/main.py``: without them a page in a browser on this
    machine, or a name rebound to 127.0.0.1, could read the lot.

    Every field here is rendered by ``NetworkAdapterCard.tsx`` except
    ``ipv6_address``, which the frontend declares in its type and never shows —
    so the guard is the control, not the payload. Relaxing that guard means
    re-reading this docstring first.
    """

    name: str
    description: str
    adapter_type: str  # Ethernet, WiFi
    status: str  # Up, Down, Disconnected, Disabled
    is_enabled: bool = True  # Admin status: whether adapter is enabled
    is_connected: bool = False  # Media status: whether cable/signal connected
    mac_address: str | None = None
    speed_mbps: int | None = None
    ipv4_address: str | None = None
    ipv6_address: str | None = None
    gateway: str | None = None
    dns_servers: list[str] = []
    # System identifiers (for API operations - use these instead of name)
    interface_index: int | None = None  # NetAdapter InterfaceIndex (for active adapters)
    instance_id: str | None = None  # PnpDevice InstanceId (for all adapters, including disabled)
    # WiFi-specific fields
    ssid: str | None = None
    channel: int | None = None
    frequency_ghz: float | None = None
    radio_type: str | None = None  # 802.11ac, 802.11ax (WiFi 6), etc.
    signal_percent: int | None = None
    auth_type: str | None = None  # WPA2-Personal, WPA3, etc.


class StorageDriveInfo(BaseModel):
    """Storage drive information."""

    drive_letter: str
    model: str
    media_type: str  # SSD, HDD
    size_gb: int
    free_gb: int | None = None
    # None: not an SSD, or the registry could not be read — never shown as off.
    trim_enabled: bool | None = None
    bus_type: str | None = None  # NVMe, SATA, etc.
    unique_id: str = ""  # EUI-64 for NVMe, serial for SATA (hardware-stable ID)


class AudioDeviceInfo(BaseModel):
    """Audio device information."""

    id: str  # Device GUID from registry
    name: str  # Friendly name: "Speakers (Realtek)", "SteelSeries Engine"
    device_type: str  # Playback, Recording
    is_default: bool = False
    is_enabled: bool = True
    driver: str | None = None
    loudness_eq_supported: bool = False  # Whether device supports volume normalization
    loudness_eq_enabled: bool = False  # Current state of volume normalization


class GpuDeviceInfo(BaseModel):
    """GPU device information."""

    vendor: str
    name: str | None = None
    driver: str | None = None
    driver_date: str | None = None  # ISO date: "2024-12-15"
    vram_mb: int | None = None
    pcie_generation: int | None = None
    pcie_lanes: int | None = None


class HardwareInfo(BaseModel):
    """All detected hardware."""

    cpu: CpuInfo | None = None
    gpus: list[GpuDeviceInfo] = []
    monitors: list[MonitorInfo] = []
    network_adapters: list[NetworkAdapterInfo] = []
    storage_drives: list[StorageDriveInfo] = []
    audio_devices: list[AudioDeviceInfo] = []
    detecting: bool = False


class HardwareContextResponse(BaseModel):
    """Hardware context for applicability checks.

    This is used by frontend to understand which settings
    are applicable to the current system.
    """

    gpu_vendor: str | None = None  # Primary GPU vendor
    gpu_vendors: list[str] = []  # All detected GPU vendors
    gpu_name: str | None = None
    windows_build: int = 0
    windows_version: str = ""  # e.g., "24H2"
    is_windows_11: bool = False
    is_admin: bool = False


# System schemas
class GpuInfoResponse(BaseModel):
    """GPU information response."""

    vendor: str
    name: str | None = None
    driver: str | None = None
    vram_mb: int | None = None
    detecting: bool = False


class SystemInfo(BaseModel):
    """System information response."""

    os_platform: str
    os_version: str
    os_build: str
    os_edition: str
    os_display_version: str = ""  # e.g., "24H2", "23H2"
    is_supported: bool
    is_admin: bool
    cpu_name: str
    cpu_cores: int
    ram_total_mb: int
    ram_available_mb: int
    # GPU fields (may be null if still detecting)
    gpu_vendor: str = "unknown"
    gpu_name: str | None = None
    gpu_driver: str | None = None
    gpu_vram_mb: int | None = None
    gpu_detecting: bool = False


class GpuDetectResponse(BaseModel):
    """GPU detection response."""

    vendor: str
    name: str | None = None
    driver_version: str | None = None
    vram_mb: int | None = None


# Every literal below is one of the named setting's own ``choices``, and every
# default is that setting's ``recommended_value`` — because omitting a field on
# these endpoints means "apply what fpstune advises", not "apply whatever this
# model happened to be typed with". Both halves are held by
# ``tests/test_api/test_gpu_schema_matches_registry.py``, which reads the built
# registry rather than a second copy of these lists.
class GpuNvidiaApplyRequest(BaseModel):
    """NVIDIA GPU apply request."""

    low_latency: Literal["off", "on", "ultra"] = "on"
    power_mode: Literal["optimal", "adaptive", "maximum"] = "optimal"
    threaded_opt: Literal["off", "on", "auto"] = "auto"
    shader_cache: Literal["off", "on"] = "on"
    # The one field whose recommendation is derived from the panel rather than
    # declared: with VRR plus a frame cap the setting recommends "on", without
    # it "off". "off" is the fixed-refresh answer and the safe direction to be
    # wrong in (tearing, not latency); a caller on a VRR panel should send "on".
    vsync: Literal["off", "on", "adaptive"] = "off"


class GpuAmdApplyRequest(BaseModel):
    """AMD GPU apply request."""

    anti_lag: Literal["enabled", "disabled"] = "enabled"
    # No ``gpu-amd:anti_lag_2`` executor is registered (C10 symmetry gap, issue
    # #34), so this field has no choices to be checked against and the route
    # forwards it only when the caller sets it explicitly.
    anti_lag_2: Literal["off", "on", "auto"] = "auto"
    shader_cache: Literal["enabled", "disabled"] = "enabled"
    vsync: Literal["off", "on"] = "off"


# Safety schemas for the manifest-based backup/revert system were removed along
# with it; System Restore is the rollback path and its endpoint returns a plain
# dict.


# Benchmark schemas
class BenchmarkRunResponse(BaseModel):
    """Benchmark run response."""

    timestamp: str
    name: str
    metrics: dict[str, float]
    system_info: dict[str, str]


class BenchmarkCompareResponse(BaseModel):
    """Benchmark comparison response."""

    before: BenchmarkRunResponse
    after: BenchmarkRunResponse
    metrics: list[dict[str, Any]]
    summary: str


# Cleanup schemas
# Activity log
class ActivityLogEntry(BaseModel):
    """Activity log entry."""

    timestamp: str
    message: str
    level: str


class ActivityLogResponse(BaseModel):
    """Activity log response."""

    entries: list[ActivityLogEntry]


# FPS Benchmark schemas (PresentMon-based)
class FpsImprovements(BaseModel):
    """FPS improvement metrics."""

    fps_avg_percent: float
    fps_1_low_percent: float
    frametime_percent: float
    stutter_percent: float


# GPU Benchmark schemas (FurMark-based)
# Power profile schemas
# =============================================================================
# SettingExecutor (routes/settings.py) request/response models
# =============================================================================


class CategoryMetadataResponse(BaseModel):
    """Category metadata for frontend UI rendering."""

    id: str
    display_name: str
    description: str
    icon: str
    color: str
    order: int
    is_action_only: bool = False


class SettingDefinitionResponse(BaseModel):
    """Setting definition for frontend initialization."""

    id: str
    category: str
    display_name: str
    description: str
    value_type: str
    choices: list[str]
    default_value: Any
    recommended_value: Any
    requires_reboot: bool
    is_action: bool
    current_impact: str
    recommended_impact: str
    scope: str = "recommended"
    short_name: str = ""
    icon: str = ""
    color: str = ""
    category_order: int = 0
    min_value: int | float | None = None
    max_value: int | float | None = None
    applicable_conditions: dict[str, Any] = {}
    # Evidence level: "proven", "likely", "experimental"
    evidence_level: str = "likely"
    # Research sources (URLs)
    sources: list[str] = []
    # Effect field (combined summary + impact scores)
    effect: str = ""
    impact_scores: dict[str, str | float] = {}
    # Kind of gain this setting delivers ("latency", "fps", ...), derived from
    # impact_scores rather than stored, so it cannot drift from the metrics.
    impact_categories: list[str] = []
    # Risk taxonomy (added Phase 1)
    risk_level: str = "low"
    risk_warning: str | None = None
    # Non-None = this setting changes what the player can see or hear, and the
    # string says what is lost — the copy the two-button UI shows before
    # Absolute Max spends it (consequence 5; scope/impact coherence gate).
    perceptible_cost: str | None = None
    # True when recommended == default under values_equal — a drift guard
    # (consequence 2): it changes nothing on a stock machine and exists to put
    # back what another optimizer moved. Counted apart from real changes so no
    # surface promises work that will not happen. Computed here so the frontend
    # never re-implements the one comparison truth (C6).
    is_drift_guard: bool = False
    # What a long action tells the user while it runs: how long it takes, and how
    # to read its own progress out of its own output (None = it reports none, and
    # the UI shows elapsed time instead of a percentage nothing measured).
    duration_estimate: str = ""
    progress_pattern: str | None = None
    # Advisory/detect-only settings
    is_readonly: bool = False
    # UI hints showing raw values next to choice labels (e.g. "enabled" -> "1")
    value_hints: dict[str, str] = {}
    # Which group heads this setting inside the list that owns it (the game it
    # belongs to, the kind of cleanup it is). Null for a list with no groups.
    # The label ships from the backend so no screen has to spell a game's name.
    group_id: str | None = None
    group_label: str | None = None
    group_order: int | None = None


class ModuleMetadataResponse(BaseModel):
    """Module metadata for frontend UI rendering."""

    id: str
    display_name: str
    description: str
    order: int


class DetectionResultResponse(BaseModel):
    """Detection result for a single setting."""

    setting_id: str
    value: Any | None
    error: str | None
    time_ms: int
    success: bool
    is_optimized: bool = False
    is_applicable: bool = True
    applicable_reason: str = ""
    recommended_value: Any | None = None
    # The numbers behind an advisory's value, keyed by a `kind` the frontend
    # has a sentence for ("linked at 100 Mbps, adapter supports 2500 Mbps").
    # Read on this machine during this detect; None for an ordinary setting.
    finding: dict[str, Any] | None = None
    # What this machine held when fpstune first saw the setting. None means
    # nothing was recorded, so there is nothing to undo — which is a different
    # state from "the original happens to equal the current value", and the UI
    # has to be able to tell them apart to decide whether to offer the action.
    original_value: Any | None = None


class DetectRequest(BaseModel):
    """Request to detect multiple settings."""

    setting_ids: list[str] | None = Field(
        None, description="Specific settings to detect (None = all)"
    )
    category: str | None = Field(None, description="Detect all settings in category")


class DetectResponse(BaseModel):
    """Response with detection results."""

    results: dict[str, DetectionResultResponse]
    total_time_ms: int
    success_count: int
    error_count: int


class ApplyRequest(BaseModel):
    """Request to apply a setting value."""

    value: Any = Field(..., description="The value to apply")


class ApplyResponse(BaseModel):
    """Response after applying a setting."""

    setting_id: str
    success: bool
    error: str | None
    new_value: Any | None
    requires_reboot: bool
    skipped: bool = False  # True if setting was not applicable (not an error)
    # Verification outcome, kept distinct from `success` so a skipped check is
    # never reported as a passed one:
    #   True  — value was read back and matched the request
    #   False — value was read back and did not match (success is False too)
    #   None  — no check was possible (action, advisory/read-only, or not run)
    verified: bool | None = None


class BulkApplyRequest(BaseModel):
    """Request to apply multiple settings."""

    settings: dict[str, Any] = Field(..., description="Map of setting_id to value")


class BulkApplyResponse(BaseModel):
    """Response after applying multiple settings."""

    results: dict[str, ApplyResponse]
    success_count: int
    error_count: int
    requires_reboot: bool


class BulkResetRequest(BaseModel):
    """Request to reset multiple settings to default."""

    setting_ids: list[str] = Field(..., description="Settings to reset to default")


class BulkStreamRequest(BaseModel):
    """Request for sequential SSE bulk operations."""

    ids: list[str] = Field(..., description="Setting IDs to process sequentially")


class VerifyRequest(BaseModel):
    """Which value to check a setting against."""

    # "recommended" — what fpstune advises (the drift check, and the default)
    # "default"     — the Windows stock value, i.e. "did a reset land"
    # "original"    — what fpstune first found here, i.e. "did an undo land"
    target: Literal["recommended", "default", "original"] = "recommended"


class VerifyResponse(BaseModel):
    """Response after verifying a setting's current state."""

    setting_id: str
    matches: bool  # True if current value equals expected_value
    current_value: Any | None
    expected_value: Any | None
    # Which question was answered. Echoed back because this endpoint used to
    # answer only one and never said so, and a caller that assumed a different
    # one read a correct machine as a failed operation.
    target: Literal["recommended", "default", "original"] = "recommended"
    error: str | None = None
