"""The status cache and the response model must agree on which keys exist.

``status_cache`` builds a row per setting and ``api/routes/system.py`` splats it
into ``ModuleSettingResponse``. Pydantic discards a key the model has no field
for and says nothing, so ``is_optimized`` was produced on every refresh, counted
into ``applied_count``, and then dropped on the way out of ``/api/status`` —
every client got the counts and never the flag they were derived from.

Nothing went red because both sides were written by hand and neither named the
other. ``CachedSetting`` is that name; these hold it to the model.
"""

from __future__ import annotations

from fpstune.api.schemas import ModuleSettingResponse
from fpstune.api.status_cache import CachedSetting, _cached_setting


def test_every_produced_key_has_a_field_on_the_response_model() -> None:
    produced = set(CachedSetting.__annotations__)
    carried = set(ModuleSettingResponse.model_fields)

    assert produced <= carried, (
        f"status_cache produces {sorted(produced - carried)}, which "
        "ModuleSettingResponse cannot carry. Pydantic drops those without a "
        "word, so the value reaches the route and never the client."
    )


def test_is_optimized_is_the_key_this_found() -> None:
    # The concrete instance, pinned so the field cannot be quietly removed
    # again: it is the one the module counts and the one that was disappearing.
    assert "is_optimized" in CachedSetting.__annotations__
    assert "is_optimized" in ModuleSettingResponse.model_fields


def test_a_row_survives_the_response_model_intact() -> None:
    """End to end over the real hand-off, with a value that is not the default.

    ``is_optimized`` defaults to False on the model, so a row asserting True is
    the only one that can tell "carried through" apart from "dropped and
    defaulted" — which is exactly how the drop stayed invisible.
    """
    from fpstune.settings.base import (
        DetectionResult,
        DetectType,
        SettingCategory,
        SettingExecutor,
        SettingValueType,
    )

    setting = SettingExecutor(
        id="network:nagle_algorithm",
        category=SettingCategory.NETWORK,
        display_name="Nagle's Algorithm",
        description="Batches small TCP writes before sending them. Disabling it "
        "sends each input packet immediately, which is what a game wants.",
        value_type=SettingValueType.CHOICE,
        choices=("enabled", "disabled"),
        default_value="enabled",
        recommended_value="disabled",
        current_impact="Enabled: Small packets are held and batched",
        recommended_impact="Disabled: Input packets leave immediately",
        detect_type=DetectType.REGISTRY,
        detect_command="",
        detect_args={},
        apply_type=DetectType.REGISTRY,
        apply_command="",
        apply_args={},
    )
    result = DetectionResult(
        setting_id=setting.id,
        value="disabled",
        error=None,
        time_ms=1,
        is_optimized=True,
    )

    row = _cached_setting(setting, result)
    assert row["is_optimized"] is True

    response = ModuleSettingResponse.model_validate(row)
    assert response.is_optimized is True
    assert response.name == "network:nagle_algorithm"
    assert response.current_value == "disabled"


def test_a_setting_with_no_detection_result_is_not_reported_optimized() -> None:
    """A missing reading is "we do not know", never "already correct"."""
    from fpstune.settings.base import (
        DetectType,
        SettingCategory,
        SettingExecutor,
        SettingValueType,
    )

    setting = SettingExecutor(
        id="network:nagle_algorithm",
        category=SettingCategory.NETWORK,
        display_name="Nagle's Algorithm",
        description="Batches small TCP writes before sending them. Disabling it "
        "sends each input packet immediately, which is what a game wants.",
        value_type=SettingValueType.CHOICE,
        choices=("enabled", "disabled"),
        default_value="enabled",
        recommended_value="disabled",
        current_impact="Enabled: Small packets are held and batched",
        recommended_impact="Disabled: Input packets leave immediately",
        detect_type=DetectType.REGISTRY,
        detect_command="",
        detect_args={},
        apply_type=DetectType.REGISTRY,
        apply_command="",
        apply_args={},
    )

    row = _cached_setting(setting, None)

    assert row["is_optimized"] is False
    assert row["current_value"] is None
