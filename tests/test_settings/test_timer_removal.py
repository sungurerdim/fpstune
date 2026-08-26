"""The debunked bcdedit timer tweaks must stay gone.

HPET (``useplatformclock``), platform tick, dynamic tick and TSC sync policy were
removed in the 2026-08 audit: each recommended the Windows default, so applying
it changed nothing, while the alternative it exposed was actively harmful. The
reported FPS gains are a measurement artifact — frame counters are themselves
driven by the timer being changed.

These tests exist so the settings cannot quietly reappear, and so the one timer
setting that does carry evidence is not removed along with them.
"""

from __future__ import annotations

import pytest

from fpstune.settings.base import SettingScope
from fpstune.settings.definitions.timer import TIMER_SETTINGS
from fpstune.settings.registry import SettingsRegistry

REMOVED_IDS = [
    "timer:hpet",
    "timer:platform_tick",
    "timer:dynamic_tick",
    "timer:tsc_sync_policy",
]


@pytest.fixture(scope="module")
def registry() -> SettingsRegistry:
    return SettingsRegistry(discover_dynamic=False)


@pytest.mark.parametrize("setting_id", REMOVED_IDS)
def test_removed_timer_setting_does_not_resolve(
    registry: SettingsRegistry, setting_id: str
) -> None:
    assert registry.get(setting_id) is None


@pytest.mark.parametrize("setting_id", REMOVED_IDS)
def test_removed_timer_setting_is_not_exported(setting_id: str) -> None:
    # Guards the other half of the failure: a definition left in the module but
    # dropped from the export list is dead code that still reads as supported.
    assert setting_id not in {s.id for s in TIMER_SETTINGS}


def test_no_bcdedit_timer_setting_survives(registry: SettingsRegistry) -> None:
    # Catches a re-add under a different id: the point was to stop writing boot
    # configuration for timer sources at all, not to blacklist four strings.
    from fpstune.settings.base import DetectType

    offenders = [
        s.id
        for s in registry.get_all()
        if s.id.startswith("timer:") and s.apply_type is DetectType.BCDEDIT
    ]
    assert offenders == []


def test_global_timer_resolution_survives(registry: SettingsRegistry) -> None:
    # The same research that debunked the four validates this one: timer
    # resolution is the knob that actually affects frame pacing.
    setting = registry.get("timer:global_timer_resolution")
    assert setting is not None
    assert setting.evidence_level == "proven"
    assert setting.scope is SettingScope.ESSENTIAL
    assert setting.recommended_value != setting.default_value


def test_timer_category_is_not_empty(registry: SettingsRegistry) -> None:
    assert [s for s in registry.get_all() if s.id.startswith("timer:")]


def test_removal_closed_the_timer_c1_violations(registry: SettingsRegistry) -> None:
    # All four carried evidence_level="experimental" without the advanced/
    # risk_warning pair that C1 requires. The category should now be clean.
    violations = [
        s.id
        for s in registry.get_all()
        if s.id.startswith("timer:")
        and s.evidence_level == "experimental"
        and not (s.risk_level == "advanced" and s.risk_warning)
    ]
    assert violations == []


def test_removal_closed_the_timer_noops(registry: SettingsRegistry) -> None:
    # A tweak whose recommendation equals the default does nothing when applied,
    # yet presents as actionable in the UI. None should remain in this category.
    noops = [
        s.id
        for s in registry.get_all()
        if s.id.startswith("timer:")
        and s.recommended_value == s.default_value
        and not s.is_readonly
        and not s.is_action
    ]
    assert noops == []
