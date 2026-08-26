"""The apply sweep's own decisions, checked without touching the machine.

The sweep in `tests/test_windows_contract/test_apply_roundtrip.py` only runs when
`FPSTUNE_APPLY_SWEEP` names something and the process is elevated, so its logic would
otherwise never be exercised by a normal run — and a harness whose skip rules are too
broad skips everything and reports a clean sweep. These pin the rules themselves.

The two that matter most:

* a setting already at its recommended value proves nothing by being applied, so it
  is skipped rather than counted as a pass
* a setting whose *current* value cannot be written back is skipped rather than
  applied, because a sweep that cannot undo itself has changed the machine
"""

from __future__ import annotations

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from tests.test_windows_contract.test_apply_roundtrip import (
    Row,
    _apply_ignores_requested_value,
    _skip_reason,
)


def _setting(**over: object) -> SettingExecutor:
    fields: dict[str, object] = {
        "id": "network:sample",
        "category": SettingCategory.NETWORK,
        "display_name": "Sample",
        "description": "A sample setting.",
        "value_type": SettingValueType.CHOICE,
        "choices": ("enabled", "disabled"),
        "default_value": "enabled",
        "recommended_value": "disabled",
        "detect_type": DetectType.REGISTRY,
        "detect_command": "read",
        "apply_type": DetectType.REGISTRY,
        "apply_command": "write",
        "apply_value_map": {"enabled": 1, "disabled": 0},
    }
    fields.update(over)
    return SettingExecutor(**fields)  # type: ignore[arg-type]


def test_a_setting_that_can_move_is_exercised() -> None:
    assert _skip_reason(_setting(), "enabled") is None


def test_an_action_is_skipped() -> None:
    reason = _skip_reason(_setting(is_action=True), "enabled")
    assert reason is not None and "action" in reason


def test_an_advisory_is_skipped() -> None:
    """fpstune reads these and cannot write them; applying one is not a thing."""
    reason = _skip_reason(_setting(is_readonly=True), "enabled")
    assert reason is not None and "advisory" in reason


def test_a_registry_setting_with_an_empty_command_is_still_exercised() -> None:
    """Its write lives entirely in `apply_args`, and most of the registry looks like this.

    Judging eligibility by `apply_command` alone exempts 102 of the 327 shipped
    settings — every registry, powercfg and NVIDIA-profile one. That is #1 in this
    project's ledger, where exactly this test silently exempted 108 settings from
    verification; a sweep that inherits it would report clean over a third of the
    product it never touched.
    """
    setting = _setting(
        apply_command="",
        apply_args={"hive": "HKLM", "path": r"SYSTEM\CurrentControlSet\X", "name": "Y"},
    )
    assert _skip_reason(setting, "enabled") is None


def test_a_setting_with_no_way_to_write_at_all_is_skipped() -> None:
    """Neither a command nor args: there is nothing to write with."""
    setting = _setting(apply_command="", apply_args={})
    assert _skip_reason(setting, "enabled") is not None


def test_an_undetected_setting_is_skipped() -> None:
    """With no original value there is nothing to restore afterwards."""
    assert _skip_reason(_setting(), None) is not None


def test_a_setting_already_at_its_target_is_skipped() -> None:
    """Applying it would pass without proving a write ever lands."""
    reason = _skip_reason(_setting(), "disabled")
    assert reason is not None and "proves nothing" in reason


def test_a_reading_that_cannot_be_written_back_is_skipped() -> None:
    """`Forced_Other` is the shipped case: a state, absent from the apply map.

    Sweeping it would apply the recommendation and then fail to restore, leaving the
    machine changed by a test that claims to measure it.
    """
    setting = _setting(
        choices=("Auto_Negotiation", "1Gbps_Full", "Forced_Other"),
        recommended_value="Auto_Negotiation",
        apply_value_map={"Auto_Negotiation": 0, "1Gbps_Full": 6},
    )
    reason = _skip_reason(setting, "Forced_Other")
    assert reason is not None and "could not be restored" in reason


def test_a_one_way_apply_is_skipped() -> None:
    """`audio:device_format` walks every endpoint and writes 48 kHz regardless.

    Handing it the original reading does not put 96 kHz back — it writes 48 kHz
    again. Sweeping it would report a clean restore over a machine it had
    permanently changed, which is the one outcome this harness must never produce.
    """
    setting = _setting(
        id="audio:device_format",
        choices=("optimal", "mismatched", "not_available"),
        default_value="optimal",
        recommended_value="optimal",
        detect_type=DetectType.POWERSHELL,
        apply_type=DetectType.POWERSHELL,
        apply_command="$x = 48000; Set-ItemProperty ...",  # no %value% anywhere
        apply_value_map={},
    )
    reason = _skip_reason(setting, "mismatched")
    assert reason is not None and "ignores the value" in reason


def test_a_named_action_handler_is_not_mistaken_for_one_way() -> None:
    """`service_toggle` is a key into ACTION_COMMANDS, whose body substitutes.

    Judging by the declared string alone flags 117 shipped settings that pass the
    value through perfectly well, and a sweep that skips almost everything reports
    clean while measuring nothing.
    """
    setting = _setting(
        id="services:sysmain",
        detect_type=DetectType.POWERSHELL,
        apply_type=DetectType.POWERSHELL,
        apply_command="service_toggle",
        apply_args={"service": "SysMain"},
        apply_value_map={},
    )
    assert not _apply_ignores_requested_value(setting)


def test_a_registry_write_is_never_one_way() -> None:
    """Registry, netsh and powercfg writes take the value by construction."""
    assert not _apply_ignores_requested_value(_setting(apply_command="anything"))


def test_a_setting_with_no_apply_map_is_still_eligible() -> None:
    """Numeric settings write their value directly; an empty map is not a barrier."""
    setting = _setting(
        value_type=SettingValueType.INT,
        choices=(),
        default_value=1500,
        recommended_value=1492,
        apply_value_map={},
    )
    assert _skip_reason(setting, 1500) is None


def _row(**over: object) -> Row:
    fields: dict[str, object] = {
        "setting_id": "network:sample",
        "original": "enabled",
        "target": "disabled",
        "observed": "disabled",
        "applied_ok": True,
        "apply_error": None,
        "restored": "enabled",
        "restore_ok": True,
    }
    fields.update(over)
    return Row(**fields)  # type: ignore[arg-type]


def test_a_clean_roundtrip_agrees_and_restores() -> None:
    row = _row()
    assert row.agrees
    assert row.back_where_it_started


def test_success_without_the_write_landing_does_not_agree() -> None:
    """The #40 shape: `[OK] applied`, and the value never moved."""
    assert not _row(observed="enabled").agrees


def test_the_comparison_tolerates_the_shapes_values_arrive_in() -> None:
    """Readings come back as strings; targets are declared as ints.

    A plain `==` here is exactly what #41 was: `512` never equals `"512"`, so the
    check would report a mismatch on a setting that applied perfectly.
    """
    assert _row(target=1492, observed="1492", original=1500, restored="1500").agrees
    assert _row(target=1492, observed="1492", original=1500, restored="1500").back_where_it_started
