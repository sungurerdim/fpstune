"""Base classes for the setting-based architecture."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class SettingCategory(StrEnum):
    """Setting categories for grouping."""

    CORE = "core"  # Priority settings
    TIMER = "timer"  # System-wide timer resolution
    POWER = "power"  # Power plan, USB, PCIe, WLAN
    NETWORK = "network"  # TCP, adapter settings
    GPU = "gpu"  # NVIDIA, AMD
    VISUAL = "visual"  # Animations, transparency
    STORAGE = "storage"  # TRIM, NTFS
    SYSTEM = "system"  # Services, memory
    MAINTENANCE = "maintenance"  # Cleanup, flush
    GAME = "game"  # Game Mode, Game Bar, Xbox
    AUDIO = "audio"  # Audio latency settings
    LAUNCHER = "launcher"  # Steam and Battle.net settings
    GAME_CONFIG = "game_config"  # Game-specific config file tweaks (CS2, MW3)


@dataclass(frozen=True)
class CategoryMetadata:
    """Rich metadata for setting categories - Single Source of Truth for UI.

    All category display information is defined here and sent to frontend.
    Frontend should never hardcode category names, icons, or colors.
    """

    id: str  # Matches SettingCategory value: "timer", "power", etc.
    display_name: str  # "Timer & Latency"
    description: str  # "System timer and latency optimizations..."
    icon: str  # Lucide icon name: "Clock", "Zap", "Wifi"
    color: str  # Tailwind color class: "text-yellow-500"
    order: int  # Sort order for UI (1 = first)
    is_action_only: bool = False  # True for categories shown in Maintenance tab only

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "display_name": self.display_name,
            "description": self.description,
            "icon": self.icon,
            "color": self.color,
            "order": self.order,
            "is_action_only": self.is_action_only,
        }


# Central registry - SSOT for category UI metadata
# Ordered by impact: highest to lowest gaming performance impact
CATEGORY_METADATA: dict[str, CategoryMetadata] = {
    "core": CategoryMetadata(
        id="core",
        display_name="Core Performance",
        description="Essential CPU priority and memory settings for maximum FPS",
        icon="Cpu",
        color="text-red-500",
        order=1,  # Highest impact: CPU/memory fundamentals
    ),
    "timer": CategoryMetadata(
        id="timer",
        display_name="Timer & Latency",
        description="System timer and input latency optimizations",
        icon="Clock",
        color="text-orange-500",
        order=2,  # Input latency crucial for competitive gaming
    ),
    "gpu": CategoryMetadata(
        id="gpu",
        display_name="GPU Optimization",
        description="Graphics card specific settings",
        icon="MonitorPlay",
        color="text-green-500",
        order=3,  # Direct FPS impact
    ),
    "power": CategoryMetadata(
        id="power",
        display_name="Power Management",
        description="Power plan, USB, and PCIe power settings",
        icon="Zap",
        color="text-yellow-500",
        order=4,  # Power plan affects CPU/GPU performance
    ),
    "game": CategoryMetadata(
        id="game",
        display_name="Game Mode",
        description="Windows Game Bar and Game Mode settings",
        icon="Gamepad2",
        color="text-indigo-500",
        order=5,  # Game-specific Windows settings
    ),
    "network": CategoryMetadata(
        id="network",
        display_name="Network",
        description="TCP/IP and network adapter optimizations",
        icon="Wifi",
        color="text-blue-500",
        order=6,  # Important for online games
    ),
    "system": CategoryMetadata(
        id="system",
        display_name="System Tuning",
        description="Services and background process settings",
        icon="Settings",
        color="text-gray-500",
        order=7,  # Background processes
    ),
    "visual": CategoryMetadata(
        id="visual",
        display_name="Visual Effects",
        description="Windows animations and transparency settings",
        icon="Palette",
        color="text-purple-500",
        order=8,  # UI effects
    ),
    "storage": CategoryMetadata(
        id="storage",
        display_name="Storage",
        description="Disk and file system optimizations",
        icon="HardDrive",
        color="text-cyan-500",
        order=9,  # Disk optimizations
    ),
    "audio": CategoryMetadata(
        id="audio",
        display_name="Audio",
        description="Audio latency and enhancement settings",
        icon="Volume2",
        color="text-pink-500",
        order=10,  # Audio latency
    ),
    "maintenance": CategoryMetadata(
        id="maintenance",
        display_name="Maintenance",
        description="System cleanup and repair utilities",
        icon="Wrench",
        color="text-amber-500",
        order=11,  # Optional cleanup utilities
        is_action_only=True,
    ),
    "launcher": CategoryMetadata(
        id="launcher",
        display_name="Game Launchers",
        description="Steam and Battle.net optimization settings",
        icon="Gamepad2",
        color="text-sky-500",
        order=12,  # Game launcher tweaks
    ),
    "game_config": CategoryMetadata(
        id="game_config",
        display_name="Game Configs",
        description="In-game config file tweaks for CS2, MW3, and other FPS titles",
        icon="FileCode",
        color="text-emerald-500",
        order=13,  # Game-specific file tweaks
    ),
}


def get_all_categories_metadata() -> list[CategoryMetadata]:
    """Get all category metadata sorted by order."""
    return sorted(CATEGORY_METADATA.values(), key=lambda c: c.order)


@dataclass(frozen=True)
class ModuleMetadata:
    """Rich metadata for setting modules - Single Source of Truth for UI.

    Modules are sub-groupings within categories (e.g., "gpu-nvidia" within "gpu").
    Frontend should use this metadata instead of hardcoding display names.
    """

    id: str  # Module ID: "timer", "gpu-nvidia", "cleanup"
    display_name: str  # "Timer", "NVIDIA", "Cleanup"
    description: str  # Brief description
    order: int  # Sort order within category (1 = first)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "display_name": self.display_name,
            "description": self.description,
            "order": self.order,
        }


# The backend owns every module's display name, so the frontend renders what it
# is given rather than mapping an id to a word of its own. A module missing here
# still reaches the UI: the route auto-generates a fallback entry, which is why
# an unlisted module degrades to a plain title instead of disappearing.
MODULE_METADATA: dict[str, ModuleMetadata] = {
    # Core category
    "priority": ModuleMetadata(
        id="priority",
        display_name="Priority",
        description="GPU priority, system responsiveness",
        order=1,
    ),
    "memory": ModuleMetadata(
        id="memory",
        display_name="Memory",
        description="Memory management, standby list",
        order=2,
    ),
    # Timer category
    "timer": ModuleMetadata(
        id="timer",
        display_name="Timer",
        description="System-wide timer resolution",
        order=1,
    ),
    # Power category
    "power": ModuleMetadata(
        id="power",
        display_name="Power",
        description="USB suspend, PCIe power, WLAN",
        order=1,
    ),
    # Network category
    "network": ModuleMetadata(
        id="network",
        display_name="Network",
        description="TCP settings, DNS, throttling",
        order=1,
    ),
    # GPU category
    "gpu-nvidia": ModuleMetadata(
        id="gpu-nvidia",
        display_name="NVIDIA",
        description="NVIDIA driver settings",
        order=1,
    ),
    "gpu-amd": ModuleMetadata(
        id="gpu-amd",
        display_name="AMD",
        description="AMD driver settings",
        order=2,
    ),
    "gpu-hardware": ModuleMetadata(
        id="gpu-hardware",
        display_name="GPU Hardware",
        description="Resizable BAR, GPU assignment, thermals",
        order=3,
    ),
    # Visual category
    "visual": ModuleMetadata(
        id="visual",
        display_name="Visual Effects",
        description="Animations, transparency, effects",
        order=1,
    ),
    # Storage category
    "storage": ModuleMetadata(
        id="storage",
        display_name="Storage",
        description="TRIM, 8.3 names, last access",
        order=1,
    ),
    # Display category
    "display": ModuleMetadata(
        id="display",
        display_name="Display",
        description="Resolution, refresh rate, windowed optimization",
        order=1,
    ),
    # System category
    "system": ModuleMetadata(
        id="system",
        display_name="System",
        description="VBS, core isolation",
        order=4,
    ),
    "services": ModuleMetadata(
        id="services",
        display_name="Services",
        description="Background services, telemetry",
        order=1,
    ),
    "privacy": ModuleMetadata(
        id="privacy",
        display_name="Privacy",
        description="Telemetry, advertising, Cortana, speech, app tracking",
        order=2,
    ),
    "perf": ModuleMetadata(
        id="perf",
        display_name="Performance",
        description="Startup, menu delay, mouse",
        order=3,
    ),
    # Game category
    "game": ModuleMetadata(
        id="game",
        display_name="Game Mode",
        description="Game Mode, Game Bar, HAGS",
        order=1,
    ),
    # Audio category
    "audio": ModuleMetadata(
        id="audio",
        display_name="Audio",
        description="Latency, enhancements, volume",
        order=1,
    ),
    # Maintenance category
    "cleanup": ModuleMetadata(
        id="cleanup",
        display_name="Cleanup",
        description="Temp files, update caches, crash dumps, browser/app caches, dev tool caches",
        order=1,
    ),
    "maintenance": ModuleMetadata(
        id="maintenance",
        display_name="Maintenance",
        description="SFC, DISM health checks",
        order=2,
    ),
    "game_cleanup": ModuleMetadata(
        id="game_cleanup",
        display_name="Game & Launcher Cleanup",
        description="Shader caches, launcher caches and crash dumps left behind by games, "
        "their launchers and the graphics driver. A shader cache that survived a driver "
        "update causes launch crashes and stutter until it is rebuilt, and the dumps are "
        "diagnostics for crashes that are already over.",
        order=3,
    ),
    # Launcher category
    "launcher": ModuleMetadata(
        id="launcher",
        display_name="Launchers",
        description="Steam, Battle.net optimization settings",
        order=1,
    ),
    # Game config category
    "game_config": ModuleMetadata(
        id="game_config",
        display_name="Game Configs",
        description="CS2, MW3, and other FPS title config tweaks",
        order=1,
    ),
}


def get_all_modules_metadata() -> list[ModuleMetadata]:
    """Get all module metadata sorted by order."""
    return sorted(MODULE_METADATA.values(), key=lambda m: m.order)


class SettingScope(StrEnum):
    """Optimization scope for settings - used by profiles for dynamic filtering.

    Settings are categorized by their impact level, not risk.
    Higher scope levels include more tweaks with diminishing returns.

    ESSENTIAL: Highest impact, proven optimizations. Must-have for any gamer.
              Examples: Global Timer Resolution, Low Latency Mode, Nagle disable
    RECOMMENDED: Noticeable benefits, good additions to essentials.
                 Examples: USB Selective Suspend, Priority settings, VSync off
    COMPLETE: All tweaks including minor improvements.
              Examples: Visual effects, minor service disables, audio tweaks
    """

    ESSENTIAL = "essential"  # ~10 core tweaks with highest measurable impact
    RECOMMENDED = "recommended"  # ~25 additional tweaks with noticeable benefits
    COMPLETE = "complete"  # ~30 remaining tweaks for completeness


class SettingValueType(StrEnum):
    """Value types for settings."""

    CHOICE = "choice"  # Predefined options
    BOOL = "bool"  # True/False
    INT = "int"  # Integer
    FLOAT = "float"  # Decimal
    STRING = "string"  # Free text


class DetectType(StrEnum):
    """Detection/Apply command types."""

    POWERCFG = "powercfg"  # powercfg.exe commands
    BCDEDIT = "bcdedit"  # bcdedit.exe commands
    REGISTRY = "registry"  # Windows Registry
    POWERSHELL = "powershell"  # PowerShell commands
    NETSH = "netsh"  # netsh.exe commands
    NVPROFILE = "nvprofile"  # NVIDIA Profile Inspector


class _ValueMapRule:
    """A reserved key in ``value_map``: a rule about the reading, not a reading.

    ``value_map`` already had one reserved key — ``None``, meaning "the value is
    absent". These add the two rules a lookup table cannot express, and they
    live in the same dict for the same reason: one place declares how a raw
    reading becomes a display value, and one function honours it for every
    executor. A field on the setting would have had to be threaded through
    thirteen call sites, and any executor that forgot it would silently ignore
    the rule.

    Identity-based so it can never collide with a value a driver reports.
    """

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return f"<{self._name}>"


# Bitmask applied to a numeric reading before lookup. For a value that packs
# several flags into one number, the table would otherwise have to enumerate
# every combination — and would be wrong for the first one it missed.
#   perf:numlock_default reads InitialKeyboardIndicators, where bit 0x2 is
#   Num Lock and 0x80000000 means "restore the previous state". The old table
#   listed 2 and 2147483650 as "on" and nothing else, so 2147483648 (the high
#   bit with Num Lock clear) reached the UI as a bare number outside `choices`
#   and could never verify.
MASK = _ValueMapRule("MASK")

# Display value for any reading the table does not cover. For a setting whose
# raw value is a threshold or a free number rather than an enum, only the
# interesting values can be listed and everything else means the same thing.
#   perf:svchost_split_threshold reads SvcHostSplitThresholdInKB. 0xFFFFFFFF
#   means "combine every service"; every other number is whatever Windows sized
#   to this machine's RAM, so it means "split". The table listed only
#   0xFFFFFFFF, so a real reading of 3774873 KB surfaced as itself.
#
# An absent reading (`not_supported` and friends) is never swallowed by this —
# absence is not an unmapped value, and collapsing it would hide hardware that
# genuinely lacks the feature behind a plausible-looking default.
UNMAPPED = _ValueMapRule("UNMAPPED")


@dataclass
class SettingExecutor:
    """Self-contained setting definition with string-based commands.

    Each setting knows how to detect its current value and apply a new value.
    Commands are string templates with {placeholder} syntax.

    Example:
        USB_SELECTIVE_SUSPEND = SettingExecutor(
            id="power:usb_selective_suspend",
            category=SettingCategory.POWER,
            display_name="USB Selective Suspend",
            ...
            detect_type=DetectType.POWERCFG,
            detect_command="/getacvalueindex {scheme} {subgroup} {setting}",
            detect_args={"subgroup": "...", "setting": "..."},
            value_map={0: "disabled", 1: "enabled"},
            ...
        )
    """

    # === Identity ===
    id: str  # Unique ID: "power:usb_selective_suspend" or "network:eth0:interrupt_moderation"
    category: SettingCategory

    # === Metadata ===
    display_name: str
    description: str
    value_type: SettingValueType = SettingValueType.CHOICE
    choices: tuple[str, ...] = ()
    default_value: Any = None
    recommended_value: Any = None
    requires_reboot: bool = False
    current_impact: str = ""
    recommended_impact: str = ""
    is_action: bool = False  # True for one-time operations (TRIM, flush DNS)
    # Evidence level: "proven" (3+ sources, measured), "likely" (1-2 sources),
    # "experimental" (anecdotal, harmless but unproven)
    evidence_level: str = "likely"

    # === Risk Taxonomy ===
    risk_level: Literal["safe", "low", "moderate", "advanced"] = "low"
    # Required when risk_level="advanced"; shown as a warning badge in the UI
    risk_warning: str | None = None

    # === Scope ===
    scope: SettingScope = SettingScope.RECOMMENDED  # Optimization scope for filtering
    # Consequence 5's line between information and decoration, carried as data:
    # non-None means this setting changes what the player can see or hear, and
    # the string says what is lost, in words the player reads before agreeing.
    # Such a setting may only live in COMPLETE — offered, never assumed — and
    # the scope/impact coherence gate enforces exactly that.
    perceptible_cost: str | None = None

    # === Detection (String-based) ===
    detect_type: DetectType = DetectType.REGISTRY
    detect_command: str = ""  # Command template with {placeholders}
    detect_args: dict[str, Any] = field(default_factory=dict)  # Static args
    value_map: dict[Any, Any] = field(default_factory=dict)  # Raw → display value

    # === Apply (String-based) ===
    apply_type: DetectType = DetectType.REGISTRY
    apply_command: str = ""  # Command template
    apply_args: dict[str, Any] = field(default_factory=dict)
    apply_value_map: dict[Any, Any] = field(default_factory=dict)  # Display → raw value

    # === Per-setting timeout overrides (seconds) ===
    # When None, the executor uses its own heuristic / default. Set this for
    # known-slow detections (e.g., WMI queries) to prevent a hung command from
    # blocking a parallel-detection slot for the executor's full default.
    detect_timeout: int | None = None
    apply_timeout: int | None = None

    # === Validation ===
    validate_pattern: str | None = None  # Regex for validation
    min_value: int | float | None = None  # Minimum value for INT/FLOAT types
    max_value: int | float | None = None  # Maximum value for INT/FLOAT types

    # === Applicability System ===
    # Conditions that must be met for this setting to be applicable
    # Examples: {"gpu_vendor": "nvidia"}, {"min_windows_build": 22000}
    applicable_conditions: dict[str, Any] = field(default_factory=dict)
    # Human-readable reason when not applicable (set at runtime)
    applicable_reason: str = ""

    # === Display ===
    short_name: str = ""  # Optional abbreviated name for compact UI
    icon: str = ""  # Lucide icon name for UI (e.g., "Clock", "Zap")
    color: str = ""  # Tailwind color class (e.g., "text-yellow-500")
    category_order: int = 0  # Sort order within category (0 = use definition order)

    # === Effect (Combined Impact) ===
    effect: str = ""  # Summary: "Reduces input latency by 0.1-0.5ms"
    impact_scores: dict[str, str | float] = field(default_factory=dict)
    # Example: {"fps": "+3%", "latency_ms": -0.5, "stability": "high"}

    # === Research Sources ===
    sources: list[str] = field(default_factory=list)
    # URLs to research/benchmarks backing this setting's evidence_level

    # === Read-only (advisory) ===
    # True for detect-only settings that can't be changed programmatically
    # (e.g., fan curves requiring NVIDIA Control Panel, BIOS-level features)
    is_readonly: bool = False

    # === Value Hints ===
    # Optional display hints shown next to choice labels in the UI (e.g. "enabled (1)")
    # If empty, hints are auto-derived from apply_value_map when raw != display label
    value_hints: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate setting definition."""
        if not self.id:
            raise ValueError("Setting ID is required")
        if ":" not in self.id:
            raise ValueError(f"Setting ID must contain ':' separator: {self.id}")
        if not self.display_name or not self.display_name.strip():
            raise ValueError(f"Setting display_name must not be empty: {self.id}")
        if self.value_type == SettingValueType.CHOICE and not self.choices:
            raise ValueError(f"CHOICE type requires non-empty choices tuple: {self.id}")

    @property
    def module(self) -> str:
        """Extract module name from ID (e.g., 'power' from 'power:usb_selective_suspend')."""
        return self.id.split(":")[0]

    @property
    def name(self) -> str:
        """Extract setting name from ID (e.g., 'usb_selective_suspend')."""
        parts = self.id.split(":")
        return ":".join(parts[1:])  # Handle "network:eth0:interrupt_moderation"

    @property
    def is_service(self) -> bool:
        """True for Windows-service settings, whose IDs are prefixed 'services:'."""
        return self.id.startswith("services:")

    def _derive_value_hints(self) -> dict[str, str]:
        """Derive UI value hints from apply_value_map.

        Returns explicitly set value_hints if provided, otherwise auto-generates
        hints from apply_value_map for entries where raw value differs from display label.
        """
        if self.value_hints:
            return self.value_hints
        hints: dict[str, str] = {}
        for display, raw in self.apply_value_map.items():
            if display is None or raw is None:
                continue
            raw_str = str(raw)
            if raw_str != str(display):
                hints[str(display)] = raw_str
        return hints

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "module": self.module,
            "name": self.name,
            "category": self.category.value,
            "display_name": self.display_name,
            "description": self.description,
            "value_type": self.value_type.value,
            "choices": list(self.choices),
            "default_value": self.default_value,
            "recommended_value": self.recommended_value,
            "requires_reboot": self.requires_reboot,
            "current_impact": self.current_impact,
            "recommended_impact": self.recommended_impact,
            "is_action": self.is_action,
            "scope": self.scope.value,
            "short_name": self.short_name,
            "icon": self.icon,
            "color": self.color,
            "category_order": self.category_order,
            "applicable_conditions": self.applicable_conditions,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "effect": self.effect,
            "impact_scores": self.impact_scores,
            "is_readonly": self.is_readonly,
            "value_hints": self._derive_value_hints(),
        }


@dataclass
class DetectionResult:
    """Result of detecting a single setting's value."""

    setting_id: str
    value: Any | None  # None if detection failed
    error: str | None  # Error message if detection failed
    time_ms: int  # Detection time in milliseconds
    is_optimized: bool = False  # True if current value == recommended value
    is_applicable: bool = True  # False if setting doesn't apply to this hardware
    applicable_reason: str = ""  # Human-readable reason when not applicable

    @property
    def success(self) -> bool:
        """True if detection succeeded (value is not None and no error)."""
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "setting_id": self.setting_id,
            "value": self.value,
            "error": self.error,
            "time_ms": self.time_ms,
            "success": self.success,
            "is_optimized": self.is_optimized,
            "is_applicable": self.is_applicable,
            "applicable_reason": self.applicable_reason,
        }


@dataclass
class MaintenanceExecutor(SettingExecutor):
    """Extended executor for maintenance actions with streaming support.

    Inherits all SettingExecutor fields and adds maintenance-specific ones.
    All instances have is_action=True by design.

    Example:
        DISM_CLEANUP = MaintenanceExecutor(
            id="maintenance:dism_cleanup",
            category=SettingCategory.MAINTENANCE,
            display_name="DISM Cleanup",
            description="Cleans Windows component store...",
            duration_estimate="5-15 min",
            supports_streaming=True,
            progress_pattern=r"(\\d+\\.?\\d*)%",
            ...
        )
    """

    # === Maintenance-specific ===
    duration_estimate: str = ""  # "~30s", "1-5 min", "5-15 min"
    supports_streaming: bool = True  # Enable live console output
    progress_pattern: str | None = None  # Regex to extract progress % from output

    def __post_init__(self) -> None:
        """Validate and ensure is_action=True for maintenance tasks."""
        # Call parent validation
        super().__post_init__()
        # Maintenance executors are always actions
        object.__setattr__(self, "is_action", True)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary including maintenance fields."""
        base = super().to_dict()
        base.update(
            {
                "duration_estimate": self.duration_estimate,
                "supports_streaming": self.supports_streaming,
                "progress_pattern": self.progress_pattern,
            }
        )
        return base
