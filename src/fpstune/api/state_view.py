"""The one `SettingState` builder, kept beside the response schema.

`/detect` and `/apply` must answer in one shape. The builder lives here rather
than in the settings router because the router already owns the routes; a second
copy of this mapping is how the two answers drift.
"""

from __future__ import annotations

from fpstune.api.schemas import SettingState
from fpstune.settings.base import SettingExecutor
from fpstune.settings.detection import DetectionResult


def setting_state(setting: SettingExecutor, result: DetectionResult) -> SettingState:
    """One setting's detection, in the one shape `/detect` and `/apply` both answer in.

    An action has a reading, not a value: `current` is None, `reading` carries the
    size/status string, and `is_optimized` is not a verdict for that row.
    """
    reading = str(result.value) if setting.is_action and result.value is not None else None
    return SettingState(
        setting_id=setting.id,
        current=None if setting.is_action else result.value,
        is_action=setting.is_action,
        reading=reading,
        applicable=result.is_applicable,
        applicable_reason=result.applicable_reason,
        recommended=setting.recommended_value,
        default=setting.default_value,
        default_source=setting.default_source,
        is_optimized=result.is_optimized,
        error=result.error,
        finding=result.finding,
    )
