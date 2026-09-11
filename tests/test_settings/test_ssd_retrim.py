"""`maintenance:ssd_retrim` — the row that notices Windows stopped optimizing.

Windows runs `ScheduledDefrag` weekly, and on an SSD that run is a retrim: the
pass that tells the drive which blocks are free again. When the schedule stops —
a disabled task, a machine that never idles, another "optimizer" that turned it
off — nothing says so. The drive keeps working and gradually loses sustained
write speed as its spare area fills with blocks it still believes are in use.

Two things are asserted here and neither is cosmetic.

The **reading contract** is rendered verbatim by the UI, so its four shapes are
part of the interface: `overdue|never`, `overdue|<n> days`, `ok|<n> days`, and
the `not_available` sentinel that means this machine has no SSD volume to
retrim. A fifth shape, or a sentinel spelled locally, is a badge showing raw
text nobody can read.

The **detect/apply agreement** is the subtler one. Both sides enumerate the SSD
volumes, and they must enumerate the same ones: a retrim that skips a volume the
reading counts leaves the row permanently overdue, reporting success each time.
They share one PowerShell fragment so that they cannot drift.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fpstune.settings.applicability import ABSENT_READINGS
from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)
from fpstune.settings.detection import DetectionEngine
from fpstune.settings.executors import CommandExecutor
from fpstune.settings.executors.powershell_actions import (
    _SSD_RETRIM,
    _SSD_TRIM_STATUS,
    _SSD_VOLUMES,
    ACTION_COMMANDS,
    MAINTENANCE_STATUS_SCRIPTS,
    constant_status_reading,
    detect_script,
)
from fpstune.settings.registry import SettingsRegistry

SETTING_ID = "maintenance:ssd_retrim"


@pytest.fixture(scope="module")
def registry() -> SettingsRegistry:
    return SettingsRegistry(discover_dynamic=False)


@pytest.fixture(scope="module")
def setting(registry: SettingsRegistry) -> SettingExecutor:
    found = registry.get(SETTING_ID)
    assert found is not None, f"{SETTING_ID} is not registered"
    return found


class TestTheSettingIsRegistered:
    def test_it_is_a_maintenance_action_the_user_runs(self, setting: SettingExecutor) -> None:
        """An action, not a value: there is nothing to set, only a pass to run."""
        assert setting.is_action is True
        assert setting.category is SettingCategory.MAINTENANCE
        assert setting.scope is SettingScope.RECOMMENDED
        assert setting.detect_type is DetectType.POWERSHELL
        assert setting.apply_type is DetectType.POWERSHELL

    def test_it_reaches_the_ssd_trim_reading_and_the_retrim_action(
        self, setting: SettingExecutor
    ) -> None:
        assert setting.detect_command == "maintenance_status"
        assert setting.detect_args == {"type": "ssd_trim"}
        assert setting.apply_command == "ssd_retrim"

    def test_it_claims_something_other_than_stability(self, setting: SettingExecutor) -> None:
        """C2: `stability` alone is not a claim about performance or resources."""
        assert any(key != "stability" for key in setting.impact_scores)
        assert setting.impact_scores["storage_performance"] == "maintained"

    def test_the_reading_passes_through_uncoerced(self, setting: SettingExecutor) -> None:
        """`ok|3 days` is a string, and a `value_map` would have to enumerate days.

        `choices` stays empty for the same reason every other action leaves it
        empty: there is no set of values to pick between.
        """
        assert setting.value_type is SettingValueType.STRING
        assert setting.value_map == {}
        assert setting.choices == ()

    def test_the_apply_gets_more_time_than_the_thirty_second_default(
        self, setting: SettingExecutor
    ) -> None:
        """Measured at 8.4 s and 5.3 s for two volumes of one NVMe SSD.

        A SATA SSD with a fuller volume is slower by a large multiple, and a
        timeout does not stop the retrim — it stops fpstune reading it, so the
        run is reported failed while the drive is still working.
        """
        assert setting.apply_timeout == 600
        assert setting.duration_estimate == "10-60 sec"


class TestTheReadingIsNotAConstant:
    """`maintenance_status` used to be the literal `Write-Output $true`.

    Three settings share that command name, and the executor short-circuits the
    ones whose script is that literal so a cold scan does not spawn a PowerShell
    process to learn a constant. This reading has something to say, so it must
    not be short-circuited — resolving on the command name alone would have
    answered `True` and the row would have shown nothing.
    """

    def test_the_ssd_trim_type_resolves_to_a_real_script(self) -> None:
        resolved = detect_script("maintenance_status", {"type": "ssd_trim"})
        assert resolved == _SSD_TRIM_STATUS
        assert resolved is not None
        assert resolved.strip() != "Write-Output $true"

    def test_it_is_not_answered_without_running(self) -> None:
        assert constant_status_reading("maintenance_status", {"type": "ssd_trim"}) is None

    @pytest.mark.parametrize("maintenance_type", ["sfc", "dism_health"])
    def test_the_other_maintenance_readings_stay_constant(self, maintenance_type: str) -> None:
        """The measured optimization this change could have silently undone."""
        assert constant_status_reading("maintenance_status", {"type": maintenance_type}) == "True"

    def test_the_dispatch_table_only_overrides_what_it_names(self) -> None:
        assert set(MAINTENANCE_STATUS_SCRIPTS) == {"ssd_trim"}

    def test_the_executor_runs_the_trim_script_and_not_the_literal(
        self, setting: SettingExecutor
    ) -> None:
        """End to end: what actually reaches PowerShell is the trim reading."""
        with patch(
            "fpstune.settings.executors.powershell.PowerShellExecutor._run",
            return_value=(True, "ok|3 days"),
        ) as run:
            value, error = CommandExecutor.detect(setting)

        assert (value, error) == ("ok|3 days", None)
        run.assert_called_once()
        sent = run.call_args.args[0]
        assert "Dfrg" in sent
        assert "LastRunTime" in sent
        assert "Write-Output $true" not in sent


class TestTheReadingContract:
    """The four shapes the UI renders, and the one that hides the row."""

    @pytest.mark.parametrize(
        "reading",
        ["overdue|never", "overdue|23 days", "overdue|14 days", "ok|3 days", "ok|0 days"],
    )
    def test_a_reading_reaches_the_ui_unchanged(
        self, setting: SettingExecutor, reading: str
    ) -> None:
        """Verbatim, because the badge shows the string the script produced."""
        with patch(
            "fpstune.settings.executors.powershell.PowerShellExecutor._run",
            return_value=(True, reading),
        ):
            assert CommandExecutor.detect(setting) == (reading, None)

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_no_ssd_volume_hides_the_row(self, mock_detect: MagicMock) -> None:
        """A machine with only spinning disks must not be offered a retrim.

        `not_available` is one of the four `ABSENT_READINGS` spellings, so
        detection turns it into `is_applicable=False` rather than into a badge
        reading "not_available".
        """
        mock_detect.return_value = ("not_available", None)
        engine = DetectionEngine(max_workers=1)
        setting = _minimal_action()

        result = engine.detect_all([setting])[SETTING_ID]

        assert result.is_applicable is False
        assert result.value is None

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_an_overdue_reading_keeps_the_row(self, mock_detect: MagicMock) -> None:
        """The mirror of the test above: `overdue|never` is an answer, not an absence.

        Without this, a sentinel spelled a little too loosely would hide exactly
        the machines the row exists for.
        """
        mock_detect.return_value = ("overdue|never", None)
        engine = DetectionEngine(max_workers=1)
        setting = _minimal_action()

        result = engine.detect_all([setting])[SETTING_ID]

        assert result.is_applicable is True
        assert result.value == "overdue|never"

    def test_the_script_emits_every_shape_and_no_other(self) -> None:
        """Each branch of the reading, matched against the script that writes it."""
        assert "Write-Output 'not_available'" in _SSD_TRIM_STATUS
        assert "Write-Output 'overdue|never'" in _SSD_TRIM_STATUS
        assert "'overdue|{0} days'" in _SSD_TRIM_STATUS
        assert "'ok|{0} days'" in _SSD_TRIM_STATUS

    def test_the_sentinel_is_the_shared_spelling(self) -> None:
        """Never re-spelled locally; `applicability.py` owns the set."""
        assert "not_available" in ABSENT_READINGS

    def test_the_threshold_is_two_missed_weekly_runs(self) -> None:
        """14 days, and the comment above the script says why it is 14 and not 30."""
        assert "$thresholdDays = 14" in _SSD_TRIM_STATUS


class TestTheSourceOfTheLastRunTime:
    """The registry key, decoded as the SYSTEMTIME it is.

    The Application event log was the obvious alternative and it is the wrong
    one: on the machine this was written on it held a single record and zero
    Defrag events, while the registry still remembered a retrim from three days
    earlier. An event log rolls.
    """

    def test_it_reads_the_defrag_statistics_key(self) -> None:
        assert "HKLM:\\SOFTWARE\\Microsoft\\Dfrg\\Statistics" in _SSD_TRIM_STATUS
        assert ".LastRunTime" in _SSD_TRIM_STATUS

    def test_it_does_not_ask_the_event_log(self) -> None:
        assert "Get-WinEvent" not in _SSD_TRIM_STATUS

    def test_it_decodes_the_systemtime_words_and_skips_the_day_of_week(self) -> None:
        """SYSTEMTIME is wYear, wMonth, wDayOfWeek, wDay, ... — bytes 4-5 are the
        day of the week, so the day of the month starts at byte 6. Reading byte 4
        as the day turns every timestamp into a weekday number between 0 and 6.
        """
        assert "$year   = $stat[0]  + $stat[1]  * 256" in _SSD_TRIM_STATUS
        assert "$month  = $stat[2]  + $stat[3]  * 256" in _SSD_TRIM_STATUS
        assert "$day    = $stat[6]  + $stat[7]  * 256" in _SSD_TRIM_STATUS
        assert "$stat[4]" not in _SSD_TRIM_STATUS

    def test_an_all_zero_structure_is_never_read_as_a_date(self) -> None:
        """A volume Windows has never optimized carries sixteen zero bytes.

        Year 0 is not a date, and building one would either throw or land in the
        first century, which reads as an age of 700000 days rather than "never".
        """
        assert "if ($year -gt 1900) {" in _SSD_TRIM_STATUS

    def test_a_backwards_clock_cannot_produce_a_negative_age(self) -> None:
        assert "if ($age -lt 0) { $age = 0 }" in _SSD_TRIM_STATUS


class TestTheRetrimAction:
    def test_the_action_command_is_registered(self) -> None:
        assert ACTION_COMMANDS["ssd_retrim"] == _SSD_RETRIM

    def test_it_retrims_rather_than_defragments(self) -> None:
        """`-ReTrim` is the SSD pass. A plain `Optimize-Volume` on an SSD would
        be Windows' own choice of pass, and on a volume it misreads as a spinning
        disk that choice is a defragmentation — writes an SSD gains nothing from.
        """
        assert "-ReTrim" in _SSD_RETRIM
        assert "-Defrag" not in _SSD_RETRIM

    def test_progress_reaches_the_streamed_run(self) -> None:
        """`Optimize-Volume` reports progress on the verbose stream, which does
        not reach stdout unless it is redirected there.
        """
        assert "-Verbose" in _SSD_RETRIM
        assert "4>&1" in _SSD_RETRIM
        assert "'Retrimming volume {0}:'" in _SSD_RETRIM

    def test_a_failed_volume_is_named_and_fails_the_run(self) -> None:
        """Reporting success on a partial run is worse than reporting failure:
        the row goes green while a volume stays untrimmed.
        """
        assert "'Volume {0}: retrim failed - {1}'" in _SSD_RETRIM
        assert "'Retrim failed on volume(s): '" in _SSD_RETRIM
        assert _SSD_RETRIM.count("exit 1") == 2

    def test_it_runs_every_ssd_volume_and_not_only_the_system_one(self) -> None:
        assert "foreach ($entry in $ssdVolumes)" in _SSD_RETRIM


class TestDetectAndApplyAgreeOnTheVolumes:
    """One enumeration, used twice.

    Two copies would drift, and the drift has one symptom: a volume the reading
    counts and the action skips leaves the row overdue for ever, reporting a
    successful retrim every time it is pressed.
    """

    def test_both_sides_share_the_one_fragment(self) -> None:
        assert _SSD_VOLUMES in _SSD_TRIM_STATUS
        assert _SSD_VOLUMES in _SSD_RETRIM

    def test_only_volumes_with_a_drive_letter_count(self) -> None:
        """`Optimize-Volume -DriveLetter` cannot address a letterless volume, so
        counting one in the reading would make the row unfixable.
        """
        assert "if (-not $part.DriveLetter) { continue }" in _SSD_VOLUMES

    def test_solid_state_is_derived_from_the_disk_s_own_report(self) -> None:
        """C1: the media type comes from the disk, never from a model list.

        `SpindleSpeed` is the second opinion, for a disk whose `MediaType` is
        `Unspecified` — Windows documents a spindle speed of 0 as solid state.
        """
        assert "$pd.MediaType -eq 'SSD'" in _SSD_VOLUMES
        assert "$pd.SpindleSpeed -eq 0" in _SSD_VOLUMES

    def test_an_external_enclosure_is_left_alone(self) -> None:
        assert "$vol.DriveType -ne 'Fixed'" in _SSD_VOLUMES

    def test_the_volume_guid_comes_from_the_volume_itself(self) -> None:
        """C9: no drive letter, no GUID and no path is written into the source.

        The registry subkey is named for the volume GUID, and the volume reports
        that GUID as its own `Path`.
        """
        assert "$volPath = $vol.Path" in _SSD_VOLUMES
        assert "Volume{" not in _SSD_VOLUMES


def _minimal_action() -> SettingExecutor:
    """The registered setting's shape, without the registry or a live detect."""
    return SettingExecutor(
        id=SETTING_ID,
        category=SettingCategory.MAINTENANCE,
        display_name="SSD TRIM Overdue",
        short_name="SSD retrim",
        description="Tells every SSD which blocks are free again.",
        value_type=SettingValueType.STRING,
        choices=(),
        default_value=False,
        recommended_value=False,
        requires_reboot=False,
        is_action=True,
        current_impact="Overdue: The optimization schedule has not run",
        recommended_impact="Run: Every SSD volume retrimmed",
        scope=SettingScope.RECOMMENDED,
        category_order=26,
        effect="Runs Windows' own retrim on every SSD volume",
        impact_scores={"storage_performance": "maintained"},
        detect_type=DetectType.POWERSHELL,
        detect_command="maintenance_status",
        detect_args={"type": "ssd_trim"},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command="ssd_retrim",
        apply_args={},
        apply_value_map={},
    )
