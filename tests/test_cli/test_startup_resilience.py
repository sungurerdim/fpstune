"""Starting fpstune with no free port, or into a crash.

Starting it a second time is ``test_instance_takeover.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import click
import pytest

from fpstune import cli


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
