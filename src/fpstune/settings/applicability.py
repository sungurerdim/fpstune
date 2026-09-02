"""Hardware context and applicability checking for settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor


# === Absent readings =========================================================
#
# A detect command answers one of these when the thing it reads does not exist
# on this machine: the driver has no such keyword, the service is not installed,
# the game was never bought. That is not a value the setting can hold — it is
# the absence of the setting — and the only correct response is
# `is_applicable=False`, never a value shown in the UI.
#
# The spellings live here because they used to live everywhere. Each executor
# invented its own (`netsh.TCP_PROPERTY_MISSING`, `ps_batch.ADAPTER_PROPERTY_MISSING`,
# `game_config_cache.NOT_INSTALLED`) and `detection.py` carried a hand-written
# tuple that happened to list three of the four. The one it missed —
# `not_installed` — reached the UI as a literal value on every machine without
# the game, which the frontend then patched back to "not applicable" in three
# separate places. That is the loop this constant closes: one spelling set, one
# decision, made once on the backend.
ABSENT_READINGS: frozenset[str] = frozenset(
    {
        "not_supported",  # the driver/hardware has no such feature
        "not_found",  # the service or key does not exist
        "not_available",  # the subsystem cannot answer on this machine
        "not_installed",  # the software the setting configures is not installed
    }
)

# Named aliases, so an executor states which absence it means rather than
# spelling a bare string. All four are equivalent to the layer above.
NOT_SUPPORTED = "not_supported"
NOT_FOUND = "not_found"
NOT_AVAILABLE = "not_available"
NOT_INSTALLED = "not_installed"


def is_absent_reading(value: Any) -> bool:
    """Whether a detected value means "this does not exist here".

    Compares case-insensitively and after stripping, because these arrive from
    PowerShell stdout as often as from a Python constant, and a trailing CRLF
    would otherwise make a sentinel read as an ordinary value — the same
    cross-type gap `values_equal` exists to close for comparisons.
    """
    return isinstance(value, str) and value.strip().lower() in ABSENT_READINGS


def absent_reason(setting: SettingExecutor | None = None) -> str:
    """The user-facing explanation that accompanies an absent reading."""
    if setting is not None and setting.is_service:
        return "Service not installed on this system"
    return "Feature not available on this system"


@dataclass
class HardwareContext:
    """Detected hardware context for applicability checks.

    This is evaluated once at startup and cached. Settings use this
    to determine if they are applicable to the current system.
    """

    # CPU information
    cpu_vendor: str | None = None  # "amd", "intel", None

    # GPU information
    gpu_vendor: str | None = None  # "nvidia", "amd", "intel", None
    gpu_vendors: list[str] = field(default_factory=list)  # All detected vendors
    gpu_name: str | None = None

    # Windows information
    windows_build: int = 0  # e.g., 22631 for Win11 23H2
    windows_version: str = ""  # e.g., "24H2", "23H2"
    is_windows_11: bool = False

    # System state
    is_admin: bool = False

    # Available features (detected at runtime)
    features: set[str] = field(default_factory=set)
    # Examples: "hyper_v", "wsl", "docker", "xbox_game_bar", "game_mode"

    # What a feature *is*, in words the person reading the reason understands.
    #
    # A feature key is an internal token, and it used to reach the user intact:
    # blocking `system:vm_platform` produced "Not recommended:
    # virtualization_in_use is installed (would break it)". There is nothing on
    # the machine called that, so the sentence names no consequence — the user
    # cannot tell whether it is protecting something they care about or
    # something they have never used.
    #
    # Populated only where a discoverer can say something concrete: the
    # virtualization probes fill this with "Docker Desktop, WSL (2
    # distributions)" because they found those by name. A key with no label
    # falls back to the key, which is what every other feature does today.
    feature_labels: dict[str, str] = field(default_factory=dict)

    # Monitor capabilities. None = the panels could not be read (or declared
    # nothing), which must never collapse into "no VRR panel" — the two produce
    # different applicability reasons.
    has_vrr_monitor: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "cpu_vendor": self.cpu_vendor,
            "gpu_vendor": self.gpu_vendor,
            "gpu_vendors": self.gpu_vendors,
            "gpu_name": self.gpu_name,
            "windows_build": self.windows_build,
            "windows_version": self.windows_version,
            "is_windows_11": self.is_windows_11,
            "is_admin": self.is_admin,
            "features": list(self.features),
            "feature_labels": dict(self.feature_labels),
            "has_vrr_monitor": self.has_vrr_monitor,
        }


class ApplicabilityChecker:
    """Evaluates setting applicability against hardware context.

    Condition types supported:
    - cpu_vendor: str - Must match detected CPU vendor ("amd", "intel")
    - gpu_vendor: str - Must match detected GPU vendor ("nvidia", "amd", "intel")
    - gpu_vendors: list[str] - Must match any of the listed vendors
    - min_windows_build: int - Windows build must be >= this value
    - max_windows_build: int - Windows build must be <= this value
    - is_windows_11: bool - Must be Windows 11
    - requires_admin: bool - Must be running as admin
    - feature: str - Feature must be available
    - feature_absent: str - Feature must NOT be present (e.g., "docker" absent = safe to disable Hyper-V)
    - features_any: list[str] - Any of these features must be available
    - features_all: list[str] - All of these features must be available
    """

    def __init__(self, context: HardwareContext) -> None:
        """Initialize with hardware context.

        Args:
            context: Detected hardware context.
        """
        self.context = context

    def is_applicable(self, setting: SettingExecutor) -> tuple[bool, str]:
        """Check if a setting applies to the current hardware.

        Args:
            setting: The setting to check.

        Returns:
            Tuple of (is_applicable, reason). Reason is empty if applicable.
        """
        conditions = setting.applicable_conditions
        if not conditions:
            return True, ""

        # CPU vendor check
        if "cpu_vendor" in conditions:
            required_vendor = conditions["cpu_vendor"].lower()
            if self.context.cpu_vendor is None:
                return False, f"Requires {required_vendor.upper()} CPU"
            if self.context.cpu_vendor.lower() != required_vendor:
                return False, f"Requires {required_vendor.upper()} CPU"

        # GPU vendor check
        if "gpu_vendor" in conditions:
            required_vendor = conditions["gpu_vendor"].lower()
            if self.context.gpu_vendor is None:
                return False, f"Requires {required_vendor.upper()} GPU"
            if self.context.gpu_vendor.lower() != required_vendor:
                return False, f"Requires {required_vendor.upper()} GPU"

        # GPU vendors (any match)
        if "gpu_vendors" in conditions:
            required_vendors = [v.lower() for v in conditions["gpu_vendors"]]
            if self.context.gpu_vendor is None:
                return False, f"Requires GPU: {', '.join(v.upper() for v in required_vendors)}"
            if self.context.gpu_vendor.lower() not in required_vendors:
                return False, f"Requires GPU: {', '.join(v.upper() for v in required_vendors)}"

        # Windows build checks
        if "min_windows_build" in conditions:
            min_build = conditions["min_windows_build"]
            if self.context.windows_build < min_build:
                return False, f"Requires Windows build {min_build}+"

        if "max_windows_build" in conditions:
            max_build = conditions["max_windows_build"]
            if self.context.windows_build > max_build:
                return False, f"Requires Windows build {max_build} or earlier"

        # Windows 11 check
        if (
            "is_windows_11" in conditions
            and conditions["is_windows_11"]
            and not self.context.is_windows_11
        ):
            return False, "Requires Windows 11"

        # Admin check
        if (
            "requires_admin" in conditions
            and conditions["requires_admin"]
            and not self.context.is_admin
        ):
            return False, "Requires administrator privileges"

        # VRR/G-Sync monitor check. Unknown and absent are different answers:
        # "could not read the panels" is a fact about detection, not hardware.
        if "requires_vrr" in conditions and conditions["requires_vrr"]:
            if self.context.has_vrr_monitor is None:
                return False, (
                    "The panels could not be read, so G-Sync/FreeSync support is unknown"
                )
            if not self.context.has_vrr_monitor:
                return False, "Requires G-Sync/FreeSync/VRR compatible monitor"

        # Single feature check
        if "feature" in conditions:
            required_feature = conditions["feature"]
            if required_feature not in self.context.features:
                return False, f"Requires {required_feature} feature"

        # Feature-absent check (feature must NOT be present)
        if "feature_absent" in conditions:
            absent_feature = conditions["feature_absent"]
            if absent_feature in self.context.features:
                # Name what would break, not the token that stands for it. The
                # user's question here is "am I losing something I use?", and
                # "virtualization_in_use is installed" cannot answer it.
                what = self.context.feature_labels.get(absent_feature, absent_feature)
                return False, f"Not recommended: would break {what}"

        # Any of features check
        if "features_any" in conditions:
            required_features = set(conditions["features_any"])
            if not required_features.intersection(self.context.features):
                return False, f"Requires one of: {', '.join(required_features)}"

        # All features check
        if "features_all" in conditions:
            required_features = set(conditions["features_all"])
            missing = required_features - self.context.features
            if missing:
                return False, f"Requires: {', '.join(missing)}"

        return True, ""

    def get_applicable_settings(self, settings: list[SettingExecutor]) -> list[SettingExecutor]:
        """Filter to only applicable settings.

        Args:
            settings: List of settings to filter.

        Returns:
            List of settings that apply to the current hardware.
        """
        return [s for s in settings if self.is_applicable(s)[0]]


def _coerce_scalar(v: Any) -> Any:
    """Normalize a scalar for comparison.

    Strips surrounding whitespace and CRLF from strings, then attempts to
    parse numeric strings so that "1" and 1 compare as equal.
    Non-string values are returned unchanged.
    """
    if not isinstance(v, str):
        return v
    v = v.strip().replace("\r\n", "\n").replace("\r", "\n")
    try:
        return int(v)
    except (ValueError, TypeError):
        pass
    try:
        return float(v)
    except (ValueError, TypeError):
        pass
    return v


def values_equal(a: Any, b: Any) -> bool:
    """Compare two setting values for equality with type coercion.

    Handles: whitespace/CRLF normalization, numeric string coercion
    ("1" == 1), case-insensitive string comparison, float tolerance.
    """
    if a is None or b is None:
        return a is b

    a = _coerce_scalar(a)
    b = _coerce_scalar(b)

    # Boolean comparison (must precede int check — bool is subclass of int)
    if isinstance(a, bool) and isinstance(b, bool):
        return a == b

    # Numeric comparison — exact for int, tolerance for float
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, int) and isinstance(b, int):
            return a == b
        return abs(float(a) - float(b)) < 0.001

    # String comparison (case-insensitive)
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()

    return bool(a == b)
