"""Tests for fpstune.safety.restore — Windows System Restore Point manager."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from fpstune.safety.restore import RestorePointInfo, RestorePointManager


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


class TestCreateRestorePointWmi:
    """WMI fallback path mirrors PowerShell path semantics."""

    def test_unavailable_returns_false(self):
        """Off-Windows must short-circuit to False."""
        with patch("sys.platform", "linux"):
            mgr = RestorePointManager()
            assert mgr.create_restore_point_wmi() is False

    def test_success_returns_true(self):
        """wmic returncode=0 must yield True."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
                assert mgr.create_restore_point_wmi() is True

    def test_failure_returns_false(self):
        """Non-zero returncode must yield False."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
                assert mgr.create_restore_point_wmi() is False


class TestListRestorePoints:
    """list_restore_points parses the pipe-separated PowerShell output."""

    def test_empty_when_unavailable(self):
        """Non-Windows must return [] without subprocess call."""
        with patch("sys.platform", "linux"):
            mgr = RestorePointManager()
            assert mgr.list_restore_points() == []

    def test_empty_on_failure(self):
        """Non-zero returncode must yield empty list."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="err")
                assert mgr.list_restore_points() == []

    def test_parses_pipe_separated_lines(self):
        """Stdout of N|desc|time|type lines must produce N RestorePointInfo objects."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="42|fpstune backup|2026-01-01|MODIFY_SETTINGS\n"
                    "43|System update|2026-01-02|APPLICATION_INSTALL\n",
                    stderr="",
                )
                results = mgr.list_restore_points()

        assert len(results) == 2
        assert results[0].sequence_number == 42
        assert results[0].description == "fpstune backup"
        assert results[1].sequence_number == 43

    def test_skips_malformed_lines(self):
        """Lines without 4 pipe-separated parts must be skipped, not crash."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="incomplete|data\n42|good|2026-01-01|MODIFY_SETTINGS\n",
                    stderr="",
                )
                results = mgr.list_restore_points()

        assert len(results) == 1
        assert results[0].sequence_number == 42

    def test_skips_lines_with_non_integer_sequence(self):
        """Lines where sequence_number isn't an int must be skipped, not crash."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="not_a_number|x|t|y\n7|legit|t|y\n",
                    stderr="",
                )
                results = mgr.list_restore_points()

        assert len(results) == 1
        assert results[0].sequence_number == 7


class TestIsSystemRestoreEnabled:
    """is_system_restore_enabled scans PowerShell stdout for 'enabled'."""

    def test_returns_false_when_unavailable(self):
        """Non-Windows platforms must return False."""
        with patch("sys.platform", "linux"):
            mgr = RestorePointManager()
            assert mgr.is_system_restore_enabled() is False

    def test_returns_true_when_stdout_says_enabled(self):
        """stdout containing 'enabled' must yield True."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="enabled", stderr="")
                assert mgr.is_system_restore_enabled() is True

    def test_returns_false_when_stdout_says_disabled(self):
        """stdout without 'enabled' must yield False."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="disabled", stderr="")
                assert mgr.is_system_restore_enabled() is False


class TestGetRestorePointByFpstune:
    """get_restore_point_by_fpstune scans for 'fpstune' (case-insensitive) in description."""

    def test_returns_first_fpstune_match(self):
        """Must return the first restore point whose description contains 'fpstune'."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            stub_points = [
                RestorePointInfo(
                    sequence_number=1,
                    description="System update",
                    creation_time="t1",
                    restore_point_type="APP",
                ),
                RestorePointInfo(
                    sequence_number=2,
                    description="fpstune optimization backup",
                    creation_time="t2",
                    restore_point_type="MODIFY",
                ),
            ]
            with patch.object(mgr, "list_restore_points", return_value=stub_points):
                result = mgr.get_restore_point_by_fpstune()
            assert result is not None
            assert result.sequence_number == 2

    def test_returns_none_when_no_fpstune_point(self):
        """No 'fpstune' description must yield None."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            stub_points = [
                RestorePointInfo(
                    sequence_number=1,
                    description="System update",
                    creation_time="t1",
                    restore_point_type="APP",
                ),
            ]
            with patch.object(mgr, "list_restore_points", return_value=stub_points):
                assert mgr.get_restore_point_by_fpstune() is None

    def test_match_is_case_insensitive(self):
        """Description with mixed case 'FPSTUNE' must still match."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            stub_points = [
                RestorePointInfo(
                    sequence_number=1,
                    description="FPSTUNE OPTIMIZATION",
                    creation_time="t",
                    restore_point_type="MODIFY",
                ),
            ]
            with patch.object(mgr, "list_restore_points", return_value=stub_points):
                result = mgr.get_restore_point_by_fpstune()
            assert result is not None


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

    def test_wmi_path_strips_embedded_double_quotes(self):
        """wmic quotes the description itself; an embedded quote is the only
        way out of that argument."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
                mgr.create_restore_point_wmi('backup", 100, 12 & del C:\\Windows')
            args = mock_run.call_args.args[0]
        assert '"backup, 100, 12 & del C:\\Windows"' in args


class TestRestoreToPoint:
    """restore_to_point invokes rstrui.exe with the sequence number."""

    def test_returns_false_when_unavailable(self):
        """Non-Windows must return False without subprocess."""
        with patch("sys.platform", "linux"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                assert mgr.restore_to_point(42) is False
                mock_run.assert_not_called()

    def test_invokes_rstrui_with_sequence(self):
        """rstrui.exe must be called with /RUNONCE:<n>."""
        with patch("sys.platform", "win32"):
            mgr = RestorePointManager()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                mgr.restore_to_point(42)

                args = mock_run.call_args.args[0]
                assert args[0] == "rstrui.exe"
                assert "/RUNONCE:42" in args
