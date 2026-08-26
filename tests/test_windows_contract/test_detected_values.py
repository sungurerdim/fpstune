"""A detected value must be one of the values the setting says it can have.

This is the other half of the contract layer. `test_generated_commands.py` proves
a command binds; this proves the reading it produces means something. Between
them they cover the two ways every defect in the 2026-08 audit manifested:

* the command did not bind (#40, 41 call sites) -- caught by the sibling module
* the command bound and returned something outside `choices`, so verification
  could never succeed:
    - #41 `receive_buffers` mapped only 1024 -> "maximum", so a real reading of
      512 surfaced as the raw number and `values_equal("512", "maximum")` could
      never hold
    - #46 `checksum_offload` read `$cs.TcpIPv4`, a property the cmdlet does not
      have; `[int]$null` is 0, so it reported "Disabled" on every system

The accounting rule this module exists to enforce, learned the expensive way:
**read `is_applicable`, not `value is not None`.** The first audit pass counted 27
failures; 23 of them were healthy settings correctly reporting "absent on this
hardware" and only 4 were real. `detection.py` converts a not_supported reading
into `value=None` + `is_applicable=False` deliberately, which is right for the UI
but destroys the distinction for a naive counter.

Windows-only, and slower than the rest of the suite because it runs a real scan.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from fpstune.settings.applicability import ABSENT_READINGS, values_equal
from fpstune.settings.base import (
    DetectionResult,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.detection import DetectionEngine
from fpstune.settings.registry import SettingsRegistry

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Runs a real detection scan against the host",
)

# What detection.py treats as "the feature is not here", before it collapses them
# to value=None + is_applicable=False. Imported rather than restated: this file
# used to carry its own three-item copy of a four-item set, so the sentinel it
# omitted was invisible to the test that exists to catch exactly that.
SENTINELS = tuple(sorted(ABSENT_READINGS))


@pytest.fixture(scope="module")
def scan() -> tuple[list[SettingExecutor], dict[str, DetectionResult]]:
    """One real scan, shared by every assertion in this module.

    Dynamic discovery is on: the per-adapter settings are where all seven defects
    lived, and they only exist once the host's adapters are enumerated.
    """
    registry = SettingsRegistry(discover_dynamic=True)
    settings = registry.get_all()
    engine = DetectionEngine()

    # Two scans, and the second is the one measured. Detection is not idempotent
    # for the cleanup family: their sizes are computed asynchronously, so a first
    # scan answers with a value while the background computation is still
    # running, and only the next one sees the settled result (which for absent
    # software is not_installed -> not applicable). Measured on this host: scan 1
    # detects 293, scans 2 and 3 detect 281 and stay there, and all 12 that move
    # are cleanup/game_cleanup. Measuring the steady state makes these numbers
    # independent of whatever ran earlier in the session.
    engine.detect_all(settings)
    results = engine.detect_all(settings)
    assert results, "The scan returned nothing; it is not exercising the registry"
    return settings, results


def _checkable(setting: SettingExecutor) -> bool:
    """Settings whose reading is supposed to be one of a fixed set.

    Actions have no state to read -- their detect reports progress or a reclaimable
    size, not a value from `choices`. Types other than CHOICE/BOOL carry a range or
    free text instead, which the range test below covers.
    """
    if setting.is_action:
        return False
    if not setting.choices:
        return False
    return setting.value_type in (SettingValueType.CHOICE, SettingValueType.BOOL)


def _in_choices(value: Any, setting: SettingExecutor) -> bool:
    """Membership through `values_equal`, never `in`.

    Executors return int for REG_DWORD, str for REG_SZ and text from PowerShell,
    so a plain `value in choices` would fail on exactly the cross-type readings
    that #41 was about. `values_equal` is the project's single comparison truth and
    is what the verify layer uses, so membership has to agree with it.
    """
    return any(values_equal(value, choice) for choice in setting.choices)


def _probe(choices: tuple[str, ...]) -> SettingExecutor:
    return SettingExecutor(
        id="probe:membership",
        category=SettingCategory.NETWORK,
        display_name="Membership probe",
        description="Exists only to prove the membership rule below rejects what it should.",
        choices=choices,
    )


@pytest.mark.parametrize(
    ("reading", "choices", "expected", "why"),
    [
        # #41 verbatim: the adapter really reported 512 while the value_map only
        # covered 1024, so the raw number reached the comparison.
        (
            "512",
            ("maximum", "default"),
            False,
            "an unmapped raw reading must not count as a choice",
        ),
        # The cross-type case that makes plain `in` the wrong operator: the
        # registry hands back an int, the choice is written as text.
        (1024, ("1024", "256"), True, "values_equal must coerce int/str, unlike `in`"),
        ("Enabled", ("enabled", "disabled"), True, "comparison is case-insensitive"),
        ("Enabled\r\n", ("enabled",), True, "CRLF from a command must not break membership"),
        ("Disabled", ("maximum", "default"), False, "a plausible but foreign value is rejected"),
    ],
)
def test_the_membership_rule_actually_rejects(
    reading: Any, choices: tuple[str, ...], expected: bool, why: str
) -> None:
    """A guard never observed to reject is not known to reject.

    The scan-based tests below pass on a healthy host, which makes them
    indistinguishable from tests that check nothing. These pin the rule itself
    against the readings that caused #41 -- and against the cross-type coercion
    that makes `values_equal` necessary rather than `in`.
    """
    assert _in_choices(reading, _probe(choices)) is expected, why


def test_no_detected_value_falls_outside_its_choices(
    scan: tuple[list[SettingExecutor], dict[str, DetectionResult]],
) -> None:
    """A reading outside `choices` can never verify, so apply can never succeed.

    #41 is the concrete failure: receive_buffers read 512, `choices` offered
    "maximum"/"default"/... and the value_map covered only 1024, so the raw 512
    was surfaced and every verification of that setting was doomed regardless of
    whether the write worked.
    """
    settings, results = scan
    offenders = []

    for setting in settings:
        if not _checkable(setting):
            continue
        result = results.get(setting.id)
        # Not applicable is the correct answer for hardware that lacks the
        # feature, and detection has already blanked the value in that case.
        if result is None or not result.is_applicable or result.value is None:
            continue
        if result.value in SENTINELS:
            continue
        if _in_choices(result.value, setting):
            continue
        offenders.append(f"  {setting.id}: read {result.value!r}, choices={setting.choices}")

    assert not offenders, (
        f"{len(offenders)} setting(s) detected a value outside their own choices, so "
        "verification of them can never succeed:\n" + "\n".join(offenders)
    )


def test_numeric_readings_respect_their_declared_range(
    scan: tuple[list[SettingExecutor], dict[str, DetectionResult]],
) -> None:
    """An INT setting that reads outside min/max is either mis-parsed or mis-declared.

    Kept separate from the choices test because the failure is different in kind:
    the value is the right shape but the declared bounds and the hardware disagree.
    #45 was this in spirit -- "maximum" was pinned to a constant 1024 while the
    adapter's real ceiling was 512 on receive and 4096 on transmit, so one write
    was clamped and the other verified against a non-maximum.
    """
    settings, results = scan
    offenders = []

    for setting in settings:
        if setting.is_action or setting.value_type not in (
            SettingValueType.INT,
            SettingValueType.FLOAT,
        ):
            continue
        if setting.min_value is None and setting.max_value is None:
            continue
        result = results.get(setting.id)
        if result is None or not result.is_applicable or result.value is None:
            continue
        if result.value in SENTINELS:
            continue
        try:
            numeric = float(str(result.value).strip())
        except (TypeError, ValueError):
            offenders.append(f"  {setting.id}: {result.value!r} is not numeric for an INT/FLOAT")
            continue
        if setting.min_value is not None and numeric < float(setting.min_value):
            offenders.append(f"  {setting.id}: {numeric} below min {setting.min_value}")
        if setting.max_value is not None and numeric > float(setting.max_value):
            offenders.append(f"  {setting.id}: {numeric} above max {setting.max_value}")

    assert not offenders, "Numeric readings outside their declared range:\n" + "\n".join(offenders)


def test_a_failed_detection_says_why(
    scan: tuple[list[SettingExecutor], dict[str, DetectionResult]],
) -> None:
    """No setting may fail silently: an error result must carry a message.

    A blank error with a null value is the state that made #31 invisible -- the
    setting simply vanished from the UI with nothing to explain it. Note this
    asserts about *reporting*, not about detection succeeding, so a host missing
    a feature does not fail the test.
    """
    settings, results = scan
    silent = [
        f"  {setting.id}"
        for setting in settings
        if (result := results.get(setting.id)) is not None
        and result.is_applicable
        and result.value is None
        and not result.error
    ]

    assert not silent, (
        f"{len(silent)} applicable setting(s) detected nothing and reported no reason:\n"
        + "\n".join(silent)
    )


# Categories whose settings configure something Windows itself ships. Whatever
# the machine is, these exist: a registry value, a power scheme index, a shell
# preference. If a whole one of them detects nothing, detection is broken, not
# the machine.
#
# The rest are excluded because their absence is a fact about the host rather
# than a defect, and the distinction is the whole point:
#   game_config, launcher -- the game or launcher is not installed
#   gpu                   -- there is no NVIDIA or AMD adapter
#   audio                 -- there is no audio endpoint (routine on a VM)
#   network               -- this driver does not publish that keyword; covered
#                            far more precisely by test_adapter_snapshot.py,
#                            which asserts the batch itself is alive
#   maintenance           -- the software whose cache it would clear is absent
WINDOWS_OWN_CATEGORIES = frozenset(
    {"core", "timer", "visual", "storage", "power", "system", "game"}
)


def _split(
    settings: list[SettingExecutor], results: dict[str, DetectionResult]
) -> tuple[int, int, int]:
    """Count (detected, absent, failed) over a set of settings."""
    detected = sum(
        1 for s in settings if (r := results.get(s.id)) and r.is_applicable and r.value is not None
    )
    absent = sum(1 for s in settings if (r := results.get(s.id)) and not r.is_applicable)
    failed = sum(
        1
        for s in settings
        if (r := results.get(s.id)) and r.is_applicable and r.value is None and r.error
    )
    return detected, absent, failed


def test_the_scan_is_reported_not_assumed(
    scan: tuple[list[SettingExecutor], dict[str, DetectionResult]],
) -> None:
    """Publish the split, per category — and assert the split accounts for everything.

    The published totals are a fact about the host and stay unasserted: this
    used to assert that 60% of the whole registry detected a value, and that
    failed on the CI runner for an entirely correct reason — a bare Windows VM
    has no games, no launchers and no vendor GPU, so 148 of 326 settings are
    legitimately absent there against 29 on a real gaming machine. A test that
    a clean machine fails is measuring the machine.

    What *is* host-independent is the accounting: every registered setting
    must appear in the scan's answer, and must land in exactly one column of
    the report. The concrete failure guarded is a setting the scan silently
    drops — no result at all — which is the shape of a dead batch that no
    per-column count would ever show, because a missing answer is counted
    nowhere. That is the same blindness the module header records: a naive
    counter cannot tell 'absent' from 'never asked'.

    What a per-column collapse looks like is asserted below and in
    test_adapter_snapshot.py, both of which are also host-independent.
    """
    settings, results = scan
    detected, absent, failed = _split(settings, results)
    silent = sum(
        1
        for s in settings
        if (r := results.get(s.id)) is not None
        and r.is_applicable
        and r.value is None
        and not r.error
    )
    unanswered = [s.id for s in settings if results.get(s.id) is None]

    assert not unanswered, (
        f"{len(unanswered)} setting(s) the registry carries got no answer from the scan "
        "at all — a silently dropped setting is counted in no column and would make "
        f"this report a lie: {unanswered}"
    )
    assert detected + absent + failed + silent == len(settings), (
        "the four states no longer partition the scan: "
        f"{detected} detected + {absent} absent + {failed} failed + {silent} silent "
        f"!= {len(settings)} settings, so a result is counted twice or not at all"
    )

    print(
        f"\nscan: {len(settings)} settings -> {detected} detected, {absent} absent, {failed} failed"
    )
    by_category: dict[str, list[SettingExecutor]] = {}
    for setting in settings:
        by_category.setdefault(setting.category.value, []).append(setting)
    for category in sorted(by_category, key=lambda c: -len(by_category[c])):
        group = by_category[category]
        found, gone, broken = _split(group, results)
        marker = " " if category in WINDOWS_OWN_CATEGORIES else "*"
        print(
            f"  {marker}{category:14} {len(group):4} -> {found:4} detected, {gone:4} absent, {broken:3} failed"
        )
    print("  (* absence here is a property of the host, not a defect)")


def test_no_windows_own_category_detects_nothing(
    scan: tuple[list[SettingExecutor], dict[str, DetectionResult]],
) -> None:
    """A whole family answering 'not applicable' is the shape of a dead batch.

    #31 is the case: `Get-NetAdapterAdvancedProperty` does not expose
    InterfaceIndex, the parser dropped every row, and roughly fifteen settings
    per adapter reported "not available on this hardware" and vanished from the
    UI. Nothing caught it, because an empty result is indistinguishable from
    hardware that genuinely has nothing -- unless the test names a family that
    cannot legitimately be empty.

    These families configure Windows itself, so every one of them has something
    to read on any Windows host. Counting per family rather than over the whole
    registry is what makes this independent of what happens to be installed.
    """
    settings, results = scan
    empty = []

    for category in sorted(WINDOWS_OWN_CATEGORIES):
        group = [s for s in settings if s.category.value == category]
        if not group:
            continue
        detected, absent, failed = _split(group, results)
        if detected == 0:
            empty.append(
                f"  {category}: 0 of {len(group)} detected ({absent} absent, {failed} failed)"
            )

    assert not empty, (
        "A category that ships with Windows detected nothing at all, which is "
        "how the dead per-adapter batch stayed invisible for a release:\n" + "\n".join(empty)
    )


def test_the_scan_reaches_most_of_what_windows_itself_provides(
    scan: tuple[list[SettingExecutor], dict[str, DetectionResult]],
) -> None:
    """A softer floor over the same families, to catch a partial collapse.

    Zero is not the only broken answer -- #31 left some adapter settings working
    while killing fifteen. The bar is a bare majority rather than a high
    percentage because Windows SKUs genuinely differ: a VM has no battery, a
    server image has no Xbox services, and each of those is a correct absence.
    Anything that takes this subset below half is not SKU variance.
    """
    settings, results = scan
    group = [s for s in settings if s.category.value in WINDOWS_OWN_CATEGORIES]
    assert group, "the registry has none of the categories this test is about"

    detected, absent, failed = _split(group, results)
    print(
        f"\nwindows-own: {len(group)} settings -> {detected} detected, {absent} absent, {failed} failed"
    )
    assert detected > len(group) * 0.5, (
        f"Only {detected} of {len(group)} settings that configure Windows itself "
        f"detected a value ({absent} absent, {failed} failed). These have "
        "something to read on every Windows host, so this is a detection "
        "regression rather than a property of this machine."
    )
