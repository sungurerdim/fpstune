"""Apply a setting, read it back, and put it where it was.

This is Phase 17's harness. Every defect found in that phase was invisible from the
code: `-InterfaceIndex` on a cmdlet that has no such parameter, a keyword spelled
`*AdvancedEEE` where the driver publishes `AdvancedEEE`, a buffer count of 1024
silently clamped to 512. All of them reported `[OK] applied` and wrote nothing, and
all of them were caught only when a later detect disagreed. So the check is not "does
apply return success" — it is "does the machine now hold what apply claimed to write".

**It mutates the real system, so it does not run by itself.** `FPSTUNE_APPLY_SWEEP`
must name what to sweep, and nothing runs without it — not in CI, not in a normal
`pytest` run. That is deliberate rather than cautious: several shipped tweaks restart
a network adapter or disable a radio, and a suite that silently did that to the
machine it runs on would be worse than the defects it hunts.

    FPSTUNE_APPLY_SWEEP="network:17:eee,timer:hpet"   two settings by id
    FPSTUNE_APPLY_SWEEP="visual"                      every setting in one module
    FPSTUNE_APPLY_SWEEP="all"                         everything eligible

Each setting is restored to the value it held before, and the restore is verified the
same way the apply is. A setting whose current value cannot be written back — a
detect-only reading like `Forced_Other`, which is a state and not a target — is
skipped rather than applied, because a sweep that cannot undo itself is a sweep that
changes the machine.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import pytest

from fpstune.settings.applicability import values_equal
from fpstune.settings.base import DetectType, SettingExecutor
from fpstune.settings.executors import CommandExecutor
from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.settings.registry import SettingsRegistry
from fpstune.utils.admin import is_admin

SWEEP_ENV = "FPSTUNE_APPLY_SWEEP"

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="Applies settings to real Windows"),
    pytest.mark.skipif(
        not os.environ.get(SWEEP_ENV),
        reason=f"Set {SWEEP_ENV} to sweep; it writes to this machine",
    ),
]


@dataclass
class Row:
    """One setting's trip through apply, re-detect and restore."""

    setting_id: str
    original: Any
    target: Any
    observed: Any
    applied_ok: bool
    apply_error: str | None
    restored: Any
    restore_ok: bool

    @property
    def agrees(self) -> bool:
        return self.applied_ok and values_equal(self.observed, self.target)

    @property
    def back_where_it_started(self) -> bool:
        return values_equal(self.restored, self.original)


def _selection(registry: SettingsRegistry) -> list[SettingExecutor]:
    """Resolve the env var into settings, refusing anything it cannot name."""
    raw = os.environ[SWEEP_ENV].strip()
    everything = registry.get_all()

    if raw == "all":
        return everything

    wanted = {part.strip() for part in raw.split(",") if part.strip()}
    by_id = {setting.id: setting for setting in everything}

    selected: list[SettingExecutor] = []
    unmatched: list[str] = []
    for name in wanted:
        if name in by_id:
            selected.append(by_id[name])
            continue
        in_module = [setting for setting in everything if setting.module == name]
        if in_module:
            selected.extend(in_module)
            continue
        unmatched.append(name)

    assert not unmatched, (
        f"{SWEEP_ENV} names nothing that exists: {sorted(unmatched)}. "
        "A typo silently sweeping zero settings would report a clean run."
    )
    return selected


def _apply_ignores_requested_value(setting: SettingExecutor) -> bool:
    """True when apply always writes one outcome, whatever value it is handed.

    `audio:device_format` is the shipped case and the reason this exists: its apply
    walks every audio endpoint and writes 48 kHz, so handing it the original value
    `mismatched` does not put 96 kHz back — it re-applies 48 kHz. A sweep would have
    reported a clean restore over a machine it had permanently changed.

    The test is on the *resolved* command, not the declared one. A raw command
    substitutes `%value%`; a named handler like `service_toggle` is a key into
    ACTION_COMMANDS whose body does the substituting, and judging those by the key
    alone flags 117 settings that pass the value through perfectly well. Resolved,
    the real count on the shipped registry is one.

    Only PowerShell applies can be one-way. Registry, netsh and powercfg writes take
    the value by construction.
    """
    if setting.apply_type is not DetectType.POWERSHELL:
        return False
    key = setting.apply_command.strip()
    resolved = ACTION_COMMANDS.get(key, setting.apply_command)
    return "%value%" not in resolved


def _skip_reason(setting: SettingExecutor, current: Any) -> str | None:
    """Why this setting cannot take part, or None if it can.

    Eligibility is deliberately not decided by `apply_command` alone. Only the
    PowerShell and netsh executors write from a command string; registry, powercfg
    and NVIDIA-profile settings describe their write entirely in `apply_args` and
    ship with an empty command. Treating an empty command as "cannot apply" exempts
    102 of the 327 shipped settings — which is #1 in this ledger, where the same
    test silently exempted 108 settings from verification, one layer up.
    """
    if setting.is_action:
        return "action: it runs, it has no state to compare"
    if setting.is_readonly:
        return "advisory: fpstune reads it and cannot write it"
    if not setting.apply_command and not setting.apply_args:
        return "nothing to write with: no apply command and no apply args"
    if current is None:
        return "nothing detected, so there is no value to restore"
    if values_equal(current, setting.recommended_value):
        return "already at the recommended value: applying proves nothing"
    if setting.apply_value_map and current not in setting.apply_value_map:
        # `Forced_Other` is the shipped example: a reading, deliberately absent from
        # the apply map because there is no single number it could write.
        return f"current value {current!r} is not writable, so it could not be restored"
    if _apply_ignores_requested_value(setting):
        return "apply ignores the value it is handed, so the original cannot be written back"
    return None


def _roundtrip(setting: SettingExecutor) -> Row:
    original, _ = CommandExecutor.detect(setting)
    applied_ok, apply_error = CommandExecutor.apply(setting, setting.recommended_value)
    observed, _ = CommandExecutor.detect(setting)

    restore_ok, _ = CommandExecutor.apply(setting, original)
    restored, _ = CommandExecutor.detect(setting)

    return Row(
        setting_id=setting.id,
        original=original,
        target=setting.recommended_value,
        observed=observed,
        applied_ok=applied_ok,
        apply_error=apply_error,
        restored=restored,
        restore_ok=restore_ok,
    )


@pytest.fixture(scope="module")
def sweep() -> tuple[list[Row], list[tuple[str, str]]]:
    """Run the sweep once and hand every assertion the same evidence."""
    assert is_admin(), (
        "This sweep must run elevated. Unelevated, every write fails with access "
        "denied and the run would report a clean machine it never touched."
    )

    registry = SettingsRegistry()
    selected = _selection(registry)

    rows: list[Row] = []
    skipped: list[tuple[str, str]] = []
    for setting in sorted(selected, key=lambda s: s.id):
        current, _ = CommandExecutor.detect(setting)
        reason = _skip_reason(setting, current)
        if reason:
            skipped.append((setting.id, reason))
            continue
        rows.append(_roundtrip(setting))

    print(f"\napply sweep: {len(rows)} exercised, {len(skipped)} skipped")
    for row in rows:
        verdict = "ok " if row.agrees else "MISMATCH"
        print(
            f"  {verdict} {row.setting_id}: {row.original!r} -> {row.target!r} "
            f"read back {row.observed!r}, restored {row.restored!r}"
        )
    for setting_id, reason in skipped:
        print(f"  skip {setting_id}: {reason}")

    return rows, skipped


def test_the_sweep_exercised_something(
    sweep: tuple[list[Row], list[tuple[str, str]]],
) -> None:
    """A sweep that skipped everything must not read as a pass."""
    rows, skipped = sweep
    assert rows, (
        "nothing was exercised — every selected setting was skipped: "
        f"{skipped}. A green result here would mean nothing."
    )


def test_apply_never_reports_success_over_an_unchanged_system(
    sweep: tuple[list[Row], list[tuple[str, str]]],
) -> None:
    """The #40 / #44 / #47 shape: `[OK] applied`, and the machine did not move."""
    rows, _ = sweep
    liars = [
        f"{row.setting_id}: claimed to write {row.target!r} but reads {row.observed!r}"
        for row in rows
        if row.applied_ok and not values_equal(row.observed, row.target)
    ]
    assert not liars, "apply reported success without the write landing:\n" + "\n".join(liars)


def test_a_failed_apply_says_why(sweep: tuple[list[Row], list[tuple[str, str]]]) -> None:
    """A failure with no message is a defect that cannot be diagnosed."""
    rows, _ = sweep
    silent = [row.setting_id for row in rows if not row.applied_ok and not row.apply_error]
    assert not silent, f"apply failed with no error text: {silent}"


def test_the_reading_stays_inside_the_settings_own_choices(
    sweep: tuple[list[Row], list[tuple[str, str]]],
) -> None:
    """#41's shape: a real reading of 512 surfaced as a raw number no map knew."""
    rows, _ = sweep
    registry = SettingsRegistry()
    strays: list[str] = []
    for row in rows:
        setting = registry.get(row.setting_id)
        if setting is None or not setting.choices or row.observed is None:
            continue
        if not any(values_equal(row.observed, choice) for choice in setting.choices):
            strays.append(f"{row.setting_id}: read {row.observed!r} not in {setting.choices}")
    assert not strays, "detected value outside its own choices:\n" + "\n".join(strays)


def test_the_machine_is_left_as_it_was_found(
    sweep: tuple[list[Row], list[tuple[str, str]]],
) -> None:
    """The sweep is a measurement, not a change.

    This is also a second, independent test of apply: restoring is another write,
    read back the same way, so a setting that can only be written in one direction
    fails here rather than quietly leaving the machine altered.
    """
    rows, _ = sweep
    stuck = [
        f"{row.setting_id}: was {row.original!r}, left at {row.restored!r}"
        for row in rows
        if not row.back_where_it_started
    ]
    assert not stuck, "settings were not restored — this machine has been changed:\n" + "\n".join(
        stuck
    )
