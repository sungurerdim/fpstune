"""Starting fpstune twice, with no free port, or into a crash."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import click
import pytest

from fpstune import cli


class TestASecondStartOpensTheFirst:
    def test_the_running_instance_is_found_by_asking_its_port(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "fpstune_serve.pid"
        pid_file.write_text(json.dumps({"pid": 4242, "port": 8123}), encoding="utf-8")

        class _Health:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def read(self):
                return json.dumps({"status": "healthy", "subsystems": {}}).encode()

        with (
            patch.object(cli, "_get_pid_file", return_value=str(pid_file)),
            patch("urllib.request.urlopen", return_value=_Health()),
        ):
            assert cli._running_instance_url() == "http://127.0.0.1:8123/ui"

    def test_something_else_on_the_port_is_not_taken_for_fpstune(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "fpstune_serve.pid"
        pid_file.write_text(json.dumps({"pid": 1, "port": 8123}), encoding="utf-8")
        with (
            patch.object(cli, "_get_pid_file", return_value=str(pid_file)),
            patch("urllib.request.urlopen", side_effect=OSError("refused")),
        ):
            assert cli._running_instance_url() is None

    def test_a_second_start_hands_over_and_kills_nothing(self) -> None:
        with (
            patch.object(cli, "_acquire_instance_lock", return_value=None),
            patch.object(cli, "_running_instance_url", return_value="http://127.0.0.1:8000/ui"),
            patch("webbrowser.open") as opened,
        ):
            assert cli._claim_single_instance(open_browser=True) is False
        opened.assert_called_once_with("http://127.0.0.1:8000/ui")
        assert not hasattr(cli, "_kill_previous_instance")


class TestNoFreePort:
    def test_it_fails_loudly_instead_of_returning_a_taken_port(self) -> None:
        """It used to hand back the preferred port, and uvicorn died binding it."""
        with (
            patch("socket.socket.bind", side_effect=OSError("in use")),
            pytest.raises(click.ClickException, match="all in use"),
        ):
            cli._find_free_port(8000, max_attempts=3)


class TestACrashLeavesAReport:
    def test_the_traceback_is_written_and_the_exit_is_non_zero(self, tmp_path: Path) -> None:
        with (
            patch.object(cli, "main", side_effect=RuntimeError("boom")),
            patch("fpstune.utils.config.get_config_dir", return_value=tmp_path),
            pytest.raises(SystemExit) as exited,
        ):
            cli.run()

        assert exited.value.code == 1
        [report] = list((tmp_path / "logs").glob("crash-*.txt"))
        text = report.read_text(encoding="utf-8")
        assert "RuntimeError: boom" in text
        assert "fpstune " in text.splitlines()[0]
