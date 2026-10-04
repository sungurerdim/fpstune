"""Reset of a Group Policy value deletes it; it never writes one.

Windows ships with no values under SOFTWARE\\Policies. Writing the "enabled"
number on reset left a policy in force — Settings then shows "managed by your
organization" and locks the toggle — and for telemetry and Delivery
Optimization the value written was more permissive than stock.
"""

from __future__ import annotations

from fpstune.settings.base import DetectType
from fpstune.settings.registry import SettingsRegistry


def _policy_settings():
    registry = SettingsRegistry(discover_dynamic=False)
    return [
        s
        for s in registry.get_all()
        if s.apply_type == DetectType.REGISTRY
        and "\\Policies\\" in "\\" + str(s.apply_args.get("path", "")) + "\\"
    ]


def test_there_are_policy_settings_to_check() -> None:
    assert len(_policy_settings()) >= 10


def test_every_policy_setting_resets_by_deleting() -> None:
    writes = {
        s.id: s.apply_value_map.get(s.default_value, "<unmapped>")
        for s in _policy_settings()
        if s.apply_value_map.get(s.default_value, "<unmapped>") is not None
    }
    assert writes == {}, f"reset would write a policy value: {writes}"


def test_an_absent_policy_reads_as_stock() -> None:
    # A script detect (Recall: is the feature even installed?) maps absence in
    # the script itself, so only a registry read is held to its value_map.
    for s in _policy_settings():
        if s.detect_type == DetectType.REGISTRY:
            assert s.value_map.get(None) == s.default_value, s.id


def test_delivery_optimization_stock_is_lan_only() -> None:
    """Microsoft: DODownloadMode "LAN (1 - Default)"."""
    setting = SettingsRegistry(discover_dynamic=False).get("system:delivery_optimization")
    assert setting is not None
    assert setting.default_value == "lan_only"
    assert setting.apply_value_map["lan_only"] is None
