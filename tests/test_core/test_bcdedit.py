"""Tests for BcdEdit core module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestBcdValue:
    """Tests for BcdValue dataclass."""

    def test_to_dict(self):
        """Test BcdValue.to_dict()."""
        from fpstune.core.bcdedit import BcdValue

        value = BcdValue(name="useplatformclock", value="yes", exists=True)
        result = value.to_dict()

        assert result["name"] == "useplatformclock"
        assert result["value"] == "yes"
        assert result["exists"] is True

    def test_to_dict_not_exists(self):
        """Test BcdValue.to_dict() when value doesn't exist."""
        from fpstune.core.bcdedit import BcdValue

        value = BcdValue(name="useplatformclock", value="", exists=False)
        result = value.to_dict()

        assert result["exists"] is False


class TestBcdEdit:
    """Tests for BcdEdit class."""

    @pytest.fixture
    def bcdedit(self):
        """Create BcdEdit instance with clean cache."""
        from fpstune.core.bcdedit import BcdEdit

        # Clear class-level cache to prevent test pollution
        BcdEdit._enum_cache = None
        BcdEdit._enum_cache_valid = False
        return BcdEdit()

    def test_is_available_non_windows(self):
        """Test is_available returns False on non-Windows."""
        with patch("sys.platform", "linux"):
            from fpstune.core.bcdedit import BcdEdit

            bcd = BcdEdit()
            assert bcd.is_available is False

    @pytest.mark.skipif("sys.platform != 'win32'")
    def test_is_available_windows(self, bcdedit):
        """Test is_available returns True on Windows."""
        assert bcdedit.is_available is True

    def test_settings_defined(self, bcdedit):
        """Test SETTINGS contains expected keys."""
        assert "useplatformclock" in bcdedit.SETTINGS
        assert "useplatformtick" in bcdedit.SETTINGS
        assert "disabledynamictick" in bcdedit.SETTINGS

    def test_settings_have_descriptions(self, bcdedit):
        """Test each setting has description and recommendation."""
        for name, setting in bcdedit.SETTINGS.items():
            assert "description" in setting, f"{name} missing description"
            assert "recommendation" in setting, f"{name} missing recommendation"

    @patch("subprocess.run")
    def test_run_bcdedit_not_available(self, mock_run, bcdedit):
        """Test _run_bcdedit returns error when not available."""
        with patch.object(bcdedit, "_available", False):
            success, output = bcdedit._run_bcdedit("/enum")
            assert success is False
            assert "not available" in output.lower()
            mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_run_bcdedit_success(self, mock_run, bcdedit):
        """Test _run_bcdedit on success."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")

        with patch.object(bcdedit, "_available", True):
            success, output = bcdedit._run_bcdedit("/enum")

        assert success is True
        assert "Success" in output

    @patch("subprocess.run")
    def test_run_bcdedit_failure(self, mock_run, bcdedit):
        """Test _run_bcdedit on failure."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")

        with patch.object(bcdedit, "_available", True):
            success, output = bcdedit._run_bcdedit("/enum")

        assert success is False

    @patch("subprocess.run")
    def test_run_bcdedit_exception(self, mock_run, bcdedit):
        """Test _run_bcdedit handles exceptions."""
        mock_run.side_effect = Exception("Process failed")

        with patch.object(bcdedit, "_available", True):
            success, output = bcdedit._run_bcdedit("/enum")

        assert success is False
        assert "failed" in output.lower()

    def test_get_value_not_available(self, bcdedit):
        """Test get_value returns None when not available."""
        with patch.object(bcdedit, "_available", False):
            result = bcdedit.get_value("useplatformclock")
            assert result is None

    @patch("subprocess.run")
    def test_get_value_exists(self, mock_run, bcdedit):
        """Test get_value when value exists."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="useplatformclock    yes\n",
            stderr="",
        )

        with patch.object(bcdedit, "_available", True):
            result = bcdedit.get_value("useplatformclock")

        assert result is not None
        assert result.exists is True
        assert result.value == "yes"

    @patch("subprocess.run")
    def test_get_value_not_exists(self, mock_run, bcdedit):
        """Test get_value when value doesn't exist."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="identifier    {current}\n",  # No useplatformclock line
            stderr="",
        )

        with patch.object(bcdedit, "_available", True):
            result = bcdedit.get_value("useplatformclock")

        assert result is not None
        assert result.exists is False

    def test_set_value_not_available(self, bcdedit):
        """Test set_value returns False when not available."""
        with patch.object(bcdedit, "_available", False):
            result = bcdedit.set_value("useplatformclock", "yes")
            assert result is False

    @patch("subprocess.run")
    def test_set_value_success(self, mock_run, bcdedit):
        """Test set_value on success."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(bcdedit, "_available", True):
            result = bcdedit.set_value("useplatformclock", "yes")

        assert result is True
        mock_run.assert_called_once()

    def test_delete_value_not_available(self, bcdedit):
        """Test delete_value returns False when not available."""
        with patch.object(bcdedit, "_available", False):
            result = bcdedit.delete_value("useplatformclock")
            assert result is False

    @patch("subprocess.run")
    def test_delete_value_success(self, mock_run, bcdedit):
        """Test delete_value on success."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(bcdedit, "_available", True):
            result = bcdedit.delete_value("useplatformclock")

        assert result is True

    @patch("subprocess.run")
    def test_delete_value_not_found(self, mock_run, bcdedit):
        """Test delete_value when element not found."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="element not found",
        )

        with patch.object(bcdedit, "_available", True):
            result = bcdedit.delete_value("useplatformclock")

        # Should return True when element not found (already deleted)
        assert result is True

    def test_disable_hpet(self, bcdedit):
        """Test disable_hpet calls delete_value."""
        with patch.object(bcdedit, "delete_value", return_value=True) as mock:
            result = bcdedit.disable_hpet()

        assert result is True
        mock.assert_called_once_with("useplatformclock")

    def test_enable_hpet(self, bcdedit):
        """Test enable_hpet calls set_value."""
        with patch.object(bcdedit, "set_value", return_value=True) as mock:
            result = bcdedit.enable_hpet()

        assert result is True
        mock.assert_called_once_with("useplatformclock", "yes")

    def test_disable_dynamic_tick(self, bcdedit):
        """Test disable_dynamic_tick calls set_value."""
        with patch.object(bcdedit, "set_value", return_value=True) as mock:
            result = bcdedit.disable_dynamic_tick()

        assert result is True
        mock.assert_called_once_with("disabledynamictick", "yes")

    def test_enable_dynamic_tick(self, bcdedit):
        """Test enable_dynamic_tick calls delete_value."""
        with patch.object(bcdedit, "delete_value", return_value=True) as mock:
            result = bcdedit.enable_dynamic_tick()

        assert result is True
        mock.assert_called_once_with("disabledynamictick")

    def test_enable_platform_tick(self, bcdedit):
        """Test enable_platform_tick."""
        with patch.object(bcdedit, "set_value", return_value=True) as mock:
            result = bcdedit.enable_platform_tick()

        assert result is True
        mock.assert_called_once_with("useplatformtick", "yes")

    def test_disable_platform_tick(self, bcdedit):
        """Test disable_platform_tick."""
        with patch.object(bcdedit, "delete_value", return_value=True) as mock:
            result = bcdedit.disable_platform_tick()

        assert result is True
        mock.assert_called_once_with("useplatformtick")

    def test_get_timer_settings(self, bcdedit):
        """Test get_timer_settings returns dict."""
        with patch.object(bcdedit, "get_value") as mock:
            from fpstune.core.bcdedit import BcdValue

            mock.return_value = BcdValue("test", "yes", True)

            result = bcdedit.get_timer_settings()

        assert isinstance(result, dict)
        assert len(result) == len(bcdedit.SETTINGS)

    def test_apply_gaming_settings(self, bcdedit):
        """Test apply_gaming_settings."""
        with patch.object(bcdedit, "disable_hpet", return_value=True) as mock:
            result = bcdedit.apply_gaming_settings()

        assert "useplatformclock" in result
        assert result["useplatformclock"] is True
        mock.assert_called_once()

    def test_revert_to_defaults(self, bcdedit):
        """Test revert_to_defaults deletes all settings."""
        with patch.object(bcdedit, "delete_value", return_value=True) as mock:
            result = bcdedit.revert_to_defaults()

        assert len(result) == len(bcdedit.SETTINGS)
        assert all(v is True for v in result.values())
        assert mock.call_count == len(bcdedit.SETTINGS)

    @patch("subprocess.run")
    def test_get_qpc_mode_tsc(self, mock_run, bcdedit):
        """Test get_qpc_mode returns TSC when useplatformclock not set."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(bcdedit, "_available", True):
            result = bcdedit.get_qpc_mode()

        assert "TSC" in result

    @patch("subprocess.run")
    def test_get_qpc_mode_hpet(self, mock_run, bcdedit):
        """Test get_qpc_mode returns HPET when useplatformclock=yes."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="useplatformclock    yes\n",
            stderr="",
        )

        with patch.object(bcdedit, "_available", True):
            result = bcdedit.get_qpc_mode()

        assert "HPET" in result or "platform" in result.lower()
