"""Tests for fpstune.safety.restore — Windows System Restore Point manager."""

from __future__ import annotations

import subprocess
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from fpstune.safety import restore
from fpstune.safety.restore import RestorePointManager, checkpoint
from fpstune.utils.process_watch import CHANGE, Stalled


class TestRestorePointAvailability:
    """RestorePointManager.is_available reflects platform."""

    def test_unavailable_on_non_windows(self):
        with patch("sys.platform", "linux"):
            assert RestorePointManager().is_available is False

    def test_available_on_windows(self):
        with patch("sys.platform", "win32"):
            assert RestorePointManager().is_available is True


@contextmanager
def _windows(stdout: str = "", *, side_effect=None, enabled: bool = True):
    """A Windows host whose checkpoint script prints ``stdout``."""
    completed = subprocess.CompletedProcess(["powershell"], 0, stdout, "")
    with (
        patch("fpstune.safety.restore.sys.platform", "win32"),
        patch("fpstune.safety.restore.system_restore_enabled", return_value=enabled),
        patch("fpstune.safety.restore.powershell_exe", return_value="powershell.exe"),
        patch(
            "fpstune.safety.restore.process_watch.run",
            return_value=completed,
            side_effect=side_effect,
        ) as run,
        patch("fpstune.utils.logger.log_activity") as log,
    ):
        yield run, log


def _script(run: MagicMock) -> str:
    argv = run.call_args.args[0]
    return str(argv[argv.index("-Command") + 1])


class TestCheckpointIsHonest:
    """Windows' once-a-day refusal is a warning with exit code 0; it was read as
    success. The point list before and after decides instead."""

    def test_a_new_point_is_created(self) -> None:
        with _windows("created|412\n"):
            outcome = checkpoint("x")
        assert (outcome.kind, outcome.protected) == ("created", True)

    def test_windows_once_a_day_refusal_is_not_a_created_point(self) -> None:
        with _windows("recent|2026-10-05 08:12\n"):
            outcome = checkpoint("x")
        assert outcome.kind == "recent"
        assert "2026-10-05 08:12" in outcome.message

    def test_an_error_line_is_reported_with_its_reason(self) -> None:
        with _windows("error|Access is denied.\n"):
            outcome = checkpoint("x")
        assert (outcome.kind, outcome.protected) == ("error", False)
        assert outcome.message.endswith("Access is denied.")

    def test_a_stall_is_named_as_one(self) -> None:
        stalled = Stalled(["powershell"], CHANGE, "", "")
        with _windows(side_effect=stalled):
            outcome = checkpoint("x")
        assert outcome.kind == "stalled"
        assert "no progress for 5 min" in outcome.message

    def test_a_snapshot_runs_under_the_stall_rule_not_a_clock(self) -> None:
        with _windows("created|1\n") as (run, _):
            checkpoint("x")
        assert run.call_args.args[1] is CHANGE

    def test_the_checkpoint_is_bracketed_by_the_point_list(self) -> None:
        with _windows("created|1\n") as (run, _):
            checkpoint("x")
        script = _script(run)
        assert script.index("Get-ComputerRestorePoint") < script.index("Checkpoint-Computer")
        assert "SequenceNumber -gt $before" in script

    def test_the_point_is_always_a_modify_settings_one(self) -> None:
        with _windows("created|1\n") as (run, _):
            checkpoint("Before tweaks")
        assert "-RestorePointType 'MODIFY_SETTINGS'" in _script(run)

    def test_system_protection_off_skips_without_running_powershell(self) -> None:
        with _windows(enabled=False) as (run, _):
            outcome = checkpoint("x")
        assert outcome.kind == "off"
        run.assert_not_called()


class TestDescriptionInjection:
    """SEC-15 regression: the description arrives from a bare query parameter
    and was f-string-interpolated into a DOUBLE-quoted PowerShell string, where
    $(...) evaluates without needing any quote break."""

    def _script_for(self, description: str) -> str:
        with _windows("created|1\n") as (run, _):
            RestorePointManager().create_restore_point(description)
        return _script(run)

    def test_description_lands_single_quoted_with_quotes_doubled(self):
        script = self._script_for("Before Tom's tweaks $(Start-Process calc)")
        assert "-Description 'Before Tom''s tweaks $(Start-Process calc)'" in script
        assert '-Description "' not in script

    def test_control_characters_are_stripped(self):
        script = self._script_for("backup\r\nStart-Process calc\x00")
        assert "-Description 'backupStart-Process calc'" in script

    def test_description_length_is_bounded(self):
        script = self._script_for("x" * 5000)
        literal = script.split("-Description '", 1)[1].split("'", 1)[0]
        assert len(literal) == 128

    def test_empty_description_gets_a_fallback(self):
        assert "-Description 'fpstune backup'" in self._script_for("\r\n\t")


class TestSessionRestorePoint:
    """One point per session, finished before the first change.

    It was fire-and-forget: the apply ran beside the snapshot, and every apply,
    reset and undo started a fresh attempt.
    """

    def test_the_session_makes_one_point_not_one_per_change(self) -> None:
        restore._session_outcome = None
        try:
            with _windows("created|7\n") as (run, _):
                first = restore.ensure_session_restore_point()
                second = restore.ensure_session_restore_point()
        finally:
            restore._session_outcome = None
        assert first is second and first.kind == "created"
        run.assert_called_once()
