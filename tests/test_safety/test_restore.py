"""Tests for fpstune.safety.restore — Windows System Restore Point manager."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from fpstune.safety.restore import RestorePointManager


class TestRestorePointAvailability:
    """RestorePointManager.is_available reflects platform."""

    def test_unavailable_on_non_windows(self):
        """Non-Windows platforms must report is_available=False."""
        with patch("sys.platform", "linux"):
            mgr = RestorePointManager()
            assert mgr.is_available is False

    def test_available_on_windows(self):
        """Windows must report is_available=True."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            assert mgr.is_available is True


class TestCreateRestorePoint:
    """create_restore_point must short-circuit off-Windows and surface subprocess outcome."""

    def test_returns_false_when_unavailable(self):
        """Off-Windows must return False without invoking PowerShell."""
        with patch("sys.platform", "linux"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                assert mgr.create_restore_point() is False
                mock_run.assert_not_called()

    def test_returns_true_on_powershell_success(self):
        """Return code 0 from Checkpoint-Computer must yield True."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                assert mgr.create_restore_point("Test backup") is True

    def test_returns_false_on_powershell_failure(self):
        """Non-zero return code must yield False."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
                assert mgr.create_restore_point("Test") is False

    def test_subprocess_error_caught(self):
        """SubprocessError must be caught and surfaced as False."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(cmd="ps", timeout=120)
                assert mgr.create_restore_point() is False

    def test_oserror_caught(self):
        """OSError (e.g., powershell.exe missing) must be caught and return False."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = OSError("powershell not found")
                assert mgr.create_restore_point() is False

    def test_the_point_is_always_a_modify_settings_one(self):
        """There is no caller-chosen restore point type, and the docstring said there was.

        The signature carried ``_restore_type`` — underscored, never read — while
        the docstring documented a live ``restore_type``. A caller who trusted it
        would have believed it could raise an APPLICATION_INSTALL point; the
        script has always hardcoded MODIFY_SETTINGS. The parameter is gone, so
        the promise and the script now say the same thing.
        """
        import inspect

        params = inspect.signature(RestorePointManager.create_restore_point).parameters
        assert list(params) == ["self", "description"]

        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                mgr.create_restore_point("Before tweaks")

            script = mock_run.call_args.args[0][-1]
            assert "-RestorePointType 'MODIFY_SETTINGS'" in script


class TestDescriptionInjection:
    """SEC-15 regression: the description arrives from a bare query parameter
    and was f-string-interpolated into a DOUBLE-quoted PowerShell string, where
    $(...) evaluates without needing any quote break."""

    def _captured_ps_script(self, mock_run) -> str:
        args = mock_run.call_args.args[0]
        return args[args.index("-Command") + 1]

    def test_description_lands_single_quoted_with_quotes_doubled(self):
        """A $() payload must stay inert data inside a single-quoted literal."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                mgr.create_restore_point("Before Tom's tweaks $(Start-Process calc)")
            script = self._captured_ps_script(mock_run)
        assert "-Description 'Before Tom''s tweaks $(Start-Process calc)'" in script
        assert '-Description "' not in script

    def test_control_characters_are_stripped(self):
        """A newline could end the statement and start a fresh one."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                mgr.create_restore_point("backup\r\nStart-Process calc\x00")
            script = self._captured_ps_script(mock_run)
        assert "-Description 'backupStart-Process calc'" in script

    def test_description_length_is_bounded(self):
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                mgr.create_restore_point("x" * 5000)
            script = self._captured_ps_script(mock_run)
        literal = script.split("-Description '", 1)[1].split("'", 1)[0]
        assert len(literal) == 128

    def test_empty_description_gets_a_fallback(self):
        """An all-control-character description must not produce ''."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                mgr.create_restore_point("\r\n\t")
            script = self._captured_ps_script(mock_run)
        assert "-Description 'fpstune backup'" in script


class TestSessionRestorePoint:
    """One point per session, finished before the first change, and honest about it.

    It was fire-and-forget under a 30 s ceiling: the apply ran beside the snapshot,
    a VSS copy past 30 s was killed and logged "skipped", and Windows' once-a-day
    refusal (a warning, exit code 0) was logged as a point created.
    """

    @staticmethod
    def _run(stdout: str = "", *, side_effect=None):
        from fpstune.safety import restore

        restore._session_outcome = None
        result = MagicMock(returncode=0, stdout=stdout, stderr="")
        with (
            patch("fpstune.safety.restore.sys.platform", "win32"),
            patch("fpstune.safety.restore.system_restore_enabled", return_value=True),
            patch("fpstune.safety.restore.powershell_exe", return_value="powershell.exe"),
            patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True),
            patch(
                "fpstune.safety.restore.subprocess.run",
                return_value=result,
                side_effect=side_effect,
            ) as run,
            patch("fpstune.utils.logger.log_activity") as log,
        ):
            first = restore.ensure_session_restore_point()
            second = restore.ensure_session_restore_point()
        restore._session_outcome = None
        return first, second, run, [c.args for c in log.call_args_list]

    def test_a_new_point_is_reported_created(self) -> None:
        outcome, _, _, logged = self._run("created|412\n")
        assert outcome == "created"
        assert logged[-1][1] == "success"

    def test_windows_once_a_day_refusal_is_not_a_created_point(self) -> None:
        outcome, _, _, logged = self._run("recent|2026-10-05 08:12\n")
        assert outcome == "recent"
        assert "already holds one from 2026-10-05 08:12" in logged[-1][0]

    def test_a_slow_snapshot_gets_minutes_not_seconds(self) -> None:
        _, _, run, _ = self._run("created|1\n")
        assert run.call_args.kwargs["timeout"] >= 300

    def test_a_timeout_is_named_as_one(self) -> None:
        expired = subprocess.TimeoutExpired(cmd="powershell", timeout=600)
        outcome, _, _, logged = self._run(side_effect=expired)
        assert outcome == "timeout"
        assert "did not finish within 10 minutes" in logged[-1][0]

    def test_the_session_makes_one_point_not_one_per_change(self) -> None:
        first, second, run, _ = self._run("created|7\n")
        assert first == second == "created"
        run.assert_called_once()

    def test_the_checkpoint_is_bracketed_by_the_point_list(self) -> None:
        _, _, run, _ = self._run("created|7\n")
        script = run.call_args.args[0][-1]
        assert script.index("Get-ComputerRestorePoint") < script.index("Checkpoint-Computer")
        assert "SequenceNumber -gt $before" in script

    def test_system_protection_off_skips_without_running_powershell(self) -> None:
        from fpstune.safety import restore

        restore._session_outcome = None
        with (
            patch("fpstune.safety.restore.sys.platform", "win32"),
            patch("fpstune.safety.restore.system_restore_enabled", return_value=False),
            patch("fpstune.safety.restore.subprocess.run") as run,
            patch("fpstune.utils.logger.log_activity"),
        ):
            assert restore.ensure_session_restore_point() == "off"
        restore._session_outcome = None
        run.assert_not_called()
