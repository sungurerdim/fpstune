"""Identifiers must not outlive the flag that lets anyone read them (issue #20).

``debug_powershell`` and ``debug_log`` once appended full command text, command
output and hardware identifiers into a 500-entry ring buffer unconditionally,
for a debug API that has since been removed. With no reader left the buffer is
gone too, and nothing the helpers are handed may stay resident in the module.

The other two failures covered here: the component log files had no size cap,
and the log directory fell back to ``Path.cwd()`` for a frozen build, which for
an executable that requests elevation can be ``System32``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpstune.utils import debug as debug_module

_MAC = "00-11-22-33-44-55"
_INSTANCE = "PCI\\VEN_10EC&DEV_8168"


@pytest.fixture(autouse=True)
def clean_debug_state(monkeypatch):
    """Each test starts with an unresolved log directory and no writers."""
    monkeypatch.setattr(debug_module, "_LOG_DIR", None)
    monkeypatch.setattr(debug_module, "_log_writers", {})


def _module_state_text() -> str:
    """Everything the module holds at module level, as text."""
    return repr({k: v for k, v in vars(debug_module).items() if not k.startswith("__")})


class TestNothingIsKeptInMemory:
    """The debug API that read a 500-entry buffer is gone, so no buffer may exist:
    an identifier handed to the debug helpers must never be held by the module."""

    @pytest.mark.parametrize("enabled", [False, True])
    def test_identifiers_are_not_retained_by_the_module(
        self, monkeypatch, tmp_path, enabled: bool
    ) -> None:
        monkeypatch.setattr(debug_module, "DEBUG_ENABLED", enabled)
        monkeypatch.setattr(debug_module, "_LOG_DIR", tmp_path)

        debug_module.debug_powershell(
            "Get-NetAdapter | Select-Object MacAddress", f"MacAddress : {_MAC}", True
        )
        debug_module.debug_log("hardware", "adapter", {"instance_id": _INSTANCE})
        with debug_module.debug_context("detect_monitors", "hardware") as ctx:
            ctx.set_detail("hardware_id", _MAC)

        for writer in debug_module._log_writers.values():
            for handler in writer.handlers:
                handler.close()
        state = _module_state_text()
        assert _MAC not in state
        assert "VEN_10EC" not in state

    def test_nothing_reaches_disk_while_debug_is_off(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(debug_module, "DEBUG_ENABLED", False)
        monkeypatch.setattr(debug_module, "_LOG_DIR", tmp_path)

        debug_module.debug_powershell("Get-NetAdapter", f"MacAddress : {_MAC}", True)
        debug_module.debug_log("hardware", "adapter", {"instance_id": _INSTANCE})

        assert list(tmp_path.iterdir()) == []


class TestComponentLogsRotate:
    def test_a_long_session_cannot_grow_a_log_without_bound(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(debug_module, "DEBUG_ENABLED", True)
        monkeypatch.setattr(debug_module, "_LOG_DIR", tmp_path)
        monkeypatch.setattr(debug_module, "_LOG_MAX_BYTES", 2048)
        monkeypatch.setattr(debug_module, "_LOG_BACKUP_COUNT", 1)

        for index in range(400):
            debug_module.debug_log("powershell", f"command {index} " + "x" * 100)

        for handler in debug_module._log_writers["powershell.log"].handlers:
            handler.close()

        live = tmp_path / "powershell.log"
        assert live.stat().st_size <= 4096
        assert (tmp_path / "powershell.log.1").exists()
        assert not (tmp_path / "powershell.log.2").exists()

    def test_the_writer_is_created_once_per_file(self, monkeypatch, tmp_path) -> None:
        """A fresh handler per call would leak file handles for the whole run."""
        monkeypatch.setattr(debug_module, "DEBUG_ENABLED", True)
        monkeypatch.setattr(debug_module, "_LOG_DIR", tmp_path)

        first = debug_module._log_writer(tmp_path, "settings.log")
        second = debug_module._log_writer(tmp_path, "settings.log")

        assert first is second
        assert len(first.handlers) == 1
        for handler in first.handlers:
            handler.close()


class TestLogDirectoryNeverFallsBackToTheWorkingDirectory:
    def test_a_frozen_build_writes_under_the_user_profile(self, monkeypatch, tmp_path) -> None:
        """`__file__` lives under sys._MEIPASS when frozen, so the pyproject walk
        can never match and the old fallback was the elevated process's cwd."""
        monkeypatch.setattr("fpstune.utils.runtime.is_frozen", lambda: True)
        monkeypatch.setattr("fpstune.utils.config.get_config_dir", lambda: tmp_path / ".fpstune")
        monkeypatch.chdir(tmp_path)

        resolved = debug_module._resolve_log_dir()

        assert resolved == tmp_path / ".fpstune" / "logs"
        assert resolved != Path.cwd() / "logs"

    def test_a_source_checkout_still_logs_beside_its_own_tree(self, monkeypatch) -> None:
        monkeypatch.setattr("fpstune.utils.runtime.is_frozen", lambda: False)

        resolved = debug_module._resolve_log_dir()

        assert resolved.name == "logs"
        assert (resolved.parent / "pyproject.toml").exists()

    def test_resolution_happens_once_even_under_concurrent_callers(
        self, monkeypatch, tmp_path
    ) -> None:
        """The read and the assignment of the module global were separate steps,
        so two threads could both run the clear — the second deleting what the
        first had already written."""
        import threading

        calls: list[int] = []

        def _slow_resolve() -> Path:
            calls.append(1)
            threading.Event().wait(0.05)
            return tmp_path / "logs"

        monkeypatch.setattr(debug_module, "_resolve_log_dir", _slow_resolve)

        results: list[Path] = []
        threads = [
            threading.Thread(target=lambda: results.append(debug_module._get_log_dir()))
            for _ in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(calls) == 1
        assert set(results) == {tmp_path / "logs"}


class TestDebugFileWritesStayGated:
    def test_no_file_is_created_while_debug_is_off(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(debug_module, "DEBUG_ENABLED", False)
        monkeypatch.setattr(debug_module, "_LOG_DIR", tmp_path)

        debug_module._write_to_file("powershell", "Get-NetAdapter", {"mac": "00-11-22-33-44-55"})

        assert list(tmp_path.iterdir()) == []

    def test_the_component_map_still_decides_the_file(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(debug_module, "DEBUG_ENABLED", True)
        monkeypatch.setattr(debug_module, "_LOG_DIR", tmp_path)

        debug_module._write_to_file("hardware", "monitor detected")

        for writer in debug_module._log_writers.values():
            for handler in writer.handlers:
                handler.close()

        assert "monitor detected" in (tmp_path / "hardware.log").read_text(encoding="utf-8")
        assert "monitor detected" in (tmp_path / "debug.log").read_text(encoding="utf-8")
