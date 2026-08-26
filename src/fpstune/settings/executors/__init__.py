"""Command executors for setting detection and application."""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from fpstune.settings.applicability import is_absent_reading
from fpstune.settings.base import MASK, UNMAPPED
from fpstune.utils.logger import tweak_label

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor, SettingValueType

logger = logging.getLogger(__name__)


def coerce_value_type(value: Any, value_type: SettingValueType) -> Any:
    """Coerce a value to the expected type based on setting's value_type.

    Handles common cases where PowerShell/registry returns strings
    but the setting expects int, bool, or float.

    Args:
        value: The raw value (often a string from command output).
        value_type: The expected SettingValueType.

    Returns:
        The value coerced to the appropriate Python type, or original value if coercion fails.
    """
    if value is None:
        return None

    # Import here to avoid circular dependency
    from fpstune.settings.base import SettingValueType

    try:
        if value_type == SettingValueType.INT:
            # Handle string representations of integers
            if isinstance(value, str):
                # Strip whitespace and handle empty strings
                value = value.strip()
                if not value:
                    return None
                # Handle hex format (0x...)
                if value.lower().startswith("0x"):
                    return int(value, 16)
                return int(float(value))  # Handle "165.0" -> 165
            return int(value) if not isinstance(value, int) else value

        elif value_type == SettingValueType.FLOAT:
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    return None
                return float(value)
            return float(value) if not isinstance(value, (int, float)) else value

        elif value_type == SettingValueType.BOOL:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                value = value.strip().lower()
                if value in ("true", "1", "yes", "on", "enabled"):
                    return True
                if value in ("false", "0", "no", "off", "disabled"):
                    return False
            if isinstance(value, (int, float)):
                return bool(value)
            return value  # Return as-is if unknown format

        # STRING and CHOICE types - return as-is
        return value

    except (ValueError, TypeError) as e:
        logger.debug("Type coercion failed for value %r to %s: %s", value, value_type, e)
        return value  # Return original if coercion fails


def _as_int(raw: Any) -> int | None:
    """Parse a reading as an integer, accepting the ``0x`` form powercfg returns."""
    try:
        as_text = str(raw).strip()
        return int(as_text, 16) if as_text.lower().startswith("0x") else int(as_text)
    except (ValueError, TypeError):
        return None


def map_raw_to_display(value_map: dict[Any, Any], raw: Any) -> Any:
    """Translate a raw executor reading into its display value.

    Single lookup rule for every executor. Registry returns ``int`` for
    REG_DWORD and ``str`` for REG_SZ, netsh/PowerShell return text, and powercfg
    returns hex — so a map keyed only as ``{1: "enabled"}`` used to miss a
    ``"1"`` reading (and vice versa) and silently leave the raw value in place,
    which then failed every comparison against the display value.

    Tries, in order: the value itself, its string form, its integer form.
    Returns ``raw`` unchanged when nothing matches, so callers keep the old
    "no mapping configured" behaviour — unless the map declares ``UNMAPPED``.

    Two reserved keys change the lookup rather than extend the table; see
    ``base.MASK`` and ``base.UNMAPPED`` for why each exists.
    """
    if not value_map:
        return raw

    # A masked reading packs several flags into one number. Reduce it to the
    # bits this setting is about before any lookup, so the table describes the
    # feature and not every combination of unrelated flags alongside it.
    mask = value_map.get(MASK)
    if mask is not None and raw is not None and not is_absent_reading(raw):
        masked = _as_int(raw)
        if masked is not None:
            raw = masked & int(mask)

    def unmapped(value: Any) -> Any:
        """What a reading outside the table means, if the setting says."""
        # Absence is not an unmapped value. A setting whose feature is missing
        # must keep reporting that, or `UNMAPPED` would dress "this NIC has no
        # such keyword" up as an ordinary default and detection would never
        # mark it not-applicable.
        if UNMAPPED in value_map and value is not None and not is_absent_reading(value):
            return value_map[UNMAPPED]
        return value

    try:
        if raw in value_map:
            return value_map[raw]
    except TypeError:  # unhashable reading — nothing can map it
        return raw

    if raw is None:
        return raw

    as_text = str(raw).strip()
    if as_text in value_map:
        return value_map[as_text]

    as_int = _as_int(as_text)
    if as_int is None:
        return unmapped(raw)

    if as_int in value_map:
        return value_map[as_int]
    if str(as_int) in value_map:
        return value_map[str(as_int)]
    return unmapped(raw)


class BaseExecutor(ABC):
    """Base class for command executors."""

    @abstractmethod
    def detect(self, setting: SettingExecutor) -> tuple[Any | None, str | None]:
        """Detect the current value of a setting.

        Args:
            setting: The setting to detect.

        Returns:
            Tuple of (value, error). Value is None if detection failed.
        """
        ...

    @abstractmethod
    def apply(self, setting: SettingExecutor, value: Any) -> tuple[bool, str | None]:
        """Apply a value to a setting.

        Args:
            setting: The setting to apply.
            value: The value to apply (display value, not raw).

        Returns:
            Tuple of (success, error).
        """
        ...


class CommandExecutor:
    """Unified command execution for all setting types."""

    _executors: dict[str, BaseExecutor] = {}
    _executors_lock: threading.Lock = threading.Lock()

    @classmethod
    def detect(cls, setting: SettingExecutor) -> tuple[Any | None, str | None]:
        """Execute detection and return (value, error).

        Automatically coerces the detected value to the expected type
        based on setting.value_type (INT, FLOAT, BOOL, etc.).
        """
        from fpstune.utils.debug import debug_log

        executor = cls._get_executor(setting.detect_type.value)
        if not executor:
            debug_log("executor", f"Unknown detect_type: {setting.detect_type} for {setting.id}")
            return None, f"Unknown detect type: {setting.detect_type}"

        raw_value, error = executor.detect(setting)

        # Log raw value before coercion
        debug_log(
            "executor",
            f"RAW DETECT {setting.id}: type={setting.detect_type.value}, "
            f"raw_value={repr(raw_value)}, value_map={setting.value_map}, error={error}",
        )

        # Apply type coercion if we got a value
        value = raw_value
        if value is not None and error is None:
            value = coerce_value_type(value, setting.value_type)
            # values-differ-by-design: this asks whether coercion changed the
            # representation, which is the one question values_equal() exists to
            # answer "no" to. "1" -> 1 is precisely what the log line reports.
            if value != raw_value:
                debug_log("executor", f"COERCED {setting.id}: {repr(raw_value)} -> {repr(value)}")

        return value, error

    @classmethod
    def apply(cls, setting: SettingExecutor, value: Any) -> tuple[bool, str | None]:
        """Execute apply and return (success, error)."""
        from fpstune.settings.base import SettingValueType
        from fpstune.utils.debug import debug_log

        logger.info("[APPLY] %s → %r", tweak_label(setting.id), value)
        debug_log(
            "executor",
            f"APPLY {setting.id}: value={repr(value)}, apply_type={setting.apply_type.value}",
        )

        # Skip action execution when value is falsy (treat as "do not run")
        if setting.is_action:
            coerced = coerce_value_type(value, SettingValueType.BOOL)
            if coerced is False or coerced is None:
                debug_log("executor", f"SKIP ACTION {setting.id}: value={repr(value)}")
                return True, None

        executor = cls._get_executor(setting.apply_type.value)
        if not executor:
            debug_log("executor", f"Unknown apply_type: {setting.apply_type} for {setting.id}")
            return False, f"Unknown apply type: {setting.apply_type}"

        success, error = executor.apply(setting, value)
        debug_log("executor", f"APPLY RESULT {setting.id}: success={success}, error={error}")
        if success:
            logger.info("[OK]   %s → applied", tweak_label(setting.id))
        else:
            logger.info("[FAIL] %s → %s", tweak_label(setting.id), error)
        return success, error

    @classmethod
    def _get_executor(cls, exec_type: str) -> BaseExecutor | None:
        """Get or create executor for the given type."""
        if not cls._executors:
            # Double-checked locking: concurrent ThreadPoolExecutor workers must
            # not race to rebuild the executor map on first miss (PERF-06).
            with cls._executors_lock:
                if not cls._executors:
                    # Lazy import to avoid circular dependencies
                    from fpstune.settings.executors.bcdedit import BcdEditExecutor
                    from fpstune.settings.executors.netsh import NetshExecutor
                    from fpstune.settings.executors.nvprofile import NvProfileExecutor
                    from fpstune.settings.executors.powercfg import PowerCfgExecutor
                    from fpstune.settings.executors.powershell import PowerShellExecutor
                    from fpstune.settings.executors.registry import RegistryExecutor

                    cls._executors = {
                        "powercfg": PowerCfgExecutor(),
                        "bcdedit": BcdEditExecutor(),
                        "registry": RegistryExecutor(),
                        "powershell": PowerShellExecutor(),
                        "netsh": NetshExecutor(),
                        "nvprofile": NvProfileExecutor(),
                    }

        return cls._executors.get(exec_type)


__all__ = ["BaseExecutor", "CommandExecutor", "coerce_value_type", "map_raw_to_display"]
