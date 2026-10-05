"""Raw state capture and restore: the exact stored value, or its absence."""

from __future__ import annotations

import contextlib
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from fpstune.safety import raw_state
from fpstune.settings.base import DetectType


def _registry_setting(path: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id="test:raw",
        apply_type=DetectType.REGISTRY,
        apply_command="",
        apply_args={"path": path, "name": name, "hive": "HKCU", "type": "REG_DWORD"},
    )


def _service_setting(service: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"services:{service}",
        apply_type=DetectType.POWERSHELL,
        apply_command="service_toggle",
        apply_args={"service": service, "start_mode": "auto"},
    )


class TestServiceRestore:
    @pytest.mark.parametrize(
        ("raw", "mode"),
        [
            ({"start": 2, "delayed": True}, "delayed-auto"),
            ({"start": 2, "delayed": False}, "auto"),
            ({"start": 3, "delayed": False}, "demand"),
            ({"start": 4, "delayed": False}, "disabled"),
        ],
    )
    def test_the_recorded_start_type_is_set_exactly(self, raw: dict, mode: str) -> None:
        calls: list[list[str]] = []

        def run(args, *_args, **_kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=0)

        with (
            patch.object(sys, "platform", "win32"),
            patch("fpstune.utils.process_watch.run", side_effect=run),
            patch("fpstune.safety.raw_state.subprocess.CREATE_NO_WINDOW", 0, create=True),
        ):
            ok, error = raw_state.restore(
                _service_setting("WSearch"), {"kind": "service", "present": True, **raw}
            )

        assert (ok, error) == (True, None)
        assert calls[0][1:] == ["config", "WSearch", "start=", mode]
        assert calls[0][0].lower().endswith("sc.exe")

    def test_a_failed_sc_call_is_reported(self) -> None:
        with (
            patch.object(sys, "platform", "win32"),
            patch(
                "fpstune.utils.process_watch.run",
                return_value=SimpleNamespace(returncode=5),
            ),
            patch("fpstune.safety.raw_state.subprocess.CREATE_NO_WINDOW", 0, create=True),
        ):
            ok, error = raw_state.restore(
                _service_setting("SysMain"),
                {"kind": "service", "present": True, "start": 2, "delayed": False},
            )

        assert ok is False
        assert "exit code 5" in (error or "")

    def test_a_service_that_did_not_exist_needs_nothing(self) -> None:
        with patch.object(sys, "platform", "win32"):
            assert raw_state.restore(
                _service_setting("Fax"), {"kind": "service", "present": False}
            ) == (True, None)


@pytest.mark.skipif(sys.platform != "win32", reason="real registry round trip")
class TestRegistryRoundTrip:
    KEY = r"Software\fpstune-test\raw-state"

    @pytest.fixture(autouse=True)
    def _clean(self):
        import winreg

        yield
        with contextlib.suppress(OSError):
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, self.KEY)

    def test_a_value_comes_back_exactly(self) -> None:
        import winreg

        setting = _registry_setting(self.KEY, "Value")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.KEY) as key:
            winreg.SetValueEx(key, "Value", 0, winreg.REG_DWORD, 2)
        captured = raw_state.capture(setting)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.KEY) as key:
            winreg.SetValueEx(key, "Value", 0, winreg.REG_DWORD, 24)

        assert raw_state.restore(setting, captured) == (True, None)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY) as key:
            assert winreg.QueryValueEx(key, "Value") == (2, winreg.REG_DWORD)

    def test_an_absent_value_is_deleted_again(self) -> None:
        import winreg

        setting = _registry_setting(self.KEY, "Value")
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.KEY).Close()
        captured = raw_state.capture(setting)
        assert captured == {"kind": "registry", "present": False}
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.KEY) as key:
            winreg.SetValueEx(key, "Value", 0, winreg.REG_DWORD, 3)

        assert raw_state.restore(setting, captured) == (True, None)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY) as key, pytest.raises(OSError):
            winreg.QueryValueEx(key, "Value")
