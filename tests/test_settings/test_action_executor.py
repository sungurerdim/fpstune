"""Tests for the streaming action executor (action_executor.py).

The failure this file guards against is an orphaned system process: these
actions are DISM and SFC class, and the subprocess used to have no timeout and
no kill path — a client closing the SSE stream left it running against the
component store with nobody watching, indefinitely.

The subprocess tests run the real Windows path with ``sys.executable`` standing
in for PowerShell: the command is a fixture argument, so nothing here depends
on what is installed on the machine.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest

from fpstune.settings.action_executor import ActionEvent, ActionExecutor

win_only = pytest.mark.skipif(
    sys.platform != "win32",
    reason="the real subprocess path is Windows-only; other platforms simulate",
)


def _executor() -> ActionExecutor:
    # _run_command_streaming never reads the setting; a bare stand-in keeps
    # these tests off the registry.
    return ActionExecutor(MagicMock())


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


async def _drain(gen: AsyncGenerator[ActionEvent, None]) -> list[ActionEvent]:
    events = []
    async for event in gen:
        events.append(event)
    return events


class TestExecuteStreamingGuards:
    async def test_a_non_action_setting_is_refused(self) -> None:
        setting = MagicMock()
        setting.is_action = False

        events = [json.loads(e) async for e in ActionExecutor(setting).execute_streaming()]

        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert events[0]["error"] == "Not an action setting"

    async def test_an_action_with_no_command_reports_it(self) -> None:
        # Registry actions are instant and carry no streamable command; the
        # stream must say so rather than complete silently.
        setting = MagicMock()
        setting.is_action = True
        setting.display_name = "Instant Action"
        setting.apply_type.value = "registry"

        events = [json.loads(e) async for e in ActionExecutor(setting).execute_streaming()]

        assert events[-1]["type"] == "error"
        assert "No command configured" in events[-1]["error"]


@win_only
class TestSubprocessStreaming:
    async def test_ring_buffer_keeps_only_the_last_lines(self) -> None:
        # Every line still reaches the client; only the in-memory tail is
        # bounded. An unbounded list would grow with DISM's output for the
        # whole run.
        executor = _executor()
        events = await _drain(
            executor._run_command_streaming(_py("for i in range(150): print(f'line-{i}')"))
        )

        outputs = [e for e in events if e.type == "output"]
        assert len(outputs) == 150
        assert len(executor._output_lines) == ActionExecutor.MAX_OUTPUT_LINES
        assert executor._output_lines[0] == "line-50"
        assert executor._output_lines[-1] == "line-149"
        assert events[-1].type == "complete"
        assert events[-1].success is True

    async def test_nonzero_exit_is_reported_not_assumed(self) -> None:
        executor = _executor()
        events = await _drain(executor._run_command_streaming(_py("import sys; sys.exit(3)")))

        done = events[-1]
        assert done.type == "complete"
        assert done.success is False
        assert "code 3" in done.error

    async def test_a_stuck_process_is_terminated_at_the_deadline(self) -> None:
        # Before the deadline existed, a process that went quiet held the
        # stream — and the PowerShell behind it — open forever.
        executor = _executor()
        executor.MAX_RUNTIME_SECONDS = 0.5  # instance override; the default is an hour
        events = await _drain(
            executor._run_command_streaming(
                _py("import time; print('started', flush=True); time.sleep(60)")
            )
        )

        assert events[-1].type == "error"
        assert "terminated" in events[-1].error
        assert executor._process is not None
        assert executor._process.returncode is not None, "the timed-out process was left running"

    async def test_closing_the_stream_kills_the_subprocess(self) -> None:
        # A client disconnect closes the generator mid-stream; the process
        # behind it must die with it, not run on orphaned.
        executor = _executor()
        gen = executor._run_command_streaming(
            _py("import time; print('running', flush=True); time.sleep(60)")
        )
        first = await asyncio.wait_for(anext(gen), timeout=30)
        assert first.type == "output"

        await gen.aclose()

        assert executor._process is not None
        assert executor._process.returncode is not None, (
            "the subprocess survived the client disconnect"
        )

    async def test_the_close_reaches_the_subprocess_through_execute_streaming(self) -> None:
        # The route consumes execute_streaming, not _run_command_streaming.
        # Closing the outer generator must chain down to the subprocess kill —
        # an abandoned inner generator would only be cleaned up at GC time,
        # with the process running the whole while.
        setting = MagicMock()
        setting.is_action = True
        setting.display_name = "Long Sleep"
        setting.apply_type.value = "powershell"
        setting.apply_command = "Write-Output ready; Start-Sleep -Seconds 60"
        setting.apply_args = {}

        executor = ActionExecutor(setting)
        gen = executor.execute_streaming()
        try:
            while True:
                event = json.loads(await asyncio.wait_for(anext(gen), timeout=60))
                if event["type"] == "output" and event["line"] == "ready":
                    break
        finally:
            await gen.aclose()

        assert executor._process is not None
        assert executor._process.returncode is not None, (
            "closing the outer stream did not kill the PowerShell process"
        )
