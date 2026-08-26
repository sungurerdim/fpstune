"""Setting-based architecture for fpstune.

This package provides a unified setting detection and application system.
Each setting is a self-contained SettingExecutor with its own detection
and apply logic, enabling parallel detection and isolated error handling.
"""

from __future__ import annotations

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.detection import DetectionEngine, DetectionResult
from fpstune.settings.executors import CommandExecutor
from fpstune.settings.registry import SettingsRegistry

__all__ = [
    # Core types
    "SettingExecutor",
    "SettingCategory",
    "SettingValueType",
    "DetectType",
    # Detection
    "DetectionEngine",
    "DetectionResult",
    # Executors
    "CommandExecutor",
    # Registry
    "SettingsRegistry",
]
